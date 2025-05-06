from .SSHSession import SSHSession
from .logger import sshmap_logger
import asyncio
from .config import CONFIG


class Result:
    """Class to store the result of a single credential attempt.
    Attributes:
        user (str): The username used for the attempt.
        method (str): The method used for the attempt (password or keyfile).
        ssh_session (SSHSession): The SSH session object if the attempt was successful. Can have a jump_session.
        creds (str): The credentials used for the attempt.
    """

    def __init__(self, user, method, ssh_session, creds):
        self.user = user
        self.method = method
        self.ssh_session = ssh_session
        self.creds = creds

    def get_ssh_connection(self):
        return self.ssh_session


async def try_single_credential(
    host, port, credential, jumper=None, credential_store=None
):
    """Class to attempt a single credential authentication.
    This function tries to authenticate using either a password or a keyfile.
    If successful, it stores the credential in the CredentialStore.
    If both methods fail, it returns None.
    If the authentication is successful, it returns a Result object containing the user, method, and SSH session.
    If the authentication fails, it returns None.

    Args:
        host (str): The target host.
        port (int): Port number to connect to.
        credential (dict): Credential information including user, method, and secret.
        credential_store (CredentialStore, optional): Credential store to save successful attempts. Defaults to None.
        jumper (str, optional): Jumper host for SSH connection. Defaults to None. SSHSession.

    Returns:
        Result or None: Result object if authentication is successful, None otherwise.
    """
    sshmap_logger.info(
        f"[START] Attempting {credential.method} authentication for {credential.user}@{host}:{port} | Jumper: {jumper}"
    )
    if host == "172.19.0.3" or host == "172.19.0.2":
        sshmap_logger.display(
            f"[WARNING] Doing authentication for {host}:{port} with {credential.method} for {credential.user} | Jumper: {jumper.host if jumper else None}"
        )
    try:
        user = credential.user
        if credential.method == "password":
            password = credential.secret
            try:
                sshmap_logger.debug(
                    f"Trying password authentication for {user}:{password}@{host}:{port}"
                )
                ssh = SSHSession(
                    host, user, password=password, port=port, jumper=jumper
                )

                if await asyncio.wait_for(
                    ssh.connect(), timeout=CONFIG["scan_timeout"]
                ):
                    sshmap_logger.info(
                        f"[SUCCESS] Password authentication succeeded for {user}:{password}@{host}:{port}, saving to CredentialStore"
                    )
                    # Store the credential in the CredentialStore
                    credential_store.store(host, port, user, password, "password")
                    return Result(user, "password", ssh, password)
            except asyncio.TimeoutError:
                sshmap_logger.warning(
                    f"[TIMEOUT] Password authentication timed out for {user}@{host}:{port} with password: {password}"
                )
                return None
            except Exception as e:
                sshmap_logger.warning(
                    f"[FAILED] Password authentication failed for {user}@{host}:{port} with password: {password} with exception: {e}"
                )
                return None
        elif credential.method == "keyfile":
            keyfile = credential.secret
            try:
                sshmap_logger.info(
                    f"[DEBUG] Trying keyfile authentication for {user}:{keyfile}@{host}:{port}"
                )
                ssh = SSHSession(
                    host, user, key_filename=keyfile, port=port, jumper=jumper
                )
                if await asyncio.wait_for(
                    ssh.connect(), timeout=CONFIG["scan_timeout"]
                ):
                    sshmap_logger.info(
                        f"[SUCCESS] Keyfile authentication succeeded for {user}:{keyfile}@{host}:{port}, saving to CredentialStore"
                    )
                    # Store the credential in the CredentialStore
                    credential_store.store(host, port, user, keyfile, "keyfile")
                    return Result(user, "keyfile", ssh, keyfile)
            except asyncio.TimeoutError:
                sshmap_logger.warning(
                    f"[TIMEOUT] Keyfile authentication timed out for {user}@{host}:{port} with keyfile: {keyfile}"
                )
                return None
            except Exception as e:
                sshmap_logger.info(
                    f"[FAILED] Keyfile authentication failed for {user}@{host}:{port} with keyfile: {keyfile} with exception: {e}"
                )
                return None
    except asyncio.CancelledError:
        sshmap_logger.error(f"[{host}][CANCELLED] Brute force attempt was cancelled.")
        raise
    except Exception as e:
        sshmap_logger.error(
            f"[ERROR] Unexpected error during authentication for {user}@{host}:{port}. Exception: {e}"
        )
    return None


async def try_all(host, port, maxworkers=10, jumper=None, credential_store=None):
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
    sshmap_logger.info(
        f"[START] Starting brute force attempts for {host}:{port} with max workers: {maxworkers}"
    )
    results = []
    tasks = []

    # Schedule all credential attempts as async tasks
    for credential in credential_store.get_credentials_host_and_bruteforce(host, port):
        sshmap_logger.debug(
            f"[TASK] Scheduling authentication attempt for {credential.user}@{host}:{port} using {credential.method}"
        )
        task = asyncio.create_task(
            try_single_credential(
                host, port, credential, jumper=jumper, credential_store=credential_store
            )
        )
        tasks.append(task)

    # Wait for all tasks to complete
    try:
        completed = await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        sshmap_logger.error("[INTERRUPT] Ctrl+C received! Cancelling all tasks...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        sshmap_logger.error("[CANCELLED] All tasks cancelled. Exiting cleanly.")
    # Filter successful results
    for result in completed:
        if result:
            sshmap_logger.debug(
                f"[RESULT] Successful authentication for {result.user}@{host}:{port} using {result.method}"
            )
            results.append(result)

    return results
