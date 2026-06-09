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
from modules.credential_store import CredentialStore
from modules.SSHSessionManager import SSHSessionManager
from modules.logger import sshmap_logger
from modules.utils import sanitize_filename_component
import html
import asyncio
import json
import subprocess
import os
import sys
from datetime import datetime

# Determine the correct paths for templates and static files
# Try multiple locations to find the files
def find_resource_dir(dirname):
    """Find the directory containing web resources (templates/static)"""
    expected_files = {
        'templates': ['index.html'],
        'static': [os.path.join('css', 'style.css'), os.path.join('js', 'app.js')]
    }

    def has_expected_files(base_path):
        files = expected_files.get(dirname, [])
        return all(os.path.exists(os.path.join(base_path, rel_path)) for rel_path in files)

    # Try current directory (development)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(current_dir, dirname)
    if os.path.exists(path) and has_expected_files(path):
        return path
    
    # Try sys.prefix (pipx installation)
    path = os.path.join(sys.prefix, 'sshmap', dirname)
    if os.path.exists(path) and has_expected_files(path):
        return path
    
    # Try site-packages location
    import site
    for site_dir in site.getsitepackages() + [site.getusersitepackages()]:
        path = os.path.join(site_dir, dirname)
        if os.path.exists(path) and has_expected_files(path):
            return path
    
    # Fallback to current directory
    return os.path.join(current_dir, dirname)

_template_folder = find_resource_dir('templates')
_static_folder = find_resource_dir('static')

app = Flask(__name__, 
            template_folder=_template_folder,
            static_folder=_static_folder)

# Initialize Neo4j connection
db = GraphDB(
    uri=CONFIG['neo4j_uri'],
    user=CONFIG['neo4j_user'],
    password=CONFIG['neo4j_pass']
)


