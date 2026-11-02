# GCP Classic Connection Reference

Distilled reference for the classic GCP monitoring integration.

## Contents
- [Architecture](#architecture)
- [Entity Model](#entity-model)
- [Metric Key Format](#metric-key-format)
- [Key Detection Queries](#key-detection-queries)
- [Key Differences from AWS and Azure](#key-differences-from-aws-and-azure)
- [Disambiguation](#disambiguation)

---

## Architecture

Unlike AWS and Azure, the classic GCP integration is fundamentally different:

| Property | Value |
|---|---|
| Deployment | **Self-hosted GKE workload** (not ActiveGate, not Settings) |
| Configuration | Kubernetes manifests / Helm chart |
| Settings schema | **None** — no `builtin:cloud.gcp` exists |
| Metric ingestion | Metrics API v2 (push from GKE to Dynatrace) |
| Entity creation | Custom Device API (topology) |
| `dt.source` | `"com.dynatrace.gcp"` (on some metrics) |
| `metadata.origin` | `"extension"` |
| `dt.da.source` | null (never set by classic) |

---

## Entity Model

**All** classic GCP entities are `CUSTOM_DEVICE` with `cloud:gcp:*` sub-types. There are NO dedicated classic entity types for GCP (unlike AWS's `EC2_INSTANCE` or Azure's `AZURE_VM`).

### Common Entity Types

`cloud:gcp:gce_instance`, `cloud:gcp:cloudsql_database`, `cloud:gcp:cloud_function`, `cloud:gcp:cloud_run_revision`, `cloud:gcp:gcs_bucket`, `cloud:gcp:k8s_cluster`, `cloud:gcp:k8s_node`, `cloud:gcp:k8s_pod`, `cloud:gcp:k8s_container`, `cloud:gcp:pubsub_topic`, `cloud:gcp:pubsub_subscription`, `cloud:gcp:spanner_instance`, `cloud:gcp:redis_instance`, `cloud:gcp:https_lb`, `cloud:gcp:nat_gateway`, `cloud:gcp:cloud_tasks_queue`, `cloud:gcp:cloud_composer_environment`

Parent: `cloud:gcp:project` — represents a GCP project.

### OneAgent Entities (Separate)

`GOOGLE_COMPUTE_ENGINE` and `GCP_ZONE` are created by OneAgent on GCE VMs, NOT by the GCP integration.

---

## Metric Key Format

```
cloud.gcp.<google_api_service>.<metric_path>
```

- `<google_api_service>` — API domain with dots → underscores (e.g., `compute_googleapis_com`)
- `<metric_path>` — API path with slashes → dots (e.g., `instance.cpu.utilization`)

> **No `dt.cloud.gcp.*` prefix exists.** All classic GCP metrics use `cloud.gcp.*`.

### Examples

| Service | Example metric key |
|---|---|
| Compute Engine | `cloud.gcp.compute_googleapis_com.instance.cpu.utilization` |
| Cloud SQL | `cloud.gcp.cloudsql_googleapis_com.database.cpu.utilization` |
| Pub/Sub | `cloud.gcp.pubsub_googleapis_com.subscription.num_undelivered_messages` |
| Cloud Functions | `cloud.gcp.cloudfunctions_googleapis_com.function.execution_count` |
| Cloud Storage | `cloud.gcp.storage_googleapis_com.storage.total_bytes` |

---

## Key Detection Queries

### Enumerate classic projects
```dql
fetch `dt.entity.cloud:gcp:project`, from:now()-12h
| fields entity.name, id, lifetime
```

(`entity.name` IS the GCP project ID)

### Custom device type counts
```dql
fetch dt.entity.custom_device
| filter contains(toString(entity.type), "cloud:gcp")
| summarize cnt=count(), by:{entity.type}
| sort cnt desc
```

### Classic metric source classification
```dql
fetch metric.series, from:now()-1h
| filter contains(metric.key, "cloud.gcp")
| filterOut startsWith(metric.key, "dac.gcp_")
| filterOut startsWith(metric.key, "dt.sfm.da.gcp")
| summarize cnt=count(), by:{dt.da.source, dt.source, metadata.origin}
| sort cnt desc
```

---

## Key Differences from AWS and Azure

- **No Settings schema** — detection relies entirely on entity and metric queries.
- **No built-in entity types** — everything is `CUSTOM_DEVICE`.
- **No `dt.cloud.gcp.*` prefix** — no Dynatrace-curated metric names.
- **No Metric Streams** — no push-based variant.
- **GKE deployment** — requires customer infrastructure, not platform-managed.

---

## Disambiguation

Classic: `cloud.gcp.<api>_googleapis_com.<path>` (2nd segment = API domain)
New: `cloud.gcp.<resource_type>.<api>_googleapis_com.<path>` (2nd segment = resource type)

Regex for classic: `/cloud\.gcp\.[a-z0-9]+_googleapis_com\./`

See [disambiguation.md](disambiguation.md) for the full decision tree.
