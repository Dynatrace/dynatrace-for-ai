---
name: dt-obs-kubernetes
description: Kubernetes clusters, pods, nodes, workloads, storage, networking, and resource relationships. Query K8s inventory, diagnose degraded deployments and pod failures, investigate rollouts, audit ingress and network policies.
license: Apache-2.0
---

# Infrastructure Kubernetes

Monitor and analyze Kubernetes infrastructure using Dynatrace DQL. Query
cluster resources, monitor workload health, analyze pod placement, optimize
costs, and assess security posture.

## When to Use This Skill

- Monitoring Kubernetes cluster health and capacity
- Analyzing pod and container resource utilization
- Investigating pod failures, OOMKills, evictions, or crash loops
- Debugging degraded deployments, stuck rollouts, or node pressure
- Optimizing Kubernetes resource costs
- Assessing security posture and compliance
- Troubleshooting workload scheduling and placement
- Auditing ingress routing and network policies

## Reference Files

| File | Contents |
|---|---|
| [`references/cluster-inventory.md`](references/cluster-inventory.md) | Clusters, namespaces, resource distribution |
| [`references/labels-annotations.md`](references/labels-annotations.md) | Labels, annotations, k8s.object parsing patterns |
| [`references/pod-node-placement.md`](references/pod-node-placement.md) | Node selectors, affinity, taints, HA scheduling |
| [`references/pod-debugging.md`](references/pod-debugging.md) | Exit codes, pod conditions, init containers, image pull errors, logs, service→pod drill-down |
| [`references/workload-health.md`](references/workload-health.md) | Degraded deployments, stuck rollouts, node conditions, CPU throttling, HPA, StatefulSet ordering |
| [`references/pv-pvc.md`](references/pv-pvc.md) | PVC/PV lifecycle, phase reference, orphaned volumes, StorageClass |
| [`references/ingress.md`](references/ingress.md) | Routing rule parsing, TLS audit |
| [`references/network-policies.md`](references/network-policies.md) | Policy listing, namespace isolation audit |

## Key Concepts

### Entity Types

**Workloads:** `K8S_DEPLOYMENT`, `K8S_STATEFULSET`, `K8S_DAEMONSET`,
`K8S_JOB`, `K8S_CRONJOB`, `K8S_HORIZONTALPODAUTOSCALER`  
**Infrastructure:** `K8S_CLUSTER`, `K8S_NAMESPACE`, `K8S_NODE`, `K8S_POD`  
**Configuration:** `K8S_SERVICE`, `K8S_CONFIGMAP`, `K8S_SECRET`,
`K8S_PERSISTENTVOLUMECLAIM`, `K8S_PERSISTENTVOLUME`, `K8S_INGRESS`,
`K8S_NETWORKPOLICY`

### Query Types

**smartscapeNodes** - Query K8s entities:

```dql
smartscapeNodes K8S_POD
| filter k8s.namespace.name == "production"
| fields k8s.cluster.name, k8s.pod.name
```

**timeseries** - Monitor metrics over time:

```dql
timeseries cpu = sum(dt.kubernetes.container.cpu_usage),
  by: {k8s.pod.name, k8s.namespace.name}
| fieldsAdd avg_cpu = arrayAvg(cpu)
```

**fetch logs** - Analyze log events:

```dql
fetch logs
| filter k8s.namespace.name == "production" and loglevel == "ERROR"
```

### Core Fields

- `k8s.cluster.name`, `k8s.namespace.name`, `k8s.pod.name`, `k8s.node.name`
- `k8s.workload.name`, `k8s.workload.kind`, `k8s.container.name`
- `k8s.object` - Full JSON configuration for deep inspection
- `tags[label]` - Access labels and annotations

### Available Metrics

**CPU:** `dt.kubernetes.container.cpu_usage`, `cpu_throttled`, `limits_cpu`,
`requests_cpu`  
**Memory:** `dt.kubernetes.container.memory_working_set`, `limits_memory`,
`requests_memory`  
**Operations:** `dt.kubernetes.container.restarts`, `oom_kills`  
**Node:** `dt.kubernetes.node.pods_allocatable`, `cpu_allocatable`,
`memory_allocatable`, `dt.kubernetes.pods`

### Entity Disambiguation

`K8S_POD` vs `CONTAINER`: these are different entity types in Dynatrace.

- **`K8S_POD`** — K8s-native entities with `k8s.object` JSON, scheduling state, conditions, and K8s metrics. Use this skill.
- **`CONTAINER`** — Host-level container inventory (image, lifetime, host assignment). Use `dt-obs-hosts` skill instead.

The smartscape edge is `CONTAINER --(is_part_of)--> K8S_POD`. To reach containers from a pod, traverse backward:

```dql-template
smartscapeNodes K8S_POD
| filter k8s.namespace.name == "<namespace>"
| traverse edgeTypes: {is_part_of}, targetTypes: {CONTAINER}, direction: backward, fieldsKeep: {id}
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, container.id=id
```

### Service → K8S_POD Correlation

