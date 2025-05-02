# SSH Brute Project

A modular Python tool for performing SSH bruteforce attacks, storing access relationships in a Neo4j graph.
There is a cli tool to get the paths from one starting point to other machines, and can creates que SSH commands to connect to the final machine.

## Features
- 🔐 SSH bruteforce with passwords and private keys
- 🗃️ Neo4j integration
- 🪵 Standard Python logging
- 🧩 Modular architecture
- 🔁 Post-exploitation SSH key discovery
- ⚡ Async scanning, fast as it can be
- 🖥️ CLI with argparse

## Setup

### Install Requirements
```bash
pip install -r requirements.txt
```
### Prepare Wordlists

- wordlists/users.txt

- wordlists/passwords.txt

- wordlists/keys/ (SSH private keys)

### Configure Neo4j
Create a file in ~/.sshmap/config.yml

It must contains the following config:
```YAML
# config.yml

# Neo4j database connection
neo4j_uri: "bolt://localhost:7687"
neo4j_user: "neo4j"
neo4j_pass: "neo4j"
max_mask: 24

# SSH scanning
ssh_ports: [22,2222,2223]        # List of ports to scan
max_depth: 3 #default max depth, not used now
# Optional settings
scan_timeout: 5        # Timeout for SSH connection attempts (in seconds)

```

### Usage

First run the Neo4J server, the easiest way is with docker:
```bash
docker run --env=NEO4J_AUTH=none --publish=7474:7474 --publish=7687:7687 --volume=$HOME/neo4j/data:/data neo4j
```

Then run the program from your starting host.
```bash
python SSHMAP.py --targets wordlists/ips.txt --users wordlists/usernames.txt --passwords wordlists/passwords.txt --keys wordlists/keys/
```

### Generate Interactive Graph (HTML):
```bash
python visualize.py
```

### Launch the Web Interface:
```bash
uvicorn ssh_brute_project.webapp:app --reload
```

Then visit: http://localhost:8000/graph

### Project Structure
```bash
ssh_brute_project/
├── main.py               # CLI entrypoint
├── visualize.py          # Standalone HTML graph generator
├── webapp.py             # FastAPI web interface
├── config.py             # Neo4j and global config
├── templates/
│   └── graph.html        # Graph HTML template
├── modules/
│   ├── bruteforce.py     # SSH brute logic
│   ├── graphdb.py        # Neo4j wrapper
│   └── key_scanner.py    # Remote SSH key search
└── logger.py             # Logger setup
```