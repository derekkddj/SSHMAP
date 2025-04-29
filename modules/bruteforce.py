from .SSHSession import SSHSession
from .logger import sshmap_logger
import concurrent.futures


class Result:
    """Class to store the result of a single credential attempt.
    Attributes:
        user (str): The username used for the attempt.
        method (str): The method used for the attempt (password or keyfile).
        ssh_session (SSHSession): The SSH session object if the attempt was successful. Can have a jump_session.
        creds (str): The credentials used for the attempt.
    """
    def __init__(self, user, method, ssh_session,creds):
        self.user = user
        self.method = method
        self.ssh_session = ssh_session
        self.creds = creds

    def get_ssh_connection(self):
        return self.ssh_session


def try_single_credential(host, port, credential, jumper=None, credential_store=None):
    """Class to attempt a single credential authentication.
    This function tries to authenticate using either a password or a keyfile.
    If successful, it stores the credential in the CredentialStore.
    If both methods fail, it returns None.
    If the authentication is successful, it returns a Result object containing the user, method, and SSH session.
    If the authentication fails, it returns None.

    Args:
        host (str): The target host.
        port (int): Port number to connect to.
        user (str): Username for authentication.
        password (str, optional): Password for authentication. Defaults to None.
        keyfile (str, optional): Path to the keyfile for authentication. Defaults to None.
        credential_store (CredentialStore, optional): Credential store to save successful attempts. Defaults to None.
        jumper (str, optional): Jumper host for SSH connection. Defaults to None. SSHSession.

    Returns:
        Result or None: Result object if authentication is successful, None otherwise.
    """
    try:
        if credential["remote_ip"] == "_bruteforce" or (credential["remote_ip"] == host and credential["port"] == str(port)):
            user = credential["user"]
            if credential["method"] == "password":
                password = credential["secret"]
                try:
                    sshmap_logger.info(f"Attempted password for {user}:{password}@{host}:{port}")
                    ssh = SSHSession(host, user, password=password, port=port, jumper=jumper)
                    if ssh.get_client():
                        sshmap_logger.highlight(f"{user}:{password}@{host}:{port}")
                        # Store the credential in the CredentialStore
                        credential_store.store(host, port, user, password, "password")
                        return Result(user, "password", ssh, password)
                except Exception:
                    sshmap_logger.info(f"Failed to authenticate {user}@{host}:{port} with password: {password}")
                    return None
            elif credential["method"] == "keyfile":
                keyfile = credential["secret"]
                try:
                    sshmap_logger.info(f"Attempted keyfile for {user}:{keyfile}@{host}:{port}")
                    ssh = SSHSession(host, user, key_filename=keyfile, port=port, jumper=jumper)
                    if ssh.client:
                        sshmap_logger.highlight(f"{user}:{keyfile}@{host}:{port}")
                        # Store the credential in the CredentialStore
                        credential_store.store(host, port, user, keyfile, "keyfile")
                        return Result(user, "keyfile", ssh, keyfile)
                except Exception:
                    sshmap_logger.info(f"Failed to authenticate {user}@{host}:{port} with keyfile: {keyfile}")
                    return None
    except Exception as e:
        sshmap_logger.error(f"Failed to authenticate {user}@{host}:{port}. Exception: {e}")
    return None

def try_all(host, port, maxworkers=10, jumper=None,credential_store=None):
    """Try all combinations of users, passwords, and keyfiles against a target host.

    Args:
        host (str): Target host to brute force.
        port (int): Port number to connect to.
        users (list): List of usernames for authentication.
        passwords (list): List of passwords for authentication.
        keyfiles (list): List of keyfiles for authentication.
        maxworkers (int, optional): Maximum number of workers for concurrent attempts. Defaults to 4.

    Returns:
        list: List of Result objects for successful authentication attempts.
    """
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=maxworkers) as executor:
        futures = []
        # Queue password attempts
        #We will use only the data from the credential store
        for credential in credential_store.get_all():
            futures.append(executor.submit(try_single_credential, host, port, credential, jumper=jumper, credential_store=credential_store))
        # Collect finished futures
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                results.append(result)
    return results
