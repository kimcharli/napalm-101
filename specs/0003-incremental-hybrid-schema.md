# ADR-0003: Incremental Hybrid Schema Architecture for Large-Scale Network Configuration Audits

* **Status:** Approved
* **Author:** Chang Hyun (Charlie) Kim
* **Date:** July 11, 2026
* **Decided By:** Architectural Consultation

---

## Context & Problem Statement

To design a high-performance, cost-effective data backend for an AI agent tasked with auditing, analyzing, and modifying Junos configurations across a large-scale network (hundreds of devices, 10,000+ lines per configuration).

Passing raw text or deep, unindexed hierarchical JSON strings directly to an LLM context window causes context window exhaustion and high token API costs ("token bankruptcy"). Conversely, trying to upfront-map the entire, volatile Junos configuration tree into a rigid relational database schema stalls development and breaks frequently across Junos OS upgrades.

---

## Decision

We will implement an **Incremental Hybrid Schema Architecture** using **Parquet** as the columnar storage format and **DuckDB** as the analytical query engine, exposed to the AI agent via the **Model Context Protocol (MCP)**.

Instead of an all-or-nothing schema, we will extract a highly optimized **Core Schema** for high-frequency global filtering and routing context, while burying the rest of the hierarchical structure inside an **Opaque JSON Column** (`raw_config_json`). Fields will be incrementally "promoted" from the opaque blob to explicit database columns as new AI agent use cases dictate.

---

## Technical Specification

### 1. Data Pipeline & Storage Format

* **Ingestion:** Configurations are fetched from devices natively in JSON format via Juniper PyEZ / XML RPC (`show configuration | display json`).
* **Storage:** Extracted data is saved into Apache Parquet files organized by date or site partition (e.g., `data/site=boston/export_date=2026-07-12.parquet`). Columnar dictionary encoding will minimize the footprint of repetitive configuration keys.
* **Query Engine:** DuckDB will run in-process within the MCP server layer to execute analytical SQL queries over the Parquet files.

### 2. Base Schema Baseline (Phase 1)

The initial Parquet dataset must contain the following structural pillars:

```sql
CREATE TABLE network_inventory (
    -- Metadata Core (For global indexing & discovery)
    hostname         VARCHAR NOT NULL,
    site             VARCHAR NOT NULL,
    model            VARCHAR,
    os_version       VARCHAR,
    last_booted      TIMESTAMP,
    
    -- Network Topology Core (High-frequency filter keys)
    management_ip    VARCHAR,
    
    -- The Opaque Safety Net (Unstructured JSON backup)
    raw_config_json  JSON NOT NULL
);
```

### 3. AI Agent Interfacing via MCP

The MCP server will expose a deterministic tool called `query_network_state`. The LLM will use this tool by writing standard SQL.

* **Example Agent Global Scope Query:**
```sql
-- High-speed columnar filter over millions of rows
SELECT hostname, raw_config_json->'protocols'->'bgp' AS bgp_payload
FROM network_inventory
WHERE site = 'boston';
```

*Result:* DuckDB filters the target down to only the Boston routers instantly, pulling just the BGP JSON fragment for those 5 devices. The LLM context window never sees the other 295 devices.

---

## Incremental Evolution & Promotion Lifecycle

To prevent schema bloat, a configuration stanza is only promoted from the opaque JSON column to a dedicated relational Parquet column when it meets the **Field Promotion Criteria**:

```
                       [ Field in raw_config_json ]
                                    │
                       Is it used in WHERE clauses 
                       for global filtering?
                                   / \
                                 YES  NO
                                 /     \
                [ PROMOTE TO COLUMN ]   \
                                     Is it used for math/counting
                                     (e.g., prefix limits, MTUs)?
                                         / \
                                       YES  NO
                                       /     \
                      [ PROMOTE TO COLUMN ]  [ LEAVE OPAQUE ]
```

### Process for Field Promotion:

1. **Alter Schema:** Execute an `ALTER TABLE network_inventory ADD COLUMN new_field TYPE;` inside the analytical pipeline.
2. **Update Ingestion Pipeline:** Modify the background Python parser script to pluck the new JSON key path and write it straight to the new column during the next sync.
3. **Simplify Agent Prompts:** Update the MCP tool description so the LLM agent knows it can query `WHERE new_field = x` directly instead of writing nested extraction paths (`->>`).

---

## Consequences

### Positive

* **Token Guardrails:** Protects against context window exhaustion by ensuring the LLM agent only reviews precise, relevant slices of configuration data.
* **Agility:** Avoids upfront data modeling gridlock. The engineering team can ship an agent targeting basic system configurations on day one.
* **Deterministic Math:** Aggregations (e.g., counting configured interfaces) are handled perfectly by DuckDB, eliminating LLM counting hallucinations.

### Negative / Risks & Mitigations

* **SQL Generation Drift:** The LLM must be well-prompted with the exact schema definitions so it doesn't try to guess or generate invalid JSON path operators against the `raw_config_json` blob.
* **Junos JSON Typology Variations:** Junos lists singleton objects differently than lists (e.g. a single BGP peer is parsed as a dictionary, but multiple peers are parsed as a list). *Mitigation:* Ensure MCP tool prompts provide robust SQL JSON extract examples using `json_transform` or `json_extract_string` to normalize array schemas.
* **Data Refresh Latency:** Changes made to a live router config are not instantly reflected in the Parquet files until the next synchronization cycle. *Mitigation:* Support explicit, agent-triggered atomic sync triggers for active devices during configuration modify jobs.
