# Threat Intelligence Queries — `security.events`

Threat intelligence report events (`event.type == "THREAT_REPORT"`) ingested from external
threat-intelligence platforms — **AlienVault OTX** (LevelBlue) pulses and **CrowdStrike Falcon
Intelligence** reports today, extensible to STIX/TAXII feeds. One event per published report:
report identity + provenance (`threat.report.*`), adversary context (`threat.actor.*`,
`threat.target.*`, `threat.malware.*`, `threat.attack.*`), and extracted indicators of compromise
(`threat.observables.*`).

> **Cross-references:** field reference → [data-model.md § Threat Intelligence Fields](data-model.md#threat-intelligence-fields-threat_report) · provider-scoping idiom → [all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type) · dashboard/tile recipes → [coverage-and-dashboards.md § Dashboard Query Patterns](coverage-and-dashboards.md#dashboard-query-patterns).

> **THREAT_REPORT is NOT a finding.** These events describe threats **in the wild** — external
> campaigns, adversary reports, IOC feeds — **not** findings on your monitored entities. They carry
> **no `finding.*`, no `object.*`, no `dt.security.risk.level`/`score`, no affected entity, and no
> scan cycle**. Do **not**:
> - put THREAT_REPORT in the cross-provider four-key `summarize` (`{event.provider, product.name, event.type, dt.security.risk.level}`) — the risk field is always null here;
> - include it in the DT-inclusive posture/overview 3-stream decomposition or the double-counting guard;
> - scope it by entity (`dt.smartscape*` / `dt.entity*` / `object.*` are all absent).
>
> Threat intelligence answers a **separate class of question** ("what threats/IOCs/campaigns are
> being reported?", "am I exposed to the IOCs in report X?") — route here only for those intents.

> **MITRE here vs. in detections.** `threat.attack.*` on a THREAT_REPORT describes the ATT&CK
> techniques of an **external campaign reported by a TI vendor** — it is NOT evidence the technique
> was observed in your environment. For ATT&CK observed on your own entities, use
> [detections.md § Automated Detections — MITRE ATT&CK Workflows](detections.md#automated-detections--mitre-attck-workflows).

> **Reports are re-ingested on update — always dedup by `threat.report.id`.** A report gets a fresh
> event each time the vendor revises it. Every query below starts from the canonical base
> (SD-compliance guard + `dedup {threat.report.id}, sort:{timestamp desc}`) so counts reflect one
> row per report (latest version), not one row per ingestion.

> **No snapshot window.** Unlike RVA (30m) / KSPM (1h), threat intel has no snapshot semantics —
> events accumulate. Use `from:now()-24h` for "recent reports", `from:now()-7d` (or wider) for
> overviews and IOC rollups. Honor an explicit user window.

---

## Contents

- [Provider Routing](#provider-routing)
- [Canonical Base (SD guard + dedup)](#canonical-base-sd-guard--dedup)
- [Overview & Summary](#overview--summary)
  - [Latest threat intelligence reports (list)](#latest-threat-intelligence-reports-list)
  - [Unique reports by provider / product](#unique-reports-by-provider--product)
  - [Reports over time (trend)](#reports-over-time-trend)
- [Indicators of Compromise (IOC extraction)](#indicators-of-compromise-ioc-extraction)
- [Filtering Reports](#filtering-reports)
  - [By MITRE technique](#by-mitre-technique)
  - [By actor / malware family](#by-actor--malware-family)
  - [By targeted country / industry](#by-targeted-country--industry)
  - [By TLP (AlienVault) / report type (CrowdStrike)](#by-tlp-alienvault--report-type-crowdstrike)
  - [Free-text search (title / tags)](#free-text-search-title--tags)
- [Threat-Exposure Correlation (IOC → environment)](#threat-exposure-correlation-ioc--environment)
  - [CVEs → vulnerabilities](#cves--vulnerabilities)
  - [Attacker IPs → detections](#attacker-ips--detections)
  - [MITRE techniques → detections](#mitre-techniques--detections)
  - [IOCs → logs and spans](#iocs--logs-and-spans)
- [Field Nuances & Vendor Extensions](#field-nuances--vendor-extensions)
- [Best Practices](#best-practices)

---

## Provider Routing

| Source | Filter |
|---|---|
| All threat intelligence reports | `event.type == "THREAT_REPORT"` |
| AlienVault OTX (LevelBlue) | `event.type == "THREAT_REPORT" AND event.provider == "AlienVault OTX"` |
| CrowdStrike Falcon Intelligence | `event.type == "THREAT_REPORT" AND event.provider == "CrowdStrike"` (`product.name == "Falcon Intelligence"`) |
| A specific provider (generic) | discover first, then exact-match — see [all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type) |

Threat-intel providers are **not** enumerated beyond the two above — discover active providers with
the [Unique reports by provider / product](#unique-reports-by-provider--product) query and scope by
exact `event.provider` match.

---

## Canonical Base (SD guard + dedup)

Every query starts from this base. The `filterOut` guard keeps only events that satisfy the SD
required set for THREAT_REPORT (`event.provider`, `product.name`, `threat.report.id`,
`threat.report.name`); the `dedup` collapses re-ingested revisions to the latest per report.

```dql
fetch security.events, from:now()-7d
| filter event.type == "THREAT_REPORT"
// keep only SD-compliant reports
| filterOut isNull(event.provider) OR isNull(product.name) OR isNull(threat.report.id) OR isNull(threat.report.name)
// latest version of each report (reports re-ingest on update)
| dedup {threat.report.id}, sort:{timestamp desc}
```

Subsequent snippets shown as `| …` are appended to this base.

---

## Overview & Summary

### Latest threat intelligence reports (list)

```dql
fetch security.events, from:now()-24h
| filter event.type == "THREAT_REPORT"
| filterOut isNull(event.provider) OR isNull(product.name) OR isNull(threat.report.id) OR isNull(threat.report.name)
| dedup {threat.report.id}, sort:{timestamp desc}
| fields Created = coalesce(toTimestamp(threat.report.time.created), timestamp),
         Updated = coalesce(toTimestamp(threat.report.time.updated), timestamp),
         event.provider, product.name, threat.report.name,
         threat.actor.names, threat.report.author
| sort Created desc
| limit 10
```

`threat.report.time.created` / `.updated` are `timestamp`-typed but may be null on some rows —
`coalesce(toTimestamp(...), timestamp)` falls back to the ingestion timestamp.

### Unique reports by provider / product

```dql
fetch security.events, from:now()-7d
| filter event.type == "THREAT_REPORT"
| filterOut isNull(event.provider) OR isNull(product.name) OR isNull(threat.report.id) OR isNull(threat.report.name)
| dedup {threat.report.id}, sort:{timestamp desc}
| summarize reports = count(), by: {event.provider, product.name}
| sort reports desc
```

### Reports over time (trend)

```dql
fetch security.events, from:now()-7d
| filter event.type == "THREAT_REPORT"
| filterOut isNull(event.provider) OR isNull(product.name) OR isNull(threat.report.id) OR isNull(threat.report.name)
| dedup {threat.report.id}, sort:{timestamp desc}
| makeTimeseries count(), by: {event.provider}
```

---

## Indicators of Compromise (IOC extraction)

Observables are typed arrays (`threat.observables.{ips,domains,urls,emails,cves,hashes.md5,hashes.sha1,hashes.sha256}`).
The idiom is: dedup reports → `expand` the observable → count **distinct reports** per value (never a
raw `count()` — one report contributes many observables, and `expand` fans out rows).

**Top CVEs referenced across reports:**

```dql
fetch security.events, from:now()-7d
| filter event.type == "THREAT_REPORT"
| filterOut isNull(event.provider) OR isNull(product.name) OR isNull(threat.report.id) OR isNull(threat.report.name)
| dedup {threat.report.id}, sort:{timestamp desc}
| filter arraySize(threat.observables.cves) > 0
| expand CVE = threat.observables.cves
| summarize Reports = countDistinctExact(threat.report.id), by: {CVE}
| sort Reports desc
| limit 10
```

**Top attacker IPs** — swap `CVE = threat.observables.cves` for `IP = threat.observables.ips`
(and the `arraySize` guard field accordingly). The same shape covers **domains**
(`threat.observables.domains`), **URLs** (`threat.observables.urls`), **emails**
(`threat.observables.emails`), and **file hashes** (`threat.observables.hashes.sha256` /
`.md5` / `.sha1`):

```dql-snippet
| expand IP = threat.observables.ips
| filterOut isNull(IP)
| summarize Reports = countDistinctExact(threat.report.id), by: {IP}
| sort Reports desc
| limit 10
```

**Observable count by type** (single-row coverage summary):

```dql
fetch security.events, from:now()-7d
| filter event.type == "THREAT_REPORT"
| filterOut isNull(event.provider) OR isNull(product.name) OR isNull(threat.report.id) OR isNull(threat.report.name)
| dedup {threat.report.id}, sort:{timestamp desc}
| summarize {
    CVEs    = sum(coalesce(arraySize(threat.observables.cves), 0)),
    IPs     = sum(coalesce(arraySize(threat.observables.ips), 0)),
    Domains = sum(coalesce(arraySize(threat.observables.domains), 0)),
    URLs    = sum(coalesce(arraySize(threat.observables.urls), 0)),
    Emails  = sum(coalesce(arraySize(threat.observables.emails), 0)),
    Hashes  = sum(coalesce(arraySize(threat.observables.hashes.sha256), 0)),
    Techniques = sum(coalesce(arraySize(threat.attack.technique.ids), 0))
  }
```

---

## Filtering Reports

### By MITRE technique

`threat.attack.technique.ids` / `.subtechnique.ids` / `.tactic.ids` are **separate arrays** (a
sub-technique ID like `T1110.001` lives only in `subtechnique.ids`).

```dql
fetch security.events, from:now()-7d
| filter event.type == "THREAT_REPORT"
| filterOut isNull(event.provider) OR isNull(product.name) OR isNull(threat.report.id) OR isNull(threat.report.name)
| dedup {threat.report.id}, sort:{timestamp desc}
| filter in("T1110", threat.attack.technique.ids)
| fields threat.report.name, threat.actor.names, event.provider, threat.attack.technique.ids
| sort threat.report.name asc
| limit 50
```

For a **parent technique + all its sub-techniques**, OR across both arrays:

```dql-snippet
| filter in("T1110", threat.attack.technique.ids)
      OR iAny(startsWith(threat.attack.subtechnique.ids[], "T1110."))
```

**Coverage breakdown by technique** — `expand Technique = threat.attack.technique.ids` then
`summarize Reports = countDistinctExact(threat.report.id), by:{Technique} | sort Reports desc`.

### By actor / malware family

```dql-snippet
| filter in("CURLY SPIDER", threat.actor.names)
```

Or rank actors/families by report count — `expand Actor = threat.actor.names` (or
`Family = threat.malware.families`), then `summarize Reports = countDistinctExact(threat.report.id), by:{Actor}`.

### By targeted country / industry

Targeting uses `threat.target.countries.names` (full names), `threat.target.countries.iso_codes`
(ISO 3166-1 alpha-2 — use for choropleth maps), and `threat.target.industries` (**plural**).

```dql-snippet
| expand ISO = threat.target.countries.iso_codes
| filterOut isNull(ISO)
| summarize Reports = countDistinctExact(threat.report.id), by: {ISO}
| sort Reports desc
```

> **Field-name gotchas:** the SD-canonical fields are `threat.target.countries.names` /
> `.iso_codes` and `threat.target.industries` (plural). A bare `threat.target.countries` is **not**
> an SD field, and `threat.target.industry` (singular) does not exist — filtering on either matches
> nothing. Some producers omit `.names`; `coalesce(threat.target.countries.names, threat.target.countries)`
> is a defensive fallback only if you know a producer populated the non-standard bare field.

### By TLP (AlienVault) / report type (CrowdStrike)

Vendor-extension fields (no SD counterpart — see [§ Field Nuances](#field-nuances--vendor-extensions)):

```dql-snippet
| filter alienvault.pulse.tlp == "WHITE"        // AlienVault OTX: WHITE | GREEN
```

```dql-snippet
| filter crowdstrike.report.type.name == "Notice"   // CrowdStrike: Notice | Tipper | Periodic Report | Intelligence Report | Recon+
```

### Free-text search (title / tags)

```dql-snippet
| filter matchesValue(threat.report.tags, "*ransomware*") OR contains(threat.report.name, "ransomware", caseSensitive:false)
```

`threat.report.tags` is an array — use `matchesValue()` for it; `threat.report.name` is a string —
use `contains(field, "…", caseSensitive:false)` for case-insensitive substring match. **The
`caseSensitive` argument must be named** (`caseSensitive:false`) — a bare positional third argument
(`contains(field, "…", false)`) is rejected as `TOO_MANY_POSITIONAL_PARAMETERS`.

---

## Threat-Exposure Correlation (IOC → environment)

The high-value use case: take the IOCs/CVEs/techniques from threat reports and check whether they
appear in **your** monitored environment. Because the two sides live in different event families (or
different datasets), correlate with **`join` on a shared key**, not `in(x, [subquery])` (an
execution block is not a valid `in()` argument). Dashboards pre-compute the IOC list into a variable
and use `in(field, $Var)`; a self-contained query uses `join`.

> **Reverse direction (IoC → report attribution) lives elsewhere.** The queries here go report →
> environment. For the inverse — you already matched an IoC and want *"which report(s) mention it,
> attributed to which actor/malware/campaign?"* — use
> `dt-sec-contextualization/references/ioc-enrichment.md`.

### CVEs → vulnerabilities

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
    | summarize reports = countDistinctExact(threat.report.id), reportNames = collectDistinct(threat.report.name), by: {cve}
  ], on: {cve}, kind: inner, prefix: "tr."
| summarize {
    findings = count(),
    affectedObjects = countDistinctExact(object.id)
  }, by: {cve, event.provider}
| sort findings desc
```

For **Dynatrace RVA** matches, run the canonical RVA 30m snapshot pipeline (see
[vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md)) and `filter in(vulnerability.references.cve, <cveList>)`,
or join the RVA stream on `vulnerability.references.cve` the same way.

### Attacker IPs → detections

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

### MITRE techniques → detections

Same join shape, keyed on the technique ID: expand `threat.attack.technique.ids` on the report side
and `threat.attack.technique.ids` on the Automated-Detections side (`event.provider == "Dynatrace
Automated Detections"`), join `on:{technique}`.

### IOCs → logs and spans

Report IOCs can also be searched in **logs** and **spans** — these are different datasets
with their own validated hunt templates. Route to **`dt-sec-ioc-hunting`** for IoC-specific
hunting across both sources.

- **Logs** — literal `matchesPhrase(content, "<ioc>")` OR-chain prefilter (one clause per IoC), then per-class matched-observable derivation using `contains` after that prefilter. Supports IPs, Domains, URLs, Emails, and Hashes.
  See `dt-sec-ioc-hunting/references/hunt-logs.md`.
- **Spans (inbound + outbound)** — single combined pass over `span.kind in {client,server}`;
  matches IPs on `client.ip`/`server.resolved_ips`/`request_attribute.SourceIP` and
  Domains/URLs on `http.host`/`url.full`. See `dt-sec-ioc-hunting/references/hunt-spans.md`.

Keep the log/span window tight (default `from:now()-15m`, unless the user explicitly asks for a wider window) and pre-filter the IOC list. The
`dt-sec-ioc-hunting` skill owns the expand-on-approval protocol for widening.

For **generic** log or trace queries not tied to an IoC hunt, route to `dt-obs-logs` /
`dt-obs-tracing` instead.

---

## Field Nuances & Vendor Extensions

- **Timestamps:** `threat.report.time.created` / `.updated` are `timestamp`-typed; use
  `coalesce(toTimestamp(...), timestamp)` to fall back to ingestion time when null.
- **Targeting:** `threat.target.countries.names` / `.iso_codes` / `threat.target.industries`
  (plural). Avoid bare `threat.target.countries` and singular `threat.target.industry` — not SD fields.
- **Observable counts after `expand`:** always `countDistinctExact(threat.report.id)`, never `count()`.
- **Vendor extensions (additive — no SD counterpart, keep as-is):**
  - AlienVault OTX: `alienvault.pulse.public` (boolean), `alienvault.pulse.tlp` (`WHITE` | `GREEN`).
  - CrowdStrike: `crowdstrike.report.slug`, `crowdstrike.report.type`, `crowdstrike.report.type.id`,
    `crowdstrike.report.type.name` (`Notice` | `Tipper` | `Periodic Report` | `Intelligence Report` | `Recon+`).
- **Raw payload:** `event.original_content` carries the vendor's original report JSON (extension/pull
  integrations); parse with `parse event.original_content, "JSON:raw"` for fields not normalized to SD.

---

## Best Practices

1. **Always dedup by `threat.report.id`** (`sort:{timestamp desc}`) — reports re-ingest on update;
   without dedup, counts and IOC rollups double-count revisions.
2. **Apply the SD-compliance guard** (`filterOut isNull(event.provider) OR isNull(product.name) OR
   isNull(threat.report.id) OR isNull(threat.report.name)`) so partial/non-conformant rows don't skew results.
3. **Never use finding/entity/risk fields** — `finding.*`, `object.*`, `dt.security.risk.level`,
   `dt.smartscape*`/`dt.entity*` are all null on THREAT_REPORT. Do not add them to filters, `by:`, or projections.
4. **Keep threat intel out of the posture/overview streams** — it is a separate intent; a broad
   "what security data do we have?" must not fold in THREAT_REPORT (see the top-of-file callout).
5. **Parent + sub-techniques require an OR** across `threat.attack.technique.ids` and `threat.attack.subtechnique.ids` — they are separate arrays.
6. **Count distinct reports after `expand`** — `countDistinctExact(threat.report.id)`, not `count()`.
7. **No snapshot window** — use `24h` for recent, `7d`+ for overviews; honor explicit windows. Threat intel accumulates; widening looks back further (unlike RVA/KSPM).
8. **Correlate with `join` on a shared IOC/CVE/technique key** — not `in(x, [subquery])`. Cross-dataset IoC hunts in logs/spans route to `dt-sec-ioc-hunting`; generic log/trace exploration routes to `dt-obs-logs` / `dt-obs-tracing`.
9. **Vendor extensions (`alienvault.pulse.*`, `crowdstrike.report.*`) are valid additive context** — use them for TLP / report-type filters; they have no SD counterpart.
10. **Report empty correlation results truthfully** — "none of the reported IOCs appear in your environment in the last X" is a real, useful answer; never fabricate matches.
