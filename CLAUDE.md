# SSHMAP - Project Architecture & Specifications

## Project Overview

**SSHMAP** (SSH Credential Mapper) is a modular Python-based security tool designed for automated SSH network reconnaissance and credential mapping. It performs intelligent SSH bruteforce attacks, recursively discovers accessible hosts through jump hosts, and stores the network topology in a Neo4j graph database for visualization and path analysis.

**Version:** 1.0.3

**Primary Use Cases:**
- Network penetration testing and security assessment
- SSH credential validation across network segments
- Network topology mapping via SSH pivoting
- Post-exploitation enumeration and credential harvesting
- Generating SSH proxy jump configurations for complex network paths

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     SSHMAP System                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  SSHMAP.py   │  │ sshmap_cli   │  │ sshmap_web   │    │
│  │  (Scanner)   │  │ (Path Finder)│  │ (Web UI)     │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         │                  │                  │             │
│         └──────────────────┴──────────────────┘             │
│                            │                                │
│                            ▼                                │
│         ┌─────────────────────────────────────┐            │
│         │      Core Modules Layer             │            │
│         ├─────────────────────────────────────┤            │
│         │ • bruteforce.py (SSH attack logic) │            │
│         │ • graphdb.py (Neo4j wrapper)       │            │
│         │ • SSHSessionManager.py (SSH mgmt)  │            │
│         │ • SSHSession.py (SSH wrapper)      │            │
│         │ • credential_store.py (creds DB)   │            │
│         │ • attempt_store.py (SQLite cache)  │            │
│         │ • key_scanner.py (SSH key finder)  │            │
│         │ • config.py (configuration mgmt)   │            │
│         │ • logger.py (logging framework)    │            │
│         └─────────────────────────────────────┘            │
│                            │                                │
│         ┌──────────────────┴───────────────────┐           │
│         ▼                                      ▼           │
│  ┌─────────────┐                      ┌─────────────┐     │
│  │   Neo4j DB  │                      │  SQLite DB  │     │
│  │  (Graph)    │                      │ (Attempts)  │     │
│  └─────────────┘                      └─────────────┘     │
│                                                             │
│  ┌─────────────────────────────────────────────────┐      │
│  │   Post-Exploitation Module System               │      │
│  ├─────────────────────────────────────────────────┤      │
│  │ • credential_harvester.py                      │      │
│  │ • system_info.py                               │      │
│  │ • linpeas.py                                   │      │
│  │ • base_module.py (framework)                   │      │
│  │ • module_registry.py (auto-discovery)          │      │
│  └─────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow Architecture

1. **Initial Target Ingestion** → Targets loaded from file/CIDR
2. **Credential Store Population** → Users/passwords/keys loaded into CSV store
3. **Async Bruteforce Engine** → Parallel SSH connection attempts
4. **Session Management** → Successful connections cached and reused
5. **Graph Database Recording** → Network topology stored in Neo4j
6. **Recursive Discovery** → New networks discovered via compromised hosts
7. **Attempt Tracking** → SQLite cache prevents duplicate attempts

---

## Core Components

### 1. Main Scanner (SSHMAP.py)

**Purpose:** Primary scanning engine for SSH network discovery

**Key Features:**
- Asynchronous concurrent scanning with configurable worker pools
- Recursive network traversal through jump hosts
- Smart connection tracking with SQLite-based attempt history
- Interactive pause/resume controls during scanning
- Support for SOCKS5/HTTP proxy routing
- Blacklist/whitelist IP filtering
- Remote host pivot scanning with `--start-from`
- Real-time progress tracking with Rich UI
- ntfy.sh push notification support

**Architecture Pattern:**
- Producer-Consumer pattern with `AsyncRandomQueue`
- Worker pool with semaphore-based concurrency control
- Scan pause controller with thread-safe state management
- Progress tracking with per-jumphost task monitoring

**Key Classes:**
- `ScanPauseController`: Manages pause/resume/block jumphost functionality
- Worker coroutines: Process targets from queue with jump host resolution

**Configuration:**
```yaml
# ~/.sshmap/config.yml
neo4j_uri: "bolt://localhost:7687"
neo4j_user: "neo4j"
neo4j_pass: "neo4j"
ssh_ports: [22, 2222, 2223]
max_depth: 5
scan_timeout: 5
brute_new_credential: False
record_connection_attempts: True
credharvest_all_homes: False
max_mask: 24
```

