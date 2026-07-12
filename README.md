# NAPALM-101 Network Automation Framework

A flexible, modular, and extensible Python-based network automation framework built on top of the **NAPALM** abstraction layer. It features a robust multi-vendor device inventory, modular task design, multi-threaded parallel execution, and an elegant command-line interface.

Designed using modern Python 3.14+ standards and powered by the fast **uv** dependency manager.

---

## Key Architectural Advantages

- **Modular Task Abstraction:** Actions (e.g., fetching facts, deploying configurations) are decoupled from the connection and execution engine. Adding a new automation action is as simple as creating a class extending `BaseTask`.
- **Intelligent Inventory Inheritance:** Device properties, credentials, and custom variables are defined within groups and automatically inherited by hosts, preventing configuration duplication while allowing fine-grained individual overrides.
- **Concurrent Execution Engine:** Built-in multi-threaded support allows tasks to be executed in parallel across hundreds of switches, significantly reducing run times compared to sequential runs.
- **Beautiful, High-Signal CLI:** Real-time feedback, detailed structured tabular outputs, and colorized differences using `rich` terminal formatting.

---

## Directory Structure

```text
napalm-101/
├── pyproject.toml             # Project & dependency definition (managed by uv)
├── inventory.yaml             # Multi-vendor device inventory (YAML)
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
│           └── configs.py     # Safe configuration merge/replace deployment
└── tests/
    ├── test_inventory.py     # Unit tests for inventory logic and overrides
    └── test_manager_tasks.py  # Moked unit tests for connection lifecycle and task runs
```

---

## Installation & Setup

Ensure you have [uv](https://github.com/astral-sh/uv) installed.

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

### 1. View Inventory
List all devices defined in `inventory.yaml` along with resolved IP addresses, drivers, groups, and variables:
```bash
uv run napalm-101 hosts
```

### 2. Retrieve Device Facts (Getters)
Fetch system facts (uptime, model, os version, hostname) using standard NAPALM getters:
```bash
# Run on all hosts (parallel by default)
uv run napalm-101 run-getter --getter get_facts

# Run on a specific host and show detailed, syntax-highlighted JSON data
uv run napalm-101 run-getter --host sw02-eos --getter get_facts

# Retrieve multiple getters (e.g. facts and IP interfaces)
uv run napalm-101 run-getter --group arista_eos --getter get_facts --getter get_interfaces_ip
```

### 3. Deploy Configurations (Dry-Run & Commit)
Push configuration changes to devices with transactional support:
```bash
# Perform a DRY-RUN and view a colorized configuration diff
uv run napalm-101 config-deploy backup_config.txt --group arista_eos --method merge

# Commit changes live to a device (on supported platforms)
uv run napalm-101 config-deploy backup_config.txt --host sw02-eos --method merge --commit
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

runner = TaskRunner("inventory.yaml")
hosts = runner.inventory.list_hosts(group="arista_eos")

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
