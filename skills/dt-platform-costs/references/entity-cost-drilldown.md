# Entity-Based Cost Drill-Down

After identifying which billing capabilities drive costs (using
[cost-estimations.md](cost-estimations.md)), drill down to find which specific
entities — applications, hosts, synthetic tests, clusters — are responsible.

## Contents

- [Workflow](#workflow)
- [Common Principles](#common-principles)
- [Entity Field Quick-Lookup](#entity-field-quick-lookup)
- [Entity IDs in Results](#entity-ids-in-results)
- [Drill-Down Query Templates](#drill-down-query-templates)
- [Non-Entity Categories](#non-entity-categories)
- [Best Practices](#best-practices)

## Workflow

When the user asks to drill down into a specific billing capability (e.g.,
"which app drives my RUM cost?", "top hosts by Full-Stack cost"):

1. **Sample first** — Run `| limit 3` (no `| fields` clause) on the target BUE
   event type to discover available entity fields. NEVER guess field names.
   Entity fields use `dt.entity.*` prefixes, not intuitive names.
2. **Look up the entity field** — Consult the
   [Entity Field Quick-Lookup](#entity-field-quick-lookup)
   to confirm the correct group-by field for the category.
3. **Run the drill-down query** — Use the template from
   [Drill-Down Query Templates](#drill-down-query-templates).
4. **Present the entity IDs as-is** — drill-down results contain `dt.entity.*`
   IDs (e.g. `HOST-1A2B3C`). Present them directly. **Do not** use
   `entityName()` or any other entity-model function to resolve names — those
   functions are deprecated and will stop being supported. See
   [Entity IDs in Results](#entity-ids-in-results).
5. **For capabilities without entity attribution** (Retain, Ingest for
   Logs/Events/Files, Query types) — use `usage.bucket` for bucket-level
   breakdown or `dt.cost.costcenter` for cost center breakdown. For Query
   types, follow [query-cost-attribution.md](query-cost-attribution.md).

## Common Principles

1. **BUE is billable truth** — Always use `BILLING_USAGE_EVENT` for entity
   drill-down. Entity fields (`dt.entity.*`) are on BUE, not QEE.

2. **Sample first** — Before building any drill-down query, run
   `| limit 3` (without `| fields`) on the target BUE event type to discover
   available fields. BUE entity fields use `dt.entity.*` prefixes — NOT
   intuitive names like `application.name`, `host.name`, or `monitor.name`.
   Always sample to verify actual field names before grouping.

3. **Dedup billing events** — Use `| dedup event.id` for single-type queries
   (all templates below filter to one `event.type`). See
   [Billing Event Deduplication](billing-capabilities.md#billing-event-deduplication).

4. **Rolling windows are acceptable here** — Investigation queries use
   `from: -7d` or `from: -30d` for diagnostic analysis. For billing totals
   that must match the Account Management Portal, use explicit UTC midnight
   boundaries per [billing-capabilities.md § Billing Timeframe Boundaries](billing-capabilities.md#billing-timeframe-boundaries).

> **CRITICAL: Sample before grouping.** Before building any entity drill-down
> query, run `| limit 3` (without `| fields`) on the target BUE event type to
> verify actual field names. BUE entity fields use `dt.entity.*` prefixes —
> NOT intuitive names like `application.name`, `host.name`, or `monitor.name`.
> Never guess field names.

## Entity Field Quick-Lookup

| BUE Category | Entity / Group-By Field(s) |
|---|---|
| Full-Stack Monitoring | `dt.entity.host` |
| Infrastructure Monitoring | `dt.entity.host` |
| Foundation & Discovery | `dt.entity.host` |
| Code Monitoring | `dt.entity.host`, `k8s.cluster.uid`, `k8s.namespace.name` |
| Runtime Application Protection | `dt.entity.host` |
| Runtime Vulnerability Analytics | `dt.entity.host` |
| Real User Monitoring | `dt.entity.application`, `dt.entity.device_application`, `device.type` |
| Real User Monitoring with Session Replay | `dt.entity.application`, `dt.entity.device_application`, `device.type` |
| Real User Monitoring Property | `dt.entity.application`, `dt.entity.device_application`, `device.type` |
| Browser Monitor or Clickpath | `dt.entity.synthetic_test` |
| HTTP Monitor | `dt.entity.http_check` |
| Third-Party Synthetic API Ingestion | `dt.entity.external_synthetic_test` |
| Kubernetes Platform Monitoring | `dt.entity.kubernetes_cluster`, `dt.entity.cloud_application_namespace` |
| Security Posture Management | `dt.entity.kubernetes_cluster`, `dt.entity.kubernetes_node` |
| Automation Workflow | `workflow.id`, `workflow.title`, `workflow.owner` |
| AppEngine Functions - Small | `workflow.id`, `function.id`, `dt.app.id` |
| AI Units | `workflow.id`, `workflow.execution.id`, `tool` (optional), `dt.app.id` (optional), `conversation_id` (optional) |
| AI Function Standard Call | `workflow.id`, `workflow.execution.id`, `tool` (optional), `dt.app.id` (optional), `conversation_id` (optional) |
| Database Monitoring | `dt.smartscape_source.id`, `dt.smartscape_source.type` |

For categories **without** entity attribution, see
[Non-Entity Categories](#non-entity-categories) below.

## Entity IDs in Results

Drill-down queries return `dt.entity.*` IDs (e.g., `HOST-1A2B3C`). **Present
these IDs directly in the output.**

> ⛔ **Do not use `entityName()` — or any entity-model function — to resolve
> IDs to names.** Entity-model functions are deprecated and will stop being
> supported. This applies to any function that takes a `dt.entity.*` field as
> input to look up entity metadata. Aggregating or grouping on the ID
> (`by: {dt.entity.host}`, `countDistinct(dt.entity.host)`) is fine — that
> treats the ID as a plain string value, not as an entity handle.

If a human-readable name is required, resolve it **outside DQL** (e.g. via the
entity/Smartscape API in a follow-up step) — not with an in-query entity
function.

**Example — Host drill-down (IDs presented as-is):**

```dql-template
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Full-Stack Monitoring"
| dedup event.id
| summarize total_gib_hours = sum(billed_gibibyte_hours),
    by: {dt.entity.host}
| sort total_gib_hours desc
| limit 20
```

## Drill-Down Query Templates

### Host Monitoring (Full-Stack, Infrastructure, Foundation)

```dql-template
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "<Full-Stack Monitoring | Infrastructure Monitoring | Foundation & Discovery>"
| dedup event.id
| summarize total_usage = sum(<billed_gibibyte_hours | billed_host_hours>),
    by: {dt.entity.host}
| sort total_usage desc
| limit 20
```

> Use `billed_gibibyte_hours` for Full-Stack, `billed_host_hours` for
> Infrastructure and Foundation. See
> [billing-event-types.md](billing-event-types.md) for the correct billed
> field per event type.

### RUM (Real User Monitoring)

```dql-template
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "<Real User Monitoring | Real User Monitoring with Session Replay | Real User Monitoring Property>"
| dedup event.id
| summarize total_sessions = sum(<billed_sessions | billed_replay_sessions | billed_property_sessions>),
    by: {dt.entity.application, device.type}
| sort total_sessions desc
| limit 20
```

> Use `dt.entity.device_application` instead of `dt.entity.application` for
> mobile app breakdown. Use `billed_sessions` for RUM, `billed_replay_sessions`
> for Session Replay, `billed_property_sessions` for RUM Property.

### Synthetic Monitoring

**Browser Monitor or Clickpath:**

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Browser Monitor or Clickpath"
| dedup event.id
| summarize total_actions = sum(billed_synthetic_action_count),
    by: {dt.entity.synthetic_test}
| sort total_actions desc
| limit 20
```

**HTTP Monitor:**

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "HTTP Monitor"
| dedup event.id
| summarize total_requests = sum(billed_http_request_count),
    by: {dt.entity.http_check}
| sort total_requests desc
| limit 20
```

### Kubernetes Platform Monitoring

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Kubernetes Platform Monitoring"
| dedup event.id
| summarize total_pod_hours = sum(billed_pod_hours),
    by: {dt.entity.kubernetes_cluster, dt.entity.cloud_application_namespace}
| sort total_pod_hours desc
| limit 20
```

### Security Posture Management

SPM has no billed field — count distinct nodes per hour:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Security Posture Management"
| dedup event.id
| fieldsAdd hour = bin(timestamp, 1h)
| summarize node_hours = countDistinct(dt.entity.kubernetes_node),
    by: {dt.entity.kubernetes_cluster, hour}
| summarize total_node_hours = sum(node_hours),
    by: {dt.entity.kubernetes_cluster}
| sort total_node_hours desc
```

### Security (Runtime Application Protection / Vulnerability Analytics)

```dql-template
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "<Runtime Application Protection | Runtime Vulnerability Analytics>"
| dedup event.id
| summarize total_gib_hours = sum(billed_gibibyte_hours),
    by: {dt.entity.host}
| sort total_gib_hours desc
| limit 20
```

### Code Monitoring

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Code Monitoring"
| dedup event.id
| summarize total_container_hours = sum(billed_container_hours),
    by: {dt.entity.host, k8s.namespace.name}
| sort total_container_hours desc
| limit 20
```

### Automation Workflow

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Automation Workflow"
| dedup event.id
| fieldsAdd hour = bin(timestamp, 1h)
| summarize hourly_wf = countDistinct(workflow.id), by: {workflow.id, workflow.title, workflow.owner, hour}
| summarize total_workflow_hours = sum(hourly_wf),
    by: {workflow.id, workflow.title, workflow.owner}
| sort total_workflow_hours desc
| limit 20
```

> For full workflow cost attribution (query scan + AppEngine + workflow-hours + AI),
> see [workflow-total-cost.md](workflow-total-cost.md).

### AppEngine AI Invocations

**AI Function Standard Call** (non-LLM tool usage, `billed_invocations`):

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "AI Function Standard Call"
| dedup event.id
| summarize total_invocations = sum(billed_invocations),
    by: {workflow.id, dt.app.id, tool}
| sort total_invocations desc
| limit 20
```

**AI Units** (AI/LLM usage, `usage.quantity.billable`):

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "AI Units"
| dedup event.id
| summarize total_units = sum(`usage.quantity.billable`),
    by: {workflow.id, dt.app.id, tool}
| sort total_units desc
| limit 20
```

> `tool` identifies the specific tool invoked (e.g. `"execute-dql"`, `"operator"`). Use
> `conversation_id` as an additional group-by to isolate costs by AI conversation.

## Non-Entity Categories

These BUE categories lack entity attribution fields. Use alternative group-by
fields:

| Category | Group-By Approach |
|---|---|
| All **Retain** types | `usage.bucket` for bucket-level breakdown; `dt.cost.costcenter` for cost center |
| All **Ingest** types (Logs, Events, Files) | `usage.bucket` or `dt.cost.costcenter` |
| **Metrics Ingest** | `monitoring_source` (fullstack vs infrastructure); `dt.cost.costcenter` via `expand` (see [cost-allocation.md](cost-allocation.md)). For per-metric-key drill-down, see [metrics-ingest-optimization.md](metrics-ingest-optimization.md) |
| All **Query** types | `client.source` / `client.application_context` — see [query-cost-attribution.md](query-cost-attribution.md) |
| **Data Egress** | `dt.openpipeline.forwarding.config_id`, `dt.openpipeline.forwarding.datatype` |

## Best Practices

1. **Sample first** — verify field names with `| limit 3` before building
   drill-down queries. Entity fields use `dt.entity.*` prefixes.
2. **Present entity IDs as-is** — show raw `dt.entity.*` IDs in results.
   **Never** use `entityName()` or any entity-model function (deprecated). See
   [Entity IDs in Results](#entity-ids-in-results).
3. **Dedup every BUE aggregation** — `| dedup event.id` is safe here
   (single-type queries). See
   [Billing Event Deduplication](billing-capabilities.md#billing-event-deduplication).
4. **NEVER guess entity field names** — BUE events use `dt.entity.application`,
   `dt.entity.host`, `dt.entity.synthetic_test`, etc. — NOT `application.name`,
   `host.name`, or `monitor.name`. Always sample first or consult the
   [Entity Field Quick-Lookup](#entity-field-quick-lookup).
