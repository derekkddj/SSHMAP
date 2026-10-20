import sqlite3
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from .logger import sshmap_logger
from .attempt_status import ATTEMPT_STATUSES


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
                status TEXT NOT NULL DEFAULT 'unknown',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Serialize migration inspection and backfill across store instances.
        cursor.execute("BEGIN IMMEDIATE")
        # Additive migration: retain every legacy row, including duplicates.
        columns = {row[1] for row in cursor.execute("PRAGMA table_info(ssh_attempts)")}
        if "status" not in columns:
            cursor.execute("ALTER TABLE ssh_attempts ADD COLUMN status TEXT NOT NULL DEFAULT 'unknown'")
            cursor.execute("UPDATE ssh_attempts SET status = 'success' WHERE success = 1")

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
        status: str = None,
    ):
        """Record latest status/time; success remains true once a tuple succeeds.

        Unclassified failures from older callers are unknown and remain retryable.
        """
        status = self._validate_status(success, status)
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
            status,
        )

    @staticmethod
    def _validate_status(success, status):
        if status is None:
            status = "success" if success else "unknown"
        if status not in ATTEMPT_STATUSES:
            raise ValueError(f"Invalid SSH attempt status: {status}")
        if bool(success) != (status == "success"):
            raise ValueError("success must agree with the latest attempt status")
        return status

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
        status: str = None,
    ):
        """Synchronously record an SSH attempt."""
        status = self._validate_status(success, status)
        try:
            conn = sqlite3.connect(self.db_path, timeout=self._busy_timeout_ms / 1000)
            # Configure for high concurrency
            conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
            conn.execute("PRAGMA synchronous=NORMAL")
            
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            
            cursor.execute(
                """
                INSERT OR IGNORE INTO ssh_attempts
                (source_hostname, target_hostname, target_ip, target_port, username, method, credential, success, status)
                SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                    status,
                    source_hostname,
                    target_ip,
                    target_port,
                    username,
                    method,
                    credential,
                ),
            )

            # BEGIN IMMEDIATE serializes the read/insert/update fallback even
            # when legacy duplicates prevented creating the unique index.
            # Update all matching legacy rows without deleting historical data.
            cursor.execute(
                """
                UPDATE ssh_attempts
                SET success = MAX(success, ?), status = ?,
                    target_hostname = CASE WHEN ? OR success = 0 THEN ? ELSE target_hostname END,
                    timestamp = CURRENT_TIMESTAMP
                WHERE source_hostname = ? AND target_ip = ? AND target_port = ?
                  AND username = ? AND method = ? AND credential = ?
                """,
                (success, status, success, target_hostname, source_hostname,
                 target_ip, target_port, username, method, credential),
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
        """Get tuples with a definitive latest success or authentication rejection.

        Transport, timeout, session, and unknown failures are retried next scan.
        The historical ever-success flag does not override the latest status.
        """
        try:
            conn = sqlite3.connect(self.db_path, timeout=self._busy_timeout_ms / 1000)
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT DISTINCT username, method, credential
                FROM ssh_attempts
                WHERE source_hostname = ? AND target_ip = ? AND target_port = ?
                  AND status IN ('success', 'auth_failed')
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
