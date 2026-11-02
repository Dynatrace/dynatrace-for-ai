# Runtime Coverage — Scan Events, Smartscape Denominator & Match Recipes

How to measure which processes, hosts, K8s workloads, and cloud entities are
covered by Dynatrace vulnerability scanning or by external security products —
the topology denominator, the scan-event numerator, and the entity match recipes
in one place. Event-type semantics (`VULNERABILITY_SCAN`, `COMPLIANCE_SCAN`, the
`*_FINDING` family) are defined in `dt-sec-insights`
(`references/all-security-events.md`); the finding-schema queries stay there.

> ⚠️ **Coverage means different things for runtime vs. non-runtime entities —
> pick the right shape first.**
>
> **Runtime entities** (hosts, processes, K8s workloads, cloud resources tracked
> in Smartscape) have a known total population, so coverage is a *percentage*
> (covered vs. not covered). These questions **REQUIRE a topology denominator —
> start from `smartscapeNodes`, never from `security.events` alone.** Compare the
> full entity population against scan/finding events via `lookup`. Scan events
> only exist for entities that *were* scanned, so summarizing them counts the
> covered set but can never reveal the uncovered set or a percentage.
>
> **Anti-pattern for runtime-entity coverage (wrong — no denominator):**

```dql
fetch security.events, from:now()-1h
| filter event.type == "VULNERABILITY_SCAN"
| summarize {scans = count(), entities = countDistinctExact(object.id)},
    by: {event.provider, product.name}
```

