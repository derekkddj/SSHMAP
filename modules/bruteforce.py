from .SSHSession import SSHSession
from .logger import sshmap_logger
from .credential_store import Credential
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
    host, port, credential, jumper=None, credential_store=None, ssh_session_manager=None, proxy_url=None
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
    attempt_id = str(uuid.uuid4())[:10]  # Use first 10 chars for readability
    jumper_info = f"{jumper.get_remote_hostname()}@{jumper.get_host()}" if jumper else "direct"
    
    # Get credential display (basename for keyfiles)
    cred_display = credential.secret.split('/')[-1] if credential.method == "keyfile" else credential.secret
    
    sshmap_logger.info(
        f"[START:{attempt_id}] {credential.user}:{cred_display}@{host}:{port} via {jumper_info}"
    )
    try:
        user = credential.user
        if credential.method == "password":
            password = credential.secret
            try:
                sshmap_logger.debug(
                    f"[{attempt_id}] {user}:{password}@{host}:{port} via {jumper_info}"
                )
                ssh = SSHSession(
                    host,
                    user,
                    password=password,
                    port=port,
                    jumper=jumper,
                    key_objects=credential_store.key_objects,
                    attempt_id=attempt_id,
                    proxy_url=proxy_url
                )

                if await asyncio.wait_for(
                    ssh.connect(), timeout=CONFIG["scan_timeout"]
                ):
                    sshmap_logger.info(
                        f"[SUCCESS:{attempt_id}] {user}:{password}@{host}:{port} via {jumper_info}"
                    )
                    # Store the credential in the CredentialStore
                    await credential_store.store(host, port, user, password, "password")

                    nssh = await ssh_session_manager.add_session(
                        ssh.get_remote_hostname(), ssh, user, "password", password
                    )

                    return Result(user, "password", nssh, password)
            except asyncio.TimeoutError:
                sshmap_logger.debug(
                    f"[{attempt_id}] {user}:{password}@{host}:{port} via {jumper_info} - Timeout"
                )
                return None
            except asyncssh.ConnectionLost as e:
                sshmap_logger.debug(
                    f"[{attempt_id}] {user}:{password}@{host}:{port} via {jumper_info} - ConnectionLost: {e}"
                )
                raise  # Re-raise for retry logic
            except Exception as e:
                sshmap_logger.debug(
                    f"[{attempt_id}] {user}:{password}@{host}:{port} via {jumper_info} - {type(e).__name__}: {e}"
                )
                return None
        elif credential.method == "keyfile":
            keyfile = credential.secret
            keyfile_name = keyfile.split('/')[-1]
            sshmap_logger.debug(
                f"[{attempt_id}] {user}:{keyfile_name}@{host}:{port} via {jumper_info}"
            )
            try:
                ssh = SSHSession(
                    host,
                    user,
                    key_filename=keyfile,
                    port=port,
                    jumper=jumper,
                    key_objects=credential_store.key_objects,
                    attempt_id=attempt_id,
                    proxy_url=proxy_url
                )
                if await asyncio.wait_for(
                    ssh.connect(), timeout=CONFIG["scan_timeout"]
                ):
                    sshmap_logger.info(
                        f"[SUCCESS:{attempt_id}] {user}:{keyfile_name}@{host}:{port} via {jumper_info}"
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
                    f"[{attempt_id}] {user}:{keyfile_name}@{host}:{port} via {jumper_info} - Timeout"
                )
                return None
            except asyncssh.ConnectionLost as e:
                sshmap_logger.debug(
                    f"[{attempt_id}] {user}:{keyfile_name}@{host}:{port} via {jumper_info} - ConnectionLost: {e}"
                )
                raise  # Re-raise for retry logic
            except Exception as e:
                sshmap_logger.debug(
                    f"[{attempt_id}] {user}:{keyfile_name}@{host}:{port} via {jumper_info} - {type(e).__name__}: {e}"
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
            f"[{attempt_id}] {user}@{host}:{port} via {jumper_info} - {type(e).__name__}: {e}"
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
    attempt_store=None,
    source_hostname=None,
    force_rescan=False,
    proxy_url=None,
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
        f"[START] Brute force {host}:{port} with max_workers={maxworkers}, max_retries={max_retries} from source_hostname={source_hostname}"
    )
    results = []
    semaphore = asyncio.Semaphore(maxworkers)
    
    # Get previous successful connections from source_hostname to this target (host:port)
    # Store as dictionary keyed by (ip, port, to_hostname) for tracking
    old_connections = {}
    if graphdb and source_hostname and not force_rescan:
        try:
            previous_connections = graphdb.get_connections_from_host(source_hostname) or []
        except Exception as e:
            sshmap_logger.warning(
                f"[DB_ERROR] Failed to get connections from {source_hostname}: {type(e).__name__}: {e}. Continuing without fallback connections."
            )
            previous_connections = []
        
        for conn in previous_connections:
            props = conn.get('props', {})
            if props.get('ip') == host and props.get('port') == port:
                # Key by unique identifier for this connection
                key = (host, port, conn['to'])
                old_connections[key] = conn
        
        if old_connections:
            sshmap_logger.info(
                f"[FALLBACK] Found {len(old_connections)} previous successful connection(s) from {source_hostname} to {host}:{port}"
            )
    # Schedule all credential attempts as async tasks
    credentials = credential_store.get_credentials_host_and_bruteforce(host, port)
    
    # Filter out already-attempted connections unless force_rescan is True
    # Only do this filtering if connection attempt recording is enabled
    attempted_set = set()
    if not force_rescan and attempt_store and source_hostname and CONFIG.get("record_connection_attempts", True):
        original_count = len(credentials)
        
        # Get all attempted credentials for this target from SQLite (very fast)
        try:
            attempted_set = attempt_store.get_attempted_credentials(
                source_hostname, host, port
            ) or set()
        except Exception as e:
            sshmap_logger.warning(
                f"[ATTEMPT_STORE] Failed to get attempted credentials for {host}:{port}: {type(e).__name__}: {e}. Continuing without filtering."
            )
            attempted_set = set()
        
        # Filter credentials against the set (O(1) lookup per credential)
        # Check full (user, method, credential) tuple to avoid re-attempting same combination
        credentials = [
            cred for cred in credentials
            if (cred.user, cred.method, cred.secret) not in attempted_set
        ]
        
        skipped_count = original_count - len(credentials)
        if skipped_count > 0:
            sshmap_logger.info(
                f"[OPTIMIZATION] Skipping {skipped_count} already-attempted credentials to {host}:{port} from {source_hostname}"
            )
    # Track retry counts per credential
    retry_counts = {}

    async def limited_try(credential, retry_attempt=0):
        async with semaphore:
            if retry_attempt > 0:
                jumper_info = f"{jumper.get_remote_hostname()}@{jumper.get_host()}" if jumper else "direct"
                cred_display = credential.secret.split('/')[-1] if credential.method == "keyfile" else credential.secret
                sshmap_logger.info(
                    f"[RETRY:{retry_attempt}/{max_retries-1}] {credential.user}:{cred_display}@{host}:{port} via {jumper_info}"
                )
                await asyncio.sleep(0.5 * retry_attempt)  # Exponential backoff
            
            result = await try_single_credential(
                host,
                port,
                credential,
                jumper=jumper,
                credential_store=credential_store,
                ssh_session_manager=ssh_session_manager,
                proxy_url=proxy_url
            )
            
            # Record the attempt in the database (if enabled in config)
            # SQLite is fast but we give it a generous timeout for high concurrency
            if attempt_store and source_hostname and CONFIG.get("record_connection_attempts", True):
                # Get the target hostname if the connection succeeded
                to_hostname = result.ssh_session.get_remote_hostname() if result and result.ssh_session else host
                try:
                    # Await directly with timeout - SQLite uses thread pool so won't block event loop
                    await asyncio.wait_for(
                        attempt_store.record_attempt(
                            source_hostname,
                            to_hostname,
                            host,
                            port,
                            credential.user,
                            credential.method,
                            credential.secret,
                            result is not None,
                        ),
                        timeout=10.0  # 10 second timeout for high-concurrency scenarios
                    )
                except asyncio.TimeoutError:
                    sshmap_logger.warning(
                        f"[ATTEMPT_STORE] Record timeout for {credential.user}@{host}:{port} - database may be overwhelmed"
                    )
                except Exception as e:
                    sshmap_logger.debug(
                        f"[ATTEMPT_STORE] Failed to record: {type(e).__name__}: {e}"
                    )
            
            return result

    # Launch all credential attempts
    random.shuffle(credentials)  # Shuffle in-place
    tasks = []
    task_to_cred = {}  # Map tasks to their credentials for retry tracking
    
    for cred in credentials:
        jumper_info = f"{jumper.get_remote_hostname()}@{jumper.get_host()}" if jumper else "direct"
        cred_display = cred.secret.split('/')[-1] if cred.method == "keyfile" else cred.secret
        sshmap_logger.debug(
            f"[TASK] {cred.user}:{cred_display}@{host}:{port} via {jumper_info}"
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
                    cred_display = cred.secret.split('/')[-1] if cred.method == "keyfile" else cred.secret
                    sshmap_logger.debug(
                        f"[TRANSIENT] {cred.user}:{cred_display}@{host}:{port} - Scheduling retry {retry_counts[id(cred)]}/{max_retries-1}"
                    )
                    retry_task = asyncio.create_task(limited_try(cred, retry_attempt=retry_counts[id(cred)]))
                    retry_tasks.append(retry_task)
                    new_task_to_cred[retry_task] = cred
                else:
                    cred_display = cred.secret.split('/')[-1] if cred.method == "keyfile" else cred.secret
                    sshmap_logger.debug(
                        f"[EXCEPTION] {cred.user}:{cred_display}@{host}:{port} - {type(result).__name__}: {result}"
                    )
            elif result:
                # Successful authentication
                cred_display = result.creds.split('/')[-1] if result.method == "keyfile" else result.creds
                sshmap_logger.info(
                    f"[RESULT] {result.user}:{cred_display}@{host}:{port}"
                )
                results.append(result)
                
                # If this connection was in old_connections, remove it since we successfully reconnected
                if result.ssh_session:
                    try:
                        remote_hostname = result.ssh_session.get_remote_hostname()
                        if remote_hostname:
                            key = (host, port, remote_hostname)
                            if key in old_connections:
                                sshmap_logger.debug(
                                    f"[FALLBACK] New connection replaces old connection to {remote_hostname}"
                                )
                                del old_connections[key]
                    except Exception as e:
                        sshmap_logger.debug(
                            f"[FALLBACK] Could not determine remote hostname for connection: {e}"
                        )
        
        # Update tasks and mapping for next iteration
        tasks = retry_tasks
        task_to_cred = new_task_to_cred

    # At the end, re-establish any old connections that weren't found with new credentials
    # This allows scanning to continue through all previously discovered paths

    if old_connections and not force_rescan:
        sshmap_logger.info(
            f"[FALLBACK] Re-establishing {len(old_connections)} previous connection(s) not found with new credentials"
        )
        
        # Create fallback tasks with timeout protection
        fallback_tasks = []

        for key, conn in old_connections.items():
            props = conn.get('props', {})
            
            # Validate that we have all required properties
            user = props.get('user')
            creds = props.get('creds')
            method = props.get('method')
            
            if not all([user, creds, method]):
                sshmap_logger.warning(
                    f"[FALLBACK] Skipping connection to {conn.get('to', 'unknown')} - missing required properties (user, creds, or method)"
                )
                continue
            
            sshmap_logger.info(
                f"[FALLBACK] Re-using previous connection: {source_hostname} -> {conn['to']} "
                f"({host}:{port}) with {user}:{method}"
            )
            
            # Create a credential object for the previous connection
            prev_cred = Credential(
                remote_ip=host,
                port=str(port),
                user=user,
                secret=creds,
                method=method
            )
            
            # Create task with timeout wrapper
            async def try_fallback_reconnect(cred, target_conn):
                try:
                    # Use asyncio.wait_for to add timeout protection
                    result = await asyncio.wait_for(
                        try_single_credential(
                            host,
                            port,
                            cred,
                            jumper=jumper,
                            credential_store=credential_store,
                            ssh_session_manager=ssh_session_manager,
                            proxy_url=proxy_url
                        ),
                        timeout=CONFIG["scan_timeout"] * 2  # Give fallback 2x normal timeout
                    )
                    return result, target_conn
                except asyncio.TimeoutError:
                    sshmap_logger.warning(
                        f"[FALLBACK] Timeout re-establishing connection to {target_conn.get('to', 'unknown')} ({host}:{port})"
                    )
                    return None, target_conn
                except Exception as e:
                    sshmap_logger.debug(
                        f"[FALLBACK] Exception attempting to re-establish connection to {target_conn.get('to', 'unknown')}: {type(e).__name__}: {e}"
                    )
                    return None, target_conn
            
            task = asyncio.create_task(try_fallback_reconnect(prev_cred, conn))
            fallback_tasks.append(task)
        
        # Execute all fallback attempts concurrently
        if fallback_tasks:
            try:
                fallback_results = await asyncio.gather(*fallback_tasks, return_exceptions=False)
                
                for result, target_conn in fallback_results:
                    if result:
                        if source_hostname == "machine2_useasjumphost" and host == "172.19.0.3" and port == 22:
                            sshmap_logger.display(
                                f"[DEBUG] Fallback successful result: {await result.ssh_session.is_connected()} for {source_hostname} -> {target_conn['to']}"
                            )
                        sshmap_logger.success(
                            f"[FALLBACK] Successfully re-established connection: {source_hostname} -> {target_conn['to']}"
                        )
                        results.append(result)
            except Exception as e:
                if source_hostname == "machine2_useasjumphost" and host == "172.19.0.3" and port == 22:
                    sshmap_logger.display(
                        f"[DEBUG] Exception during fallback batch processing: {e}"
                    )
                sshmap_logger.warning(
                    f"[FALLBACK] Error during fallback batch processing: {e}"
                )


    return results
