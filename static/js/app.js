// Global variables
let network = null;
let nodes = new vis.DataSet([]);
let edges = new vis.DataSet([]);
let allNodes = [];
let allEdges = [];

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initNetwork();
    loadGraph();
    loadHostnames();
    setupEventListeners();
});

// Initialize the vis.js network
function initNetwork() {
    const container = document.getElementById('network');
    const data = {
        nodes: nodes,
        edges: edges
    };
    
    const options = {
        nodes: {
            shape: 'dot',
            size: 20,
            font: {
                size: 14,
                face: 'Tahoma'
            },
            borderWidth: 2,
            borderWidthSelected: 4,
            color: {
                border: '#667eea',
                background: '#97a9f7',
                highlight: {
                    border: '#764ba2',
                    background: '#a67ec1'
                }
            }
        },
        edges: {
            width: 2,
            color: {
                color: '#848484',
                highlight: '#667eea'
            },
            arrows: {
                to: {
                    enabled: true,
                    scaleFactor: 0.5
                }
            },
            smooth: {
                type: 'cubicBezier',
                forceDirection: 'horizontal',
                roundness: 0.4
            }
        },
        physics: {
            stabilization: {
                iterations: 200
            },
            barnesHut: {
                gravitationalConstant: -30000,
                centralGravity: 0.3,
                springLength: 150,
                springConstant: 0.04
            }
        },
        interaction: {
            hover: true,
            tooltipDelay: 100,
            navigationButtons: true,
            keyboard: true
        }
    };
    
    network = new vis.Network(container, data, options);
    
    // Event listeners for node/edge selection
    network.on('selectNode', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            loadNodeDetails(nodeId);
        }
    });
    
    network.on('selectEdge', function(params) {
        if (params.edges.length > 0) {
            const edgeId = params.edges[0];
            loadEdgeDetails(edgeId);
        }
    });
    
    network.on('deselectNode', function() {
        showDefaultInfo();
    });
    
    network.on('deselectEdge', function() {
        showDefaultInfo();
    });
}

// Load the complete graph from the API
function loadGraph() {
    showLoading(true);
    
    fetch('/api/graph')
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showError('Error loading graph: ' + data.error);
                return;
            }
            
            allNodes = data.nodes;
            allEdges = data.edges;
            
            nodes.clear();
            edges.clear();
            nodes.add(data.nodes);
            edges.add(data.edges);
            
            updateStats(data.nodes.length, data.edges.length);
            showLoading(false);
            
            // Fit the network to show all nodes
            setTimeout(() => {
                network.fit({
                    animation: {
                        duration: 1000,
                        easingFunction: 'easeInOutQuad'
                    }
                });
            }, 500);
        })
        .catch(error => {
            showError('Failed to load graph: ' + error.message);
            showLoading(false);
        });
}

// Load hostnames for autocomplete
function loadHostnames() {
    fetch('/api/hosts')
        .then(response => response.json())
        .then(data => {
            const datalist = document.getElementById('hostnames');
            datalist.innerHTML = '';
            
            data.hostnames.forEach(hostname => {
                const option = document.createElement('option');
                option.value = hostname;
                datalist.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Failed to load hostnames:', error);
        });
}

// Search functionality
function performSearch(query) {
    if (!query || query.trim() === '') {
        // Reset to show all nodes
        nodes.clear();
        edges.clear();
        nodes.add(allNodes);
        edges.add(allEdges);
        updateStats(allNodes.length, allEdges.length);
        return;
    }
    
    fetch(`/api/search?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showError('Search error: ' + data.error);
                return;
            }
            
            // Get IDs of matching nodes and connected nodes
            const matchingNodeIds = new Set(data.nodes.map(n => n.id));
            const connectedNodeIds = new Set();
            
            // Add nodes that are connected to matching edges
            data.edges.forEach(edge => {
                connectedNodeIds.add(edge.from);
                connectedNodeIds.add(edge.to);
            });
            
            // Combine all relevant node IDs
            const relevantNodeIds = new Set([...matchingNodeIds, ...connectedNodeIds]);
            
            // Filter nodes and edges to show
            const filteredNodes = allNodes.filter(n => relevantNodeIds.has(n.id));
            const filteredEdges = allEdges.filter(e => 
                relevantNodeIds.has(e.from) && relevantNodeIds.has(e.to)
            );
            
            nodes.clear();
            edges.clear();
            nodes.add(filteredNodes);
            edges.add(filteredEdges);
            
            updateStats(filteredNodes.length, filteredEdges.length);
            
            // Highlight matching nodes
            data.nodes.forEach(node => {
                nodes.update({
                    id: node.id,
                    color: {
                        border: '#ffc107',
                        background: '#fff176'
                    }
                });
            });
            
            // Fit to show filtered results
            setTimeout(() => {
                network.fit({
                    animation: {
                        duration: 500,
                        easingFunction: 'easeInOutQuad'
                    }
                });
            }, 100);
        })
        .catch(error => {
            showError('Search failed: ' + error.message);
        });
}

// Load details for a specific node
function loadNodeDetails(nodeId) {
    fetch(`/api/node/${nodeId}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showError('Error loading node details: ' + data.error);
                return;
            }
            
            displayNodeDetails(data);
        })
        .catch(error => {
            showError('Failed to load node details: ' + error.message);
        });
}

