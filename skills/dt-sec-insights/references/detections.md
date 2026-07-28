# Detection Queries — `security.events`

Runtime Application Protection (RAP) detections, Automated Detection rules, and
external provider detections.

> **Cross-references:** field reference → [data-model.md § Detection Fields](data-model.md#detection-fields-detection_finding) · entity
> scoping OR chain, sem-dict filter, default summarization →
> [common-patterns.md](common-patterns.md).

> **`DETECTION_FINDING` is the only event type fully covered by the
> cross-provider summary pattern for both Dynatrace and external sources.** The
> canonical vendor filter (`product.vendor != "Dynatrace" or event.type=="DETECTION_FINDING"`)
> lets DT RAP / Automated Detections through. For vulnerabilities and compliance,
> pair the cross-provider summary with the Dynatrace RVA snapshot pattern or the
> Dynatrace SPM snapshot pattern.

> **No state-report pattern.** Detection findings are **one-shot events**. Each
> detection arrives as a single `DETECTION_FINDING` row — no dedup or
> vulnerability-level summarize required.

> **RAP event-type caveat.** Most RAP examples use `DETECTION_FINDING`, but some
> tenants expose RAP rows as `SECURITY_EVENT`. For broad RAP/critical-detection
> summaries, include both event types and scope by
> `product.name == "Runtime Application Protection"`:
> `in(event.type, {"DETECTION_FINDING","SECURITY_EVENT"})`.

> **No mute / dismiss / suppress in `security.events`.** Detections have no
> equivalent of `vulnerability.mute.*` — there's no per-finding lifecycle
> tracked in DQL. Suppression happens UI-side (Threats & Exploits app
> filters) or at OneAgent ingest time (Application Protection allowlist
> rules — see § RAP Action / Block-vs-Monitor); neither writes to
> `security.events`. If asked "show me dismissed detections," explain the
> data isn't there.

> **Two DT-native event types from Automated Detections.** Beside
> `DETECTION_FINDING`, threat-detection-service also emits
> `DETECTION_EXECUTION_SUMMARY` — one audit row per rule run with scan stats
> and status. Use it to answer "did my rule fire? how often? did it succeed?"
> See § Automated Detections — Execution Summary below.

---

## Contents

- [Provider Routing](#provider-routing)
- [All Dynatrace-Generated Detections (canonical)](#all-dynatrace-generated-detections-canonical)
  - [Widen-on-empty fallback (retrieval queries)](#widen-on-empty-fallback-retrieval-queries)
  - [Latest RAP detections — current window (both event types)](#latest-rap-detections--current-window-both-event-types)
  - [Automated Detections (custom / built-in rules)](#automated-detections-custom--built-in-rules)
  - [Critical Dynatrace detections grouped by affected host (24h)](#critical-dynatrace-detections-grouped-by-affected-host-24h)
- [RAP: Attack-Type & Action Workflows](#rap-attack-type--action-workflows)
  - [Attack-type breakdown](#attack-type-breakdown)
  - [Blocked vs. monitored breakdown](#blocked-vs-monitored-breakdown)
  - [Top attacker IPs — cross-provider](#top-attacker-ips-last-24h-cross-provider)
  - [Filter detections by an IoC IP list](#filter-detections-by-an-ioc-ip-list-cross-provider)
  - [Same source IP attacking multiple targets — cross-provider](#same-source-ip-attacking-multiple-targets-cross-provider)
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
- [Repeated Detections — Frequency-of-Occurrence](#repeated-detections--frequency-of-occurrence)
- [Cross-Provider Summary Pattern (all finding types)](#cross-provider-summary-pattern-all-finding-types)
- [Single-Finding Drill-Down Pattern](#single-finding-drill-down-pattern)
- [Detection Workflows](#detection-workflows)
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
| **RAP only** (Runtime Application Protection via OneAgent) | `in(event.type, {"DETECTION_FINDING","SECURITY_EVENT"}) AND product.name == "Runtime Application Protection"` |
| Automated Detections only (custom / built-in rules) | `event.type == "DETECTION_FINDING" AND event.provider == "Dynatrace Automated Detections"` |
| AutomationEngine (workflow detections) | `event.type == "DETECTION_FINDING" AND event.provider == "AutomationEngine"` |
| All external providers | `event.type == "DETECTION_FINDING"` + `filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"` |

External detections all share the `DETECTION_FINDING` event type — query them together with
the catch-all above. To narrow to one external provider, use the shared provider-scoping
pattern in
[all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type).
Default to the unified Dynatrace form (`product.vendor == "Dynatrace"`) — only split when the
user specifically asks for RAP-only, Automated-Detections-only, or a specific provider.

> **RAP filter — both forms are current and equivalent.** On every RAP
> detection, `event.provider == "OneAgent"` AND `product.name == "Runtime
> Application Protection"` are both populated (`product.vendor == "Dynatrace"`
> as well). The two are independent SD fields — neither subsumes the other.
> Either filter works on its own; this skill prefers
> `product.name == "Runtime Application Protection"` as the canonical form
> because it matches the official Dynatrace docs naming. Don't OR them or AND
> them — that's redundant.

---

## All Dynatrace-Generated Detections (canonical)

```dql
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter product.vendor == "Dynatrace"
```

### Widen-on-empty fallback (detection queries)

**Default to `from:now()-2h` for all unqualified detection queries** — "how many detections do I have?",
"detections by severity", "show me detections", "list recent attacks", "by attack type / entity / provider".
This matches the Threats & Exploits app default. Run the fallback **only when the 2h query returns
zero rows**; do not pre-emptively widen. If the user explicitly asks for a time window (for example
"last 24 hours" or "last 7 days"), honor that explicit window.

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
| filter product.vendor == "Dynatrace"
```

If 24h is still empty (sparse tenant, new environment), widen once more to `from:now()-7d` before
concluding "no detections." **Report the wider window used** when you fall back, e.g. "no
detections in the last 2h; widening to 24h returned X results."

> **Never run the 2h and 24h queries in parallel.** The 24h window is a *sequential* fallback —
> trigger it only when the 2h query returns zero rows. Running both upfront wastes ~10× the
> data budget and misleads the answer (two windows → two result sets that must be reconciled).

> **History and analytics queries use wider windows only when the user asks for that history** —
> top attacker IPs over 24h, MITRE breakdowns over 24h or 7d, detections-grouped-by-day over 7d,
> and critical-grouped-by-host over 24h are valid when the prompt includes that timeframe. Without
> an explicit timeframe, start at `2h` and widen only on empty.

### Latest RAP detections — current window (both event types)

RAP detects code-level attacks via OneAgent (`finding.type` = attack class,
`finding.action` = response). RAP emits `DETECTION_FINDING` on most tenants but
`SECURITY_EVENT` on some — **include both**; never narrow to `DETECTION_FINDING` alone
for RAP. Canonical "show me current RAP attacks" recipe:

```dql
fetch security.events, from:now()-2h
// Include both RAP event types — never narrow to DETECTION_FINDING alone for RAP
| filter in(event.type, {"DETECTION_FINDING", "SECURITY_EVENT"})
| filter product.name == "Runtime Application Protection"
| fields timestamp, finding.id, finding.title, dt.security.risk.level,
         finding.type, finding.action, actor.ips, actor.geo.country.name,
         object.id, object.name, object.type,
         "dt.smartscape*", "dt.entity*"
| sort timestamp desc
| limit 100
```

If zero rows are returned, widen to `from:now()-24h` (widen-on-empty rule — see § Widen-on-empty fallback).

### Automated Detections (custom / built-in rules)

```dql
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter event.provider == "Dynatrace Automated Detections"
| fields timestamp, "dt.smartscape*", "dt.entity*",
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
  }, by: {host.name, dt.smartscape.host, dt.entity.host}
| sort detections desc
| limit 25
```

---

## RAP: Attack-Type & Action Workflows

RAP detects code-level attacks via OneAgent. `finding.type` is the canonical
attack class; `finding.action` carries OneAgent's response.

### Attack-type breakdown

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
     AND product.name == "Runtime Application Protection"
| summarize {
    Detections = count(),
    Critical = countIf(dt.security.risk.level == "CRITICAL"),
    Blocked = countIf(finding.action == "Blocked"),
    Audited = countIf(finding.action == "Audited"),
    Allowlisted = countIf(finding.action == "Allowlisted"),
    AffectedProcesses = countDistinctExact(dt.entity.process_group),
    smartscape_node.ids = collectDistinct(dt.smartscape_source.id)
  }, by: {AttackType = finding.type}
| sort Detections desc
```

### Blocked vs. monitored breakdown

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
     AND product.name == "Runtime Application Protection"
| summarize Detections = count(),
            by: {Action = finding.action,
                 AttackType = finding.type,
                 Severity = dt.security.risk.level}
| sort Detections desc
```

> **`finding.action` enum**: `Blocked` (OneAgent stopped the request),
> `Audited` (Monitor mode — detected but not stopped), `Allowlisted` (an
> Application Protection rule explicitly allowed it). If `finding.action` is
> null on a row, the OneAgent version may not yet emit it — fall back to
> `event.outcome` if present, or treat as `Audited` for triage purposes.

### Top attacker IPs (last 24h, cross-provider)

> **Default to cross-provider scope for attacker analytics.** `actor.ips` is
> populated across RAP and external detection sources. Don't narrow to
> `product.name == "Runtime Application Protection"` unless the user explicitly
> asks (see § Scope variants below).

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

> **Why `expand` + `ip()` cast.** `actor.ips` is `ipAddress[]` — one row may
> carry IPv4 + IPv6 or a proxy chain. `expand` splits multi-IP rows into one
> row per IP so each ranks independently. The `ip(actor.ips)` cast types the
> value as a proper IP address, so downstream `==`, range, and CIDR
> comparisons type-check correctly.

> **Mixed provenance.** The same IP appearing under multiple `Providers`
> (e.g. RAP + an external detection source) is signal — perimeter and in-process detection
> agreeing on an attacker. Same IP in only one provider is normal — different
> providers see different traffic.

### Filter detections by an IoC IP list (cross-provider)

Use this when you have a **known list of attacker IPs** (from a threat report, STIX
bundle, or advisory) and want to check whether any of them appeared as attackers in
your environment. Distinct from the `join`-based correlation in
`threat-intelligence.md` (which correlates against IPs already ingested as
`THREAT_REPORT` events) — this query works directly against a pasted/extracted IP list.

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
| filter isNotNull(actor.ips)
| expand actor.ips
| filter in(ip(actor.ips), array(toIp("<ip1>"), toIp("<ip2>")))
| fields timestamp, finding.id, finding.title, dt.security.risk.level,
         finding.type, finding.action, actor.ips, actor.geo.country.name,
         object.id, object.name, object.type, event.provider, product.name
| sort timestamp desc
| limit 100
```

> **Why `ip()`/`toIp()`, not `toString()`.** Typed IP comparison canonicalizes
> IPv6 representations and supports CIDR/range predicates. String equality silently
> misses the same IPv6 address in a different notation. Always use the typed form
> in skill templates; `toString()` string comparison is only appropriate when you
> know the IoC list is IPv4-only.

Zero matches is a valid, meaningful answer ("none of the IoC IPs attacked us in
this window") — report it truthfully with the window used.

### Same source IP attacking multiple targets (cross-provider)

Fan-out pattern: a single IP hitting many distinct targets, not the same target
many times. Strong signal for reconnaissance / wide-scan campaigns. Take the **Top
attacker IPs** query above, add `SampleTargets = arraySlice(collectDistinct(object.name), from: 0, to: 10)`
to the summarize, then append:

```dql-snippet
| filter DistinctTargets >= 2
| fieldsAdd DurationMin = round((toLong(LastSeen) - toLong(FirstSeen)) / 1000000000.0 / 60, decimals: 1)
| sort DistinctTargets desc, Detections desc
| limit 25
```

`DistinctTargets >= 2` is the threshold — raise to `>= 5` for wide-scan recon. Long
`DurationMin` + high `Detections` = slow-burn; short = automated burst. Groups by
`object.id` (cross-provider target id), not `dt.entity.process_group` (null for external).

### Scope variants (narrow only when the user explicitly asks)

Apply on top of either query above; never apply by default.

| User intent | Add this filter |
|---|---|
| "In-application attacks" / "RAP" / "OneAgent attacks" | `AND product.name == "Runtime Application Protection"` |
| "External tools" / "perimeter" / "cloud security findings" | `AND product.vendor != "Dynatrace"` |
| A specific external provider | See [all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type) |

### `actor.ips` coverage check (when results look sparse)

Not every provider populates `actor.ips` — some carry the IP only in
`dt.raw_data`. Run this first if the cross-provider query looks empty:

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

For providers with `HasIPs == 0`, the attacker IP (if any) is in
`dt.raw_data` — parse with `parse dt.raw_data, "JSON:raw"` and project the
relevant key.

> **Enrichment context.** `actor.ips` is enrichable via the **Security
> Enrichment** app (AbuseIPDB / VirusTotal / custom threat-intel APIs) —
> enrichment happens client-side in the Threats & Exploits app, not in
> `security.events`. For queries, group by the cast IP and resolve reputation
> outside the DQL pipeline. Geo fields (`actor.geo.country.name`,
> `actor.geo.city.name`, `actor.geo.continent.name`) are marked Experimental
> and may be null when enrichment isn't configured.

### RAP attack drilldown (specific attack on a process)

```dql-template
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
     AND product.name == "Runtime Application Protection"
     AND contains(lower(finding.type), "sql")
| filter dt.entity.process_group == "PROCESS_GROUP-XXXXXXXXXXXXXXXX"
| sort timestamp desc
| limit 50
| fieldsKeep timestamp, "dt.smartscape*", "dt.entity*", "dt.source*",
            finding.id, finding.type, finding.action, finding.title,
            actor.ips, actor.geo.country.name,
            dt.security.rap.target.id, dt.security.rap.target.type, dt.security.rap.target.name,
            object.id, object.name, object.type, url.path
```

> RAP-specific drilldown into entry-point payloads, user-controlled inputs,
> and sink-code details lives in product-emitted fields outside the SD
> stable namespace. Use the Threats & Exploits app for the full attack
> reconstruction; SD-stable fields above are sufficient for "which attack,
> from whom, hitting which target" queries.

`finding.type` is a **vendor-original free-form string** — not a normalized enum. RAP emits
display strings whose exact form can differ across OneAgent versions; observed values:
`SQL injection`, `CMD injection`, `JNDI injection`, `SSRF`. Use `contains(lower(finding.type), …)`
rather than exact-match literals. JNDI/SSRF are Java-only; SQL/command/path injection cover
Java + .NET + Go. Discover active values on any tenant with the summarize query in UC-D3 below.

---

## Automated Detections — MITRE ATT&CK Workflows

Automated Detections rules can be tagged with MITRE ATT&CK classifications
via the canonical SD namespace `threat.attack.*` (technique, sub-technique,
tactic — separate arrays). This is the only DT-native source that emits
MITRE in `security.events` — RAP findings don't carry MITRE tags directly.
Full field reference (types, examples, companion `.names` / `.version`) →
[data-model.md § DT Automated Detections](data-model.md#dt-automated-detections-eventprovider--dynatrace-automated-detections).

> **Query rules that affect DQL:** use `in(value, array)` for exact-ID membership
> (fallback: `expand technique = threat.attack.technique.ids | filter technique == "T1078"`).
> Sub-technique IDs (`T1059.003`) live in their **own** array — querying
> `threat.attack.technique.ids` for them won't match. "Parent + all sub-techniques"
> requires an OR across both arrays (see the parent+sub query below).

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
| fields timestamp, "dt.smartscape*", "dt.entity*",
         detection.title, finding.title, dt.security.risk.level,
         threat.attack.technique.ids, threat.attack.subtechnique.ids, object.name
| sort timestamp desc
```

For a **parent technique + all its sub-techniques** (e.g. T1110 Brute Force +
T1110.001/002/…), OR across both arrays — swap the single-technique filter for:

```dql-snippet
| filter in("T1110", threat.attack.technique.ids)
      OR iAny(startsWith(threat.attack.subtechnique.ids[], "T1110."))
```

### Untagged Automated Detections (rules missing MITRE)

Coverage gap audit — which rules fired but lack MITRE tagging?

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
     AND event.provider == "Dynatrace Automated Detections"
| filter (isNull(threat.attack.technique.ids) OR arraySize(threat.attack.technique.ids) == 0)
     AND (isNull(threat.attack.subtechnique.ids) OR arraySize(threat.attack.subtechnique.ids) == 0)
| summarize Detections = count(),
            Sample = takeFirst(finding.title),
            by: {RuleID = detection.id, Rule = detection.title}
| sort Detections desc
```

---

## Automated Detections — Execution Summary

`DETECTION_EXECUTION_SUMMARY` is a separate event type emitted **per rule
run**. Use it to answer "did my rule fire? did it succeed? how much data did
it scan?" — without scanning the findings stream itself.

> **Filter canonically by `event.provider == "Dynatrace Automated Detections"`**
> for consistency with the findings filter — both `event.provider` and
> `product.name == "Automated Detections"` are populated on every execution
> summary row, so either works on its own. (`product.name` and `event.provider`
> are independent SD fields and don't have to share a value; for Automated
> Detections they happen to convey the same source.)

### Execution status breakdown (last 24h)

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_EXECUTION_SUMMARY"
     AND event.provider == "Dynatrace Automated Detections"
| summarize {
    Runs = count(),
    Success = countIf(execution.status == "SUCCESS"),
    Warnings = countIf(execution.status == "SUCCESS_W_WARNINGS"),
    Failures = countIf(execution.status == "FAILURE"),
    TotalEventsWritten = sum(execution.events_written),
    TotalRecordsScanned = sum(execution.scanned_records)
  }, by: {RuleID = detection.id, Rule = detection.title}
| sort Failures desc, Warnings desc, Runs desc
```

> **Field names for execution stats** (`execution.status`,
> `execution.events_written`, `execution.scanned_records`,
> `execution.scanned_bytes`, `execution.analysis_timeframe_start` /
> `_end`) are the SD-normalized forms; raw events may carry the
> Java-camelCase names (`eventsWritten`, `scannedRecords`, etc.). If a query
> returns nulls, inspect a single row first to confirm casing.

### Rules that have not fired in the last 24h

Take the execution-status query above, reduce its summarize to
`{ Runs = count(), Findings = sum(execution.events_written) }` keyed by
`{detection.id, detection.title}`, then append `| filter Findings == 0 | sort Runs desc`.
This answers "is my detection rule actually catching anything?" — `Findings == 0` over a
representative window means either the threat hasn't occurred or the rule is mis-tuned.

---

## External Detection Queries

Ingested from external cloud-security and SIEM/SOAR tools via OpenPipeline — same
`DETECTION_FINDING` event type as Dynatrace-native detections, different
`event.provider` / `product.vendor`.

**All external detections (not Dynatrace-generated):**

```dql
fetch security.events
| filter event.type == "DETECTION_FINDING"
| filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
```

### Threats & Exploits (T&E) App Compatibility

To return findings the way the **Threats & Exploits app** displays them, apply the
9-field SD-compliance filter (`event.id`, `event.provider`, `finding.type`,
`finding.id`, `finding.time.created`, `finding.title`, `dt.security.risk.level`,
`object.id`, `object.type` all `isNotNull`). Findings missing any are hidden or
rendered incomplete. The canonical filter (applicable to any `*_FINDING` type) lives
in [all-security-events.md § Semantic-Dictionary Fields](all-security-events.md#semantic-dictionary-fields)
— scope it to detections with `filter event.type == "DETECTION_FINDING"`. **Omit it**
when investigating *why* findings are missing from the app (query unfiltered to see
the non-compliant rows).

**Time-bounded detections** — add the SD-compatibility filter plus a
`finding.time.created` bound (it's a string — wrap with `toTimestamp()`):

```dql-snippet
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter <SD-compatibility filter — see all-security-events.md § Semantic-Dictionary Fields>
| filter toTimestamp(finding.time.created) > now()-2h
```

### Detections from a specific external provider

**Step 1 — discover the active provider strings** (if not already known):

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
| summarize detections=count(), by:{event.provider, product.vendor, product.name}
| sort detections desc
```

**Step 2 — scope with exact match** once the provider strings are confirmed (prefer
exact equality over fuzzy `contains`). The general scoping pattern lives in
[all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type);
the detection-specific point is that **one provider may arrive via two ingestion paths**
(e.g. direct and via AWS Security Hub) — combine both with `OR`.

**Named example — Amazon GuardDuty** (two ingestion paths in the same tenant; provider
strings verified via the discovery query above):

```dql
fetch security.events, from:now()-24h
// Exact match both GuardDuty ingestion paths
| filter (event.provider == "Amazon GuardDuty")
      OR (event.provider == "AWS Security Hub" AND product.name == "GuardDuty")
| filter event.type == "DETECTION_FINDING"
| filter isNotNull(finding.id) AND isNotNull(object.id) AND isNotNull(dt.security.risk.level)
| summarize {
    Detections = count(),
    AffectedObjects = countDistinctExact(object.id),
    SampleTitles = collectDistinct(finding.title, maxLength: 5),
    MaxScore = takeMax(dt.security.risk.score),
    AffectedResourceTypes = collectDistinct(object.type)
  }, by: {event.provider, dt.security.risk.level, finding.type}
| sort MaxScore desc, Detections desc
```

The query keys off the generic `object.*` namespace so it works for any provider. For
hyperscaler-specific resource identifiers (cloud resource IDs, ARNs, account /
subscription / project scoping), use the dedicated AWS / Azure / GCP skills — this
skill stays provider-neutral. For attacker-IP / sign-in / WAF detections, the
cross-provider `actor.ips` pattern (§ Top attacker IPs) already covers external
sources — don't narrow to one provider unless the user asks.

### Custom / non-normalized ingest

Custom ingest sources arrive as `DETECTION_FINDING` with their own field values.
Discover the populated providers/products first, then parse any non-normalized
fields from `dt.raw_data` (the original ingested JSON payload):

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
| summarize Count = count(), by: {event.provider, product.vendor, product.name, finding.type}
| sort Count desc
```

```dql-snippet
// project non-normalized fields from the raw payload (key names vary by source schema)
| parse dt.raw_data, "JSON:raw"
| fields timestamp, raw[`<field-a>`], raw[`<field-b>`], raw[`<message>`]
```

---

## Repeated Detections — Frequency-of-Occurrence

Detections are one-shot, but the **same kind of detection** can repeat —
either because the same `finding.id` re-arrives (rare; some external
providers re-ingest unchanged findings), or more typically because the same
attack pattern (`finding.type` / `detection.id` for
Automated Detections) hits the same target repeatedly.

### Repeated attack patterns by source IP + attack type (cross-provider)

Distinct from "Same IP attacking multiple targets" — group by **both** IP and attack
type to surface the same kind of attack hitting infrastructure repeatedly (an IP probing
for SQL injection across the fleet, or repeatedly triggering one external rule). Take the
**Top attacker IPs** query, change its `by:` to `{SourceIP = ip, AttackType = finding.type}`,
then append:

```dql-snippet
| filter Detections >= 5
| fieldsAdd DurationMin = round((toLong(LastSeen) - toLong(FirstSeen)) / 1000000000.0 / 60, decimals: 1)
| sort Detections desc
```

`Detections >= 5` is a noise-floor heuristic — adjust to taste. Long duration + high count =
slow-burn campaign; short = automated bursts. To narrow to one source, apply a scope variant
from § Top attacker IPs.

### Same rule / attack firing on the same object repeatedly (cross-provider)

Groups by `finding.type` (cross-provider attack/rule classification) and
`object.id` (cross-provider target) to surface "this kind of detection
keeps hitting the same target." Works for RAP attacks repeating against a
process group, Automated Detections rules re-firing on a K8s pod, and
external findings re-arriving against the same
cloud resource.

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
| filter isNotNull(finding.type) AND isNotNull(object.id)
| summarize {
    Fires = count(),
    Providers = collectDistinct(event.provider),
    Products = collectDistinct(product.name),
    SampleTitle = takeFirst(finding.title),
    FirstSeen = takeMin(timestamp),
    LastSeen = takeMax(timestamp)
  }, by: {
    Kind = finding.type,
    ObjectID = object.id,
    ObjectName = object.name,
    ObjectType = object.type
  }
| filter Fires >= 3
| fieldsAdd DurationHours = round((toLong(LastSeen) - toLong(FirstSeen)) / 1000000000.0 / 3600, decimals: 1)
| sort Fires desc
| limit 50
```

`Fires >= 3` is a noise-floor — adjust to taste. **Long duration + high
fires** suggests an unaddressed persistent issue (root cause not
remediated). **Short duration + high fires** suggests a tuning issue (noisy
rule or attack pattern).

To narrow to a specific target type (e.g. "only pods"):

```dql-snippet
| filter object.type == "KUBERNETES_POD"   // SD-normalized form
   OR object.type == "k8spod"              // KSPM analyzer code (lowercase)
```

To narrow to a specific source, apply a scope variant from § Top attacker
IPs (RAP-only / external-only / single-provider).

---

## Cross-Provider Summary Pattern (all finding types)

For a unified summary across detections + other finding types and providers, use the canonical
cross-provider query in
[all-security-events.md § Canonical Cross-Provider Query](all-security-events.md#canonical-cross-provider-query)
— it applies the SD, compliance-FAILED, and double-counting guards. Scope it to detections by
adding `filter event.type == "DETECTION_FINDING"`, and narrow to a provider via
[§ Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type).

---

## Single-Finding Drill-Down Pattern

For a specific `finding.id`, `scan.id`, or title substring. Uses `append` to
combine a windowed external query with a fixed-1h Dynatrace query, then sorts
latest first:

```dql-template
fetch security.events, from:now()-${timeRange}
| filter (product.vendor != "Dynatrace" or event.type=="DETECTION_FINDING")
| filter ("${findingID}"=="ALL" or finding.id == "${findingID}")
| filter ("${scanID}"=="ALL" or scan.id == "${scanID}")
| filter ("${title}"=="ALL" or contains(finding.title, "${title}")
                            or contains(scan.title, "${title}")
                            or contains(event.description, "${title}"))
| append [
    fetch security.events, from:now()-1h
    | filter (product.vendor == "Dynatrace" and not event.type=="DETECTION_FINDING")
    | filter ("${findingID}"=="ALL" or finding.id == "${findingID}")
    | filter ("${scanID}"=="ALL" or scan.id == "${scanID}")
    | filter ("${title}"=="ALL" or contains(finding.title, "${title}")
                                or contains(scan.title, "${title}")
                                or contains(event.description, "${title}"))
  ]
| sort timestamp desc
| limit ${maxResults}
```

`finding.id` format is provider-specific — match exactly. See
[data-model.md § Finding ID Format Cheatsheet](data-model.md#finding-id-format-cheatsheet).

---

## Detection Workflows

### Simple detection count ("how many?")

For questions like "How many security detections do I have?" or "How many CRITICAL detections?",
deliver total + per-risk-level breakdown in **one query** using `countIf`. Do **not** group by
`event.provider` or `product.name` — those are detail fields for breakdown and list queries;
for a simple count they obscure the primary number and inflate the result set.

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
// If Total == 0, re-run sequentially with from:now()-24h (widen-on-empty fallback).
// Report the wider window: "no detections in the last 2h; 24h returned X."
```

If the user also asks "by provider" or "by product" in the same prompt, run a **second** query
(grouped `by: {event.provider, dt.security.risk.level}`) — do not merge it into the count query
with a combined `by:` clause.

### New findings within a time window (UC-G2 for detections)

Detections are one-shot events — filter `finding.time.created` to scope to
genuinely new arrivals. `finding.time.created` is a string timestamp; use
`toTimestamp()` for comparison:

```dql
fetch security.events, from:now()-24h
| filter event.type == "DETECTION_FINDING"
| filter toTimestamp(finding.time.created) > now() - 24h
| summarize findings=count(), by:{event.provider, dt.security.risk.level, finding.type}
| sort findings desc
```

This approach (filter on `finding.time.created`) works for **all** `*_FINDING`
event types — `VULNERABILITY_FINDING`, `DETECTION_FINDING`, `COMPLIANCE_FINDING`.
For DT RVA, prefer filtering on `vulnerability.resolution.change_date` instead
(see [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md#new-vulnerabilities-in-the-last-24h--7-days-uc-v3)).

### Detections by finding type (UC-D3)

Filter by `finding.type` to scope to a specific attack category.
`finding.type` is a **vendor-original free-form string** (not a normalized enum) —
always discover the live values first, then use a case-insensitive substring match:

```dql
// Discover active finding types:
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
| summarize Count=count(), by:{finding.type, event.provider}
| sort Count desc
```

```dql
// Filter for a specific type — match both finding.type and finding.title (vendor-original):
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter contains(lower(finding.type), "sql") OR contains(lower(finding.title), "sql")
| fields timestamp, "dt.smartscape*", "dt.entity*",
         event.provider, finding.title, dt.security.risk.level,
         object.name, object.type, event.description
| sort timestamp desc
```

### Detections over time (grouped by day or hour)

```dql
fetch security.events, from:now()-7d
| filter event.type == "DETECTION_FINDING"
| summarize detections = count(),
            by: {day = bin(timestamp, 1d), event.provider, dt.security.risk.level}
| sort day asc, detections desc
```

For an hourly trend by provider, change `bin(timestamp, 1d)` → `bin(timestamp, 1h)`
(drop `dt.security.risk.level` from `by:` if you only want per-provider counts).

### Critical detections on a specific entity

Use the entity OR-chain from
[common-patterns.md § 5](common-patterns.md#5-wide-entity-scoping-or-chain). Example
inline with a Smartscape host ID:

```dql-template
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter dt.security.risk.level == "CRITICAL"
| filter dt.smartscape.host == "<SMARTSCAPE_HOST_ID>"
     or dt.entity.host == "<HOST_ENTITY_ID>"
     or host.name == "<HOST_NAME>"
| sort timestamp desc
| fieldsKeep timestamp, "dt.smartscape*", "dt.entity*", "dt.source*",
            event.provider, finding.title, dt.security.risk.level,
            object.id, object.name, object.type, event.description
```

### Detection lookup by ID or title

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

1. **No dedup or summarize is required** — detection findings are one-shot events;
   each row is a discrete detection.
2. **Start with a 2h window; widen only on empty results, sequentially** — see
   [§ Widen-on-empty fallback](#widen-on-empty-fallback-retrieval-queries) for the
   fallback query and the intentionally-wider history/analytics exceptions.
3. **Project normalized fields first** — `dt.security.risk.level`, `finding.title`,
   `object.name`, `event.provider`, `product.name` (exist across all providers);
   project provider-specific payloads (`actor.ips`, `threat.attack.*`) explicitly when
   needed. For list/detail queries use the wildcard block `"dt.smartscape*",
   "dt.entity*", "dt.source*"`; for entity-grouped summaries add
   `smartscape_node.ids = collectDistinct(dt.smartscape_source.id)`, and where the node
   type is known include the domain field in `by:` (e.g. `dt.smartscape.host` alongside
   `dt.entity.host`).
4. **Correlate with traces and audit events** — for RAP detections on a process, load
   `dt-obs-tracing` for representative traces; for settings / access-control changes
   around a detection, use the audit trail.
5. **Use `product.vendor == "Dynatrace"` for the all-Dynatrace form**; split by
   `event.provider` / `product.name` only when the user asks for one source.
6. **Default to cross-provider scope for attacker / target analytics** — `actor.ips`,
   `finding.type`, `dt.security.risk.level`, `object.id` are SD-canonical across RAP,
   Automated Detections, and external providers. Narrow to a source only on an explicit
   ask; if results look sparse, run the `actor.ips` coverage check first
   ([§ `actor.ips` coverage check](#actorips-coverage-check-when-results-look-sparse)).
7. **RAP filter is `product.name == "Runtime Application Protection"`** (canonical per
   docs); `event.provider == "OneAgent"` is equivalent — pick one, don't OR/AND them.
8. **MITRE lives in `threat.attack.*` arrays** (Automated Detections only) — use
   `in(value, array)` membership; parent + all sub-techniques needs an OR across
   `threat.attack.technique.ids` and `threat.attack.subtechnique.ids`. Field reference →
   [data-model.md § DT Automated Detections](data-model.md#dt-automated-detections-eventprovider--dynatrace-automated-detections).
9. **`finding.action` is the RAP block-vs-monitor signal** — `Blocked` / `Audited` /
   `Allowlisted`; don't conflate with `event.outcome`.
10. **`actor.ips` is `ipAddress[]` — `expand` then `ip()` cast** before IP comparisons;
    see [§ Top attacker IPs](#top-attacker-ips-last-24h-cross-provider).
11. **`DETECTION_EXECUTION_SUMMARY` ≠ `DETECTION_FINDING`** — per-rule-run audit vs.
    per-detection; don't mix them in one count query.
12. **Detections have no mute / suppression in events** — explain the limitation rather
    than inventing fields (suppression is UI-side or RAP-ingest-side).
13. **Simple count questions use `countIf` — one row, one query** ([§ Simple detection
    count](#simple-detection-count-how-many)); don't group by provider/product unless
    asked.
