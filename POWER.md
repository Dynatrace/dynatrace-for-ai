---
name: "dynatrace-for-ai"
displayName: "Dynatrace for AI"
description: "Query and analyze Dynatrace telemetry — logs, traces, metrics, problems, and security events — directly from Kiro using the Dynatrace MCP server and DQL. Includes 30+ curated observability skills covering Kubernetes, cloud providers, services, and Davis AI problem analysis. Requires a Dynatrace environment URL and a platform token."
keywords: ["dynatrace", "dql", "grail", "davis", "smartscape", "oneagent", "bizevents", "timeseries", "mcp-gateway", "vulnerabilities"]
author: "Dynatrace"
---

# Dynatrace for AI

Connect Kiro to your Dynatrace environment to query telemetry, investigate Davis AI–detected problems, analyze logs, run DQL queries, and receive notifications — all without leaving your IDE.

## Key Capabilities

| Capability | Tools |
|---|---|
| Run DQL queries against Grail | `execute_dql` |
| Generate DQL from natural language | `generate_dql_from_natural_language` |
| Investigate Davis AI problems | `list_problems`, `chat_with_davis_copilot` |
| Search entities by name | `find_entity_by_name` |
| Query security vulnerabilities | `list_vulnerabilities` |
| Monitor Kubernetes events | `get_kubernetes_events` |
| Send Slack / email notifications | `send_slack_message`, `send_email` |
| Create alerting workflows | `create_workflow_for_notification` |
| Inspect environment metadata | `get_environment_info` |
| Reset Grail query budget | `reset_grail_budget` |

The Power also loads 30+ observability skills that guide the agent on DQL syntax, field namespaces, entity types, and domain-specific query patterns for services, logs, traces, Kubernetes, AWS, Azure, GCP, and security.

---

## Authentication Setup

### 1. Locate your Dynatrace environment URL

Open your Dynatrace tenant. The URL in the browser bar is your `DT_ENVIRONMENT`. It has the form:

```
https://<env-id>.apps.dynatrace.com
```

Include the `https://` prefix. Do **not** add a trailing slash.

### 2. Create a platform token

1. In Dynatrace, go to **Settings → Access tokens** (or use the platform **Account** app).
2. Click **Generate new token**.
3. Give it a descriptive name, for example `kiro-mcp`.
4. Enable the following token scopes:

| Scope | Required for |
|---|---|
| `storage:logs:read` | Log queries |
| `storage:events:read` | Davis event queries |
| `storage:spans:read` | Distributed trace queries |
| `storage:metrics:read` | Metric timeseries queries |
| `storage:bizevents:read` | Business event queries |
| `storage:system:read` | System / data-object discovery |
| `storage:buckets:read` | Bucket enumeration |
| `environment-api:problems:read` | Problem listing via `list_problems` |
| `environment-api:entities:read` | Entity lookup via `find_entity_by_name` |
| `security:events:read` | Vulnerability queries |
| `DataExport` | Grail query execution |

5. Click **Generate token** and copy the value. You cannot view it again after closing the dialog.

### 3. Set environment variables

Add the two variables to your Kiro or shell environment:

```bash
export DT_ENVIRONMENT=https://<env-id>.apps.dynatrace.com
export DT_PLATFORM_TOKEN=<your-token-here>
```

For persistent configuration, add them to your shell profile (`~/.bashrc`, `~/.zshrc`) or to Kiro's environment settings.

### 4. Verify the connection

Ask Kiro:

> "What is my Dynatrace environment?"

The `get_environment_info` tool runs and returns the tenant name, version, and capabilities. If it fails, verify that `DT_ENVIRONMENT` includes `https://` and that the token has at least `storage:system:read`.

---

## Tool Reference

### `execute_dql`

Run a DQL (Dynatrace Query Language) query against Grail.

| Parameter | Type | Description |
|---|---|---|
| `query` | string | The DQL query string |
| `defaultTimeframeStart` | string | ISO 8601 start (optional) |
| `defaultTimeframeEnd` | string | ISO 8601 end (optional) |
| `maxResultRecords` | integer | Row limit (optional, default 1000) |

**Returns:** Query result rows as a record set, plus metadata (scanned bytes, execution time).