**Command-Line Interface:**
```bash
sshmap --targets <file> \
       --users <file> \
       --passwords <file> \
       --keys <dir> \
       --maxworkers 100 \
       --maxworkers-ssh 25 \
       --maxdepth 5 \
       [--force-rescan] \
       [--start-from <hostname>] \
       [--proxy socks5://127.0.0.1:9050] \
       [--blacklist <file>] \
       [--whitelist <file>] \
       [--ntfy-url https://ntfy.sh --ntfy-topic sshmap]
```

---

### 2. Graph Database Module (graphdb.py)

**Purpose:** Neo4j wrapper for storing and querying SSH network topology

**Data Model:**
```cypher
# Node: Host
(:Host {
    hostname: String,
    ips: List<String>,
    first_seen: Integer (timestamp),
    last_seen: Integer (timestamp)
})

# Relationship: SSH_CONNECTION
(:Host)-[:SSH_CONNECTION {
    user: String,
    method: String (password|keyfile),
    creds: String,
    ip: String,
    port: Integer,
    first_seen: Integer,
    last_seen: Integer
}]->(:Host)
```

**Key Operations:**
- `add_host(hostname, ips)` - Create/update host node
- `add_ssh_connection(from, to, user, method, creds, ip, port)` - Create relationship
- `find_path(start, end)` - Shortest path Cypher query
- `find_all_paths_to(start, end, max_depth)` - All paths with depth limit
- `get_all_hosts()` - Retrieve all discovered hosts
- `get_host(hostname)` - Retrieve specific host details
- `write_ssh_config_for_path(start, end, method)` - Generate SSH config file

**Path Finding Example:**
```python
db = GraphDB(uri, user, password)
path = db.find_path("machine1", "machine4")
# Returns: [(src, metadata, dst), ...]
```

---

### 3. SSH Session Management (SSHSessionManager.py)

**Purpose:** Manages SSH connection lifecycle with jump host chaining

**Key Features:**
- Automatic jump host chain resolution from Neo4j
- Connection pooling and reuse
- Recursive session establishment through multiple hops
- Graceful cleanup of all sessions
- Support for SOCKS5/HTTP proxy routing

**Architecture:**
```python
SSHSessionManager
    ├── session_cache: Dict[hostname, SSHSession]
    ├── graphdb: GraphDB reference
    ├── credential_store: CredentialStore reference
    └── proxy_url: Optional[str]

SSHSession (Wrapper around asyncssh.SSHClientConnection)
    ├── connection: AsyncSSH connection
    ├── jump_host_chain: List[SSHSession]
    ├── hostname: String
    ├── ip: String
    ├── port: Integer
    └── methods:
        ├── exec_command(cmd)
        ├── sftp_upload(local, remote)
        ├── sftp_download(remote, local)
        ├── get_remote_hostname()
        └── is_connected()
```

**Usage Example:**
```python
manager = SSHSessionManager(graphdb, credential_store)
session = await manager.get_session("target_host", "from_host")
output, exit_code = await session.exec_command("whoami")
await manager.close_all()
```

---

### 4. Bruteforce Engine (bruteforce.py)

**Purpose:** Parallel SSH credential testing with retry logic

**Key Features:**
- Concurrent credential testing (configurable workers)
- Password and SSH key authentication
- Transient error retry mechanism (network failures)
- Connection attempt tracking to prevent duplicates
- Fallback mechanism to reuse previous successful connections
- SOCKS5/HTTP proxy support

**Smart Connection Tracking:**
- Tracks every `(source_host, target_ip, target_port, user, method, credential)` combination
- Automatically skips already-attempted credentials
- On new credentials: attempts new ones, reuses previous successful connections if no new ones succeed
- Stored in SQLite for fast lookups

**Fallback Mechanism:**
```python
# Load previous successful connections
prev_connections = graphdb.get_connections(from=source, to=target)

# Try new credentials
results = await try_all(target, port, credentials)

# If no new success, reuse previous connections
if not results:
    for prev in prev_connections:
        if not was_replaced:
            reuse_connection(prev)
```

**Function Signature:**
```python
async def try_all(
    target: str,
    port: int,
    maxworkers: int,
    jump: Optional[SSHSession],
    credential_store: CredentialStore,
    ssh_session_manager: SSHSessionManager,
    max_retries: int = 3,
    graphdb: Optional[GraphDB] = None,
    attempt_store: Optional[AttemptStore] = None,
    source_hostname: str = None,
    force_rescan: bool = False,
    proxy_url: Optional[str] = None
) -> List[BruteforceResult]
```

---

### 5. Credential Store (credential_store.py)

**Purpose:** CSV-based credential database with host-specific and global credentials

