# Pod Debugging

Exit codes, pod conditions, init container failures, image pull errors, and
K8s-scoped log queries.

**Note:** OOMKill and restart *metrics* are available via `dt.kubernetes.container.*`
metric series. This reference covers the complementary approach of parsing
`k8s.object` for per-container state details not available in metrics.

## Contents

- [Exit Codes and Termination Reasons](#exit-codes-and-termination-reasons)
- [Pod Conditions](#pod-conditions)
- [Init Container Failures](#init-container-failures)
- [Image Pull Failures](#image-pull-failures)
- [K8s-Scoped Log Queries](#k8s-scoped-log-queries)
- [Service → Pod Drill-Down](#service--pod-drill-down)

## Exit Codes and Termination Reasons

Container exit codes from `lastState.terminated` explain why a container
stopped:

| Exit code | Cause | Action |
|---|---|---|
| `137` | OOMKilled | Raise memory limit |
| `1` or `2` | Application crash | Check container logs |
| `143` | SIGTERM (graceful shutdown) | Normal or probe misconfiguration causing premature restart |
| `0` | Clean exit | Likely a failing readiness probe restarting a healthy container |

```dql
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| expand container = config[`status`][`containerStatuses`]
| fieldsAdd
    name = container[`name`],
    restart_count = container[`restartCount`],
    exit_code = container[`lastState`][`terminated`][`exitCode`],
    reason = container[`lastState`][`terminated`][`reason`]
| filter isNotNull(exit_code) and restart_count > 0
| sort restart_count desc
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, name,
    restart_count, exit_code, reason
```

## Pod Conditions

`status.conditions` explains why a pod is not `Ready` or not `Scheduled`. `status.condition` is an array of objects, where the last element of the array represents the latest status.

| Condition | If `False` or `Unknown` means |
|---|---|
| `PodScheduled` | No node accepted the pod (resource pressure, taint mismatch, affinity conflict) |
| `ContainersReady` | At least one container not yet passing readiness probes |
| `Ready` | Pod not ready to serve traffic |

```dql
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| expand condition = config[`status`][`conditions`][-1]
| fieldsAdd
    cond_type = condition[`type`],
    cond_status = condition[`status`],
    cond_reason = condition[`reason`],
    message = condition[`message`]
| filter (cond_status == "False" or cond_status == "Unknown") and cond_reason != "PodCompleted"
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name,
    cond_type, cond_status, message, cond_reason
```

## Init Container Failures

Init containers run sequentially before main containers start. A failed init
container blocks the entire pod indefinitely.

```dql
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| expand init = config[`status`][`initContainerStatuses`]
| fieldsAdd
    init_name = init[`name`],
    init_ready = init[`ready`],
    init_exit = coalesce(init[`state`][`terminated`][`exitCode`], init[`state`][`waiting`][`exitCode`], init[`state`][`terminated`][`running`])
| filter init_ready == false
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, init_name, init_exit
```

## Image Pull Failures

`ImagePullBackOff` and `ErrImagePull` appear in `state.waiting.reason`.

**Note:** Container image names are not available in smartscape — they are
only accessible via `k8s.object` JSON parsing.

```dql
smartscapeNodes K8S_POD
| parse k8s.object, "JSON:config"
| expand container = config[`status`][`containerStatuses`]
| fieldsAdd
    name = container[`name`],
    image = container[`image`],
    reason = container[`state`][`waiting`][`reason`]
| filter in(reason, array("ImagePullBackOff", "ErrImagePull", "InvalidImageName"))
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, name, image, reason
```

## K8s-Scoped Log Queries

Namespace-level log filtering for pod-specific and crash-window scenarios.

Errors from a specific pod:

```dql-template
fetch logs
| filter k8s.pod.name == "<pod-name>" and k8s.namespace.name == "<namespace>"
| filter loglevel == "ERROR"
| fields timestamp, k8s.container.name, content
| sort timestamp desc
```

Logs within a time window before a known restart:

```dql-template
fetch logs, from: <restart_timestamp> - 5m, to: <restart_timestamp>
| filter k8s.pod.name == "<pod-name>" and k8s.namespace.name == "<namespace>"
| sort timestamp desc
```

## Service → Pod Drill-Down

No direct smartscape edge exists between `SERVICE` and `K8S_POD`. Use the shared dimension `k8s.workload.name` as the correlation key.

**Step 1** — find workloads with elevated error rate:

```dql
timeseries errors = sum(dt.service.request.failure_count),
  by: {k8s.workload.name, k8s.namespace.name}
| fieldsAdd total_errors = arraySum(errors)
| filter total_errors > 0
| sort total_errors desc
```

**Step 2** — filter pods by the identified workload and expand container statuses:

```dql-template
smartscapeNodes K8S_POD
| filter k8s.workload.name == "<workload-name>" and k8s.namespace.name == "<namespace>"
| parse k8s.object, "JSON:config"
| expand container = config[`status`][`containerStatuses`]
| fieldsAdd
    phase = config[`status`][`phase`],
    container_name = container[`name`],
    container_ready = container[`ready`],
    restart_count = container[`restartCount`],
    exit_code = container[`lastState`][`terminated`][`exitCode`]
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name,
    phase, container_name, container_ready, restart_count, exit_code
```

Cross-reference exit codes with the table at the top of this file to determine the failure cause.
