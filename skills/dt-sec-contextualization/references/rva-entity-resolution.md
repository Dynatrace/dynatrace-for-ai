# RVA Entity Resolution — from an RVA finding to a Smartscape entity

Resolve the entity ids on Dynatrace-native RVA events (`affected_entity.*`,
`related_entities.<group>.ids`) to the **current** entity name and Smartscape id
through `smartscapeNodes`, and go the other way (a known Smartscape id to its classic id).
The RVA event pipeline itself (Steps 1–3, entity scope, CVE filter) and the entity rankings
built on it ("most vulnerable hosts / K8s workloads") live in **dt-sec-insights**
`vulnerabilities-dynatrace.md` and `vulnerabilities-rankings.md`; those queries group on the
in-event classic id alone (the event-time name is display metadata). This file owns the id-resolution mechanics,
including the tails that add the current name and Smartscape id to such a ranking.

> **Related references:** field table and id generations →
> [identity-mapping.md § RVA / Native Entity Fields](identity-mapping.md#rva--native-entity-fields) ·
> mapping *external* findings to entities (2-way match / host-by-IP / cloud) →
> [entity-enrichment.md](entity-enrichment.md).

## Contents

- [Namespace and id generations](#namespace-and-id-generations)
- [Smartscape id -> classic id (one known entity)](#smartscape-id---classic-id-one-known-entity)
- [RVA classic id -> current name and Smartscape id](#rva-classic-id---current-name-and-smartscape-id)
- [Per-type recipes](#per-type-recipes)
  - [Host](#host)
  - [K8s workload (ReplicaSet roll-up)](#k8s-workload-replicaset-roll-up)
  - [Any other type](#any-other-type)
- [Resolving a ranking result](#resolving-a-ranking-result)
  - [Host ranking tail](#host-ranking-tail)
  - [K8s workload ranking tail](#k8s-workload-ranking-tail)
  - [CVE to entities tail](#cve-to-entities-tail)
- [Notes](#notes)

---

## Namespace and id generations

RVA events carry **2nd-gen (classic)** entity ids in `affected_entity.id` and in the typed
`related_entities.<group>.ids` arrays. The generic `dt.smartscape*` / `dt.smartscape_source.*`
fields are **null** on them, so a filter or join on those returns nothing. Field list and id
generation table:
[identity-mapping.md § RVA / Native Entity Fields](identity-mapping.md#rva--native-entity-fields).

`smartscapeNodes` bridges the generations: its `id_classic` column matches the RVA classic ids and
its `id` column is the 3rd-gen Smartscape id. Resolve on `id_classic`; everything else joins on `id`.

## Smartscape id -> classic id (one known entity)

When the user supplies a Smartscape id, resolve it to its classic id before scoping RVA events
(the one-known-entity scope in **dt-sec-insights** `vulnerabilities-dynatrace.md` § One known entity
takes both ids).

**Placeholders:** `<SMARTSCAPE_ID>` — the Smartscape node id the user supplied, format `<TYPE>-` plus 16 hex characters (e.g. `K8S_CLUSTER-F867CA38C2E66AF1`). If you only know the name, find it with `smartscapeNodes "K8S_CLUSTER" | fields id, id_classic, name`. Keep the `toSmartscapeId("…")` wrapper: `id` is a typed Smartscape id and a bare string literal matches nothing.

```dql-template
smartscapeNodes "*"
| filter id == toSmartscapeId("<SMARTSCAPE_ID>")
| fields id, id_classic
```

Returns `id` (Smartscape, e.g. `K8S_CLUSTER-F867CA38C2E66AF1`) and `id_classic` (classic, e.g.
`KUBERNETES_CLUSTER-8D1821868AEBCC21`). Pass **both** to the insights entity scope. Say in the
answer why: RVA events store classic (2nd-gen) ids, so `id_classic` is the value the scope must
receive, and the Smartscape `id` is kept alongside it for the hand-off.

## RVA classic id -> current name and Smartscape id

Pattern for building a ranking or listing of RVA findings by entity (host, K8s workload, service, …)
that resolves while collecting ids. To resolve an *existing* dt-sec-insights ranking result, append
a tail instead ([§ Resolving a ranking result](#resolving-a-ranking-result)).

1. If the entity type can be the directly-affected entity (HOST, KUBERNETES_NODE), merge
   `affected_entity.id` into the typed `ids` array at record grain **before** the Step-3 summarize
   (it is not repeated in `related_entities.*`).
2. Collect the typed `related_entities.<group>.ids` array in Step 3 (collect ids, not names).
3. `expand` the ids array, then `lookup` (or `join`) `smartscapeNodes` on `lookupField:id_classic`
   to resolve the **current** name and Smartscape id.
4. Aggregate by the resolved `{Smartscape id, name}` keys.

Rank on the resolved Smartscape identity, never on the raw `related_entities.<group>.names`
array, which can carry stale or duplicate names.

Placeholders: `<GROUP>` — the `related_entities` group (`hosts`, `kubernetes_workloads`,
`services`, …); `<SMARTSCAPE_TYPE>` — the matching `smartscapeNodes` type, or `"*"` when unsure
(see [§ Per-type recipes](#per-type-recipes)). The block takes the output of the RVA Step 1–3
pipeline in **dt-sec-insights**
`vulnerabilities-dynatrace.md` (Steps 1–3, with `related_entities.<GROUP>.ids` collected in
Step 3):

```dql-template
// RVA Steps 1–3 from vulnerabilities-dynatrace.md, collecting
// related_entities.<GROUP>.ids = arrayRemoveNulls(collectDistinct(related_entities.<GROUP>.ids, expand:true))
| filter vulnerability.resolution.status=="OPEN"
     AND vulnerability.mute.status!="MUTED"
| expand entity.id = related_entities.<GROUP>.ids
| filter isNotNull(entity.id)
| lookup [
    smartscapeNodes <SMARTSCAPE_TYPE>
  ], sourceField:entity.id, lookupField:id_classic, fields:{entity.name=name, entity.smartscape.id=id}
| filterOut isNull(entity.smartscape.id)
| summarize vulnerabilities=count(), by:{entity.smartscape.id, entity.name}
| sort vulnerabilities desc
```

`filterOut isNull(...)` drops ids with no active Smartscape node (expired entities). `count()` is
valid only when the grain entering the `expand` is already one row per vulnerability (the Step-3
output); use `countDistinctExact(vulnerability.display_id)` when expanding directly off collected
arrays.

## Per-type recipes

### Host

RVA affected entities are often process groups or process-group instances, with the host context
under `related_entities.hosts.*`. **When `affected_entity.type == "HOST"` the directly-affected host
is the `affected_entity` itself and is NOT repeated in `related_entities.hosts.*`**, so reading
host context only from `related_entities.hosts.*` silently drops every host that was the direct
target. Merge the affected host into the typed `ids` array first. Do not filter
`affected_entity.type == "HOST"` for host ranking.

Insert after the Step-1 dedup, **before** the Step-3 summarize (record grain, no aggregation):

```dql-snippet
| fieldsAdd related_entities.hosts.ids = if(in(affected_entity.type, {"HOST", "KUBERNETES_NODE"}),
    arrayConcat(array(affected_entity.id), related_entities.hosts.ids),
    else: related_entities.hosts.ids)
```

Nodes are hosts, so `smartscapeNodes HOST` resolves both types; to merge only direct HOST targets
use `affected_entity.type == "HOST"`. Do the merge at record grain, never inside `summarize`: a
conditional mixed with aggregations is rejected with
`INVALID_MIX_OF_AGGREGATIONS_AND_OTHER_EXPRESSIONS`.

Resolve the collected `hosts.ids` with the generic pattern above (`smartscapeNodes HOST`). For the
dt-sec-insights host ranking (id + event-time name), use [§ Host ranking tail](#host-ranking-tail).

### K8s workload (ReplicaSet roll-up)

K8s and host context on RVA events lives only in `related_entities.*`; the generic
`k8s.namespace.name`, `k8s.cluster.name`, `host.name` namespaces are null. Do not fall back to
pattern-matching `affected_entity.name` (process-group names are not workload identities). Use the
typed `related_entities.kubernetes_workloads.ids` array, not the all-types union
`related_entities.ids` (it mixes cluster, host, service and workload ids).

The ids are `CLOUD_APPLICATION-…` classic ids. Resolve them against all workload node types,
including `K8S_REPLICASET`, and read the workload name from `k8s.workload.name`. The concrete tail
for the dt-sec-insights workload ranking is
[§ K8s workload ranking tail](#k8s-workload-ranking-tail).

### Any other type

For services, clusters or a cross-type list, `smartscapeNodes "*"` needs no
narrowing (process groups are the exception, see below); swap the `related_entities.<group>` group for `.services.*`, `.kubernetes_workloads.*`,
etc. Start from a record that already carries the typed ids (for example, one
`VULNERABILITY_STATE_REPORT_EVENT` per vulnerability, dedup by `{affected_entity.id, vulnerability.id}`);
the tail is [§ CVE to entities tail](#cve-to-entities-tail).

Always project `affected_entity.*` as well: when `affected_entity.type` is `HOST` or
`KUBERNETES_NODE` the directly-affected entity is not repeated in `related_entities.hosts.*`.
A directly-affected entity itself resolves the same way: `lookup` its `affected_entity.id` on
`id_classic`, **except `PROCESS_GROUP`**. An `affected_entity.type == "PROCESS_GROUP"` id has no node
of its own, so the `id_classic` lookup returns nothing and an active group would be reported as
unresolved (checked on two tenants: 0 of 75 groups resolved on `id_classic`, 74 on the group field).
Resolve it on `dt.process_group.id` of `smartscapeNodes PROCESS`, which returns the member processes:

```dql-snippet
| lookup [
    smartscapeNodes PROCESS
    | fields process.id = id, process.name = name, dt.process_group.id
  ], sourceField:affected_entity.id, lookupField:dt.process_group.id, fields:{process.id, process.name}
```

The lookup keeps one member process per group; use a `join` when every member is needed. Branch on `affected_entity.type` before
choosing the lookup field.

## Resolving a ranking result

The dt-sec-insights entity queries (`vulnerabilities-rankings.md`) are pure `security.events`
queries: they output the classic id and the event-time name, which can be generic or stale. Append
one of these tails to the query's last stage to add the **current** name and the Smartscape id.
Each tail resolves on `id_classic`, which maps one classic id to exactly one Smartscape node, so it
changes neither counts nor order. An id with no active node (expired entity) keeps its row with the
event-time name and a null Smartscape id. The lookup lands the current name in a temporary field
(a direct `fields:{host.name=name}` raises `FIELD_OVERRIDDEN`); `coalesce` picks it and the
temporary field is removed. Say in the answer that the tail leaves counts and order unchanged and
that event-time names can be generic or stale, which is why the current name replaces them.

### Host ranking tail

**Input contract:** `host.id` (classic id, `HOST-…`) and `host.name` (event-time name) from
dt-sec-insights `vulnerabilities-rankings.md` § Most vulnerable hosts — DT RVA. **Adds:**
`dt.smartscape.host` (Smartscape id); `host.name` becomes the current name.

```dql-snippet
| lookup [
    smartscapeNodes HOST
  ], sourceField:host.id, lookupField:id_classic, fields:{host.current_name=name, dt.smartscape.host=id}
| fieldsAdd host.name = coalesce(host.current_name, host.name)
| fieldsRemove host.current_name
```

### K8s workload ranking tail

**Input contract:** `workload.id` (classic id, `CLOUD_APPLICATION-…`) and `workload.name`
(event-time name) from dt-sec-insights `vulnerabilities-rankings.md` § Most vulnerable K8s workloads
(UC-V2). **Adds:** `dt.smartscape_source.id` (Smartscape id, e.g. `K8S_DEPLOYMENT-…`);
`workload.name` becomes the current `k8s.workload.name`. `K8S_REPLICASET` is in the type list so a
classic id that resolves to a ReplicaSet node still gets a name and id.

```dql-snippet
| lookup [
    smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}, from:now()-2h
  ], sourceField:workload.id, lookupField:id_classic, fields:{workload.current_name=k8s.workload.name, dt.smartscape_source.id=id}
| fieldsAdd workload.name = coalesce(workload.current_name, workload.name)
| fieldsRemove workload.current_name
```

### CVE to entities tail

**Input contract:** `related_host.id` (classic id) and `related_host.name` (event-time name) from
dt-sec-insights `vulnerabilities-rankings.md` § Named entity list for a specific vulnerability,
Option B. **Adds:** `dt.smartscape_source.id`; `related_host.name` becomes the current name. Rows
with no active Smartscape node (expired entities) are dropped.

```dql-snippet
| lookup [
    smartscapeNodes "*"
  ], sourceField:related_host.id, lookupField:id_classic, fields:{related_host.current_name=name, dt.smartscape_source.id=id}
| filterOut isNull(dt.smartscape_source.id)
| fieldsAdd related_host.name = coalesce(related_host.current_name, related_host.name)
| fieldsRemove related_host.current_name
```

For other entity types, swap the field prefix (`related_host.*`) to match the expanded group
(`.kubernetes_workloads.*`, `.services.*`, …); `smartscapeNodes "*"` needs no narrowing.

## Notes

- **Id prefix differs from the group name.** `related_entities.kubernetes_workloads.ids` hold
  `CLOUD_APPLICATION-…` ids, not `KUBERNETES_WORKLOAD-…`; resolve through `id_classic`, never by
  matching the prefix.
- **Arrays need `expand`.** `related_entities.<group>.ids` is an array; `lookup` / `join` on the
  array itself matches nothing. Filter `isNotNull` on the expanded value.
- **Rank on the identity, not the name.** Aggregate by the id (the classic id in dt-sec-insights
  rankings, `{Smartscape id, name}` when resolving in-pipeline), never on the raw
  `related_entities.<group>.names` array, and add the current name afterwards.
- **RVA process groups resolve to processes.** An RVA `affected_entity.id` of type `PROCESS_GROUP`
  equals `dt.process_group.id` on `smartscapeNodes PROCESS`, giving the member `PROCESS-…` ids.
- **Empty 30m window.** If the 30m pipeline returns nothing, use the 24h latest-known-state fallback in **dt-sec-insights** `vulnerabilities-dynatrace.md`
  (§ Latest-known-state fallback when 30m is empty or stale).
