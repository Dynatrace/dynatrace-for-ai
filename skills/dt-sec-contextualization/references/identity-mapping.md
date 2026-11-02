# Identity Mapping

## Contents

- [Mapping Primitive](#mapping-primitive)
- [Supported Identity Fields](#supported-identity-fields)
- [2-Way Match Strategy](#2-way-match-strategy)
- [Path 1 — Direct Smartscape ID](#path-1--direct-smartscape-id)
- [Path 2 — Container Image Digest → CONTAINER → Workload/Host](#path-2--container-image-digest--container--workloadhost)
  - [Single supplied digest → workload](#single-supplied-digest--workload)
- [Path 3 — AI Service → Runtime Process (`GENAI_SERVICE → SERVICE → PROCESS`)](#path-3--ai-service--runtime-process-genai_service--service--process)
- [Host-by-IP Resolution](#host-by-ip-resolution)
  - [Single supplied host IP → HOST](#single-supplied-host-ip--host)
- [Level Selection Guide](#level-selection-guide)
- [Entity-Key Bundle (required for correlation)](#entity-key-bundle-required-for-correlation)
- [Data Model](#data-model)
- [Typed Smartscape Fields (`dt.smartscape.*`)](#typed-smartscape-fields-dtsmartscape)
- [K8s Co-projected Fields](#k8s-co-projected-fields)
- [RVA / Native Entity Fields](#rva--native-entity-fields)
- [ID Generation Notes](#id-generation-notes)

---

## Mapping Primitive

For a SUPPLIED identifier or small supplied set (container-image digest, host IP, Smartscape id,
GenAI process), or any row set carrying entity-identity fields, resolve it to Smartscape entities at
a requested level. This is the only file to load for that shape. A finding STREAM needing per-entity
aggregation (risk counts, top-N) goes to [entity-enrichment.md](entity-enrichment.md) instead.

> **The pre-flight scan applies to finding streams; skip it when the caller supplies the
> identifier(s).** It lives in [entity-enrichment.md](entity-enrichment.md#pre-flight-check--identifier-availability).

> **Pure mapping primitive — no finding-schema semantics** (`finding.*`, `vulnerability.*`,
> `compliance.*`, `dt.security.risk.level` belong to the **dt-sec-insights** consumers). Input rows
> need only carry one identity field from the paths below.

---

## Supported Identity Fields

| Field | Used by path / notes |
|---|---|
| `dt.smartscape_source.id` | Path 1. Smartscape node ID (3rd-gen when available); may point to workload, cluster, namespace, or cloud resource |
| `dt.smartscape_source.type` | Path 1 granularity check: K8s workload types, `HOST`, `KUBERNETES_CLUSTER`, `KUBERNETES_NAMESPACE`, or cloud-resource types |
| `container_image.digest` | Path 2. SHA256 digest on the finding; immutable and registry-independent (Amazon ECR, Google Artifact Registry, Microsoft Defender). The node side spells it `container.image.digest` (dot separator) |
| `container_image.repository` / `.registry` / `.tags`, `artifact.repository` | Supplemental repository path, registry host, tag array; `coalesce(artifact.repository, container_image.repository)` for the registry URL. The node-side `container.image.name` includes the pull host |
| `host.ip` | Host-by-IP. IP address or array |
| `dt.smartscape.host` / `.process` / `.container` | Path 1 / Path 2 entity-scoping |
| `k8s.cluster.name`, `k8s.namespace.name` / `k8s.node.name`, `k8s.workload.name` | Tier-3 context / Tier-2 topology |

---

## 2-Way Match Strategy

Two independent paths resolve findings or artifact attributes to Smartscape entities; over a finding
stream they are combined with `append`
([entity-enrichment.md](entity-enrichment.md#k8s-workload-enrichment-paths-1--2)). Path 1 matches
`dt.smartscape_source.id` directly against a K8s workload or HOST node. Path 2 goes
`container_image.digest` → CONTAINER node → `references[is_part_of.*]` → parent workload, or
`runs_on.host` → HOST.

> **Path 1 granularity constraint.** Path 1 matches only when `dt.smartscape_source.id` identifies a
> K8s **workload** node (`K8S_DEPLOYMENT`, `K8S_DAEMONSET`, `K8S_STATEFULSET`, `K8S_CRONJOB`, `K8S_JOB`,
> `K8S_REPLICASET`) or a HOST. Providers often populate it at coarser granularity (namespace,
> cluster, cloud resources), where Path 1 returns 0 although the field is non-null. Check
> `dt.smartscape_source.type` first.

> **Path 2 is the reliable artifact→runtime path** and needs no pre-enrichment (verified: ECR and
> Artifact Registry findings for 8 images, 7 days, all resolved to running workloads).

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

Resolves a build artifact (`container_image.digest`) to the running Smartscape CONTAINER node, then
follows `is_part_of.*` to the parent workload, or `runs_on.host` to the HOST. Project the
[Entity-Key Bundle](#entity-key-bundle-required-for-correlation) on the resolved rows; resolved
workload name and ids alone are not the finished result. Over a finding stream, run the pre-flight
in entity-enrichment.md first; for a supplied digest skip it and use the single-digest form below.

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
    | lookup [
        smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}, from:now()-2h
      ], sourceField:dt.smartscape_source.id, lookupField:id, fields:{classic_entity.id=id_classic}
  ], kind:leftOuter, on:{left[container_image.digest]==right[container.image.digest]},
     fields:{dt.smartscape_source.id, classic_entity.id, workloadName=k8s.workload.name}
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

> **The HOST variant needs a `runs_on` edge on the CONTAINER node**, which only some tenants have
> (see [entity-enrichment.md § Host Enrichment by Entity](entity-enrichment.md#host-enrichment-by-entity-paths-1--2));
> where it is absent the join returns no match.

> **Digest match is registry-independent** (an Artifact Registry finding resolved to containers pulled
> from `ghcr.io`); never join on image names: the node name carries the pull host, the finding
> repository is the path only. `classic_entity.id` is the **workload's** classic ID, so rows stay one
> per workload.

### Single supplied digest → workload

One digest in, one row per running workload out. Starts from the CONTAINER nodes (no
`security.events` scan, no pre-flight) and projects the entity-key bundle.

**Placeholders**

| Placeholder | Meaning | Example | Where to get it |
|---|---|---|---|
| `<container-image-digest>` | Full image digest (string, quoted) | `sha256:9236406e43f6c6aadaf679f73c85e900bd7d8601fababf0f03be4bdf0e1e13ad` | The finding's `container_image.digest`, or the user prompt |

```dql-template
smartscapeNodes CONTAINER, from:now()-2h
| filter container.image.digest == "<container-image-digest>"
| expand dt.k8s.workload.id=coalesce(references[is_part_of.k8s_deployment],
    coalesce(references[is_part_of.k8s_daemonset],
    coalesce(references[is_part_of.k8s_cronjob],
    coalesce(references[is_part_of.k8s_statefulset],
    coalesce(references[is_part_of.k8s_job],
    references[is_part_of.k8s_replicaset])))))
| filter isNotNull(dt.k8s.workload.id)
| lookup [
    smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}, from:now()-2h
  ], sourceField:dt.k8s.workload.id, lookupField:id,
     fields:{workloadName=k8s.workload.name, classic_entity.id=id_classic, workloadType=type}
| dedup dt.k8s.workload.id
| fields container.image.digest,
         entityKey.smartscape_id = dt.k8s.workload.id,
         entityKey.classic_id    = classic_entity.id,
         entityKey.name          = workloadName,
         entityKey.type          = workloadType,
         entityKey.k8s.cluster   = k8s.cluster.name,
         entityKey.k8s.namespace = k8s.namespace.name
```

An empty result means no running CONTAINER carries that digest in the window (scanned in a registry
but not running, or replaced): report it as unresolved via the Path 2 digest join, never as a
fabricated workload. Null `entityKey.name` / `entityKey.classic_id` means the workload node is
outside the 2h Smartscape window (about half of the containers on a large tenant): keep the id and
say the name is unresolved.

---

## Path 3 — AI Service → Runtime Process (`GENAI_SERVICE → SERVICE → PROCESS`)

Scopes any process-level finding stream to AI/GenAI workloads, or resolves a process back to its
owning AI service (`GENAI_SERVICE` entities come from Dynatrace AI Observability).

**Forward — AI services → their processes.** Use to scope a finding stream to AI:

```dql
smartscapeNodes "GENAI_SERVICE", from:now()-2h
| traverse edgeTypes: {instance_of}, targetTypes: {SERVICE}
| traverse edgeTypes: {runs_on},     targetTypes: {PROCESS}
| filter toTimestamp(lifetime[end]) > now()-2h  // alive in the investigation window
| fields dt.smartscape.process = id
| dedup dt.smartscape.process
```

Adjust `from:now()-2h` and `now()-2h` together to match the investigation window (avoid
`$dt_timeframe_from` outside dashboards/notebooks).

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
| lookup [ smartscapeNodes GENAI_SERVICE, from:-2h ],
    sourceField:genai_service.id, lookupField:id, fields:{genai_service.name = name}
```

The final `lookup` resolves the AI service display name (`genai_service.name`) in the same query;
keep it in the final DQL. Join back to findings on `left[dt.smartscape.process] == right[process.id]`.

> **Duplicate rows on multi-service processes.** A process reachable via multiple
> `GENAI_SERVICE` nodes can appear more than once — dedup on `dt.smartscape.process`
> (forward) or on `{genai_service.id, …}` (reverse) as appropriate.

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

### Single supplied host IP → HOST

One IP in, one row per HOST out. Reads `smartscapeNodes HOST` only (no `security.events` scan, no
join) and projects the entity-key bundle.

**Placeholders**

| Placeholder | Meaning | Example | Where to get it |
|---|---|---|---|
| `<host-ip>` | IPv4/IPv6 address (string, quoted); a host with several IPs matches on any of them | `172.31.88.27` | The finding's `host.ip` (expand the array first), or the user prompt |

```dql-template
smartscapeNodes HOST, from:now()-2h
| expand ip
| filter ip == ip("<host-ip>")
| dedup id
| fields entityKey.smartscape_id = id,
         entityKey.classic_id    = id_classic,
         entityKey.name          = name,
         entityKey.type          = "HOST",
         host.ip                 = ip
```

An empty result means no monitored HOST reports that IP: report it as unresolved via the host-by-IP
match, never as a fabricated host.

---

## Level Selection Guide

| Requested level | Use | Notes |
|---|---|---|
| K8s workload | Path 1+2 → `K8S_DEPLOYMENT` etc. | Primary level for external findings |
| K8s node | Pod→node traversal (via `k8s.node.name` or Smartscape edge) | See `correlation.md` § Pod→Node Topology |
| HOST | Path 1+2 → `HOST` smartscapeNodes | Or host-by-IP when only IP is available |
| Cloud entity (EC2, S3, VM, etc.) | Path 1 → `smartscapeNodes "*" \| filter exists(cloud.provider)` | Cloud entities only need Path 1 |

---

## Entity-Key Bundle (required for correlation)

Every leg in a multi-leg hunt or enrichment flow projects an **entity-key bundle**, the minimal fields needed to join across legs:

```dql-snippet
| fieldsAdd entityKey.smartscape_id = dt.smartscape_source.id,
            entityKey.classic_id    = classic_entity.id,
            entityKey.name          = workloadName,    // or hostName
            entityKey.type          = dt.smartscape_source.type,
            entityKey.k8s.cluster   = k8s.cluster.name,
            entityKey.k8s.namespace = k8s.namespace.name,
            entityKey.k8s.node      = k8s.node.name    // if available (pod co-projection)
```

These keys feed the tiered correlation in [correlation.md](correlation.md); without them cross-leg
matching falls back to Tier 3 (same cluster), which is non-scoring.

---

## Data Model

Typed, K8s, and RVA entity fields used by the mapping primitive, enrichment, and correlation. Finding-schema
fields (`finding.*`, `vulnerability.*`, `compliance.*`, `dt.security.risk.level`, `actor.*`,
`threat.attack.*`) live in `dt-sec-insights/references/data-model.md`.

---

## Typed Smartscape Fields (`dt.smartscape.*`)

Typed (`smartscape_id`) 3rd-gen Smartscape IDs. Present on cross-provider findings
and on Dynatrace scan/detection events. **Not populated on DT RVA state/change
events** — those use `affected_entity.*` instead.

| Field | Type | Notes |
|---|---|---|
| `dt.smartscape.host` | HOST-... ID | On Dynatrace scans populated only for non-K8s processes — do not rely on it alone |
| `dt.smartscape.process` | PROCESS-... ID | Equals `dt.smartscape_source.id` on Dynatrace scans and detections |
| `dt.smartscape.container` | CONTAINER-... ID | Containerized processes only |
| `dt.smartscape.k8s_cluster` | K8S_CLUSTER-... ID | Cluster-level scope (`k8s.cluster.name` for the name) |
| `dt.smartscape.k8s_node` / `k8s_namespace` / `k8s_pod` | K8S_NODE / K8S_NAMESPACE / K8S_POD-... ID | Node, namespace, pod scope (`k8s.*.name` for names) |

`dt.smartscape.k8s_workload` is empty — use `k8s.workload.name` for the workload.

> **No typed process-group field on events.** `dt.smartscape.process` is process-instance
> granularity. For group-level scoping or rollups, resolve it through `smartscapeNodes PROCESS`
> (`dt.process_group.id`, `dt.process_group.detected_name`); the attribute is set on only part of the
> PROCESS nodes, so a null group means "unresolved", not "no group".

> `dt.entity.*` fields and `fetch dt.entity.*` tables are deprecated — do not use them.
> Use the typed `dt.smartscape.*` fields above and `smartscapeNodes`.

---

## K8s Co-projected Fields

Native strings (not entity IDs) on `smartscapeNodes K8S_POD` and some findings, used for Tier-2
name correlation and pod→node resolution: `k8s.cluster.name`, `k8s.namespace.name`, `k8s.node.name`
(co-projected on pods; not on all finding types), `k8s.pod.name`, `k8s.workload.name`, `k8s.pod.uid`.

---

## RVA / Native Entity Fields

DT RVA events (`VULNERABILITY_STATE_REPORT_EVENT`, `VULNERABILITY_STATUS_CHANGE_EVENT`,
`VULNERABILITY_TRACKING_LINK_CHANGE_EVENT`) use a separate entity namespace. **`dt.smartscape_source.*`
and `dt.smartscape.*` are null on these events**; scope by `affected_entity.id` and `related_entities.*`.

| Field | Type | Notes |
|---|---|---|
| `affected_entity.id` / `.name` / `.type` | entity ID / string / string | Primary entity reference (typically `PROCESS_GROUP-...`; also `KUBERNETES_NODE`, `HOST`, ...) |
| `related_entities.hosts.ids` / `.names` | array | Related HOST ids / names (typed arrays, expand before join) |
| `related_entities.kubernetes_workloads.ids` / `.names` | array | Related K8s workload ids / names |
| `related_entities.services.ids` / `.names` | array | Related service ids / names |

> **RVA process groups resolve to processes.** An `affected_entity.id` of type `PROCESS_GROUP` equals
> `dt.process_group.id` on `smartscapeNodes PROCESS`, giving the member `PROCESS-…` IDs.

> **Resolving RVA ids to Smartscape.** These ids are 2nd-gen: `expand` the typed
> `related_entities.<group>.ids` array, then `lookup`/`join` `smartscapeNodes` on
> `lookupField: id_classic`. Full patterns: [rva-entity-resolution.md](rva-entity-resolution.md).
> Rankings and the vulnerabilities of one known entity stay in **dt-sec-insights**
> (`vulnerabilities-rankings.md`, `vulnerabilities-dynatrace.md` § One known entity).

---

## ID Generation Notes

2nd-gen (classic) ids look like `HOST-ABC123` / `PROCESS_GROUP-DEF456` and appear in RVA
`affected_entity.*` / `related_entities.*` and in `id_classic` on `smartscapeNodes`. 3rd-gen
(Smartscape) ids look like `<TYPE>-<HEX>` and appear in `smartscapeNodes` `id`,
`dt.smartscape_source.id`, and `dt.smartscape.*`. Use `id_classic` in a lookup only when matching
the 2nd-gen RVA fields; everything else joins on `id`.
