# Post-Exploitation Module Development Guide

This guide explains how to create custom post-exploitation modules for SSHMAP.

## Overview

Post-exploitation modules are executed on compromised SSH hosts to collect information, retrieve files, or perform various reconnaissance tasks. Each module has access to an active SSH session and can execute commands remotely.

## Module Structure

All modules must inherit from `BaseModule` and implement specific properties and methods.

### Required Components

1. **Inherit from BaseModule**: Your module class must extend `modules.postexploit.base_module.BaseModule`
2. **Define properties**: Implement `name`, `description`, and optionally `category`
3. **Implement run()**: This async method contains your module's main logic
4. **Return structured results**: Return a dictionary with success status and data

## Quick Start

### 1. Create a New Module File

Create a new Python file in `modules/postexploit/modules/`. For example, `mymodule.py`:

```python
"""
My custom post-exploitation module.

Brief description of what this module does.
"""

from typing import Dict, Any
from modules.postexploit.base_module import BaseModule


class MyModule(BaseModule):
    """Detailed description of the module."""
    
    _name = "mymodule"  # Class variable for registry
    
    def __init__(self, ssh_session, custom_param=None):
        """
        Initialize the module.
        
        Args:
            ssh_session: Active SSH session
            custom_param: Optional custom parameter
        """
        super().__init__(ssh_session)
        self.custom_param = custom_param
    
    @property
    def name(self) -> str:
        """Return the unique module name."""
        return "mymodule"
    
    @property
    def description(self) -> str:
        """Return a description of what the module does."""
        return "My custom module that does something useful"
    
    @property
    def category(self) -> str:
        """
        Return the module category.
        
        Common categories:
        - 'recon': Reconnaissance and information gathering
        - 'exfil': Data exfiltration
        - 'persist': Persistence mechanisms
        - 'lateral': Lateral movement
        - 'general': General purpose
        """
        return "recon"
    
    async def run(self) -> Dict[str, Any]:
        """
        Execute the module's main functionality.
        
        Returns:
            Dictionary with structure:
            {
                'success': bool,
                'hostname': str,
                'data': dict,
                'error': str (optional, if success=False)
            }
        """
        hostname = self.get_hostname()
        self.log_info(f"Starting custom module on {hostname}")
        
        try:
            results = {
                'success': True,
                'hostname': hostname,
                'data': {}
            }
            
            # Execute commands and collect data
            output = await self.execute_command("whoami")
            results['data']['current_user'] = output.strip()
            
            # More data collection...
            
            self.log_success(f"Module completed successfully on {hostname}")
            return results
            
        except Exception as e:
            self.log_error(f"Module failed: {e}")
            return {
                'success': False,
                'hostname': hostname,
                'error': str(e),
                'data': {}
            }
```

### 2. Test Your Module

The module will be automatically discovered and available immediately. Test it:

```bash
# List modules to verify it's available
python3 sshmap_postexploit.py --list

# Run your module
python3 sshmap_postexploit.py --hostname target_host --module mymodule
```

## BaseModule API Reference

The `BaseModule` class provides several useful methods and properties:

### Properties to Implement

- `name`: Unique identifier for your module (lowercase, no spaces)
- `description`: Human-readable description of module functionality
- `category`: Module category (recon, exfil, persist, lateral, general)

### Methods to Implement

- `async run() -> Dict[str, Any]`: Main module logic

### Available Helper Methods

#### Command Execution

```python
# Execute a command and get stdout
output = await self.execute_command("ls -la /tmp")

# Execute a command and get both stdout and stderr
stdout, stderr = await self.execute_command_with_stderr("find / -name secret.txt 2>&1")
```

#### Information Methods

```python
# Get the remote hostname
hostname = self.get_hostname()
```

#### Logging Methods

```python
# Log informational messages
self.log_info("Processing data...")

# Log success messages
self.log_success("Data collected successfully")

# Log warnings
self.log_warning("Some data unavailable")

# Log errors
self.log_error("Failed to retrieve data")
```

## Best Practices

### 1. Error Handling

Always wrap your code in try-except blocks and handle failures gracefully:

```python
async def run(self):
    try:
        # Main logic here
        pass
    except Exception as e:
        self.log_error(f"Module failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'hostname': self.get_hostname(),
            'data': {}
        }
```

### 2. Graceful Degradation

If some commands fail, still return partial results:

```python
results = {
    'success': True,
    'data': {}
}

try:
    data1 = await self.execute_command("command1")
    results['data']['field1'] = data1
except Exception as e:
    self.log_warning(f"Could not get field1: {e}")
    results['data']['field1'] = None

# Continue with other data collection...
```

### 3. Check Command Availability

Before using specific tools, check if they exist:

```python
# Check if a tool is available
check = await self.execute_command("which nmap 2>/dev/null")
if check.strip():
    # nmap is available
    output = await self.execute_command("nmap -sn 192.168.1.0/24")
else:
    self.log_warning("nmap not available")
```

