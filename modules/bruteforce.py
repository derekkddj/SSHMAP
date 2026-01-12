from .SSHSession import SSHSession
from .logger import sshmap_logger
import asyncio
from .config import CONFIG
import random
import uuid
import asyncssh


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
    host, port, credential, jumper=None, credential_store=None, ssh_session_manager=None
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
    attempt_id = str(uuid.uuid4())[:8]  # Use first 8 chars for readability
    jumper_info = f"{jumper.get_remote_hostname()}@{jumper.get_host()}" if jumper else "direct"
    sshmap_logger.info(
        f"[START:{attempt_id}] {credential.method}:{credential.user}@{host}:{port} via {jumper_info}"
    )
    try:
        user = credential.user
        if credential.method == "password":
            password = credential.secret
            try:
                sshmap_logger.debug(
                    f"[DEBUG:{attempt_id}] password:{user}@{host}:{port} via {jumper_info}"
                )
                ssh = SSHSession(
                    host,
                    user,
                    password=password,
                    port=port,
                    jumper=jumper,
                    key_objects=credential_store.key_objects,
                    attempt_id=attempt_id
                )

                if await asyncio.wait_for(
                    ssh.connect(), timeout=CONFIG["scan_timeout"]
                ):
                    sshmap_logger.info(
                        f"[SUCCESS:{attempt_id}] password:{user}@{host}:{port} via {jumper_info}"
                    )
                    # Store the credential in the CredentialStore
                    await credential_store.store(host, port, user, password, "password")

                    nssh = await ssh_session_manager.add_session(
                        ssh.get_remote_hostname(), ssh, user, "password", password
                    )

                    return Result(user, "password", nssh, password)
            except asyncio.TimeoutError:
                sshmap_logger.warning(
                    f"[TIMEOUT:{attempt_id}] password:{user}@{host}:{port} via {jumper_info}"
                )
                return None
            except asyncssh.ConnectionLost as e:
                sshmap_logger.info(
                    f"[CONNECTIONLOST:{attempt_id}] password:{user}@{host}:{port} via {jumper_info} - {e}"
                )
                raise  # Re-raise for retry logic
            except Exception as e:
                sshmap_logger.warning(
                    f"[FAILED:{attempt_id}] password:{user}@{host}:{port} via {jumper_info} - {type(e).__name__}: {e}"
                )
                return None
        elif credential.method == "keyfile":
            keyfile = credential.secret
            sshmap_logger.debug(
                f"[DEBUG:{attempt_id}] keyfile:{user}@{host}:{port} via {jumper_info} using {keyfile}"
            )
            try:
                ssh = SSHSession(
                    host,
                    user,
                    key_filename=keyfile,
                    port=port,
                    jumper=jumper,
                    key_objects=credential_store.key_objects,
                    attempt_id=attempt_id
                )
                if await asyncio.wait_for(
                    ssh.connect(), timeout=CONFIG["scan_timeout"]
                ):
                    sshmap_logger.info(
                        f"[SUCCESS:{attempt_id}] keyfile:{user}@{host}:{port} via {jumper_info}"
                    )
                    # Store the credential in the CredentialStore
                    await credential_store.store(host, port, user, keyfile, "keyfile")
                    # Add the session to the SSHSessionManager

                    nssh = await ssh_session_manager.add_session(
                        ssh.get_remote_hostname(), ssh, user, "keyfile", keyfile
                    )

                    return Result(user, "keyfile", nssh, keyfile)
            except asyncio.TimeoutError:
                sshmap_logger.debug(
                    f"[TIMEOUT:{attempt_id}] keyfile:{user}@{host}:{port} via {jumper_info}"
                )
                return None
            except asyncssh.ConnectionLost as e:
                sshmap_logger.info(
                    f"[CONNECTIONLOST:{attempt_id}] keyfile:{user}@{host}:{port} via {jumper_info} - {e}"
                )
                raise  # Re-raise for retry logic
            except Exception as e:
                sshmap_logger.warning(
                    f"[FAILED:{attempt_id}] keyfile:{user}@{host}:{port} via {jumper_info} - {type(e).__name__}: {e}"
                )
                return None
    except asyncio.CancelledError:
        sshmap_logger.error(f"[{host}][CANCELLED] Brute force attempt was cancelled.")
        raise
    except asyncssh.ConnectionLost:
        # Re-raise ConnectionLost for retry logic
        raise
    except Exception as e:
        sshmap_logger.error(
            f"[ERROR:{attempt_id}] {user}@{host}:{port} - {type(e).__name__}: {e}"
        )
    return None


