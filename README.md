# NAPALM-101 Network Automation Framework

A flexible, modular, and extensible Python-based network automation framework built on top of the **NAPALM** abstraction layer. It features a robust multi-vendor device inventory, modular task design, multi-threaded parallel execution, and an elegant command-line interface.

Designed using modern Python 3.14+ standards and powered by the fast **uv** dependency manager.

---

## Key Architectural Advantages

- **Modular Task Abstraction:** Actions (e.g., fetching facts, deploying configurations, running backups) are decoupled from the connection and execution engine. Adding a new automation action is as simple as creating a class extending `BaseTask`.
- **Multi-Environment Architecture:** Isolates inventories and configs under dedicated environment boundary subdirectories (e.g., `environments/pslab/`, `environments/user1/`), dynamically switched via CLI flags or OS variables.
- **Dynamic Capture Rules via YAML:** Decouples what metrics and route targets to capture during audits from the Python codebase, delegating control to environment-specific `config.yaml` rule files.
- **Custom Junos EVPN structured audits:** Integrates custom EVPN operational database audits natively using NETCONF XML/JSON RPCs over PyEZ, with automatic redundant nesting flattening and CLI text fallbacks.
- **Intelligent Inventory Inheritance:** Device properties, credentials, and custom variables are defined within groups and automatically inherited by hosts, preventing configuration duplication while allowing fine-grained individual overrides.
- **Concurrent Execution Engine:** Built-in multi-threaded support allows tasks to be executed in parallel across hundreds of switches, significantly reducing run times compared to sequential runs.
- **Beautiful, High-Signal CLI:** Real-time feedback, detailed structured tabular outputs, and colorized differences using `rich` terminal formatting.

---

## Directory Structure

```text
napalm-101/
├── pyproject.toml             # Project & dependency definition (managed by uv)
├── mise.toml                  # Local environment runtime definitions (mise)
├── environments/
│   ├── pslab/                 # Default laboratory environment
│   │   ├── inventory.yaml     # Pslab host targets and shared credentials
│   │   ├── config.yaml        # Environmental snapshot and capture rules
│   │   └── snapshots/         # Unified, point-in-time snapshots (Git ignored)
│   │       └── 2026-07-11_23-28/
│   │           ├── configs/   # Text configuration backups (.conf)
│   │           └── states/    # Structured operational state audits (.json)
│   └── user1/                 # User1 sandbox network environment
│       ├── inventory.yaml     # User1 host targets and specific credentials
│       └── config.yaml        # User1 snapshot and capture rules
├── src/
│   └── napalm_101/
│       ├── __init__.py        # Public API exposure
│       ├── cli.py             # Rich CLI interface (Typer)
│       ├── core/
│       │   ├── exceptions.py  # Structured custom exceptions
│       │   ├── inventory.py   # Pydantic schema validation & group inheritance
│       │   └── manager.py     # NAPALM driver session lifecycle manager
│       └── tasks/
│           ├── base.py        # BaseTask and multi-threaded TaskRunner
│           ├── getters.py     # Dynamic operational state retriever
│           ├── configs.py     # Safe config merge/replace & BackupTask
│           └── audits.py      # Custom dynamic state audits (BGP, MAC, EVPN, etc.)
└── tests/
    ├── test_inventory.py     # Unit tests for inventory logic and overrides
    └── test_manager_tasks.py  # Mocked unit tests for connection, configurations, and audits
```

---

## Installation & Setup

Ensure you have [uv](https://github.com/astral-sh/uv) and [mise](https://github.com/jdx/mise) installed.

1. **Clone and enter the workspace:**
   ```bash
   cd napalm-101
   ```

2. **Sync dependencies and create virtual environment:**
   ```bash
   uv sync
   ```

3. **Run the test suite:**
   Verify that all components are fully operational:
   ```bash
   uv run pytest
   ```

---

## Getting Started

The entrypoint script is registered as **`run`** under uv.

### 1. View Inventory
List all devices defined in the active environment's inventory:
```bash
# Views default (pslab) environment
uv run run hosts

# View user1 environment using the global flag
uv run run --env user1 hosts

# View user1 environment using an OS environment variable
export NAPALM_ENV=user1
uv run run hosts
```

### 2. Retrieve Device Facts (Getters)
Fetch system facts (uptime, model, os version, hostname) using standard NAPALM getters:
```bash
# Run on all hosts (parallel by default) in the default environment
uv run run run-getter --getter get_facts

# Run on a specific host and show detailed, syntax-highlighted JSON data
uv run run run-getter --host pslab-qfx14 --getter get_facts

# Retrieve multiple getters (e.g. facts and IP interfaces)
uv run run run-getter --group qfx5100 --getter get_facts --getter get_interfaces_ip
```

### 3. Capture Unified Network Snapshots (Configs + States)
Capture a unified, point-in-time network-wide snapshot. This runs Phase 1 (Configuration Backups) and Phase 2 (State Audits) concurrently across devices:
```bash
# Snapshot all devices in parallel
uv run run snapshot

# Snapshot a specific device
uv run run snapshot --host pslab-qfx14

# Query a custom route lookup destination (overriding config.yaml)
uv run run snapshot --host pslab-qfx14 --route 1.1.1.1
```
*Snapshots are saved under the minute-scale date directory `environments/{env}/snapshots/YYYY-MM-DD_HH-MM/` inside `configs/` and `states/` subdirectories. They are automatically ignored in Git to prevent sensitive operating data leaks.*

### 4. Backup Running Configurations (Only Configs)
If you only want to save the flat-text running configuration without operational state audits:
```bash
uv run run backup
```
*Backups are saved to `environments/{env}/config/backups/YYYY-MM-DD_HH-MM/`.*

### 5. Deploy Configurations (Dry-Run & Commit)
Push configuration changes to devices with transactional support:
```bash
# Perform a DRY-RUN and view a colorized configuration diff
uv run run config-deploy candidate_config.txt --group qfx5100 --method merge

# Commit changes live to a device (on supported platforms)
uv run run config-deploy candidate_config.txt --host pslab-qfx14 --method merge --commit
```

---

## Writing Custom Tasks

To add a new automation task, subclass `BaseTask` and implement the `run` method:

```python
from typing import Any
from napalm_101.tasks.base import BaseTask

class PingTask(BaseTask):
    @property
    def name(self) -> str:
        return "PingTask"

    def run(self, device: Any, **kwargs) -> Any:
        # device is the connected NAPALM driver instance
        destination = kwargs.get("destination", "8.8.8.8")
        return device.ping(destination=destination)
```

Run your custom task across hosts using the `TaskRunner`:

```python
from napalm_101.tasks.base import TaskRunner

runner = TaskRunner("environments/pslab/inventory.yaml")
hosts = runner.inventory.list_hosts(group="qfx5100")

results = runner.run_on_hosts(
    hosts=hosts,
    task=PingTask(),
    destination="1.1.1.1"
)

for host, result in results.items():
    if result.success:
        print(f"{host} ping successful: {result.data}")
    else:
        print(f"{host} failed: {result.error}")
```
