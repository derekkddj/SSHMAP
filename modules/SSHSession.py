import asyncio
import asyncssh
import logging
import sys
import os
import tty
import termios
from .logger import NXCAdapter
from .utils import get_remote_hostname, create_proxy_socket
from .config import CONFIG


class SSHSession:
    def __init__(
        self,
        host,
        user,
        password=None,
        key_filename=None,
        port=22,
        jumper=None,
        key_objects=None,
        attempt_id=None,
        proxy_url=None,
    ):
        # If jump_session is provided, use it for the connection. Must be SSHSession instance.
        self.host = host
        self.user = user
        self.password = password
        self.key_filename = key_filename
        self.port = port
        self.jumper = jumper
        self.proxy_url = proxy_url
        self.connection = (
            None  # Initialize the client as None, type asyncssh.SSHClientConnection
        )
        self.remote_hostname = None  # hostname of the machine were we are connected to
        self.key_objects = key_objects
        self.attempt_id = attempt_id
        # Disable asyncssh logging
        logging.getLogger("asyncssh").disabled = True
        self.sshmap_logger = NXCAdapter(
            extra={
                "protocol": "SSH",
                "host": self.host,
                "port": self.port,
                "hostname": (
                    jumper.get_remote_hostname() if jumper is not None else None
                )
            }
        )
        if jumper:
            # jumper is an instance of SSHSession, get the transport ip from the jumper
            jumper_info = f"{jumper.get_remote_hostname()}@{jumper.get_host()}"
            self.sshmap_logger.debug(f"[{attempt_id}] Using jumper {jumper_info}")
        elif proxy_url:
            self.sshmap_logger.debug(f"[{attempt_id}] Using proxy {proxy_url}")

    async def connect(self):
        """Connect to the host using asyncssh."""
        attempt_prefix = f"[{self.attempt_id}] " if self.attempt_id is not None else ""
        try:
            # Direct connection or via jumper (proxy)
            if self.jumper:
                tunnel_conn = self.jumper.get_connection()
                # If we have a jumper, we tunnel through it.
                # Note: Chaining proxies AND jumpers is complex.
                # For now simplify: If jumper is set, it takes precedence or we assume proxy helps reach jumper?
                # Usually proxy is for reaching the FIRST hop.
                # If self.jumper is set, it means we are deeper in the chain.
                # So we probably don't use self.proxy_url here, unless the jumper itself needed a proxy (which would be handled in jumper's session).
                pass 
                
                if self.key_filename:
                    key_obj = self.key_objects.get(self.key_filename)
                    self.connection = await asyncssh.connect(
                        self.host,
                        connect_timeout=CONFIG["scan_timeout"],
                        tunnel=tunnel_conn,
                        agent_path=None,
                        agent_forwarding=False,
                        username=self.user,
                        port=self.port,
                        known_hosts=None,
                        client_keys=[key_obj],
                    )

                else:
                    self.connection = await asyncssh.connect(
                        self.host,
                        connect_timeout=CONFIG["scan_timeout"],
                        tunnel=tunnel_conn,
                        agent_path=None,
                        agent_forwarding=False,
                        username=self.user,
                        port=self.port,
                        password=self.password,
                        known_hosts=None,
                        client_keys=None,
                    )

            else:
                # No jumper (direct or proxy)
                sock = None
                if self.proxy_url:
                    sock = create_proxy_socket(self.proxy_url, self.host, self.port)
                    if not sock:
                        # Failed to create proxy socket
                        raise ConnectionError(f"Failed to connect to proxy {self.proxy_url}")
                
                # If proxy enabled, pass sock=sock. asyncssh ignores host/port if sock is provided (it uses them for host key verification mostly)
                # Correction: asyncssh documentation says: "If a socket is provided, the host and port arguments are used only for host key verification."
                
                if self.key_filename:
                    key_obj = self.key_objects.get(self.key_filename)
                    self.connection = await asyncssh.connect(
                        self.host,
                        connect_timeout=CONFIG["scan_timeout"],
                        agent_path=None,
                        agent_forwarding=False,
                        username=self.user,
                        port=self.port,
                        known_hosts=None,
                        client_keys=[key_obj],
                        sock=sock
                    )

                else:
                    self.connection = await asyncssh.connect(
                        self.host,
                        connect_timeout=CONFIG["scan_timeout"],
                        agent_path=None,
                        agent_forwarding=False,
                        username=self.user,
                        port=self.port,
                        password=self.password,
                        known_hosts=None,
                        client_keys=None,
                        sock=sock
                    )

            # Small stabilization delay so command channels are ready
            await asyncio.sleep(0.1)

            # Warm up command channel: some targets return exit_status -1 on first command
            # immediately after connect. Run a cheap no-op a few times before hostname.
            for _ in range(3):
                try:
                    warmup = await self.connection.run("true", check=False)
                    if warmup.exit_status == 0:
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.15)

            self.remote_hostname = await get_remote_hostname(self)
            keyfile_display = self.key_filename.split('/')[-1] if self.key_filename else None
            cred_display = self.password if self.password else keyfile_display
            self.sshmap_logger.success(
                f"{attempt_prefix}{self.user}:{cred_display} (hostname:{self.remote_hostname})"
            )
            return True

        except asyncssh.PermissionDenied:
            keyfile_display = self.key_filename.split('/')[-1] if self.key_filename else None
            cred_display = self.password if self.password else keyfile_display
            self.sshmap_logger.fail(
                f"{attempt_prefix}{self.user}:{cred_display}"
            )
            return False
        except asyncssh.ChannelOpenError as e:
            keyfile_display = self.key_filename.split('/')[-1] if self.key_filename else None
            cred_display = self.password if self.password else keyfile_display
            jumper_info = f"{self.jumper.get_remote_hostname()}@{self.jumper.get_host()}" if self.jumper else "direct"
            self.sshmap_logger.info(
                f"{attempt_prefix}{self.user}:{cred_display}@{self.host}:{self.port} via {jumper_info} - ChannelOpenError: {e.reason}"
            )
            return False
        except asyncssh.ConnectionLost as e: # aqui aparecen muchos casos cuando hay mucha sobrecarga
            # Re-raise ConnectionLost for retry logic in bruteforce.py
            keyfile_display = self.key_filename.split('/')[-1] if self.key_filename else None
            cred_display = self.password if self.password else keyfile_display
            jumper_info = f"{self.jumper.get_remote_hostname()}@{self.jumper.get_host()}" if self.jumper else "direct"
            self.sshmap_logger.warning(
                f"{attempt_prefix}{self.user}:{cred_display}@{self.host}:{self.port} via {jumper_info} - ConnectionLost: {e}"
            )
            raise
        except Exception as e:
            keyfile_display = self.key_filename.split('/')[-1] if self.key_filename else None
            cred_display = self.password if self.password else keyfile_display
            jumper_info = f"{self.jumper.get_remote_hostname()}@{self.jumper.get_host()}" if self.jumper else "direct"
            self.sshmap_logger.error(
                f"{attempt_prefix}{self.user}:{cred_display}@{self.host}:{self.port} via {jumper_info} - {type(e).__name__}: {e}"
            )
            self.connection = None
            return False

    async def get_jumper(self):
        return self.jumper

    def get_remote_hostname(self):
        return self.remote_hostname

    def __str__(self):
        return f"SSHSession({self.user}@{self.remote_hostname}:{self.port})"

    async def exec_command(self, command):
        """Execute command on remote machine."""
        if self.connection is None:
            raise ValueError("SSH connection is not established.")

        result = await self.connection.run(command)
        return result.stdout

    async def exec_command_with_stderr(self, command):
        """Execute command on remote machine."""
        if self.connection is None:
            raise ValueError("SSH connection is not established.")

        result = await self.connection.run(command)
        return result.stdout, result.stderr, result.exit_status

    async def interactive_shell(self):
        """
        Opens an interactive shell on the remote host.
        Handles TTY raw mode if stdin is a terminal.
        """
        if self.connection is None:
            raise ValueError("SSH connection is not established.")

        term_type = os.environ.get('TERM', 'xterm')
        
        # Check if we are connected to a TTY
        if sys.stdin.isatty():
            # Save original terminal settings
            old_tty_attrs = termios.tcgetattr(sys.stdin)
            try:
                # Set raw mode for true interactive feel (passes all keystrokes including Ctrl+C)
                tty.setraw(sys.stdin)
                
                # Open the session
                # We use encoding=None to pass raw bytes if needed, but asyncssh usually expects strings for run unless requested otherwise.
                # However, for an interactive shell, we usually want to connect streams.
                # connection.create_process with no command starts the user's shell.
                # We use create_process which handles stdin/stdout/stderr redirection properly
                process = await self.connection.create_process(
                    term_type=term_type,
                    term_size=os.get_terminal_size(),
                    stdin=sys.stdin,
                    stdout=sys.stdout,
                    stderr=sys.stderr
                )
                await process.wait()
                
            finally:
                # Restore terminal settings
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_tty_attrs)
        else:
            # Non-interactive (e.g. piped input)
            process = await self.connection.create_process(
                term_type=term_type,
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr
            )
            await process.wait()

    async def close(self):
        """Close the SSH connection."""
        if self.connection:
            self.connection.close()
            await self.connection.wait_closed()
            self.sshmap_logger.debug(f"Closed connection to {self.host}:{self.port}")

    def get_connection(self):
        return self.connection

    def get_host(self):
        return self.host

    async def is_connected(self) -> bool:
        if self.connection is None:
            return False
        
        # First check if jumper chain is healthy (recursive validation)
        if self.jumper and not await self.jumper.is_connected():
            self.sshmap_logger.warning(
                f"Jumper connection broken for {self.host}:{self.port}"
            )
            return False
        
        # Then check our own connection
        try:
            process = await self.connection.create_process("true")
            await process.wait()
            return process.exit_status == 0
        except Exception as e:
            self.sshmap_logger.error(
                f"Error checking connection for {self.host}:{self.port} - {type(e).__name__}: {e}"
            )
            return False
