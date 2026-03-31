# Billing Usage Queries

DQL query examples for each billing event type. Companion to
[billing-event-types.md](billing-event-types.md) which documents fields,
metering intervals, and event type tables.

> **Reminder:** Billing events can be refreshed — always use `| dedup event.id`
> before aggregating to prevent double-counting.

## Contents

- [Ingest & Process](#ingest--process)
  - [Log & Event Ingest Volume](#log--event-ingest-volume)
  - [Metrics Ingest Volume](#metrics-ingest-volume)
  - [Trace Ingest Volume](#trace-ingest-volume)
  - [Daily Ingest Trend](#daily-ingest-trend)
- [Query](#query)
  - [Top Query Consumers by Category](#top-query-consumers-by-category)
- [Retain](#retain)
  - [Retention Volume by Data Type](#retention-volume-by-data-type)
- [Host Monitoring](#host-monitoring)
  - [Full-Stack Monitoring by Host](#full-stack-monitoring-by-host)
  - [Infrastructure & Foundation Host-Hours](#infrastructure--foundation-host-hours)
  - [Mainframe MSU-Hours](#mainframe-msu-hours)
  - [Code Monitoring by Namespace](#code-monitoring-by-namespace)
  - [Code Monitoring by Cluster](#code-monitoring-by-cluster)
- [RUM](#rum)
  - [RUM Sessions by Application](#rum-sessions-by-application)
  - [Session Replay by Application](#session-replay-by-application)
- [Synthetic](#synthetic)
  - [Browser Monitor Executions](#browser-monitor-executions)
  - [HTTP Monitor Requests](#http-monitor-requests)
  - [Third-Party Synthetic Ingestion](#third-party-synthetic-ingestion)
- [Security](#security)
  - [Security GiB-Hours (RAP + RVA)](#security-gib-hours-rap--rva)
  - [SPM Hourly Node Count](#spm-hourly-node-count)
  - [SPM Nodes by Cluster](#spm-nodes-by-cluster)
- [Containers](#containers)
  - [Pod-Hours by Cluster](#pod-hours-by-cluster)
- [Automation](#automation)
  - [Workflow-Hours per Hour](#workflow-hours-per-hour)
  - [Top Workflows by Execution Count](#top-workflows-by-execution-count)
  - [Daily Workflow-Hours Trend](#daily-workflow-hours-trend)
  - [AppEngine Function Invocations](#appengine-function-invocations)
- [Data Egress](#data-egress)
  - [Egress Volume by Forwarding Config](#egress-volume-by-forwarding-config)
- [Cross-Category](#cross-category)
  - [Cost Spike Investigation — Week-over-Week](#cost-spike-investigation--week-over-week)

## Ingest & Process

### Log & Event Ingest Volume

Log and event ingest volume by type (GiB):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type,
    "Log Management & Analytics - Ingest & Process",
    "Events - Ingest & Process",
    "Files - Ingest & Process")
| dedup event.id
| summarize total_gib = sum(billed_bytes) / 1073741824, by: {event.type}
| sort total_gib desc
```

### Metrics Ingest Volume

Metrics ingest volume by metric type (data points):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Metrics - Ingest & Process"
| dedup event.id
| summarize total_data_points = sum(data_points), by: {metric.type}
| sort total_data_points desc
```

### Trace Ingest Volume

Trace ingest volume by licensing type (bytes and spans):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Traces - Ingest & Process"
| dedup event.id
| summarize
    total_gib = sum(ingested_bytes) / 1073741824,
    total_spans = sum(ingested_spans),
    by: {licensing_type}
| sort total_gib desc
```

### Daily Ingest Trend

Daily log and event ingest trend over 30 days:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type,
    "Log Management & Analytics - Ingest & Process",
    "Events - Ingest & Process")
| dedup event.id
| fieldsAdd bytes = billed_bytes
| makeTimeseries daily_bytes = sum(bytes), by: {event.type}, interval: 1d
```

## Query

### Top Query Consumers by Category

Top query scan consumers by billing category:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Events - Query"
| dedup event.id
| summarize total_gib = sum(billed_bytes) / 1073741824,
    by: {event.billing.category}
| sort total_gib desc
```

## Retain

### Retention Volume by Data Type

Retention volume in GiB-days by data type. Retain events are emitted hourly,
each recording 1/24th of a GiB-day — divide by `25769803776`
(`1073741824 × 24`):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type,
    "Traces - Retain",
    "Log Management & Analytics - Retain",
    "Log Management & Analytics - Retain with Included Queries",
    "Metrics - Retain",
    "Events - Retain",
    "Files - Retain",
    "Digital Experience Monitoring - Retain")
| dedup event.id
| summarize total_gib_days = sum(billed_bytes) / 25769803776, by: {event.type}
| sort total_gib_days desc
```

## Host Monitoring

### Full-Stack Monitoring by Host

Full-Stack Monitoring consumption by host (GiB-hours):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Full-Stack Monitoring"
| dedup event.id
| summarize total_gib_hours = sum(billed_gibibyte_hours), by: {dt.entity.host}
| sort total_gib_hours desc
| limit 20
| lookup [fetch dt.entity.host], sourceField: dt.entity.host, lookupField: id,
    fields: {entity.name}
```

### Infrastructure & Foundation Host-Hours

Infrastructure and Foundation host-hours by host:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type, "Infrastructure Monitoring", "Foundation & Discovery")
| dedup event.id
| summarize total_host_hours = sum(billed_host_hours),
    by: {event.type, dt.entity.host}
| sort total_host_hours desc
| limit 20
```

### Mainframe MSU-Hours

Mainframe MSU-hours by host:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Mainframe Monitoring"
| dedup event.id
| summarize total_msu_hours = sum(billed_msu_hours), by: {dt.entity.host}
| sort total_msu_hours desc
| lookup [fetch dt.entity.host], sourceField: dt.entity.host, lookupField: id,
    fields: {entity.name}
```

### Code Monitoring by Namespace

Code Monitoring container-hours by namespace:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Code Monitoring"
| dedup event.id
| summarize total_container_hours = sum(billed_container_hours),
    by: {k8s.namespace.name}
| sort total_container_hours desc
| limit 20
```

### Code Monitoring by Cluster

Code Monitoring container-hours by cluster:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Code Monitoring"
| dedup event.id
| summarize total_container_hours = sum(billed_container_hours),
    by: {k8s.cluster.uid}
| sort total_container_hours desc
| limit 20
```

## RUM

### RUM Sessions by Application

RUM sessions by application:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Real User Monitoring"
| dedup event.id
| summarize total_sessions = sum(billed_sessions),
    by: {dt.entity.application}
| sort total_sessions desc
| lookup [fetch dt.entity.application], sourceField: dt.entity.application,
    lookupField: id, fields: {entity.name}
```

### Session Replay by Application

Session Replay consumption by application:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Real User Monitoring with Session Replay"
| dedup event.id
| summarize total_replay_sessions = sum(billed_replay_sessions),
    by: {dt.entity.application}
| sort total_replay_sessions desc
```

## Synthetic

### Browser Monitor Executions

Browser monitor executions by monitor:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Browser Monitor or Clickpath"
| dedup event.id
| summarize total_actions = sum(billed_synthetic_action_count),
    by: {dt.entity.synthetic_test}
| sort total_actions desc
| limit 20
```

### HTTP Monitor Requests

HTTP monitor request count by monitor:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "HTTP Monitor"
| dedup event.id
| summarize total_requests = sum(billed_http_request_count),
    by: {dt.entity.http_check}
| sort total_requests desc
| limit 20
```

### Third-Party Synthetic Ingestion

Third-Party Synthetic ingestion by test:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Third-Party Synthetic API Ingestion"
| dedup event.id
| summarize total_ingestions = sum(billed_test_result_ingestion_count),
    by: {dt.entity.external_synthetic_test}
| sort total_ingestions desc
```

## Security

### Security GiB-Hours (RAP + RVA)

Security GiB-hours by type (Runtime Application Protection + Runtime
Vulnerability Analytics):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type,
    "Runtime Application Protection",
    "Runtime Vulnerability Analytics")
| dedup event.id
| summarize total_gib_hours = sum(billed_gibibyte_hours), by: {event.type}
| sort total_gib_hours desc
```

### SPM Hourly Node Count

Security Posture Management: hourly monitored node count:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Security Posture Management"
| dedup event.id
| fieldsAdd hour = bin(timestamp, 1h)
| summarize hourly_nodes = countDistinct(dt.entity.kubernetes_node), by: {hour}
| sort hour desc
```

### SPM Nodes by Cluster

SPM: nodes by cluster:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Security Posture Management"
| dedup event.id
| summarize node_count = countDistinct(dt.entity.kubernetes_node),
    by: {dt.entity.kubernetes_cluster}
| sort node_count desc
| lookup [fetch dt.entity.kubernetes_cluster],
    sourceField: dt.entity.kubernetes_cluster, lookupField: id,
    fields: {entity.name}
```

## Containers

### Pod-Hours by Cluster

Pod-hours by K8s cluster:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Kubernetes Platform Monitoring"
| dedup event.id
| summarize total_pod_hours = sum(billed_pod_hours),
    by: {dt.entity.kubernetes_cluster}
| sort total_pod_hours desc
| lookup [fetch dt.entity.kubernetes_cluster],
    sourceField: dt.entity.kubernetes_cluster, lookupField: id,
    fields: {entity.name}
```

## Automation

### Workflow-Hours per Hour

Workflow-hours (distinct workflows per hour):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Automation Workflow"
| dedup event.id
| fieldsAdd hour = bin(timestamp, 1h)
| summarize workflow_hours = countDistinct(workflow.id), by: {hour}
| sort hour desc
```

### Top Workflows by Execution Count

Top workflows by execution count:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Automation Workflow"
| dedup event.id
| summarize executions = count(), by: {workflow.id, workflow.title}
| sort executions desc
| limit 20
```

### Daily Workflow-Hours Trend

Workflow-hours (distinct workflows per hour, summed per day):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Automation Workflow"
| dedup event.id
| fieldsAdd hour = bin(timestamp, 1h), day = bin(timestamp, 1d)
| summarize hourly_workflow_hours = countDistinct(workflow.id), by: {day, hour}
| summarize daily_workflow_hours = sum(hourly_workflow_hours), by: {day}
| sort day desc
```

### AppEngine Function Invocations

AppEngine function invocations by app:

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "AppEngine Functions - Small"
| dedup event.id
| summarize total_invocations = sum(billed_invocations), by: {dt.app.id}
| sort total_invocations desc
| limit 20
```

## Data Egress

### Egress Volume by Forwarding Config

Data Egress volume by OpenPipeline forwarding configuration (GiB):

```dql
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter event.type == "Data Egress"
| dedup event.id
| summarize total_gib = sum(billed_bytes) / 1073741824,
    by: {dt.openpipeline.forwarding.config_id, dt.openpipeline.forwarding.datatype}
| sort total_gib desc
```

## Cross-Category

### Cost Spike Investigation — Week-over-Week

Compare event counts between current and previous week to detect spikes:

```dql
fetch dt.system.events, from: -14d
| filter event.kind == "BILLING_USAGE_EVENT"
| dedup event.id
| fieldsAdd week = if(timestamp >= now() - 7d, "current", else: "previous")
| summarize event_count = count(), by: {event.type, week}
| sort event.type asc
```
