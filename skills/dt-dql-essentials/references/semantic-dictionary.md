# Dynatrace Semantic Dictionary

Standardized field names used across logs, events, spans, metrics, and entities in Grail. Fields are organized by `namespace.sub_namespace.field_name` (e.g., `http.request.method`, `k8s.namespace.name`).

## IMPORTANT: Fetching Complete Field Lists

### The `dt.semantic_dictionary.fields` Table

The Semantic Dictionary is itself queryable as a Grail table: `dt.semantic_dictionary.fields`. Each row describes one field definition. The table exposes these columns:

| Column | Type | Description |
|--------|------|-------------|
| `name` | string | The fully qualified field name (e.g., `service.name`, `k8s.pod.uid`) |
| `type` | string[] | May either be a `string[]` (simple types are single-element arrays (e.g. `["string"]`, `["long"]`, `["boolean"]`, `["timestamp"]`, `["uid"]`, `["ipAddress"]`, etc.); array variants add `[]` to the element (e.g. `["string[]"]`); combined same-type fields yield multi-element arrays (e.g. `["string", "string[]"]`)) or for enum fields a nested object instead. |
| `stability` | string | The stability level: `stable`, `experimental`, or `deprecated` |
| `description` | string | Human-readable description of what the field represents |
| `tags` | string[] | Semantic tags assigned to the field (e.g., `entity-id`, `permission`, `primary-field`, `smartscape-id`, `sensitive-spans`, `sensitive-user-events`) |
| `unit` | string | The unit of measurement for the field (e.g., `kBy`, `zl`); null when no unit applies |
| `supported_values` | string[] | Enumerated set of allowed values for fields with a fixed value set (e.g., `span.kind` supports `internal`, `server`, `client`, `producer`, `consumer`) |
| `examples` | string[] | Example values illustrating typical field content (e.g., `"Rome"` for `actor.geo.city.name`) |
| `model_id` | string | The model this field belongs to; `null` for global fields that apply across all models |
| `is_resource` | boolean | Whether this field is a resource attribute |

To list only global fields. Global fields maintain consistent semantics across the entire Grail product, offering standardized data references.

```dql
fetch dt.semantic_dictionary.fields
| filter isNull(model_id)
| dedup name
```

### The `dt.semantic_dictionary.models` Table

Data models describe predefined schemas for Grail data objects — which fields belong together and how they map to Grail tables. Each row represents one model definition. The table exposes these columns:

| Column                 | Type | Description |
|------------------------|------|-------------|
| `name`                 | string | The model name (e.g., `audit_event`, `bizevents`, `dt.smartscape.host`) |
| `display_name`         | string | Human-readable display name for the model |
| `description`          | string | Human-readable description of what the model represents |
| `data_object`          | string | The Grail table this model maps to (e.g., `spans`, `logs`, `events`, `smartscape.nodes`, `dt.system.events`) |
| `fields`               | string[] | Ordered list of field names that belong to this model |
| `relationships`        | string[] | Entity relationships (e.g., `uses[dt.smartscape.aws_s3_bucket]`, `runs_on[dt.entity.host]`) |
| `smartscape_node_name` | string | The field used as display name for Smartscape nodes (e.g., `aws.resource.name`, `k8s.cluster.name`); null for non-entity models |
| `smartscape_node_type` | string | The Smartscape entity type for this model (e.g., `dt.smartscape.host`, `dt.smartscape.service`); null for non-entity models |
| `smartscape_id_inputs` | string[] | Fields used to compute the Smartscape entity ID for this model; null for non-entity models |
| `classic_models` | string[] | Classic models associated with this model |


### Namespace Lookup Queries

**For every namespace referenced in this skill, the fields listed here are only the most commonly used ones.** The Semantic Dictionary contains many more fields per namespace. To get the **complete and up-to-date list** of all fields in any namespace, always run:

```dql
fetch dt.semantic_dictionary.fields
| filter startsWith(name, "<namespace_prefix>.")
| dedup name
```

Replace `<namespace_prefix>` with the target namespace (e.g., `aws`, `azure`, `k8s`, `http`, `db`, `dt.rum`, etc.).

Many namespaces have **sub-namespaces** (e.g., `k8s.pod.*`, `http.request.*`). Drill into them with the same pattern: `filter startsWith(name, "k8s.pod.")`. **Always use these queries** to discover fields beyond what is listed below.

