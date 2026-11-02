# Classic Detection Patterns

Rules for identifying classic cloud connection references in DQL queries, metric selectors, entity selectors, dashboards, SLOs, and alerts.

---

## Table of Contents

- [1. Classic Metric Key Prefixes](#1-classic-metric-key-prefixes)
- [2. Classic Entity Types](#2-classic-entity-types)
- [3. Classic Entity Selector Patterns](#3-classic-entity-selector-patterns)
- [4. Detection Logic Details](#4-detection-logic-details)

---

## 1. Classic Metric Key Prefixes

Any occurrence of these prefixes in a metric key, DQL query, or metric selector expression indicates a classic cloud dependency.

### AWS

| Prefix | Source | Example |
|---|---|---|
| `dt.cloud.aws.*` | Classic built-in (definitive; Grail) | `dt.cloud.aws.ec2.cpu.usage` |
| `builtin:cloud.aws.*` | Classic built-in (Cassandra-era selector format) | `builtin:cloud.aws.ec2.cpu_usage` |
| `ext:cloud.aws.*` | Classic non-built-in (Cassandra-era selector format) | `ext:cloud.aws.lambda.invocations_sum` |
| `cloud.aws.<service>.<snake_case>` | Classic non-built-in (Grail) — **requires disambiguation** | `cloud.aws.lambda.concurrent_executions_sum` |

**AWS disambiguation**: The prefix `cloud.aws.*` is shared between classic non-built-in and the new connection. Classic non-built-in keys use snake_case after the service name. New connection keys use PascalCase with `.By.` dimension separators. Apply this regex to detect classic-only:

```
/cloud\.aws\.[a-z0-9_]+\.[a-z][a-z0-9_]*/
```

This matches `cloud.aws.lambda.concurrent_executions_sum` (classic) but NOT `cloud.aws.lambda.ConcurrentExecutions.By.FunctionName` (new connection).

### Azure

| Prefix | Source | Example |
|---|---|---|
| `dt.cloud.azure.*` | Classic built-in (definitive) | `dt.cloud.azure.vm.cpu_usage` |
| `builtin:cloud.azure.*` | Classic built-in (Cassandra-era selector format) | `builtin:cloud.azure.redis.cache.hits` |
| `ext:cloud.azure.*` | Classic non-built-in (Cassandra-era selector format) | `ext:cloud.azure.microsoft_cache.redis.cachehits` |
| `cloud.azure.microsoft_*` | Ambiguous — may be classic cloud service OR new connection | `cloud.azure.microsoft_cache.redis.cachehits` |

**Azure disambiguation**: The prefix `cloud.azure.microsoft_*` is shared between classic cloud services and the new connection. Distinguish by checking `dt.da.source`:
- `dt.da.source == "azure-metric-poller"` → new connection
- `dt.da.source` is null → classic cloud service

When scanning static text (dashboards, SLO expressions), flag `cloud.azure.microsoft_*` as ambiguous.

### GCP

| Prefix | Source | Example |
|---|---|---|
| `cloud.gcp.<api>_googleapis_com.*` | Classic (definitive — 2nd segment ends in `_googleapis_com`) | `cloud.gcp.cloudsql_googleapis_com.database.cpu.utilization` |
| `builtin:cloud.gcp.*` | Classic built-in (Cassandra-era selector format) | `builtin:cloud.gcp.compute.cpu.utilization` |

**GCP disambiguation**: Classic GCP keys have `<api>_googleapis_com` as the 2nd segment. New connection keys insert a resource type between: `cloud.gcp.<resource_type>.<api>.<path>`. Apply this regex to detect classic-only:

```
/cloud\.gcp\.[a-z0-9]+_googleapis_com\./
```

This matches `cloud.gcp.compute_googleapis_com.instance.cpu.utilization` (classic) but NOT `cloud.gcp.gce_instance.compute_googleapis_com.instance.cpu.utilization` (new connection).

> **Note**: GCP has NO `dt.cloud.gcp.*` prefix. All classic GCP metrics use `cloud.gcp.*`.

---

## 2. Classic Entity Types

A `fetch dt.entity.<type>` in DQL referencing these types indicates a classic cloud dependency. New connections use `smartscapeNodes <TYPE>` — never `fetch dt.entity.*`.

### AWS Built-in Entity Types

`ec2_instance`, `ebs_volume`, `aws_lambda_function`, `auto_scaling_group`, `aws_application_load_balancer`, `aws_network_load_balancer`, `elastic_load_balancer`, `relational_database_service`, `dynamo_db_table`

### AWS Non-Built-in (Custom Device)

`custom_device` with `cloud:aws:*` sub-types (e.g., `cloud:aws:s3`, `cloud:aws:sqs`, `cloud:aws:rds`, `cloud:aws:aurora`, `cloud:aws:lambda`, etc.)

### Azure Built-in Entity Types

`azure_vm`, `azure_vm_scale_set`, `azure_load_balancer`, `azure_event_hub_namespace`, `azure_event_hub`, `azure_redis_cache`, `azure_function_app`, `azure_storage_account`, `azure_cosmos_db`, `azure_web_app`, `azure_sql_server`, `azure_sql_database`

### Azure Non-Built-in (Custom Device)

`custom_device` with `cloud:azure:*` sub-types (e.g., `cloud:azure:cache:redis`, `cloud:azure:postgresql:flexibleservers`, `cloud:azure:containerservice:managedcluster`, etc.)

### GCP (All Classic)

`custom_device` with `cloud:gcp:*` sub-types (e.g., `cloud:gcp:gce_instance`, `cloud:gcp:cloudsql_database`, `cloud:gcp:cloud_function`, etc.)

Parent entity: `cloud:gcp:project`

> **GCP has NO dedicated classic entity types** — all GCP entities are `CUSTOM_DEVICE` with `cloud:gcp:*` sub-types.

---

## 3. Classic Entity Selector Patterns

In classic SLOs, the `filter` field uses entity selectors. These patterns indicate classic dependencies:

| Pattern | What it means | Example |
|---|---|---|
| `type(EC2_INSTANCE)` | Classic AWS EC2 entity | `type(EC2_INSTANCE),entityName.contains("prod")` |
| `type(AZURE_VM)` | Classic Azure VM entity | `type(AZURE_VM),tag("env:prod")` |
| `type(CUSTOM_DEVICE)` | Classic custom device (any provider) | `type(CUSTOM_DEVICE),entityName.startsWith("cloud:gcp:")` |
| `type(<CLASSIC_TYPE>)` | Any classic entity type from the lists above | `type(AWS_LAMBDA_FUNCTION)` |

---

## 4. Detection Logic Details

### Scanning DQL Queries (Dashboard Tiles)

For each DQL query string found in a dashboard tile:

1. **Check for classic metric prefixes** — search for any prefix from §1 in the query text
2. **Check for classic entity fetches** — search for `fetch dt.entity.<type>` patterns from §2
3. **Apply disambiguation** — for ambiguous prefixes (`cloud.aws.*`, `cloud.azure.microsoft_*`, `cloud.gcp.*`), apply the provider-specific regex rules

### Scanning Metric Selectors (Classic Dashboard Tiles, Alerts)

For metric selector strings (e.g., `builtin:cloud.aws.ec2.cpu_usage:avg`):

1. Scan the full text for classic prefixes from §1
2. Strip trailing aggregation suffixes (`:avg`, `:min`, `:max`, `:sum`, `:count`, `:value`, `:auto`) before matching
3. The `ext:` and `builtin:` prefixes are only found in Cassandra-era selectors — they are definitive classic indicators

### Scanning Entity Selectors (Classic SLOs)

For entity selector strings:

1. Scan for `type(<ENTITY_TYPE>)` patterns matching classic entity types from §2
2. For GCP, any `type(CUSTOM_DEVICE)` is potentially a classic GCP reference
