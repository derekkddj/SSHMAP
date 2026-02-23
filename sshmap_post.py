"""
SSHMAP Post-Exploitation Tool

This tool runs post-exploitation modules on remote hosts using connections
discovered by the main SSHMAP scanning tool. It does not interfere with the
scanning process and operates independently.
"""
import argparse
import sys
import asyncio
import os
from datetime import datetime
from modules.config import CONFIG
from modules.graphdb import GraphDB
from modules.logger import sshmap_logger, setup_debug_logging
from modules.console import nxc_console
from modules.SSHSessionManager import SSHSessionManager
from modules.credential_store import CredentialStore
from modules.post_exploitation import ModuleRegistry
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
)
from rich.table import Table
import subprocess

console = nxc_console

# These will be initialized in main()
graph = None
currenttime = None


def print_banner():
    """Print the sshmap-post banner."""
    banner = """
    ███████╗███████╗██╗  ██╗███╗   ███╗ █████╗ ██████╗     ██████╗  ██████╗ ███████╗████████╗
    ██╔════╝██╔════╝██║  ██║████╗ ████║██╔══██╗██╔══██╗    ██╔══██╗██╔═══██╗██╔════╝╚══██╔══╝
    ███████╗███████╗███████║██╔████╔██║███████║██████╔╝    ██████╔╝██║   ██║███████╗   ██║   
    ╚════██║╚════██║██╔══██║██║╚██╔╝██║██╔══██║██╔═══╝     ██╔═══╝ ██║   ██║╚════██║   ██║   
    ███████║███████║██║  ██║██║ ╚═╝ ██║██║  ██║██║         ██║     ╚██████╔╝███████║   ██║   
    ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝         ╚═╝      ╚═════╝ ╚══════╝   ╚═╝   
    
    Post-Exploitation Tool for SSHMAP
    Run modular post-exploitation on discovered SSH connections
    """
    console.print(banner, style="bold cyan")


