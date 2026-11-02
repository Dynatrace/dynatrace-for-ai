# Stage Output Contract

Specifies the single document that grows across all four migration stages. Every stage appends one section to it; the document is both human-readable and machine-parseable. Both the TypeScript library (target) and the model in DT Assist write to this shape. The Python scripts (transitional) are expected to align to it.

The **REQUIRED** JSON schema is in [`stage-output.schema.json`](stage-output.schema.json) — validate the document front-matter against it before writing.

---

## Document Lifecycle

1. **Stage 1** creates the file and writes the front-matter manifest + the Discovery section.
2. **Stages 2–4** open the existing file, update the manifest (`stages_completed`, `stages_in_progress`), and append the next section.
3. **Resume**: if a session resumes mid-migration, the model reads the file, finds `stages_completed` in the manifest, and continues from the next stage. No re-running completed work.

### File naming

```
cloud-migration-<tenant-slug>-<YYYY-MM-DD>.md
```

Example: `cloud-migration-acme-prod-2026-05-15.md`

Place the file in the working directory (or a Dynatrace Document when running in DT Assist). It is the primary artifact of the migration run — keep it until cutover is complete and signed off.

---

## Document Structure

### Front-matter manifest

Every document starts with a YAML front-matter block. Update the manifest in-place when stage status changes (do not append a second block).

```yaml
---
contract_version: 1
run_id: <ISO-8601 timestamp of Stage 1 start>-<tenant-slug>
tenant: <tenant URL, e.g. acme-prod.live.dynatrace.com>
providers: [aws, azure, gcp]              # subset discovered in Stage 1
stages_completed: []                       # add stage name when section is complete
stages_in_progress: [discovery]            # one entry; remove when completed
skill_version: <semver from SKILL.md>
---
```

Valid stage names for `stages_completed` / `stages_in_progress`: `discovery`, `assessment`, `guidance`, `cutover`.

**Conflict resolution:** If the same stage name appears in both `stages_completed` and `stages_in_progress`, treat `stages_in_progress` as authoritative — that stage is in progress, not complete. Remove it from `stages_completed` and resume from that stage.

---

### Stage 1 — Discovery

Append after the front-matter.

```markdown
## Stage 1 — Discovery & Classification

**Completed:** <ISO-8601 timestamp>

### Inputs

Queries run from `discovery-queries.md` (window: `from:now()-12h`).

### Connection Inventory

| Provider | Account ID | Name | Status | Blocked |
|----------|------------|------|--------|---------|
| AWS | 123456789012 | prod-main | Parallel | No |
| AWS | 987654321098 | staging | Not Started | Yes (Metric Streams) |
| Azure | My Subscription | My Subscription | Parallel | No |
| GCP | my-gcp-project | my-gcp-project | Not Started | No |

**Status values:** `Not Started` · `Parallel` · `Complete`
**Blocked** = `Yes (Metric Streams)` when an AWS account has both a classic connection and active Metric Streams traffic.

### Summary

- **<N> connection(s) Not Started** — migration has not begun
- **<N> connection(s) Parallel** — running classic + new simultaneously; ready to cut over
- **<N> connection(s) Complete** — new connection only

### Next Steps

- Providers in scope for Stage 2: [aws, azure, gcp] (or subset chosen by user)
- Asset types to scan: [dashboards, alerts, slos] (or subset chosen by user)
```

---

### Stage 2 — Assessment

```markdown
## Stage 2 — Dependency Assessment

**Completed:** <ISO-8601 timestamp>
**Scope:** providers=[aws, azure], assets=[dashboards, metric-events, slos, anomaly-detectors]

### Inputs

Asset files fetched from Dynatrace environment (or read from `./assessment/` in IDE mode):
- `dashboards-details.json` — <N> dashboards
- `metric-events.json` — <N> metric event alerts
- `slos.json` — <N> SLOs
- `infrastructure-detection.json` — <N> infrastructure anomaly detection objects
- `davis-anomaly-detectors.json` — <N> anomaly detectors
Detection rules applied from `classic-detection-patterns.json`.

Disambiguation applied per `disambiguation.md`.

### Findings

#### Dashboards (<N> affected of <total> scanned)

- **<Dashboard Name>** (`<id>`) [AWS] — metrics: `dt.cloud.aws.lambda.invocations`, `ext:cloud.aws.ec2.cpu`; entities: `fetch dt.entity.ec2_instance`
- *(no classic references found)* — when count is 0

#### Metric Event Alerts (<N> affected of <total> scanned)

- **<Alert Name>** (`<id>`) [AWS] — metric: `builtin:cloud.aws.rds.freeStorageSpace`

#### Infrastructure Anomaly Detection (<N> affected)

- **AWS Infrastructure** (`<objectId>`) [AWS] — classic AWS entity types present; no manual migration required (auto-managed)

#### Anomaly Detectors (<N> affected of <total> scanned)

- **<Detector Name>** (`<objectId>`) [Azure] — metric: `cloud.azure.microsoft_sql_servers.connection_failed`

#### SLOs (<N> affected of <total> scanned)

- **<SLO Name>** (`<id>`) [GCP] — metric: `dt.cloud.gcp.gce_instance.cpu.utilization`

### Disambiguation Results

List any ambiguous `cloud.<provider>.*` keys that were resolved via live DQL probes:

| Key | Resolution | Source |
|-----|------------|--------|
| `cloud.aws.ec2.cpuUtilization` | classic | no `dt.da.source` present in last 1h |
| `cloud.aws.lambda.invocations` | new | `dt.da.source = aws-metric-poller` |

### GCP Coverage Note

*(Include this section IF all three conditions are true:
1. GCP provider was in scope for Stage 2
2. At least one GCP classic metric or entity reference was detected
3. At least one detected GCP key has no confirmed new-connection mapping

If any condition is false, omit this section entirely.)*

> GCP metric mapping database is not yet complete. The following GCP metric key(s) have no confirmed new-connection equivalent and require manual lookup: `<key1>`, `<key2>`. Consult `gcp-new.md`.

### Next Steps

- <N> assets need migration guidance (Stage 3)
- Mode: Report Only / Guided Execution (user's choice)
- Granularity: one at a time / by type / all at once (user's choice)
```

