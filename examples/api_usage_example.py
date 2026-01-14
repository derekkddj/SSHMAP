#!/usr/bin/env python3
"""
Example script demonstrating how to use the SSHMAP Web Interface API programmatically.

This script shows various ways to interact with the API endpoints to:
- Retrieve graph data
- Search for nodes and edges
- Find paths between hosts
- Get detailed information about nodes and edges

Prerequisites:
1. Start the web interface: python3 sshmap_web.py
2. Ensure Neo4j is running with SSHMAP data
"""

import requests
import json

# Base URL for the API
BASE_URL = "http://127.0.0.1:5000"


def get_graph_data():
    """Get all nodes and edges in the graph."""
    print("=" * 60)
    print("Retrieving complete graph data...")
    print("=" * 60)

    response = requests.get(f"{BASE_URL}/api/graph")
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Found {len(data['nodes'])} nodes and {len(data['edges'])} edges")
        return data
    else:
        print(f"✗ Error: {response.status_code}")
        return None


def search_hosts(query):
    """Search for hosts matching a query."""
    print("\n" + "=" * 60)
    print(f"Searching for: '{query}'")
    print("=" * 60)

    response = requests.get(f"{BASE_URL}/api/search", params={"q": query})
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Found {len(data['nodes'])} matching nodes")
        for node in data['nodes']:
            print(f"  - {node['hostname']} (IPs: {', '.join(node['interfaces'])})")
        print(f"✓ Found {len(data['edges'])} matching edges")
        return data
    else:
        print(f"✗ Error: {response.status_code}")
        return None


def find_path(start, end):
    """Find path between two hosts."""
    print("\n" + "=" * 60)
    print(f"Finding path from '{start}' to '{end}'")
    print("=" * 60)

    response = requests.post(
        f"{BASE_URL}/api/path",
        json={"start": start, "end": end, "all": False},
        headers={"Content-Type": "application/json"}
    )

    if response.status_code == 200:
        data = response.json()
        if data['paths']:
            path = data['paths'][0]
            print(f"✓ Found path with {len(path)} hops:")
            for i, step in enumerate(path, 1):
                print(f"\n  Hop {i}: {step['from']} → {step['to']}")
                print(f"    User: {step['user']}")
                print(f"    IP: {step['ip']}:{step['port']}")
                print(f"    Method: {step['method']}")
                print(f"    Credentials: {step['creds']}")
            return path
        else:
            print("✗ No path found")
            return None
    else:
        print(f"✗ Error: {response.status_code}")
        return None


def get_node_details(node_id):
    """Get detailed information about a specific node."""
    print("\n" + "=" * 60)
    print(f"Getting details for node ID: {node_id}")
    print("=" * 60)

    response = requests.get(f"{BASE_URL}/api/node/{node_id}")
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Node: {data['hostname']}")
        print(f"  Interfaces: {', '.join(data['interfaces'])}")
        print(f"  Outgoing connections: {len(data['outgoing_connections'])}")
        print(f"  Incoming connections: {len(data['incoming_connections'])}")

        if data['outgoing_connections']:
            print("\n  Outgoing to:")
            for conn in data['outgoing_connections'][:5]:  # Show first 5
                print(f"    → {conn['target']} ({conn['user']}@{conn['ip']}:{conn['port']})")

        if data['incoming_connections']:
            print("\n  Incoming from:")
            for conn in data['incoming_connections'][:5]:  # Show first 5
                print(f"    ← {conn['source']} ({conn['user']}@{conn['ip']}:{conn['port']})")

        return data
    else:
        print(f"✗ Error: {response.status_code}")
        return None


def get_edge_details(edge_id):
    """Get detailed information about a specific edge."""
    print("\n" + "=" * 60)
    print(f"Getting details for edge ID: {edge_id}")
    print("=" * 60)

    response = requests.get(f"{BASE_URL}/api/edge/{edge_id}")
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Connection: {data['from_hostname']} → {data['to_hostname']}")
        print(f"  User: {data['user']}")
        print(f"  IP: {data['ip']}:{data['port']}")
        print(f"  Method: {data['method']}")
        print(f"  Credentials: {data['creds']}")
        if data.get('time'):
            print(f"  Last used: {data['time']}")
        return data
    else:
        print(f"✗ Error: {response.status_code}")
        return None


def get_all_hostnames():
    """Get list of all hostnames for autocomplete."""
    print("\n" + "=" * 60)
    print("Retrieving all hostnames...")
    print("=" * 60)

    response = requests.get(f"{BASE_URL}/api/hosts")
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Found {len(data['hostnames'])} hosts:")
        for hostname in data['hostnames'][:10]:  # Show first 10
            print(f"  - {hostname}")
        if len(data['hostnames']) > 10:
            print(f"  ... and {len(data['hostnames']) - 10} more")
        return data['hostnames']
    else:
        print(f"✗ Error: {response.status_code}")
        return None


def export_graph_to_json(filename="graph_export.json"):
    """Export the complete graph to a JSON file."""
    print("\n" + "=" * 60)
    print(f"Exporting graph to {filename}...")
    print("=" * 60)

    data = get_graph_data()
    if data:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✓ Graph exported to {filename}")
        return True
    return False


def main():
    """Run example API calls."""
    print("\n" + "=" * 70)
    print("SSHMAP Web Interface - API Usage Examples")
    print("=" * 70)
    print("\nMake sure the web interface is running on http://127.0.0.1:5000")
    print()

    try:
        # Example 1: Get complete graph
        graph_data = get_graph_data()

        if not graph_data or len(graph_data['nodes']) == 0:
            print("\n⚠️  No data found. Make sure:")
            print("  1. Neo4j is running")
            print("  2. SSHMAP has been run to collect data")
            print("  3. Web interface is started: python3 sshmap_web.py")
            return

        # Example 2: Search for hosts
        search_hosts("192.168")  # Search by IP
        search_hosts("root")     # Search by user

        # Example 3: Get all hostnames
        hostnames = get_all_hostnames()

        # Example 4: Find path (if we have at least 2 hosts)
        if hostnames and len(hostnames) >= 2:
            find_path(hostnames[0], hostnames[-1])

        # Example 5: Get node details (use first node)
        if graph_data['nodes']:
            first_node = graph_data['nodes'][0]
            get_node_details(first_node['id'])

        # Example 6: Get edge details (use first edge)
        if graph_data['edges']:
            first_edge = graph_data['edges'][0]
            get_edge_details(first_edge['id'])

        # Example 7: Export graph
        export_graph_to_json()

        print("\n" + "=" * 70)
        print("✓ All examples completed successfully!")
        print("=" * 70)

    except requests.exceptions.ConnectionError:
        print("\n✗ Error: Cannot connect to the web interface")
        print("  Make sure it's running: python3 sshmap_web.py")
    except Exception as e:
        print(f"\n✗ Error: {e}")


if __name__ == "__main__":
    main()