**Example:**
```dql
fetch logs, from: now()-1h
| filter loglevel == "ERROR"
| summarize count(), by: {k8s.namespace.name}
| sort `count()` desc
| limit 10
```

---

### `generate_dql_from_natural_language`

Convert a natural-language question into a valid DQL query without running it.

| Parameter | Type | Description |
|---|---|---|
| `prompt` | string | Natural-language description of the query |

**Returns:** A DQL query string ready to pass to `execute_dql`.

---

### `explain_dql`

Explain what an existing DQL query does in plain language.

| Parameter | Type | Description |
|---|---|---|
| `query` | string | The DQL query to explain |

**Returns:** A human-readable explanation of each pipeline stage.

---

### `verify_dql`

Validate a DQL query for syntax errors without executing it.

| Parameter | Type | Description |
|---|---|---|
| `query` | string | The DQL query to check |

**Returns:** Validation result — valid, or a list of syntax errors with positions.

---

### `find_entity_by_name`

Search Dynatrace entities (hosts, services, processes, clusters) by display name.

| Parameter | Type | Description |
|---|---|---|
| `entityName` | string | Full or partial entity name |
| `entityType` | string | Optional filter — e.g. `HOST`, `SERVICE`, `K8S_CLUSTER` |

**Returns:** Matching entities with Smartscape IDs, names, and types.

---

### `get_environment_info`

Return metadata about the connected Dynatrace environment.

| Parameter | Type | Description |
|---|---|---|
| *(none)* | — | — |

**Returns:** Tenant name, environment ID, Dynatrace version, and enabled capabilities.

---

### `list_problems`

List Davis AI–detected problems for a time range.

| Parameter | Type | Description |
|---|---|---|
| `from` | string | Start time (ISO 8601 or relative, e.g. `now-2h`) |
| `to` | string | End time (optional, defaults to now) |
| `status` | string | `OPEN` or `CLOSED` (optional) |
| `entitySelector` | string | Dynatrace entity selector (optional) |

**Returns:** Problem list with IDs, titles, categories, status, and affected entity counts.

---

### `chat_with_davis_copilot`

Send a question or task to Davis CoPilot, Dynatrace's AI assistant, and return its response.

| Parameter | Type | Description |
|---|---|---|
| `message` | string | The question or instruction |

**Returns:** Davis CoPilot's natural-language response, including any DQL it suggests.

---

### `list_vulnerabilities`

List open security vulnerabilities detected by Dynatrace Runtime Vulnerability Analytics.

| Parameter | Type | Description |
|---|---|---|
| `from` | string | Start time for detection window (optional) |
| `riskLevel` | string | Filter by risk — `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` (optional) |

**Returns:** Vulnerability list with CVE IDs, affected components, risk scores, and entity context.

---

### `get_kubernetes_events`

Retrieve Kubernetes operational events (pod restarts, OOMKills, evictions) from Grail.

| Parameter | Type | Description |
|---|---|---|
| `clusterName` | string | K8s cluster name (optional) |
| `namespace` | string | Namespace filter (optional) |
| `from` | string | Start time (optional) |

**Returns:** K8s event records with reason, object, message, and timestamps.

---

### `send_email`

Send an email notification.

| Parameter | Type | Description |
|---|---|---|
| `to` | string | Recipient email address |
| `subject` | string | Email subject |
| `body` | string | Email body (plain text or HTML) |

**Returns:** Delivery confirmation.

---

### `send_slack_message`

Post a message to a Slack channel.

| Parameter | Type | Description |
|---|---|---|
| `channel` | string | Slack channel name or ID |
| `message` | string | Message text (Markdown supported) |

**Returns:** Delivery confirmation with message timestamp.

---

### `create_workflow_for_notification`

Create a Dynatrace Workflow that sends notifications when a problem or alert fires.

| Parameter | Type | Description |
|---|---|---|
| `workflowName` | string | Display name for the workflow |
| `trigger` | object | Trigger definition (problem, event, schedule) |
| `notificationType` | string | `slack`, `email`, or `webhook` |
| `destination` | string | Channel, address, or URL |

**Returns:** Workflow ID and configuration URL.

