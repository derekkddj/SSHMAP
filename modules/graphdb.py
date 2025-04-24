from neo4j import GraphDatabase

class GraphDB:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def add_ssh_path(self, from_ip, to_ip, user, method):
        with self.driver.session() as session:
            session.run("""
                MERGE (a:Host {ip: $from})
                MERGE (b:Host {ip: $to})
                MERGE (a)-[:CAN_SSH_TO {user: $user, method: $method}]->(b)
            """, from=from_ip, to=to_ip, user=user, method=method)
