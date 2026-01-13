import sqlite3
import os
from pathlib import Path
import asyncio
from .logger import sshmap_logger


class AttemptStore:
    """SQLite-based store for SSH attempt records.
    
    This stores all SSH attempts (successful or not) in a lightweight SQLite database.
    Much faster than Neo4j for this high-volume write pattern.
    """

    def __init__(self, db_path: str = "output/ssh_attempts.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database with the required schema."""
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        
        # Enable WAL mode for better concurrency (multiple writers)
        conn.execute("PRAGMA journal_mode=WAL")
        # Increase timeout for lock contention
        conn.execute("PRAGMA busy_timeout=5000")  # 5 second timeout
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
            None,
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
            conn = sqlite3.connect(self.db_path)
            # Configure for high concurrency
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA synchronous=NORMAL")
            
            cursor = conn.cursor()
            
            cursor.execute(
                """
                INSERT INTO ssh_attempts 
                (source_hostname, target_hostname, target_ip, target_port, username, method, credential, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (source_hostname, target_hostname, target_ip, target_port, username, method, credential, success),
            )
            
            conn.commit()
            conn.close()
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
            conn = sqlite3.connect(self.db_path)
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
            conn = sqlite3.connect(self.db_path)
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
        # SQLite handles this automatically, but this method exists for compatibility
        pass
