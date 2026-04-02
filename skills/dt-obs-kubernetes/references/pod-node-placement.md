# Node and Pod Placement - Reference

Deep dive into pod distribution, node characteristics, scheduling constraints,
and high availability patterns in Kubernetes.

## Overview

Understanding pod distribution across nodes is critical for resource
utilization, high availability, and capacity planning. This reference covers
comprehensive analysis of node characteristics and pod placement patterns.

## Contents

- [Node Queries](#node-queries)
  - [List All Nodes](#list-all-nodes)
  - [Node Count per Cluster](#node-count-per-cluster)
  - [Find Unschedulable Nodes](#find-unschedulable-nodes)
  - [Extract Node Labels](#extract-node-labels)
  - [Node Taints Summary](#node-taints-summary)
- [Pod Distribution](#pod-distribution)
  - [Pods per Node](#pods-per-node)
  - [Pod Distribution Balance](#pod-distribution-balance)
  - [Namespace Distribution per Node](#namespace-distribution-per-node)
  - [Workload Distribution per Node](#workload-distribution-per-node)
- [Pod Placement Constraints](#pod-placement-constraints)
  - [Pods with Node Selectors](#pods-with-node-selectors)
  - [Pods with Node Affinity](#pods-with-node-affinity)
  - [Pods with Tolerations](#pods-with-tolerations)
  - [Workloads with Anti-Affinity](#workloads-with-anti-affinity)
- [Node Capacity Analysis](#node-capacity-analysis)
  - [Nodes by Availability Zone](#nodes-by-availability-zone)
  - [Nodes by Instance Type](#nodes-by-instance-type)
  - [Pod Distribution by Zone](#pod-distribution-by-zone)
- [Scheduling Analysis](#scheduling-analysis)
  - [DaemonSet Coverage](#daemonset-coverage)
  - [Pods Pending Scheduling](#pods-pending-scheduling)
  - [Single-Node Workloads (HA Risk)](#single-node-workloads-ha-risk)
- [High Availability Patterns](#high-availability-patterns)
  - [Multi-Node Deployment Verification](#multi-node-deployment-verification)
  - [Zone Distribution for Critical Apps](#zone-distribution-for-critical-apps)
  - [StatefulSet Pod Distribution](#statefulset-pod-distribution)
- [Advanced Patterns](#advanced-patterns)
  - [Node Pressure and Pod Placement](#node-pressure-and-pod-placement)
  - [Pod Spread by Topology](#pod-spread-by-topology)
- [Best Practices](#best-practices)
- [Common Issues and Solutions](#common-issues-and-solutions)
- [Related Topics](#related-topics)

## Node Queries

### List All Nodes

```dql
// List all Kubernetes nodes
smartscapeNodes K8S_NODE
| fields k8s.cluster.name, k8s.node.name
| sort k8s.cluster.name, k8s.node.name
```

### Node Count per Cluster

```dql
// Count nodes per cluster
smartscapeNodes K8S_NODE
| summarize node_count = count(), by: {k8s.cluster.name}
| sort node_count desc
```

### Find Unschedulable Nodes

```dql
// Find nodes that are unschedulable (cordoned)
smartscapeNodes K8S_NODE
| parse k8s.object, "JSON:config"
| fieldsAdd taints = config[spec][taints]
| expand taint = taints
| filter taint[key] == "node.kubernetes.io/unschedulable"
| fields k8s.cluster.name, k8s.node.name, taint[effect]
```

### Extract Node Labels

```dql
// List nodes with their labels
smartscapeNodes K8S_NODE
| parse k8s.object, "JSON:config"
| fieldsAdd labels = config[metadata][labels]
| fieldsFlatten labels, prefix: "label."
| fields k8s.cluster.name, k8s.node.name, labels
| limit 10
```

### Node Taints Summary

```dql
// Summarize all node taints across clusters
smartscapeNodes K8S_NODE
| parse k8s.object, "JSON:config"
| expand taint = config[spec][taints]
| filter isNotNull(taint)
| fieldsAdd taint_key = taint[key], taint_effect = taint[effect]
| summarize node_count = count(), by: {k8s.cluster.name, taint_key, taint_effect}
| sort k8s.cluster.name, node_count desc
```

## Pod Distribution

### Pods per Node

```dql
// Count pods running on each node
smartscapeNodes K8S_POD
| filter isNotNull(k8s.node.name)
| summarize pod_count = count(), by: {k8s.cluster.name, k8s.node.name}
| sort pod_count desc
```

### Pod Distribution Balance

```dql
// Check pod distribution balance across nodes
smartscapeNodes K8S_POD
| filter isNotNull(k8s.node.name)
| summarize pod_count = count(), by: {k8s.cluster.name, k8s.node.name}
| summarize avg_pods = avg(pod_count),
            min_pods = min(pod_count),
            max_pods = max(pod_count),
            by: {k8s.cluster.name}
| fieldsAdd imbalance_ratio = max_pods / avg_pods
| sort imbalance_ratio desc
```

**Interpretation:**

- `imbalance_ratio` near 1.0 = well-balanced
- `imbalance_ratio` > 2.0 = significant imbalance

### Namespace Distribution per Node

```dql
// Show namespace distribution across nodes
smartscapeNodes K8S_POD
| filter isNotNull(k8s.node.name)
| summarize pod_count = count(), by: {k8s.cluster.name, k8s.node.name, k8s.namespace.name}
| sort k8s.node.name, pod_count desc
```

### Workload Distribution per Node

```dql
// Show workload distribution across nodes
smartscapeNodes K8S_POD
| filter isNotNull(k8s.node.name) and isNotNull(k8s.workload.name)
| summarize pod_count = count(), by: {k8s.cluster.name, k8s.node.name, k8s.workload.name}
| sort k8s.node.name, pod_count desc
```

## Pod Placement Constraints

### Pods with Node Selectors

```dql
// Find pods using node selectors
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| fieldsAdd node_selector = config[spec][nodeSelector]
| filter isNotNull(node_selector)
| fieldsFlatten node_selector, prefix: "selector."
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, node_selector
```

**Use Case:** Identify pods with specific node placement requirements (GPU
nodes, high-memory nodes, etc.)

### Pods with Node Affinity

```dql
// Find pods with node affinity rules
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| fieldsAdd node_affinity = config[spec][affinity][nodeAffinity]
| filter isNotNull(node_affinity)
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name
```

### Pods with Tolerations

```dql
// List pods with tolerations
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| fieldsAdd tolerations = config[spec][tolerations]
| filter isNotNull(tolerations) and arraySize(tolerations) > 0
| expand toleration = tolerations
| fieldsAdd taint_key = toleration[key], taint_effect = toleration[effect]
| fields k8s.pod.name, k8s.node.name, taint_key, taint_effect
```

**Use Case:** Understand which pods can tolerate node taints (e.g., dedicated
nodes, maintenance windows)

### Workloads with Anti-Affinity

```dql
// Find workloads with pod anti-affinity rules
smartscapeNodes K8S_DEPLOYMENT, K8S_STATEFULSET
| parse k8s.object, "JSON:config"
| fieldsAdd anti_affinity =
  config[spec][template][spec][affinity][podAntiAffinity]
| filter isNotNull(anti_affinity)
| fields k8s.cluster.name, k8s.namespace.name, k8s.workload.name
```

**Use Case:** Identify workloads configured for high availability (spread
across nodes/zones)

## Node Capacity Analysis

### Nodes by Availability Zone

```dql
// Group nodes by availability zone
smartscapeNodes K8S_NODE
| parse k8s.object, "JSON:config"
| fieldsAdd zone = config[metadata][labels][`topology.kubernetes.io/zone`]
| filter isNotNull(zone)
| summarize node_count = count(), by: {k8s.cluster.name, zone}
| sort k8s.cluster.name, zone
```

### Nodes by Instance Type

```dql
// Group nodes by instance type
smartscapeNodes K8S_NODE
| parse k8s.object, "JSON:config"
| fieldsAdd instance_type = config[metadata][labels][`node.kubernetes.io/instance-type`]
| filter isNotNull(instance_type)
| summarize node_count = count(), by: {k8s.cluster.name, instance_type}
| sort k8s.cluster.name, node_count desc
```

### Pod Distribution by Zone

```dql
// Analyze pod distribution across availability zones
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| fieldsAdd node_name = config[spec][nodeName]
| lookup [
    smartscapeNodes K8S_NODE
    | parse k8s.object, "JSON:config"
    | fieldsAdd zone = config[metadata][labels][`topology.kubernetes.io/zone`]
    | fields k8s.node.name, zone
  ], sourceField: node_name, lookupField: k8s.node.name
| filter isNotNull(zone)
| summarize pod_count = count(), by: {k8s.cluster.name, zone}
| sort k8s.cluster.name, zone
```

## Scheduling Analysis

### DaemonSet Coverage

```dql
// Verify DaemonSet pods are on all nodes
// Note: Using join instead of lookup because DQL lookup doesn't merge
// aggregated fields from subqueries, causing total_nodes field to be
// inaccessible
smartscapeNodes K8S_POD
| filter k8s.workload.kind == "daemonset"
| summarize nodes_with_daemonset = countDistinct(k8s.node.name),
  by: {k8s.cluster.name, k8s.workload.name}
| join [
    smartscapeNodes K8S_NODE
    | summarize total_nodes = count(), by: {k8s.cluster.name}
  ], on: {k8s.cluster.name}, fields: {total_nodes}
| fieldsAdd coverage_pct =
  100.0 * nodes_with_daemonset / total_nodes
| filter coverage_pct < 100
| fields k8s.cluster.name, k8s.workload.name, nodes_with_daemonset,
  total_nodes, coverage_pct
```

**Use Case:** Detect DaemonSets that aren't running on all nodes (may indicate
taint/toleration issues)

### Pods Pending Scheduling

```dql
// Find pods that are pending (not scheduled to nodes)
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| fieldsAdd phase = config[status][phase]
| filter phase == "Pending" or isNull(k8s.node.name)
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, phase
```

**Common Causes:**

- Insufficient resources
- No nodes match nodeSelector/affinity
- Node taints without matching tolerations
- PVC binding issues

### Single-Node Workloads (HA Risk)

```dql
// Find workloads with all pods on one node
smartscapeNodes K8S_POD
| filter isNotNull(k8s.workload.name) and isNotNull(k8s.node.name)
| summarize pod_count = count(),
            node_count = countDistinct(k8s.node.name),
            nodes = collectDistinct(k8s.node.name),
            by: {k8s.cluster.name, k8s.namespace.name, k8s.workload.name}
| filter pod_count > 1 and node_count == 1
| fields k8s.cluster.name, k8s.namespace.name, k8s.workload.name, pod_count, nodes
```

**Action:** Review these workloads for high availability requirements

## High Availability Patterns

### Multi-Node Deployment Verification

```dql
// Verify deployments are spread across multiple nodes
smartscapeNodes K8S_POD
| filter k8s.workload.kind == "deployment"
| summarize pod_count = count(),
            node_count = countDistinct(k8s.node.name),
            by: {k8s.cluster.name, k8s.namespace.name, k8s.workload.name}
| fieldsAdd ha_compliant = node_count > 1
| filter pod_count >= 2 and not ha_compliant
| fields k8s.cluster.name, k8s.namespace.name, k8s.workload.name, pod_count, node_count
```

**Best Practice:** Deployments with 2+ replicas should span multiple nodes

### Zone Distribution for Critical Apps

```dql
// Check if critical workloads span multiple zones
smartscapeNodes K8S_POD
| filter tags[criticality] == "high"
| parse k8s.object, "JSON:config"
| fieldsAdd node_name = config[spec][nodeName]
| lookup [
    smartscapeNodes K8S_NODE
    | parse k8s.object, "JSON:config"
    | fieldsAdd zone = config[metadata][labels][`topology.kubernetes.io/zone`]
    | fields k8s.node.name, zone
  ], sourceField: node_name, lookupField: k8s.node.name
| summarize zone_count = countDistinct(zone),
            zones = collectDistinct(zone),
            by: {k8s.cluster.name, k8s.workload.name}
| fields k8s.cluster.name, k8s.workload.name, zone_count, zones
```

**Best Practice:** Critical apps should span 2+ availability zones

### StatefulSet Pod Distribution

```dql
// Analyze StatefulSet pod placement
smartscapeNodes K8S_POD
| filter k8s.workload.kind == "statefulset"
| summarize pod_count = count(),
  node_count = countDistinct(k8s.node.name),
  nodes = collectDistinct(k8s.node.name),
  by: {k8s.cluster.name, k8s.namespace.name, k8s.workload.name}
| fields k8s.cluster.name, k8s.namespace.name, k8s.workload.name, pod_count,
  node_count, nodes
```

## Advanced Patterns

### Node Pressure and Pod Placement

```dql
// Correlate node resource pressure with pod count
timeseries {
  cpu_usage = sum(dt.kubernetes.container.cpu_usage),
  pod_count = avg(dt.kubernetes.pods)
}, by: {k8s.node.name, k8s.cluster.name}
| fieldsAdd avg_cpu = arrayAvg(cpu_usage),
            avg_pods = arrayAvg(pod_count)
| filter avg_cpu > 70000000000
| sort avg_cpu desc
```

### Pod Spread by Topology

```dql
// Analyze pod spread using topology spread constraints
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| fieldsAdd spread_constraints = config[spec][topologySpreadConstraints]
| filter isNotNull(spread_constraints) and arraySize(spread_constraints) > 0
| expand constraint = spread_constraints
| fieldsAdd topology_key = constraint[topologyKey],
            max_skew = constraint[maxSkew]
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, topology_key, max_skew
```

## Best Practices

1. **Monitor Balance**: Regularly check pod distribution to avoid node hotspots
   - Target: `imbalance_ratio` < 1.5

2. **Verify HA**: Ensure critical workloads span multiple nodes and
   zones
   - Production deployments: 2+ nodes, 2+ zones
   - StatefulSets: Consider node anti-affinity

3. **Track Taints**: Monitor node taints to understand scheduling
   constraints
   - Document custom taints and their purpose
   - Ensure DaemonSets have appropriate tolerations

4. **Check Pending Pods**: Regularly query for pending pods to detect
   scheduling issues
   - Set up alerts for pods pending > 5 minutes
   - Review nodeSelector/affinity rules

5. **Validate DaemonSets**: Verify DaemonSet coverage across all applicable
   nodes
   - Expect 100% coverage unless using node selectors
   - Check for taint/toleration mismatches

6. **Zone Awareness**: Use topology spread constraints for critical
   applications
   - Prefer `topologySpreadConstraints` over deprecated
     `podAntiAffinity`
   - Target even distribution across zones

## Common Issues and Solutions

| Issue | Query to Detect | Solution |
| ----- | --------------- | -------- |
| Pod hotspots | Pod Distribution Balance query | Add anti-affinity rules |
| Pending pods | Pods Pending Scheduling query | Check resources/taints |
| Single-zone deployment | Zone Distribution query | Add spread constraints |
| DaemonSet gaps | DaemonSet Coverage query | Add tolerations |
| HA violations | Multi-Node Deployment Verification | Add anti-affinity |

## Related Topics

- **Cluster Inventory** → `cluster-inventory.md` - Understand cluster topology
- **Labels & Annotations** → `labels-annotations.md` - Use labels for node selection
- **Node Resources** (documentation) - Monitor node capacity and utilization
- **Pod Lifecycle** (documentation) - Investigate pod failures and restarts