### Model Lookup Queries

To find all fields belonging to a **specific model** (using `model_id` on `dt.semantic_dictionary.fields`):
`model_id` on `dt.semantic_dictionary.fields` equals the `name` column on `dt.semantic_dictionary.models` (e.g., `"audit_event"`, `"bizevents"`, `"dt.smartscape.host"`).

```dql
fetch dt.semantic_dictionary.fields
| filter model_id == "<model_id>"
| dedup name
```

To find all models for a specific Grail data object:

```dql
fetch dt.semantic_dictionary.models
| filter data_object == "spans"
```

To find a model by name and see its fields:

```dql
fetch dt.semantic_dictionary.models
| filter name == "audit_event"
```

To list all Grail data objects that have models defined:

```dql
fetch dt.semantic_dictionary.models
| summarize modelCount = count(), by: {data_object}
| sort modelCount desc
```

## Stability Levels

| Level | Meaning |
|---|---|
| `stable` | Safe for production; will not change without notice |
| `experimental` | May change or be removed; use with caution |
| `deprecated` | Avoid; migrate to alternative fields |

## Global Field Namespaces

### Top-Level Fields

Core fields available across all data types:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `timestamp` | timestamp | Point in time when the data point occurred | 1649822520123123165 |
| `start_time` | timestamp | Start time of a data point (UNIX Epoch in nanoseconds) | 1649822520123123165 |
| `end_time` | timestamp | End time of a data point (greater than or equal to start_time) | 1649822520123123165 |
| `duration` | duration | Difference between start_time and end_time in nanoseconds | 42 |
| `interval` | string | Timeframe represented by individual timeseries measurements | 1 min |

### Service Fields (service.*)

> **Gotcha**: `service.name` is a **resource attribute** on spans — do not confuse with `k8s.service.name` (Kubernetes Service) or `dt.smartscape.service` (Dynatrace Smartscape ID).

### Cloud Provider Fields

#### AWS (aws.*)

> See the `dt-obs-aws` skill for AWS field reference.

#### Azure (azure.*)

Key Azure fields:
- `azure.subscription` - Azure subscription ID (stable, primary-field, permission)
- `azure.location` - Geographical location (stable, primary-field)
- `azure.resource.group` - Resource group name (stable, primary-field, permission)
- `azure.resource.id` - Unique immutable identifier for the Azure resource (experimental)
- `azure.tenant.id` - Azure tenant identifier (experimental)
- `azure.vm.name` - Virtual machine name (experimental)
- `azure.tags.__tag_key__` - Azure tag values (experimental)

#### GCP (gcp.*)

Key GCP fields:
- `gcp.project.id` - GCP project identifier (stable, primary-field)
- `gcp.region` - GCP region (stable, primary-field)
- `gcp.zone` - Subset of a region (stable)
- `gcp.instance.id` - Unique numeric identifier (experimental)
- `gcp.resource.name` - Globally unique resource name (stable)
- `gcp.user_labels.__label__` - User labels (experimental)

### Kubernetes Fields (k8s.*)

> See the `dt-obs-kubernetes` skill and its `references/labels-annotations.md` for K8s field reference.

### Database Fields (db.*)

> See `dt-app-tracing/references/database-spans.md` for database field reference.

### URL Fields (url.*)

- `url.full`, `url.scheme`, `url.path`, `url.query` (sensitive), `url.fragment` — all stable
- `url.domain`, `url.path.pattern`, `url.port` — experimental

### Trace Fields (trace.*)

- `trace.id` - Unique trace identifier (16-byte, hex-encoded) (stable)
- `trace.state` - W3C trace context format state (experimental)
- `trace.is_sampled` - Sampling indicator (experimental)

### Log Fields (log.*)

Global `log.*` fields (not documented in other skills):
- `log.source` - Human-readable log stream identifier (stable, permission)
- `log.iostream` - I/O stream: `stdout`, `stderr` (stable)
- `log.file.name` - Basename of the log file (experimental)
- `log.file.path` - Full path to the log file (experimental)
- `log.logger` - Logger name inside the application (experimental)
- `log.raw_level` - Original severity level before standardization (experimental)

### Other Global Namespaces

The following namespaces follow standard conventions. Query `dt.semantic_dictionary.fields` for full field lists:

