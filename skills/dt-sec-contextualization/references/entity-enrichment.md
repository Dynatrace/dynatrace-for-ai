# Entity Enrichment — Map Signals to Dynatrace Entities

Maps security findings, IoC match rows, or raw Smartscape nodes to Dynatrace
runtime entities using the [mapping primitive](identity-mapping.md). Produces
per-entity risk-level breakdowns (Critical / High / Medium / Low counts) grouped
by Smartscape entity.

> **Input is generic.** The recipes here work with any row set carrying the identity
> fields described in [identity-mapping.md](identity-mapping.md) — `security.events`
> findings (the most common caller, from dt-sec-insights), IoC match rows from
> dt-sec-ioc-hunting, or raw `smartscapeNodes` rows. The risk-level summarization at
> the end of each recipe assumes `dt.security.risk.level` and/or `compliance.rule.severity.level`
> are present on input rows; callers that don't carry those fields skip the `summarize`
> step and use only the resolved entity keys.

> **DT-native RVA entity rankings** ("most vulnerable hosts / workloads / components")
> live in `dt-sec-insights/references/vulnerabilities-entities.md` — those build on
> the RVA snapshot pipeline rather than the external-finding joins here.

---

## Contents

- [Problem → Affected Entities → Findings (two-query chain)](#problem--affected-entities--findings-two-query-chain)
- [Cloud Entity Enrichment (Path 1 only)](#cloud-entity-enrichment-path-1-only)
- [K8s Workload Enrichment (Paths 1 + 2 + 3)](#k8s-workload-enrichment-paths-1--2--3)
  - [Pre-flight check](#pre-flight-check)
  - [Canonical 3-way enrichment (compact)](#canonical-3-way-enrichment-compact)
  - [3-way enrichment with identity preserved](#3-way-enrichment-with-identity-preserved)
- [Host Enrichment by IP](#host-enrichment-by-ip)
- [Host Enrichment by Entity (Paths 1 + 2 + 3)](#host-enrichment-by-entity-paths-1--2--3)
- [Natural-language entity name fallback](#natural-language-entity-name-fallback)
- [Entity-Scoping OR-Chain (for broad entity questions)](#entity-scoping-or-chain)
- [Scope a Finding Stream to AI Services](#scope-a-finding-stream-to-ai-services)
- [Best Practices](#best-practices)

---

## Problem → Affected Entities → Findings (two-query chain)

**Use case:** "What security findings exist for the entities affected by Davis problem
P-XXX?" Pull the problem's entity IDs first, then scope security findings to those IDs.

### Step 1 — pull entity IDs from `dt.davis.problems`

```dql
fetch dt.davis.problems, from:now()-7d
| filter display_id == "P-260575"
| fields affected_entity_ids,
         dt.entity.service, dt.entity.process_group, dt.entity.host,
         dt.entity.cloud_application, dt.entity.cloud_application_namespace,
         dt.entity.kubernetes_cluster
| limit 1
```

`affected_entity_ids` is Davis's canonical list. The `dt.entity.*` topology arrays
add process groups, hosts, clusters — which is what `security.events` actually
carries on per-finding rows.

### Step 2 — scope `security.events` to those entities

`security.events` has no single `entity.id` field; different finding types put the
entity ID in different places. Use the OR-chain below; substitute actual IDs from
Step 1:

```dql-template
fetch security.events, from:now()-2h
| filter in(event.type, {"VULNERABILITY_STATE_REPORT_EVENT",
                          "VULNERABILITY_FINDING",
                          "DETECTION_FINDING",
                          "COMPLIANCE_FINDING"})
| filter in(affected_entity.id, array("<ID1>","<ID2>"))
      or in(object.id,          array("<ID1>","<ID2>"))
  or in(toString(dt.smartscape_source.id), array("<ID1>","<ID2>"))
  or in(toString(dt.entity.host), array("<ID1>","<ID2>"))
  or in(toString(dt.entity.process_group), array("<ID1>","<ID2>"))
| summarize {
    findings  = count(),
    Critical  = countIf(dt.security.risk.level == "CRITICAL" or compliance.rule.severity.level == "CRITICAL"),
    High      = countIf(dt.security.risk.level == "HIGH"     or compliance.rule.severity.level == "HIGH"),
    Medium    = countIf(dt.security.risk.level == "MEDIUM"   or compliance.rule.severity.level == "MEDIUM"),
    Low       = countIf(dt.security.risk.level == "LOW"      or compliance.rule.severity.level == "LOW"),
    topTitles = arraySlice(collectDistinct(finding.title), from: 0, to: 10)
  }, by: {event.type, event.provider, product.name}
| sort Critical desc, High desc, findings desc
```

---

## Cloud Entity Enrichment (Path 1 only)

Cloud entities resolve via `dt.smartscape_source.id` directly. No container
traversal needed.

```dql
fetch security.events
| filter exists(dt.smartscape_source.id)
| dedup {event.provider, finding.id, object.id, dt.security.risk.level}, sort: {timestamp desc}
| join [
    smartscapeNodes "*", from:now()-24h
    | filter exists(cloud.provider)
  ], on:{left[dt.smartscape_source.id]==right[id]}, fields:{name}
| summarize {
    Critical=countIf(dt.security.risk.level=="CRITICAL"),
    High=countIf(dt.security.risk.level=="HIGH"),
    Medium=countIf(dt.security.risk.level=="MEDIUM"),
    Low=countIf(dt.security.risk.level=="LOW")
  }, by:{Type=dt.smartscape_source.type, dt.smartscape_source.id, Name=name}
| sort {Critical,direction:"descending"}, {High,direction:"descending"},
       {Medium,direction:"descending"}
```

---

## K8s Workload Enrichment (Paths 1 + 2 + 3)

> **Always use the 3-way enrichment recipe — never fall back to `object.name` alone.**
> `object.name` is not unique across clusters or namespaces; it collapses findings
> from different workloads with the same display name and produces wrong counts.

### Pre-flight check

See [identity-mapping.md § Mapping Primitive](identity-mapping.md#mapping-primitive)
for the two-step pre-flight that confirms at least one identifier path is populated
before running the expensive append chain.

### Canonical 3-way enrichment (compact)

A final `dedup` after `append` removes duplicates introduced by multiple matching paths.

```dql
fetch security.events, from:now()-7d
| filter exists(dt.smartscape_source.id) and isNotNull(dt.smartscape_source.id)
| dedup {event.provider, finding.id, object.id, dt.security.risk.level}, sort: {timestamp desc}
| join [
    smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}, from:now()-2h
  ], on:{left[dt.smartscape_source.id]==right[id]},
     fields:{
       containerNames=name, dt.smartscape_source.id=id, classic_entity.id=id_classic, workloadName=k8s.workload.name
     }
| append [
    fetch security.events
    | filter isNotNull(container_image.digest)
    | dedup {container_image.digest, event.provider, finding.id, object.id, dt.security.risk.level}, sort: {timestamp desc}
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
        fields:{
          containerNames=name, dt.smartscape_source.id, classic_entity.id=id_classic, workloadName=k8s.workload.name
        }
  ]
| append [
    fetch security.events
    | filter isNotNull(container_image.id)
    | join [
        fetch dt.entity.container_group_instance, from:now()-2h
        | fieldsAdd containerNames, containerImageId,
                    container_group.id=instance_of[dt.entity.container_group],
                    workload.id=belongs_to[dt.entity.cloud_application], workloadName
        | fieldsAdd classic_entity.id=coalesce(workload.id,container_group.id)
        | lookup [
            smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}, from:now()-2h
          ], sourceField:workload.id, lookupField:id_classic, fields:{dt.smartscape_source.id=id}
      ], kind:leftOuter, on:{left[container_image.id]==right[containerImageId]},
         fields:{containerNames, dt.smartscape_source.id, classic_entity.id, workloadName}
  ]
| filterOut isNull(classic_entity.id)
| dedup {dt.smartscape_source.id, classic_entity.id, containerNames, workloadName,
         container_image.digest, event.provider, finding.id, object.id, dt.security.risk.level},
        sort:{timestamp desc}
| summarize {
    Containers=arrayDistinct(arrayFlatten(collectDistinct(containerNames))),
    Critical=countIf(dt.security.risk.level=="CRITICAL"),
    High=countIf(dt.security.risk.level=="HIGH"),
    Medium=countIf(dt.security.risk.level=="MEDIUM"),
    Low=countIf(dt.security.risk.level=="LOW")
  }, by:{dt.smartscape_source.id, classic_entity.id, Workload=workloadName}
| sort {Critical,direction:"descending"}, {High,direction:"descending"},
       {Medium,direction:"descending"}
```

### 3-way enrichment with identity preserved

Use when findings from different registries or image versions must not be collapsed.
Preserves `container_image.digest`, `artifact.repository` / `container_image.repository`,
`object.name`, and `event.provider` before ranking.

```dql
fetch security.events, from:now()-24h
| filterOut event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter isNotNull(finding.id) AND isNotNull(object.id) AND isNotNull(dt.security.risk.level)
| fieldsAdd repository = coalesce(artifact.repository, container_image.repository)

// Path 1
| filter exists(dt.smartscape_source.id) AND isNotNull(dt.smartscape_source.id)
| dedup {event.provider, finding.id, object.id, dt.security.risk.level}, sort: {timestamp desc}
| join [
    smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}, from:now()-2h
  ], on:{left[dt.smartscape_source.id]==right[id]},
     fields:{dt.smartscape_source.id=id, classic_entity.id=id_classic, workloadName=k8s.workload.name}

// Path 2
| append [
    fetch security.events, from:now()-24h
    | filterOut event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
    | filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
    | filter isNotNull(container_image.digest)
    | fieldsAdd repository = coalesce(artifact.repository, container_image.repository)
    | dedup {container_image.digest, event.provider, finding.id, object.id, dt.security.risk.level}, sort: {timestamp desc}
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
  ]

// Path 3
| append [
    fetch security.events, from:now()-24h
    | filterOut event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
    | filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
    | filter isNotNull(container_image.id)
    | fieldsAdd repository = coalesce(artifact.repository, container_image.repository)
    | join [
        fetch dt.entity.container_group_instance, from:now()-2h
        | fieldsAdd containerImageId, workload.id=belongs_to[dt.entity.cloud_application], workloadName
        | lookup [
            smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}, from:now()-2h
          ], sourceField:workload.id, lookupField:id_classic, fields:{dt.smartscape_source.id=id}
      ], kind:leftOuter, on:{left[container_image.id]==right[containerImageId]},
         fields:{dt.smartscape_source.id, classic_entity.id=workload.id, workloadName}
  ]

| filterOut isNull(classic_entity.id)
| dedup {dt.smartscape_source.id, classic_entity.id, event.provider, finding.id, object.id, dt.security.risk.level},
        sort:{timestamp desc}
| summarize {
    Critical = countIf(dt.security.risk.level == "CRITICAL"),
    High = countIf(dt.security.risk.level == "HIGH"),
    Medium = countIf(dt.security.risk.level == "MEDIUM"),
    Low = countIf(dt.security.risk.level == "LOW"),
    image.objects = collectDistinct(object.name),
    image.digests = collectDistinct(container_image.digest),
    repositories = collectDistinct(repository),
    providers = collectDistinct(event.provider),
    finding.titles = collectDistinct(finding.title, maxLength: 10)
  }, by: {dt.smartscape_source.id, Workload = workloadName}
| sort Critical desc, High desc
```

---

## Host Enrichment by IP

Expands the `host.ip` array field, normalizes via `ip()`, then joins HOST
smartscapeNodes on IP.

```dql
fetch security.events, from:now()-24h
| filter isNotNull(host.ip)
| dedup {event.provider, finding.id, object.id, dt.security.risk.level}, sort:{timestamp desc}
| expand host.ip
| fieldsAdd host.ip=ip(host.ip)
| join [
    smartscapeNodes HOST
    | expand ip
  ], on:{left[host.ip]==right[ip]}, fields:{host.id=id, host.name=name}
| sort timestamp desc
| summarize {
    `Host name`=takeLast(host.name),
    IP=collectDistinct(host.ip),
    Critical=countIf(dt.security.risk.level=="CRITICAL"),
    High=countIf(dt.security.risk.level=="HIGH"),
    Medium=countIf(dt.security.risk.level=="MEDIUM"),
    Low=countIf(dt.security.risk.level=="LOW")
  }, by:{host.id}
| sort {Critical,direction:"descending"}, {High,direction:"descending"},
       {Medium,direction:"descending"}
```

---

## Host Enrichment by Entity (Paths 1 + 2 + 3)

Same 3-way structure as K8s Workload Enrichment but resolves to HOST entities.
Path 2: CONTAINER → `runs_on.host` → HOST. Path 3: CGI → workload → `runs_on.host` → HOST.

```dql
fetch security.events
| filter exists(dt.smartscape_source.id) and isNotNull(dt.smartscape_source.id)
| dedup {event.provider, finding.id, object.id, dt.security.risk.level}, sort: {timestamp desc}
| join [
    smartscapeNodes {HOST}, from:now()-2h
  ], on:{left[dt.smartscape_source.id]==right[id]},
     fields:{hostName=name, dt.smartscape_source.id=id, host.classic.id=id_classic}
| append [
    fetch security.events
    | filter isNotNull(container_image.digest)
    | dedup {container_image.digest, event.provider, finding.id, object.id, dt.security.risk.level}, sort: {timestamp desc}
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
  ]
| append [
    fetch security.events
    | filter isNotNull(container_image.id)
    | join [
        fetch dt.entity.container_group_instance, from:now()-2h
        | fieldsAdd containerNames, containerImageId,
                    container_group.id=instance_of[dt.entity.container_group],
                    workload.id=belongs_to[dt.entity.cloud_application], workloadName
        | lookup [
            smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}, from:now()-2h
            | expand dt.host.id=references[runs_on.host]
            | filter isNotNull(dt.host.id)
            | fieldsAdd dt.smartscape_source.id=dt.host.id
            | lookup [
                smartscapeNodes {HOST}, from:now()-2h
              ], sourceField:dt.smartscape_source.id, lookupField:id,
                 fields:{hostName=name, host.classic.id=id_classic}
          ], sourceField:workload.id, lookupField:id_classic,
             fields:{dt.smartscape_source.id, host.classic.id, hostName}
      ], kind:leftOuter, on:{left[container_image.id]==right[containerImageId]},
         fields:{hostName, dt.smartscape_source.id, host.classic.id}
  ]
| filterOut isNull(host.classic.id)
| dedup {dt.smartscape_source.id, host.classic.id, hostName,
         event.provider, finding.id, object.id, dt.security.risk.level},
        sort:{timestamp desc}
| summarize {
    Critical=countIf(dt.security.risk.level=="CRITICAL"),
    High=countIf(dt.security.risk.level=="HIGH"),
    Medium=countIf(dt.security.risk.level=="MEDIUM"),
    Low=countIf(dt.security.risk.level=="LOW")
  }, by:{dt.smartscape_source.id, host.classic.id, Host=hostName}
| sort {Critical,direction:"descending"}, {High,direction:"descending"},
       {Medium,direction:"descending"}
```

---

## Natural-language Entity Name Fallback

If an entity cannot be resolved through a Smartscape lookup tool, search
`security.events` directly. Security rows often preserve names in `object.name`,
`affected_entity.name`, and `related_entities.*.names` even when a separate
topology lookup misses the entity.

```dql
fetch security.events, from:now()-24h
| filter in(event.type, {"VULNERABILITY_STATE_REPORT_EVENT",
                         "VULNERABILITY_STATUS_CHANGE_EVENT",
                         "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT",
                         "VULNERABILITY_FINDING",
                         "DETECTION_FINDING",
                         "COMPLIANCE_FINDING"})
| filter contains(lower(object.name), lower("<entity-name>"))
      OR contains(lower(affected_entity.name), lower("<entity-name>"))
      OR iAny(contains(lower(related_entities.services.names[]), lower("<entity-name>")))
      OR iAny(contains(lower(related_entities.kubernetes_workloads.names[]), lower("<entity-name>")))
      OR iAny(contains(lower(related_entities.hosts.names[]), lower("<entity-name>")))
| fieldsKeep timestamp, event.type, event.provider, product.name,
             finding.title, vulnerability.title, dt.security.risk.level,
             object.id, object.name, affected_entity.id, affected_entity.name,
             "related_entities*"
| limit 100
```

---

## Entity-Scoping OR-Chain

For broad entity-security questions ("all security findings on this K8s node / host / workload"),
use the wide OR-chain that covers all finding-type entity namespaces.

```dql-template
// Substitute the actual entity IDs from Step 1 or from the correlation entity-key bundle
fetch security.events, from:now()-24h
| filter in(event.type, {"VULNERABILITY_STATE_REPORT_EVENT",
                          "VULNERABILITY_FINDING",
                          "DETECTION_FINDING",
                          "COMPLIANCE_FINDING"})
| filter in(affected_entity.id, array("<ID1>"))
      or in(object.id, array("<ID1>"))
  or in(toString(dt.smartscape_source.id), array("<ID1>"))
  or in(toString(dt.entity.host), array("<ID1>"))
  or in(toString(dt.entity.process_group), array("<ID1>"))
```

> **Include the external stream for broad entity-security questions.** For prompts
> like "what are the security findings on this K8s node / host / workload / cluster",
> run this external `*_FINDING` branch (`24h`) **and** the DT RVA entity scope (`30m`,
> using `affected_entity.id`) **and** the DT SPM entity scope (`1h`). Do not answer
> only from one source.

---

## Scope a Finding Stream to AI Services

To restrict any process-level `VULNERABILITY_FINDING` / detection stream to AI/GenAI
workloads, inner-join the finding's `dt.smartscape.process` to the **forward** GENAI
path in [identity-mapping.md § Mapping Primitive / Path 4](identity-mapping.md#mapping-primitive).
To attribute a matched finding back to its owning AI service (e.g. per-service
grouping or deep-links), use the **reverse** traversal in the same section.

---

## Best Practices

1. **Use the 3-way match for K8s and host enrichment — never fall back to `object.name` alone.**
2. **Cloud entities only need Path 1** — they don't traverse the container abstraction.
3. **Run the pre-flight check first** — confirms at least one identifier path is populated;
   avoids running the expensive append chain against providers with no K8s identifiers.
4. **Dedup early** — `dedup {event.provider, finding.id, object.id, dt.security.risk.level}`
   before joins collapses re-ingested duplicates.
5. **Dedup again after `append`** — the same finding can match multiple paths.
6. **Use `from:now()-2h` on smartscapeNodes** — Smartscape topology is relatively stable;
   a 2-hour window keeps the join cheap.
7. **Preserve image/digest/repository identity before ranking** — always include
   `object.name`, `container_image.digest`, `coalesce(artifact.repository, container_image.repository)`,
   `object.id`, and `event.provider` when summarizing external findings. Do not group
   by `object.name` alone.
8. **Check `dt.smartscape_source.type` granularity** — a non-null `dt.smartscape_source.id`
   does not guarantee workload-level resolution. Run the pre-flight Step 2 query to confirm.
9. **Project the entity-key bundle** before passing rows to `correlation-and-coverage.md` — include
   `dt.smartscape_source.id`, `classic_entity.id`, workload/host name, `k8s.cluster.name`,
   `k8s.namespace.name`, and `k8s.node.name` (when co-projected on pods).
