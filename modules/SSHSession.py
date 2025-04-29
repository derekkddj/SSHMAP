import asyncssh
import asyncio
from .logger import sshmap_logger
from .utils import get_remote_info


class SSHSession:
    def __init__(self, host, user, password=None, key_filename=None, port=22,jumper=None):
        # If jump_session is provided, use it for the connection. Must be SSHJumpClient instance.
        self.host = host
        self.user = user
        self.password = password
        self.key_filename = key_filename
        self.port = port
        self.jumper = jumper
        self.connection = None  # Initialize the client as None
        if jumper:
            # jumper is an instance of SSHSession, get the transport ip from the jumper
            sshmap_logger.debug(f"[{host}:{port}] Using jumper {jumper}...")
            jumper_hostname,jumper_ips = get_remote_info(jumper)
            sshmap_logger.info(f"[{host}:{port}] Using jump session {jumper_hostname} for {user}@{host}")


    async def connect(self):
        """Connect to the host using asyncssh."""
        try:
            # Direct connection or via jumper (proxy)
            if self.jumper:
                if self.key_filename:
                    self.connection = await asyncssh.connect(self.host, tunnel=self.jumper.get_connection(), agent_path=None, agent_forwarding=False, username=self.user, port=self.port, 
                                                     password=self.password, known_hosts=None, client_keys=[self.key_filename])
                    sshmap_logger.success(f"[{self.jumper}->{self.host}:{self.port}] Successfully connected as {self.user} with keyfile {self.key_filename}")
                else:
                    self.connection = await asyncssh.connect(self.host, tunnel=self.jumper.get_connection(), agent_path=None, agent_forwarding=False, username=self.user, port=self.port, 
                                                     password=self.password, known_hosts=None, client_keys=None)
                    sshmap_logger.success(f"[{self.host}:{self.port}] Successfully connected as {self.user} with password {self.password}")
            else:
                if self.key_filename:
                    self.connection = await asyncssh.connect(self.host, agent_path=None, agent_forwarding=False, username=self.user, port=self.port, known_hosts=None, client_keys=[self.key_filename])
                    sshmap_logger.success(f"[{self.host}:{self.port}] Successfully connected as {self.user} with keyfile {self.key_filename}")
                else:   
                    self.connection = await asyncssh.connect(self.host, agent_path=None, agent_forwarding=False, username=self.user, port=self.port, password=self.password, known_hosts=None, client_keys=None)
                    sshmap_logger.success(f"[{self.host}:{self.port}] Successfully connected as {self.user} with password {self.password}")
            return True

        except asyncssh.AuthenticationException as e:
            sshmap_logger.error(f"Authentication failed for {self.user}@{self.host}: {e}")
            self.connection = None
        except asyncssh.SSHException as e:
            sshmap_logger.error(f"SSH error for {self.user}@{self.host}: {e}")
            self.connection = None
        except Exception as e:
            sshmap_logger.error(f"Unexpected error for {self.user}@{self.host}: {e}")
            self.connection = None


    async def get_jumper(self):
        return self.jumper

    async def exec_command(self, command):
        """Execute command on remote machine."""
        if self.connection is None:
            raise ValueError("SSH connection is not established.")
        
        try:
            result = await self.connection.run(command)
            return result.stdout
        except asyncssh.SSHException as e:
            sshmap_logger.error(f"Command execution failed on {self.host}: {e}")
            return None
    async def exec_command_with_stderr(self, command):
        """Execute command on remote machine."""
        if self.connection is None:
            raise ValueError("SSH connection is not established.")
        
        try:
            result = await self.connection.run(command)
            return result.stdout, result.stderr
        except asyncssh.SSHException as e:
            sshmap_logger.error(f"Command execution failed on {self.host}: {e}")
            return None
    async def close(self):
        """Close the SSH connection."""
        if self.connection:
            self.connection.close()
            await self.connection.wait_closed()
            sshmap_logger.debug(f"Closed SSH connection to {self.host}")

    
    def get_connection(self):
        return self.connection

    def get_host(self):
        return self.host

