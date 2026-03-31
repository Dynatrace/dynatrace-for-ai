# Data Management Events

Data pipeline and enrichment telemetry in `dt.system.events`. Covers two
event kinds:

- `ENRICHMENT_EXECUTION_EVENT` — Security intelligence enrichment runs
- `DATA_ACQUISITION_EVENT` — Cloud data acquisition task status

## Contents

- [Discovery Query](#discovery-query)
- [ENRICHMENT_EXECUTION_EVENT](#enrichment_execution_event)
- [DATA_ACQUISITION_EVENT](#data_acquisition_event)
- [Best Practices](#best-practices)

## Discovery Query

```dql
fetch dt.system.events, from: -7d
| filter in(event.kind, "ENRICHMENT_EXECUTION_EVENT", "DATA_ACQUISITION_EVENT")
| summarize count = count(), by: {event.kind}
```

## ENRICHMENT_EXECUTION_EVENT

Emitted for each data enrichment execution (security intelligence lookups).

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | timestamp | When the enrichment ran |
| `event.kind` | string | Always `"ENRICHMENT_EXECUTION_EVENT"` |
| `event.id` | string | Unique event identifier |
| `event.outcome` | string | `"success"` or `"failure"` |
| `event.provider` | string | `"SECURITY_INTELLIGENCE_ENGINE"` |
| `event.version` | string | Event schema version |
| `dt.enrichment.integration.id` | string | Integration name (e.g., `"dynatrace.abuseipdb"`) |
| `dt.enrichment.integration.method.id` | string | Method invoked (e.g., `"check-ip"`) |
| `dt.enrichment.integration.connection.id` | string | Connection settings object ID |
| `dt.enrichment.duration` | long | Duration in nanoseconds |
| `dt.enrichment.result.is_cached` | boolean | `true` when result served from cache |
| `dt.app.id` | string | App providing the integration |
| `user.id` | string | User UUID |

### Integration Distribution

| Integration | Outcome | Description |
|-------------|---------|-------------|
| `dynatrace.abuseipdb` | success | AbuseIPDB IP reputation lookups |
| `dynatrace.virustotal` | success | VirusTotal threat intelligence lookups |

### Workflows

#### Enrichment Overview

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "ENRICHMENT_EXECUTION_EVENT"
| summarize executions = count(), cached = countIf(dt.enrichment.result.is_cached == true), by: {dt.enrichment.integration.id, dt.enrichment.integration.method.id, event.outcome}
| sort executions desc
```

#### Failed Enrichments

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "ENRICHMENT_EXECUTION_EVENT"
| filter event.outcome == "failure"
| fields timestamp, dt.enrichment.integration.id, dt.enrichment.integration.method.id, dt.enrichment.duration
| sort timestamp desc
```

#### Enrichment Performance

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "ENRICHMENT_EXECUTION_EVENT"
| summarize avg_duration_ms = avg(dt.enrichment.duration) / 1000000, executions = count(), by: {dt.enrichment.integration.id}
| sort avg_duration_ms desc
```

## DATA_ACQUISITION_EVENT

Emitted by cloud data acquisition tasks (pollers). Reports task status
including warnings and errors from cloud provider integrations.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | timestamp | When the event was recorded |
| `event.kind` | string | Always `"DATA_ACQUISITION_EVENT"` |
| `da.clouds.accountId` | string | Cloud account ID (`"unknown"` if unavailable) |
| `da.clouds.configurationId` | string | Integration configuration UUID |
| `da.clouds.source` | string | Poller source (e.g., `"aws-smartscape-poller"`) |
| `da.clouds.status` | string | `"WARN"`, `"ERROR"`, or `"OK"` |
| `da.clouds.task` | string | Task name (e.g., `"aws-smartscape-poller-full"`) |
| `da.clouds.content` | string | Status message with details |

### Source Distribution

| Source | Status | Description |
|--------|--------|-------------|
| `aws-smartscape-poller` | `WARN` | AWS topology polling warnings (auth/permission issues) |

### Workflows

#### Data Acquisition Issues

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "DATA_ACQUISITION_EVENT"
| summarize issues = count(), by: {da.clouds.source, da.clouds.status, da.clouds.task}
| sort issues desc
```

#### Acquisition Error Details

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "DATA_ACQUISITION_EVENT"
| filter in(da.clouds.status, "WARN", "ERROR")
| fields timestamp, da.clouds.source, da.clouds.status, da.clouds.task, da.clouds.content, da.clouds.accountId
| sort timestamp desc
| limit 20
```

#### Acquisition Trend

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "DATA_ACQUISITION_EVENT"
| summarize events = count(), by: {timeframe = bin(timestamp, 1d), da.clouds.status}
| sort timeframe asc
```

## Best Practices

1. **Enrichment `duration` is nanoseconds** — Divide by
   `1000000` for milliseconds: `dt.enrichment.duration / 1000000`
2. **Cache hit ratio matters** — High `is_cached == true` ratio means the
   enrichment engine is efficient; low ratio may indicate excessive unique lookups
3. **Data acquisition warnings are often permission issues** — Check
   `da.clouds.content` for IAM or authorization errors
4. **`da.clouds.accountId == "unknown"`** — Common when the poller cannot
   resolve the account; use `da.clouds.configurationId` to identify the integration
