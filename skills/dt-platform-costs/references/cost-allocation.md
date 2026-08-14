# Cost Allocation & Chargeback

Querying billing events for cost center and product attribution, building
chargeback and showback reports.

## Contents

- [Entity Attribution Fields](#entity-attribution-fields)
- [Cost Attribution Fields](#cost-attribution-fields)
- [Why String vs Record\[\]](#why-string-vs-record)
- [Field Type by Event Type](#field-type-by-event-type)
- [Chargeback Queries](#chargeback-queries)
  - [String-Type Cost Attribution](#string-type-cost-attribution)
  - [Record-Type Cost Attribution](#record-type-cost-attribution)
  - [Metrics Ingest — Billable Volume per Cost Center](#metrics-ingest--billable-volume-per-cost-center)
  - [Traces Ingest — Billable Volume per Cost Center](#traces-ingest--billable-volume-per-cost-center)
  - [Unified Chargeback (All Types)](#unified-chargeback-all-types)

## Entity Attribution Fields

Billing events carry entity and measurement window references that vary by
event type:

| Field | Type | Description |
|-------|------|-------------|
| `dt.entity.host` | string | Host entity ID (Host Monitoring, Security) |
| `dt.entity.application` | string | Application entity ID (RUM) |
| `dt.entity.kubernetes_cluster` | string | K8s cluster entity ID (K8s Platform Monitoring, SPM) |
| `dt.entity.synthetic_test` | string | Synthetic test entity ID (Browser Monitor) |
| `dt.entity.http_check` | string | HTTP check entity ID (HTTP Monitor — NOT `dt.entity.synthetic_test`) |
| `usage.start` / `usage.end` | timestamp | Measurement time window (typically 15 min) |
| `usage.bucket` | string | Grail bucket name for ingest/query/retain events |

> **Entity attribution varies by event type.** Retention events often lack
> entity references. Not all fields are present on all event types — check
> [billing-event-types.md](billing-event-types.md) for per-type field details.

## Cost Attribution Fields

Two fields carry cost allocation data on billing events:

| Field | Description |
|-------|-------------|
| `dt.cost.costcenter` | Cost center tag assigned to the monitored entity |
| `dt.cost.product` | Product tag assigned to the monitored entity |

These fields are **only populated when cost attribution tags are configured** on
monitored entities. Not all event types support them.

> **Pre-flight check — MUST run before building chargeback queries.** Coverage
> varies dramatically by environment and event type. If tags are not configured,
> chargeback queries return empty or near-empty results with no warning.

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| dedup {event.id, event.type}
| summarize
    total = count(),
    with_costcenter = countIf(isNotNull(dt.cost.costcenter)),
    by: {event.type}
| fieldsAdd coverage_pct = round(toDouble(with_costcenter) / total * 100, decimals: 1)
| sort coverage_pct desc
```

> If `coverage_pct` is zero or near-zero for key event types, cost attribution
> tags have not been applied to monitored entities. Configure `dt.cost.costcenter`
> tags on hosts/processes before relying on chargeback queries.

> **Important:** Dynatrace does not officially support querying `dt.cost.costcenter`
> and `dt.cost.product` together in the same aggregation. All built-in billing
> automation treats these two dimensions separately. Build chargeback queries
> against one dimension at a time.

## Why String vs Record[]

The type of `dt.cost.costcenter` / `dt.cost.product` depends on how the billing
system produces events for each capability:

- **String type** — Used when each billing event maps to a single entity (e.g.,
  one Full-Stack host, one Infrastructure host) so the cost center is simply the
  tag value from that entity. Also used for aggregated capabilities like Log
  Ingest and Traces Ingest where the system splits usage by cost center
  **before** writing the billing events.

- **Record[] type** — Used when technical limitations prevent pre-splitting
  usage by cost center. For Metrics Ingest and Log/Metrics Retain, a single
  billing event aggregates across many entities. The cost center breakdown must
  be embedded as an array of `{key, billed_amount}` records within each event.
  Queries must use `expand` to unnest these records before aggregation.

- **Not present** — Event types that have no entity relationship (query events,
  automation events) or where cost attribution is not applicable (RUM, synthetic,
  K8s).

## Field Type by Event Type

The type of `dt.cost.costcenter` and `dt.cost.product` varies:

### String type

Simple string values (e.g., `"quality-assurance/QA"`, `"stock-market-app"`):

- Full-Stack Monitoring
- Infrastructure Monitoring
- Foundation & Discovery
- Code Monitoring
- Data Egress
- Database Monitoring
- Log Management & Analytics - Ingest & Process
- Traces - Ingest & Process
- Runtime Application Protection
- Runtime Vulnerability Analytics

### Record[] type

Array of records, each containing a `key` (cost center/product name or
`"unassigned"`) and a billed quantity field:

| Event Type | Record Structure |
|------------|-----------------|
| `Log Management & Analytics - Retain` | `{key: string, billed_bytes: long}` |
| `Log Management & Analytics - Retain with Included Queries` | `{key: string, billed_bytes: long}` |
| `Metrics - Ingest & Process` | `{key: string, data_points: long}` |

### Not present

These event types do **not** have cost attribution fields:

- All Query events (Traces, Logs, Events, Files, DEM)
- All RUM events
- Synthetic monitoring events
- Kubernetes Platform Monitoring
- Automation Workflow, AppEngine Functions
- Events Ingest/Retain, Files Ingest/Query/Retain
- Security Posture Management

## Chargeback Queries

> All queries below use `dt.cost.costcenter`. Replace with `dt.cost.product`
> for product attribution — same field types, same query patterns.
>
> Replace `<START>` / `<END>` with UTC midnight boundaries (e.g.,
> `2026-03-01T00:00:00Z` / `2026-03-31T00:00:00Z`).

### String-Type Cost Attribution

For event types where `dt.cost.costcenter` is a string, filter and group
directly:

```dql-template
fetch dt.system.events, from: "<START>", to: "<END>"
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Full-Stack Monitoring"
| filter isNotNull(dt.cost.costcenter)
| dedup event.id
| summarize total_gib_hours = sum(billed_gibibyte_hours),
    by: {dt.cost.costcenter}
| sort total_gib_hours desc
```

Infrastructure Monitoring by cost center (host-hours):

```dql-template
fetch dt.system.events, from: "<START>", to: "<END>"
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Infrastructure Monitoring"
| filter isNotNull(dt.cost.costcenter)
| dedup event.id
| summarize total_host_hours = sum(billed_host_hours),
    by: {dt.cost.costcenter}
| sort total_host_hours desc
```

Log ingest by cost center (GiB):

```dql-template
fetch dt.system.events, from: "<START>", to: "<END>"
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Log Management & Analytics - Ingest & Process"
| filter isNotNull(dt.cost.costcenter)
| dedup event.id
| summarize total_gib = sum(billed_bytes) / 1073741824,
    by: {dt.cost.costcenter}
| sort total_gib desc
```

### Record-Type Cost Attribution

For event types where `dt.cost.costcenter` is `record[]`, use `expand` to
unnest records and index into the record fields:

Metrics ingest by cost center — **total** data points (before included volume
deduction):

> ⚠️ **This query shows total usage, not billable usage.** Metrics Ingest
> includes a baseline from host monitoring that is deducted before billing. For
> **billable** data points per cost center, use
> [Metrics Ingest — Billable Volume per Cost Center](#metrics-ingest--billable-volume-per-cost-center)
> instead.

```dql-template
fetch dt.system.events, from: "<START>", to: "<END>"
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Metrics - Ingest & Process"
| dedup event.id
| expand dt.cost.costcenter
| summarize total_data_points = sum(dt.cost.costcenter[data_points]),
    by: {costcenter = dt.cost.costcenter[key]}
| sort total_data_points desc
```

Log retention by cost center (GiB-days). Divide by `25769803776`
(`unitDivisor` for retain — see
[billing-capabilities.md § Unit Conversion Table](billing-capabilities.md#unit-conversion-table)):

```dql-template
fetch dt.system.events, from: "<START>", to: "<END>"
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Log Management & Analytics - Retain"
| dedup event.id
| expand dt.cost.costcenter
| summarize total_gib_days = sum(dt.cost.costcenter[billed_bytes]) / 25769803776,
    by: {costcenter = dt.cost.costcenter[key]}
| sort total_gib_days desc
```

### Metrics Ingest — Billable Volume per Cost Center

Metrics Ingest includes a baseline of data points from host monitoring (see
[billing-capabilities.md § Included Volume](billing-capabilities.md#included-volume)).
The [total data points query](#record-type-cost-attribution) above does **not**
deduct this baseline — it overstates billable usage. This query computes
**billable** data points per cost center using the same algorithm the billing
system uses internally.

> **No 14-day limitation.** Unlike the global
> [Metrics Ingest — Billable Volume](billing-capabilities.md#metrics-ingest--billable-volume)
> query (which uses `timeseries` for included volume metrics), this query
> computes included volume from **host monitoring BUEs** — no timeseries
> dependency, works for any timeframe.

#### Algorithm

1. **Expand** Metrics BUEs by cost center → `{costcenter, data_points,
   monitoring_source}` per 15-min slot
2. **Join** Full-Stack / Infrastructure BUEs (same slot, cost center,
   monitoring_source) to compute **per-cost-center included volume**:
   `included = billed_host_value × 4 × multiplier` (900 for fullstack, 1500
   for infrastructure)
3. **Subtract** included volume per cost center → per-cost-center billable
4. **Proportionally redistribute** — the global billable total
   (`total_data_points − included_total`) is distributed proportionally to each
   cost center's share of the billable-after-deduction pool. This ensures cost
   center totals sum exactly to the global billable total.

#### Included Volume Multipliers

See [billing-capabilities.md § Metrics Ingest — Included Volume](billing-capabilities.md#metrics-ingest--included-volume)
for the full multiplier table. Summary: fullstack = `billed_gibibyte_hours × 4 × 900`,
infrastructure = `billed_host_hours × 4 × 1500`, other/discovery = 0.

#### Query

> Replace `<START>` / `<END>` with UTC midnight boundaries. Replace
> `<END_PLUS_5H>` with `<END>` + 5 hours (Metrics Ingest emission lag — see
> [billing-capabilities.md § Billing Event Emission Lag](billing-capabilities.md#billing-event-emission-lag)).
> Both the outer fetch and the join subquery use `<END_PLUS_5H>` — the join's
> `usage.start < toTimestamp("<END>")` filter prevents over-counting regardless
> of the fetch window. Do NOT use plain `<END>` for either fetch here.
>
> Uses `dt.cost.costcenter`. Replace with `dt.cost.product` for product
> attribution — same field types, same query pattern.

```dql-template
fetch dt.system.events, from: "<START>", to: "<END_PLUS_5H>"
| filter event.kind == "BILLING_USAGE_EVENT" and event.type == "Metrics - Ingest & Process"
| filter usage.start >= toTimestamp("<START>") and usage.start < toTimestamp("<END>")
| dedup event.id
| expand dt.cost.costcenter
| fieldsFlatten dt.cost.costcenter
| fields
    usage.start,
    dt.cost.costcenter = if(isNull(dt.cost.costcenter.key), "unassigned", else: dt.cost.costcenter.key),
    data_points = toLong(dt.cost.costcenter.data_points),
    monitoring_source = if(monitoring_source == "fullstack" or monitoring_source == "infrastructure", monitoring_source, else: "other")
| summarize data_points = toLong(sum(data_points)),
    by: {usage.start, dt.cost.costcenter, monitoring_source}
| join [
    fetch dt.system.events, from: "<START>", to: "<END_PLUS_5H>"
    | filter event.kind == "BILLING_USAGE_EVENT"
    | filter in(event.type, { "Full-Stack Monitoring", "Infrastructure Monitoring" })
    | filter usage.start >= toTimestamp("<START>") and usage.start < toTimestamp("<END>")
    | dedup {event.id, event.type}
    | fields
        usage.start,
        dt.cost.costcenter = if(isNotNull(dt.cost.costcenter), dt.cost.costcenter, else: "unassigned"),
        billed_value = coalesce(
            if(exists(billed_gibibyte_hours), billed_gibibyte_hours, else: null),
            if(exists(billed_host_hours), billed_host_hours, else: null)),
        monitoring_source = if(event.type == "Full-Stack Monitoring", "fullstack",
            else: if(event.type == "Infrastructure Monitoring", "infrastructure"))
    | summarize billed = sum(billed_value),
        by: {usage.start, dt.cost.costcenter, monitoring_source}
    | fieldsAdd included_usage_per_costcenter = billed * 4
        * if(monitoring_source == "fullstack", 900,
            else: if(monitoring_source == "infrastructure", 1500, else: 0))
  ], on: {usage.start, dt.cost.costcenter, monitoring_source}, kind: leftOuter,
    fields: {included_usage_per_costcenter}
| fieldsAdd included_usage_per_costcenter = if(isNotNull(included_usage_per_costcenter), included_usage_per_costcenter, else: 0)
| fieldsAdd billable_costcenter = if(data_points > included_usage_per_costcenter, data_points - included_usage_per_costcenter, else: 0)
| summarize
    total_data_points = sum(data_points),
    included_total = sum(included_usage_per_costcenter),
    billable_costcenter_total = sum(billable_costcenter),
    rec = collectArray(record(dt.cost.costcenter, billable_costcenter, included_usage_per_costcenter)),
    by: {usage.start, monitoring_source}
| fieldsAdd billable_total = if(total_data_points > included_total, total_data_points - included_total, else: 0)
| expand rec
| fieldsAdd total_per_costcenter = rec[billable_costcenter] / billable_costcenter_total * billable_total
| summarize total_per_costcenter = sum(total_per_costcenter),
    by: {dt.cost.costcenter = rec[dt.cost.costcenter]}
| sort total_per_costcenter desc
```

> **How proportional redistribution works:** Per-cost-center included volume
> deduction can produce rounding artifacts where cost center subtotals don't
> sum to the global billable total. The final step normalizes: the global
> billable total (`total_data_points − included_total`) is distributed in
> proportion to each cost center's share of the pre-redistribution billable
> pool.

> **Accuracy:** Results may differ slightly from Account Management due to
> rounding and differences in included volume computation. Account Management
> is the source of truth for billable totals.

### Traces Ingest — Billable Volume per Cost Center

Traces Ingest includes a baseline of trace volume from Full-Stack Monitoring
(see [billing-capabilities.md § Included Volume](billing-capabilities.md#included-volume)).
A simple `summarize sum(ingested_bytes), by: {dt.cost.costcenter}` shows
**total** usage, not **billable** usage — it overstates cost. This query
computes billable bytes per cost center using the same algorithm the billing
system uses internally.

> **14-day limitation.** This query uses `timeseries` for included volume
> metrics (`dt.billing.traces.*`). For timeframes longer than 14 days, use the
> [multi-window pattern](billing-capabilities.md#longer-timeframes-multi-window-pattern) —
> split into ≤ 14-day windows and sum results.

> **⚠️ Silent coarsening risk.** The `15 *` multiplier on `included_volume`
> (line below) assumes 15-minute `timeseries` intervals. If the window exceeds
> 15 days, the interval silently doubles to 30 minutes and the included volume
> deduction is **halved** — inflating billable volumes with no error. Keep
> windows ≤ 14 days. See
> [billing-capabilities.md § 14-Day Limitation](billing-capabilities.md#14-day-limitation).

#### Algorithm

1. **Fetch** Traces BUEs per 15-min slot by cost center; bucket
   `licensing_type` into `fullstack-adaptive`, `fullstack-fixed-rate`, `other`
   (OTLP + serverless)
2. **Compute ratio** — Full-Stack BUE `billed_gibibyte_hours` per cost center
   divided by total Full-Stack usage per slot → each cost center's share
3. **Distribute included volume** — join included volume metrics, multiply by
   per-cost-center ratio → `included_volume_costcenter`
4. **Apply billable formula** (two modes per slot):
   - ATM enabled (`configured > included`):
     `billable = adaptive + fixed_rate − included`
   - ATM disabled: `billable = fixed_rate − max(0, included − adaptive)`
5. **Proportionally redistribute** — same pattern as
   [Metrics Ingest](#metrics-ingest--billable-volume-per-cost-center):
   the global billable fullstack total is distributed proportionally to each
   cost center's share. `other` volume (OTLP + serverless) is added directly
   (always fully billed).

#### Licensing Types

See [billing-capabilities.md § Traces Ingest — Included Volume](billing-capabilities.md#traces-ingest--included-volume)
for the full licensing type table and deduction logic.

#### Query

> Replace `<START>` / `<END>` with UTC midnight boundaries (≤ 14 days apart).
>
> Uses `dt.cost.costcenter`. Replace with `dt.cost.product` for product
> attribution — same field types, same query pattern.

```dql-template
fetch dt.system.events, from: "<START>", to: "<END>"
| filter event.kind == "BILLING_USAGE_EVENT" and event.type == "Traces - Ingest & Process"
| fieldsKeep usage.start, licensing_type, ingested_bytes, dt.cost.costcenter, event.id
| dedup event.id
| fieldsAdd licensing_type = if(in(licensing_type, {"otlp-trace-ingest", "serverless"}), "other", else: licensing_type)
| fieldsAdd adaptive_volume = if(licensing_type == "fullstack-adaptive", ingested_bytes)
| fieldsAdd fixed_rate_volume = if(licensing_type == "fullstack-fixed-rate", ingested_bytes)
| fieldsAdd other_volume = if(licensing_type == "other", ingested_bytes)
| fieldsAdd dt.cost.costcenter = if(isNull(dt.cost.costcenter), "unassigned", else: dt.cost.costcenter)
| makeTimeseries interval: 15m, time: usage.start, from: toTimestamp("<START>"), to: toTimestamp("<END>"), by: {dt.cost.costcenter}, nonempty: true, {
    adaptive_volume = sum(adaptive_volume, default: 0),
    fixed_rate_volume = sum(fixed_rate_volume, default: 0),
    other_volume = sum(other_volume, default: 0)
  }
// join with per-cost-center included volume (derived from Full-Stack BUE ratio × global included volume metrics)
| join [
  fetch dt.system.events, from: "<START>", to: "<END>"
  | filter event.kind == "BILLING_USAGE_EVENT"
  | filter event.type == "Full-Stack Monitoring"
  | fieldsKeep usage.start, billed_gibibyte_hours, dt.cost.costcenter, event.id
  | dedup event.id
  | fieldsAdd dt.cost.costcenter = if(isNull(dt.cost.costcenter), "unassigned", else: dt.cost.costcenter)
  | makeTimeseries { billed = sum(billed_gibibyte_hours) }, by: { dt.cost.costcenter }, time: usage.start, from: toTimestamp("<START>"), to: toTimestamp("<END>"), interval: 15m
  | summarize by: { timeframe, interval }, { total = sum(billed[]), r = collectArray(record(dt.cost.costcenter, billed)) }
  | expand r
  | fieldsFlatten r, fields: { dt.cost.costcenter, billed }
  | fieldsAdd ratio = billed[] / total[]
  | fields timeframe, interval, dt.cost.costcenter, ratio
  | join [
      timeseries interval: 15m, union: true, from: "<START>", to: "<END>", nonempty: true, bucket: {"default_metrics"}, {
        included_volume = max(dt.billing.traces.maximum_included_fullstack_volume_per_minute, default: null),
        configured_volume = max(dt.billing.traces.maximum_configured_fullstack_volume_per_minute, default: null)
      }
      | fieldsAdd extra_ingest_on = configured_volume[] > included_volume[]
      | fieldsAdd included_volume = 15 * if(isNull(configured_volume[]), null, else: included_volume[])
    ], on: { timeframe, interval }, fields: { included_volume, extra_ingest_on }
  | fieldsAdd included_volume_costcenter = included_volume[] * ratio[]
  | fieldsAdd dt.cost.costcenter = if(isNull(dt.cost.costcenter), "unassigned", else: dt.cost.costcenter)
  ], on: { timeframe, interval, dt.cost.costcenter }, kind: outer, prefix: "r."
// coalesce fields from outer join — ensure every row has timeframe, interval, cost center
| fieldsAdd timeframe = coalesce(timeframe, r.timeframe)
| fieldsAdd interval = coalesce(interval, r.interval)
| fieldsAdd dt.cost.costcenter = coalesce(dt.cost.costcenter, r.dt.cost.costcenter)
// derive a template array for null-fill (at least one side of the outer join always has data)
| fieldsAdd _template = coalesce(adaptive_volume, r.included_volume_costcenter)
| fieldsAdd extra_ingest_on = if(exists(r.extra_ingest_on) and isNotNull(r.extra_ingest_on), r.extra_ingest_on, else: iCollectArray(_template[] * 0 == 1))
| fieldsAdd adaptive_volume = if(exists(adaptive_volume) and isNotNull(adaptive_volume), iCollectArray(coalesce(adaptive_volume[], 0)), else: iCollectArray(_template[] * 0))
| fieldsAdd fixed_rate_volume = if(exists(fixed_rate_volume) and isNotNull(fixed_rate_volume), iCollectArray(coalesce(fixed_rate_volume[], 0)), else: iCollectArray(_template[] * 0))
| fieldsAdd other_volume = if(exists(other_volume) and isNotNull(other_volume), iCollectArray(coalesce(other_volume[], 0)), else: iCollectArray(_template[] * 0))
| fieldsAdd included_volume_costcenter = if(exists(r.included_volume_costcenter) and isNotNull(r.included_volume_costcenter), r.included_volume_costcenter, else: iCollectArray(_template[] * 0))
| fieldsKeep timeframe, interval, dt.cost.costcenter, adaptive_volume, fixed_rate_volume, other_volume, included_volume_costcenter, extra_ingest_on
// per-slot billable fullstack calculation
| fieldsAdd license_remaining = included_volume_costcenter[] - adaptive_volume[]
| fieldsAdd license_remaining = if(license_remaining[] > 0, license_remaining[], else: 0)
| fieldsAdd billable_fullstack = if(isNull(included_volume_costcenter[]), 0, else: if(extra_ingest_on[], adaptive_volume[] + fixed_rate_volume[] - included_volume_costcenter[], else: fixed_rate_volume[] - license_remaining[]))
| fieldsAdd billable_fullstack = if(billable_fullstack[] > 0, billable_fullstack[], else: 0)
// proportional redistribution
| summarize {
    total_included = sum(included_volume_costcenter[]),
    total_adaptive = sum(adaptive_volume[]),
    total_fixed_rate = sum(fixed_rate_volume[]),
    total_to_allocate = sum(billable_fullstack[]),
    r = collectArray(record(extra_ingest_on, billable_fullstack, billable_other = other_volume, dt.cost.costcenter, included_volume_costcenter))
  }, by: { timeframe, interval }
| expand r
| fieldsFlatten r
| fieldsRemove r
| fieldsAdd total_license_remaining = total_included[] - total_adaptive[]
| fieldsAdd total_license_remaining = if(total_license_remaining[] > 0, total_license_remaining[], else: 0)
| fieldsAdd total_applicable_fullstack = if(isNull(total_included), 0, else: if(r.extra_ingest_on[], total_adaptive[] + total_fixed_rate[] - total_included[], else: total_fixed_rate[] - total_license_remaining[]))
| fieldsAdd total_billable_fullstack = if(total_applicable_fullstack[] > 0, total_applicable_fullstack[], else: 0)
| fieldsAdd distributed_fullstack = if(total_to_allocate[] <= 0, 0, else: r.billable_fullstack[] / total_to_allocate[] * total_billable_fullstack[])
| fieldsAdd adjusted = iCollectArray(toDouble(distributed_fullstack[] + r.billable_other[]))
| fields dt.cost.costcenter = r.dt.cost.costcenter, total_per_costcenter = arraySum(adjusted)
| filterOut isNull(total_per_costcenter)
| sort total_per_costcenter desc
```

> **Output:** `total_per_costcenter` is in **bytes**. Divide by 1,073,741,824
> for GiB.

> **How proportional redistribution works:** Same pattern as
> [Metrics Ingest](#metrics-ingest--billable-volume-per-cost-center) — the
> global billable fullstack total is distributed proportionally to each cost
> center's share. This ensures cost center totals sum to the global billable
> total. `other` volume (OTLP + serverless) is added directly without
> redistribution since it is always fully billed.

> **Accuracy:** Results may differ slightly from Account Management due to
> rounding and differences in included volume computation. Account Management
> is the source of truth for billable totals.

### Unified Chargeback (All Types)

Single query handling both string and record[] cost center types. Builds on the
[Base Usage](billing-capabilities.md#base-usage) query from
`billing-capabilities.md` (which produces a `usage` field via `coalesce` +
`dedup {event.id, event.type}`), then applies cost-center-specific logic.

> **Scope:** This snippet covers standard billing types only (those handled by
> the Base Usage query). Excluded:
> - **Metrics Ingest** — requires included volume deduction per cost center;
>   use [Metrics Ingest — Billable Volume per Cost Center](#metrics-ingest--billable-volume-per-cost-center)
> - **Traces Ingest** — requires included volume deduction per cost center;
>   use [Traces Ingest — Billable Volume per Cost Center](#traces-ingest--billable-volume-per-cost-center)
> - **Automation Workflow, SPM** — lack cost attribution fields (see
>   [Not present](#not-present))

DQL behavior exploited:
- `expand` on a string is a no-op — works for both string and record[] types
- `coalesce(c[key], c)` — extracts key from records, uses string directly
- `coalesce(c[data_points], c[billed_bytes], usage)` — picks the
  record value field or falls back to the coalesced usage field

```dql-snippet
// After the Base Usage query from billing-capabilities.md (produces {event.type, usage} per event):
| filter isNotNull(dt.cost.costcenter)
| expand c = dt.cost.costcenter
| fieldsAdd
    cc = coalesce(c[key], c),
    v = coalesce(c[data_points], c[billed_bytes], usage)
| summarize by: {event.type, dt.cost.costcenter = cc}, raw_usage = sum(v)
| sort event.type, dt.cost.costcenter
```

> **Caution:** `raw_usage` values are in **raw units** (data points, bytes,
> host-hours, GiB-hours) which differ per event type. Do not sum across event
> types without unit conversion. For cross-type cost ranking, rename the output
> field to `billable_usage` and append the
> [Full Inline Lookup for Cost Rankings](cost-estimations.md#full-inline-lookup-for-cost-rankings)
> — it handles both unit conversion and cost-weight computation in DQL.
