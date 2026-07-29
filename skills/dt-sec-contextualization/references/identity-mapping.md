# Identity Mapping

## Contents

- [Mapping Primitive](#mapping-primitive)
- [Data Model](#data-model)


---

## Mapping Primitive


Given any row set carrying entity-identity fields, resolve it to Smartscape
entities at a requested level. Accepts findings, IoC match rows, or raw
Smartscape nodes as input.

> **This is a pure mapping primitive — no finding-schema semantics.**
> Fields such as `finding.*`, `vulnerability.*`, `compliance.*`, or
> `dt.security.risk.level` belong in **dt-sec-insights** consumers that call
> this primitive. Input rows need only carry at least one identity field from
> the three paths below.

---

## Contents

- [Supported Identity Fields](#supported-identity-fields)
- [3-Way Match Strategy (K8s Workload / Host)](#3-way-match-strategy)
- [Path 1 — Direct Smartscape ID](#path-1--direct-smartscape-id)
- [Path 2 — Container Image Digest → CONTAINER → Workload/Host](#path-2--container-image-digest--container--workloadhost)
- [Path 3 — Container Image ID → Workload](#path-3--container-image-id--workload)
- [Path 4 — AI Service → Runtime Process (`GENAI_SERVICE → SERVICE → PROCESS`)](#path-4--ai-service--runtime-process-genai_service--service--process)
- [Pre-flight Check — Identifier Availability](#pre-flight-check--identifier-availability)
- [Host-by-IP Resolution](#host-by-ip-resolution)
- [Level Selection Guide](#level-selection-guide)
- [Entity-Key Bundle (required for correlation)](#entity-key-bundle-required-for-correlation)

---

## Supported Identity Fields

| Field | Type | Used by path |
|---|---|---|
| `dt.smartscape_source.id` | Smartscape node ID (2nd or 3rd gen) | Path 1 |
| `dt.smartscape_source.type` | Entity type string (granularity check) | Path 1 pre-flight |
| `container_image.digest` | SHA256 image digest string | Path 2 |
| `container_image.id` | OCI image ID string | Path 3 |
| `container_image.repository` | Image registry URL | (supplemental) |
| `artifact.repository` | Alternative registry URL (some providers) | (supplemental) |
| `host.ip` | IP address or array | Host-by-IP |
| `dt.entity.host` | Classic entity ID (HOST-...) | Path 1 / entity-scoping |
| `dt.entity.process_group` | Classic entity ID (PROCESS_GROUP-...) | Path 1 / entity-scoping |
| `dt.entity.container_group_instance` | Classic entity ID (CGI) | Path 3 |
| `k8s.cluster.name` | Kubernetes cluster name | Tier-3 context |
| `k8s.namespace.name` | Kubernetes namespace name | Tier-3 context |
| `k8s.node.name` | Kubernetes node name (pod-co-projected) | Tier-2 topology |
| `k8s.workload.name` | Kubernetes workload name | Tier-2 topology |

---

## 3-Way Match Strategy

Three independent paths resolve external findings or artifact attributes to
Smartscape entities. For K8s workloads and hosts, all three are combined with
`append` to maximize match rate across providers:

| Path | Match key | Resolution mechanism | Level |
|---|---|---|---|
| 1 | `dt.smartscape_source.id` | Direct join on K8s workload / host Smartscape ID | Workload or HOST |
| 2 | `container_image.digest` | CONTAINER smartscapeNode → `references[is_part_of.*]` → parent workload or `runs_on.host` → HOST | Workload or HOST |
| 3 | `container_image.id` | `dt.entity.container_group_instance` → `belongs_to[dt.entity.cloud_application]` → workload | Workload |

> **Path 1 granularity constraint.** Path 1 matches only when
> `dt.smartscape_source.id` identifies a K8s **workload** node
> (`K8S_DEPLOYMENT`, `K8S_DAEMONSET`, `K8S_STATEFULSET`, `K8S_CRONJOB`,
> `K8S_JOB`, `K8S_REPLICASET`) or a HOST. External providers commonly populate
> this field at coarser granularity — the namespace, the cluster, or cloud
> resources (EC2, VM, S3, container registry) — in which case Path 1 returns 0
> even though the field is non-null. Always run the pre-flight check first.

> **Path 2 is the reliable artifact→runtime path.** When `dt.smartscape_source.id`
> is absent or points to the wrong granularity, `container_image.digest` →
> `smartscapeNodes CONTAINER` → workload resolves the running instance from the
> build artifact with no pre-enrichment required.

---

## Path 1 — Direct Smartscape ID

Join rows directly on `dt.smartscape_source.id` to K8s workload or HOST nodes.

```dql-snippet
// K8s workload resolution via Path 1
| join [
    smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}, from:now()-2h
  ], on:{left[dt.smartscape_source.id]==right[id]},
     fields:{dt.smartscape_source.id=id, classic_entity.id=id_classic, workloadName=k8s.workload.name}
```

```dql-snippet
// HOST resolution via Path 1
| join [
    smartscapeNodes {HOST}, from:now()-2h
  ], on:{left[dt.smartscape_source.id]==right[id]},
     fields:{hostName=name, dt.smartscape_source.id=id, host.classic.id=id_classic}
```

---

## Path 2 — Container Image Digest → CONTAINER → Workload/Host

Resolves a build artifact (`container_image.digest`) to the running Smartscape
CONTAINER node, then traverses the `is_part_of.*` reference to the parent
workload, or `runs_on.host` to the HOST.

```dql-snippet
// Path 2: digest → CONTAINER → parent workload
| join [
    smartscapeNodes CONTAINER, from:now()-2h
    | expand dt.k8s.workload.id=coalesce(references[is_part_of.k8s_deployment],
                             coalesce(references[is_part_of.k8s_daemonset],
                               coalesce(references[is_part_of.k8s_cronjob],
                                 coalesce(references[is_part_of.k8s_statefulset],
                                   coalesce(references[is_part_of.k8s_job],
                                     references[is_part_of.k8s_replicaset])))))
    | filter isNotNull(dt.k8s.workload.id)
    | fieldsAdd dt.smartscape_source.id=dt.k8s.workload.id
  ], kind:leftOuter, on:{left[container_image.digest]==right[container.image.digest]},
     fields:{dt.smartscape_source.id, classic_entity.id=id_classic, workloadName=k8s.workload.name}
```

```dql-snippet
// Path 2 variant: digest → CONTAINER → runs_on HOST
| join [
    smartscapeNodes CONTAINER, from:now()-2h
    | expand dt.host.id=references[runs_on.host]
    | filter isNotNull(dt.host.id)
    | fieldsAdd dt.smartscape_source.id=dt.host.id
    | lookup [
        smartscapeNodes {HOST}, from:now()-2h
      ], sourceField:dt.smartscape_source.id, lookupField:id,
         fields:{hostName=name, host.classic.id=id_classic}
  ], kind:leftOuter, on:{left[container_image.digest]==right[container.image.digest]},
     fields:{hostName, dt.smartscape_source.id, host.classic.id}
```

---

## Path 3 — Container Image ID → Workload

Resolves via the `dt.entity.container_group_instance` classic entity table, which
carries `containerImageId`, then looks up the workload Smartscape ID via `id_classic`.

```dql-snippet
// Path 3: container_image.id → CGI → workload → Smartscape ID
| join [
    fetch dt.entity.container_group_instance, from:now()-2h
    | fieldsAdd containerImageId, workload.id=belongs_to[dt.entity.cloud_application], workloadName
    | lookup [
        smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}, from:now()-2h
      ], sourceField:workload.id, lookupField:id_classic, fields:{dt.smartscape_source.id=id}
  ], kind:leftOuter, on:{left[container_image.id]==right[containerImageId]},
     fields:{dt.smartscape_source.id, classic_entity.id=workload.id, workloadName}
```

---

## Path 4 — AI Service → Runtime Process (`GENAI_SERVICE → SERVICE → PROCESS`)

This path scopes any process-level finding stream to AI/GenAI workloads, or
resolves a process back to its owning AI service. `GENAI_SERVICE` entities are
created by Dynatrace AI Observability (OpenLLMetry instrumentation).

**Forward — AI services → their processes.** Use to scope a finding stream to AI:

```dql
smartscapeNodes "GENAI_SERVICE", from:now()-2h
| traverse edgeTypes: {instance_of}, targetTypes: {SERVICE}
| traverse edgeTypes: {runs_on},     targetTypes: {PROCESS}
| filter toTimestamp(lifetime[end]) > now()-2h  // alive in the investigation window
| fields dt.smartscape.process = id
| dedup dt.smartscape.process
```

Adjust `from:now()-2h` and `now()-2h` together to match the investigation window.
Avoid `$dt_timeframe_from` in standalone DQL snippets unless the query is embedded in a
dashboard/notebook context that defines that variable.

Inner-join the result against a findings stream on `dt.smartscape.process`.

**Reverse — process → owning AI service.** Use for per-service grouping / linking:

```dql
smartscapeEdges "*", from:-2h
| filter source_type == "GENAI_SERVICE"
| fields genai_service.id = source_id, service.id = target_id
| join [
    smartscapeEdges "*", from:-2h
    | filter source_type == "SERVICE" AND target_type == "PROCESS"
    | fields process.id = target_id, service.id = source_id
  ], on:{service.id}, fields:{process.id}
```

Join back to findings on `left[dt.smartscape.process] == right[process.id]`.
Resolve the service display name with:

```dql-snippet
| lookup [ smartscapeNodes GENAI_SERVICE, from:-2h ],
    sourceField:genai_service.id, lookupField:id, fields:{genai_service.name = name}
```

> **Duplicate rows on multi-service processes.** A process reachable via multiple
> `GENAI_SERVICE` nodes can appear more than once — dedup on `dt.smartscape.process`
> (forward) or on `{genai_service.id, …}` (reverse) as appropriate.

---

## Pre-flight Check — Identifier Availability

Before running the full 3-way enrichment, confirm the input rows carry
resolvable identifiers. External providers vary — many scope to cloud resources
(EC2, S3, IAM), not K8s workloads. If no identifier path is populated, skip
the append chain and report the gap explicitly.

```dql
// Step 1: check identifier presence across providers
fetch security.events, from:now()-24h
| filterOut event.provider == "Dynatrace" or product.vendor == "Dynatrace"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| summarize {
    findings = count(),
    `has container_image.digest`  = countIf(isNotNull(container_image.digest)),
    `has container_image.id`      = countIf(isNotNull(container_image.id)),
    `has dt.smartscape_source.id` = countIf(isNotNull(dt.smartscape_source.id))
  }, by: {event.provider, product.name}
```

```dql
// Step 2 (if has dt.smartscape_source.id > 0): check entity granularity
fetch security.events, from:now()-24h
| filterOut event.provider == "Dynatrace" or product.vendor == "Dynatrace"
| filter isNotNull(dt.smartscape_source.id)
| summarize Count=count(), by:{event.provider, dt.smartscape_source.type}
| sort Count desc
```

**Interpretation:**
- `dt.smartscape_source.type` is a K8s workload type → Path 1 will yield matches.
- `dt.smartscape_source.type` is a namespace, cluster, or cloud-resource type → Path 1 returns 0; use Path 2/3.
- All three identifier counts are 0 → no K8s workload mapping possible; report this and use host-by-IP if applicable.

---

## Host-by-IP Resolution

When findings carry `host.ip` but no Smartscape ID or container digest, resolve
to HOST smartscapeNodes by IP address.

```dql-snippet
// Host-by-IP resolution
| expand host.ip
| fieldsAdd host.ip=ip(host.ip)
| join [
    smartscapeNodes HOST
    | expand ip
  ], on:{left[host.ip]==right[ip]}, fields:{host.id=id, host.name=name}
```

---

## Level Selection Guide

Choose the resolution level based on the question:

| Requested level | Use | Notes |
|---|---|---|
| K8s workload (deployment/daemonset/statefulset) | Path 1+2+3 → `K8S_DEPLOYMENT` etc. | Primary level for external VULNERABILITY/DETECTION findings |
| K8s node | Pod→node traversal (via `k8s.node.name` or Smartscape edge) | See `correlation-and-coverage.md` § Pod→Node Topology |
| HOST | Path 1+2 → `HOST` smartscapeNodes | Or host-by-IP when only IP is available |
| Cloud entity (EC2, S3, VM, etc.) | Path 1 → `smartscapeNodes "*" \| filter exists(cloud.provider)` | Cloud entities only need Path 1 |
| Container (running instance) | `smartscapeNodes CONTAINER` direct lookup by digest | Used as intermediate step in Path 2 |

---

## Entity-Key Bundle (required for correlation)

Every leg in a multi-leg hunt or enrichment flow must project an **entity-key bundle** — a minimal set of fields sufficient to join across legs without data loss:

```dql-snippet
| fieldsAdd entityKey.smartscape_id = dt.smartscape_source.id,
            entityKey.classic_id    = classic_entity.id,
            entityKey.name          = workloadName,    // or hostName
            entityKey.type          = dt.smartscape_source.type,
            entityKey.k8s.cluster   = k8s.cluster.name,
            entityKey.k8s.namespace = k8s.namespace.name,
            entityKey.k8s.node      = k8s.node.name    // if available (pod co-projection)
```

These keys are the input to the tiered correlation logic in
[correlation-and-coverage.md](correlation-and-coverage.md). Without them, cross-leg matching falls back
to Tier 3 (same cluster) at best — which is non-scoring.


---

## Data Model


Reference for the entity-identity fields used by the mapping primitive,
enrichment, and correlation recipes. These fields exist across all security
finding types and Smartscape nodes.

> **Finding-schema fields** (`finding.*`, `vulnerability.*`, `compliance.*`,
> `dt.security.risk.level`, `actor.*`, `threat.attack.*`) live in
> `dt-sec-insights/references/data-model.md`. This file covers only the
> **entity-identity slice** shared across dt-sec-contextualization.

---

## Contents

- [Smartscape Source Fields (cross-provider findings)](#smartscape-source-fields-cross-provider-findings)
- [Classic Entity Fields (`dt.entity.*`)](#classic-entity-fields-dtentity)
- [K8s Co-projected Fields](#k8s-co-projected-fields)
- [Container Image Fields](#container-image-fields)
- [RVA / Native Entity Fields](#rva--native-entity-fields)
- [ID Generation Notes](#id-generation-notes)

---

## Smartscape Source Fields (cross-provider findings)

Present on cross-provider findings (`VULNERABILITY_FINDING`, `DETECTION_FINDING`,
`COMPLIANCE_FINDING`) injected by external integrations.

| Field | Type | Notes |
|---|---|---|
| `dt.smartscape_source.id` | Smartscape node ID | 3rd-gen ID when available. May point to workload, cluster, namespace, or cloud resource — check `type` before assuming workload granularity |
| `dt.smartscape_source.type` | string | Entity type: `K8S_DEPLOYMENT`, `K8S_DAEMONSET`, `K8S_STATEFULSET`, `K8S_CRONJOB`, `K8S_JOB`, `K8S_REPLICASET`, `HOST`, `KUBERNETES_CLUSTER`, `KUBERNETES_NAMESPACE`, or cloud-resource types |

> **Granularity check required.** A non-null `dt.smartscape_source.id` does not
> guarantee workload-level resolution. Always check `dt.smartscape_source.type`
> before treating it as a K8s workload match (Path 1). Cloud-resource types
> (EC2, VM, S3, container registry) are common even when only K8s findings were
> expected.

---

## Classic Entity Fields (`dt.entity.*`)

2nd-generation classic entity IDs. Present on cross-provider findings and on
some scan events. **Not populated on DT RVA events** — those use
`affected_entity.*` instead.

| Field | Type | Notes |
|---|---|---|
| `dt.entity.host` | HOST-... ID | 2nd-gen host entity reference |
| `dt.entity.process_group` | PROCESS_GROUP-... ID | 2nd-gen process group reference |
| `dt.entity.process_group_instance` | PGI-... ID | Process group instance; used in scan coverage events |
| `dt.entity.container_group_instance` | CGI ID | Used in Path 3 (container_image.id resolution) |
| `dt.entity.cloud_application` | cloud application ID | Workload entity in cloud-application topology |
| `dt.entity.kubernetes_cluster` | K8s cluster ID | Cluster-level scope |
| `dt.entity.cloud_application_namespace` | namespace ID | K8s namespace entity |

---

## K8s Co-projected Fields

Present on `smartscapeNodes K8S_POD` and some cross-provider findings.
These are native string fields (not entity IDs) — they are used for name-based
Tier-2 correlation and pod→node topology resolution.

| Field | Type | Notes |
|---|---|---|
| `k8s.cluster.name` | string | Kubernetes cluster name |
| `k8s.namespace.name` | string | Kubernetes namespace |
| `k8s.node.name` | string | Node name — **co-projected** on K8S_POD smartscapeNodes; not available on all finding types |
| `k8s.pod.name` | string | Pod name (on K8S_POD smartscapeNodes) |
| `k8s.workload.name` | string | Workload name (on K8S_POD and workload smartscapeNodes) |
| `k8s.pod.uid` | string | Pod UID |

---

## Container Image Fields

Used for artifact→runtime resolution (Path 2 and Path 3).

| Field | Type | Notes |
|---|---|---|
| `container_image.digest` | string (sha256:...) | Strongly recommended over `container_image.id`; digest is immutable and unique across registries |
| `container_image.id` | string | OCI image ID; less stable than digest |
| `container_image.repository` | string | Image registry URL (some providers) |
| `artifact.repository` | string | Alternative registry URL field (other providers) — use `coalesce(artifact.repository, container_image.repository)` |
| `container.image.digest` | string | Same digest, but on `smartscapeNodes CONTAINER` — note the dot separator vs. underscore |

> **Field name difference.** Security findings use `container_image.digest`
> (underscore separator). `smartscapeNodes CONTAINER` uses `container.image.digest`
> (dot separator). The join condition in Path 2 bridges these:
> `on:{left[container_image.digest]==right[container.image.digest]}`.

---

## RVA / Native Entity Fields

DT RVA events (`VULNERABILITY_STATE_REPORT_EVENT`, `VULNERABILITY_STATUS_CHANGE_EVENT`,
`VULNERABILITY_TRACKING_LINK_CHANGE_EVENT`) use a separate entity namespace.
**`dt.smartscape_source.*` and `dt.entity.*` are null on these events.**

| Field | Type | Notes |
|---|---|---|
| `affected_entity.id` | entity ID | Primary entity reference on RVA events (typically PROCESS_GROUP-...) |
| `affected_entity.name` | string | Display name of the affected entity |
| `affected_entity.type` | string | Entity type: `PROCESS_GROUP`, `KUBERNETES_NODE`, `HOST`, etc. |
| `related_entities.hosts.ids` | array | Related HOST entity IDs (typed array — expand before join) |
| `related_entities.hosts.names` | array | Related HOST names |
| `related_entities.kubernetes_workloads.ids` | array | Related K8s workload entity IDs |
| `related_entities.kubernetes_workloads.names` | array | Related K8s workload names |
| `related_entities.services.ids` | array | Related service entity IDs |
| `related_entities.services.names` | array | Related service names |

> **Do not use `dt.smartscape.*` or `dt.entity.*` for RVA scoping.** They are
> null on RVA state/change events. Use `affected_entity.id` and
> `related_entities.*` instead. This is the cross-provider vs. RVA namespace split.

---

## ID Generation Notes

| Generation | Format | Used in |
|---|---|---|
| 2nd-gen (classic) | `HOST-ABC123`, `PROCESS_GROUP-DEF456`, ... | `dt.entity.*` fields, `dt.entity.*` tables (`fetch dt.entity.host`), `id_classic` column on smartscapeNodes |
| 3rd-gen (Smartscape) | UUID-like string (no type prefix) | `smartscapeNodes` `id` column, `dt.smartscape_source.id` |

The `id_classic` field on `smartscapeNodes` is the bridge between the two
generations:

```dql-snippet
// Bridge: 3rd-gen Smartscape ID → 2nd-gen classic ID
smartscapeNodes HOST, from:now()-2h
| fields id, id_classic, name
// id      = 3rd-gen Smartscape ID (matches dt.smartscape_source.id)
// id_classic = 2nd-gen classic ID (matches dt.entity.host)
```

Use `id_classic` in lookup conditions when joining smartscapeNodes to classic
entity tables (`fetch dt.entity.*`) or when matching `affected_entity.id` (which
is 2nd-gen) against a Smartscape node.