**Schema:**
```csv
hostname,port,user,secret,method
_bruteforce,22,root,password123,password
_bruteforce,22,admin,/path/to/key.pem,keyfile
192.168.1.10,22,dbuser,dbpass,password
```

**Special Hostname:**
- `_bruteforce`: Global credentials attempted on all targets

**Methods:**
- `store(hostname, port, user, secret, method)` - Add credential
- `get_credentials(hostname, port)` - Get host-specific credentials
- `get_credentials_bruteforce()` - Get global bruteforce credentials
- `get_credentials_host_and_bruteforce(hostname, port)` - Combined credentials

---

### 6. Attempt Store (attempt_store.py)

**Purpose:** SQLite database for tracking connection attempts to prevent duplicates

**Schema:**
```sql
CREATE TABLE attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_hostname TEXT NOT NULL,
    target_hostname TEXT NOT NULL,
    target_ip TEXT NOT NULL,
    target_port INTEGER NOT NULL,
    username TEXT NOT NULL,
    method TEXT NOT NULL,
    credential TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 0,
    timestamp INTEGER NOT NULL,
    UNIQUE(source_hostname, target_ip, target_port, username, method, credential)
);
```

**Key Operations:**
- `record_attempt(source, target, ip, port, user, method, cred, success)` - Record attempt
- `get_attempted_credentials(source, target, port)` - Retrieve attempted set
- `has_been_attempted(source, target, port, user, method, cred)` - Check if attempted
- Batched writes for performance (batches of 500 attempts)

---

### 7. Command Execution Tool (sshmap_execute.py)

**Purpose:** Execute commands on discovered hosts using stored graph topology

**Features:**
- Execute on single host or all reachable hosts
- Automatic jump host chain resolution
- Output storage to files
- Quiet mode for automated scripts
- Concurrent execution with worker pools

**Usage:**
```bash
# Execute on single host
sshmap-execute --hostname machine3 --command "cat /etc/passwd"

# Execute on all hosts
sshmap-execute --all --command "uname -a" --output results/

# Quiet mode (no output to console)
sshmap-execute --hostname machine2 --command "id" --quiet
```

---

### 8. CLI Path Finder (sshmap_cli.py)

**Purpose:** Find and visualize SSH connection paths between hosts

**Features:**
- Shortest path finding
- All paths enumeration with depth limit
- SSH config file generation (ProxyJump/ProxyCommand)
- Rich console output with connection details

**Usage:**
```bash
# Find shortest path
sshmap-cli machine1 machine4

# Find all paths
sshmap-cli machine1 machine4 --all --max-depth 5

# Generate SSH config
sshmap-cli machine1 machine4 --write-config --method proxyjump
# Output: /tmp/sshmap_config
```

**Generated SSH Config Example:**
```ssh-config
Host jump0
    HostName 192.168.1.100
    User root
    Port 22

Host target
    HostName 192.168.2.50
    User admin
    Port 2222
    ProxyJump jump0
```

---

### 9. Web Interface (sshmap_web.py + web_app.py)

**Purpose:** Interactive web-based graph visualization and exploration

**Technology Stack:**
- **Backend:** Flask (Python)
- **Frontend:** JavaScript + vis.js for graph rendering
- **Host:** localhost only (127.0.0.1:5000)
- **No authentication** (designed for local use)

**Features:**
- Interactive network graph visualization
- Real-time search (hostname, IP, user, port)
- Path finder with visual highlighting
- Node/edge details view
- Statistics dashboard
- Hostname autocomplete
- Zoom/pan controls

**REST API Endpoints:**
```
GET  /                    - Main web interface
GET  /api/graph           - All nodes and edges
GET  /api/search?q=<query> - Search nodes/edges
POST /api/path            - Find path between nodes
GET  /api/node/<id>       - Node details
GET  /api/edge/<id>       - Edge details
GET  /api/hosts           - All hostnames (autocomplete)
POST /api/command/execute - Execute command on host
POST /api/command/schedule- Schedule recurring command
POST /api/graph/export    - Export graph data
POST /api/graph/import    - Import graph data
```

**Starting the Web Interface:**
```bash
sshmap-web
# Open browser to http://127.0.0.1:5000
```

---

### 10. Post-Exploitation Module System (sshmap_post.py)

**Purpose:** Modular post-exploitation framework for automated enumeration

**Architecture:**
```python
BasePostExploitationModule (abstract base class)
    ├── name: str (property)
    ├── description: str (property)
    └── execute(ssh_session, output_dir) -> Dict[str, Any]

ModuleRegistry
    ├── Auto-discovery of modules in modules/post_exploitation/modules/
    ├── register(module_class)
    ├── get_module(name) -> Module instance
    └── list_modules() -> List[Module]
```

