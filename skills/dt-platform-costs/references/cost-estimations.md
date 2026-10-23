# Cost Estimations

Rank and compare DPS (Dynatrace Platform Subscription) consumption across capabilities. Uses the tenant's contracted rate card when available (rated path) or normalized cost weights when it is not (unrated path) — see [Pre-flight Detection](#pre-flight-detection). Enables cross-capability ranking, chargeback normalization, and spend trend analysis.

## Contents

- [Important Disclaimers](#important-disclaimers)
- [Price Source Resolution](#price-source-resolution)
  - [Pre-flight Detection](#pre-flight-detection)
  - [Rate Card Join Snippet](#rate-card-join-snippet)
  - [Validity Labeling Rule](#validity-labeling-rule)
  - [Output Rules for Rated Path](#output-rules-for-rated-path)
- [Rated Cost Estimation (rate card present)](#rated-cost-estimation-rate-card-present)
  - [Estimated Cost by Capability (rated)](#estimated-cost-by-capability-rated)
  - [Daily Cost Trend (rated)](#daily-cost-trend-rated)
  - [Period Comparison / WoW / MoM (rated)](#period-comparison--wow--mom-rated)
- [Cost Estimation Pattern (Unrated / No Rate Card)](#cost-estimation-pattern-unrated--no-rate-card)
  - [Cost Normalization Weights](#cost-normalization-weights)
  - [Step 1 — DQL: Obtain Usage + Cost Weight](#step-1--dql-obtain-usage--cost-weight)
  - [Step 2 — Post-Query Delta Math (Period Comparison only)](#step-2--post-query-delta-math-period-comparison-only)
- [Full Inline Lookup for Cost Rankings](#full-inline-lookup-for-cost-rankings)
- [Ready-to-Use Queries (Unrated / No Rate Card)](#ready-to-use-queries-unrated--no-rate-card)
  - [Estimated Cost by Capability (unrated)](#estimated-cost-by-capability-unrated)
  - [Estimated Cost by Cost Center](#estimated-cost-by-cost-center)
  - [Estimated Query Cost by Source](#estimated-query-cost-by-source)
  - [Daily Cost Trend (unrated)](#daily-cost-trend-unrated)
  - [Period Comparison (WoW / MoM) (unrated)](#period-comparison-wow--mom-unrated)

## Important Disclaimers

> **1. Relative rankings only (unrated path).** Every customer has a custom rate card
> negotiated as part of their DPS contract. The normalization weights used here
> will differ from actual costs. Use these queries for directional rankings,
> relative comparisons, and spike detection — not for invoice reconciliation.
> **Never display the computed cost weight as a dollar estimate** — present
> ranked or percentage output instead. For disclaimer wording and output rules,
> see **SKILL.md § Cost Ranking Rules** — that section is the single source of
> truth for all user-facing disclaimer text.

> **2. Estimated cost is not authoritative billing (rated path).** When the tenant's
> contracted rate card is available, `estimated_cost` is derived from that rate card
> but is not an authoritative billing figure. For invoice reconciliation, direct users to
> **Account Management > Subscription > Overview > Cost and usage details**. For output
> formatting rules, see [§ Output Rules for Rated Path](#output-rules-for-rated-path).

> **3. Normalization weights may change.** The normalization weights in the table below are
> based on the Dynatrace public rate card as of March 2026.

> **4. Not all BUE types have a weight.** Preview types (`Digital
> Experience Monitoring - Query/Retain`) have no weight.
> `Files` types use the corresponding `Events` weight — see
> [billing-capabilities.md § BUE-to-Capability Mapping](billing-capabilities.md#bue-to-capability-mapping).

> **5. Included volume handling.** The cross-capability queries use the 4-query pattern from
> [billing-capabilities.md § Cross-Capability Usage](billing-capabilities.md#cross-capability-usage-4-queries)
> which deducts included volume for Metrics Ingest and Traces Ingest. See
> [billing-capabilities.md § Included Volume](billing-capabilities.md#included-volume)
> for deduction details.

> **6. DPS only.** All patterns, queries, and cost estimations in this file apply
> exclusively to the Dynatrace Platform Subscription (DPS) license
> model. They cannot be used with classic license models (host units, DDUs, DEM
> units, ASUs).

> **CRITICAL: Cross-Capability Cost Comparison.** NEVER compare raw usage across
> billing categories — units are incomparable (bytes, GiB-hours, sessions,
> pod-hours). Always use cost-normalized estimation from this file.
> Single-category questions (e.g., "how much log ingest?") can use raw usage
> because units are consistent within a category.

## Price Source Resolution

When a DPS rate card is present at `/dt/dps-cost-control/unit-prices`, append
the join below after any `| summarize billable_usage = ...` step to convert native usage
into estimated costs in the customer's contracted currency.

### Pre-flight Detection

Before producing any cost-amount answer, the skill runs a silent pre-flight check to determine
whether the rate card is present and accessible.

```dql
fetch dt.system.files
| filter name == "/dt/dps-cost-control/unit-prices"
| fields name, records
| limit 1
```

**Decision logic:**
- 1 row returned AND `records > 0` → **rated path**: proceed with cost estimates in contracted
  currency using the join below.
- 0 rows returned OR `records == 0` → **unrated path**: fall back to native units + cost-weight
  ranking (existing behavior), unchanged.

The skill runs this check silently before every cost-related request. It does not inform the
user that a pre-flight was run; it uses the result to pick a path automatically.

### Rate Card Join Snippet

Append this snippet after any `| summarize billable_usage = ...` step in a BUE query.
The lookup projects `bue_type, price_per_unit, unit_divisor, currency, valid_from, valid_to`
and adds three fields to each row:

- `capability_usage` — usage converted to the capability's native unit (GiB, hours, sessions,
  etc.) using the rate card's `unit_divisor`
- `estimated_cost` — rounded cost in the contracted currency (2 decimal places)
- `currency_code` — ISO 4217 code read from the rate card's `currency` field

```dql-snippet
| join [
    load "/dt/dps-cost-control/unit-prices"
    | fields bue_type, price_per_unit, unit_divisor, currency, valid_from, valid_to
  ], on: {left[`event.type`] == right[bue_type]}, prefix: "lookup.", kind: leftOuter
// fallback_divisor converts types missing from the rate card (e.g. preview types) to native units
| fieldsAdd fallback_divisor = if(endsWith(event.type, "- Retain") or endsWith(event.type, "Retain with Included Queries"), 25769803776,
    else: if(endsWith(event.type, "- Query") or event.type == "Data Egress"
      or (endsWith(event.type, "- Ingest & Process") and event.type != "Metrics - Ingest & Process"), 1073741824, else: 1))
| fieldsAdd capability_usage = toDouble(billable_usage) / coalesce(toDouble(lookup.unit_divisor), fallback_divisor)
| fieldsAdd estimated_cost = round(capability_usage * lookup.price_per_unit, decimals: 2)
| fieldsAdd currency_code = lookup.currency
| fieldsAdd valid_from = toTimestamp(lookup.valid_from), valid_to = toTimestamp(lookup.valid_to)
```

BUE types absent from the rate card (`lookup.*` null under `leftOuter`) keep their row: `fallback_divisor` already converts their `capability_usage` to native units (e.g. `Digital Experience Monitoring - Query` → GiB scanned), and `estimated_cost` stays null. Take the unit label from [billing-capabilities.md § Unit Conversion Table](billing-capabilities.md#unit-conversion-table), show the usage, and leave the cost column empty. Sort them last with `sort isNull(estimated_cost) asc, estimated_cost desc` — a plain `sort estimated_cost desc` puts null rows first.

### Validity Labeling Rule

> After running the join, compare the query's `<START>` against `valid_from` and `<END>` against `valid_to`. If `<START>` is before `valid_from` or `<END>` is after `valid_to` for any rate card entry, add the following warning **before** presenting results:
>
> ⚠️ Some periods in this query fall outside the rate card's validity window
> (`valid_from` / `valid_to`). Estimated costs may not reflect the correct price for those
> periods.
>
> Still proceed with the rated join and present results. Do **not** fall back to the unrated
> path because of a validity window mismatch. Only an absent or unreadable rate card
> (pre-flight failure) triggers a fallback to the unrated path — a ⚠️ warning is sufficient
> for a validity window issue.

### Output Rules for Rated Path

1. **Label cost amounts** as "estimated cost (from BUE) [<currency_code>]" — always, in
   every table header and in prose. Include the ISO 4217 currency code from `currency_code`
   in column headers (e.g., "estimated cost (from BUE) [EUR]") and on first mention in prose.
2. **Show native units alongside the estimated cost** — include a capability-units column
   next to the cost column for transparency. Do not replace native units with cost amounts.
3. **Two decimal places** for all cost amounts (`round(..., decimals: 2)`).
4. **No authoritative billing claim** — always direct to
   **Account Management > Subscription > Overview > Cost and usage details** for
   actual invoice reconciliation. Never state that estimated costs are authoritative billing
   figures.
5. **No `cost_weight` in rated path** — the rated path uses `estimated_cost` in the
   contracted currency. Do not also compute or display `cost_weight` or normalization weights
   when the rate card is present.

## Rated Cost Estimation (rate card present)

When a rate card is available, use the queries below. Append the
[Rate Card Join Snippet](#rate-card-join-snippet) after each `billable_usage` step.
The Full Inline Lookup and `cost_weight` are **not** used in the rated path.

### Estimated Cost by Capability (rated)

Runs the same 4-sub-query Combined Query as the unrated path (including Metrics/Traces Ingest
included-volume deduction — see [billing-capabilities.md § Combined Query](billing-capabilities.md#quick-overview--combined-query)).
The final `summarize` step must produce `billable_usage` by `event.type`, then append the
rate-card join.

> Replace `<START>` / `<END>` / `<END_PLUS_2H>` / `<END_PLUS_5H>` with UTC midnight
> boundaries. **14-day limit:** for any window longer than 14 days, split into ≤ 14-day
> windows with the [multi-window pattern](billing-capabilities.md#longer-timeframes-multi-window-pattern)
> and sum — a single longer window silently inflates Traces Ingest several-fold.

Run the [Combined Query](billing-capabilities.md#quick-overview--combined-query)
from `billing-capabilities.md` (all 4 sub-queries), then append the
[Rate Card Join Snippet](#rate-card-join-snippet). Finish with
`| sort isNull(estimated_cost) asc, estimated_cost desc | fields event.type, capability_usage, estimated_cost, currency_code, valid_from, valid_to`.

Present as a ranked table: rank, capability name, native units (`capability_usage` with unit
label), estimated cost labeled "estimated cost (from BUE) [<currency_code>]". Show the ℹ️
rated disclaimer before results. Apply ⚠️ validity warning if timeframe extends outside
`valid_from`/`valid_to`.

### Daily Cost Trend (rated)

Daily bucketing by `bin(usage.start, 24h)` for event types with `usage.start` (or
`bin(timestamp, 1d)` for Workflow/SPM), then rate-card join. Outputs `day`,
`capability_usage`, `estimated_cost`, `currency_code`.

> Replace `<START>` / `<END>` / `<END_PLUS_2H>` with UTC midnight boundaries. For windows
> over 14 days, use the [multi-window pattern](billing-capabilities.md#longer-timeframes-multi-window-pattern).

Run the [Combined Query](billing-capabilities.md#quick-overview--combined-query) with the
daily-bucketing modification (see [Daily Cost Trend (unrated)](#daily-cost-trend-unrated)
for the per-sub-query modification rules), then append the
[Rate Card Join Snippet](#rate-card-join-snippet). Finish with
`| sort day asc, isNull(estimated_cost) asc, estimated_cost desc | fields event.type, day, capability_usage, estimated_cost, currency_code, valid_from, valid_to`.

### Period Comparison / WoW / MoM (rated)

Run the [Estimated Cost by Capability (rated)](#estimated-cost-by-capability-rated) query
twice — once per window (Window A = previous, Window B = current) — using explicit UTC
midnight boundaries. Then compute delta post-query:

```
estimated_cost_delta = estimated_cost_B − estimated_cost_A   ← sort key
```

Sort by `abs(estimated_cost_delta) desc` — largest cost movers first. Show "New" for
capabilities with zero estimated cost in the previous window.

> No weight multiplication needed: the rate-card join already converts to contracted currency.

## Cost Estimation Pattern (Unrated / No Rate Card)

**For all cost rankings, compute `cost_weight` inside DQL** — never mentally.
Append the [Full Inline Lookup for Cost Rankings](#full-inline-lookup-for-cost-rankings)
to any billing usage query. DQL returns rows pre-sorted by `cost_weight`; the
agent only formats them.

> **NEVER multiply normalization weights mentally.** Usage values span 10 orders
> of magnitude; weights span 5. Mental arithmetic across 20+ rows with small
> decimals produces silent, undetectable ranking errors. DQL arithmetic is exact.

### Cost Normalization Weights

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
>   have no weight — omit from **unrated** cost rankings. On the rated path they
>   stay in the result in native units with an empty cost column.
> - `AI Units` uses `usage.quantity.billable` (double) as its billed field,
>   not `billed_invocations`.

### Step 1 — DQL: Obtain Usage + Cost Weight

Run the appropriate query from [Ready-to-Use Queries](#ready-to-use-queries-unrated--no-rate-card),
then append the [Full Inline Lookup for Cost Rankings](#full-inline-lookup-for-cost-rankings).
The lookup computes both `capability_usage` (for display) and `cost_weight`
(for sorting) in a single DQL step.

Finish the query with:

```dql-snippet
| filter isNotNull(cost_weight)
| sort cost_weight desc
// cost_weight is for sorting only — drop before presenting; see SKILL.md § Cost Ranking Rules step 2
| fields event.type, capability_usage, cost_weight
```

The agent receives rows already ranked correctly. Format and present — no
arithmetic required.

### Step 2 — Post-Query Delta Math (Period Comparison only)

Manual delta computation is only needed for [Period Comparison](#period-comparison-wow--mom-unrated),
where two separate DQL result sets must be subtracted. For all other ranking
use cases, Step 1 + inline lookup is sufficient.

Show the disclaimer before results (see SKILL.md §
[Cost Ranking Rules](../SKILL.md#cost-ranking-rules)).

## Ready-to-Use Queries (Unrated / No Rate Card)

> **IMPORTANT — For cost rankings, append the
> [Full Inline Lookup for Cost Rankings](#full-inline-lookup-for-cost-rankings)
> after these queries. It computes both `capability_usage` and `cost_weight` in
> DQL. Never display `cost_weight` as a dollar estimate — present ranked output
> in native units only.**

### Estimated Cost by Capability (unrated)

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

**Cross-capability ranking by cost center** — run the
[Unified Chargeback (All Types, Unrated / No Rate Card)](cost-allocation.md#unified-chargeback-all-types-unrated--no-rate-card)
query (produces `billable_usage` per `event.type, dt.cost.costcenter`), then
append the [Full Inline Lookup for Cost Rankings](#full-inline-lookup-for-cost-rankings)
and finish with `| filter isNotNull(cost_weight) | sort cost_weight desc`.

**Single-capability breakdown by cost center** — the individual per-capability
queries in [cost-allocation.md](cost-allocation.md) produce already-converted
fields. Apply the normalization weight as a single multiplication:
`cost_weight = capability_usage × weight` (look up `weight` from
[Cost Normalization Weights](#cost-normalization-weights)). Safe because only one
weight is involved.

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

### Daily Cost Trend (unrated)

Track daily billable usage to detect spikes. Uses the same
[Combined Query](billing-capabilities.md#quick-overview--combined-query),
modified for daily bucketing.

Replace `<START>` / `<END>` with UTC midnight boundaries (e.g.,
`2026-03-01T00:00:00Z` / `2026-03-31T00:00:00Z`).

> **14-day limit** — Billed Metrics/Traces Ingest sub-queries use `timeseries`.
> For longer timeframes, use the
> [multi-window pattern](billing-capabilities.md#longer-timeframes-multi-window-pattern).

> **Unexplained Log Ingest spike?** A historical Log Import is an uncommon but
> easy-to-miss cause — it bills in the window the job ran, under the same
> `Log Management & Analytics - Ingest & Process` event type. Check `isNotNull(dt.job.id)` to rule it out — see
> [billing-event-types.md § Log Ingest Sources](billing-event-types.md#log-ingest-sources).

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

### Period Comparison (WoW / MoM) (unrated)

Compare two equal-length windows to surface what grew, shrank, or appeared.
Use for "compare last week to the week before", "what changed month over month",
or "what's trending up in spend".

> **Do not use `event_count` for period comparisons.** Billing event counts
> reflect emission frequency, not consumption volume — a 20% rise in event
> count does not mean 20% more GiB or hours consumed. Always compare
> `capability_usage` (capability units).

**Steps:**

1. **Run the [Estimated Cost by Capability (unrated)](#estimated-cost-by-capability-unrated) query
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

> For `join` command syntax, see `dt-dql-essentials`.

Each entry carries `unitDivisor` (bytes → capability unit conversion) plus
`factor` / `factorBase` (numerator and denominator of the normalization weight;
`weight = factor / factorBase`).

```dql-snippet
// --- Full Inline Lookup for Cost Rankings (append after summarize) ---
| join [
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
  ], on: {left[`event.type`] == right[event_type]}, prefix: "lookup.", kind: leftOuter
| fieldsAdd capability_usage = toDouble(billable_usage) / coalesce(lookup.unitDivisor, 1)
| fieldsAdd cost_weight = capability_usage / lookup.factorBase * lookup.factor
// finish with: | filter isNotNull(cost_weight) | sort cost_weight desc | fields event.type, capability_usage, cost_weight
```

> **Notes:**
> - `Files` types are mapped to `Events` normalization weights (see
>   [billing-capabilities.md § BUE-to-Capability Mapping](billing-capabilities.md#bue-to-capability-mapping)).
> - Preview types (`Digital Experience Monitoring - Query/Retain`) are omitted
>   from this unrated ranking — they return `null` for `cost_weight`. Filter with
>   `| filter isNotNull(cost_weight)` before sorting. (The rated path keeps them;
>   see [Rate Card Join Snippet](#rate-card-join-snippet).)
