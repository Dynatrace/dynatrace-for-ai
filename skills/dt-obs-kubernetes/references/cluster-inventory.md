# Kubernetes Cluster and Namespace Inventory - Reference

Deep dive into cluster and namespace inventory queries for understanding
Kubernetes topology, resource distribution, and organizational hierarchy.

## Overview

Cluster and namespace entities provide the organizational foundation for
Kubernetes resources. This reference covers comprehensive querying patterns for
cluster topology, namespace distribution, and resource organization.

## Contents

- [Cluster Queries](#cluster-queries)
  - [List All Clusters](#list-all-clusters)
  - [Cluster by Distribution](#cluster-by-distribution)
  - [Cluster Version Summary](#cluster-version-summary)
  - [Count Nodes per Cluster](#count-nodes-per-cluster)
- [Namespace Queries](#namespace-queries)
  - [List All Namespaces](#list-all-namespaces)
  - [Count Namespaces per Cluster](#count-namespaces-per-cluster)
  - [Filter System Namespaces](#filter-system-namespaces)
  - [Find Empty Namespaces](#find-empty-namespaces)
- [Resource Distribution](#resource-distribution)
  - [Count All Resources per Cluster](#count-all-resources-per-cluster)
  - [Pod Distribution per Cluster](#pod-distribution-per-cluster)
  - [Workload Distribution per Cluster](#workload-distribution-per-cluster)
  - [Namespace Resource Summary](#namespace-resource-summary)
- [Multi-Cluster Queries](#multi-cluster-queries)
  - [Compare Clusters](#compare-clusters)
  - [Find Clusters with Specific Workload](#find-clusters-with-specific-workload)
  - [Namespace Naming Patterns](#namespace-naming-patterns)
- [Cluster Health Overview](#cluster-health-overview)
  - [Cluster Entity Count](#cluster-entity-count)
  - [Clusters with Nodes](#clusters-with-nodes)
- [Namespace Analysis](#namespace-analysis)
  - [Largest Namespaces by Pod Count](#largest-namespaces-by-pod-count)
  - [Namespace Age](#namespace-age)
  - [Namespaces by Label](#namespaces-by-label)
- [Resource Organization](#resource-organization)
  - [Services per Namespace](#services-per-namespace)
  - [ConfigMaps per Namespace](#configmaps-per-namespace)
  - [Secrets per Namespace](#secrets-per-namespace)
- [Advanced Patterns](#advanced-patterns)
  - [Multi-Cluster Resource Comparison](#multi-cluster-resource-comparison)
  - [Namespace Resource Density](#namespace-resource-density)
  - [Cluster Growth Tracking](#cluster-growth-tracking)
- [Best Practices](#best-practices)
- [Related Topics](#related-topics)

## Cluster Queries

### List All Clusters

```dql
// List all Kubernetes clusters monitored by Dynatrace
smartscapeNodes K8S_CLUSTER
| fields k8s.cluster.name, k8s.cluster.uid, k8s.cluster.version, k8s.cluster.distribution
| sort k8s.cluster.name
```

### Cluster by Distribution

```dql
// Count clusters by Kubernetes distribution
smartscapeNodes K8S_CLUSTER
| summarize count(), by: {k8s.cluster.distribution}
| sort k8s.cluster.distribution
```

### Cluster Version Summary

```dql
// List clusters with their Kubernetes versions
smartscapeNodes K8S_CLUSTER
| fields k8s.cluster.name, k8s.cluster.version, k8s.cluster.distribution
| sort k8s.cluster.version desc
```

### Count Nodes per Cluster

```dql
// Count nodes in each cluster
smartscapeNodes K8S_NODE
| summarize node_count = count(), by: {k8s.cluster.name}
| sort node_count desc
```

## Namespace Queries

### List All Namespaces

```dql
// List all namespaces across all clusters
smartscapeNodes K8S_NAMESPACE
| fields k8s.cluster.name, k8s.namespace.name
| sort k8s.cluster.name, k8s.namespace.name
```

### Count Namespaces per Cluster

```dql
// Count namespaces in each cluster
smartscapeNodes K8S_NAMESPACE
| summarize namespace_count = count(), by: {k8s.cluster.name}
| sort namespace_count desc
```

### Filter System Namespaces

```dql
// List only application namespaces (exclude system)
smartscapeNodes K8S_NAMESPACE
| filterOut in(k8s.namespace.name, {"kube-system", "kube-public",
  "kube-node-lease", "dynatrace"})
| fields k8s.cluster.name, k8s.namespace.name
| sort k8s.cluster.name, k8s.namespace.name
```

### Find Empty Namespaces

```dql
// Find namespaces with no pods
// Note: Uses composite key workaround because array syntax is not supported
// in lookup fields
smartscapeNodes K8S_NAMESPACE
| fieldsAdd composite_key = concat(k8s.cluster.name, "|", k8s.namespace.name)
| lookup [
    smartscapeNodes K8S_POD
    | summarize pod_count = count(), by: {k8s.cluster.name, k8s.namespace.name}
    | fieldsAdd composite_key = concat(k8s.cluster.name, "|", k8s.namespace.name)
  ], sourceField: composite_key, lookupField: composite_key
| filter isNull(pod_count)
| fields k8s.cluster.name, k8s.namespace.name
```

## Resource Distribution

### Count All Resources per Cluster

```dql
// Count all Kubernetes resources by type per cluster
smartscapeNodes "K8S_*"
| summarize count(), by: {k8s.cluster.name, type}
| sort k8s.cluster.name, type
```

### Pod Distribution per Cluster

```dql
// Count pods per cluster
smartscapeNodes K8S_POD
| summarize pod_count = count(), by: {k8s.cluster.name}
| sort pod_count desc
```

### Workload Distribution per Cluster

```dql
// Count workloads by type per cluster
smartscapeNodes K8S_DEPLOYMENT, K8S_STATEFULSET, K8S_DAEMONSET
| summarize count(), by: {k8s.cluster.name, k8s.workload.kind}
| sort k8s.cluster.name, k8s.workload.kind
```

### Namespace Resource Summary

```dql
// Count resources per namespace
smartscapeNodes K8S_POD, K8S_DEPLOYMENT, K8S_STATEFULSET, K8S_DAEMONSET, K8S_SERVICE
| summarize resource_count = count(), by: {k8s.cluster.name, k8s.namespace.name, type}
| sort k8s.cluster.name, k8s.namespace.name, type
```

## Multi-Cluster Queries

### Compare Clusters

```dql
// Compare resource counts across clusters
smartscapeNodes K8S_POD
| summarize pod_count = count(), by: {k8s.cluster.name}
| sort pod_count desc
```

### Find Clusters with Specific Workload

```dql
// Find clusters running a specific workload
smartscapeNodes K8S_DEPLOYMENT
| filter k8s.workload.name == "nginx"
| dedup k8s.cluster.name
| sort k8s.cluster.name
```

### Namespace Naming Patterns

```dql
// Analyze namespace naming patterns
smartscapeNodes K8S_NAMESPACE
| parse k8s.namespace.name, "LD:prefix '-' LD:suffix"
| filter isNotNull(prefix)
| summarize namespace_count = count(), by: {prefix}
| sort namespace_count desc
```

## Cluster Health Overview

### Cluster Entity Count

```dql
// Get total entity count per cluster
smartscapeNodes "K8S_*"
| summarize total_entities = count(), by: {k8s.cluster.name}
| sort total_entities desc
```

### Clusters with Nodes

```dql
// Verify all clusters have active nodes
smartscapeNodes K8S_CLUSTER
| lookup [
    smartscapeNodes K8S_NODE
    | summarize node_count = count(), by: {k8s.cluster.name}
  ], sourceField: k8s.cluster.name, lookupField: k8s.cluster.name
| fields k8s.cluster.name, node_count
| sort k8s.cluster.name
```

## Namespace Analysis

### Largest Namespaces by Pod Count

```dql
// Find namespaces with most pods
smartscapeNodes K8S_POD
| summarize pod_count = count(), by: {k8s.cluster.name, k8s.namespace.name}
| sort pod_count desc
| limit 20
```

### Namespace Age

```dql
// Calculate namespace age
smartscapeNodes K8S_NAMESPACE
| fieldsAdd age_days = (now() - lifetime[start]) / 1d
| fields k8s.cluster.name, k8s.namespace.name, age_days
| sort age_days desc
```

### Namespaces by Label

```dql
// Group namespaces by environment label
smartscapeNodes K8S_NAMESPACE
| filter isNotNull(tags[environment])
| summarize namespaces = collectDistinct(k8s.namespace.name),
  by: {k8s.cluster.name, environment = tags[environment]}
| sort k8s.cluster.name, environment
```

## Resource Organization

### Services per Namespace

```dql
// Count services per namespace
smartscapeNodes K8S_SERVICE
| summarize service_count = count(), by: {k8s.cluster.name, k8s.namespace.name}
| sort service_count desc
```

### ConfigMaps per Namespace

```dql
// Count configmaps per namespace
smartscapeNodes K8S_CONFIGMAP
| summarize configmap_count = count(), by: {k8s.cluster.name, k8s.namespace.name}
| sort configmap_count desc
```

### Secrets per Namespace

```dql
// Count secrets per namespace
smartscapeNodes K8S_SECRET
| summarize secret_count = count(), by: {k8s.cluster.name, k8s.namespace.name}
| sort secret_count desc
```

## Advanced Patterns

### Multi-Cluster Resource Comparison

```dql
// Compare resource distribution across clusters
smartscapeNodes K8S_POD, K8S_DEPLOYMENT, K8S_SERVICE
| summarize count(), by: {k8s.cluster.name, type}
| fields cluster = k8s.cluster.name, resource_type = type, count = `count()`
```

### Namespace Resource Density

```dql-snippet
// Calculate resource density per namespace
smartscapeNodes K8S_POD
| summarize pod_count = count(), by: {k8s.cluster.name, k8s.namespace.name}
| lookup [
    smartscapeNodes K8S_SERVICE
    | summarize service_count = count(),
      by: {k8s.cluster.name, k8s.namespace.name}
  ], sourceField: k8s.cluster.name,
  lookupField: k8s.cluster.name
| fieldsAdd pod_to_service_ratio = pod_count / service_count
| filter isNotNull(service_count) and service_count > 0
| sort pod_to_service_ratio desc
```

### Cluster Growth Tracking

```dql
// Track new namespaces created in last 7 days
smartscapeNodes K8S_NAMESPACE
| fieldsAdd age_days = (now() - lifetime[start]) / 1d
| filter age_days <= 7
| fields k8s.cluster.name, k8s.namespace.name, age_days
| sort age_days asc
```

## Best Practices

1. **Cache Cluster List**: Store cluster names in variables for repeated
   queries:

   ```dql
   smartscapeNodes K8S_CLUSTER
   | fields cluster = k8s.cluster.name
   | summarize clusters = collectArray(cluster)
   ```

2. **Exclude System Resources**: Filter out system namespaces for
   application-focused analysis:

   ```dql
   | filterOut in(k8s.namespace.name, {"kube-system", "kube-public",
     "kube-node-lease"})
   ```

3. **Use Lookups**: Join cluster/namespace data with resource counts for
   comprehensive views

4. **Monitor Distribution**: Track resource distribution to identify overloaded
   clusters/namespaces

5. **Track Changes**: Compare entity counts over time to detect cluster
   changes

## Related Topics

- **Labels & Annotations** → `labels-annotations.md` - Filter namespaces by
  labels
- **Pod Placement** → `pod-node-placement.md` - Analyze pod distribution
  within clusters
- **Workload Queries** (documentation) - Query specific workload types
- **Entity Relationships** (documentation) - Navigate cluster topology