**Built-in Modules:**

#### credential_harvester
- Searches for credentials in:
  - Shell history (`.bash_history`, `.zsh_history`)
  - SSH keys and configs (`.ssh/id_rsa`, `.ssh/config`)
  - Database configs (`.my.cnf`, `.pgpass`)
  - Network configs (`.netrc`)
  - Environment files (`.env`)
  - Git configs (`.git/config`)
- Configurable: search other users' home directories

#### system_info
- Gathers comprehensive system information:
  - OS details (`uname`, `/etc/os-release`)
  - Network configuration (`ip addr`, `ifconfig`)
  - Users and groups (`/etc/passwd`, `/etc/group`)
  - Running processes (`ps aux`)
  - Installed packages (`dpkg`, `rpm`)
  - Listening services (`netstat`, `ss`)
  - Cron jobs (`crontab -l`)
  - Docker containers (if available)

#### linpeas
- Downloads LinPEAS to attacker machine (via GitHub)
- Uploads via SFTP to remote host (`/tmp/linpeas.sh`)
- Executes with bash
- Captures output for privilege escalation analysis
- Works even if remote host has no internet access
- Automatic caching to avoid repeated downloads

**Usage:**
```bash
# List available modules
sshmap-post --list

# Run specific module on one host
sshmap-post --hostname machine2 --module credential_harvester

# Run all modules on all hosts
sshmap-post --all --all-modules

# Run specific module on all hosts
sshmap-post --all --module system_info --output results/
```

**Creating Custom Modules:**
```python
# modules/post_exploitation/modules/my_module.py
from modules.post_exploitation.base_module import BasePostExploitationModule

class MyCustomModule(BasePostExploitationModule):
    @property
    def name(self) -> str:
        return "my_module"
    
    @property
    def description(self) -> str:
        return "Does custom enumeration"
    
    async def execute(self, ssh_session, output_dir: str) -> Dict[str, Any]:
        hostname = ssh_session.get_remote_hostname()
        output, _ = await ssh_session.exec_command("my_command")
        
        # Save to file
        filepath = os.path.join(output_dir, f"{hostname}_custom.txt")
        with open(filepath, 'w') as f:
            f.write(output)
        
        return {
            "success": True,
            "hostname": hostname,
            "data": output,
            "error": None
        }
```

---

## Key Algorithms and Techniques

### 1. Recursive Network Discovery

**Algorithm:**
```python
function scan_network(targets, depth=0):
    if depth > MAX_DEPTH:
        return
    
    for target in targets:
        credentials = get_credentials(target)
        results = bruteforce(target, credentials)
        
        for successful_connection in results:
            add_to_graph(successful_connection)
            
            if not visited(successful_connection.hostname):
                mark_visited(successful_connection.hostname)
                remote_networks = discover_networks(successful_connection)
                scan_network(remote_networks, depth + 1)  # Recursive call
```

**Key Optimizations:**
- Visited host tracking to prevent infinite loops
- Async/concurrent scanning with worker pools
- Smart credential filtering (skip already-attempted)
- Connection reuse via SSHSessionManager

---

### 2. Smart Connection Attempt Tracking

**Problem:** Avoid re-attempting the same credentials on every scan

**Solution:** SQLite-based tracking with composite key

**Key Implementation:**
```python
# Before attempting connection
attempted = attempt_store.get_attempted_credentials(source, target, port)
new_credentials = [c for c in all_credentials if c not in attempted]

# Attempt only new credentials
results = try_all(target, port, new_credentials)

# Record all attempts
for cred in new_credentials:
    attempt_store.record_attempt(
        source, target, ip, port,
        cred.user, cred.method, cred.secret,
        success=(cred in results)
    )

# Fallback: if no new connections, reuse previous
if not results:
    previous_connections = graphdb.get_connections(source, target)
    for prev in previous_connections:
        reuse_connection(prev)
```

**Benefits:**
- Dramatically faster subsequent scans
- Automatic credential freshness across network depth
- Maintains all discovered paths (not just latest)

---

### 3. Jump Host Chain Resolution

**Problem:** Connect to hosts deep in network via multiple hops

**Algorithm:**
```python
async def get_session(target_hostname, from_hostname):
    # Check cache
    if target_hostname in session_cache:
        return session_cache[target_hostname]
    
    # Query graph for path
    path = graphdb.find_path(from_hostname, target_hostname)
    
    # Build chain of SSH sessions
    jump_chain = []
    current_session = None
    
    for (src, metadata, dst) in path:
        current_session = await establish_connection(
            dst,
            metadata.ip,
            metadata.port,
            metadata.user,
            metadata.method,
            metadata.creds,
            via=current_session  # Use previous as jump
        )
        jump_chain.append(current_session)
    
    # Cache final session
    session_cache[target_hostname] = current_session
    return current_session
```

