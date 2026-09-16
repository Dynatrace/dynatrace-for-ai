# Kubernetes Migration Guide

Use this guide when the migration centers on Kubernetes cluster, node, namespace, service, pod, or workload entities.

## Common mappings

| Classic | Smartscape |
| --- | --- |
| `dt.entity.kubernetes_cluster` | `dt.smartscape.k8s_cluster` / `K8S_CLUSTER` |
| `dt.entity.kubernetes_node` | `dt.smartscape.k8s_node` / `K8S_NODE` |
| `dt.entity.kubernetes_service` | `dt.smartscape.k8s_service` / `K8S_SERVICE` |
| `dt.entity.cloud_application_namespace` | `dt.smartscape.k8s_namespace` / `K8S_NAMESPACE` |
| `dt.entity.cloud_application_instance` | `dt.smartscape.k8s_pod` / `K8S_POD` |

## Workload relationships

Smartscape models workload relationships explicitly:

- `K8S_POD belongs_to K8S_CLUSTER`
- `K8S_POD belongs_to K8S_NAMESPACE`
- `K8S_POD runs_on K8S_NODE`
- `K8S_POD is_part_of K8S_DEPLOYMENT`, `K8S_STATEFULSET`, `K8S_DAEMONSET`, and related workload types
- `K8S_SERVICE routes_to K8S_POD`

## K8S_CLUSTER schema changes

The `K8S_CLUSTER` entity has notable schema differences from its classic counterpart:

- **No `k8s.object` field** — unlike all other k8s entity types, `K8S_CLUSTER` does not expose a `k8s.object` JSON field. Using `parse k8s.object` on cluster entities silently returns null.
- **`operatorVersion` does not exist in the classic schema** — it is only available in Smartscape 2.0 via `dt.metadata[operator_version]`.
- **ActiveGate metadata** moved from top-level fields into the `dt.metadata` map.
- **`kubernetesDistribution`** returns a normalized enum (e.g. `KUBERNETES`) in classic; Smartscape 2.0 returns the actual distribution name (`GKE`, `AKS`, `EKS`, `Kubernetes`).

| Classic (`dt.entity.kubernetes_cluster`) | Smartscape (`K8S_CLUSTER` via `smartscapeNodes`) |
| --- | --- |
| `entity.name` | `k8s.cluster.name` |
| `kubernetesClusterId` | `k8s.cluster.uid` |
| `kubernetesDistribution` | `k8s.cluster.distribution` |
| `activeGateId` | `dt.metadata[activegate_id]` |
| `activeGateVersion` | `dt.metadata[activegate_version]` |
| *(not available)* | `dt.metadata[operator_version]` |
| *(not available)* | `k8s.cluster.version` |

Classic query:

```dql
fetch dt.entity.kubernetes_cluster
| fieldsAdd activeGateId, activeGateVersion, kubernetesDistribution, kubernetesClusterId
| fields entity.name, kubernetesDistribution, activeGateId, activeGateVersion
```

Equivalent Smartscape 2.0 query — also surfaces operator version, which is not available in classic:

```dql
smartscapeNodes K8S_CLUSTER
| fieldsAdd operator_version = dt.metadata[operator_version],
            activegate_id = dt.metadata[activegate_id],
            activegate_version = dt.metadata[activegate_version]
| fields k8s.cluster.name, k8s.cluster.uid, k8s.cluster.distribution,
         k8s.cluster.version, operator_version, activegate_id, activegate_version
```

## Migration guidance

- Prefer first-class `k8s.*` fields when querying pods or workloads directly
- Use `traverse` when the relationship itself matters
- For classic cloud application concepts, also load [entity-cloud-application.md](entity-cloud-application.md)

## Example

```dql
smartscapeNodes K8S_POD
| fields entity.name = name,
  workloadName = k8s.workload.name,
  namespaceName = k8s.namespace.name,
  nodeName = k8s.node.name,
  kubernetesClusterName = k8s.cluster.name
```

## Related references

- [entity-cloud-application.md](entity-cloud-application.md)
- [relationship-mappings.md](relationship-mappings.md)
- [examples.md](examples.md)
