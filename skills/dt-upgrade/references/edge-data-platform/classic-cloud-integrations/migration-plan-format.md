# Migration Plan Format (Mode A)

Specifies the structure of the Stage 3 Mode A migration plan document. Both the TypeScript library (`scripts/migration-lookup.ts`) and the model in DT Assist produce this shape.

The plan is a self-contained markdown file — the user executes changes independently without needing the tool again.

---

## Table of Contents

- [File naming](#file-naming)
- [Document structure](#document-structure)
- [Migration Blockers (conditional)](#migration-blockers-conditional)
- [Part 1: Classic → New Metric Key Reference (required)](#part-1-classic--new-metric-key-reference-required)
- [Part 2: Dashboard Remediation (required)](#part-2-dashboard-remediation-required)
- [Part 3: Metric Event Alert Remediation (required)](#part-3-metric-event-alert-remediation-required)
- [Part 3b: Notebook Remediation (conditional)](#part-3b-notebook-remediation-conditional)
- [Part 3c: Classic Dashboard Remediation (conditional)](#part-3c-classic-dashboard-remediation-conditional)
- [Part 3d: Anomaly Detector Remediation (conditional)](#part-3d-anomaly-detector-remediation-conditional)
- [Part 4: No-Match Keys — DQL Discovery (required)](#part-4-no-match-keys--dql-discovery-required)
- [DAC Coverage Gaps (conditional)](#dac-coverage-gaps-conditional)
- [Part 5: Cutover Checklist (required)](#part-5-cutover-checklist-required)
- [Implementation notes](#implementation-notes)

---

## File naming

```
cloud-migration-plan-<tenant-slug>-<YYYY-MM-DD>.md
```

Example: `cloud-migration-plan-acme-prod-2026-05-15.md`

---

## Document structure

```
# <Provider> Classic Connection — Migration Plan

Generated: <YYYY-MM-DD HH:MM UTC>
Environment: `<tenant URL>`
Scope: <PROVIDER> only | **<N> affected dashboards · <N> affected notebooks · <N> affected classic dashboards · <N> affected metric event alerts · <N> affected SLOs**

> **Availability legend:**
> - **recommended** — in the default collection set; no extra connection config needed
> - **autodiscovered** — set the new connection to *recommended + custom* and add this key as a custom metric
> - **no match** — no direct mapping; must use the DQL discovery query in Part 4

> **Alert migration:** Classic metric event alerts must be deleted and re-created (cannot be edited in place).
> Zero-gap strategy:
>
> 1. Create new alerts now (disabled) — before metric ingest is enabled.
> 2. When new connection begins ingesting data (confirmed by `dt.da.source`): simultaneously disable classic alerts and enable new ones.
> 3. After ≥ 7 days of stable operation: delete old classic alerts.

[--- Migration Blockers section (CONDITIONAL — only when blockers exist) ---]
[--- Part 1 (REQUIRED) ---]
[--- Part 2 (REQUIRED — show "none" message if 0 affected) ---]
[--- Part 3 (REQUIRED — show "none" message if 0 affected) ---]
[--- Part 3b: Notebooks (CONDITIONAL — only when notebooks > 0) ---]
[--- Part 3c: Classic Dashboards (CONDITIONAL — only when classic dashboards > 0) ---]
[--- Part 3d: Anomaly Detectors (CONDITIONAL — only when anomaly detectors > 0) ---]
[--- Part 4 (REQUIRED) ---]
[--- DAC Coverage Gaps (CONDITIONAL — only when gap_keys > 0) ---]
[--- Part 5 (REQUIRED) ---]
```

---

## Migration Blockers (conditional)

Include only when one or more assets have blockers.

```markdown
---

## ⛔ Migration Blockers

The following assets have blockers that prevent direct migration.
Resolve each blocker before migrating the asset.

**<Asset Name>** (`<asset_id>`)
  - Asset type: `<asset_type>`
  - Blockers: `<blocker_code>`, `<blocker_code>`
  - EoL service: `<resource_type>` retired <YYYY-MM-DD> — [announcement](<url>)
  - Metric Streams keys require a separate cutover process: `<key1>`, `<key2>` …
```

**Blocker codes:** `eol-service`, `metric-streams`.

---

## Part 1: Classic → New Metric Key Reference (required)

One sub-section per AWS/Azure service segment, sorted alphabetically. Skip `_alert`-suffix keys (they are classic-only artifacts; add a callout when present).

```markdown
---

## Part 1: Classic → New Metric Key Reference

### <SERVICE> (uppercase)

| Classic key | New DAC key | Availability |
|---|---|---|
| `<classic_key>` | `<new_dac_key>` | recommended |
| `<classic_key>` | `not-matched` | no match — must use DQL discovery (see [Part 4: No-Match Keys — DQL Discovery](#part-4-no-match-keys--dql-discovery-required)) |

> `_alert`-suffix key(s) detected (`<key1>`, `<key2>`).
> These are classic-only artifacts — **do not re-create** with new keys.
```

**Availability cell values:**
- `recommended` — metric is in the default collection set
- `autodiscovered` — metric requires custom metric configuration on the new connection
- `no match — must use DQL discovery` — no DAC entry; refer to [Part 4](#part-4-no-match-keys--dql-discovery-required)

---

## Part 2: Dashboard Remediation (required)

Show "No classic references found in any dashboard." when count is 0.

```markdown
---

## Part 2: Dashboard Remediation (<N> affected)

Open in Dynatrace UI → edit each tile → swap classic keys for new DAC keys from Part 1.
Or via CLI: `dtctl get dashboards <id> -o json` → edit `tile.query` → `dtctl apply`.

### <SERVICE> Dashboards

#### <Dashboard Name>

ID: `<dashboard_id>`

| Before (classic) | After (new DAC) | Availability |
|---|---|---|
| `<classic_key>` | `<new_key>` | recommended |

**Entity selector** `<selector>` → replace with `smartscapeNodes <TYPE>` filter
```

Dashboards are grouped by the service segment of their first affected metric key.

---

## Part 3: Metric Event Alert Remediation (required)

Show "No classic metric event alerts found." when count is 0.

```markdown
---

## Part 3: Metric Event Alert Remediation (<N> affected)

Navigate to: **Settings → Anomaly Detection → Metric Events**

All alerts must be deleted and re-created with new metric keys. See zero-gap strategy above.

### <SERVICE> Alerts

#### <Alert Name>

ID: `<alert_id>`

| Before (classic) | After (new DAC) | Availability |
|---|---|---|
| `<classic_key>` | `<new_key>` | recommended |
```

---

## Part 3b: Notebook Remediation (conditional)

Include only when notebooks with classic references were found.

```markdown
---

## Part 3b: Notebook Remediation (<N> affected)

Open each notebook in Dynatrace → edit code cells → swap classic metric keys for new DAC keys from Part 1.

#### <Notebook Name>

ID: `<notebook_id>`

| Before (classic) | After (new DAC) | Availability |
|---|---|---|
| `<classic_key>` | `<new_key>` | recommended |
```

---

## Part 3c: Classic Dashboard Remediation (conditional)

Include only when classic dashboards (Config API v1) with classic references were found.

```markdown
---

## Part 3c: Classic Dashboard Remediation (<N> affected)

Classic dashboards (Config API v1) cannot be edited in place for new metric keys.
Recommended: recreate each as a new platform dashboard referencing new DAC keys.

#### <Dashboard Name>

ID: `<dashboard_id>`

| Before (classic) | After (new DAC) | Availability |
|---|---|---|
| `<classic_key>` | `<new_key>` | recommended |
```

---

## Part 3d: Anomaly Detector Remediation (conditional)

Include only when anomaly detectors (custom alerts) with classic references were found.

```markdown
---

## Part 3d: Anomaly Detector Remediation (<N> affected)

Davis anomaly detectors referencing classic metrics must be reviewed and updated when the classic
connection is removed. Group them by analyzer type.

### Analyzer type: `<analyzer_type>` (<N> detector(s))

**<Detector Name>**
  Classic metric key(s): `<key1>`, `<key2>`
  Matching inputs: <N>

> **Action:** For each detector: (1) note the classic metric key(s) above,
> (2) find the new-connection equivalent in Part 1,
> (3) update the detector's metric selector after the new connection is active.
```

---

## Part 4: No-Match Keys — DQL Discovery (required)

Show "All detected classic metric keys have direct mappings. No DQL discovery needed." when no-match set is empty.

``````markdown
---

## Part 4: No-Match Keys — DQL Discovery

After the new connection is active, run these DQL queries to discover live new metric keys:

**<SERVICE>** (<N> key(s)): `<key1>`, `<key2>`

```dql
fetch metric.series, from:now()-1h
| filter startsWith(metric.key, "cloud.<provider>.<service>.") AND isNotNull(dt.da.source)
| summarize cnt=count(), by:{metric.key, dt.da.source}
```
``````

---

## DAC Coverage Gaps (conditional)

Include only when one or more keys returned `not-matched` from the DAC database (distinct from "no match" via fallback chain — this means the key was not found even after all 5 fallback steps).

```markdown
---

## § DAC Coverage Gaps

<N> metric key(s) had no DAC mapping entry. These services may have been added after the last
DAC data refresh or may use abbreviated classic key formats. Review manually:

- `<key1>`
- `<key2>`

> **Action:** Check `manual-metric-mappings.json` for known abbreviation mappings.
```

Cap the displayed list at 20 keys; note the remainder count.

---

## Part 5: Cutover Checklist (required)

```markdown
---

## Part 5: Cutover Checklist (Stage 4)

- [ ] **4a.** Create new connection(s) in topology-only mode (metric ingest disabled).
- [ ] **4b.** Validate Smartscape node counts match expected entity counts (Stage 1 queries).
- [ ] **4c.** Apply dashboard changes (Part 2). Create new alerts (Part 3) in *disabled* state.
- [ ] **4d.** Enable metric ingest. Validate `dt.da.source`. Disable classic alerts, enable new alerts simultaneously.
- [ ] **4e.** Disable classic connection(s) (do not delete). Re-run Stage 2 scan to confirm no remaining classic references.
- [ ] **4f.** Delete classic connection(s) after ≥1 week validation buffer.

> Autodiscovered metrics require the new connection configured with *recommended + custom* metric collection.
```

---

## Implementation notes

- **`_alert`-suffix keys** are never emitted as rows in mapping tables. They are classic-only artifacts; if detected, add the callout in Part 1. If an `_alert`-suffix key unexpectedly appears in a metric mapping result or database lookup: do **not** include it in the migration plan. Discard it — it is a classic-only artifact with no equivalent. Include only the primary key in the plan.
- **Service grouping** uses the service segment extracted from the classic key (e.g. `lambda` from `dt.cloud.aws.lambda.invocations`). Do not use simple string replacement — use `extractServiceSegment(key, provider)` from `scripts/migration-lookup.ts` (**REQUIRED**) to group findings by service. Reference `metric-key-mapping.md` (**reference only**) for understanding key format patterns.
- **Deduplication** within a section: if the same classic key appears in multiple tiles of the same dashboard, emit it once.
- **Availability cell formatting:** use the exact strings `recommended`, `autodiscovered`, `none`. Do not abbreviate. (When availability is `none`, use the DQL discovery instructions in Part 4.)
- **EOL annotation:** append ` ⚠ EOL (<YYYY-MM-DD>)` to the availability cell when `end_of_life` is true.
