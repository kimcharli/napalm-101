import os
from pathlib import Path
from typing import List, Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from napalm_101.core.inventory import Inventory
from napalm_101.tasks.base import TaskRunner
from napalm_101.tasks.getters import GettersTask
from napalm_101.tasks.configs import ConfigTask

app = typer.Typer(
    name="napalm-101",
    help="Flexible, vendor-agnostic network automation CLI using NAPALM.",
    add_completion=False,
)
console = Console()


def get_runner(inventory_path: Optional[Path]) -> TaskRunner:
    """Helper to locate inventory file and initialize runner."""
    path = inventory_path or Path("inventory.yaml")
    if not path.exists():
        # Fall back to root or relative
        path = Path(os.getcwd()) / "inventory.yaml"
        if not path.exists():
            console.print(
                f"[red]Error:[/red] Inventory file not found. "
                "Specify with --inventory or create 'inventory.yaml' in current directory."
            )
            raise typer.Exit(code=1)
    return TaskRunner(str(path))


def display_results(results: dict):
    """Utility to print results in a beautiful rich table."""
    table = Table(title="Execution Results", show_lines=True)
    table.add_column("Host", style="cyan", no_wrap=True)
    table.add_column("Task", style="magenta")
    table.add_column("Status", style="bold")
    table.add_column("Duration (s)", justify="right")
    table.add_column("Message / Data Summary")

    for host_name, result in results.items():
        if result.success:
            status_str = "[green]SUCCESS[/green]"
            
            # Formulate a clean summary of returned data
            if isinstance(result.data, dict):
                if len(result.data) == 1:
                    # Single top-level key (e.g. getter name)
                    key = list(result.data.keys())[0]
                    val = result.data[key]
                    if isinstance(val, dict):
                        summary = f"{key}: {list(val.keys())[:5]}... ({len(val)} items)"
                    else:
                        summary = f"{key}: {str(val)[:80]}"
                else:
                    summary = f"Dict with keys: {list(result.data.keys())}"
            else:
                summary = str(result.data)[:120] + ("..." if len(str(result.data)) > 120 else "")
        else:
            status_str = "[red]FAILED[/red]"
            summary = f"[red]{result.error}[/red]"

        table.add_row(
            host_name,
            result.task_name,
            status_str,
            f"{result.elapsed_seconds:.3f}",
            summary,
        )

    console.print(table)


@app.command()
def hosts(
    inventory_path: Optional[Path] = typer.Option(
        None, "--inventory", "-i", help="Path to inventory YAML file."
    ),
):
    """List all configured hosts and groups in the inventory."""
    runner = get_runner(inventory_path)
    
    table = Table(title="Inventory Hosts")
    table.add_column("Host Name", style="cyan")
    table.add_column("IP / Hostname", style="green")
    table.add_column("Driver", style="magenta")
    table.add_column("Username", style="yellow")
    table.add_column("Groups")
    table.add_column("Variables")

    for host in runner.inventory.hosts.values():
        table.add_row(
            host.name,
            host.hostname,
            host.driver,
            host.username,
            ", ".join(host.groups) if host.groups else "-",
            str(host.vars) if host.vars else "-",
        )

    console.print(table)


@app.command()
def run_getter(
    getter: List[str] = typer.Option(
        ["get_facts"], "--getter", "-g", help="Getter name(s) to run (can be passed multiple times)."
    ),
    group: Optional[str] = typer.Option(None, "--group", "-grp", help="Filter by inventory group."),
    host: Optional[str] = typer.Option(None, "--host", "-H", help="Target a specific host."),
    parallel: bool = typer.Option(True, "--parallel/--sequential", help="Run tasks in parallel."),
    inventory_path: Optional[Path] = typer.Option(
        None, "--inventory", "-i", help="Path to inventory YAML file."
    ),
):
    """Fetch operational data (getters) from devices."""
    runner = get_runner(inventory_path)

    # Resolve target hosts
    if host:
        try:
            target_hosts = [runner.inventory.get_host(host)]
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1)
    elif group:
        target_hosts = runner.inventory.list_hosts(group=group)
        if not target_hosts:
            console.print(f"[yellow]Warning:[/yellow] No hosts found in group '{group}'")
            raise typer.Exit()
    else:
        target_hosts = list(runner.inventory.hosts.values())
        if not target_hosts:
            console.print("[yellow]Warning:[/yellow] No hosts found in inventory.")
            raise typer.Exit()

    console.print(f"Running getter task [blue]{getter}[/blue] on {len(target_hosts)} host(s)...")
    
    task = GettersTask()
    results = runner.run_on_hosts(
        hosts=target_hosts,
        task=task,
        parallel=parallel,
        getters=getter,
    )

    display_results(results)

    # Let user inspect detailed JSON data for success tasks if single host was requested
    if len(target_hosts) == 1 and results:
        res = list(results.values())[0]
        if res.success:
            import json
            console.print("\n[bold]Detailed Data Output:[/bold]")
            json_str = json.dumps(res.data, indent=2)
            console.print(Syntax(json_str, "json", theme="monokai", word_wrap=True))


@app.command()
def config_deploy(
    config_file: Path = typer.Argument(..., help="Path to configuration file to load."),
    group: Optional[str] = typer.Option(None, "--group", "-grp", help="Filter by inventory group."),
    host: Optional[str] = typer.Option(None, "--host", "-H", help="Target a specific host."),
    method: str = typer.Option("merge", "--method", "-m", help="Load method: merge or replace."),
    commit: bool = typer.Option(False, "--commit", "-c", help="Actually commit changes instead of dry-run."),
    parallel: bool = typer.Option(True, "--parallel/--sequential", help="Run tasks in parallel."),
    inventory_path: Optional[Path] = typer.Option(
        None, "--inventory", "-i", help="Path to inventory YAML file."
    ),
):
    """Deploy configuration changes onto devices (default dry-run)."""
    runner = get_runner(inventory_path)

    # Ensure config file exists
    if not config_file.exists():
        console.print(f"[red]Error:[/red] Configuration file not found: {config_file}")
        raise typer.Exit(code=1)

    # Resolve target hosts
    if host:
        try:
            target_hosts = [runner.inventory.get_host(host)]
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1)
    elif group:
        target_hosts = runner.inventory.list_hosts(group=group)
    else:
        target_hosts = list(runner.inventory.hosts.values())

    if not target_hosts:
        console.print("[red]Error:[/red] No targets selected.")
        raise typer.Exit(code=1)

    mode_str = "[bold yellow]DRY-RUN (No Changes Committed)[/bold yellow]" if not commit else "[bold red]LIVE DEPLOYMENT (Changes will be committed)[/bold red]"
    console.print(f"Deploying configuration [blue]{config_file}[/blue] ({method}) on {len(target_hosts)} host(s)... Mode: {mode_str}")

    task = ConfigTask()
    results = runner.run_on_hosts(
        hosts=target_hosts,
        task=task,
        parallel=parallel,
        config_file=str(config_file),
        method=method,
        dry_run=not commit,
    )

    # Display execution table
    display_results(results)

    # Display diffs for each host
    for h_name, res in results.items():
        if res.success and res.data:
            diff = res.data.get("diff")
            if diff:
                console.print(Panel(
                    Syntax(diff, "diff", theme="monokai", word_wrap=True),
                    title=f"Configuration Diff - {h_name}",
                    expand=False,
                ))
            else:
                console.print(f"[green]Info:[/green] No changes needed for {h_name}.")


if __name__ == "__main__":
    app()
