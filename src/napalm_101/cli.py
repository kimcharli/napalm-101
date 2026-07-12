import os
import yaml
from pathlib import Path
from typing import List, Optional
from datetime import datetime
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from napalm_101.core.inventory import Inventory
from napalm_101.tasks.base import TaskRunner
from napalm_101.tasks.getters import GettersTask
from napalm_101.tasks.configs import ConfigTask, BackupTask
from napalm_101.tasks.audits import StateAuditTask

app = typer.Typer(
    name="napalm-101",
    help="Flexible, vendor-agnostic network automation CLI using NAPALM.",
    add_completion=False,
)
console = Console()


@app.callback()
def main(
    ctx: typer.Context,
    env: str = typer.Option(
        None,
        "--env",
        "-e",
        envvar="NAPALM_ENV",
        help="Target environment (e.g. pslab, user1). Fallback defaults to 'pslab'.",
    ),
):
    """Global configuration callback to resolve environment context."""
    active_env = env or "pslab"
    env_dir = Path("environments") / active_env
    inventory_path = env_dir / "inventory.yaml"

    ctx.obj = {
        "env_name": active_env,
        "env_dir": env_dir,
        "inventory_path": inventory_path,
    }


def get_runner(ctx: typer.Context, inventory_path_override: Optional[Path] = None) -> TaskRunner:
    """Helper to locate inventory file and initialize runner."""
    path = inventory_path_override or ctx.obj["inventory_path"]
    
    if not path.exists():
        console.print(
            f"[red]Error:[/red] Inventory file not found at '{path}'. "
            f"Ensure the environment '{ctx.obj['env_name']}' is correctly initialized."
        )
        raise typer.Exit(code=1)
    return TaskRunner(str(path))


def load_env_config(env_dir: Path) -> dict:
    """Helper to load environment-specific config.yaml rules."""
    config_path = env_dir / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Failed to load configuration rules file '{config_path}': {e}")
    return {}


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
    ctx: typer.Context,
    inventory_path: Optional[Path] = typer.Option(
        None, "--inventory", "-i", help="Override path to inventory YAML file."
    ),
):
    """List all configured hosts and groups in the active environment's inventory."""
    runner = get_runner(ctx, inventory_path)
    
    table = Table(title=f"Inventory Hosts - Environment: {ctx.obj['env_name']}")
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
    ctx: typer.Context,
    getter: List[str] = typer.Option(
        ["get_facts"], "--getter", "-g", help="Getter name(s) to run (can be passed multiple times)."
    ),
    group: Optional[str] = typer.Option(None, "--group", "-grp", help="Filter by inventory group."),
    host: Optional[str] = typer.Option(None, "--host", "-H", help="Target a specific host."),
    parallel: bool = typer.Option(True, "--parallel/--sequential", help="Run tasks in parallel."),
    inventory_path: Optional[Path] = typer.Option(
        None, "--inventory", "-i", help="Override path to inventory YAML file."
    ),
):
    """Fetch operational data (getters) from devices."""
    runner = get_runner(ctx, inventory_path)

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

    console.print(f"Running getter task [blue]{getter}[/blue] on {len(target_hosts)} host(s) in [cyan]{ctx.obj['env_name']}[/cyan]...")
    
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
    ctx: typer.Context,
    config_file: Path = typer.Argument(..., help="Path to configuration file to load."),
    group: Optional[str] = typer.Option(None, "--group", "-grp", help="Filter by inventory group."),
    host: Optional[str] = typer.Option(None, "--host", "-H", help="Target a specific host."),
    method: str = typer.Option("merge", "--method", "-m", help="Load method: merge or replace."),
    commit: bool = typer.Option(False, "--commit", "-c", help="Actually commit changes instead of dry-run."),
    parallel: bool = typer.Option(True, "--parallel/--sequential", help="Run tasks in parallel."),
    inventory_path: Optional[Path] = typer.Option(
        None, "--inventory", "-i", help="Override path to inventory YAML file."
    ),
):
    """Deploy configuration changes onto devices (default dry-run)."""
    runner = get_runner(ctx, inventory_path)

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


@app.command()
def backup(
    ctx: typer.Context,
    group: Optional[str] = typer.Option(None, "--group", "-grp", help="Filter by inventory group."),
    host: Optional[str] = typer.Option(None, "--host", "-H", help="Target a specific host."),
    parallel: bool = typer.Option(True, "--parallel/--sequential", help="Run tasks in parallel."),
    inventory_path: Optional[Path] = typer.Option(
        None, "--inventory", "-i", help="Override path to inventory YAML file."
    ),
):
    """Backup active running configurations of devices into environment backups folder."""
    env_info = ctx.obj
    runner = get_runner(ctx, inventory_path)

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
        console.print("[yellow]Warning:[/yellow] No target hosts found for backup.")
        raise typer.Exit()

    # Resolve timestamp subfolder (minute-scale)
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    backup_dir = env_info["env_dir"] / "config" / "backups" / timestamp_str
    
    # Ensure folder structure is present
    backup_dir.mkdir(parents=True, exist_ok=True)

    console.print(
        f"Initiating running config backup for {len(target_hosts)} host(s) "
        f"in [cyan]{env_info['env_name']}[/cyan] environment..."
    )

    task = BackupTask()
    results = runner.run_on_hosts(
        hosts=target_hosts,
        task=task,
        parallel=parallel,
    )

    display_results(results)

    # Save successful configuration content to the resolved date-partitioned backup path
    saved_count = 0
    for h_name, res in results.items():
        if res.success and res.data:
            file_path = backup_dir / f"{h_name}.conf"
            try:
                file_path.write_text(res.data)
                console.print(f"💾 Saved backup: [green]{file_path}[/green]")
                saved_count += 1
            except Exception as e:
                console.print(f"[red]Error saving backup file for {h_name}:[/red] {e}")

    if saved_count > 0:
        console.print(f"\n[green]Success:[/green] Completed saving {saved_count} configuration backup(s) to [blue]{backup_dir}[/blue]")


