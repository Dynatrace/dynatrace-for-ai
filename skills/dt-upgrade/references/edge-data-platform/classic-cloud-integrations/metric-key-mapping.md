# Metric Key Mapping — Heuristic Fallback Guide

> **Primary approach**: Use `lookupMetricKey(key, index)` from `scripts/migration-lookup.ts` with the pre-built `per-key-mappings.json` index to look up exact mappings from the authoritative JSON database (a large pre-built index of AWS and Azure metric key mappings (see `per-key-mappings.json` for current counts)). The rules below are **heuristic fallbacks** for metrics not found in the mapping database, and for GCP (mapping database not yet available).
>
> **REQUIRED:** Before applying heuristic rules below, check `manual-metric-mappings.json` for authoritative overrides for abbreviated and non-standard keys (e.g., `cloud.aws.alb.*`, `cloud.aws.eccustom.*`). If the key is present there, use that mapping and skip the heuristic rules.

Rules for translating classic cloud metric keys to their new connection equivalents when the exact mapping is not available in the JSON database.

---

## Table of Contents

- [1. Mapping Strategy](#1-mapping-strategy)
- [2. AWS Metric Key Migration](#2-aws-metric-key-migration)
- [3. Azure Metric Key Migration](#3-azure-metric-key-migration)
- [4. GCP Metric Key Migration](#4-gcp-metric-key-migration)
- [5. Discovery Queries](#5-discovery-queries)

---

## 1. Mapping Strategy

> **Terminology:** "Classic" in this guide refers to all pre-2024 cloud connection metric keys, including `builtin:` and `ext:` prefixed keys (sometimes called "Cassandra-era" keys). All refer to the same legacy system.

The primary mapping approach is the **authoritative JSON database** queried via `scripts/migration-lookup.ts` (`lookupMetricKey()`). When that returns no match, apply the heuristic rules below.

There is **no 1:1 rename** from classic to new metric keys. The metric key format, naming convention, and enrichment dimensions all change. The heuristic strategy is:

1. **Identify the classic prefix type** (built-in `dt.cloud.*`, non-built-in `cloud.*`, Cassandra-era `builtin:*` / `ext:*`)
2. **Apply the key format transformation** using the patterns below
3. **Discover the new metric key** by querying live metric data for the new connection (Section 5)
4. **Validate the new key produces data** for the same resources

### Key Format Differences

| Classic | New | Example |
|---|---|---|
| `dt.cloud.aws.<service>.<metric>` | `cloud.aws.<service>.<Metric>.By.<Dim>` | `dt.cloud.aws.ec2.cpu.usage` → `cloud.aws.ec2.CPUUtilization.By.InstanceId` |
| `cloud.aws.<service>.<snake_case>` | `cloud.aws.<service>.<PascalCase>.By.<Dim>` | `cloud.aws.lambda.concurrent_executions_sum` → `cloud.aws.lambda.ConcurrentExecutions.By.FunctionName` |
| `dt.cloud.azure.<service>.<metric>` | `cloud.azure.microsoft_<provider>.<resource>.<Metric>` | `dt.cloud.azure.vm.cpu_usage` → `cloud.azure.microsoft_compute.virtualmachines.PercentageCPU` |
| `cloud.gcp.<api>_googleapis_com.<path>` | `cloud.gcp.<resource>.<api>_googleapis_com.<path>` | `cloud.gcp.compute_googleapis_com.instance.cpu.utilization` → `cloud.gcp.gce_instance.compute_googleapis_com.instance.cpu.utilization` |

---

## 2. AWS Metric Key Migration

### Built-in → New Connection

Classic built-in (`dt.cloud.aws.*`) metric names are Dynatrace-curated short names. New connection uses CloudWatch original names (PascalCase) with `.By.` dimension separators.

**Lambda examples:**

| Classic (`dt.cloud.aws.`) | New Connection |
|---|---|
| `dt.cloud.aws.lambda.invocations` | `cloud.aws.lambda.Invocations.By.FunctionName` |
| `dt.cloud.aws.lambda.duration` | `cloud.aws.lambda.Duration.By.FunctionName` |
| `dt.cloud.aws.lambda.errors` | `cloud.aws.lambda.Errors.By.FunctionName` |
| `dt.cloud.aws.lambda.conc_executions` | `cloud.aws.lambda.ConcurrentExecutions.By.FunctionName` |
| `dt.cloud.aws.lambda.throttlers` | `cloud.aws.lambda.Throttles.By.FunctionName` |

**EC2 examples:**

| Classic (`dt.cloud.aws.`) | New Connection |
|---|---|
| `dt.cloud.aws.ec2.cpu.usage` | `cloud.aws.ec2.CPUUtilization.By.InstanceId` |
| `dt.cloud.aws.ec2.network.in` | `cloud.aws.ec2.NetworkIn.By.InstanceId` |
| `dt.cloud.aws.ec2.network.out` | `cloud.aws.ec2.NetworkOut.By.InstanceId` |
| `dt.cloud.aws.ec2.disk.read` | `cloud.aws.ec2.DiskReadBytes.By.InstanceId` |
| `dt.cloud.aws.ec2.disk.write` | `cloud.aws.ec2.DiskWriteBytes.By.InstanceId` |

**RDS examples:**

| Classic (`dt.cloud.aws.`) | New Connection |
|---|---|
| `dt.cloud.aws.rds.cpuUsage` | `cloud.aws.rds.CPUUtilization.By.DBInstanceIdentifier` |
| `dt.cloud.aws.rds.freeStorage` | `cloud.aws.rds.FreeStorageSpace.By.DBInstanceIdentifier` |
| `dt.cloud.aws.rds.readLatency` | `cloud.aws.rds.ReadLatency.By.DBInstanceIdentifier` |

### Non-Built-in (Classic) → New Connection

Classic non-built-in keys use snake_case; new connection uses PascalCase. The service segment is often the same.

| Classic non-built-in | New Connection |
|---|---|
| `cloud.aws.lambda.concurrent_executions_sum` | `cloud.aws.lambda.ConcurrentExecutions.By.FunctionName` |
| `cloud.aws.s3.number_of_objects_average` | *(discover via query — S3 metrics differ by filter)* |

### Cassandra-era Selectors

| Cassandra-era prefix | Grail equivalent | Then migrate to |
|---|---|---|
| `builtin:cloud.aws.<service>.*` | `dt.cloud.aws.<service>.*` | New connection key |
| `ext:cloud.aws.<service>.*` | `cloud.aws.<service>.*` | New connection key |

---

## 3. Azure Metric Key Migration

### Built-in → New Connection

Classic built-in (`dt.cloud.azure.*`) uses Dynatrace-curated names. New connection uses Azure Monitor original names.

**VM examples:**

| Classic (`dt.cloud.azure.`) | New Connection |
|---|---|
| `dt.cloud.azure.vm.cpu_usage` | `cloud.azure.microsoft_compute.virtualmachines.PercentageCPU` |
| `dt.cloud.azure.vm.disk.read` | `cloud.azure.microsoft_compute.virtualmachines.DiskReadBytes` |
| `dt.cloud.azure.vm.network.bytes_in` | `cloud.azure.microsoft_compute.virtualmachines.NetworkInTotal` |

**Redis examples:**

| Classic (`dt.cloud.azure.`) | New Connection |
|---|---|
| `dt.cloud.azure.redis.cache.hits` | `cloud.azure.microsoft_cache.redis.cachehits` |
| `dt.cloud.azure.redis.cache.misses` | `cloud.azure.microsoft_cache.redis.cachemisses` |
| `dt.cloud.azure.redis.connected` | `cloud.azure.microsoft_cache.redis.connectedclients` |

### Cloud Service (Classic) → New Connection

For Azure Cloud Services metrics: if the metric key matches the `cloud.azure.microsoft_*` pattern, the **key itself is identical** between classic and new connection — no metric key rewrite is needed. Distinguish which connection produced the data using `dt.da.source` (classic: null; new: `azure-metric-poller`).

---

## 4. GCP Metric Key Migration

GCP classic and new connection keys differ by an inserted resource type segment:

| Classic | New |
|---|---|
| `cloud.gcp.<api>_googleapis_com.<metric_path>` | `cloud.gcp.<resource_type>.<api>_googleapis_com.<metric_path>` |

**Examples:**

| Classic | New |
|---|---|
| `cloud.gcp.compute_googleapis_com.instance.cpu.utilization` | `cloud.gcp.gce_instance.compute_googleapis_com.instance.cpu.utilization` |
| `cloud.gcp.cloudsql_googleapis_com.database.cpu.utilization` | `cloud.gcp.cloudsql_database.cloudsql_googleapis_com.database.cpu.utilization` |
| `cloud.gcp.pubsub_googleapis_com.subscription.num_undelivered_messages` | `cloud.gcp.pubsub_subscription.pubsub_googleapis_com.subscription.num_undelivered_messages` |
| `cloud.gcp.storage_googleapis_com.storage.total_bytes` | `cloud.gcp.gcs_bucket.storage_googleapis_com.storage.total_bytes` |

---

## 5. Discovery Queries

When the exact new metric key is unknown, discover it from live data.

**Which query to run:**
- Know the service name → run query 1 (discover keys for a specific service)
- Have a classic key and want to validate the new equivalent has data → run query 2 (validate specific key)
- Results interpretation: each row is a candidate new metric key; pick the one whose dimensions match your use case

> **Note:** In the `dtctl query` examples below, inner quotes are escaped for the shell (`\"`). When running DQL directly, use standard double-quotes.

### Discover New AWS Metric Keys for a Service

```
dtctl query "fetch metric.series, from:now()-1h
| filter startsWith(metric.key, \"cloud.aws.<service>\") AND dt.da.source == \"aws-metric-poller\"
| summarize cnt=count(), by:{metric.key, dt.da.source, dt.smartscape_source.type}"
```

### Discover New Azure Metric Keys for a Service

```
dtctl query "fetch metric.series, from:now()-1h
| filter startsWith(metric.key, \"cloud.azure.microsoft_<provider>\") AND dt.da.source == \"azure-metric-poller\"
| summarize cnt=count(), by:{metric.key, dt.da.source, dt.smartscape_source.type}"
```

### Discover New GCP Metric Keys for a Service

```
dtctl query "fetch metric.series, from:now()-1h
| filter startsWith(metric.key, \"cloud.gcp.\") AND dt.da.source == \"gcp-cloud-monitoring\"
| summarize cnt=count(), by:{metric.key, dt.da.source, dt.smartscape_source.type}"
```

### Validate a Specific Metric Key Has Data

```
dtctl query "fetch metric.series, from:now()-1h
| filter metric.key == \"<new_metric_key>\"
| summarize cnt=count()"
```

---

If neither the mapping database, heuristic rules, nor live discovery query produces a match: mark the metric key as **non-migratable** in the assessment report. Flag it for manual review — it may be a decommissioned metric with no new-connection equivalent.
