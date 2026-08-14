# Query Cost Attribution

Step-by-step workflow for investigating what is driving DQL query scan costs.
Covers BUE billable totals, per-source attribution, per-detector breakdown
(ALERTING pool), and QEE drill-down.

## Contents

- [Common Principles](#common-principles)
- [Overview](#overview)
- [BUE Query Attribution Fields](#bue-query-attribution-fields)
- [Step 1 — Top Sources by Billable Scan (BUE)](#step-1--top-sources-by-billable-scan-bue)
  - [Step 1a — Coverage Check](#step-1a--coverage-check)
  - [Step 1b — Combined Attribution](#step-1b--combined-attribution)
- [Step 2 — Identify Source Type](#step-2--identify-source-type)
  - [Step 2a — AI-Generated Queries](#step-2a--ai-generated-queries)
  - [Step 2b — Drill Down by Bucket](#step-2b--drill-down-by-bucket)
- [Step 3 — Drill Into QEE for Details](#step-3--drill-into-qee-for-details)
  - [Step 3b — Cross-Validate Execution Count](#step-3b--cross-validate-execution-count)
- [Step 4 — Per-Detector Scan & Name Resolution (ALERTING pool)](#step-4--per-detector-scan--name-resolution-alerting-pool)
- [Step 5 — Rank by Cost Weight](#step-5--rank-by-cost-weight)
- [Investigating QEE↔BUE Mismatches](#investigating-qeebue-mismatches)

## Common Principles

1. **BUE is billable truth, QEE is diagnostic** — BUE Query events reflect
   actual billed scan volumes; QEE provides per-query execution details
   (`client.client_context`, query text, duration). Always start cost
   investigations with BUE, then drill into QEE for attribution detail.

2. **Sample first** — Before building any attribution query, run
   `| limit 3` (without `| fields`) on the target event type to discover
   available fields. `client.source`, `client.function_context`, and
   `client.workflow_context` vary by pool; confirm they are populated.

3. **Dedup billing events** — Use `| dedup {event.id, event.type}` for
   multi-type queries. See
   [Billing Event Deduplication](billing-capabilities.md#billing-event-deduplication).

4. **Always verify coverage before attributing** — Run the
   [Step 1a coverage check](#step-1a--coverage-check) before filtering on any
   `client.*` field.

5. **Rolling windows are acceptable here** — Investigation queries use
   `from: -7d` or `from: -30d` for diagnostic analysis. For billing totals
   that must match the Account Management Portal, use explicit UTC midnight
   boundaries per [billing-capabilities.md § Billing Timeframe Boundaries](billing-capabilities.md#billing-timeframe-boundaries).

## Overview

Query cost attribution requires **all 5 steps**. BUE (Step 1) shows billable
totals but lacks per-detector breakdown. Steps 2-4 resolve that using QEE
and `ANALYZER_EXECUTION_EVENT`. Stopping at Step 1 leaves most costs
unattributed.

**BUE vs QEE:** BUE Query events are billable truth. QEE's `scanned_bytes` is diagnostic,
not billable. Start with BUE for totals, drill into QEE for breakdown.

## BUE Query Attribution Fields

Coverage of all `client.*` attribution fields depends on your tenant's query pool
distribution, not on BUE event type. Always run the coverage check in Step 1a
before building attribution queries.

| Field | Description | Populated on |
|-------|-------------|--------------|
| `client.source` | Named source (dashboard URL, detector ID) | ALERTING, DASHBOARDS, APPLICATION, OPERATIONAL, BILLING; variable on INTERNAL_APPLICATION |
| `client.application_context` | App ID (e.g., `dynatrace.automations`) | AUTOMATION, DASHBOARDS, APPLICATION, INTERNAL_APPLICATION |
| `client.function_context` | Function within the app — drill down after attributing | AUTOMATION reliably; partial on INTERNAL_APPLICATION |
| `client.client_context` | Structured JSON with app, function, and version details | ALERTING and AUTOMATION reliably; variable on API and APPLICATION |
| `client.internal_service_context` | Internal Dynatrace service name | ALERTING, OPERATIONAL, BILLING |
| `client.workflow_context` | Workflow ID | AUTOMATION only |
| `user.id` / `user.email` | User or service account | Most pools |
| `ai_generated` | `true` when the query was issued by an AI agent (Davis Copilot, MCP assistant) | All Query BUE types |

Use `coalesce(client.source, client.application_context, client.internal_service_context, client.workflow_context, client.function_context, client.client_context, "unknown")` for
attribution. For app-level results, drill into `client.function_context`.

## Step 1 — Top Sources by Billable Scan (BUE)

Start with BUE — billable truth. First run a **coverage check** to see which
attribution field to use, then run the attribution query.

### Step 1a — Coverage Check

Verify which attribution fields are populated before building the attribution
query:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type,
    "Log Management & Analytics - Query",
    "Events - Query",
    "Traces - Query",
    "Files - Query")
| dedup {event.id, event.type}
| fieldsAdd has_source = isNotNull(client.source)
| fieldsAdd has_app_ctx = isNotNull(client.application_context)
| summarize
    total_gib = sum(toDouble(billed_bytes) / 1073741824),
    with_source_gib = sum(if(has_source, toDouble(billed_bytes) / 1073741824, else: 0)),
    with_app_ctx_gib = sum(if(has_app_ctx, toDouble(billed_bytes) / 1073741824, else: 0)),
    by: {event.type}
| fieldsAdd source_coverage_pct = round(with_source_gib / total_gib * 100, decimals: 1)
| fieldsAdd app_ctx_coverage_pct = round(with_app_ctx_gib / total_gib * 100, decimals: 1)
| sort event.type asc
```

### Step 1b — Combined Attribution

Use `coalesce()` across all six `client.*` attribution fields to capture the first
non-null value regardless of which query pool generated the event:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type,
    "Log Management & Analytics - Query",
    "Events - Query",
    "Traces - Query",
    "Files - Query")
| dedup {event.id, event.type}
| fieldsAdd attribution = coalesce(client.source, client.application_context, client.internal_service_context, client.workflow_context, client.function_context, client.client_context, "unknown")
| summarize total_billed_gib = sum(toDouble(billed_bytes) / 1073741824),
    by: {attribution, event.type}
| sort total_billed_gib desc
| limit 20
```

## Step 2 — Identify Source Type

The meaning of `attribution` depends on which query pool generated the cost.

| `attribution` pattern | Source type | Next step |
|------------------------|-------------|-----------|
| `https://.../document/...` | Dashboard (DASHBOARDS pool) | Filter Step 1b by `matchesPhrase(client.source, "/ui/dashboard/")` to rank dashboards |
| Encoded settings UID / opaque ID | Detector settings `objectId` (ALERTING pool) | Step 4 — resolved in combined query |
| `builtin:davis.anomaly-detectors/...` | Detector type name (ALERTING pool) | Step 4 — parse `client.client_context` |
| `dynatrace.automations:...` | Automation function (AUTOMATION pool) | Resolve via [workflow-total-cost.md § Cross-Event Field Reference](workflow-total-cost.md#cross-event-field-reference) |
| `dynatrace.<appname>` | Platform app (from `client.application_context`) | Drill into `client.function_context` |
| `dt.*` service name | Internal platform service | Review with platform team |
| `ai_generated == true` | AI agent (Davis Copilot / MCP) | Step 2a — attribute by `session_id`; `client.source` has the MCP tool name |

### Step 2a — AI-Generated Queries

Queries with `ai_generated == true` on BUE Query events represent **indirect** AI costs — the DQL scan volume triggered by an AI agent on top of the direct charges billed as `AI Units` / `AI Function Standard Call` BUEs. For direct AI invocation costs, see [billing-event-types.md § Agentic AppEngine](billing-event-types.md#agentic-appengine).

Filter on `ai_generated == true` to isolate the indirect scan cost:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type, "Log Management & Analytics - Query", "Events - Query", "Traces - Query", "Files - Query")
| filter ai_generated == true
| dedup {event.id, event.type}
| summarize total_gib = sum(toDouble(billed_bytes) / 1073741824),
    event_count = count(),
    by: {event.type}
```

To see which AI sessions drove the most scan volume, group by `session_id`. The `session_id`
on these Query BUEs matches the `session_id` on the `AI Units` / `AI Function Standard
Call` BUEs that initiated them, enabling cross-BUE attribution:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type, "Log Management & Analytics - Query", "Events - Query", "Traces - Query", "Files - Query")
| filter ai_generated == true
| filter isNotNull(session_id) and session_id != ""
| dedup {event.id, event.type}
| summarize total_gib = sum(toDouble(billed_bytes) / 1073741824),
    event_count = count(),
    by: {session_id, event.type}
| sort total_gib desc
| limit 20
```

> `client.source` on these BUEs typically contains the MCP tool name (e.g.,
> `dynatrace-mcp.get-problem-by-id`, `dynatrace-mcp.execute-dql`), useful for seeing which
> AI tools are driving the most scan volume. `conversation_id` may be an empty string on
> Query BUEs even when present on the AI Units / AI Function Standard Call BUEs in the same
> session — use `session_id` as the reliable join key.

### Step 2b — Drill Down by Bucket

Identify which Grail buckets drive scan volume — high scan on one bucket often
means missing time filters, over-broad aggregations, or detectors on
large-retention data.

> **BUE `usage.bucket` coverage varies by BUE `event.type`** (verified:
> emitted by `Events - Query` and `Digital Experience Monitoring - Query`;
> not by `Log Management & Analytics - Query`, `Traces - Query`,
> `Files - Query`) and can change as Dynatrace adds groupers. For **reliable
> per-bucket attribution across all BUE Query types, use QEE** — carries
> `table` and `bucket` with 100% coverage.

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type,
    "Events - Query",
    "Digital Experience Monitoring - Query")
| dedup {event.id, event.type}
| summarize total_gib = sum(toDouble(billed_bytes) / 1073741824),
    bue_rows = count(),
    by: {usage.bucket, event.type}
| sort total_gib desc
| limit 20
```

> ### ⛔ Cardinality rules for BUE + QEE joins
>
> Both BUE and QEE can fan out to multiple rows per `query_id`, and grouper
> dimensions may change over time. Apply universally:
>
> | Wrong | Right |
> |-------|-------|
> | `count()` on BUE/QEE for query count | `countDistinct(query_id)` |
> | `sum(billed_bytes)` grouped by `query_id` on BUE+QEE join | `sum(billed_bytes)` grouped by `event.id` |
>
> **`event.id` = safe grain for billed volume; `query_id` = safe grain for
> query counts.** Never mix them.

Join BUE with QEE for per-query details (group by `event.id` when summing
`billed_bytes`, use `countDistinct(query_id)` for query counts):

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type,
    "Log Management & Analytics - Query",
    "Events - Query",
    "Traces - Query",
    "Files - Query")
| dedup {event.id, event.type}
| lookup [
    fetch dt.system.events, from: -7d
    | filter event.kind == "QUERY_EXECUTION_EVENT"
    | fields query_id, query_string, execution_duration_ms, user.email, table
  ], sourceField: query_id, lookupField: query_id,
     fields: {query_string, execution_duration_ms, query_user = user.email, table}
```

## Step 3 — Drill Into QEE for Details

QEE provides per-query execution details not available on BUE: `query_string`,
`scanned_bytes`, and `execution_duration_ms`.

> **Sample a BUE Query event with `| limit 1` before joining to QEE** to
> confirm available fields — notably `query_id`, the correct join key.

> **Filter must match the attribution field from Step 1b.** If the top
> `attribution` value came from `client.source`, filter on `client.source`.
> If it came from `client.application_context`, filter on that instead. Use
> `coalesce` to cover both:

> ### ⛔ What QEE `count()` actually counts — do NOT mislabel it
>
> A `QUERY_EXECUTION_EVENT` is emitted **once per bucket touched per DQL
> statement** — NOT once per DQL statement, and NOT once per workflow/detector
> run. A single `fetch logs` that scans 3 buckets produces **3 QEE records**
> (all sharing one `query_id`). Therefore:
>
> | Quantity | How to count it | What it means |
> |----------|-----------------|---------------|
> | `qee_events = count()` | raw QEE row count | bucket-touches — **diagnostic only** |
> | `dql_statements = countDistinct(query_id)` | distinct `query_id` | actual DQL queries executed |
> | workflow / detector **runs** | a **separate** `WORKFLOW_EVENT` / `ANALYZER_EXECUTION_EVENT` query — see [Step 3b](#step-3b--cross-validate-execution-count) | how many times something actually ran |
>
> Never alias the QEE row count as `queries` or phrase it as "ran N times" — the
> gap between `count()` and `countDistinct(query_id)` is unpredictable (a few× to
> 50×+), so a raw count is never a safe proxy for query volume or run frequency.
> Use `countDistinct(query_id)` for query volume, and cross-validate run counts
> with the source event ([Step 3b](#step-3b--cross-validate-execution-count))
> before reporting any "how often did this run" conclusion.

```dql-template
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter coalesce(client.source, client.application_context, client.internal_service_context, client.workflow_context, client.function_context, client.client_context) == "<top attribution from step 1b>"
| summarize qee_events = count(),
    dql_statements = countDistinct(query_id),
    total_scanned_gib = sum(scanned_bytes) / 1073741824,
    avg_duration_ms = avg(execution_duration_ms),
    by: {table, status}
| sort total_scanned_gib desc
```

### Step 3b — Cross-Validate Execution Count

**Required whenever you report how often a source ran** (e.g. "this workflow
runs N times/day", "this detector fires every X"). QEE counts can never answer
this — QEE `count()` is bucket-touches (see the ⛔ block in Step 3), and the
real run count lives on the source's **originating** event, which differs by
pool. Each event has its own fan-out shape — use the exact count expression
from the table:

| Attribution pool | Originating event | Filter on | Count runs with |
|------------------|-------------------|-----------|-----------------|
| `dynatrace.automations` (AUTOMATION) | `WORKFLOW_EVENT` (`event.type == "WORKFLOW_EXECUTION"`) | `dt.automation_engine.workflow.id` | `countDistinct(dt.automation_engine.workflow_execution.id)` — fans out ≈2× per run (a `RUNNING` row + a terminal `SUCCESS`/`ERROR`/`CANCELLED` row share one execution id). See [workflow-total-cost.md § How Often Did the Workflow Run](workflow-total-cost.md#how-often-did-the-workflow-run) for the full query. |
| ALERTING (detectors) | `ANALYZER_EXECUTION_EVENT` | `dt.task.id` | `countDistinct(dt.analyzer.execution.start)` grouped by `dt.task.id` — runs are keyed by `(dt.task.id, dt.analyzer.execution.start)` (no dedicated execution-id field is emitted). `countDistinct` on the start timestamp is safe if the event ever fans out; sample first (`\| limit 3`) to confirm shape. |

## Step 4 — Per-Detector Scan & Name Resolution (ALERTING pool)

For ALERTING sources, parse `client.client_context` from QEE to get per-detector
scan volume, then resolve detector names from `ANALYZER_EXECUTION_EVENT` via
`join`.

**`dt.task.id` is the full encoded settings UID** (base64-encoded, e.g.,
`vu9U3hXa3q0AAAAB...vu9U3hXa3q0`) — not a plain UUID. This same encoded UID
appears in QEE `client.client_context` → `dt.task.id`, AEE `dt.task.id`, and
partially in QEE `client.source`.

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter query_pool == "ALERTING"
| parse client.client_context, "JSON:ctx"
| summarize qee_events = count(),
    dql_statements = countDistinct(query_id),
    total_scanned_gib = sum(scanned_bytes) / 1073741824,
    by: {task_id = ctx[`dt.task.id`], task_group = ctx[`dt.task.group`]}
| sort total_scanned_gib desc
| limit 20
| join [
    fetch dt.system.events, from: -7d
    | filter event.kind == "ANALYZER_EXECUTION_EVENT"
    | fieldsAdd task_id = dt.task.id, detector_name = dt.task.name
    | summarize detector_name = takeFirst(detector_name), by: {task_id}
  ], on: {task_id}, fields: {detector_name}, kind: leftOuter
```

> **Dotted JSON keys:** `ctx[\`dt.task.id\`]` — without backticks, DQL
> interprets dots as nested field access and fails silently.
>
> **`user.id` is NOT detector-specific.** All anomaly detectors share a service
> account. Use `dt.task.id` / `client.client_context` instead.

## Step 5 — Rank by Cost Weight

Apply normalization weights from [cost-estimations.md](cost-estimations.md) → [Cost Normalization Weights](cost-estimations.md#cost-normalization-weights).

## Investigating QEE↔BUE Mismatches

When QEE `scanned_bytes` significantly exceeds BUE `billed_bytes` for the same
source:

1. **Join on `query_id`** to identify which QEE records have no matching BUE
2. **Check for zero-rating** — certain queries may be zero-rated based on
   execution context (user, apps, queried data). These produce QEE
   records but no corresponding BUE. The gap is zero-rated usage, not a
   pipeline issue.
3. Only after ruling out zero-rating, investigate attribution coverage gaps
