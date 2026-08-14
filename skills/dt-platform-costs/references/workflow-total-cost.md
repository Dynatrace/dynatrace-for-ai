# Workflow Total Cost

Composite cost attribution for automation workflows. Workflows generate costs
across **four separate billing signals** — missing any one gives an incomplete
picture.

## Contents

- [Common Principles](#common-principles)
- [Four-Signal Checklist](#four-signal-checklist)
- [Cross-Event Field Reference](#cross-event-field-reference)
- [Step 1 — Query Scan Cost](#step-1--query-scan-cost)
- [Step 2 — AppEngine Function Cost (BUE)](#step-2--appengine-function-cost-bue)
- [Step 3 — Automation Workflow BUE Cost](#step-3--automation-workflow-bue-cost)
- [Step 4 — AI Invocation Cost (BUE)](#step-4--ai-invocation-cost-bue)
- [Per-Workflow Deep Dive](#per-workflow-deep-dive)
- [How Often Did the Workflow Run](#how-often-did-the-workflow-run)
- [Owner Identification](#owner-identification)
- [Best Practices](#best-practices)

## Common Principles

1. **BUE is billable truth, QEE is diagnostic** — BUE Query events reflect
   actual billed scan volumes; QEE provides per-query execution details
   (`client.client_context`, query text, duration). Always start cost
   investigations with BUE, then drill into QEE for attribution detail.

2. **Sample first** — Before building any attribution query, run
   `| limit 3` (without `| fields`) on the target event type to discover
   available fields. When a field returns no results, sample raw events first.

3. **Dedup billing events** — Use `| dedup event.id` for single-type queries
   (all templates below filter to one `event.type`). See
   [Billing Event Deduplication](billing-capabilities.md#billing-event-deduplication).

4. **Rolling windows are acceptable here** — Investigation queries use
   `from: -7d` or `from: -30d` for diagnostic analysis. For billing totals
   that must match the Account Management Portal, use explicit UTC midnight
   boundaries per [billing-capabilities.md § Billing Timeframe Boundaries](billing-capabilities.md#billing-timeframe-boundaries).

## Four-Signal Checklist

| # | Signal | BUE `event.type` | What it measures |
|---|--------|------------------|-----------------|
| 1 | Query Execution | `Events - Query`, `Log Management & Analytics - Query`, `Traces - Query`, `Files - Query` | DQL scans run inside workflow scripts |
| 2 | AppEngine Functions | `AppEngine Functions - Small` | JS/Python function invocations |
| 3 | Automation Workflow | `Automation Workflow` | Workflow existence time (workflow-hours) — **STANDARD workflows only** |
| 4 | AI Invocations | `AI Units`, `AI Function Standard Call` | AI invocations from workflow AI actions — `usage.quantity.billable` (Units) for AI Units, `billed_invocations` for AI Function Standard Call |

Always check all four before concluding what a workflow costs.

> **Signal 3 applies to `STANDARD` workflows only.** `SIMPLE` and `DRAFT` workflows
> emit no `Automation Workflow` BUE — cost lives in signals 1, 2, and (if the
> workflow uses AI actions) 4. Only Signal 3 is inapplicable.
> Resolve `dt.automation_engine.workflow.type` from `WORKFLOW_EVENT` before
> interpreting Signal 3. See
> [Dynatrace Automation billing docs](https://docs.dynatrace.com/docs/license/capabilities/automation/automation).

## Cross-Event Field Reference

Field names differ across event kinds **and** across BUE event types.

| Concept | QEE (AUTOMATION pool) | `WORKFLOW_EVENT` | BUE `Automation Workflow` | BUE `AppEngine Functions` | BUE Query types |
|---------|----------------------|------------------|--------------------------|--------------------------|----------------|
| Workflow ID | `client.workflow_context` | `dt.automation_engine.workflow.id` | `workflow.id` | `workflow.id` | `client.workflow_context` |
| Workflow name | — | `dt.automation_engine.workflow.title` | `workflow.title` | — | ❌ not available |
| Workflow type | — | `dt.automation_engine.workflow.type` (`STANDARD` / `SIMPLE` / `DRAFT`) | — | — | — |
| Function/action | `client.function_context` | `dt.automation_engine.action.name` | — | `function.id` | `client.function_context` |
| User ID | `user.id` | `dt.automation_engine.workflow_execution.actor` | `workflow.actor` | `user.id` | `user.id` |
| Trigger type | — | `dt.automation_engine.workflow_execution.trigger.type` | `workflow.trigger_type` | — | — |

> **Critical:** BUE Query events (`Events - Query`, etc.) have the `client.workflow_context` field available.
> To attribute query scan costs to a workflow when no `client.workflow_context` field is given (value is `null`),
> use QEE AUTOMATION pool with the QEE's `client.workflow_context`.
>
> **Tip:** When a field returns no results, sample raw events first:
> `| limit 3` (without `fields`) to see all available fields on the event.

## Step 1 — Query Scan Cost

BUE Query events carry `client.workflow_context` (AUTOMATION-pool queries), so
read the workflow's **billable** scan straight from BUE — billable truth, and
the figure that reflects actual cost. Do not rank on QEE `scanned_bytes`: it is
diagnostic and overstates cost wherever queries are zero-rated, so a scan-based
ranking can order workflows differently from their actual bill.

> **Multi-type dedup:** this query spans multiple BUE Query `event.type`s, so
> use compound `dedup {event.id, event.type}`. Plain `dedup event.id` would
> silently drop same-id siblings across types (an id can repeat across
> `Logs`/`Events`/`Traces`/`Files` query events).

```dql-template
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type, "Log Management & Analytics - Query", "Events - Query", "Traces - Query", "Files - Query")
| dedup {event.id, event.type}
| filter client.workflow_context == "<workflow-uuid>"
| summarize total_billed_gib = sum(toDouble(billed_bytes) / 1073741824), by: {event.type}
| sort total_billed_gib desc
```

**Fallback when BUE attribution is null:** `client.workflow_context` is a
recently added BUE attribute, so older BUEs in the retention window emit it as
null (this is time-based, not tenant-specific — see
[query-cost-attribution.md § Step 1a](query-cost-attribution.md#step-1a--coverage-check)
for a coverage check).
Where it is null, attribute via QEE AUTOMATION pool — this yields diagnostic
`scanned_bytes`, not billable bytes, so use it only to fill coverage gaps:

```dql-template
fetch dt.system.events, from: -30d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter query_pool == "AUTOMATION"
| filter client.workflow_context == "<workflow-uuid>"
| summarize total_scanned_gib = sum(scanned_bytes) / 1073741824,
    dql_statements = countDistinct(query_id),
    qee_rows = count(),
    by: {table}
| sort total_scanned_gib desc
```

> **⛔ QEE count ≠ workflow run count.** `count()` on QEE counts bucket-touches
> (one row per bucket per DQL statement), `countDistinct(query_id)` counts DQL
> statements. **Neither is the number of times the workflow ran** — one run
> fires multiple DQL statements, each touching multiple buckets. To get actual
> run count and frequency, use the
> [WORKFLOW_EXECUTION query](#how-often-did-the-workflow-run) below. Never write
> "ran N times" or compute a per-second/per-minute rate from a QEE count.

## Step 2 — AppEngine Function Cost (BUE)

```dql-template
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "AppEngine Functions - Small"
| dedup event.id
| filter workflow.id == "<workflow-uuid>"
| summarize total_invocations = sum(billed_invocations)
```

## Step 3 — Automation Workflow BUE Cost

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
```

> **Note:** Each distinct `workflow.id` appearing within a given hour contributes
> 1 workflow-hour. The standard `coalesce()` pattern cannot capture this; query
> it separately.

> **Output rule:** Present `total_invocations` and `total_workflow_hours` in
> native units. Apply **SKILL.md § Cost Ranking Rules** for any cross-capability
> cost comparison — do not compute or display dollar estimates from these values.
> For `SIMPLE`/`DRAFT` workflows, label Signal 3 **"N/A (workflow type)"** — not `0` or `missing`.

## Step 4 — AI Invocation Cost (BUE)

If the workflow uses AI/LLM actions, also check Signal 4 BUEs:

**AI Function Standard Call** (non-LLM tool usage):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "AI Function Standard Call"
| dedup event.id
| filter workflow.id == "<workflow-uuid>"
| summarize total_invocations = sum(billed_invocations)
```

**AI Units** (AI/LLM work):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "AI Units"
| dedup event.id
| filter workflow.id == "<workflow-uuid>"
| summarize total_units = sum(`usage.quantity.billable`)
```

## Per-Workflow Deep Dive

First, identify the top workflows by **billable** query scan. BUE Query events
carry `client.workflow_context` (AUTOMATION-pool queries), so rank on BUE
`billed_bytes` — not QEE `scanned_bytes`. QEE overstates cost wherever queries
are zero-rated, so a `scanned_bytes` ranking can put a heavily-scanning but
partly zero-rated workflow above the one that actually costs the most:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type, "Log Management & Analytics - Query", "Events - Query", "Traces - Query", "Files - Query")
| dedup {event.id, event.type}
| filter isNotNull(client.workflow_context)
| summarize total_billed_gib = sum(toDouble(billed_bytes) / 1073741824),
    by: {client.workflow_context}
| sort total_billed_gib desc
| limit 20
```

> **Coverage fallback:** where `client.workflow_context` is null on the BUE
> (recently added attribute — older BUEs in the retention window carry no
> value; see
> [query-cost-attribution.md § Step 1a](query-cost-attribution.md#step-1a--coverage-check)),
> fall back to QEE AUTOMATION pool (`client.workflow_context`) for a diagnostic
> `scanned_bytes` ranking. Never rank by `qee_events` (bucket-touches). See
> [How Often Did the Workflow Run](#how-often-did-the-workflow-run).

Then resolve the workflow name and type from `WORKFLOW_EVENT` — always pull
`workflow.type` to know whether Signal 3 applies (`STANDARD`) or not (`SIMPLE`/`DRAFT`):

```dql-template
fetch dt.system.events, from: -30d
| filter event.kind == "WORKFLOW_EVENT"
| filter dt.automation_engine.workflow.id == "<uuid from above>"
| fields dt.automation_engine.workflow.id, dt.automation_engine.workflow.title, dt.automation_engine.workflow.type
| limit 1
```

> **Two caveats when resolving workflow IDs:**
> 1. **No `Automation Workflow` BUE for `SIMPLE`/`DRAFT`.** These types emit no
>    Signal 3 by design — check `dt.automation_engine.workflow.type` on
>    `WORKFLOW_EVENT` before interpreting a missing Signal 3.
> 2. **Event history retains deleted workflows.** `WORKFLOW_EVENT`,
>    `Automation Workflow` BUE, and QEE all keep rows for as long as their
>    events bucket retention allows, so an ID that resolves in events may
>    already have been deleted in the platform. Event data alone cannot
>    distinguish "still exists" from "deleted but recent" — treat resolution
>    via events as a name/type lookup, not proof of existence.

## How Often Did the Workflow Run

**The number of times a workflow ran lives on `WORKFLOW_EVENT`** with
`event.type == "WORKFLOW_EXECUTION"` — but count it with
`countDistinct(dt.automation_engine.workflow_execution.id)`, **not** bare
`count()`.

> ### ⛔ Two layers of `count()` fan-out
>
> 1. **QEE** (`QUERY_EXECUTION_EVENT`) `count()` = bucket-touches; neither it nor
>    `countDistinct(query_id)` (= DQL statements) is a run count.
> 2. **`WORKFLOW_EXECUTION` `count()` is also not a run count** — it is a
>    state-change event, so a completed run emits ≈2 rows (a `RUNNING` row plus a
>    terminal `SUCCESS`/`ERROR`/`CANCELLED` row) that share one
>    `dt.automation_engine.workflow_execution.id`. Count runs with
>    `countDistinct(dt.automation_engine.workflow_execution.id)`.
>
> Example of the fan-out: a workflow running ≈1/min emits ≈2 `WORKFLOW_EXECUTION`
> rows per run (the ≈2× is structural — a `RUNNING` plus a terminal row) and many
> more QEE events (one per bucket per statement, so that factor *varies* with the
> queries). A raw `count()` on either is therefore several× the true run count.
> Derive frequency **only** from distinct executions ÷ timespan.

```dql-template
fetch dt.system.events, from: -7d
| filter event.kind == "WORKFLOW_EVENT"
| filter event.provider == "AUTOMATION_ENGINE"
| filter event.type == "WORKFLOW_EXECUTION"
| filter in(dt.automation_engine.workflow.id, "<workflow-uuid-1>", "<workflow-uuid-2>")
| summarize
    workflow_runs = countDistinct(dt.automation_engine.workflow_execution.id),
    workflow_title = takeFirst(dt.automation_engine.workflow.title),
    by: {workflow_id = dt.automation_engine.workflow.id}
| sort workflow_runs desc
```

> - **Exclude editor test runs:** add `| filter dt.automation_engine.is_draft == false`.
> - **Why so often:** `dt.automation_engine.workflow_execution.trigger.type`
>   (`Schedule`/`Event`/`Manual`/`Workflow`) — a `Schedule` trigger is the usual
>   cause of thousands of runs/day.
> - **Hit the cap:** `event.type == "WORKFLOW_THROTTLED"` rows mean the workflow
>   exceeded its per-hour execution limit (`dt.automation_engine.throttle.limit`).
> - **Reporting both signals:** when QEE or row volume looks alarming, always
>   report the distinct workflow-execution count alongside it. A large gap
>   between any `count()` and
>   `countDistinct(dt.automation_engine.workflow_execution.id)` is expected
>   fan-out, not a spike. The QEE-to-run ratio is workflow-specific (depends on
>   how many DQL statements the script fires and how many buckets each touches)
>   and is **not a diagnostic signal on its own**.

## Owner Identification

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
| fields workflow.id, workflow.title, workflow.owner
| limit 1
```

## Best Practices

1. **Always check all four billing signals** for workflows — a query scan spike
   may be just one of multiple cost contributors.
2. **Sample first, then extend to 30d** — verify field availability on a 7-day
   slice before running expensive 30-day queries.
3. **Dedup every BUE aggregation** — `| dedup event.id` is safe here
   (single-type queries). See
   [Billing Event Deduplication](billing-capabilities.md#billing-event-deduplication).