> For a *runtime* entity this answers "how many entities were scanned" — NOT
> "what is my coverage". Use [§ DT Runtime Coverage Analysis](#dt-runtime-coverage-analysis-smartscapenodes)
> instead; the scan-event-only queries in the first section are building blocks
> for the `lookup` subquery, not standalone runtime-coverage answers.
>
> **Non-runtime entities** (container images, code artifacts, repositories) have
> **no Smartscape population to divide by**, so there is no percentage. Coverage
> here is simply a *count of distinct scanned objects* — and the scan-event
> summary above is the **correct** answer for this class (see [§ Non-Runtime
> Entity Coverage](#non-runtime-entity-coverage-images--artifacts)).
>
> **Build the "covered" set from scan events AND findings.** Scan events
> (`VULNERABILITY_SCAN` / `COMPLIANCE_SCAN`) are the preferred coverage signal,
> but some providers/features emit no scan event — in that case a *finding* on an
> entity also proves it was covered. Product coverage dashboards union the two.
> When scan events may be missing, `lookup`/`join` both scan events and findings
> and treat an entity as covered if it appears in either (the container-image
> recipe below already does this).

> **Specific-entity coverage interpretation:** when the user asks whether a
> named entity is covered by a Dynatrace security capability (for example, RVA on
> a host/process/workload, SPM/KSPM on a K8s cluster, RAP on a service/process, or
> another DT-native capability), query the capability-specific coverage signals
> and findings in the correct operational window. If **no relevant scan,
> scan-completed, coverage, or finding events** exist for that entity, answer that
> the entity is **not covered** by that capability. The likely reason is that the
> capability is not enabled, not deployed, or not configured to monitor that
> entity. Do not answer only "no findings" when the user asked about coverage.

> **`VULNERABILITY_SCAN` is the current event type for scan coverage.**
> `VULNERABILITY_COVERAGE_REPORT_EVENT` is **deprecated** — do not use in new
> queries.

> **`product.feature` distinguishes RVA modes** — `Code-level Vulnerability
> Analytics` vs. third-party VA. Filter or filterOut on this to scope.

---

## Contents

- [DT Vulnerability Scan Events](#dt-vulnerability-scan-events)
- [DT Runtime Coverage Analysis (smartscapeNodes)](#dt-runtime-coverage-analysis-smartscapenodes)
- [Non-Runtime Entity Coverage (Images & Artifacts)](#non-runtime-entity-coverage-images--artifacts)
- [External Product Coverage Analysis](#external-product-coverage-analysis)
  - [2-Way Match Strategy for Container-Based Entities](#2-way-match-strategy-for-container-based-entities)
  - [K8s Workload Coverage (count by provider/product)](#k8s-workload-coverage-count-by-providerproduct)
  - [K8s workloads with container images that have no security findings](#k8s-workloads-with-container-images-that-have-no-security-findings)
  - [Cloud Entity Coverage (count by provider/product)](#cloud-entity-coverage-count-by-providerproduct)
  - [Host Coverage by IP Match (count by provider/product)](#host-coverage-by-ip-match-count-by-providerproduct)
- [AI-Process Coverage](#ai-process-coverage)
- [Coverage Donut Variants (smartscapeNodes-driven)](#coverage-donut-variants-smartscapenodes-driven)
- [Enrichment vs. Coverage](#enrichment-vs-coverage)
- [Best Practices](#best-practices)

---

## DT Vulnerability Scan Events

Scan events (`event.type == "VULNERABILITY_SCAN"`) mark which processes were
analyzed. Scan lookups use an explicit `from:now()-30m` window (the current scan
cadence); without `from:` the query silently falls back to the 2h default.

| Feature | `product.feature` filter |
|---|---|
| Third-party Vulnerability Analytics | `filterOut product.feature == "Code-level Vulnerability Analytics"` |
| Code-level Vulnerability Analytics | `filter product.feature == "Code-level Vulnerability Analytics"` |

**All Dynatrace scan coverage events for processes:**

```dql
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_SCAN" AND product.vendor=="Dynatrace"
| filter dt.smartscape_source.type == "PROCESS"
```

**Covered processes — Third-party Vulnerability Analytics** (deduplicated per
process):

```dql
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_SCAN" AND product.vendor=="Dynatrace"
| filter dt.smartscape_source.type == "PROCESS"
| filterOut product.feature == "Code-level Vulnerability Analytics"
| dedup dt.smartscape.process
```

**Covered processes — Code-level Vulnerability Analytics only:**

```dql
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_SCAN" AND product.vendor=="Dynatrace"
| filter dt.smartscape_source.type == "PROCESS"
| filter product.feature == "Code-level Vulnerability Analytics"
| dedup dt.smartscape.process
```

---

## DT Runtime Coverage Analysis (smartscapeNodes)

> **Topology-start vs. events-start.** For "what's NOT covered" questions
> (entities present in topology but findings missing), **start from
> `smartscapeNodes`** and `lookup` the scan events. For "covered with what?"
> questions (findings present and you want to know which entities they map to),
> start from `security.events` and join back to topology. The wrong start
> direction produces structurally-correct queries that under- or over-count.

Start from Smartscape topology, then `lookup` scan events to classify entities as
covered vs. not covered.

> **Windows.** The scan-side `fetch security.events` of every template below is
> pinned to `from:now()-30m`; the `smartscapeNodes` denominator keeps its default
> (current-topology) window — do not add `from:` to it, a short window drops
> entities and shrinks the denominator. Widen only the scan window, and only when
> the user asks for a different one.

> **Scan-only is sufficient for DT process/host coverage.** Dynatrace RVA emits a
> `VULNERABILITY_SCAN` event for every analyzed process, so the scan-event lookup
> below is a reliable covered-set on its own. The scan-events-**and**-findings
> union (top of file) matters for **external products** and any feature that may
> not emit a scan event — there a finding on the entity is the only proof it was
> covered (see the container-image recipe, which `lookup`s findings).

**Process coverage — Third-party Vulnerability Analytics:**

The scan-side `filterOut product.feature == "Code-level Vulnerability Analytics"` is **required** for
third-party (library + OS) process coverage, including when the user asks about "RVA coverage" in general:
code-level scans mark processes covered that have no third-party analytics, which inflates the covered count.
Drop it only for an explicit code-level question (use the Code-level variant above).

```dql
smartscapeNodes PROCESS
| lookup [
    fetch security.events, from:now()-30m
    | filter event.type == "VULNERABILITY_SCAN"
    | filter dt.smartscape_source.type == "PROCESS"
    | filterOut product.feature == "Code-level Vulnerability Analytics"
    | dedup dt.smartscape.process
    | fields dt.smartscape.process
  ],
  sourceField: id, lookupField: dt.smartscape.process
| fieldsAdd coverageStatus = if(isNull(lookup.dt.smartscape.process), "not covered", else: "covered")
| summarize count(), by: { coverageStatus }
```

**Host coverage — Third-party Vulnerability Analytics:**

```dql
smartscapeNodes HOST
| dedup id
| lookup [
    fetch security.events, from:now()-30m
    | filter event.type == "VULNERABILITY_SCAN"
    | filter product.vendor == "Dynatrace" or event.provider == "Dynatrace"
    | filter dt.smartscape_source.type == "PROCESS"
    | filterOut product.feature == "Code-level Vulnerability Analytics"
    | fieldsKeep dt.smartscape.host
    | dedup dt.smartscape.host
  ],
  sourceField: id, lookupField: dt.smartscape.host, prefix: "scan.events."
| fields id,
         coverage = if(isNotNull(scan.events.dt.smartscape.host), "covered", else: "not covered")
| summarize hosts = count(), by: { coverage }
| fieldsKeep hosts, coverage
```

**Uncovered hosts — list form:**

```dql
smartscapeNodes HOST
| dedup id
| lookup [
    fetch security.events, from:now()-30m
    | filter event.type == "VULNERABILITY_SCAN"
    | filter product.vendor == "Dynatrace" or event.provider == "Dynatrace"
    | filter dt.smartscape_source.type == "PROCESS"
    | filterOut product.feature == "Code-level Vulnerability Analytics"
    | fieldsKeep dt.smartscape.host
    | dedup dt.smartscape.host
  ],
  sourceField: id, lookupField: dt.smartscape.host, prefix: "scan.events."
| fields id, name,
         coverage = if(isNotNull(scan.events.dt.smartscape.host), "covered", else: "not covered")
| filter coverage == "not covered"
| sort name asc
```

**Host coverage per `product.feature` (single query):** use when the question asks
"by feature" / "per product feature". Each host is crossed with both features and
`join`ed (not `lookup`ed — a `lookup` returns one match per host, so a host
scanned by both features would be counted for only one) on host id **and**
feature, so each feature gets its own covered / not-covered split. A scan event
without `product.feature` is third-party Vulnerability Analytics. A host scanned
by both features is `covered` in both rows; the rows are per feature and do not sum
to the host count.

```dql
smartscapeNodes HOST
| dedup id
| fieldsAdd product.feature = array("Third-party Vulnerability Analytics", "Code-level Vulnerability Analytics")
| expand product.feature
| join [
    fetch security.events, from:now()-30m
    | filter event.type == "VULNERABILITY_SCAN"
    | filter product.vendor == "Dynatrace" or event.provider == "Dynatrace"
    | fields dt.smartscape.host, product.feature = coalesce(product.feature, "Third-party Vulnerability Analytics")
    | dedup {dt.smartscape.host, product.feature}
  ], kind: leftOuter,
  on: {left[id] == right[dt.smartscape.host], left[product.feature] == right[product.feature]},
  fields: {scan.host = dt.smartscape.host}
| fieldsAdd coverage = if(isNotNull(scan.host), "covered", else: "not covered")
| summarize {
    hosts = count(),
    sampleHostNames = arraySlice(collectArray(name), from: 0, to: 50)
  }, by: {product.feature, coverage}
| sort product.feature asc, coverage asc
```

### Interpreting `0 not covered` results

**When `not covered = 0` is returned, that is a complete answer** — every host
in the topology has a matching `VULNERABILITY_SCAN` event. Do not re-query to
sanity-check. Instead, surface the total host count from the same query
(`summarize hosts = count(), by: { coverage }`) so the answer reads
`0 of N hosts uncovered` — that's the actionable form. To confirm scan
freshness, surface scan-event timestamps separately rather than re-running the
join.

---

## Non-Runtime Entity Coverage (Images & Artifacts)

Container images, code artifacts, and repositories are **not runtime entities**
and have no Smartscape population to divide by — so there is **no coverage
percentage**. Coverage for this class is a *count of distinct scanned objects*,
optionally broken down by provider/product. Here the scan-event summary (the
"anti-pattern" for runtime coverage) is the **correct** shape, because there is
no denominator to reconcile against.

Count the covered set from scan events **and** findings (a finding on an image
also proves it was covered, and some providers emit no scan event):

```dql
fetch security.events, from:now()-24h
| filter in(event.type, {"VULNERABILITY_SCAN", "VULNERABILITY_FINDING"})
| filter isNotNull(container_image.digest)
| summarize {
    images = countDistinctExact(container_image.digest)
  }, by: {event.provider, product.name}
| sort images desc
```

There is no "not covered" row here: without an authoritative image/artifact
inventory, the uncovered set is unknown. Report this as an absolute count, not a
ratio. (To answer "which *running workloads* have images with no findings" — a
runtime question with a denominator — use [§ K8s workloads with container images
that have no security findings](#k8s-workloads-with-container-images-that-have-no-security-findings)
instead.)

---

## External Product Coverage Analysis

Count entities covered (or not) by any external security product. These queries
start from Smartscape topology (not `security.events`) and join external findings.

### 2-Way Match Strategy for Container-Based Entities

External findings link to Dynatrace entities via two independent paths — both
combined with `append`:

| Path | Match key | Source node |
|---|---|---|
| 1 | `dt.smartscape_source.id` (direct entity ID) | finding → workload via Smartscape ID |
| 2 | `container_image.digest` | finding → CONTAINER smartscapeNode → parent workload |

### K8s Workload Coverage (count by provider/product)

> **Do not rename `id` before the join.** The `id` field of `smartscapeNodes`
> must be used as-is in join conditions (`left[id]`). Renaming it to an alias
> before the join (e.g. `| fields workload.id=id`) causes the DQL engine to
> return 0 rows on the Smartscape-ID comparison. Always add the alias after
> all joins via `fieldsAdd`.

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

### K8s workloads with container images that have no security findings

Start from workload topology, expand container image identifiers, then anti-join
security findings. If the pre-flight in
[entity-enrichment.md § Pre-flight Check](entity-enrichment.md#pre-flight-check--identifier-availability)
shows no container-image identifiers in external findings, report that the
tenant cannot answer this as a coverage gap rather than treating zero findings
as proof of safety.

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
    | fields container.image.digest, references
    | expand workload.id = coalesce(references[is_part_of.k8s_deployment],
                              coalesce(references[is_part_of.k8s_daemonset],
                                coalesce(references[is_part_of.k8s_cronjob],
                                  coalesce(references[is_part_of.k8s_statefulset],
                                    coalesce(references[is_part_of.k8s_job],
                                      references[is_part_of.k8s_replicaset])))))
    | filter isNotNull(workload.id)
  ], kind:leftOuter, on:{workload.id}, fields:{container.image.digest}
| lookup [
    fetch security.events, from:now()-7d
    | filter in(event.type, {"VULNERABILITY_FINDING","DETECTION_FINDING","COMPLIANCE_FINDING"})
    | filter isNotNull(container_image.digest)
    | dedup container_image.digest, event.provider, product.name
    | fields container_image.digest, event.provider, product.name
  ], sourceField:container.image.digest, lookupField:container_image.digest, prefix:"finding.digest."
| fieldsAdd hasFinding = isNotNull(finding.digest.event.provider)
| summarize {
    containerImages = countDistinctExact(container.image.digest),
    matchedImages = countDistinctExact(if(hasFinding, container.image.digest)),
    replicaCount = takeMax(replicaCount)
  }, by:{workload.id, workload.name}
| filter matchedImages == 0 and containerImages > 0
| sort replicaCount desc, containerImages desc
```

### Cloud Entity Coverage (count by provider/product)

Only uses `dt.smartscape_source.id` — direct match is sufficient for cloud entities.

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
   fields:{coveredBy=dt.smartscape_source.id, event.provider, product.name}
| fieldsAdd Product=if(isNotNull(coveredBy), product.name, else:"Not covered")
| fieldsAdd Provider=if(isNotNull(coveredBy), event.provider, else:"Not covered")
| summarize {Entities=countDistinctExact(id)}, by:{Provider, Product}
| sort Entities desc
```

### Host Coverage by IP Match (count by provider/product)

Matches via IP address. The inner join also counts findings/scans per IP to
enable filtering if needed.

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

## AI-Process Coverage

For AI-process coverage, use `GENAI_SERVICE -> PROCESS` as the denominator (Path 3 in
[identity-mapping.md](identity-mapping.md) § Mapping Primitive) and left-`lookup`
`VULNERABILITY_SCAN`, then report covered vs. uncovered entities. Same shape as
[§ DT Runtime Coverage Analysis](#dt-runtime-coverage-analysis-smartscapenodes) with the AI-scoped
process set in place of `smartscapeNodes PROCESS`.

---

## Coverage Donut Variants (smartscapeNodes-driven)

### Host Coverage by Any External Product (donut)

```dql
smartscapeNodes HOST
| dedup id
| join [
    fetch security.events
    | filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
    | filter exists(host.ip)
  ], on:{host.ip}, kind:leftOuter
| summarize count(), by:{covered=if(isNotNull(event.provider), "Covered", else:"Not covered")}
```

### Host Coverage by Dynatrace Scan Events (donut)

Counts Smartscape hosts that have a Dynatrace `VULNERABILITY_SCAN` event
(`dt.smartscape.host` is set on non-K8s scans only). The 24h scan window here is
deliberate for a dashboard tile; use `from:now()-30m` for a current-state answer:

```dql
smartscapeNodes HOST
| dedup id
| lookup [
    fetch security.events, from:now()-24h
    | filter event.type == "VULNERABILITY_SCAN"
    | filter isNotNull(dt.smartscape.host)
    | dedup dt.smartscape.host
  ], sourceField:id, lookupField:dt.smartscape.host
| summarize count(), by:{coverage=if(isNotNull(lookup.dt.smartscape.host), "covered", else: "not covered")}
```

For full coverage analysis broken down by provider/product (and the 2-way
K8s/host match), see [§ External Product Coverage Analysis](#external-product-coverage-analysis).

---

## Enrichment vs. Coverage

Both use cases use the same **2-way match** (Path 1 `dt.smartscape_source.id` + Path 2
`container_image.digest`); they differ in the starting point and the summarization goal.
See [entity-enrichment.md § K8s Workload Enrichment](entity-enrichment.md) for the enrichment form.

| Context | Paths used | Starting point |
|---|---|---|
| Entity enrichment (risk count by workload) | Path 1 + 2 | `fetch security.events` |
| Coverage (covered vs. not-covered workload count) | Path 1 + 2 | `smartscapeNodes` (denominator) |

---

## Best Practices

1. **Use `VULNERABILITY_SCAN` not `VULNERABILITY_COVERAGE_REPORT_EVENT`** — the
   latter is deprecated.
2. **Distinguish Code-level vs Third-party VA via `product.feature`** — these
   are separate scanning modes within RVA; coverage means different things.
3. **For runtime coverage of external products**, start from `smartscapeNodes`
   not `security.events` — the question is "which entities exist," and the answer
   joins back to findings.
4. **Use the 2-way match for container-based entities** — direct Smartscape ID
   and container image digest. Different external scanners populate different
   paths.
5. **For cloud entities**, direct `dt.smartscape_source.id` match is sufficient
   — they don't go through the container abstraction.
6. **For hosts**, prefer IP-based matching when the external scanner doesn't
   carry Dynatrace entity IDs (most don't).
7. **No default `dt.system.bucket` filter** — see SKILL.md best practice 8.
