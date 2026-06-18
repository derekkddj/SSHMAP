// Global variables
let network = null;
let nodes = new vis.DataSet([]);
let edges = new vis.DataSet([]);
let allNodes = [];
let allEdges = [];
let currentLayout = 'force';
let isPathView = false;
let filterState = {
    users: [],
    methods: [],
    maxEdges: 0,
    minConnections: 0,
    selectedNodeHops: 0
};
let uniqueUsers = new Set();
let uniqueMethods = new Set();
let mobileUiInitialized = false;
let pathHostnames = [];
let pathSuggestionsPopup = null;
let activePathInputId = null;
let selectedNodeId = null;
let physicsEnabled = true;
let physicsManualOverride = null; // null = auto, true = force on, false = force off
let searchResultNodes = null;
let searchResultEdges = null;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initNetwork();
    initializeResponsiveUI();
    loadGraph();
    loadHostnames();
    setupEventListeners();
    updateGraphStatus(0, 0);
});

// Initialize the vis.js network
function initNetwork() {
    const container = document.getElementById('network');
    const data = {
        nodes: nodes,
        edges: edges
    };
    
    const options = getLayoutOptions(currentLayout);
    network = new vis.Network(container, data, options);

    bindNetworkEvents(container);
}

function bindNetworkEvents(container) {
    // Prevent default browser context menu
    container.addEventListener('contextmenu', function(event) {
        event.preventDefault();
        return false;
    });

    // Event listeners for node/edge selection
    network.on('selectNode', function(params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const previousSelectedNode = selectedNodeId;
            selectedNodeId = nodeId;
            loadNodeDetails(nodeId);
            if (filterState.selectedNodeHops > 0 && previousSelectedNode !== nodeId) {
                applyFilters();
            }
        }
    });

    network.on('selectEdge', function(params) {
        if (params.edges.length > 0) {
            const edgeId = params.edges[0];
            loadEdgeDetails(edgeId);
        }
    });

    network.on('deselectNode', function() {
        const hadSelection = selectedNodeId !== null;
        selectedNodeId = null;
        if (filterState.selectedNodeHops > 0 && hadSelection) {
            applyFilters();
        }
        showDefaultInfo();
    });

    network.on('deselectEdge', function() {
        showDefaultInfo();
    });

    // Context menu on right-click
    network.on('oncontext', function(params) {
        params.event.preventDefault();

        const nodeId = network.getNodeAt(params.pointer.DOM);
        const edgeId = network.getEdgeAt(params.pointer.DOM);

        if (nodeId) {
            showContextMenu(params.event, nodeId, null);
        } else if (edgeId) {
            showContextMenu(params.event, null, edgeId);
        } else {
            hideContextMenu();
        }
    });
}

// Get layout options based on selected layout type
function getLayoutOptions(layoutType) {
    const baseOptions = {
        nodes: {
            shape: 'dot',
            size: 35,
            font: {
                size: 14,
                face: 'Arial',
                color: '#ffffff',
                strokeWidth: 0
            },
            borderWidth: 3,
            borderWidthSelected: 4,
            color: {
                border: '#6a7cf6',
                background: '#6a7cf6',
                highlight: {
                    border: '#dc2626',
                    background: '#ef4444'
                },
                hover: {
                    border: '#fbbf24',
                    background: '#fbbf24'
                }
            },
            shadow: false
        },
        edges: {
            width: 2,
            color: {
                color: '#6b7280',
                highlight: '#dc2626',
                hover: '#fbbf24'
            },
            arrows: {
                to: {
                    enabled: true,
                    scaleFactor: 0.8,
                    type: 'arrow'
                }
            },
            smooth: {
                enabled: true,
                type: 'dynamic',
                roundness: 0.5
            },
            shadow: false,
            font: {
                size: 11,
                color: '#d1d5db',
                background: 'rgba(30, 31, 34, 0.8)',
                strokeWidth: 0,
                align: 'horizontal'
            },
            scaling: {
                min: 1,
                max: 4
            }
        },
        interaction: {
            hover: true,
            tooltipDelay: 50,
            navigationButtons: true,
            keyboard: false,
            multiselect: true,
            selectable: true,
            zoomView: true,
            dragView: true
        },
        configure: {
            enabled: false
        }
    };

    // Layout-specific configurations
    switch(layoutType) {
        case 'hierarchical-lr':
            return {
                ...baseOptions,
                layout: {
                    hierarchical: {
                        enabled: true,
                        direction: 'LR',
                        sortMethod: 'directed',
                        levelSeparation: 250,
                        nodeSpacing: 180,
                        treeSpacing: 250,
                        blockShifting: true,
                        edgeMinimization: true,
                        parentCentralization: true
                    }
                },
                physics: {
                    enabled: true,
                    hierarchicalRepulsion: {
                        centralGravity: 0.0,
                        springLength: 200,
                        springConstant: 0.01,
                        nodeDistance: 180,
                        damping: 0.09
                    },
                    stabilization: {
                        enabled: true,
                        iterations: 200
                    },
                    solver: 'hierarchicalRepulsion'
                },
                interaction: {
                    ...baseOptions.interaction,
                    dragNodes: true,
                    dragView: true
                }
            };
        
        case 'hierarchical-tb':
            return {
                ...baseOptions,
                layout: {
                    hierarchical: {
                        enabled: true,
                        direction: 'UD',
                        sortMethod: 'directed',
                        levelSeparation: 200,
                        nodeSpacing: 220,
                        treeSpacing: 250,
                        blockShifting: true,
                        edgeMinimization: true,
                        parentCentralization: true
                    }
                },
                physics: {
                    enabled: true,
                    hierarchicalRepulsion: {
                        centralGravity: 0.0,
                        springLength: 200,
                        springConstant: 0.01,
                        nodeDistance: 200,
                        damping: 0.09
                    },
                    stabilization: {
                        enabled: true,
                        iterations: 200
                    },
                    solver: 'hierarchicalRepulsion'
                },
                interaction: {
                    ...baseOptions.interaction,
                    dragNodes: true,
                    dragView: true
                }
            };
        
        case 'circular':
            return {
                ...baseOptions,
                layout: {
                    randomSeed: 2
                },
                physics: {
                    enabled: true,
                    stabilization: { 
                        enabled: true,
                        iterations: 500 
                    },
                    solver: 'barnesHut',
                    barnesHut: {
                        gravitationalConstant: -10000,
                        centralGravity: 0.5,
                        springLength: 200,
                        springConstant: 0.05,
                        damping: 0.2,
                        avoidOverlap: 0.5
                    }
                }
            };
        
        case 'force':
        default: {
            // Check current visible edges, not all edges
            const visibleEdges = edges.get();
            const edgeCount = visibleEdges.length || 0;
            const isLarge = edgeCount > 500;
            
            return {
                ...baseOptions,
                layout: {
                    randomSeed: 2
                },
                physics: {
                    enabled: true, // Always start with physics enabled for initial layout
                    stabilization: {
                        enabled: true,
                        iterations: isLarge ? 50 : 400, // Fewer iterations for large graphs
                        onlyDynamicEdges: false,
                        fit: true
                    },
                    solver: 'barnesHut',
                    barnesHut: {
                        gravitationalConstant: isLarge ? -50000 : -30000,
                        centralGravity: isLarge ? 0.5 : 0.3,
                        springLength: isLarge ? 100 : 150,
                        springConstant: isLarge ? 0.01 : 0.04,
                        damping: isLarge ? 0.3 : 0.2,
                        avoidOverlap: isLarge ? 0.1 : 0.2
                    }
                }
            };
        }
    }
}

