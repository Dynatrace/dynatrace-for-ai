# Classic Cloud Integrations

**Gen3 replacement**: Settings app (current), Fleet Management App (mid-term)

**Phase 2 required**: yes

Guide customers through migrating Dynatrace cloud monitoring from **classic connections** to **new connections (Smartscape on Grail)** for AWS, Azure, and GCP.

Use it to:

- discover and inventory classic vs new cloud connections per provider
- classify each cloud account's migration status (Not Started / Parallel / Complete)
- detect classic metric, entity, and entity-selector references in dashboards, SLOs, and alerts
- explain what changes between classic and new connections and why
- guide remediation: rewrite DQL, suggest new metric keys, update dashboards and alerts
- guide cutover: new connection setup, entity validation, asset migration, metric enablement, classic removal

### Prerequisites

- Load **`dtctl`** >= **0.27.0** before running any queries — all data gathering uses `dtctl query` and `dtctl get`. Run `dtctl version` to verify. See [dynatrace-oss/dtctl releases](https://github.com/dynatrace-oss/dtctl/releases).
- Stage 2 scanning requires a **Dynatrace platform token** (`dt0s16.*`) with the scopes below. Set it in a `.dtmigration` file (copy `.dtmigration.example`) or export `DT_PLATFORM_TOKEN` in your shell. The active `dtctl` context must point to the same environment.
  - Required scopes: `document:documents:read`, `document:documents:admin`, `settings:objects:read`
- **`scripts/migration-lookup.ts`** is the deterministic core library for classic pattern detection and metric key lookup. It provides pure functions (no file I/O) that work in both DT Assist and Node.js IDE environments. Key functions:
  - `detectAll(data, providers, patterns)` — scans all asset types for classic cloud patterns (replaces Stage 2 scanning)
  - `lookupMetricKey(key, index)` — looks up a classic metric key in the pre-built `per-key-mappings.json` index via a 4-step normalization chain
  - `extractServiceSegment(key, provider)` — extracts the service segment from a classic key for grouping findings
  - `scanDashboards`, `scanMetricEvents`, `scanSlos`, `scanDavisDetectors`, `scanInfrastructureDetection` — individual asset-type scanners
- The model executes all orchestration (discovery, assessment reports, migration plans) using native DQL and document read tools combined with the library functions. Stage 1 queries are in `discovery-queries.md`; detection rules are in `classic-detection-patterns.json`; mapping rules are in `per-key-mappings.json`.
- Stage output follows the contract in `stage-output-contract.md`. Use `migration-plan-format.md` as the Stage 3 plan template.

## Interaction Model

This reference is designed for **iterative use across multiple conversations**, not a single end-to-end run. Each stage is a natural conversation boundary. The typical flow:

1. **Stage 1** — Discover and classify all cloud connections → user reviews inventory
2. **Stage 2** — Scan for classic dependencies within a user-selected scope → user reviews assessment report
3. **Stage 3** — Get migration guidance per asset (report or guided execution) → user decides how to proceed
4. **Stage 4** — Set up new connections, validate, migrate assets, enable metrics, remove classic → user executes in UI with agent guidance

At each stage boundary, **pause and ask the user** how to proceed. Do not automatically advance to the next stage.

## Use Cases

| Use case | What to do |
|---|---|
| Assess migration readiness for all cloud accounts | Run Stage 1 (Discovery & Classification) |
| Check a specific provider's connection status | Run Stage 1, focus on that provider |
| Find dashboards referencing classic cloud metrics | Run Stage 2 with dashboard scanning selected |
| Find alerts using classic metric keys | Run Stage 2 with alert scanning selected |
| Find SLOs using classic metric keys | Run Stage 2 with SLO scanning selected |
| Understand classic vs new metric key differences | Load the provider-specific reference for the provider in question |
| Get a migration plan for affected assets | Run Stage 3 in report-only mode |
| Interactively migrate a dashboard or SLO | Run Stage 3 in guided execution mode |
| Set up a new cloud connection and cut over | Run Stage 4 |

## Concepts

### Connection Types

Each cloud provider has **classic** and **new** connection types. They coexist during migration.

| Aspect | Classic | New (Smartscape on Grail) |
|---|---|---|
| **Entity model** | `dt.entity.*` (dedicated types + `CUSTOM_DEVICE`) | Smartscape nodes (`AWS_*`, `AZURE_*`, `GCP_*`) |
| **Entity query** | `fetch dt.entity.<type>` | `smartscapeNodes <TYPE>` |
| **Metric prefixes** | `dt.cloud.<provider>.*`, `cloud.<provider>.*`, `builtin:cloud.<provider>.*`, `ext:cloud.<provider>.*` | `cloud.<provider>.<Service>.<Metric>.By.<Dim>` (new DA source) |
| **Data acquisition** | ActiveGate polling or Metric Streams | Platform-managed DA service |
| **Settings schema** | `builtin:cloud.aws` / Config API v1 (Azure) / none (GCP) | `builtin:hyperscaler-authentication.connections.*` |

### Migration Status Classification

Each cloud account falls into one of three states:

| Status | Condition | Meaning |
|---|---|---|
| **Not Started** | Classic connection exists, no new connection for the same account ID | Migration has not begun for this account |
| **Parallel** | Both classic and new connections exist for the **same** account ID | Running in parallel — ready to cut over |
| **Complete** | New connection only, no classic connection for this account ID | Migration finished |

### Classic Detection Patterns

Classic dependencies are identified by metric key prefix and entity type. The full detection rules (all prefixes per provider, all entity types, disambiguation logic) are in [classic-detection-patterns.md](classic-detection-patterns.md).

**Key indicators:**
- **Metric prefixes**: `dt.cloud.<provider>.*`, `builtin:cloud.<provider>.*`, `ext:cloud.<provider>.*`, and ambiguous `cloud.<provider>.*` keys without `dt.da.source`
- **Entity types**: `fetch dt.entity.<classic_cloud_type>` or `custom_device` with `cloud:<provider>:*` sub-types

When the prefix `cloud.<provider>.*` is ambiguous (could be classic or new), **REQUIRED:** Load [disambiguation.md](disambiguation.md) for the resolution rules.

## Stage 1: Discovery & Classification

**Goal**: Build a complete inventory of all cloud connections across AWS, Azure, and GCP. Classify each account's migration status.

```
Stage 1 Progress:
- [ ] Step 1: Run connection discovery queries (all providers)
- [ ] Step 2: Classify each account (Not Started / Parallel / Complete)
- [ ] Step 3: Present inventory table and confirm scope with user
```

> Run the queries from [discovery-queries.md](discovery-queries.md) using the DQL tool (`dtctl query` in the IDE, or the native DQL tool in DT Assist). The file contains all queries with the correct join-key fields for each provider. The manual steps below describe the same workflow in detail.

Run these steps in order. All queries use `dtctl query`.

### Step 1: Discover Cloud Connections

Run the connection discovery queries for each provider. Load [discovery-queries.md](discovery-queries.md) for the full set.

**Summary of queries to run:**

1. **AWS classic:** `fetch dt.entity.aws_credentials` — one row per classic connection
2. **AWS new:** `smartscapeNodes AWS_ACCOUNT` — one row per new connection
3. **Azure classic:** `fetch dt.entity.azure_credentials` with subscription lookup
4. **Azure new:** `smartscapeNodes AZURE_MICROSOFT_RESOURCES_SUBSCRIPTIONS`
5. **GCP classic:** `` fetch `dt.entity.cloud:gcp:project` ``
6. **GCP new:** `smartscapeNodes GCP_CLOUDRESOURCEMANAGER_GOOGLEAPIS_COM_PROJECT`
7. **AWS Metric Streams:** `fetch metric.series | filter dt.source == "AWS Metric Streams"` — flag affected accounts

### Step 2: Classify Each Account

For each account ID found across classic and new queries:

1. If account appears in **classic only** (no matching account ID in new connections) → status: `Not Started`
2. If account appears in **new only** (no matching account ID in classic connections) → status: `Complete`
3. If the **same account ID** appears in both classic and new → status: `Parallel`
4. If AWS and Metric Streams detected for same account → add `not-yet-supported` flag (Metric Streams is not yet supported by new connections; only the Metric Streams portion is blocked — classic built-in and non-built-in polling can still be migrated. **REQUIRED if Metric Streams detected:** Load [metric-streams.md](metric-streams.md) for migration-blocked logic.)

Present results as a summary table: Provider | Account ID | Connection Name | Status | Blocked?

### Step 3: Conversation Boundary — Scope Selection

After presenting the inventory table, **pause and ask the user**:

> "Which cloud providers do you want to assess for classic dependencies? (all providers, or a specific one like AWS/Azure/GCP)"
> "Which asset types should I scan for classic cloud dependencies? (default: all)"
> - New platform dashboards
> - Alerts (metric events, infrastructure anomaly detection, anomaly detectors)
> - SLOs
> - All of the above

> - **Out of scope — alerting profiles and management-zone-scoped alerts.** These belong to a broader alerting workflow that covers all domains, not cloud-specific migration. Do not attempt to scan, remediate, or comment on these within this reference.

Scoping guidance:
- For environments with **fewer than 20 cloud accounts**: scanning all providers at once is reasonable
- For environments with **20+ cloud accounts**: recommend scoping to **one provider at a time** to keep the assessment manageable
- Scoping is **by provider only** — it is not possible to filter by individual cloud account when scanning dashboards, alerts, and SLOs

Do **not** proceed to Stage 2 without the user's scope selection.

## Stage 2: Dependency Assessment

**Goal**: Scan dashboards, alerts, and SLOs for classic cloud references within the provider scope and asset types selected in Stage 1. Produce a detailed assessment report.

```
Stage 2 Progress:
- [ ] Step 1: Confirm provider scope and asset types from Stage 1
- [ ] Step 2: Fetch and scan selected asset types
- [ ] Step 3: Apply detection rules (load classic-detection-patterns.md + disambiguation.md)
- [ ] Step 4: Produce assessment report (chat summary + detailed file)
- [ ] Step 5: Confirm remediation mode and granularity with user
```

> **IDE automation** — use `scripts/migration-lookup.ts` functions to scan fetched assets programmatically. Run in order:
> 1. Fetch assets: `dtctl get dashboards`, `dtctl get settings --schema builtin:anomaly-detection.metric-events`, etc. (see Step 2 table). Export each to `./assessment/`.
> 2. Load detection patterns from `classic-detection-patterns.json` using `loadDetectionPatterns()`.
> 3. Run `detectAll(assessmentData, providers, patterns)` to scan all asset types at once, or use individual scanners (`scanDashboards`, `scanMetricEvents`, etc.).
>
> **DT Assist** — use native document and settings read tools to fetch each asset type, then apply detection rules from `classic-detection-patterns.json`. The manual steps below describe the same workflow.

### Step 1: Confirm Scope and Selected Asset Types

Confirm the provider scope and asset types selected in Stage 1.

Default to scanning **all asset types** if the user does not specify.

### Step 2: Scan Selected Asset Types

| Asset type | Fetch command | What to inspect | Reference |
|---|---|---|---|
| Dashboards (new platform only) | `dtctl get dashboards --admin-access --filter "not (originAppId exists and originAppId starts-with 'dynatrace.') and (type == 'dashboard')" -o json` then fetch each ID via Document Service | `tile.query`, `tile.queries[].query` — preset dashboards and non-dashboard types excluded server-side by `--filter` (type restriction required due to dtctl bug where `--filter` bypasses implicit type scoping); `--admin-access` (requires `document:documents:admin` OAuth permission) includes all users' dashboards; script gracefully falls back to user-visible scan when permission is absent | [dashboard-scanning.md](dashboard-scanning.md) |
| Alerts — metric events | `dtctl get settings --schema builtin:anomaly-detection.metric-events -o json` | `queryDefinition.metricKey`, `queryDefinition.metricSelector` | [alert-scanning.md](alert-scanning.md) |
| Alerts — infrastructure anomaly detection (AWS only) | `dtctl get settings --schema builtin:anomaly-detection.infrastructure-aws --scope environment -o json` | Presence of any object signals classic AWS entity type monitoring | [alert-scanning.md](alert-scanning.md) |
| Alerts — anomaly detectors (custom alerts) | `dtctl get settings --schema builtin:davis.anomaly-detectors -o json` | `analyzer.input[].value` — scan each input value for classic metric patterns | [alert-scanning.md](alert-scanning.md) |
| SLOs | `dtctl get slos -o json` | `metricExpression`, `filter` | [slo-scanning.md](slo-scanning.md) |

> **Classic dashboards (Config API v1):** Use `scanClassicDashboards()` from `scripts/migration-lookup.ts` to scan them when `DT_API_TOKEN` (dt0c01.* with `ReadConfig` scope) is set in `.dtmigration`. Without that token, classic dashboards cannot be scanned automatically — inform the user: *"Classic dashboards (Config API v1) require a `DT_API_TOKEN` with `ReadConfig` scope. Set it in `.dtmigration` and re-run. Without it, review classic dashboards manually."*

### Step 3: Apply Detection Rules

> **REQUIRED before scanning:** Load [classic-detection-patterns.md](classic-detection-patterns.md)
> for the full prefix and entity type rules, and [disambiguation.md](disambiguation.md) for
> overlapping-prefix resolution. Do not attempt detection without reading both.

For all scanned content, apply the classic detection patterns:
- Classic metric prefix matching — **REQUIRED:** Load [classic-detection-patterns.md](classic-detection-patterns.md)
- Ambiguous prefix disambiguation — **REQUIRED:** Load [disambiguation.md](disambiguation.md)
- Classic entity type detection — see [Classic Detection Patterns](#classic-detection-patterns) above

### Step 4: Produce Assessment Report

Produce two outputs:

1. **Chat summary** — A concise overview: count of affected dashboards, alerts, and SLOs (out of total scanned), plus an "out of scope" note for classic dashboards (Config API v1).

2. **Detailed report file** — A local markdown file (e.g., `cloud-migration-assessment.md`) or Dynatrace Document containing: connection inventory table (Provider | Account ID | Name | Status | Blocked?), then each affected asset grouped by type with name, ID, owner, and the specific classic patterns detected.

**REQUIRED:** Load [assessment-report-template.md](assessment-report-template.md) for the full report template.

### Step 5: Conversation Boundary — Remediation Mode

After presenting the assessment, **pause and ask the user**:

> "How would you like to proceed with migration guidance?"
> 1. **Report only** — I'll produce a detailed migration plan file with all suggested changes. You execute them independently.
> 2. **Guided execution** — I'll walk you through each change interactively, with confirmation before applying anything.
>
> "At what granularity do you want to work?"
> - One asset at a time
> - By asset type (all dashboards first, then alerts, then SLOs)
> - All at once

Do **not** proceed to Stage 3 without the user's mode and granularity selection.

## Stage 3: Migration Guidance & Remediation

**Goal**: For each classic dependency found in Stage 2, provide migration guidance. The user controls whether this is a report or guided execution.

```
Stage 3 Progress:
- [ ] Determine mode (report only or guided execution)
- [ ] For each affected asset: translate metric keys and entity types
- [ ] For each affected dashboard: rewrite DQL tiles
- [ ] For each affected alert: remap metric keys, check _alert suffix, check EOL
- [ ] For each affected SLO: rewrite metric expression
- [ ] Deliver migration plan file (Mode A) or confirm each change (Mode B)
```

**Determine mode from Stage 2 selection before proceeding:**
- **Mode A (Report only)?** → Follow [Mode A: Report Only](#mode-a-report-only) — produce migration plan file, then stop
- **Mode B (Guided execution)?** → Follow [Mode B: Guided Execution](#mode-b-guided-execution) — work through assets interactively

### Mode A: Report Only

Produce a structured migration plan file (markdown) that the user can execute independently. For each affected asset, document:

1. **What is classic**: the specific metric key, entity type, or DQL pattern detected
2. **What the new equivalent is**: the replacement metric key, Smartscape node type, or rewritten DQL
3. **What needs to change**: concrete before/after showing the exact modification

Include all rewritten DQL snippets, new metric keys, and entity type mappings so the file is self-contained.

> **Detection output key**: Metric event alert findings are under the key `"metric_events"` in the `detectAll()` output.

> **Grouping findings by service**: When organising the migration plan by AWS/Azure service (e.g. a
> "Lambda" section, an "EC2" section), extract the service segment from each classic metric key using
> `extractServiceSegment(key, provider)` from `scripts/migration-lookup.ts`. Do **not** use simple
> substring replacement such as `key.replace('cloud.aws.', '')` — this strips `cloud.aws.` from
> within the string, so `builtin:cloud.aws.lambda.*` becomes `builtin:lambda.*`, producing
> `builtin:lambda` as the service group name instead of `lambda`.

### Mode B: Guided Execution

Work through assets at the user-chosen granularity (one at a time, by type, or all at once). For each asset:

1. Explain what classic references were found and why they need to change
2. Show the proposed change (before/after)
3. **Ask for confirmation** before applying any modification
4. Help apply the change (create updated dashboard, update alert, re-create SLO)

### Metric Key Migration

For each classic metric key detected in Stage 2, translate it to the new connection equivalent using the authoritative mapping database.

#### Primary: Lookup via pre-built index (AWS, Azure)

Use `lookupMetricKey(key, index)` from `scripts/migration-lookup.ts` to look up exact mappings from the pre-built `per-key-mappings.json` index (derived from 53K+ AWS and 46K+ Azure DAC entries). The function applies a 4-step normalization chain:

1. Exact match
2. Strip selector modifiers (`:avg`, `:splitBy`, ...)
3. Normalize prefix (`dt.cloud.*` → `builtin:cloud.*` → `builtin:*`)
4. Strip dimension suffix (`By[A-Z].*`) and retry

**Interpreting results:**

| Field | Meaning |
|---|---|
| `bestDacKey` | The preferred new metric key |
| `availability` | `recommended` (no extra config needed), `autodiscovered` (requires custom metric configuration on new connection), or `none` |

#### Fallback: Heuristic Rules + Discovery Query (all providers including GCP)

When `lookupMetricKey()` returns `null`, or for GCP (mapping database not yet available), **REQUIRED for fallback:** Load [metric-key-mapping.md](metric-key-mapping.md) and apply heuristic rules:

- `dt.cloud.aws.<service>.<metric>` → `cloud.aws.<Service>.<Metric>.By.<Dim>` (with `dt.da.source` filter for new DA)
- `builtin:cloud.aws.*` / `ext:cloud.aws.*` → look up the Grail equivalent first, then map to new
- Azure patterns: Load [azure-classic.md](azure-classic.md) and [azure-new.md](azure-new.md)
- GCP patterns: Load [gcp-classic.md](gcp-classic.md) and [gcp-new.md](gcp-new.md)

When neither the database nor heuristics produce a match, discover the new key from live data:

> **Note:** In the `dtctl query` examples below, inner quotes are escaped for the shell (`\"`). When running DQL directly (e.g., in a notebook), use standard double-quotes.

```
dtctl query "fetch metric.series, from:now()-1h
| filter startsWith(metric.key, \"cloud.aws.<service>\") AND isNotNull(dt.da.source)
| summarize cnt=count(), by:{metric.key, dt.da.source}"
```

#### End-of-Life Checks

Always check end-of-life status for services referenced in the migration. Consult `end-of-life-services.json` for the list of EOL services with dates and announcement URLs.

When a service is end-of-life, **report this prominently to the user** with the EOL date and announcement URL. The user may choose to skip migration for EOL services rather than invest effort in migrating metrics for a retiring service.

### Entity Migration

For each classic entity type detected in Stage 2, translate it to the new Smartscape node type.

#### Primary: Entity mapping databases (AWS, Azure)

Use the entity mapping databases (`dac-aws-to-2ndgen-entities.json`, `dac-azure-to-2ndgen-entities.json`) to look up exact entity type mappings from classic to new Smartscape node types.

#### Fallback: Heuristic Tables (all providers including GCP)

When the mapping database has no match, or for GCP, use the mapping tables in [entity-type-mapping.md](entity-type-mapping.md).

Key DQL rewrite patterns:
- `fetch dt.entity.<classic_type>` → `smartscapeNodes <NEW_TYPE>`
- `entity.name` → `name` in Smartscape context
- `custom_device` with `cloud:*` sub-types → use the dedicated Smartscape node type from the mapping database or mapping table
- Classic entity selectors in SLO `filter` fields → rewrite using Smartscape node filters

Load [entity-type-mapping.md](entity-type-mapping.md) for the full heuristic mapping tables (AWS, Azure, GCP) and query syntax change details.

### Dashboard Remediation

For each affected dashboard:
1. Explain which tiles have classic references and what the replacement is
2. Provide rewritten DQL for each affected tile
3. If the user confirms, help create an updated dashboard or guide manual editing

### Alert Remediation

There are three types of classic alerts to remediate:

#### Metric Event Alerts

For each affected metric event:
1. Explain the classic metric key and its new equivalent
2. Suggest the replacement metric key or DQL expression
3. If the metric event alert had a condition-based trigger (threshold, baseline), guide creation of an equivalent Anomaly Detector using the new metric key — this is the modern replacement for metric event alerts

> **Classic `_alert` suffix keys**: Classic metric event alerts sometimes define a paired key with an
> `_alert` suffix alongside the primary key (e.g. `ext:cloud.aws.amazonmq.cpuUtilizationAverage_alert`).
> These `_alert` variants are classic-only artifacts — they have no equivalent in the new connection.
> When re-creating an alert with the new metric key, use only the primary mapped new key.
> Do not look for or attempt to create an `_alert` variant.

#### Infrastructure Anomaly Detection (AWS Only)

Classic AWS infrastructure anomaly detection (`builtin:anomaly-detection.infrastructure-aws`) is auto-managed by Dynatrace. **No manual migration is required.** When the new connection is active, new Smartscape entity types have their own built-in anomaly detection.

However, if **customised thresholds** exist on the classic infrastructure detection (e.g., custom CPU thresholds for EC2), these do not carry over. Review custom thresholds before cutover and create equivalent Anomaly Detectors with new metric keys to preserve the custom thresholds.

#### Anomaly Detectors (Custom Alerts)

For each affected anomaly detector:
1. Identify which analyzer input fields contain classic metric references
2. Look up new metric key equivalents using `lookupMetricKey()` from `scripts/migration-lookup.ts`
3. Re-create the detector with updated analyzer inputs (detectors must be deleted and re-created — inputs cannot be edited in place)
4. Follow the same zero-gap migration strategy as metric events: create new disabled → enable after new connection ingests data → delete old

Load [alert-scanning.md](alert-scanning.md) for the full detection logic, remediation workflow, and report formats for all three alert types.

### SLO Remediation

For each affected SLO:
1. Explain the classic metric/entity reference
2. Provide the rewritten metric expression using new keys
3. Guide SLO re-creation with the updated definition (classic SLOs using metric selectors cannot be edited to use DQL — they must be re-created)

## Stage 4: Cutover & Validation

**Goal**: Guide the user through setting up new connections, validating entities, migrating assets, enabling metrics with parallel running, and removing classic connections. **All guidance-only** — the user executes steps in the Dynatrace UI.

**REQUIRED:** Load [cutover-guide.md](cutover-guide.md) before starting — it contains provider-specific setup instructions, required permissions, and all validation queries.

```
Stage 4 Progress:
- [ ] 4a: New connection created (topology only, metric ingest disabled)
- [ ] 4b: Entity validation passed — Smartscape node counts match expected
- [ ] 4c: Assets migrated from Stage 3 output; alert strategy confirmed with user
- [ ] 4d: Metric ingest enabled; new metrics validated with dt.da.source
- [ ] 4e: Classic connection disabled; re-validation passed; buffer period started
```

### Step 4a: New Connection Setup — Topology Only

Create the new connection with **metric ingest disabled**. This starts topology ingestion (Smartscape nodes appear) without metric data flow — safe for parallel running alongside classic.

Per-provider auth requirements:
- **AWS**: IAM role
- **Azure**: service principal with Reader role
- **GCP**: service account with Viewer role (replaces classic GKE deployment entirely)

See [cutover-guide.md](cutover-guide.md) for exact Settings schema, required permissions, and setup steps per provider.

### Step 4b: Entity Validation

Re-run the new connection discovery queries from Stage 1 (`smartscapeNodes` queries). Compare expected vs actual Smartscape node counts.

If counts don't match:
1. Check IAM/RBAC permissions — missing permissions are the most common cause
2. Check service enablement on the new connection
3. Allow propagation time (up to 15 min for initial ingestion)
4. If still mismatched → return to Step 4a and review connection configuration before proceeding

**Do not proceed to Step 4c until entity counts are satisfactory.**

### Step 4c: Asset Migration

Apply the Stage 3 remediation output. Asset migration happens **before** enabling metric ingest — migrated assets will show no data until Step 4d, which is expected.

**For alerts, pause and ask the user which strategy they prefer:**

> "When should I migrate the alerts?"
> - **Option 1 (no-gap)**: Create new alerts now (disabled), swap at Step 4d — no alerting gap, no double-firing
> - **Option 2 (gap accepted)**: Migrate alerts after classic is disabled at Step 4e — brief coverage gap during switchover

The choice depends on risk tolerance and environment criticality. Document the chosen option — it affects Step 4d and 4e.

### Step 4d: Metric Configuration & Parallel Running

Enable metric ingest on the new connection. Prioritize services referenced by assets scanned in Stage 2.

**Validate after enabling:**
1. Run `dtctl query "fetch metric.series | filter isNotNull(dt.da.source) | summarize count()"` — non-zero result confirms new metrics are flowing
2. Spot-check dashboards that were remediated in Stage 3 — tiles should now show data
3. Verify SLOs are evaluating against new metric keys

If metric data is absent after 15 minutes:
- Check `dt.da.source` values — if null, metrics are still from classic
- Verify metric ingest is enabled on the new connection settings
- Return to Step 4a to confirm the connection was set up correctly

**If Option 1 (no-gap alerts)**: simultaneously disable the old classic alerts and enable the new ones now.

> Note: classic entity IDs do **not** carry over to new Smartscape nodes — entity-based alert filters must reference new Smartscape node types.

### Step 4e: Classic Connection Removal

Disable (don't delete) the classic connection. Deletion is irreversible; disabling allows rollback if issues emerge.

**Re-validate after disabling:**
1. Re-run Stage 1 discovery queries — classic connection should now show no active data
2. Re-run Stage 2 scanning queries — no new classic dependencies should appear
3. If issues are found → re-enable classic connection and investigate before proceeding

**If Option 2 (gap-accepted alerts)**: create and enable the new alerts now.

Recommend a **buffer period** (typically 1–2 weeks) before final deletion to confirm stability. Classic historical data is retained per the environment's retention settings.

Detailed per-provider instructions, IAM/RBAC requirements, validation queries, and metric validation DQL are all in [cutover-guide.md](cutover-guide.md).

## References

### General

- [discovery-queries.md](discovery-queries.md) — All DQL queries for connection discovery and classification
- [metric-key-mapping.md](metric-key-mapping.md) — Classic → new metric key translation rules and lookup strategy
- [entity-type-mapping.md](entity-type-mapping.md) — Classic entity type → Smartscape node type mapping table
- [classic-detection-patterns.md](classic-detection-patterns.md) — All classic metric prefix and entity type detection rules
- [disambiguation.md](disambiguation.md) — How to distinguish classic vs new when metric prefixes overlap
- [assessment-report-template.md](assessment-report-template.md) — Chat summary and detailed report templates for Stage 2
- [stage-output-contract.md](stage-output-contract.md) — Full multi-stage run document contract: front-matter manifest, per-stage section structure, resume behavior
- [stage-output.schema.json](stage-output.schema.json) — JSON Schema for the stage-output manifest and per-stage findings arrays
- [migration-plan-format.md](migration-plan-format.md) — Stage 3 Mode A migration plan output spec: section structure, table formats, availability labels

### Scanning & Remediation

- [dashboard-scanning.md](dashboard-scanning.md) — New platform dashboard scanning patterns and edge cases
- [alert-scanning.md](alert-scanning.md) — Alert scanning: metric events, infrastructure anomaly detection (AWS), and anomaly detectors (custom alerts)
- [slo-scanning.md](slo-scanning.md) — SLO scanning patterns (classic and new format)
- [cutover-guide.md](cutover-guide.md) — New connection setup, entity validation, parallel running, and classic removal guidance
- [metric-streams.md](metric-streams.md) — AWS Metric Streams detection and migration-blocked logic

### Provider Deep References

- [aws-classic.md](aws-classic.md) — Classic AWS connection flavours, metric key formats, entity types
- [aws-new.md](aws-new.md) — New AWS connection, Smartscape entity types, DA sources
- [azure-classic.md](azure-classic.md) — Classic Azure connection flavours, metric key formats
- [azure-new.md](azure-new.md) — New Azure connection, Smartscape entity types
- [gcp-classic.md](gcp-classic.md) — Classic GCP connection (GKE-based), custom device model
- [gcp-new.md](gcp-new.md) — New GCP connection, Smartscape entity types

