# Disambiguation: Classic vs New Connection Metrics

How to distinguish classic connection metrics from new connection metrics when they share the same metric key prefix.

---

## Table of Contents

- [1. The Problem](#1-the-problem)
- [2. The Universal Rule](#2-the-universal-rule)
- [3. AWS Disambiguation](#3-aws-disambiguation)
- [4. Azure Disambiguation](#4-azure-disambiguation)
- [5. GCP Disambiguation](#5-gcp-disambiguation)
- [6. Static Text Scanning](#6-static-text-scanning)

---

## 1. The Problem

Classic and new connections share overlapping metric key prefixes:

| Shared prefix | Classic source | New source |
|---|---|---|
| `cloud.aws.<service>.*` | Non-built-in classic polling | New AWS connection |
| `cloud.azure.microsoft_*` | Classic cloud services | New Azure connection |
| `cloud.gcp.*` | Classic GKE integration | New GCP connection |

When scanning live metric data, these can be distinguished via metadata dimensions. When scanning static text (dashboard DQL, SLO expressions), only key format patterns are available.

---

## 2. The Universal Rule

> **`dt.da.source` is the definitive discriminator.** Classic connections NEVER set `dt.da.source`. Any non-null `dt.da.source` value originates from the new connection.

| `dt.da.source` value | Connection |
|---|---|
| `aws-metric-poller` | New AWS |
| `azure-metric-poller` | New Azure |
| `gcp-cloud-monitoring` | New GCP |
| `(null)` | Classic (any provider) |

Additional new-connection-only dimensions:
- `dt.smartscape_source.type` — Smartscape entity type (e.g., `AWS_EC2_INSTANCE`)
- `dt.smartscape_source.id` — Smartscape entity ID

Additional classic-only dimensions:
- `dt.source_entity.type` — classic entity type (e.g., `ec2_instance`, `cloud:aws:rds`)
- `dt.source` — `"AWS Metric Streams"` for Metric Streams, `"com.dynatrace.gcp"` for classic GCP

---

## 3. AWS Disambiguation

### `cloud.aws.*` prefix — shared between classic non-built-in and new connection

**Live data query:**

```dql
fetch metric.series, from:now()-1h
| filter startsWith(metric.key, "cloud.aws.")
| summarize cnt=count(), by:{dt.da.source, dt.source_entity.type, dt.source}
| sort cnt desc
```

| Dimension | Classic | New |
|---|---|---|
| `dt.da.source` | null | `aws-metric-poller` |
| `dt.source_entity.type` | Present (e.g., `cloud:aws:rds`, `ec2_instance`) | null |
| `dt.smartscape_source.type` | null | Present (e.g., `AWS_EC2_INSTANCE`) |
| `dt.source` | `"AWS Metric Streams"` (if applicable) | null |

**Static text (metric key format):**

| Pattern | Connection |
|---|---|
| `cloud.aws.<service>.<snake_case_metric>` | Classic non-built-in |
| `cloud.aws.<service>.<PascalCase>.By.<Dim>` | New connection |

Regex for classic: `/cloud\.aws\.[a-z0-9_]+\.[a-z][a-z0-9_]*/`

### Definitive classic prefixes (no ambiguity)

- `dt.cloud.aws.*` — always classic built-in
- `builtin:cloud.aws.*` — always classic (Cassandra-era)
- `ext:cloud.aws.*` — always classic (Cassandra-era)

---

## 4. Azure Disambiguation

### `cloud.azure.microsoft_*` prefix — shared between classic cloud services and new connection

**Live data query:**

```dql
fetch metric.series, from:now()-1h
| filter startsWith(metric.key, "cloud.azure.")
| summarize cnt=count(), by:{dt.da.source, dt.source_entity.type}
| sort cnt desc
```

| Dimension | Classic | New |
|---|---|---|
| `dt.da.source` | null | `azure-metric-poller` |
| `dt.source_entity.type` | Present (e.g., `cloud:azure:cache:redis`, `azure_vm`) | null |
| `dt.smartscape_source.type` | null | Present (e.g., `AZURE_MICROSOFT_CACHE_REDIS`) |
| `azure.resource.type` | null | Present (e.g., `microsoft.cache/redis`) |

**Static text**: No reliable key-format pattern to distinguish. Flag `cloud.azure.microsoft_*` as **ambiguous** and recommend live data inspection.

### Definitive classic prefixes (no ambiguity)

- `dt.cloud.azure.*` — always classic built-in
- `builtin:cloud.azure.*` — always classic (Cassandra-era)
- `ext:cloud.azure.*` — always classic (Cassandra-era)

---

## 5. GCP Disambiguation

### `cloud.gcp.*` prefix — classic and new use different patterns

**Live data query:**

```dql
fetch metric.series, from:now()-1h
| filter startsWith(metric.key, "cloud.gcp.")
| filterOut startsWith(metric.key, "dac.gcp_")
| filterOut startsWith(metric.key, "dt.sfm.da.gcp")
| summarize cnt=count(), by:{dt.da.source, dt.source, metadata.origin}
| sort cnt desc
```

| Dimension | Classic | New |
|---|---|---|
| `dt.da.source` | null | `gcp-cloud-monitoring` |
| `dt.source` | `com.dynatrace.gcp` or null | null |
| `metadata.origin` | `extension` or null | null |

**Static text (metric key format):**

| Pattern | Connection |
|---|---|
| `cloud.gcp.<api>_googleapis_com.<path>` | Classic (2nd segment = API domain) |
| `cloud.gcp.<resource_type>.<api>_googleapis_com.<path>` | New (2nd segment = resource type, 3rd = API domain) |

Regex for classic: `/cloud\.gcp\.[a-z0-9]+_googleapis_com\./`

### Definitive classic prefixes (no ambiguity)

- `builtin:cloud.gcp.*` — always classic (Cassandra-era)

> GCP has no `dt.cloud.gcp.*` prefix — all classic GCP metrics use `cloud.gcp.*`.

---

## 6. Static Text Scanning

When scanning dashboards, SLOs, or alerts where you only have the text (no live dimensions), use this decision tree:

1. `dt.cloud.aws.*` / `dt.cloud.azure.*` → **definitive classic**
2. `builtin:cloud.*` / `ext:cloud.*` → **definitive classic**
3. `cloud.aws.<service>.<snake_case>` → **classic** (apply regex)
4. `cloud.gcp.<api>_googleapis_com.*` → **classic** (apply regex)
5. `cloud.azure.microsoft_*` → **ambiguous** — flag for review
6. `fetch dt.entity.<cloud_type>` → **definitive classic**
7. `smartscapeNodes <TYPE>` → **definitive new**
