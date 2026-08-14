# Hunt Security Events (Detections + Vulnerabilities)

Leg 3 of the hunt: correlate IoCs through `security.events` — attacker IPs /
domains / URLs against **detections** (`DETECTION_FINDING`, `actor.*`), and CVEs
against **vulnerabilities** (Runtime Vulnerability Analytics state reports). This
is the only surface where RAP and external security tools record attacker IPs,
and the only surface that maps CVEs to affected entities.

## Ownership boundary — read first

`security.events` field semantics, the data model, event families, provider
scoping, and the **generic** summarization idioms are owned by **dt-sec-insights**
(one home per pattern). This file does **not** re-teach them. Load
`dt-sec-insights` and reference:

- `references/data-model.md` — event families, entity namespaces, RVA vs
  `*_FINDING` field split.
- `references/detections.md` — canonical IoC-filter clauses (IP list, domain/URL
  list, MITRE technique) and the full-record listing queries (drill-down).
- `references/vulnerabilities-dynatrace.md` — RVA snapshot pipeline, CVE filtering,
  and the full-record listing (drill-down).
- `references/common-patterns.md` **§15 Default Summarization Recipe** and
  **§17 entity-identifier preservation** — the generic summarize guidance this
  file specializes for the hunt.

**What lives here (and only here):** the hunt-specific, IoC-scoped
**summarize-first rollups** tuned for exposure scoring and cross-evidence
correlation — the family-split collector sets, correlation join keys, and the
drill-down pointers. This is the narrow carve-out to `SKILL.md` Best Practice #10.

## Summarize-first (hunt output contract)

Return an aggregated rollup — **one row per affected entity** — collecting entity
identifiers, matched observables/CVEs, counts, and first/last-seen timestamps. Do
**not** return raw per-finding rows by default. Fetch full records only via the
drill-down (see below) when a single finding's raw context is needed.
Summarize-first ≠ truncation: the rollup keeps every affected entity and matched
IoC, so the exposure report stays complete.

## Family-split collectors (mandatory)

Entity namespaces differ by event family — never apply one collector list to both:

| Family | Event | Entity namespaces (populate) | Null here |
|---|---|---|---|
| Cross-provider finding | `DETECTION_FINDING` | `object.*`, `dt.smartscape_source.id`, `dt.source_entity`, `dt.entity.*`, `k8s.*`, `aws.resource.id` / `azure.resource.id` | `affected_entity.*`, `related_entities.*` |
| RVA state report | `VULNERABILITY_STATE_REPORT_EVENT` | `affected_entity.*`, `related_entities.*.ids`, `affected_entity.reachable_data_assets.ids` | generic `k8s.*` / `dt.entity.*` / `dt.smartscape*` |

## Detection hunt rollup (IPs / domains / URLs)

