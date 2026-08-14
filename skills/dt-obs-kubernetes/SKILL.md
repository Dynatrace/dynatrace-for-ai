---
name: dt-obs-kubernetes
description: >-
  Kubernetes cluster, pod, node, and workload monitoring. Use when analyzing K8s health, resource
  optimization, pod failures, OOMKills, scheduling, or security posture. Also use for Kubernetes
  operational events like pod restarts, OOM events, evictions, and cluster event history.
  Trigger: "Kubernetes pods", "K8s cluster health", "OOMKill", "pod restarts", "container CPU",
  "namespace resource usage", "over-provisioned pods", "privileged containers",
  "pod placement", "K8s node capacity", "running containers by cluster",
  "workload scheduling", "pod evictions", "K8s labels and annotations",
  "kubernetes events", "pod restart events", "OOM events", "K8s event history".
  Do NOT use for explaining existing queries, product documentation questions,
  AWS-specific resource queries, service-level RED metrics, distributed tracing, or
  log analysis — use the relevant skill instead.
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
## Knowledge Base Structure

### Core Monitoring (Start Here)

1. **Cluster Inventory** → `references/cluster-inventory.md` - Clusters,
   namespaces, resource distribution
2. **Node Monitoring** - Node capacity, CPU/memory usage, pod density
3. **Pod Monitoring** - Pod CPU, memory, lifecycle events
4. **Workload Monitoring** - Deployment, StatefulSet, DaemonSet resources

### Advanced Topics

1. **Configuration Analysis** → `references/labels-annotations.md` - Parse
   k8s.object, labels, annotations
2. **Scheduling & Placement** → `references/pod-node-placement.md` - Node
   selectors, affinity, taints, HA
3. **Cost Optimization** - Right-sizing, waste detection, efficiency scoring
4. **Security & Compliance** - Privileged containers, security contexts

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

Pod troubleshooting benefits from combining **metrics** (timeseries) with
**Kubernetes events** (event stream) for a complete picture.

#### Metrics-Based Troubleshooting

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

#### Event-Based Troubleshooting

For operational events (pod restarts, OOM kills, evictions, scheduling failures),
Kubernetes events provide richer context than metrics alone — including event
reasons, messages, and timestamps.

**When to use Kubernetes events over metrics:**
- User asks about recent operational events ("show me pod restart events")
- User wants event details like reasons and messages
- User asks about events in a specific time window ("last 48 hours")
- User wants to correlate events with root causes

**Kubernetes events** are available through the `get-events-for-kubernetes-cluster`
tool. **Prefer this tool** when the user asks about OOM events, pod restarts,
evictions, or cluster-wide event history.

**Important: distinguish event types when filtering results.** Kubernetes events
cover many categories. When the user asks about a specific event type, filter
the results accordingly — do not report unrelated events:

| User Asks About | Relevant Event Reasons | NOT Related |
|-----------------|----------------------|-------------|
| Pod restarts | `BackOff`, `CrashLoopBackOff`, `Killing` | Readiness probe failures, CPU throttling |
| OOM events | `OOMKilling`, `OOMKilled` | Memory pressure warnings |
| Evictions | `Evicted`, `Preempting` | Node pressure |
| Scheduling failures | `FailedScheduling`, `Unschedulable` | Resource quotas |

**For a complete answer**, combine both approaches:
1. Use the **events tool** to get the event details (what happened, when, why)
2. Use **timeseries metrics** to show the quantitative impact (how many restarts,
   OOM kill counts over time)

#### Fetch Kubernetes Events via DQL

Pod restart and operational events can also be queried via DQL from the events
table:

```dql
fetch events
| filter event.kind == "K8S_EVENT"
| filter event.type == "Warning"
| fields timestamp, k8s.cluster.name, k8s.namespace.name, k8s.pod.name,
    event.reason, event.message
| sort timestamp desc
| limit 50
```

Filter for specific event reasons:

```dql
fetch events
| filter event.kind == "K8S_EVENT"
| filter in(event.reason, {"OOMKilling", "BackOff", "Evicted", "FailedScheduling"})
| fields timestamp, k8s.cluster.name, k8s.namespace.name, k8s.pod.name,
    event.reason, event.message
| sort timestamp desc
```

