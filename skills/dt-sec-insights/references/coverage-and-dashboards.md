# Coverage & Dashboard Patterns

How to measure which processes, hosts, K8s workloads, and cloud entities are
covered by Dynatrace vulnerability scanning or by external security products.

> **Match recipes are in `dt-sec-contextualization`.** The 2-way container→workload
> match recipe (K8s workload coverage), cloud entity match (Path 1), and host
> coverage by IP match live in
> `dt-sec-contextualization/references/correlation-and-coverage.md`. This file owns the **counting
> logic** — the `smartscapeNodes` denominator queries, the DT-native scan-event
> lookups, and the covered/not-covered classification. Load
> `dt-sec-contextualization` alongside this file for any external-product coverage
> question that requires the container→workload or cloud match recipe.

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
| summarize scans = count(), entities = countDistinctExact(object.id),
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
  - [3-Way Match Strategy for Container-Based Entities](#3-way-match-strategy-for-container-based-entities)
  - [K8s Workload Coverage (count by provider/product)](#k8s-workload-coverage-count-by-providerproduct)
  - [Cloud Entity Coverage (count by provider/product)](#cloud-entity-coverage-count-by-providerproduct)
  - [Host Coverage by IP Match (count by provider/product)](#host-coverage-by-ip-match-count-by-providerproduct)
- [Best Practices](#best-practices)

---

## DT Vulnerability Scan Events

Scan events (`event.type == "VULNERABILITY_SCAN"`) mark which processes were
analyzed.

| Feature | `product.feature` filter |
|---|---|
| Third-party Vulnerability Analytics | `filterOut product.feature == "Code-level Vulnerability Analytics"` |
| Code-level Vulnerability Analytics | `filter product.feature == "Code-level Vulnerability Analytics"` |

**All Dynatrace scan coverage events for processes:**

```dql
fetch security.events
| filter event.type == "VULNERABILITY_SCAN" AND product.vendor=="Dynatrace"
| filter dt.source_entity.type == "process_group_instance"
```

**Covered processes — Third-party Vulnerability Analytics** (deduplicated per
host+process):

```dql
fetch security.events
| filter event.type == "VULNERABILITY_SCAN" AND product.vendor=="Dynatrace"
| filter dt.source_entity.type == "process_group_instance"
| filterOut product.feature == "Code-level Vulnerability Analytics"
| dedup dt.entity.host, dt.entity.process_group_instance
```

**Covered processes — Code-level Vulnerability Analytics only:**

```dql
fetch security.events
| filter event.type == "VULNERABILITY_SCAN" AND product.vendor=="Dynatrace"
| filter dt.source_entity.type == "process_group_instance"
| filter product.feature == "Code-level Vulnerability Analytics"
| dedup dt.entity.host, dt.entity.process_group_instance
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

> **Scan-only is sufficient for DT process/host coverage.** Dynatrace RVA emits a
> `VULNERABILITY_SCAN` event for every analyzed process, so the scan-event lookup
> below is a reliable covered-set on its own. The scan-events-**and**-findings
> union (top of file) matters for **external products** and any feature that may
> not emit a scan event — there a finding on the entity is the only proof it was
> covered (see the container-image recipe, which `lookup`s findings).

**Process coverage — Third-party Vulnerability Analytics:**

```dql
smartscapeNodes PROCESS
| lookup [
    fetch security.events
    | filter event.type == "VULNERABILITY_SCAN"
    | filter dt.source_entity.type == "process_group_instance"
    | filterOut product.feature == "Code-level Vulnerability Analytics"
    | dedup dt.entity.host, dt.entity.process_group_instance
    | fields dt.entity.process_group_instance
  ],
  sourceField: id_classic, lookupField: dt.entity.process_group_instance
| fieldsAdd coverageStatus = if(isNull(lookup.dt.entity.process_group_instance), "not covered", else: "covered")
| summarize count(), by: { coverageStatus }
```

**Host coverage — Third-party Vulnerability Analytics:**

```dql
smartscapeNodes HOST
| dedup id_classic
| lookup [
    fetch security.events
    | filter event.type == "VULNERABILITY_SCAN"
    | filter dt.source_entity.type == "process_group_instance"
    | filterOut product.feature == "Code-level Vulnerability Analytics"
    | fieldsKeep dt.entity.host
    | dedup dt.entity.host
  ],
  sourceField: id_classic, lookupField: dt.entity.host, prefix: "scan.events."
| fields id_classic,
         coverage = if(isNotNull(scan.events.dt.entity.host), "covered", else: "not covered")
| summarize hosts = count(), by: { coverage }
| fieldsKeep hosts, coverage
```

**Uncovered hosts — list form:**

```dql
smartscapeNodes HOST
| dedup id_classic
| lookup [
    fetch security.events
    | filter event.type == "VULNERABILITY_SCAN"
    | filter dt.source_entity.type == "process_group_instance"
    | filterOut product.feature == "Code-level Vulnerability Analytics"
    | fieldsKeep dt.entity.host
    | dedup dt.entity.host
  ],
  sourceField: id_classic, lookupField: dt.entity.host, prefix: "scan.events."
| fields id_classic, name,
         coverage = if(isNotNull(scan.events.dt.entity.host), "covered", else: "not covered")
| filter coverage == "not covered"
| sort name asc
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
| filter isNotNull(container_image.digest) or isNotNull(container_image.id)
| summarize {
    images = countDistinctExact(coalesce(container_image.digest, container_image.id))
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

> **Why only 2 paths?** A third path matching on `container_image.id`
> (OCI image ID) previously used `dt.entity.container_group_instance`, which
> carries `containerImageId`. That field does not exist on `smartscapeNodes
> CONTAINER`, so the path has no pure-Smartscape equivalent and is omitted.

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
`dt-sec-contextualization/references/entity-enrichment.md` (§ K8s Workload Enrichment)
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
   fields:{dt.smartscape_source.id, event.provider, product.name}
| fieldsAdd Product=if(isNotNull(dt.smartscape_source.id), product.name, else:"Not covered")
| fieldsAdd Provider=if(isNotNull(dt.smartscape_source.id), event.provider, else:"Not covered")
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

## Best Practices

1. **Use `VULNERABILITY_SCAN` not `VULNERABILITY_COVERAGE_REPORT_EVENT`** — the
   latter is deprecated.
2. **Distinguish Code-level vs Third-party VA via `product.feature`** — these
   are separate scanning modes within RVA; coverage means different things.
3. **For runtime coverage of external products**, start from `smartscapeNodes`
   not `security.events` — the question is "which entities exist," and the answer
   joins back to findings.
4. **Use the 3-way match for container-based entities** — direct Smartscape ID,
   container image digest, and container image ID. Different external scanners
   populate different paths.
5. **For cloud entities**, direct `dt.smartscape_source.id` match is sufficient
   — they don't go through the container abstraction.
6. **For hosts**, prefer IP-based matching when the external scanner doesn't
   carry Dynatrace entity IDs (most don't).
7. **No `dt.system.bucket` filter** — security event data may live in any bucket;
   bucket scoping risks hiding data.

---

## Dashboard Query Patterns

KPI tiles, top-N tables, trend charts, and container/registry rollups. Each
pattern complements the base queries in [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md),
[compliance.md](compliance.md), and [detections.md](detections.md).

For shared building blocks (risk-level mapping, status aggregation, sem-dict
filter, time-window rules), see [common-patterns.md](common-patterns.md). For
field reference, see [data-model.md](data-model.md).

> **No `dt.system.bucket` filter.** Security event data may live in any bucket;
> bucket scoping risks hiding tile data.

> **Load this reference only for dashboard / chart / KPI requests.** For plain
> investigation, triage, or drill-down, the per-domain references are sufficient.

---

## Contents

- [KPI Tiles (single-value)](#kpi-tiles-single-value)
  - [Open Non-Muted Vulnerability Count (DT RVA)](#open-non-muted-vulnerability-count-dt-rva)
  - [Vulnerabilities with Public Exploit Available](#vulnerabilities-with-public-exploit-available)
  - [Open vs. Resolved Status Counter](#open-vs-resolved-status-counter)
  - [Critical External Findings by Registry](#critical-external-findings-by-registry)
- [Top-N Tables](#top-n-tables)
  - [Top 10 External Vulnerabilities by Affected Object Count](#top-10-external-vulnerabilities-by-affected-object-count)
  - [Top 10 Container-Image Vulnerabilities by Image Count](#top-10-container-image-vulnerabilities-by-image-count)
  - [Top 10 Repositories by Critical+High Findings](#top-10-repositories-by-criticalhigh-findings)
  - [Top 10 Vulnerable Components](#top-10-vulnerable-components)
  - [Findings Distribution by Object Type (HIGH+CRITICAL only)](#findings-distribution-by-object-type-highcritical-only)
  - [Top 10 Affected Hosts (entity-enriched)](#top-10-affected-hosts-entity-enriched)
- [Trend Charts (timeseries)](#trend-charts-timeseries)
  - [Vulnerability Counts Over Time, Stacked by Risk Level](#vulnerability-counts-over-time-stacked-by-risk-level)
- [Provider / Product Coverage Summary](#provider--product-coverage-summary)
  - [Findings vs. Scans Split per Product](#findings-vs-scans-split-per-product)
- [Coverage Donut Variants (smartscapeNodes-driven)](#coverage-donut-variants-smartscapenodes-driven)
  - [Host Coverage by Any External Product (donut)](#host-coverage-by-any-external-product-donut)
  - [Entity-Centric Coverage via `fetch dt.entity.host`](#entity-centric-coverage-via-fetch-dtentityhost)
- [Multi-Type Combined Views](#multi-type-combined-views)
  - [One-Row-Per-Entity Risk Summary (DT RVA + external)](#one-row-per-entity-risk-summary-dt-rva--external)

---

## KPI Tiles (single-value)

### Open Non-Muted Vulnerability Count (DT RVA)

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT","VULNERABILITY_STATUS_CHANGE_EVENT","VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| filter vulnerability.mute.status != "MUTED"
| summarize count()
```

### Vulnerabilities with Public Exploit Available

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT","VULNERABILITY_STATUS_CHANGE_EVENT","VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| filter vulnerability.davis_assessment.exploit_status=="AVAILABLE"
| summarize {Vulnerabilities = countDistinctExact(vulnerability.display_id)}
```

### Open vs. Resolved Status Counter

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT","VULNERABILITY_STATUS_CHANGE_EVENT","VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| summarize {
    Open=countIf(vulnerability.resolution.status=="OPEN"),
    Resolved=countIf(vulnerability.resolution.status=="RESOLVED")
  }
```

### Critical External Findings by Registry

```dql
fetch security.events
| filter event.type=="VULNERABILITY_FINDING" AND dt.security.risk.level=="CRITICAL"
| filter isNotNull(container_image.registry)
| dedup {object.id, vulnerability.id}
| summarize {Findings=count()}, by:{Registry=container_image.registry}
```

---

## Top-N Tables

### Top 10 External Vulnerabilities by Affected Object Count

```dql
fetch security.events
| filter event.type=="VULNERABILITY_FINDING"
| fieldsAdd repository=coalesce(artifact.repository, container_image.repository)
| filterOut isNull(finding.id) OR isNull(object.id) OR isNull(vulnerability.id)
| fieldsAdd component_name=coalesce(software_component.name, component.name),
            component_version=component.version
| dedup {object.id, vulnerability.id, component_name, component_version}, sort: {timestamp desc}
| summarize {
    `Risk score`=toDouble(takeMax(dt.security.risk.score)),
    `Affected objects`=countDistinctExact(object.id),
    `Vulnerable components`=countDistinctExact(component_name)
  }, by:{Vulnerability=vulnerability.title, `Risk level`=dt.security.risk.level}
| sort {`Risk score`, direction:"descending"}
| fields `Risk level`, Vulnerability, `Affected objects`, `Vulnerable components`
| limit 10
```

### Top 10 Container-Image Vulnerabilities by Image Count

```dql
fetch security.events
| filter event.type == "VULNERABILITY_FINDING"
     AND object.type == "CONTAINER_IMAGE"
| fieldsAdd component_name=coalesce(software_component.name, component.name),
      component_version=component.version
| filter isNotNull(component_name)
| dedup {object.id, vulnerability.id, component_name, component_version,
         container_image.registry, container_image.repository}, sort: {timestamp desc}
| summarize {
    `Risk score`=toDouble(takeMax(dt.security.risk.score)),
    `Container images`=countDistinctExact(container_image.digest)
  }, by:{Vulnerability=vulnerability.id, `Risk level`=dt.security.risk.level}
| sort {`Risk score`, direction:"descending"}, {`Container images`, direction:"descending"}
| fields `Risk level`, Vulnerability, `Container images`
| limit 10
```

### Top 10 Repositories by Critical+High Findings

```dql
fetch security.events
| filter event.type == "VULNERABILITY_FINDING"
| fieldsAdd repository=coalesce(artifact.repository, container_image.repository)
| filter isNotNull(repository)
| dedup {repository, vulnerability.id, object.id}
| summarize {
    Findings=count(),
    Critical=countIf(dt.security.risk.level=="CRITICAL"),
    High=countIf(dt.security.risk.level=="HIGH")
  }, by:{Repository=repository}
| sort Critical desc, High desc
| limit 10
```

### Top 10 Vulnerable Components

```dql
fetch security.events
| filter event.type=="VULNERABILITY_FINDING"
| fieldsAdd component_name=coalesce(software_component.name, component.name),
            component_version=component.version
| filter isNotNull(component_name)
| dedup {component_name, component_version, vulnerability.id}
| summarize {
    Findings=count(),
    Critical=countIf(dt.security.risk.level=="CRITICAL"),
    High=countIf(dt.security.risk.level=="HIGH"),
    `Affected images`=countDistinctExact(container_image.digest)
  }, by:{Component=component_name, Version=component_version}
| sort Critical desc
| limit 10
```

### Findings Distribution by Object Type (HIGH+CRITICAL only)

```dql
fetch security.events
| filter event.type=="VULNERABILITY_FINDING" AND in(dt.security.risk.level,{"HIGH","CRITICAL"})
| dedup {object.id, vulnerability.id}, sort: {timestamp desc}
| summarize {Findings=count()}, by:{`Object type`=object.type}
| sort Findings desc
```

### Top 10 Affected Hosts (entity-enriched)

Joins findings to HOST smartscapeNodes for runtime context. For full 3-way
enrichment (container image digest / id paths), see
`dt-sec-contextualization/references/entity-enrichment.md`.

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT","VULNERABILITY_STATUS_CHANGE_EVENT","VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| summarize {
    Vulnerabilities=count(),
    Critical=countIf(vulnerability.risk.score >= 9)
  }, by:{affected_entity.id, affected_entity.name}
| join [smartscapeNodes HOST], on:{right[id]==left[affected_entity.id]}
| sort Vulnerabilities desc
| limit 10
```

---

## Trend Charts (timeseries)

### Vulnerability Counts Over Time, Stacked by Risk Level

Uses a computed sort key (`riskLevelSorting`) so the visualization stacks levels
in CRITICAL → LOW order:

```dql
fetch security.events
| filter event.type == "VULNERABILITY_FINDING"
| fieldsAdd riskLevelSorting = coalesce(
    if(dt.security.risk.level=="CRITICAL", 1),
    if(dt.security.risk.level=="HIGH",     2),
    if(dt.security.risk.level=="MEDIUM",   3),
    if(dt.security.risk.level=="LOW",      4),
    5)
| makeTimeseries countDistinct(vulnerability.id),
                 by:{riskLevelSorting, dt.security.risk.level},
                 bins: 24
```

For DT RVA equivalents (open vulnerability counts over 7d in 3h buckets), see
[vulnerabilities-dynatrace.md § Time-Series Trends](vulnerabilities-dynatrace.md#dt-rva-time-series-trends-7-days-3h-buckets).

---

## Provider / Product Coverage Summary

### Findings vs. Scans Split per Product

```dql
fetch security.events
| summarize {
    Findings=countIf(in(event.type,{"VULNERABILITY_FINDING","DETECTION_FINDING","COMPLIANCE_FINDING"})),
    Scans=countIf(in(event.type,{"VULNERABILITY_SCAN","COMPLIANCE_SCAN"}))
  }, by:{Provider=event.provider, Product=product.name}
```

This is the canonical "which integrations are active" query — counts both findings
and scan-coverage events per source.

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

### Entity-Centric Coverage via `fetch dt.entity.host`

Alternative to `smartscapeNodes`-based coverage; uses the entity stream directly:

```dql
fetch dt.entity.host
| lookup [
    fetch security.events
    | filter event.type == "VULNERABILITY_SCAN"
    | dedup dt.entity.host
  ], sourceField:id, lookupField:dt.entity.host
| summarize count(), by:{coverage=if(isNotNull(lookup.dt.entity.host), "covered", else: "not covered")}
```

For full coverage analysis broken down by provider/product (and the 3-way
K8s/host match), see [§ External Product Coverage Analysis](#external-product-coverage-analysis).

---

## Multi-Type Combined Views

### One-Row-Per-Entity Risk Summary (DT RVA + external)

To produce a single row per entity with risk counts across vulnerability types,
combine the canonical RVA pattern (from [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md))
with external findings via `union`/`append`, then summarize. Keep this as a
reporting-layer merge — don't try to unify the two query shapes upstream.

```dql
// Branch A: DT RVA per entity
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT","VULNERABILITY_STATUS_CHANGE_EVENT","VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| summarize {
    Critical = countIf(vulnerability.risk.score >= 9),
    High     = countIf(vulnerability.risk.score >= 7 and vulnerability.risk.score < 9),
    Medium   = countIf(vulnerability.risk.score >= 4 and vulnerability.risk.score < 7),
    Low      = countIf(vulnerability.risk.score >= 0.1 and vulnerability.risk.score < 4)
  }, by:{Entity=affected_entity.name}
| append [
    // Branch B: external per object (sample)
    fetch security.events
    | filter event.type=="VULNERABILITY_FINDING"
    | filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
    | dedup {object.id, vulnerability.id}
    | summarize {
        Critical=countIf(dt.security.risk.level=="CRITICAL"),
        High    =countIf(dt.security.risk.level=="HIGH"),
        Medium  =countIf(dt.security.risk.level=="MEDIUM"),
        Low     =countIf(dt.security.risk.level=="LOW")
      }, by:{Entity=object.name}
  ]
| summarize {
    Critical=sum(Critical), High=sum(High), Medium=sum(Medium), Low=sum(Low)
  }, by:{Entity}
| sort Critical desc, High desc
| limit 25
```

---

## Threat Intelligence Dashboards

Threat-intelligence (`THREAT_REPORT`) tiles use the canonical base (SD guard +
`dedup {threat.report.id}`) — see [threat-intelligence.md](threat-intelligence.md). Two ready-made
sample dashboards live in `evals/skills/dt-sec-insights/sources/sample-dashboards/`:

- **`emerging-threat-intelligence-reports.json`** — overview: unique-reports-over-time by provider
  (`makeTimeseries count(), by:{event.provider}`), total-reports single value, last-10-reports table,
  and top-N IOC/actor/industry/country/tag/technique tiles (`expand` observable →
  `countDistinctExact(threat.report.id)`). Visualizations: **choropleth** for target countries
  (`threat.target.countries.iso_codes`), **categorical bar** (log scale) for actors / industries /
  tags, **bar chart** for the provider trend.
- **`threat-exposure-analysis.json`** — per-report drilldown: select a report, extract its IOCs, then
  correlate against the environment (RVA + external vulnerabilities by CVE, detections by actor IP /
  MITRE technique, logs by `contains(content, …)`, traces by IP/domain/URL). Uses dashboard
  **variables** to carry the IOC lists and `in(field, $Var)` filters (the self-contained-query
  equivalent uses `join` — see [threat-intelligence.md § Threat-Exposure Correlation](threat-intelligence.md#threat-exposure-correlation-ioc--environment)).

> **Tile field nuances:** use `threat.target.industries` (plural) and
> `threat.target.countries.iso_codes` for the map; `coalesce(toTimestamp(threat.report.time.created), timestamp)`
> for report time. These are threat-intel tiles — do **not** add `dt.security.risk.level` coloring
> (the field is null on `THREAT_REPORT`).
