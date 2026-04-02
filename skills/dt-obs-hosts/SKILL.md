---
name: dt-obs-hosts
description: Host and process metrics including CPU, memory, disk, network, containers, and process-level telemetry. Monitor infrastructure health and resource utilization.
license: Apache-2.0
---

# Infrastructure Hosts Skill

Monitor and manage host and process infrastructure including CPU, memory, disk, network, and technology inventory.

## What This Skill Does

- Discover and inventory hosts across cloud and on-premise environments
- Monitor host resource utilization (CPU, memory, disk, network)
- Track process resource consumption and lifecycle
- Analyze container and Kubernetes infrastructure
- Discover services via listening ports
- Manage technology stack versions and compliance
- Attribute infrastructure costs by cost center and product
- Validate data quality and metadata completeness
- Plan capacity and detect resource saturation
- Correlate infrastructure health across layers

## When to Use This Skill

Use this skill when the user needs to:

- **Inventory:** "Show me all Linux hosts in AWS us-east-1"
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

→ For detailed CPU analysis, see [references/host-metrics.md](#cpu-monitoring)  
→ For memory breakdown, see [references/host-metrics.md](#memory-monitoring)

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

→ For process I/O analysis, see [references/process-monitoring.md](#process-io)  
→ For process network metrics, see [references/process-monitoring.md](#process-network)

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

→ For version compliance checks, see [references/inventory-discovery.md](#technology-inventory)

### 5. Service Discovery via Ports

Map listening ports to services for security and inventory.

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.listen_ports, dt.process_group.detected_name
| filter isNotNull(process.listen_ports) and arraySize(process.listen_ports) > 0
| expand port = process.listen_ports
| summarize process_count = count(), by: {port, dt.process_group.detected_name}
| sort toLong(port) asc
| limit 50
```

**Well-known ports:** 80 (HTTP), 443 (HTTPS), 22 (SSH), 3306 (MySQL), 5432 (PostgreSQL)

→ For comprehensive port mapping, see [references/inventory-discovery.md](#port-discovery)

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

→ For K8s version tracking, see [references/container-monitoring.md](#kubernetes-versions)  
→ For container lifecycle, see [references/container-monitoring.md](#container-inventory)

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

→ For product-level cost tracking, see [references/inventory-discovery.md](#cost-attribution)

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

→ For multi-resource saturation detection, see [references/host-metrics.md](#resource-saturation)

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

→ For complete tag reference, see [references/inventory-discovery.md](#tags-and-metadata)

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

### Kubernetes
- `k8s.cluster.name`, `k8s.cluster.uid`
- `k8s.namespace.name`, `k8s.node.name`, `k8s.pod.name`
- `k8s.workload.name`, `k8s.workload.kind`

→ For multi-cloud analysis, see [references/inventory-discovery.md](#multi-cloud-hosts)

---

## Best Practices

### Alerting
1. Use percentiles (p95, p99) for latency metrics
2. Use `max()` for resource limits
3. Use `avg()` for utilization trends
4. Set multi-level thresholds (warning at 80%, critical at 90%)

### Time Windows
- **Real-time:** 5-15 minute windows
- **Trends:** 24 hours to 7 days
- **Capacity planning:** 30-90 days

### Query Optimization
1. Use filters early in the pipeline
2. Limit results with `| limit N`
3. Use specific entity types in smartscapeNodes
4. Aggregate before enrichment (lookup)

### Data Quality
1. Validate metadata completeness (target >90%)
2. Check for duplicate host names
3. Ensure cost tag coverage
4. Monitor data freshness (lifetime.end)

---

## Limitations and Notes

### Smartscape Limitations
- Container image names/versions NOT available in smartscape
- Generic `tags` field NOT populated (use specific tag namespaces)
- Process metadata varies by process type

### Platform-Specific
- `dt.host.cpu.iowait` available on Linux only
- AIX has specific CPU metrics (entitlement, physc)
- Inode metrics available on Linux only

### Best Practices
- Use `getNodeName()` to get human-readable names
- Convert bytes to GB for readability: `/ 1024 / 1024 / 1024`
- Round aggregated values: `round(value, decimals: 1)`
- Use `isNotNull()` checks before array operations

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

---

## References

- [host-metrics.md](references/host-metrics.md) - Detailed host CPU, memory, disk, and network monitoring
- [process-monitoring.md](references/process-monitoring.md) - Process-level CPU, memory, I/O, and network analysis
- [container-monitoring.md](references/container-monitoring.md) - Container inventory, Kubernetes versions, and operator management
- [inventory-discovery.md](references/inventory-discovery.md) - Host/process discovery, technology inventory, cost attribution, and data quality

---
