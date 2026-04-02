# Cloud Application Migration Guide

Use this guide when the classic query uses:

- `dt.entity.cloud_application`
- `dt.entity.cloud_application_instance`
- `dt.entity.cloud_application_namespace`

## Core mappings

| Classic | Smartscape |
| --- | --- |
| `dt.entity.cloud_application` | multiple workload types: `K8S_DEPLOYMENT`, `K8S_DAEMONSET`, `K8S_STATEFULSET`, `K8S_REPLICASET`, `K8S_REPLICATIONCONTROLLER`, `K8S_JOB`, `K8S_DEPLOYMENTCONFIG` |
| `dt.entity.cloud_application_instance` | `K8S_POD` |
| `dt.entity.cloud_application_namespace` | `K8S_NAMESPACE` |

## Why this matters

The classic cloud-application model grouped several Kubernetes workload concepts under one type. Smartscape models those workload types explicitly.

That means a direct one-to-one replacement often does not exist for `dt.entity.cloud_application`.

## Migration guidance

### `dt.entity.cloud_application`

- query the relevant workload types explicitly
- use workload or Kubernetes fields such as `k8s.cluster.name`
- if the classic query assumed one unified type, make the new multi-type scope explicit

### `dt.entity.cloud_application_instance`

- translate to `smartscapeNodes K8S_POD`
- use first-class pod fields:
  - `k8s.workload.name`
  - `k8s.namespace.name`
  - `k8s.node.name`
  - `k8s.cluster.name`

### `dt.entity.cloud_application_namespace`

- translate to `smartscapeNodes K8S_NAMESPACE`

## Example: workload mapping

```dql
smartscapeNodes K8S_DEPLOYMENT, K8S_DAEMONSET, K8S_STATEFULSET, K8S_REPLICASET,
  K8S_REPLICATIONCONTROLLER, K8S_JOB, K8S_DEPLOYMENTCONFIG
| fields
    entity.name = name,
    kubernetesClusterName = k8s.cluster.name,
    cloudApplicationLabels = `tags:k8s.labels`
```

## Example: pod mapping

```dql
smartscapeNodes K8S_POD
| fields entity.name = name,
  workloadName = k8s.workload.name,
  namespaceName = k8s.namespace.name,
  nodeName = k8s.node.name,
  kubernetesClusterName = k8s.cluster.name
```

## Related references

- [entity-kubernetes.md](entity-kubernetes.md)
- [type-mappings.md](type-mappings.md)
- [examples.md](examples.md)
