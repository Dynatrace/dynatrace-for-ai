# Vulnerability Entity Rankings — `security.events`

"Most vulnerable hosts / K8s workloads / components" and "which entities are affected
by CVE X" for **Dynatrace-native RVA**. These build on the canonical RVA snapshot
pipeline — **Steps 1–3** in
[vulnerabilities-dynatrace.md § DT RVA: Full Snapshot Queries](vulnerabilities-dynatrace.md#dt-rva-full-snapshot-queries)
— and resolve entity identity via `smartscapeNodes` (DT RVA carries
`related_entities.*` / `affected_entity.*`, not the external `object.*` identifiers).

> **Related references:** scoping RVA to a *known* entity (filter, not rank) →
> [vulnerabilities-dynatrace.md § Entity Scoping Workflows](vulnerabilities-dynatrace.md#dt-rva-entity-scoping-workflows) ·
> external-scanner component rankings → [vulnerabilities-external.md](vulnerabilities-external.md) ·
> mapping *external* findings to entities (3-way match / host-by-IP / cloud) →
> [entity-enrichment.md](../../dt-sec-contextualization/references/entity-enrichment.md).

## Contents

- [Resolving RVA entity names via Smartscape](#resolving-rva-entity-names-via-smartscape)
- [Top vulnerable components (libraries) — DT RVA](#top-vulnerable-components-libraries--dt-rva)
- [Most vulnerable hosts — DT RVA](#most-vulnerable-hosts--dt-rva)
- [Most vulnerable K8s workloads (UC-V2)](#most-vulnerable-k8s-workloads-uc-v2)
- [Entities indirectly related to a CVE (UC-V5)](#entities-indirectly-related-to-a-cve-uc-v5)

---

## Resolving RVA entity names via Smartscape

**Canonical pattern for ranking/listing RVA findings by entity (host, K8s
workload, service, …).** `related_entities.<group>.ids` and `affected_entity.id`
on RVA events carry *classic* (2nd-gen) entity ids. To rank or list by entity:

1. If the entity type can be the directly-affected entity (HOST, KUBERNETES_NODE),
   merge `affected_entity.id` into the typed `ids` array at record grain **before**
   the Step-3 summarize (it is not repeated in `related_entities.*`).
2. Collect the typed `related_entities.<group>.ids` array in Step 3 (collect ids,
   not names).
3. `expand` the ids array, then `join` / `lookup` `smartscapeNodes` on
   `lookupField:id_classic` to resolve the **current** name + Smartscape id.
4. Aggregate by the resolved `{dt.smartscape*, name}` keys.

Rank on the resolved Smartscape identity — never on the raw
`related_entities.<group>.names` array, which can carry stale or duplicate names.
The host and workload recipes below are concrete instances of this pattern;
[vulnerabilities-dynatrace.md § Named entity list for a specific vulnerability](vulnerabilities-dynatrace.md#named-entity-list-for-a-specific-vulnerability)
(Option B) shows the same shape for an arbitrary entity type via `smartscapeNodes "*"`.

## Top vulnerable components (libraries) — DT RVA

Apply Steps 1–3 (with `affected_entity.vulnerable_component.names` collected),
then:

```dql-snippet
| filter vulnerability.resolution.status=="OPEN"
     AND vulnerability.mute.status!="MUTED"
| expand component = affected_entity.vulnerable_component.names
| filter isNotNull(component)
| summarize vulnerabilities = countDistinctExact(vulnerability.display_id), by: {component}
| sort vulnerabilities desc
| limit 20
```

> **Count distinct vulnerabilities after `expand`.** The Step-3 component arrays
> are collected per affected entity, so the same `(vulnerability, component)`
> pair appears once per entity after `expand`. A plain `count()` here counts
> those duplicate rows and inflates the ranking 3–50×. Always
> `countDistinctExact(vulnerability.display_id)` when ranking components,
> workloads, or hosts after an `expand`.

## Most vulnerable hosts — DT RVA

Do not filter `affected_entity.type == "HOST"` for host ranking. RVA affected
entities are often process groups or process-group instances, with the host
context surfaced under `related_entities.hosts.*`. **But when
`affected_entity.type == "HOST"` the directly-affected host is the
`affected_entity` itself and is NOT repeated in `related_entities.hosts.*`** —
so a query that reads host context only from `related_entities.hosts.*` silently
drops every host that was the direct target. Merge the affected host back into
the typed `ids` array first, then resolve names through Smartscape.

This is the canonical RVA entity-ranking shape (see [§ Resolving RVA entity
names via Smartscape](#resolving-rva-entity-names-via-smartscape)): related
entities store *classic* ids, so expand `related_entities.hosts.ids` and look
them up in `smartscapeNodes` on `id_classic` to get the current name + Smartscape
id — do not rank on the raw `related_entities.hosts.names` array.

> **Do the affected-host merge at record grain, BEFORE the Step-3 summarize —
> never inside it.** A conditional mixed with aggregations inside `summarize`
> (`if(affected_entity.type == "HOST", collectArray(...), else: array())`) is
> rejected with `INVALID_MIX_OF_AGGREGATIONS_AND_OTHER_EXPRESSIONS`. A plain
> record-level `fieldsAdd` after the dedup is valid and is the correct place.
> See [common-patterns.md § Mistakes #45](common-patterns.md#mistakes-to-avoid).

```dql-snippet
// After Step-1 dedup, BEFORE the Step-3 summarize — merge the directly-affected
// host into the typed ids array (record grain, no aggregation):
| fieldsAdd related_entities.hosts.ids = if(affected_entity.type == "HOST",
    arrayConcat(array(affected_entity.id), related_entities.hosts.ids),
    else: related_entities.hosts.ids)
// Step 3 summarize — collect the typed ids only (names come from Smartscape):
| summarize {
    ...,  // mute/resolution status arrays + risk.score, see shared Step 3 block
    hosts.ids = arrayRemoveNulls(collectDistinct(related_entities.hosts.ids, expand:true))
  }, by: {vulnerability.display_id, vulnerability.id}
// ... fieldsAdd derives resolution.status / mute.status / risk.level ...
| filter vulnerability.resolution.status=="OPEN"
     AND vulnerability.mute.status!="MUTED"
| expand host.id = hosts.ids
| filter isNotNull(host.id)
| lookup [
    smartscapeNodes HOST
  ], sourceField:host.id, lookupField:id_classic, fields:{host.name=name, dt.smartscape.host=id}
| summarize {
    Vulnerabilities=count(),
    Critical=countIf(vulnerability.risk.level=="CRITICAL"),
    High=countIf(vulnerability.risk.level=="HIGH")
  }, by:{dt.smartscape.host, host.name}
| sort Critical desc, High desc, Vulnerabilities desc
| limit 10
```

The golden merges only `affected_entity.type == "HOST"`. If you also want
hosts that were the direct target as a Kubernetes node, extend the condition to
`in(affected_entity.type, {"HOST", "KUBERNETES_NODE"})` — nodes are hosts and
`smartscapeNodes HOST` resolves them.

> **Why `count()` here is correct (and not a count-distinct best-practice violation).**
> The pipeline is already deduped to one row per vulnerability
> (`{vulnerability.display_id, vulnerability.id}`) before the `expand`, so after
> `expand host.id` each row is a distinct `(vulnerability, host)` pair and
> `count()` per host equals the number of vulnerabilities on that host. The
> `countDistinctExact` rule applies when the grain entering the `expand` is *not*
> already one-row-per-counted-item (e.g. the component ranking above, which
> expands directly off collected arrays).

## Most vulnerable K8s workloads (UC-V2)

> **K8s/host context on RVA events lives ONLY in `related_entities.*`.** The
> generic namespaces (`k8s.namespace.name`, `k8s.cluster.name`, `host.name`,
> `dt.entity.*`, `dt.smartscape*`) are **null** on RVA state/change events — a
> filter on them returns 0 rows. When that happens, do **not** fall back to
> pattern-matching `affected_entity.name` (process-group names are not workload
> identities and the same workload appears under multiple PG name variants).
> Pivot to the typed `related_entities.kubernetes_workloads.ids` array + a
> `smartscapeNodes` lookup on `id_classic` — that is the canonical recovery.

For typed entity questions like "most vulnerable workloads" / "top affected
hosts" / "services hit by this CVE", **use the typed sub-field**
(`related_entities.kubernetes_workloads.ids`) — not the all-types union
`related_entities.ids`. The union mixes cluster ids + host ids +
service ids + workload ids into one array; expanding it for a
workload-specific question silently surfaces hosts/clusters next to workloads,
answering a different question than asked.

Rank on the typed `ids` (not `names`): related entities store *classic* ids, so
expand `related_entities.kubernetes_workloads.ids` and `join smartscapeNodes`
on `id_classic` to resolve the current workload name + Smartscape id (see [§
Resolving RVA entity names via Smartscape](#resolving-rva-entity-names-via-smartscape)).
Apply Steps 1–3 with the typed sub-field collected in the Step 3 summarize:

```dql-snippet
// Step 3 summarize — collect the typed ids sub-field (names come from Smartscape):
| summarize {
    ...,  // mute/resolution status arrays + risk.score, see shared Step 3 block
    related_entities.kubernetes_workloads.ids = arrayRemoveNulls(
      collectDistinct(related_entities.kubernetes_workloads.ids, expand:true)
    )
  }, by: {vulnerability.display_id, vulnerability.id}
// ... fieldsAdd derives resolution.status / mute.status / risk.level ...
| filter vulnerability.resolution.status=="OPEN"
     AND vulnerability.mute.status!="MUTED"
| expand workload.id = related_entities.kubernetes_workloads.ids
| filter isNotNull(workload.id)
| join [
    smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}, from:now()-2h
  ], on:{left[workload.id]==right[id_classic]},
     fields:{workload.name=k8s.workload.name, dt.smartscape_source.id=id}
| summarize {
    Vulnerabilities=count(),
    Critical=countIf(vulnerability.risk.level=="CRITICAL"),
    High=countIf(vulnerability.risk.level=="HIGH")
  }, by:{dt.smartscape_source.id, workload.name}
| sort Critical desc, High desc
| limit 10
```

(`count()` is correct here for the same reason as the host ranking above — the
grain entering the `expand` is already one row per vulnerability.)

### Related-entity union (blast-radius across types)

Use the `related_entities.names` (all-types union) variant **only** when the
question is genuinely cross-type — e.g. "what entities — services, hosts,
workloads, clusters — are affected by this CVE?" (UC-V5 blast radius). For
typed entity questions, use the typed sub-field above.

## Entities indirectly related to a CVE (UC-V5)

After Steps 1–3, filter by CVE and expand the full related-entity blast radius:

```dql-snippet
// After Steps 1–3:
| filter in("CVE-2021-44228", vulnerability.references.cve)
| filter vulnerability.resolution.status=="OPEN"
| expand relatedEntity = related_entities.names
| filter isNotNull(relatedEntity)
| summarize vulnerabilities=count(), by:{relatedEntity}
| sort vulnerabilities desc
```

For directly affected entities, use `affected_entity.names` instead of
`related_entities.names`.

For CVE membership, prefer `in("<CVE>", vulnerability.references.cve)` before
or after aggregation. If tenant compatibility is uncertain, use the explicit
fallback `expand cve = vulnerability.references.cve | filter cve == "<CVE>"`.
Do not compare the whole CVE array to a string.
