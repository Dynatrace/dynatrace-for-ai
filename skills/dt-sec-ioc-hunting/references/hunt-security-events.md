# Hunt Security Events (Detections + Vulnerabilities)

Leg 3 of the hunt: correlate IoCs through `security.events` — attacker IPs /
domains / URLs against **detections** (`DETECTION_FINDING`, `actor.*`), and CVEs
against **vulnerabilities** (Runtime Vulnerability Analytics state reports). This
is the only surface where RAP and external security tools record attacker IPs,
and the only surface that maps CVEs to affected entities.
IoCs come either from a literal list (the rollups below, after `ioc-intake.md`) or from
ingested `THREAT_REPORT` events (§ Report-driven correlation, join form).

## Contents

- [Ownership boundary — read first](#ownership-boundary--read-first)
- [Summarize-first (hunt output contract)](#summarize-first-hunt-output-contract)
- [Family-split collectors (mandatory)](#family-split-collectors-mandatory)
- [Detection hunt rollup (IPs / domains / URLs)](#detection-hunt-rollup-ips--domains--urls)
  - [Domain / URL variant](#domain--url-variant)
  - [MITRE technique variant](#mitre-technique-variant)
- [Vulnerability hunt rollup (CVEs)](#vulnerability-hunt-rollup-cves)
- [Report-driven correlation (join form)](#report-driven-correlation-join-form)
  - [Report CVEs → vulnerabilities](#report-cves--vulnerabilities)
  - [Report IPs → detections](#report-ips--detections)
  - [Report MITRE techniques → detections](#report-mitre-techniques--detections)
- [Correlation join keys (feed scoring + contextualization)](#correlation-join-keys-feed-scoring--contextualization)
- [Drill-down (full records)](#drill-down-full-records)
- [Default Timeframe and Widening](#default-timeframe-and-widening)
- [Field-name notes](#field-name-notes)

## Ownership boundary — read first

`security.events` field semantics, the data model, event families, provider
scoping, and the **generic** summarization idioms are owned by **dt-sec-insights**
(one home per pattern). This file does **not** re-teach them. Load
`dt-sec-insights` and reference:

- `references/data-model.md` — event families, entity namespaces, RVA vs
  `*_FINDING` field split.
- `references/detections.md` — detection retrieval, provider routing, and the MITRE
  technique filter. It does **not** own the IoC-list filters (IP, domain/URL): those live
  in this file (§ Detection hunt rollup and § Drill-down).
- `references/vulnerabilities-dynatrace.md` — RVA snapshot pipeline, CVE filtering,
  and the full-record listing (drill-down).
- `references/common-patterns.md` **§15 Default Summarization Recipe** and
  **§17 entity-identifier preservation** — the generic summarize guidance this
  file specializes for the hunt.

**What lives here (and only here):** the hunt-specific, IoC-scoped
**summarize-first rollups** tuned for exposure scoring and cross-evidence
correlation — the IoC-list filter clauses (IP, domain/URL), the family-split collector
sets, correlation join keys, and the IoC-scoped drill-down listings. This is the narrow
carve-out to `SKILL.md` Best Practice #10. Behavior-based (non-IoC) detection
investigation lives in `detection-investigation.md`.

## Summarize-first (hunt output contract)

Return an aggregated rollup — **one row per affected entity** — collecting entity
identifiers, matched observables/CVEs, counts, and first/last-seen timestamps. Do
**not** return raw per-finding rows by default. Fetch full records only via the
drill-down (see below) when a single finding's raw context is needed.
Summarize-first ≠ truncation: the rollup keeps every affected entity and matched
IoC, so the exposure report stays complete. If a rollup returns exactly its `limit`, treat it
as possibly truncated: re-run with a higher limit (or split the IoC chunk) before reporting
the leg as complete, and state the truncation otherwise.

## Family-split collectors (mandatory)

Entity namespaces differ by event family — never apply one collector list to both:

| Family | Event | Entity namespaces (populate) | Null here |
|---|---|---|---|
| Cross-provider finding | `DETECTION_FINDING` | `object.*`, `dt.smartscape_source.id`, `dt.process_group.id`, `dt.smartscape.*`, `k8s.*`, `aws.resource.id` / `azure.resource.id` | `affected_entity.*`, `related_entities.*` |
| RVA state report | `VULNERABILITY_STATE_REPORT_EVENT` | `affected_entity.*`, `related_entities.*.ids`, `affected_entity.reachable_data_assets.ids` | generic `k8s.*` / `dt.smartscape*` |

## Detection hunt rollup (IPs / domains / URLs)

The IoC-filter clauses are owned by this file:
- IPs → `isNotNull(actor.ips)` + `in(iCollectArray(ip(actor.ips[])), array(toIp("<ip1>"), toIp("<ip2>")))` — `actor.ips` is an array (string or ip elements, tenant-dependent); `actor.ips[]` iterates elements, `ip()` types each, `iCollectArray` reassembles, `in(array,array)` checks intersection without an expand step.
- Domains/URLs → `contains(url.full|url.domain|server.address, …, caseSensitive:false)` / `contains(url.full|url.path, …)`
  clauses (never `lower()` on the field) (see § Domain / URL variant below).

Default window: `from:now()-2h`. On zero rows, re-run automatically at `from:now()-24h` (no approval needed) and report both windows; going beyond 24h needs approval.

**Placeholders** (substitute before running; the template is executable afterwards):

- `<ip1>`, `<ip2>`: normalized public IPs from `ioc-intake.md`, for example `192.0.2.11`. Each IP is one
  `toIp("<ipN>")` element in the single `in(...)` clause, so the filter does not grow per IP; for very
  large lists split into chunks and merge by `object.id`.
- Window: `from:now()-2h` is the detection default; on zero rows re-run at `from:now()-24h` (see Default
  Timeframe and Widening), or use the anchored window from `timeframe-gating.md`.

```dql-template
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter isNotNull(actor.ips)
| filter in(iCollectArray(ip(actor.ips[])), array(toIp("<ip1>"), toIp("<ip2>")))
| summarize by:{object.id, object.name, davis_risk=dt.security.risk.level},
  {
    detectionsNum = countDistinctExact(finding.id),
    minTime       = takeMin(finding.time.created),
    maxTime       = takeMax(finding.time.created),
    detections    = collectDistinct(finding.title, maxLength:100),
    actor_ips     = arrayRemoveNulls(collectDistinct(actor.ips, expand:true, maxLength:100)),
    actor_fqdns   = arrayRemoveNulls(collectDistinct(actor.fqdns, expand:true, maxLength:100)),
    process_groups     = collectDistinct(dt.process_group.id, maxLength:100),
    smartscape_sources = collectDistinct(dt.smartscape_source.id, maxLength:100),
    smartscape_hosts   = collectDistinct(dt.smartscape.host, maxLength:100),
    k8s_namespaces     = collectDistinct(k8s.namespace.name, maxLength:100),
    k8s_workloads      = collectDistinct(k8s.workload.name, maxLength:100),
    k8s_pods           = collectDistinct(k8s.pod.name, maxLength:100),
    aws_resource_ids   = collectDistinct(aws.resource.id, maxLength:100),
    azure_resource_ids = collectDistinct(azure.resource.id, maxLength:100)
  }
| sort detectionsNum desc
| limit 200
```

### Domain / URL variant

Use this template for Domain and URL IoCs. It is the same rollup with a domain/URL filter and a
`Matched observables` attribution so the exposure report can say which IoC matched. Fill
`Domains` and `URLs`; omit the class with no values (and its `matched*` line, using
`Matched observables = matchedDomains` or `= matchedURLs` directly when only one class
remains). `host.fqdn` is the affected host's own FQDN, not an attacker observable, so it is
not part of the hunt filter. Domains are matched case-insensitively and as substrings of
`url.full`; URL/path IoCs are matched as-is.

Not every provider populates every URL field, so the filter is a broad OR across the fields that may
carry the evidence:

| Field | Notes |
|---|---|
| `url.full` | Full URL; provider-dependent. RAP findings never carry it |
| `url.path` | HTTP path of the request; provider-dependent. RAP findings never carry it — RAP's `entry_point.url.path` is the victim endpoint the attacker hit, not an attacker indicator, so it is deliberately not matched in IoC hunts |
| `url.domain` | Domain component of the URL; provider-dependent |
| `server.address` | Target server domain/hostname; provider-dependent |

For external providers, headers such as `http.request.header.Host` may exist only in `dt.raw_data` — if the
fields above are null, `parse dt.raw_data, "JSON:raw"`.

**Safety:** DQL-escape IoC values before inserting them into string literals (`\` → `\\`, `"` → `\"`); see
`ioc-intake.md` § URL Cleaning step 7.

**Casing:** domains are case-insensitive — `contains(..., caseSensitive:false)` ignores case, so apply no
`lower()` to the fields (it would defeat the index). URL/path IoCs are matched as-is (paths can be case-sensitive).

**Placeholders** (substitute before running; the template is executable afterwards):

- `<domain1>`, `<domain2>`: normalized lowercase domains and hostnames from `ioc-intake.md`, for
  example `example.test`. One element each in `Domains`; matched case-insensitively against `url.full`,
  `url.domain`, and `server.address`.
- `<url1>`: cleaned, DQL-escaped URL or path from `ioc-intake.md`, for example `/admin/login.php`. One
  element in `URLs` per URL; matched against `url.full` and `url.path`.
- Window: as in the IP template above (`from:now()-2h`, then `now()-24h` on zero rows).
- Omit a class with no values together with its array and its `matched*` line, as described above.

```dql-template
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| fieldsAdd Domains = array("<domain1>", "<domain2>"),
            URLs    = array("<url1>")
| fieldsAdd matchedDomains = arrayRemoveNulls(iCollectArray(
    if(contains(url.full, Domains[], caseSensitive:false)
       OR contains(url.domain, Domains[], caseSensitive:false)
       OR contains(server.address, Domains[], caseSensitive:false),
       Domains[]
    )))
| fieldsAdd matchedURLs = arrayRemoveNulls(iCollectArray(
    if(contains(url.full, URLs[]) OR contains(url.path, URLs[]),
       URLs[]
    )))
| fieldsAdd `Matched observables` = arrayConcat(matchedDomains, matchedURLs)
| filter isNotNull(`Matched observables`[0])
| summarize by:{object.id, object.name, davis_risk=dt.security.risk.level},
  {
    detectionsNum = countDistinctExact(finding.id),
    minTime       = takeMin(finding.time.created),
    maxTime       = takeMax(finding.time.created),
    matched_observables = arrayRemoveNulls(collectDistinct(`Matched observables`, expand:true, maxLength:100)),
    detections    = collectDistinct(finding.title, maxLength:100),
    actor_ips     = arrayRemoveNulls(collectDistinct(actor.ips, expand:true, maxLength:100)),
    actor_fqdns   = arrayRemoveNulls(collectDistinct(actor.fqdns, expand:true, maxLength:100)),
    process_groups     = collectDistinct(dt.process_group.id, maxLength:100),
    smartscape_sources = collectDistinct(dt.smartscape_source.id, maxLength:100),
    smartscape_hosts   = collectDistinct(dt.smartscape.host, maxLength:100),
    k8s_namespaces     = collectDistinct(k8s.namespace.name, maxLength:100),
    k8s_workloads      = collectDistinct(k8s.workload.name, maxLength:100),
    k8s_pods           = collectDistinct(k8s.pod.name, maxLength:100),
    aws_resource_ids   = collectDistinct(aws.resource.id, maxLength:100),
    azure_resource_ids = collectDistinct(azure.resource.id, maxLength:100)
  }
| sort detectionsNum desc
| limit 200
```

When both IP and domain/URL IoCs are retained, run the IP template and this template as two
queries and merge by `object.id` outside DQL; do not OR the filters into one query.

### MITRE technique variant

For user-supplied techniques (a report's TTPs, or a pasted list), hunt the Automated Detections rules
that carry MITRE tags. Only `event.provider == "Dynatrace Automated Detections"` populates
`threat.attack.*`, so this leg does not see RAP or external detections. Sub-technique IDs
(`T1059.001`) live in their own array: `threat.attack.technique.ids` never matches them, so the filter
checks both arrays with the same ID list.

**Placeholders** (substitute before running; the template is executable afterwards):

- `<tech1>`, `<tech2>`: technique and sub-technique IDs from `ioc-intake.md`, upper case, exactly as
  given (`T1190`, `T1059.001`). Put every ID, parent or sub-technique, in the one `array(...)`; each
  array is matched against both fields. A parent ID does not match its sub-techniques: to hunt a
  parent plus all its sub-techniques, use the `startsWith` filter in `dt-sec-insights` `detections.md`
  (§ Filter detections by technique) in place of the `in(...)` line.
- Window: `from:now()-2h` is the detection default; on zero rows re-run at `from:now()-24h` (same rule
  as the rollup above) and report both windows.

```dql-template
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING" AND event.provider == "Dynatrace Automated Detections"
| filter in(threat.attack.technique.ids, array("<tech1>", "<tech2>"))
      OR in(threat.attack.subtechnique.ids, array("<tech1>", "<tech2>"))
| summarize by:{object.id, object.name, davis_risk=dt.security.risk.level},
  {
    detectionsNum = countDistinctExact(finding.id),
    minTime       = takeMin(finding.time.created),
    maxTime       = takeMax(finding.time.created),
    detections    = collectDistinct(finding.title, maxLength:100),
    techniques    = arrayRemoveNulls(collectDistinct(threat.attack.technique.ids, expand:true, maxLength:100)),
    subtechniques = arrayRemoveNulls(collectDistinct(threat.attack.subtechnique.ids, expand:true, maxLength:100)),
    process_groups     = collectDistinct(dt.process_group.id, maxLength:100),
    smartscape_sources = collectDistinct(dt.smartscape_source.id, maxLength:100)
  }
| sort detectionsNum desc
| limit 200
```

A zero result can mean the tenant has no MITRE-tagged Automated Detections rules rather than no
activity: say so, and point to the untagged-rules audit in `dt-sec-insights` `detections.md`.

## Vulnerability hunt rollup (CVEs)

CVE filtering and the RVA snapshot pipeline (provider scope `event.provider == "Dynatrace"`,
three-event-type union, `event.level == "ENTITY"`, per-`{vulnerability.display_id,
affected_entity.id}` dedup, `OPEN` resolution) are owned by `dt-sec-insights`
`vulnerabilities-dynatrace.md`. The hunt adds the CVE-list scope
`in(vulnerability.references.cve, array("<cve1>", "<cve2>"))` and the
`affected_entity`-keyed rollup.

Scope with `event.provider`, **never** a default `dt.system.bucket` filter: security events land in the
default bucket `default_security` (the name varies per tenant), but users can route them to any custom bucket, and a
wrong bucket silently returns zero rows after scanning ~1 record — a false "no CVE match". Filter by bucket only when the user explicitly names one.

**Placeholders** (substitute before running; the template is executable afterwards):

- `<cve1>`, `<cve2>`: CVE identifiers from `ioc-intake.md`, upper case, for example `CVE-2021-44228`.
  Each is one element of the single `in(vulnerability.references.cve, array(...))` clause, so the
  filter does not grow per CVE; split very large lists into chunks and merge by `affected_entity.id`.
- Window: `from:now()-30m` is deliberate. The RVA state report is a snapshot, so 30m already holds the
  latest state per entity; do not widen it.

```dql-template
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type, {"VULNERABILITY_STATE_REPORT_EVENT",
                          "VULNERABILITY_STATUS_CHANGE_EVENT",
                          "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
| filter event.level == "ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| filter vulnerability.resolution.status == "OPEN"
| filter in(vulnerability.references.cve, array("<cve1>", "<cve2>"))
| summarize by:{affected_entity.id, affected_entity.name,
                davis_risk=vulnerability.davis_assessment.level},
  {
    vulnerabilitiesCount = countDistinctExact(vulnerability.id),
    vulnerabilities = collectDistinct(vulnerability.title, maxLength:100),
    CVEs = arrayRemoveNulls(collectDistinct(vulnerability.references.cve, expand:true, maxLength:100)),
    vulnerable_components      = collectDistinct(affected_entity.vulnerable_component.package_name, maxLength:100),
    vulnerable_component_names = collectDistinct(affected_entity.vulnerable_component.name, maxLength:100),
    kubernetes_clusters = arrayRemoveNulls(collectDistinct(related_entities.kubernetes_clusters.ids, expand:true, maxLength:100)),
    hosts               = arrayRemoveNulls(collectDistinct(related_entities.hosts.ids, expand:true, maxLength:100)),
    services            = arrayRemoveNulls(collectDistinct(related_entities.services.ids, expand:true, maxLength:100)),
    reachable_data_assets = arrayRemoveNulls(collectDistinct(affected_entity.reachable_data_assets.ids, expand:true, maxLength:100))
  }
| sort vulnerabilitiesCount desc
| limit 200
```

The rollup is keyed on `affected_entity.id` **and** `affected_entity.name`, so every row carries both
for the report's `name (ID)` list (`exposure-scoring.md` § Section 6 entity rendering). Render all
rows; the 200-row `limit` is the only cap.

`maxLength:` on every `collect*` call is required to bound row size on high-fanout
entities. Omit any collector class with no values in your environment (they are
harmlessly null when absent, e.g. `k8s.*` outside Kubernetes, `reachable_data_assets`
when Davis data-flow is not configured).

## Report-driven correlation (join form)

Use this when the user names **no indicators** and asks *"am I exposed to what the recent threat
reports describe?"*: the IoCs are the CVEs, IPs and techniques held in **ingested `THREAT_REPORT`
events**, correlated with detections and vulnerabilities in one self-contained query. When the user
pastes or links a report, extract the IoCs with [ioc-intake.md](ioc-intake.md) and use the rollups
above instead; logs and spans are [hunt-logs.md](hunt-logs.md) and [hunt-spans.md](hunt-spans.md).

Reading the reports themselves (listing, filtering by actor / technique / TLP, top observables
across reports) is plain `security.events` access and stays in `dt-sec-insights`
(`threat-intelligence.md`). The reverse direction (a matched IoC → which reports mention it) is in
`dt-sec-contextualization` `ioc-enrichment.md`.

The two sides live in different event families, so correlate with **`join` on a shared key**, not
`in(x, [subquery])` (an execution block is not a valid `in()` argument). Dashboards pre-compute the
IOC list into a variable and use `in(field, $Var)`; a self-contained query uses `join`. Reports are
re-ingested on update: dedup or aggregate by `threat.report.id`, and never use finding / entity / risk
fields on the report side (all null on `THREAT_REPORT`).

### Report CVEs → vulnerabilities

"Am I running anything with a CVE named in recent threat intel?" — join report CVEs to
`VULNERABILITY_FINDING` (external scanners) on the CVE:

```dql
fetch security.events, from:now()-7d
| filter event.type == "VULNERABILITY_FINDING"
| filter isNotNull(vulnerability.references.cve)
| expand cve = vulnerability.references.cve
| join [
    fetch security.events, from:now()-7d
    | filter event.type == "THREAT_REPORT"
    | filterOut isNull(threat.report.id)
    | expand cve = threat.observables.cves
    | filterOut isNull(cve)
    | summarize {reports = countDistinctExact(threat.report.id), reportNames = collectDistinct(threat.report.name)}, by: {cve}
  ], on: {cve}, kind: inner, prefix: "tr."
| summarize {
    findings = count(),
    affectedObjects = countDistinctExact(object.id)
  }, by: {cve, event.provider}
| sort findings desc
```

For **Dynatrace RVA** matches, join the RVA 30m snapshot (pipeline owned by `dt-sec-insights`
`vulnerabilities-dynatrace.md`) to the same report subquery on the CVE. The outer fetch keeps its own
30m window; the 7d applies only to the report subquery:

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type, {"VULNERABILITY_STATE_REPORT_EVENT",
                          "VULNERABILITY_STATUS_CHANGE_EVENT",
                          "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
| filter event.level == "ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| filter vulnerability.resolution.status == "OPEN"
| filter isNotNull(vulnerability.references.cve)
| expand cve = vulnerability.references.cve
| join [
    fetch security.events, from:now()-7d
    | filter event.type == "THREAT_REPORT"
    | filterOut isNull(threat.report.id)
    | expand cve = threat.observables.cves
    | filterOut isNull(cve)
    | summarize {reports = countDistinctExact(threat.report.id), reportNames = collectDistinct(threat.report.name, maxLength:100)}, by: {cve}
  ], on: {cve}, kind: inner, prefix: "tr."
| summarize {
    vulnerabilitiesCount = countDistinctExact(vulnerability.id),
    affectedEntities = countDistinctExact(affected_entity.id),
    reports = takeMax(tr.reports),
    reportNames = takeAny(tr.reportNames),
    entityNames = collectDistinct(affected_entity.name, maxLength:100)
  }, by: {cve}
| sort affectedEntities desc
| limit 200
```

When either join returns no rows, tell an empty correlation from missing intelligence with this check
(reports in the window, and how many name a CVE):

```dql
fetch security.events, from:now()-7d
| filter event.type == "THREAT_REPORT"
| filterOut isNull(threat.report.id)
| summarize {
    reports = countDistinctExact(threat.report.id),
    reportsWithCves = countDistinctExact(if(isNotNull(threat.observables.cves), threat.report.id))
  }
```

`reportsWithCves = 0` means there is no CVE intelligence to correlate, not that the environment is
clean; report it that way.

> **CISA KEV vs `THREAT_REPORT` — they answer different questions.** The Dynatrace Library
> Vulnerability Feed carries a CISA KEV flag per vulnerability. KEV is **binary**: it tells you
> *that* exploitation is known, and nothing more. Threat reports carry the **evidence and detail** —
> which campaign, which actor, which IOCs, what was observed.
>
> - *"Is CVE-X known to be exploited?"* / *"which of my vulnerabilities are actively exploited?"* — a
>   KEV hit is a sufficient answer on its own. Use
>   `dt-sec-insights` `vulnerability-feed.md` § KEV in your environment
>   (RVA snapshot + `lookup` of the feed's KEV entries); no `THREAT_REPORT` needed.
> - **No KEV flag, or the user wants the concrete threat** — who is exploiting it, in what campaign,
>   with which indicators — fall back to `THREAT_REPORT` as described in this reference. Absence of a
>   KEV flag is not evidence that nothing is exploiting it; it only means CISA has not catalogued it.
>
> Report which source the answer came from, and never present a KEV flag as campaign detail.

### Report IPs → detections

"Have any IPs flagged in threat intel shown up as attackers?" — join report IPs to
`DETECTION_FINDING` `actor.ips` on a shared string key:

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
| filter isNotNull(actor.ips)
| expand ioc = actor.ips
| fieldsAdd ioc = toString(ioc)
| join [
    fetch security.events, from:now()-7d
    | filter event.type == "THREAT_REPORT"
    | expand ioc = threat.observables.ips
    | filterOut isNull(ioc)
    | fieldsAdd ioc = toString(ioc)
    | summarize reportNames = collectDistinct(threat.report.name), by: {ioc}
  ], on: {ioc}, kind: inner, prefix: "tr."
| summarize matchedDetections = count(), matchedIPs = countDistinctExact(ioc),
            reports = collectDistinct(tr.reportNames)
| fieldsRemove reports  // drop if you want the report names projected
```

Zero matches is a valid, meaningful answer ("none of the reported IPs have attacked us in this
window") — report it truthfully with the window used.

### Report MITRE techniques → detections

Same join shape, keyed on the technique ID: expand `threat.attack.technique.ids` on the report side
and `threat.attack.technique.ids` on the Automated-Detections side (`event.provider == "Dynatrace
Automated Detections"`), join `on:{technique}`.

## Correlation join keys (feed scoring + contextualization)

Call these out in the hunt output so `dt-sec-contextualization`
`correlation.md` and `exposure-scoring.md` can match entities across
legs:

| From leg | Key | Joins to |
|---|---|---|
| Detection | `object.id` / `dt.smartscape_source.id` | log/span `dt.smartscape_source.id` (3rd-gen) |
| Detection | `dt.process_group.id` (`PROCESS_GROUP-*`) | RVA `affected_entity.id`, log/span `dt.process_group.id` |
| Vulnerability | `affected_entity.id` (`PROCESS_GROUP-*`) | detection `dt.process_group.id`, log/span `dt.process_group.id` |
| Vulnerability | `related_entities.hosts.ids` / `.services.ids` | Smartscape host/service topology |

## Drill-down (full records)

When a single finding's raw record is needed (e.g. inspecting one detection's
`actor.*` context, or one vulnerability's full field set), list the matched records
instead of summarizing. Explicit request only — the rollup is the default output.

**Detections, IP IoCs** — same filter and placeholders as the IP rollup, raw projection:

```dql-template
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter isNotNull(actor.ips)
| filter in(iCollectArray(ip(actor.ips[])), array(toIp("<ip1>"), toIp("<ip2>")))
| fields timestamp, finding.id, finding.title, dt.security.risk.level,
         finding.type, finding.action, actor.ips, actor.geo.country.name,
         object.id, object.name, object.type, event.provider, product.name
| sort timestamp desc
| limit 100
```

**Detections, Domain / URL IoCs** — take the Domain / URL variant template and replace everything
from `| summarize` onward with:

```dql-snippet
| fieldsKeep timestamp, finding.id, finding.title, dt.security.risk.level,
         finding.type, finding.action, event.provider, product.name,
         `Matched observables`, url.full, url.path, url.domain, server.address,
         object.id, object.name, object.type,
         actor.ips, actor.fqdns, "dt.smartscape*"
| sort timestamp desc
| limit 100
```

Zero matches is a valid answer ("none of the IoCs appear in detections in this window") — report it with
the window used; apply the widening rule in § Default Timeframe and Widening.

**Vulnerabilities** — use the owned full-record query in `dt-sec-insights`:

- Vulnerabilities → `vulnerabilities-dynatrace.md` raw state-report listing
  (`| fieldsKeep timestamp, "affected_entity*", "related_entities*", ... `).

## Default Timeframe and Widening

- Detections default `from:now()-2h`; on zero rows, re-run automatically at `from:now()-24h`
  (no approval needed) and report both windows. Going beyond 24h needs approval.
- Vulnerabilities (RVA) are a state snapshot — `from:now()-30m` captures the latest reported
  state per entity, so zero rows on the 30m snapshot **is** a valid no-exposure result for
  Dynatrace RVA findings. Do not widen it.
- `FETCH_EXEC_TIME_LIMIT` on a leg = INCONCLUSIVE, not no-match. Record it and
  continue. Follow `timeframe-gating.md` for anchored windows on IoCs derived
  from timestamped events.

## Field-name notes

- `aws.arn` is not a `security.events` field — use `aws.resource.id`
  (and `azure.resource.id`). Deep hyperscaler fields belong to the cloud skills.
- `actor.fqdns` is the **attacker** FQDN array (parallel to `actor.ips`) — collect
  it. `host.fqdn` is a different field (the affected host's own FQDN), not an
  attacker observable.
- `dt.source_entity` is a legacy identifier (`PROCESS_GROUP_INSTANCE-*` or a cluster
  id, never `PROCESS_GROUP-*`) and does not join RVA `affected_entity.id`. Use
  `dt.smartscape_source.id` (`PROCESS-*`) as the primary detection entity key and
  `dt.process_group.id` (collected as `process_groups`) as the RVA join key.