No direct smartscape edge exists between `SERVICE` and `K8S_POD`. The correlation key is the shared dimension `k8s.workload.name`. See [Service → Pod Drill-Down](references/pod-debugging.md#service--pod-drill-down) in `references/pod-debugging.md` for the full two-step pattern.

## Common Workflows

### 1. Cluster Health Check

List all clusters:

```dql
smartscapeNodes K8S_CLUSTER
| fields k8s.cluster.name, k8s.cluster.version, k8s.cluster.distribution
```

Check node capacity:

```dql
timeseries {
  current_pods = avg(dt.kubernetes.pods),
  max_pods = avg(dt.kubernetes.node.pods_allocatable)
}, by: {k8s.node.name, k8s.cluster.name}
| fieldsAdd pod_capacity_pct = (arrayAvg(current_pods) / arrayAvg(max_pods)) * 100
| filter pod_capacity_pct > 80
```

Identify pods in non-Running state:

```dql
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| fieldsAdd phase = config[status][phase]
| filter phase != "Running"
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, phase
```

### 2. Resource Optimization

Find over-provisioned pods (usage < 30%):

```dql
timeseries {
  cpu_usage = sum(dt.kubernetes.container.cpu_usage),
  cpu_requests = avg(dt.kubernetes.container.requests_cpu)
}, by: {k8s.pod.name, k8s.namespace.name, k8s.cluster.name}
| fieldsAdd usage_pct = (arrayAvg(cpu_usage) / arrayAvg(cpu_requests)) * 100
| filter usage_pct < 30 and arrayAvg(cpu_requests) > 0
```

Identify containers without limits:

```dql
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| expand container = config[spec][containers]
| fieldsAdd
    container_name = container[name],
    cpu_limit = container[resources][limits][cpu],
    memory_limit = container[resources][limits][memory]
| filter isNull(cpu_limit) or isNull(memory_limit)
```

### 3. Troubleshooting Pod Issues

Find pods with OOMKills:

```dql
timeseries oom_kills = sum(dt.kubernetes.container.oom_kills),
  by: {k8s.pod.name, k8s.namespace.name, k8s.cluster.name}
| filter arraySum(oom_kills) > 0
| fieldsAdd total_oom_kills = arraySum(oom_kills)
| sort total_oom_kills desc
```

Analyze pod restart patterns:

```dql
timeseries restarts = sum(dt.kubernetes.container.restarts),
  by: {k8s.pod.name, k8s.namespace.name, k8s.cluster.name}
| fieldsAdd total_restarts = arraySum(restarts)
| filter total_restarts > 5
```

### 4. Security Assessment

Identify privileged containers:

```dql
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| expand container = config[spec][containers]
| fieldsAdd
    container_name = container[name],
    privileged = container[securityContext][privileged]
| filter privileged == true
```

Find containers running as root:

```dql
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| expand container = config[spec][containers]
| fieldsAdd
    container_name = container[name],
    run_as_user = container[securityContext][runAsUser],
    run_as_non_root = container[securityContext][runAsNonRoot]
| filter (isNull(run_as_user) or run_as_user == 0) and run_as_non_root != true
```

### 5. Scheduling Analysis

Verify pod distribution (HA compliance):

```dql
smartscapeNodes K8S_POD
| filter k8s.workload.kind == "deployment"
| summarize pod_count = count(),
            node_count = countDistinct(k8s.node.name),
            by: {k8s.cluster.name, k8s.namespace.name, k8s.workload.name}
| fieldsAdd ha_compliant = node_count > 1
| filter pod_count >= 2 and not ha_compliant
```

### 6. DAVIS Problems affecting K8s Entities

Find active DAVIS problems affecting K8s entities:

```dql
fetch dt.davis.problems, from:now() - 2h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter matchesPhrase(smartscape.affected_entity.types, "K8S_")
| fields display_id, event.name, event.category, smartscape.affected_entity.ids
```

Use entries `smartscape.affected_entity.ids` (array of Smartscape IDs) to look up the affected entity using its Smartscape ID.

## Best Practices

### Query Performance

1. **Filter early** - Apply cluster/namespace filters immediately
2. **Use specific entity types** - Avoid wildcards
3. **Limit result sets** - Use `limit` for exploration

### Monitoring Recommendations

1. Set resource limits on all containers
2. Monitor OOMKills and adjust memory limits
3. Track CPU throttling and adjust CPU limits
4. Review resource efficiency regularly (target 70-80%)
5. Implement security best practices (non-root, read-only filesystem)
6. Use specific image tags (avoid :latest)

### Configuration Standards

1. Use labels for organization (app, environment, team)
2. Set resource requests and limits
3. Configure health checks (liveness/readiness probes)
4. Use TLS for all ingress resources
5. Document with annotations

## Limitations

**Unavailable Metrics:**

- Pod network metrics (rx_bytes, tx_bytes) are NOT available in Grail
- Workaround: Use service mesh metrics or host-level network metrics

**Query Considerations:**

- Minimize result set size: Do not include the `k8s.object` field if not necessary
- Keep result set as simple as possible: Parsing k8s.object increases query complexity
- Large clusters may require pagination or time-range limits
- Some K8s status fields update asynchronously