---

### `reset_grail_budget`

Reset the Grail query scan budget for the current session to avoid hitting scan limits during heavy investigation sessions.

| Parameter | Type | Description |
|---|---|---|
| *(none)* | — | — |

**Returns:** Confirmation that the budget was reset.

---

## Multi-Step Workflow Examples

### Workflow 1 — Investigate an Active Production Incident

**Goal:** Identify the root cause of an active problem and correlate it with logs and traces.

**Step 1 — List active problems**
```
list_problems(status="OPEN", from="now-2h")
```
Pick the problem ID with the highest affected-user count.

**Step 2 — Get problem details with DQL**
```dql
fetch dt.davis.problems, from: now()-2h
| filter display_id == "P-XXXXXXXXXX"
| fields event.name, event.category, root_cause_entity_name,
          smartscape.affected_entity.ids, dt.davis.affected_users_count
```

**Step 3 — Correlate with error logs**
```dql
fetch logs, from: now()-2h
| filter loglevel == "ERROR"
| filter contains(k8s.namespace.name, "<namespace>")
| summarize count(), by: {content}
| sort `count()` desc
| limit 20
```

**Step 4 — Check failing spans**
```dql
fetch spans, from: now()-2h
| filter span.http.status_code >= 500
| filter service.name == "<service>"
| summarize count(), by: {span.name, span.http.status_code}
| sort `count()` desc
```

**Step 5 — Notify on-call**
```
send_slack_message(channel="#on-call", message="P-XXXXX active: <summary>")
```

---

### Workflow 2 — Kubernetes Health Check

**Goal:** Check cluster capacity and identify pods in a bad state.

**Step 1 — Get K8s events**
```
get_kubernetes_events(clusterName="prod-cluster", from="now-1h")
```

**Step 2 — Check node pressure**
```dql
timeseries {
  cpu = avg(dt.kubernetes.node.cpu.usage_percent),
  mem = avg(dt.kubernetes.node.memory.usage_percent)
}, by: {dt.smartscape.k8s_node}, from: now()-30m
| fieldsAdd avg_cpu = arrayAvg(cpu), avg_mem = arrayAvg(mem)
| filter avg_cpu > 80 or avg_mem > 80
```

**Step 3 — Find OOMKill events**
```dql
fetch dt.davis.events, from: now()-1h
| filter event.type == "OOM_KILL"
| summarize count(), by: {k8s.namespace.name, k8s.pod.name}
| sort `count()` desc
```

**Step 4 — Ask Davis CoPilot for remediation advice**
```
chat_with_davis_copilot("Cluster prod-cluster has nodes above 80% CPU. What should I check and what actions do you recommend?")
```

---

### Workflow 3 — Service Performance Regression After Deployment

**Goal:** Detect whether a recent deployment degraded service latency.

**Step 1 — Compare p95 before vs. after deployment**
```dql
timeseries p95 = percentile(dt.service.request.response_time, 95, rollup: avg),
           by: {dt.service.name}, from: now()-4h
| fieldsAdd pre  = arrayAvg(arraySlice(p95, 0, arraySize(p95)/2)),
            post = arrayAvg(arraySlice(p95, arraySize(p95)/2, arraySize(p95)))
| filter post > pre * 1.2
| sort post desc
```

**Step 2 — Find slow spans introduced after deployment**
```dql
fetch spans, from: now()-2h
| filter span.duration > 5s
| filter service.name == "<service>"
| fields timestamp, span.name, span.duration, trace.id
| sort span.duration desc
| limit 20
```

**Step 3 — Look for new error patterns in logs**
```dql
fetch logs, from: now()-2h
| filter loglevel == "ERROR"
| filter service.name == "<service>"
| summarize count(), by: {content}
| sort `count()` desc
| limit 15
```

---

## DQL Cheat-Sheet

### Data Sources

