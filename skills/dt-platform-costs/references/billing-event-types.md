# Billing Event Types

Complete catalog of Dynatrace billing event types available in
`dt.system.events` with `event.kind == "BILLING_USAGE_EVENT"`.

> **Important:** Not all event types are active in every environment. Run the
> discovery query below to see what is available in yours.

## Contents

- [Discovery Query](#discovery-query)
- [Common Fields](#common-fields-all-billing-events)
- [Metering Intervals](#metering-intervals)
- [Event Types by Category](#event-types-by-category)
  - [Ingest & Process](#ingest--process)
  - [Query](#query)
  - [Retain](#retain)
  - [Host Monitoring](#host-monitoring)
  - [RUM](#rum-real-user-monitoring)
  - [Synthetic](#synthetic-monitoring)
  - [Security](#security)
  - [Containers](#containers)
  - [Automation](#automation)
  - [AppEngine Functions](#appengine-functions)
  - [Agentic AppEngine](#agentic-appengine)
  - [Data Egress](#data-egress)
  - [Database Monitoring](#database-monitoring)

For capability mapping and unit conversion, see
[billing-capabilities.md](billing-capabilities.md). For cost estimation, see
[cost-estimations.md](cost-estimations.md).

## Discovery Query

List all billing event types present in your environment:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| summarize count = count(), by: {event.type}
| sort count desc
```

## Common Fields (All Billing Events)

Every `BILLING_USAGE_EVENT` includes these fields:

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | timestamp | When the usage record was created |
| `event.kind` | string | Always `"BILLING_USAGE_EVENT"` |
| `event.type` | string | Human-readable category name (see tables below) |
| `event.id` | string | Unique event identifier |
| `event.version` | string | Event schema version (`"1.0"`, `"1.0.0"`, or `"2.0"`). |
| `event.provider` | string | Source system (`"LIMA_CLIENT"`, `"LIMA_USAGE_TRACKER"`, `"LIMA_USAGE_STREAM"`) |
| `dt.security_context` | string | Always `"BILLING_USAGE_EVENT"` |

### Optional Common Fields

| Field | Type | Description |
|-------|------|-------------|
| `usage.start` | **timestamp** | Start of the usage measurement window. ⚠️ **Timestamp type** — use `toTimestamp("<ISO-string>")` for comparisons; plain string comparisons return silently empty results. |
| `usage.end` | **timestamp** | End of the usage measurement window. Same timestamp type caveat as `usage.start`. |
| `usage.bucket` | string | Grail bucket name (e.g., `"default_logs"`, `"default_spans"`) |
| `dt.cost.costcenter` | string or record[] | Cost center tag — see [cost-allocation.md](cost-allocation.md) for type variations and chargeback queries. **Coverage note:** field presence ≠ population; coverage depends on whether tags are configured on monitored entities. Verify with a pre-flight query before building chargeback reports (see [cost-allocation.md](cost-allocation.md)). |
| `dt.cost.product` | string or record[] | Product tag — see [cost-allocation.md](cost-allocation.md). Same coverage caveat as `dt.cost.costcenter`. |
| `event.billing.category` | string | Subcategory (only on Events and Digital Experience Monitoring ingest/query/retain) |

## Metering Intervals

Usage events are generated at different cadences depending on the capability:

| Interval | Event Types |
|----------|-------------|
| **15 min** | All Ingest types (Log, Events, Files, Metrics, Traces), Host monitoring (Full-Stack, Infrastructure, Foundation, Mainframe, Code), K8s Platform Monitoring, RUM (Real User Monitoring, Session Replay), Synthetic (all types), Runtime Application Protection, Runtime Vulnerability Analytics, Data Egress, Database Monitoring |
| **Hourly** | All Retain types (Log, Events, Files, Metrics, Traces, DEM, Log Retain with Included Queries), Real User Monitoring Property, Automation Workflow, Security Posture Management |
| **Per execution** | All Query types (per query execution), AppEngine Functions - Small, AI Function Standard Call, AI Units (per invocation) |

The interval determines the granularity of `usage.start` / `usage.end` windows
(where present) and how to bin events for trend analysis. For event types that
have `usage.start`, always bin by `usage.start` (not `timestamp`) — the
`timestamp` field reflects emission time, which lags `usage.start` by ≈20
minutes for most 15-min types and ≈4 hours for Metrics Ingest (see
[Billing Event Emission Lag](billing-capabilities.md#billing-event-emission-lag)).
For event types that lack `usage.start` (Retain, Query, Workflow, SPM,
AppEngine Functions - Small, AI Function Standard Call, AI Units), bin by `timestamp` instead.

## Event Types by Category

### Ingest & Process

Billing fields vary by event type — see the table below.

| Event Type | Billed Field | Type | Notes |
|------------|-------------|------|-------|
| `Log Management & Analytics - Ingest & Process` | `billed_bytes` | long | |
| `Events - Ingest & Process` | `billed_bytes` | double | Has `event.billing.category` subcategories |
| `Files - Ingest & Process` | `billed_bytes` | long | Same normalization weight as **Events - Ingest & Process** (see [cost-estimations.md](cost-estimations.md)) |
| `Metrics - Ingest & Process` | `data_points` | long | |
| `Traces - Ingest & Process` | `ingested_bytes` + `ingested_spans` | long | `licensing_type` available |

**Additional fields:** `usage.bucket`, `usage.start`, `usage.end`,
`dt.cost.costcenter`, `dt.cost.product`

**Events subcategories** (via `event.billing.category`):
- `"Business events"`
- `"Custom Davis & Kubernetes events"`
- `"Custom generic events"`
- `"Security events"`

**Traces `licensing_type` values:** `"fullstack-adaptive"`,
`"fullstack-fixed-rate"`, `"otlp-trace-ingest"`, `"serverless"`

**Metrics additional fields:** `metric.type`, `monitoring_source`

### Query

Charged per scan volume. Billed unit: `billed_bytes` (long).

| Event Type | Description |
|------------|-------------|
| `Traces - Query` | Querying trace / span data |
| `Log Management & Analytics - Query` | Querying log data |
| `Events - Query` | Querying event data (has `event.billing.category` subcategories) |
| `Files - Query` | Querying file data; same normalization weight as **Events - Query** (see [cost-estimations.md](cost-estimations.md)) |
| `Digital Experience Monitoring - Query` | Querying DEM / user event data (has `event.billing.category` subcategories); **preview** — no Normalization Weight available |

**Additional fields:** `usage.bucket`, `query_id`, `query_start`,
`client.application_context`, `client.function_context`, `client.source`,
`client.client_context`, `client.workflow_context`, `client.internal_service_context`,
`action_type` (values: `"QUERY"`, `"DELETION"`), `user.id`, `user.email`,
`ai_generated` (boolean, always present — `true` when the query was issued by an AI agent, `false` otherwise),
`conversation_id` (string, optional — may be empty string on Query BUEs even when set on the originating AI Units or AI Function Standard Call BUE),
`session_id` (string, optional)

**Indirect AI costs:** Query BUEs with `ai_generated == true` represent scan volume triggered by AI agents
— the indirect cost of AI functionality on top of the direct charges billed as `AI Units` and
`AI Function Standard Call` BUEs. The `session_id` field links these Query BUEs to the corresponding
AI Units / AI Function Standard Call BUEs from the same session. See
[query-cost-attribution.md → Step 2a — AI-Generated Queries](query-cost-attribution.md#step-2a--ai-generated-queries)
for isolation queries.

#### Query Attribution

Coverage of `client.*` attribution fields depends on your tenant's query pool
distribution, not on BUE event type. Use `coalesce(client.source, client.application_context, client.internal_service_context, client.workflow_context, client.function_context, client.client_context, "unknown")` for
attribution. See
[query-cost-attribution.md → BUE Query Attribution Fields](query-cost-attribution.md#bue-query-attribution-fields)
for the per-pool breakdown and
[query-cost-attribution.md → Step 1a](query-cost-attribution.md#step-1a--coverage-check)
for the coverage check query.

> **BUE Query events and workflow attribution fields** — 
> The `client.workflow_context` field is available (contains the `workflow.id` value). To attribute query costs to a
> workflow where no context is available (value is `null`) on the BUE, use QEE AUTOMATION pool with `client.workflow_context`. See
> [workflow-total-cost.md → Cross-Event Field Reference](workflow-total-cost.md#cross-event-field-reference).

**Events - Query subcategories** (via `event.billing.category`):
- `"Business events"`, `"Custom Davis & Kubernetes events"`,
  `"Custom generic events"`, `"Kubernetes warning events"`,
  `"Security events"`

**Digital Experience Monitoring - Query** details:
- **Billed field:** `billed_bytes` (long)
- **Pricing:** Preview — no Normalization Weight available. Not included in
  standard cost estimation queries but can be queried for volume tracking.
- **Additional fields:** same as other Query types (`usage.bucket`, `query_id`,
  `query_start`, `client.source`, `client.application_context`,
  `client.function_context`, `client.client_context`,
  `client.workflow_context`, `client.internal_service_context`,
  `action_type`, `user.id`, `user.email`, `ai_generated`,
  `conversation_id`, `session_id`, `event.billing.category`)
- **Subcategories** (via `event.billing.category`): `"Synthetic events"` and
  RUM-related subcategories
- **Provider:** `LIMA_USAGE_TRACKER`
- To include DEM - Query in cost investigation, add it to the `filter in(event.type, ...)`
  clause in [query-cost-attribution.md → Step 1](query-cost-attribution.md#step-1--top-sources-by-billable-scan-bue).
  No `Normalization Weight` is available — omit from cost ranking, use
  for usage/volume tracking only.

### Retain

Charged per volume retained in **GiB-days**. Billed unit: `billed_bytes` (long).
Events are emitted **hourly**, each recording the bytes currently stored — this
represents 1/24th of a GiB-day. **Divide summed bytes by `1073741824 * 24`**
(or `25769803776`) to convert to GiB-days.

| Event Type | Description |
|------------|-------------|
| `Traces - Retain` | Trace data retention |
| `Log Management & Analytics - Retain` | Log data retention |
| `Log Management & Analytics - Retain with Included Queries` | Log retention with bundled queries |
| `Metrics - Retain` | Metric data retention |
| `Events - Retain` | Event data retention (has `event.billing.category` subcategories) |
| `Files - Retain` | File data retention; same normalization weight as **Events - Retain** (see [cost-estimations.md](cost-estimations.md)) |
| `Digital Experience Monitoring - Retain` | DEM / user event data retention; **preview** — no Normalization Weight available |

**Additional fields:** `usage.bucket`

### Host Monitoring

Charged per unit of monitored host resource. Billed unit varies by type:

| Event Type | Billed Field | Type | Unit |
|------------|-------------|------|------|
| `Full-Stack Monitoring` | `billed_gibibyte_hours` | double | GiB-hours of host memory |
| `Infrastructure Monitoring` | `billed_host_hours` | double | Host-hours |
| `Foundation & Discovery` | `billed_host_hours` | double | Host-hours |
| `Mainframe Monitoring` | `billed_msu_hours` | double | MSU-hours |
| `Code Monitoring` | `billed_container_hours` | double | Container-hours; 0.25 per container per 15-min interval |

**Additional fields:** `dt.entity.host`, `dt.cost.costcenter`,
`dt.cost.product`, `usage.start`, `usage.end`

**Code Monitoring additional fields:** `application_only_type`,
`aws.account.id`, `azure.subscription`, `gcp.project.id`, `k8s.cluster.uid`,
`k8s.namespace.name`

### RUM (Real User Monitoring)

Charged per session. Billed unit varies by type:

| Event Type | Billed Field | Type | Notes |
|------------|-------------|------|-------|
| `Real User Monitoring` | `billed_sessions` | long | |
| `Real User Monitoring with Session Replay` | `billed_replay_sessions` | long | |
| `Real User Monitoring Property` | `billed_property_sessions` | long | User action and session properties counted by application |

**Additional fields:** `dt.entity.application`, `dt.entity.device_application`,
`device.type`, `usage.start`, `usage.end`

### Synthetic Monitoring

Charged per execution. Billed unit varies by type:

| Event Type | Billed Field | Type | Entity Field |
|------------|-------------|------|--------------|
| `Browser Monitor or Clickpath` | `billed_synthetic_action_count` | long | `dt.entity.synthetic_test` |
| `HTTP Monitor` | `billed_http_request_count` | long | `dt.entity.http_check` |
| `Third-Party Synthetic API Ingestion` | `billed_test_result_ingestion_count` | long | `dt.entity.external_synthetic_test` |

**Additional fields:** `usage.start`, `usage.end`

> **Note on `dt.entity.external_synthetic_test`:** This field may contain a
> plain-text name (e.g. `"RFA Test"`) rather than an entity ID
> (`EXTERNAL_SYNTHETIC_TEST-xxx`). Entity lookup may not work; group by the
> field value directly.

### Security

| Event Type | Billed Field | Type | Notes |
|------------|-------------|------|-------|
| `Runtime Application Protection` | `billed_gibibyte_hours` | double | GiB-hours |
| `Runtime Vulnerability Analytics` | `billed_gibibyte_hours` | double | GiB-hours |
| `Security Posture Management` | *(none)* | — | No billed field; usage = distinct node count per hour |

**Runtime Application Protection / Runtime Vulnerability Analytics** additional
fields: `dt.entity.host`, `dt.cost.costcenter`, `dt.cost.product`,
`usage.start`, `usage.end`

**Security Posture Management** is unique among billing events:
- **No billed field** — usage is determined by counting distinct K8s nodes per hour
- Has `dt.entity.kubernetes_cluster` and `dt.entity.kubernetes_node` (NOT `dt.entity.host`)
- **No `usage.start` / `usage.end`** — only `timestamp`
- Provider is `LIMA_USAGE_STREAM` (not `LIMA_CLIENT` like most others)
- No `dt.cost.costcenter` / `dt.cost.product`

> **SPM node-hour metering:** In Kubernetes environments, each node that is
> scanned during an hour is counted as a host-hour, regardless of how many
> times it was scanned. You can enable Kubernetes Security Posture Management
> on a per-cluster basis.

### Containers

Charged per pod-hour. Billed unit: `billed_pod_hours` (double).

| Event Type | Description |
|------------|-------------|
| `Kubernetes Platform Monitoring` | K8s platform monitoring |

**Additional fields:** `dt.entity.kubernetes_cluster`,
`dt.entity.cloud_application_namespace`, `usage.start`, `usage.end`

### Automation

Two distinct metering models:

**Automation Workflow** — Charged per workflow-hour. Every `workflow.id`
identified within a given hour contributes 1 workflow-hour. There is **no
billed field** — each event represents one workflow execution, and billing
counts distinct workflows per hour.

| Event Type | Billed Field | Metering |
|------------|-------------|----------|
| `Automation Workflow` | *(none)* | Count distinct `workflow.id` per hour |

**Additional fields:** `workflow.id`, `workflow.title`,
`workflow.owner`, `workflow.actor`, `workflow.trigger_type`,
`workflow.is_private`, `workflow.created_at`, `workflow.updated_by`,
`event.start`, `event.end`

### AppEngine Functions

Charged per invocation. Billed unit: `billed_invocations` (long). Appears as **Standard Function Calls** in Account Management.

| Event Type | Billed Field | Type | Notes |
|------------|-------------|------|-------|
| `AppEngine Functions - Small` | `billed_invocations` | long | JS/Python function invocations |

**Additional fields:** `dt.app.id`, `function.id`,
`function.execution_id`, `function.duration_sec`, `function.memory_mib`,
`function.type`, `caller.app.id`, `caller.service.id`, `workflow.id`,
`workflow.execution.id`, `user.id`, `user.email`

### Agentic AppEngine

AI-triggered invocations. Two types: non-LLM tool calls (`AI Function Standard Call`) and AI/LLM work (`AI Units`). `AI Function Standard Call` shares the **Standard Function Calls** rate-card item with `AppEngine Functions - Small`; `AI Units` is a separate rate-card item.

| Event Type | Billed Field | Type | Notes |
|------------|-------------|------|-------|
| `AI Function Standard Call` | `billed_invocations` | long | Non-LLM tool usage (no LLM inference); typically 1 per call |
| `AI Units` | `usage.quantity.billable` | double | AI/LLM work — model inference and LLM-based tools; `usage.unit` = `"Units"` |

**Additional fields (AI Function Standard Call and AI Units):**
`tool` (specific tool name, e.g. `"execute-dql"`, `"operator"`; optional),
`tool.category` (`"standard"` or `"ai"`),
`caller.type` (`"api"` | `"mcp"` | `"internal"`),
`caller.app.id` (optional), `caller.service.id` (optional), `dt.app.id` (optional),
`conversation_id` (optional), `session_id` (optional),
`workflow.id` (optional — present when invoked from a workflow),
`workflow.execution.id` (optional),
`user.id`, `user.email`

**AI Units only:** `usage.unit` (always `"Units"`).

**Event type names are exact.** When displaying event type names to the user, always copy them verbatim — never abbreviate.

### Data Egress

Charged per volume egressed. Billed unit: `billed_bytes` (long).
Normalization weight: 0.15 per GiB (see [cost-estimations.md](cost-estimations.md)).

| Event Type | Description |
|------------|-------------|
| `Data Egress` | Data forwarded via OpenPipeline |

**Additional fields:** `dt.openpipeline.forwarding.config_id`,
`dt.openpipeline.forwarding.datatype`, `usage.start`, `usage.end`

### Database Monitoring

Charged per database instance hour. Billed unit: `database-instance-hours`
(double). Each 1,000 unique queries count as 0.25 hours, with a minimum of 0.25
hours per 15-min window. Normalization weight: 0.11 per database-instance-hour
(see [cost-estimations.md](cost-estimations.md)).

| Event Type | Description |
|------------|-------------|
| `Database Monitoring` | Database instances monitored (entity type e.g. `DB_INSTANCE_POSTGRES`) |

**Additional fields:** `database_queries`, `dt.smartscape_source.id`,
`dt.smartscape_source.type`, `dt.cost.costcenter`, `dt.cost.product`,
`usage.start`, `usage.end`
