# Cost Allocation & Chargeback

Querying billing events for cost center and product attribution, building
chargeback and showback reports.

## Contents

- [Entity Attribution Fields](#entity-attribution-fields)
- [Cost Attribution Fields](#cost-attribution-fields)
- [Field Type by Event Type](#field-type-by-event-type)
- [Chargeback Queries](#chargeback-queries)
  - [String-Type Cost Attribution](#string-type-cost-attribution)
  - [Record-Type Cost Attribution](#record-type-cost-attribution)
  - [Unified Chargeback (All Types)](#unified-chargeback-all-types)

## Entity Attribution Fields

Billing events carry entity and measurement window references that vary by
event type:

| Field | Type | Description |
|-------|------|-------------|
| `dt.entity.host` | string | Host entity ID (Host Monitoring, Security) |
| `dt.entity.application` | string | Application entity ID (RUM) |
| `dt.entity.kubernetes_cluster` | string | K8s cluster entity ID (K8s Platform Monitoring, SPM) |
| `dt.entity.synthetic_test` | string | Synthetic test entity ID (Browser Monitor) |
| `dt.entity.http_check` | string | HTTP check entity ID (HTTP Monitor — NOT `dt.entity.synthetic_test`) |
| `usage.start` / `usage.end` | timestamp | Measurement time window (typically 15 min) |
| `usage.bucket` | string | Grail bucket name for ingest/query/retain events |

> **Entity attribution varies by event type.** Retention events often lack
> entity references. Not all fields are present on all event types — check
> [billing-event-types.md](billing-event-types.md) for per-type field details.

## Cost Attribution Fields

Two fields carry cost allocation data on billing events:

| Field | Description |
|-------|-------------|
| `dt.cost.costcenter` | Cost center tag assigned to the monitored entity |
| `dt.cost.product` | Product tag assigned to the monitored entity |

These fields are **only populated when cost attribution tags are configured** on
monitored entities. Not all event types support them.

> **Important:** Dynatrace does not officially support querying `dt.cost.costcenter`
> and `dt.cost.product` together in the same aggregation. All built-in billing
> automation treats these two dimensions separately. Build chargeback queries
> against one dimension at a time.

## Why String vs Record[]

The type of `dt.cost.costcenter` / `dt.cost.product` depends on how the billing
system produces events for each capability:

- **String type** — Used when each billing event maps to a single entity (e.g.,
  one Full-Stack host, one Infrastructure host) so the cost center is simply the
  tag value from that entity. Also used for aggregated capabilities like Log
  Ingest and Traces Ingest where the system splits usage by cost center
  **before** writing the billing events.

- **Record[] type** — Used when technical limitations prevent pre-splitting
  usage by cost center. For Metrics Ingest and Log/Metrics Retain, a single
  billing event aggregates across many entities. The cost center breakdown must
  be embedded as an array of `{key, billed_amount}` records within each event.
  Queries must use `expand` to unnest these records before aggregation.

- **Not present** — Event types that have no entity relationship (query events,
  automation events) or where cost attribution is not applicable (RUM, synthetic,
  K8s).

## Field Type by Event Type

The type of `dt.cost.costcenter` and `dt.cost.product` varies:

### String type

Simple string values (e.g., `"quality-assurance/QA"`, `"stock-market-app"`):

- Full-Stack Monitoring
- Infrastructure Monitoring
- Foundation & Discovery
- Code Monitoring
- Data Egress
- Log Management & Analytics - Ingest & Process
- Traces - Ingest & Process
- Runtime Application Protection
- Runtime Vulnerability Analytics

### Record[] type

Array of records, each containing a `key` (cost center/product name or
`"unassigned"`) and a billed quantity field:

| Event Type | Record Structure |
|------------|-----------------|
| `Log Management & Analytics - Retain` | `{key: string, billed_bytes: long}` |
| `Log Management & Analytics - Retain with Included Queries` | `{key: string, billed_bytes: long}` |
| `Metrics - Ingest & Process` | `{key: string, data_points: long}` |

### Not present

These event types do **not** have cost attribution fields:

- All Query events (Traces, Logs, Events, Files, DEM)
- All RUM events
- Synthetic monitoring events
- Kubernetes Platform Monitoring
- Automation Workflow, AppEngine Functions
- Events Ingest/Retain, Files Ingest/Query/Retain
- Security Posture Management

## Chargeback Queries

### String-Type Cost Attribution

For event types where `dt.cost.costcenter` is a string, filter and group
directly:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Full-Stack Monitoring"
| filter isNotNull(dt.cost.costcenter)
| dedup event.id
| summarize total_gib_hours = sum(billed_gibibyte_hours),
    by: {dt.cost.costcenter}
| sort total_gib_hours desc
```

Infrastructure Monitoring by cost center (host-hours):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Infrastructure Monitoring"
| filter isNotNull(dt.cost.costcenter)
| dedup event.id
| summarize total_host_hours = sum(billed_host_hours),
    by: {dt.cost.costcenter}
| sort total_host_hours desc
```

Log ingest by cost center (GiB):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Log Management & Analytics - Ingest & Process"
| filter isNotNull(dt.cost.costcenter)
| dedup event.id
| summarize total_gib = sum(billed_bytes) / 1073741824,
    by: {dt.cost.costcenter}
| sort total_gib desc
```

### Record-Type Cost Attribution

For event types where `dt.cost.costcenter` is `record[]`, use `expand` to
unnest records and index into the record fields:

Metrics ingest by cost center (data points):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Metrics - Ingest & Process"
| dedup event.id
| expand dt.cost.costcenter
| summarize total_data_points = sum(dt.cost.costcenter[data_points]),
    by: {costcenter = dt.cost.costcenter[key]}
| sort total_data_points desc
```

Log retention by cost center (GiB):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Log Management & Analytics - Retain"
| dedup event.id
| expand dt.cost.costcenter
| summarize total_gib = sum(dt.cost.costcenter[billed_bytes]) / 1073741824,
    by: {costcenter = dt.cost.costcenter[key]}
| sort total_gib desc
```

### Unified Chargeback (All Types)

Single query handling both string and record[] cost center types. Works by
exploiting DQL behavior: `expand` on a string is a no-op, and `coalesce`
falls through to extract the right value for each type.

Pattern:
1. Normalize usage via the `coalesce()` snippet from
   [cost-estimations.md § Cost Estimation Pattern](cost-estimations.md#cost-estimation-pattern)
2. `expand c=dt.cost.costcenter` — unnests record[], no-op for strings
3. `coalesce(c[key], c)` — extracts key from records, uses string directly
4. `coalesce(toDouble(c[data_points]), toDouble(c[billed_bytes]), usage)` —
   picks the record value field or falls back to top-level usage

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter isNotNull(dt.cost.costcenter)
| dedup event.id
| fieldsAdd usage = coalesce(
    billed_gibibyte_hours,
    billed_host_hours,
    billed_msu_hours,
    billed_container_hours,
    toDouble(billed_bytes) / 1073741824,
    billed_sessions,
    billed_replay_sessions,
    billed_property_sessions,
    billed_pod_hours,
    billed_synthetic_action_count,
    billed_http_request_count,
    billed_test_result_ingestion_count,
    billed_invocations,
    data_points,
    toDouble(ingested_bytes) / 1073741824)
| expand c = dt.cost.costcenter
| fieldsAdd
    cc = coalesce(c[key], c),
    v = coalesce(toDouble(c[data_points]), toDouble(c[billed_bytes]), usage)
| summarize by: {event.type, dt.cost.costcenter = cc}, usage = sum(v)
| sort event.type, dt.cost.costcenter
```

> **Caution:** Usage values are in **native units** (data points, bytes,
> host-hours, GiB-hours) which differ per event type. Do not sum `usage` across
> event types without DPS conversion. Use
> [cost-estimations.md](cost-estimations.md) for cross-type cost comparison.
