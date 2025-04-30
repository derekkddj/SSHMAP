import asyncssh
import asyncio
import logging
from .logger import NXCAdapter
from .utils import get_remote_info, get_remote_hostname


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
        self.remote_hostname = None # hostname of the machine were we are connected to
        logging.getLogger("asyncssh").disabled = True
        self.sshmap_logger = NXCAdapter(
                extra={
                    "protocol": "SSH",
                    "host": self.host,
                    "port": self.port,
                    "hostname": jumper.get_remote_hostname() if jumper is not None else None,
                }
            )
        if jumper:
            # jumper is an instance of SSHSession, get the transport ip from the jumper
            self.sshmap_logger.debug(f"[{host}:{port}] Using jumper {jumper}...")

    async def connect(self):
        """Connect to the host using asyncssh."""
        try:
            # Direct connection or via jumper (proxy)
            if self.jumper:
                if self.key_filename:
                    self.connection = await asyncssh.connect(self.host, connect_timeout=15, tunnel=self.jumper.get_connection(), agent_path=None, agent_forwarding=False, username=self.user, port=self.port, 
                                                     password=self.password, known_hosts=None, client_keys=[self.key_filename])
                    self.sshmap_logger.success(f"{self.user}:{self.key_filename}")
                else:
                    self.connection = await asyncssh.connect(self.host, connect_timeout=15, tunnel=self.jumper.get_connection(), agent_path=None, agent_forwarding=False, username=self.user, port=self.port, 
                                                     password=self.password, known_hosts=None, client_keys=None)
                    self.sshmap_logger.success(f"{self.user}:{self.password}")
            else:
                if self.key_filename:
                    self.connection = await asyncssh.connect(self.host, connect_timeout=15, agent_path=None, agent_forwarding=False, username=self.user, port=self.port, known_hosts=None, client_keys=[self.key_filename])
                    self.sshmap_logger.success(f"{self.user}:{self.key_filename}")
                else:   
                    self.connection = await asyncssh.connect(self.host, connect_timeout=15, agent_path=None, agent_forwarding=False, username=self.user, port=self.port, password=self.password, known_hosts=None, client_keys=None)
                    self.sshmap_logger.success(f"{self.user}:{self.password}")
            self.remote_hostname = await get_remote_hostname(self)
            return True

        except asyncssh.PermissionDenied:
            self.sshmap_logger.fail(f"{self.user}:{self.password if self.password else self.key_filename}")
            return False
        except asyncssh.AuthenticationException as e:
            self.sshmap_logger.error(f"Authentication failed for {self.user}@{self.host}: {e}")
            self.connection = None
        except asyncssh.SSHException as e:
            self.sshmap_logger.error(f"SSH error for {self.user}@{self.host}: {e}")
            self.connection = None
        except Exception as e:
            self.sshmap_logger.error(f"Unexpected error for {self.user}@{self.host}: {e}")
            self.connection = None


    async def get_jumper(self):
        return self.jumper


    def get_remote_hostname(self):
        return self.remote_hostname

    async def exec_command(self, command):
        """Execute command on remote machine."""
        if self.connection is None:
            raise ValueError("SSH connection is not established.")
        
        try:
            result = await self.connection.run(command)
            return result.stdout
        except asyncssh.SSHException as e:
            self.sshmap_logger.error(f"Command execution failed on {self.host}: {e}")
            return None
    async def exec_command_with_stderr(self, command):
        """Execute command on remote machine."""
        if self.connection is None:
            raise ValueError("SSH connection is not established.")
        
        try:
            result = await self.connection.run(command)
            return result.stdout, result.stderr
        except asyncssh.SSHException as e:
            self.sshmap_logger.error(f"Command execution failed on {self.host}: {e}")
            return None
    async def close(self):
        """Close the SSH connection."""
        if self.connection:
            self.connection.close()
            await self.connection.wait_closed()
            self.sshmap_logger.debug(f"Closed SSH connection to {self.host}")

    
    def get_connection(self):
        return self.connection

    def get_host(self):
        return self.host

