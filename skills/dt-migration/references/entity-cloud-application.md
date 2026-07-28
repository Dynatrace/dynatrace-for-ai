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

## Signal query migration with hardcoded IDs

When `dt.entity.cloud_application` appears in a `timeseries filter:` with a hardcoded `CLOUD_APPLICATION-xxx` ID, both the dimension field **and the entity ID** change. Unlike SERVICE or HOST migrations, `toSmartscapeId("CLOUD_APPLICATION-xxx")` does not resolve to the correct Smartscape node because the entity type prefix changes (e.g. `CLOUD_APPLICATION-xxx` → `K8S_DEPLOYMENT-yyy`).

### Step 1 — Resolve the new ID

Use the variadic `in()` form to resolve one or more classic IDs in a single query:

```dql
smartscapeNodes "*" | filter in(id_classic, {"CLOUD_APPLICATION-xxx"}) | fields id, id_classic, name, type
```

For multiple IDs, add them as additional arguments:

```dql
smartscapeNodes "*" | filter in(id_classic, {"CLOUD_APPLICATION-aaa", "CLOUD_APPLICATION-bbb", "CLOUD_APPLICATION-ccc"}) | fields id, id_classic, name, type
```

The result gives the new Smartscape ID (e.g. `K8S_DEPLOYMENT-yyy`). Determine which workload type it belongs to (`K8S_DEPLOYMENT`, `K8S_DAEMONSET`, `K8S_STATEFULSET`, etc.) from the returned ID prefix.

### Step 2 — Rewrite the signal filter

Before:

```dql-snippet
filter: in(dt.entity.cloud_application, {"CLOUD_APPLICATION-xxx"})
```

After:

```dql-snippet
filter: in(dt.smartscape.k8s_deployment, { toSmartscapeId("K8S_DEPLOYMENT-yyy") })
```

The Smartscape dimension field must match the resolved workload type, so DQL queries must be adopted.

`K8S_DEPLOYMENT` -> `dt.smartscape.k8s_deployment`

`K8S_DAEMONSET` -> `dt.smartscape.k8s_daemonset`

`K8S_STATEFULSET` -> `dt.smartscape.k8s_statefulset`

`K8S_REPLICASET` -> `dt.smartscape.k8s_replicaset`

`K8S_REPLICATIONCONTROLLER` -> `dt.smartscape.k8s_replicationcontroller`

`K8S_JOB` -> `dt.smartscape.k8s_job`

`K8S_DEPLOYMENTCONFIG` -> `dt.smartscape.k8s_deploymentconfig`

## Related references

- [entity-kubernetes.md](entity-kubernetes.md)
- [type-mappings.md](type-mappings.md)
- [examples.md](examples.md)
