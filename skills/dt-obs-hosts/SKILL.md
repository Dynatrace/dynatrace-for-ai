---
name: dt-obs-hosts
description: >-
  Host and process metrics including CPU, memory, disk, network, containers, and process-level
  telemetry. Use when analyzing infrastructure health, resource utilization, process consumption,
  or host discovery. Also use when building timeseries queries for host metrics that feed into
  analytical workflows like anomaly detection, forecasting, or seasonality analysis.
  Trigger: "show hosts", "CPU usage", "memory utilization", "disk space", "high CPU",
  "top hosts by CPU", "top processes by memory",
  "Linux hosts in AWS", "what databases are running", "infrastructure costs by cost center",
  "hosts running EOL Java", "container monitoring", "listening ports",
  "process resource consumption", "CPU forecast", "memory anomaly", "host seasonality",
  "OneAgent mode", "OneAgent version", "GCP hosts".
  Do NOT use for explaining existing queries, product documentation questions,
  Kubernetes pod/workload queries (use dt-obs-kubernetes), AWS cloud resource inventory
  (use dt-obs-aws), or service-level metrics (use dt-obs-services).
license: Apache-2.0
---

# Infrastructure Hosts Skill

Monitor and manage host and process infrastructure including CPU, memory, disk, network, and technology inventory.

## When to Use This Skill

Use this skill when the user needs to:

- **Inventory:** "Show me all Linux hosts in AWS us-east-1"
- **Agent Inventory:** "Which hosts run FULL_STACK, INFRASTRUCTURE, or DISCOVERY mode?" / "Show OneAgent version distribution"
- **Monitor:** "What hosts have high CPU usage?"
- **Troubleshoot:** "Which processes are consuming the most memory?"
- **Discover:** "What databases are running in production?"
- **Plan:** "Track Kubernetes version distribution for upgrade planning"
- **Cost:** "Calculate infrastructure costs by cost center"
- **Security:** "Find all processes listening on port 22"
- **Compliance:** "Identify hosts running EOL Java versions"
- **Quality:** "Check data completeness for AWS hosts"
- **Optimize:** "Find rightsizing candidates based on utilization"

---
> **Cross-source join required:** If the query must combine host data with logs or other
> telemetry sources (e.g. "show logs from Linux hosts with their IP addresses") → also read
> `dt-dql-essentials/references/smartscape-topology-navigation.md` before writing the query.
---

## Core Concepts

### Entities
- **HOST** - Physical or virtual machines (cloud or on-premise)
- **PROCESS** - Running processes and process groups
- **CONTAINER** - Kubernetes containers
- **NETWORK_INTERFACE** - Host network interfaces
- **DISK** - Host disk volumes

### Metrics Categories
1. **Host Metrics** - `dt.host.cpu.*`, `dt.host.memory.*`, `dt.host.disk.*`, `dt.host.net.*`
2. **Process Metrics** - `dt.process.cpu.*`, `dt.process.memory.*`, `dt.process.io.*`, `dt.process.network.*`
3. **Inventory** - OS type, cloud provider, technology stack, versions
4. **Cost** - `dt.cost.costcenter`, `dt.cost.product`
5. **Quality** - Metadata completeness, version compliance

### Alert Thresholds
- **CPU/Memory/Disk:** 80% warning, 90% critical
- **Network:** >70% high, >85% saturated
- **Disk Latency:** >20ms bottleneck
- **Network Errors:** Drop rate >1%, error rate >0.1%
- **Swap:** >30% warning, >50% critical

---

## Key Workflows

### 1. Host Discovery and Classification

Discover hosts, classify by OS/cloud, inventory resources.

```dql
smartscapeNodes "HOST"
| fieldsAdd os.type, cloud.provider, host.logical.cpu.cores, host.physical.memory
| summarize host_count = count(), by: {os.type, cloud.provider}
| sort host_count desc
```

**OS Types:** `LINUX`, `WINDOWS`, `AIX`, `SOLARIS`, `ZOS`

