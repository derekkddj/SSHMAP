import argparse
import asyncio
import os
import sys
from modules import bruteforce, graphdb
from modules.attempt_store import AttemptStore
from modules.logger import sshmap_logger, setup_debug_logging
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


VERSION = "1.0.1"

# Setup neo4j for graph data (successful connections)
graph = graphdb.GraphDB(CONFIG["neo4j_uri"], CONFIG["neo4j_user"], CONFIG["neo4j_pass"])

# Setup SQLite for attempt logging (much faster than Neo4j for this use case)
attempt_store = AttemptStore(db_path="output/ssh_attempts.db")

start_host, start_ips = get_local_info()
ssh_ports = CONFIG["ssh_ports"]
# Max depth for the ssh scan
max_depth = CONFIG["max_depth"]
# Thread-safe function to handle a target

# Date of running
currenttime = datetime.now().strftime("%Y%m%d_%H%M%S")

console = nxc_console
visited_attempts = set()


progress = Progress(
    SpinnerColumn(),
    TextColumn("[bold]{task.fields[jump_host]}", justify="right"),
    BarColumn(),
    "[{task.completed}/{task.total}]",
    TimeElapsedColumn(),
    TimeRemainingColumn(),
    transient=True,
)


async def handle_target(
    target,
    maxworkers_ssh,
    credential_store,
    current_depth,
    jump=None,
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
):
    try:
        if current_depth > max_depth:
            sshmap_logger.debug(f"Max depth {max_depth} reached. Skipping {target}")
            return
        source_host = start_host if current_depth == 1 else jump.get_remote_hostname()
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
            # We can not check open ports if we are using a jump host, so we just try to connect to all ports
            if current_depth > 1 or await check_open_port(target, port):
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
                        remote_ips = await get_remote_ip(ssh_conn)

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
                                )
                            sshmap_logger.info(
                                f"Curent-depth: {current_depth}, scaning from: {source_host} We create a recursive job, using remote_hostname: {remote_hostname} as the jump, loaded {len(new_targets)} new targets"
                            )

                            for new_target in new_targets:
                                await queue.put(
                                    (new_target, current_depth + 1, ssh_conn)
                                )
                        else:
                            sshmap_logger.info(
                                f"Already scanned from {remote_hostname}. Skipping."
                            )
            else:
                sshmap_logger.debug(
                    f"[{target}] No open ports found, skipping bruteforce."
                )

        sshmap_logger.info(f"[{target}] Bruteforce completed successfully from {source_host} with jump {jump if jump else 'None'}.")
        return
    except asyncio.CancelledError:
        sshmap_logger.error(f"{target} was cancelled in handle target.")
        raise


async def worker(queue, semaphore, maxworkers, credential_store, blacklist_ips, whitelist_ips, force_targets_mode=False, force_targets_ips=None):
    while True:
        try:
            target, depth, jumper = await queue.get()

            async with semaphore:
                await handle_target(
                    target,
                    maxworkers,
                    credential_store,
                    current_depth=depth,
                    jump=jumper,
                    queue=queue,
                    blacklist_ips=blacklist_ips,
                    whitelist_ips=whitelist_ips,
                    force_targets_mode=force_targets_mode,
                    force_targets_ips=force_targets_ips,
                )

        except asyncio.CancelledError:
            break
        finally:
            queue.task_done()


async def async_main(args):
    setup_debug_logging()
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
        graphdb=graph, credential_store=credential_store
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
    queue = AsyncRandomQueue()
    task_ids = {}
    random.shuffle(new_targets)
    for target in new_targets:
        await queue.put((target, 1, initial_jump_session))

    with Live(progress, console=console, refresh_per_second=10):

        # Add a task per initial jump host (in this case, just one unless more logic added)
        task_ids[initial_jump_host] = progress.add_task(
            description=f"Scanning from {initial_jump_host}",
            total=len(new_targets),
            jump_host=initial_jump_host,
        )

        semaphore = asyncio.Semaphore(args.maxworkers)

        async def tracked_worker():
            while True:
                try:
                    target, depth, jumper = await queue.get()
                    current_jump = (
                        jumper.get_remote_hostname() if jumper else initial_jump_host
                    )

                    async with semaphore:
                        await handle_target(
                            target,
                            args.maxworkers_ssh,
                            credential_store,
                            depth,
                            jumper,
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
                        )

                    if current_jump in task_ids:
                        progress.update(task_ids[current_jump], advance=1)
                except asyncio.CancelledError:
                    break
                finally:
                    await queue.task_done()

        workers = [
            asyncio.create_task(tracked_worker()) for _ in range(args.maxworkers)
        ]

        try:
            await queue.join()
        except KeyboardInterrupt:
            sshmap_logger.warn("Ctrl+C received! Cancelling...")
        finally:
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            graph.close()

        print_jumphosts(visited_attempts)
    
    sshmap_logger.success("Closing all SSH sessions and connections.")
    await ssh_session_manager.close_all()
    sshmap_logger.success("All tasks completed.")


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

    args = parser.parse_args()
    global max_depth
    max_depth = args.maxdepth

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
