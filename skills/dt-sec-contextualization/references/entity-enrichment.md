# Entity Enrichment — Finding Streams to Dynatrace Entities

Aggregates a **finding stream** from `security.events` (external `*_FINDING` rows, IoC match rows, or
smartscape rows) per Smartscape entity: Critical/High/Medium/Low counts per workload, host,
or cloud entity. Each template is a complete pipeline; no other file is needed.

> **Route.** Load this file for a stream that needs aggregation (risk counts, top-N, "map external
> findings to workloads"). For a SUPPLIED identifier (one digest, host IP, Smartscape id, GenAI
> process) load [identity-mapping.md](identity-mapping.md) instead; this file and its pre-flight are not
> needed. The `summarize` steps assume `dt.security.risk.level` and/or
> `compliance.rule.severity.level` on the rows; callers without them keep only the entity keys.

---

## Contents

- [Pre-flight Check — Identifier Availability](#pre-flight-check--identifier-availability)
- [Problem → Affected Entities → Findings (two-query chain)](#problem--affected-entities--findings-two-query-chain)
- [Cloud Entity Enrichment (Path 1 only)](#cloud-entity-enrichment-path-1-only)
- [K8s Workload Enrichment (Paths 1 + 2)](#k8s-workload-enrichment-paths-1--2)
- [Host Enrichment by IP](#host-enrichment-by-ip) · [by Entity](#host-enrichment-by-entity-paths-1--2)
- [Natural-language entity name fallback](#natural-language-entity-name-fallback)
- [Entity-Scoping OR-Chain](#entity-scoping-or-chain) · [AI services scope](#scope-a-finding-stream-to-ai-services)
- [Best Practices](#best-practices)

---

## Pre-flight Check — Identifier Availability

First step of the stream route. Providers vary (many scope to cloud resources, not K8s workloads):
confirm the stream carries a resolvable identifier before the expensive append chain; if none is
populated, skip the chain and report the gap. The scan is tenant-wide (about 15 GB at 24h on a
busy tenant): when the user names a provider, add
`| filter contains(event.provider, "<name>", caseSensitive:false) or contains(product.name, "<name>", caseSensitive:false)`
after the Dynatrace exclusion in both steps. Use the full name the user gave (a short fragment such
as "ecr" also matches "Secret scanning"); `product.name` covers integrations whose `event.provider`
is null. Step 1 without the filter lists the exact provider strings if the name needs confirming.

```dql
// Step 1: check identifier presence across providers
fetch security.events, from:now()-24h
| filterOut event.provider == "Dynatrace" or product.vendor == "Dynatrace"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| summarize {
    findings = count(),
    `has container_image.digest`  = countIf(isNotNull(container_image.digest)),
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
- Workload `dt.smartscape_source.type` → Path 1 yields matches; namespace, cluster, or cloud-resource type → Path 1 returns 0, use Path 2.
- Both identifier counts 0 → no K8s workload mapping possible; report it and use host-by-IP if `host.ip` exists.
- Registry scanners (Amazon ECR, Google Artifact Registry) report on a slow, bursty cadence: when `has container_image.digest` is 0 at 24h, repeat Step 1 at 7 days before concluding.

---

## Problem → Affected Entities → Findings (two-query chain)

**Use case:** "What security findings exist for the entities affected by Davis problem
P-XXX?" Pull the problem's entity IDs first, then scope security findings to those IDs.

### Step 1 — pull entity IDs from `dt.davis.problems`

**Placeholders**

| Placeholder | Meaning | Example | Where to get it |
|---|---|---|---|
| `<problem-display-id>` | Davis problem display ID (string, quoted) | `P-260575` | Problem card / `dt.davis.problems` `display_id` |

```dql-template
fetch dt.davis.problems, from:now()-7d
| filter display_id == "<problem-display-id>"
| expand entity = smartscape.affected_entities
| fields display_id,
         entity.id = entity[id], entity.type = entity[type], entity.name = entity[name],
         root_cause.id = root_cause.smartscape_entity[id]
```

`smartscape.affected_entities` is Davis's list of `{id, type, name}` records (typed ids such as
`K8S_CRONJOB-...`); they match `dt.smartscape_source.id` and `dt.smartscape.*` on finding rows.

### Step 2 — scope `security.events` to those entities

`security.events` has no single `entity.id` field. Substitute the Step 1 `entity.id` values into the
[Entity-Scoping OR-Chain](#entity-scoping-or-chain) template, use `from:now()-2h` for a problem
window, and append its risk-summary tail.

---

## Cloud Entity Enrichment (Path 1 only)

Cloud entities resolve via `dt.smartscape_source.id` directly; no container traversal.

```dql
fetch security.events
| filterOut event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
// Semantic-dictionary guard: drop events without type or object id
| filterOut isNull(event.type) or isNull(object.id)
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
       {Medium,direction:"descending"}, {Low,direction:"descending"}
```

---

## K8s Workload Enrichment (Paths 1 + 2)

> **Always use the 2-way enrichment recipe, never `object.name` alone**: it is not unique across
> clusters or namespaces and collapses different workloads into wrong counts.

Run the [pre-flight](#pre-flight-check--identifier-availability) first.

### Canonical 2-way enrichment

Answers "top N workloads with risk counts from external findings" (append `| limit 10` for a
top-10). It keeps `container_image.digest`, the repository, `object.name`, and `event.provider` before
ranking, so findings from different registries or image versions are not collapsed. The window is
7 days because registry scanners (Amazon ECR, Google Artifact Registry) report on a slow, bursty
cadence. The final `dedup` after `append` removes duplicates from multiple matching paths. Verified
(7 days): findings for 8 images resolved to 10 workloads, one row per workload.

```dql
fetch security.events, from:now()-7d
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
    fetch security.events, from:now()-7d
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
        | lookup [
            smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}, from:now()-2h
          ], sourceField:dt.smartscape_source.id, lookupField:id, fields:{classic_entity.id=id_classic}
      ], kind:leftOuter, on:{left[container_image.digest]==right[container.image.digest]},
        fields:{dt.smartscape_source.id, classic_entity.id, workloadName=k8s.workload.name}
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
  }, by: {dt.smartscape_source.id, classic_entity.id, Workload = workloadName}
| sort Critical desc, High desc, Medium desc, Low desc
```

---

## Host Enrichment by IP

Expands the `host.ip` array field, normalizes via `ip()`, then joins HOST
smartscapeNodes on IP.

```dql
fetch security.events, from:now()-24h
// Semantic-dictionary guard: drop events without type, object id, or host IP
| filterOut isNull(event.type) or isNull(object.id) or isNull(host.ip)
| expand host.ip
| fieldsAdd host.ip=ip(host.ip)
| join [
    smartscapeNodes HOST
    | expand ip
  ], on:{left[host.ip]==right[ip]}, fields:{host.id=id, host.name=name}
// Dedup AFTER the join: one finding on several IPs of the same host counts once
| dedup {host.id, host.name, host.ip, event.provider, finding.id, object.id, dt.security.risk.level},
        sort:{timestamp desc}
| summarize {
    IP=collectDistinct(host.ip),
    Critical=countIf(dt.security.risk.level=="CRITICAL"),
    High=countIf(dt.security.risk.level=="HIGH"),
    Medium=countIf(dt.security.risk.level=="MEDIUM"),
    Low=countIf(dt.security.risk.level=="LOW")
  }, by:{host.id, `Host name`=host.name}
| sort {Critical,direction:"descending"}, {High,direction:"descending"},
       {Medium,direction:"descending"}, {Low,direction:"descending"}
```

---

## Host Enrichment by Entity (Paths 1 + 2)

Same 2-way structure as K8s Workload Enrichment, resolving to HOST (Path 2: CONTAINER by digest →
`runs_on.host` → HOST).

> **`runs_on.host` is tenant-dependent.** CONTAINER nodes carry a `runs_on` → HOST edge on one
> tested tenant and none on the other (there the container links only to its pod and carries
> `k8s.node.name`). The digest → HOST leg is not verified end to end; on K8s-only tenants resolve
> to the node (`k8s.node.name`) instead.

```dql
fetch security.events, from:now()-7d
| filter exists(dt.smartscape_source.id) and isNotNull(dt.smartscape_source.id)
| dedup {event.provider, finding.id, object.id, dt.security.risk.level}, sort: {timestamp desc}
| join [
    smartscapeNodes {HOST}, from:now()-2h
  ], on:{left[dt.smartscape_source.id]==right[id]},
     fields:{hostName=name, dt.smartscape_source.id=id, host.classic.id=id_classic}
// Path 2 (digest)
| append [
    fetch security.events, from:now()-7d
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
  ]| filterOut isNull(host.classic.id)
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

If an entity cannot be resolved through a Smartscape lookup, search `security.events` directly:
rows often keep names in `object.name`, `affected_entity.name`, and `related_entities.*.names` even
when topology misses the entity. For the Dynatrace RVA vulnerabilities of a named entity use
`dt-sec-insights` `vulnerabilities-dynatrace.md` § One known entity instead.

**Placeholders**

| Placeholder | Meaning | Example | Where to get it |
|---|---|---|---|
| `<entity-name>` | Case-insensitive substring of the entity display name (string, quoted); the same value is used in all five `contains` clauses | `unguard-user-auth` | User prompt, Davis problem, or UI entity name |

```dql-template
fetch security.events, from:now()-24h
| filter in(event.type, {"VULNERABILITY_STATE_REPORT_EVENT",
                         "VULNERABILITY_STATUS_CHANGE_EVENT",
                         "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT",
                         "VULNERABILITY_FINDING",
                         "DETECTION_FINDING",
                         "COMPLIANCE_FINDING"})
| filter contains(object.name, "<entity-name>", caseSensitive:false)
      OR contains(affected_entity.name, "<entity-name>", caseSensitive:false)
      OR iAny(contains(related_entities.services.names[], "<entity-name>", caseSensitive:false))
      OR iAny(contains(related_entities.kubernetes_workloads.names[], "<entity-name>", caseSensitive:false))
      OR iAny(contains(related_entities.hosts.names[], "<entity-name>", caseSensitive:false))
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

**Placeholders**

| Placeholder | Meaning | Example | Where to get it |
|---|---|---|---|
| `<ID1>` | One entity ID as a quoted string; for several IDs list them in each `array(...)` (edit every clause). Pass 3rd-gen IDs for the `dt.smartscape*` clauses and classic IDs for `affected_entity.id` | `K8S_NODE-89300B0C743BBBB5` | Step 1, or the correlation entity-key bundle (`entityKey.smartscape_id` / `entityKey.classic_id`) |

Typed fields (`dt.smartscape.*`) are wrapped in `toString(...)` so plain string literals compare;
without it use `toSmartscapeId("K8S_NODE-89300B0C743BBBB5")`.

```dql-template
fetch security.events, from:now()-24h
| filter in(event.type, {"VULNERABILITY_STATE_REPORT_EVENT",
                          "VULNERABILITY_FINDING",
                          "DETECTION_FINDING",
                          "COMPLIANCE_FINDING"})
| filter in(affected_entity.id, array("<ID1>"))
      or in(object.id, array("<ID1>"))
  or in(toString(dt.smartscape_source.id), array("<ID1>"))
  or in(toString(dt.smartscape.host), array("<ID1>"))
  or in(toString(dt.smartscape.process), array("<ID1>"))
  or in(toString(dt.smartscape.k8s_node), array("<ID1>"))
```

Append this risk-summary tail for per-type counts (the "findings of Davis problem P-XXX" case: use
`from:now()-2h` and the ids from Step 1 of the chain above):

```dql-snippet
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

> **`dt.smartscape.host` is partial** (non-K8s processes only on Dynatrace scans); for a K8s-hosted
> process scope by `dt.smartscape.process` or `dt.smartscape.k8s_node`. There is no process-group
> field on events: resolve the process through `smartscapeNodes PROCESS` and read
> `dt.process_group.id` (null means unresolved; an RVA `PROCESS_GROUP` `affected_entity.id` equals it).

Roll process-level findings up to the process group (no placeholders):

```dql
fetch security.events, from:now()-24h
| filter (product.vendor == "Dynatrace" or event.provider == "Dynatrace") and event.type == "VULNERABILITY_FINDING"
| filter isNotNull(dt.smartscape.process)
| summarize findings=count(), by:{dt.smartscape.process}
| join [
    smartscapeNodes PROCESS, from:now()-24h
    | fields id, dt.process_group.id, dt.process_group.detected_name
  ], kind:leftOuter, on:{left[dt.smartscape.process]==right[id]},
     fields:{processGroup=dt.process_group.id, processGroupName=dt.process_group.detected_name}
| summarize {findings=sum(findings), processes=countDistinct(dt.smartscape.process)}, by:{processGroup, processGroupName}
| sort findings desc
```

> **Include the external stream for broad entity-security questions.** For prompts
> like "what are the security findings on this K8s node / host / workload / cluster",
> run this external `*_FINDING` branch (`24h`) **and** the DT RVA entity scope (`30m`, see
> `dt-sec-insights` `vulnerabilities-dynatrace.md` § One known entity) **and** the DT SPM entity scope (`1h`). Do not answer
> only from one source.

---

## Scope a Finding Stream to AI Services

To restrict any process-level `VULNERABILITY_FINDING` / detection stream to AI/GenAI
workloads, inner-join the finding's `dt.smartscape.process` to the **forward** GENAI
path in [identity-mapping.md § Path 3](identity-mapping.md#path-3--ai-service--runtime-process-genai_service--service--process).
To attribute a matched finding back to its owning AI service (e.g. per-service
grouping or deep-links), use the **reverse** traversal in the same section.

---

## Best Practices

1. **Check `dt.smartscape_source.type` granularity** (pre-flight Step 2): a non-null
   `dt.smartscape_source.id` is not proof of workload-level resolution.
2. **Dedup early and after `append`** — before joins to collapse re-ingested duplicates, after
   `append` because the same finding can match multiple paths.
3. **Use `from:now()-2h` on smartscapeNodes** — topology is stable; keeps joins cheap.
4. **Preserve image identity before ranking** — include `object.name`,
   `container_image.digest`, `coalesce(artifact.repository, container_image.repository)`, `object.id`,
   and `event.provider`; never group by `object.name` alone.
5. **Project the [entity-key bundle](identity-mapping.md#entity-key-bundle-required-for-correlation)**
   before passing rows to `correlation.md`.