async def try_all(
    host,
    port,
    maxworkers=25,
    jumper=None,
    credential_store=None,
    ssh_session_manager=None,
    max_retries=3,
    graphdb=None,
    source_hostname=None,
    force_rescan=False,
):
    """Try all combinations of users, passwords, and keyfiles against a target host.

    Args:
        host (str): Target host to brute force.
        port (int): Port number to connect to.
        users (list): List of usernames for authentication.
        passwords (list): List of passwords for authentication.
        keyfiles (list): List of keyfiles for authentication.
        maxworkers (int, optional): Maximum number of workers for concurrent attempts. Defaults to 25.
        max_retries (int, optional): Maximum number of retries for transient failures. Defaults to 3.
        graphdb (GraphDB, optional): Graph database to track connection attempts.
        source_hostname (str, optional): Source hostname for tracking attempts.
        force_rescan (bool, optional): Force retry of already-attempted connections.

    Returns:
        list: List of Result objects for successful authentication attempts.
    """
    sshmap_logger.info(
        f"[START] Brute force {host}:{port} with max_workers={maxworkers}, max_retries={max_retries}"
    )
    results = []
    semaphore = asyncio.Semaphore(maxworkers)
    # Schedule all credential attempts as async tasks
    credentials = credential_store.get_credentials_host_and_bruteforce(host, port)
    
    # Filter out already-attempted connections unless force_rescan is True
    if not force_rescan and graphdb and source_hostname:
        original_count = len(credentials)
        filtered_credentials = []
        for cred in credentials:
            if not graphdb.has_connection_been_attempted(
                source_hostname, host, port, cred.user, cred.method, cred.secret
            ):
                filtered_credentials.append(cred)
        credentials = filtered_credentials
        skipped_count = original_count - len(credentials)
        if skipped_count > 0:
            sshmap_logger.info(
                f"[OPTIMIZATION] Skipping {skipped_count} already-attempted credentials for {host}:{port} from {source_hostname}"
            )
    
    # Track retry counts per credential
    retry_counts = {}

    async def limited_try(credential, retry_attempt=0):
        async with semaphore:
            if retry_attempt > 0:
                jumper_info = f"{jumper.get_remote_hostname()}@{jumper.get_host()}" if jumper else "direct"
                sshmap_logger.info(
                    f"[RETRY] Attempt {retry_attempt}/{max_retries-1} for {credential.method}:{credential.user}@{host}:{port} via {jumper_info}"
                )
                await asyncio.sleep(0.5 * retry_attempt)  # Exponential backoff
            
            result = await try_single_credential(
                host,
                port,
                credential,
                jumper=jumper,
                credential_store=credential_store,
                ssh_session_manager=ssh_session_manager,
            )
            
            # Record the attempt in the database
            if graphdb and source_hostname:
                # Get the target hostname if the connection succeeded
                to_hostname = result.ssh_session.get_remote_hostname() if result and result.ssh_session else None
                graphdb.record_connection_attempt(
                    source_hostname,
                    to_hostname if to_hostname else host,
                    host,
                    port,
                    credential.user,
                    credential.method,
                    credential.secret,
                    success=result is not None,
                )
            
            return result

    # Launch all credential attempts
    random.shuffle(credentials)  # Shuffle in-place
    tasks = []
    task_to_cred = {}  # Map tasks to their credentials for retry tracking
    
    for cred in credentials:
        jumper_info = f"{jumper.get_remote_hostname()}@{jumper.get_host()}" if jumper else "direct"
        sshmap_logger.debug(
            f"[TASK] Scheduling {cred.method}:{cred.user}@{host}:{port} via {jumper_info}"
        )
        task = asyncio.create_task(limited_try(cred, retry_attempt=0))
        tasks.append(task)
        task_to_cred[task] = cred
        retry_counts[id(cred)] = 0
    
    # Process tasks with retry logic
    while tasks:
        try:
            completed = await asyncio.gather(*tasks, return_exceptions=True)
        except KeyboardInterrupt:
            sshmap_logger.error("[INTERRUPT] Ctrl+C received! Cancelling all tasks...")
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            sshmap_logger.error("[CANCELLED] All tasks cancelled. Exiting cleanly.")
            return results

        # Prepare next batch of retries
        retry_tasks = []
        new_task_to_cred = {}
        
        for i, result in enumerate(completed):
            original_task = tasks[i]
            cred = task_to_cred.get(original_task)
            
            if isinstance(result, Exception):
                # Check if it's a transient error and we haven't exceeded retries
                if isinstance(result, asyncssh.ConnectionLost) and retry_counts[id(cred)] < max_retries - 1:
                    retry_counts[id(cred)] += 1
                    sshmap_logger.info(
                        f"[TRANSIENT] {cred.method}:{cred.user}@{host}:{port} - Scheduling retry {retry_counts[id(cred)]}/{max_retries-1}"
                    )
                    retry_task = asyncio.create_task(limited_try(cred, retry_attempt=retry_counts[id(cred)]))
                    retry_tasks.append(retry_task)
                    new_task_to_cred[retry_task] = cred
                else:
                    sshmap_logger.debug(
                        f"[EXCEPTION] {cred.method}:{cred.user}@{host}:{port} - {type(result).__name__}: {result}"
                    )
            elif result:
                # Successful authentication
                sshmap_logger.info(
                    f"[RESULT] Success: {result.method}:{result.user}@{host}:{port}"
                )
                results.append(result)
        
        # Update tasks and mapping for next iteration
        tasks = retry_tasks
        task_to_cred = new_task_to_cred

    # If no new successful connections were found and we have graphdb access,
    # retrieve and return previous successful connections so scanning can continue
    if not results and graphdb and source_hostname and not force_rescan:
        sshmap_logger.info(
            f"[FALLBACK] No new connections found from {source_hostname} to {host}:{port}. "
            f"Checking for previous successful connections from {source_hostname}."
        )
        previous_connections = graphdb.get_connections_from_host(source_hostname)
        
        # Find connections to the target host:port
        for conn in previous_connections:
            props = conn.get('props', {})
            if props.get('ip') == host and props.get('port') == port:
                sshmap_logger.info(
                    f"[FALLBACK] Re-using previous connection: {source_hostname} -> {conn['to']} "
                    f"({host}:{port}) with {props.get('user')}:{props.get('method')}"
                )
                
                # Try to re-establish the connection using the previous credentials
                try:
                    # Create a credential object for the previous connection
                    from .credential_store import Credential
                    prev_cred = Credential(
                        remote_ip=host,
                        port=str(port),
                        user=props.get('user'),
                        secret=props.get('creds'),
                        method=props.get('method')
                    )
                    
                    # Try to reconnect with the previous credentials
                    result = await try_single_credential(
                        host,
                        port,
                        prev_cred,
                        jumper=jumper,
                        credential_store=credential_store,
                        ssh_session_manager=ssh_session_manager,
                    )
                    
                    if result:
                        sshmap_logger.success(
                            f"[FALLBACK] Successfully re-established connection: {source_hostname} -> {conn['to']}"
                        )
                        results.append(result)
                except Exception as e:
                    sshmap_logger.warning(
                        f"[FALLBACK] Failed to re-establish connection to {host}:{port}: {e}"
                    )

    return results
