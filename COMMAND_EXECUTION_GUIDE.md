# Command Execution Feature

## Overview
The SSHMAP web interface now includes the ability to execute commands directly on any node in the SSH network graph. This feature leverages the existing `sshmap_execute` functionality to establish SSH connections through discovered jump hosts and execute commands remotely.

## Installation

When installing SSHMAP with pipx, the `sshmap-execute` command is now automatically available:

```bash
pipx install .
```

This will install both:
- `sshmap` - Main scanning tool
- `sshmap-execute` - Command execution tool

## Web Interface Usage

### Executing Commands on a Node

1. **Select a Node**: Click on any node in the graph visualization
2. **Enter Command**: In the right sidebar "Node/Edge Details" panel, you'll see an "⚡ Execute Command" section
3. **Type Command**: Enter any shell command (e.g., `ls -la`, `whoami`, `cat /etc/hostname`)
4. **Execute**: Click the "🚀 Execute" button

### Features

- **Real-time Feedback**: See command output immediately in the web interface
- **Automatic SSH Routing**: The system automatically uses the correct jump hosts from your discovered SSH network
- **Credential Management**: Uses the same credential store from your initial scan
- **Output Persistence**: All command outputs are automatically saved to the `output/` directory with timestamps
- **Error Handling**: Clear error messages if the command fails or connection cannot be established

### Output Files

Command outputs are saved to:
```
output/YYYYMMDD_HHMMSS_hostname_command.txt
```

For example:
```
output/20260114_153045_webserver01_ls_-la.txt
```

## Command-Line Usage

You can also use the standalone command-line tool:

```bash
# Execute on a single host
sshmap-execute --hostname machine5 --command "ls -la"

# Execute on all reachable hosts
sshmap-execute --all --command "whoami"

# Suppress output (save to file only)
sshmap-execute --hostname machine5 --command "ps aux" --quiet

# Don't save output to file
sshmap-execute --hostname machine5 --command "uptime" --no-store

# Use custom credentials file
sshmap-execute --hostname machine5 --command "hostname" --credentialspath /path/to/creds.csv

# Use multiple workers for parallel execution
sshmap-execute --all --command "uname -a" --maxworkers 5
```

## How It Works

1. **Session Reuse**: The system uses the SSH connection graph stored in Neo4j
2. **Jump Host Discovery**: Automatically finds the path to reach the target host
3. **Credential Selection**: Uses previously successful credentials from your scan
4. **Command Execution**: Establishes SSH connection and executes the command
5. **Result Storage**: Saves output to file and displays in web interface

## Security Considerations

- The web interface runs on `127.0.0.1:5000` (localhost only)
- Command execution requires access to the Neo4j database with discovered paths
- Uses the same credential store as the initial SSHMAP scan
- All outputs are logged for audit purposes

## Troubleshooting

### "Could not establish SSH session"
- Ensure the target host is reachable
- Verify credentials are still valid
- Check that jump hosts are still accessible

### "No reachable hosts found"
- Run an SSHMAP scan first to populate the Neo4j database
- Ensure Neo4j is running and accessible

### Command hangs
- Some commands (like interactive ones) may not work well
- Use non-interactive commands (e.g., `ls` instead of `vim`)
- Consider using `--quiet` flag for long-running commands

## Example Workflows

### Quick System Info Gathering
```bash
sshmap-execute --all --command "uname -a" --maxworkers 10
```

### Check Specific File
1. Click on target node in web interface
2. Enter: `cat /etc/os-release`
3. Click Execute
4. Review output in sidebar

### Automated Scanning
```python
from sshmap_execute import execute_command_on_host

# Use programmatically in your own scripts
```

## API Endpoint

The web interface uses the `/api/execute` endpoint:

```bash
curl -X POST http://127.0.0.1:5000/api/execute \
  -H "Content-Type: application/json" \
  -d '{"hostname": "machine5", "command": "ls -la"}'
```

Response:
```json
{
  "success": true,
  "output": "total 48\ndrwxr-xr-x 1 user user 4096 Jan 14 15:30 .\n...",
  "hostname": "machine5",
  "command": "ls -la",
  "user": "root",
  "output_file": "output/20260114_153045_machine5_ls_-la.txt"
}
```
