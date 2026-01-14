from .SSHSession import SSHSession
from .logger import sshmap_logger


class SSHSessionManager:
    def __init__(self, graphdb, credential_store):
        self.graphdb = graphdb
        self.credential_store = credential_store
        self.sessions = {}  # hostname -> SSHSession instance

    async def get_session(self, target_hostname, start_hostname) -> SSHSession:
        """
        Returns a connected session to the target_hostname starting from start_hostname.
        Builds the jump chain as needed and caches sessions by (hostname, user, method, creds).
        """
        path = self.graphdb.find_path(start_hostname, target_hostname)
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
            )

            sshmap_logger.info(f"Connecting to {dst} ({meta['ip']}:{meta['port']}) as {meta['user']}...")
            connected = await session.connect()
            
            if not connected:
                sshmap_logger.error(f"Failed to connect to {dst} ({meta['ip']}:{meta['port']}) as {meta['user']}")
                return None
            
            self.sessions[key] = session
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
            self.sessions[key] = session
            return session

    async def close_all(self):
        for session in self.sessions.values():
            try:
                await session.close()
            except Exception as e:
                sshmap_logger.error(f"[!] Failed to close session: {e}")
        self.sessions.clear()