**Field names in `fetch events`:** Use `event.reason` and `event.message` — not
`dt.kubernetes.event.reason`. The `dt.kubernetes.*` prefix is for timeseries metrics,
not the events table. Queries using the wrong prefix return zero results.

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
| filter iAny(startsWith(smartscape.affected_entities[][type], "K8S_"))
| fields display_id, event.name, event.category, affected_entity_ids = smartscape.affected_entities[][id]
```

`smartscape.affected_entities` is a record array; each record has `id`, `type`, and `name`. Use
`[][id]` to get the array of Smartscape IDs to look up the affected entity, or
`[id]` after `expand smartscape.affected_entities`. Without a preceding `expand`, `[id]` returns
`null` silently. A `filter` cannot take a bare iterative expression, so wrap it in `iAny(...)`.

## Best Practices

### Choosing the Right Data Source

| User Question | Best Approach | Why |
|---------------|---------------|-----|
| "Show me OOM events" | Events tool + metrics | Events give reasons/messages; metrics show trends |
| "Show me pod restart events" | Events tool + timeseries metrics | Events reveal the reason (BackOff, Killing, CrashLoopBackOff); `dt.kubernetes.container.restarts` metric gives the actual restart counts |
| "How many pod restarts?" | Timeseries metrics | Quantitative data over time |
| "What happened to my pods in the last 48h?" | Events tool | Operational event history with context |
| "Which pods are using the most CPU?" | Timeseries metrics | Resource utilization analysis |
| "List all clusters/namespaces" | smartscapeNodes | Entity discovery and inventory |
| "Are there scheduling failures?" | Events tool | Event reasons explain why |

### Query Performance

1. **Filter early** - Apply cluster/namespace filters immediately
2. **Use specific entity types** - Avoid wildcards
3. **Limit result sets** - Use `limit` for exploration
4. **Cache cluster lists** - Store in variables

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

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| No pod data returned | Wrong entity type or missing cluster filter | Use `K8S_POD` (not `POD`); add `k8s.cluster.name` filter |
| `k8s.object` parsing errors | Complex JSON structure | Use `parse k8s.object, "JSON:config"` then access nested fields |
| Pod network metrics unavailable | Not available in Grail | Use service mesh metrics or host-level network metrics |
| Large result sets | No time range or cluster filter | Add time range and filter by cluster/namespace early |
| Missing labels in output | Labels accessed incorrectly | Use `tags[label_name]` to access labels |

## Limitations

**Unavailable Metrics:**

- Pod network metrics (rx_bytes, tx_bytes) are NOT available in Grail
- Workaround: Use service mesh metrics or host-level network metrics

**Query Considerations:**

- Minimize result set size: Do not include the `k8s.object` field if not necessary
- Keep result set as simple as possible: Parsing k8s.object increases query complexity
- Large clusters may require pagination or time-range limits
- Some K8s status fields update asynchronously

## When to Load References

### Load cluster-inventory.md when:
- Performing cluster, namespace, or resource distribution analysis
- Auditing workload counts across clusters

→ [references/cluster-inventory.md](references/cluster-inventory.md)

### Load labels-annotations.md when:
- Filtering by labels or annotations
- Parsing `k8s.object` for detailed configuration inspection

→ [references/labels-annotations.md](references/labels-annotations.md)

### Load pod-node-placement.md when:
- Analyzing scheduling constraints (affinity, taints, tolerations)
- Verifying HA compliance and pod distribution

→ [references/pod-node-placement.md](references/pod-node-placement.md)

### Load pod-debugging.md when:
- Investigating pod exit codes, crash loops, or init container failures
- Diagnosing image pull errors or service-to-pod connectivity issues
- Drilling down from a service problem to pod-level details

→ [references/pod-debugging.md](references/pod-debugging.md)

### Load workload-health.md when:
- Investigating degraded deployments or stuck rollouts
- Checking node conditions, CPU throttling, or HPA scaling
- Analyzing StatefulSet ordering or DaemonSet coverage

→ [references/workload-health.md](references/workload-health.md)

### Load pv-pvc.md when:
- Working with persistent storage (PVC/PV lifecycle, orphaned volumes)
- Checking StorageClass configurations

→ [references/pv-pvc.md](references/pv-pvc.md)

### Load ingress.md when:
- Analyzing ingress routing rules or TLS certificates
- Auditing ingress controller configurations

→ [references/ingress.md](references/ingress.md)

### Load network-policies.md when:
- Listing or auditing network policies
- Checking namespace isolation configurations

→ [references/network-policies.md](references/network-policies.md)

## References

- [cluster-inventory.md](references/cluster-inventory.md) — Cluster, namespace, and resource distribution analysis
- [labels-annotations.md](references/labels-annotations.md) — Label/annotation filtering and k8s.object parsing
- [pod-node-placement.md](references/pod-node-placement.md) — Scheduling, affinity, taints, and HA patterns
- [pod-debugging.md](references/pod-debugging.md) — Exit codes, pod conditions, init containers, image pull errors, logs, service-to-pod drill-down
- [workload-health.md](references/workload-health.md) — Degraded deployments, stuck rollouts, node conditions, CPU throttling, HPA, StatefulSet ordering
- [pv-pvc.md](references/pv-pvc.md) — PVC/PV lifecycle, phase reference, orphaned volumes, StorageClass
- [ingress.md](references/ingress.md) — Routing rule parsing, TLS audit
- [network-policies.md](references/network-policies.md) — Policy listing, namespace isolation audit

## Related Skills

- **dt-obs-problems** — For problems associated with Kubernetes clusters (use `dt.smartscape_source.id` with K8S_ prefix filters)
- **dt-dql-essentials** — Core DQL syntax and query structure
- **dt-obs-hosts** — Host-level metrics for K8s nodes

