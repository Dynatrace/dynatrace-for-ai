# Extensions Events

Extension self-monitoring (SFM) telemetry in `dt.system.events` with
`event.kind == "EXTENSIONS_EVENT"`. Tracks Extensions 2.0 lifecycle health:
connection errors, polling failures, and endpoint status messages.

> **See also:** The `dt-obs-extensions` skill covers extension status codes,
> monitoring configuration troubleshooting, and DEC error code lookup.

## Contents

- [Discovery Query](#discovery-query)
- [Fields](#fields)
- [Common Workflows](#common-workflows)
- [Best Practices](#best-practices)

## Discovery Query

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "EXTENSIONS_EVENT"
| summarize count = count(), by: {dt.extension.name, loglevel}
| sort count desc
```

## Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | timestamp | When the event was recorded |
| `event.kind` | string | Always `"EXTENSIONS_EVENT"` |
| `event.type` | string | Always `"SFM"` (self-monitoring) |
| `dt.extension.name` | string | Extension identifier (e.g., `"com.dynatrace.extension.postgres"`). Sometimes empty. |
| `dt.extension.config.id` | string | UUID of the monitoring configuration |
| `endpoint` | string | Connection endpoint string. Null on ~43% of events (summary-level messages). |
| `content` | string | Free-text SFM log message — the actual diagnostic detail |
| `loglevel` | string | `"INFO"`, `"WARN"`, or `"ERROR"` |
| `status` | string | Mirrors `loglevel` |
| `ordinal` | long | Event ordering sequence number |
| `dt.openpipeline.source` | string | `"extension:<extension-name>"` pattern |
| `dt.openpipeline.pipelines` | string | Usually `"system.events:default"` |

**Not populated:** `event.id` (rare — nearly always null), `event.provider`,
`event.version`, `dt.security_context`.

## Common Workflows

### Extension Health Overview

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "EXTENSIONS_EVENT"
| summarize total = count(),
    errors = countIf(loglevel == "ERROR"),
    warnings = countIf(loglevel == "WARN"),
    by: {dt.extension.name}
| fieldsAdd error_pct = 100.0 * errors / total
| sort errors desc
```

### Noisiest Extensions

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "EXTENSIONS_EVENT"
| filter in(loglevel, "ERROR", "WARN")
| summarize events = count(), by: {dt.extension.name, loglevel}
| sort events desc
| limit 20
```

### Recent Errors

```dql
fetch dt.system.events, from: -24h
| filter event.kind == "EXTENSIONS_EVENT"
| filter loglevel == "ERROR"
| fields timestamp, dt.extension.name, dt.extension.config.id, endpoint, content
| sort timestamp desc
| limit 20
```

### Failing Endpoints

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "EXTENSIONS_EVENT"
| filter loglevel == "ERROR"
| filter isNotNull(endpoint)
| summarize errors = count(), by: {dt.extension.name, endpoint}
| sort errors desc
| limit 20
```

### Error Trend by Extension

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "EXTENSIONS_EVENT"
| filter in(loglevel, "ERROR", "WARN")
| summarize events = count(), by: {timeframe = bin(timestamp, 1d), dt.extension.name, loglevel}
| sort timeframe asc
```

### Extension Config Overview

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "EXTENSIONS_EVENT"
| summarize events = count(),
    endpoints = countDistinct(endpoint),
    by: {dt.extension.name, dt.extension.config.id}
| sort events desc
```

### Content Pattern Search

Search SFM log messages for specific error patterns (e.g., timeouts):

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "EXTENSIONS_EVENT"
| filter loglevel == "ERROR"
| filter contains(content, "timeout")
| fields timestamp, dt.extension.name, endpoint, content
| sort timestamp desc
| limit 20
```

## Best Practices

1. **Filter by `loglevel` for health monitoring** — `ERROR` and `WARN` events
   signal real problems; `INFO` events are routine execution confirmations
2. **`content` is free-text** — Use `contains()` to search for specific error
   patterns (e.g., `contains(content, "timeout")`)
3. **`endpoint` is null on summary events** — Summary messages (e.g., "Polling
   finished with issues for endpoints: ...") lack the `endpoint` field; filter
   `isNotNull(endpoint)` for endpoint-specific analysis
4. **No `event.id` for dedup** — Unlike billing events, extension events rarely
   carry `event.id`; dedup is not needed
5. **`status` mirrors `loglevel`** — Use either field for filtering; `loglevel`
   is the conventional choice
6. **Volume varies dramatically** — Database extensions (postgres, sql-server)
   can generate high WARN volumes from "did not produce any events"
   messages; SNMP extensions tend to produce ERROR events from timeouts
