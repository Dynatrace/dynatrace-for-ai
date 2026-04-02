# Workload Health and Rollout Debugging

Detection patterns for degraded deployments, stuck rollouts, node pressure,
CPU throttling, HPA scaling, and StatefulSet ordering.

## Contents

- [Deployment Replica Health](#deployment-replica-health)
- [Stuck Rollout Detection](#stuck-rollout-detection)
- [Node Conditions](#node-conditions)
- [CPU Throttling](#cpu-throttling)
- [HPA Inspection](#hpa-inspection)
- [StatefulSet](#statefulset)
  - [StatefulSet Pod Order](#statefulset-pod-order)

## Deployment Replica Health

A deployment is healthy when `status.readyReplicas == spec.replicas`. Filter with `isNotNull(desired)` to guard against false positives when `k8s.object` is unpopulated.

```dql
smartscapeNodes K8S_DEPLOYMENT
| parse k8s.object, "JSON:config"
| fieldsAdd
    desired = config[`spec`][`replicas`],
    ready = config[`status`][`readyReplicas`],
    available = config[`status`][`availableReplicas`],
    updated = config[`status`][`updatedReplicas`]
| filter isNotNull(desired) and (isNull(ready) or ready < desired)
| fields k8s.cluster.name, k8s.namespace.name, k8s.workload.name, desired, ready, available
```

## Stuck Rollout Detection

A **stuck rollout** differs from a simple replica shortage:

- **Replica shortage** — replicas are missing but the rollout is still
  progressing (slow image pull, resource pressure). Will resolve.
- **Stuck rollout** — Kubernetes gave up after `progressDeadlineSeconds`
  (default: 10 min). No further progress until intervention. Common causes:
  bad image tag, quota exhausted, PVC not bound, failing readiness probe.

`status.conditions` will contain `type=Progressing` with
`reason=ProgressDeadlineExceeded`:

```dql
smartscapeNodes K8S_DEPLOYMENT
| parse k8s.object, "JSON:config"
| expand condition = config[`status`][`conditions`]
| fieldsAdd
    cond_type = condition[`type`],
    cond_reason = condition[`reason`],
    cond_message = condition[`message`]
| filter cond_type == "Progressing" and cond_reason == "ProgressDeadlineExceeded"
| fields k8s.cluster.name, k8s.namespace.name, k8s.workload.name, cond_message
```

## Node Conditions

Node `status.conditions` exposes health states that block scheduling or
trigger evictions.

| Condition | Unhealthy state | Impact |
|---|---|---|
| `Ready` | `False` or `Unknown` | Node not accepting pods; existing pods may be evicted |
| `MemoryPressure` | `True` | Memory low; evictions likely |
| `DiskPressure` | `True` | Disk low; image pulls may fail |
| `PIDPressure` | `True` | Near process limit |

```dql
smartscapeNodes K8S_NODE
| parse k8s.object, "JSON:config"
| expand condition = config[`status`][`conditions`]
| fieldsAdd
    cond_type = condition[`type`],
    cond_status = condition[`status`],
    message = condition[`message`]
| filter (cond_type == "Ready" and cond_status != "True")
      or (in(cond_type, array("MemoryPressure","DiskPressure","PIDPressure")) and cond_status == "True")
| fields k8s.cluster.name, k8s.node.name, cond_type, cond_status, message
```

**Blast radius** — all pods on a failing node:

```dql-template
smartscapeNodes K8S_POD
| filter k8s.node.name == "<failing-node>"
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, k8s.workload.name
```

## CPU Throttling

CPU throttling caps container execution when usage hits the CPU limit. Unlike
OOMKills, the container stays running but responds slowly — a common source
of latency that appears as application slowness rather than crashes.

```dql
timeseries {
  throttled = avg(dt.kubernetes.container.cpu_throttled),
  limit = avg(dt.kubernetes.container.limits_cpu),
  usage = avg(dt.kubernetes.container.cpu_usage)
}, by: {k8s.pod.name, k8s.namespace.name, k8s.cluster.name}
| fieldsAdd throttle_pct = (arrayAvg(throttled) / arrayAvg(limit)) * 100
| filter throttle_pct > 25
| sort throttle_pct desc
```

`throttle_pct > 25` means the container is throttled more than 25% of the
time it wants to run. Resolution: raise the CPU limit or reduce usage.

## HPA Inspection

`K8S_HORIZONTALPODAUTOSCALER` exposes current, desired, min, and max replicas.

```dql
smartscapeNodes K8S_HORIZONTALPODAUTOSCALER
| parse k8s.object, "JSON:config"
| fieldsAdd
    min_replicas = config[`spec`][`minReplicas`],
    max_replicas = config[`spec`][`maxReplicas`],
    current_replicas = config[`status`][`currentReplicas`],
    desired_replicas = config[`status`][`desiredReplicas`]
| fields k8s.cluster.name, k8s.namespace.name, k8s.horizontalpodautoscaler.name,
    min_replicas, max_replicas, current_replicas, desired_replicas
```

HPAs stuck at max (cannot scale further):

```dql
smartscapeNodes K8S_HORIZONTALPODAUTOSCALER
| parse k8s.object, "JSON:config"
| fieldsAdd
    max_replicas = config[`spec`][`maxReplicas`],
    current_replicas = config[`status`][`currentReplicas`]
| filter current_replicas >= max_replicas
| fields k8s.cluster.name, k8s.namespace.name, k8s.workload.name,
    current_replicas, max_replicas
```

## StatefulSet

Retrieve `StatefulSet` instances

```dql
smartscapeNodes K8S_STATEFULSET
| parse k8s.object, "JSON:config"
| sort k8s.statefulset.name asc
| fields k8s.cluster.name, k8s.namespace.name, k8s.workload.name, k8s.pod.name, config
```

### StatefulSet Pod Order

StatefulSets start and stop pods in strict ordinal order (pod-0, pod-1...).
Pod N will not start until pod N-1 is `Ready`. The first pod in non-Running
state is the blocker.

```dql
smartscapeNodes K8S_POD
| filter k8s.workload.kind == "statefulset"
| parse k8s.object, "JSON:config"
| fieldsAdd phase = config[`status`][`phase`]
| sort k8s.pod.name asc
| fields k8s.cluster.name, k8s.namespace.name, k8s.workload.name, k8s.pod.name, phase
```

Investigate the blocking pod using `references/pod-debugging.md`.
