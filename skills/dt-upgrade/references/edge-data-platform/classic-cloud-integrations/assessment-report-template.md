# Assessment Report Template

Templates for the two outputs produced in Stage 2 Step 4.

---

## Table of Contents

- [1. Chat Summary](#1-chat-summary)
- [2. Detailed Report File](#2-detailed-report-file)

---

## 1. Chat Summary

Present this concise overview in the conversation:

```
## Classic Dependencies Found

- **Dashboards**: <count> affected (out of <total> scanned)
- **Metric Event Alerts**: <count> affected (out of <total> scanned)
- **Infrastructure Anomaly Detection**: <count> affected (AWS only)
- **Anomaly Detectors (Davis custom alerts)**: <count> affected (out of <total> scanned)
- **SLOs**: <count> affected (out of <total> scanned)

Note: Classic dashboards (Config API v1) are **not scannable** via `dtctl get dashboards` — they require a separate `DT_API_TOKEN` with `ReadConfig` scope. If `DT_API_TOKEN` is not exported (for example via `.dtmigration`), classic dashboards were not scanned. Recommend manual review of classic dashboards if any exist in the environment.
```

---

## 2. Detailed Report File

**Default:** write to a local markdown file named `cloud-migration-assessment.md`. **Alternative (DT Assist only):** create a Dynatrace Document using the platform document tool (no `dtctl`).

Use this structure:

```
## Cloud Migration Assessment — <environment name>

### Connection Inventory
| Provider | Account ID | Name | Migration Status | Migration Blocked     |
|----------|-----------|------|----------------|--------------------------|
| AWS      | 123456789 | prod | Parallel       | No                       |
| ...      |           |      |                | Yes (AWS Metric Streams) |

### Classic Dependencies Found
#### Dashboards (<count> affected)
- <dashboard name> (<id>) — patterns: dt.cloud.aws.ec2.*, fetch dt.entity.ec2_instance

#### Metric Event Alerts (<count> affected)
- <alert name> (<id>) — metric: dt.cloud.aws.lambda.invocations

#### Infrastructure Anomaly Detection (<count> affected)
- AWS Infrastructure Anomaly Detection (<objectId>) — classic AWS entity types monitored

#### Anomaly Detectors (Davis custom alerts) (<count> affected)
- <detector title> (<objectId>) — metrics: dt.cloud.aws.lambda.errors (in analyzer input: timeSeriesSelector)

#### SLOs (<count> affected)
- <SLO name> (<id>) — metric: builtin:cloud.aws.ec2.cpu.usage

### Out of Scope
- Classic dashboards (Config API v1) — not scannable via dtctl
```

For each affected asset, include: name, ID, owner (leave blank if unavailable from API — the Document Service does not always expose owner for all document types), and each classic reference detected with its location (tile name, metric key field, etc.).
