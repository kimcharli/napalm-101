# ADR-0002: Scalability Roadmap for High-Volume Configurations and Operational States

* **Status:** Proposed (Future Candidate / Roadmap)
* **Author:** Chang Hyun (Charlie) Kim
* **Date:** July 11, 2026
* **Decided By:** Architectural Consultation

---

## Context & Problem Statement

As the network automation framework (`napalm-101`) scales from a small lab of 8 devices to a large enterprise production network with hundreds or thousands of devices, storing configurations as flat-text files and operational states as separate JSON files within dated directories will introduce severe inefficiencies:
1. **Disk Storage Footprint:** Saving duplicate text configurations and redundant, key-heavy JSON structures on every run will quickly consume gigabytes of storage space.
2. **Querying & Analytical Performance:** Searching across thousands of flat JSON files to locate active network state (e.g., finding which switch port has a specific MAC or ARP IP address) requires slow, sequential file-system parsing.

---

## Proposed Scaling Candidates (Roadmap)

We have identified three core architectural candidates to scale the storage and querying pipelines:

### 1. Git-Backed Configuration Storage (Delta-Compression)
Instead of saving duplicate text-configuration backups in nested dated directories, we will transition to a single stable directory and commit configurations to an internal Git repository.
* **Why:** Git utilizes incredibly efficient delta-compression under the hood. It only stores the daily line differences (diffs), shrinking the disk footprint by up to 95% while natively preserving full configuration version control.

### 2. Dual-Storage Configuration Archiving (Text + Parquet)
For configurations at scale, we will implement a dual-storage pipeline. While raw flat-text configuration backups will still be saved to disk for standard, native device restoration procedures (e.g., `load override` in Junos), they will simultaneously be ingested as a raw text column inside a compressed Apache Parquet database file.
* **Why:** Storing configurations inside Parquet's columnar dictionary-encoding format compresses repetitive configurations by over 90% (e.g., shrinking 100MB of raw configs down to 5MB–10MB in Parquet).
* **Cross-Device Analytical Queries:** Storing raw text configurations alongside structured metadata (hostname, environment, timestamp) inside Parquet columns enables blazing-fast, serverless SQL querying using DuckDB natively in Python. It allows network teams to query all device configs instantly to:
  * Detect configuration drift and security compliance issues (e.g., find which switches are missing security timeouts).
  * Identify IP and subnet overlaps across the entire network footprint using standard SQL strings/regex.
  * Map fleet-wide peering topologies (e.g., listing BGP neighbors and AS configurations) in milliseconds.

### 3. Time-Series & Document Databases (PostgreSQL / TimescaleDB / MongoDB)
For active, real-time tracking, we will refactor our multi-threaded TaskRunner to stream-write (upsert) state dictionaries directly into a central database like TimescaleDB (PostgreSQL) or MongoDB.
* **Why:** This supports millisecond-scale indexing of MACs, IPs, and VLANs, enabling instant searches across the entire network footprint, as well as time-series trend analysis (e.g., tracking BGP peers flaps or port flapping counters over a 30-day window).

---

## Consequences

* **Clean Separation:** Operational snapshots can still be triggered locally by CLI, but the storage backend will dynamically direct data into either Git, Parquet, or PostgreSQL depending on environment scale.
* **Cost Efficiency:** Storage costs on local disks or cloud storage mounts remain minimal at high scale.
* **Actionable Telemetry:** Instantly turns unstructured text/JSON logs into indexable, queryable network intelligence databases.