| Source | Command | Key Fields |
|---|---|---|
| Logs | `fetch logs` | `content`, `loglevel`, `k8s.*`, `host.*` |
| Spans / Traces | `fetch spans` | `span.*`, `service.*`, `http.*`, `db.*` |
| Davis Problems | `fetch dt.davis.problems` | `display_id`, `event.name`, `event.status` |
| Davis Events | `fetch dt.davis.events` | `event.*`, `dt.smartscape.*` |
| Business Events | `fetch bizevents` | `event.type`, custom fields |
| Security Events | `fetch security.events` | `vulnerability.*`, `event.*` |
| RUM Sessions | `fetch user.sessions` | `dt.rum.*`, `browser.*`, `geo.*` |
| Metrics | `timeseries avg(metric.key)` | Use `timeseries`, **not** `fetch` |
| Topology | `smartscapeNodes "HOST"` | Use `smartscapeNodes`, **not** `fetch` |

### Common Syntax Pitfalls

| Wrong | Correct | Reason |
|---|---|---|
| `filter x in ["a","b"]` | `filter in(x, {"a","b"})` | `[]` wraps sub-queries; `{}` for static sets |
| `event.status == "OPEN"` | `event.status == "ACTIVE"` | Davis uses ACTIVE / CLOSED |
| `filter host = "A"` | `filter host == "A"` | `=` is assignment, `==` is comparison |
| `log.level == "ERROR"` | `loglevel == "ERROR"` | Field is `loglevel`, no dot |
| `by: severity, status` | `by: {severity, status}` | `by:` requires curly braces |
| `metrics dt.host.cpu.usage` | `timeseries avg(dt.host.cpu.usage)` | `metrics` = discovery, `timeseries` = values |
| `sort count() desc` | `` sort `count()` desc `` | Backtick fields whose names contain `()` |
| `dt.entity.host` | `dt.smartscape.host` | `dt.entity.*` is deprecated |
| `length(x)` | `stringLength(x)` | No `length()` function in DQL |

### Time Range Examples

```dql
-- Last hour
fetch logs, from: now()-1h

-- Yesterday complete
fetch logs, from: now()-1d@d, to: now()@d

-- Absolute range (double quotes required)
fetch logs, from: "2026-09-20T10:00:00Z", to: "2026-09-20T11:00:00Z"

-- This month so far
fetch bizevents, from: now()@M
```

### Key Aggregation Patterns

```dql
-- Count by field
| summarize count(), by: {service.name}

-- Error rate
| summarize total = count(), errors = countIf(loglevel == "ERROR")
| fieldsAdd error_pct = (errors * 100.0) / total

-- Metric timeseries with percentile (rollup: required)
timeseries p95 = percentile(dt.service.request.response_time, 95, rollup: avg),
           by: {dt.service.name}

-- Timeseries-to-scalar
timeseries cpu = avg(dt.host.cpu.usage), by: {dt.smartscape.host}
| fieldsAdd avg_cpu = arrayAvg(cpu), max_cpu = arrayMax(cpu)
```

### Entity ID Reference

| Entity | ID Field in DQL | `smartscapeNodes` Type |
|---|---|---|
| Host | `dt.smartscape.host` | `"HOST"` |
| Service | `dt.smartscape.service` | `"SERVICE"` |
| Process | `dt.smartscape.process` | `"PROCESS"` |
| K8s Cluster | `dt.smartscape.k8s_cluster` | `"K8S_CLUSTER"` |

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `get_environment_info` fails | Missing `https://` in `DT_ENVIRONMENT` | Add `https://` prefix; remove trailing slash |
| All queries return 0 rows | Token missing `storage:*:read` scopes | Regenerate token with all required scopes listed above |
| `list_problems` returns empty | Wrong time range or all problems closed | Widen `from:`; omit `status` filter to see both |
| DQL syntax error on `filter x in [...]` | `[]` is sub-query syntax | Use `{}` for static value lists |
| `timeseries` with `percentile` returns empty | Missing `rollup:` parameter | Add `rollup: avg` (or `min` / `max`) to the aggregation |
| Scan budget exhausted | Query scans too much data | Narrow `from:`/`to:`; add `samplingRatio:`; call `reset_grail_budget` |
| `find_entity_by_name` returns nothing | Name mismatch or wrong type filter | Try a shorter partial name; omit `entityType` |
| `dt.entity.*` fields in a DQL query | Deprecated field namespace | Replace with `dt.smartscape.*` equivalents |
