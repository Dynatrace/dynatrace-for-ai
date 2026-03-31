# Cost Investigation

Step-by-step workflows for investigating what is driving DPS costs. Covers
query scan costs (ALERTING pool / detectors, Automation workflows) and
composite cost attribution across multiple billing signals.

## Contents

- [Common Principles](#common-principles)
- [Query Cost Attribution](#query-cost-attribution)
- [Workflow Total Cost](#workflow-total-cost)
  - [Three-Signal Checklist](#three-signal-checklist)
  - [Cross-Event Field Reference](#cross-event-field-reference)
  - [Step 1 — Query Scan Cost (QEE)](#step-1--query-scan-cost-qee)
  - [Step 2 — AppEngine Function Cost (BUE)](#step-2--appengine-function-cost-bue)
  - [Step 3 — Automation Workflow BUE Cost](#step-3--automation-workflow-bue-cost)
  - [Per-Workflow Deep Dive](#per-workflow-deep-dive)
  - [Owner Identification](#owner-identification)
- [Best Practices](#best-practices)

## Common Principles

1. **BUE is billable truth, QEE is diagnostic** — BUE Query events reflect
   actual billed scan volumes; QEE provides per-query execution details
   (`client.client_context`, query text, duration). Always start cost
   investigations with BUE, then drill into QEE for attribution detail.

2. **Sample first** — Before querying 30 days, run a 7-day discovery query
   to understand field availability. `client.source`, `client.function_context`,
   and `client.workflow_context` vary by pool; confirm they are populated before
   building attribution queries.

3. **`dt.system.events` cannot be a lookup source** — DQL `lookup` requires
   `data json:"""..."""` inline lookups. Use `data json` or materialize results
   when joining across event kinds.

4. **Dedup billing events** — BUE events can be refreshed (updated); always
   `| dedup event.id` before aggregating to avoid double-counting.

## Query Cost Attribution

Step-by-step guide for "what is driving DQL query scan costs?":

### Step 1 — Top Sources by Billable Scan (BUE)

Start with BUE — billable truth, grouped by `client.source`:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type,
    "Log Management & Analytics - Query",
    "Events - Query",
    "Traces - Query",
    "Files - Query")
| dedup event.id
| filter isNotNull(client.source)
| summarize total_billed_gib = sum(toDouble(billed_bytes) / 1073741824),
    by: {client.source, event.type}
| sort total_billed_gib desc
| limit 20
```

### Step 2 — Identify Source Type

| `client.source` pattern | Source type | Next step |
|-------------------------|-------------|-----------|
| `https://.../document/...` | Dashboard URL | Load dashboard to see tile queries |
| UUID-like string | Detector `objectId` | Cross-ref with `ANALYZER_EXECUTION_EVENT.dt.task.id` |
| `builtin:davis.anomaly-detectors/...` | Detector type name | Parse `client.client_context` in QEE (Step 4) |
| `dynatrace.automations:...` | Automation function | Cross-ref with `WORKFLOW_EVENT` |
| `dt.*` service name | Internal platform service | Review with platform team |

### Step 3 — Drill Into QEE for Details

```dql-template
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter client.source == "<top source from step 1>"
| summarize queries = count(),
    total_scanned_gib = sum(scanned_bytes) / 1073741824,
    avg_duration_ms = avg(execution_duration_ms),
    by: {table, status}
| sort total_scanned_gib desc
```

### Step 4 — Per-Detector Attribution (ALERTING pool)

For ALERTING sources, parse `client.client_context` to get per-detector scan
volume. **QEE only** — not available on BUE:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter query_pool == "ALERTING"
| parse client.client_context, "JSON:ctx"
| summarize queries = count(),
    total_scanned_gib = sum(scanned_bytes) / 1073741824,
    by: {task_id = ctx[`dt.task.id`], task_group = ctx[`dt.task.group`]}
| sort total_scanned_gib desc
| limit 20
```

### Step 5 — Resolve Detector Name

Cross-reference `task_id` (settings `objectId`) with `ANALYZER_EXECUTION_EVENT`:

```dql-template
fetch dt.system.events, from: -7d
| filter event.kind == "ANALYZER_EXECUTION_EVENT"
| filter dt.task.id == "<objectId from step 4>"
| summarize count(), by: {dt.task.name, dt.task.id, dt.task.result_status}
```

> **Combining Steps 4+5:** To resolve all detector names in a single query,
> `append` the ANALYZER_EXECUTION_EVENT fetch (keyed by `task_id = dt.task.id,
> detector_name = dt.task.name`) to Step 4's result, then `summarize` by
> `task_id` using `takeMax(total_scanned_gib)` and `takeFirst(detector_name)`.

### Step 6 — Estimate Cost

Apply rate card from [cost-estimations.md](cost-estimations.md) → Public Rate Card.

---

## Workflow Total Cost

Automation workflows generate costs across **three separate billing signals**.
Missing any one gives an incomplete picture.

### Three-Signal Checklist

| # | Signal | BUE `event.type` | What it measures |
|---|--------|------------------|-----------------|
| 1 | Query Execution | `Events - Query`, `Log Management & Analytics - Query`, `Traces - Query`, `Files - Query` | DQL scans run inside workflow scripts |
| 2 | AppEngine Functions | `AppEngine Functions - Small` | JS/Python function invocations |
| 3 | Automation Workflow | `Automation Workflow` | Workflow execution time (workflow-hours) |

Always check all three before concluding what a workflow costs.

### Cross-Event Field Reference

Field names differ across event kinds **and** across BUE event types. BUE Query
events lack workflow attribution fields — use QEE AUTOMATION pool instead.

| Concept | QEE (AUTOMATION pool) | `WORKFLOW_EVENT` | BUE `Automation Workflow` | BUE `AppEngine Functions` | BUE Query types |
|---------|----------------------|------------------|--------------------------|--------------------------|----------------|
| Workflow ID | `client.workflow_context` | `dt.automation_engine.workflow.id` | `workflow.id` | `workflow.id` | ❌ not available |
| Workflow name | — | `dt.automation_engine.workflow.title` | `workflow.title` | — | ❌ not available |
| Function/action | `client.function_context` | `dt.automation_engine.action.name` | — | `function.id` | `client.function_context` |
| User ID | `user.id` | `dt.automation_engine.workflow_execution.actor` | `workflow.actor` | `user.id` | `user.id` |
| Trigger type | — | `dt.automation_engine.workflow_execution.trigger.type` | `workflow.trigger_type` | — | — |

> **Critical:** BUE Query events (`Events - Query`, etc.) have NO `workflow.id`
> or `client.workflow_context` field. To attribute query scan costs to a workflow,
> use QEE AUTOMATION pool with `client.workflow_context`.
>
> **Tip:** When a field returns no results, sample raw events first:
> `| limit 3` (without `fields`) to see all available fields on the event.

### Step 1 — Query Scan Cost (QEE)

BUE Query events lack workflow attribution fields. Use QEE AUTOMATION pool
(`client.workflow_context`) to attribute query scan volume to a workflow:

```dql-template
fetch dt.system.events, from: -30d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter query_pool == "AUTOMATION"
| filter client.workflow_context == "<workflow-uuid>"
| summarize total_scanned_gib = sum(scanned_bytes) / 1073741824,
    queries = count(),
    by: {table}
| sort total_scanned_gib desc
```

> **Note:** QEE `scanned_bytes` is diagnostic, not billable. For billable totals,
> sum BUE Query events by `client.source` pattern matching (see
> [Query Cost Attribution](#query-cost-attribution)), then correlate with QEE for
> per-workflow breakdown.

### Step 2 — AppEngine Function Cost (BUE)

```dql-template
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "AppEngine Functions - Small"
| dedup event.id
| filter workflow.id == "<workflow-uuid>"
| summarize total_invocations = sum(billed_invocations)
| fieldsAdd estimated_cost_usd = total_invocations / 1000000.0 * 1000
```

### Step 3 — Automation Workflow BUE Cost

Workflow-hours = distinct `workflow.id` per hour. Bin by hour first, then sum:

```dql-template
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Automation Workflow"
| dedup event.id
| filter workflow.id == "<workflow-uuid>"
| fieldsAdd hour = bin(timestamp, 1h)
| summarize hourly_wf = countDistinct(workflow.id), by: {hour}
| summarize total_workflow_hours = sum(hourly_wf)
| fieldsAdd estimated_cost_usd = total_workflow_hours / 10000.0 * 300
```

> **Note:** Each distinct `workflow.id` appearing within a given hour contributes
> 1 workflow-hour. The standard `coalesce()` pattern cannot capture this; query
> it separately.

### Per-Workflow Deep Dive

First, identify top workflows by query scan volume using QEE AUTOMATION pool
(BUE Query events lack workflow attribution):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter query_pool == "AUTOMATION"
| filter isNotNull(client.workflow_context)
| summarize total_scanned_gib = sum(scanned_bytes) / 1073741824,
    queries = count(),
    by: {client.workflow_context}
| sort total_scanned_gib desc
| limit 20
```

Then resolve the workflow name from `WORKFLOW_EVENT`:

```dql-template
fetch dt.system.events, from: -30d
| filter event.kind == "WORKFLOW_EVENT"
| filter dt.automation_engine.workflow.id == "<uuid from above>"
| summarize count(), by: {dt.automation_engine.workflow.id, dt.automation_engine.workflow.title}
| limit 1
```

### Owner Identification

Use this priority order to identify who owns an expensive workflow:

| Priority | Field | Event Kind / BUE Type | Notes |
|----------|-------|----------------------|-------|
| 1 | `workflow.owner` | BUE `Automation Workflow` | Most reliable — set at creation |
| 2 | `dt.automation_engine.workflow_execution.actor` | `WORKFLOW_EVENT` | UUID, not email — resolve via user API |
| 3 | `user.email` | BUE Query types | Available when query ran under a user context |
| 4 | `user.id` | BUE / QEE | UUID — resolve via user API if needed |

Quick owner lookup (uses BUE `Automation Workflow` which has `workflow.owner`):

```dql-template
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Automation Workflow"
| dedup event.id
| filter workflow.id == "<workflow-uuid>"
| filter isNotNull(workflow.owner)
| summarize count(), by: {workflow.id, workflow.title, workflow.owner}
| limit 1
```

---

## Best Practices

1. **Always check all three billing signals** for workflows — a query scan spike
   may be just one of multiple cost contributors.
2. **Use BUE `client.source` for ALERTING attribution** — covers ~50% of
   detector queries; use `client.client_context` parse on QEE for the full
   per-detector breakdown.
3. **`user.id` is never detector-specific** — all anomaly detectors share the
   same service account; use `dt.task.id` / `client.client_context` instead.
4. **Sample first, then extend to 30d** — verify field availability on a 7-day
   slice before running expensive 30-day queries.
5. **Dedup every BUE aggregation** — `| dedup event.id` prevents double-counting
   from BUE refresh events.