def list_modules(registry: ModuleRegistry):
    """Display a table of available modules."""
    table = Table(title="Available Post-Exploitation Modules", show_header=True)
    table.add_column("Module Name", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")
    
    for module_instance in registry.get_all_modules():
        table.add_row(module_instance.name, module_instance.description)
    
    console.print(table)


async def run_module_on_host(
    module_name: str,
    hostname: str,
    local_hostname: str,
    credential_store: CredentialStore,
    output_dir: str,
    registry: ModuleRegistry,
    proxy_url: str = None,
):
    """Run a specific module on a single host."""
    try:
        # Get the module
        module = registry.get_module(module_name)
        
        # Establish SSH connection
        ssh_session_manager = SSHSessionManager(
            graphdb=graph, credential_store=credential_store, proxy_url=proxy_url
        )
        ssh_session = await ssh_session_manager.get_session(hostname, local_hostname)
        
        if not ssh_session:
            sshmap_logger.error(f"No SSH session found for {hostname}.")
            return {"success": False, "error": "No SSH session"}
        
        sshmap_logger.display(
            f"SSH session established with {hostname} as {ssh_session.user}."
        )
        
        # Execute the module
        result = await module.execute(ssh_session, output_dir)
        
        return result
        
    except Exception as e:
        sshmap_logger.error(f"Failed to run module {module_name} on {hostname}: {e}")
        return {"success": False, "error": str(e)}


async def async_main(args):
    """Main async execution function."""
    setup_debug_logging()
    # Load credentials
    credential_store = CredentialStore(args.credentialspath)
    
    # Get local hostname
    local_hostname = None
    try:
        result = subprocess.run(
            ["hostname"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            local_hostname = result.stdout.strip()
            sshmap_logger.display(f"Local hostname: {local_hostname}")
        else:
            sshmap_logger.error("Failed to get local hostname")
            return
    except Exception as e:
        sshmap_logger.error(f"Failed to get local hostname: {e}")
        return
    
    # Initialize module registry
    registry = ModuleRegistry()
    
    # List modules if requested
    if args.list:
        list_modules(registry)
        return
    
    # Create base output directory
    base_output_dir = os.path.join(args.output, f"post_exploitation_{currenttime}")
    os.makedirs(base_output_dir, exist_ok=True)
    sshmap_logger.display(f"Base output directory: {base_output_dir}")
    
    # Determine which hosts to target
    if args.all:
        hosts = graph.get_all_hosts()
        hostnames = [h["hostname"] for h in hosts if h["hostname"] != local_hostname]
        sshmap_logger.display(f"Running on all {len(hostnames)} reachable hosts")
    else:
        if not args.hostname:
            sshmap_logger.error("Either --hostname or --all must be specified")
            return
        hostnames = [args.hostname]
    
    # Determine which modules to run
    if args.module:
        modules_to_run = [args.module]
    elif args.all_modules:
        modules_to_run = registry.list_modules()
    else:
        sshmap_logger.error("Either --module or --all-modules must be specified")
        return
    
    sshmap_logger.display(
        f"Running modules: {', '.join(modules_to_run)} on {len(hostnames)} host(s)"
    )
    
    # Progress tracking
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}", justify="right"),
        BarColumn(),
        "[{task.completed}/{task.total}]",
        TimeElapsedColumn(),
        console=console,
        disable=not console.is_terminal,
    )
    
    # Run modules on each host
    with progress:
        for hostname in hostnames:
            for module_name in modules_to_run:
                task = progress.add_task(
                    f"[cyan]{module_name} on {hostname}", total=1
                )
                
                result = await run_module_on_host(
                    module_name,
                    hostname,
                    local_hostname,
                    credential_store,
                    base_output_dir,
                    registry,
                    proxy_url=args.proxy,
                )
                
                progress.update(task, advance=1)
                
                if result["success"]:
                    progress.console.print(
                        f"[green]✓[/green] {module_name} completed on {hostname}"
                    )
                else:
                    progress.console.print(
                        f"[red]✗[/red] {module_name} failed on {hostname}: {result.get('error', 'Unknown error')}"
                    )
    
    console.print("\n[green]Post-exploitation completed![/green]")
    console.print(f"Results saved in: {base_output_dir}")


def main():
    """Main entry point."""
    global graph, currenttime
    
    parser = argparse.ArgumentParser(
        description="SSHMAP Post-Exploitation Tool - Run modular post-exploitation on discovered SSH connections",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    
    parser.add_argument(
        "--hostname",
        help="Target hostname to run post-exploitation on"
    )
    
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run on all reachable hosts in the graph database"
    )
    
    parser.add_argument(
        "--module",
        help="Specific module to run (use --list to see available modules)"
    )
    
    parser.add_argument(
        "--all-modules",
        action="store_true",
        help="Run all available post-exploitation modules"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all available post-exploitation modules and exit"
    )
    
    parser.add_argument(
        "--credentialspath",
        default="wordlists/credentials.csv",
        help="Path to CSV credentials file (default: wordlists/credentials.csv)"
    )
    
    parser.add_argument(
        "--output",
        default="output",
        help="Base output directory for results (default: output)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug level logging"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    parser.add_argument(
        "--proxy",
        help="SOCKS5/HTTP proxy URL (e.g., socks5://127.0.0.1:9050)",
        default=None
    )
    
    args = parser.parse_args()
    
    # Print banner
    if not args.list:
        print_banner()
    
    # Initialize GraphDB and timestamp
    currenttime = datetime.now().strftime('%Y%m%d_%H%M%S')
    graph = GraphDB(CONFIG["neo4j_uri"], CONFIG["neo4j_user"], CONFIG["neo4j_pass"])
    
    # Check Neo4j connectivity
    try:
        graph.driver.verify_connectivity()
    except Exception as e:
        sshmap_logger.error(
            f"Neo4J connectivity check failed, check if it is running: {e}"
        )
        return
    
    # Run async main
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        sshmap_logger.warning("\nInterrupted by user")
        sys.exit(1)
    finally:
        graph.close()


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        import asyncio.windows_events
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    main()
