# SSH Brute Project

A modular Python tool for performing SSH bruteforce attacks, storing access relationships in a Neo4j graph, and visualizing them with an interactive web interface.

## Features
- 🔐 SSH bruteforce with passwords and private keys
- 🗃️ Neo4j integration
- 🪵 Standard Python logging
- 🧩 Modular architecture
- 🔁 Post-exploitation SSH key discovery
- ⚡ Threaded scanning
- 🖥️ CLI with argparse
- 🌐 Web interface via FastAPI + PyVis

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
Edit ssh_brute_project/config.py:
```JSON
CONFIG = {
    "neo4j_uri": "bolt://localhost:7687",
    "neo4j_user": "neo4j",
    "neo4j_pass": "your_password"
}

```

### Usage
```bash
python main.py 10.0.0.1 10.0.0.2 --users wordlists/users.txt --passwords wordlists/passwords.txt --keys wordlists/keys/
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