**Key Feature:** Automatic resolution from any source to any destination in graph

---

### 4. Concurrent Worker Pool Pattern

**Architecture:**
```python
# Producer: Queue of targets
queue = AsyncRandomQueue()
for target in targets:
    await queue.put((target, depth, jump_host))

# Consumers: Worker pool
async def worker():
    while True:
        target, depth, jump = await queue.get()
        async with semaphore:  # Limit concurrency
            await handle_target(target, depth, jump, queue)
        queue.task_done()

# Launch workers
workers = [asyncio.create_task(worker()) for _ in range(MAX_WORKERS)]
await queue.join()  # Wait for all targets processed
```

**Configurable Limits:**
- `--maxworkers`: Concurrent target scanning (default: 100)
- `--maxworkers-ssh`: Concurrent credential attempts per target (default: 25)

---

### 5. Graph-Based Path Finding

**Cypher Query (Shortest Path):**
```cypher
MATCH path = shortestPath(
    (start:Host {hostname: $start_hostname})-[:SSH_CONNECTION*]->(end:Host {hostname: $end_hostname})
)
RETURN [rel in relationships(path) | {
    user: rel.user,
    method: rel.method,
    creds: rel.creds,
    ip: rel.ip,
    port: rel.port
}] as edges,
[node in nodes(path) | node.hostname] as hostnames
```

**All Paths Query:**
```cypher
MATCH path = (start:Host {hostname: $start_hostname})-[:SSH_CONNECTION*1..$max_depth]->(end:Host {hostname: $end_hostname})
RETURN path
ORDER BY length(path)
LIMIT 100
```

---

## Data Structures

### 1. BruteforceResult
```python
@dataclass
class BruteforceResult:
    user: str
    method: str  # "password" | "keyfile"
    creds: str   # password or path to keyfile
    ssh_session: Optional[SSHSession] = None
    
    def get_ssh_connection(self) -> SSHSession:
        return self.ssh_session
```

### 2. CredentialEntry
```python
@dataclass
class CredentialEntry:
    hostname: str
    port: int
    user: str
    secret: str  # password or keyfile path
    method: str  # "password" | "keyfile"
```

### 3. AsyncRandomQueue
Custom queue implementation that randomizes target order to avoid sequential patterns
```python
class AsyncRandomQueue:
    def __init__(self, randomize=True):
        self._queue = asyncio.Queue()
        self._unfinished_tasks = 0
        self._randomize = randomize
    
    async def put(self, item):
        await self._queue.put(item)
        self._unfinished_tasks += 1
    
    async def get(self):
        # If randomize, occasionally swap with random item
        return await self._queue.get()
```

---

## Security Considerations

### Intended Use
**SSHMAP is a penetration testing and security assessment tool intended for authorized testing only.**

- Only use on networks you own or have explicit permission to test
- Unauthorized access to computer systems is illegal
- Bruteforce attacks can cause account lockouts
- Tool logs all activities for audit trails

### Storage Security
- Neo4j database stores cleartext credentials
- SQLite attempt store contains connection metadata
- Recommend: Encrypt Neo4j data directory
- Recommend: Restrict file permissions on `~/.sshmap/`

### Network Footprint
- Generates significant SSH connection attempts
- May trigger IDS/IPS alerts
- Use `--maxworkers` and `--maxworkers-ssh` to throttle
- Consider proxy routing (`--proxy socks5://...`)

---

## Performance Characteristics

### Scalability
- **Targets:** Tested with 1000+ targets
- **Credentials:** Tested with 500+ username/password combinations
- **Depth:** Practical limit around depth 5 (exponential growth)
- **Neo4j:** Handles 10,000+ nodes and edges efficiently
- **SQLite:** Handles millions of attempt records with indexes

### Optimization Techniques
1. **Attempt Tracking:** Skips 90%+ of duplicate work on subsequent scans
2. **Batched Writes:** SQLite batch inserts (500 records)
3. **Connection Pooling:** Reuses SSH sessions via SSHSessionManager
4. **Async I/O:** Non-blocking concurrent operations
5. **Randomized Queue:** Distributes load across network segments

### Typical Performance
- **Single host scan:** 1-5 seconds (depending on credentials)
- **Network of 50 hosts:** 5-15 minutes (first scan)
- **Network of 50 hosts:** 30 seconds - 2 minutes (subsequent scans with attempt tracking)
- **Web interface load time:** <1 second for graphs with 100+ nodes

