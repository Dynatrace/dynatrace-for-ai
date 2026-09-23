# Dynatrace Observability — Kiro Steering Guide

This document gives Kiro the context to answer Dynatrace observability questions, run DQL queries, and investigate problems. Read it before any Dynatrace task.

---

## 1. Environment Setup

Two environment variables must be set:

- `DT_ENVIRONMENT` — full tenant URL, e.g. `https://abc12345.apps.dynatrace.com`
- `DT_PLATFORM_TOKEN` — platform token with `storage:*:read`, `environment-api:*:read`, `security:events:read`, and `DataExport` scopes

Call `get_environment_info` first to confirm the connection before running any queries.

---

## 2. DQL Fundamentals

DQL is a pipeline-based query language. Commands chain with `|`. Data flows left-to-right, unlike SQL.

### 2.1 Data Sources

Always start with `fetch <source>` or `timeseries`. Every query needs a time range.

| Source | Command | Primary Use |
|---|---|---|
| Logs | `fetch logs` | Application and infrastructure log entries |
| Spans | `fetch spans` | Distributed trace spans |
| Davis Problems | `fetch dt.davis.problems` | AI-detected problems |
| Davis Events | `fetch dt.davis.events` | Underlying events powering problems |
| Business Events | `fetch bizevents` | Custom business telemetry |
| Security Events | `fetch security.events` | Vulnerability and threat detection |
| RUM Sessions | `fetch user.sessions` | Real user monitoring |
| RUM Events | `fetch user.events` | Page views, clicks, crashes |
| Metrics | `timeseries avg(metric.key)` | Pre-aggregated metric values — do NOT use `fetch` for metrics |
| Topology | `smartscapeNodes "HOST"` | Entity topology — do NOT use `fetch` for topology |

Discover available data objects:
```dql
fetch dt.system.data_objects | fields name, display_name, type
```

### 2.2 Time Ranges

Always specify `from:` to avoid full-scan queries:

```dql
-- Relative
fetch logs, from: now()-1h
fetch logs, from: now()-7d

-- Aligned to boundary (offset THEN align)
fetch logs, from: now()-1h@h              -- previous complete hour
fetch logs, from: now()-1d@d, to: now()@d -- yesterday complete

-- Absolute (double quotes required)
fetch logs, from: "2026-09-20T10:00:00Z", to: "2026-09-20T11:00:00Z"

-- This month so far
fetch bizevents, from: now()@M
```

Time alignment operator `@`: always offset before aligning — `now()-2h@h`, not `now()@h-2h`.

### 2.3 Core Command Pipeline

```dql
fetch logs, from: now()-1h            -- load data
| filter loglevel == "ERROR"          -- row filter (use == not =)
| filter contains(content, "timeout") -- substring match
| fields timestamp, content, service.name  -- select columns
| fieldsAdd severity = upper(loglevel)     -- computed column
| summarize count(), by: {service.name}    -- aggregate
| sort `count()` desc                      -- sort (backtick fields with parens in name)
| limit 20                                 -- cap rows
```

### 2.4 Critical Syntax Rules

| Wrong | Correct | Why |
|---|---|---|
| `filter x in ["a","b"]` | `filter in(x, {"a","b"})` | `[]` wraps sub-queries; `{}` for static sets |
| `filter host = "web"` | `filter host == "web"` | `=` is assignment |
| `filter log.level == "ERROR"` | `filter loglevel == "ERROR"` | Field is `loglevel`, no dot |
| `by: a, b` | `by: {a, b}` | `by:` requires curly braces |
| `toLowercase(x)` | `lower(x)` | Function is `lower()` |
| `sort count() desc` | `` sort `count()` desc `` | Backtick names containing `()` |
| `dt.entity.host` | `dt.smartscape.host` | `dt.entity.*` is deprecated |
| `event.status == "OPEN"` | `event.status == "ACTIVE"` | Davis uses ACTIVE / CLOSED |
| `metrics dt.host.cpu.usage` | `timeseries avg(dt.host.cpu.usage)` | `metrics` = discovery, not values |
| `length(x)` | `stringLength(x)` | No `length()` in DQL |

### 2.5 Metrics with `timeseries`

