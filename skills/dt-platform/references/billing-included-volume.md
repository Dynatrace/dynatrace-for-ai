# Included Volume Calculation

Some DPS capabilities include a baseline volume that is deducted before billing.
This affects **Metrics Ingest** and **Traces Ingest** — the raw `data_points` /
`ingested_bytes` fields on billing events represent *total* usage, not *billed*
usage. To calculate what is actually billed, the included volume from host
monitoring must be subtracted.

## Contents

- [14-Day Limitation](#14-day-limitation)
- [Metrics Ingest — Included Volume](#metrics-ingest--included-volume)
  - [How It Works](#how-it-works)
  - [Included Volume Metrics](#included-volume-metrics)
  - [Billed Usage Query](#billed-usage-query)
  - [Billed Usage by Monitoring Source](#billed-usage-by-monitoring-source)
- [Traces Ingest — Included Volume](#traces-ingest--included-volume)
  - [How It Works](#how-it-works-1)
  - [Licensing Types](#licensing-types)
  - [Included Volume Metrics](#included-volume-metrics-1)
  - [Billed Usage by Monitoring Source](#billed-usage-by-monitoring-source-1)
- [Longer Timeframes (Multi-Window Pattern)](#longer-timeframes-multi-window-pattern)
- [When to Use These Queries](#when-to-use-these-queries)

## 14-Day Limitation

> **These queries provide accurate data for up to 14 days only.** The included
> volume calculation uses the `timeseries` command to read host monitoring
> metrics (`dt.billing.*`). The `timeseries` command has a maximum lookback of
> ~14 days for fine-grained data. For precise values over longer periods, use
> Account Management (**Subscription** > **Overview** > **Cost and usage
> details**).

## Metrics Ingest — Included Volume

### How It Works

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

### Included Volume Metrics

| Metric Key | Description |
|------------|-------------|
| `dt.billing.full_stack_monitoring.usage` | Current Full-Stack GiB-hours |
| `dt.billing.infrastructure_monitoring.usage` | Current Infrastructure GiB-hours |

These are standard Dynatrace metrics queried via the `timeseries` command. The
included data points per 15-min interval are calculated by multiplying the
GiB-hours value by the per-mode multiplier.

### Billed Usage Query

Total billed metric data points (after deducting included volume):

```dql
fetch dt.system.events, from: -14d
| filter event.kind == "BILLING_USAGE_EVENT"
    and event.type == "Metrics - Ingest & Process"
| dedup event.id
| summarize total_data_points = toLong(sum(data_points)),
    by: {usage.start, monitoring_source}
| makeTimeseries {total_usage = sum(total_data_points, default: 0)},
    interval: 15m, time: usage.start, by: {monitoring_source}
| join [
    timeseries {included_usage = sum(dt.billing.full_stack_monitoring.usage,
        default: 0)}, interval: 15m, nonempty: true
    | fields monitoring_source = "fullstack",
        included_usage = 4 * 900 * included_usage[]
    | append [
        timeseries {included_usage = sum(
            dt.billing.infrastructure_monitoring.usage, default: 0)},
            interval: 15m, nonempty: true
        | fields monitoring_source = "infrastructure",
            included_usage = 4 * 1500 * included_usage[]
    ]
  ], on: {monitoring_source}, fields: {included_usage}, kind: leftOuter
| fieldsAdd billed_usage = if(isNotNull(included_usage)
    and total_usage[] > included_usage[],
    total_usage[] - included_usage[], else: 0)
| fieldsAdd billed_usage = if(isNull(included_usage),
    total_usage, else: billed_usage)
| fieldsAdd billed_usage = arraySum(billed_usage)
| fieldsKeep monitoring_source, billed_usage
| summarize total_billed = sum(billed_usage)
```

### Billed Usage by Monitoring Source

Breakdown of billed data points per monitoring source (after included volume
deduction):

```dql
fetch dt.system.events, from: -14d
| filter event.kind == "BILLING_USAGE_EVENT"
    and event.type == "Metrics - Ingest & Process"
| dedup event.id
| summarize total_data_points = toLong(sum(data_points)),
    by: {usage.start, monitoring_source}
| makeTimeseries {total_usage = sum(total_data_points, default: 0)},
    interval: 15m, time: usage.start, by: {monitoring_source}
| join [
    timeseries {included_usage = sum(dt.billing.full_stack_monitoring.usage,
        default: 0)}, interval: 15m, nonempty: true
    | fields monitoring_source = "fullstack",
        included_usage = 4 * 900 * included_usage[]
    | append [
        timeseries {included_usage = sum(
            dt.billing.infrastructure_monitoring.usage, default: 0)},
            interval: 15m, nonempty: true
        | fields monitoring_source = "infrastructure",
            included_usage = 4 * 1500 * included_usage[]
    ]
  ], on: {monitoring_source}, fields: {included_usage}, kind: leftOuter
| fieldsAdd billed_usage = if(isNotNull(included_usage)
    and total_usage[] > included_usage[],
    total_usage[] - included_usage[], else: 0)
| fieldsAdd billed_usage = if(isNull(included_usage),
    total_usage, else: billed_usage)
| fieldsAdd billed_usage = arraySum(billed_usage)
| summarize billed_usage = sum(billed_usage),
    by: {timeframe, interval, monitoring_source}
```

## Traces Ingest — Included Volume

### How It Works

Full-Stack Monitoring includes a baseline of trace data volume. Traces from
Full-Stack monitored hosts and containers are only billed on the Traces Ingest
capability when they **exceed** this included volume. Traces from non-Full-Stack
sources (OTLP API, serverless) are always fully billed.

The included volume calculation is per 15-minute interval:

1. Compare Full-Stack trace ingest against the included volume limit
2. If the configured Adaptive Traffic Management limit exceeds the included
   volume **and** actual ingest exceeds the included volume, the excess is
   charged as `fullstack-adaptive`
3. Any remaining Full-Stack OTLP trace data that exceeds the leftover included
   volume is charged as `fullstack-fixed-rate`

### Licensing Types

The `licensing_type` field on Traces Ingest billing events identifies the source:

| Licensing Type | Description | Billed? |
|----------------|-------------|---------|
| `fullstack-adaptive` | OneAgent trace data exceeding included volume (with Adaptive Traffic Management configured) | Only the excess |
| `fullstack-fixed-rate` | OTLP traces from Full-Stack hosts/containers exceeding included volume | Only the excess |
| `otlp-trace-ingest` | OTLP traces from non-Full-Stack sources | Always fully billed |
| `serverless` | Traces from serverless environments | Always fully billed |

### Included Volume Metrics

| Metric Key | Description |
|------------|-------------|
| `dt.billing.traces.maximum_included_fullstack_volume_per_minute` | Included Full-Stack trace volume (bytes/min) |
| `dt.billing.traces.maximum_configured_fullstack_volume_per_minute` | Configured Adaptive Traffic Management limit (bytes/min) |

### Billed Usage by Monitoring Source

Total billed trace ingest by source (after deducting included Full-Stack
volume):

```dql
fetch dt.system.events, from: -14d
| filter event.kind == "BILLING_USAGE_EVENT"
    and event.type == "Traces - Ingest & Process"
| dedup event.id
| makeTimeseries {ingested_bytes = sum(ingested_bytes, default: 0)},
    interval: 15m, time: usage.start, by: {licensing_type}, nonempty: true
| append [
    timeseries {
        license_limit = avg(
            dt.billing.traces.maximum_included_fullstack_volume_per_minute),
        configured_volume = avg(
            dt.billing.traces.maximum_configured_fullstack_volume_per_minute)
    }, interval: 15m, nonempty: true
    | fieldsAdd interval_in_minutes = toLong(interval) / 60000000000
    | fieldsAdd license_limit = license_limit[] * interval_in_minutes
    | fieldsAdd configured_volume = configured_volume[] * interval_in_minutes
    | fields license_limit, configured_volume,
        helper_zeroes = license_limit[] * 0, timeframe, interval
  ]
| summarize {
    adaptive_volume = takeFirst(
        if(licensing_type == "fullstack-adaptive", ingested_bytes)),
    fixed_rate_volume = takeFirst(
        if(licensing_type == "fullstack-fixed-rate", ingested_bytes)),
    otlp_volume = takeFirst(
        if(licensing_type == "otlp-trace-ingest", ingested_bytes)),
    serverless_volume = takeFirst(
        if(licensing_type == "serverless", ingested_bytes)),
    license_limit = takeFirst(license_limit),
    configured_volume = takeFirst(configured_volume),
    helper_zeroes = takeFirst(helper_zeroes)
  }
| fieldsAdd adaptive_volume = coalesce(adaptive_volume, helper_zeroes),
    fixed_rate_volume = coalesce(fixed_rate_volume, helper_zeroes),
    otlp_volume = coalesce(otlp_volume, helper_zeroes),
    serverless_volume = coalesce(serverless_volume, helper_zeroes)
| fieldsAdd adaptive_volume_charged = if(
    configured_volume[] > license_limit[]
        AND adaptive_volume[] > license_limit[],
    adaptive_volume[] - license_limit[], else: 0)
| fieldsAdd lic_remain = if(license_limit[] - adaptive_volume[] > 0,
    license_limit[] - adaptive_volume[], else: 0)
| fieldsAdd fixed_rate_volume_charged = if(
    fixed_rate_volume[] - lic_remain[] > 0
        AND isNotNull(license_limit[]),
    fixed_rate_volume[] - lic_remain[], else: 0)
| fieldsAdd fullstack = adaptive_volume_charged[] + fixed_rate_volume_charged[]
| fields fullstack = toLong(arraySum(fullstack)),
    otlp = toLong(arraySum(otlp_volume)),
    serverless = toLong(arraySum(serverless_volume))
| fields total = array(
    record(value = fullstack, monitoring_source = "fullstack"),
    record(value = otlp, monitoring_source = "otlp-trace-ingest"),
    record(value = serverless, monitoring_source = "serverless"))
| expand total
| fields total = total[value], monitoring_source = total[monitoring_source]
```

> **Note:** The `total` values are in bytes. Divide by 1,073,741,824 for GiB.

## Longer Timeframes (Multi-Window Pattern)

The `timeseries` command limits included-volume queries to **≤ 14 days** per
query. For longer timeframes, split the period into consecutive windows of
≤ 14 days each and run one query per window.

### How It Works

1. Divide the requested timeframe into N windows, each ≤ 14 days.
2. Run the included-volume query (Metrics or Traces) once per window, adjusting
   `from:` and `to:` for each.
3. Sum `billed_data_points` (Metrics) or `billed_bytes` (Traces) across all
   windows for the total billed usage over the full period.

### Example — 30-Day Metrics Ingest

A 30-day request requires 3 windows (14d + 14d + 2d). Run the
[Billed Usage Query](#billed-usage-query) three times with these time ranges:

| Window | `from:` | `to:` |
|--------|---------|-------|
| 1 | `-30d` | `-16d` |
| 2 | `-16d` | `-2d` |
| 3 | `-2d` | `now()` |

Sum the `billed_data_points` from each result for the 30-day total.

> **Agent instruction:** When the user requests included-volume analysis for
> more than 14 days, automatically split into multiple queries. State the number
> of windows and present both per-window and summed totals.

## When to Use These Queries

| Scenario | Use Included Volume Queries? |
|----------|------------------------------|
| Simple cost overview / spike detection | No — use `data_points` / `ingested_bytes` directly |
| Accurate billed consumption (< 14 days) | Yes — these queries deduct included volume |
| Accurate billed consumption (> 14 days) | Yes — use the [multi-window pattern](#longer-timeframes-multi-window-pattern) to split into ≤ 14-day queries |
| Rate card cost estimation | Depends — [cost-estimations.md](cost-estimations.md) queries use raw totals; for precise cost, subtract included volume first |
| Cost center chargeback | See the Metrics Ingest cost allocation queries in the notebooks linked from Account Management |
