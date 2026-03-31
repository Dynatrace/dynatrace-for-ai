# Anomaly Detector Events

Davis AI anomaly detector execution and status telemetry in `dt.system.events`.
Covers two event kinds:

- `ANALYZER_EXECUTION_EVENT` — Scheduled analyzer task runs
- `ANOMALY_DETECTOR_STATUS_EVENT` — Detector health status changes

## Contents

- [Discovery Query](#discovery-query)
- [ANALYZER_EXECUTION_EVENT](#analyzer_execution_event)
- [ANOMALY_DETECTOR_STATUS_EVENT](#anomaly_detector_status_event)
- [Cross-References](#cross-references)
- [Best Practices](#best-practices)

## Discovery Query

```dql
fetch dt.system.events, from: -7d
| filter in(event.kind, "ANALYZER_EXECUTION_EVENT", "ANOMALY_DETECTOR_STATUS_EVENT")
| summarize count = count(), by: {event.kind}
```

## ANALYZER_EXECUTION_EVENT

Emitted for each scheduled Davis analyzer execution.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | timestamp | When the event was recorded |
| `event.kind` | string | Always `"ANALYZER_EXECUTION_EVENT"` |
| `dt.task.name` | string | Analyzer task display name |
| `dt.task.id` | string | Task object ID |
| `dt.task.group` | string | Task group — see [Task Groups](#task-groups) |
| `dt.task.result_status` | string | `"SUCCESS"` or `"FAILED"` |
| `dt.task.failure_reason` | string | Error details (when FAILED) |
| `dt.task.scheduling_expression` | string | Schedule interval (e.g., `"PT1M"`) |
| `dt.task.scheduling_type` | string | `"FIXED_DELAY"` |
| `dt.analyzer.execution.start` | timestamp | Execution start (null when disabled) |
| `dt.analyzer.execution.end` | timestamp | Execution end |
| `dt.analyzer.analysis_timeframe.start` | timestamp | Analysis window start |
| `dt.analyzer.analysis_timeframe.end` | timestamp | Analysis window end |
| `dt.analyzer.result_records` | long | Records produced |
| `dt.analyzer.error_messages` | array | Error messages |
| `dt.analyzer.warning_messages` | array | Warning messages |

### Task Groups

| Group | Description |
|-------|-------------|
| `builtin:davis.anomaly-detectors` | Davis anomaly detection tasks |
| `builtin:health-experience.cloud-alert` | Cloud health alert tasks |

### Status Distribution

| Status | Notes |
|--------|-------|
| `FAILED` | Mostly disabled/misconfigured detectors |
| `SUCCESS` | Successfully executed analyzers |

> **Note:** High failure counts are common — disabled detectors still emit
> `FAILED` events with a descriptive `failure_reason`.

### Workflows

#### Analyzer Failure Summary

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "ANALYZER_EXECUTION_EVENT"
| filter dt.task.result_status == "FAILED"
| summarize failures = count(), by: {dt.task.name, dt.task.failure_reason}
| sort failures desc
| limit 20
```

#### Successful Analyzers

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "ANALYZER_EXECUTION_EVENT"
| filter dt.task.result_status == "SUCCESS"
| summarize runs = count(), by: {dt.task.name, dt.task.group}
| sort runs desc
```

#### Failure Rate by Task Group

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "ANALYZER_EXECUTION_EVENT"
| summarize total = count(), failed = countIf(dt.task.result_status == "FAILED"), by: {dt.task.group}
| fieldsAdd failure_rate = 100.0 * failed / total
```

## ANOMALY_DETECTOR_STATUS_EVENT

Emitted when a Davis anomaly detector changes health status. Very low volume
— indicates detectors that encountered errors.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | timestamp | When the status changed |
| `event.kind` | string | Always `"ANOMALY_DETECTOR_STATUS_EVENT"` |
| `davis.anomaly_detector.status` | string | `"ERROR"` or `"OK"` |
| `davis.anomaly_detector.message` | string | Status details (e.g., query timeout) |
| `dt.settings.object_id` | string | Settings object ID of the detector |
| `client.internal_service_context` | string | `"dt.davis.anomaly-detector"` |

### Workflows

#### Detector Status Issues

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "ANOMALY_DETECTOR_STATUS_EVENT"
| fields timestamp, davis.anomaly_detector.status, davis.anomaly_detector.message, dt.settings.object_id
| sort timestamp desc
```

## Cross-References

### Linking Detectors to Query Costs

The same detector identifier appears in three places under different field names:

| Source | Field | Value |
|--------|-------|-------|
| This file (ANALYZER_EXECUTION_EVENT) | `dt.task.id` | Settings `objectId` |
| This file (ANOMALY_DETECTOR_STATUS_EVENT) | `dt.settings.object_id` | Settings `objectId` |
| Query analytics (QEE, ALERTING pool) | `client.client_context` → `dt.task.id` | Settings `objectId` |
| Query analytics (QEE, ALERTING pool) | `client.source` | Settings `objectId` (~50% of ALERTING queries) |

To attribute query costs to a specific detector, join on the settings `objectId`:

```dql
// Step 1: Find a detector's objectId from its name
fetch dt.system.events, from: -7d
| filter event.kind == "ANALYZER_EXECUTION_EVENT"
| filter contains(dt.task.name, "my detector name")
| summarize count(), by: {dt.task.id, dt.task.name}
```

```dql-template
// Step 2: Find that detector's queries in QEE (parse client_context JSON)
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter query_pool == "ALERTING"
| parse client.client_context, "JSON:ctx"
| filter ctx[`dt.task.id`] == "<objectId from step 1>"
| summarize queries = count(), total_scanned = sum(scanned_bytes), by: {status}
```

See [cost-investigation.md](cost-investigation.md) → Query Cost Attribution for
the full step-by-step investigation workflow including BUE cost estimation.

> **QEE only.** The `client.client_context` field is NOT available on BUE
> Query events. For billable cost by source, use `client.source` on BUE — but
> only ~50% of ALERTING queries carry the `objectId` there.

### `user.id` Is Not Detector-Specific

Anomaly detectors execute under a shared service account configured in
`executionSettings.actor` on the detector settings object. This means
all detectors share the same `user.id` in QEE events (e.g.,
`dt.davis.anomaly-detector`). NEVER use `user.id` to attribute query
costs to a single detector — it will aggregate all detector queries
together. Use `dt.task.id` / `client.client_context` instead.

## Best Practices

1. **High failure count is often expected** — Disabled detectors emit FAILED
   events; filter by `dt.task.failure_reason` to find actionable failures
2. **Use `dt.task.group` to segment** — Separates Davis anomaly detectors from
   cloud health alerts
3. **`ANOMALY_DETECTOR_STATUS_EVENT` is rare** — Only emitted on status
   transitions; absence means detectors are healthy
4. **`dt.settings.object_id`** — Links to the settings object for the detector;
   use with Settings API for configuration details