```dql
-- Single metric
timeseries cpu = avg(dt.host.cpu.usage), by: {dt.smartscape.host}

-- Multiple metrics (rollup: goes inside each function when mixing aggregations)
timeseries {
  p95 = percentile(dt.service.request.response_time, 95, rollup: avg),
  avg_rt = avg(dt.service.request.response_time)
}, by: {dt.service.name}

-- Scalar result (no array allocated — preferred when you only need one value)
timeseries cpu = avg(dt.host.cpu.usage, scalar:true), by: {dt.smartscape.host}

-- Full array then collapse to scalar in a later stage
timeseries cpu = avg(dt.host.cpu.usage), by: {dt.smartscape.host}
| fieldsAdd avg_cpu = arrayAvg(cpu), max_cpu = arrayMax(cpu)
```

**Key rule:** `percentile`, `median`, and `percentRank` in `timeseries` **require `rollup:`**. Without it the query returns empty results with no error.

Discover metrics by keyword:
```dql
metrics from: now()-1h
| filter contains(metric.key, "cpu")
| summarize count(), by: {metric.key}
| sort `count()` desc
```

### 2.6 `summarize` and `makeTimeseries`

**`summarize`** collapses rows to aggregates:
```dql
fetch logs, from: now()-1h
| summarize total = count(), errors = countIf(loglevel == "ERROR"),
            by: {k8s.namespace.name}
| fieldsAdd error_pct = (errors * 100.0) / total
```

**`makeTimeseries`** builds a time-bucketed series from events (not pre-aggregated metrics):
```dql
fetch logs, from: now()-6h
| makeTimeseries total = count(), errors = countIf(loglevel == "ERROR"),
               interval: 5m, by: {k8s.namespace.name}
| fieldsAdd error_rate = errors[] * 100.0 / total[]
```

Do **not** pipe `timeseries` into `makeTimeseries` — it fails with `INVALID_IMPLICIT_TIME_DEFAULT`.

---

## 3. Entity Discovery

### 3.1 Find an Entity by Name

Use the MCP tool for quick lookup:
```
find_entity_by_name(entityName="checkout-service", entityType="SERVICE")
```

Or use DQL:
```dql
smartscapeNodes "SERVICE"
| filter contains(getNodeName(), "checkout")
| fields getNodeName(), dt.smartscape.service
| limit 20
```

### 3.2 Entity ID Mapping

| Entity | ID Field in DQL | `smartscapeNodes` Type |
|---|---|---|
| Host | `dt.smartscape.host` | `"HOST"` |
| Service | `dt.smartscape.service` | `"SERVICE"` |
| Process | `dt.smartscape.process` | `"PROCESS"` |
| K8s Cluster | `dt.smartscape.k8s_cluster` | `"K8S_CLUSTER"` |
| K8s Node | `dt.smartscape.k8s_node` | `"K8S_NODE"` |
| K8s Pod | `dt.smartscape.k8s_pod` | `"K8S_POD"` |

Use `getNodeName()` (not `entityName()`) to resolve display names from Smartscape nodes.

### 3.3 Entity Attributes

```dql
smartscapeNodes "HOST"
| fieldsAdd tags = getNodeField(dt.smartscape.host, "tags")
| filter matchesValue(tags, "env:production")
| fields getNodeName(), dt.smartscape.host, tags
```

### 3.4 Topology Navigation

Find services running on a specific host:
```dql
smartscapeEdges "HOST_TO_SERVICE"
| filter getNodeField(dt.smartscape.host, "name") == "web-host-01"
| fields getNodeField(dt.smartscape.service, "name")
```

---

## 4. Problem Investigation Workflows

Davis AI automatically detects problems that aggregate related alert events and identify root causes.

### 4.1 List Active Problems

Use the MCP tool for a structured list:
```
list_problems(status="OPEN", from="now-2h")
```

Or use DQL for custom filtering:
```dql
fetch dt.davis.problems, from: now()-2h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| fields event.start, display_id, event.name, event.category,
          dt.davis.affected_users_count, root_cause_entity_name
| sort event.start desc
| limit 20
```

**Always** filter `not(dt.davis.is_duplicate)` to remove duplicate detections.

### 4.2 Problem Field Names

