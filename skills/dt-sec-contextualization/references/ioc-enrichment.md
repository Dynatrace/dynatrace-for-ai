# IoC Enrichment — Threat-Report Attribution (reverse lookup)

Attribute an **already-matched or suspected** indicator of compromise (IoC) with adversary
context by reverse-looking-up the ingested **threat intelligence reports** whose observable
arrays already contain that IoC. This turns a bare value ("a detection fired from
`157.250.195.229`") into attribution — *"that IP is listed as C2 infrastructure in the
AlienVault OTX report 'Interlock and Rhysida within the Ransomware Ecosystem', attributed to
Rhysida / Vanilla Tempest, malware families Interlock / SystemBC, techniques T1486 / T1566"*.

The enrichment source is `security.events` with `event.type == "THREAT_REPORT"` — the same
events documented in `dt-sec-insights/references/threat-intelligence.md`. That skill owns the
**forward** direction (report → environment: "am I exposed to the IOCs in report X", overviews,
IOC rollups). This file owns the **reverse** direction (a found IoC → which report(s) mention it,
and what adversary context they carry). One home per pattern — do not duplicate report
overview/extraction queries here.

> **Window (no snapshot).** THREAT_REPORT events accumulate; there is no 30m/1h snapshot
> semantic. Use `from:now()-7d` by default. Widen to `30d` or more when you need maximum
> attribution recall (an IoC found today may appear in an older report). Honor an explicit user
> window.

> **Dedup + SD guard, always.** Reports re-ingest on every vendor revision, so every query starts
> from the canonical base (SD-required-field guard + `dedup {threat.report.id}`). Note: the same
> report *name* can carry more than one `threat.report.id` (e.g. an OTX pulse re-published under a
> new id); dedup by id keeps each distinct report, which is correct.

---

## Contents

- [Supported IoC Types](#supported-ioc-types)
- [Canonical Base](#canonical-base)
- [Template — single IoC lookup](#template--single-ioc-lookup)
- [Template — batch lookup with per-IoC attribution](#template--batch-lookup-with-per-ioc-attribution)
- [Per-Type Variants](#per-type-variants)
- [Complementary: app-side reputation enrichment](#complementary-app-side-reputation-enrichment)
- [Best Practices](#best-practices)

---

## Supported IoC Types

Every IoC type below is enrichable via reverse lookup against the matching `threat.observables.*`
(or `threat.attack.*`) array. Field names and taxonomy are aligned with
`dt-sec-ioc-hunting/references/ioc-intake.md` § Supported IoC Taxonomy.

| IoC type | THREAT_REPORT field to match against |
|---|---|
| **IPs** (IPv4 / IPv6) | `threat.observables.ips` |
| **Domains** (hostnames fold here — no `threat.observables.hosts`) | `threat.observables.domains` |
| **URLs** | `threat.observables.urls` |
| **Emails** | `threat.observables.emails` |
| **CVEs** | `threat.observables.cves` |
| **Hashes** (md5 / sha1 / sha256) | `threat.observables.hashes.md5` / `.sha1` / `.sha256` |
| **MITRE TTPs** (ATT&CK technique IDs) | `threat.attack.technique.ids` / `.subtechnique.ids` |

**Adversary context projected by the enrichment** (all arrays, may be null on a given report):
`threat.report.name`, `event.provider`, `product.name`, `threat.actor.names`,
`threat.malware.families`, `threat.attack.technique.ids`, `threat.target.industries`,
`threat.target.countries.names`.

---

## Canonical Base

Identical to the base in `dt-sec-insights/references/threat-intelligence.md` — reused, not
reinvented. The `filterOut` guard keeps only reports satisfying the SD-required set
(`event.provider`, `product.name`, `threat.report.id`, `threat.report.name`); the `dedup`
collapses re-ingested revisions to the latest per report.

```dql
fetch security.events, from:now()-7d
| filter event.type == "THREAT_REPORT"
// keep only SD-compliant reports
| filterOut isNull(event.provider) OR isNull(product.name) OR isNull(threat.report.id) OR isNull(threat.report.name)
// latest version of each report (reports re-ingest on update)
| dedup {threat.report.id}, sort:{timestamp desc}
```

The two templates below extend this base.

---

## Template — single IoC lookup

"Which report(s) mention this IP, and what do they say about it?"

```dql
fetch security.events, from:now()-7d
| filter event.type == "THREAT_REPORT"
| filterOut isNull(event.provider) OR isNull(product.name) OR isNull(threat.report.id) OR isNull(threat.report.name)
| dedup {threat.report.id}, sort:{timestamp desc}
| filter in("157.250.195.229", threat.observables.ips)
| fields threat.report.name, event.provider, product.name,
         threat.actor.names, threat.malware.families,
         threat.attack.technique.ids, threat.target.industries,
         Created = coalesce(toTimestamp(threat.report.time.created), timestamp)
| sort Created desc
```

Replace `"157.250.195.229"` with the found value and `threat.observables.ips` with the field for
its IoC type (see [Per-Type Variants](#per-type-variants)). Zero rows is a valid answer — the IoC
is not attributed to any ingested report in the window.

---

## Template — batch lookup with per-IoC attribution

The realistic agent case: enrich a **list** of hunted IoCs at once and get one attribution row
per IoC. Dedup reports → `expand` the observable to a scalar → cast with `toString()` →
`filter in(scalar, array(...))` intersection → `summarize` by the IoC. Grounded in the validated
list-membership idiom (`in(scalarField, array("v1","v2"))`).

```dql
fetch security.events, from:now()-7d
| filter event.type == "THREAT_REPORT"
| filterOut isNull(event.provider) OR isNull(product.name) OR isNull(threat.report.id) OR isNull(threat.report.name)
| dedup {threat.report.id}, sort:{timestamp desc}
| expand ioc = threat.observables.ips
| filterOut isNull(ioc)
| fieldsAdd ioc = toString(ioc)
| filter in(ioc, array("157.250.195.229", "162.221.93.164"))
| summarize reports     = countDistinctExact(threat.report.id),
            reportNames = collectDistinct(threat.report.name),
            actors      = collectDistinct(threat.actor.names),
            malware     = collectDistinct(threat.malware.families),
            by: {ioc}
| sort reports desc
```

- **Count distinct reports after `expand`** — always `countDistinctExact(threat.report.id)`, never
  raw `count()` (one report fans out into many observable rows).
- `threat.actor.names` / `threat.malware.families` are themselves arrays, so
  `collectDistinct(...)` yields an **array of arrays**. Flatten (`arrayFlatten(...)`) or project
  `reportNames` alone if you want a single-level list for display.
- IoCs from your list that match no report simply produce no row — the surviving rows are the
  attributed subset.

---

## Per-Type Variants

Swap the expanded/filtered field in either template above. The shape is identical.

| IoC type | Field to swap in |
|---|---|
| IPs | `threat.observables.ips` |
| Domains | `threat.observables.domains` |
| URLs | `threat.observables.urls` |
| Emails | `threat.observables.emails` |
| CVEs | `threat.observables.cves` |
| Hashes | `threat.observables.hashes.sha256` (repeat for `.md5` / `.sha1`; pool results) |

**MITRE TTPs** — a technique ID may live in either the technique or the sub-technique array, so OR
across both. A sub-technique like `T1566.001` lives only in `subtechnique.ids`; matching parent
`T1566` requires the `startsWith` leg:

```dql-snippet
| filter in("T1566", threat.attack.technique.ids)
      OR iAny(startsWith(threat.attack.subtechnique.ids[], "T1566."))
```

> **Routing — CVEs and MITRE go further, elsewhere.** Reverse-attributing a CVE or technique *to a
> report* belongs here. But correlating it to **your environment** (CVE → `VULNERABILITY_FINDING` /
> RVA, technique → `DETECTION_FINDING`) is the forward direction owned by
> `dt-sec-insights/references/threat-intelligence.md` § Threat-Exposure Correlation. CVEs and MITRE
> TTPs are never hunted in logs or spans.

---

## Complementary: app-side reputation enrichment

Threat-report attribution answers *"is this IoC known bad, by whom, in what campaign?"* from data
already in Grail. It is **complementary to**, not a replacement for, external reputation services
(AbuseIPDB confidence score, VirusTotal verdict, custom feeds). Those run **client-side / app-side**
in the Dynatrace Threats & Exploits (Security Enrichment) app and are **not exposed as
DQL-queryable `security.events` rows** — see `dt-sec-insights/references/data-model.md` (`actor.ips`
note) and `mistakes-and-troubleshooting.md`. If the user has reputation context from that app or a
direct lookup, incorporate it alongside the report attribution; do not attempt to fetch it via DQL.

---

## Best Practices

1. **Load `dt-dql-essentials` first** — confirm DQL syntax/functions before generating queries.
2. **Always start from the canonical base** — SD-compliance `filterOut` guard +
   `dedup {threat.report.id}, sort:{timestamp desc}`. Skipping either double-counts revisions or
   admits non-conformant rows.
3. **Default `7d`, no snapshot** — use `from:now()-7d` by default; widen to `30d`+ only for
   maximum recall or on user request. Unlike RVA/KSPM, widening looks further back, it does not
   change snapshot semantics.
4. **`countDistinctExact(threat.report.id)` after `expand`** — never raw `count()`.
5. **Never use finding/entity/risk fields** — THREAT_REPORT carries no `finding.*`, `object.*`,
   `dt.security.risk.*`, `dt.smartscape*`, or `dt.entity*`. It is not entity-scoped.
6. **Report zero matches truthfully** — "this IoC is not attributed to any ingested report in the
   last X" is a real, useful answer; never fabricate attribution.
7. **One home per pattern** — reverse attribution lives here; forward correlation, overviews, and
   IOC rollups live in `dt-sec-insights/references/threat-intelligence.md`.
