---
name: dt-sec-ioc-hunting
description: >-
  Hunt threat-intelligence indicators of compromise (IoCs) across Dynatrace
  logs and spans and produce a 0-100 threat-exposure score. Extracts and
  normalizes IoCs — IPs, Domains (hostnames included), URLs, Emails, CVEs,
  File hashes (md5/sha1/sha256), MITRE TTPs — from unstructured reports,
  advisories, advisory URLs, pasted text, or STIX, then hunts them in fetch
  logs and fetch spans. Trigger: hunt these IoCs, am I exposed to this threat,
  check these indicators in my logs and traces, threat exposure report, extract
  IoCs from this advisory URL, search these hashes/domains/IPs in my environment.
  Routes CVE-to-vulnerability and IP/MITRE-to-detection legs to dt-sec-insights.
  Do NOT use for: querying security.events directly (vulnerabilities, detections,
  compliance, THREAT_REPORT — use dt-sec-insights); general log queries not
  tied to an IoC hunt (use dt-obs-logs); general span/trace analysis
  (use dt-obs-tracing); explaining DQL syntax (use dt-dql-essentials).
license: Apache-2.0
---

# IoC Hunting Skill

Hunt indicators of compromise (IoCs) across Dynatrace **logs** and **spans**,
and optionally correlate CVEs and attacker-IPs/MITRE techniques through
`security.events` (routed to **dt-sec-insights**). Produces matched-observable
evidence sets and an AI threat-exposure score (0–100%).

## Universal Best Practices

1. **Always load `dt-dql-essentials` first** — it provides DQL syntax, function
   reference, and query construction patterns required by all hunt templates.
2. **Ground every query in a template** — reference files contain validated DQL
   adapted from the Dynatrace Threat Exposure Analysis dashboard. Do not improvise
   hunt queries; modify only the IoC arrays and time window.
3. **Use indexed log prefiltering for broad hunts** — in log hunts, generate literal
   `matchesPhrase(content, "<ioc>")` clauses before using `contains` to populate
   matched-observable columns. Do not start unscoped log hunts with raw
   `iAny(contains(content, allObservables[]))`.
4. **Chunk large log IoC sets** — do not generate one DQL query with hundreds of
   `matchesPhrase` clauses. Split large IoC lists into smaller chunks (default 25
   IoCs; 10 for long URLs/emails/hashes or after a query-length failure), run each
   chunk with the same timeframe/scope, and aggregate results outside DQL. A no-match
   conclusion is valid only if every chunk completes cleanly.
5. **Tight windows for logs and spans** — default `from:now()-15m` for unanchored
   hunts. Use event-anchored windows for IoCs derived from timestamped
   detections/logs/events. Widen only on approval (see `timeframe-gating.md`).
6. **Never send CVE or MITRE TTPs to logs/spans** — they have no matching field there.
   Route them to `dt-sec-insights` (`threat-intelligence.md`).
7. **Emails and file hashes have no span home** — logs only (`hunt-logs.md`).
8. **Hostnames fold into Domains** — there is no `threat.observables.hosts` field.
   Hostname IoCs belong in the Domains array.
9. **Report empty results truthfully** — "no matches in the searched window" is a real, useful
   answer; propose widening rather than fabricating evidence.
10. **One-home-per-pattern** — `security.events` legs (VULNERABILITY, DETECTION_FINDING,
   THREAT_REPORT) are exclusively owned by `dt-sec-insights`. Never re-author those
   queries here.
11. **Unscoped hunts are valid for broad discovery** — when the user has only IoCs and
   no entity context, run the hunt without a scope filter. Do not silently add a namespace,
   host, or service filter. `FETCH_EXEC_TIME_LIMIT` on an unscoped hunt is INCONCLUSIVE,
   not no-match. Offer scoped follow-up only if entity context exists or the user explicitly
   provides one.
12. **After primary hunts, extract and re-hunt secondary observables** — before scoring,
   inspect every matched log or span record for additional IPs in proxy/relay headers
   (`X-Forwarded-For`, `Forwarded`, `X-Real-IP`, `True-Client-IP`, `CF-Connecting-IP`,
   `Akamai-True-Client-IP`, etc.) and structured fields (`clientIP`, `src_ip`, `source.ip`,
   `remote_addr`). Deduplicate against already-hunted IPs and re-hunt derived IPs across
   logs, spans, and detection `actor.ips` using the same window and scope. Do this
   automatically — never wait for user prompting. See `secondary-observable-extraction.md`.

## IoC Type → Data Source → Reference

| IoC type | Logs | Spans (inbound + outbound) | security.events |
|---|---|---|---|
| IP | `hunt-logs.md` | `hunt-spans.md` | Detections → **dt-sec-insights** |
| Domain (incl. hostname) | `hunt-logs.md` | `hunt-spans.md` | — |
| URL | `hunt-logs.md` | `hunt-spans.md` | — |
| Email | `hunt-logs.md` | ❌ no span field | — |
| File hash (md5/sha1/sha256) | `hunt-logs.md` | ❌ no span field | — |
| CVE | — | — | Vulnerabilities → **dt-sec-insights** |
| MITRE TTP | — | — | Detections → **dt-sec-insights** |

> **Pull IoCs FROM a THREAT_REPORT event** — route to **dt-sec-insights**
> `threat-intelligence.md` § Indicators of Compromise. THREAT_REPORT is a
> `security.events` dataset; this skill does not query it.

## When to Use This Skill

| User says | Load this reference |
|---|---|
| Extract IoCs from an advisory URL / web page | `ioc-intake.md` (agent fetches the page; see intake note) |
| Extract IoCs from a pasted advisory / report / STIX text | `ioc-intake.md` |
| Hunt these IPs/domains/URLs/emails/hashes in logs | `hunt-logs.md` |
| Hunt these IPs/domains/URLs in spans/traces | `hunt-spans.md` |
| Score how exposed my environment is / threat exposure report | `exposure-scoring.md` |
| Cross-evidence correlation — do detection and CVE relate? | **dt-sec-contextualization** → `correlation-and-coverage.md` |
| Pod→node topology (detection on pod, CVE on node) | **dt-sec-contextualization** → `correlation-and-coverage.md` § Pod→Node Topology |
| Compliance enrichment on matched entities | **dt-sec-insights** → `compliance.md` § Entity Security-Tab View |
| A matched IoC — which threat reports mention it (actor/malware/campaign)? | **dt-sec-contextualization** → `ioc-enrichment.md` |
| Timeframe too short / should I widen the search window? | `timeframe-gating.md` |
| Secondary IPs in evidence (X-Forwarded-For, proxy headers, structured fields) | `secondary-observable-extraction.md` |
| CVEs from this report — am I vulnerable? | Route to **dt-sec-insights** |
| IPs from this report — any detections? | Route to **dt-sec-insights** |
| MITRE techniques from this report — any detections? | Route to **dt-sec-insights** |

## Related Skills

| Skill | Role |
|---|---|
| `dt-dql-essentials` | **Load first.** Core DQL syntax, functions, query patterns. |
| `dt-sec-insights` | `security.events` — vulnerabilities, detections, THREAT_REPORT IoC extraction. |
| `dt-sec-contextualization` | Cross-evidence correlation, pod→node topology, per-entity enrichment, compliance enrichment on matched entities, and IoC→threat-report attribution (`ioc-enrichment.md`). Load after hunt legs complete. |
| `dt-obs-logs` | Generic log exploration not tied to IoC hunting. |
| `dt-obs-tracing` | Generic span/trace analysis not tied to IoC hunting; span field semantics. |
