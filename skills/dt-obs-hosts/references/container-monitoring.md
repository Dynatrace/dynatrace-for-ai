# Container Monitoring Reference

Container inventory, Kubernetes version management, and operator tracking with comprehensive lifecycle analysis.

**Important Note:** Container image names and versions are NOT available in smartscape queries. Use container names and Kubernetes workload information for identification.

---

## Container Inventory

### All Containers Overview

Fetch all containers with basic information:

```dql
smartscapeNodes "CONTAINER"
| fieldsAdd name, k8s.cluster.name, k8s.namespace.name, k8s.workload.name
| sort name asc
| limit 100
```

Returns container instances with their Kubernetes context.

### Kubernetes Container Distribution

Analyze container distribution across Kubernetes clusters:

```dql
smartscapeNodes "CONTAINER"
| filter isNotNull(k8s.cluster.name)
| fieldsAdd k8s.cluster.name, k8s.namespace.name
| summarize
    container_count = count(),
    namespaces = countDistinct(k8s.namespace.name),
    by: {k8s.cluster.name}
| sort container_count desc
```

### Containers by Workload Type

Group containers by Kubernetes workload kind:

```dql
smartscapeNodes "CONTAINER"
| filter isNotNull(k8s.workload.kind)
| fieldsAdd k8s.workload.kind
| summarize container_count = count(), by: {k8s.workload.kind}
| sort container_count desc
```

**Workload Types:**
- `daemonset`: Node-level services
- `deployment`: Standard deployments
- `statefulset`: Stateful applications
- `job`: Batch jobs
- `cronjob`: Scheduled tasks
- `replicaset`: Replica sets

### Containers by Namespace

List containers grouped by Kubernetes namespace:

```dql
smartscapeNodes "CONTAINER"
| filter isNotNull(k8s.namespace.name)
| fieldsAdd k8s.namespace.name, k8s.cluster.name
| summarize container_count = count(), by: {k8s.cluster.name, k8s.namespace.name}
| sort k8s.cluster.name, container_count desc
```

### Container Workload Distribution

Analyze workloads across clusters:

```dql
smartscapeNodes "CONTAINER"
| filter isNotNull(k8s.workload.name)
| fieldsAdd k8s.cluster.name, k8s.workload.name, k8s.workload.kind
| summarize container_count = count(), by: {k8s.cluster.name, k8s.workload.name, k8s.workload.kind}
| sort k8s.cluster.name, container_count desc
| limit 100
```

### Containers on Specific Nodes

Find containers running on particular Kubernetes nodes:

```dql
smartscapeNodes "CONTAINER"
| filter isNotNull(k8s.node.name)
| fieldsAdd k8s.node.name, k8s.pod.name, name
| summarize container_count = count(), by: {k8s.node.name}
| sort container_count desc
```

**Use Case:** Identify node resource distribution and imbalances.

### Containers by Pod

Group containers within pods:

```dql
smartscapeNodes "CONTAINER"
| filter isNotNull(k8s.pod.name)
| fieldsAdd k8s.pod.name, k8s.namespace.name, name, k8s.container.name
| summarize container_count = count(), by: {k8s.pod.name, k8s.namespace.name}
| filter container_count > 1
| sort container_count desc
```

**Pattern:** Multi-container pods (sidecar pattern, init containers).

### Container Lifetime Analysis

Analyze container age and churn:

```dql-snippet
smartscapeNodes "CONTAINER"
| fieldsAdd name, lifetime, k8s.workload.name
| fieldsAdd
    age_hours = toDuration(timeframe(lifetime[start], to: now())),
    is_active = isNull(lifetime[end])
| summarize
    total_containers = count(),
    active_containers = countIf(is_active),
    avg_age_hours = avg(age_hours),
    by: {k8s.workload.name}
| fieldsAdd avg_age_hours = round(avg_age_hours, decimals: 1)
| sort total_containers desc
| limit 20
```

### Short-Lived Containers

Identify ephemeral containers that terminated quickly:

```dql
smartscapeNodes "CONTAINER"
| fieldsAdd name, lifetime, k8s.pod.name
| filter isNotNull(lifetime[end])
| fieldsAdd lifespan_minutes = duration(lifetime[start], lifetime[end])
| filter lifespan_minutes < 10m
| sort lifespan_minutes asc
| limit 50
```

**Alert:** Very short-lived containers may indicate crash loops or failed init containers.

### Container Density per Cluster

Calculate container density across clusters:

```dql
smartscapeNodes "CONTAINER"
| filter isNotNull(k8s.cluster.name)
| fieldsAdd k8s.cluster.name, k8s.node.name
| summarize
    container_count = count(),
    node_count = countDistinct(k8s.node.name),
    by: {k8s.cluster.name}
| fieldsAdd containers_per_node = round(toDouble(container_count) / toDouble(node_count), decimals: 1)
| sort containers_per_node desc
```

