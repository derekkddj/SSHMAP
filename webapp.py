from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pyvis.network import Network
from neo4j import GraphDatabase
from config import CONFIG

app = FastAPI()

class Visualizer:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def get_graph_html(self):
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
        net.show("templates/graph.html")
        with open("templates/graph.html") as f:
            return f.read()

@app.get("/graph", response_class=HTMLResponse)
def graph():
    viz = Visualizer(CONFIG["neo4j_uri"], CONFIG["neo4j_user"], CONFIG["neo4j_pass"])
    html = viz.get_graph_html()
    viz.close()
    return HTMLResponse(content=html)