### 4. Logging

Use appropriate log levels:
- `log_info()`: Progress updates
- `log_success()`: Successful operations
- `log_warning()`: Recoverable issues
- `log_error()`: Serious errors

### 5. Result Structure

Always return a consistent structure:

```python
{
    'success': True,           # or False
    'hostname': 'host.name',   # target hostname
    'data': {                  # collected data
        'key1': 'value1',
        'key2': 'value2'
    },
    'error': 'error message'   # only if success=False
}
```

## Example Modules

### Simple Command Output Module

```python
class SimpleCommandModule(BaseModule):
    _name = "simple_cmd"
    
    def __init__(self, ssh_session, command="uname -a"):
        super().__init__(ssh_session)
        self.command = command
    
    @property
    def name(self):
        return "simple_cmd"
    
    @property
    def description(self):
        return "Execute a simple command and return output"
    
    @property
    def category(self):
        return "general"
    
    async def run(self):
        try:
            output = await self.execute_command(self.command)
            return {
                'success': True,
                'hostname': self.get_hostname(),
                'data': {
                    'command': self.command,
                    'output': output.strip()
                }
            }
        except Exception as e:
            return {
                'success': False,
                'hostname': self.get_hostname(),
                'error': str(e)
            }
```

### Data Collection Module

```python
class ProcessListModule(BaseModule):
    _name = "proclist"
    
    @property
    def name(self):
        return "proclist"
    
    @property
    def description(self):
        return "Collect list of running processes"
    
    @property
    def category(self):
        return "recon"
    
    async def run(self):
        hostname = self.get_hostname()
        self.log_info(f"Collecting process list from {hostname}")
        
        try:
            # Get detailed process list
            ps_output = await self.execute_command(
                "ps aux --sort=-%mem | head -20"
            )
            
            # Get process count
            proc_count = await self.execute_command(
                "ps aux | wc -l"
            )
            
            results = {
                'success': True,
                'hostname': hostname,
                'data': {
                    'top_processes': ps_output.strip(),
                    'total_count': int(proc_count.strip()) - 1  # Subtract header
                }
            }
            
            self.log_success(f"Collected {results['data']['total_count']} processes")
            return results
            
        except Exception as e:
            self.log_error(f"Failed to collect processes: {e}")
            return {
                'success': False,
                'hostname': hostname,
                'error': str(e),
                'data': {}
            }
```

## Module Discovery

Modules are automatically discovered by the `ModuleRegistry` when placed in the `modules/postexploit/modules/` directory. The registry:

1. Scans for `.py` files in the modules directory
2. Imports each file
3. Finds classes that inherit from `BaseModule`
4. Registers them by name

No additional configuration is needed - just create your module file and it will be available immediately.

## Testing Your Module

Create unit tests in `tests/test_postexploit.py`:

```python
@pytest.mark.asyncio
async def test_mymodule(mock_ssh_session):
    """Test MyModule functionality."""
    module = MyModule(mock_ssh_session)
    result = await module.run()
    
    assert result['success'] is True
    assert 'data' in result
    # Add more assertions...
```

Run tests:
```bash
python -m pytest tests/test_postexploit.py -v
```

## Advanced Topics

### Using Module Parameters

You can pass custom parameters when instantiating modules:

```python
class ConfigurableModule(BaseModule):
    def __init__(self, ssh_session, target_dir="/tmp", recursive=False):
        super().__init__(ssh_session)
        self.target_dir = target_dir
        self.recursive = recursive
```

When using the module programmatically:
```python
result = await runner.run_module(
    "configurable",
    ssh_session,
    target_dir="/var/log",
    recursive=True
)
```

### Saving Files Locally

To save retrieved files:

```python
import os

async def run(self):
    # Get file content
    content = await self.execute_command("cat /etc/passwd")
    
    # Save locally
    output_dir = "output/retrieved_files"
    os.makedirs(output_dir, exist_ok=True)
    
    filename = f"{self.get_hostname()}_passwd.txt"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    return {
        'success': True,
        'data': {
            'local_path': filepath,
            'size': len(content)
        }
    }
```

## Troubleshooting

### Module Not Appearing

1. Check file is in `modules/postexploit/modules/`
2. Verify class inherits from `BaseModule`
3. Ensure `_name` class variable is set
4. Check for syntax errors in the module

### Module Fails to Run

1. Check SSH session is active
2. Verify commands are compatible with target OS
3. Check command permissions on remote host
4. Add more error handling and logging

## Contributing

When contributing modules:

1. Follow the coding style of existing modules
2. Add docstrings for classes and methods
3. Include unit tests
4. Handle errors gracefully
5. Log appropriately
6. Update this guide if you add new patterns

## Need Help?

- Check existing modules in `modules/postexploit/modules/`
- Review `base_module.py` for available methods
- Look at test examples in `tests/test_postexploit.py`
