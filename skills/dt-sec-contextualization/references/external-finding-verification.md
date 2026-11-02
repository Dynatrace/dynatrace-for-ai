# External Finding Verification — are external vulnerability findings confirmed by Dynatrace RVA on the same runtime entity?

This file reads RVA state only to verify a given set of external `VULNERABILITY_FINDING`
rows against runtime. RVA counts, rankings, lifecycle, and the external finding queries
themselves stay in `dt-sec-insights` (`vulnerabilities-dynatrace.md`,
`vulnerabilities-external.md`). Identity resolution recipes live in
[identity-mapping.md](identity-mapping.md); entity enrichment in
[entity-enrichment.md](entity-enrichment.md).

## Contents

- [Two-stage verification](#two-stage-verification)
- [Direct Smartscape id verification](#direct-smartscape-id-verification)
- [Host/IP verification](#hostip-verification)
- [Container-image findings also detected by RVA on the same K8s workload](#container-image-findings-also-detected-by-rva-on-the-same-k8s-workload)

## Two-stage verification

Use this when the user asks whether external vendor vulnerability
findings are confirmed by Dynatrace Runtime Vulnerability Analytics (RVA), for
example: "does this external image finding run in my K8s environment and match
an RVA vulnerability?" or "does a Qualys host finding correspond to a runtime
vulnerability on the same host?"

Verification is a two-stage process:

1. **Same vulnerability:** match external `VULNERABILITY_FINDING` rows to open RVA
   rows by CVE using `vulnerability.references.cve` on both sides. Expand the CVE
   array (on the RVA side only after the per-vulnerability/entity `dedup`, which
   would otherwise collapse each pair to one CVE). Do not use
   `vulnerability.cve.id` / `.ids`.

   The RVA side of every query below is the canonical snapshot: the three RVA
   entity-level event types (`VULNERABILITY_STATE_REPORT_EVENT`,
   `VULNERABILITY_STATUS_CHANGE_EVENT`, `VULNERABILITY_TRACKING_LINK_CHANGE_EVENT`),
   deduplicated to the latest event per `(vulnerability.display_id,
   affected_entity.id)`, and only then filtered to open, non-muted state. RVA state
   is therefore the latest open, non-muted state per vulnerability/entity pair.
2. **Related runtime entity/resource/artifact:** prove that the external object is
   related to an RVA runtime entity through one of the supported relationship
   paths below.

| External evidence | Runtime relationship proof | Use when |
|---|---|---|
| `dt.smartscape_source.id`, `dt.smartscape.host`, or DT-style `object.id` | Direct ID match to `affected_entity.id` or `related_entities.*.ids` from RVA | External provider already emits Dynatrace/Smartscape IDs |
| `object.type == "CONTAINER_IMAGE"` + `container_image.digest` | `smartscapeNodes CONTAINER` by `container.image.digest`, then container → K8s workload ([identity-mapping.md Path 2](identity-mapping.md#path-2--container-image-digest--container--workloadhost)), then same RVA `related_entities.kubernetes_workloads.ids` (workload `id_classic`, not the name) | Image scanners such as Snyk Container, Inspector, registry scanners |
| `host.ip` | Expand `host.ip`, join to `smartscapeNodes HOST.ip`, then same RVA `related_entities.hosts.ids` | Host scanners that report IP addresses but no DT entity ID |

Report both stages separately: "same CVE found" is weaker than "same CVE found
and mapped to the same runtime workload/host/entity". If only stage 1 matches,
state that runtime relatedness was not proven. Give both numbers in the answer even when the
runtime stage returns no rows: the CVE-only match count first, then the count that also maps to
the same runtime entity.

## Direct Smartscape id verification

Use this path first when external findings carry Smartscape IDs. It proves a
same-CVE match and then checks whether the external entity ID is the RVA affected
entity or appears in the RVA related entity arrays.

RVA stores **classic (2nd-gen)** entity ids, while `dt.smartscape_source.id` and
`dt.smartscape.host` are **3rd-gen** Smartscape ids; casting one to a string does not convert it.
The query therefore resolves both through `smartscapeNodes "*"` to `id_classic` before comparing,
and keeps `object.id` as-is (a DT-style `object.id` is already classic). If `object.id` holds a
3rd-gen id instead, add a third `lookup` on `object.id` the same way. External findings are counted
by distinct `provider|finding.id|object.id`, so the CVE and entity fan-out of the join does not
inflate `ExternalFindings`.

```dql
fetch security.events, from:now()-24h
| filter event.type == "VULNERABILITY_FINDING"
| filterOut event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
| filter isNotNull(vulnerability.references.cve)
| dedup {event.provider, finding.id, object.id}, sort:{timestamp desc}
| lookup [
    smartscapeNodes "*" | fields id, id_classic
  ], sourceField:dt.smartscape_source.id, lookupField:id, fields:{source_classic_id = id_classic}
| lookup [
    smartscapeNodes "*" | fields id, id_classic
  ], sourceField:dt.smartscape.host, lookupField:id, fields:{host_classic_id = id_classic}
| fieldsAdd external_entity_ids = arrayRemoveNulls(array(source_classic_id, host_classic_id, object.id)),
            external_key = concat(coalesce(toString(event.provider), ""), "|",
                                  coalesce(toString(finding.id), ""), "|",
                                  coalesce(toString(object.id), ""))
| filter arraySize(external_entity_ids) > 0
| expand external_entity_id = external_entity_ids
| expand cve = vulnerability.references.cve
| join [
    fetch security.events, from:now()-30m
    | filter event.provider == "Dynatrace"
    | filter in(event.type, {"VULNERABILITY_STATE_REPORT_EVENT",
                             "VULNERABILITY_STATUS_CHANGE_EVENT",
                             "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
          AND event.level == "ENTITY"
    | dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
    | filter vulnerability.resolution.status == "OPEN" AND vulnerability.mute.status != "MUTED"
    | filter isNotNull(vulnerability.references.cve)
    | expand rva_cve = vulnerability.references.cve
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
    ExternalFindings = countDistinctExact(external_key),
    Providers = collectDistinct(event.provider, maxLength: 10),
    ExternalObjects = collectDistinct(object.name, maxLength: 10),
    RVAEntities = collectDistinct(rva_entity_name, maxLength: 10),
    RVADisplayIds = collectDistinct(rva_display_id, maxLength: 10),
    RVATitles = collectDistinct(rva_title, maxLength: 10)
  }, by:{cve, external_entity_id}
| sort ExternalFindings desc
```

## Host/IP verification

Use this path when the external vendor reports host IPs but not DT entity IDs.
It resolves `host.ip` to a Smartscape HOST and then requires the same host to be
present in RVA `related_entities.hosts.ids` for the same CVE. Both sides compare **classic**
ids: the HOST node contributes `id_classic`, and the RVA side merges a directly affected
HOST / KUBERNETES_NODE into the host array first (it is not repeated in `related_entities.hosts.ids`;
see [rva-entity-resolution.md § Host](rva-entity-resolution.md#host)). `ExternalFindings` counts distinct
`provider|finding.id|object.id`, not joined rows.

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
    | fields host_id = id_classic, host_name = name, normalized_ip = ip
  ], kind:inner, on:{normalized_ip}, fields:{host_id, host_name}
| dedup {event.provider, finding.id, object.id, host_id, cve}, sort:{timestamp desc}
| fieldsAdd external_key = concat(coalesce(toString(event.provider), ""), "|",
                                  coalesce(toString(finding.id), ""), "|",
                                  coalesce(toString(object.id), ""))
| join [
    fetch security.events, from:now()-30m
    | filter event.provider == "Dynatrace"
    | filter in(event.type, {"VULNERABILITY_STATE_REPORT_EVENT",
                             "VULNERABILITY_STATUS_CHANGE_EVENT",
                             "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
          AND event.level == "ENTITY"
    | dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
    | filter vulnerability.resolution.status == "OPEN" AND vulnerability.mute.status != "MUTED"
    | filter isNotNull(vulnerability.references.cve)
    | fieldsAdd rva_hosts = if(in(affected_entity.type, {"HOST", "KUBERNETES_NODE"}),
        arrayConcat(array(affected_entity.id), related_entities.hosts.ids),
        else: related_entities.hosts.ids)
    | expand rva_cve = vulnerability.references.cve
    | fields rva_cve, rva_hosts,
             rva_display_id = vulnerability.display_id,
             rva_title = vulnerability.title,
             rva_entity_name = affected_entity.name,
             rva_component = affected_entity.vulnerable_component.name
  ], kind:inner, on:{left[cve] == right[rva_cve]},
     fields:{rva_display_id, rva_title, rva_entity_name, rva_component, rva_hosts}
| filter in(host_id, rva_hosts)
| summarize {
    ExternalFindings = countDistinctExact(external_key),
    Providers = collectDistinct(event.provider, maxLength: 10),
    ExternalTitles = collectDistinct(coalesce(finding.title, vulnerability.title), maxLength: 10),
    RVAEntities = collectDistinct(rva_entity_name, maxLength: 10),
    RVAComponents = collectDistinct(rva_component, maxLength: 10),
    RVADisplayIds = collectDistinct(rva_display_id, maxLength: 10)
  }, by:{cve, host_id, host_name}
| sort ExternalFindings desc
```

## Container-image findings also detected by RVA on the same K8s workload

For questions like "are external image-scanner vulnerabilities also detected by
RVA, and is the scanned image actually running in Kubernetes?", use a strict
three-way correlation:

1. external `VULNERABILITY_FINDING` rows scoped to `object.type == "CONTAINER_IMAGE"`;
2. runtime `smartscapeNodes CONTAINER` matched by `container_image.digest`;
3. open RVA rows matched by `vulnerability.references.cve` **and** the same
   Kubernetes workload **classic id**: the resolved workload's `id_classic` against
   `related_entities.kubernetes_workloads.ids`. Never match on the workload name; two namespaces
   or clusters can each run a workload called `backend`, so a name match can mark a finding
   runtime-verified from the other one's RVA row. Names are for display only.

Do not use `vulnerability.cve.id` / `.ids`; CVEs are in
`vulnerability.references.cve`. Smartscape reference fields are arrays, so unwrap
them with `arrayFirst(...)` before joining. The digest → CONTAINER → workload
resolution and the registry-independence of the digest match are described in
[identity-mapping.md Path 2](identity-mapping.md#path-2--container-image-digest--container--workloadhost);
the query below applies that path and then adds the RVA stage. `ExternalFindings` counts distinct
`provider|finding.id|object.id`; `RunningContainers` and `RVAEntities` are separate metrics, so the
fan-out over containers and RVA records does not inflate it.

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
| fieldsAdd external_key = concat(coalesce(toString(event.provider), ""), "|",
                                  coalesce(toString(finding.id), ""), "|",
                                  coalesce(toString(object.id), ""))
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
    | fields dt.k8s.workload.id = id, runtime_workload_id = id_classic, runtime_workload_name = name
  ], kind:inner, on:{left[dt.k8s.workload.id] == right[dt.k8s.workload.id]},
     fields:{runtime_workload_id, runtime_workload_name}
| join [
    fetch security.events, from:now()-30m
    | filter event.provider == "Dynatrace"
    | filter in(event.type, {"VULNERABILITY_STATE_REPORT_EVENT",
                             "VULNERABILITY_STATUS_CHANGE_EVENT",
                             "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
          AND event.level == "ENTITY"
    | dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
    | filter vulnerability.resolution.status == "OPEN" AND vulnerability.mute.status != "MUTED"
    | filter isNotNull(vulnerability.references.cve)
    | expand rva_cve = vulnerability.references.cve
    | expand rva_workload_id = related_entities.kubernetes_workloads.ids
    | fields rva_cve, rva_workload_id,
             rva_display_id = vulnerability.display_id,
             rva_title = vulnerability.title,
             rva_entity_id = affected_entity.id,
             rva_entity_name = affected_entity.name,
             rva_component = affected_entity.vulnerable_component.name
  ], kind:inner, on:{left[cve] == right[rva_cve], left[runtime_workload_id] == right[rva_workload_id]},
     fields:{rva_display_id, rva_title, rva_entity_id, rva_entity_name, rva_component}
| summarize {
    ExternalFindings = countDistinctExact(external_key),
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
  }, by:{cve, runtime_workload_id, runtime_workload_name}
| sort ExternalFindings desc, RunningContainers desc
| limit 50
```