---

### Stage 3 — Guidance

```markdown
## Stage 3 — Migration Guidance

**Completed:** <ISO-8601 timestamp>
**Mode:** Report Only / Guided Execution
**Provider:** aws / azure / gcp / all

### Mapping Summary

| Classic key | New DAC key | Availability | EOL |
|-------------|-------------|--------------|-----|
| `dt.cloud.aws.lambda.invocations` | `cloud.aws.Lambda.Invocations.By.FunctionName` | recommended | No |
| `ext:cloud.aws.ec2.cpu` | `cloud.aws.EC2.CPUUtilization.By.InstanceId` | recommended | No |
| `cloud.aws.exotic.someMetric` | `not-matched` | none | No |

**Availability values:** `recommended` · `autodiscovered` · `none` (use DQL discovery)

### Migration Plan

*(See [`cloud-migration-plan-<tenant>-<date>.md`](cloud-migration-plan-acme-prod-2026-05-15.md) for the full Mode A plan. Structure defined in [`references/migration-plan-format.md`](migration-plan-format.md).)*

Or inline the plan here when operating in DT Assist without a filesystem.

### Unresolved Keys

| Key | Reason |
|-----|--------|
| `cloud.aws.exotic.someMetric` | Not in DAC database — use DQL discovery query |

### Next Steps

- Apply dashboard changes (N dashboards)
- Re-create N metric event alerts (zero-gap strategy)
- Re-create N SLOs
- Proceed to Stage 4 when all assets are migrated
```

---

### Stage 4 — Cutover

```markdown
## Stage 4 — Cutover & Validation

**Completed:** <ISO-8601 timestamp>
**Provider:** aws / azure / gcp / all

### Steps Completed

- [x] **4a** — New connection(s) created in topology-only mode
- [x] **4b** — Smartscape node counts validated: expected <N>, found <N>
- [x] **4c** — Asset migration applied (dashboards updated, new alerts created disabled)
- [x] **4d** — Metric ingest enabled; `dt.da.source` validated; classic alerts disabled, new alerts enabled
- [x] **4e** — Classic connection(s) disabled; Stage 2 re-scan confirmed no remaining classic references
- [ ] **4f** — Classic connection(s) deleted (after ≥1 week validation buffer)

### Validation Queries Run

*(Record DQL queries used for validation and their results.)*

| Query | Result |
|-------|--------|
| Smartscape node count (AWS) | 12 nodes — matches Stage 1 expected |
| `dt.da.source` spot-check | `aws-metric-poller` confirmed on all new metrics |
| Stage 2 re-scan | 0 classic references remaining |

### Residual Classic Traffic

*(Leave blank if none. Populate if classic metrics were still detected after 4e.)*

### Sign-off

**Status:** `pending` / `approved` / `rolled-back`

*(Set to `approved` when all checklist items are complete and validation passes.)*
```

---

## Machine-readable conventions

- Use ISO-8601 timestamps everywhere (`2026-05-15T14:23:07Z`).
- Asset IDs in backticks.
- Status values are exactly as specified (case-sensitive in the JSON schema): `Not Started`, `Parallel`, `Complete`.
- Availability values: `recommended`, `autodiscovered`, `none`.
- Sign-off values: `pending`, `approved`, `rolled-back`.
- The JSON schema validates the front-matter manifest and the summary counts; the markdown body is free-form but must follow the section heading structure (`## Stage N — <Name>`).