---

## Configuration Files

### 1. ~/.sshmap/config.yml
```yaml
# Neo4j database connection
neo4j_uri: "bolt://localhost:7687"
neo4j_user: "neo4j"
neo4j_pass: "neo4j"

# SSH scanning
ssh_ports: [22, 2222, 2223]
max_depth: 5
scan_timeout: 5
max_mask: 24

# Features
brute_new_credential: False
record_connection_attempts: True
credharvest_all_homes: False

# Storage paths
attempt_db_path: "~/.sshmap/ssh_attempts.db"

# Notifications (optional)
ntfy_url: "https://ntfy.sh"
ntfy_topic: "sshmap-alerts"
ntfy_token: ""
```

### 2. wordlists/credentials.csv
```csv
hostname,port,user,secret,method
_bruteforce,22,root,toor,password
_bruteforce,22,admin,admin123,password
_bruteforce,22,user,/path/to/key.pem,keyfile
192.168.1.100,22,dbadmin,dbpass,password
```

### 3. wordlists/users.txt
```
root
admin
user
guest
```

### 4. wordlists/passwords.txt
```
password
admin
123456
toor
```

---

## Testing Framework

### Test Suite Structure
```
tests/
├── conftest.py                           # Pytest fixtures
├── docker-compose.yaml                   # Test environment
├── test_bruteforce.py                    # Bruteforce logic tests
├── test_integration_bruteforce.py        # Integration tests
├── test_integration_jump_chain_validation.py
├── test_e2e_full_scan.py                 # End-to-end tests
├── test_unit_ssh_session.py              # SSH session unit tests
├── test_connection_attempts.py           # Attempt store tests
├── test_start_from_option.py             # Remote pivot tests
├── test_web_interface.py                 # Web interface tests
├── test_interactive_shell.py             # Interactive features
├── test_proxy.py                         # Proxy support tests
└── test_linpeas_caching.py               # LinPEAS module tests
```

### Running Tests
```bash
# All tests
pytest

# Specific test file
pytest tests/test_bruteforce.py

# With coverage
pytest --cov=modules --cov-report=html

# Integration tests (requires Docker)
docker-compose -f tests/docker-compose.yaml up -d
pytest tests/test_integration_*.py
```

### Docker Test Environment
```yaml
# tests/docker-compose.yaml
version: '3'
services:
  machine1:
    image: rastasheep/ubuntu-sshd
    ports:
      - "2221:22"
  
  machine2:
    image: rastasheep/ubuntu-sshd
    ports:
      - "2222:22"
  
  neo4j:
    image: neo4j:latest
    ports:
      - "7474:7474"
      - "7687:7687"
```

---

## Installation & Deployment

### Requirements
- Python 3.8+
- Neo4j 4.x or 5.x with APOC plugin
- Linux/macOS/Windows (Linux recommended)
- Network access to target SSH servers

### Installation Methods

#### 1. pipx (Recommended)
```bash
# From GitHub
pipx install git+https://github.com/derekkddj/SSHMAP.git

# From local directory
cd SSHMAP
pipx install .

# Verify
sshmap --help
```

#### 2. pip (Virtual Environment)
```bash
git clone https://github.com/derekkddj/SSHMAP.git
cd SSHMAP
python -m venv venv
source venv/bin/activate
pip install -e .
```

#### 3. Docker Neo4j Setup
```bash
docker run \
  --env=NEO4J_AUTH=none \
  --publish=7474:7474 \
  --publish=7687:7687 \
  --volume=$HOME/neo4j/data:/data \
  -e NEO4J_apoc_export_file_enabled=true \
  -e NEO4J_apoc_import_file_enabled=true \
  -e NEO4J_apoc_import_file_use__neo4j__config=true \
  -e NEO4JLABS_PLUGINS='["apoc"]' \
  neo4j
```

---

## CLI Command Reference

### sshmap (Main Scanner)
```bash
sshmap --targets <file|IP|CIDR> \
       --users <file|username> \
       --passwords <file|password> \
       [--keys <directory>] \
       [--credentialspath <csv>] \
       [--maxworkers <int>] \
       [--maxworkers-ssh <int>] \
       [--maxdepth <int>] \
       [--force-rescan] \
       [--start-from <hostname>] \
       [--blacklist <file>] \
       [--whitelist <file>] \
       [--force-targets <file>] \
       [--extra-recursive-targets <file>] \
       [--proxy <url>] \
       [--ntfy-url <url> --ntfy-topic <topic>] \
       [--debug] [--verbose] [--log] [--log-file <path>]
```