→ For cloud-specific attributes, see [references/inventory-discovery.md](#cloud-specific-attributes)

### 2. Resource Utilization Monitoring

Monitor CPU, memory, disk, network across hosts.

```dql
timeseries {
  cpu = avg(dt.host.cpu.usage),
  memory = avg(dt.host.memory.usage),
  disk = avg(dt.host.disk.used.percent)
}, by: {dt.smartscape.host}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| filter arrayAvg(cpu) > 80 or arrayAvg(memory) > 80
| sort arrayAvg(cpu) desc
```

**High utilization threshold:** 80% warning, 90% critical

**Key CPU Metrics:**
- `dt.host.cpu.usage` — Total CPU utilization (0-100%)
- `dt.host.cpu.idle` — CPU idle time (inverse of usage; useful for anomaly detection)
- `dt.host.cpu.user` — CPU time in user mode
- `dt.host.cpu.system` — CPU time in kernel mode
- `dt.host.cpu.iowait` — CPU waiting for I/O (Linux only)

→ For detailed CPU analysis, see [references/host-metrics.md](references/host-metrics.md#cpu-monitoring)  
→ For memory breakdown, see [references/host-metrics.md](references/host-metrics.md#memory-monitoring)

#### Disk Free Space — Find Hosts with Most/Least Free Disk

```dql
timeseries disk_used_pct = avg(dt.host.disk.used.percent), by: {dt.smartscape.host}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| fieldsAdd avg_disk_used = arrayAvg(disk_used_pct),
    free_pct = 100 - arrayAvg(disk_used_pct)
| sort free_pct desc
| limit 10
```

### 3. Process Resource Analysis

Identify top resource consumers at process level.

```dql
timeseries {
  cpu = avg(dt.process.cpu.usage),
  memory = avg(dt.process.memory.usage)
}, by: {dt.smartscape.process}
| fieldsAdd process_name = getNodeName(dt.smartscape.process)
| filter arrayAvg(cpu) > 50
| sort arrayAvg(cpu) desc
| limit 20
```

→ For process I/O analysis, see [references/process-monitoring.md](references/process-monitoring.md#process-io)  
→ For process network metrics, see [references/process-monitoring.md](references/process-monitoring.md#process-network)

### 4. Technology Stack Inventory

Discover and track software technologies and versions.

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.software_technologies
| expand tech = process.software_technologies
| fieldsAdd tech_type = tech[type], tech_version = tech[version]
| summarize process_count = count(), by: {tech_type, tech_version}
| sort process_count desc
```

**Common Technologies:** Java, Node.js, Python, .NET, databases, web servers, messaging systems

→ For version compliance checks, see [references/inventory-discovery.md](references/inventory-discovery.md#technology-inventory)

### 5. Service Discovery via Ports

Map listening ports to services for security and inventory.

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.listen_ports, dt.process_group.detected_name
| filter isNotNull(process.listen_ports) and arraySize(process.listen_ports) > 0
| expand listen_port = process.listen_ports
| summarize process_count = count(), by: {listen_port, dt.process_group.detected_name}
| sort toLong(listen_port) asc
| limit 50
```

**Well-known ports:** 80 (HTTP), 443 (HTTPS), 22 (SSH), 3306 (MySQL), 5432 (PostgreSQL)

→ For comprehensive port mapping, see [references/inventory-discovery.md](references/inventory-discovery.md#port-discovery)

### 6. Container and Kubernetes Monitoring

Track container distribution and K8s workload types.

```dql
smartscapeNodes "CONTAINER"
| fieldsAdd k8s.cluster.name, k8s.namespace.name, k8s.workload.kind
| summarize container_count = count(), by: {k8s.cluster.name, k8s.workload.kind}
| sort k8s.cluster.name, container_count desc
```

**Workload Types:** `deployment`, `daemonset`, `statefulset`, `job`, `cronjob`

**Note:** Container image names/versions NOT available in smartscape.

→ For K8s version tracking, see [references/container-monitoring.md](references/container-monitoring.md#kubernetes-versions)  
→ For container lifecycle, see [references/container-monitoring.md](references/container-monitoring.md#container-inventory)

### 7. Cost Attribution and Chargeback

Calculate infrastructure costs by cost center.

```dql
smartscapeNodes "HOST"
| fieldsAdd dt.cost.costcenter, host.logical.cpu.cores, host.physical.memory
| filter isNotNull(dt.cost.costcenter)
| fieldsAdd memory_gb = toDouble(host.physical.memory) / 1024 / 1024 / 1024
| summarize 
    host_count = count(),
    total_cores = sum(toLong(host.logical.cpu.cores)),
    total_memory_gb = sum(memory_gb),
    by: {dt.cost.costcenter}
| sort total_cores desc
```

→ For product-level cost tracking, see [references/inventory-discovery.md](references/inventory-discovery.md#cost-attribution)

### 8. Infrastructure Health Correlation

Correlate host and process metrics for cross-layer analysis.

```dql
timeseries {
  host_cpu = avg(dt.host.cpu.usage),
  host_memory = avg(dt.host.memory.usage),
  process_cpu = avg(dt.process.cpu.usage)
}, by: {dt.smartscape.host, dt.smartscape.process}
| fieldsAdd
    host_name = getNodeName(dt.smartscape.host),
    process_name = getNodeName(dt.smartscape.process)
| filter arrayAvg(host_cpu) > 70
| sort arrayAvg(host_cpu) desc
```

**Health scoring:** Critical if any resource >90%, warning if >80%

→ For multi-resource saturation detection, see [references/host-metrics.md](references/host-metrics.md#resource-saturation)

### 9. OneAgent Inventory

Count and list hosts by OneAgent monitoring mode, version, or cloud region.

**ONEAGENT entity:** OneAgent is a separate smartscape entity type (`smartscapeNodes "ONEAGENT"`). Access it by traversing backward from HOST via the `monitors` edge (the edge runs ONEAGENT → HOST, so HOST→ONEAGENT is `direction: backward`).

**Key ONEAGENT fields:**
- `dt.agent.monitoring_mode` — monitoring coverage level: `FULL_STACK` / `INFRASTRUCTURE` / `DISCOVERY`
- `dt.agent.module.version` — installed version string, e.g. `1.347.0.20260809-172428`

**Count by monitoring mode:**

```dql
smartscapeNodes "HOST"
| traverse edgeTypes: {monitors}, targetTypes: {ONEAGENT}, direction: backward
| fieldsAdd oa_mode = `dt.agent.monitoring_mode`
| summarize host_count = count(), by: {oa_mode}
| sort host_count desc
```

**Count by agent version:**

```dql
smartscapeNodes "HOST"
| traverse edgeTypes: {monitors}, targetTypes: {ONEAGENT}, direction: backward
| fieldsAdd oa_version = `dt.agent.module.version`
| summarize host_count = count(), by: {oa_version}
| sort host_count desc
```

**Combined: mode + version** (for upgrade planning):

```dql
smartscapeNodes "HOST"
| traverse edgeTypes: {monitors}, targetTypes: {ONEAGENT}, direction: backward
| fieldsAdd oa_mode = `dt.agent.monitoring_mode`, oa_version = `dt.agent.module.version`
| summarize host_count = count(), by: {oa_mode, oa_version}
| sort host_count desc
```

**Monitoring modes:** `FULL_STACK` (full code-level monitoring + infrastructure), `INFRASTRUCTURE` (infrastructure metrics only, no code-level monitoring), `DISCOVERY` (topology discovery and basic host monitoring)

→ For listing hosts by mode/version, see [references/inventory-discovery.md](references/inventory-discovery.md#oneagent-inventory)

---

## Response Construction

When the user asks for data retrieval or a DQL query (e.g., "show me top hosts by
CPU"), **include the DQL query in the response** alongside the results. Users want to
see and reuse the query — it is the deliverable, not just a means to get results.

When the user asks for analysis (anomaly detection, forecasting, seasonality), the
analysis results are the deliverable. Focus on presenting findings clearly:
- **Prioritize metric-level findings** over data collection artifacts. If an analysis
  tool reports data gaps alongside actual anomalies, lead with the metric behavior
  the user asked about and mention gaps only as supplementary context.
- **Include host names** (not just IDs) using `getNodeName(dt.smartscape.host)` or the
  `get-entity-name` tool.
- **State the timeframe** analyzed and the tools/parameters used.

---

## Analytical Workflows

Host metric queries often serve as inputs to analytical tools (anomaly detection,
forecasting, seasonality analysis). This skill helps construct the right DQL query;
the actual analysis is performed by dedicated tools.

### Anomaly Detection and Pattern Analysis

When users ask about "unusual behavior", "anomalies", "spikes", or "sudden changes"
in host metrics, the workflow is:

1. **Construct the timeseries query** using this skill's patterns
2. **Pass it to the appropriate analysis tool** (anomaly detector, novelty detection)

**Choosing between detectors:**
- **`adaptive-anomaly-detector`** — use when the user asks about *magnitude*: "spikes",
  "abrupt changes", "values that went above normal", "sudden jumps". It answers "did this
  metric cross an unexpected threshold?" and reports alert durations and peak values.
- **`timeseries-novelty-detection`** — use when the user asks about *behavioral change*:
  "unusual patterns", "something changed", "trends", "new behavior". It answers "did the
  shape of the signal change?" without implying a specific threshold was crossed.

**Response format for anomaly results:** Include both the host **name** (resolved via
`getNodeName(dt.smartscape.host)` or `get-entity-name`) and the host **entity ID** alongside timestamps and values.
Entity IDs alone are opaque to users; names alone prevent follow-up queries.

**Novelty type selection rule:** When using novelty detection, set
`analysisNoveltyType` to only `[SPIKE, CHANGE_IN_VALUES, TREND_IN_VALUES]` by default.
**EXCLUDE** `GAP_WITH_MISSING_VALUES` and `CHANGE_IN_MISSING_VALUES` unless the user
explicitly asks about data gaps or monitoring coverage. Data gaps are infrastructure
issues, not metric behavior anomalies — reporting them when the user asks about CPU
or memory patterns is incorrect.

Queries for analysis tools should use simple `timeseries` format with a single
aggregated metric and appropriate time range:

```dql
timeseries avg(dt.host.cpu.idle), by: {dt.smartscape.host}
```

```dql
timeseries avg(dt.host.memory.usage), by: {dt.smartscape.host}
```

Avoid adding filters or field transformations that reduce the data — the analysis
tools work best with complete timeseries data.


### Forecasting

When users ask to "predict", "forecast", or "estimate future" host metrics:

1. **Construct the timeseries query** with sufficient historical data (e.g., 7d for
   short-term, 30d for longer predictions)
2. **Pass to the forecasting tool** with the desired forecast horizon

The **forecast horizon** (how far ahead to predict) and the **historical window** (how much
past data the model trains on) are independent. A request like "forecast the next 2 hours"
sets the horizon to 2h — it says nothing about the lookback. Always use at least 7 days of
historical data regardless of how short the forecast horizon is. Too few training data points
cause the forecast model to fail and fall back to raw historical values.

```dql
timeseries avg(dt.host.cpu.usage), by: {dt.smartscape.host}
```

### Seasonality Detection

When users ask about "seasonality", "weekly patterns", or "recurring behavior":

1. **Use a longer time range** (at least 14d for weekly, 30d+ for monthly)
2. **Pass to the seasonal baseline anomaly detector**

**Response format for seasonal analysis:** When presenting results, include:
- Whether seasonal anomalies were detected (yes/no)
- The analysis timeframe and parameters used
- For each affected host: host name (not just ID), timestamps of violations, violation
  counts, baseline values vs actual values, and upper/lower bounds
- Organize results by host if multiple hosts are involved

### Scope Boundary — Service-Level vs Host-Level Metrics

This skill covers **host and process infrastructure metrics only**. If the user asks
about service-level metrics (request rate, response time, error rate, service calls per
minute, throughput), use `dt-obs-services` instead — even when the question involves
forecasting or anomaly detection of those metrics.

**Redirect these to `dt-obs-services`:** "service calls per minute", "request rate",
"response time by service", "error rate by endpoint", "service throughput forecast".

---

## Common Query Patterns

### Pattern 1: Smartscape Discovery
Use `smartscapeNodes` to discover and classify entities.
```dql-template
smartscapeNodes "HOST"
| fieldsAdd <attributes>
| filter <conditions>
| summarize <aggregations>
```

### Pattern 2: Timeseries Performance
Use `timeseries` to analyze metrics over time.
```dql-template
timeseries metric = avg(dt.host.<metric>), by: {dt.smartscape.host}
| fieldsAdd <calculations>
| filter <thresholds>
```

### Pattern 3: Cross-Layer Correlation
Correlate host and process metrics.
```dql
timeseries {
  host_cpu = avg(dt.host.cpu.usage),
  process_cpu = avg(dt.process.cpu.usage)
}, by: {dt.smartscape.host, dt.smartscape.process}
```

### Pattern 4: Entity Enrichment with Lookup
Enrich data with entity attributes. After `lookup`, reference fields with `lookup.` prefix.
```dql
timeseries cpu = avg(dt.host.cpu.usage), by: {dt.smartscape.host}
| lookup [
    smartscapeNodes HOST
    | fields id, cpuCores, memoryTotal
  ], sourceField:dt.smartscape.host, lookupField:id
| fieldsAdd cores = lookup.cpuCores, mem_gb = lookup.memoryTotal / 1024 / 1024 / 1024
```

---

## Tags and Metadata

### Important Notes
- Generic `tags` field is NOT populated in smartscape queries
- Use specific tag fields: `tags:azure[*]`, `tags:environment`
- Use custom metadata: `host.custom.metadata[*]`

### Available Tags
- **Azure Tags:** `tags:azure[dt_owner_team]`, `tags:azure[dt_cloudcost_capability]`
- **Environment:** `tags:environment`
- **Custom Metadata:** `host.custom.metadata[OperatorVersion]`, `host.custom.metadata[Cluster]`
- **Cost:** `dt.cost.costcenter`, `dt.cost.product`

→ For complete tag reference, see [references/inventory-discovery.md](references/inventory-discovery.md#tags-and-metadata)

---

## Cloud-Specific Attributes

### AWS
- `cloud.provider == "aws"`
- `aws.region`, `aws.availability_zone`, `aws.account.id`
- `aws.resource.id`, `aws.resource.name`
- `aws.state` (running, stopped, terminated)

### Azure
- `cloud.provider == "azure"`
- `azure.location`, `azure.subscription`, `azure.resource.group`
- `azure.status`, `azure.provisioning_state`
- `azure.resource.sku.name` (VM size)

### GCP
- `cloud.provider == "gcp"`
- `gcp.region`, `gcp.zone`, `gcp.location`
- `gcp.project.id` (note: two dots)
- `gcp.resource.type` (e.g. `gce_instance`), `gcp.asset.type` (e.g. `compute.googleapis.com/Instance`)

### Kubernetes
- `k8s.cluster.name`, `k8s.cluster.uid`
- `k8s.namespace.name`, `k8s.node.name`, `k8s.pod.name`
- `k8s.workload.name`, `k8s.workload.kind`

→ For multi-cloud analysis, see [references/inventory-discovery.md](references/inventory-discovery.md#multi-cloud-hosts)

---

## Best Practices

1. Use percentiles (p95, p99) for latency; `max()` for limits; `avg()` for trends
2. Set multi-level thresholds (warning 80%, critical 90%)
3. Filter early in the pipeline; limit results with `| limit N`
4. Aggregate before enrichment (lookup)
5. Use `getNodeName(dt.smartscape.host)` for human-readable host names; `getNodeName(dt.smartscape.process)` for processes
6. Convert bytes to GB: `/ 1024 / 1024 / 1024`; round with `round(value, decimals: 1)`

**Time windows:** Real-time: 5-15 min | Trends: 1-7 days | Capacity planning: 30-90 days

### Limitations
- `dt.host.cpu.iowait` available on Linux only
- Generic `tags` field NOT populated in smartscape (use specific tag namespaces)
- Container image names NOT available in smartscape

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| No hosts returned from `smartscapeNodes "HOST"` | Missing time range or OneAgent not deployed | Verify OneAgent is installed; add a time range to the query |
| `tags` field always empty | Generic `tags` not populated in smartscape | Use specific tag namespaces: `tags:azure[*]`, `tags:environment`, `dt.cost.costcenter` |
| Memory values in bytes are unreadable | Raw metric unit is bytes | Divide by `1024 / 1024 / 1024` and use `round(value, decimals: 1)` |
| `dt.host.cpu.iowait` returns no data | Metric is Linux-only | Check `os.type`; iowait is unavailable on Windows, AIX, Solaris |
| Container image names missing | Not available in smartscape | Use `k8s.object` parsing for image details; see dt-obs-kubernetes skill |
| `process.software_technologies` is empty | Process not monitored by deep code-level monitoring | Verify OneAgent deep monitoring is enabled for the process group |
| `dt.agent.monitoring_mode` always null | Field name uses underscore, not dot | Use `dt.agent.monitoring_mode`; `dt.agent.monitoring.mode` (dot) always returns null |
| `gcp.project.id` always null | Wrong field name used | GCP project uses two dots: `gcp.project.id` not underscore, `gcp.project_id` always returns null |

---

## When to Load References

This skill uses **progressive disclosure**. Start here for 80% of use cases. Load reference files for detailed specifications when needed.

### Load host-metrics.md when:
- Analyzing CPU component breakdown (user, system, iowait, steal)
- Investigating memory pressure and swap usage
- Troubleshooting disk I/O latency
- Diagnosing network packet drops or errors

### Load process-monitoring.md when:
- Analyzing process-level I/O patterns
- Investigating TCP connection quality
- Detecting resource exhaustion (file descriptors, threads)
- Tracking GC suspension time

### Load container-monitoring.md when:
- Analyzing container lifecycle and churn
- Tracking Kubernetes version distribution
- Managing OneAgent operator versions
- Planning K8s cluster upgrades

### Load inventory-discovery.md when:
- Performing security audits via port discovery
- Implementing cost attribution and chargeback
- Validating data quality and metadata completeness
- Managing multi-cloud infrastructure
- Listing or filtering hosts by OneAgent mode/version

---

## References

- [host-metrics.md](references/host-metrics.md) - Detailed host CPU, memory, disk, and network monitoring
- [process-monitoring.md](references/process-monitoring.md) - Process-level CPU, memory, I/O, and network analysis
- [container-monitoring.md](references/container-monitoring.md) - Container inventory, Kubernetes versions, and operator management
- [inventory-discovery.md](references/inventory-discovery.md) - Host/process discovery, technology inventory, cost attribution, and data quality

---