---

## Kubernetes Versions

### Kubernetes Version Distribution

List all Kubernetes versions across worker nodes:

```dql
smartscapeNodes "HOST"
| fieldsAdd process.software_technologies
| filter isNotNull(process.software_technologies)
| expand tech = process.software_technologies
| filter tech[type] == "KUBERNETES"
| fieldsAdd k8s_version = tech[version], k8s_edition = tech[edition]
| summarize host_count = count(), by: {k8s_version, k8s_edition}
| sort k8s_version desc, k8s_edition
```

**Use Case:** Identify deployed Kubernetes versions and plan upgrades.

### Kubernetes Version by Cluster

Group Kubernetes versions by cluster:

```dql
smartscapeNodes "HOST"
| filter isNotNull(k8s.cluster.name)
| fieldsAdd process.software_technologies, k8s.cluster.name
| expand tech = process.software_technologies
| filter tech[type] == "KUBERNETES"
| fieldsAdd k8s_version = tech[version]
| summarize
    host_count = count(),
    versions = collectDistinct(k8s_version),
    by: {k8s.cluster.name}
| sort k8s.cluster.name
```

**Pattern:** Each cluster should have consistent K8s versions across nodes.

### Version Skew Detection

Identify clusters with version skew (mixed versions):

```dql
smartscapeNodes "HOST"
| filter isNotNull(k8s.cluster.name)
| fieldsAdd process.software_technologies, k8s.cluster.name
| expand tech = process.software_technologies
| filter tech[type] == "KUBERNETES" and tech[edition] == "worker"
| fieldsAdd k8s_version = tech[version]
| summarize
    version_count = countDistinct(k8s_version),
    versions = collectDistinct(k8s_version),
    host_count = count(),
    by: {k8s.cluster.name}
| filter version_count > 1
| sort version_count desc, host_count desc
```

**Alert:** Version skew indicates incomplete cluster upgrades or configuration drift.

### Master vs Worker Version Comparison

Compare control plane and worker node versions:

```dql
smartscapeNodes "HOST"
| fieldsAdd process.software_technologies, k8s.cluster.name
| expand tech = process.software_technologies
| filter tech[type] == "KUBERNETES"
| fieldsAdd k8s_version = tech[version], k8s_edition = tech[edition]
| summarize host_count = count(), by: {k8s.cluster.name, k8s_edition, k8s_version}
| sort k8s.cluster.name, k8s_edition, k8s_version desc
```

**Best Practice:** Control plane should be same version or one minor version ahead of workers.

### Outdated Kubernetes Versions

Identify hosts running EOL or outdated K8s versions:

```dql
smartscapeNodes "HOST"
| fieldsAdd process.software_technologies, k8s.cluster.name, name
| expand tech = process.software_technologies
| filter tech[type] == "KUBERNETES"
| fieldsAdd k8s_version = tech[version]
| filter k8s_version < "1.30.0" or isNull(k8s_version)
| summarize host_count = count(), by: {k8s.cluster.name, k8s_version}
| sort k8s_version asc
```

**Security:** Older versions may have unpatched vulnerabilities.

### Kubernetes Version Upgrade Candidates

List clusters eligible for upgrade:

```dql
smartscapeNodes "HOST"
| filter isNotNull(k8s.cluster.name)
| fieldsAdd process.software_technologies, k8s.cluster.name
| expand tech = process.software_technologies
| filter tech[type] == "KUBERNETES" and tech[edition] == "worker"
| fieldsAdd k8s_version = tech[version]
| summarize
    current_version = takeFirst(k8s_version),
    host_count = count(),
    by: {k8s.cluster.name}
| filter current_version < "1.32.0"
| sort current_version asc
```

**Planning:** Prioritize clusters with older versions for upgrades.

### Kubernetes Version Compliance Rate

Calculate compliance rate against target version:

```dql
smartscapeNodes "HOST"
| fieldsAdd process.software_technologies
| expand tech = process.software_technologies
| filter tech[type] == "KUBERNETES" and tech[edition] == "worker"
| fieldsAdd k8s_version = tech[version]
| fieldsAdd
    is_compliant = k8s_version >= "1.32.0"
| summarize
    total_hosts = count(),
    compliant_hosts = countIf(is_compliant),
    non_compliant = countIf(not is_compliant)
| fieldsAdd compliance_rate = round((toDouble(compliant_hosts) / toDouble(total_hosts)) * 100, decimals: 1)
```

---

## OneAgent Operator Management

