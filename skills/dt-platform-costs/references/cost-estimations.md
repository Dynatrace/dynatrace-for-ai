# Cost Estimations

Rank and compare DPS (Dynatrace Platform Subscription) consumption across
capabilities using normalized cost weights. Enables cross-capability ranking,
chargeback normalization, and spend trend analysis.

> **RELATIVE RANKINGS ONLY — NOT ACTUAL BILLING DATA.** Every customer has a
> custom rate card negotiated as part of their DPS contract. The normalization
> weights used throughout this document **will differ from actual costs**. Use
> these queries for directional rankings, relative comparisons, and spike
> detection — **never for invoice reconciliation**.
>
> For actual billing data, use **Account Management > Subscription > Overview >
> Cost and usage details**.

## Contents

- [Important Disclaimers](#important-disclaimers)
- [Cost Normalization Weights](#cost-normalization-weights)
- [Cost Estimation Pattern](#cost-estimation-pattern)
  - [Step 1 — DQL: Obtain Usage + Cost Weight](#step-1--dql-obtain-usage--cost-weight)
  - [Step 2 — Post-Query Delta Math (Period Comparison only)](#step-2--post-query-delta-math-period-comparison-only)
- [Unit Conversion Lookup](#unit-conversion-lookup)
- [Full Inline Lookup for Cost Rankings](#full-inline-lookup-for-cost-rankings)
- [Ready-to-Use Queries](#ready-to-use-queries)
  - [Estimated Cost by Capability](#estimated-cost-by-capability)
  - [Estimated Cost by Cost Center](#estimated-cost-by-cost-center)
  - [Estimated Query Cost by Source](#estimated-query-cost-by-source)
  - [Daily Cost Trend](#daily-cost-trend)
  - [Period Comparison (WoW / MoM)](#period-comparison-wow--mom)

## Important Disclaimers

> **1. Relative rankings only.** Every customer has a custom rate card
> negotiated as part of their DPS contract. The normalization weights used here
> will differ from actual costs. Use these queries for directional rankings,
> relative comparisons, and spike detection — not for invoice reconciliation.
> **Never display the computed cost weight as a dollar estimate** — present
> ranked or percentage output instead. For disclaimer wording and output rules,
> see **SKILL.md § Cost Ranking Rules** — that section is the single source of
> truth for all user-facing disclaimer text.

> **2. Normalization weights may change.** The weights in this document are
> based on the Dynatrace public rate card as of March 2026. Always verify
> current rates before updating this file.

> **3. Not all BUE types have a weight.** Preview types (`Digital
> Experience Monitoring - Query/Retain`) have no weight.
> `Files` types use the corresponding `Events` weight — see
> [billing-capabilities.md § BUE-to-Capability Mapping](billing-capabilities.md#bue-to-capability-mapping).

> **4. Included volume handling.** The cross-capability queries
> ([Estimated Cost by Capability](#estimated-cost-by-capability),
> [Daily Cost Trend](#daily-cost-trend)) use the 4-query pattern from
> [billing-capabilities.md § Cross-Capability Usage](billing-capabilities.md#cross-capability-usage-4-queries)
> which deducts included volume for Metrics Ingest and Traces Ingest. See
> [billing-capabilities.md § Included Volume](billing-capabilities.md#included-volume)
> for deduction details.

> **5. DPS only.** The normalization weights, unit conversion lookup, and all cost
> ranking queries apply exclusively to the Dynatrace Platform Subscription (DPS) license
> model. They cannot be used with classic license models (host units, DDUs, DEM
> units, ASUs).

> **CRITICAL: Cross-Capability Cost Comparison.** NEVER compare raw usage across
> billing categories — units are incomparable (bytes, GiB-hours, sessions,
> pod-hours). Always use cost-normalized estimation from this file.
> Single-category questions (e.g., "how much log ingest?") can use raw usage
> because units are consistent within a category.

## Cost Normalization Weights

The `Normalization Weight` column is the normalization weight used internally to rank
capabilities by relative cost. **Never display these values as dollar estimates**
— actual rates depend on negotiated DPS contracts.

| Event Type | Unit | Normalization Weight |
|------------|------|-------------:|
| `Full-Stack Monitoring` | GiB-hours | 0.01 |
| `Infrastructure Monitoring` | host-hours | 0.04 |
| `Foundation & Discovery` | host-hours | 0.01 |
| `Mainframe Monitoring` | MSU-hours | 0.10 |
| `Code Monitoring` | container-hours | 0.005 |
| `Kubernetes Platform Monitoring` | pod-hours | 0.002 |
| `Log Management & Analytics - Ingest & Process` | GiB | 0.20 |
| `Log Management & Analytics - Query` | GiB scanned | 0.0035 |
| `Log Management & Analytics - Retain` | GiB-days | 0.0007 |
| `Log Management & Analytics - Retain with Included Queries` | GiB-days | 0.02 |
| `Traces - Ingest & Process` | GiB | 0.20 |
| `Traces - Query` | GiB scanned | 0.0035 |
| `Traces - Retain` | GiB-days | 0.0007 |
| `Metrics - Ingest & Process` | data points | 0.0000015 |
| `Metrics - Retain` | GiB-days | 0.0007 |
| `Events - Ingest & Process` | GiB | 0.20 |
| `Events - Query` | GiB scanned | 0.0035 |
| `Events - Retain` | GiB-days | 0.0007 |
| `Files - Ingest & Process` | GiB | 0.20 |
| `Files - Query` | GiB scanned | 0.0035 |
| `Files - Retain` | GiB-days | 0.0007 |
| `Real User Monitoring` | sessions | 0.00225 |
| `Real User Monitoring with Session Replay` | replay captures | 0.0045 |
| `Real User Monitoring Property` | properties/session | 0.0001 |
| `Browser Monitor or Clickpath` | synthetic actions | 0.0045 |
| `HTTP Monitor` | synthetic requests | 0.001 |
| `Third-Party Synthetic API Ingestion` | synthetic results | 0.001 |
| `Runtime Application Protection` | GiB-hours | 0.00225 |
| `Runtime Vulnerability Analytics` | GiB-hours | 0.00225 |
| `Security Posture Management` | host-hours | 0.007 |
| `Automation Workflow` | workflow-hours | 0.03 |
| `AppEngine Functions - Small` | invocations | 0.001 |
| `AI Function Standard Call` | invocations | 0.001 |
| `AI Units` | units | 0.1 |
| `Data Egress` | GiB | 0.15 |
| `Database Monitoring` | database-instance-hours | 0.11 |

> **Notes:**
> - `Files` types use the corresponding `Events` weights (see
>   [billing-capabilities.md § BUE-to-Capability Mapping](billing-capabilities.md#bue-to-capability-mapping)).
> - Preview types (`Digital Experience Monitoring - Query/Retain`)
>   have no weight — omit from cost rankings.
> - `AI Units` uses `usage.quantity.billable` (double) as its billed field,
>   not `billed_invocations`.

## Cost Estimation Pattern

**For all cost rankings, compute `cost_weight` inside DQL** — never mentally.
Append the [Full Inline Lookup for Cost Rankings](#full-inline-lookup-for-cost-rankings)
to any billing usage query. DQL returns rows pre-sorted by `cost_weight`; the
agent only formats them.

> **NEVER multiply normalization weights mentally.** Usage values span 10 orders
> of magnitude; weights span 5. Mental arithmetic across 20+ rows with small
> decimals produces silent, undetectable ranking errors. DQL arithmetic is exact.

### Step 1 — DQL: Obtain Usage + Cost Weight

Run the appropriate query from [Ready-to-Use Queries](#ready-to-use-queries),
then append the [Full Inline Lookup for Cost Rankings](#full-inline-lookup-for-cost-rankings).
The lookup computes both `capability_usage` (for display) and `cost_weight`
(for sorting) in a single DQL step.

Finish the query with:

```dql-snippet
| filter isNotNull(cost_weight)
| sort cost_weight desc
| fields event.type, capability_usage, cost_weight
```

The agent receives rows already ranked correctly. Format and present — no
arithmetic required.

### Step 2 — Post-Query Delta Math (Period Comparison only)

Manual delta computation is only needed for [Period Comparison](#period-comparison-wow--mom),
where two separate DQL result sets must be subtracted. For all other ranking
use cases, Step 1 + inline lookup is sufficient.

Show the disclaimer before results (see SKILL.md §
[Cost Ranking Rules](../SKILL.md#cost-ranking-rules)).

## Unit Conversion Lookup

> **⚠️ Usage-only — NOT for cost rankings.** This snippet converts units but
> does NOT compute `cost_weight`. For cost rankings, use the
> [Full Inline Lookup for Cost Rankings](#full-inline-lookup-for-cost-rankings)
> instead — it handles both unit conversion and cost-weight computation.

Append this snippet to any billing usage query that produces a
`billable_usage` field **when you need usage in capability units without
ranking**. It converts raw values to capability units and adds a
`capability_usage` field. Follow with your own `| fields` clause to select
the columns you need.

> **Prerequisite:** Upstream queries must dedup before aggregating. Use
> `| dedup {event.id, event.type}` for multi-type queries — see
> [Billing Event Deduplication](billing-capabilities.md#billing-event-deduplication).

```dql-snippet
// --- Unit Conversion Lookup (append after summarize) ---
| lookup [
    data json:"""[
      {"event_types": ["Log Management & Analytics - Ingest & Process", "Log Management & Analytics - Query", "Traces - Ingest & Process", "Traces - Query", "Events - Ingest & Process", "Events - Query", "Files - Ingest & Process", "Files - Query", "Digital Experience Monitoring - Query", "Data Egress"], "unitDivisor": 1073741824},
      {"event_types": ["Log Management & Analytics - Retain", "Log Management & Analytics - Retain with Included Queries", "Traces - Retain", "Metrics - Retain", "Events - Retain", "Files - Retain", "Digital Experience Monitoring - Retain"], "unitDivisor": 25769803776}
    ]"""
    | expand event_type = event_types
    | fieldsRemove event_types
  ], sourceField: event.type, lookupField: event_type
| fieldsAdd capability_usage = toDouble(billable_usage) / coalesce(lookup.unitDivisor, 1)
```

Uses a grouped `expand` pattern — 2 JSON entries cover 17 byte-based event
types (including DEM preview types and Data Egress for correct usage reporting). Types not in
the lookup (sessions, hours, data points) get `lookup.unitDivisor=null` →
`coalesce(null, 1)` → raw value passes through unchanged.

`1073741824` = 1 GiB in bytes; `25769803776` = 1 GiB-day in byte-hours
(1073741824 × 24).

## Ready-to-Use Queries

> **IMPORTANT — For cost rankings, append the
> [Full Inline Lookup for Cost Rankings](#full-inline-lookup-for-cost-rankings)
> after these queries. It computes both `capability_usage` and `cost_weight` in
> DQL. Never display `cost_weight` as a dollar estimate — present ranked output
> in native units only.**

### Estimated Cost by Capability

Total billable usage per billing event type in capability units. Uses the
[Combined Query](billing-capabilities.md#quick-overview--combined-query) from
`billing-capabilities.md` (with included volume deducted for Metrics/Traces
Ingest), then applies the [Full Inline Lookup for Cost Rankings](#full-inline-lookup-for-cost-rankings).

Replace `<START>` / `<END>` with explicit UTC midnight boundaries (see
[billing-capabilities.md § Billing Timeframe Boundaries](billing-capabilities.md#billing-timeframe-boundaries)).

> **14-day limit** — Metrics Ingest and Traces Ingest sub-queries
> use `timeseries` for included volume metrics. For longer timeframes, use the
> [multi-window pattern](billing-capabilities.md#longer-timeframes-multi-window-pattern).

Run the [Combined Query](billing-capabilities.md#quick-overview--combined-query)
from `billing-capabilities.md` (all 4 sub-queries), then append the
[Full Inline Lookup for Cost Rankings](#full-inline-lookup-for-cost-rankings).
Finish with `| filter isNotNull(cost_weight) | sort cost_weight desc | fields event.type, capability_usage, cost_weight`.

DQL returns rows pre-sorted by cost weight. Present as a ranked table in native
units — no post-query arithmetic. See SKILL.md § Cost Ranking Rules for output
format and disclaimer wording.

### Estimated Cost by Cost Center

For cost center attribution and chargeback, use the queries in
[cost-allocation.md](cost-allocation.md). Two cases:

**Cross-capability ranking by cost center** — use the
[Unified Chargeback](cost-allocation.md#unified-chargeback-all-types) query,
renaming its output to `billable_usage`, then append the Full Inline Lookup:

```dql-snippet
// After the Base Usage query (produces {event.type, usage} per event):
| filter isNotNull(dt.cost.costcenter)
| expand c = dt.cost.costcenter
| fieldsAdd
    cc = coalesce(c[key], c),
    v = coalesce(c[data_points], c[billed_bytes], usage)
| summarize billable_usage = sum(v), by: {event.type, dt.cost.costcenter = cc}
// append Full Inline Lookup here, then:
| filter isNotNull(cost_weight)
| sort cost_weight desc
| fields dt.cost.costcenter, event.type, capability_usage, cost_weight
```

The Unified Chargeback query produces mixed raw units (bytes for ingest types,
native for hour types) — exactly what the inline lookup's `unitDivisor` handles.

**Single-capability breakdown by cost center** — the individual per-capability
queries in [cost-allocation.md](cost-allocation.md) produce already-converted
fields (e.g. `total_gib_hours`, `total_data_points`). The Full Inline Lookup
cannot be appended (values are already in capability units). For these, apply
the normalization weight as a single multiplication:
`cost_weight = capability_usage × weight` (look up `weight` from
[Cost Normalization Weights](#cost-normalization-weights)). This is safe because
only one weight is involved.

### Estimated Query Cost by Source

Attribute query scan costs to originating source. Uses `coalesce()` across all
`client.*` attribution fields — see
[query-cost-attribution.md → BUE Query Attribution Fields](query-cost-attribution.md#bue-query-attribution-fields).

All Query types use `unitDivisor = 1073741824` (bytes → GiB scanned), so a
simplified single-value conversion is used instead of the full lookup:

```dql-template
fetch dt.system.events, from: "<START>", to: "<END>"
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type,
    "Log Management & Analytics - Query",
    "Events - Query",
    "Traces - Query",
    "Files - Query")
| dedup {event.id, event.type}
| fieldsAdd attribution = coalesce(client.source, client.application_context, client.internal_service_context, client.workflow_context, client.function_context, client.client_context, "unknown")
| summarize total_bytes = sum(billed_bytes), by: {attribution, event.type}
| fieldsAdd capability_usage = toDouble(total_bytes) / 1073741824
| fields attribution, event.type, capability_usage
| sort capability_usage desc
| limit 30
```

All Query types included above share the same normalization weight (`0.0035`),
so the inline lookup is not required — `capability_usage` already reflects
relative cost within this result set. Sort by `capability_usage desc`.

> The `attribution` values mix source types (dashboard, detector, workflow, app).
> To interpret them and drill down per source — per-detector, per-workflow, and
> the full investigation workflow — see
> [query-cost-attribution.md](query-cost-attribution.md).

### Daily Cost Trend

Track daily billable usage to detect spikes. Uses the same
[Combined Query](billing-capabilities.md#quick-overview--combined-query),
modified for daily bucketing.

Replace `<START>` / `<END>` with UTC midnight boundaries (e.g.,
`2026-03-01T00:00:00Z` / `2026-03-31T00:00:00Z`).

> **14-day limit** — Billed Metrics/Traces Ingest sub-queries use `timeseries`.
> For longer timeframes, use the
> [multi-window pattern](billing-capabilities.md#longer-timeframes-multi-window-pattern).

**Modification:** In each of the 4 sub-queries, replace the final
`summarize ... by: {event.type}` with a daily-bucketed variant. Use the
correct time field per sub-query (see
[Best Practice #5](billing-capabilities.md#best-practices)):

- **Base Usage** — the [Base Usage template](billing-capabilities.md#base-usage) already uses `<END_PLUS_2H>` + `effective_start` guard. For daily bucketing, replace the final summarize with `by: {event.type, day = bin(effective_start, 24h)}`
- **Workflow + SPM** — no `usage.start`: `by: {event.type, day = bin(timestamp, 1d)}`
- **Metrics Ingest** — already uses `usage.start` in `makeTimeseries`; see the [Per-Day Breakdown](billing-capabilities.md#metrics-ingest--per-day-breakdown) variant
- **Traces Ingest** — uses `makeTimeseries time: usage.start`; add `day = bin(usage.start, 24h)` to the final aggregation

Run the [Combined Query](billing-capabilities.md#quick-overview--combined-query)
with the daily-bucketing modification above applied to each sub-query, then
append the [Full Inline Lookup for Cost Rankings](#full-inline-lookup-for-cost-rankings).
Finish with `| filter isNotNull(cost_weight) | sort day asc, cost_weight desc | fields event.type, capability_usage, day, cost_weight`.

DQL returns rows with `capability_usage` in native units, pre-sorted by cost
weight within each day. Output the daily-bucketed table in native units only
(GiB, GiB-hours, workflow-hours, etc.), with direction markers (↑ elevated,
🔴 spike, ~ normal) derived from relative `cost_weight` within the day. See
SKILL.md § Cost Ranking Rules step 2 for output formatting — drop `cost_weight`
and present native units only.

### Period Comparison (WoW / MoM)

Compare two equal-length windows to surface what grew, shrank, or appeared.
Use for "compare last week to the week before", "what changed month over month",
or "what's trending up in spend".

> **Do not use `event_count` for period comparisons.** Billing event counts
> reflect emission frequency, not consumption volume — a 20% rise in event
> count does not mean 20% more GiB or hours consumed. Always compare
> `capability_usage` (capability units).

**Steps:**

1. **Run the [Estimated Cost by Capability](#estimated-cost-by-capability) query
   twice** — once per window — using explicit UTC midnight boundaries each time.
   Use identical query structure for both runs; change only `<START>`, `<END>`,
   and their derived values (`<END_PLUS_2H>`, `<END_PLUS_5H>`).

   - Window A (previous): e.g. `2026-04-14T00:00:00Z` → `2026-04-21T00:00:00Z`
   - Window B (current):  e.g. `2026-04-21T00:00:00Z` → `2026-04-28T00:00:00Z`

   Windows must be equal length (7d vs 7d, 30d vs 30d).

2. **Compute delta per capability** (post-query):
   Both query results include `cost_weight` from the inline lookup — no weight
   multiplication needed. Subtract to get the sort key:
   ```
   delta_usage       = capability_usage_B − capability_usage_A
   cost_weight_delta = cost_weight_B − cost_weight_A   ← sort key
   ```

3. **Sort** by `abs(cost_weight_delta) desc` — largest cost movers first.
   Drop all `cost_weight` columns before presenting.

4. **Present** a comparison table in native units with a direction indicator.
   Show the ℹ️ disclaimer before results (multi-capability output).
   For zero-baseline capabilities (previous = 0), show `"New"` instead of a
   percentage. Note in the response that units differ by row and are not
   directly comparable to each other.

**Example output:**
```
ℹ️ Rankings show relative spend — for actual dollar figures, see **Account Management > Subscription > Overview > Cost and usage details**.

Capability                Apr 14–20         Apr 21–27        Change
Full-Stack Monitoring     2.41M GiB-hours   2.33M GiB-hours  ↓ –3%
Log Mgmt - Ingest         490 GiB           590 GiB          ↑ +20%
RUM Property              2.57B props/sess  2.57B props/sess  → 0%
Files - Ingest            0                 6 GiB             New
```

> **14-day limit** — If either window uses Metrics Ingest or Traces Ingest
> sub-queries, the included-volume deduction is limited to 14 days. For longer
> windows, use the
> [multi-window pattern](billing-capabilities.md#longer-timeframes-multi-window-pattern).

## Full Inline Lookup for Cost Rankings

Append this snippet after any billing usage query that produces a
`billable_usage` field. It computes both `capability_usage` (display unit) and
`cost_weight` (internal sort key) in DQL — the agent never performs arithmetic.

> ⚠️ `cost_weight` is a **ranking value only** — never display it as a dollar
> estimate. Drop it from the user-facing response (and optionally from the query
> output with `| fields event.type, capability_usage` after sorting). For output
> rules and disclaimer wording, see SKILL.md § Cost Ranking Rules.

> For `lookup` command syntax and chaining rules, see `dt-dql-essentials`.
> Each `lookup` **removes all existing `lookup.*` fields** — use `fieldsRename`
> between chained lookups to preserve results.

Each entry carries `unitDivisor` (bytes → capability unit conversion) plus
`factor` / `factorBase` (numerator and denominator of the normalization weight;
`weight = factor / factorBase`).

```dql-snippet
// --- Full Inline Lookup for Cost Rankings (append after summarize) ---
| lookup [
    data json:"""
    [
      {"event_type": "Full-Stack Monitoring", "unitDivisor": 1, "unit": "GiB-hours", "factor": 1000, "factorBase": 100000},
      {"event_type": "Infrastructure Monitoring", "unitDivisor": 1, "unit": "host-hours", "factor": 4000, "factorBase": 100000},
      {"event_type": "Foundation & Discovery", "unitDivisor": 1, "unit": "host-hours", "factor": 1000, "factorBase": 100000},
      {"event_type": "Mainframe Monitoring", "unitDivisor": 1, "unit": "MSU-hours", "factor": 1000, "factorBase": 10000},
      {"event_type": "Code Monitoring", "unitDivisor": 1, "unit": "container-hours", "factor": 500, "factorBase": 100000},
      {"event_type": "Kubernetes Platform Monitoring", "unitDivisor": 1, "unit": "pod-hours", "factor": 200, "factorBase": 100000},
      {"event_type": "Log Management & Analytics - Ingest & Process", "unitDivisor": 1073741824, "unit": "GiB", "factor": 2000, "factorBase": 10000},
      {"event_type": "Log Management & Analytics - Query", "unitDivisor": 1073741824, "unit": "GiB scanned", "factor": 3500, "factorBase": 1000000},
      {"event_type": "Log Management & Analytics - Retain", "unitDivisor": 25769803776, "unit": "GiB-days", "factor": 700, "factorBase": 1000000},
      {"event_type": "Log Management & Analytics - Retain with Included Queries", "unitDivisor": 25769803776, "unit": "GiB-days", "factor": 20000, "factorBase": 1000000},
      {"event_type": "Traces - Ingest & Process", "unitDivisor": 1073741824, "unit": "GiB", "factor": 2000, "factorBase": 10000},
      {"event_type": "Traces - Query", "unitDivisor": 1073741824, "unit": "GiB scanned", "factor": 3500, "factorBase": 1000000},
      {"event_type": "Traces - Retain", "unitDivisor": 25769803776, "unit": "GiB-days", "factor": 700, "factorBase": 1000000},
      {"event_type": "Metrics - Ingest & Process", "unitDivisor": 1, "unit": "data points", "factor": 150, "factorBase": 100000000},
      {"event_type": "Metrics - Retain", "unitDivisor": 25769803776, "unit": "GiB-days", "factor": 700, "factorBase": 1000000},
      {"event_type": "Events - Ingest & Process", "unitDivisor": 1073741824, "unit": "GiB", "factor": 2000, "factorBase": 10000},
      {"event_type": "Events - Query", "unitDivisor": 1073741824, "unit": "GiB scanned", "factor": 3500, "factorBase": 1000000},
      {"event_type": "Events - Retain", "unitDivisor": 25769803776, "unit": "GiB-days", "factor": 700, "factorBase": 1000000},
      {"event_type": "Files - Ingest & Process", "unitDivisor": 1073741824, "unit": "GiB", "factor": 2000, "factorBase": 10000},
      {"event_type": "Files - Query", "unitDivisor": 1073741824, "unit": "GiB scanned", "factor": 3500, "factorBase": 1000000},
      {"event_type": "Files - Retain", "unitDivisor": 25769803776, "unit": "GiB-days", "factor": 700, "factorBase": 1000000},
      {"event_type": "Real User Monitoring", "unitDivisor": 1, "unit": "sessions", "factor": 225, "factorBase": 100000},
      {"event_type": "Real User Monitoring with Session Replay", "unitDivisor": 1, "unit": "replay captures", "factor": 450, "factorBase": 100000},
      {"event_type": "Real User Monitoring Property", "unitDivisor": 1, "unit": "properties/session", "factor": 10, "factorBase": 100000},
      {"event_type": "Browser Monitor or Clickpath", "unitDivisor": 1, "unit": "synthetic actions", "factor": 450, "factorBase": 100000},
      {"event_type": "HTTP Monitor", "unitDivisor": 1, "unit": "synthetic requests", "factor": 100, "factorBase": 100000},
      {"event_type": "Third-Party Synthetic API Ingestion", "unitDivisor": 1, "unit": "synthetic results", "factor": 100, "factorBase": 100000},
      {"event_type": "Runtime Application Protection", "unitDivisor": 1, "unit": "GiB-hours", "factor": 225, "factorBase": 100000},
      {"event_type": "Runtime Vulnerability Analytics", "unitDivisor": 1, "unit": "GiB-hours", "factor": 225, "factorBase": 100000},
      {"event_type": "Security Posture Management", "unitDivisor": 1, "unit": "host-hours", "factor": 700, "factorBase": 100000},
      {"event_type": "Automation Workflow", "unitDivisor": 1, "unit": "workflow-hours", "factor": 300, "factorBase": 10000},
      {"event_type": "AppEngine Functions - Small", "unitDivisor": 1, "unit": "invocations", "factor": 1000, "factorBase": 1000000},
      {"event_type": "AI Function Standard Call", "unitDivisor": 1, "unit": "invocations", "factor": 1000, "factorBase": 1000000},
      {"event_type": "AI Units", "unitDivisor": 1, "unit": "units", "factor": 1000, "factorBase": 10000},
      {"event_type": "Data Egress", "unitDivisor": 1073741824, "unit": "GiB", "factor": 1500, "factorBase": 10000},
      {"event_type": "Database Monitoring", "unitDivisor": 1, "unit": "database-instance-hours", "factor": 1100, "factorBase": 10000}
    ]
    """
  ], sourceField: event.type, lookupField: event_type
| fieldsAdd capability_usage = toDouble(billable_usage) / lookup.unitDivisor
| fieldsAdd cost_weight = capability_usage / lookup.factorBase * lookup.factor
// finish with: | filter isNotNull(cost_weight) | sort cost_weight desc | fields event.type, capability_usage, cost_weight
```

> **Notes:**
> - `Files` types are mapped to `Events` normalization weights (see
>   [billing-capabilities.md § BUE-to-Capability Mapping](billing-capabilities.md#bue-to-capability-mapping)).
> - Preview types (`Digital Experience Monitoring - Query/Retain`) are omitted
>   — they return `null` for `cost_weight`. Filter with
>   `| filter isNotNull(cost_weight)` before sorting.
