from pyvis.network import Network
from neo4j import GraphDatabase
from ssh_brute_project.config import CONFIG

class Visualizer:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def generate_graph(self, output_file="ssh_network.html"):
        net = Network(height="750px", width="100%", directed=True)
        with self.driver.session() as session:
            results = session.run("MATCH (a:Host)-[r:CAN_SSH_TO]->(b:Host) RETURN a.ip AS from, b.ip AS to, r.user AS user, r.method AS method")
            for record in results:
                src = record["from"]
                dst = record["to"]
                label = f"{record['user']} ({record['method']})"
                net.add_node(src, label=src)
                net.add_node(dst, label=dst)
                net.add_edge(src, dst, label=label)
        net.show(output_file)

if __name__ == "__main__":
    viz = Visualizer(CONFIG["neo4j_uri"], CONFIG["neo4j_user"], CONFIG["neo4j_pass"])
    viz.generate_graph()
    viz.close()
    print("Graph generated: ssh_network.html")
