# ADR-0001: Multi-Environment Isolation and Unified Snapshot Architecture

* **Status:** Approved
* **Author:** Chang Hyun (Charlie) Kim
* **Date:** July 11, 2026
* **Decided By:** User Confirmation

---

## Context & Problem Statement

To operate network automation across distinct physical and virtual testing workspaces (e.g., `pslab` and `user1`), the framework required a scaling strategy that avoids inventory duplication, handles individual device overrides, and cleanly segregates runtime configuration backups and operational state data. 

Additionally, network operations require consistent, point-in-time snapshots capturing both device states (JSON) and configurations (Text) without polluting the source control repository with dynamic environment data.

---

## Decisions

### 1. Isolated Environment Folder Structure (Option A)
We chose to organize the codebase by grouping inventories and configuration metadata into dedicated, isolated boundaries under an `environments/` directory:
```text
environments/
├── pslab/
│   ├── inventory.yaml
│   └── config/ (and snapshots/)
└── user1/
    └── inventory.yaml
```
* **Rejected Alternative:** A flat directory structure splitting files strictly by type (e.g., all inventories under `inventories/` and all configs under `configs/`). Option A was chosen because it creates clean boundaries, enabling easy packaging, migration, or deletion of entire environment contexts.

### 2. Global CLI Environment Routing
We implemented an environment-routing mechanism inside our Typer CLI using Typer Context (`ctx.obj`).
* The CLI resolves the active environment context in a global callback, accepting either a global flag `--env` / `-e` or falling back to the `NAPALM_ENV` environment variable, defaulting to `pslab`.
* Paths for inventories and snapshot configurations are dynamically constructed at runtime based on this context.

### 3. Unified Network-Wide Snapshots
We replaced simple configuration-only backups with a unified, chronological **Network Snapshot** model.
* For any snapshot run, a minute-scale date directory is created: `environments/{env}/snapshots/YYYY-MM-DD_HH-MM/`.
* The folder contains two distinct subdirectories:
  * `configs/`: Stores flat-text running configuration backups (`{host}.conf`).
  * `states/`: Stores structured JSON operational state audits (`{host}_state.json`), including Interfaces status, Interface IPs, BGP Neighbors, ARP tables, MAC tables, and target route routing metrics.

### 4. Dynamic Capture Lists via YAML Config Rules
We chose to decouple the list of operational state metrics from the Python codebase.
* The CLI dynamically parses environment-specific `config.yaml` configuration rules at runtime.
* These rule files specify exactly what metrics to capture and what routing targets to query per environment, keeping the core task logic highly generic.

### 5. Custom Junos EVPN NETCONF Audits & Flattening
Since EVPN is not a standard, vendor-agnostic NAPALM getter, we implemented custom, Junos-specific operational audits:
* **Structured NETCONF RPC Retrieval**: The task directly accesses the underlying PyEZ engine to execute XML/JSON RPCs (`get-evpn-database-information` and `get-evpn-instance-information`) over NETCONF, passing positional format parameters (`{"format": "json"}`) to retrieve structured Python dictionaries natively.
* **Auto-Fallback to CLI**: If the device's firmware or RPC options are incompatible with PyEZ JSON rendering, the task automatically falls back to raw CLI screen-scraping over SSH, ensuring connection reliability.
* **Redundant Nesting Flattening**: We resolved to automatically detect and flatten Junos's redundant JSON top-level wrapping keys, mapping data natively to standard, dashed keys (`evpn-database-information` and `evpn-instance-information`).

### 6. CLI CLI Script Rename
We renamed our registered command-line script entrypoint from `napalm-101` to **`run`** inside `pyproject.toml` to maximize terminal efficiency, readability, and speed.

### 7. GitOps Security Enforcement
We configured `.gitignore` to strictly exclude all dynamic snapshots:
```ini
environments/*/snapshots/
```
* **Rationale:** Running configurations, ARP caches, and peer route lookup details contain sensitive operating details and passwords that should never be leaked into open-source Git repositories. Dynamic configuration assets are kept locally or stored in secure document vaults.

---

## Consequences

* **Modularity:** Adding a new environment (e.g., `staging`) is as simple as creating an `environments/staging/` folder with its own `inventory.yaml`.
* **Reliability:** Device operational states are safely fetched concurrently with retry logic. Any unsupported getter parameters on specific drivers (e.g., platform limitations on older switches) are safely captured as errors inside the JSON output without interrupting execution.
* **Tracking:** Network configurations are tracked dynamically on a minute-scale timestamp.
