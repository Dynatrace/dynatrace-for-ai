# Query Cost Attribution

Investigate what drives DQL query billable volume. Answer from BUE (billing usage events); use QEE
(query execution events) only for the [QEE Fallbacks](#qee-fallbacks).

## Contents

- [Rules](#rules)
- [Decision Path](#decision-path)
- [Spike Investigation](#spike-investigation)
- [BUE Attribution Fields](#bue-attribution-fields)
- [Coverage Check](#coverage-check)
- [Attribution Ranking](#attribution-ranking)
- [Source Interpretation and Dashboard Ranking](#source-interpretation-and-dashboard-ranking)
- [Detector Ranking](#detector-ranking)
- [AI and Agent Queries](#ai-and-agent-queries)
- [Bucket Drill-Down](#bucket-drill-down)
- [Run Counts](#run-counts)
- [QEE Fallbacks](#qee-fallbacks): Bucket Scan, Single-Query Details, QEE Exceeds BUE

## Rules

- Select Query BUEs with `endsWith(event.type, " - Query")`. NEVER hard-code an `event.type` list; tenants differ and new Query types appear.
- Dedup with `dedup {event.id, event.type}` ([why](billing-capabilities.md#billing-event-deduplication)). Filter before the dedup; duplicates share every field.
- Count queries with `countDistinct(query_id)`, NEVER `count()` (inflates 2-3x). `countDistinct(query_id)` is approximate (about 1%); say so when quoting exact counts.
- Sum raw `billed_bytes` as `billable_usage`. Unrated: add `billable_gib = billable_usage / 1073741824` for display. Rated: append the [Rate Card Join Snippet](cost-estimations.md#rate-card-join-snippet) instead (it divides by `unit_divisor`; summing GiB divides twice and every cost rounds to `0.00`).
- **Rated variant** (ranking queries below; Spike Q1 and Detector Ranking have their own rated lines): keep `event.type` in `by`; replace the `billable_gib` `fieldsAdd`, `sort` and `limit` with the [Rate Card Join Snippet](cost-estimations.md#rate-card-join-snippet), `| sort isNull(estimated_cost) asc, estimated_cost desc`, `| limit 20`; add `estimated_cost, currency_code` to any `fields` line.
- Timeframe: `-7d` default, `-14d` max ([SKILL.md Best Practice 2](../SKILL.md#best-practices)). Billing totals that must match the portal use [UTC midnight boundaries](billing-capabilities.md#billing-timeframe-boundaries).
- NEVER join BUE with QEE in bulk. For one query's detail, take `query_id` from BUE and filter QEE by it ([Single-Query Details](#single-query-details)).
- Unrated path: rank by `billable_usage`, NEVER compute `cost_weight` ([why](cost-estimations.md#estimated-query-cost-by-source)). Rated path: rank by `estimated_cost`.
- `user.email` is the caller, not the owner or the last editor. Infer no team or fix that the data does not show.
- Asked for a team or product area, say billing data can't attribute it; give `user.email` or the detector `task_id`/name instead.
- Label BUE volume "billable GiB" in headings, columns and prose, even when the user asks about "scan volume". "Scanned" is QEE wording.

## Decision Path

Questions that name no source type (for example "what drives our query cost?"): run the [Coverage Check](#coverage-check), then the [Attribution Ranking](#attribution-ranking). Others: route by the table.

| Question | Section |
|----------|---------|
| Spike or anomaly on one Query type around a date (observed vs predicted)? | [Spike Investigation](#spike-investigation) |
| Which sources are billed most? | [Attribution Ranking](#attribution-ranking), [Source Interpretation](#source-interpretation-and-dashboard-ranking) |
| Which dashboards? | [Dashboard Ranking](#dashboard-ranking) |
| Which detectors? | [Detector Ranking](#detector-ranking) |
| AI cost? | Coverage Check `ai_generated` split; if `ai_generated == true` has volume, [AI and Agent Queries](#ai-and-agent-queries) |
| Which buckets? | [Bucket Drill-Down](#bucket-drill-down); Logs, Traces, Files: [Bucket Scan](#bucket-scan) (QEE) |
| What did one query do? | [Single-Query Details](#single-query-details) (QEE) |
| How often did X run? | [Run Counts](#run-counts) |
| QEE far above BUE? | [QEE Exceeds BUE](#qee-exceeds-bue) (QEE) |

## Spike Investigation

Anomaly on one Query type around date D (observed vs predicted). Resolve the price source first ([Cost Ranking Rules step 0](../SKILL.md#cost-ranking-rules)). Two BUE queries answer who, when and how much. Use BUE only, with no QEE or `query_string` step; single-query questions go to [Single-Query Details](#single-query-details).

**Q1 trend.** Window D-13 00:00Z to D+1 00:00Z (14 days, the cap). Fill in the one `event.type` and the dates.

```dql-template
fetch dt.system.events, from: toTimestamp("<D-13>T00:00:00Z"), to: toTimestamp("<D+1>T00:00:00Z")
| filter event.kind == "BILLING_USAGE_EVENT" and event.type == "<event.type>"
| dedup {event.id, event.type}
| fieldsAdd attribution = coalesce(client.application_context, client.internal_service_context, client.source, client.workflow_context, client.function_context, client.client_context, "unknown")
| summarize billable_usage = sum(billed_bytes),
    attributed_usage = sum(if(attribution != "unknown", billed_bytes, else: 0)),
    queries = countDistinct(query_id), callers = countDistinct(user.email),
    by: {day = bin(timestamp, 24h)}
| fieldsAdd billable_gib = billable_usage / 1073741824,
    attributed_pct = round(toDouble(attributed_usage) / billable_usage * 100, decimals: 1)
| summarize {baseline_gib = arrayMedian(collectArray(billable_gib)),
    days = collectArray(record(day, billable_gib, attributed_pct, queries, callers))}
| expand d = days
| fields day = d[day], billable_gib = d[billable_gib], baseline_gib,
    spike = d[billable_gib] > 1.2 * baseline_gib,
    attributed_pct = d[attributed_pct], queries = d[queries], callers = d[callers]
| sort day asc
```

- Rated (the pre-flight found a rate card, so this is the Q1 to run): add `event.type` to the daily `by` (one row per day, single type), insert the [Rate Card Join Snippet](cost-estimations.md#rate-card-join-snippet) right after that `summarize`, add `estimated_cost, currency_code` to the `record(...)` and `estimated_cost = d[estimated_cost], currency_code = d[currency_code]` to the final `fields`; compare daily `estimated_cost` with the anomaly's currency values.
- Baseline: `baseline_gib`, the median daily `billable_gib` across the Q1 window, computed in DQL by the query's tail. `spike` is true for days above 1.2 × `baseline_gib`. The median is not pulled up by the spike itself.
- If Q1 shows no day above baseline, say so, skip Q2, and name no cause.
- The spike window is the run of days above baseline; D need not be in it.

**Q2 spike attribution.** Spike window only. One query replaces the Coverage Check, Attribution Ranking, [Time-Split](#time-split) and [Unknown-by-User Drill-Down](#unknown-by-user-drill-down) on this path.

```dql-template
fetch dt.system.events, from: toTimestamp("<spike start>T00:00:00Z"), to: toTimestamp("<spike end+1>T00:00:00Z")
| filter event.kind == "BILLING_USAGE_EVENT" and event.type == "<event.type>"
| dedup {event.id, event.type}
| fieldsAdd attribution = coalesce(client.application_context, client.internal_service_context, client.source, client.workflow_context, client.function_context, client.client_context, "unknown")
| summarize {billable_usage = sum(billed_bytes),
    queries = countDistinct(query_id)},
    by: {attribution, user.email}
| fieldsAdd billable_gib = billable_usage / 1073741824
| sort billable_usage desc
| limit 20
```

Rated: [rated variant](#rules).

| Top `attribution` | Next |
|-------------------|------|
| Detector source | [Detector Ranking](#detector-ranking) on the spike window; `user.email` is only the run-as user. State impact only from billable GiB per run or totals, never from query text |
| `unknown` | The `user.email` rows are the answer; report callers only |
| Other | [Source Interpretation](#source-interpretation-and-dashboard-ranking) |

Rules:

- Baseline days near zero before the spike: say it is a resumption of an earlier level, not a new workload (D-7 windows hide it).
- Claim a billing gap or zero-rating only through [QEE Exceeds BUE](#qee-exceeds-bue), not on this path.
- Explain the baseline only from Q1 data; label it an inference. Say what was not verified.
- Report what the data shows, not why: give no tuning or remediation advice (time ranges, filters, bucket scoping, config changes) and name no cause or owner the BUE fields don't show.
- Unrated path with a currency anomaly: say the currency figures can't be reconciled from BUE and report billable GiB; give no rate and no forecast method.

## BUE Attribution Fields

Population depends on the query pool, not on the BUE type.

| Field | Meaning | Notes |
|-------|---------|-------|
| `client.application_context` | App id (`dynatrace.automations`) | Clean for URL sources |
| `client.internal_service_context` | Internal service | Detectors arrive as `dt.davis.anomaly-detector` |
| `client.source` | Dashboard URL, detector id, MCP tool | |
| `client.workflow_context` | Workflow id | Automation only |
| `client.function_context` | Function within an app | Drill-down |
| `client.client_context` | JSON or plain string | JSON shapes: external client (`agent`, for example dtctl), detector (`dt.task.id`, `dt.task.group`, `dt.analyzer.execution_id`), backend (`app`), app sub-source (`source`) |
| `query_id` | Query identity | Always set; the grain for query counts |
| `user.email` | Caller | Always set. For detectors it is the run-as user, shared by several detectors: never use it for per-detector attribution, use `dt.task.id` |
| `usage.bucket` | Grail bucket | Events and Digital Experience Monitoring only |
| `session_id` | AI session | `ai_generated` rows only |
| `ai_generated` | Platform AI tool query (CoPilot/Assist, Dynatrace MCP) | Indirect AI cost signal, see [AI and Agent Queries](#ai-and-agent-queries) |

Preview types (for example Digital Experience Monitoring) have real `billed_bytes` but no public weight or rate card price. Keep their rows in the ranking and mark them preview/unpriced; on the rated path `estimated_cost` stays null and they sort last.

## Coverage Check

One pass per `event.type` and `ai_generated`. Report `attributed_pct` (coalesce is not `unknown`), `bucket_pct` and the `ai_generated` split. Skip types under 1% of total `billable_gib`. State the overall unattributed share in one line of the answer, then branch on `attributed_pct`:

| `attributed_pct` | Next |
|------------------|------|
| `<10%` | Skip the Attribution Ranking and [Time-Split](#time-split); run the [Unknown-by-User Drill-Down](#unknown-by-user-drill-down) |
| `10% to <90%` | Continue as routed, plus the [Unknown-by-User Drill-Down](#unknown-by-user-drill-down) |
| `≥90%` | Continue as routed |

If `unknown` is in the top 3 of the [Attribution Ranking](#attribution-ranking), run the [Time-Split](#time-split) against the top named source. If `unknown` stops when a named source starts, at the same volume and callers, it is one workload: merge the two and say so.

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT" and endsWith(event.type, " - Query")
| dedup {event.id, event.type}
| fieldsAdd attribution = coalesce(client.application_context, client.internal_service_context, client.source, client.workflow_context, client.function_context, client.client_context, "unknown")
| summarize billable_usage = sum(billed_bytes),
    attributed_usage = sum(if(attribution != "unknown", billed_bytes, else: 0)),
    bucket_usage = sum(if(isNotNull(usage.bucket), billed_bytes, else: 0)),
    queries = countDistinct(query_id),
    by: {event.type, ai_generated}
| fieldsAdd billable_gib = billable_usage / 1073741824,
    attributed_pct = round(toDouble(attributed_usage) / billable_usage * 100, decimals: 1),
    bucket_pct = round(toDouble(bucket_usage) / billable_usage * 100, decimals: 1)
| fields event.type, ai_generated, billable_gib, attributed_pct, bucket_pct, queries
| sort billable_gib desc
```

### Time-Split

6-hour bins; fill in the top named source:

```dql-template
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT" and endsWith(event.type, " - Query")
| dedup {event.id, event.type}
| fieldsAdd attribution = coalesce(client.application_context, client.internal_service_context, client.source, client.workflow_context, client.function_context, client.client_context, "unknown")
| filter in(attribution, array("unknown", "<top named source>"))
| summarize {billable_usage = sum(billed_bytes),
    queries = countDistinct(query_id), callers = countDistinct(user.email)},
    by: {time = bin(timestamp, 6h), attribution}
| fieldsAdd billable_gib = round(billable_usage / 1073741824, decimals: 0)
| sort time asc
```

### Unknown-by-User Drill-Down

The [Attribution Ranking](#attribution-ranking) query with `| filter attribution == "unknown"` inserted after its `fieldsAdd attribution` line and its `by` replaced with `by: {user.email, event.type}`.

## Attribution Ranking

The only canonical ranking query.

- **Unrated:** run as shown. Open the answer with the unrated ℹ️ disclaimer ([SKILL.md Cost Ranking Rules step 3](../SKILL.md#cost-ranking-rules)).
- **Rated:** [rated variant](#rules). Output rules: [cost-estimations.md](cost-estimations.md#output-rules-for-rated-path).
- **Dashboards in the top sources:** if `dynatrace.dashboards` or a `/ui/dashboard/` URL is among them, run [Dashboard Ranking](#dashboard-ranking) before answering and show its top dashboards.

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT" and endsWith(event.type, " - Query")
| dedup {event.id, event.type}
| fieldsAdd attribution = coalesce(client.application_context, client.internal_service_context, client.source, client.workflow_context, client.function_context, client.client_context, "unknown")
| summarize {billable_usage = sum(billed_bytes),
    queries = countDistinct(query_id)},
    by: {attribution, event.type}
| fieldsAdd billable_gib = billable_usage / 1073741824
| sort billable_usage desc
| limit 20
```

## Source Interpretation and Dashboard Ranking

| `attribution` pattern | Source | Next |
|-----------------------|--------|------|
| URL with `/ui/dashboard/<id>` (only when no app context is set; rare) | Dashboard | [Dashboard Ranking](#dashboard-ranking) |
| Other app URL (only when no app context is set; rare) | App page | Group by `client.application_context` |
| `dt.statistics.anomaly_detection.*`, `dt.davis.anomaly-detector` | Anomaly detector | [Detector Ranking](#detector-ranking) |
| Other `dt.statistics.*`, `dt.rca.*`, `dt.security.assessments.*` | Davis or security analyzer, not a detector | Report as analyzer; no per-detector breakdown |
| `dynatrace.automations` | Workflow | [workflow-total-cost.md](workflow-total-cost.md#cross-event-field-reference) |
| `dynatrace.dashboards` | Dashboard | [Dashboard Ranking](#dashboard-ranking) |
| `dynatrace.<app>` | Platform app | Drill into `client.function_context` |
| `dynatrace-mcp*.<tool>` | Dynatrace MCP tool | [AI and Agent Queries](#ai-and-agent-queries) |
| JSON with `agent` | External client (dtctl or another CLI) | Group by `agent`; not AI cost |
| JSON with `app` or `source` | Backend service or app sub-source | Group by `app` or `source` |
| Other `dt.*` | Dynatrace internal service | Report as internal service |
| `unknown` | Unattributed: API-pool or service calls without client context | Run the Coverage Check [Time-Split](#time-split), then group by `user.email`; state the unattributed share |

### Dashboard Ranking

Filter on the URL path, which carries the dashboard id, not on the app id. Rated: [rated variant](#rules).

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT" and endsWith(event.type, " - Query")
    and contains(client.source, "/ui/dashboard/")
| dedup {event.id, event.type}
| parse client.source, "LD '/ui/dashboard/' LD:dashboard_id ('?' | '/' | '#' | EOS)"
| summarize {billable_usage = sum(billed_bytes),
    queries = countDistinct(query_id),
    users = countDistinct(user.email)},
    by: {dashboard_id}
| fieldsAdd billable_gib = billable_usage / 1073741824
| sort billable_usage desc
| limit 20
```

## Detector Ranking

Attribute by `task_id` only. Filter on the `client.source` prefix and require `dt.task.id`: detector BUEs span several Query types by tenant, and notebook previews carry `dt.statistics.anomaly_detection.*` sources without a task id. Detector names are not unique: the answer table MUST show `task_id` next to the full, unshortened `detector_name`.

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT" and endsWith(event.type, " - Query")
    and startsWith(client.source, "dt.statistics.anomaly_detection")
| dedup {event.id, event.type}
| parse client.client_context, "JSON:ctx"
| filter isNotNull(ctx[`dt.task.id`])
| summarize {billable_usage = sum(billed_bytes),
    runs = countDistinctExact(ctx[`dt.analyzer.execution_id`])},
    by: {task_id = toString(ctx[`dt.task.id`])}
| sort billable_usage desc
| limit 20
| join [
    fetch dt.system.events, from: -7d
    | filter event.kind == "ANALYZER_EXECUTION_EVENT"
    | summarize detector_name = takeFirst(dt.task.name), by: {task_id = toString(dt.task.id)}
  ], on: {task_id}, fields: {detector_name}, kind: leftOuter
| fieldsAdd billable_gib = billable_usage / 1073741824
| fields task_id, detector_name, billable_gib, runs
```

- Wrap `ctx[...]` keys in backticks; unquoted dots read as nested fields and fail silently.
- `toString` on both join keys is required.

Rated: re-aggregate per `task_id` after the rate-card join so `limit 20` counts detectors:

```dql-snippet
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT" and endsWith(event.type, " - Query")
    and startsWith(client.source, "dt.statistics.anomaly_detection")
| dedup {event.id, event.type}
| parse client.client_context, "JSON:ctx"
| filter isNotNull(ctx[`dt.task.id`])
| summarize billable_usage = sum(billed_bytes),
    by: {task_id = toString(ctx[`dt.task.id`]), event.type}
// Rate Card Join Snippet (cost-estimations.md#rate-card-join-snippet) goes here
| summarize {billable_usage = sum(billable_usage), estimated_cost = sum(estimated_cost),
    currency_code = takeFirst(currency_code), valid_from = max(valid_from), valid_to = min(valid_to)},
    by: {task_id}
| sort isNull(estimated_cost) asc, estimated_cost desc
| limit 20
| join [
    fetch dt.system.events, from: -7d
    | filter event.kind == "BILLING_USAGE_EVENT" and endsWith(event.type, " - Query")
        and startsWith(client.source, "dt.statistics.anomaly_detection")
    | dedup {event.id, event.type}
    | parse client.client_context, "JSON:ctx"
    | filter isNotNull(ctx[`dt.task.id`])
    | summarize runs = countDistinctExact(ctx[`dt.analyzer.execution_id`]), by: {task_id = toString(ctx[`dt.task.id`])}
  ], on: {task_id}, fields: {runs}, kind: leftOuter
| join [
    fetch dt.system.events, from: -7d
    | filter event.kind == "ANALYZER_EXECUTION_EVENT"
    | summarize detector_name = takeFirst(dt.task.name), by: {task_id = toString(dt.task.id)}
  ], on: {task_id}, fields: {detector_name}, kind: leftOuter
| fieldsAdd billable_gib = billable_usage / 1073741824
| fields task_id, detector_name, billable_gib, runs, estimated_cost, currency_code, valid_from, valid_to
```

## AI and Agent Queries

Indirect AI cost is Query BUEs with `ai_generated == true` only: queries issued by Platform AI tools (CoPilot/Assist, Dynatrace MCP). External clients such as dtctl set `agent` in `client_context`; they are normal API queries, not AI cost, even when an AI coding agent drives them. These are indirect AI costs on top of the direct `AI Units` / `AI Function Standard Call` BUEs ([billing-event-types.md](billing-event-types.md#agentic-appengine)).

Sessions (only `ai_generated` rows carry `session_id`; it matches the session on the AI Units BUEs; `conversation_id` can be empty on Query BUEs):

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT" and endsWith(event.type, " - Query")
| filter ai_generated == true and isNotNull(session_id) and session_id != ""
| dedup {event.id, event.type}
| summarize {billable_usage = sum(billed_bytes),
    queries = countDistinct(query_id)},
    by: {session_id}
| fieldsAdd billable_gib = billable_usage / 1073741824
| sort billable_usage desc
| limit 20
```

## Bucket Drill-Down

BUE `usage.bucket` exists on Events and Digital Experience Monitoring only (0% on Logs, Traces, Files):

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT" and endsWith(event.type, " - Query")
| filter isNotNull(usage.bucket)
| dedup {event.id, event.type}
| summarize {billable_usage = sum(billed_bytes),
    queries = countDistinct(query_id)},
    by: {usage.bucket, event.type}
| fieldsAdd billable_gib = billable_usage / 1073741824
| sort billable_usage desc
| limit 20
```

Logs, Traces, Files: [Bucket Scan](#bucket-scan) (QEE).

## Run Counts

Required whenever you say how often something ran. Count on the originating event:

| Source | Event | Count with |
|--------|-------|------------|
| Workflow | `WORKFLOW_EVENT` `WORKFLOW_EXECUTION` | `countDistinct(dt.automation_engine.workflow_execution.id)`, about 2 rows per run. See [workflow-total-cost.md](workflow-total-cost.md#how-often-did-the-workflow-run) |
| Detector (from BUE) | Query BUE | `countDistinctExact` of `dt.analyzer.execution_id` in `client_context` ([Detector Ranking](#detector-ranking)) |
| Detector (from AEE) | `ANALYZER_EXECUTION_EVENT` | `countDistinct(dt.analyzer.execution.start)` by `dt.task.id` |

## QEE Fallbacks

Use QEE (`QUERY_EXECUTION_EVENT`) only for the cases below, and state the case's reason in every answer. These rules apply to all of them:

- QEE `scanned_bytes` is diagnostic scan, NEVER cost. NEVER present a QEE total (including the ALERTING pool) as cost; rankings come from BUE.
- `scanned_bytes` = `scanned_bytes.included` + `scanned_bytes.on_demand`. Only `on_demand` is billable query volume; neither is cost on the rated path without a BUE. Report the included/on-demand split for every source you discuss; a source's QEE total alone never shows it is free or unscanned.
- One QEE row per bucket touched (count rule: [Rules](#rules)). QEE has no `event.id`; do not dedup it.
- `query_string` literals may be masked as `"*"`. A `"*"` is never a wildcard.
- Zero-rated queries (by user, app or queried data) and included volume (for example Logs on `Retain with Included Queries`, where QEE scan can be 100x the billed bytes) produce QEE rows but no BUE.

### Bucket Scan

Reason: BUE has no `usage.bucket` on Logs, Traces and Files. For Logs, first check for `Retain with Included Queries` BUEs; a high `included_gib` confirms it. A row with null `table` and `bucket` can have `scanned_gib` but no split: report it as unsplit, not as on-demand. Optional, one capability only: add `| filter table == "<table>"` after the `event.kind` filter.

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| summarize {scanned_gib = sum(scanned_bytes) / 1073741824,
    included_gib = sum(coalesce(toDouble(scanned_bytes.included), 0.0)) / 1073741824,
    on_demand_gib = sum(coalesce(toDouble(scanned_bytes.on_demand), 0.0)) / 1073741824,
    queries = countDistinct(query_id)},
    by: {table, bucket}
| sort scanned_gib desc
| limit 20
```

### Single-Query Details

Reason: query text, duration and tables are not BUE fields. Step 1: top `query_id`s from BUE. Tied top `billable_gib` means a repeated workload: report how many rows tie and their callers instead of sampling ids from the tie (raise `limit` if all 5 tie).

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT" and endsWith(event.type, " - Query")
| dedup {event.id, event.type}
| summarize billable_usage = sum(billed_bytes), by: {query_id, user.email}
| fieldsAdd billable_gib = billable_usage / 1073741824
| sort billable_usage desc
| limit 5
```

Step 2: filter QEE by those ids, aggregated per `query_id`.

```dql-template
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter in(query_id, array("<query_id_1>", "<query_id_2>"))
| summarize {scanned_gib = sum(scanned_bytes) / 1073741824,
    max_duration_ms = max(execution_duration_ms),
    tables = collectDistinct(table),
    query_string = takeFirst(query_string)},
    by: {query_id}
```

### QEE Exceeds BUE

Reason: zero-rated and included-volume queries produce no BUE. Compare QEE totals per source joined with deduped BUE totals per source (one row per source, not a bulk join). A high `included_gib` means included volume; a high `on_demand_gib` with no BUE means zero-rated.

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| fieldsAdd attribution = coalesce(client.application_context, client.internal_service_context, client.source, client.workflow_context, client.function_context, client.client_context, "unknown")
| summarize {scanned_gib = sum(scanned_bytes) / 1073741824,
    included_gib = sum(coalesce(toDouble(scanned_bytes.included), 0.0)) / 1073741824,
    on_demand_gib = sum(coalesce(toDouble(scanned_bytes.on_demand), 0.0)) / 1073741824},
    by: {attribution}
| join [
    fetch dt.system.events, from: -7d
    | filter event.kind == "BILLING_USAGE_EVENT" and endsWith(event.type, " - Query")
    | dedup {event.id, event.type}
    | fieldsAdd attribution = coalesce(client.application_context, client.internal_service_context, client.source, client.workflow_context, client.function_context, client.client_context, "unknown")
    | summarize billable_gib = sum(toDouble(billed_bytes)) / 1073741824, by: {attribution}
  ], on: {attribution}, fields: {billable_gib}, kind: leftOuter
| fieldsAdd billable_gib = coalesce(billable_gib, 0.0)
| fieldsAdd gap_gib = scanned_gib - billable_gib
| sort gap_gib desc
| limit 20
```