// Load the complete graph from the API
function loadGraph() {
    showLoading(true);
    isPathView = false;

    fetch('/api/graph')
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showError('Error loading graph: ' + data.error);
                return;
            }

            allNodes = data.nodes;
            allEdges = data.edges;

            // Auto-detect large graph and set default edge limit
            const slider = document.getElementById('maxEdgesSlider');
            if (slider) {
                const maxVal = parseInt(slider.max);
                if (allEdges.length > 1000) {
                    const autoLimit = Math.min(500, maxVal); // Auto-limit to 500 edges for performance
                    slider.max = Math.max(maxVal, allEdges.length);
                    slider.value = autoLimit;
                    filterState.maxEdges = autoLimit;
                    document.getElementById('maxEdgesValue').textContent = String(autoLimit);
                    showError(null);
                    const container = document.getElementById('detailsContainer');
                    
                    let layoutMsg = '';
                    if (allEdges.length > 2000) {
                        layoutMsg = `<br><br><strong>💡 Tip:</strong> For graphs this large, try the <strong>Hierarchical</strong> layout for better performance.`;
                    }
                    
                    container.innerHTML = `
                        <div class="info-section" style="margin-top:20px;">
                            <h3>⚠️ Large Graph Detected</h3>
                            <p style="color:#f59e0b; font-size:13px; line-height:1.6;">
                                Your graph has <strong>${allEdges.length}</strong> edges.<br>
                                Auto-limited to <strong>${autoLimit}</strong> most recent for performance.<br><br>
                                Adjust the <strong>Max Edges</strong> slider in the Filters panel<br>
                                to show more or fewer connections.${layoutMsg}
                            </p>
                        </div>
                    `;
                } else {
                    slider.max = Math.max(maxVal, allEdges.length);
                }
            }

            // Auto-disable edge labels for large graphs
            if (allEdges.length > 500) {
                slider.step = 50;
            }

            // Collect unique users and methods for filters
            uniqueUsers.clear();
            uniqueMethods.clear();
            data.edges.forEach(edge => {
                uniqueUsers.add(edge.user);
                uniqueMethods.add(edge.method);
            });

            // Initialize filters
            populateFilterOptions();

            // Apply current filters
            applyFilters();

            showLoading(false);

            // Fit the network to show all nodes
            setTimeout(() => {
                network.fit({
                    animation: {
                        duration: 1000,
                        easingFunction: 'easeInOutQuad'
                    }
                });
                // Explicitly ensure zoom is enabled
                network.moveTo({
                    scale: network.getScale(),
                    animation: false
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
            pathHostnames = Array.isArray(data.hostnames) ? data.hostnames : [];
            const startDatalist = document.getElementById('startHostnames');
            const endDatalist = document.getElementById('endHostnames');

            if (!startDatalist || !endDatalist) {
                return;
            }

            startDatalist.innerHTML = '';
            endDatalist.innerHTML = '';
            
            pathHostnames.forEach(hostname => {
                const startOption = document.createElement('option');
                startOption.value = hostname;
                startDatalist.appendChild(startOption);

                const endOption = document.createElement('option');
                endOption.value = hostname;
                endDatalist.appendChild(endOption);
            });
        })
        .catch(error => {
            console.error('Failed to load hostnames:', error);
        });
}

function ensurePathSuggestionsPopup() {
    if (pathSuggestionsPopup) {
        return pathSuggestionsPopup;
    }

    const popup = document.createElement('div');
    popup.id = 'pathSuggestionsPopup';
    popup.className = 'search-popup';
    popup.style.display = 'none';
    popup.style.position = 'fixed';
    popup.style.zIndex = '3000';
    popup.style.maxHeight = '240px';
    popup.style.overflowY = 'auto';
    document.body.appendChild(popup);
    pathSuggestionsPopup = popup;
    return popup;
}

function hidePathSuggestionsPopup() {
    if (pathSuggestionsPopup) {
        pathSuggestionsPopup.style.display = 'none';
    }
    activePathInputId = null;
}

function showPathSuggestionsPopup(inputEl) {
    const popup = ensurePathSuggestionsPopup();
    const query = inputEl.value.trim().toLowerCase();
    const filtered = pathHostnames
        .filter(hostname => hostname.toLowerCase().includes(query))
        .slice(0, 100);

    if (filtered.length === 0) {
        popup.innerHTML = '<div class="search-no-results">No matching hosts</div>';
    } else {
        popup.innerHTML = filtered
            .map(hostname => `<div class="search-result-item node-result" data-hostname="${encodeURIComponent(hostname)}">🖥️ ${escapeHtml(hostname)}</div>`)
            .join('');
    }

    const rect = inputEl.getBoundingClientRect();
    popup.style.left = `${rect.left}px`;
    popup.style.top = `${rect.bottom + 4}px`;
    popup.style.width = `${rect.width}px`;
    popup.style.display = 'block';
    activePathInputId = inputEl.id;
}

function bindPathInputAutocomplete(inputEl) {
    if (!inputEl) {
        return;
    }

    inputEl.addEventListener('focus', function() {
        showPathSuggestionsPopup(inputEl);
    });

    inputEl.addEventListener('click', function() {
        showPathSuggestionsPopup(inputEl);
    });

    inputEl.addEventListener('input', function() {
        showPathSuggestionsPopup(inputEl);
    });
}

// Search functionality
function performSearch(query) {
    if (!query || query.trim() === '') {
        // Reset search state and apply normal filters
        searchResultNodes = null;
        searchResultEdges = null;
        applyFilters();
        return;
    }
    
    fetch(`/api/search?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showError('Search error: ' + data.error);
                return;
            }
            
            // Get IDs of matching nodes
            const matchingNodeIds = new Set(data.nodes.map(n => n.id));
            
            // For matching nodes, get ALL their edges (incoming and outgoing)
            const relevantEdges = allEdges.filter(edge => 
                matchingNodeIds.has(edge.from) || matchingNodeIds.has(edge.to)
            );
            
            // Get all nodes connected by these edges
            const connectedNodeIds = new Set();
            matchingNodeIds.forEach(id => connectedNodeIds.add(id));
            relevantEdges.forEach(edge => {
                connectedNodeIds.add(edge.from);
                connectedNodeIds.add(edge.to);
            });
            
            // Store search results as the base for filtering
            searchResultNodes = allNodes.filter(n => connectedNodeIds.has(n.id));
            searchResultEdges = relevantEdges;
            
            // Store matching node IDs for highlighting
            window.searchHighlightNodes = matchingNodeIds;
            
            // Apply filters on search results
            applyFilters();
            
            // Fit to show filtered results, focusing on the matched node
            setTimeout(() => {
                if (matchingNodeIds.size === 1) {
                    // If single node match, focus on it
                    const nodeId = Array.from(matchingNodeIds)[0];
                    network.focus(nodeId, {
                        scale: 1.5,
                        animation: {
                            duration: 500,
                            easingFunction: 'easeInOutQuad'
                        }
                    });
                } else {
                    // Multiple matches, fit all
                    network.fit({
                        animation: {
                            duration: 500,
                            easingFunction: 'easeInOutQuad'
                        }
                    });
                }
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
        
        <div class="info-section">
            <h3>⚡ Execute Command</h3>
            <div class="command-exec-container">
                <input type="text" id="commandInput" placeholder="Enter command (e.g., ls -la, whoami)" class="command-input" />
                <button class="btn btn-primary" onclick="executeCommand('${escapeHtml(data.hostname)}')" style="width: 100%; margin-top: 10px;">🚀 Execute</button>
                <div id="commandOutput" class="command-output" style="display: none;"></div>
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
                <div class="connection-item" style="cursor: pointer;" onclick="focusOnEdge(${conn.edge_id})" title="Click to focus on this connection">
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
                <div class="connection-item" style="cursor: pointer;" onclick="focusOnEdge(${conn.edge_id})" title="Click to focus on this connection">
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
    
    showLoading(true);
    
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
        showLoading(false);
        
        if (data.error) {
            showError('Error finding path: ' + data.error);
            return;
        }
        
        if (data.paths && data.paths.length > 0) {
            displayPath(data.paths[0]);
            showOnlyPath(data.paths[0]);
        } else {
            showError('No path found between the specified nodes');
        }
    })
    .catch(error => {
        showLoading(false);
        showError('Failed to find path: ' + error.message);
    });
}

// Display path in sidebar
function displayPath(path) {
    const container = document.getElementById('detailsContainer');
    
    let html = `
        <div class="info-section">
            <h3>🛤️ Path Found (${path.length} hops)</h3>
            <button class="btn btn-secondary" onclick="restoreFullGraph()" style="width: 100%; margin-bottom: 15px;">
                ↩️ Show Full Graph
            </button>
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

// Show only the path in the graph
function showOnlyPath(path) {
    isPathView = true;
    
    // Collect all nodes and edges in the path
    const pathNodeNames = new Set();
    path.forEach(step => {
        pathNodeNames.add(step.from);
        pathNodeNames.add(step.to);
    });

    // Filter nodes that are in the path
    const pathNodes = allNodes.filter(n => pathNodeNames.has(n.hostname));
    const pathNodeIds = pathNodes.map(n => n.id);
    
    // Find matching edges in the path
    const pathEdges = [];
    path.forEach(step => {
        const matchingEdges = allEdges.filter(e =>
            e.from_hostname === step.from &&
            e.to_hostname === step.to &&
            e.user === step.user &&
            e.ip === step.ip &&
            e.port === step.port
        );
        pathEdges.push(...matchingEdges);
    });

    // Clear and show only path nodes/edges
    nodes.clear();
    edges.clear();
    
    // Add nodes with green path colors (BloodHound style)
    const highlightedNodes = pathNodes.map(node => ({
        ...node,
        color: {
            border: '#22c55e',
            background: '#22c55e'
        },
        size: 40
    }));
    
    // Add edges with green colors and labels
    const highlightedEdges = pathEdges.map(edge => ({
        ...edge,
        color: {
            color: '#22c55e'
        },
        width: 3,
        label: edge.user
    }));
    
    nodes.add(highlightedNodes);
    edges.add(highlightedEdges);
    
    updateStats(highlightedNodes.length, highlightedEdges.length);

    // Focus on the path
    setTimeout(() => {
        network.fit({
            animation: {
                duration: 1000,
                easingFunction: 'easeInOutQuad'
            }
        });
    }, 100);
}

// Change graph layout
function changeLayout(layoutType) {
    currentLayout = layoutType;

    // Show loading
    showLoading(true);

    // Get current node and edge data
    const currentNodes = nodes.get();
    const currentEdges = edges.get();

    // Destroy and recreate network with new layout
    if (network) {
        network.destroy();
    }

    // Reinitialize network with new layout
    const container = document.getElementById('network');
    const data = {
        nodes: nodes,
        edges: edges
    };

    const options = getLayoutOptions(layoutType);
    network = new vis.Network(container, data, options);

    bindNetworkEvents(container);

    // Update UI to show active layout
    document.querySelectorAll('.layout-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-layout="${layoutType}"]`).classList.add('active');

    // For large graphs, disable physics immediately
    const visibleEdges = edges.get();
    if (visibleEdges.length > 500) {
        network.setOptions({ 
            physics: { enabled: false },
            interaction: {
                zoomView: true,
                dragView: true
            }
        });
        physicsEnabled = false;
        // Force redraw to ensure canvas is responsive
        network.redraw();
    } else {
        physicsEnabled = true;
    }

    // Wait for stabilization then fit and hide loading
    network.once('stabilizationIterationsDone', function() {
        setTimeout(() => {
            network.fit({
                animation: {
                    duration: 500,
                    easingFunction: 'easeInOutQuad'
                }
            });
            showLoading(false);
        }, 100);
    });
    
    // Fallback in case stabilization doesn't trigger
    setTimeout(() => {
        showLoading(false);
        network.fit({
            animation: {
                duration: 500,
                easingFunction: 'easeInOutQuad'
            }
        });
    }, 3000);
}

// Restore full graph view
function restoreFullGraph() {
    isPathView = false;
    searchResultNodes = null;
    searchResultEdges = null;
    window.searchHighlightNodes = null;
    filterState = {
        users: [],
        methods: [],
        maxEdges: 0,
        minConnections: 0,
        selectedNodeHops: 0
    };
    selectedNodeId = null;

    // Reset filter UI
    document.querySelectorAll('.filter-checkbox').forEach(cb => cb.checked = true);
    const maxEdgesSlider = document.getElementById('maxEdgesSlider');
    if (maxEdgesSlider) {
        maxEdgesSlider.value = 0;
        document.getElementById('maxEdgesValue').textContent = 'All';
    }
    document.getElementById('minConnectionsSlider').value = 0;
    document.getElementById('minConnectionsValue').textContent = '0';
    document.getElementById('selectedNodeHopsSlider').value = 0;
    document.getElementById('selectedNodeHopsValue').textContent = 'All';
    
    // Clear search input
    const searchInput = document.getElementById('search');
    if (searchInput) {
        searchInput.value = '';
    }

    applyFilters();
    showDefaultInfo();
}

// Toggle physics manually
function togglePhysics() {
    if (physicsManualOverride === null) {
        // Currently auto, switch to force off
        physicsManualOverride = false;
    } else if (physicsManualOverride === false) {
        // Currently off, switch to force on
        physicsManualOverride = true;
    } else {
        // Currently on, switch to auto
        physicsManualOverride = null;
    }
    
    applyFilters(); // Re-apply to update physics state
}

// Update physics button display
function updatePhysicsButton() {
    const btn = document.getElementById('physicsToggleBtn');
    if (!btn) return;
    
    if (physicsManualOverride === null) {
        btn.textContent = physicsEnabled ? '⚡ Physics: Auto (On)' : '⚡ Physics: Auto (Off)';
        btn.title = 'Physics auto-managed. Click to force off.';
    } else if (physicsManualOverride === true) {
        btn.textContent = '⚡ Physics: On';
        btn.title = 'Physics forced on. Click to reset to auto.';
    } else {
        btn.textContent = '⚡ Physics: Off';
        btn.title = 'Physics forced off. Click to force on.';
    }
}

// Populate filter options
function populateFilterOptions() {
    const userFilterDiv = document.getElementById('userFilters');
    const methodFilterDiv = document.getElementById('methodFilters');
    
    // User filters
    userFilterDiv.innerHTML = '';
    Array.from(uniqueUsers).sort().forEach(user => {
        const label = document.createElement('label');
        label.className = 'filter-option';
        label.innerHTML = `
            <input type="checkbox" class="filter-checkbox" data-type="user" value="${escapeHtml(user)}" checked>
            <span>${escapeHtml(user)}</span>
        `;
        userFilterDiv.appendChild(label);
    });
    
    // Method filters
    methodFilterDiv.innerHTML = '';
    Array.from(uniqueMethods).sort().forEach(method => {
        const label = document.createElement('label');
        label.className = 'filter-option';
        label.innerHTML = `
            <input type="checkbox" class="filter-checkbox" data-type="method" value="${escapeHtml(method)}" checked>
            <span>${escapeHtml(method)}</span>
        `;
        methodFilterDiv.appendChild(label);
    });
    
    // Add event listeners
    document.querySelectorAll('.filter-checkbox').forEach(cb => {
        cb.addEventListener('change', onFilterChange);
    });
}

// Handle filter changes
function onFilterChange() {
    // Update filter state
    filterState.users = Array.from(document.querySelectorAll('.filter-checkbox[data-type="user"]:checked')).map(cb => cb.value);
    filterState.methods = Array.from(document.querySelectorAll('.filter-checkbox[data-type="method"]:checked')).map(cb => cb.value);
    filterState.maxEdges = parseInt(document.getElementById('maxEdgesSlider').value) || 0;
    filterState.minConnections = parseInt(document.getElementById('minConnectionsSlider').value) || 0;
    filterState.selectedNodeHops = parseInt(document.getElementById('selectedNodeHopsSlider').value) || 0;

    applyFilters();
}

// Apply filters to the graph
function applyFilters() {
    if (isPathView) return; // Don't apply filters in path view

    // Use search results if search is active, otherwise use all data
    const baseNodes = searchResultNodes || allNodes;
    const baseEdges = searchResultEdges || allEdges;

    // Filter edges by user/method
    let filteredEdges = baseEdges;
    if (filterState.users.length > 0) {
        filteredEdges = filteredEdges.filter(e => filterState.users.includes(e.user));
    }
    if (filterState.methods.length > 0) {
        filteredEdges = filteredEdges.filter(e => filterState.methods.includes(e.method));
    }

    // Limit edges by recency (most recent first)
    const edgesBeforeLimit = filteredEdges.length;
    if (filterState.maxEdges > 0 && filteredEdges.length > filterState.maxEdges) {
        filteredEdges = filteredEdges
            .slice()
            .sort((a, b) => (b.time || 0) - (a.time || 0))
            .slice(0, filterState.maxEdges);
    }

    // Get nodes that have edges
    const connectedNodeIds = new Set();
    const nodeConnectionCount = {};
    const incomingCount = {};
    const outgoingCount = {};

    filteredEdges.forEach(edge => {
        connectedNodeIds.add(edge.from);
        connectedNodeIds.add(edge.to);
        nodeConnectionCount[edge.from] = (nodeConnectionCount[edge.from] || 0) + 1;
        nodeConnectionCount[edge.to] = (nodeConnectionCount[edge.to] || 0) + 1;
        outgoingCount[edge.from] = (outgoingCount[edge.from] || 0) + 1;
        incomingCount[edge.to] = (incomingCount[edge.to] || 0) + 1;
    });

    // Filter nodes by minimum connections
    let filteredNodes = baseNodes.filter(n =>
        connectedNodeIds.has(n.id) &&
        (nodeConnectionCount[n.id] || 0) >= filterState.minConnections
    );

    // Apply BloodHound-style colors based on node role
    const isLargeGraph = filteredEdges.length > 500;
    filteredNodes = filteredNodes.map(node => {
        const incoming = incomingCount[node.id] || 0;
        const outgoing = outgoingCount[node.id] || 0;

        let color;
        if (outgoing > 0 && incoming === 0) {
            color = { border: '#22c55e', background: '#22c55e' };
        } else if (incoming > outgoing * 2) {
            color = { border: '#a855f7', background: '#a855f7' };
        } else if (incoming > 0 && outgoing > 0) {
            color = { border: '#fbbf24', background: '#fbbf24' };
        } else {
            color = { border: '#6a7cf6', background: '#6a7cf6' };
        }

        return {
            ...node,
            color: color,
            title: `${node.hostname}\nIPs: ${node.interfaces.join(', ')}\nIncoming: ${incoming}, Outgoing: ${outgoing}`
        };
    });

    // Filter edges to only include those between filtered nodes
    const filteredNodeIds = new Set(filteredNodes.map(n => n.id));
    filteredEdges = filteredEdges.filter(e =>
        filteredNodeIds.has(e.from) && filteredNodeIds.has(e.to)
    );

    if (selectedNodeId !== null && filterState.selectedNodeHops > 0) {
        const visibleIds = getNodesWithinHops(selectedNodeId, filterState.selectedNodeHops, filteredEdges);
        filteredNodes = filteredNodes.filter(n => visibleIds.has(n.id));
        const hopFilteredNodeIds = new Set(filteredNodes.map(n => n.id));
        filteredEdges = filteredEdges.filter(e => hopFilteredNodeIds.has(e.from) && hopFilteredNodeIds.has(e.to));
    }

    // Add labels only for smaller graphs (performance)
    filteredEdges = filteredEdges.map(edge => {
        const edgeData = {
            ...edge,
            title: `${edge.user}@${edge.ip}:${edge.port}\nMethod: ${edge.method}\nCreds: ${edge.creds}`
        };
        if (!isLargeGraph) {
            edgeData.label = edge.user;
        }
        return edgeData;
    });

    // Apply search highlighting if search is active
    if (window.searchHighlightNodes) {
        filteredNodes = filteredNodes.map(node => {
            if (window.searchHighlightNodes.has(node.id)) {
                return {
                    ...node,
                    color: {
                        border: '#ffc107',
                        background: '#fff176'
                    }
                };
            }
            return node;
        });
    }

    // Update graph
    nodes.clear();
    edges.clear();
    nodes.add(filteredNodes);
    edges.add(filteredEdges);

    if (selectedNodeId !== null && filteredNodes.some(n => n.id === selectedNodeId)) {
        network.selectNodes([selectedNodeId]);
    }

    const totalAvailable = edgesBeforeLimit;
    updateStats(filteredNodes.length, filteredEdges.length, totalAvailable, isLargeGraph);

    // Handle physics based on manual override or graph size
    const shouldEnablePhysics = physicsManualOverride !== null ? physicsManualOverride : !isLargeGraph;
    
    if (shouldEnablePhysics && !physicsEnabled) {
        // Enable physics
        network.setOptions({ 
            physics: { 
                enabled: true, 
                solver: 'barnesHut',
                stabilization: {
                    enabled: true,
                    iterations: isLargeGraph ? 50 : 200
                }
            } 
        });
        physicsEnabled = true;
    } else if (!shouldEnablePhysics && physicsEnabled) {
        // Disable physics
        network.setOptions({ 
            physics: { enabled: false },
            interaction: {
                zoomView: true,
                dragView: true
            }
        });
        physicsEnabled = false;
        network.redraw();
    }

    // Update physics button state
    updatePhysicsButton();

    setTimeout(() => {
        network.fit({
            animation: {
                duration: 500,
                easingFunction: 'easeInOutQuad'
            }
        });
    }, 100);
}

function getNodesWithinHops(startNodeId, maxHops, edgeList) {
    if (maxHops <= 0) {
        return new Set(allNodes.map(n => n.id));
    }

    const adjacency = new Map();
    edgeList.forEach(edge => {
        if (!adjacency.has(edge.from)) adjacency.set(edge.from, new Set());
        if (!adjacency.has(edge.to)) adjacency.set(edge.to, new Set());
        adjacency.get(edge.from).add(edge.to);
        adjacency.get(edge.to).add(edge.from);
    });

    if (!adjacency.has(startNodeId)) {
        return new Set([startNodeId]);
    }

    const visited = new Set([startNodeId]);
    const queue = [{ id: startNodeId, depth: 0 }];

    while (queue.length > 0) {
        const current = queue.shift();
        if (current.depth >= maxHops) {
            continue;
        }

        const neighbors = adjacency.get(current.id) || new Set();
        neighbors.forEach(neighborId => {
            if (!visited.has(neighborId)) {
                visited.add(neighborId);
                queue.push({ id: neighborId, depth: current.depth + 1 });
            }
        });
    }

    return visited;
}

// Toggle filter panel
function toggleFilters() {
    const panel = document.getElementById('filterPanel');
    const btn = document.querySelector('.filter-toggle-btn');
    
    if (panel.style.display === 'none' || !panel.style.display) {
        panel.style.display = 'block';
        btn.textContent = '✕ Close Filters';
    } else {
        panel.style.display = 'none';
        btn.textContent = '⚙️ Filters';
    }
}

// Update max edges filter
function updateMaxEdges(value) {
    const parsedValue = parseInt(value) || 0;
    document.getElementById('maxEdgesValue').textContent = parsedValue === 0 ? 'All' : String(parsedValue);
    filterState.maxEdges = parsedValue;
    applyFilters();
}

// Update min connections filter
function updateMinConnections(value) {
    document.getElementById('minConnectionsValue').textContent = value;
    filterState.minConnections = parseInt(value);
    applyFilters();
}

function updateSelectedNodeHops(value) {
    const parsedValue = parseInt(value) || 0;
    document.getElementById('selectedNodeHopsValue').textContent = parsedValue === 0 ? 'All' : String(parsedValue);
    filterState.selectedNodeHops = parsedValue;
    applyFilters();
}

// Show/hide loading indicator
function showLoading(show) {
    const loading = document.getElementById('loading');
    loading.style.display = show ? 'block' : 'none';
}

// Update statistics
function updateStats(nodeCount, edgeCount, totalAvailable, isLargeGraph) {
    // Update total database counts (from allNodes/allEdges)
    document.getElementById('totalNodeCount').textContent = allNodes.length;
    document.getElementById('totalEdgeCount').textContent = allEdges.length;
    
    updateGraphStatus(nodeCount, edgeCount, totalAvailable, isLargeGraph);
    updateInsights(nodes.get(), edges.get());
}

function updateGraphStatus(nodeCount, edgeCount, totalAvailable, isLargeGraph) {
    const status = document.getElementById('graphStatus');
    if (!status) {
        return;
    }
    let html = `<strong>${nodeCount}</strong> nodes • <strong>${edgeCount}</strong> edges`;
    if (totalAvailable && totalAvailable > edgeCount) {
        html += ` <span style="color:#f59e0b;">(showing ${edgeCount} of ${totalAvailable} most recent)</span>`;
    }
    if (isLargeGraph) {
        html += ` <span style="color:#60a5fa;" title="Physics stabilized for performance">⚡</span>`;
    }
    status.innerHTML = html;
}

function updateInsights(visibleNodes, visibleEdges) {
    const panel = document.getElementById('insightsPanel');
    if (!panel) {
        return;
    }

    if (!visibleEdges || visibleEdges.length === 0) {
        panel.innerHTML = `
            <div class="insight-item">
                <h6>No active connections</h6>
                <p>Adjust filters or reload to view insights.</p>
            </div>
        `;
        return;
    }

    const nodeNameById = new Map((visibleNodes || []).map(node => [node.id, node.hostname || node.label || String(node.id)]));
    const incoming = {};
    const outgoing = {};
    const users = {};
    const methods = {};

    visibleEdges.forEach(edge => {
        incoming[edge.to] = (incoming[edge.to] || 0) + 1;
        outgoing[edge.from] = (outgoing[edge.from] || 0) + 1;
        users[edge.user] = (users[edge.user] || 0) + 1;
        methods[edge.method] = (methods[edge.method] || 0) + 1;
    });

    const topTargetId = getTopKey(incoming);
    const topPivotId = getTopKey(outgoing);
    const topUser = getTopKey(users);
    const topMethod = getTopKey(methods);

    const targetName = topTargetId !== null ? (nodeNameById.get(Number(topTargetId)) || nodeNameById.get(topTargetId) || 'Unknown host') : 'N/A';
    const pivotName = topPivotId !== null ? (nodeNameById.get(Number(topPivotId)) || nodeNameById.get(topPivotId) || 'Unknown host') : 'N/A';

    panel.innerHTML = `
        <div class="insight-item">
            <h6>Most targeted host</h6>
            <p>${escapeHtml(targetName)}</p>
            <div class="muted">${topTargetId !== null ? incoming[topTargetId] : 0} incoming connection(s)</div>
        </div>
        <div class="insight-item">
            <h6>Best pivot candidate</h6>
            <p>${escapeHtml(pivotName)}</p>
            <div class="muted">${topPivotId !== null ? outgoing[topPivotId] : 0} outgoing connection(s)</div>
        </div>
        <div class="insight-item">
            <h6>Most used account/method</h6>
            <p>${escapeHtml(topUser || 'N/A')} via ${escapeHtml(topMethod || 'N/A')}</p>
            <div class="muted">Based on currently visible edges</div>
        </div>
    `;
}

function getTopKey(counter) {
    let bestKey = null;
    let bestValue = -1;
    Object.keys(counter).forEach(key => {
        if (counter[key] > bestValue) {
            bestValue = counter[key];
            bestKey = key;
        }
    });
    return bestKey;
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

function exportGraphJSON() {
    fetch('/api/export')
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showError('Export failed: ' + data.error);
                return;
            }

            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            const a = document.createElement('a');
            a.href = url;
            a.download = `sshmap-export-${timestamp}.json`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        })
        .catch(error => {
            showError('Export failed: ' + error.message);
        });
}

function triggerImportGraphJSON() {
    const fileInput = document.getElementById('importGraphFile');
    if (!fileInput) {
        showError('Import control is not available.');
        return;
    }

    fileInput.value = '';
    fileInput.click();
}

function handleImportGraphFile(input) {
    const file = input.files && input.files[0];
    if (!file) {
        return;
    }

    const replaceExisting = document.getElementById('replaceExistingImport')?.checked || false;
    const warningMessage = replaceExisting
        ? 'This will replace the current Neo4j project data with the selected import. Continue?'
        : 'Import this project snapshot into the current Neo4j database?';

    if (!confirm(warningMessage)) {
        input.value = '';
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('replace_existing', replaceExisting ? 'true' : 'false');

    fetch('/api/import', {
        method: 'POST',
        body: formData
    })
    .then(async response => {
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Import failed');
        }
        return data;
    })
    .then(data => {
        alert(`Import completed successfully. Loaded ${data.nodes_imported} nodes and ${data.relationships_imported} relationships.`);
        loadGraph();
    })
    .catch(error => {
        showError('Import failed: ' + error.message);
    })
    .finally(() => {
        input.value = '';
    });
}

// Execute command on target host
function executeCommand(hostname) {
    const commandInput = document.getElementById('commandInput');
    const command = commandInput.value.trim();
    const outputDiv = document.getElementById('commandOutput');
    
    if (!command) {
        outputDiv.style.display = 'block';
        outputDiv.innerHTML = '<div class="error">⚠️ Please enter a command</div>';
        return;
    }
    
    // Show loading state
    outputDiv.style.display = 'block';
    outputDiv.innerHTML = '<div class="loading"><div class="loading-spinner"></div>Executing command...</div>';
    
    fetch('/api/execute', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            hostname: hostname,
            command: command
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            outputDiv.innerHTML = `
                <div class="command-result-success">
                    <strong>✓ Command executed successfully</strong><br>
                    <small>User: ${escapeHtml(data.user)}</small><br>
                    <small>Output saved to: ${escapeHtml(data.output_file)}</small>
                </div>
                <div class="command-output-text">
                    <pre>${escapeHtml(data.output)}</pre>
                </div>
            `;
        } else {
            outputDiv.innerHTML = `<div class="error">❌ Error: ${escapeHtml(data.error)}</div>`;
        }
    })
    .catch(error => {
        outputDiv.innerHTML = `<div class="error">❌ Failed to execute command: ${escapeHtml(error.message)}</div>`;
    });
}