IoC-filter clauses are owned by `dt-sec-insights` `detections.md`:
- IPs → `isNotNull(actor.ips)` + `expand actor.ips` + `in(ip(actor.ips), array(toIp("<ip1>"), toIp("<ip2>")))` — `actor.ips` is `ipAddress[]`; expand first so each IP filters independently (canonical pattern from `detections.md` BP #10).
- Domains/URLs → `lower(url.domain)` / `lower(url.full)` / `lower(server.address)`
  clauses (see `detections.md § Filter detections by domain/URL/URI IoC list`).

Default window: `from:now()-2h`; widen to `from:now()-24h` only if zero rows.

```dql-template
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter isNotNull(actor.ips)
| expand actor.ips
| filter in(ip(actor.ips), array(toIp("<ip1>"), toIp("<ip2>")))
| summarize by:{object.id, object.name, davis_risk=dt.security.risk.level},
  {
    detectionsNum = countDistinctExact(finding.id),
    minTime       = takeMin(finding.time.created),
    maxTime       = takeMax(finding.time.created),
    detections    = collectDistinct(finding.title, maxLength:100),
    actor_ips     = arrayDistinct(arrayRemoveNulls(collectArray(actor.ips, expand:true, maxLength:100))),
    actor_fqdns   = arrayDistinct(arrayRemoveNulls(collectArray(actor.fqdns, expand:true, maxLength:100))),
    target_entities    = collectDistinct(dt.source_entity, maxLength:100),
    smartscape_sources = collectDistinct(dt.smartscape_source.id, maxLength:100),
    dt_entity_hosts    = collectDistinct(dt.entity.host, maxLength:100),
    k8s_namespaces     = collectDistinct(k8s.namespace.name, maxLength:100),
    k8s_workloads      = collectDistinct(k8s.workload.name, maxLength:100),
    k8s_pods           = collectDistinct(k8s.pod.name, maxLength:100),
    aws_resource_ids   = collectDistinct(aws.resource.id, maxLength:100),
    azure_resource_ids = collectDistinct(azure.resource.id, maxLength:100)
  }
| sort detectionsNum desc
| limit 25
```

Swap the IP filter for the domain/URL filter when hunting those IoC types. Keep
the `by:` keys and collectors; only the filter clause changes.

## Vulnerability hunt rollup (CVEs)

CVE filtering and the RVA snapshot pipeline (bucket, three-event-type union,
`event.level == "ENTITY"`, per-`{vulnerability.display_id, affected_entity.id}` dedup,
`OPEN` resolution) are owned by `dt-sec-insights` `vulnerabilities-dynatrace.md`. The
hunt adds the CVE-list scope `in(vulnerability.references.cve, array("<cve1>", "<cve2>"))`
and the `affected_entity`-keyed rollup.

```dql-template
fetch security.events, from:now()-30m
| filter dt.system.bucket == "default_securityevents_builtin"
| filter in(event.type, {"VULNERABILITY_STATE_REPORT_EVENT",
                          "VULNERABILITY_STATUS_CHANGE_EVENT",
                          "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
| filter event.level == "ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| filter vulnerability.resolution.status == "OPEN"
| filter in(vulnerability.references.cve, array("<cve1>", "<cve2>"))
| summarize by:{dt.source_entity=affected_entity.id, affected_entity.name,
                davis_risk=vulnerability.davis_assessment.level},
  {
    vulnerabilitiesCount = countDistinctExact(vulnerability.id),
    vulnerabilities = collectDistinct(vulnerability.title, maxLength:100),
    CVEs = arrayDistinct(arrayRemoveNulls(collectArray(vulnerability.references.cve, expand:true, maxLength:100))),
    vulnerable_components      = collectDistinct(affected_entity.vulnerable_component.package_name, maxLength:100),
    vulnerable_component_names = collectDistinct(affected_entity.vulnerable_component.name, maxLength:100),
    kubernetes_clusters = arrayDistinct(arrayRemoveNulls(collectArray(related_entities.kubernetes_clusters.ids, expand:true, maxLength:100))),
    hosts               = arrayDistinct(arrayRemoveNulls(collectArray(related_entities.hosts.ids, expand:true, maxLength:100))),
    services            = arrayDistinct(arrayRemoveNulls(collectArray(related_entities.services.ids, expand:true, maxLength:100))),
    reachable_data_assets = arrayDistinct(arrayRemoveNulls(collectArray(affected_entity.reachable_data_assets.ids, expand:true, maxLength:100)))
  }
| sort vulnerabilitiesCount desc
| limit 25
```

`maxLength:` on every `collect*` call is required to bound row size on high-fanout
entities. Omit any collector class with no values in your environment (they are
harmlessly null when absent, e.g. `k8s.*` outside Kubernetes, `reachable_data_assets`
when Davis data-flow is not configured).

## Correlation join keys (feed scoring + contextualization)

Call these out in the hunt output so `dt-sec-contextualization`
`correlation-and-coverage.md` and `exposure-scoring.md` can match entities across
legs:

| From leg | Key | Joins to |
|---|---|---|
| Detection | `object.id` / `dt.smartscape_source.id` | log/span `dt.smartscape_source.id` (3rd-gen) |
| Detection | `dt.source_entity` (`PROCESS_GROUP-*`) | RVA `affected_entity.id`, log/span `dt.process_group.id` |
| Vulnerability | `affected_entity.id` (`PROCESS_GROUP-*`) | detection `dt.source_entity`, log/span `dt.process_group.id` |
| Vulnerability | `related_entities.hosts.ids` / `.services.ids` | Smartscape host/service topology |

## Drill-down (full records)

When a single finding's raw record is needed (e.g. inspecting one detection's
`actor.*` context, or one vulnerability's full field set), do **not** re-author a
listing query here — use the owned full-record queries in `dt-sec-insights`:

- Detections → `detections.md` raw listing (`| fields ... | limit N`), scoped by
  the same IoC filter.
- Vulnerabilities → `vulnerabilities-dynatrace.md` raw state-report listing
  (`| fieldsKeep timestamp, "affected_entity*", "related_entities*", ... `).

## Default Timeframe and Widening

- Detections default `from:now()-2h`; widen to `from:now()-24h` only on zero rows.
- Vulnerabilities are a state snapshot — `from:now()-30m` captures the latest
  reported state per entity; no widening needed for coverage.
- `FETCH_EXEC_TIME_LIMIT` on a leg = INCONCLUSIVE, not no-match. Record it and
  continue. Follow `timeframe-gating.md` for anchored windows on IoCs derived
  from timestamped events.

## Field-name notes

- `aws.arn` is not a `security.events` field — use `aws.resource.id`
  (and `azure.resource.id`). Deep hyperscaler fields belong to the cloud skills.
- `actor.fqdns` is the **attacker** FQDN array (parallel to `actor.ips`) — collect
  it. `host.fqdn` is a different field (the affected host's own FQDN), not an
  attacker observable.
- `dt.source_entity` is a legacy/scan-era identifier on findings — collect it as a
  join key, but prefer `object.id` / `dt.smartscape_source.id` as the primary
  detection entity key.
