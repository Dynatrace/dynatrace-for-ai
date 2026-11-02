# Detection Queries — `security.events`

Runtime Application Protection (RAP) detections, Automated Detection rules, and
external provider detections.

> **Cross-references:** field reference → [data-model.md § Detection Fields](data-model.md#detection-fields-detection_finding) · entity
> scoping OR chain, sem-dict filter, default summarization →
> [common-patterns.md](common-patterns.md).

> **Detections are one-shot events** — one `DETECTION_FINDING` row per detection, no
> state-report dedup or vulnerability-level summarize. `DETECTION_FINDING` is the only
> event type fully covered by the cross-provider summary pattern for both Dynatrace and
> external sources (the null-safe Dynatrace-exclusion guard keeps DT RAP / Automated Detections and drops
> the rest of Dynatrace's own events; see [all-security-events.md § Canonical Cross-Provider Query](all-security-events.md#canonical-cross-provider-query)). For vulnerabilities and compliance, pair it
> with the Dynatrace RVA / SPM snapshot patterns.

> **No mute / dismiss / suppress in `security.events`.** There is no equivalent of
> `vulnerability.mute.*`; suppression happens UI-side (Threats & Exploits filters) or at
> OneAgent ingest (Application Protection allowlist rules, see § RAP: Attack-Type & Action
> Workflows). If asked for "dismissed detections," explain the data isn't there.

> **Two DT-native event types from Automated Detections:** `DETECTION_FINDING` and
> `DETECTION_EXECUTION_SUMMARY` (one audit row per rule run) — see § Automated Detections — Execution Summary.

---

## Contents

- [Provider Routing](#provider-routing)
- [All Dynatrace-Generated Detections (canonical)](#all-dynatrace-generated-detections-canonical)
  - [Widen-on-empty fallback (retrieval queries)](#widen-on-empty-fallback-retrieval-queries)
  - [Top-N detections across all providers (24h)](#top-n-detections-across-all-providers-24h)
  - [Latest RAP detections — current window (both event types)](#latest-rap-detections--current-window-both-event-types)
  - [Automated Detections (custom / built-in rules)](#automated-detections-custom--built-in-rules)
  - [Critical Dynatrace detections grouped by affected host (24h)](#critical-dynatrace-detections-grouped-by-affected-host-24h)
- [RAP: Attack-Type & Action Workflows](#rap-attack-type--action-workflows)
  - [Attack-type breakdown](#attack-type-breakdown)
  - [Blocked vs. monitored breakdown](#blocked-vs-monitored-breakdown)
  - [Top attacker IPs — cross-provider](#top-attacker-ips-last-24h-cross-provider)
  - [Scope variants (RAP-only / external-only / single provider)](#scope-variants-narrow-only-when-the-user-explicitly-asks)
  - [`actor.ips` coverage check](#actorips-coverage-check-when-results-look-sparse)
  - [RAP attack drilldown (specific attack on a process)](#rap-attack-drilldown-specific-attack-on-a-process)
- [Automated Detections — MITRE ATT&CK Workflows](#automated-detections--mitre-attck-workflows)
  - [Coverage breakdown by MITRE technique](#coverage-breakdown-by-mitre-technique)
  - [Filter detections by technique (single, or parent + sub)](#filter-detections-by-technique-single-technique-or-parent--sub-techniques)
  - [Untagged Automated Detections (rules missing MITRE)](#untagged-automated-detections-rules-missing-mitre)
- [Automated Detections — Execution Summary](#automated-detections--execution-summary)
- [External Detection Queries](#external-detection-queries)
  - [Threats & Exploits (T&E) App Compatibility](#threats--exploits-te-app-compatibility)
  - [Detections from a specific external provider](#detections-from-a-specific-external-provider)
  - [Custom / non-normalized ingest](#custom--non-normalized-ingest)
- [Cross-Provider Summary Pattern (all finding types)](#cross-provider-summary-pattern-all-finding-types)
- [Single-Finding Drill-Down Pattern](#single-finding-drill-down-pattern)
- [Detection Workflows](#detection-workflows)
  - [Simple detection count ("how many?")](#simple-detection-count-how-many)
  - [New findings within a time window (UC-G2)](#new-findings-within-a-time-window-uc-g2-for-detections)
  - [Detections by finding type (UC-D3)](#detections-by-finding-type-uc-d3)
  - [Detections over time (grouped by day or hour)](#detections-over-time-grouped-by-day-or-hour)
  - [Critical detections on a specific entity](#critical-detections-on-a-specific-entity)
  - [Detection lookup by ID or title](#detection-lookup-by-id-or-title)
- [Best Practices](#best-practices)

---

## Provider Routing

| Source | Filter |
|---|---|
| All Dynatrace-generated detections (RAP + Automated Detections) | `event.type == "DETECTION_FINDING" AND product.vendor == "Dynatrace"` |
| **RAP only** (Runtime Application Protection via OneAgent) | `in(event.type, {"DETECTION_FINDING","SECURITY_EVENT"}) AND (product.name == "Runtime Application Protection" OR event.provider == "OneAgent")` |
| Automated Detections only (custom / built-in rules) | `event.type == "DETECTION_FINDING" AND event.provider == "Dynatrace Automated Detections"` |
| AutomationEngine (workflow detections) | `event.type == "DETECTION_FINDING" AND event.provider == "AutomationEngine"` |
| All external providers | `event.type == "DETECTION_FINDING"` + `filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"` |

Default to the unified Dynatrace form (`product.vendor == "Dynatrace"`); split only when the
user asks for RAP-only, Automated-Detections-only, or a specific provider. External detections
share the `DETECTION_FINDING` type — query them together with the catch-all above, and narrow to
one provider with
[all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type).

> **RAP filter — keep the combined form.** `product.name == "Runtime Application Protection"` is
> canonical (Dynatrace docs / SD), but older RAP rows on at least one tenant carry
> `product.name == "Application Security"`, so that half alone returns zero there. `event.provider == "OneAgent"`
> is not used by Automated Detections or external providers, so the OR pulls in no other source.
> Never drop either half.
>
> **RAP event type:** most tenants emit RAP as `DETECTION_FINDING`, some as `SECURITY_EVENT` — for
> broad RAP / critical-detection summaries always include both; never narrow to `DETECTION_FINDING` alone.

---

## All Dynatrace-Generated Detections (canonical)

```dql
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter product.vendor == "Dynatrace"
```

### Widen-on-empty fallback (retrieval queries)

**Default to `from:now()-2h` for every unqualified detection query** ("how many detections do I have?",
"detections by severity", "list recent attacks", "by attack type / entity / provider") — the Threats & Exploits
app default. Run the fallback **only when the 2h query returns zero rows**, and honor any window the user states
explicitly.

**Exception — cross-provider scope starts at 24h.** For top-N, "all providers" / "any external source", or
named-external-provider asks (GuardDuty, Sentinel, Defender, ...), start at `from:now()-24h` and use
[§ Top-N detections across all providers](#top-n-detections-across-all-providers-24h): external detections arrive in
batches and are usually invisible in a 2h window (a 2h run returns only RAP). RAP-only and unqualified
"latest / recent detections" asks keep 2h.

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
| filter product.vendor == "Dynatrace"
```

If 24h is still empty (sparse or new tenant), widen once more to `from:now()-7d` before concluding "no detections."
**Report the wider window used** ("no detections in the last 2h; widening to 24h returned X results"). Cross-provider
asks (exception above) already start at 24h, so their fallback is 24h -> 7d.

> **Never run the 2h and 24h queries in parallel** — the fallback is sequential. Running both
> wastes ~10× the data budget and yields two result sets to reconcile.

> **Wider windows are correct for history/analytics prompts** that state the timeframe: top attacker IPs
> over 24h, MITRE breakdowns over 24h/7d, detections by day over 7d, critical-by-host over 24h, cross-provider
> top-N over 24h. Without an explicit timeframe and outside the cross-provider exception, start at `2h`.

### Top-N detections across all providers (24h)

"Top 50 critical and high detections ... Dynatrace RAP and any external source." Raw listing (no `summarize`), so it
keeps entity identifiers; the 9-field SD guard (see [all-security-events.md § Semantic-Dictionary Fields](all-security-events.md#semantic-dictionary-fields))
matches what the Threats & Exploits app shows. `DETECTION_FINDING` covers RAP and external rows alike.

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
| filter isNotNull(event.id) AND isNotNull(event.provider) AND isNotNull(finding.type)
     AND isNotNull(finding.id) AND isNotNull(finding.time.created) AND isNotNull(finding.title)
     AND isNotNull(dt.security.risk.level) AND isNotNull(object.id) AND isNotNull(object.type)
| filter in(dt.security.risk.level, {"CRITICAL", "HIGH"})
| fieldsKeep timestamp, event.provider, product.name, finding.id, finding.title, finding.type, finding.action,
            dt.security.risk.level, dt.security.risk.score, actor.ips, object.name, object.type, "dt.smartscape*"
| sort dt.security.risk.score desc, timestamp desc
| limit 50
```

Ranking is by score across providers, so a high-volume provider (RAP) can fill the whole list. When the ask names
external sources, also report the per-provider split: same filters, `summarize Detections = count(), by:{event.provider, dt.security.risk.level}`
instead of `fieldsKeep ... limit 50`.

### Latest RAP detections — current window (both event types)

RAP detects code-level attacks via OneAgent (`finding.type` = attack class, `finding.action` = response).
Canonical "show me current RAP attacks" recipe (both event types, see § Provider Routing):

```dql
fetch security.events, from:now()-2h
| filter in(event.type, {"DETECTION_FINDING", "SECURITY_EVENT"})
| filter (product.name == "Runtime Application Protection" OR event.provider == "OneAgent")
| fieldsKeep timestamp, finding.id, finding.title, dt.security.risk.level,
         dt.security.risk.score, finding.type, finding.action, actor.ips,
         object.id, object.name, object.type,
         "dt.smartscape*"
| sort timestamp desc
| limit 100
```

On zero rows, widen to `from:now()-24h` (see § Widen-on-empty fallback).

### Automated Detections (custom / built-in rules)

```dql
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter event.provider == "Dynatrace Automated Detections"
| fieldsKeep timestamp, "dt.smartscape*",
         detection.id, detection.title, finding.title,
         dt.security.risk.level, threat.attack.technique.ids, threat.attack.subtechnique.ids,
         object.name, object.type, execution.id
| sort timestamp desc
```

### Critical Dynatrace detections grouped by affected host (24h)

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
     AND product.vendor == "Dynatrace"
     AND dt.security.risk.level == "CRITICAL"
| summarize {
    detections = count(),
    titles = collectDistinct(finding.title),
    smartscape_node.ids = collectDistinct(dt.smartscape_source.id)
  }, by: {host.name, dt.smartscape.host}
| sort detections desc
| limit 25
```

---

## RAP: Attack-Type & Action Workflows

`finding.type` is the canonical attack class; `finding.action` carries OneAgent's response.

### Attack-type breakdown

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
     AND (product.name == "Runtime Application Protection" OR event.provider == "OneAgent")
| summarize {
    Detections = count(),
    Critical = countIf(dt.security.risk.level == "CRITICAL"),
    Blocked = countIf(finding.action == "Blocked"),
    Audited = countIf(finding.action == "Audited"),
    Allowlisted = countIf(finding.action == "Allowlisted"),
    AffectedProcesses = countDistinctExact(dt.smartscape_source.id),
    smartscape_node.ids = collectDistinct(dt.smartscape_source.id)
  }, by: {AttackType = finding.type}
| sort Detections desc
```

### Blocked vs. monitored breakdown

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
     AND (product.name == "Runtime Application Protection" OR event.provider == "OneAgent")
| summarize Detections = count(),
            by: {Action = finding.action,
                 AttackType = finding.type,
                 Severity = dt.security.risk.level}
| sort Detections desc
```

> **`finding.action` enum**: `Blocked` (OneAgent stopped the request), `Audited` (Monitor mode — detected
> not stopped), `Allowlisted` (an Application Protection rule explicitly allowed it). If null (older
> OneAgent), fall back to `event.outcome` if present, or treat as `Audited` for triage. Don't conflate
> `finding.action` with `event.outcome`.

### Top attacker IPs (last 24h, cross-provider)

> **Default to cross-provider scope for attacker analytics** — `actor.ips` is populated across RAP and
> external sources. Narrow only on an explicit ask (see § Scope variants below).

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
| filter isNotNull(actor.ips)
| expand actor.ips
| fieldsAdd ip = ip(actor.ips)
| summarize {
    Detections = count(),
    DistinctTargets = countDistinctExact(object.id),
    AttackTypes = collectDistinct(finding.type),
    Providers = collectDistinct(event.provider),
    Products = collectDistinct(product.name),
    Countries = collectDistinct(actor.geo.country.name),
    FirstSeen = takeMin(timestamp),
    LastSeen = takeMax(timestamp)
  }, by: {SourceIP = ip}
| sort Detections desc
| limit 25
```

> **`expand` + `ip()` cast:** `actor.ips` is `ipAddress[]` (one row may carry IPv4 + IPv6 or a proxy chain).
> `expand` ranks each IP independently; the `ip()` cast types the value so `==`, range and CIDR comparisons
> type-check.

> **Mixed provenance:** the same IP under multiple `Providers` (e.g. RAP + an external source) is signal —
> perimeter and in-process detection agree. A single provider is normal.

> **Out of scope here:** filtering detections by a known IoC list and repeat / fan-out investigation
> (same IP across many targets, same rule re-firing on one object) live in **dt-sec-ioc-hunting**
> (`hunt-security-events.md`, `detection-investigation.md`).

### Scope variants (narrow only when the user explicitly asks)

Apply on top of the Top attacker IPs query above; never by default.

| User intent | Add this filter |
|---|---|
| "In-application attacks" / "RAP" / "OneAgent attacks" | `AND (product.name == "Runtime Application Protection" OR event.provider == "OneAgent")` |
| "External tools" / "perimeter" / "cloud security findings" | `filterOut event.provider == "Dynatrace" or product.vendor == "Dynatrace"` |
| A specific external provider | See [all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type) |

### `actor.ips` coverage check (when results look sparse)

Not every provider populates `actor.ips`; run this first if the cross-provider query looks empty:

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
| summarize {
    Total = count(),
    HasIPs = countIf(isNotNull(actor.ips)),
    CoveragePct = round(countIf(isNotNull(actor.ips)) * 100.0 / count(), decimals: 1)
  }, by: {event.provider, product.name}
| sort Total desc
```

For providers with `HasIPs == 0`, the IP (if any) is in `dt.raw_data` — `parse dt.raw_data, "JSON:raw"` and project the key.

> **Enrichment:** `actor.ips` reputation enrichment (AbuseIPDB / VirusTotal / custom APIs via the **Security
> Enrichment** app) happens client-side in the Threats & Exploits app, not in `security.events` — group by the cast
> IP and resolve reputation outside DQL. Geo fields (`actor.geo.*`) are Experimental, are never populated on RAP findings, and only some external detections (e.g. GuardDuty) carry them.

### RAP attack drilldown (specific attack on a process)

**Placeholders:**

- `<PROCESS_ID>` — Smartscape id of the attacked process, `PROCESS-` plus 16 hex characters (e.g. `PROCESS-2BFEC6517F8B5A64`). Take it from `dt.smartscape_source.id` of a detection row or from the discovery query below. It identifies a process instance, not a process group; for OneAgent events it equals `object.id`.
- `<ATTACK_CLASS>` — case-insensitive substring of `finding.type`, e.g. `sql`, `cmd`, `ssrf` (live values: finding-type discovery query under § Detections by finding type).
- Type pitfall: `dt.smartscape_source.id` is a typed Smartscape id — compare with `toSmartscapeId("…")` (or `toString(field) == "…"`); a bare string literal silently matches nothing.

Discovery — most attacked processes (copy `dt.smartscape_source.id` into the template):

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
| summarize {Detections = count(), AttackTypes = collectDistinct(finding.type)}, by: {dt.smartscape_source.id, object.name}
| sort Detections desc
| limit 10
```

```dql-template
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
     AND (product.name == "Runtime Application Protection" OR event.provider == "OneAgent")
     AND contains(finding.type, "<ATTACK_CLASS>", caseSensitive:false)
| filter dt.smartscape_source.id == toSmartscapeId("<PROCESS_ID>")
| sort timestamp desc
| limit 50
| fieldsKeep timestamp, "dt.smartscape*",
            finding.id, finding.type, finding.action, finding.title,
            actor.ips,
            dt.security.rap.target.id, dt.security.rap.target.type, dt.security.rap.target.name,
            object.id, object.name, object.type
```

> Entry-point payloads, user-controlled inputs and sink-code details are product-emitted fields outside the SD
> stable namespace — use the Threats & Exploits app for full attack reconstruction; the fields above answer
> "which attack, from whom, hitting which target."

`finding.type` is a **vendor-original free-form string**, not a normalized enum; RAP display strings vary across
OneAgent versions (observed: `SQL injection`, `CMD injection`, `JNDI injection`, `SSRF`). Use
`contains(finding.type, "…", caseSensitive:false)`, not exact-match literals. JNDI/SSRF are Java-only; SQL/command/path
injection cover Java + .NET + Go. Discover live values with the summarize query in UC-D3 below.

---

## Automated Detections — MITRE ATT&CK Workflows

Automated Detections rules can carry MITRE ATT&CK tags in the SD namespace `threat.attack.*` (technique,
sub-technique, tactic — separate arrays). This is the only DT-native source of MITRE in `security.events`; RAP
findings carry none. Field reference (types, examples, `.names` / `.version`) →
[data-model.md § DT Automated Detections](data-model.md#dt-automated-detections-eventprovider--dynatrace-automated-detections).

> **Query rules:** use `in(value, array)` for exact-ID membership (fallback:
> `expand technique = threat.attack.technique.ids | filter technique == "T1078"`). Sub-technique IDs
> (`T1059.003`) live in their **own** array, so `threat.attack.technique.ids` never matches them;
> "parent + all sub-techniques" needs an OR across both arrays (see below).

### Coverage breakdown by MITRE technique

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
     AND event.provider == "Dynatrace Automated Detections"
| filter isNotNull(threat.attack.technique.ids) AND arraySize(threat.attack.technique.ids) > 0
| expand technique = threat.attack.technique.ids
| summarize {
    Detections = count(),
    Rules = countDistinctExact(detection.id),
    AffectedObjects = countDistinctExact(object.id),
    Severities = collectDistinct(dt.security.risk.level)
  }, by: {Technique = technique}
| sort Detections desc
```

### Filter detections by technique (single technique, or parent + sub-techniques)

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
     AND event.provider == "Dynatrace Automated Detections"
| filter in("T1078", threat.attack.technique.ids)
| fieldsKeep timestamp, "dt.smartscape*",
         detection.title, finding.title, dt.security.risk.level,
         threat.attack.technique.ids, threat.attack.subtechnique.ids, object.name
| sort timestamp desc
```

For a **parent technique + all its sub-techniques** (e.g. T1110 + T1110.001/002/…), swap the single-technique filter for:

```dql-snippet
| filter in("T1110", threat.attack.technique.ids)
      OR iAny(startsWith(threat.attack.subtechnique.ids[], "T1110."))
```

### Untagged Automated Detections (rules missing MITRE)

Coverage-gap audit — which rules fired but lack MITRE tagging?

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
     AND event.provider == "Dynatrace Automated Detections"
| filter (isNull(threat.attack.technique.ids) OR arraySize(threat.attack.technique.ids) == 0)
     AND (isNull(threat.attack.subtechnique.ids) OR arraySize(threat.attack.subtechnique.ids) == 0)
| summarize {Detections = count(),
            Sample = takeFirst(finding.title)},
            by: {RuleID = detection.id, Rule = detection.title}
| sort Detections desc
```

---

## Automated Detections — Execution Summary

`DETECTION_EXECUTION_SUMMARY` is emitted **per rule run**; use it for "did my rule fire / succeed / how much did it
scan?" without scanning the findings stream. Filter by `event.provider == "Dynatrace Automated Detections"`
(`product.name == "Automated Detections"` is also populated on every row and works alone).

### Execution status breakdown (last 24h)

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_EXECUTION_SUMMARY"
     AND event.provider == "Dynatrace Automated Detections"
| summarize {
    Runs = count(),
    Success = countIf(execution.result.status == "SUCCESS"),
    Warnings = countIf(execution.result.status == "SUCCESS_W_WARNINGS"),
    Failures = countIf(execution.result.status == "FAILURE"),
    TotalEventsWritten = sum(execution.stats.events_written),
    TotalRecordsScanned = sum(execution.stats.scanned_records)
  }, by: {RuleID = detection.id, Rule = detection.title}
| sort Failures desc, Warnings desc, Runs desc
```

> **Execution stat fields** are `execution.result.status`, `execution.stats.events_written` / `.scanned_records` /
> `.scanned_bytes` and `execution.query.timeframe.start` / `.end` (verified on dev-demo; the flat `execution.status`,
> `execution.events_written` names and the camelCase `eventsWritten` / `scannedRecords` do not exist and return null).
> See [data-model.md § Automated Detections](data-model.md#dt-automated-detections-eventprovider--dynatrace-automated-detections).

### Rules that have not fired in the last 24h

Take the execution-status query, reduce its summarize to `{ Runs = count(), Findings = sum(execution.stats.events_written) }`
keyed by `{detection.id, detection.title}`, then append `| filter Findings == 0 | sort Runs desc`.
`Findings == 0` over a representative window means the threat hasn't occurred or the rule is mis-tuned.

---

## External Detection Queries

Ingested from external cloud-security and SIEM/SOAR tools via OpenPipeline — same `DETECTION_FINDING` type, different
`event.provider` / `product.vendor`.

**All external detections (not Dynatrace-generated):**

```dql
fetch security.events
| filter event.type == "DETECTION_FINDING"
| filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
```

### Threats & Exploits (T&E) App Compatibility

To return findings as the **Threats & Exploits app** displays them, apply the 9-field SD-compliance filter
(`event.id`, `event.provider`, `finding.type`, `finding.id`, `finding.time.created`, `finding.title`,
`dt.security.risk.level`, `object.id`, `object.type` all `isNotNull`); findings missing any are hidden or
rendered incomplete. The canonical filter (any `*_FINDING` type) lives in
[all-security-events.md § Semantic-Dictionary Fields](all-security-events.md#semantic-dictionary-fields) — scope it
with `filter event.type == "DETECTION_FINDING"`. **Omit it** when investigating *why* findings are missing from the app.

**Time-bounded detections** — SD-compatibility filter plus a `finding.time.created` bound (a string — wrap with `toTimestamp()`):

```dql
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter isNotNull(event.id) AND isNotNull(event.provider) AND isNotNull(finding.type)
     AND isNotNull(finding.id) AND isNotNull(finding.time.created) AND isNotNull(finding.title)
     AND isNotNull(dt.security.risk.level) AND isNotNull(object.id) AND isNotNull(object.type)
| filter toTimestamp(finding.time.created) > now()-2h
| sort timestamp desc
| limit 100
```

### Detections from a specific external provider

**Step 1 — discover the active provider strings** (if not already known):

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
| summarize detections=count(), by:{event.provider, product.vendor, product.name}
| sort detections desc
```

**Step 2 — scope with exact match** (prefer exact equality over fuzzy `contains`; general pattern:
[all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type)).
Detection-specific point: **one provider may arrive via two ingestion paths** (e.g. direct and via AWS Security Hub) —
combine both with `OR`. Named example, Amazon GuardDuty: the query lives in
[all-security-events.md § GuardDuty risk and resource summary](all-security-events.md#guardduty-risk-and-resource-summary-named-provider-exact-match-example)
(one home for it; do not copy it here). Use this Step 1 for discovery: it reads `DETECTION_FINDING` only, a
fraction of the all-types discovery scan.

That query uses the generic `object.*` namespace, so it works for any provider. For hyperscaler-specific resource
identifiers (ARNs, account / subscription / project scoping) use the dedicated AWS / Azure / GCP skills. For
attacker-IP / sign-in / WAF detections, the cross-provider `actor.ips` pattern (§ Top attacker IPs) already
covers external sources.

### Custom / non-normalized ingest

Custom sources arrive as `DETECTION_FINDING` with their own values. Discover providers/products first, then parse
non-normalized fields from `dt.raw_data` (the original ingested JSON payload):

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
| summarize Count = count(), by: {event.provider, product.vendor, product.name, finding.type}
| sort Count desc
```

**Placeholders:**

- `<PROVIDER>` — exact `event.provider` string from the discovery query above; it must be a provider that carries `dt.raw_data` (e.g. `Amazon GuardDuty`; Dynatrace-native `OneAgent` detections carry none).
- `<field-a>`, `<field-b>` — top-level key names in the provider's raw JSON payload, e.g. `region` and `source` for GuardDuty; keys vary by source schema. Inspect one payload first (`… | filter event.provider == "<PROVIDER>" | fields dt.raw_data | limit 1`) and copy the exact keys, case included. Keep the backticks around each key.

```dql-template
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
| filter event.provider == "<PROVIDER>"
| parse dt.raw_data, "JSON:raw"
| fields timestamp, finding.id, finding.title, raw[`<field-a>`], raw[`<field-b>`]
| limit 100
```

---

## Cross-Provider Summary Pattern (all finding types)

For a unified summary across detections and other finding types, use the canonical cross-provider query in
[all-security-events.md § Canonical Cross-Provider Query](all-security-events.md#canonical-cross-provider-query)
(it applies the SD, compliance-FAILED, and double-counting guards). Scope it to detections with
`filter event.type == "DETECTION_FINDING"` — `event.type` is then constant, so group by `finding.type` in its place. **The severity split is required** in every cross-provider detection summary: add these four `countIf` columns inside the `summarize { … }` next to the canonical collectors (do not drop any of them):

```dql-snippet
    Critical = countIf(dt.security.risk.level == "CRITICAL"),
    High = countIf(dt.security.risk.level == "HIGH"),
    Medium = countIf(dt.security.risk.level == "MEDIUM"),
    Low = countIf(dt.security.risk.level == "LOW"),
```

Narrow to a provider via
[§ Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type).

---

## Single-Finding Drill-Down Pattern

For a specific `finding.id`, `scan.id`, or title substring. Uses `append` to combine a windowed external query with a
fixed-1h Dynatrace query, sorted latest first.

**Placeholders** (dashboard-variable style `${…}`, substitute literally before running):

- `${timeRange}` — look-back duration with unit, e.g. `24h`, `7d` (used as `from:now()-24h`; a bare number fails).
- `${findingID}`, `${scanID}` — exact id strings, e.g. `A-18NMJSIF` (RAP); format is provider-specific (see [data-model.md § Finding ID Format Cheatsheet](data-model.md#finding-id-format-cheatsheet)). The literal `ALL` switches that filter off. Get ids from any detection row's `finding.id` / `scan.id`.
- `${title}` — case-sensitive substring of `finding.title`, `scan.title` or `event.description`, e.g. `injection`; `ALL` switches it off.
- `${maxResults}` — integer row cap, e.g. `100`.
- Keep the double quotes around the string placeholders (they are DQL string literals) and escape any `"` or `\` inside the value; do not quote `${timeRange}` or `${maxResults}`. "Expression is always true/false" warnings on the constant comparisons (e.g. `"ALL"=="ALL"`) are expected.

```dql-template
fetch security.events, from:now()-${timeRange}
| filterOut (event.provider == "Dynatrace" or product.vendor == "Dynatrace") and event.type != "DETECTION_FINDING"
| filter ("${findingID}"=="ALL" or finding.id == "${findingID}")
| filter ("${scanID}"=="ALL" or scan.id == "${scanID}")
| filter ("${title}"=="ALL" or contains(finding.title, "${title}")
                            or contains(scan.title, "${title}")
                            or contains(event.description, "${title}"))
| append [
    fetch security.events, from:now()-1h
    | filter (event.provider == "Dynatrace" or product.vendor == "Dynatrace") and event.type != "DETECTION_FINDING"
    | filter ("${findingID}"=="ALL" or finding.id == "${findingID}")
    | filter ("${scanID}"=="ALL" or scan.id == "${scanID}")
    | filter ("${title}"=="ALL" or contains(finding.title, "${title}")
                                or contains(scan.title, "${title}")
                                or contains(event.description, "${title}"))
  ]
| sort timestamp desc
| limit ${maxResults}
```

---

## Detection Workflows

### Simple detection count ("how many?")

For "How many detections do I have?" / "How many CRITICAL?", deliver total + per-risk-level breakdown in **one query**
with `countIf`. Do **not** group by `event.provider` or `product.name` — for a simple count they obscure the
primary number and inflate the result set.

```dql-snippet
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| summarize {
    Total = count(),
    Critical = countIf(dt.security.risk.level == "CRITICAL"),
    High     = countIf(dt.security.risk.level == "HIGH"),
    Medium   = countIf(dt.security.risk.level == "MEDIUM"),
    Low      = countIf(dt.security.risk.level == "LOW"),
    AffectedObjects = countDistinctExact(object.id)
  }
```

If the user also asks "by provider" / "by product", run a **second** query (grouped `by: {event.provider, dt.security.risk.level}`)
rather than merging a combined `by:` into the count query. On `Total == 0`, re-run sequentially at `24h` and report the wider window.

### New findings within a time window (UC-G2 for detections)

Filter `finding.time.created` (a string timestamp — compare via `toTimestamp()`) to scope to genuinely new arrivals:

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
| filter toTimestamp(finding.time.created) > now() - 24h
| summarize findings=count(), by:{event.provider, dt.security.risk.level, finding.type}
| sort findings desc
```

This works for **all** `*_FINDING` types (`VULNERABILITY_FINDING`, `DETECTION_FINDING`, `COMPLIANCE_FINDING`). For DT RVA,
filter on `vulnerability.resolution.change_date` instead (see
[vulnerabilities-lifecycle.md](vulnerabilities-lifecycle.md#new-vulnerabilities-in-the-last-24h--7-days-uc-v3)).

### Detections by finding type (UC-D3)

`finding.type` is a **vendor-original free-form string** (not a normalized enum): discover live values first, then
use a case-insensitive substring match.

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
| summarize Count=count(), by:{finding.type, event.provider}
| sort Count desc
```

Filter for a specific type — match both `finding.type` and `finding.title`:

```dql
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter contains(finding.type, "sql", caseSensitive:false) OR contains(finding.title, "sql", caseSensitive:false)
| fieldsKeep timestamp, "dt.smartscape*",
         event.provider, finding.title, dt.security.risk.level,
         object.name, object.type, event.description
| sort timestamp desc
```

### Detections over time (grouped by day or hour)

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
| summarize detections = count(),
            by: {day = bin(timestamp, 24h), event.provider, dt.security.risk.level}
| sort day asc, detections desc
```

For an hourly trend change `bin(timestamp, 24h)` → `bin(timestamp, 1h)` (drop `dt.security.risk.level` from `by:` for per-provider counts only).

### Critical detections on a specific entity

Use the entity OR-chain from [common-patterns.md § 5](common-patterns.md#5-wide-entity-scoping-or-chain). Example with a Smartscape host ID:

**Placeholders:**

- `<SMARTSCAPE_HOST_ID>` — Smartscape host id, `HOST-` plus 16 hex characters (e.g. `HOST-D987BB6363604FE6`). Take it from `dt.smartscape.host` of a detection row, or list hosts with `smartscapeNodes "HOST" | fields id, name`. Keep it inside `toSmartscapeId("…")` — `dt.smartscape.host` is a typed Smartscape id and a bare string never matches.
- `<HOST_NAME>` — the `host.name` string of the same host (for Kubernetes-hosted processes it can be a pod name). The `or` keeps events lacking the typed id; drop that line if you only have the id.
- Only `CRITICAL` is shown; change it to `"HIGH"` etc. as needed.

```dql-template
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter dt.security.risk.level == "CRITICAL"
| filter dt.smartscape.host == toSmartscapeId("<SMARTSCAPE_HOST_ID>")
     or host.name == "<HOST_NAME>"
| sort timestamp desc
| fieldsKeep timestamp, "dt.smartscape*",
            event.provider, finding.title, dt.security.risk.level,
            object.id, object.name, object.type, event.description
```

### Detection lookup by ID or title

**Placeholders:**

- `<FINDING_ID>` — exact `finding.id`; format is provider-specific (e.g. `A-18NMJSIF` for RAP), see [data-model.md § Finding ID Format Cheatsheet](data-model.md#finding-id-format-cheatsheet).
- `<TITLE_SUBSTRING>` — case-sensitive substring of `finding.title`, e.g. `CMD injection`.
- `<DESCRIPTION_SUBSTRING>` — case-sensitive substring of `event.description`.
- Plain strings inside the double quotes. The lines are OR-ed: delete the conditions you have no value for (keep at least one; the first remaining condition replaces `or` with `| filter`).

```dql-template
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
| filter finding.id == "<FINDING_ID>"
     or contains(finding.title, "<TITLE_SUBSTRING>")
     or contains(event.description, "<DESCRIPTION_SUBSTRING>")
| sort timestamp desc
| limit 5
```

---

## Best Practices

1. **No dedup or summarize is required** — each row is a discrete detection.
2. **Start with a 2h window; widen only on empty results, sequentially** — see
   [§ Widen-on-empty fallback](#widen-on-empty-fallback-retrieval-queries) (including the wider-window history/analytics exceptions).
3. **Project normalized fields first** — `dt.security.risk.level`, `finding.title`, `object.name`, `event.provider`,
   `product.name` exist across all providers; project provider-specific payloads (`actor.ips`, `threat.attack.*`)
   explicitly when needed. For list/detail queries use the wildcard `"dt.smartscape*"` (covers
   `dt.smartscape_source.{id,type,name}` and the typed domain fields); for entity-grouped summaries add
   `smartscape_node.ids = collectDistinct(dt.smartscape_source.id)` and, where the node type is known, the domain field in
   `by:` (e.g. `dt.smartscape.host` alongside `host.name`).
4. **Correlate with traces and audit events** — for RAP detections on a process load `dt-obs-tracing`; for settings /
   access-control changes around a detection use the audit trail.
5. **Use `product.vendor == "Dynatrace"` for the all-Dynatrace form**; split by `event.provider` / `product.name` only
   when the user asks for one source (§ Provider Routing; RAP keeps the combined filter).
6. **Default to cross-provider scope for attacker / target analytics** — `actor.ips`, `finding.type`,
   `dt.security.risk.level`, `object.id` are SD-canonical across RAP, Automated Detections, and external providers.
   Narrow only on an explicit ask; if results look sparse, run the
   [§ `actor.ips` coverage check](#actorips-coverage-check-when-results-look-sparse) first.
7. **MITRE lives in `threat.attack.*` arrays** (Automated Detections only) — `in(value, array)` membership; parent + all
   sub-techniques needs an OR across `technique.ids` and `subtechnique.ids`.
8. **`finding.action` is the RAP block-vs-monitor signal** (`Blocked` / `Audited` / `Allowlisted`), not `event.outcome`.
9. **`actor.ips` is `ipAddress[]` — `expand` then `ip()` cast** before IP comparisons
   ([§ Top attacker IPs](#top-attacker-ips-last-24h-cross-provider)).
10. **`DETECTION_EXECUTION_SUMMARY` ≠ `DETECTION_FINDING`** — per-rule-run audit vs. per-detection; never mix them in one count query.
11. **Detections have no mute / suppression in events** — explain the limitation rather than inventing fields.
12. **Simple count questions use `countIf` — one row, one query** ([§ Simple detection
    count](#simple-detection-count-how-many)); don't group by provider/product unless asked.