### sshmap-cli (Path Finder)
```bash
sshmap-cli <start_host> <end_host> \
           [--all] \
           [--max-depth <int>] \
           [--write-config] \
           [--method {proxyjump|proxycommand}]
```

### sshmap-execute (Command Execution)
```bash
sshmap-execute --hostname <hostname> \
               --command <command> \
               [--all] \
               [--maxworkers <int>] \
               [--output <directory>] \
               [--quiet] \
               [--no-store] \
               [--debug]
```

### sshmap-post (Post-Exploitation)
```bash
sshmap-post [--hostname <hostname> | --all] \
            [--module <name> | --all-modules] \
            [--list] \
            [--output <directory>] \
            [--credentialspath <csv>] \
            [--debug]
```

### sshmap-web (Web Interface)
```bash
sshmap-web [--host <ip>] [--port <port>]
```

---

## Workflow Examples

### Example 1: Basic Network Scan
```bash
# 1. Start Neo4j
docker run -d --name neo4j \
  --env=NEO4J_AUTH=none \
  --publish=7474:7474 \
  --publish=7687:7687 \
  -e NEO4JLABS_PLUGINS='["apoc"]' \
  neo4j

# 2. Create wordlists
echo "192.168.1.0/24" > targets.txt
echo -e "root\nadmin\nuser" > users.txt
echo -e "password\nadmin\n123456" > passwords.txt

# 3. Run scan
sshmap --targets targets.txt \
       --users users.txt \
       --passwords passwords.txt \
       --maxworkers 50 \
       --maxdepth 3

# 4. View results in web interface
sshmap-web
# Open http://127.0.0.1:5000
```

### Example 2: Pivot Scanning from Compromised Host
```bash
# 1. Initial scan discovers "jumpbox"
sshmap --targets initial_targets.txt \
       --users users.txt \
       --passwords passwords.txt

# 2. Start scanning from jumpbox to reach internal network
sshmap --targets internal_targets.txt \
       --users users.txt \
       --passwords passwords.txt \
       --start-from jumpbox
```

### Example 3: Post-Exploitation on All Hosts
```bash
# 1. Run credential harvester on all discovered hosts
sshmap-post --all --module credential_harvester --output results/

# 2. Run LinPEAS for privilege escalation opportunities
sshmap-post --all --module linpeas --output results/

# 3. Run all modules on specific host
sshmap-post --hostname target_server --all-modules
```

### Example 4: Generate SSH Config for Deep Host
```bash
# Find path and generate config
sshmap-cli local_machine target_deep_host --write-config

# Use generated config
ssh -F /tmp/sshmap_config target

# Now you can connect directly with all jumps handled automatically
```

---

## Troubleshooting

### Common Issues

#### Neo4j Connection Failed
```
Error: Neo4J connectivity check failed
Solution: Ensure Neo4j is running on bolt://localhost:7687
         docker ps | grep neo4j
         Check ~/.sshmap/config.yml
```

#### APOC Plugin Missing
```
Error: Procedure apoc.* not found
Solution: Install APOC plugin
         docker exec neo4j neo4j-plugins install apoc
         Restart Neo4j container
```

#### SSH Authentication Failed
```
Error: All credentials failed for target
Solution: - Verify credentials in wordlists/credentials.csv
         - Check SSH service is running on target
         - Try manual SSH: ssh user@target
         - Check SSH key permissions (chmod 600)
```

#### Too Many Connection Attempts
```
Error: Connection refused or timeouts
Solution: Reduce worker counts
         --maxworkers 10 --maxworkers-ssh 5
         Add delays between attempts
```

#### Web Interface Not Loading
```
Error: 404 Not Found or template errors
Solution: Ensure templates/ and static/ directories exist
         pipx reinstall sshmap
         Run from source directory
```

---

## Extension and Customization

### Adding Custom Post-Exploitation Modules

1. Create new module file:
```python
# modules/post_exploitation/modules/custom_scanner.py
from modules.post_exploitation.base_module import BasePostExploitationModule
import os

class CustomScanner(BasePostExploitationModule):
    @property
    def name(self) -> str:
        return "custom_scanner"
    
    @property
    def description(self) -> str:
        return "Custom security scanner for specific vulnerabilities"
    
    async def execute(self, ssh_session, output_dir: str) -> Dict[str, Any]:
        hostname = ssh_session.get_remote_hostname()
        
        # Run commands
        output, exit_code = await ssh_session.exec_command("your_command_here")
        
        # Save results
        output_file = os.path.join(output_dir, f"{hostname}_custom.txt")
        with open(output_file, 'w') as f:
            f.write(output)
        
        return {
            "success": exit_code == 0,
            "hostname": hostname,
            "data": output,
            "error": None if exit_code == 0 else "Command failed"
        }
```

