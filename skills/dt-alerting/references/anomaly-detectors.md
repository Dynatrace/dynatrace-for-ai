# Anomaly Detectors

Configure anomaly detectors to continuously evaluate metrics and fire Davis events
when conditions are breached.

## Contents

- [Alert Source Categories](#alert-source-categories)
- [DQL-Based Detector Variants](#dql-based-detector-variants)
- [Detector Models](#detector-models)
- [Built-in Davis AI Detection](#built-in-davis-ai-detection)
- [Davis Anomaly Detectors (Metric Key)](#davis-anomaly-detectors-metric-key)
- [Davis Anomaly Detectors (DQL-based)](#davis-anomaly-detectors-dql-based)
  - [Runtime JSON structure](#runtime-json-structure)
  - [Input key reference](#input-key-reference)
  - [Example: Static threshold](#example-static-threshold)
  - [Example: Adaptive baseline](#example-adaptive-baseline)
  - [Example: Seasonal baseline](#example-seasonal-baseline)
  - [eventTemplate.properties reference](#eventtemplateproperties-reference)
  - [DQL query notes](#dql-query-notes)
- [Davis Anomaly Detectors (Record-based)](#davis-anomaly-detectors-record-based)
  - [How record-based detection works](#how-record-based-detection-works)
  - [alertIdentityFields — per-row deduplication](#alertidentityfields--per-row-deduplication)
  - [Example: Scalar alert — log error count above threshold](#example-scalar-alert--log-error-count-above-threshold)
  - [Example: Per-entity alert — disk free space per host](#example-per-entity-alert--disk-free-space-per-host)
  - [Example: Timeseries flattened to scalar per entity](#example-timeseries-flattened-to-scalar-per-entity)
- [OneAgent Edge-Side Anomaly Detectors](#oneagent-edge-side-anomaly-detectors)
  - [How Edge-Side Detection Works](#how-edge-side-detection-works)
  - [When to Prefer Edge Detection](#when-to-prefer-edge-detection)
  - [Disk Edge Alerts (`builtin:infrastructure.disk.edge.anomaly-detectors`)](#disk-edge-alerts-builtininfrastructurediskedgeanomaly-detectors)
  - [OS Service Monitoring (`os-services-monitoring`)](#os-service-monitoring-os-services-monitoring)
  - [Process Availability (`process-availability`)](#process-availability-process-availability)
- [Choosing the Right Detector and Model](#choosing-the-right-detector-and-model)
- [Configuration Best Practices](#configuration-best-practices)

---

## Alert Source Categories

Dynatrace supports five fundamentally different categories of anomaly detectors,
distinguished by **where detection runs** and **how the alert event is generated**.
Understanding the category determines which tool to configure and what latency and
data access trade-offs apply.

| # | Category | Detection runs on | Trigger mechanism |
|---|----------|-------------------|-------------------|
| 1 | **DQL-based detectors** | Grail (server-side, on a schedule) | Reads stored telemetry via DQL `timeseries` query and evaluates a model |
| 2 | **Edge alerts** | OneAgent (on the monitored host or process) | Agent detects a violation locally and pushes the event directly to Dynatrace |
| 3 | **Pipeline alerts** | OpenPipeline ingest path | DQL filter matcher evaluates raw data in-stream as it traverses the pipeline, before indexing |
| 4 | **Synthetic alerts** | Synthetic checker node (worldwide locations) | Checker node detects an availability or latency violation and pushes the event directly |
| 5 | **Externally ingested events** | External system (customer-owned) | Customer pushes alert events via the Dynatrace Events API, a Workflow, OpenPipeline ingest APIs, or OneAgent local event ingest |

### Category characteristics

**1. DQL-based detectors**
Run entirely on the server side against data already stored in Grail. Evaluated
on a configurable schedule (typically every minute). Covers the widest range of
metrics — anything reachable via DQL, including calculated metrics, log-derived
metrics, span metrics, and business events. Includes:
- Built-in Davis AI health alerts for services, hosts, databases, Kubernetes
- User-defined Davis anomaly detectors (`builtin:davis.anomaly-detectors`) — supports metric-key and DQL-based query definitions

**2. Edge alerts**
Detected locally by the Dynatrace OneAgent running on the monitored
host or process. The agent observes conditions (disk space, process crashes,
network errors) that are known before data is ever sent to Grail, and pushes
a Davis event directly. Examples: disk full alert, process crash alert, host
availability alert. Near-real-time latency because no Grail read is required.

**3. Pipeline alerts**
Evaluated by DQL filter matchers embedded directly in the OpenPipeline ingest
path. Raw data (typically logs or events) is checked against the matcher rule
as it flows through the pipeline, before it is indexed in Grail. This enables
zero-latency alerting on log patterns — a matching log line raises an alert the
moment it arrives, without waiting for a scheduled DQL query to run.

**4. Synthetic alerts**
A specialized variant of edge alerting where the detection runs on Dynatrace
synthetic checker nodes distributed across worldwide locations. Each node
executes availability and performance checks (HTTP monitors, browser click paths,
API tests) and raises a Davis event directly when a check fails or a latency
threshold is exceeded. Like edge alerts, synthetic alerts bypass the Grail
read path for near-real-time detection.

**5. Externally ingested alert events**
The customer or an external tool owns the alert logic. Dynatrace acts as the
**alert ingestion, storage, and correlation layer** rather than the detector.
Alert events are pushed into Dynatrace using:
- **Events API v2** (`POST /api/v2/events/ingest`) — direct REST call
- **Workflow action** — a workflow step that creates a Davis event
- **OpenPipeline ingest APIs** — event routed through the pipeline with alert classification
- **OneAgent local event ingest** — agent SDK used by custom application code

These events receive the same Davis AI problem grouping and workflow notification
treatment as internally generated alerts. Common use cases: third-party monitoring
tools forwarding alerts, application-level business KPI alerts, CI/CD deployment
events that should trigger alerting.

### Trade-offs by category

| Dimension | DQL-based | Edge | Pipeline | Synthetic | External |
|-----------|-----------|------|----------|-----------|---------|
| Detection latency | Minutes (scheduled) | Seconds | Near-zero (in-stream) | Seconds | Depends on caller |
| Data access | Any stored metric/event | Local host/process only | Raw in-flight data | Synthetic check result | Defined by caller |
| Alert logic owner | Dynatrace | Dynatrace (OneAgent) | Dynatrace (pipeline rule) | Dynatrace (synthetic node) | Customer / external tool |
| Configuration location | Settings v2 / UI | Settings v2 / UI | OpenPipeline configuration | Synthetic monitor config | Caller-side |
| Requires Grail data | Yes | No | No | No | No |

---

## DQL-Based Detector Variants

Within the DQL-based category, Dynatrace offers three detector variants that
differ in how the metric is specified and which models are available:

| Variant | Settings schema | Metric source | Model options |
|---------|----------------|---------------|---------------|
| **Built-in Davis AI** | Auto-enabled, tune sensitivity only | Predefined per entity type | Adaptive (auto-tuned) |
| **Davis anomaly detectors (metric key)** | `builtin:davis.anomaly-detectors` | Any metric key in Dynatrace | Static, Adaptive baseline |
| **Davis anomaly detectors (DQL-based, timeseries)** | `builtin:davis.anomaly-detectors` | Any metric via DQL `timeseries` | Static, Adaptive, Seasonal |
| **Davis anomaly detectors (Record-based)** | `builtin:davis.anomaly-detectors` | Any DQL query result (fetch, summarize, data, timeseries+transform) | Condition encoded in DQL filter — each returned row = one alert |

---

## Detector Models

### Static Threshold

Fires when a metric value exceeds (or falls below) a fixed value you define, for
a minimum sustained duration.

**Use when:**
- You have a hard SLO or operational boundary (e.g., error rate > 5%, disk > 90%)
- The acceptable range does not change over time
- You want predictable, auditable alert conditions

**Key parameters:**
- `threshold` — the fixed boundary value
- `violationType` — ABOVE or BELOW
- `violationDuration` — how long the threshold must be breached before firing

**Pitfall:** Setting thresholds too tight on volatile metrics causes alert storms.
Use adaptive baseline if the metric fluctuates naturally.

---

### Adaptive Baseline

Learns normal behavior from recent historical data and fires when the metric
deviates significantly from that learned baseline. The threshold is dynamic —
it adjusts as behavior shifts.

**Use when:**
- The metric has no natural fixed limit but has a clear normal range
- Normal values differ between environments or time periods
- You want to detect anomalies without knowing the exact threshold upfront

**Key parameters:**
- `sensitivity` — LOW / MEDIUM / HIGH: controls how many standard deviations from
  the baseline count as a violation (HIGH = fires sooner, more sensitive)
- `referencePeriod` — how much history to use for baseline learning (typically 7–30 days)

**Pitfall:** Running adaptive baseline on a metric that is genuinely trending
upward will produce continuous false positives as the metric leaves its baseline.
Use novelty detection (`dt-obs-predictive-analytics`) to detect trends instead.

---

### Seasonal Baseline

Like adaptive baseline but explicitly models time-of-day and day-of-week patterns
before deciding what is anomalous. Monday 9am traffic is compared to previous
Monday 9am values, not to the overall average.

**Use when:**
- The metric follows clear business-hour or weekly patterns (request rate, active
  users, transaction volume)
- Adaptive baseline fires too often during expected peaks and valleys
- You need to distinguish "high traffic Monday morning" from a genuine anomaly

**Key parameters:**
- Same sensitivity and reference period as adaptive
- Requires sufficient history (at least 2 full weekly cycles) before the seasonal
  model stabilizes

**Pitfall:** Seasonal baseline needs at least 2 weeks of stable history to be
reliable. Newly onboarded services or environments will have a learning period
with higher false-positive rates.

---

## Built-in Davis AI Detection

Dynatrace automatically detects anomalies for every monitored entity type
(services, hosts, databases, Kubernetes workloads, synthetic monitors, etc.)
without any configuration. Detection uses adaptive models tuned per entity.

### What it covers

| Entity type | Detected conditions |
|------------|-------------------|
| Services | Response time degradation, error rate increase, throughput drop |
| Hosts | CPU saturation, memory pressure, disk saturation |
| Databases | Query time slowdown, connection issues |
| Kubernetes | Pod evictions, OOM kills, resource quota breaches |
| Synthetic monitors | Availability failures, performance threshold breaches |

### Tuning built-in detection

Navigate to **Settings → Anomaly detection → [Entity type]** to:
- Enable / disable specific detection categories (availability, performance, errors)
- Adjust detection sensitivity (LOW / MEDIUM / HIGH)
- Override sensitivity per individual entity

Built-in detection cannot be replaced with custom queries — use custom metric
events or Davis anomaly detectors for metrics beyond the predefined catalog.

---

## Davis Anomaly Detectors (Metric Key)

Settings schema: `builtin:davis.anomaly-detectors`

**Note:** The field names documented in this section (`queryDefinition`,
`modelProperties`, `eventTemplate.severity`) reflect an older API representation.
The current runtime format uses the **analyzer-based structure** described in
the [DQL-based section](#davis-anomaly-detectors-dql-based). When creating new
detectors via `dtctl apply` or the Settings v2 API, use the analyzer structure
with `analyzer.name` and `analyzer.input` key-value pairs.

Allows user-defined alert rules on any metric available in Dynatrace using a
metric key selector. Each rule defines a metric key, an entity scope, a model,
and a threshold. Use this variant when you do not need the full flexibility of a
DQL query. The legacy `builtin:anomaly-detection.metric-events` schema served the
same purpose but has been superseded by `builtin:davis.anomaly-detectors` and
does not support DQL-based query definitions.

### Configuration fields

| Field | Description |
|-------|-------------|
| `metricSelector` | Metric key and aggregation (e.g., `builtin:service.errors.total:splitBy():avg`) |
| `entityFilter` | Entity selector scoping which entities to monitor |
| `model.type` | `STATIC` or `BASELINE` |
| `model.threshold` | Fixed value (STATIC only) |
| `model.signalFluctuation` | Sensitivity for BASELINE: `HIGH`, `MEDIUM`, `LOW` |
| `model.violationWindow` | Number of consecutive violated samples before firing |
| `model.dealertingWindow` | Number of consecutive non-violated samples before clearing |
| `eventTemplate.title` | Name of the resulting Davis event |
| `eventTemplate.severity` | `PERFORMANCE`, `RESOURCE`, `AVAILABILITY`, `CUSTOM_ALERT`, `INFO` |

### Example: Static threshold on error rate

```json
{
  "enabled": true,
  "queryDefinition": {
    "type": "METRIC_KEY",
    "metricKey": "builtin:service.errors.total",
    "aggregation": "AVG",
    "entityFilter": {
      "dimensionKey": "dt.entity.service",
      "conditions": [
        { "type": "TAG", "value": "env:production" }
      ]
    }
  },
  "modelProperties": {
    "type": "STATIC_THRESHOLD",
    "threshold": 5.0,
    "violationType": "ABOVE",
    "alertCondition": "ALL_SERIES_IN_VIOLATIONS",
    "violationWindowInMinutes": 5,
    "dealertingWindowInMinutes": 10
  },
  "eventTemplate": {
    "title": "Error rate above 5% in production",
    "severity": "AVAILABILITY"
  }
}
```

---

## Davis Anomaly Detectors (DQL-based)

Settings schema: `builtin:davis.anomaly-detectors`

The most powerful and flexible custom detector type. You write a DQL `timeseries`
query to define exactly which metric to evaluate. Davis evaluates it on a schedule
and applies the chosen model.

### Why use DQL-based detectors

- Any metric reachable via DQL — including calculated metrics, span metrics,
  log-based metrics, and business events
- Flexible entity grouping via `by:{}` dimensions
- All three models available: static, adaptive, seasonal
- DQL lets you pre-aggregate, filter, or transform before anomaly evaluation

### Runtime JSON structure

The actual runtime format for `builtin:davis.anomaly-detectors` uses an
**analyzer-based structure** — not the field paths sometimes shown in older
documentation. The top-level object to `POST` to `PUT /api/v2/settings/objects`
(or apply via `dtctl apply -f`) is:

```json
{
  "schemaId": "builtin:davis.anomaly-detectors",
  "scope": "tenant",
  "value": {
    "title": "...",
    "description": "...",
    "enabled": true,
    "source": "Davis Anomaly Detection",
    "analyzer": {
      "name": "<analyzer-class-name>",
      "input": [
        { "key": "<param>", "value": "<value>" }
      ]
    },
    "eventTemplate": {
      "properties": [
        { "key": "<property>", "value": "<value>" }
      ]
    },
    "executionSettings": {
      "actor": "<user-uuid>"
    }
  }
}
```

The **`analyzer.name`** selects the detection model. The **`analyzer.input`**
array supplies all model parameters as key-value string pairs. The three
supported analyzers and their input signatures are:

| Analyzer class | Model | Key input parameters |
|----------------|-------|----------------------|
| `dt.statistics.ui.anomaly_detection.StaticThresholdAnomalyDetectionAnalyzer` | Static threshold | `query`, `threshold`, `alertCondition` |
| `dt.statistics.ui.anomaly_detection.AutoAdaptiveAnomalyDetectionAnalyzer` | Adaptive baseline | `query.expression`, `numberOfSignalFluctuations`, `alertCondition` |
| `dt.statistics.ui.anomaly_detection.SeasonalBaselineAnomalyDetectionAnalyzer` | Seasonal baseline | `query.expression`, `tolerance`, `alertCondition` |

### Input key reference

**Shared across all three models:**

| Key | Type | Description |
|-----|------|-------------|
| `query` / `query.expression` | string | DQL `timeseries` query. Both keys are accepted; `query.expression` is preferred for new configs |
| `alertCondition` | `ABOVE` \| `BELOW` | Direction of violation — `ABOVE` for detecting increases |
| `alertOnMissingData` | `"true"` \| `"false"` | Fire an alert if the metric stops reporting entirely |
| `violatingSamples` | numeric string | Samples within `slidingWindow` that must violate before the alert fires |
| `slidingWindow` | numeric string | Number of evaluation samples in the rolling window |
| `dealertingSamples` | numeric string | Clean samples required before the alert clears |

**Model-specific:**

| Key | Model | Description |
|-----|-------|-------------|
| `threshold` | Static | Fixed boundary value (in the metric's native unit) |
| `numberOfSignalFluctuations` | Adaptive | Sensitivity: `1` = LOW (fires only on clear deviations), higher = more sensitive |
| `tolerance` | Seasonal | Sensitivity: `1` = very sensitive, `4` = tolerant (default). Analogous to `numberOfSignalFluctuations` |
| `query.filterSegments[0].id` | Adaptive / Seasonal | Optional. Restrict the detector to a saved filter segment by its ID |

### Example: Static threshold

Fires when average CPU load stays above 80% for 3 of 5 consecutive samples:

```json
{
  "schemaId": "builtin:davis.anomaly-detectors",
  "scope": "tenant",
  "value": {
    "title": "CPU load above 80% — production hosts",
    "enabled": true,
    "source": "Davis Anomaly Detection",
    "analyzer": {
      "name": "dt.statistics.ui.anomaly_detection.StaticThresholdAnomalyDetectionAnalyzer",
      "input": [
        { "key": "query",              "value": "timeseries avg(dt.host.cpu.usage), by: {dt.entity.host}" },
        { "key": "threshold",          "value": "80" },
        { "key": "alertCondition",     "value": "ABOVE" },
        { "key": "alertOnMissingData", "value": "false" },
        { "key": "violatingSamples",   "value": "3" },
        { "key": "slidingWindow",      "value": "5" },
        { "key": "dealertingSamples",  "value": "5" }
      ]
    },
    "eventTemplate": {
      "properties": [
        { "key": "dt.source_entity", "value": "{dims:dt.entity.host}" },
        { "key": "event.type",       "value": "RESOURCE_CONTENTION_EVENT" },
        { "key": "event.name",       "value": "CPU load above 80% on {dims:dt.entity.host}" },
        { "key": "dt.alert_group",   "value": "ops-team" }
      ]
    },
    "executionSettings": { "actor": "<user-uuid>" }
  }
}
```

### Example: Adaptive baseline

Fires when service response time rises significantly above its learned normal
behavior (detects gradual degradation without a fixed threshold):

```json
{
  "schemaId": "builtin:davis.anomaly-detectors",
  "scope": "tenant",
  "value": {
    "title": "Abnormal latency increase — JourneyService",
    "enabled": true,
    "source": "Davis Anomaly Detection",
    "analyzer": {
      "name": "dt.statistics.ui.anomaly_detection.AutoAdaptiveAnomalyDetectionAnalyzer",
      "input": [
        { "key": "query.expression",          "value": "timeseries avg_latency = avg(dt.service.request.response_time), by: {dt.smartscape.service} | filter dt.smartscape.service == toSmartscapeId(\"SERVICE-18AA85290DF3D5D2\")" },
        { "key": "numberOfSignalFluctuations", "value": "1" },
        { "key": "alertCondition",             "value": "ABOVE" },
        { "key": "alertOnMissingData",         "value": "false" },
        { "key": "violatingSamples",           "value": "3" },
        { "key": "slidingWindow",              "value": "5" },
        { "key": "dealertingSamples",          "value": "5" }
      ]
    },
    "eventTemplate": {
      "properties": [
        { "key": "dt.source_entity", "value": "{dims:dt.smartscape.service}" },
        { "key": "event.type",       "value": "PERFORMANCE_EVENT" },
        { "key": "event.name",       "value": "Abnormal latency increase on JourneyService" },
        { "key": "event.description","value": "Latency deviated above its adaptive baseline. Detected {violating_samples} violation samples within the evaluation window." },
        { "key": "dt.alert_group",   "value": "my-routing-group" }
      ]
    },
    "executionSettings": { "actor": "<user-uuid>" }
  }
}
```

### Example: Seasonal baseline

Fires when a business metric deviates from its expected time-of-day / day-of-week
pattern. Requires at least 2 weeks of stable history before the model stabilizes:

```json
{
  "schemaId": "builtin:davis.anomaly-detectors",
  "scope": "tenant",
  "value": {
    "title": "Abnormal order rate — business hours pattern",
    "enabled": true,
    "source": "Davis Anomaly Detection",
    "analyzer": {
      "name": "dt.statistics.ui.anomaly_detection.SeasonalBaselineAnomalyDetectionAnalyzer",
      "input": [
        { "key": "query.expression",  "value": "timeseries orders = sum(orders_placed_count), by: {dt.entity.service}" },
        { "key": "tolerance",         "value": "4" },
        { "key": "alertCondition",    "value": "BELOW" },
        { "key": "alertOnMissingData","value": "false" },
        { "key": "violatingSamples",  "value": "3" },
        { "key": "slidingWindow",     "value": "5" },
        { "key": "dealertingSamples", "value": "5" }
      ]
    },
    "eventTemplate": {
      "properties": [
        { "key": "dt.source_entity", "value": "{dims:dt.entity.service}" },
        { "key": "event.type",       "value": "CUSTOM_ALERT" },
        { "key": "event.name",       "value": "Order rate below seasonal baseline" },
        { "key": "dt.alert_group",   "value": "my-routing-group" }
      ]
    },
    "executionSettings": { "actor": "<user-uuid>" }
  }
}
```

### eventTemplate.properties reference

| Key | Required | Description |
|-----|----------|-------------|
| `dt.source_entity` | Recommended | Links the Davis event to a specific entity. Use `{dims:<dimension_key>}` where `<dimension_key>` matches the `by:{}` field in the timeseries query (e.g. `{dims:dt.smartscape.service}`, `{dims:dt.entity.host}`) |
| `event.type` | Required | Determines Davis problem category. Valid values: `AVAILABILITY_EVENT`, `ERROR_EVENT`, `PERFORMANCE_EVENT`, `RESOURCE_CONTENTION_EVENT`, `CUSTOM_ALERT`, `CUSTOM_INFO` |
| `event.name` | Recommended | Title shown on the Davis event and problem. Use template variables like `{dims:dt.entity.host}` for dynamic names |
| `event.description` | Optional | Markdown-formatted detail. Supports template variables: `{violating_samples}`, `{threshold}`, `{alert_condition}`, `{metricname}` |
| `dt.alert_group` | Optional | Routing label carried through to the Davis problem. Used to filter which workflows handle this alert. See `workflow-notifications.md` |

**`event.type` → Davis problem category mapping:**

| `event.type` value | Davis problem category | Use for |
|--------------------|----------------------|---------|
| `AVAILABILITY_EVENT` | AVAILABILITY | Service or host unreachable |
| `ERROR_EVENT` | ERROR | Error rate spikes |
| `PERFORMANCE_EVENT` | SLOWDOWN | Latency degradation, throughput drop |
| `RESOURCE_CONTENTION_EVENT` | RESOURCE | CPU, memory, disk saturation |
| `CUSTOM_ALERT` | CUSTOM | Business KPIs, custom conditions |
| `CUSTOM_INFO` | INFO | Informational — does not open a problem |

### DQL query notes

- **Filter by Smartscape entity ID:** Use `toSmartscapeId("SERVICE-...")` when
  comparing a string literal to a Smartscape dimension — raw string comparison
  produces a warning and may not match correctly.
```dql
timeseries avg_latency = avg(dt.service.request.response_time), by: {dt.smartscape.service}
| filter dt.smartscape.service == toSmartscapeId("SERVICE-03F1F46B45BFA6C4")
```
- **Multiple entities:** Chain `or` conditions with `toSmartscapeId()` per entity.
- **`query` vs `query.expression`:** Both keys are accepted. `query.expression` is
  the newer form and is required when also supplying `query.filterSegments[0].id`
  for filter segment scoping.

Davis evaluates the timeseries on a schedule, applies the chosen model to each
series returned by the `by:{}` dimension independently, and fires a Davis event
for any series that violates the threshold.

---

## Davis Anomaly Detectors (Record-based)

Settings schema: `builtin:davis.anomaly-detectors`
Analyzer class: `dt.statistics.anomaly_detection.RecordAnomalyDetectionAnalyzer`

The record-based detector is a fundamentally different kind of DQL detector.
Where the timeseries-based analyzers continuously evaluate a metric signal
against a model (static, adaptive, or seasonal), the record analyzer evaluates
**any DQL query** on a schedule and treats each row of the result as a
violation that triggers a Davis event.

**The DQL query IS the alert condition.** You write a query whose `filter`
clauses define what constitutes a violation, and you structure the query so
that it returns rows only when the condition is actually breached. When Davis
evaluates the query:
- Zero rows returned → no alert fires
- N rows returned → N alert events fire, one per row

This approach supports alert conditions that are impossible to express as a
timeseries threshold:
- **Existence checks** — fire when a specific record appears (or disappears) in a log, event, or entity list
- **Scalar aggregates** — fire when a summarized count exceeds a threshold (e.g., total error count in the last hour)
- **Entity inventory conditions** — fire for each entity matching a structural criterion (e.g., each host that has more than one disk mount, each service with zero throughput)
- **Cross-signal joins** — combine logs, traces, metrics, and entities in a single `fetch` pipeline

### How record-based detection works

```
Scheduler tick
      │
      ▼
DQL query executes
      │
      ├─ 0 rows returned ──→ no alert, any open alert for this detector closes
      │
      └─ N rows returned ──→ one Davis event fires per row
                              │
                              ▼
                     alertIdentityFields determine deduplication:
                     - no alertIdentityFields: N independent events, no dedup
                     - with alertIdentityFields: each unique field-value
                       combination is one open alert; same combination on
                       the next tick updates the existing problem instead
                       of opening a new one; disappearing row closes the alert
```

### alertIdentityFields — per-row deduplication

`alertIdentityFields` is an optional list of column names from the query
result that together uniquely identify each violating entity. When set:

- Each distinct combination of those field values tracks as one open alert
- A row that appeared in the previous evaluation and appears again is treated
  as "still violating" — Davis updates the existing problem rather than opening
  a second one for the same entity
- A row that appeared previously but no longer appears is treated as "recovered"
  — Davis closes the alert for that combination

**Without `alertIdentityFields`:** every row on every evaluation tick creates
a new independent event. This is appropriate for one-shot notification patterns
but will generate duplicate problems if the condition persists across multiple
evaluations.

**With `alertIdentityFields`:** alerts behave like persistent per-entity state,
opening when a row appears, staying open while it persists, closing when it
disappears. This is the correct pattern for per-entity violation tracking.

Input key format: `alertIdentityFields[0]`, `alertIdentityFields[1]`, … (zero-indexed array)

### Event template field placeholders

In `eventTemplate.properties`, all column names from the query result are
available as `{column_name}` placeholders in `event.name` and `event.description`.
This is different from the timeseries analyzers where only a fixed set of
`{violating_samples}`, `{threshold}`, etc. are available.

```json
{ "key": "event.name",        "value": "High error count on {dt.service.name}: {error_count} errors" }
{ "key": "event.description", "value": "Service {dt.service.name} produced {error_count} errors in the last hour. Error rate: {error_rate_pct}%" }
```

Use `{dims:<column>}` (instead of `{column}`) when referencing an entity ID
column that should resolve to the entity's display name.

To link the Davis event to a Smartscape entity:
- `dt.source_entity`: `{dims:<entity_id_column>}` — preferred; resolves entity ID to entity name
- `dt.smartscape_source.id`: `{<smartscape_id_column>}` — alternative when the result contains a Smartscape ID directly

### Input key reference

| Key | Required | Description |
|-----|----------|-------------|
| `query` / `query.expression` | Yes | Any DQL query. Rows returned = violations. Use `filter` to express the alert condition. |
| `alertIdentityFields[N]` | Recommended | Column name(s) that uniquely identify each violating entity. Enables per-row open/close tracking. Omit only for one-shot single-event patterns. |
| `query.filterSegments[0].id` | Optional | Restrict the detector to a saved filter segment by its ID. |

### Example: Scalar alert — log error count above threshold

Fires a single alert when the total number of ERROR log entries in the last
hour across the entire environment exceeds 100. Returns at most one row, so
one event fires. When the count drops below 100, the query returns no rows
and the alert closes.

```json
{
  "schemaId": "builtin:davis.anomaly-detectors",
  "scope": "tenant",
  "value": {
    "title": "High ERROR log volume — environment-wide",
    "enabled": true,
    "source": "Davis Anomaly Detection",
    "analyzer": {
      "name": "dt.statistics.anomaly_detection.RecordAnomalyDetectionAnalyzer",
      "input": [
        { "key": "query.expression", "value": "fetch logs, from: -1h | filter loglevel == \"ERROR\" | summarize error_count = count() | filter error_count > 100" }
      ]
    },
    "eventTemplate": {
      "properties": [
        { "key": "event.type",       "value": "ERROR_EVENT" },
        { "key": "event.name",       "value": "High ERROR log volume: {error_count} errors in last hour" },
        { "key": "event.description","value": "The environment produced {error_count} ERROR log lines in the last hour, exceeding the threshold of 100." },
        { "key": "dt.alert_group",   "value": "my-routing-group" }
      ]
    },
    "executionSettings": { "actor": "<user-uuid>" }
  }
}
```

### Example: Per-entity alert — high CPU usage per host

Fires one alert per host where the maximum CPU usage has exceeded 80%. Uses
`alertIdentityFields` so that each host tracks as a separate open alert that
closes when CPU usage drops back below the threshold.

```json
{
  "schemaId": "builtin:davis.anomaly-detectors",
  "scope": "tenant",
  "value": {
    "title": "High CPU usage — per host",
    "enabled": true,
    "source": "Davis Anomaly Detection",
    "analyzer": {
      "name": "dt.statistics.anomaly_detection.RecordAnomalyDetectionAnalyzer",
      "input": [
        { "key": "query.expression",   "value": "timeseries cpu=avg(dt.host.cpu.usage), by: { dt.smartscape.host }\n| fieldsAdd max_cpu = arrayMax(cpu)\n| fieldsRemove cpu\n| filter max_cpu > 80" },
        { "key": "alertIdentityFields[0]", "value": "dt.smartscape.host" }
      ]
    },
    "eventTemplate": {
      "properties": [
        { "key": "dt.source_entity", "value": "{dims:dt.smartscape.host}" },
        { "key": "event.type",       "value": "RESOURCE_CONTENTION_EVENT" },
        { "key": "event.name",       "value": "High CPU usage on {dims:dt.smartscape.host}: {max_cpu}%" },
        { "key": "event.description","value": "Host {dims:dt.smartscape.host} CPU usage reached {max_cpu}%, exceeding the 80% threshold." },
        { "key": "dt.alert_group",   "value": "my-routing-group" }
      ]
    },
    "executionSettings": { "actor": "<user-uuid>" }
  }
}
```

### Example: Timeseries flattened to scalar per entity

A `timeseries` query can be used with the record analyzer by collapsing the
array values to scalars with `fieldsAdd ... = arrayAvg(...)` and then
`filter`-ing to the violating rows. This gives per-entity static threshold
alerting without using the `StaticThresholdAnomalyDetectionAnalyzer`, and
allows arbitrary post-processing (joins, renaming, calculated fields) before
the threshold test.

```json
{
  "schemaId": "builtin:davis.anomaly-detectors",
  "scope": "tenant",
  "value": {
    "title": "CPU usage above 80% — per host",
    "enabled": true,
    "source": "Davis Anomaly Detection",
    "analyzer": {
      "name": "dt.statistics.anomaly_detection.RecordAnomalyDetectionAnalyzer",
      "input": [
        { "key": "query.expression",       "value": "timeseries cpu_usage = avg(dt.host.cpu.usage), by: {dt.entity.host}\n| fieldsAdd cpu_usage = arrayAvg(cpu_usage)\n| filter cpu_usage > 80" },
        { "key": "alertIdentityFields[0]", "value": "dt.entity.host" }
      ]
    },
    "eventTemplate": {
      "properties": [
        { "key": "dt.source_entity", "value": "{dims:dt.entity.host}" },
        { "key": "event.type",       "value": "RESOURCE_CONTENTION_EVENT" },
        { "key": "event.name",       "value": "CPU above 80% on {dims:dt.entity.host}" },
        { "key": "event.description","value": "Average CPU usage is {cpu_usage}% on host {dims:dt.entity.host}, exceeding the 80% threshold." },
        { "key": "dt.alert_group",   "value": "my-routing-group" }
      ]
    },
    "executionSettings": { "actor": "<user-uuid>" }
  }
}
```

### When to use record-based vs. timeseries-based detectors

| Condition | Use record-based | Use timeseries-based |
|-----------|-----------------|----------------------|
| Alert on log pattern or log count | ✅ | ❌ not possible |
| Alert on fetch events / entity inventory | ✅ | ❌ not possible |
| Alert on scalar aggregate across entities | ✅ | ❌ timeseries requires `by:{}` |
| Static threshold per entity, need post-processing | ✅ (flatten timeseries) | ⚠ `StaticThreshold` is simpler if no transforms needed |
| Adaptive baseline (learn normal behavior) | ❌ no model, condition must be explicit | ✅ `AutoAdaptive` |
| Seasonal baseline (day-of-week patterns) | ❌ | ✅ `SeasonalBaseline` |
| Per-entity open/close tracking | ✅ with `alertIdentityFields` | ✅ native per-series tracking |

---

## OneAgent Edge-Side Anomaly Detectors

Edge-side detectors run entirely within the Dynatrace OneAgent process on the
monitored host. The agent observes local system conditions — disk space, CPU,
memory, process availability — and evaluates alert thresholds without sending
data to Grail first and without executing any DQL query. When a threshold is
breached, the agent emits a Davis event directly.

This makes edge detection fundamentally different from DQL-based detectors:
there is no scheduled query, no Grail read latency, and no dependency on the
Dynatrace cluster being reachable at the moment the condition occurs. Each agent
evaluates its own host independently, so detection scales linearly with the
monitored fleet at zero additional query load on Grail.

| Property | Edge-side (OneAgent) | DQL-based (Grail) |
|----------|----------------------|--------------------|
| Detection latency | Seconds (local evaluation) | Minutes (query schedule) |
| Requires Grail data | No | Yes |
| Uses DQL queries | No | Yes |
| Scales with fleet | Linearly — each agent independent | Query cost grows with host count |
| Works when cluster unreachable | Yes (events buffered) | No |
| Supports custom DQL expressions | No | Yes |
| Best for | Infrastructure conditions (disk, CPU, memory, process) | Custom metrics, business KPIs, derived signals |

---

### How Edge-Side Detection Works

1. The OneAgent process monitors the host operating system and collects raw
   infrastructure metrics locally (disk usage, inodes, process state, network
   interface stats, etc.).
2. Configured thresholds are evaluated in the agent's local evaluation loop,
   typically every 60 seconds, without any round-trip to the Dynatrace cluster.
3. When a threshold breach is detected, the agent creates a Davis event and
   forwards it to the Dynatrace ingest endpoint. If connectivity is interrupted,
   events are buffered locally and delivered when connectivity is restored.
4. Davis AI receives the event and applies the same problem grouping and noise
   reduction as it does for server-side alerts.

Because the entire detection pipeline lives on the host, latency between a real
breach and the resulting Davis event is measured in seconds rather than the
minutes a DQL query schedule would impose.

---

### When to Prefer Edge Detection

Prefer edge-side detectors over DQL-based detectors when **all** of the
following are true:

- A OneAgent is already deployed on the host (no additional instrumentation needed)
- The condition you want to alert on is a local infrastructure signal (disk, CPU,
  memory, process, network interface) that the agent can observe directly
- You need fast detection — a DQL query schedule delay is unacceptable
- The fleet is large and you want to avoid Grail query fan-out costs at scale

Do **not** use edge detection when:
- The alert condition requires combining multiple signals or metrics from
  different hosts or services (use DQL-based detector instead)
- The condition is derived from logs, spans, or business events (not observable
  locally by the agent)
- No OneAgent is running on the target host (use DQL-based detector instead)

---

### Disk Edge Alerts (`builtin:infrastructure.disk.edge.anomaly-detectors`)

Settings schema: `builtin:infrastructure.disk.edge.anomaly-detectors`

The disk edge detector is the recommended approach for alerting on disk-related
conditions on any host where a OneAgent is running. It is fast, requires no DQL
query, and scales to arbitrarily large host fleets without increasing Grail query
load. Detection covers disk space exhaustion, inode exhaustion, and slow disk
read/write performance.

**Prefer `builtin:infrastructure.disk.edge.anomaly-detectors` over a DQL-based disk detector whenever a OneAgent
is present.** The agent observes disk metrics at the OS level in real time;
a DQL query on `builtin:host.disk.used.percent` would only evaluate on a
scheduler cadence and adds unnecessary Grail read overhead for a signal that
is already available locally.

#### What it detects

| Condition | Description |
|-----------|-------------|
| Low disk space | Free space percentage falls below a configurable threshold |
| Low disk inodes | Available inodes fall below a configurable threshold (Linux only) |
| Slow disk reads | Average disk read latency exceeds a configurable threshold |
| Slow disk writes | Average disk write latency exceeds a configurable threshold |

#### Configuration fields

| Field | Description |
|-------|-------------|
| `enabled` | Master toggle for the detector on this host or host group |
| `diskLowSpaceDetection.enabled` | Enable/disable low-space alerting |
| `diskLowSpaceDetection.thresholds.high.freeSpacePercentage` | Free-space % below which a HIGH-severity event fires |
| `diskLowSpaceDetection.thresholds.medium.freeSpacePercentage` | Free-space % below which a MEDIUM-severity event fires |
| `diskLowInodesDetection.enabled` | Enable/disable low-inode alerting (Linux) |
| `diskLowInodesDetection.thresholds.high.freeInodesPercentage` | Inode headroom % below which a HIGH-severity event fires |
| `diskSlowWritesAndReadsDetection.enabled` | Enable/disable slow I/O alerting |
| `diskSlowWritesAndReadsDetection.writeAndReadTime.slowDisk` | Latency threshold in milliseconds for slow I/O classification |

#### Example: Configure disk edge alerts via Settings API

The following payload applies disk edge alert thresholds to a specific host
group. POST it to `PUT /api/v2/settings/objects` with schema
`builtin:infrastructure.disk.edge.anomaly-detectors`.

```json
{
  "schemaId": "builtin:infrastructure.disk.edge.anomaly-detectors",
  "scope": "HOST_GROUP-0000000000000001",
  "value": {
    "enabled": true,
    "diskLowSpaceDetection": {
      "enabled": true,
      "thresholds": {
        "high": { "freeSpacePercentage": 5 },
        "medium": { "freeSpacePercentage": 10 }
      }
    },
    "diskLowInodesDetection": {
      "enabled": true,
      "thresholds": {
        "high": { "freeInodesPercentage": 5 },
        "medium": { "freeInodesPercentage": 10 }
      }
    },
    "diskSlowWritesAndReadsDetection": {
      "enabled": true,
      "writeAndReadTime": {
        "slowDisk": 200
      }
    }
  }
}
```

#### Scope options

| Scope | Effect |
|-------|--------|
| `environment` | Applies to all hosts in the environment (global default) |
| `HOST_GROUP-<id>` | Applies to all hosts in a specific host group |
| `HOST-<id>` | Applies to a single host, overrides group and environment settings |

Settings cascade from environment → host group → host. A host-level setting
always wins. This lets you set conservative defaults globally and tighten
thresholds for critical hosts.

#### Scalability note

Each OneAgent evaluates the disk thresholds independently using its local OS
metrics. Adding 1,000 more hosts to your environment does not increase Grail
query load for disk alerting — each new agent simply runs its own evaluation
loop. This is the primary scalability advantage over DQL-based disk detectors,
which would require Grail to query and evaluate `builtin:host.disk.used.percent`
across all hosts on every scheduler tick.

---

### OS Service Monitoring (`os-services-monitoring`)

Settings schema: `os-services-monitoring`

The OS service monitoring detector instructs the OneAgent to continuously check
whether selected operating system services (systemd units on Linux, Windows
Services on Windows) are running on the host. When a monitored service stops or
enters a failed state, the agent emits a Davis event directly without any DQL
query or Grail round-trip.

**Prefer `os-services-monitoring` over a DQL-based availability check whenever
a OneAgent is present.** The agent polls the OS service manager (systemd /
Windows SCM) locally; a DQL-based approach would require the agent to first ship
availability metrics to Grail and then wait for a scheduled query to evaluate
them, adding minutes of latency for a condition the agent already knows about
immediately.

#### What it detects

| Condition | Description |
|-----------|-------------|
| Service unavailable | A monitored OS service is not in the running/active state |
| Service startup failure | A service that should auto-start failed to start after boot |
| Service crash / unexpected stop | A previously running service transitioned to stopped or failed state |

#### Configuration fields

| Field | Description |
|-------|-------------|
| `enabled` | Master toggle for OS service monitoring on this scope |
| `monitoringMode` | `MONITOR_ALL_SERVICES` or `MONITOR_SELECTED_SERVICES` |
| `serviceFilter` | List of service name patterns to include when `monitoringMode` is `MONITOR_SELECTED_SERVICES` |
| `serviceFilter[].serviceId` | OS service name or pattern (e.g. `nginx`, `sshd`, `*sql*`) |
| `statusCondition` | The service state that triggers an alert: `NOT_RUNNING` or `FAILED` |
| `alertActivationDuration` | How long the service must be in the alert state before a Davis event fires (in minutes) |

#### Example: Monitor selected services via Settings API

The following payload configures OS service monitoring for a host group to watch
`nginx` and `postgresql`. Apply it via `PUT /api/v2/settings/objects` with
schema `os-services-monitoring`.

```json
{
  "schemaId": "os-services-monitoring",
  "scope": "HOST_GROUP-0000000000000001",
  "value": {
    "enabled": true,
    "monitoringMode": "MONITOR_SELECTED_SERVICES",
    "serviceFilter": [
      { "serviceId": "nginx" },
      { "serviceId": "postgresql" }
    ],
    "statusCondition": "NOT_RUNNING",
    "alertActivationDuration": 1
  }
}
```

To monitor all services on every host in the environment and alert as soon as
any service stops running:

```json
{
  "schemaId": "os-services-monitoring",
  "scope": "environment",
  "value": {
    "enabled": true,
    "monitoringMode": "MONITOR_ALL_SERVICES",
    "statusCondition": "NOT_RUNNING",
    "alertActivationDuration": 0
  }
}
```

#### Scope options

| Scope | Effect |
|-------|--------|
| `environment` | Applies to all hosts in the environment (global default) |
| `HOST_GROUP-<id>` | Applies to all hosts in a specific host group |
| `HOST-<id>` | Applies to a single host, overrides group and environment settings |

Settings cascade from environment → host group → host, with the most specific
scope winning. Use environment scope for a broad baseline and override at host
group or host level where service lists differ.

#### Scalability note

The OneAgent polls the local OS service manager (systemd on Linux, Service
Control Manager on Windows) directly. No metric is shipped to Grail until a
violation is detected, and no DQL query is executed on any schedule. A fleet of
10,000 hosts each running OS service monitoring adds exactly zero additional
Grail query load for availability checking. This is the preferred approach for
any service availability use case on OneAgent-monitored hosts.

---

### Process Availability (`process-availability`)

Settings schema: `process-availability`

The process availability detector instructs the OneAgent to watch whether
selected processes are running on the host. The agent monitors the local process
table directly and emits a Davis event the moment a watched process disappears,
without any DQL query or Grail round-trip.

This is the successor to the deprecated server-side **Process Group Availability**
detector (`builtin:availability.process-group-alerting`). That legacy schema
evaluated process availability by querying Grail on a schedule, introducing
minutes of detection latency and adding query load proportional to the monitored
fleet. The `process-availability` schema moves the check to the agent, eliminating
both problems.

**Prefer `process-availability` over `builtin:availability.process-group-alerting`
and over any DQL-based process check whenever a OneAgent is present.** The
deprecated schema should no longer be used for new configurations.

#### What it detects

| Condition | Description |
|-----------|-------------|
| Process not running | A watched process or process group is absent from the host process table |
| Process instance count below minimum | The number of running instances of a process drops below a configured minimum |
| Process crash / unexpected exit | A process that was running transitions to not running outside of a planned maintenance window |

#### Configuration fields

| Field | Description |
|-------|-------------|
| `enabled` | Master toggle for process availability monitoring on this scope |
| `processAvailabilityRule` | List of rules, each targeting a set of processes by detection condition |
| `processAvailabilityRule[].name` | Human-readable name for the rule (appears in the Davis event title) |
| `processAvailabilityRule[].condition` | Match expression selecting which processes to watch (e.g. `$eq(nginx)`, `$contains(java)`) |
| `processAvailabilityRule[].minimumInstances` | Minimum number of matching process instances that must be running; alert fires when count falls below this value |
| `recoveryDetectionTime` | Minutes a process must be absent before a recovery is confirmed (prevents flapping on fast restarts) |

#### Example: Watch specific processes via Settings API

The following payload monitors `nginx` (at least 1 instance) and a Java
application (at least 2 instances) on a host group. Apply it via
`PUT /api/v2/settings/objects` with schema `process-availability`.

```json
{
  "schemaId": "process-availability",
  "scope": "HOST_GROUP-0000000000000001",
  "value": {
    "enabled": true,
    "processAvailabilityRule": [
      {
        "name": "nginx must be running",
        "condition": "$eq(nginx)",
        "minimumInstances": 1
      },
      {
        "name": "Java application — minimum 2 instances",
        "condition": "$contains(java)",
        "minimumInstances": 2
      }
    ],
    "recoveryDetectionTime": 5
  }
}
```

#### Deprecation note: `builtin:availability.process-group-alerting`

The legacy Process Group Availability schema evaluated process state by reading
process group metrics from Grail on a scheduled query. It is deprecated and
should not be used for new configurations. Existing rules should be migrated to
`process-availability` to gain:

- Seconds-level detection latency instead of minutes
- No additional Grail query load as the fleet grows
- Agent-local resilience — detection continues even when connectivity to the
  Dynatrace cluster is temporarily interrupted

#### Scope options

| Scope | Effect |
|-------|--------|
| `environment` | Applies to all hosts in the environment (global default) |
| `HOST_GROUP-<id>` | Applies to all hosts in a specific host group |
| `HOST-<id>` | Applies to a single host, overrides group and environment settings |

Settings cascade from environment → host group → host, with the most specific
scope winning.

#### Scalability note

The OneAgent scans the local process table on each evaluation cycle. No process
metrics are shipped to Grail until a violation is detected, and no DQL query is
ever executed. A fleet of 10,000 hosts each running process availability
monitoring adds exactly zero additional Grail query load — the inverse of the
deprecated `builtin:availability.process-group-alerting` schema, which would
issue one or more Grail queries per host per scheduler tick.

---

## Choosing the Right Detector and Model

### Decision guide

```
Is the condition a local infrastructure signal (disk, OS service availability,
process availability) AND a OneAgent is running on the host?
  └─ YES → Use an edge-side detector
           Disk conditions          → builtin:infrastructure.disk.edge.anomaly-detectors
           OS service availability  → os-services-monitoring
           Process availability     → process-availability
           Fast, scalable, no DQL, no Grail dependency
  └─ NO ──────────────────────────────────────────────────────────┐
                                                                   │
Is the metric predefined (service response time, host CPU, etc.)? │
  └─ YES → Use built-in Davis AI detection, tune sensitivity only │
  └─ NO ──────────────────────────────────────────────────────────┤
                                                                   │
  Do you know the exact acceptable boundary (hard SLO/limit)?     │
  └─ YES → Static threshold (DQL-based)                          │
  └─ NO ──────────────────────────────────────────────────────────┤
                                                                   │
  Does the metric follow business-hour or weekly patterns?         │
  └─ YES → Seasonal baseline (DQL-based)                         │
  └─ NO  → Adaptive baseline (DQL-based)                         │
```

### Model comparison

| Scenario | Static | Adaptive | Seasonal | Edge (OneAgent) |
|----------|--------|----------|----------|-----------------|
| Error rate > 5% SLO | ✅ best fit | ⚠ overkill | ❌ not relevant | ❌ not applicable |
| Request rate anomaly | ❌ threshold unclear | ⚠ misses peaks | ✅ best fit | ❌ not applicable |
| Memory leak detection | ⚠ threshold unclear | ✅ best fit | ❌ memory isn't seasonal | ❌ not applicable |
| Business KPI (orders/hr) | ⚠ threshold varies by time | ⚠ averages away patterns | ✅ best fit | ❌ not applicable |
| Disk usage threshold (OneAgent host) | ⚠ DQL adds latency & cost | ❌ disk has a hard limit | ❌ not relevant | ✅ `builtin:infrastructure.disk.edge.anomaly-detectors` — fast, scalable, no DQL |
| Disk usage threshold (no OneAgent) | ✅ best fit | ❌ disk has a hard limit | ❌ not relevant | ❌ no agent available |
| OS service availability (OneAgent host) | ❌ no metric to threshold | ❌ not applicable | ❌ not applicable | ✅ `os-services-monitoring` — immediate, no DQL |
| OS service availability (no OneAgent) | ❌ requires external event ingest | ❌ not applicable | ❌ not applicable | ❌ no agent available |
| Process availability (OneAgent host) | ❌ no metric to threshold | ❌ not applicable | ❌ not applicable | ✅ `process-availability` — replaces deprecated `builtin:availability.process-group-alerting` |
| Process availability (no OneAgent) | ❌ requires external event ingest | ❌ not applicable | ❌ not applicable | ❌ no agent available |

---

## Configuration Best Practices

1. **Start with LOW sensitivity** — reduces false positives during the initial
   learning period. Move to MEDIUM or HIGH only after observing real baseline
   behavior over 1–2 weeks.

2. **Use `violationWindow` / `dealertingWindow`** — require a sustained breach
   before firing and a sustained recovery before clearing. Prevents flapping
   on spiky metrics. A window of 5–10 minutes is a good starting point.

3. **Scope entity selectors tightly** — a detector that covers all services will
   fire on every service simultaneously during a shared infrastructure event,
   creating dozens of Davis events. Scope to a management zone, tag, or specific
   entity list.

4. **Test the DQL query before creating the detector** — run the `timeseries` query
   in a Notebook or the Explore view and inspect the signal shape. Confirm it
   returns data, has the right granularity, and is not null for key entities.

5. **Name events clearly** — the `eventTemplate.title` becomes the Davis event
   name and the problem title. Use the pattern:
   `[Metric] [condition] for [scope]` — e.g., "Error rate above 5% — payment-service".

6. **Avoid overlapping detector definitions** — two detectors on the same metric
   and entity scope will each fire independently, creating two Davis events and
   potentially two problems for the same incident.

7. **Use severity levels intentionally** — `AVAILABILITY` and `ERROR` severity
   events are weighted higher in Davis problem prioritization than `PERFORMANCE`
   or `CUSTOM_ALERT`. Match severity to business impact, not technical magnitude.

8. **Filter notification workflows by `smartscape.affected_entities`, not `root_cause_entity_id`** —
   when a problem trigger in a workflow needs to be scoped to a specific entity,
   do **not** filter on `root_cause_entity_id`. Davis may not populate a root cause,
   and the root cause assignment may shift during the problem lifecycle.
   Instead, match the target entity ID against the `smartscape.affected_entities` record array.
   Use `[][id]` to iterate the array and wrap the comparison in `iAny(...)`, because DQL rejects
   a bare iterative expression in a `filter`. The `id` member is a `smartscapeId`, so convert it
   with `toString()` before comparing it to a string:

   ```
   iAny(toString(smartscape.affected_entities[][id]) == "SERVICE-0000000000000001")
   ```

   This makes the filter resilient to root-cause re-assignments and ensures the
   workflow fires whenever the entity is involved in the problem, regardless of
   whether Davis considers it the root cause.
