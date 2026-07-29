# Correlation And Coverage

## Contents

- [Correlation](#correlation)
- [Coverage](#coverage)


---

## Correlation


Connect security findings that land on different entity levels through a shared
runtime entity. Use this when two or more hunt legs (e.g. a detection, a CVE, a
compliance finding) return results and you want to know if they relate to the
same infrastructure.

---

## Correlation Contents

- [Entity-Key Bundle](#entity-key-bundle-spec)
- [Tiered Match Rules](#tiered-match-rules)
- [Pod→Node Topology Resolution](#podnode-topology-resolution)
- [Compliance Enrichment on Matched Entities](#compliance-enrichment-on-matched-entities)
- [Scoring Contract](#scoring-contract)
- [Correlation Workflow](#correlation-workflow)
- [Convergence Matrix (report format)](#convergence-matrix-report-format)

---

## Entity-Key Bundle Spec

Every hunt or enrichment leg MUST project a minimal entity-key bundle before
the correlation step. Without it, the tiered match has nothing to join on.

Required fields (project via `fieldsAdd` at the end of each leg):

```dql-snippet
| fieldsAdd entityKey.smartscape_id = dt.smartscape_source.id,
            entityKey.classic_id    = classic_entity.id,        // or host.classic.id
            entityKey.name          = workloadName,              // or hostName
            entityKey.type          = dt.smartscape_source.type,
            entityKey.k8s.cluster   = k8s.cluster.name,
            entityKey.k8s.namespace = k8s.namespace.name,
            entityKey.k8s.node      = k8s.node.name             // if available (pod rows)
```

When a leg does not use the [mapping primitive](identity-mapping.md) (e.g. a
raw DT RVA vulnerability leg that uses `affected_entity.*`), project equivalent
keys from the RVA fields:

```dql-snippet
// RVA leg entity-key bundle
| fieldsAdd entityKey.classic_id    = affected_entity.id,
            entityKey.name          = affected_entity.name,
            entityKey.type          = affected_entity.type,
            entityKey.k8s.cluster   = k8s.cluster.name,
            entityKey.k8s.namespace = k8s.namespace.name,
            entityKey.k8s.node      = k8s.node.name
```

> **RVA caveat — `k8s.cluster.name` / `k8s.namespace.name` are null on RVA state/change
> events.** Only `affected_entity.*` and `related_entities.*` carry entity context on
> those events; the generic `k8s.*` namespace is empty. So `entityKey.k8s.cluster` above
> will be null on every RVA row. For Tier-3 cluster comparison you must resolve the
> cluster via Smartscape: look up `affected_entity.id` in `smartscapeNodes K8S_NODE` (on
> `id_classic`) and read the resolved `k8s.cluster.name` from the topology node. Do not
> infer the cluster from the raw RVA event fields.

For **log and span hunt legs** (`dt-sec-ioc-hunting` → `hunt-logs.md` / `hunt-spans.md`),
project the entity-key bundle from the identifiers those templates now surface. Spans are
uniform OneAgent and always carry these; log identifiers are **best-effort** (see caveat
below):

```dql-snippet
// Span leg entity-key bundle
| fieldsAdd entityKey.classic_id    = dt.process_group.id,      // joins RVA affected_entity.id
            entityKey.smartscape_id = dt.smartscape.service,    // joins FINDING dt.smartscape_source.id
            entityKey.name          = dt.service.name,
            entityKey.hostName      = host.name

// Log leg entity-key bundle
| fieldsAdd entityKey.smartscape_id = dt.smartscape_source.id,  // joins FINDING dt.smartscape_source.id
            entityKey.classic_id    = dt.process_group.id,      // joins RVA affected_entity.id
            entityKey.type          = dt.smartscape_source.type,
            entityKey.k8s.namespace = k8s.namespace.name,
            entityKey.k8s.pod       = k8s.pod.name
```

> **Generation discipline — never cross the two.** `dt.process_group.id` (spans and logs)
> is a classic (`PROCESS_GROUP-<hex>`) ID and joins RVA `affected_entity.id` only.
> `dt.smartscape.service` (spans) and `dt.smartscape_source.id` (logs) are 3rd-gen
> Smartscape IDs and join `security.events` FINDING `dt.smartscape_source.id` only.
> Comparing a classic ID against a 3rd-gen ID is always a false negative — keep the two
> `entityKey` slots (`classic_id` vs `smartscape_id`) matched to their own generation.
>
> **Log entity-key caveat — best-effort.** OneAgent/container logs carry these keys at high
> coverage; **API-ingested logs (JFrog, cloud log forwarders) carry none** — every key is
> null. A matched log row with no entity ID is legitimate **perimeter evidence** — record it
> as such and do not treat the null as an error. Also, `k8s.cluster.name` and
> `k8s.workload.name` are **not** populated on demo.dev logs, so `entityKey.k8s.cluster` is
> unavailable from log rows — resolve the cluster via Smartscape (as in the RVA caveat above)
> if cluster-level tiering is needed.

---

## Tiered Match Rules

Given two legs A and B (e.g. detection leg and CVE leg), attempt the tiers in
order and stop at the highest tier that produces a match.

| Tier | Match condition | Scoring weight |
|---|---|---|
| **Tier 1** | `entityKey.smartscape_id` identical **OR** `entityKey.classic_id` identical | Full convergence — positions at the top of the score band |
| **Tier 2** | Same workload/pod name (`entityKey.name`) AND same cluster+namespace (`entityKey.k8s.cluster` + `entityKey.k8s.namespace`) | Probable convergence — positions in the upper half of the band |
| **Tier 3** | Same cluster only (`entityKey.k8s.cluster`) | **Context only — non-scoring.** Demo tenants co-locate everything; shared cluster alone is not evidence of relatedness |

> **Tier-1 note on cross-level findings.** A detection on a `K8S_POD` and a CVE
> on a `KUBERNETES_NODE` will **never** share a Smartscape ID (pod ≠ node). This
> is not a failed correlation — it is a topology resolution problem, resolved by
> the [Pod→Node section below](#podnode-topology-resolution). Report Tier-1 = no
> match truthfully, then attempt pod→node resolution before concluding.

---

## Pod→Node Topology Resolution

**Motivating case:** Detection leg hits `object.type = K8S_POD`; CVE (RVA) leg hits
`affected_entity.type = KUBERNETES_NODE`. No shared entity ID → Tier-1 fails.
Resolution: find the node that the matched pod runs on, then compare it to the
CVE's affected node.

### Step 1 — Resolve pod → node via `k8s.node.name`

`k8s.node.name` is a native co-projected field on `smartscapeNodes K8S_POD`.
This is the cheapest path — no edge traversal needed.

```dql
smartscapeNodes K8S_POD, from:now()-2h
| filter contains(lower(k8s.pod.name), lower("<pod-name-substring>"))
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, k8s.node.name, k8s.workload.name, id, id_classic
| sort k8s.pod.name asc
| limit 50
```

> See also `dt-obs-kubernetes/references/pod-node-placement.md` for comprehensive
> pod-distribution and node-placement queries. Route to that skill for full K8s
> topology analysis; use the snippet above for targeted single-pod→node lookup.

### Step 2 — Traverse Smartscape edge (alternative)

When `k8s.node.name` is unavailable (e.g. older agent versions), traverse the
`K8S_POD --runs_on--> K8S_NODE` edge:

```dql
smartscapeNodes K8S_POD, from:now()-2h
| filter contains(lower(k8s.pod.name), lower("<pod-name-substring>"))
| traverse edgeTypes:{runs_on}, targetTypes:{K8S_NODE}, direction:forward
| fields k8s.cluster.name, k8s.node.name, id, id_classic
```

### Step 3 — Compare resolved node to CVE's affected node

After resolving `k8s.node.name` from the pod, compare it to the
`affected_entity.name` values from the CVE (RVA) leg:

- **Match** → Tier-1 topology convergence (pod runs on a vulnerable node).
  Report as "The pod that fired the detection runs on node X, which has Y
  open vulnerabilities."
- **No match** → Tier-3 context at best (same cluster). Report truthfully as
  "No topology convergence found — the detection pod does not appear to run
  on any of the CVE-affected nodes."

```dql
// Example: check if pod 'unguard-backend-*' resolves to a node that matches RVA affected_entity.name
smartscapeNodes K8S_POD, from:now()-2h
| filter contains(lower(k8s.workload.name), lower("unguard-backend"))
| fields k8s.cluster.name, k8s.namespace.name, k8s.pod.name, k8s.node.name, k8s.workload.name
| summarize resolvedNodes = collectDistinct(k8s.node.name), by:{k8s.cluster.name, k8s.workload.name}
```

Then compare `resolvedNodes` with the `affected_entity.name` array from the RVA leg.
If the intersection is non-empty → Tier-1 topology convergence.

---

## Compliance Enrichment on Matched Entities

When a convergent entity (Tier-1 or Tier-2) is identified, enrich with
compliance/misconfiguration data from dt-sec-insights across **both** Dynatrace
SPM/KSPM and external posture tools.

Load `dt-sec-insights/references/compliance.md § Entity Security-Tab View` for the
full query pipeline. Run three steps in order:

### Step A — Resolve the SPM scan-target (parent cluster for K8s entities)

Dynatrace SPM/KSPM emits `COMPLIANCE_FINDING` per individual K8s resource (node,
pod, role, namespace, …). The `k8s.cluster.name` field is populated on these events
and is the correct scoping key. To get the cluster name from node IDs carried by the
CVE/RVA leg, resolve it via Smartscape using the query already available from the
pod→node resolution above:

```dql-snippet
// Resolve K8S_NODE → parent cluster (same query also co-projects k8s.cluster.name on K8S_POD)
smartscapeNodes K8S_NODE, from:now()-2h
| filter in(id_classic, array("<nodeClassicId1>", "<nodeClassicId2>"))
| fields id, id_classic, k8s.cluster.name, k8s.node.name
```

Collect the distinct `k8s.cluster.name` values as the enrichment scope.
For non-K8s entities (HOST, SERVICE, …), use the entity id directly — no cluster
resolution step is needed.

### Step B — Dynatrace SPM/KSPM enrichment (1h, cluster-scoped)

```dql-template
// DT KSPM: Tables 1 + 2 of the Entity Security-Tab View
// Replace <clusterName1> with k8s.cluster.name resolved in Step A
fetch security.events, from:now()-1h
| filter event.type == "COMPLIANCE_FINDING"
| filter product.vendor == "Dynatrace" AND product.name == "Security Posture Management"
| filter compliance.result.status.level == "FAILED"
| filter in(k8s.cluster.name, array("<clusterName1>", "<clusterName2>"))
| fields timestamp, compliance.rule.id, compliance.rule.name,
         compliance.result.status.level, compliance.rule.severity.level,
         compliance.standard.short_name,
         object.id, object.name, object.type
| sort compliance.rule.severity.level asc, timestamp desc
| limit 50
```

> **1h is correct for DT SPM** — the inner join to `COMPLIANCE_SCAN_COMPLETED` is cycle-aligned
> (hourly per cluster). Widening past 1h does not return more findings.

### Step C — External compliance enrichment (24h, original entity-scoped)

```dql-template
// External CSPM/VSPM: Table 3 of the Entity Security-Tab View
// Use the original entity ids (node/pod) — external rows are per-finding, not cluster-aggregated
fetch security.events, from:now()-24h
| filter event.type == "COMPLIANCE_FINDING"
| filterOut product.vendor == "Dynatrace"
| filter in(object.id, array("<entityId1>", "<entityId2>"))
      OR in(toString(dt.smartscape_source.id), array("<entityId1>", "<entityId2>"))
| filter compliance.result.status.level == "FAILED"
| fields timestamp, event.provider, product.vendor,
         compliance.result.status.level, compliance.rule.severity.level,
         object.id, object.name, object.type
| sort compliance.rule.severity.level asc, timestamp desc
| limit 50
```

> **24h for external** — external findings arrive on a slower polling cycle and are not
> inner-joined to a scan event. 1h risks missing the most recent external scan.

Report compliance enrichment as a sub-section of the convergence finding — not as
a standalone finding. The presence of misconfigurations on a vulnerable/detected
entity means "exploitable attack path identified." State results per source (DT SPM /
external) and note "none found" explicitly for each if 0 rows returned.

---

## Scoring Contract

> **Correlation adjusts within the assigned score band only — it never crosses a
> band boundary.**

The exposure score band is determined by the raw evidence presence (per
`dt-sec-ioc-hunting/references/exposure-scoring.md`). Correlation then
**positions within the assigned band**:

| Correlation outcome | Position in band |
|---|---|
| Tier-1 exact entity convergence (detection + CVE on same entity) | Top of band |
| Tier-1 topology convergence (detection pod runs on CVE node) | Top of band |
| Tier-1 with compliance misconfigs on converged entity or its parent cluster | Top of band + note "exploitable path" |
| Tier-2 workload-level convergence | Upper half of band |
| Tier-3 same cluster only | Band unchanged (context note only) |
| No convergence | Band unchanged (no convergence note) |

Example: multi-evidence score already in ≥90 band → Tier-1 topology convergence
positions at 95–98; no convergence positions at 90–92. The band floor (90) is
never breached downward by correlation.

---

## Correlation Workflow

Run this workflow after all hunt legs have completed and evidence is collected.

1. **Build the entity-key bundle** for each leg that returned results. See
   [Entity-Key Bundle Spec](#entity-key-bundle-spec).

2. **Tier-1 check** — compare `entityKey.smartscape_id` and `entityKey.classic_id`
   across all leg result sets. If any IDs intersect → Tier-1 match; go to Step 5.

3. **Pod→node resolution** (if detection leg has pods and CVE/vuln leg has nodes) —
   run [Step 1 query](#step-1--resolve-pod--node-via-k8snodename) to get
   `k8s.node.name` for each matched pod. Compare to CVE leg's `affected_entity.name`.
   If intersecting → Tier-1 topology convergence; go to Step 5.

4. **Tier-2 check** — compare `entityKey.name` + `entityKey.k8s.cluster` +
   `entityKey.k8s.namespace` across legs. If any triples intersect → Tier-2 match.
   
5. **Tier-3 check** — compare `entityKey.k8s.cluster` only. Record as context if
   matching; do not adjust score.

6. **Compliance enrichment** (on Tier-1 or Tier-2 matched entities) — run the
   three-step enrichment from [§ Compliance Enrichment](#compliance-enrichment-on-matched-entities):
   resolve the parent cluster for K8s entities (Step A), query DT SPM/KSPM at `1h`
   cluster-scoped (Step B), query external posture tools at `24h` entity-scoped (Step C).

7. **Render the [Convergence Matrix](#convergence-matrix-report-format)** and update
   the exposure score position within its band.

---

## Convergence Matrix (report format)

Produce this table in the exposure report (Section 7) for any hunt that had
multiple evidence legs:

```
### Section 7 — Cross-Evidence Correlation

| Leg A | Leg B | Entity A | Entity B | Tier | Convergence |
|---|---|---|---|---|---|
| Detection (IoC match) | CVE-YYYY-NNNN | K8S_POD/my-service-abc123 | K8S_NODE/ip-10-x-y-z.ec2.internal | 1 (topology) | Pod runs on CVE-affected node ✓ |
| Detection (IoC match) | CVE-ZZZZ-MMMM | K8S_POD/my-service-abc123 | K8S_NODE/other-node.ec2.internal | — | Pod not in Smartscape; topology unresolvable |
| Span match (203.0.113.5) | CVE-YYYY-NNNN | PROCESS_GROUP-2EF55DD2017DF0F5/30-IG-1 | PROCESS_GROUP-2EF55DD2017DF0F5/30-IG-1 | 1 (exact) | Span `dt.process_group.id` == RVA `affected_entity.id` ✓ |
| Log match (1.2.3.4, API-ingested source) | CVE-YYYY-NNNN | (perimeter — no entity ID on this row) | KUBERNETES_NODE/ip-10-x-y-z.ec2.internal | — | Log source carries no entity key; perimeter evidence only |
```

> **Template note:** this is a hypothetical outcome table. The Tier-1 topology row shows what
> success looks like when the pod IS found in Smartscape and resolves to a CVE-affected node.
> The Tier-1 exact row shows a span/log leg converging on the CVE leg by classic ID —
> `dt.process_group.id` (span/log) and `affected_entity.id` (RVA) share one ID space, so an
> identical value is a genuine Tier-1 match. The last row shows the residual perimeter case:
> a matched log row from an API-ingested source carries no entity key, so it cannot tier —
> report it as perimeter evidence, not as a failed correlation. If a detection pod is not in
> Smartscape (ephemeral/synthetic), report the pod as "not found in topology" and fall back
> to Tier 3 at most.

**Fields:**
- **Leg A / Leg B** — which evidence source
- **Entity A / Entity B** — entity type + name from each leg's entity-key bundle
- **Tier** — highest tier achieved (or "—" for no match attempted)
- **Convergence** — plain-language outcome

After the table, add:

```
**Correlation summary:** <1–2 sentences describing the convergence result and its
impact on the score position within the band.>

**Misconfigurations on converged entities:** <list failed CIS rules or "none found">
```


---

## Coverage


Shared entity→Smartscape match recipes for coverage counting. These patterns
resolve which runtime entities are associated with security findings or scan
events — the **match recipe only**. The **counting logic** (covered vs.
not-covered numerator/denominator, scan-event lookup, `smartscapeNodes`
denominator) stays in `dt-sec-insights/references/coverage-and-dashboards.md` as a thin
consumer of these recipes.

> **Who uses this file:**
> - `dt-sec-insights/references/coverage-and-dashboards.md` — imports these match recipes for
>   the K8s workload coverage count, cloud entity coverage count, and host
>   coverage by IP match.
> - `dt-sec-contextualization/references/entity-enrichment.md` — reuses the 3-way
>   container→workload match (same recipes, different summarization goal).

---

## Coverage Contents

- [2-Way Match for Container-Based Entities (coverage)](#2-way-match-strategy-for-container-based-entities)
- [K8s Workload Coverage Match](#k8s-workload-coverage-match)
  - [No-findings workloads (anti-join)](#k8s-workloads-with-container-images-that-have-no-security-findings)
- [Cloud Entity Coverage Match](#cloud-entity-coverage-match)
- [Host Coverage by IP Match](#host-coverage-by-ip-match)
- [Notes on the 3-Way vs. 2-Way difference](#notes-on-the-3-way-vs-2-way-difference)

---

## 2-Way Match Strategy for Container-Based Entities

External findings link to Dynatrace entities via two independent paths — combined
with `append` in the coverage context:

| Path | Match key | Source node |
|---|---|---|
| 1 | `dt.smartscape_source.id` (direct entity ID) | finding → workload via Smartscape ID |
| 2 | `container_image.digest` | finding → CONTAINER smartscapeNode → parent workload |

> **Why only 2 paths here?** A third path (`container_image.id` →
> `dt.entity.container_group_instance`) carries `containerImageId`, which does
> not exist on `smartscapeNodes CONTAINER`. The path has no pure-Smartscape
> equivalent and is omitted from the coverage counting recipe. It is used in the
> [3-way enrichment](entity-enrichment.md) context where `fetch dt.entity.*`
> is acceptable.

---

## K8s Workload Coverage Match

Used by `dt-sec-insights/references/coverage-and-dashboards.md` § K8s Workload Coverage.
Starts from `smartscapeNodes` (the denominator), then joins external findings
via Path 1 and Path 2.

> **Do not rename `id` before the join.** The `id` field of `smartscapeNodes`
> must be used as-is in join conditions (`left[id]`). Renaming it before the join
> causes the DQL engine to return 0 rows on the Smartscape-ID comparison.

```dql
smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}
| fields id, containerNames=name
| join [
    fetch security.events
    | filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
    | filter exists(dt.smartscape_source.id)
    | filterOut isNull(event.type) or isNull(object.id)
    | dedup dt.smartscape_source.id, event.provider, product.name
    | fields dt.smartscape_source.id, event.provider, product.name
  ], kind:leftouter, on:{left[id]==right[dt.smartscape_source.id]},
     fields:{event.provider, product.name, dt.smartscape_source.id}
| append [
    smartscapeNodes CONTAINER
    | expand dt.k8s.workload.id=coalesce(references[is_part_of.k8s_deployment],
                             coalesce(references[is_part_of.k8s_daemonset],
                               coalesce(references[is_part_of.k8s_cronjob],
                                 coalesce(references[is_part_of.k8s_statefulset],
                                   coalesce(references[is_part_of.k8s_job],
                                     references[is_part_of.k8s_replicaset])))))
    | filter isNotNull(dt.k8s.workload.id)
    | fields dt.k8s.workload.id, container.image.digest
    | join [
        fetch security.events
        | filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
        | filter isNotNull(container_image.digest)
        | filterOut isNull(event.type) or isNull(object.id)
        | dedup event.provider, product.name, container_image.digest
        | fields event.provider, product.name, container_image.digest
      ], kind:leftOuter, on:{left[container.image.digest]==right[container_image.digest]},
        fields:{event.provider, product.name, container_image.digest}
  ]
| fieldsAdd Product=if(isNotNull(container_image.digest) or isNotNull(dt.smartscape_source.id), product.name, else:"Not covered")
| fieldsAdd Provider=if(isNotNull(container_image.digest) or isNotNull(dt.smartscape_source.id), event.provider, else:"Not covered")
| fieldsAdd dt.k8s.workload.id=coalesce(dt.smartscape_source.id, dt.k8s.workload.id, id)
| summarize {Entities=countDistinctExact(dt.k8s.workload.id)}, by:{Provider, Product}
| sort Entities desc
```

---

## K8s Workloads with Container Images that Have No Security Findings

Start from workload topology, expand container image identifiers, then anti-join
security findings to find uncovered workloads.

```dql
smartscapeNodes {K8S_DEPLOYMENT, K8S_CRONJOB, K8S_DAEMONSET, K8S_JOB, K8S_STATEFULSET, K8S_REPLICASET}
| fields workload.id = id,
         workload.name = name,
         replicaCount = coalesce(k8s.deployment.replicas.desired,
                         coalesce(k8s.statefulset.replicas.desired,
                                  coalesce(k8s.daemonset.desired_scheduled_nodes, 0))),
         references
| join [
    smartscapeNodes CONTAINER
    | fields container.image.digest, container.image.id, references
    | fieldsAdd workload.id = coalesce(references[is_part_of.k8s_deployment],
                              coalesce(references[is_part_of.k8s_daemonset],
                                coalesce(references[is_part_of.k8s_cronjob],
                                  coalesce(references[is_part_of.k8s_statefulset],
                                    coalesce(references[is_part_of.k8s_job],
                                      references[is_part_of.k8s_replicaset])))))
    | filter isNotNull(workload.id)
  ], kind:leftOuter, on:{workload.id}, fields:{container.image.digest, container.image.id}
| lookup [
    fetch security.events, from:now()-24h
    | filter in(event.type, {"VULNERABILITY_FINDING","DETECTION_FINDING","COMPLIANCE_FINDING"})
    | filter isNotNull(container_image.digest) or isNotNull(container_image.id)
    | dedup container_image.digest, container_image.id, event.provider, product.name
    | fields container_image.digest, container_image.id, event.provider, product.name
  ], sourceField:container.image.digest, lookupField:container_image.digest, prefix:"finding.digest."
| lookup [
    fetch security.events, from:now()-24h
    | filter in(event.type, {"VULNERABILITY_FINDING","DETECTION_FINDING","COMPLIANCE_FINDING"})
    | filter isNotNull(container_image.id)
    | dedup container_image.id, event.provider, product.name
    | fields container_image.id, event.provider, product.name
  ], sourceField:container.image.id, lookupField:container_image.id, prefix:"finding.id."
| fieldsAdd hasFinding = isNotNull(finding.digest.event.provider) or isNotNull(finding.id.event.provider)
| summarize {
    containerImages = countDistinctExact(coalesce(container.image.digest, container.image.id)),
    matchedImages = countDistinctExact(if(hasFinding, coalesce(container.image.digest, container.image.id))),
    replicaCount = takeMax(replicaCount)
  }, by:{workload.id, workload.name}
| filter matchedImages == 0 and containerImages > 0
| sort replicaCount desc, containerImages desc
```

> If the pre-flight in [entity-enrichment.md](entity-enrichment.md) shows no
> container-image identifiers in external findings, report that the tenant cannot
> answer this as a coverage gap rather than treating zero findings as proof of safety.

---

## Cloud Entity Coverage Match

Only uses `dt.smartscape_source.id` — direct match is sufficient for cloud entities.
Used by `dt-sec-insights/references/coverage-and-dashboards.md` § Cloud Entity Coverage.

```dql
smartscapeNodes "*"
| filter exists(cloud.provider)
| join [
    fetch security.events
    | filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
    | filterOut isNull(event.type) or isNull(object.id)
    | filter exists(dt.smartscape_source.id)
    | dedup dt.smartscape_source.id, event.provider, product.name
    | fields dt.smartscape_source.id, event.provider, product.name
  ], kind:leftOuter,
     on:{right[dt.smartscape_source.id]==left[id]},
     fields:{dt.smartscape_source.id, event.provider, product.name}
| fieldsAdd Product=if(isNotNull(dt.smartscape_source.id), product.name, else:"Not covered")
| fieldsAdd Provider=if(isNotNull(dt.smartscape_source.id), event.provider, else:"Not covered")
| summarize {Entities=countDistinctExact(id)}, by:{Provider, Product}
| sort Entities desc
```

---

## Host Coverage by IP Match

Matches via IP address. Used by `dt-sec-insights/references/coverage-and-dashboards.md`
§ Host Coverage by IP Match.

```dql
smartscapeNodes HOST
| fields id, name, ip
| expand host.ip=ip
| join [
    fetch security.events
    | filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
    | filterOut isNull(event.type) or isNull(object.id)
    | filterOut isNull(host.ip)
    | expand host.ip
    | fieldsAdd host.ip=ip(host.ip)
    | summarize {
        Findings=countIf(in(event.type,{"VULNERABILITY_FINDING","DETECTION_FINDING","COMPLIANCE_FINDING"})),
        Scans=countIf(in(event.type,{"VULNERABILITY_SCAN","COMPLIANCE_SCAN"}))
      }, by:{host.ip, event.provider, product.name}
  ], kind:leftOuter, on:{host.ip}, fields:{event.provider, product.name}
| fieldsAdd Product=if(isNotNull(event.provider) or isNotNull(product.name), product.name, else:"Not covered")
| fieldsAdd Provider=if(isNotNull(event.provider) or isNotNull(product.name), event.provider, else:"Not covered")
| summarize {Entities=countDistinctExact(id)}, by:{Provider, Product}
| sort Entities desc
```

---

## Notes on the 3-Way vs. 2-Way Difference

The **enrichment** use case (mapping findings to entities for risk counting) uses
the **3-way match** including Path 3 (`container_image.id` →
`dt.entity.container_group_instance` → workload). See
[entity-enrichment.md § K8s Workload Enrichment](entity-enrichment.md).

The **coverage** use case (counting which workloads are covered by a product)
uses the **2-way match** (Path 1 + Path 2 only) because coverage starts from
`smartscapeNodes` and Path 3 has no pure-Smartscape equivalent.

| Context | Paths used | Starting point |
|---|---|---|
| Entity enrichment (risk count by workload) | Path 1 + 2 + 3 | `fetch security.events` |
| Coverage (covered vs. not-covered workload count) | Path 1 + 2 | `smartscapeNodes` (denominator) |