// Show default information
function showDefaultInfo() {
    const container = document.getElementById('detailsContainer');
    container.innerHTML = `
        <div class="info-section" style="margin-top: 20px;">
            <h3>ℹ️ Information</h3>
            <p style="color: #9ca3af; font-size: 14px; line-height: 1.6;">
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
    const searchResults = document.getElementById('searchResults');
    let searchTimeout = null;
    
    // Hide context menu on any click
    document.addEventListener('click', function(event) {
        if (!event.target.closest('#contextMenu')) {
            hideContextMenu();
        }
    });
    
    searchInput.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        const query = this.value;
        
        if (!query || query.trim() === '') {
            searchResults.style.display = 'none';
            performSearch('');
            return;
        }
        
        searchTimeout = setTimeout(() => {
            performSearchWithPopup(query);
        }, 300);
    });
    
    // Close popup when clicking outside
    document.addEventListener('click', function(e) {
        if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
            searchResults.style.display = 'none';
        }
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

    bindPathInputAutocomplete(document.getElementById('startNode'));
    bindPathInputAutocomplete(document.getElementById('endNode'));

    document.addEventListener('click', function(e) {
        const startInput = document.getElementById('startNode');
        const endInput = document.getElementById('endNode');
        const clickedPathInput = (startInput && startInput.contains(e.target)) ||
            (endInput && endInput.contains(e.target));
        const clickedPopup = pathSuggestionsPopup && pathSuggestionsPopup.contains(e.target);

        if (!clickedPathInput && !clickedPopup) {
            hidePathSuggestionsPopup();
        }
    });

    document.addEventListener('mousedown', function(e) {
        if (!pathSuggestionsPopup || !pathSuggestionsPopup.contains(e.target)) {
            return;
        }

        const item = e.target.closest('[data-hostname]');
        if (!item || !activePathInputId) {
            return;
        }

        const inputEl = document.getElementById(activePathInputId);
        if (!inputEl) {
            return;
        }

        const encodedHostname = item.getAttribute('data-hostname') || '';
        inputEl.value = decodeURIComponent(encodedHostname);
        inputEl.focus();
        hidePathSuggestionsPopup();
    });

    window.addEventListener('resize', function() {
        initializeResponsiveUI();
        if (activePathInputId) {
            const activeInput = document.getElementById(activePathInputId);
            if (activeInput) {
                showPathSuggestionsPopup(activeInput);
            }
        }
    });

    document.addEventListener('keydown', function(e) {
        if (isTypingField(e.target)) {
            if (e.key === 'Escape') {
                searchResults.style.display = 'none';
                hideContextMenu();
                hidePathSuggestionsPopup();
            }
            return;
        }

        const key = e.key.toLowerCase();
        if (e.key === '/') {
            e.preventDefault();
            searchInput.focus();
            searchInput.select();
            return;
        }

        if (e.key === 'Escape') {
            searchResults.style.display = 'none';
            hideContextMenu();
            hidePathSuggestionsPopup();
            network.unselectAll();
            showDefaultInfo();
            return;
        }

        if (key === 'r') {
            loadGraph();
            return;
        }

        if (key === 'f' && network) {
            network.fit();
            return;
        }

        if (key === 'l') {
            toggleSidebar('left');
            return;
        }

        if (key === 'd') {
            toggleSidebar('right');
        }
    });
}

function initializeResponsiveUI() {
    if (window.innerWidth > 900 || mobileUiInitialized) {
        return;
    }

    const leftSidebar = document.getElementById('leftSidebar');
    const rightSidebar = document.getElementById('rightSidebar');
    const leftFloatingBtn = document.getElementById('floatingLeftToggle');
    const rightFloatingBtn = document.getElementById('floatingRightToggle');

    if (!leftSidebar.classList.contains('collapsed')) {
        leftSidebar.classList.add('collapsed');
        leftFloatingBtn.classList.add('visible');
    }

    if (!rightSidebar.classList.contains('collapsed')) {
        rightSidebar.classList.add('collapsed');
        rightFloatingBtn.classList.add('visible');
    }

    mobileUiInitialized = true;
}

function isTypingField(target) {
    if (!target) {
        return false;
    }
    return target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;
}

// Search with popup results
function performSearchWithPopup(query) {
    fetch(`/api/search?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showError('Search error: ' + data.error);
                return;
            }
            
            displaySearchPopup(data, query);
            // Also perform the graph filtering
            filterGraphBySearchResults(data);
        })
        .catch(error => {
            showError('Search failed: ' + error.message);
        });
}

