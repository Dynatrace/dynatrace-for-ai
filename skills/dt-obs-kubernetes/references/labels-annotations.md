# Kubernetes Labels and Annotations - Reference

Deep dive into using Kubernetes labels and annotations for filtering,
organizing, and managing K8s resources in Dynatrace DQL.

## Overview

Kubernetes labels and annotations are exposed in Dynatrace smartscape entities
through the `tags` array. These metadata fields enable powerful filtering,
organization, and compliance tracking of K8s resources.

## Contents

- [Accessing Labels and Annotations](#accessing-labels-and-annotations)
- [Basic Query Patterns](#basic-query-patterns)
  - [Filter by Label](#filter-by-label)
  - [Filter by Multiple Labels](#filter-by-multiple-labels)
  - [Find Resources with Label Present](#find-resources-with-label-present)
  - [Find Resources Missing Label](#find-resources-missing-label)
- [Grouping and Aggregation](#grouping-and-aggregation)
  - [Group by Label Value](#group-by-label-value)
  - [List All Label Values](#list-all-label-values)
  - [Summarize by Label Presence](#summarize-by-label-presence)
  - [Multi-Cluster Label Analysis](#multi-cluster-label-analysis)
- [Pattern Matching and Validation](#pattern-matching-and-validation)
  - [Filter with Label Pattern Matching](#filter-with-label-pattern-matching)
  - [Find Mismatched Labels](#find-mismatched-labels)
  - [Multi-Value Label Filtering](#multi-value-label-filtering)
- [Compliance and Standards](#compliance-and-standards)
  - [Check for Required Labels](#check-for-required-labels)
  - [Label Coverage Report](#label-coverage-report)
  - [Find Non-Compliant Resources](#find-non-compliant-resources)
- [Annotation-Specific Queries](#annotation-specific-queries)
  - [Filter by Annotation](#filter-by-annotation)
  - [Find Annotated Services](#find-annotated-services)
  - [Extract Documentation Annotations](#extract-documentation-annotations)
- [Namespace Label Queries](#namespace-label-queries)
  - [Access Namespace Labels](#access-namespace-labels)
  - [Namespace Label Propagation Check](#namespace-label-propagation-check)
- [Cost and Ownership Tracking](#cost-and-ownership-tracking)
  - [Cost Center Allocation](#cost-center-allocation)
  - [Team Ownership Mapping](#team-ownership-mapping)
  - [Environment Resource Distribution](#environment-resource-distribution)
- [Advanced Patterns](#advanced-patterns)
  - [Conditional Label Logic](#conditional-label-logic)
  - [Label-Based Resource Correlation](#label-based-resource-correlation)
  - [Label Migration Detection](#label-migration-detection)
- [Label Naming Conventions](#label-naming-conventions)
  - [Standard Kubernetes Labels](#standard-kubernetes-labels)
  - [Common Custom Labels](#common-custom-labels)
  - [Common Annotations](#common-annotations)
- [Best Practices](#best-practices)
  - [Query Best Practices](#query-best-practices)
  - [Labeling Standards](#labeling-standards)
- [Common Use Cases](#common-use-cases)
- [Troubleshooting](#troubleshooting)
  - [Label Not Found](#label-not-found)
  - [Special Characters in Labels](#special-characters-in-labels)
- [Related Topics](#related-topics)

## Accessing Labels and Annotations

### Syntax

Labels and annotations are accessed using the `tags` field with the key name:

**Simple keys:**

```dql-snippet
tags[app]
tags[environment]
tags[version]
```

**Keys with special characters (dots, slashes):**

```dql-snippet
tags[`app.kubernetes.io/name`]
tags[`prometheus.io/scrape`]
tags[`example.com/annotation`]
```

**Key Types:**

- **Labels**: Standard Kubernetes labels → `tags[label_key]`
- **Annotations**: Kubernetes annotations → `tags[annotation_key]`

Both are accessed the same way in DQL.

## Basic Query Patterns

### Filter by Label

```dql
// Find pods with specific label
smartscapeNodes K8S_POD
| filter tags[app] == "checkout-service"
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name
```

### Filter by Multiple Labels

```dql
// Find pods matching multiple labels
smartscapeNodes K8S_POD
| filter tags[app] == "frontend" and tags[environment] == "production"
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name
```

### Find Resources with Label Present

```dql
// Find deployments that have a specific label set
smartscapeNodes K8S_DEPLOYMENT
| filter isNotNull(tags[version])
| fields k8s.cluster.name, k8s.namespace.name, k8s.workload.name, tags[version]
```

### Find Resources Missing Label

```dql
// Find deployments without owner label
smartscapeNodes K8S_DEPLOYMENT
| filter isNull(tags[owner])
| fields k8s.cluster.name, k8s.namespace.name, k8s.workload.name
```

**Use Case:** Identify resources that don't comply with labeling standards

## Grouping and Aggregation

### Group by Label Value

```dql
// Count pods by application label
smartscapeNodes K8S_POD
| filter isNotNull(tags[app])
| summarize pod_count = count(), by: {k8s.cluster.name, app_label = tags[app]}
| sort pod_count desc
```

### List All Label Values

```dql
// Find all unique values for environment label
smartscapeNodes K8S_DEPLOYMENT, K8S_STATEFULSET
| filter isNotNull(tags[environment])
| summarize by: {environment = tags[environment]}, count()
| sort environment
```

**Use Case:** Discover what values are being used for a label across your infrastructure

### Summarize by Label Presence

```dql
// Count workloads by presence of monitoring label
smartscapeNodes K8S_DEPLOYMENT, K8S_STATEFULSET
| fieldsAdd has_monitoring = if(isNotNull(tags[monitoring]), "yes", else: "no")
| summarize count(), by: {k8s.cluster.name, has_monitoring}
```

### Multi-Cluster Label Analysis

```dql
// Compare label usage across clusters
smartscapeNodes K8S_POD
| filter isNotNull(tags[tier])
| summarize pod_count = count(), by: {k8s.cluster.name, tier = tags[tier]}
| sort k8s.cluster.name, pod_count desc
```

## Pattern Matching and Validation

### Filter with Label Pattern Matching

```dql
// Find pods with labels starting with specific prefix
smartscapeNodes K8S_POD
| filter matchesPhrase(tags[app], "payment-*")
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, tags[app]
```

### Find Mismatched Labels

```dql
// Find pods where app and service labels don't match
smartscapeNodes K8S_POD
| filter isNotNull(tags[app]) and isNotNull(tags[service])
| filter tags[app] != tags[service]
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name,
         tags[app], tags[service]
```

**Use Case:** Detect labeling inconsistencies

### Multi-Value Label Filtering

```dql
// Find pods with label in set of values
smartscapeNodes K8S_POD
| filter in(tags[tier], {"frontend", "backend", "database"})
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, tier = tags[tier]
| sort tier
```

## Compliance and Standards

### Check for Required Labels

```dql
// Find deployments missing required labels
smartscapeNodes K8S_DEPLOYMENT
| filter isNull(tags[owner]) or isNull(tags[team]) or isNull(tags[`cost-center`])
| fields k8s.cluster.name, k8s.namespace.name, k8s.workload.name,
         owner = tags[owner], team = tags[team], cost_center = tags[`cost-center`]
```

**Use Case:** Enforce organizational labeling policies

### Label Coverage Report

```dql
// Report on label coverage across deployments
smartscapeNodes K8S_DEPLOYMENT
| fieldsAdd
    has_owner = isNotNull(tags[owner]),
    has_team = isNotNull(tags[team]),
    has_environment = isNotNull(tags[environment]),
    has_version = isNotNull(tags[version])
| summarize
    total = count(),
    with_owner = countIf(has_owner),
    with_team = countIf(has_team),
    with_environment = countIf(has_environment),
    with_version = countIf(has_version),
    by: {k8s.cluster.name}
| fieldsAdd
    owner_pct = 100.0 * with_owner / total,
    team_pct = 100.0 * with_team / total,
    environment_pct = 100.0 * with_environment / total,
    version_pct = 100.0 * with_version / total
```

### Find Non-Compliant Resources

```dql
// Find resources not following naming conventions
smartscapeNodes K8S_POD
| filter isNotNull(tags[app])
| filter not matchesPhrase(tags[app], "*-service")
  and not matchesPhrase(tags[app], "*-worker")
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, tags[app]
```

## Annotation-Specific Queries

### Filter by Annotation

```dql
// Find pods with Prometheus scraping enabled
smartscapeNodes K8S_POD
| filter tags[`prometheus.io/scrape`] == "true"
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name,
         tags[`prometheus.io/port`], tags[`prometheus.io/path`]
```

### Find Annotated Services

```dql
// Find services with specific cloud provider annotation
smartscapeNodes K8S_SERVICE
| filter tags[`service.beta.kubernetes.io/aws-load-balancer-type`] == "nlb"
| fields k8s.cluster.name, k8s.namespace.name, k8s.service.name
```

### Extract Documentation Annotations

```dql
// Find resources with documentation annotations
smartscapeNodes K8S_DEPLOYMENT, K8S_STATEFULSET
| filter isNotNull(tags[`description`])
| fields k8s.cluster.name, k8s.namespace.name, k8s.workload.name,
         description = tags[`description`]
```

## Namespace Label Queries

### Access Namespace Labels

```dql
// Query namespaces by labels
smartscapeNodes K8S_NAMESPACE
| filter tags[environment] == "production"
| fields k8s.cluster.name, k8s.namespace.name, tags[environment], tags[team]
```

### Namespace Label Propagation Check

```dql
// Check if pods inherit namespace labels
smartscapeNodes K8S_POD
| filter k8s.namespace.name == "production-app"
| lookup [
    smartscapeNodes K8S_NAMESPACE
    | fields k8s.namespace.name, ns_env = tags[environment]
  ], sourceField: k8s.namespace.name, lookupField: k8s.namespace.name
| fieldsAdd pod_env = tags[environment]
| filter ns_env != pod_env
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, ns_env, pod_env
```

## Cost and Ownership Tracking

### Cost Center Allocation

```dql
// Aggregate pod count by cost center
smartscapeNodes K8S_POD
| filter isNotNull(tags[`cost-center`])
| summarize pod_count = count(), by: {cost_center = tags[`cost-center`]}
| sort pod_count desc
```

### Team Ownership Mapping

```dql
// Map resources to owning teams
smartscapeNodes K8S_DEPLOYMENT, K8S_STATEFULSET
| filter isNotNull(tags[team])
| summarize workload_count = count(), by: {k8s.cluster.name, team = tags[team]}
| sort k8s.cluster.name, workload_count desc
```

### Environment Resource Distribution

```dql
// Count resources per environment
smartscapeNodes K8S_POD
| filter isNotNull(tags[environment])
| summarize pod_count = count(), by: {environment = tags[environment], k8s.cluster.name}
| sort environment, pod_count desc
```

## Advanced Patterns

### Conditional Label Logic

```dql
// Classify workloads by label patterns
smartscapeNodes K8S_DEPLOYMENT
| fieldsAdd workload_class = if(
    matchesPhrase(tags[app], "*-api"), "API",
    else: if(matchesPhrase(tags[app], "*-worker"), "Worker",
    else: if(matchesPhrase(tags[app], "*-frontend"), "Frontend",
    else: "Unknown"))
  )
| summarize count(), by: {k8s.cluster.name, workload_class}
```

### Label-Based Resource Correlation

```dql
// Correlate pods with their parent workload labels
smartscapeNodes K8S_POD
| filter isNotNull(k8s.workload.name)
| lookup [
    smartscapeNodes K8S_DEPLOYMENT, K8S_STATEFULSET
    | fields k8s.workload.name, workload_env = tags[environment]
  ], sourceField: k8s.workload.name, lookupField: k8s.workload.name
| fieldsAdd pod_env = tags[environment]
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, pod_env, workload_env
```

### Label Migration Detection

```dql
// Find resources using deprecated labels
smartscapeNodes K8S_POD
| filter isNotNull(tags[app]) and isNull(tags[`app.kubernetes.io/name`])
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name,
         old_label = tags[app]
```

**Use Case:** Track migration from legacy label keys to recommended keys

## Label Naming Conventions

### Standard Kubernetes Labels

**Recommended label keys (kubernetes.io namespace):**

- `app.kubernetes.io/name` - Application name
- `app.kubernetes.io/instance` - Unique instance name
- `app.kubernetes.io/version` - Application version
- `app.kubernetes.io/component` - Component in the architecture
- `app.kubernetes.io/part-of` - Higher-level application name
- `app.kubernetes.io/managed-by` - Tool managing the operation

### Common Custom Labels

**Application labels:**

- `app` - Application name (legacy, prefer app.kubernetes.io/name)
- `version` - Application version
- `component` - Application component

**Organizational labels:**

- `environment` - Deployment environment (dev, staging, prod)
- `owner` - Owning team or individual
- `team` - Team responsible for the resource
- `cost-center` - Cost allocation identifier

**Infrastructure labels:**

- `tier` - Application tier (frontend, backend, database)
- `criticality` - Business criticality (high, medium, low)
- `region` - Geographic region

### Common Annotations

**Kubernetes annotations:**

- `kubernetes.io/created-by` - Creator information
- `kubernetes.io/description` - Resource description

**Tool-specific annotations:**

- `prometheus.io/scrape` - Enable Prometheus scraping
- `prometheus.io/port` - Metrics port
- `prometheus.io/path` - Metrics endpoint path

**Cloud provider annotations:**

- `service.beta.kubernetes.io/aws-load-balancer-type` - AWS LB type
- `service.beta.kubernetes.io/azure-load-balancer-internal` - Azure internal LB

## Best Practices

### Query Best Practices

1. **Use Backticks for Special Characters**: Always wrap keys with dots or
   slashes in backticks

   ```dql
   tags[``app.kubernetes.io/name``]
   tags[``prometheus.io/scrape``]
   ```

2. **Check for Null**: Use `isNotNull()` before accessing label values to
   avoid errors

   ```dql
   | filter isNotNull(tags[app])
   | fields tags[app]
   ```

3. **Filter Early**: Apply label filters immediately after entity selection
   for better performance

   ```dql
   smartscapeNodes K8S_POD
   | filter tags[environment] == "production"  // Early filter
   | parse k8s.object, "JSON:config"           // Then parse
   ```

4. **Use Summarize for Aggregations**: Group by labels efficiently

   ```dql
   | summarize count(), by: {app = tags[app], env = tags[environment]}
   ```

### Labeling Standards

1. **Consistent Naming**: Use standardized label keys across your organization
   - Document required vs. optional labels
   - Use domain prefixes for custom labels: `mycompany.io/label`

2. **Label Hierarchy**: Establish clear label hierarchy
   - Namespace-level: environment, team, cost-center
   - Workload-level: app, version, component
   - Pod-level: instance, replica

3. **Validation**: Implement label validation at deployment time
   - Use admission webhooks
   - Regular audits with compliance queries

4. **Documentation**: Use annotations for human-readable documentation
   - `description` - What the resource does
   - `contact` - Who to contact for issues
   - `runbook` - Link to operational runbook

5. **Avoid Overuse**: Don't put dynamic data in labels
   - Labels are for grouping and selection
   - Use annotations for non-queryable metadata
   - Limit: 63 characters per label value

## Common Use Cases

| Use Case | Query Type | Example Label |
| -------- | ---------- | ------------- |
| Cost allocation | Group by cost-center | `tags[cost-center]` |
| Team ownership | Group by team | `tags[team]` |
| Environment isolation | Filter by environment | `tags[environment]` |
| Version tracking | Filter/group by version | `tags[version]` |
| Feature flags | Filter by feature label | `tags[feature]` |
| Compliance auditing | Check required labels | Multiple required labels |
| Resource organization | Group by tier/component | `tier`, `component` |

## Troubleshooting

### Label Not Found

**Issue:** Query returns no results when filtering by label

**Solutions:**

```dql
// Check if label exists
smartscapeNodes K8S_POD
| filter isNotNull(tags[your_label])
```

```dql
// List all labels on a resource
smartscapeNodes K8S_POD
| limit 1
| parse k8s.object, "JSON:config"
| fieldsAdd labels = config[metadata][labels]
```

### Special Characters in Labels

**Issue:** Label key has dots, slashes, or other special characters

**Solution:** Use backticks

```dql-snippet
tags[`app.kubernetes.io/name`]
tags[`example.com/custom-label`]
```

## Related Topics

- **Cluster Inventory** → `cluster-inventory.md` - Use labels to organize namespaces
- **Pod Placement** → `pod-node-placement.md` - Use labels for node selection
- **Security Posture** (documentation) - Label-based compliance checks
- **Cost Optimization** (documentation) - Label-based cost tracking
