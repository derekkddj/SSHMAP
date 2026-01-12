from neo4j import GraphDatabase
from ipaddress import ip_network
import os
import time


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
            # Write jump hosts (excluding the last one which is the final target)
            for idx, (src, meta, dst) in enumerate(path[:-1]):
                alias = f"jump{idx}"
                host_aliases.append((alias, meta))

                f.write(f"Host {alias}\n")
                f.write(f"    HostName {meta['ip']}\n")
                f.write(f"    User {meta['user']}\n")
                f.write(f"    Port {meta['port']}\n")
                if "keyfile" in meta["method"]:
                    f.write(f"    IdentityFile {meta['creds']}\n")
                f.write("\n")

            # Final hop is the actual target
            final_alias = "target"
            _, final_meta, _ = path[-1]

            f.write(f"Host {final_alias}\n")
            f.write(f"    HostName {final_meta['ip']}\n")
            f.write(f"    User {final_meta['user']}\n")
            f.write(f"    Port {final_meta['port']}\n")
            if "keyfile" in meta["method"]:
                f.write(f"    IdentityFile {meta['creds']}\n")

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
                    key_path = meta["method"]
                    ssh_part = f"ssh -o StrictHostKeyChecking=no -p {port} -W %h:%p {user}@{host} "
                    if "keyfile" in key_path:
                        ssh_part += f"-i {meta['creds']} "
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

    def find_freshest_paths(self, start_hostname, end_hostname, limit=5, max_depth=15):
        """
        Find multiple freshest paths from start_hostname to end_hostname through SSH_ACCESS relationships.
        Paths are sorted by freshness based on inverted 'time' edge property.
        Returns list of paths, each path is list of (src, meta, dst).
        """
        query = """
        MATCH (start:Host {hostname: $start}), (end:Host {hostname: $end})
        CALL apoc.path.expandConfig(start, {
            relationshipFilter: 'SSH_ACCESS>',
            labelFilter: '+Host',
            endNodes: [end],
            uniqueness: 'NODE_GLOBAL',
            bfs: true,
            limit: $limit,
            maxLevel: $max_depth,
            filterStartNode: true
        }) YIELD path
        WITH path, reduce(
            inv_weight = 0, r IN relationships(path) |
            inv_weight + (9999999999999 - coalesce(r.time, 0))
        ) AS total_inv_weight
        RETURN path, total_inv_weight
        ORDER BY total_inv_weight ASC
        LIMIT $limit
        """

        with self.driver.session() as session:
            result = session.run(
                query,
                start=start_hostname,
                end=end_hostname,
                limit=limit,
                max_depth=max_depth,
            )

            all_paths = []
            for record in result:
                path = record["path"]
                nodes = record["nodes"] if "nodes" in record else path.nodes
                rels = (
                    record["relationships"]
                    if "relationships" in record
                    else path.relationships
                )

                path_segments = []
                for i in range(len(rels)):
                    src = nodes[i]["hostname"]
                    dst = nodes[i + 1]["hostname"]
                    rel = rels[i]
                    meta = {
                        "user": rel.get("user"),
                        "method": rel.get("method"),
                        "creds": rel.get("creds"),
                        "ip": rel.get("ip"),
                        "port": rel.get("port"),
                        "time": rel.get("time"),
                    }
                    path_segments.append((src, meta, dst))
                all_paths.append(path_segments)

            return all_paths

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

    def get_host(self, hostname):
        """
        Retrieve a host by its hostname.
        Returns a dictionary with hostname and interfaces (IP/mask pairs in CIDR).
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (h:Host {hostname: $hostname}) RETURN h.hostname AS hostname, h.interfaces AS interfaces",
                hostname=hostname,
            )
            record = result.single()
            if record:
                return {
                    "hostname": record["hostname"],
                    "interfaces": record["interfaces"] or [],
                }
            return None

    def get_all_hosts(self):
        """
        Retrieve all hosts in the database.
        Returns a list of dictionaries with hostname and interfaces (IP/mask pairs in CIDR).
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (h:Host) RETURN h.hostname AS hostname, h.interfaces AS interfaces"
            )
            return [
                {
                    "hostname": record["hostname"],
                    "interfaces": record["interfaces"] or [],
                }
                for record in result
            ]

    def add_ssh_connection(
        self, from_hostname, to_hostname, user, method, creds, ip, port
    ):
        # Get current time in milliseconds since epoch
        currentmilis = round(time.time() * 1000)  # Uncomment if you want
        # We have to use MERGE here to avoid duplicates
        # If the relationship already exists, it will not create a new one
        # If it does not exist, it will create a new one with the provided properties
        # Update the "time" property of the existing SSH_ACCESS relationship if it exists,
        # otherwise create a new one with all properties.
        with self.driver.session() as session:
            session.run(
                """
            MATCH (src:Host {hostname: $from_hostname})-[r:SSH_ACCESS]->(dst:Host {hostname: $to_hostname})
            WHERE r.user = $user AND r.method = $method AND r.creds = $creds AND r.ip = $ip AND r.port = $port
            SET r.time = $currentmilis
            WITH count(r) AS updated
            CALL apoc.do.when(
                updated = 0,
                'MATCH (src:Host {hostname: $from_hostname}), (dst:Host {hostname: $to_hostname}) MERGE (src)-[r:SSH_ACCESS {user: $user, method: $method, creds: $creds, ip: $ip, port: $port}]->(dst) SET r.time = $currentmilis',
                '',
                {from_hostname: $from_hostname, to_hostname: $to_hostname, user: $user, method: $method, creds: $creds, ip: $ip, port: $port, currentmilis: $currentmilis}
            ) YIELD value
            RETURN value
            """,
                from_hostname=from_hostname,
                to_hostname=to_hostname,
                user=user,
                method=method,
                creds=creds,
                ip=ip,
                port=port,
                currentmilis=currentmilis,
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

    def get_all_hosts_detailed(self):
        """
        Retrieve all hosts with their IDs and full details.
        Returns a list of dicts: [{'id': int, 'hostname': str, 'interfaces': [...]}, ...]
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (h:Host) RETURN id(h) AS id, h.hostname AS hostname, h.interfaces AS interfaces"
            )
            return [
                {
                    "id": record["id"],
                    "hostname": record["hostname"],
                    "interfaces": record["interfaces"] or [],
                }
                for record in result
            ]

    def get_connections_from_host(self, hostname):
        """
        Retrieve all SSH_ACCESS relationships originating from a given hostname.
        Returns a list of dicts: [{'id': int, 'from': str, 'to': str, 'type': str, 'props': {...}}, ...]
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (a:Host {hostname:$hostname})-[r:SSH_ACCESS]->(b:Host)
                RETURN id(r) AS id, a.hostname AS from, b.hostname AS to, type(r) AS type, r AS props
                """,
                hostname=hostname,
            )
            rels = []
            for record in result:
                props = dict(record["props"]) if record["props"] is not None else {}
                rels.append(
                    {
                        "id": record["id"],
                        "from": record["from"],
                        "to": record["to"],
                        "type": record["type"],
                        "props": props,
                    }
                )
            return rels

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

    def has_connection_been_attempted(self, from_hostname, to_ip, port, user, method, creds):
        """
        Check if a specific connection attempt has already been tried.
        
        :param from_hostname: Source hostname
        :param to_ip: Target IP address
        :param port: Target port
        :param user: Username for authentication
        :param method: Authentication method (password/keyfile)
        :param creds: Credentials (password or key path)
        :return: True if attempt was already made, False otherwise
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (src:Host {hostname: $from_hostname})-[r:SSH_ATTEMPT]->(dst)
                WHERE r.ip = $ip AND r.port = $port AND r.user = $user 
                    AND r.method = $method AND r.creds = $creds
                RETURN r
                LIMIT 1
                """,
                from_hostname=from_hostname,
                ip=to_ip,
                port=port,
                user=user,
                method=method,
                creds=creds,
            )
            return result.single() is not None

    def record_connection_attempt(self, from_hostname, to_hostname, to_ip, port, user, method, creds, success):
        """
        Record a connection attempt (successful or failed).
        
        :param from_hostname: Source hostname
        :param to_hostname: Target hostname (if known)
        :param to_ip: Target IP address
        :param port: Target port
        :param user: Username used
        :param method: Authentication method (password/keyfile)
        :param creds: Credentials used
        :param success: Whether the attempt was successful
        """
        currentmilis = round(time.time() * 1000)
        with self.driver.session() as session:
            # Ensure target host exists (even if we don't have a hostname yet)
            session.run(
                """
                MERGE (dst:Host {hostname: $to_hostname})
                """,
                to_hostname=to_hostname if to_hostname else to_ip,
            )
            
            # Record the attempt
            session.run(
                """
                MATCH (src:Host {hostname: $from_hostname})
                MATCH (dst:Host {hostname: $to_hostname})
                MERGE (src)-[r:SSH_ATTEMPT {ip: $ip, port: $port, user: $user, method: $method, creds: $creds}]->(dst)
                SET r.last_attempt = $time, r.success = $success
                """,
                from_hostname=from_hostname,
                to_hostname=to_hostname if to_hostname else to_ip,
                ip=to_ip,
                port=port,
                user=user,
                method=method,
                creds=creds,
                time=currentmilis,
                success=success,
            )

    def get_all_attempted_connections(self, from_hostname):
        """
        Get all connection attempts from a specific host.
        
        :param from_hostname: Source hostname
        :return: List of connection attempt details
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (src:Host {hostname: $from_hostname})-[r:SSH_ATTEMPT]->(dst:Host)
                RETURN dst.hostname AS to_hostname, r.ip AS ip, r.port AS port, 
                       r.user AS user, r.method AS method, r.creds AS creds, 
                       r.success AS success, r.last_attempt AS last_attempt
                """,
                from_hostname=from_hostname,
            )
            return [
                {
                    "to_hostname": record["to_hostname"],
                    "ip": record["ip"],
                    "port": record["port"],
                    "user": record["user"],
                    "method": record["method"],
                    "creds": record["creds"],
                    "success": record["success"],
                    "last_attempt": record["last_attempt"],
                }
                for record in result
            ]

    def get_all_known_jump_hosts(self, start_hostname):
        """
        Get all hosts that have successful SSH_ACCESS connections and can be used as jump hosts.
        Excludes the start_hostname itself.
        
        :param start_hostname: The starting hostname to exclude
        :return: List of hostnames that can be used as jump hosts
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (h:Host)
                WHERE h.hostname <> $start_hostname
                AND EXISTS((h)-[:SSH_ACCESS]->())
                RETURN DISTINCT h.hostname AS hostname
                """,
                start_hostname=start_hostname,
            )
            return [record["hostname"] for record in result]

    def get_targets_accessible_from_host(self, from_hostname):
        """
        Get all target IPs and ports that are accessible from a given host.
        Returns targets from both SSH_ACCESS and SSH_ATTEMPT edges.
        
        :param from_hostname: Source hostname
        :return: Set of (ip, port) tuples
        """
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (src:Host {hostname: $from_hostname})-[r]->(dst:Host)
                WHERE type(r) = 'SSH_ACCESS' OR type(r) = 'SSH_ATTEMPT'
                RETURN DISTINCT r.ip AS ip, r.port AS port
                """,
                from_hostname=from_hostname,
            )
            return {(record["ip"], record["port"]) for record in result}
