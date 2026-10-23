# Metrics Ingest Cost Optimization

Actionable strategies to reduce Metrics — Ingest & Process costs. Metrics
ingest is typically the leading cost driver among the three metrics billing
capabilities (Ingest & Process, Retain, Query), because retention is included
at no cost for the first 15 months and queries are included at no cost.

Based on [Dynatrace docs: Best practices for optimizing metrics cost](https://docs.dynatrace.com/docs/analyze-explore-automate/metrics/best-practices-metrics).

Use this reference **after** identifying metrics ingest as a top cost driver
via [cost-estimations.md](cost-estimations.md) or
[entity-cost-drilldown.md](entity-cost-drilldown.md).

## Contents

- [Core Concepts](#core-concepts)
- [Billable vs Non-Billable Metrics](#billable-vs-non-billable-metrics)
- [Analyze Metrics Ingest](#analyze-metrics-ingest)
  - [Step 1 — Break Down by Source and by Cost Center + Product](#step-1--break-down-by-source-and-by-cost-center--product)
  - [Step 2 — Top Metric Keys Across All Sources](#step-2--top-metric-keys-across-all-sources)
- [OTel Collector Self-Monitoring Metrics](#otel-collector-self-monitoring-metrics)
  - [Debug Exporter](#debug-exporter)
- [Optimization Strategies](#optimization-strategies)
- [Ongoing Cost Management](#ongoing-cost-management)
- [Best Practices](#best-practices)

## Core Concepts

| Term | Definition |
|------|------------|
| Metric | A named numerical measurement observed over time |
| Dimension | A key-value pair used to filter, split, or group metrics |
| Metric data point | A single recorded value at a specific point in time |
| Timeseries | A unique combination of a metric and its dimension values |
| Cardinality | The number of unique timeseries a metric produces |

Ingested data points depend on three factors: **number of metrics**,
**collection intervals**, and **cardinality**. Any increase in these factors
raises consumption.

## Billable vs Non-Billable Metrics

Not all ingested metrics are billed. NEVER include non-billable metrics in cost
rankings or cost estimates — they inflate numbers and mislead users.

### Billable Rules

| Rule | Billable? |
|------|-----------|
| `dt.*` keys (default) | **No** — most `dt.*` built-in metrics are zero-rated |
| `dt.cloud.aws.*` (except `dt.cloud.aws.az.running`) | **Yes** |
| `dt.cloud.azure.*` (except 6 VM count metrics¹) | **Yes** |
| `dt.osservice.*` | **Yes** |
| `dt.service.*` | **Yes** (charged as Metrics Ingest unless originating from Full-Stack hosts²) |
| `dt.synthetic.multi_protocol.*` (8 NAM metrics³) | **Yes** |
| Non-`dt.*` keys (custom, extension, OTel) | **Yes** |
| Any key in bucket `dt_system_metrics` | **No** |
| Metrics with `grail.monitoring_source` set (mainframe/legacy) | **No** |

¹ Non-billable Azure VM metrics: `dt.cloud.azure.region.vms.initializing`,
`.running`, `.stopped`, `dt.cloud.azure.vm_scale_set.vms.initializing`,
`.running`, `.stopped`

² `dt.service.*` from Full-Stack hosts consume included volume, not Metrics
Ingest. From other sources, they are charged as Metrics Ingest.

³ NAM metrics: `dt.synthetic.multi_protocol.request.availability`,
`.request.executions`, `.icmp.success_rate`, `.icmp.packets_sent`,
`.icmp.packets_received`, `.icmp.round_trip_time`, `.tcp.connection_time`,
`.dns.resolution_time`

Also non-billable: `legacy.containers.*`, `legacy.dotnet.perform.*`,
`legacy.tomcat.*`

Source: [Dynatrace docs: Billable and non-billable metrics](https://docs.dynatrace.com/docs/license/capabilities/metrics/dps-metrics-ingest#billable-and-non-billable-metrics)

### Billable Metrics Filter

Use this filter in `timeseries` queries on `dt.sfm.metrics.ingest.datapoints`
to restrict results to billable metrics only. Apply it in Steps 1 and 2.
In `dql-template` blocks below, replace `<Billable Metrics Filter>` with the
full filter block shown here.

**MUST copy this filter verbatim — NEVER abbreviate or omit clauses.**

```dql-snippet
// Billable metrics filter — use in timeseries filter: clause
(startswith(grail.metric.key, "dt.service.")
  or startswith(grail.metric.key, "dt.cloud.aws")
  or startswith(grail.metric.key, "dt.cloud.azure")
  or startswith(grail.metric.key, "dt.osservice.")
  or in(grail.metric.key,
    "dt.synthetic.multi_protocol.request.availability",
    "dt.synthetic.multi_protocol.request.executions",
    "dt.synthetic.multi_protocol.icmp.success_rate",
    "dt.synthetic.multi_protocol.icmp.packets_sent",
    "dt.synthetic.multi_protocol.icmp.packets_received",
    "dt.synthetic.multi_protocol.icmp.round_trip_time",
    "dt.synthetic.multi_protocol.tcp.connection_time",
    "dt.synthetic.multi_protocol.dns.resolution_time")
  or NOT startswith(grail.metric.key, "dt."))
and not in(grail.metric.key,
  "dt.cloud.aws.az.running",
  "dt.cloud.azure.region.vms.initializing",
  "dt.cloud.azure.region.vms.running",
  "dt.cloud.azure.region.vms.stopped",
  "dt.cloud.azure.vm_scale_set.vms.initializing",
  "dt.cloud.azure.vm_scale_set.vms.running",
  "dt.cloud.azure.vm_scale_set.vms.stopped")
and isnull(grail.monitoring_source)
and grail.bucket.name!="dt_system_metrics"
and grail.metric.key!="..."
```

> **When to omit this filter:** If the user explicitly asks about *all* ingested
> metrics (including non-billable), run without the filter but clearly label
> results as "total ingest (including non-billable metrics)".

> **Lower-bound disclosure:** `dt.sfm.metrics.ingest.datapoints` aggregates keys
> beyond its top-N individually reported entries under `"..."`. Always exclude
> this bucket with `grail.metric.key!="..."`. Per-key values are a lower bound —
> keys outside the top-N are not individually visible.

### Histogram Weighting

Histogram metrics are billed at **10x the weight** of scalar metrics. Always
apply the multiplier below when computing data point volumes:

```dql-snippet
| fieldsadd data_points=if(
    grail.metric.type=="histogram"
    and not startswith(grail.metric.key,"dt.service."),
    10, else:1)*data_points
```

**NEVER omit this multiplier** — without it, histogram metrics are severely
underweighted and rankings are misleading.

## Analyze Metrics Ingest

Before optimizing, identify which metrics and sources drive the most ingest.
Follow the two-step workflow below **in order** — each step narrows scope and
increases detail.

> **NEVER expose internal workflow steps to the user.** Do not say "Step 1",
> "Step 2", "proceed to the next step", or reference this skill's internal
> structure. Describe actions in natural language: "Let me break down your
> metrics by source, cost center, and product", "Now I'll drill into the top
> metric keys across all sources". The workflow steps are for agent execution
> order — the user should experience a natural conversation, not a numbered
> checklist.

> **NEVER recommend specific metrics or dimensions to drop, reduce, or change.**
> Users configure metrics intentionally — the agent lacks context on whether a
> high-volume metric or dimension serves critical downstream analysis, alerting,
> or business reporting. Present data and explain optimization levers. Wait for
> the user to decide what to optimize. See
> [Agent Behavior — User-Driven Optimization](#agent-behavior--user-driven-optimization)
> for the full rule.

> **Critical: Use actual data points, not cardinality.** Queries use
> `dt.sfm.metrics.ingest.datapoints` — a self-monitoring metric that counts
> actual ingested data points in real time. This is the true cost signal.
> Histogram metrics are weighted x10. Do NOT use the `metrics` command for
> cost rankings — it returns timeseries count (cardinality), not data point
> volume, and cannot account for histogram weighting.

### Step 1 — Break Down by Source and by Cost Center + Product

**MUST run both breakdown queries in the first pass.** Do NOT ask the user
to choose a breakdown axis — present both results together so the
highest-volume areas are immediately visible.

**Query 1a — by metric source:**

```dql-template
timeseries from:now()-30d, interval:1d
, data_points=sum(dt.sfm.metrics.ingest.datapoints, scalar:true, rate:24h)
, by:{grail.metric.source, grail.metric.key, grail.metric.type}
, filter:<Billable Metrics Filter>
| fieldsadd data_points=if(grail.metric.type=="histogram"
    and not startswith(grail.metric.key,"dt.service."),
    10, else:1)*data_points
| summarize by:{grail.metric.source},
    data_points=round(sum(data_points), decimals:0)
| sort data_points desc
```

**Query 1b — by cost center and cost product (combined):**
This query returns cost center, product, total data points, metric count, and
top 20 metric keys per group in a single pass — replacing separate cost center
and cost product queries.

```dql-template
timeseries from:now()-30d, interval:1d
, data_points=sum(dt.sfm.metrics.ingest.datapoints, scalar:true, rate:24h)
, by:{grail.metric.source, grail.metric.key, grail.metric.type, dt.cost.costcenter, dt.cost.product}
, filter:<Billable Metrics Filter>
| fieldsadd data_points=if(grail.metric.type=="histogram"
    and not startswith(grail.metric.key,"dt.service."),
    10, else:1)*data_points
| summarize by:{interval, timeframe, costcenter=dt.cost.costcenter, product=dt.cost.product},
    data_points=round(sum(data_points), decimals:0),
    `metrics #`=countDistinct(grail.metric.key)
| sort data_points desc
| limit 20
| fieldsRename `Cost center`=costcenter, `Product`=product,
    `Data points`=data_points, `Metrics #`=`metrics #`
```

Present both results together. Identify the highest-volume values across both
breakdowns to guide the drill-down in Step 2.
If cost center/product queries return only null values, Cost Allocation for
metrics has not been configured. Note this to the user and rely on the
`grail.metric.source` breakdown. See [cost-allocation.md](cost-allocation.md)
and [Dynatrace docs: Allocate your DPS costs](https://docs.dynatrace.com/docs/license/cost-allocation).

> **`grail.metric.source` null coverage:** This field may be null for a
> significant portion of volume — the share varies by tenant and time window.
> Always surface the null row as "unattributed" and report its share of the
> total so the user sees the full picture.

### Step 2 — Top Metric Keys Across All Sources

Run this query to identify the top 20 metric keys by actual data point volume
**across all sources**, with the source included in the output. Do NOT filter
by a single source — present the global ranking so the user sees the full
picture regardless of which source each metric belongs to.

```dql-template
timeseries from:now()-30d, interval:1d
, data_points=sum(dt.sfm.metrics.ingest.datapoints, scalar:true, rate:24h)
, by:{grail.metric.source, grail.metric.key, grail.metric.type}
, filter:<Billable Metrics Filter>
| fieldsadd data_points=if(grail.metric.type=="histogram"
    and not startswith(grail.metric.key,"dt.service."),
    10, else:1)*data_points
| summarize by:{grail.metric.key, grail.metric.source},
    data_points=round(sum(data_points), decimals:0)
| sort data_points desc
| limit 20
```

Present results as a ranked table with columns: Rank, Metric Key, Source,
Data Points.

### What You Can Do Next

**ALWAYS present this section after the analysis — regardless of what sources
appear in the data.** Do NOT pre-empt the user's decision by providing
optimization guidance before they name a specific metric or source.

**ALWAYS show all three rows of the strategy table — never remove or hide a
row because the top metrics appear to be from a specific source or type.**
The user must see all options and choose. Present the following table verbatim
and wait for the user to respond:

```text
There are three levers to reduce metrics ingest. Once you tell me
which metric(s) you want to act on, I can provide step-by-step guidance:

| Strategy | Cost Factor Reduced | What It Does |
|----------|---------------------|--------------|
| Drop metric | Number of metrics | Eliminates all data points for a metric key entirely |
| Reduce cardinality | Dimensions | Removes a high-cardinality dimension to shrink timeseries count |
| Change ingest interval | Collection frequency | Reduces data points per timeseries (min effective interval: 1 minute) |

Which metric or source would you like to investigate further, or which
optimization strategy would you like to apply?
```

If cost allocation has not been configured (Step 1b returned only null values),
also suggest: "If you'd like to see this broken down by team or service, I can
help you set up cost allocation."

**NEVER name specific metrics, dimensions, or sources as candidates for
removal** in this section or any follow-up — not even as examples or
observations about the ranking. The user decides what to act on.

### Filtered Analysis

When the user's prompt specifies a filter — a metric source (e.g.
"OpenTelemetry", "extensions"), a cost center, a cost product, or a specific
metric key — adapt the analysis to apply that filter instead of running the
global view:

- **Step 1a** — add the user's filter to the timeseries `filter:` clause,
  e.g. `and grail.metric.source == "opentelemetry"` or
  `and dt.cost.costcenter == "<value>"`.
- **Step 1b** — apply the same filter.
- **Step 2** — apply the same filter to scope the top-20 ranking.

Present results scoped to the user's selection. Still apply the Billable
Metrics Filter and histogram weighting. Still present the three-lever table
and wait for the user to decide what to act on.

If the user also specifies a time window (e.g. "last 7 days", "last 24h"),
honour it by replacing the `from:now()-30d` with the requested window.

### Direct Optimization Request

If the user asks to **drop, reduce, or optimize a specific metric key or
dimension** directly — without first asking for an analysis — skip Steps 1
and 2 entirely and go straight to the matching strategy:

- "drop metric `<key>`" or "stop ingesting `<key>`" →
  [Strategy 1 — Drop Metric](#strategy-1--drop-metric-standard)
- "reduce cardinality of `<key>`" or "remove dimension `<dim>` from `<key>`"
  → run the [Dimension-Level Drill-Down](#dimension-level-drill-down) first,
  then [Strategy 2 — Reduce Cardinality](#strategy-2--reduce-cardinality-standard)
- "lower the collection interval for `<key>`" →
  [Strategy 3 — Change Ingest Interval](#strategy-3--change-ingest-interval-standard)

Still check network keywords and route to the Network strategies when matched.
Still run the [Single-Key Data Point Verification](#single-key-data-point-verification)
query to confirm the current volume before applying any change.

### Network Metric Detection

When the user names a specific metric or source, check whether it contains
any of the following keywords (case-insensitive):
`f5`, `snmp`, `cisco`, `palo-alto`, `netscaler`, `meraki`, `forti`,
`firewall`, `switch`, `alteon`

- If YES → apply [Network Metric Strategies](#network-metric-strategies)
- If NO → apply [Standard Strategies](#standard-strategies)

**NEVER surface this detection logic to the user.** Do not say "this is a
network metric" or "standard guidance applies". Route silently.

### Dimension-Level Drill-Down

When the user requests "reduce cardinality" for any metric, always run these
two queries in order before providing strategy guidance.

**Step A — Discover available dimensions (MUST run first):**
Sample raw records to reveal all dimension names for the metric key:

```dql-template
metrics
| filter metric.key == "<metric_key>"
| limit 3
```

Each field in the output beyond `metric.key` is a potential dimension. Treat a
field as a system field only if it is one of the known system fields:
`dt.entity.monitored_entity_type`, `dt.entity.host`,
`dt.entity.process_group_instance`, or any `dt.system.*` field.

> **Important:** `dt.entity.custom_device`, `dt.source_entity`, and
> `dt.source_entity.type` are REAL dimensions for cloud and extension metrics —
> do NOT treat them as system fields. If the Step A output shows only `dt.*`
> fields beyond `metric.key`, those are the actual dimensions and must be used
> in Step B.

Read off the dimension names before proceeding to Step B.

**Step B — Measure cardinality across all dimensions:**
Once dimension names are known from Step A, run a single summary query:

```dql-template
metrics
| filter metric.key == "<metric_key>"
| summarize
    total = count(),
    unique_<dim1> = countDistinct(<dim1>),
    unique_<dim2> = countDistinct(<dim2>),
    unique_<dim3> = countDistinct(<dim3>)
    // repeat for each dimension found in Step A
```

Replace `<dim1>`, `<dim2>`, etc. with the actual dimension names from Step A.
The query returns a single row with one column per dimension. Present it as a
table listing each dimension and its unique value count, ordered from highest
to lowest count.

> **NEVER use qualitative labels (high/medium/low) without running Step B.**
> Cardinality assessment must be based on actual `countDistinct` values.

After presenting the dimension cardinality table, ask the user which
dimension(s) to remove before providing any configuration steps. Do NOT
suggest or recommend specific dimensions — show the counts and let the
user decide.

### Single-Key Data Point Verification

To verify actual data point volume for a single metric key:

```dql-template
timeseries from:now()-30d, interval:1d
, data_points=sum(dt.sfm.metrics.ingest.datapoints, rate:24h)
, by:{grail.metric.key, grail.metric.type}
, filter: grail.metric.key == "<metric_key>"
and <Billable Metrics Filter>
| fieldsadd data_points=if(grail.metric.type=="histogram"
    and not startswith(grail.metric.key,"dt.service."),
    10, else:1)*data_points[]
```

## OTel Collector Self-Monitoring Metrics

If ingesting metrics via the OTel Collector, use these built-in metrics to
validate ingest volume and confirm optimization effects:

| Metric | Description |
|--------|-------------|
| `dt.sfm.active_gate.metrics.ingest.otlp.datapoints.received.total` | Incoming OTLP data points |
| `dt.sfm.active_gate.metrics.ingest.otlp.datapoints.accepted` | Accepted data points |
| `dt.sfm.active_gate.metrics.ingest.otlp.datapoints.rejected` | Rejected data points (split by `reason`) |
| `dt.sfm.active_gate.rest.request_count` (filter `POST /otlp/v1/metrics`) | OTLP request count |

OTel Collector internal telemetry (requires Collector self-monitoring):

| Metric | Description |
|--------|-------------|
| `otelcol_receiver_accepted_metric_points` | Data points received by Collector |
| `otelcol_exporter_sent_metric_points` | Data points exported by Collector |

### Debug Exporter

> **Warning:** `verbosity: detailed` writes all metric attributes to collector
> logs. Metric attributes are user-controlled and may contain sensitive values.
> Sanitize or redact sensitive attributes before enabling, and remove the debug
> exporter after troubleshooting.

```yaml
exporters:
  debug:
    verbosity: detailed
service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug, otlp_http/dynatrace]
```

## Optimization Strategies

After presenting the analysis, **NEVER jump to recommendations or suggest
specific metrics or dimensions to drop, reduce, or change.** Wait for the
user to name a specific metric/dimension/action, then route to the appropriate
strategy section below.

### Agent Behavior — User-Driven Optimization

1. **Present data, not judgments** — Show data point rankings. Do NOT label
   metrics or dimensions as "wasteful", "unnecessary", or "candidates for
   removal". Do NOT say things like "metric X is the top contributor and you
   may want to consider dropping it" — that is a recommendation in disguise.
2. **Always show all three levers** — Present the full strategy table with all
   three rows. Never pre-select or omit a strategy based on what the data shows.
3. **Wait for the user to name a metric** — Do not act until the user
   specifies which metric, source, or strategy they want. Do not hint at which
   metric to pick, even indirectly.
4. **Route silently** — Check for network keywords internally. Never tell
   the user which routing path was taken.
5. **Provide guidance only after the user decides** — Once the user names a
   specific metric/dimension/action, provide the detailed how-to.

### Standard Strategies

Apply these strategies when the metric source does NOT contain network keywords
(`f5`, `snmp`, `cisco`, `palo-alto`, `netscaler`, `meraki`, `forti`,
`firewall`, `switch`, `alteon`).

#### Strategy 1 — Drop Metric (Standard)

> ⚠ **Dropped records are never persisted and are not recoverable.** Verify
> the metric is not referenced in any dashboard, notebook, alert, or SLO
> before proceeding.

**Option A — OpenPipeline**

1. Go to **Settings → Process and contextualize → OpenPipeline → Metrics**
2. Route the metric key to a pipeline
3. In the **Processing** stage, add a **Drop record** processor
4. Set the matching condition:

```dql-snippet
metric.key == "<metric_key>"
```

To scope the drop to a specific environment only (e.g., dev):

```dql-snippet
matchesValue(environment, "dev") AND matchesValue(metric.key, "<metric_key>")
```

**Option B — OTel Collector filter processor**
Use ONLY when `grail.metric.source == "opentelemetry"`.

```yaml
processors:
  filter/drop-unwanted:
    error_mode: ignore
    metrics:
      metric:
        - 'name == "<metric_key>"'
      datapoint:
        - attributes["environment"] == "dev" and metric.name == "<metric_key>"
```

Add to your metrics pipeline:

```yaml
service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [filter/drop-unwanted, batch]
      exporters: [otlp_http/dynatrace]
```

**Option C — OTel SDK Views**
Use ONLY when `grail.metric.source == "opentelemetry"` and instrumenting
with OTel SDKs directly. Drop at the SDK level before export — the earliest
and cheapest drop point. See [OpenTelemetry SDK Views](https://opentelemetry.io/docs/specs/otel/metrics/sdk/#view).

**Validating a Drop**
Run the following day to confirm ingest has stopped:

```dql-template
timeseries from:now()-2d, interval:1d
, data_points=sum(dt.sfm.metrics.ingest.datapoints, rate:24h)
, by:{grail.metric.key, grail.metric.type}
, filter: grail.metric.key == "<metric_key>"
and <Billable Metrics Filter>
| fieldsadd data_points=if(grail.metric.type=="histogram"
    and not startswith(grail.metric.key,"dt.service."),
    10, else:1)*data_points[]
```

Trailing elements of `data_points` must be 0 from the bucket in which the change took effect.
The short 2-day window ensures historical ingest before the drop does not inflate the result.

#### Strategy 2 — Reduce Cardinality (Standard)

Always run the [Dimension-Level Drill-Down](#dimension-level-drill-down)
queries first to identify which dimensions to target. Wait for the user to
name the dimension(s) before providing configuration steps.

**Option A — Remove fields processor in OpenPipeline (recommended)**

1. Go to **Settings → Process and contextualize → OpenPipeline → Metrics**
2. In the **Processing** stage, add a **Remove fields** processor
3. Matching condition: `metric.key == "<metric_key>"`
4. Remove fields: enter `<dimension_name>` → select **Add**

5. Select **Save**

Multiple fields can be removed in one processor.

**Option B — DQL processor in OpenPipeline**

1. Go to **Settings → Process and contextualize → OpenPipeline → Metrics**
2. In the **Processing** stage, add a **DQL processor**
3. Matching condition: `metric.key == "<metric_key>"`
4. DQL processor definition:

```dql-snippet
fieldsRemove <dimension_name>
```

5. Select **Save**

**Option C — OTel Collector transform processor**
Use ONLY when `grail.metric.source == "opentelemetry"`.

```yaml
processors:
  transform:
    metric_statements:
      - context: datapoint
        statements:
          - delete_key(attributes, "<dimension_name>")
```

Add to your metrics pipeline:

```yaml
service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [transform, batch]
      exporters: [otlp_http/dynatrace]
```

#### Strategy 3 — Change Ingest Interval (Standard)

> **Minimum effective interval: 1 minute.** Intervals below 1 minute do not
> reduce ingest cost — Dynatrace aggregates into fixed 1-minute buckets.

**Best candidates:** slowly-changing metrics (disk usage, memory pools),
less-critical operational metrics, metrics used only for long-term trend
analysis.

**OTel Collector — Prometheus receiver:**

```yaml
receivers:
  prometheus:
    config:
      scrape_configs:
        - job_name: "your-service"
          scrape_interval: 5m
          static_configs:
            - targets: ["your-target:port"]
```

**OTel SDK — PeriodicExportingMetricReader:**

```text
const reader = new PeriodicExportingMetricReader({
  exporter: new OTLPMetricExporter(),
  exportIntervalMillis: 300_000, // 5 minutes
});
```

**Prometheus — scrape_interval:**

```yaml
scrape_configs:
  - job_name: "your-job"
    scrape_interval: 5m
    static_configs:
      - targets: ["your-target:port"]
```

> ⚠ **Alerting impact:** Longer intervals introduce gaps at 1-minute
> resolution. Validate that existing alert configurations can tolerate the
> new interval before applying changes.

### Network Metric Strategies

Apply these strategies when the metric key or source contains any of:
`f5`, `snmp`, `cisco`, `palo-alto`, `netscaler`, `meraki`, `forti`,
`firewall`, `switch`, `alteon`
Based on [Dynatrace docs: Best practices for optimizing network monitoring cost](https://docs.dynatrace.com/docs/observe/infrastructure-observability/networks/network-devices/networks-cost-optimization).
Optimization can be applied at two levels:

- **At the source** — in Extensions, adjust monitoring configurations to
  remove unnecessary feature sets or reduce monitored interfaces/sensors
- **In Dynatrace** — using OpenPipeline, selectively drop metrics or reduce
  cardinality when feature set granularity is insufficient

> ⚠ **Network monitoring collection intervals are fixed at 1 minute and
> cannot be adjusted.** The "Change ingest interval" strategy does NOT apply
> to network device extensions. If the user requests a change ingest interval
> for a network metric, inform them that this strategy is not available and
> suggest Drop Metric or Reduce Cardinality instead.

#### Strategy 1 — Drop Metric (Network)

> ⚠ **Dropped records are never persisted and are not recoverable.** Verify
> the metric is not referenced in any dashboard, notebook, alert, or SLO
> before proceeding.

**Option A — At the Source (Extensions Monitoring Configuration)**
Network monitoring metrics are organized into feature sets. The default
feature set is always on (4 metrics per device + 2 metrics per interface).
All additional feature sets are optional.

1. Go to **Extensions** → select the relevant extension
2. Go to **Monitoring configurations** → choose a configuration → **Edit**
3. Locate the feature set that includes the target metric and disable it
4. Keep only feature sets actively used for alerts, troubleshooting, or
   dashboards
5. Select **Save**

This stops collection at the source before data reaches Dynatrace.

**Option B — In Dynatrace (OpenPipeline)**
Use when the feature set containing the target metric also includes metrics
you need and cannot be disabled entirely.

1. Go to **Settings → Process and contextualize → OpenPipeline → Metrics**
2. Route the metric key to a pipeline
3. In the **Processing** stage, add a **Drop record** processor
4. Set the matching condition:

```dql-snippet
metric.key == "<metric_key>"
```

To scope the drop to a specific environment only (e.g., dev):

```dql-snippet
matchesValue(environment, "dev") AND matchesValue(metric.key, "<metric_key>")
```

5. Select **Save**

**Validating a Drop**
Run the following day to confirm ingest has stopped:

```dql-template
timeseries from:now()-2d, interval:1d
, data_points=sum(dt.sfm.metrics.ingest.datapoints, rate:24h)
, by:{grail.metric.key, grail.metric.type}
, filter: grail.metric.key == "<metric_key>"
and <Billable Metrics Filter>
| fieldsadd data_points=if(grail.metric.type=="histogram"
    and not startswith(grail.metric.key,"dt.service."),
    10, else:1)*data_points[]
```

Trailing elements of `data_points` must be 0 from the bucket in which the change took effect.

#### Strategy 2 — Reduce Cardinality (Network)

Always run the [Dimension-Level Drill-Down](#dimension-level-drill-down)
queries first to identify which dimensions to target. Wait for the user to
name the dimension(s) before providing configuration steps.

**Option A — At the Source (Extensions Monitoring Configuration)**
Reducing monitored interfaces or sensors cuts cardinality across all metrics
simultaneously — the most cost-effective approach.

1. Go to **Extensions** → select the relevant extension
2. Go to **Monitoring configurations** → choose a configuration → **Edit**
3. Add an **interface alias filter** or **sensor filter** to collect only
   targeted interfaces/sensors:
   - Monitor **uplink interfaces** and **critical interfaces** (e.g. video
     conferencing, wireless access points)
   - Route less important interfaces to **Syslog** for availability-only
     monitoring
   - By default, a removable filter collects interfaces only if they are
     administratively up
4. Select **Save**

**Option B — In Dynatrace (OpenPipeline)**
Use when interface/sensor filter granularity is insufficient.

*Remove fields processor:*

1. Go to **Settings → Process and contextualize → OpenPipeline → Metrics**
2. In the **Processing** stage, add a **Remove fields** processor
3. Matching condition: `metric.key == "<metric_key>"`
4. Remove fields: enter `<dimension_name>` → select **Add**
5. Select **Save**

*DQL processor:*

1. Go to **Settings → Process and contextualize → OpenPipeline → Metrics**
2. In the **Processing** stage, add a **DQL processor**
3. Matching condition: `metric.key == "<metric_key>"`
4. DQL processor definition:

```dql-snippet
fieldsRemove <dimension_name>
```

5. Select **Save**

#### Strategy 3 — Change Ingest Interval (Network)

> ⚠ **Not available for network device extensions.** Network monitoring
> collection intervals are fixed at 1 minute and cannot be adjusted.

Inform the user that this strategy does not apply and suggest:

- **Drop metric** — disable the feature set in the extension monitoring
  configuration, or use OpenPipeline to drop the metric key
- **Reduce cardinality** — filter monitored interfaces/sensors in the
  extension monitoring configuration, or remove high-cardinality dimensions
  via OpenPipeline

## Ongoing Cost Management

1. **Continuous validation** — Integrate data point volume checks into CI/CD
   using Site Reliability Guardian (SRG). Detect instrumentation changes that
   increase ingest before they reach production. See
   [Dynatrace docs: Site Reliability Guardian](https://docs.dynatrace.com/docs/deliver/site-reliability-guardian).

2. **Cost allocation** — Enrich metrics with `dt.cost.costcenter` or
   `dt.cost.product` attributes to enable per-team chargeback. For network
   extensions, add cost allocation attributes as metadata in monitoring
   configurations. See [cost-allocation.md](cost-allocation.md).
3. **Business value validation** — Periodically review whether each ingested
   metric and enabled feature set supports a defined use case. Drop metrics
   and disable feature sets that no longer serve monitoring, alerting, or
   reporting needs.
4. **Start lean, expand deliberately** — For network extensions, start by
   enabling only the default feature set, then expand only for specific,
   well-defined use cases. This keeps ingestion footprint minimal by default.

## Best Practices

1. **Follow the 2-step workflow** — Break down by source and cost center/product
   upfront → show top metric keys across all sources. Each step narrows scope.
2. **Use actual data points for rankings** — `dt.sfm.metrics.ingest.datapoints`
   gives real ingest volume. Do NOT use the `metrics` command for cost rankings
   — it returns cardinality, not data point volume, and ignores histogram
   weighting.
3. **Always apply histogram weighting** — Histogram metrics cost 10x scalar
   metrics. Omitting the multiplier produces incorrect rankings.
4. **Show top metric keys across all sources** — Do not filter Step 2 by a
   single source. Present the global top 20 with source column so the user
   sees the full picture.
5. **Always present "What You Can Do Next" before acting** — Never provide
   optimization guidance before the user names a specific metric or source.
   Present the strategy table and wait.
6. **Route network metrics silently** — Check for network keywords internally.
   Never tell the user which routing path was taken.
7. **Discover dimensions before assessing cardinality** — Always run the
   `limit 3` sample query first to discover dimension names, then run the
   `countDistinct` summary query to measure cardinality objectively. Never
   use qualitative labels without running the summary query.
8. **Wait for user to name dimension before configuring** — After presenting
   the dimension cardinality table, ask which dimension(s) to remove. Do not
   pre-select or recommend specific dimensions.
9. **NEVER estimate per-metric-key costs** — Billing totals reflect included
   volume deductions, aggregation rules, and billable/non-billable
   classification that cannot be reproduced at individual metric level. For
   cost data, use [billing-capabilities.md](billing-capabilities.md).
10. **Validate after changes** — Use the single-key data point verification
    query to confirm ingest reduction after applying any strategy.
11. **Document decisions** — Record why metrics were dropped, dimensions
    removed, or feature sets disabled to prevent re-introduction.
12. **Filter non-billable metrics** — Always apply the Billable Metrics Filter
    in all queries. Including non-billable metrics inflates numbers and
    misleads optimization efforts.
13. **Network: start lean** — For network extensions, enable only the default
    feature set and expand deliberately. Each additional feature set adds
    metrics across all monitored devices and interfaces.