// Display node details in sidebar
function displayNodeDetails(data) {
    const container = document.getElementById('detailsContainer');
    
    let html = `
        <div class="info-section">
            <h3>🖥️ Host Information</h3>
            <div class="info-item">
                <strong>Hostname:</strong>
                <span>${escapeHtml(data.hostname)}</span>
            </div>
            <div class="info-item">
                <strong>Interfaces:</strong>
                <span>${data.interfaces.length > 0 ? data.interfaces.map(i => escapeHtml(i)).join('<br>') : 'N/A'}</span>
            </div>
        </div>
    `;
    
    if (data.outgoing_connections && data.outgoing_connections.length > 0) {
        html += `
            <div class="info-section">
                <h3>📤 Outgoing Connections (${data.outgoing_connections.length})</h3>
                <div class="connection-list">
        `;
        
        data.outgoing_connections.forEach(conn => {
            html += `
                <div class="connection-item">
                    <strong>→ ${escapeHtml(conn.target)}</strong><br>
                    User: ${escapeHtml(conn.user)}<br>
                    IP: ${escapeHtml(conn.ip)}:${conn.port}<br>
                    Method: ${escapeHtml(conn.method)}
                </div>
            `;
        });
        
        html += `
                </div>
            </div>
        `;
    }
    
    if (data.incoming_connections && data.incoming_connections.length > 0) {
        html += `
            <div class="info-section">
                <h3>📥 Incoming Connections (${data.incoming_connections.length})</h3>
                <div class="connection-list">
        `;
        
        data.incoming_connections.forEach(conn => {
            html += `
                <div class="connection-item">
                    <strong>← ${escapeHtml(conn.source)}</strong><br>
                    User: ${escapeHtml(conn.user)}<br>
                    IP: ${escapeHtml(conn.ip)}:${conn.port}<br>
                    Method: ${escapeHtml(conn.method)}
                </div>
            `;
        });
        
        html += `
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

// Load details for a specific edge
function loadEdgeDetails(edgeId) {
    fetch(`/api/edge/${edgeId}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showError('Error loading edge details: ' + data.error);
                return;
            }
            
            displayEdgeDetails(data);
        })
        .catch(error => {
            showError('Failed to load edge details: ' + error.message);
        });
}

// Display edge details in sidebar
function displayEdgeDetails(data) {
    const container = document.getElementById('detailsContainer');
    
    const timestamp = data.time ? new Date(data.time).toLocaleString() : 'N/A';
    
    const html = `
        <div class="info-section">
            <h3>🔗 Connection Details</h3>
            <div class="info-item">
                <strong>From:</strong>
                <span>${escapeHtml(data.from_hostname)}</span>
            </div>
            <div class="info-item">
                <strong>To:</strong>
                <span>${escapeHtml(data.to_hostname)}</span>
            </div>
            <div class="info-item">
                <strong>User:</strong>
                <span>${escapeHtml(data.user)}</span>
            </div>
            <div class="info-item">
                <strong>Target IP:</strong>
                <span>${escapeHtml(data.ip)}:${data.port}</span>
            </div>
            <div class="info-item">
                <strong>Method:</strong>
                <span>${escapeHtml(data.method)}</span>
            </div>
            <div class="info-item">
                <strong>Credentials:</strong>
                <span>${escapeHtml(data.creds)}</span>
            </div>
            <div class="info-item">
                <strong>Last Used:</strong>
                <span>${timestamp}</span>
            </div>
        </div>
    `;
    
    container.innerHTML = html;
}