| Wrong (SQL-style) | Correct DQL field | Meaning |
|---|---|---|
| `title` | `event.name` | Problem description |
| `status` | `event.status` | `ACTIVE` or `CLOSED` |
| `severity` | `event.category` | Problem type |
| `start` | `event.start` | Detection timestamp |

### 4.3 Problem Categories

| `event.category` | Meaning |
|---|---|
| `AVAILABILITY` | Service or entity unreachable |
| `ERROR` | Error rate above baseline |
| `SLOWDOWN` | Response time degraded |
| `RESOURCE` | CPU / memory / disk saturation |
| `CUSTOM` | Custom anomaly detection threshold |

### 4.4 Root Cause Identification

```dql
fetch dt.davis.problems, from: now()-2h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter isNotNull(root_cause_entity_id)
| fields display_id, event.name, root_cause_entity_name,
          root_cause_entity_id, smartscape.affected_entity.ids
| sort event.start desc
```

### 4.5 Correlate Problem with Logs

```dql
fetch logs, from: now()-2h
| filter loglevel in {"ERROR", "FATAL"}
| filter service.name == "<root-cause-service>"
| fields timestamp, content, service.name
| sort timestamp desc
| limit 50
```

### 4.6 Correlate Problem with Traces

```dql
fetch spans, from: now()-2h
| filter span.http.status_code >= 500
| filter service.name == "<root-cause-service>"
| fields timestamp, span.name, span.duration, span.http.status_code, trace.id
| sort span.duration desc
| limit 30
```

### 4.7 Blast Radius

```dql
fetch dt.davis.problems, from: now()-7d
| filter not(dt.davis.is_duplicate)
| filter isNotNull(root_cause_entity_id)
| fieldsAdd affected_count = arraySize(smartscape.affected_entity.ids)
| summarize avg_affected = avg(affected_count), max_affected = max(affected_count),
            problem_count = count(), by: {root_cause_entity_name}
| sort avg_affected desc
```

---

## 5. Log Analysis Patterns

### 5.1 Basic Log Search

```dql
fetch logs, from: now()-1h
| filter loglevel == "ERROR"
| filter matchesPhrase(content, "NullPointerException")
| fields timestamp, content, service.name, k8s.pod.name
| sort timestamp desc
| limit 50
```

### 5.2 Error Rate Over Time

```dql
fetch logs, from: now()-6h
| makeTimeseries total = count(), errors = countIf(loglevel == "ERROR"),
               interval: 5m, by: {service.name}
| fieldsAdd error_pct = errors[] * 100.0 / total[]
```

### 5.3 Top Error Messages

```dql
fetch logs, from: now()-1h
| filter loglevel == "ERROR"
| summarize count(), by: {content}
| sort `count()` desc
| limit 20
```

### 5.4 Logs by Kubernetes Namespace

```dql
fetch logs, from: now()-30m
| filter loglevel == "ERROR"
| summarize count(), by: {k8s.namespace.name, k8s.pod.name}
| sort `count()` desc
| limit 30
```

### 5.5 Parse Structured Fields from Log Content

```dql
fetch logs, from: now()-1h
| filter matchesPhrase(content, "duration_ms")
| parse content, "LD 'duration_ms=' LONG:duration_ms"
| filter duration_ms > 1000
| fields timestamp, content, duration_ms
| sort duration_ms desc
```

---

## 6. Metrics and Service Health

### 6.1 Service RED Metrics

Rate, Errors, Duration for a service:
```dql
timeseries {
  requests = sum(dt.service.request.count),
  failures = sum(dt.service.request.failure_count),
  p95_rt   = percentile(dt.service.request.response_time, 95, rollup: avg)
}, by: {dt.service.name}, from: now()-1h
| fieldsAdd error_rate = failures[] * 100.0 / requests[],
            p95_ms     = p95_rt[] / 1000
```

### 6.2 Host CPU and Memory

```dql
timeseries {
  cpu = avg(dt.host.cpu.usage),
  mem = avg(dt.host.memory.usage_percent)
}, by: {dt.smartscape.host}, from: now()-1h
| fieldsAdd avg_cpu = arrayAvg(cpu), avg_mem = arrayAvg(mem)
| filter avg_cpu > 80 or avg_mem > 80
| sort avg_cpu desc
```

