from .SSHSession import SSHSession
from .logger import sshmap_logger
from .config import CONFIG
import asyncio


class SSHSessionManager:
    def __init__(self, graphdb, credential_store, proxy_url=None):
        self.graphdb = graphdb
        self.credential_store = credential_store
        self.proxy_url = proxy_url
        self.sessions = {}  # hostname -> SSHSession instance
        self._session_locks = {}
        self._session_locks_guard = asyncio.Lock()

    async def _get_session_lock(self, key):
        async with self._session_locks_guard:
            if key not in self._session_locks:
                self._session_locks[key] = asyncio.Lock()
            return self._session_locks[key]

    def _cache_session(self, key, session):
        session.set_broken_callback(self.invalidate_session)
        self.sessions[key] = session

    async def invalidate_session(self, session):
        removed_keys = [key for key, cached in self.sessions.items() if cached is session]
        for key in removed_keys:
            self.sessions.pop(key, None)

        if removed_keys:
            sshmap_logger.debug(
                f"Invalidated broken cached session(s): {removed_keys}"
            )

    async def get_session(self, target_hostname, start_hostname) -> SSHSession:
        """
        Returns a connected session to the target_hostname starting from start_hostname.
        Builds the jump chain as needed and caches sessions by (hostname, user, method, creds).
        """
        # GraphDB uses the synchronous Neo4j driver; run path lookup off the event loop
        # so multiple hosts can be processed concurrently.
        path = await asyncio.to_thread(self.graphdb.find_path, start_hostname, target_hostname)
        if not path:
            sshmap_logger.error(f"No path found from {start_hostname} to {target_hostname}")
            return None

        previous_session = None
        last_session = None

        for src, meta, dst in path:
            key = (dst, meta["user"], meta["method"], meta["creds"])

            # Reuse if alive
            existing = self.sessions.get(key)
            if existing and await existing.is_connected():
                sshmap_logger.debug(f"Reusing existing session to {dst}")
                previous_session = existing
                last_session = existing
                continue

            session_lock = await self._get_session_lock(key)
            async with session_lock:
                existing = self.sessions.get(key)
                if existing and await existing.is_connected():
                    sshmap_logger.debug(f"Reusing existing session to {dst}")
                    previous_session = existing
                    last_session = existing
                    continue

                key_filename = meta["creds"] if meta["method"] == "keyfile" else None
                password = meta["creds"] if meta["method"] == "password" else None

                key_object = None
                if meta["method"] == "keyfile":
                    key_object = self.credential_store.get_key_objects()

                session = SSHSession(
                    host=meta["ip"],
                    user=meta["user"],
                    password=password,
                    key_filename=key_filename,
                    key_objects=key_object if key_object else None,
                    port=meta["port"],
                    jumper=previous_session,
                    proxy_url=self.proxy_url
                )

                sshmap_logger.info(f"Connecting to {dst} ({meta['ip']}:{meta['port']}) as {meta['user']}...")
                try:
                    connected = await asyncio.wait_for(
                        session.connect(),
                        timeout=CONFIG["scan_timeout"] * 2,
                    )
                except asyncio.TimeoutError:
                    sshmap_logger.warning(
                        f"Timeout connecting to {dst} ({meta['ip']}:{meta['port']}) as {meta['user']}"
                    )
                    try:
                        await session.close()
                    except Exception as e:
                        sshmap_logger.debug(
                            f"Error closing timed-out session to {dst}: {type(e).__name__}: {e}"
                        )
                    return None
                
                if not connected:
                    sshmap_logger.warn(f"Failed to connect to {dst} ({meta['ip']}:{meta['port']}) as {meta['user']}")
                    return None
                
                self._cache_session(key, session)
                previous_session = session
                last_session = session

        return last_session

    async def add_session(
        self, hostname: str, session: SSHSession, user: str, method: str, creds: str
    ) -> SSHSession:
        """
        Adds a new SSH session identified by hostname, user, method and creds.
        If a session with the same parameters already exists and is connected, close the new one and reuse the existing.
        """

        key = (hostname, user, method, creds)

        existing = self.sessions.get(key)
        if existing and await existing.is_connected():
            sshmap_logger.debug(
                f"[!] Session for {key} already exists and is alive. Closing the new one."
            )
            await session.close()
            return existing
        else:
            sshmap_logger.info(f"[+] Adding new session for {key}")
            self._cache_session(key, session)
            return session

    async def close_all(self):
        for session in self.sessions.values():
            try:
                await session.close()
            except Exception as e:
                sshmap_logger.error(f"[!] Failed to close session: {e}")
        self.sessions.clear()
        self._session_locks.clear()
