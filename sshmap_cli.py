import argparse
from rich.console import Console
from rich.panel import Panel
from modules.config import CONFIG
from modules.graphdb import GraphDB

console = Console()


def print_detailed_path(path, index=None):
    steps = []
    for src, meta, dst in path:
        segment = (
            f"[bold]{src}[/bold] ──▶ [bold]{dst}[/bold]\n"
            f"[blue]user:[/blue] {meta['user']}   "
            f"[blue]method:[/blue] {meta['method']}   "
            f"[blue]creds:[/blue] {meta['creds']}\n"
            f"[blue]IP:[/blue] {meta['ip']}   "
            f"[blue]port:[/blue] {meta['port']}"
        )
        steps.append(segment)
    title = (
        "[green]Shortest SSH Path[/green]"
        if index is None
        else f"[green]Path #{index + 1}[/green]"
    )
    console.print(Panel.fit("\n\n".join(steps), title=title))


def main():
    parser = argparse.ArgumentParser(description="SSH Path Visualizer")
    parser.add_argument("start", help="Starting hostname")
    parser.add_argument("end", help="Target hostname")
    parser.add_argument(
        "--all", action="store_true", help="Show all paths (default: only one)"
    )
    parser.add_argument(
        "--max-depth", type=int, default=5, help="Max path depth (for --all)"
    )
    parser.add_argument(
        "--write-config", action="store_true", help="Write SSH config file to /tmp"
    )
    parser.add_argument(
        "--method",
        choices=["proxyjump", "proxycommand"],
        default="proxyjump",
        help="SSH config method",
    )

    args = parser.parse_args()

    db = GraphDB(CONFIG["neo4j_uri"], CONFIG["neo4j_user"], CONFIG["neo4j_pass"])

    try:
        if args.all:
            paths = db.find_all_paths_to(args.start, args.end, args.max_depth)
            if not paths:
                console.print("[red]No paths found.[/red]")
            for i, path in enumerate(paths):
                print_detailed_path(path, i)
        else:
            path = db.find_path(args.start, args.end)
            if not path:
                console.print("[red]No path found.[/red]")
            else:
                print_detailed_path(path)
                if args.write_config:
                    config_path = db.write_ssh_config_for_path(
                        args.start, args.end, method=args.method
                    )
                    if config_path:
                        console.print(
                            f"[green]SSH config written to[/green] {config_path}"
                        )
                        console.print(
                            f"[yellow]Usage:[/yellow] ssh -F {config_path} target"
                        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