- `user.*` — `user.id` (stable), `user.email` (stable), `user.name`, `user.organization`
- `geo.*` — `geo.country.name`, `geo.city.name`, `geo.region.name` (stable); `geo.location.latitude/longitude` (sensitive)
- `network.*` — `network.transport` (`tcp`/`udp`), `network.type` (`ipv4`/`ipv6`), `network.peer.ip/port`
- `client.*` / `server.*` — `client.address`, `client.ip` (sensitive), `client.port`; `server.address`, `server.port`
- `container.*` — `container.id`, `container.name`, `container.image.name`, `container.image.version`
- `process.*` — `process.executable.name`, `process.executable.path`, `process.pid`
- `messaging.*` — see `dt-app-tracing/references/messaging-spans.md`
- `browser.*` — see `dt-app-frontend`
- `audit.*` — `audit.action`, `audit.identity`, `audit.result`, `audit.status` (all stable)

## Dynatrace-Specific Fields

### Smartscape IDs (dt.smartscape.*)

Entity ID format: `PREFIX-0123456789ABCDEF`

Common entity types:
- `dt.smartscape.host` - Host entity
- `dt.smartscape.service` - Service entity
- `dt.smartscape.process` - Process
- `dt.smartscape.frontend` - Web or mobile frontend
- `dt.smartscape.k8s_cluster` - K8s cluster
- `dt.smartscape.k8s_deployment` - K8s deployment

Legacy note: `dt.entity.*` field names are deprecated aliases in older content. Prefer `dt.smartscape.*` in all new queries and examples.

### Legacy Mapping (dt.entity.* → dt.smartscape.*)

| Deprecated field | Preferred field |
|---|---|
| `dt.entity.host` | `dt.smartscape.host` |
| `dt.entity.service` | `dt.smartscape.service` |
| `dt.entity.process_group_instance` | `dt.smartscape.process` |
| `dt.entity.kubernetes_cluster` | `dt.smartscape.k8s_cluster` |
| `dt.entity.cloud_application_instance` | `dt.smartscape.k8s_pod` |

> See the `dt-migration` skill for complete entity type mapping.

### Dynatrace System Fields (dt.system.*)

Automatically set by Grail, cannot be ingested.

Key system fields:
- `dt.system.bucket` - Grail bucket name (stable)
- `dt.system.table` - Table name (stable)
- `dt.system.environment` - Dynatrace environment (stable)
- `dt.system.segment_id` - Segment identifier (stable)
- `dt.system.monitoring_source` - License type (stable)

### Dynatrace Metadata Fields (dt.*)

Key metadata fields:
- `dt.host_group.id` - Host group name (stable, primary-field)
- `dt.security_context` - Security context for permissions (stable, permission)
- `dt.source_entity` - Source entity IDs (**deprecated** — use `dt.smartscape_source.id` instead; will be removed in the future)
- `dt.source_entity.type` - Source entity type (**deprecated** — use `dt.smartscape_source.type` instead; will be removed in the future)
- `dt.cost.costcenter` - Cost center assignment (stable)
- `dt.cost.product` - Product/application assignment (stable)

### RUM Fields (dt.rum.*)

> See the `dt-app-frontend` skill for RUM field reference.

## Primary Grail Tags

Customer-selected tags automatically attached to raw telemetry. Format: `primary_tags.__key__` (e.g., `primary_tags.ownership`, `primary_tags.cost_center`, `primary_tags.environment`).

## Grail Special Field Tags

- **`permission`** — affects data access: `event.kind`, `event.type`, `event.provider`, `dt.security_context`
- **`primary-field`** — key organizational attributes: `aws.account.id`, `azure.subscription`, `k8s.cluster.name`, `k8s.namespace.name`
- **`sensitive-spans`** — `client.ip`, `db.connection_string`, `db.query.parameters`, `url.query`
- **`sensitive-user-events`** — `client.ip`, `geo.location.latitude`, `geo.location.longitude`

## Resources

- [Semantic Dictionary Overview](https://docs.dynatrace.com/docs/semantic-dictionary)
- [Global Field Reference](https://docs.dynatrace.com/docs/semantic-dictionary/fields)
- [Data Models](https://docs.dynatrace.com/docs/semantic-dictionary/model)
- [Grail Special Fields](https://docs.dynatrace.com/docs/semantic-dictionary/tags)
- [Versions & Changelog](https://docs.dynatrace.com/docs/semantic-dictionary/versions)