// Display search results in popup
function displaySearchPopup(data, query) {
    const popup = document.getElementById('searchResults');
    
    if (data.nodes.length === 0 && data.edges.length === 0) {
        popup.innerHTML = '<div class="search-no-results">No results found for "' + escapeHtml(query) + '"</div>';
        popup.style.display = 'block';
        return;
    }
    
    let html = '';
    
    // Display nodes section
    if (data.nodes.length > 0) {
        html += '<div class="search-section">';
        html += '<div class="search-section-title">🖥️ Nodes <span class="search-result-count">(' + data.nodes.length + ')</span></div>';
        
        data.nodes.forEach(node => {
            const interfaces = node.interfaces && node.interfaces.length > 0 
                ? node.interfaces.join(', ') 
                : 'No IPs';
            
            html += `
                <div class="search-result-item node-result" onclick="selectNodeFromSearch(${node.id})">
                    <div class="search-result-primary">🖥️ ${escapeHtml(node.hostname)}</div>
                    <div class="search-result-secondary">${escapeHtml(interfaces)}</div>
                </div>
            `;
        });
        
        html += '</div>';
    }
    
    // Display edges section
    if (data.edges.length > 0) {
        html += '<div class="search-section">';
        html += '<div class="search-section-title">🔗 Connections <span class="search-result-count">(' + data.edges.length + ')</span></div>';
        
        data.edges.forEach(edge => {
            html += `
                <div class="search-result-item edge-result" onclick="selectEdgeFromSearch(${edge.id})">
                    <div class="search-result-primary">🔗 ${escapeHtml(edge.from_hostname)} → ${escapeHtml(edge.to_hostname)}</div>
                    <div class="search-result-secondary">${escapeHtml(edge.user)}@${escapeHtml(edge.ip)}:${edge.port} (${escapeHtml(edge.method)})</div>
                </div>
            `;
        });
        
        html += '</div>';
    }
    
    popup.innerHTML = html;
    popup.style.display = 'block';
}

