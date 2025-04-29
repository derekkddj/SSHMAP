from neo4j import GraphDatabase
from ipaddress import ip_network

# graphdb.py

class GraphDB:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def add_host(self, hostname, ip_info):
        """
        Store host with multiple IPs and subnet masks in CIDR notation.
        ip_info = [{'ip': '192.168.1.10', 'mask': 24}, ...]
        """
        # Convert IP/mask pairs to CIDR notation (e.g., '192.168.1.10/24')
        cidr_info = [f"{iface['ip']}/{iface['mask']}" for iface in ip_info]
        with self.driver.session() as session:
            session.run("""
                MERGE (h:Host {hostname: $hostname})
                SET h.interfaces = $cidr_info
            """, hostname=hostname, cidr_info=cidr_info)

    def add_ssh_connection(self, from_hostname, to_hostname, user, method,creds,ip,port):
        with self.driver.session() as session:
            session.run("""
                MATCH (src:Host {hostname: $from_hostname})
                MATCH (dst:Host {hostname: $to_hostname})
                MERGE (src)-[r:SSH_ACCESS {user: $user, method: $method, creds: $creds, ip: $ip, port:$port}]->(dst)
            """, from_hostname=from_hostname, to_hostname=to_hostname, user=user, method=method, creds=creds,ip=ip,port=port)



    def find_hosts_in_same_subnet(self, ip, mask):
        target_net = ip_network(f"{ip}/{mask}", strict=False)
        matching_hosts = []

        with self.driver.session() as session:
            result = session.run("MATCH (h:Host) RETURN h.hostname AS hostname, h.interfaces AS interfaces")
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