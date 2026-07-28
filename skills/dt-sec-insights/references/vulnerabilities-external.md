# External Vulnerability Findings — `security.events`

Ingested vulnerability findings from external SCA / SAST / image scanners (Snyk,
Qualys, Tenable, AWS Inspector, GitHub Advanced Security, etc.). For Dynatrace-native
Runtime Vulnerability Analytics (RVA) see [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md).

> **Cross-references:** field reference → [data-model.md § Vulnerability Fields (external)](data-model.md#vulnerability-fields-external--dt-emitted-vulnerability_finding) ·
> provider scoping, double-counting guard, cross-provider summary →
> [all-security-events.md](all-security-events.md) · repository coalescing,
> lifecycle anti-join → [common-patterns.md](common-patterns.md) · mapping findings
> to runtime entities → [dt-sec-contextualization entity-enrichment.md](../../dt-sec-contextualization/references/entity-enrichment.md).

## Contents

- [Top vulnerable components (libraries)](#top-vulnerable-components-libraries--external-findings-uc-v9)
- [External vulnerable container images](#external-vulnerable-container-images)
- [Verify external vulnerability findings with RVA](#verify-external-vulnerability-findings-with-rva)
- [External container-image findings also detected by RVA on the same running K8s workload](#external-container-image-findings-also-detected-by-rva-on-the-same-running-k8s-workload)
- [Critical external vulnerabilities newly reported in the last 7d](#critical-external-vulnerabilities-newly-reported-in-the-last-7d-not-in-the-prior-7d)
- [Cross-provider vulnerability view](#cross-provider-vulnerability-view)
- [Mapping external findings to runtime entities](#mapping-external-findings-to-runtime-entities)

External vulnerability findings are one-shot `VULNERABILITY_FINDING` events. They do
**not** need the dedup+summarize-to-state pipeline that DT RVA requires — each row is
already a discrete finding. Dedup is still useful when the same finding is re-ingested.

> **External component fields:** use `software_component.*` as the SD-compatible
> component namespace for external `VULNERABILITY_FINDING` rows (especially
> `software_component.name`, `software_component.purl`, `software_component.type`).
> Some providers still populate legacy `component.name` / `component.version`, so
> use `coalesce(software_component.name, component.name)` for display and dedup
> keys when broad provider compatibility is needed. Do **not** use
> `affected_entity.vulnerable_component.*` on external findings — that namespace is
> Dynatrace RVA-specific.

> **CVE reference field:** use `vulnerability.references.cve` for CVE matching on
> both external `VULNERABILITY_FINDING` rows and DT RVA rows. It is usually an
> array, so prefer `in("CVE-…", vulnerability.references.cve)` or `expand` before
> equality checks. Do **not** query invented fields such as
> `vulnerability.cve.id` or `vulnerability.cve.ids`.

**All external vulnerabilities:**

```dql
fetch security.events
| filter event.type == "VULNERABILITY_FINDING"
| filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
```

**Vulnerabilities-app compatibility check** (validates all SD-required fields are
present):

```dql
fetch security.events
| filter event.type == "VULNERABILITY_FINDING"
| filter isNotNull(event.id)
     and isNotNull(event.provider)
     and isNotNull(finding.type)
     and isNotNull(dt.security.risk.level)
     and isNotNull(dt.security.risk.score)
     and isNotNull(finding.id)
     and isNotNull(finding.title)
     and isNotNull(object.id)
     and isNotNull(object.type)
     and isNotNull(finding.time.created)
```

**Top 10 external vulnerabilities by affected object count:**

```dql
fetch security.events
| filter event.type=="VULNERABILITY_FINDING"
| filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
| fieldsAdd repository=coalesce(artifact.repository, container_image.repository)
| filterOut isNull(finding.id) OR isNull(object.id) OR isNull(vulnerability.id)
| fieldsAdd component_name = coalesce(software_component.name, component.name),
            component_version = component.version
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

Lists vulnerable container images with identity preserved — repository, image name, and digest are all included in the `by:` keys so findings from different registries or digest versions are never collapsed together. Uses `coalesce(artifact.repository, container_image.repository)` (see [common-patterns.md § 12](common-patterns.md)) because external scanners populate one of the two repository fields. `container_image.digest` is the primary image identity field — `container_image.name` is not reliably populated by external providers.

```dql
fetch security.events, from: -24h
| filter event.type == "VULNERABILITY_FINDING"
| filterOut event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
// SD-isNotNull guard — mandatory for cross-provider counts
| filter isNotNull(finding.id) AND isNotNull(object.id) AND isNotNull(dt.security.risk.level)
// Coalesce both repository fields
| fieldsAdd repository = coalesce(artifact.repository, container_image.repository)
// Dedup: same finding on same image digest from same provider counts once
| dedup {event.provider, finding.id, object.id, dt.security.risk.level}, sort: {timestamp desc}
// Preserve full identity before ranking — do not group only by image name
| summarize {
    findings.count = count(),
    Critical = countIf(dt.security.risk.level == "CRITICAL"),
    High = countIf(dt.security.risk.level == "HIGH"),
    vulnerabilities = collectDistinct(finding.title),
    providers = collectDistinct(event.provider)
  }, by: {repository, ObjectName = object.name, ImageDigest = container_image.digest, object.type}
| sort Critical desc, High desc
| limit 50
```

## Verify external vulnerability findings with RVA

Use this use case when the user asks whether external vendor vulnerability
findings are confirmed by Dynatrace Runtime Vulnerability Analytics (RVA), for
example: "does this external image finding run in my K8s environment and match
an RVA vulnerability?" or "does a Qualys host finding correspond to a runtime
vulnerability on the same host?"

Verification is a two-stage process:

1. **Same vulnerability:** match external `VULNERABILITY_FINDING` rows to open RVA
   rows by CVE using `vulnerability.references.cve` on both sides. Expand the CVE
   array first. Do not use `vulnerability.cve.id` / `.ids`.
2. **Related runtime entity/resource/artifact:** prove that the external object is
   related to an RVA runtime entity through one of the supported relationship
   paths below.

| External evidence | Runtime relationship proof | Use when |
|---|---|---|
| `dt.smartscape_source.id`, DT-style `object.id`, or `dt.entity.*` | Direct ID match to `affected_entity.id` or `related_entities.*.ids` from RVA | External provider already emits Dynatrace/Smartscape IDs |
| `object.type == "CONTAINER_IMAGE"` + `container_image.digest` | `smartscapeNodes CONTAINER` by `container.image.digest`, then container → K8s workload, then same RVA `related_entities.kubernetes_workloads.names` | Image scanners such as Snyk Container, Inspector, registry scanners |
| `host.ip` | Expand `host.ip`, join to `smartscapeNodes HOST.ip`, then same RVA `related_entities.hosts.ids` | Host scanners that report IP addresses but no DT entity ID |

Report both stages separately: "same CVE found" is weaker than "same CVE found
and mapped to the same runtime workload/host/entity". If only stage 1 matches,
state that runtime relatedness was not proven.

### Direct Smartscape / DT entity ID verification

Use this path first when external findings carry DT-style entity IDs. It proves a
same-CVE match and then checks whether the external entity ID is the RVA affected
entity or appears in the RVA related entity arrays.

```dql
fetch security.events, from:now()-24h
| filter event.type == "VULNERABILITY_FINDING"
| filterOut event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
| filter isNotNull(vulnerability.references.cve)
| fieldsAdd external_entity_ids = arrayRemoveNulls(array(
      toString(dt.smartscape_source.id),
      toString(dt.entity.host),
      toString(dt.entity.process_group),
      toString(dt.entity.process_group_instance),
      toString(dt.entity.kubernetes_node),
      toString(dt.entity.kubernetes_cluster),
      object.id))
| filter arraySize(external_entity_ids) > 0
| expand external_entity_id = external_entity_ids
| expand cve = vulnerability.references.cve
| dedup {event.provider, finding.id, object.id, external_entity_id, cve}, sort:{timestamp desc}
| join [
    fetch security.events, from:now()-30m
    | filter event.type == "VULNERABILITY_STATE_REPORT_EVENT"
          OR event.type == "VULNERABILITY_OPEN_EVENT"
          OR event.type == "VULNERABILITY_MUTED_EVENT"
    | filter event.level == "ENTITY" AND vulnerability.resolution.status == "OPEN"
    | filter isNotNull(vulnerability.references.cve)
    | expand rva_cve = vulnerability.references.cve
    | dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
    | fields rva_cve,
             rva_display_id = vulnerability.display_id,
             rva_title = vulnerability.title,
             rva_entity_id = affected_entity.id,
             rva_entity_name = affected_entity.name,
             rva_hosts = related_entities.hosts.ids,
             rva_workloads = related_entities.kubernetes_workloads.ids,
             rva_clusters = related_entities.kubernetes_clusters.ids,
             rva_services = related_entities.services.ids
  ], kind:inner, on:{left[cve] == right[rva_cve]},
     fields:{rva_display_id, rva_title, rva_entity_id, rva_entity_name,
             rva_hosts, rva_workloads, rva_clusters, rva_services}
| fieldsAdd runtime_related = external_entity_id == rva_entity_id
      OR in(external_entity_id, rva_hosts)
      OR in(external_entity_id, rva_workloads)
      OR in(external_entity_id, rva_clusters)
      OR in(external_entity_id, rva_services)
| filter runtime_related == true
| summarize {
    ExternalFindings = count(),
    Providers = collectDistinct(event.provider, maxLength: 10),
    ExternalObjects = collectDistinct(object.name, maxLength: 10),
    RVAEntities = collectDistinct(rva_entity_name, maxLength: 10),
    RVADisplayIds = collectDistinct(rva_display_id, maxLength: 10),
    RVATitles = collectDistinct(rva_title, maxLength: 10)
  }, by:{cve, external_entity_id}
| sort ExternalFindings desc
```

### Host/IP verification

Use this path when the external vendor reports host IPs but not DT entity IDs.
It resolves `host.ip` to a Smartscape HOST and then requires the same host to be
present in RVA `related_entities.hosts.ids` for the same CVE.

```dql
fetch security.events, from:now()-24h
| filter event.type == "VULNERABILITY_FINDING"
| filterOut event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
| filter isNotNull(vulnerability.references.cve) AND isNotNull(host.ip)
| expand cve = vulnerability.references.cve
| expand host.ip
| fieldsAdd normalized_ip = ip(host.ip)
| join [
    smartscapeNodes HOST
    | expand ip
    | fields host_id = id, host_name = name, normalized_ip = ip
  ], kind:inner, on:{normalized_ip}, fields:{host_id, host_name}
| dedup {event.provider, finding.id, object.id, host_id, cve}, sort:{timestamp desc}
| join [
    fetch security.events, from:now()-30m
    | filter event.type == "VULNERABILITY_STATE_REPORT_EVENT"
          OR event.type == "VULNERABILITY_OPEN_EVENT"
          OR event.type == "VULNERABILITY_MUTED_EVENT"
    | filter event.level == "ENTITY" AND vulnerability.resolution.status == "OPEN"
    | filter isNotNull(vulnerability.references.cve)
    | expand rva_cve = vulnerability.references.cve
    | dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
    | fields rva_cve,
             rva_display_id = vulnerability.display_id,
             rva_title = vulnerability.title,
             rva_entity_name = affected_entity.name,
             rva_component = affected_entity.vulnerable_component.name,
             rva_hosts = related_entities.hosts.ids
  ], kind:inner, on:{left[cve] == right[rva_cve]},
     fields:{rva_display_id, rva_title, rva_entity_name, rva_component, rva_hosts}
| filter in(host_id, rva_hosts)
| summarize {
    ExternalFindings = count(),
    Providers = collectDistinct(event.provider, maxLength: 10),
    ExternalTitles = collectDistinct(coalesce(finding.title, vulnerability.title), maxLength: 10),
    RVAEntities = collectDistinct(rva_entity_name, maxLength: 10),
    RVAComponents = collectDistinct(rva_component, maxLength: 10),
    RVADisplayIds = collectDistinct(rva_display_id, maxLength: 10)
  }, by:{cve, host_id, host_name}
| sort ExternalFindings desc
```

## External container-image findings also detected by RVA on the same running K8s workload

For questions like "are external image-scanner vulnerabilities also detected by
RVA, and is the scanned image actually running in Kubernetes?", use a strict
three-way correlation:

1. external `VULNERABILITY_FINDING` rows scoped to `object.type == "CONTAINER_IMAGE"`;
2. runtime `smartscapeNodes CONTAINER` matched by `container_image.digest`;
3. open RVA rows matched by `vulnerability.references.cve` **and** the same
   Kubernetes workload name.

Do not use `vulnerability.cve.id` / `.ids`; CVEs are in
`vulnerability.references.cve`. Smartscape reference fields are arrays, so unwrap
them with `arrayFirst(...)` before joining.

```dql
fetch security.events, from:now()-7d
| filter event.type == "VULNERABILITY_FINDING"
| filterOut event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
| filter object.type == "CONTAINER_IMAGE"
| filter isNotNull(container_image.digest) AND isNotNull(vulnerability.references.cve)
| expand cve = vulnerability.references.cve
| fieldsAdd repository = coalesce(artifact.repository, container_image.repository),
            image_ref = concat(coalesce(repository, container_image.name, object.name), "@", container_image.digest),
            component_name = coalesce(software_component.name, component.name)
| dedup {event.provider, finding.id, object.id, container_image.digest, cve}, sort:{timestamp desc}
| join [
    smartscapeNodes CONTAINER
    | fields dt.container.id = id, dt.container.name = name, container.image.digest, references
    | fieldsAdd dt.k8s.workload.id = coalesce(arrayFirst(references[is_part_of.k8s_deployment]),
                                  coalesce(arrayFirst(references[is_part_of.k8s_daemonset]),
                                    coalesce(arrayFirst(references[is_part_of.k8s_cronjob]),
                                      coalesce(arrayFirst(references[is_part_of.k8s_statefulset]),
                                        coalesce(arrayFirst(references[is_part_of.k8s_job]), arrayFirst(references[is_part_of.k8s_replicaset]))))))
    | fieldsKeep dt.container.id, dt.container.name, container.image.digest, dt.k8s.workload.id
  ], kind:inner, on:{left[container_image.digest] == right[container.image.digest]},
     fields:{dt.container.id, dt.container.name, dt.k8s.workload.id}
| join [
    smartscapeNodes {K8S_DEPLOYMENT, K8S_DAEMONSET, K8S_CRONJOB, K8S_STATEFULSET, K8S_JOB, K8S_REPLICASET}
    | fields dt.k8s.workload.id = id, runtime_workload_name = name
  ], kind:inner, on:{left[dt.k8s.workload.id] == right[dt.k8s.workload.id]},
     fields:{runtime_workload_name}
| join [
    fetch security.events, from:now()-30m
    | filter event.type == "VULNERABILITY_STATE_REPORT_EVENT"
          OR event.type == "VULNERABILITY_OPEN_EVENT"
          OR event.type == "VULNERABILITY_MUTED_EVENT"
    | filter event.level == "ENTITY"
    | filter vulnerability.resolution.status == "OPEN"
    | filter isNotNull(vulnerability.references.cve)
    | expand rva_cve = vulnerability.references.cve
    | expand rva_workload_name = related_entities.kubernetes_workloads.names
    | dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
    | fields rva_cve, rva_workload_name,
             rva_display_id = vulnerability.display_id,
             rva_title = vulnerability.title,
             rva_entity_id = affected_entity.id,
             rva_entity_name = affected_entity.name,
             rva_component = affected_entity.vulnerable_component.name
  ], kind:inner, on:{left[cve] == right[rva_cve], left[runtime_workload_name] == right[rva_workload_name]},
     fields:{rva_display_id, rva_title, rva_entity_id, rva_entity_name, rva_component}
| summarize {
    ExternalFindings = count(),
    Providers = collectDistinct(event.provider, maxLength: 10),
    Products = collectDistinct(product.name, maxLength: 10),
    RiskLevels = collectDistinct(dt.security.risk.level, maxLength: 10),
    Images = collectDistinct(image_ref, maxLength: 10),
    RunningContainers = countDistinct(dt.container.id),
    RuntimeContainers = collectDistinct(dt.container.name, maxLength: 10),
    ExternalTitles = collectDistinct(coalesce(finding.title, vulnerability.title), maxLength: 10),
    ExternalComponents = collectDistinct(component_name, maxLength: 10),
    RVAEntities = countDistinct(rva_entity_id),
    RVAEntityNames = collectDistinct(rva_entity_name, maxLength: 10),
    RVAComponents = collectDistinct(rva_component, maxLength: 10),
    RVADisplayIds = collectDistinct(rva_display_id, maxLength: 10),
    RVATitles = collectDistinct(rva_title, maxLength: 10)
  }, by:{cve, runtime_workload_name}
| sort ExternalFindings desc, RunningContainers desc
| limit 50
```

## Critical external vulnerabilities newly reported in the last 7d (not in the prior 7d)

"What's genuinely new this week?" — take this period's critical external findings and anti-join
(outer join + `isNull(right…)`) against the prior 7-day period, deduped per `{object.id, vulnerability.id}`:

```dql
// This period's critical external findings
fetch security.events, from:-7d, to:now()
| filter event.type == "VULNERABILITY_FINDING"
     AND product.vendor != "Dynatrace" AND event.provider != "Dynatrace"
     AND dt.security.risk.level == "CRITICAL"
| dedup {object.id, vulnerability.id}
// Anti-join the previous 7-day window
| join kind:outer, on:{object.id, vulnerability.id}, [
    fetch security.events, from:-14d, to:-7d
    | filter event.type == "VULNERABILITY_FINDING"
         AND product.vendor != "Dynatrace" AND event.provider != "Dynatrace"
         AND dt.security.risk.level == "CRITICAL"
    | dedup {object.id, vulnerability.id}
    | fields object.id, vulnerability.id
  ]
| filter isNull(right.vulnerability.id)   // present now, absent in the prior period
| fields event.provider, product.name, dt.security.risk.level, dt.security.risk.score,
         finding.time.created, finding.title, vulnerability.id, object.name,
         component.name, repository=coalesce(artifact.repository, container_image.repository)
| sort dt.security.risk.score desc
```

> Adjust `dt.security.risk.level` (or drop it) and the window offsets for other severities / cadences.

## Cross-provider vulnerability view

To combine Dynatrace-native (canonical RVA pattern) with ingested findings using the
normalized fields `dt.security.risk.level`, `finding.id`, `finding.title`,
`object.id`, `object.name`, `object.type`, see
[all-security-events.md](all-security-events.md).

## Mapping external findings to runtime entities

External findings carry `object.*` / `container_image.*` / cloud-resource identifiers,
not Dynatrace runtime entity IDs. To map them to hosts / K8s workloads / cloud entities
via Smartscape, use the recipes in [entity-enrichment.md](../../dt-sec-contextualization/references/entity-enrichment.md).
