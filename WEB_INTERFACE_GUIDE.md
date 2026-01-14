# SSHMAP Web Interface - Quick Start Guide

## Overview
The SSHMAP Web Interface provides an intuitive way to visualize and explore SSH connection data stored in your Neo4j graph database. It runs locally on your machine and offers an interactive network graph with search and path-finding capabilities.

## Prerequisites
1. **Neo4j Database**: Must be running and accessible
   - Default URI: `bolt://localhost:7687`
   - Configure in `~/.sshmap/config.yml`

2. **Python Dependencies**: Install required packages
   ```bash
   pip install -r requirements.txt
   ```

3. **SSHMAP Data**: Run SSHMAP scanner to populate the database
   ```bash
   python3 SSHMAP.py --targets wordlists/ips.txt --users wordlists/usernames.txt --passwords wordlists/passwords.txt
   ```

## Starting the Web Interface

### Option 1: Using the launcher script (Recommended)
```bash
python3 sshmap_web.py
```

### Option 2: Direct Flask app
```bash
python3 web_app.py
```

The server will start on: **http://127.0.0.1:5000**

## Features

### 1. Graph Visualization
- **Interactive Network Graph**: Visualize all hosts and SSH connections
- **Node Interaction**: Click on nodes to see detailed information
- **Edge Interaction**: Click on connections to see authentication details
- **Zoom & Pan**: Navigate large networks easily
- **Physics Simulation**: Automatic layout with adjustable physics

### 2. Search Functionality
- Search by:
  - Hostname
  - IP address
  - Username
  - Port number
- Real-time filtering as you type
- Highlights matching nodes and edges

### 3. Path Finder
- Find routes between any two hosts
- Autocomplete for hostname selection
- Visual path highlighting on the graph
- Detailed hop-by-hop information including:
  - Usernames
  - IP addresses and ports
  - Authentication methods
  - Credentials used

### 4. Node Details Panel
View comprehensive information about selected hosts:
- Hostname
- Network interfaces (IP addresses)
- Outgoing SSH connections
- Incoming SSH connections

### 5. Edge Details Panel
View connection details:
- Source and destination hosts
- Username
- Target IP and port
- Authentication method
- Credentials
- Last connection time

### 6. Statistics Dashboard
- Total number of nodes (hosts)
- Total number of connections
- Real-time updates

## Usage Examples

### Example 1: Viewing the Complete Network
1. Start the web interface: `python3 sshmap_web.py`
2. Open browser to `http://127.0.0.1:5000`
3. The graph will automatically load and display all hosts and connections

### Example 2: Finding a Specific Host
1. Use the search bar at the top
2. Type the hostname or IP address
3. The graph will filter to show matching results
4. Click on the highlighted node to see details

### Example 3: Finding a Path Between Hosts
1. Enter the starting hostname in "Start Node" field
2. Enter the target hostname in "End Node" field
3. Click "Find Path" button
4. The path will be highlighted on the graph
5. Detailed hop information appears in the sidebar

### Example 4: Exploring Connection Details
1. Click on any edge (arrow) in the graph
2. View authentication details in the sidebar:
   - Which user was used
   - What credentials worked
   - Authentication method (password/key)

## Keyboard Shortcuts
- **Arrow Keys**: Pan the graph
- **Mouse Wheel**: Zoom in/out
- **Left Click**: Select node/edge
- **Right Click**: Context menu (if enabled)

## Troubleshooting

### Web Interface Won't Start
**Error**: "Cannot connect to Neo4j"
- **Solution**: Ensure Neo4j is running on `bolt://localhost:7687`
- Check config file at `~/.sshmap/config.yml`

### Empty Graph
**Issue**: Graph loads but shows no nodes
- **Solution**: Run SSHMAP scanner first to populate data
- Verify data in Neo4j browser: `http://localhost:7474`

### Search Not Working
**Issue**: Search returns no results
- **Solution**: Ensure you're using exact or partial hostnames/IPs
- Search is case-insensitive

### Path Not Found
**Issue**: "No path found between the specified nodes"
- **Solution**: Verify both hostnames exist in the database
- Ensure there is an SSH connection path between the nodes
- Check that nodes are reachable (may need to scan deeper)

## Configuration

### Neo4j Connection
Edit `~/.sshmap/config.yml`:
```yaml
neo4j_uri: "bolt://localhost:7687"
neo4j_user: "neo4j"
neo4j_pass: "your_password"
```

### Web Server Port
To change the port, edit `web_app.py`:
```python
app.run(host='127.0.0.1', port=5000, debug=True)
```

## API Endpoints

The web interface provides a RESTful API that can be used programmatically:

- `GET /api/graph` - Get all nodes and edges
- `GET /api/search?q=query` - Search nodes and edges
- `POST /api/path` - Find path between nodes
- `GET /api/node/<id>` - Get node details
- `GET /api/edge/<id>` - Get edge details
- `GET /api/hosts` - Get all hostnames

## Security Notes

⚠️ **Important**: The web interface is designed for **localhost access only**.

- No authentication is implemented
- Runs on 127.0.0.1 (localhost) only
- Not suitable for production or external access
- Do not expose to external networks

## Tips for Best Experience

1. **Use Chrome/Firefox**: Best compatibility with vis.js
2. **Large Networks**: May take a few seconds to render
3. **Refresh Graph**: Click "Refresh Graph" after new scans
4. **Path Finding**: Use autocomplete for accurate hostname entry
5. **Node Colors**: Green nodes indicate path highlights

## Advanced Usage

### Custom Queries
For advanced users who want to extend the functionality, the GraphDB API provides additional methods:
- `find_all_paths_to()` - Find all paths between nodes
- `find_freshest_paths()` - Find recently used paths
- `get_connections_from_host()` - Get all connections from a host

### Extending the Web Interface
The web application is built with Flask and can be extended:
- Add new API endpoints in `web_app.py`
- Customize the UI in `templates/index.html`
- Modify graph appearance in `static/js/app.js`

## Support

For issues or questions:
1. Check the main README.md
2. Review Neo4j connection settings
3. Verify SSHMAP scanner has run successfully
4. Check browser console for JavaScript errors

## Version Information

- Web Interface: v1.0
- Compatible with SSHMAP: v0.2+
- Requires: Flask, Neo4j Python Driver, vis.js

---

**Enjoy exploring your SSH network topology with SSHMAP Web Interface!** 🔐🌐
