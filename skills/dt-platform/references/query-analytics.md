# Query Analytics

DQL query execution telemetry in `dt.system.events` with
`event.kind == "QUERY_EXECUTION_EVENT"`. Track query performance, scan costs,
failure rates, and usage patterns by table, pool, and user.

> **High volume.** Each DQL query execution emits one event. Filter by
> `table`, `query_pool`, or `status` to narrow scope.

## Contents

- [Discovery Query](#discovery-query)
- [Fields](#fields)
- [Tables](#tables)
- [Query Pools](#query-pools)
- [`client.source` Semantics](#clientsource-semantics)
- [`client.client_context` Formats](#clientclient_context-formats)
- [Internal Service Context Values](#internal-service-context-values)
- [`client.*` Field Availability on BUE vs QEE](#client-field-availability-on-bue-vs-qee)
- [Common Workflows](#common-workflows)
- [Best Practices](#best-practices)

## Discovery Query

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| summarize count = count(), by: {table, status}
| sort count desc
```

## Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | timestamp | Query execution time |
| `event.kind` | string | Always `"QUERY_EXECUTION_EVENT"` |
| `event.type` | string | `"TABLE"` (standard queries) or `"FILES"` (file queries) |
| `status` | string | `"SUCCEEDED"`, `"FAILED"`, or `"CANCELLED"` |
| `query_string` | string | Full DQL query text |
| `table` | string | Target data table — see [Tables](#tables) |
| `bucket` | string | Target Grail bucket (e.g., `"default_metrics"`, `"default_logs"`) |
| `query_pool` | string | Execution pool — see [Query Pools](#query-pools) |
| `execution_duration_ms` | long | Query execution time in milliseconds |
| `scanned_bytes` | long | Total bytes scanned |
| `scanned_bytes.included` | long | Bytes scanned from included volume |
| `scanned_bytes.on_demand` | long | Bytes scanned from on-demand volume |
| `scanned_records` | long | Number of records scanned |
| `scanned_data_points` | long | Data points scanned (metrics queries) |
| `delivered_records` | long | Records returned to caller |
| `sampling_ratio` | long | Sampling ratio applied |
| `query_id` | string | Unique query execution ID |
| `query_start` | long | Query start epoch (ms) |
| `query_end` | long | Query end epoch (ms) |
| `query_queue_time_ms` | long | Queue wait time (ms) |
| `user.id` | string | User UUID |
| `user.email` | string | User email |
| `user` | string | User UUID (duplicate of `user.id`) |
| `environment` | string | Environment ID |
| `client.source` | string | Pool-dependent — see [`client.source` Semantics](#clientsource-semantics) |
| `client.application_context` | string | App ID making the query |
| `client.client_context` | string | Pool-dependent JSON or string — see [`client.client_context` Formats](#clientclient_context-formats) |
| `client.internal_service_context` | string | Internal service identifier — see [Internal Service Context Values](#internal-service-context-values) |
| `client.function_context` | string | AppEngine function path (AUTOMATION, INTERNAL_APPLICATION pools) |
| `client.workflow_context` | string | Workflow UUID (AUTOMATION pool only) |
| `client.api_version` | string | API version |
| `analysis_timeframe.start` | timestamp | Queried time range start |
| `analysis_timeframe.end` | timestamp | Queried time range end |
| `dt.security_context` | string | Always `"QUERY_EXECUTION_EVENT"` |

## Tables

| Table | Description |
|-------|-------------|
| `metrics` | Metric timeseries queries |
| `events` | Event queries |
| (empty) | Queries without explicit table (e.g., metadata) |
| `bizevents` | Business event queries |
| `logs` | Log queries |
| `spans` | Distributed trace span queries |
| `smartscape.nodes` | Topology node queries |
| `user.events` | User event queries |
| `dt.system.events` | System event queries |
| `security.events` | Security event queries |
| `smartscape.edges` | Topology edge queries |
| `application.snapshots` | Application snapshot queries |
| `user.sessions` | User session queries |
| `user.replays` | Session replay queries |

## Query Pools

| Pool | Description |
|------|-------------|
| `INTERNAL_APPLICATION` | Dynatrace platform app queries |
| `API` | External API queries |
| `AUTOMATION` | Workflow automation queries |
| `ALERTING` | Davis alerting queries |
| `DASHBOARDS` | Dashboard tile queries |
| `OTHER` | Miscellaneous queries |
| `BILLING` | Billing system queries |
| `APPLICATION` | Custom app queries |

## `client.source` Semantics

The `client.source` field has pool-dependent meaning:

| Pool | `client.source` contains | Example |
|------|--------------------------|---------|
| `DASHBOARDS` | Dashboard URL | `https://<env>.apps.dynatrace.com/ui/document/...` |
| `ALERTING` | Settings `objectId` (~50%) OR analyzer type name (~50%) | `builtin:davis.anomaly-detectors/...` or `dt.davis.anomaly-detector.metric-event` |
| `AUTOMATION` | `"appId:functionName"` string | `dynatrace.automations:run-javascript` |
| `APPLICATION` | App URL or identifier | `https://<env>.apps.dynatrace.com/ui/apps/...` |
| `INTERNAL_APPLICATION` | Internal service name or app URL | Varies |
| `API` | Client identifier or URL | Varies |
| `OTHER` | Mixed | Varies |
| `BILLING` | Billing service identifier | Varies |

> **Key insight for ALERTING:** ~50% of queries carry the detector settings
> `objectId` in `client.source`, enabling direct cost attribution. The other
> ~50% carry generic analyzer type names (3 types:
> `dt.davis.anomaly-detector.metric-event`,
> `dt.davis.anomaly-detector.log-event`,
> `dt.davis.anomaly-detector.static-threshold`).

## `client.client_context` Formats

The `client.client_context` field is polymorphic — its format depends on the
query pool. **Available on QEE only, NOT on BUE.**

| Pool | Format | Key fields / pattern |
|------|--------|---------------------|
| `ALERTING` | JSON object | `dt.task.id`, `dt.task.group`, `dt.analyzer.query_type`, `dt.analyzer.execution_id` |
| `INTERNAL_APPLICATION` | JSON subset | `dt.davis.datadriver` (when present) |
| `AUTOMATION` | `"appId:functionName"` string | Same as `client.source` |
| `APPLICATION`, `OTHER`, `API` | Plain string | App or client identifier |

### Parsing ALERTING `client.client_context`

Use `"JSON:varname"` to parse the JSON string into a record, then access
dotted keys with backtick-quoted bracket notation:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter query_pool == "ALERTING"
| parse client.client_context, "JSON:ctx"
| summarize queries = count(), total_scanned = sum(scanned_bytes),
    by: {task_id = ctx[`dt.task.id`], task_group = ctx[`dt.task.group`]}
| sort total_scanned desc
| limit 20
```

> **Dotted keys**: JSON keys containing dots (e.g., `dt.task.id`) MUST use
> backtick quoting inside bracket access: `ctx[\`dt.task.id\`]`. Without
> backticks, DQL interprets the dots as nested field access and fails.
>
> The `dt.task.id` inside `client.client_context` is the settings `objectId`
> from `builtin:davis.anomaly-detectors` — the same value as `dt.task.id` in
> `ANALYZER_EXECUTION_EVENT`. Use this to join detector execution data with
> query cost data.

## Internal Service Context Values

The `client.internal_service_context` field identifies the internal Dynatrace
service making the query. **Available on QEE only.**

| Value | Description |
|-------|-------------|
| `dt.davis.anomaly-detector` | Davis anomaly detection |
| `dt.security.threat-detection-service` | Security threat detection |
| `dt.mcp.gateway` | MCP gateway |
| `dt.davis.datadriver` | Davis data driver |
| `dt.cloud.aws.monitoring` | AWS cloud monitoring |
| `dt.cloud.azure.monitoring` | Azure cloud monitoring |
| `dt.dql.api` | DQL API service |
| `dt.settings.schema` | Settings schema service |
| `dt.billing.query` | Billing query service |
| `dt.slo.evaluation` | SLO evaluation |
| `dt.hub.search` | Hub search |

## `client.*` Field Availability on BUE vs QEE

Not all `client.*` fields are available on both event kinds:

| Field | QEE (`QUERY_EXECUTION_EVENT`) | BUE (`BILLING_USAGE_EVENT` Query types) |
|-------|------|------|
| `client.source` | ✅ | ✅ |
| `client.application_context` | ✅ | ✅ |
| `client.function_context` | ✅ | ✅ |
| `client.client_context` | ✅ | ❌ |
| `client.internal_service_context` | ✅ | ❌ |
| `client.workflow_context` | ✅ | ❌ |

> **Implication:** Per-detector cost attribution via `client.client_context`
> parse is QEE-only. For billable cost by source, use `client.source` on BUE
> Query events — but accept that ALERTING attribution is partial (~50%).

## Common Workflows

### Query Volume by Table

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| summarize query_count = count(), by: {table}
| sort query_count desc
```

### Failed Queries

```dql
fetch dt.system.events, from: -24h
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter status == "FAILED"
| fields timestamp, table, query_pool, query_string, user.email, execution_duration_ms
| sort timestamp desc
| limit 50
```

### Slowest Queries

```dql
fetch dt.system.events, from: -24h
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter status == "SUCCEEDED"
| sort execution_duration_ms desc
| fields timestamp, table, execution_duration_ms, scanned_bytes, scanned_records, query_string, user.email
| limit 20
```

### Scan Cost by Table (Bytes Scanned)

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter status == "SUCCEEDED"
| summarize total_scanned_gib = sum(scanned_bytes) / 1073741824, query_count = count(), by: {table}
| sort total_scanned_gib desc
```

### Query Volume Trend by Pool

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| summarize query_count = count(), by: {timeframe = bin(timestamp, 1h), query_pool}
| sort timeframe asc
```

### Top Query Consumers by User

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| summarize query_count = count(), total_scanned_gib = sum(scanned_bytes) / 1073741824, by: {user.email}
| sort total_scanned_gib desc
| limit 20
```

### Failure Rate by Table

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| summarize total = count(), failed = countIf(status == "FAILED"), by: {table}
| fieldsAdd failure_rate = 100.0 * failed / total
| sort failure_rate desc
```

### On-Demand vs Included Scan Volume

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter status == "SUCCEEDED"
| summarize included_gib = sum(`scanned_bytes.included`) / 1073741824, on_demand_gib = sum(`scanned_bytes.on_demand`) / 1073741824, by: {table}
| sort on_demand_gib desc
```

### Dashboard Query Performance

```dql
fetch dt.system.events, from: -24h
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter query_pool == "DASHBOARDS"
| summarize avg_duration = avg(execution_duration_ms), p95_duration = percentile(execution_duration_ms, 95), query_count = count(), by: {table}
| sort p95_duration desc
```

### Queries Targeting a Specific Table

```dql-template
fetch dt.system.events, from: -7d
| filter event.kind == "QUERY_EXECUTION_EVENT"
| filter table == "<TABLE_NAME>"
| summarize query_count = count(), avg_duration_ms = avg(execution_duration_ms), total_scanned_gib = sum(scanned_bytes) / 1073741824, by: {query_pool}
| sort total_scanned_gib desc
```

### Cost Attribution Investigation

For full query cost attribution workflows — BUE by source, per-detector
breakdown via `client.client_context`, and step-by-step investigation guide —
see [cost-investigation.md](cost-investigation.md) → Query Cost Attribution.

## Best Practices

1. **Backtick fields with dots** — Use `` `scanned_bytes.included` `` for
   fields containing dots that are not nested
2. **Filter by `query_pool` for source analysis** — Distinguishes dashboard
   queries from automation, alerting, and app queries
3. **Empty `table` field** — Some queries (metadata lookups, multi-table) don't
   populate this field
4. **`scanned_bytes` drives DPS cost** — Focus on `scanned_bytes.on_demand` for
   cost optimization; included volume is free
5. **BUE for billable truth, QEE for diagnostics** — BUE Query events reflect
   actual billed scan volumes; QEE provides execution details (duration, query
   text, `client.client_context`) but is not the billing source of truth
6. **`dt.system.events` cannot be a lookup source** — Use `data json:"""..."""`
   inline lookups or materialize results when joining platform data