2. Module is automatically discovered and registered:
```bash
sshmap-post --list
# Will show your custom_scanner module

sshmap-post --hostname target --module custom_scanner
```

### Adding Custom Notification Channels

Extend `modules/notifier.py`:
```python
class NotificationManager:
    def notify_new_access(self, source_host, remote_host, user, method, creds, ip, port):
        # Add custom notification logic
        self._send_to_custom_service({
            "event": "new_access",
            "source": source_host,
            "target": remote_host,
            "user": user
        })
```

---

## Future Development Roadmap

### Planned Features
- [ ] Multi-protocol support (RDP, VNC, Telnet)
- [ ] Automated credential spraying with timing controls
- [ ] Machine learning for credential prediction
- [ ] Real-time web interface updates via WebSockets
- [ ] Distributed scanning with multiple attacker machines
- [ ] Integrated exploit framework (Metasploit integration)
- [ ] Advanced post-exploitation modules (persistence, lateral movement)
- [ ] Reporting engine with PDF/HTML exports
- [ ] API authentication for web interface
- [ ] Cloud provider integration (AWS, Azure, GCP)

### Completed Features
- [x] Progress bars and real-time monitoring
- [x] SSH session management and reuse
- [x] Clean shutdown on Ctrl-C
- [x] Timestamp logging in JSONL format
- [x] Post-exploitation module framework
- [x] Web-based graph visualization
- [x] Smart connection attempt tracking

---

## License & Credits

**License:** MIT License (assumed - check repository for actual license)

**Author:** derekkddj

**GitHub:** https://github.com/derekkddj/SSHMAP

**Dependencies:**
- neo4j-driver (Apache License 2.0)
- asyncssh (Eclipse Public License)
- flask (BSD License)
- rich (MIT License)
- vis.js (Apache License 2.0)
- PyYAML (MIT License)

---

## Contributing

Contributions welcome! Areas for improvement:
1. Additional post-exploitation modules
2. Performance optimizations
3. New authentication methods (Kerberos, certificates)
4. Enhanced web interface features
5. Documentation improvements
6. Bug fixes and test coverage

**Contribution Process:**
1. Fork repository
2. Create feature branch
3. Add tests for new functionality
4. Submit pull request with description

---

## Appendix: Architecture Diagrams

### Scanning Flow
```
[Start] → [Load Targets] → [Load Credentials]
   ↓
[Queue Initial Targets]
   ↓
[Worker Pool] → [Attempt SSH] → [Success?]
   │                              ├─[Yes]→[Add to Graph]→[Discover Networks]→[Queue New Targets]
   │                              └─[No]→[Record Attempt]→[Next Credential]
   ↓
[All Targets Done] → [Close Sessions] → [Generate Reports]
```

### Session Management Flow
```
[Request Session(target, from)] 
   ↓
[Check Cache] → [Found?] → [Yes] → [Return Cached Session]
   │
   └─[No] → [Query Graph for Path]
              ↓
           [Build Jump Chain]
              ↓
           [Establish Connections Recursively]
              ↓
           [Cache Final Session]
              ↓
           [Return Session]
```

### Post-Exploitation Flow
```
[sshmap-post --all --module credential_harvester]
   ↓
[Get All Hosts from Neo4j]
   ↓
[For Each Host] → [Get Session via SSHSessionManager]
                     ↓
                  [Execute Module]
                     ↓
                  [Save Results to output/]
                     ↓
                  [Return Summary]
```

---

## Conclusion

SSHMAP is a comprehensive SSH network reconnaissance framework combining bruteforce capabilities, intelligent graph-based topology mapping, automated post-exploitation, and intuitive visualization. Its modular architecture allows for easy extension while maintaining high performance through async I/O, connection pooling, and smart attempt tracking.

**Key Strengths:**
- Recursive network discovery through jump hosts
- Graph database for relationship mapping
- Smart connection tracking prevents duplicate work
- Modular post-exploitation framework
- Web-based visualization for intuitive exploration
- Comprehensive CLI tools for path finding and command execution

**Ideal Use Cases:**
- Penetration testing engagements
- Security assessments of complex networks
- Credential validation and rotation verification
- Network topology documentation
- Jump host path optimization

For questions, issues, or contributions, visit the GitHub repository.

---

**Document Version:** 1.0  
**Last Updated:** 2026-07-08  
**SSHMAP Version:** 1.0.3
