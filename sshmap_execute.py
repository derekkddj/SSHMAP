import argparse
import sys
import asyncio
import os
import re
from datetime import datetime
from modules.config import CONFIG
from modules.graphdb import GraphDB
from modules.logger import sshmap_logger, setup_debug_logging
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.live import Live
from modules.console import nxc_console
from modules.SSHSessionManager import SSHSessionManager
from modules.credential_store import CredentialStore
from modules.utils import sanitize_filename_component
import subprocess

console = nxc_console

progress = Progress(
    SpinnerColumn(),
    TextColumn("[bold]{task.fields[jump_host]}", justify="right"),
    BarColumn(),
    "[{task.completed}/{task.total}]",
    TimeElapsedColumn(),
    TimeRemainingColumn(),
    transient=True,
)

# Initialize the Neo4j graph database connection
graph = GraphDB(CONFIG["neo4j_uri"], CONFIG["neo4j_user"], CONFIG["neo4j_pass"])

# Date of running
currenttime = datetime.now().strftime('%Y%m%d_%H%M%S')

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
SUDO_CMD_RE = re.compile(r"(^|[;&|]\s*|\s)sudo(\s|$)")


def normalize_command_output(output: str) -> str:
    """Normalize remote command output for stable terminal rendering and storage."""
    if not output:
        return ""
    normalized = output.replace("\r\n", "\n").replace("\r", "\n")
    normalized = ANSI_ESCAPE_RE.sub("", normalized)
    return normalized


def command_requires_pty(command: str) -> bool:
    """Return True when command likely needs a PTY (e.g., sudo with requiretty)."""
    if not command:
        return False
    return bool(SUDO_CMD_RE.search(command))

async def execute_command_on_host(
    args, target, local_hostname, credential_store, task_id, defer_output=False
):
    """
    Executes the specified command on the target host using SSH.
    Handles jump hosts and credentials from the CredentialStore.
    """
    try:
        ssh_session_manager = SSHSessionManager(
            graphdb=graph, credential_store=credential_store, proxy_url=args.proxy
        )
        host_ssh = await ssh_session_manager.get_session(target, local_hostname)
        if not host_ssh:
            sshmap_logger.error(f"No SSH session found for {target}.")
            return

        sshmap_logger.display(
            f"SSH session established with {target} as {host_ssh.user}."
        )

        if args.shell:
            await host_ssh.interactive_shell()
            return

        use_pty = args.pty or command_requires_pty(args.command)
        if use_pty:
            output = await host_ssh.exec_command_with_pty(args.command)
        else:
            output = await host_ssh.exec_command(args.command)
        output = normalize_command_output(output)
        if not args.quiet and not defer_output:
            progress.console.print(f"[green]Output from {target}:[/green]\n{output}")
        # Now save the output to a file, each host gets its own file with the date and time
        # Create output directory if it doesn't exist
        if not args.no_store:
            os.makedirs(args.output, exist_ok=True)
            # Keep outputs in the same folder even if hostname/command contains path separators.
            safe_target = sanitize_filename_component(target)
            safe_command = sanitize_filename_component(args.command[:10])
            output_filename = os.path.join(
                args.output, f"{currenttime}_{safe_target}_{safe_command}.txt"
            )
            with open(output_filename, "w") as f:
                f.write(f"Output from {target}:\n")
                f.write(f"Executed command: {args.command}\n\n")
                f.write(output)
        
        return output
    except Exception as e:
        sshmap_logger.error(f"Failed to execute command on {target}: {e}")
        return None
    finally:
        if task_id is not None:
            # Update the progress bar for this task
            progress.update(task_id, advance=1)