### Operator Version Distribution

List all operator versions across hosts:

```dql
smartscapeNodes "HOST"
| fieldsAdd operator_version = host.custom.metadata[OperatorVersion]
| filter isNotNull(operator_version)
| summarize host_count = count(), by: {operator_version}
| sort host_count desc
```

**Use Case:** Identify which operator versions are deployed and plan upgrades.

### Operator Version by Cloud Provider

Analyze operator versions across cloud providers:

```dql
smartscapeNodes "HOST"
| fieldsAdd operator_version = host.custom.metadata[OperatorVersion], cloud.provider
| filter isNotNull(operator_version)
| summarize host_count = count(), by: {operator_version, cloud.provider}
| sort operator_version desc, host_count desc
```

**Pattern:** Check if different cloud providers run different operator versions.

### Operator Version by Cluster

Group operator versions by Kubernetes cluster:

```dql
smartscapeNodes "HOST"
| filter isNotNull(k8s.cluster.name)
| fieldsAdd operator_version = host.custom.metadata[OperatorVersion], k8s.cluster.name
| filter isNotNull(operator_version)
| summarize host_count = count(), by: {k8s.cluster.name, operator_version}
| sort k8s.cluster.name, operator_version desc
```

**Use Case:** Cluster-by-cluster upgrade planning.

### Outdated Operator Versions

Identify hosts running older operator versions:

```dql
smartscapeNodes "HOST"
| fieldsAdd operator_version = host.custom.metadata[OperatorVersion], name, k8s.cluster.name
| filter isNotNull(operator_version)
| filter operator_version != "v1.6.3" and operator_version != "v1.7.1"
| sort operator_version, k8s.cluster.name
```

**Alert:** Target specific version for upgrades (adjust filter based on latest version).

### Operator Version Consistency Check

Find clusters with mixed operator versions:

```dql
smartscapeNodes "HOST"
| filter isNotNull(k8s.cluster.name)
| fieldsAdd operator_version = host.custom.metadata[OperatorVersion], k8s.cluster.name
| filter isNotNull(operator_version)
| summarize
    versions = collectDistinct(operator_version),
    version_count = countDistinct(operator_version),
    host_count = count(),
    by: {k8s.cluster.name}
| filter version_count > 1
| sort version_count desc, host_count desc
```

**Alert:** Clusters with multiple operator versions indicate incomplete rollouts.

### Operator Upgrade Progress Tracking

Monitor upgrade progress by comparing versions:

```dql
smartscapeNodes "HOST"
| fieldsAdd operator_version = host.custom.metadata[OperatorVersion]
| filter isNotNull(operator_version)
| fieldsAdd
    version_category = if(operator_version == "v1.7.1", "latest",
                      else: if(operator_version == "v1.6.3", "current",
                      else: "legacy"))
| summarize host_count = count(), by: {version_category}
| sort version_category desc
```

### Hosts Without Operator Version

Identify hosts missing operator version metadata:

```dql
smartscapeNodes "HOST"
| filter isNotNull(k8s.cluster.name)
| fieldsAdd operator_version = host.custom.metadata[OperatorVersion], name, k8s.cluster.name
| filter isNull(operator_version)
| sort k8s.cluster.name, name
```

**Data Quality:** Hosts in K8s clusters should have operator versions.

---

## Cloud-Specific Container Analysis

### AWS EKS Container Distribution

Analyze containers in AWS EKS clusters:

```dql
smartscapeNodes "CONTAINER"
| fieldsAdd k8s.cluster.name, k8s.namespace.name
| lookup [
    smartscapeNodes HOST
    | filter cloud.provider == "aws"
    | fields id, cloud.provider, aws.region
  ], sourceField:references[runs_on.host], lookupField:id
| filter isNotNull(cloud.provider)
| summarize container_count = count(), by: {k8s.cluster.name, aws.region}
| sort container_count desc
```

### Azure AKS Container Distribution

Analyze containers in Azure AKS clusters:

```dql
smartscapeNodes "CONTAINER"
| fieldsAdd k8s.cluster.name, k8s.namespace.name
| lookup [
    smartscapeNodes HOST
    | filter cloud.provider == "azure"
    | fields id, cloud.provider, azure.location
  ], sourceField:references[runs_on.host], lookupField:id
| filter isNotNull(cloud.provider)
| summarize container_count = count(), by: {k8s.cluster.name, azure.location}
| sort container_count desc
```

---

## Related Documentation

For host inventory and discovery, see [inventory-discovery.md](inventory-discovery.md).  
For process monitoring, see [process-monitoring.md](process-monitoring.md).  
For host resource metrics, see [host-metrics.md](host-metrics.md).
