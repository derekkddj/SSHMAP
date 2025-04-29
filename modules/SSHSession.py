from paramiko_jump import SSHJumpClient, simple_auth_handler
from paramiko import AutoAddPolicy, SSHException, AuthenticationException, SSHException
from .logger import sshmap_logger
from .utils import get_remote_info


class SSHSession:
    def __init__(self, host, user, password=None, key_filename=None, port=22,jumper=None):
        # If jump_session is provided, use it for the connection. Must be SSHJumpClient instance.
        self.jumper = jumper
        if jumper:
            # jumper is an instance of SSHSession, get the transport ip from the jumper
            sshmap_logger.debug(f"[{host}:{port}] Using jumper {jumper}...")
            jumper_hostname,jumper_ips = get_remote_info(jumper)
            sshmap_logger.info(f"[{host}:{port}] Using jump session {jumper_hostname} for {user}@{host}")
            self.client = SSHJumpClient(jump_session=jumper)
        else:
            sshmap_logger.info(f"[{host}:{port}] No jump session provided, direct connection")
            self.client = SSHJumpClient()
        self.client.set_missing_host_key_policy(AutoAddPolicy())
        # Disable SSH agent and don't look for any keys
        self.client.load_system_host_keys()
        self.client.get_host_keys().clear()
        try:
            if key_filename:
                sshmap_logger.debug(f"[{host}:{port}] Test: {user}@{host} using keyfile: {key_filename} in SSHSession")
                self.client.connect(hostname=host, port=port, username=user, key_filename=key_filename,timeout=5, allow_agent=False, look_for_keys=False)
                sshmap_logger.success(f"[{host}:{port}] Success: {user}@{host} using keyfile: {key_filename}")
            else:
                sshmap_logger.debug(f"[{host}:{port}] Test: {user}@{host} using password: {password} in SSHSession")
                self.client.connect(hostname=host, port=port, username=user, password=password, timeout=5, allow_agent=False, look_for_keys=False)
                sshmap_logger.success(f"[{host}:{port}] Success: {user}@{host} using password: {password}")
        except AuthenticationException as e:
            sshmap_logger.debug(f"Authentication failed user: {user}: {e}")
            self.client = None
        except SSHException as e:
            sshmap_logger.error(f"SSH error: {e}")
            self.client = None
        except Exception as e:
            sshmap_logger.error(f"Unexpected error: {e}")
            self.client = None

    def get_jumper(self):
        return self.jumper

    def exec_command(self, command):
        stdin, stdout, stderr = self.client.exec_command(command)
        return stdout.read().decode()

    def exec_command_with_stderr(self, command):
        stdin, stdout, stderr = self.client.exec_command(command)
        return stdout.read().decode(), stderr.read().decode()

    def get_client(self):
        return self.client

    def close(self):
        self.client.close()