@app.command()
def snapshot(
    ctx: typer.Context,
    group: Optional[str] = typer.Option(None, "--group", "-grp", help="Filter by inventory group."),
    host: Optional[str] = typer.Option(None, "--host", "-H", help="Target a specific host."),
    route: Optional[str] = typer.Option(None, "--route", "-r", help="Target destination IP to query route status. Overrides config.yaml."),
    parallel: bool = typer.Option(True, "--parallel/--sequential", help="Run tasks in parallel."),
    inventory_path: Optional[Path] = typer.Option(
        None, "--inventory", "-i", help="Override path to inventory YAML file."
    ),
):
    """Capture a unified network snapshot: concurrent configuration backups and operational state audits."""
    env_info = ctx.obj
    runner = get_runner(ctx, inventory_path)

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
        console.print("[yellow]Warning:[/yellow] No target hosts found for snapshot.")
        raise typer.Exit()

    # Load environment-specific config.yaml rules
    env_config = load_env_config(env_info["env_dir"])
    snapshot_rules = env_config.get("snapshot", {})

    # Resolve dynamic getters and route lookup destinations
    configured_getters = snapshot_rules.get("getters", None)
    route_destination = route or snapshot_rules.get("route_lookup_destination", "8.8.8.8")

    # Resolve minute-scale timestamp subfolder
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    snapshot_dir = env_info["env_dir"] / "snapshots" / timestamp_str
    configs_dir = snapshot_dir / "configs"
    states_dir = snapshot_dir / "states"

    # Ensure directories exist
    configs_dir.mkdir(parents=True, exist_ok=True)
    states_dir.mkdir(parents=True, exist_ok=True)

    console.print(
        f"\n📸 [bold blue]Initiating Unified Network Snapshot[/bold blue] ({len(target_hosts)} host(s)) "
        f"in [cyan]{env_info['env_name']}[/cyan] environment..."
    )
    console.print(f"📁 Destination directory: [yellow]{snapshot_dir}[/yellow]")
    if configured_getters:
        console.print(f"📝 Custom getters defined in config.yaml: [green]{configured_getters}[/green]")
    console.print(f"🎯 Route target resolved: [green]{route_destination}[/green]\n")

    # 1. Execute Config Backup Task
    console.print("[bold]Phase 1: Retrieving Running Configurations...[/bold]")
    backup_task = BackupTask()
    backup_results = runner.run_on_hosts(
        hosts=target_hosts,
        task=backup_task,
        parallel=parallel,
    )
    display_results(backup_results)

    # Save successful configs
    configs_saved = 0
    for h_name, res in backup_results.items():
        if res.success and res.data:
            file_path = configs_dir / f"{h_name}.conf"
            try:
                file_path.write_text(res.data)
                configs_saved += 1
            except Exception as e:
                console.print(f"[red]Error saving config for {h_name}:[/red] {e}")

    # 2. Execute State Audit Task
    console.print("\n[bold]Phase 2: Auditing Operational States (BGP, Interfaces, ARP, MAC, Routes)...[/bold]")
    audit_task = StateAuditTask()
    audit_results = runner.run_on_hosts(
        hosts=target_hosts,
        task=audit_task,
        parallel=parallel,
        getters=configured_getters,
        route_destination=route_destination,
    )
    display_results(audit_results)

    # Save successful states as JSON
    import json
    states_saved = 0
    for h_name, res in audit_results.items():
        if res.success and res.data:
            file_path = states_dir / f"{h_name}_state.json"
            try:
                with open(file_path, "w") as f:
                    json.dump(res.data, f, indent=2)
                states_saved += 1
            except Exception as e:
                console.print(f"[red]Error saving state audit for {h_name}:[/red] {e}")

    # Final summary
    console.print(f"\n[green]Success:[/green] Completed Unified Network Snapshot!")
    console.print(f"💾 Configurations saved : [green]{configs_saved}/{len(target_hosts)}[/green] in [yellow]{configs_dir}[/yellow]")
    console.print(f"📊 State audits saved  : [green]{states_saved}/{len(target_hosts)}[/green] in [yellow]{states_dir}[/yellow]")


if __name__ == "__main__":
    app()
