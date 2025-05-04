from neo4j import GraphDatabase
from ipaddress import ip_network
import os


# graphdb.py


class GraphDB:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def write_ssh_config_for_path(
        self, start, end, method="proxyjump", config_path="/tmp/sshmap_config"
    ):
        """
        Generates an SSH config file to connect from start to end using recorded jump path.

        :param start: Hostname of the source node.
        :param end: Hostname of the target node.
        :param method: "proxyjump" for ProxyJump, "proxycommand" for ProxyCommand.
        :param config_path: Output SSH config file path.
        :return: Path to the config file.
        """
        path = self.find_path(start, end)
        if not path:
            raise ValueError(f"No path found from {start} to {end}")

        with open(config_path, "w") as f:
            host_aliases = []

            for idx, (src, meta, dst) in enumerate(path):
                alias = f"jump{idx}"
                host_aliases.append((alias, meta))

                f.write(f"Host {alias}\n")
                f.write(f"    HostName {meta['ip']}\n")
                f.write(f"    User {meta['user']}\n")
                f.write(f"    Port {meta['port']}\n")
                # Optional: f.write(f"    IdentityFile {meta.get('key_path', '')}\n")
                f.write("\n")

            # Write the final target
            final_alias = "target"
            final_meta = path[-1][1]

            f.write(f"Host {final_alias}\n")
            f.write(f"    HostName {final_meta['ip']}\n")
            f.write(f"    User {final_meta['user']}\n")
            f.write(f"    Port {final_meta['port']}\n")

            if method == "proxyjump":
                jump_chain = " ".join(alias for alias, _ in host_aliases)
                f.write(f"    ProxyJump {jump_chain}\n")
            elif method == "proxycommand":
                # Build ProxyCommand using chained netcat (or ssh -W)
                proxy_cmd = ""
                for i in range(len(host_aliases) - 1, -1, -1):
                    alias, meta = host_aliases[i]
                    host = meta["ip"]
                    port = meta["port"]
                    user = meta["user"]
                    ssh_part = f"ssh -o StrictHostKeyChecking=no -p {port} -W %h:%p {user}@{host} "
                    if i != len(host_aliases) - 1:
                        ssh_part += f"-o ProxyCommand='{proxy_cmd}'"
                    proxy_cmd = ssh_part

                f.write(f"    ProxyCommand {proxy_cmd}\n")
            else:
                raise ValueError("Unsupported method. Use 'jump' or 'command'.")

            f.write("\n")

        os.chmod(config_path, 0o600)
        print(f"[+] SSH config written to {config_path}")
        print(f"[+] Use it with: ssh -F {config_path} target")
        return config_path

    def find_path(self, start_hostname, end_hostname):
        """
        Find the shortest path from start_hostname to end_hostname through SSH_ACCESS relationships.
        Also returns connection metadata from each hop.
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (start:Host {hostname: $start}), (end:Host {hostname: $end})
                MATCH path = shortestPath((start)-[rels:SSH_ACCESS*..15]->(end))
                RETURN nodes(path) AS nodes, rels AS relationships
            """,
                start=start_hostname,
                end=end_hostname,
            )

            for record in result:
                nodes = record["nodes"]
                rels = record["relationships"]

                full_path = []
                for i in range(len(rels)):
                    src = nodes[i]["hostname"]
                    dst = nodes[i + 1]["hostname"]
                    rel = rels[i]
                    # Collect the relevant SSH metadata
                    meta = {
                        "user": rel.get("user"),
                        "method": rel.get("method"),
                        "creds": rel.get("creds"),
                        "ip": rel.get("ip"),
                        "port": rel.get("port"),
                    }
                    full_path.append((src, meta, dst))

                return full_path

            return None  # No path found

    def find_all_paths_to(self, start_hostname, end_hostname, max_depth=5):
        """
        Find all paths (up to max_depth) from start_hostname to end_hostname.
        Includes metadata for each hop along the path.
        """
        with self.driver.session() as session:
            result = session.run(
                f"""
                MATCH path = (start:Host {{hostname: $start}})-[:SSH_ACCESS*1..{max_depth}]->(end:Host {{hostname: $end}})
                RETURN path
            """,
                start=start_hostname,
                end=end_hostname,
            )

            # Process each path returned and format it with metadata
            all_paths = []
            for record in result:
                formatted_path = self._format_path_with_metadata(record["path"])
                all_paths.append(formatted_path)

            return all_paths

    def add_host(self, hostname, ip_info):
        """
        Store host with multiple IPs and subnet masks in CIDR notation.
        ip_info = [{'ip': '192.168.1.10', 'mask': 24}, ...]
        """
        # Convert IP/mask pairs to CIDR notation (e.g., '192.168.1.10/24')
        cidr_info = [f"{iface['ip']}/{iface['mask']}" for iface in ip_info]
        with self.driver.session() as session:
            session.run(
                """
                MERGE (h:Host {hostname: $hostname})
                SET h.interfaces = $cidr_info
            """,
                hostname=hostname,
                cidr_info=cidr_info,
            )

    def add_ssh_connection(
        self, from_hostname, to_hostname, user, method, creds, ip, port
    ):
        with self.driver.session() as session:
            session.run(
                """
                MATCH (src:Host {hostname: $from_hostname})
                MATCH (dst:Host {hostname: $to_hostname})
                MERGE (src)-[r:SSH_ACCESS {user: $user, method: $method, creds: $creds, ip: $ip, port:$port}]->(dst)
            """,
                from_hostname=from_hostname,
                to_hostname=to_hostname,
                user=user,
                method=method,
                creds=creds,
                ip=ip,
                port=port,
            )

    def find_hosts_in_same_subnet(self, ip, mask):
        target_net = ip_network(f"{ip}/{mask}", strict=False)
        matching_hosts = []

        with self.driver.session() as session:
            result = session.run(
                "MATCH (h:Host) RETURN h.hostname AS hostname, h.interfaces AS interfaces"
            )
            for record in result:
                hostname = record["hostname"]
                interfaces = record["interfaces"] or []
                for iface in interfaces:
                    try:
                        # Parse each interface as a CIDR
                        net = ip_network(f"{iface}", strict=False)
                        if target_net.overlaps(net):
                            matching_hosts.append(hostname)
                            break
                    except Exception:
                        continue

        return list(set(matching_hosts))

    def _format_path(self, path):
        """
        Helper to extract hostnames from a path.
        """
        return [node["hostname"] for node in path.nodes]

    def _format_path_with_metadata(self, path):
        """
        Converts a Neo4j Path object into a list of (src, metadata, dst) tuples with full metadata.
        """
        segments = []
        nodes = path.nodes
        rels = path.relationships

        for i in range(len(rels)):
            src = nodes[i]["hostname"]
            dst = nodes[i + 1]["hostname"]
            # Extract all properties of the relationship (metadata)
            meta = dict(rels[i])  # Includes user, method, creds, ip, port, etc.
            segments.append((src, meta, dst))

        return segments
