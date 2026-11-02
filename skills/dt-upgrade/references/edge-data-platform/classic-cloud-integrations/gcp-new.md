# GCP New Connection Reference

Distilled reference for the new (Smartscape on Grail) GCP monitoring integration.

## Contents
- [Architecture](#architecture)
- [Entity Model](#entity-model)
- [Metric Key Format](#metric-key-format)
- [Key Detection Queries](#key-detection-queries)
- [Migration Mapping](#migration-mapping)
- [Migration Notes](#migration-notes)

---

## Architecture

| Property | Value |
|---|---|
| Settings schema | `builtin:hyperscaler-authentication.connections.gcp` |
| Data pipeline | Data Analytics pipeline (DA) |
| `dt.da.source` | `"gcp-cloud-monitoring"` |
| Entity model | Smartscape (new dedicated types) |
| Metric enrichment | Dimensions from Cloud Asset Inventory |
| Entity discovery | via Cloud Asset Inventory |

### Connection Discovery Query

```dtctl
dtctl get settings builtin:hyperscaler-authentication.connections.gcp
```

Or via DQL:

```dql
fetch dt.entity.GCP_CLOUDRESOURCEMANAGER_GOOGLEAPIS_COM_PROJECT
| fields entity.name, id, gcp_project_id
```

---

## Entity Model

GCP new integration creates **dedicated Smartscape entity types** per GCP resource type (no more CUSTOM_DEVICE).

### Key Entity Types

Entity type naming pattern: `GCP_<SERVICE>_GOOGLEAPIS_COM_<RESOURCE>`

| Entity type | GCP resource |
|---|---|
| `GCP_CLOUDRESOURCEMANAGER_GOOGLEAPIS_COM_PROJECT` | GCP Project root |
| `GCP_COMPUTE_GOOGLEAPIS_COM_INSTANCE` | Compute Engine VM |
| `GCP_SQLADMIN_GOOGLEAPIS_COM_INSTANCE` | Cloud SQL instance |
| `GCP_CLOUDFUNCTIONS_GOOGLEAPIS_COM_FUNCTION` | Cloud Function |
| `GCP_RUN_GOOGLEAPIS_COM_SERVICE` | Cloud Run service |
| `GCP_STORAGE_GOOGLEAPIS_COM_BUCKET` | Cloud Storage bucket |
| `GCP_CONTAINER_GOOGLEAPIS_COM_CLUSTER` | GKE Cluster |
| `GCP_CONTAINER_GOOGLEAPIS_COM_NODE` | GKE Node |
| `GCP_PUBSUB_GOOGLEAPIS_COM_SUBSCRIPTION` | Pub/Sub Subscription |
| `GCP_PUBSUB_GOOGLEAPIS_COM_TOPIC` | Pub/Sub Topic |
| `GCP_REDIS_GOOGLEAPIS_COM_INSTANCE` | Memorystore Redis |
| `GCP_SPANNER_GOOGLEAPIS_COM_INSTANCE` | Spanner Instance |

### Entity Attributes

- **`project_id`** — GCP project ID
- **`zone`** (if zonal)
- **`region`** (if regional)
- **Standard Smartscape attributes** — `entity.name`, `lifetime`, `tags`

---

## Metric Key Format

```
cloud.gcp.<resource_type>.<google_api_service>.<metric_path>
```

Key difference from classic: the **resource type** is inserted as the 3rd segment.

### Examples

| Service | Example metric key |
|---|---|
| Compute Engine | `cloud.gcp.gce_instance.compute_googleapis_com.instance.cpu.utilization` |
| Cloud SQL | `cloud.gcp.cloudsql_database.cloudsql_googleapis_com.database.cpu.utilization` |
| Pub/Sub | `cloud.gcp.pubsub_subscription.pubsub_googleapis_com.subscription.num_undelivered_messages` |
| Cloud Functions | `cloud.gcp.cloud_function.cloudfunctions_googleapis_com.function.execution_count` |

> **Disambiguation**: the 3rd segment (`<resource_type>`) is a lowercase resource name in classic metrics (e.g., `compute_googleapis_com`) but in new metrics the 3rd segment is a resource type (e.g., `gce_instance`), followed by the API domain in the 4th segment.

---

## Key Detection Queries

### Enumerate new GCP projects
```dql
fetch dt.entity.GCP_CLOUDRESOURCEMANAGER_GOOGLEAPIS_COM_PROJECT
| fields entity.name, id
```

### New metric source classification
```dql
fetch metric.series, from:now()-1h
| filter contains(metric.key, "cloud.gcp")
| filter dt.da.source == "gcp-cloud-monitoring"
| summarize cnt=count(), by:{metric.key}
| sort cnt desc
| limit 50
```

### New entity type inventory
```dql
smartscapeNodes "*"
| filter matchesPhrase(entity.type, "GCP_")
| summarize cnt=count(), by:{entity.type}
| sort cnt desc
```

---

## Migration Mapping

### Entity Mapping (Classic → New)

See [entity-type-mapping.md](entity-type-mapping.md) for the full table.

All classic GCP entities are `CUSTOM_DEVICE` with `cloud:gcp:*` sub-types. Each maps to a dedicated Smartscape type:

| Classic sub-type | New entity type |
|---|---|
| `cloud:gcp:gce_instance` | `GCP_COMPUTE_GOOGLEAPIS_COM_INSTANCE` |
| `cloud:gcp:cloudsql_database` | `GCP_SQLADMIN_GOOGLEAPIS_COM_INSTANCE` |
| `cloud:gcp:cloud_function` | `GCP_CLOUDFUNCTIONS_GOOGLEAPIS_COM_FUNCTION` |
| `cloud:gcp:gcs_bucket` | `GCP_STORAGE_GOOGLEAPIS_COM_BUCKET` |
| `cloud:gcp:k8s_cluster` | `GCP_CONTAINER_GOOGLEAPIS_COM_CLUSTER` |
| `cloud:gcp:pubsub_topic` | `GCP_PUBSUB_GOOGLEAPIS_COM_TOPIC` |

### Metric Mapping

Same prefix (`cloud.gcp.`), but new format inserts resource type as 3rd segment:

```
Classic: cloud.gcp.<api_domain>.<path>
New:     cloud.gcp.<resource_type>.<api_domain>.<path>
```

---

## Migration Notes

- **No Metric Streams** — GCP does not have a Metric Streams analogue. No blocking mechanism.
- **All classic entities are CUSTOM_DEVICE** — migration impact is typically larger than AWS/Azure since every entity type changes.
- **Settings-based configuration** — new connections are managed via Settings 2.0, unlike the classic GKE deployment.
- **Project as root** — `GCP_CLOUDRESOURCEMANAGER_GOOGLEAPIS_COM_PROJECT` replaces `cloud:gcp:project` as the root entity.
- **OneAgent types unchanged** — `GOOGLE_COMPUTE_ENGINE` and `GCP_ZONE` are unaffected by migration.