def _parse_import_flag(raw_value):
    """Interpret checkbox/form flags consistently across JSON and form uploads."""
    if isinstance(raw_value, bool):
        return raw_value
    if raw_value is None:
        return False
    return str(raw_value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _normalize_import_time(raw_value):
    """Keep imported relationship times numeric when possible for freshness queries."""
    if raw_value in (None, ''):
        return None
    if isinstance(raw_value, bool):
        raise ValueError('Relationship time must not be a boolean value')
    if isinstance(raw_value, (int, float)):
        return int(raw_value)
    if isinstance(raw_value, str):
        value = raw_value.strip()
        if not value:
            return None
        if value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
            return int(value)
        try:
            return int(datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() * 1000)
        except ValueError as exc:
            raise ValueError(f'Unsupported relationship time value: {raw_value}') from exc
    raise ValueError(f'Unsupported relationship time type: {type(raw_value).__name__}')


def _load_import_payload(req):
    """Load import JSON from either multipart upload or JSON request body."""
    upload = req.files.get('file')
    if upload:
        filename = upload.filename or 'upload.json'
        if not filename.lower().endswith('.json'):
            raise ValueError('Import file must be a JSON file')

        try:
            payload = json.load(upload.stream)
        except json.JSONDecodeError as exc:
            raise ValueError(f'Invalid JSON file: {exc.msg}') from exc

        return payload, _parse_import_flag(req.form.get('replace_existing'))

    payload = req.get_json(silent=True)
    if payload is None:
        raise ValueError('Upload a JSON export file or send a JSON body')

    return payload, _parse_import_flag(payload.get('replace_existing'))


def _validate_import_payload(payload):
    """Validate and normalize a graph import payload."""
    if not isinstance(payload, dict):
        raise ValueError('Import payload must be a JSON object')

    nodes = payload.get('nodes')
    edges = payload.get('edges')
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError('Import payload must include nodes and edges arrays')

    normalized_nodes = []
    hostnames = set()
    for index, node in enumerate(nodes, start=1):
        if not isinstance(node, dict):
            raise ValueError(f'Node #{index} must be an object')

        hostname = str(node.get('hostname', '')).strip()
        if not hostname:
            raise ValueError(f'Node #{index} is missing hostname')

        interfaces = node.get('interfaces') or []
        if not isinstance(interfaces, list):
            raise ValueError(f'Node #{index} interfaces must be a list')

        normalized_nodes.append({
            'hostname': hostname,
            'interfaces': [str(interface) for interface in interfaces]
        })
        hostnames.add(hostname)

    normalized_edges = []
    for index, edge in enumerate(edges, start=1):
        if not isinstance(edge, dict):
            raise ValueError(f'Edge #{index} must be an object')

        from_hostname = str(edge.get('from_hostname', '')).strip()
        to_hostname = str(edge.get('to_hostname', '')).strip()
        if not from_hostname or not to_hostname:
            raise ValueError(f'Edge #{index} must include from_hostname and to_hostname')
        if from_hostname not in hostnames or to_hostname not in hostnames:
            raise ValueError(f'Edge #{index} references a hostname not present in nodes')

        port = edge.get('port')
        if port in (None, ''):
            raise ValueError(f'Edge #{index} is missing port')

        try:
            normalized_port = int(port)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'Edge #{index} port must be an integer') from exc

        normalized_edges.append({
            'from_hostname': from_hostname,
            'to_hostname': to_hostname,
            'user': str(edge.get('user', '')),
            'method': str(edge.get('method', '')),
            'creds': str(edge.get('creds', '')),
            'ip': str(edge.get('ip', '')),
            'port': normalized_port,
            'time': _normalize_import_time(edge.get('time'))
        })

    return normalized_nodes, normalized_edges


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
            hostname = html.escape(host['hostname'])
            interfaces = [html.escape(ip) for ip in host['interfaces']]
            interfaces_str = ', '.join(interfaces) if interfaces else 'N/A'
            nodes.append({
                'id': host['id'],
                'label': hostname,
                'hostname': hostname,
                'interfaces': interfaces,
                'title': f"{hostname}<br>IPs: {interfaces_str}"
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
                    # Escape user input for HTML display
                    user = html.escape(str(record['user']))
                    ip = html.escape(str(record['ip']))
                    method = html.escape(str(record['method']))
                    from_hostname = html.escape(str(record['from_hostname']))
                    to_hostname = html.escape(str(record['to_hostname']))
                    creds = html.escape(str(record['creds']))

                    edges.append({
                        'id': edge_id,
                        'from': record['from_id'],
                        'to': record['to_id'],
                        'from_hostname': from_hostname,
                        'to_hostname': to_hostname,
                        'user': user,
                        'method': method,
                        'creds': creds,
                        'ip': ip,
                        'port': record['port'],
                        'time': record['time'],
                        'title': f"{user}@{ip}:{record['port']}<br>Method: {method}",
                        'label': f"{user}@{ip}"
                    })

        return jsonify({
            'nodes': nodes,
            'edges': edges
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/export')
def export_graph():
    """Export full graph as JSON for offline analysis or reporting."""
    try:
        hosts = db.get_all_hosts_detailed()
        nodes = []
        for host in hosts:
            nodes.append({
                'id': host['id'],
                'hostname': host['hostname'],
                'interfaces': host['interfaces']
            })

        edges = []
        with db.driver.session() as session:
            result = session.run("""
                MATCH (a:Host)-[r:SSH_ACCESS]->(b:Host)
                RETURN id(r) AS edge_id,
                       id(a) AS from_id,
                       id(b) AS to_id,
                       a.hostname AS from_hostname,
                       b.hostname AS to_hostname,
                       r.user AS user,
                       r.method AS method,
                       r.creds AS creds,
                       r.ip AS ip,
                       r.port AS port,
                       r.time AS time
            """)

            for record in result:
                time_value = record['time']
                if hasattr(time_value, 'isoformat'):
                    time_value = time_value.isoformat()

                edges.append({
                    'id': record['edge_id'],
                    'from': record['from_id'],
                    'to': record['to_id'],
                    'from_hostname': record['from_hostname'],
                    'to_hostname': record['to_hostname'],
                    'user': record['user'],
                    'method': record['method'],
                    'creds': record['creds'],
                    'ip': record['ip'],
                    'port': record['port'],
                    'time': time_value
                })

        return jsonify({
            'exported_at': datetime.utcnow().isoformat() + 'Z',
            'node_count': len(nodes),
            'edge_count': len(edges),
            'nodes': nodes,
            'edges': edges
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/import', methods=['POST'])
def import_graph():
    """Import a previously exported graph snapshot into Neo4j."""
    try:
        payload, replace_existing = _load_import_payload(request)
        nodes, edges = _validate_import_payload(payload)

        with db.driver.session() as session:
            if replace_existing:
                session.run("""
                    MATCH (n:Host)
                    DETACH DELETE n
                """)

            if nodes:
                session.run(
                    """
                    UNWIND $nodes AS node
                    MERGE (h:Host {hostname: node.hostname})
                    SET h.interfaces = node.interfaces
                    """,
                    nodes=nodes,
                )

            if edges:
                session.run(
                    """
                    UNWIND $edges AS edge
                    MATCH (src:Host {hostname: edge.from_hostname})
                    MATCH (dst:Host {hostname: edge.to_hostname})
                    MERGE (src)-[r:SSH_ACCESS {
                        user: edge.user,
                        method: edge.method,
                        creds: edge.creds,
                        ip: edge.ip,
                        port: edge.port
                    }]->(dst)
                    SET r.time = edge.time
                    """,
                    edges=edges,
                )

        return jsonify({
            'success': True,
            'message': 'Database import completed successfully',
            'nodes_imported': len(nodes),
            'relationships_imported': len(edges),
            'replace_existing': replace_existing
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
                WHERE toLower(a.hostname) CONTAINS $search_query
                   OR toLower(b.hostname) CONTAINS $search_query
                   OR toLower(r.user) CONTAINS $search_query
                   OR toLower(r.ip) CONTAINS $search_query
                   OR toLower(toString(r.port)) CONTAINS $search_query
                RETURN id(a) AS from_id, id(b) AS to_id, id(r) AS edge_id,
                       a.hostname AS from_hostname, b.hostname AS to_hostname,
                       r.user AS user, r.method AS method, r.creds AS creds,
                       r.ip AS ip, r.port AS port
            """, search_query=query)

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
                RETURN id(r) AS edge_id, target.hostname AS target, r.user AS user,
                       r.method AS method, r.ip AS ip, r.port AS port
            """, node_id=node_id)

            # Get incoming connections
            incoming = session.run("""
                MATCH (source:Host)-[r:SSH_ACCESS]->(h:Host)
                WHERE id(h) = $node_id
                RETURN id(r) AS edge_id, source.hostname AS source, r.user AS user,
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


@app.route('/api/node/<int:node_id>', methods=['DELETE'])
def delete_node(node_id):
    """
    Delete a node (host) from the database.
    """
    try:
        with db.driver.session() as session:
            result = session.run("""
                MATCH (n:Host)
                WHERE id(n) = $node_id
                DETACH DELETE n
                RETURN count(n) AS deleted
            """, node_id=node_id)
            
            record = result.single()
            if record['deleted'] > 0:
                return jsonify({'success': True, 'message': 'Node deleted successfully'})
            else:
                return jsonify({'success': False, 'error': 'Node not found'}), 404
                
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/edge/<int:edge_id>', methods=['DELETE'])
def delete_edge(edge_id):
    """
    Delete an edge (SSH_ACCESS relationship) from the database.
    """
    try:
        with db.driver.session() as session:
            result = session.run("""
                MATCH ()-[r:SSH_ACCESS]->()
                WHERE id(r) = $edge_id
                DELETE r
                RETURN count(r) AS deleted
            """, edge_id=edge_id)
            
            record = result.single()
            if record['deleted'] > 0:
                return jsonify({'success': True, 'message': 'Edge deleted successfully'})
            else:
                return jsonify({'success': False, 'error': 'Edge not found'}), 404
                
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/clean-database', methods=['DELETE'])
def clean_database():
    """
    Delete all nodes and relationships from the database.
    """
    try:
        with db.driver.session() as session:
            # Count before deletion
            count_result = session.run("""
                MATCH (n:Host)
                OPTIONAL MATCH (n)-[r:SSH_ACCESS]-()
                RETURN count(DISTINCT n) AS nodes, count(DISTINCT r) AS rels
            """)
            counts = count_result.single()
            
            # Delete everything
            session.run("""
                MATCH (n:Host)
                DETACH DELETE n
            """)
            
            return jsonify({
                'success': True,
                'message': 'Database cleaned successfully',
                'nodes_deleted': counts['nodes'],
                'relationships_deleted': counts['rels']
            })
                
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/execute', methods=['POST'])
def execute_command():
    """
    Execute a command on a target host.
    Expects JSON: {"hostname": "target", "command": "ls -la"}
    """
    try:
        data = request.json
        hostname = data.get('hostname')
        command = data.get('command')
        
        if not hostname or not command:
            return jsonify({'error': 'hostname and command are required'}), 400
        
        # Run the command execution in a separate thread to avoid blocking
        result = asyncio.run(execute_command_async(hostname, command))
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


async def execute_command_async(hostname, command):
    """
    Async function to execute command on target host.
    """
    try:
        # Get local hostname
        try:
            local_hostname = subprocess.run(
                ["hostname"], capture_output=True, text=True, check=True
            ).stdout.strip()
            sshmap_logger.display(f"Local hostname: {local_hostname}")
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to get local hostname: {str(e)}'
            }
        
        # Initialize credential store
        try:
            credential_store = CredentialStore("wordlists/credentials.csv")
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to load credentials: {str(e)}'
            }
        
        # Create SSH session manager
        ssh_session_manager = SSHSessionManager(
            graphdb=db, 
            credential_store=credential_store
        )
        
        # Get SSH session
        sshmap_logger.display(f"Attempting to establish SSH session to {hostname}...")
        host_ssh = await ssh_session_manager.get_session(hostname, local_hostname)
        
        if not host_ssh:
            return {
                'success': False,
                'error': f'Could not establish SSH session to {hostname}. The host may not be reachable or no valid credentials found.'
            }
        
        # Verify the connection is actually established
        if not await host_ssh.is_connected():
            return {
                'success': False,
                'error': f'SSH session to {hostname} was created but connection is not active. The host may have disconnected.'
            }
        
        sshmap_logger.display(f"SSH session established with {hostname} as {host_ssh.user}")
        
        # Execute the command
        try:
            output = await host_ssh.exec_command(command)
        except ValueError as e:
            return {
                'success': False,
                'error': f'Cannot execute command: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Command execution failed: {str(e)}'
            }
        
        # Save output to file
        currenttime = datetime.now().strftime('%Y%m%d_%H%M%S')
        os.makedirs('output', exist_ok=True)
        safe_hostname = sanitize_filename_component(hostname)
        safe_command = sanitize_filename_component(command[:10])
        output_filename = os.path.join(
            'output', f"{currenttime}_{safe_hostname}_{safe_command}.txt"
        )
        
        try:
            with open(output_filename, 'w') as f:
                f.write(f"Output from {hostname}:\n")
                f.write(f"Executed command: {command}\n")
                f.write(f"User: {host_ssh.user}\n\n")
                f.write(output)
        except Exception as e:
            sshmap_logger.warning(f"Failed to save output to file: {e}")
            # Continue anyway, at least return the output
        
        sshmap_logger.success(f"Command executed successfully on {hostname}")
        
        return {
            'success': True,
            'output': output,
            'hostname': hostname,
            'command': command,
            'user': host_ssh.user,
            'output_file': output_filename
        }
        
    except Exception as e:
        error_msg = f"Failed to execute command on {hostname}: {type(e).__name__} - {str(e)}"
        sshmap_logger.error(error_msg)
        return {
            'success': False,
            'error': error_msg
        }


if __name__ == '__main__':
    print("=" * 60)
    print("SSHMAP Web Interface")
    print("=" * 60)
    print("Starting web server on http://localhost:5000")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)

    # Run on localhost only (no external access)
    # Debug mode is disabled for security (prevents code execution via web interface)
    app.run(host='127.0.0.1', port=5000, debug=False)