async def async_main(args):
    setup_debug_logging()
    credential_store = CredentialStore(args.credentialspath)

    # I get my "hostname" for the starting point, execute "hostname" in this host with python
    local_hostname = None
    try:
        result = subprocess.run(
            ["hostname"], capture_output=True, text=True, check=True
        )
        local_hostname = result.stdout.strip()
        sshmap_logger.display(f"Local hostname: {local_hostname}")
    except Exception as e:
        sshmap_logger.error(f"Failed to get local hostname: {e}")
        return
    try:
        if args.all:
            sshmap_logger.display(
                f"[START] Executing command '{args.command}' on all reachable hosts."
            )
            hosts = graph.get_all_hosts()
            sshmap_logger.display(
                f"Found {len(hosts)} reachable hosts in the graph database."
            )
            if len(hosts) == 0:
                sshmap_logger.error("No reachable hosts found in the graph database.")
                return
            # Launch multiple tasks concurrently for all targets
            queue = asyncio.Queue()
            task_ids = {}
            targets = [t["hostname"] for t in hosts if t["hostname"] != local_hostname]
            if not targets:
                sshmap_logger.warning("No remote targets found after excluding local host.")
                return

            worker_count = args.maxworkers if args.maxworkers is not None else min(10, len(targets))
            if worker_count < 1:
                worker_count = 1

            sshmap_logger.display(
                f"Using {worker_count} worker(s) for {len(targets)} target(s)."
            )

            for target in targets:
                await queue.put((target, 1, None))
            task_ids[args.command] = progress.add_task(
                description="Executing command on targets",
                total=len(targets),
                jump_host=args.command,
            )

            semaphore = asyncio.Semaphore(worker_count)
            buffered_outputs = {}

            async def tracked_worker():
                while True:
                    try:
                        hostname, _, _ = await queue.get()
                        async with semaphore:
                            output = await execute_command_on_host(
                                args,
                                hostname,
                                local_hostname,
                                credential_store,
                                None,
                                defer_output=not args.quiet,
                            )
                        if output is not None and not args.quiet:
                            buffered_outputs[hostname] = output
                        if args.command in task_ids:
                            progress.update(task_ids[args.command], advance=1)
                    except asyncio.CancelledError:
                        break
                    finally:
                        queue.task_done()

            with Live(progress, console=console, refresh_per_second=10):
                workers = [
                    asyncio.create_task(tracked_worker())
                    for _ in range(worker_count)
                ]
                try:
                    await queue.join()
                except KeyboardInterrupt:
                    sshmap_logger.warning("Ctrl+C received! Cancelling...")
                finally:
                    for w in workers:
                        w.cancel()
                    await asyncio.gather(*workers, return_exceptions=True)

            if not args.quiet:
                for hostname in targets:
                    output = buffered_outputs.get(hostname)
                    if output is None:
                        continue
                    console.print(f"[green]Output from {hostname}:[/green]\n{output}")
        else:
            sshmap_logger.display(
                f"[START] Executing command '{args.command}' on {args.hostname}."
            )
            await execute_command_on_host(
                args, args.hostname, local_hostname, credential_store, None
            )
    except Exception as e:
        sshmap_logger.error(f"An error occurred: {e}")
    finally:
        graph.close()


def main():
    parser = argparse.ArgumentParser(description="SSH Execute")
    parser.add_argument("--hostname", help="Hostname to execute commands on")
    parser.add_argument("--command", help="Command to execute")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Execute on all reachable hosts (default: only one)",
    )
    parser.add_argument(
        "--credentialspath",
        default="wordlists/credentials.csv",
        help="Path to CSV credentials file, will populate users and passwords",
    )
    parser.add_argument(
        "--debug", action="store_true", help="enable debug level information"
    )
    parser.add_argument("--verbose", action="store_true", help="enable verbose output")
    parser.add_argument(
        "--maxworkers",
        type=int,
        default=None,
        help="Number of concurrent workers when using --all (default: auto, up to 10)",
    )
    parser.add_argument(
        "--output", type=str, default="output", help="Path to output folder"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress all output of command execution"
    )
    parser.add_argument(
        "--no-store", action="store_true", help="Do not store the output to a file"
    )
    parser.add_argument(
        "--proxy",
        help="SOCKS5/HTTP proxy URL (e.g., socks5://127.0.0.1:9050)",
        default=None
    )
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Open an interactive shell on the remote host (ignores --command)"
    )
    parser.add_argument(
        "--pty",
        action="store_true",
        help="Force PTY allocation for command execution (auto-enabled for sudo commands)",
    )

    args = parser.parse_args()

    try:
        graph.driver.verify_connectivity()
    except Exception as e:
        sshmap_logger.error(
            f"Neo4J connectivity check failed, check if it is running: {e}"
        )
        return

    if args.shell and args.all:
        sshmap_logger.error("--shell cannot be used with --all. Please specify a single target with --hostname.")
        return

    if args.shell and not args.hostname:
        sshmap_logger.error("--shell requires --hostname.")
        return

    if not args.shell and not args.command:
         sshmap_logger.error("--command is required unless --shell is specified.")
         return

    asyncio.run(async_main(args))


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        # Fix for Windows Proactor loop shutdown issues
        import asyncio.windows_events

        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    main()