// Filter graph based on search results
function filterGraphBySearchResults(data) {
    // Get IDs of matching nodes
    const matchingNodeIds = new Set(data.nodes.map(n => n.id));
    
    // For matching nodes, get ALL their edges (incoming and outgoing)
    const relevantEdges = allEdges.filter(edge => 
        matchingNodeIds.has(edge.from) || matchingNodeIds.has(edge.to)
    );
    
    // Get all nodes connected by these edges
    const connectedNodeIds = new Set();
    matchingNodeIds.forEach(id => connectedNodeIds.add(id));
    relevantEdges.forEach(edge => {
        connectedNodeIds.add(edge.from);
        connectedNodeIds.add(edge.to);
    });
    
    // Store search results as the base for filtering
    searchResultNodes = allNodes.filter(n => connectedNodeIds.has(n.id));
    searchResultEdges = relevantEdges;
    
    // Store matching node IDs for highlighting
    window.searchHighlightNodes = matchingNodeIds;
    
    // Apply filters on search results
    applyFilters();
    
    // Fit to show filtered results, focusing on the matched node
    setTimeout(() => {
        if (matchingNodeIds.size === 1) {
            // If single node match, focus on it
            const nodeId = Array.from(matchingNodeIds)[0];
            network.focus(nodeId, {
                scale: 1.5,
                animation: {
                    duration: 500,
                    easingFunction: 'easeInOutQuad'
                }
            });
        } else {
            // Multiple matches, fit all
            network.fit({
                animation: {
                    duration: 500,
                    easingFunction: 'easeInOutQuad'
                }
            });
        }
    }, 100);
}

