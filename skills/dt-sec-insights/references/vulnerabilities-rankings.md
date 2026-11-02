# Vulnerability Rankings — `security.events`

"Top vulnerable components / images / artifacts", "most vulnerable hosts / K8s workloads" and
"which entities are affected by CVE X": the top-X and grouping use cases for vulnerabilities,
for **Dynatrace-native RVA** and for **external scanners**. Every query here is a pure
`security.events` query that groups on fields carried in the events.

- **RVA** queries build on the canonical snapshot pipeline — **Steps 1–3** in
  [vulnerabilities-dynatrace.md § DT RVA: Full Snapshot Queries](vulnerabilities-dynatrace.md#dt-rva-full-snapshot-queries) —
  and group on the entity fields RVA events carry in-event: the classic id
  (`affected_entity.id`, `related_entities.<group>.ids`) and the event-time name
  (`affected_entity.name`, `related_entities.<group>.names`). Rankings output the classic id, that
  in-event name and the counts. Resolving the ids to the current name and the Smartscape id is
  entity context, owned by dt-sec-contextualization `rva-entity-resolution.md`
  § Resolving a ranking result.
- **External** rankings (`VULNERABILITY_FINDING` from Snyk, Qualys, Tenable, ECR, GitHub, …) are one-shot
  findings: no dedup-to-state pipeline, but always exclude Dynatrace rows null-safely and rank by
  **distinct** vulnerabilities. Field semantics: [vulnerabilities-external.md](vulnerabilities-external.md).

> **Related references:** vulnerabilities of ONE known entity (filter, not rank) →
> [vulnerabilities-dynatrace.md § One known entity](vulnerabilities-dynatrace.md#one-known-entity--step-2-scope) · keyword / substring
> scope across entities → [vulnerabilities-dynatrace.md § Step 4](vulnerabilities-dynatrace.md#step-4--final-filter-variants-append-after-step-3) ·
> external-scanner finding semantics, verification against RVA, newly reported → [vulnerabilities-external.md](vulnerabilities-external.md) ·
> current entity name, Smartscape id, deep links, ReplicaSet roll-up for a ranking result →
> dt-sec-contextualization `rva-entity-resolution.md` § Resolving a ranking result ·
> mapping *external* findings to entities (2-way match / host-by-IP / cloud) →
> dt-sec-contextualization `entity-enrichment.md`.

## Contents

- [Top vulnerable components (libraries) — DT RVA](#top-vulnerable-components-libraries--dt-rva)
- [Most vulnerable hosts — DT RVA](#most-vulnerable-hosts--dt-rva)
- [Most vulnerable K8s workloads (UC-V2)](#most-vulnerable-k8s-workloads-uc-v2)
- [Entities indirectly related to a CVE (UC-V5)](#entities-indirectly-related-to-a-cve-uc-v5)
- [Named entity list for a specific vulnerability](#named-entity-list-for-a-specific-vulnerability)
- [Top vulnerable components (libraries) — external findings (UC-V9)](#top-vulnerable-components-libraries--external-findings-uc-v9)
- [External vulnerable container images](#external-vulnerable-container-images)
- [External vulnerable code artifacts](#external-vulnerable-code-artifacts)

---

## Top vulnerable components (libraries) — DT RVA

Apply Steps 1–3 (with `affected_entity.vulnerable_component.names` collected),
then:

```dql-snippet
| filter vulnerability.resolution.status=="OPEN"
     AND vulnerability.mute.status!="MUTED"
| expand component = affected_entity.vulnerable_component.names
| filter isNotNull(component)
| fieldsAdd component = lower(component)        // merge case variants of the same package
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

Do not filter `affected_entity.type == "HOST"` for host ranking. A directly-affected host is NOT
repeated in `related_entities.hosts.*`, so merge it into the typed `ids` and `names` arrays at
record grain **before** the Step-3 summarize (never inside it). The typed `ids` and `names` arrays
are positionally paired, so zip them into one `{id, name}` record per host before aggregating;
independent `collectDistinct` calls on the two arrays would lose the pairing.

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT",
                        "VULNERABILITY_STATUS_CHANGE_EVENT",
                        "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
// BEFORE the Step-3 summarize — merge the directly-affected host into the typed
// ids/names arrays, then pair them positionally (record grain, no aggregation):
| fieldsAdd isHost = affected_entity.type == "HOST"
| fieldsAdd hostIds = if(isHost, arrayConcat(array(affected_entity.id), related_entities.hosts.ids),
                         else: related_entities.hosts.ids),
            hostNames = if(isHost, arrayConcat(array(affected_entity.name), related_entities.hosts.names),
                           else: related_entities.hosts.names)
| fieldsAdd hostPairs = iCollectArray(record(id = hostIds[], name = hostNames[]))
// Step 3 summarize (trimmed to the fields this ranking needs) — collect the id/name pairs:
| sort {timestamp, direction:"descending"}
| summarize {
    vulnerability.risk.score=round(takeMax(if(vulnerability.mute.status!="MUTED",vulnerability.risk.score,else:0)),decimals:1),
    muteStatuses=collectDistinct(vulnerability.mute.status),
    resolutionStatuses=collectDistinct(vulnerability.resolution.status),
    hosts = arrayRemoveNulls(collectDistinct(hostPairs, expand:true))
  }, by: {vulnerability.display_id, vulnerability.id}
| fieldsAdd vulnerability.resolution.status=if(in("OPEN",resolutionStatuses), "OPEN", else: "RESOLVED"),
            vulnerability.mute.status=if(in("NOT_MUTED",muteStatuses), "NOT_MUTED", else: "MUTED"),
            vulnerability.risk.level=if(vulnerability.risk.score>=9,"CRITICAL",
                   else:if(vulnerability.risk.score>=7,"HIGH",
                   else:if(vulnerability.risk.score>=4,"MEDIUM",
                   else:if(vulnerability.risk.score>=0.1,"LOW",
                   else:"NONE"))))
| fieldsRemove muteStatuses, resolutionStatuses
| filter vulnerability.resolution.status=="OPEN"
     AND vulnerability.mute.status!="MUTED"
| expand host = hosts
| fieldsAdd host.id = host[id], host.name = host[name]
| filter isNotNull(host.id)
| dedup {vulnerability.display_id, host.id}
| summarize {
    Vulnerabilities=count(),
    Critical=countIf(vulnerability.risk.level=="CRITICAL"),
    High=countIf(vulnerability.risk.level=="HIGH"),
    host.name=takeFirst(host.name)
  }, by:{host.id}
| sort Critical desc, High desc, Vulnerabilities desc
| limit 10
```

Output columns: `host.id` (classic id, `HOST-…`), `host.name` (name at event time, which can be
generic or stale; display only, one of the event-time names via `takeFirst`), `Vulnerabilities`, `Critical`, `High`.

The ranking groups by the **entity id alone**. One host can carry different event-time names
(renamed, or reported under a generic name by different entities), and grouping by `{host.id, host.name}`
would split its counts across rows and could drop it out of the top 10. The `dedup {vulnerability.display_id, host.id}`
before the `summarize` keeps a vulnerability counted once per host even when its pairs differ only by name.

The block merges only `affected_entity.type == "HOST"`. To include Kubernetes nodes that were the
direct target, extend the condition to `isHost = in(affected_entity.type, {"HOST", "KUBERNETES_NODE"})`.

> **Why `count()` here is correct (and not a count-distinct best-practice violation).**
> The pipeline is already deduped to one row per vulnerability
> (`{vulnerability.display_id, vulnerability.id}`) before the `expand`, so after
> `expand host` each row is one `(vulnerability, host id and name)` pair; the
> `dedup {vulnerability.display_id, host.id}` collapses pairs that differ only by name, so
> `count()` per host equals the number of vulnerabilities on that host. The
> `countDistinctExact` rule applies when the grain entering the `expand` is *not*
> already one-row-per-counted-item (e.g. the component ranking above, which
> expands directly off collected arrays).

To add the current name and Smartscape id (deep links, ReplicaSet roll-up), resolve the result with dt-sec-contextualization `rva-entity-resolution.md` § Resolving a ranking result.

## Most vulnerable K8s workloads (UC-V2)

K8s and host context on RVA events lives only in `related_entities.*`: the generic
`k8s.namespace.name`, `k8s.cluster.name`, `host.name`, `dt.smartscape*` fields are null, and
`affected_entity.name` is not a workload identity. For typed questions use the typed sub-fields
`related_entities.kubernetes_workloads.ids` / `.names` (positionally paired), not the all-types
union `related_entities.ids`. The block below carries Step 1 and a trimmed Step 3 (only the fields
the ranking needs) with the typed id/name pairs collected:

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT",
                        "VULNERABILITY_STATUS_CHANGE_EVENT",
                        "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
// BEFORE the Step-3 summarize — pair the typed ids/names positionally (record grain):
| fieldsAdd workloadPairs = iCollectArray(record(id = related_entities.kubernetes_workloads.ids[],
                                                 name = related_entities.kubernetes_workloads.names[]))
// Step 3 summarize (trimmed to the fields this ranking needs) — collect the id/name pairs:
| sort {timestamp, direction:"descending"}
| summarize {
    vulnerability.risk.score=round(takeMax(if(vulnerability.mute.status!="MUTED",vulnerability.risk.score,else:0)),decimals:1),
    muteStatuses=collectDistinct(vulnerability.mute.status),
    resolutionStatuses=collectDistinct(vulnerability.resolution.status),
    workloads = arrayRemoveNulls(collectDistinct(workloadPairs, expand:true))
  }, by: {vulnerability.display_id, vulnerability.id}
| fieldsAdd vulnerability.resolution.status=if(in("OPEN",resolutionStatuses), "OPEN", else: "RESOLVED"),
            vulnerability.mute.status=if(in("NOT_MUTED",muteStatuses), "NOT_MUTED", else: "MUTED"),
            vulnerability.risk.level=if(vulnerability.risk.score>=9,"CRITICAL",
                   else:if(vulnerability.risk.score>=7,"HIGH",
                   else:if(vulnerability.risk.score>=4,"MEDIUM",
                   else:if(vulnerability.risk.score>=0.1,"LOW",
                   else:"NONE"))))
| fieldsRemove muteStatuses, resolutionStatuses
| filter vulnerability.resolution.status=="OPEN"
     AND vulnerability.mute.status!="MUTED"
| expand workload = workloads
| fieldsAdd workload.id = workload[id], workload.name = workload[name]
| filter isNotNull(workload.id)
| dedup {vulnerability.display_id, workload.id}
| summarize {
    Vulnerabilities=count(),
    Critical=countIf(vulnerability.risk.level=="CRITICAL"),
    High=countIf(vulnerability.risk.level=="HIGH"),
    workload.name=takeFirst(workload.name)
  }, by:{workload.id}
| sort Critical desc, High desc
| limit 10
```

Output columns: `workload.id` (classic id, `CLOUD_APPLICATION-…`), `workload.name` (name at event
time; display only, one of the event-time names via `takeFirst`), `Vulnerabilities`, `Critical`, `High`. As in the host
ranking, it groups by the id alone and dedups `{vulnerability.display_id, workload.id}` first.

(`count()` is correct here for the same reason as the host ranking above — the
grain entering the `expand` is already one row per vulnerability.)

To add the current name and Smartscape id (deep links, ReplicaSet roll-up), resolve the result with dt-sec-contextualization `rva-entity-resolution.md` § Resolving a ranking result.

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

### Named entity list for a specific vulnerability

"Which entities does vulnerability X hit" (UC-V5 for ONE vulnerability). Use
`VULNERABILITY_STATE_REPORT_EVENT` only (state reports carry the full entity context) and dedup by
`{affected_entity.id, vulnerability.id}`. For an advisory id instead of `display_id`, use the
multi-field OR from
[vulnerabilities-dynatrace.md § Step 2](vulnerabilities-dynatrace.md#step-2--optional-pre-aggregation-filter-insert-after-step-1-before-step-3).

> **Always project `affected_entity.*`.** When `affected_entity.type` is `HOST` or
> `KUBERNETES_NODE` the directly-affected entity is itself the host or node and is not repeated in
> `related_entities.hosts.*`; projecting only the related arrays silently omits it.

**Base and Option A (simple list: the names arrays as-is, no expand):**

```dql
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_STATE_REPORT_EVENT"
     AND event.provider == "Dynatrace"
     AND vulnerability.display_id == "S-2647"
     AND isNotNull(affected_entity.id)
| dedup {affected_entity.id, vulnerability.id}
| fields vulnerability.display_id, vulnerability.title,
         affected_entity.id, affected_entity.name, affected_entity.type,
         related_entities.hosts.names, related_entities.hosts.ids
```

**Option B (one row per related host, in-event name).** Pair the typed `ids` and `names` arrays
positionally, then expand. Hosts without a related-host array drop out of this list; the
directly-affected entity stays visible through the projected `affected_entity.*`. For other entity
types swap `related_entities.hosts.*` for `.kubernetes_workloads.*`, `.services.*`, etc.

```dql
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_STATE_REPORT_EVENT"
     AND event.provider == "Dynatrace"
     AND vulnerability.display_id == "S-2647"
     AND isNotNull(affected_entity.id)
| dedup {affected_entity.id, vulnerability.id}
| fieldsAdd related_host = iCollectArray(record(id = related_entities.hosts.ids[],
                                                name = related_entities.hosts.names[]))
| expand related_host
| fields related_host.id = related_host[id], related_host.name = related_host[name],
         affected_entity.id, affected_entity.name, affected_entity.type
```

Empty 30m: use the 24h fallback. To add the current name and Smartscape id, resolve the result with dt-sec-contextualization `rva-entity-resolution.md` § Resolving a ranking result.

---

## Top vulnerable components (libraries) — external findings (UC-V9)

External scanners carry component info primarily in `software_component.*`; use
legacy `component.*` only as a fallback:

```dql
fetch security.events
| filter event.type == "VULNERABILITY_FINDING"
| filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
| fieldsAdd component_name = coalesce(software_component.name, component.name),
            component_version = component.version
| filter isNotNull(component_name)
| dedup {component_name, component_version, vulnerability.id}
| summarize {
    Findings=count(),
    Critical=countIf(dt.security.risk.level=="CRITICAL"),
    High=countIf(dt.security.risk.level=="HIGH"),
    `Affected objects`=countDistinctExact(object.id),
    `Affected images`=countDistinctExact(container_image.digest)
  }, by:{Component=component_name, Version=component_version}
| sort Critical desc, High desc
| limit 10
```

## External vulnerable container images

Ranks container images by distinct vulnerabilities (`countDistinctExact(vulnerability.id)`, never a raw `count()` of finding rows). Provider, product, object id/name, registry, repository, and digest are all `by:` keys so images from different registries or digest versions are never collapsed. `container_image.digest` is the primary image identity — `container_image.name` is not reliably populated by external providers. The window is `-24h`; use the user's window when given (for example `from:-7d`), and `limit 10` for a top-10 ask.

```dql
fetch security.events, from: -24h
| filter event.type == "VULNERABILITY_FINDING"
| filterOut event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
| filter object.type == "CONTAINER_IMAGE"
// Identity guard (ranking by distinct vulnerabilities) — not the nine-field SD guard: Amazon ECR leaves finding.type null
| filter isNotNull(finding.id) AND isNotNull(object.id) AND isNotNull(vulnerability.id)
| summarize {
    vulnerabilities = countDistinctExact(vulnerability.id)
  }, by: {event.provider, product.name, object.id, object.name,
          container_image.registry, container_image.repository, container_image.digest}
| sort vulnerabilities desc
| limit 10
```

## External vulnerable code artifacts

Same ranking for `CODE_ARTIFACT` objects (SCA/SAST repositories such as Dependabot or CodeQL findings): distinct vulnerabilities per artifact, identified by `artifact.repository` and `artifact.path`.

```dql
fetch security.events, from: -24h
| filter event.type == "VULNERABILITY_FINDING"
| filterOut event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
| filter object.type == "CODE_ARTIFACT"
// Identity guard (ranking by distinct vulnerabilities) — not the nine-field SD guard: Amazon ECR leaves finding.type null
| filter isNotNull(finding.id) AND isNotNull(object.id) AND isNotNull(vulnerability.id)
| summarize {
    vulnerabilities = countDistinctExact(vulnerability.id)
  }, by: {event.provider, product.name, object.id, object.name, artifact.repository, artifact.path}
| sort vulnerabilities desc
| limit 10
```