### 6.3 Discover Available Metrics

```dql
metrics from: now()-1h
| filter contains(metric.key, "kubernetes")
| summarize count(), by: {metric.key}
| sort `count()` desc
| limit 30
```

---

## 7. Kubernetes Monitoring

### 7.1 K8s Operational Events

```
get_kubernetes_events(clusterName="prod-cluster", from="now-1h")
```

### 7.2 Pod Resource Usage

```dql
timeseries {
  cpu = avg(dt.kubernetes.container.cpu.usage_percent),
  mem = avg(dt.kubernetes.container.memory.usage_percent)
}, by: {k8s.namespace.name, k8s.pod.name}, from: now()-30m
| fieldsAdd avg_cpu = arrayAvg(cpu), avg_mem = arrayAvg(mem)
| filter avg_cpu > 90 or avg_mem > 90
```

### 7.3 OOMKill Events

```dql
fetch dt.davis.events, from: now()-24h
| filter event.type == "OOM_KILL"
| summarize count(), by: {k8s.namespace.name, k8s.pod.name}
| sort `count()` desc
```

---

## 8. Security Queries

### 8.1 List Critical Vulnerabilities

```
list_vulnerabilities(riskLevel="CRITICAL")
```

### 8.2 Security Events via DQL

```dql
fetch security.events, from: now()-24h
| filter vulnerability.resolution.status == "OPEN"
| filter vulnerability.risk.level == "CRITICAL"
| summarize count(), by: {vulnerability.display_id, vulnerability.title}
| sort `count()` desc
| limit 20
```

---

## 9. Notification and Workflow Patterns

### 9.1 Send an Alert to Slack

```
send_slack_message(
  channel="#sre-alerts",
  message="P-12345 ACTIVE: checkout-service error rate 15% — investigating"
)
```

### 9.2 Create a Problem Notification Workflow

```
create_workflow_for_notification(
  workflowName="critical-problems-slack",
  trigger={type: "problem", filter: "event.category == 'AVAILABILITY'"},
  notificationType="slack",
  destination="#incidents"
)
```

### 9.3 Send Investigation Summary by Email

```
send_email(
  to="team@example.com",
  subject="Incident P-12345 resolved",
  body="Root cause: memory leak in checkout-service v2.3.1. Mitigated by rollback to v2.3.0."
)
```

---

## 10. Query Cost Control

Large queries exhaust the Grail scan budget. To reduce cost:

1. **Always specify `from:`** — never omit the time range.
2. **Filter early** — put `filter` commands directly after `fetch`.
3. **Select only needed fields** — add `| fields` to drop unused columns.
4. **Use `samplingRatio:`** for exploratory queries on high-volume sources:
   ```dql
   fetch logs, from: now()-1h, samplingRatio: 100
   | filter loglevel == "ERROR"
   | summarize count = sum(dt.system.sampling_ratio), by: {service.name}
   ```
5. **Use `limit`** to cap result size during exploration.
6. **Reset the budget** if you hit scan limits:
   ```
   reset_grail_budget()
   ```

---

## 11. Common Troubleshooting Scenarios

### Query Returns No Results

1. Widen `from:` — data may not exist in the requested window.
2. Check field names — run `fetch logs | limit 1` to inspect actual field names.
3. For problems: use `event.status == "ACTIVE"` (not `"OPEN"`).
4. For `timeseries percentile`: ensure `rollup:` is set.

### Duplicate Problem Records in Results

Add `filter not(dt.davis.is_duplicate)` immediately after `fetch dt.davis.problems`.

### Entity IDs Not Resolving

Use `find_entity_by_name` to get the correct Smartscape ID, then use `toSmartscapeId()` in DQL:
```dql
fetch spans, from: now()-1h
| filter in(dt.smartscape.service, toSmartscapeId("SERVICE-ABCDEF1234567890"))
```

### Scan Budget Exhausted

Call `reset_grail_budget()`, then rerun with a narrower time window and explicit `fields` selection.

### Complex Questions

When unsure how to investigate an issue, ask Davis CoPilot:
```
chat_with_davis_copilot("What is causing the high error rate on checkout-service in the last 2 hours?")
```