// Find path between two nodes
function findPath() {
    const startNode = document.getElementById('startNode').value.trim();
    const endNode = document.getElementById('endNode').value.trim();
    
    if (!startNode || !endNode) {
        showError('Please enter both start and end nodes');
        return;
    }
    
    fetch('/api/path', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            start: startNode,
            end: endNode,
            all: false
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showError('Error finding path: ' + data.error);
            return;
        }
        
        if (data.paths && data.paths.length > 0) {
            displayPath(data.paths[0]);
            highlightPath(data.paths[0]);
        } else {
            showError('No path found between the specified nodes');
        }
    })
    .catch(error => {
        showError('Failed to find path: ' + error.message);
    });
}

// Display path in sidebar
function displayPath(path) {
    const container = document.getElementById('detailsContainer');
    
    let html = `
        <div class="info-section">
            <h3>🛤️ Path Found (${path.length} hops)</h3>
            <div class="path-result">
    `;
    
    path.forEach((step, index) => {
        html += `
            <div class="path-step">
                <strong>${index + 1}. ${escapeHtml(step.from)} → ${escapeHtml(step.to)}</strong>
                <div class="arrow">↓</div>
                User: ${escapeHtml(step.user)}<br>
                IP: ${escapeHtml(step.ip)}:${step.port}<br>
                Method: ${escapeHtml(step.method)}
            </div>
        `;
    });
    
    html += `
            </div>
        </div>
    `;
    
    container.innerHTML = html;
}

// Highlight path in the graph
function highlightPath(path) {
    // Reset all nodes and edges to default colors
    allNodes.forEach(node => {
        nodes.update({
            id: node.id,
            color: {
                border: '#667eea',
                background: '#97a9f7'
            }
        });
    });

    allEdges.forEach(edge => {
        edges.update({
            id: edge.id,
            color: {
                color: '#848484'
            },
            width: 2
        });
    });

    // Collect all nodes and edges in the path
    const pathNodeNames = new Set();

    path.forEach(step => {
        pathNodeNames.add(step.from);
        pathNodeNames.add(step.to);
    });

    // Find node IDs
    const pathNodeIds = allNodes
        .filter(n => pathNodeNames.has(n.hostname))
        .map(n => n.id);

    // Highlight nodes in path
    pathNodeIds.forEach(nodeId => {
        nodes.update({
            id: nodeId,
            color: {
                border: '#4caf50',
                background: '#81c784'
            }
        });
    });

    // Find and highlight edges in path
    path.forEach(step => {
        const matchingEdges = allEdges.filter(e =>
            e.from_hostname === step.from &&
            e.to_hostname === step.to &&
            e.user === step.user &&
            e.ip === step.ip &&
            e.port === step.port
        );

        matchingEdges.forEach(edge => {
            edges.update({
                id: edge.id,
                color: {
                    color: '#4caf50'
                },
                width: 4
            });
        });
    });

    // Focus on the path
    network.fit({
        nodes: pathNodeIds,
        animation: {
            duration: 1000,
            easingFunction: 'easeInOutQuad'
        }
    });
}

// Show/hide loading indicator
function showLoading(show) {
    const loading = document.getElementById('loading');
    loading.style.display = show ? 'block' : 'none';
}

// Update statistics
function updateStats(nodeCount, edgeCount) {
    document.getElementById('nodeCount').textContent = nodeCount;
    document.getElementById('edgeCount').textContent = edgeCount;
}

// Show error message
function showError(message) {
    const container = document.getElementById('detailsContainer');
    container.innerHTML = `
        <div class="error">
            <strong>⚠️ Error</strong><br>
            ${escapeHtml(message)}
        </div>
    `;
}

// Show default information
function showDefaultInfo() {
    const container = document.getElementById('detailsContainer');
    container.innerHTML = `
        <div class="info-section" style="margin-top: 20px;">
            <h3>ℹ️ Information</h3>
            <p style="color: #666; font-size: 14px; line-height: 1.6;">
                Click on a node to see its details and connections.<br><br>
                Click on an edge to see connection details.<br><br>
                Use the search bar to filter the graph.<br><br>
                Use the path finder to discover routes between hosts.
            </p>
        </div>
    `;
}

// Setup event listeners
function setupEventListeners() {
    const searchInput = document.getElementById('search');
    let searchTimeout = null;
    
    searchInput.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            performSearch(this.value);
        }, 300);
    });
    
    // Allow Enter key to trigger path finding
    document.getElementById('startNode').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            findPath();
        }
    });
    
    document.getElementById('endNode').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            findPath();
        }
    });
}

// Utility function to escape HTML
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}
