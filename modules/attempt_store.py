import sqlite3
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from .logger import sshmap_logger


class AttemptStore:
    """SQLite-based store for SSH attempt records.
    
    This stores all SSH attempts (successful or not) in a lightweight SQLite database.
    Much faster than Neo4j for this high-volume write pattern.
    """

    def __init__(self, db_path: str = "output/ssh_attempts.db"):
        self.db_path = db_path
        self._busy_timeout_ms = 60000
        # SQLite supports concurrent readers, but only one writer. Keep writes
        # serialized so high scan concurrency does not create lock storms.
        self._write_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="sshmap-attempt-store",
        )
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database with the required schema."""
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        
        conn = sqlite3.connect(self.db_path, timeout=self._busy_timeout_ms / 1000)
        
        # Enable WAL mode for better concurrency (multiple writers)
        conn.execute("PRAGMA journal_mode=WAL")
        # Increase timeout for lock contention
        conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
        # Reduce fsync frequency for better performance
        conn.execute("PRAGMA synchronous=NORMAL")
        
        cursor = conn.cursor()
        
        # Create attempts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ssh_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_hostname TEXT NOT NULL,
                target_hostname TEXT NOT NULL,
                target_ip TEXT NOT NULL,
                target_port INTEGER NOT NULL,
                username TEXT NOT NULL,
                method TEXT NOT NULL,
                credential TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create index for quick lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_attempt_lookup 
            ON ssh_attempts(source_hostname, target_ip, target_port, username, method, credential)
        """)

        try:
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_attempt_unique
                ON ssh_attempts(source_hostname, target_ip, target_port, username, method, credential)
            """)
        except sqlite3.IntegrityError:
            sshmap_logger.debug(
                "[ATTEMPT_STORE] Existing duplicate rows prevent unique index creation. "
                "New writes will still be deduplicated."
            )
        
        conn.commit()
        conn.close()

    async def record_attempt(
        self,
        source_hostname: str,
        target_hostname: str,
        target_ip: str,
        target_port: int,
        username: str,
        method: str,
        credential: str,
        success: bool,
    ):
        """Record an SSH attempt asynchronously."""
        # Run the database write in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._write_executor,
            self._record_attempt_sync,
            source_hostname,
            target_hostname,
            target_ip,
            target_port,
            username,
            method,
            credential,
            success,
        )

    def _record_attempt_sync(
        self,
        source_hostname: str,
        target_hostname: str,
        target_ip: str,
        target_port: int,
        username: str,
        method: str,
        credential: str,
        success: bool,
    ):
        """Synchronously record an SSH attempt."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=self._busy_timeout_ms / 1000)
            # Configure for high concurrency
            conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
            conn.execute("PRAGMA synchronous=NORMAL")
            
            cursor = conn.cursor()
            
            cursor.execute(
                """
                INSERT OR IGNORE INTO ssh_attempts
                (source_hostname, target_hostname, target_ip, target_port, username, method, credential, success)
                SELECT ?, ?, ?, ?, ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM ssh_attempts
                    WHERE source_hostname = ?
                      AND target_ip = ?
                      AND target_port = ?
                      AND username = ?
                      AND method = ?
                      AND credential = ?
                )
                """,
                (
                    source_hostname,
                    target_hostname,
                    target_ip,
                    target_port,
                    username,
                    method,
                    credential,
                    success,
                    source_hostname,
                    target_ip,
                    target_port,
                    username,
                    method,
                    credential,
                ),
            )

            if success:
                cursor.execute(
                    """
                    UPDATE ssh_attempts
                    SET success = 1, target_hostname = ?
                    WHERE source_hostname = ?
                      AND target_ip = ?
                      AND target_port = ?
                      AND username = ?
                      AND method = ?
                      AND credential = ?
                      AND success = 0
                    """,
                    (
                        target_hostname,
                        source_hostname,
                        target_ip,
                        target_port,
                        username,
                        method,
                        credential,
                    ),
                )
            
            conn.commit()
            conn.close()
        except Exception as e:
            sshmap_logger.debug(
                f"[ATTEMPT_STORE] Failed to record attempt: {type(e).__name__}: {e}"
            )

    def get_attempted_credentials(
        self, source_hostname: str, target_ip: str, target_port: int
    ) -> set:
        """Get all attempted (username, method, secret) tuples for a target.
        
        Returns a set of (username, method, credential) tuples that have been attempted.
        Credentials are actual values stored in the database.
        """
        try:
            conn = sqlite3.connect(self.db_path, timeout=self._busy_timeout_ms / 1000)
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT DISTINCT username, method, credential
                FROM ssh_attempts
                WHERE source_hostname = ? AND target_ip = ? AND target_port = ?
                """,
                (source_hostname, target_ip, target_port),
            )
            
            results = cursor.fetchall()
            conn.close()
            
            # Return set of (username, method, credential) tuples
            return set((username, method, credential) for username, method, credential in results)
        except Exception as e:
            sshmap_logger.debug(
                f"[ATTEMPT_STORE] Failed to get attempted credentials: {type(e).__name__}: {e}"
            )
            return set()

    def get_successful_attempts(
        self, source_hostname: str, target_ip: str, target_port: int
    ) -> set:
        """Get all successful attempts for a target.
        
        Returns a set of (username, method, credential) tuples that were successful.
        """
        try:
            conn = sqlite3.connect(self.db_path, timeout=self._busy_timeout_ms / 1000)
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT DISTINCT username, method, credential FROM ssh_attempts
                WHERE source_hostname = ? AND target_ip = ? AND target_port = ? AND success = 1
                """,
                (source_hostname, target_ip, target_port),
            )
            
            results = cursor.fetchall()
            conn.close()
            
            # Return set of (username, method, credential) tuples
            return set((username, method, credential) for username, method, credential in results)
        except Exception as e:
            sshmap_logger.debug(
                f"[ATTEMPT_STORE] Failed to get successful attempts: {type(e).__name__}: {e}"
            )
            return set()

    def close(self):
        """Close the database connection."""
        self._write_executor.shutdown(wait=True)
