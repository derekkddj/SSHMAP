# SSHMAP Web Interface - Visual Overview

## Interface Layout

The SSHMAP Web Interface consists of several key components:

```
┌──────────────────────────────────────────────────────────────────┐
│                    🔐 SSHMAP - SSH Connection Graph Viewer       │
│           Visualize and explore your SSH network topology        │
└──────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  🔍 Search   │  📍 Start Node  │  🎯 End Node  │  [Find Path]  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────┬───────────────────────────────┐
│                                 │   📊 Graph Statistics         │
│         INTERACTIVE             │   ┌────────┬────────┐         │
│         GRAPH DISPLAY           │   │  Nodes │  Edges │         │
│                                 │   └────────┴────────┘         │
│     ○ ─────→ ○                 │                               │
│     │        │                  │   ℹ️ Information             │
│     ↓        ↓                  │   Click on nodes/edges for    │
│     ○ ←───── ○                 │   detailed information        │
│                                 │                               │
│                                 │   Selected item details       │
│                                 │   appear here...              │
│                                 │                               │
└─────────────────────────────────┴───────────────────────────────┘
```

## Features Demonstration

### 1. Graph Visualization
- **Nodes (Circles)**: Represent SSH hosts in your network
  - Size indicates importance
  - Color coding shows different states
  - Hover to see quick info
  - Click to see full details

- **Edges (Arrows)**: Represent SSH connections
  - Direction shows connection flow
  - Hover to see connection details
  - Click for full authentication info

### 2. Search Bar
Type in the search bar to filter:
- Hostname: `web-server-01`
- IP Address: `192.168.1.100`
- Username: `root`
- Port: `22` or `2222`

The graph automatically filters to show matching results!

### 3. Path Finder
Find how to reach any host from another:

```
Start Node: [my-laptop]  →  End Node: [internal-database]

[Find Path] →

Result:
my-laptop → gateway-server → app-server → internal-database
```

Each hop shows:
- Username used
- IP address and port
- Authentication method (password/key)
- Credentials

### 4. Interactive Controls
- **Zoom**: Mouse wheel or pinch gesture
- **Pan**: Click and drag the background
- **Select**: Click on nodes or edges
- **Reset View**: Click "Refresh Graph"
- **Navigate**: Use arrow keys

## Example Use Cases

### Case 1: Exploring Your Network
**Scenario**: You've completed an SSH scan and want to see the network topology.

**Steps**:
1. Start the web interface: `python3 sshmap_web.py`
2. Open browser to `http://127.0.0.1:5000`
3. The graph automatically loads showing all discovered hosts
4. Click on any node to see its connections

**What You See**:
- A visual network map of all SSH-accessible hosts
- Connection paths between hosts
- Statistics showing network size

### Case 2: Finding a Specific Host
**Scenario**: You remember a host's partial name but need its full details.

**Steps**:
1. Type partial hostname in search bar: "web"
2. Graph filters to show hosts matching "web"
3. Click on the highlighted node
4. View full details in sidebar

**What You Get**:
- Hostname and IP addresses
- All incoming connections (who can access this host)
- All outgoing connections (what this host can access)

### Case 3: Planning SSH Access Path
**Scenario**: You need to connect to an internal host from your workstation.

**Steps**:
1. Enter your workstation name in "Start Node"
2. Enter target host name in "End Node"
3. Click "Find Path"
4. See the complete path highlighted on graph
5. View hop-by-hop connection details

**What You Get**:
- Visual path through the network
- Complete credentials for each hop
- Information needed to configure ProxyJump or ProxyCommand

### Case 4: Security Audit
**Scenario**: Identify hosts with many incoming connections (potential critical nodes).

**Steps**:
1. Look at the graph visualization
2. Identify nodes with many incoming arrows
3. Click on high-degree nodes
4. Review their incoming connections
5. Search for specific users or credential patterns

**What You Learn**:
- Which hosts are critical access points
- What credentials are being reused
- Potential security concerns in the network

## Visual Elements Guide

### Node Colors
- **Blue/Purple**: Normal host
- **Yellow**: Highlighted from search
- **Green**: Part of found path
- **Larger size**: More connections

### Edge Styles
- **Gray Arrow**: Standard connection
- **Blue Arrow**: Highlighted connection
- **Green Arrow**: Part of found path
- **Thicker line**: Recently used connection

### Sidebar Sections
1. **Graph Statistics**: Overview of network size
2. **Host Information**: Details about selected node
3. **Connection Details**: Authentication info for selected edge
4. **Path Results**: Step-by-step route between hosts

## Tips for Effective Use

1. **Start with Overview**: Let the graph load completely to see the full network
2. **Use Search First**: If you know what you're looking for, use search to filter
3. **Explore Connections**: Click on critical nodes to understand the network structure
4. **Path Finding**: Use path finder to plan your SSH access routes
5. **Regular Updates**: Click "Refresh Graph" after new scans to see latest data

## Performance Notes

- **Small Networks** (< 50 hosts): Instant loading and smooth interaction
- **Medium Networks** (50-200 hosts): May take a few seconds to render
- **Large Networks** (> 200 hosts): Consider using search to filter before viewing

## Keyboard Shortcuts

- **Arrow Keys**: Pan the graph view
- **Mouse Wheel**: Zoom in and out
- **Enter**: Submit path finding (when focused on input fields)
- **Escape**: Deselect nodes/edges

## Browser Compatibility

Tested and working on:
- ✅ Google Chrome (Recommended)
- ✅ Mozilla Firefox
- ✅ Microsoft Edge
- ✅ Safari

For best experience, use a modern browser with JavaScript enabled.

## Troubleshooting Display Issues

**Graph doesn't display**:
- Check browser console for errors
- Ensure JavaScript is enabled
- Try refreshing the page

**Search not working**:
- Make sure Neo4j has data
- Check search terms are correct
- Try partial matches

**Path not highlighting**:
- Verify both hostnames exist
- Check if path actually exists
- Ensure nodes are connected

---

**Ready to explore your SSH network visually?**

Run: `python3 sshmap_web.py` and open `http://127.0.0.1:5000` 🚀
