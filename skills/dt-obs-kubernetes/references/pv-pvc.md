# Persistent Volumes and Claims

## Contents

- [PVC and PV Lifecycle — Phase Reference](#pvc-and-pv-lifecycle--phase-reference)
- [Relationships](#relationships)
- [Find Problem PVCs](#find-problem-pvcs)
- [K8S_PERSISTENTVOLUME Entity](#k8s_persistentvolume-entity)
- [StorageClass Distribution](#storageclass-distribution)

## PVC and PV Lifecycle — Phase Reference

PersistentVolumeClaims (PVCs) and PersistentVolumes (PVs) have **separate
lifecycle phases**. Confusing them produces incorrect filters.

**PVC phases** (`K8S_PERSISTENTVOLUMECLAIM`):

| Phase | Meaning |
|---|---|
| `Pending` | No matching PV bound yet — storage class or capacity mismatch, or provisioner not ready |
| `Bound` | PVC is linked to a PV and in use |
| `Lost` | The backing PV was deleted while this PVC still exists; pods mounting it will stay in `Pending` |

**PV phases** (`K8S_PERSISTENTVOLUME`):

| Phase | Meaning |
|---|---|
| `Available` | PV exists but no PVC has claimed it |
| `Bound` | PV is linked to a PVC |
| `Released` | The PVC was deleted but the PV was not reclaimed (data still present) |
| `Failed` | Automatic reclaim failed |

> `Released` and `Failed` are **PV phases only**. A filter
> `phase == "Released"` on `K8S_PERSISTENTVOLUMECLAIM` will never match.

## Relationships

```
K8S_POD --(uses)--> K8S_PERSISTENTVOLUMECLAIM --(uses)--> K8S_PERSISTENTVOLUME
K8S_PERSISTENTVOLUME --(belongs_to)--> K8S_CLUSTER
```

## Find Problem PVCs

List PVCs that are `Pending` or `Lost`.

```dql
smartscapeNodes K8S_PERSISTENTVOLUMECLAIM
| parse k8s.object, "JSON:config"
| fieldsAdd
    phase = config[`status`][`phase`],
    storage_class = config[`spec`][`storageClassName`],
    capacity = config[`status`][`capacity`][`storage`]
| filter in(phase, array("Pending", "Lost"))
| fields k8s.cluster.name, k8s.namespace.name, k8s.pvc.name, phase,
    storage_class, capacity
```

`Lost` PVCs block any pod that tries to mount them. `Pending` PVCs prevent
StatefulSet pods from starting (pod-order dependency — see
`references/workload-health.md`).

## K8S_PERSISTENTVOLUME Entity

`K8S_PERSISTENTVOLUME` is cluster-scoped (no namespace). Query it directly
when you need cross-cluster storage inventory or to detect leaked volumes —
neither is visible from the PVC side alone.

**All PVs with phase and capacity** (inventory / cost audit):

```dql
smartscapeNodes K8S_PERSISTENTVOLUME
| parse k8s.object, "JSON:config"
| fieldsAdd
    phase = config[`status`][`phase`],
    storage_class = config[`spec`][`storageClassName`],
    capacity = config[`spec`][`capacity`][`storage`],
    reclaim_policy = config[`spec`][`persistentVolumeReclaimPolicy`]
| fields k8s.cluster.name, entity.name, phase, storage_class, capacity, reclaim_policy
```

**Released PVs** — the PVC was deleted but the PV (and its data) still exists.
With a `Retain` reclaim policy this is expected; with `Delete` it signals a
reclaim failure that needs manual cleanup:

```dql
smartscapeNodes K8S_PERSISTENTVOLUME
| parse k8s.object, "JSON:config"
| fieldsAdd
    phase = config[`status`][`phase`],
    reclaim_policy = config[`spec`][`persistentVolumeReclaimPolicy`]
| filter phase == "Released"
| fields k8s.cluster.name, entity.name, phase, reclaim_policy
```

**Filter by provisioner** — because `K8S_STORAGECLASS` is not a smartscape entity type, the annotation `pv.kubernetes.io/provisioned-by` (values like `ebs.csi.aws.com`, `pd.csi.storage.gke.io`) is the only way to scope PV queries to a specific CSI driver:

```dql-template
smartscapeNodes K8S_PERSISTENTVOLUME
| parse k8s.object, "JSON:config"
| fieldsAdd
    provisioner = config[`metadata`][`annotations`][`pv.kubernetes.io/provisioned-by`],
    phase = config[`status`][`phase`],
    storage_class = config[`spec`][`storageClassName`],
    capacity = config[`spec`][`capacity`][`storage`]
| filter provisioner == "<provisioner>"
| fields k8s.cluster.name, entity.name, provisioner, phase, storage_class, capacity
```

## StorageClass Distribution

```dql
smartscapeNodes K8S_PERSISTENTVOLUMECLAIM
| parse k8s.object, "JSON:config"
| fieldsAdd storage_class = config[`spec`][`storageClassName`]
| summarize pvc_count = count(), by: {k8s.cluster.name, storage_class}
| sort pvc_count desc
```