// Select node from search popup
function selectNodeFromSearch(nodeId) {
    document.getElementById('searchResults').style.display = 'none';
    network.selectNodes([nodeId]);
    network.focus(nodeId, {
        scale: 1.5,
        animation: {
            duration: 500,
            easingFunction: 'easeInOutQuad'
        }
    });
    loadNodeDetails(nodeId);
}

// Select edge from search popup
function selectEdgeFromSearch(edgeId) {
    document.getElementById('searchResults').style.display = 'none';
    network.selectEdges([edgeId]);
    
    // Get the edge to find connected nodes
    const edge = allEdges.find(e => e.id === edgeId);
    if (edge) {
        // Focus on the source node of the edge
        network.focus(edge.from, {
            scale: 1.5,
            animation: {
                duration: 500,
                easingFunction: 'easeInOutQuad'
            }
        });
    }
    
    loadEdgeDetails(edgeId);
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

// Toggle sidebar visibility
function toggleSidebar(side) {
    if (side === 'left') {
        const sidebar = document.getElementById('leftSidebar');
        const floatingBtn = document.getElementById('floatingLeftToggle');
        sidebar.classList.toggle('collapsed');
        
        // Show/hide floating button
        if (sidebar.classList.contains('collapsed')) {
            floatingBtn.classList.add('visible');
        } else {
            floatingBtn.classList.remove('visible');
        }
    } else if (side === 'right') {
        const sidebar = document.getElementById('rightSidebar');
        const floatingBtn = document.getElementById('floatingRightToggle');
        sidebar.classList.toggle('collapsed');
        
        // Show/hide floating button
        if (sidebar.classList.contains('collapsed')) {
            floatingBtn.classList.add('visible');
        } else {
            floatingBtn.classList.remove('visible');
        }
    }
}

// Focus on a node by hostname
function focusOnHostname(hostname) {
    const node = allNodes.find(n => n.hostname === hostname);
    if (node) {
        network.focus(node.id, {
            scale: 1.5,
            animation: {
                duration: 1000,
                easingFunction: 'easeInOutQuad'
            }
        });
        network.selectNodes([node.id]);
        loadNodeDetails(node.id);
    } else {
        console.error('Node not found:', hostname);
    }
}

// Focus on an edge by ID
function focusOnEdge(edgeId) {
    const edge = allEdges.find(e => e.id === edgeId);
    if (edge) {
        network.fit({
            nodes: [edge.from, edge.to],
            animation: {
                duration: 1000,
                easingFunction: 'easeInOutQuad'
            }
        });
        network.selectEdges([edgeId]);
        loadEdgeDetails(edgeId);
    } else {
        console.error('Edge not found:', edgeId);
    }
}

// Context menu handling
let contextMenuTarget = null;
let contextMenuType = null;

function showContextMenu(event, nodeId, edgeId) {
    event.preventDefault();
    
    const menu = document.getElementById('contextMenu');
    contextMenuTarget = nodeId || edgeId;
    contextMenuType = nodeId ? 'node' : 'edge';
    
    // Build menu content based on type
    let menuHTML = '';
   
    if (contextMenuType === 'node') {
        // Node context menu
        menuHTML = `
            <div class="context-menu-item" onclick="contextMenuAction('focus')">
                <span>🎯</span> Focus on this
            </div>
            <div class="context-menu-divider"></div>
            <div class="context-menu-item" onclick="contextMenuAction('start')">
                <span>🏁</span> Start from here
            </div>
            <div class="context-menu-item" onclick="contextMenuAction('end')">
                <span>🏁</span> End here
            </div>
            <div class="context-menu-divider"></div>
            <div class="context-menu-item danger" onclick="contextMenuAction('delete')">
                <span>🗑️</span> Delete from database
            </div>
        `;
    } else {
        // Edge context menu
        menuHTML = `
            <div class="context-menu-item" onclick="contextMenuAction('focus')">
                <span>🎯</span> Focus on this
            </div>
            <div class="context-menu-divider"></div>
            <div class="context-menu-item danger" onclick="contextMenuAction('delete')">
                <span>🗑️</span> Delete from database
            </div>
        `;
    }
    
    menu.innerHTML = menuHTML;
    menu.style.display = 'block';
    menu.style.left = event.pageX + 'px';
    menu.style.top = event.pageY + 'px';
}

function hideContextMenu() {
    const menu = document.getElementById('contextMenu');
    menu.style.display = 'none';
    contextMenuTarget = null;
    contextMenuType = null;
}

function contextMenuAction(action) {
    // Store target info before hiding menu
    const target = contextMenuTarget;
    const type = contextMenuType;
    
    hideContextMenu();
    
    if (!target) {
        console.log('No context menu target');
        return;
    }
    
    console.log('Context menu action:', action, 'for', type, target);
    
    switch(action) {
        case 'focus':
            if (type === 'node') {
                console.log('Focusing on node:', target);
                network.focus(target, {
                    scale: 1.5,
                    animation: {
                        duration: 1000,
                        easingFunction: 'easeInOutQuad'
                    }
                });
                network.selectNodes([target]);
            } else if (type === 'edge') {
                console.log('Focusing on edge:', target);
                // Get edge to find connected nodes
                const edge = allEdges.find(e => e.id === target);
                if (edge) {
                    network.fit({
                        nodes: [edge.from, edge.to],
                        animation: {
                            duration: 1000,
                            easingFunction: 'easeInOutQuad'
                        }
                    });
                    network.selectEdges([target]);
                }
            }
            break;
            
        case 'start':
            if (type === 'node') {
                console.log('Setting start node:', target);
                const node = allNodes.find(n => n.id === target);
                if (node) {
                    document.getElementById('startNode').value = node.hostname;
                    document.getElementById('startNode').focus();
                    console.log('Set startNode to:', node.hostname);
                }
            }
            break;
            
        case 'end':
            if (type === 'node') {
                console.log('Setting end node:', target);
                const node = allNodes.find(n => n.id === target);
                if (node) {
                    document.getElementById('endNode').value = node.hostname;
                    document.getElementById('endNode').focus();
                    console.log('Set endNode to:', node.hostname);
                }
            }
            break;
            
        case 'delete':
            if (confirm(`Are you sure you want to delete this ${type} from the database? This action cannot be undone.`)) {
                deleteFromDatabase(type, target);
            }
            break;
            
        default:
            console.log('Unknown action:', action);
    }
}

// Delete node or edge from database
function deleteFromDatabase(type, id) {
    const endpoint = type === 'node' ? `/api/node/${id}` : `/api/edge/${id}`;
    
    fetch(endpoint, {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(`${type.charAt(0).toUpperCase() + type.slice(1)} deleted successfully!`);
            // Reload the graph
            loadGraph();
        } else {
            alert(`Error: ${data.error}`);
        }
    })
    .catch(error => {
        alert(`Failed to delete ${type}: ${error.message}`);
    });
}

// Clean entire database
function cleanDatabase() {
    if (!confirm('⚠️ WARNING: This will delete ALL nodes and relationships from the database. This action cannot be undone. Are you sure?')) {
        return;
    }
    
    if (!confirm('Really sure? All your SSH mapping data will be permanently deleted.')) {
        return;
    }
    
    fetch('/api/clean-database', {
        method: 'DELETE'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert(`Database cleaned successfully! Deleted ${data.nodes_deleted} nodes and ${data.relationships_deleted} relationships.`);
            // Reload the graph (should be empty)
            loadGraph();
        } else {
            alert(`Error: ${data.error}`);
        }
    })
    .catch(error => {
        alert(`Failed to clean database: ${error.message}`);
    });
}

// Toggle collapsible sections
function toggleSection(header) {
    const section = header.closest('.sidebar-section');
    section.classList.toggle('collapsed');
}
