#!/usr/bin/env python3
"""
SSHMAP Web Interface
A web application for visualizing and exploring SSH connection data stored in Neo4j.
This application runs on localhost only and provides an intuitive GUI for:
- Viewing the graph of SSH connections
- Searching for nodes and edges
- Finding paths between nodes
"""

from flask import Flask, render_template, jsonify, request
from modules.graphdb import GraphDB
from modules.config import CONFIG
import os

app = Flask(__name__)

# Initialize Neo4j connection
db = GraphDB(
    uri=CONFIG['neo4j_uri'],
    user=CONFIG['neo4j_user'],
    password=CONFIG['neo4j_pass']
)


@app.route('/')
def index():
    """Main page with graph visualization"""
    return render_template('index.html')


@app.route('/api/graph')
def get_graph():
    """
    Get all nodes and edges for visualization.
    Returns JSON with nodes and edges arrays.
    """
    try:
        # Get all hosts (nodes)
        hosts = db.get_all_hosts_detailed()
        nodes = []
        for host in hosts:
            nodes.append({
                'id': host['id'],
                'label': host['hostname'],
                'hostname': host['hostname'],
                'interfaces': host['interfaces'],
                'title': f"{host['hostname']}<br>IPs: {', '.join(host['interfaces']) if host['interfaces'] else 'N/A'}"
            })
        
        # Get all SSH_ACCESS relationships (edges)
        edges = []
        edge_ids = set()  # Track unique edges
        
        with db.driver.session() as session:
            result = session.run("""
                MATCH (a:Host)-[r:SSH_ACCESS]->(b:Host)
                RETURN id(a) AS from_id, id(b) AS to_id, id(r) AS edge_id,
                       a.hostname AS from_hostname, b.hostname AS to_hostname,
                       r.user AS user, r.method AS method, r.creds AS creds,
                       r.ip AS ip, r.port AS port, r.time AS time
            """)
            
            for record in result:
                edge_id = record['edge_id']
                if edge_id not in edge_ids:
                    edge_ids.add(edge_id)
                    edges.append({
                        'id': edge_id,
                        'from': record['from_id'],
                        'to': record['to_id'],
                        'from_hostname': record['from_hostname'],
                        'to_hostname': record['to_hostname'],
                        'user': record['user'],
                        'method': record['method'],
                        'creds': record['creds'],
                        'ip': record['ip'],
                        'port': record['port'],
                        'time': record['time'],
                        'title': f"{record['user']}@{record['ip']}:{record['port']}<br>Method: {record['method']}",
                        'label': f"{record['user']}@{record['ip']}"
                    })
        
        return jsonify({
            'nodes': nodes,
            'edges': edges
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/search')
def search():
    """
    Search for nodes or edges by text query.
    Query parameter: q (search query)
    Returns matching nodes and edges.
    """
    try:
        query = request.args.get('q', '').lower()
        if not query:
            return jsonify({'nodes': [], 'edges': []})
        
        # Search nodes (hosts)
        matching_nodes = []
        hosts = db.get_all_hosts_detailed()
        for host in hosts:
            if (query in host['hostname'].lower() or 
                any(query in ip.lower() for ip in host['interfaces'])):
                matching_nodes.append({
                    'id': host['id'],
                    'label': host['hostname'],
                    'hostname': host['hostname'],
                    'interfaces': host['interfaces']
                })
        
        # Search edges (connections)
        matching_edges = []
        with db.driver.session() as session:
            result = session.run("""
                MATCH (a:Host)-[r:SSH_ACCESS]->(b:Host)
                WHERE toLower(a.hostname) CONTAINS $query
                   OR toLower(b.hostname) CONTAINS $query
                   OR toLower(r.user) CONTAINS $query
                   OR toLower(r.ip) CONTAINS $query
                   OR toLower(toString(r.port)) CONTAINS $query
                RETURN id(a) AS from_id, id(b) AS to_id, id(r) AS edge_id,
                       a.hostname AS from_hostname, b.hostname AS to_hostname,
                       r.user AS user, r.method AS method, r.creds AS creds,
                       r.ip AS ip, r.port AS port
            """, query=query)
            
            for record in result:
                matching_edges.append({
                    'id': record['edge_id'],
                    'from': record['from_id'],
                    'to': record['to_id'],
                    'from_hostname': record['from_hostname'],
                    'to_hostname': record['to_hostname'],
                    'user': record['user'],
                    'method': record['method'],
                    'creds': record['creds'],
                    'ip': record['ip'],
                    'port': record['port']
                })
        
        return jsonify({
            'nodes': matching_nodes,
            'edges': matching_edges
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/node/<int:node_id>')
def get_node(node_id):
    """
    Get detailed information about a specific node.
    """
    try:
        with db.driver.session() as session:
            result = session.run("""
                MATCH (h:Host)
                WHERE id(h) = $node_id
                RETURN id(h) AS id, h.hostname AS hostname, h.interfaces AS interfaces
            """, node_id=node_id)
            
            record = result.single()
            if not record:
                return jsonify({'error': 'Node not found'}), 404
            
            # Get outgoing connections
            outgoing = session.run("""
                MATCH (h:Host)-[r:SSH_ACCESS]->(target:Host)
                WHERE id(h) = $node_id
                RETURN target.hostname AS target, r.user AS user, 
                       r.method AS method, r.ip AS ip, r.port AS port
            """, node_id=node_id)
            
            # Get incoming connections
            incoming = session.run("""
                MATCH (source:Host)-[r:SSH_ACCESS]->(h:Host)
                WHERE id(h) = $node_id
                RETURN source.hostname AS source, r.user AS user,
                       r.method AS method, r.ip AS ip, r.port AS port
            """, node_id=node_id)
            
            return jsonify({
                'id': record['id'],
                'hostname': record['hostname'],
                'interfaces': record['interfaces'],
                'outgoing_connections': [dict(r) for r in outgoing],
                'incoming_connections': [dict(r) for r in incoming]
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/edge/<int:edge_id>')
def get_edge(edge_id):
    """
    Get detailed information about a specific edge.
    """
    try:
        with db.driver.session() as session:
            result = session.run("""
                MATCH (a:Host)-[r:SSH_ACCESS]->(b:Host)
                WHERE id(r) = $edge_id
                RETURN id(r) AS id, a.hostname AS from_hostname, b.hostname AS to_hostname,
                       r.user AS user, r.method AS method, r.creds AS creds,
                       r.ip AS ip, r.port AS port, r.time AS time
            """, edge_id=edge_id)
            
            record = result.single()
            if not record:
                return jsonify({'error': 'Edge not found'}), 404
            
            return jsonify(dict(record))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/path', methods=['POST'])
def find_path():
    """
    Find path(s) between two nodes.
    JSON body: {
        "start": "hostname1",
        "end": "hostname2",
        "all": false (optional, default false)
    }
    """
    try:
        data = request.get_json()
        start = data.get('start')
        end = data.get('end')
        find_all = data.get('all', False)
        
        if not start or not end:
            return jsonify({'error': 'start and end parameters are required'}), 400
        
        if find_all:
            # Find all paths (limited to reasonable depth)
            paths = db.find_all_paths_to(start, end, max_depth=10)
        else:
            # Find shortest path
            path = db.find_path(start, end)
            paths = [path] if path else []
        
        if not paths:
            return jsonify({'paths': [], 'message': 'No path found'})
        
        # Format paths for display
        formatted_paths = []
        for path in paths:
            formatted_path = []
            for src, meta, dst in path:
                formatted_path.append({
                    'from': src,
                    'to': dst,
                    'user': meta['user'],
                    'method': meta['method'],
                    'creds': meta['creds'],
                    'ip': meta['ip'],
                    'port': meta['port']
                })
            formatted_paths.append(formatted_path)
        
        return jsonify({'paths': formatted_paths})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/hosts')
def get_hosts():
    """
    Get list of all hostnames for autocomplete.
    """
    try:
        hosts = db.get_all_hosts()
        hostnames = [h['hostname'] for h in hosts]
        return jsonify({'hostnames': hostnames})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("SSHMAP Web Interface")
    print("=" * 60)
    print(f"Starting web server on http://localhost:5000")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    
    # Run on localhost only (no external access)
    app.run(host='127.0.0.1', port=5000, debug=True)
