# Billing Capabilities

How billing usage event (BUE) types map to capabilities and units. Companion to
[billing-event-types.md](billing-event-types.md) which documents per-type
fields and metering intervals.

> **DPS only.** The capability mapping and unit conversion table below apply
> exclusively to the Dynatrace Platform Subscription (DPS) license model — not
> to classic license models.

> **Reminder:** Billing events can be refreshed — always use
> `| dedup {event.id, event.type}` before aggregating to prevent double-counting.
> `event.id` is not unique across event types — using `| dedup event.id` alone
> silently drops rows in multi-type queries. Single-type queries (filtered to one
> `event.type`) are safe with plain `| dedup event.id`.
> See [Billing Event Deduplication](#billing-event-deduplication).

## Contents

- [BUE-to-Capability Mapping](#bue-to-capability-mapping)
  - [Files→Events Remap](#files-to-events-remap)
- [Unit Conversion Table](#unit-conversion-table)
- [Cross-Capability Usage (4 Queries)](#cross-capability-usage-4-queries)
  - [Quick Overview — Combined Query](#quick-overview--combined-query)
  - [Base Usage](#base-usage)
  - [Workflow + SPM](#workflow--spm)
  - [Metrics Ingest — Billable Volume](#metrics-ingest--billable-volume)
  - [Traces Ingest — Billable Volume](#traces-ingest--billable-volume)
- [Period Comparison (WoW / MoM)](#period-comparison-wow--mom)
- [Included Volume](#included-volume)
  - [14-Day Limitation](#14-day-limitation)
  - [Metrics Ingest — Included Volume](#metrics-ingest--included-volume)
  - [Traces Ingest — Included Volume](#traces-ingest--included-volume)
  - [Longer Timeframes (Multi-Window Pattern)](#longer-timeframes-multi-window-pattern)
- [Billing Timeframe Boundaries](#billing-timeframe-boundaries)
  - [Billing Event Emission Lag](#billing-event-emission-lag)
- [Billing Event Deduplication](#billing-event-deduplication)
- [Best Practices](#best-practices)

## BUE-to-Capability Mapping

Most billing event types map 1:1 to a capability. The following types roll up
to a **different** capability for usage reporting:

| BUE Event Type | Capability |
|----------------|------------|
| `Files - Ingest & Process` | Events - Ingest & Process |
| `Files - Query` | Events - Query |
| `Files - Retain` | Events - Retain |

The [Base Usage](#base-usage) and [Combined Query](#quick-overview--combined-query)
aggregate by `event.type` as stored. When the user asks for results at the DPS
capability level, append the [Files→Events Remap](#files-to-events-remap) snippet to
collapse Files volumes into their parent Events capability.

### Files-to-Events Remap

Standalone snippet — append after `dedup {event.id, event.type}` and before
`summarize` when you need results grouped by capability (matching Account
Management):

```dql-snippet
// --- Files→Events Remap (append before summarize) ---
| fieldsAdd event.type = if(event.type == "Files - Ingest & Process", "Events - Ingest & Process",
    else: if(event.type == "Files - Query", "Events - Query",
    else: if(event.type == "Files - Retain", "Events - Retain",
    else: event.type)))
```

> **When to use:** When the user asks for results at the DPS capability level
> (not per billing event type), or when comparing against Account Management.
> Omit when you need per-event-type granularity (e.g., showing Files volumes
> separately).

## Unit Conversion Table

Convert raw billed field values to human-readable capability units. The
`unitDivisor` divides summed raw values into the unit shown on the capability
level in the Account Management Portal.

| Billed Field | unitDivisor | Capability Unit |
|-------------|-----------|----------------|
| `billed_gibibyte_hours` | 1 | GiB-hours |
| `billed_host_hours` | 1 | host-hours |
| `billed_msu_hours` | 1 | MSU-hours |
| `billed_container_hours` | 1 | container-hours |
| `billed_bytes` (Ingest/Query) | 1073741824 | GiB / GiB scanned |
| `billed_bytes` (Retain) | 25769803776 (1073741824 × 24) | GiB-days — hourly events each record 1/24th of a GiB-day |
| `billed_sessions` | 1 | sessions |
| `billed_replay_sessions` | 1 | replay captures |
| `billed_property_sessions` | 1 | properties/session |
| `billed_pod_hours` | 1 | pod-hours |
| `billed_synthetic_action_count` | 1 | synthetic actions |
| `billed_http_request_count` | 1 | synthetic requests |
| `billed_test_result_ingestion_count` | 1 | synthetic results |
| `billed_invocations` | 1 | invocations |
| `usage.quantity.billable` | 1 | Units |
| `database-instance-hours` | 1 | database-instance-hours |
| `data_points` | 1 | data points |
| `ingested_bytes` | 1073741824 | GiB |

> `usage.quantity.billable` is a generic field; its unit label is carried in the sibling `usage.unit` field (`"Units"` for AI Units). Sum `usage.quantity.billable` directly — no divisor needed.
## Cross-Capability Usage (4 Queries)

> ⚠️ **All 4 queries are required for complete coverage.** Use the
> [Combined Query](#quick-overview--combined-query) for totals, or run all 4
> individual queries below. The Metrics Ingest and Traces Ingest queries handle
> included volume deduction — skipping them produces **inflated numbers**.
> NEVER substitute your own query for Metrics/Traces Ingest.

| # | Query | Covers | Why Separate |
|---|-------|--------|-------------|
| 1 | [Base Usage](#base-usage) | All standard billing types (Logs, Events, Host, RUM, Synthetic, etc.) | Uses `coalesce` across billed fields |
| 2 | [Workflow + SPM](#workflow--spm) | Automation Workflow, Security Posture Management | Count-based metering (distinct per hour), not a billed field |
| 3 | [Metrics Ingest — Billable Volume](#metrics-ingest--billable-volume) | Metrics - Ingest & Process | Requires included volume deduction from host monitoring baseline |
| 4 | [Traces Ingest — Billable Volume](#traces-ingest--billable-volume) | Traces - Ingest & Process | Requires included volume deduction from Full-Stack monitoring baseline |

Apply the [Unit Conversion Lookup](cost-estimations.md#unit-conversion-lookup)
to convert raw values to capability units (GiB, GiB-days, etc.) for
**usage-only** reporting. For **cost ranking**, use the
[Full Inline Lookup for Cost Rankings](cost-estimations.md#full-inline-lookup-for-cost-rankings)
instead — it computes both `capability_usage` and `cost_weight` in DQL.

Replace `<START>` / `<END>` with explicit UTC midnight boundaries (see
[Billing Timeframe Boundaries](#billing-timeframe-boundaries)).

> **Usage only — no cost estimates.** These queries return raw/converted usage.
> For cost estimation, see [cost-estimations.md](cost-estimations.md).

### Quick Overview — Combined Query

All 4 queries below combined into a single `append`-chained query. Returns one
row per event.type with `{event.type, billable_usage}`. Use for totals only;
use individual queries for per-source detail (e.g., `monitoring_source`
breakdown for Metrics/Traces).

> **14-day limit** — Metrics Ingest and Traces Ingest sub-queries use
> `timeseries` for included volume metrics.

> **Per-sub-query timeframes.** Each sub-query has its own `to:` boundary —
> see the individual query sections below and
> [Billing Event Emission Lag](#billing-event-emission-lag) for rationale.

```dql-snippet
// Query 1 — Base Usage (uses <END_PLUS_2H> + coalesce(usage.start, timestamp) guard)
<Base Usage>
| summarize billable_usage = sum(usage), by: {event.type}

// Query 2 — Workflow + SPM (uses <END>, NOT <END_PLUS_5H>)
// billable_usage = distinct workflow/node per hour, NOT execution count
| append [
  <Workflow + SPM>
  | summarize billable_usage = toDouble(count()), by: {event.type}
]

// Query 3 — Metrics Ingest — Billable Volume (uses <END_PLUS_5H> + usage.start filter)
| append [
  <Metrics Ingest — Billable Volume>
  | summarize billable_usage = sum(billable), by: {event.type}
]

// Query 4 — Traces Ingest — Billable Volume (uses <END>)
| append [
  <Traces Ingest — Billable Volume>
  | fields billable_usage = fullstack + otlp + serverless, event.type
]

| sort event.type asc
```

### Base Usage

All standard billing types **except** Workflow, SPM, Metrics Ingest, and Traces
Ingest (covered by the other queries — this query excludes them because they
require different metering logic).

> **Emission lag handling.** Some billing event types have emission lag up to
> ~80 minutes between `usage.start` and `timestamp` (see
> [Emission Lag table](#billing-event-emission-lag)). A naive `to: <END>` misses
> late-arriving events. The query extends `to:` by +2h and uses
> `coalesce(usage.start, timestamp)` as the effective time boundary guard. For
> types without `usage.start` (Retain, Query, AppEngine), `timestamp` serves as
> the period anchor — these events are never forward-dated, so the guard
> correctly excludes next-period data.

```dql-template
fetch dt.system.events, from: "<START>", to: "<END_PLUS_2H>"
| filter event.kind == "BILLING_USAGE_EVENT"
| filter not in(event.type, {"Automation Workflow", "Security Posture Management", "Metrics - Ingest & Process", "Traces - Ingest & Process"})
| fieldsAdd effective_start = coalesce(usage.start, timestamp)
| filter effective_start >= toTimestamp("<START>") and effective_start < toTimestamp("<END>")
| fieldsAdd usage = coalesce(billed_gibibyte_hours, billed_host_hours, billed_msu_hours,
    billed_container_hours, billed_bytes, billed_sessions, billed_replay_sessions,
    billed_property_sessions, billed_pod_hours, billed_synthetic_action_count,
    billed_http_request_count, billed_test_result_ingestion_count, billed_invocations,
    `usage.quantity.billable`, `database-instance-hours`)
| dedup {event.id, event.type}
```

> **`<END_PLUS_2H>`** = the `<END>` timestamp + 2 hours. Example: if `<END>` is
> `2026-04-28T00:00:00Z`, then `<END_PLUS_2H>` is `2026-04-28T02:00:00Z`. This
> covers the worst-case RUM Property emission lag (~80 min) with margin.

### Workflow + SPM

Count-based metering — distinct workflows per hour, distinct K8s nodes per
hour. The `count()` result represents **workflow-hours** for Automation Workflow
(distinct `workflow.id` per 1-hour bucket) and **node-hours** for SPM (distinct
`dt.entity.kubernetes_node` per 1-hour bucket):

```dql-template
fetch dt.system.events, from: "<START>", to: "<END>"
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type, { "Automation Workflow", "Security Posture Management"})
| fieldsAdd utc_hour = bin(timestamp, 1h)
| fieldsAdd dedup_key = if(event.type == "Automation Workflow", record(utc_hour, workflow.id))
| fieldsAdd dedup_key = if(event.type == "Security Posture Management", record(utc_hour, dt.entity.kubernetes_node), else: dedup_key)
| dedup dedup_key
```

### Metrics Ingest — Billable Volume

Metrics Ingest with included volume deduction. See
[Metrics Ingest — Included Volume](#metrics-ingest--included-volume) for how
the deduction works.

> **14-day limit** — uses `timeseries` for included volume metrics. For longer
> timeframes, use the [multi-window pattern](#longer-timeframes-multi-window-pattern).

> **⚠️ Silent coarsening risk.** The `4 * 900` and `4 * 1500` multipliers
> assume 4 intervals per hour (15-minute intervals). If the window exceeds 15
> days, the interval silently doubles to 30 minutes, halving the included
> volume calculation. Always keep each window ≤ 14 days. See
> [14-Day Limitation](#14-day-limitation).

> **Emission lag:** This query extends `to:` by +5 hours and filters on
> `usage.start` (via `toTimestamp()`) to handle billing event emission delay.
> See [Billing Event Emission Lag](#billing-event-emission-lag).

> **Array alignment:** Both inner `timeseries` commands in the `join` use
> `from: "<START>", to: "<END_PLUS_5H>"` — matching the outer `fetch` boundary.
> NEVER omit these; mismatched array lengths corrupt element-wise comparison and
> collapse billable values to zero.

```dql-template
fetch dt.system.events, from: "<START>", to: "<END_PLUS_5H>"
| filter event.kind == "BILLING_USAGE_EVENT" and event.type == "Metrics - Ingest & Process"
| filter usage.start >= toTimestamp("<START>") and usage.start < toTimestamp("<END>")
| dedup event.id  // safe: single event.type filter above
| summarize total_data_points = toLong(sum(data_points)), by: {event.type, usage.start, monitoring_source}
| fieldsAdd monitoring_source = if(monitoring_source == "fullstack" or monitoring_source == "infrastructure", monitoring_source, else: "other")
| fieldsAdd utc_hour = bin(usage.start, 1h)
| makeTimeseries {total_usage = sum(total_data_points, default: 0)}, interval: 15m, time: usage.start, by: {event.type, utc_hour, monitoring_source}
| join [
    timeseries {included_usage = sum(dt.billing.full_stack_monitoring.usage, default: 0)}, interval: 15m, from: "<START>", to: "<END_PLUS_5H>", nonempty: true
    | fields monitoring_source = "fullstack", included_usage = 4 * 900 * included_usage[]
    | append [
        timeseries {included_usage = sum(dt.billing.infrastructure_monitoring.usage, default: 0)}, interval: 15m, from: "<START>", to: "<END_PLUS_5H>", nonempty: true
        | fields monitoring_source = "infrastructure", included_usage = 4 * 1500 * included_usage[]
    ]
  ], on: {monitoring_source}, fields: {included_usage}, kind: leftOuter
| fieldsAdd billable = if(isNotNull(included_usage) and total_usage[] > included_usage[], total_usage[] - included_usage[], else: 0)
| fieldsAdd billable = if(isNull(included_usage), total_usage, else: billable)
| fieldsAdd billable = arraySum(billable)
```

#### Metrics Ingest — Per-Day Breakdown

Use this variant when the user asks for a **day-by-day** breakdown. Apply two changes to the query above:

1. Add `utc_day` to the `makeTimeseries` group-by: replace `by: {event.type, utc_hour, monitoring_source}` with `by: {event.type, utc_day, utc_hour, monitoring_source}` — and add `| fieldsAdd utc_day = bin(usage.start, 24h)` before the existing `utc_hour` line.
2. Append after `arraySum(billable)`: `| summarize billable_data_points = sum(billable), by: {utc_day} | sort utc_day asc`

### Traces Ingest — Billable Volume

Traces Ingest with included volume deduction. See
[Traces Ingest — Included Volume](#traces-ingest--included-volume) for how
the deduction works.

> **14-day limit** — uses `timeseries` for included volume metrics. For longer
> timeframes, use the [multi-window pattern](#longer-timeframes-multi-window-pattern).

> **⚠️ Silent coarsening risk.** The `* 15` multipliers on `license_limit` and
> `configured_volume` (lines below) assume 15-minute `timeseries` intervals. If
> the window exceeds 15 days, the interval silently doubles to 30 minutes and
> deduction values are **halved** — producing inflated billable volumes with no
> error. Always keep each window ≤ 14 days. See
> [14-Day Limitation](#14-day-limitation).

```dql-template
fetch dt.system.events, from: "<START>", to: "<END>"
| filter event.kind == "BILLING_USAGE_EVENT" and event.type == "Traces - Ingest & Process"
| dedup event.id  // safe: single event.type filter above
| makeTimeseries {ingested_bytes = sum(ingested_bytes, default: 0)}, interval: 15m, time: usage.start, by: {event.type, licensing_type}, nonempty: true
| append [
    timeseries {
      license_limit = max(dt.billing.traces.maximum_included_fullstack_volume_per_minute),
      configured_volume = max(dt.billing.traces.maximum_configured_fullstack_volume_per_minute)
    }, interval: 15m, nonempty: true
    | fieldsAdd license_limit = license_limit[] * 15
    | fieldsAdd configured_volume = configured_volume[] * 15
    | fields license_limit, configured_volume, helper_zeroes = license_limit[] * 0, timeframe
  ]
| summarize {
    adaptive_volume = takeFirst(if(licensing_type == "fullstack-adaptive", ingested_bytes)),
    fixed_rate_volume = takeFirst(if(licensing_type == "fullstack-fixed-rate", ingested_bytes)),
    otlp_volume = takeFirst(if(licensing_type == "otlp-trace-ingest", ingested_bytes)),
    serverless_volume = takeFirst(if(licensing_type == "serverless", ingested_bytes)),
    license_limit = takeFirst(license_limit),
    configured_volume = takeFirst(configured_volume),
    helper_zeroes = takeFirst(helper_zeroes),
    event.type = takeFirst(event.type)
  }
| fieldsAdd adaptive_volume = coalesce(adaptive_volume, helper_zeroes),
    fixed_rate_volume = coalesce(fixed_rate_volume, helper_zeroes),
    otlp_volume = coalesce(otlp_volume, helper_zeroes),
    serverless_volume = coalesce(serverless_volume, helper_zeroes)
| fieldsAdd adaptive_volume_charged = if(configured_volume[] > license_limit[] AND adaptive_volume[] > license_limit[], adaptive_volume[] - license_limit[], else: 0)
| fieldsAdd lic_remain = if(license_limit[] - adaptive_volume[] > 0, license_limit[] - adaptive_volume[], else: 0)
| fieldsAdd fixed_rate_volume_charged = if(fixed_rate_volume[] - lic_remain[] > 0 AND isNotNull(license_limit[]), fixed_rate_volume[] - lic_remain[], else: 0)
| fieldsAdd fullstack = adaptive_volume_charged[] + fixed_rate_volume_charged[]
| fields event.type, fullstack = arraySum(fullstack), otlp = arraySum(otlp_volume), serverless = arraySum(serverless_volume)
```

> **Note:** `fullstack`, `otlp`, `serverless` values are in bytes. Divide by
> 1,073,741,824 for GiB.

## Period Comparison (WoW / MoM)

> **Do not use `event_count` for period comparisons.** Billing event counts
> reflect emission frequency, not consumption volume. A 20% increase in event
> count for Log Ingest does not mean 20% more GiB ingested — it may simply
> reflect a change in how often 15-minute billing slots are emitted.
>
> The query below is the **incorrect pattern** — it is preserved here only as a
> warning. Do not use it:
> ```text
> // ❌ WRONG — event_count is not a cost proxy
> fetch dt.system.events, from: -14d
> | filter event.kind == "BILLING_USAGE_EVENT"
> | dedup event.id
> | fieldsAdd week = if(timestamp >= now() - 7d, "current", else: "previous")
> | summarize event_count = count(), by: {event.type, week}
> ```
>
> For correct week-over-week or month-over-month cost comparison, use the
> [Period Comparison pattern](cost-estimations.md#period-comparison-wow--mom)
> in `cost-estimations.md`. It compares `capability_usage` (in capability units)
> across two explicit UTC midnight windows.

## Included Volume

Some capabilities include a baseline volume from host monitoring that is
deducted before billing. This affects **Metrics Ingest** and **Traces Ingest**
— the raw `data_points` / `ingested_bytes` fields on billing events represent
*total* usage, not *billed* usage.

The [Metrics Ingest — Billable Volume](#metrics-ingest--billable-volume) and
[Traces Ingest — Billable Volume](#traces-ingest--billable-volume) queries above already apply these
deductions. This section documents how the deduction works.

### 14-Day Limitation

> **Included volume queries are only correct for windows ≤ 15 days.** The
> `timeseries` command has a maximum bucket count of **1440**. At `interval:
> 15m`, this allows 15 days (15 × 96 = 1440). Windows exceeding this threshold
> trigger **silent auto-coarsening** — the interval doubles to 30 minutes
> without any error or warning.
>
> The deduction queries in this skill hardcode multipliers that assume
> 15-minute intervals (e.g., `license_limit[] * 15`, `4 * 900`). When the
> interval is coarsened to 30 minutes, these multipliers are wrong — included
> volume is halved, and billable volume is inflated by 1–5%.
>
> **Always use ≤ 14-day windows** (conservative margin). For longer periods,
> use the [multi-window pattern](#longer-timeframes-multi-window-pattern). For
> authoritative values, use Account Management (**Subscription** > **Overview**
> > **Cost and usage details**).

### Metrics Ingest — Included Volume

Host monitoring modes include a baseline of metric data points that are not
billed against the Metrics Ingest capability:

| Monitoring Mode | Included Data Points per GiB-hour |
|-----------------|----------------------------------|
| Full-Stack Monitoring | 3,600 (= `4 * 900` per 15-min interval) |
| Infrastructure Monitoring | 6,000 (= `4 * 1500` per 15-min interval) |

The `monitoring_source` field on Metrics Ingest billing events identifies the
source: `fullstack`, `infrastructure`, `discovery`, or `other`. Only `fullstack`
and `infrastructure` sources have included volume. Sources `discovery` and
`other` (cloud extensions, remote extensions, etc.) are always fully billed.

The billing calculation is:

```
billed_data_points = max(0, total_data_points - included_data_points)
```

**Included volume metrics:**

| Metric Key | Description |
|------------|-------------|
| `dt.billing.full_stack_monitoring.usage` | Current Full-Stack GiB-hours |
| `dt.billing.infrastructure_monitoring.usage` | Current Infrastructure GiB-hours |

### Traces Ingest — Included Volume

Full-Stack Monitoring includes a baseline of trace data volume. Traces from
Full-Stack monitored hosts and containers are only billed on the Traces Ingest
capability when they **exceed** this included volume. Traces from non-Full-Stack
sources (OTLP API, serverless) are always fully billed.

The `licensing_type` field on Traces Ingest billing events identifies the
source:

| Licensing Type | Description | Billed? |
|----------------|-------------|---------|
| `fullstack-adaptive` | OneAgent trace data exceeding included volume (with Adaptive Traffic Management configured) | Only the excess |
| `fullstack-fixed-rate` | OTLP traces from Full-Stack hosts/containers exceeding included volume | Only the excess |
| `otlp-trace-ingest` | OTLP traces from non-Full-Stack sources | Always fully billed |
| `serverless` | Traces from serverless environments | Always fully billed |

**Included volume metrics:**

| Metric Key | Description |
|------------|-------------|
| `dt.billing.traces.maximum_included_fullstack_volume_per_minute` | Included Full-Stack trace volume (bytes/min) |
| `dt.billing.traces.maximum_configured_fullstack_volume_per_minute` | Configured Adaptive Traffic Management limit (bytes/min) |

### Longer Timeframes (Multi-Window Pattern)

For timeframes exceeding 14 days, automatically split into consecutive
≤ 14-day windows, run the appropriate query per window, and sum results.
State the number of windows and present both per-window and summed totals.

> **⚠️ Off-by-one warning:** `to:` is exclusive. A window from Apr 14 to Apr
> 30 (`to: "2026-04-30T00:00:00Z"`) spans 16 days — this exceeds the 15-day
> threshold and triggers coarsening. Always verify that each window's
> `to: - from:` difference is ≤ 15 days (≤ 14 recommended).

## Billing Timeframe Boundaries

When users ask for billing data over "last N days", **always use explicit UTC
midnight boundaries** — not rolling `from: -Nd`:

- OK: `from: "2026-03-20T00:00:00Z", to: "2026-03-30T00:00:00Z"` — 10 complete
  UTC days, comparable with the Account Management Portal
- Bad: `from: -10d` — starts mid-day, first day is partial, totals won't match
  the Account Management Portal

This ensures billing totals are comparable with **Account Management >
Subscription > Overview > Cost and usage details**.

> **`to:` is exclusive.** The `to:` boundary is not included in the results.
> `from: "2026-04-06T00:00:00Z", to: "2026-04-13T00:00:00Z"` covers Apr 6–12
> (7 complete UTC days). When presenting date ranges to users, always label by
> the last *included* date, not by the `to:` timestamp.

### Billing Event Emission Lag

Billing events are emitted after the `usage.start` measurement window closes.
The lag between `usage.start` and `timestamp` (emission time) varies by type:

| Emission Lag | Event Types |
|---|---|
| **≈0 min** | Synthetic (all types), Ingest types (Logs, Events, Traces) — `timestamp` is set equal to `usage.start`, so fetch timeframe always captures them regardless of actual emission delay |
| **≈20 min** | Host monitoring (Full-Stack, Infrastructure, Foundation, Mainframe), RUM (sessions, replay), K8s Platform Monitoring, Code Monitoring, Security (Runtime App Protection, Runtime Vulnerability Analytics) |
| **≈75 min** | RUM Property |
| **≈few min** | Query types (Logs, Events, Traces, Files) — negligible for daily binning |
| **≈4 hours** | Metrics Ingest only |
| **N/A** | Retain types, AppEngine Functions - Small, AI Function Standard Call, AI Units, Workflow, SPM — no `usage.start` field; use `timestamp` for time-based logic |

For most types the lag is operationally negligible — events land within the
same hour they measure. The key consequence is for **daily binning**: always use
`bin(usage.start, 24h)` instead of `bin(timestamp, 1d)` to avoid day-boundary
shifts (see [Best Practice #5](#best-practices)).

#### Metrics Ingest — `to:` Extension

Because Metrics Ingest has ≈4-hour lag, queries that filter on `usage.start`
will miss late-arriving events if the `fetch` timeframe `to:` matches the
measurement window end exactly.

**Fix:** Extend `to:` by +5 hours in the Metrics Ingest sub-query only.
The `usage.start` filter keeps the measurement window accurate while the
extended `fetch` captures late events.

The other sub-queries (Workflow+SPM, Traces Ingest) are
**not affected**: Workflow+SPM fetches by `timestamp` (event creation time,
post-emission) and Traces Ingest re-buckets via `makeTimeseries time: usage.start`
without filtering on `usage.start` — late events are already captured by the
`fetch` timeframe.

The **Base Usage** sub-query handles emission lag by extending `to:` to
`<END_PLUS_2H>` and guarding on `coalesce(usage.start, timestamp)` — this
catches late Host/RUM/RUM Property events while the coalesce fallback to
`timestamp` prevents over-capturing next-period Retain/Query/AppEngine events
(which lack `usage.start`).

**NEVER apply +5h to all sub-queries in a combined query.** Only the Metrics
Ingest sub-query uses `<END_PLUS_5H>`; Base Usage uses `<END_PLUS_2H>` (with
`effective_start` guard); all others use plain `<END>`.

## Billing Event Deduplication

Two distinct phenomena make raw billing events non-unique:

### 1. Refresh duplicates

Dynatrace may re-emit a billing event after correction. The refreshed row has
the **same `event.id` + same `event.type`** with updated `billed_*` fields.
Without dedup, aggregations double-count.

### 2. Cross-bucket siblings

A single user query scanning multiple Grail bucket families (logs, spans, files,
events) emits **one billing event per bucket family**, all sharing the **same
`event.id`** (reused from the originating query id) but with **different
`event.type`**. These are *not* duplicates — each row reflects an independent
billable charge against its own capability.

### Correct form

`dedup {event.id, event.type}` handles **both** phenomena: collapses refresh
duplicates and preserves cross-bucket siblings.

| Query scope | Dedup command |
|---|---|
| Multi-type (e.g., Base Usage) | `\| dedup {event.id, event.type}` |
| Single-type (e.g., Metrics Ingest) | `\| dedup event.id` — safe because the query is already filtered to one `event.type` |
| Hour/distinct-entity counting (Workflow, SPM) | `\| dedup <compound_key>` (already type-scoped) |

### Diagnostic query

Detect cross-bucket siblings in any tenant:

```dql-template
fetch dt.system.events, from: "<START>", to: "<END>"
| filter event.kind == "BILLING_USAGE_EVENT"
| summarize n_types = countDistinctExact(event.type),
            types = collectDistinct(event.type),
            by: {event.id}
| filter n_types > 1
| sort n_types desc
```

### Why compound dedup

Cross-bucket siblings are common in practice — a single Query event id routinely
appears under `Log Management & Analytics - Query` alongside `Traces - Query` or
`Files - Query`. Bare `dedup event.id` keeps only one of those rows, silently
dropping the others and undercounting the affected Query capabilities (typically
a fraction of a percent, but real and easy to miss). `dedup {event.id, event.type}`
preserves each sibling while still collapsing refresh duplicates.

## Best Practices

1. **Always dedup billing events** — Billing events can be refreshed; without
   dedup, aggregations double-count. Use `| dedup {event.id, event.type}` for
   multi-type queries. Single-type queries (filtered to one `event.type`) are
   safe with `| dedup event.id`. See
   [Billing Event Deduplication](#billing-event-deduplication).
2. **NEVER sum raw usage across billing categories** — Units are incomparable
   (bytes, GiB-hours, sessions, pod-hours). Use cost-normalized rate-card queries
   from [cost-estimations.md](cost-estimations.md).
3. **Sort multi-capability results alphabetically** — When presenting usage
   across capabilities with different units, sort by capability name. Only sort
   by value when all values share the same unit (e.g., estimated cost).
4. **Use explicit UTC midnight boundaries** — Not rolling `from: -Nd`. See
   [Billing Timeframe Boundaries](#billing-timeframe-boundaries).
5. **Bin by `effective_start` for daily breakdowns** — Use
   `bin(coalesce(usage.start, timestamp), 24h)` for daily aggregation. This
   matches the Base Usage template's `effective_start` pattern: types with
   `usage.start` bin by measurement time (avoiding day-boundary shifts from
   emission lag), types without it fall back to `timestamp`.
6. **Capability-level rollups** — DQL queries return per-`event.type` rows
   (e.g., `Files - Ingest & Process` separate from `Events - Ingest & Process`).
   When the user asks for results at the DPS capability level, apply the
   [Files→Events Remap](#files-to-events-remap) to collapse Files volumes into their
   parent Events capability. Self-check: if Events totals look lower than
   expected, the remap is likely missing.
7. **NEVER extend `to:` without an `effective_start` guard** — Extending `to:`
   beyond `<END>` without filtering on `coalesce(usage.start, timestamp) < <END>`
   over-captures next-period Retain/Query/AppEngine events.
8. **Verify timeseries interval when debugging deduction queries** — If
   Metrics/Traces Ingest billable values seem too high, check whether the
   `timeseries` interval was coarsened:
    ```dql
    timeseries {x = max(dt.billing.traces.maximum_included_fullstack_volume_per_minute)},
      interval: 15m, from: "<START>", to: "<END>", nonempty: true
    | fieldsAdd actual_elements = arraySize(x),
        expected_elements = toLong(toDouble(<WINDOW_MINUTES>) / 15)
    | fields actual_elements, expected_elements, coarsened = actual_elements != expected_elements
    ```
    Replace `<WINDOW_MINUTES>` with the window size in minutes (e.g., `20160`
    for 14 days). If `coarsened` is `true`, split into ≤ 14-day sub-windows.
