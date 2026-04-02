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
