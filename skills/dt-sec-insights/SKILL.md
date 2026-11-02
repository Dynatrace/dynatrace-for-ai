---
name: dt-sec-insights
description: >-
  Query Dynatrace security.events with DQL: vulnerabilities, threat
  detections, compliance posture. Covers Dynatrace-native Runtime
  Vulnerability Analytics (RVA — CVEs, reachability, exploit), Runtime
  Application Protection (RAP), Automated Detections, Security Posture
  Management (KSPM/CSPM), Dynatrace vulnerability feed, external tools.
  Trigger: "open critical vulnerabilities", "vulnerable functions in use and
  exposed", "top vulnerable libraries / K8s workloads", "vulnerabilities on
  this host", "CIS/DORA compliance pass rate", "SQL injection
  detections", "does Dynatrace know CVE-X / how is it fixed", "what is DTV-…",
  "new in the feed", "exploited in the wild (KEV)". Do NOT use for scan
  coverage, mapping external findings to workloads / entity mapping, or RVA
  verification of external findings (use dt-sec-contextualization), explaining
  DQL (dt-dql-essentials), Davis problems (dt-obs-problems), logs
  (dt-obs-logs), tracing (dt-obs-tracing), service metrics (dt-obs-services),
  platform audit (dt-platform).
license: Apache-2.0
---

# Security Insights Skill

Query and analyze Dynatrace security data in `security.events` using DQL. Events
come from **Dynatrace-native sources** (RVA, RAP, Automated Detections, SPM) or
**external products** ingested via integrations (AWS Security Hub, Amazon
GuardDuty, GitHub Advanced Security, Snyk, Qualys, Tenable, and more).

## What This Skill Covers

- **Vulnerability management** — open CVEs on running code from DT-native RVA
  (risk-ranked with Dynatrace Security Score and the four-dimension runtime
  assessment: vulnerable-function-in-use, public network exposure, reachable
  data assets, public exploit available) plus external SCA / SAST / image scanners.
- **Compliance posture** — DT-native KSPM (Kubernetes-only: CIS, DORA, NIST,
  STIG, Security Essentials) plus CSPM/VSPM and external compliance/posture providers.
- **Runtime attacks and threats** — DT-native detections (RAP runtime attacks,
  Automated Detections rules) plus external detection providers.
- **Threat intelligence** — external threat-intelligence reports (AlienVault OTX
  pulses, CrowdStrike Falcon Intelligence) with actor / campaign / targeting context
  and indicators of compromise (IOCs); correlate reported IOCs / CVEs / techniques
  against your environment. **Threat intel about the wild — not findings on your
  entities — queried separately.**
- **Vulnerability feed** — the Dynatrace Library Vulnerability Feed lookup table
  (`/dt/security/vulnerabilities/libraries`): curated knowledge about CVEs in library
  ecosystems (npm, PyPI, Maven, Packagist, Go, NuGet) — affected packages and version
  ranges, fix versions, CISA KEV. **Knowledge about the wild, not findings on your
  entities** — it enriches any finding about a **library/third-party component** (RVA: join
  on `vulnerability.external_id`; external: join on the CVE). **Code-level and OS findings
  have no record in this table** (CLV by design; OS records live in a separate feed) — report
  that, never as a gap in the feed.
- **Dashboards / KPIs** — tiles, top-N tables, trend charts.

## Scope Boundary

This skill is **pure security data access and grouping**: filter, aggregate, rank, and
trend `security.events` using only the fields that are in the events. Putting findings in
the context of runtime entities belongs to **dt-sec-contextualization**: Smartscape
resolution (`smartscapeNodes` lookups and joins), runtime context for external findings,
scan coverage, IoC enrichment, verification of external findings against Dynatrace RVA,
and cross-correlation between findings. Typical hand-off: this skill produces the finding
set or ranking, contextualization resolves it to entities.

## When to Use This Skill

✅ **Must-first routing rule:** identify the user's intent first, then load the matching primary reference from the tables below before generating DQL.

**Cross-cutting (any / all finding types)**

| Intent / example | Reference | Pattern |
|---|---|---|
| Security posture / overview across all products (incl. DT-native) | `all-security-events.md` § Broad-Question Query Decomposition | 3-stream decomposition (external+detections `24h` / RVA `30m` / KSPM `1h`), merged; **lead the count summary with KSPM compliance — CIS first** (other standards + RVA + detections beneath) → `compliance.md` § CIS-Primary Standard Summary |
| Findings on a specific entity — direct or related (blast radius) | **dt-sec-contextualization** `entity-enrichment.md` (external arm) · `vulnerabilities-dynatrace.md` § One known entity (RVA arm) · `all-security-events.md` | **Broad entity-security questions must decompose**: external `*_FINDING` by `dt.smartscape_source.id` / `dt.smartscape.*` / `k8s.*` (`24h`) + DT RVA entity scope (`30m`) + DT SPM entity scope (`1h`) |
| When did X first / last appear? since when? when did this last occur? (first seen / last seen) | `common-patterns.md` § First seen / last seen | per-family timestamp choice (`finding.time.created` vs `timestamp`), Recipe A findings / B scans; the window bounds "first seen" — widen it |
| Findings from a specific provider | `all-security-events.md` § Scoping to a Specific Provider | `contains(event.provider \| product.vendor, "<p>", caseSensitive:false)` |
| Which **integrations / tools are sending, reporting or ingesting data** (third-party / external; DT-native excluded) — e.g. "which security integrations are sending us data?" | `all-security-events.md` § Which external integrations are active | external-only enumeration (single query) |
| Which security products are integrated? / what security data do we have? (default: **include DT-native** RVA + KSPM) | `all-security-events.md` § Broad-Question Query Decomposition | 3-stream decomposition; never a single wide `security.events` scan |
| Which products cover a specific entity | **dt-sec-contextualization** `runtime-coverage.md` · `all-security-events.md` | summarize by `product.*`; findings-vs-scans split |

> **Routing tie-breaker:** "integrations / tools **sending, reporting or ingesting** data" (with or without the word "external") is the **external-only single query**. An unqualified "which security products are integrated (incl. Dynatrace)? / are we covered? / what security data do we have? / posture overview" defaults to the **DT-inclusive 3-stream decomposition** (it *must* query DT vulnerabilities and compliance).

**Vulnerabilities (CVE management)**

| Intent / example | Reference | Pattern |
|---|---|---|
| Counts / severity ("how many critical?", by risk + mute status) | `vulnerabilities-dynatrace.md` | RVA snapshot Steps 1–3 |
| Most vulnerable components / hosts / workloads — Dynatrace RVA (rankings) | `vulnerabilities-rankings.md` | Steps 1–3 + `expand` typed `related_entities.<group>.ids`, grouped on the in-event classic id alone, name carried for display (pure `security.events`); event-time names can be generic (`live`), so for host / workload rankings append **dt-sec-contextualization** `rva-entity-resolution.md` § Resolving a ranking result for the current name + Smartscape id — ⚠ `k8s.*`/`dt.smartscape*` are null on RVA events |
| CVE / library lookup; "am I vulnerable to log4shell?" | `vulnerabilities-dynatrace.md` § Step 2 | Step 2 CVE/component filter; keyword / substring across entities = Step 4 entity fragment (§ Entity Scoping) |
| Vulnerabilities on ONE known entity (name / classic id / Smartscape id) | `vulnerabilities-dynatrace.md` § One known entity | RVA 30m snapshot scoped by `related_entities.<group>.{ids,names}` OR `affected_entity.*`, Steps 1–3 reused; Smartscape id → resolve to `id_classic` via **dt-sec-contextualization** `rva-entity-resolution.md` first |
| Blast radius — which entities are affected by CVE X | `vulnerabilities-rankings.md` | `related_entities.*` indirect-relation expand |
| Lifecycle — new / resolved / open-duration / MTTR; trends, CLV, tracking, mute audit, fix-available, vulnerable functions | `vulnerabilities-lifecycle.md` | Steps 1–3 of `vulnerabilities-dynatrace.md`; post-derive `resolution.change_date`; MTTR: change-events-only |
| Runtime advanced — function-in-use, exposure, exploit, data-assets | `vulnerabilities-dynatrace.md` | Davis-assessment `fieldsAdd` (Step 3) |
| External scanner vulns — top containers / artifacts / components (rankings) | `vulnerabilities-rankings.md` § UC-V9, external images, external code artifacts | `VULNERABILITY_FINDING`, null-safe Dynatrace exclusion, rank by `countDistinctExact(vulnerability.id)` |
| External scanner vulns — finding semantics, component fields, cross-provider view | `vulnerabilities-external.md` | `VULNERABILITY_FINDING` + external routing |
| Are external vulnerability findings confirmed by RVA? Is the scanned image running in my K8s? | **dt-sec-contextualization** `external-finding-verification.md` | Two stages: same vulnerability (`vulnerability.references.cve`), then same runtime entity (direct `dt.smartscape*` ids, container-image digest → running `CONTAINER` → workload, or `host.ip` → HOST) |
| "Newly reported this period **and not in the previous period**" (external) | `vulnerabilities-external.md` · `common-patterns.md` § 18 | prior-period **anti-join** (`isNull(right.*)`) — a `finding.time.created` filter is NOT equivalent |
| AI/LLM/GenAI workload vulnerabilities; "which AI services have vulnerabilities?" | **dt-sec-contextualization** `ai-workload-vulnerabilities.md` | Resolved through `GENAI_SERVICE` in Smartscape; probe first — zero rows is a hard stop (no fallbacks), see that file |
| New AI-workload vulnerabilities this period | **dt-sec-contextualization** `ai-workload-vulnerabilities.md` § UC-AI2 | prior-window **anti-join** on `{genai_service.id, vulnerability.id}` |
| **Anything about the Dynatrace vulnerability feed** — "does Dynatrace know about CVE-X?", what is CVE-X / `DTV-…`, affected packages and version ranges, fix versions, new in the last N days, KEV, enriching my findings, workflow use, bulk-export requests | `vulnerability-feed.md` § Routing within the feed | Its routing table maps each intent to a section; the feed is read with `load`, never `fetch security.events` |

> **Feed vs RVA tie-breaker:** "am I vulnerable to / affected by CVE-X?" is an environment question → RVA (`vulnerabilities-dynatrace.md`); "does Dynatrace know CVE-X / what does it affect / how is it fixed?" is a knowledge question → the feed. Findings *annotated* with feed knowledge join on `vulnerability.external_id`. `UNKNOWN_TABULAR_FILE` means the feed is not provisioned — say so, do not substitute.

**Detections (threats & attacks)**

| Intent / example | Reference | Pattern |
|---|---|---|
| Severity / time-window overview (DT + external) | `detections.md` · `all-security-events.md` | `DETECTION_FINDING` summary; default unqualified timeframe is `2h`, widen to `24h` only if empty |
| By attack type (`SQL injection`, crypto-mining, …) | `detections.md` | `finding.type` substring match |
| Attacker IPs / campaigns | `detections.md` | `expand actor.ips` + `ip()` |
| MITRE technique / sub-technique | `detections.md` | `threat.attack.*` arrays |
| RAP-only / Automated-Detections-only | `detections.md` § Provider Routing | `(product.name=="Runtime Application Protection" OR event.provider=="OneAgent")` / `event.provider=="Dynatrace Automated Detections"` |
| Map detections to entities | `detections.md` · **dt-sec-contextualization** `entity-enrichment.md` | `object.id` grouping / enrichment |
| Repeated firing / same IP across many targets / detections matching an IoC list | **dt-sec-ioc-hunting** `detection-investigation.md` · `hunt-security-events.md` | Not owned here — route to the hunting skill |
| A specific external provider | `all-security-events.md` § Scoping to a Specific Provider | provider `contains` idiom |

> **MITRE routing tie-breaker:** a MITRE ATT&CK question routes by intent. "Which techniques did we **detect / observe** (on our entities)?" → `detections.md` (`DETECTION_FINDING`). "Which techniques are **reported in threat intel / campaigns in the wild**?" → `threat-intelligence.md` (`THREAT_REPORT`). Don't merge the two — a report tagged T1059 is not evidence T1059 occurred in your environment.

**Threat intelligence (external reports & IOCs)**

| Intent / example | Reference | Pattern |
|---|---|---|
| Show / list / count threat intelligence reports; reports by provider, actor, malware family, targeted country/industry, TLP, report type | `threat-intelligence.md` | `THREAT_REPORT` + **`dedup {threat.report.id}`** (SD guard first); **never** the four-key finding summarize |
| Top IOCs (CVEs / IPs / domains / URLs / emails / hashes) or MITRE techniques across reports | `threat-intelligence.md` § IOC extraction | `dedup` → `expand` observable → `countDistinctExact(threat.report.id)` |
| **Am I exposed to report X / are these IOCs in my environment?** (threat-exposure) | **dt-sec-ioc-hunting** `hunt-security-events.md` § Report-driven correlation (report → environment join) · `ioc-intake.md` + `hunt-*.md` (user-supplied IoCs) | IoC hunting is not `security.events` access: this skill only reads the reports (`threat-intelligence.md`) |

**Compliance (policy violations & benchmarks)**

| Intent / example | Reference | Pattern |
|---|---|---|
| Pass-rate / posture (CIS / DORA / NIST / STIG) | `compliance.md` | **Load `compliance.md` first** — SPM Steps 1–2 + passRate |
| Critical misconfigurations | `compliance.md` | **Load `compliance.md` first** — Steps 1–2 + severity filter |
| Compliance / misconfigurations on a **specific entity** | `compliance.md` § Entity Security-Tab View (entity-scoped `${entityIdsOrNames}` filter) · **dt-sec-contextualization** `entity-enrichment.md` | Mirror the entity **Security tab** (CIS default, failed-only): Table 1 DT CIS failed rules → Table 2 other DT standards (overlap caveat) → Table 3 external misconfigs. Broad posture/count questions instead use § CIS-Primary Standard Summary (scorecard). |
| Map control/standard → entities; per-namespace | `compliance.md` | entity scoping via `compliance.standard.short_name` / `compliance.rule.id` (⚠ never `metadata_json`) |
| Cloud / non-K8s (PCI/ISO/HIPAA/GDPR; AWS/Azure/GCP) | `compliance.md` § External | external taxonomy (`compliance.standards`, or `compliance.standard.short_name` for Runecast-style feeds / `policy` / `control`) |
| External violations grouped by standard / framework | `compliance.md` § External | `compliance.standards` is an **array** — `expand` it before `summarize` |
| Config **drift** / newly failing rules vs previous week (DT) | `compliance.md` § Week-over-Week Config Drift | prior-period **anti-join** — a wide fetch window is NOT a substitute |
| External compliance findings new this period, absent in prior | `compliance.md` § External | prior-period anti-join (same rule as drift) |
| KSPM (Kubernetes-only, DT-native) | `compliance.md` | `product.name=="Security Posture Management"` |

**Coverage, enrichment & dashboards**

| Intent / example | Reference | Pattern |
|---|---|---|
| Coverage / "covered vs not covered" / coverage gaps — hosts / processes / workloads | **dt-sec-contextualization** `runtime-coverage.md` (denominator, scan-event lookups, match recipes) | ⚠ **MUST start from `smartscapeNodes` + `lookup` scan events** — summarizing scan events alone has no denominator and cannot answer a coverage question |
| Specific entity coverage by a DT capability (RVA, SPM, RAP, other DT-native) | **dt-sec-contextualization** `runtime-coverage.md` | If no relevant findings or scan/completion events exist for that entity in the capability's operational window, answer **not covered** — capability is likely not enabled or not configured for that entity |
| Map external findings → workloads / hosts / cloud | **dt-sec-contextualization** `entity-enrichment.md` | 2-way match (K8s) / host-by-IP / Path-1 (cloud) — ⚠ **always join to Smartscape; never group findings by raw `object.name` / `k8s.namespace.name` / `host.name` / cloud resource IDs alone** |
| One-row-per-entity risk summary | **dt-sec-contextualization** `entity-enrichment.md` · `dashboard-patterns.md` § Multi-Type Combined Views | RVA + external merge |
| Dashboards — KPI tiles, top-N tables, trends | `dashboard-patterns.md` | `makeTimeseries`, summarization recipes (coverage donuts → **dt-sec-contextualization** `runtime-coverage.md`) |

❌ **Don't use for:**

- Dynatrace-detected problems → `dt-obs-problems`
- Application/infrastructure logs → `dt-obs-logs`
- Distributed tracing → `dt-obs-tracing`
- Service performance/RED metrics → `dt-obs-services`

## Introduction to AppSec Data

All security events are stored in **`security.events`** and are categorized by `event.type`:

- **RVA vulnerabilities** — `VULNERABILITY_STATE_REPORT_EVENT` (15-minute snapshots per entity)
- **KSPM compliance** — `COMPLIANCE_FINDING` (per `(rule, K8s object)`, joined with `COMPLIANCE_SCAN_COMPLETED` on `scan.id` for latest-scan dedup)
- **External compliance (CSPM / VSPM / external posture tools)** — `COMPLIANCE_FINDING` with the external taxonomy (`compliance.standards` / `compliance.policy` / `compliance.control`); `compliance.rule.*` typically null (Runecast populates it)
- **Detections** — `DETECTION_FINDING` (RAP via `(product.name == "Runtime Application Protection" OR event.provider == "OneAgent")`), `SECURITY_EVENT` (RAP events in some tenants), Automated Detections via `event.provider == "Dynatrace Automated Detections"`, external security tools; plus `DETECTION_EXECUTION_SUMMARY` for per-rule-run audit (Automated Detections only)
- **Scan coverage** — `VULNERABILITY_SCAN`, `COMPLIANCE_SCAN`
- **Threat intelligence** — `THREAT_REPORT` (external TI platforms: AlienVault OTX pulses, CrowdStrike Falcon Intelligence). **A separate class of data — not a finding:** no `finding.*` / `object.*` / `dt.security.risk.level`, no affected entity, no scan cycle. **Never folded into the cross-provider finding summary or the posture-overview decomposition** — queried on its own via [threat-intelligence.md](references/threat-intelligence.md). Dedup by `threat.report.id`.
- **Vulnerability feed** — **not in `security.events`**: the `/dt/security/vulnerabilities/libraries` lookup table, read with `load`, one `load` per question. **Not gated on RVA** and still rolling out (`UNKNOWN_TABULAR_FILE` = not provisioned here yet — say so). On a tenant without RVA every *environment* half returns zero rows: probe RVA before reading that as "nothing affected". Knowledge about CVEs in the wild, queried on its own via [vulnerability-feed.md](references/vulnerability-feed.md).

Full taxonomy and field reference → [data-model.md](references/data-model.md)

**Snapshot windows:** DT RVA and KSPM are snapshot tools, not event streams — their fixed windows, the Dynatrace-app defaults and the fallbacks are in Universal Best Practice #5.

## How This Skill Is Organized

**SKILL.md** (this file) is the entry point and router; **references/** holds the detailed guidance by capability:

- [**data-model.md**](references/data-model.md) — `fetch security.events` event types, providers, fields, entity scoping.
- [**common-patterns.md**](references/common-patterns.md) — Cross-cutting query building blocks.
- [**mistakes-and-troubleshooting.md**](references/mistakes-and-troubleshooting.md) — Mistakes and troubleshooting; load when results look wrong or counts disagree with the apps.
- [**vulnerabilities-dynatrace.md**](references/vulnerabilities-dynatrace.md) — RVA snapshot pipeline, counts, runtime assessment, entity scope.
- [**vulnerabilities-lifecycle.md**](references/vulnerabilities-lifecycle.md) — RVA lifecycle / MTTR, trends, CLV, tracking, mute audit, fix-available, vulnerable functions.
- [**vulnerabilities-external.md**](references/vulnerabilities-external.md) — External SCA / SAST / image-scanner findings (`VULNERABILITY_FINDING`); RVA verification: dt-sec-contextualization `external-finding-verification.md`.
- [**vulnerabilities-rankings.md**](references/vulnerabilities-rankings.md) — vulnerability top-X: DT RVA most vulnerable hosts / K8s workloads / components, CVE blast radius, external top components / images / artifacts (Smartscape: dt-sec-contextualization `rva-entity-resolution.md`).
- [**vulnerability-feed.md**](references/vulnerability-feed.md) — Dynatrace Library Vulnerability Feed: CVE / package / DTVR-ID lookup, recently added, version ranges, fix versions, CISA KEV, RVA enrichment; has its own routing table.
- [**compliance.md**](references/compliance.md) — Dynatrace SPM / XSPM compliance findings and external provider compliance findings.
- [**detections.md**](references/detections.md) — Runtime Application Protection (RAP) detections, Automated Detection rules, and external provider detections.
- [**threat-intelligence.md**](references/threat-intelligence.md) — External threat-intelligence reports (`THREAT_REPORT`): IOC extraction and threat-exposure correlation. Not findings — queried separately.
- [**all-security-events.md**](references/all-security-events.md) — Cross-provider queries, double-counting guard, unified summaries
- [**dashboard-patterns.md**](references/dashboard-patterns.md) — KPI tiles, top-N tables, trend charts, findings-vs-scans split, threat-intelligence dashboards. Load only for dashboard / chart / KPI requests.

## Universal Best Practices

1. **Load `dt-dql-essentials` only when you write or adapt DQL beyond a canonical template** — run a routed reference's template as written (placeholders substituted) without it; load it before changing the query shape (new commands, joins, functions) and on the first query error. DQL syntax and function names differ from SQL.
2. **Ground every query in the routed reference's canonical template — do not improvise DQL.** Identify intent, load the matching reference (per *When to Use*), and build from its canonical pipeline / named building block. Do **not** invent field names, enum values, join syntax, or pipeline shape from SQL habits. Deviate from a template only with syntax explicitly shown in a skill example or validated in `dt-dql-essentials`. If no template covers the request, say so and adapt the closest one — never fabricate fields or values.
3. **No `dt.system.bucket` filters by default** — security events land in the default bucket `default_security` (the name varies per tenant), but users can route them to any custom bucket, so a bucket filter is irrelevant and can hide findings. Scope by `event.provider` / `product.vendor` instead; add a `dt.system.bucket` filter only when the user explicitly names a bucket to search.
4. **Use the correct provenance field for the family** — RVA state/status/tracking events (`event.level == "ENTITY"`, no vendor) use `event.provider == "Dynatrace"`. Dynatrace-native FINDING events (RVA findings, KSPM compliance, RAP and Automated Detections) use `(product.vendor == "Dynatrace" or event.provider == "Dynatrace")`: `event.provider` is null on some tenants, `product.vendor` is always set. Automated-Detections-only uses `event.provider == "Dynatrace Automated Detections"`. See [data-model.md § Provider Taxonomy](references/data-model.md).
5. **Always include an explicit `from:` clause — use the correct window for the query class.** DT RVA and KSPM are **snapshot tools**, not event streams: widening their windows does NOT look back further, it only captures the latest report/scan cycle. For historical trends use `makeTimeseries` over longer windows.

   | Query class | Default window | Dynatrace app default | Notes |
   |---|---|---|---|
   | DT RVA snapshots | `30m` fixed | Vulnerabilities app: 30 minutes | Captures latest 15-min state-report cycle — do not widen. If a 30m snapshot is empty or clearly stale, use the controlled 24h latest-known-state fallback in [vulnerabilities-dynatrace.md](references/vulnerabilities-dynatrace.md#latest-known-state-fallback-when-30m-is-empty-or-stale) |
   | DT KSPM snapshots | `1h` fixed | Security Posture Management app: 2 hours | Aligned with scan-completion cycle: needs the latest `COMPLIANCE_SCAN_COMPLETED` marker for the inner-join — do not widen |
   | External findings (incl. CSPM/VSPM) | `2h`–`24h+` | — | No snapshot semantics — these are one-shot events |
   | RAP / external detection retrieval or current summary | `2h` first attempt | Threats & Exploits app: 2 hours | Widen to `24h` only if zero rows returned or if the user explicitly asks for a longer window (see [detections.md § Widen-on-empty fallback](references/detections.md)) |
   | Cross-provider summary (aggregated) | `24h` | — | Summaries aggregate over time; start broad |

   Omitting `from:` falls back to a default window that doesn't match snapshot semantics and produces drift between query runs. The 30m / 1h windows are *not* arbitrary — they're tied to the underlying RVA / SPM scan cadence. See [common-patterns.md § 7](references/common-patterns.md) for the full window reference and [vulnerabilities-dynatrace.md § Snapshot vs. History](references/vulnerabilities-dynatrace.md) for details.

   The app defaults are *broader* than the minimum windows (e.g. SPM app = 2h vs. KSPM minimum = 1h): the minimum is what the inner-join / latest-cycle dedup needs to function, the app default is what the user sees on first load. Use the **minimum window** for canonical pipeline DQL; use the **app default** when the user references "the app's view" without an explicit window (e.g. "what does the SPM app show me right now?") or builds a dashboard tile meant to match the app.

   **DT-generated `VULNERABILITY_FINDING` vs. RVA state reports.** Dynatrace-generated `VULNERABILITY_FINDING` queries (e.g. AI-workload scoping in **dt-sec-contextualization** `ai-workload-vulnerabilities.md` § AI-workload vulnerabilities) also use a `30m` window, but dedup on **`finding.id`** because DT findings are re-emitted on every scan run (~15 min) — distinct from the RVA state-report `30m` window, which dedups on **`{vulnerability.display_id, affected_entity.id}`**. Do not mix the two dedup grains.

   **Decompose DT-inclusive broad / posture-overview questions** ("which security products are integrated incl. Dynatrace-native?", posture overview, cross-category counts that include DT vulnerabilities/compliance) — never answer with one wide scan over all of `security.events`. Run three separate queries and merge: Stream A external + DT detections (`24h`, double-counting guard), Stream B DT RVA (`30m`), Stream C DT KSPM (`1h`). This keeps the high-cardinality snapshot streams in their tight windows and avoids double-counting. A narrower "which **external** integrations are sending data?" stays a single external-only query. See [all-security-events.md § Broad-Question Query Decomposition](references/all-security-events.md#broad-question-query-decomposition).
6. **Preserve entity identifiers on raw listings** (top / latest / list / show-me — no `summarize`) so users see which entity each finding is on. The namespaces split by family and are **not** interchangeable: cross-provider `*_FINDING` / scan events use the generic `dt.smartscape*` fields (including the typed `dt.smartscape_source.type`); RVA state/change events leave those null and carry refs in `affected_entity*` / `related_entities*`. Not for pure count / pass-rate summaries. Field lists and wildcard reference → [common-patterns.md § 17](references/common-patterns.md#17-entity-identifier-preservation-on-raw-listings).
7. **Broad entity-security questions require the external stream too.** For prompts like "security findings of this host / K8s node / workload / cluster", do not stop after DT RVA and SPM. Also run the external/cross-provider `*_FINDING` stream scoped with the wide entity OR chain (`dt.smartscape_source.id`, `dt.smartscape.*`, `object.*`, and relevant `k8s.*` fields) in `24h`, then merge with RVA (`30m`, scope via `vulnerabilities-dynatrace.md` § One known entity) and SPM (`1h`). Do not use the legacy `dt.source_entity` / `dt.source_entity.type` (lowercase, only on Dynatrace process-sourced events) — it is superseded by `dt.smartscape_source.id` / `dt.smartscape_source.type` (UPPERCASE, e.g. `PROCESS`, `HOST`). If the external branch returns 0 rows, report "no external findings found" with the scope used. Load **dt-sec-contextualization** → `entity-enrichment.md` for the Smartscape join. See also [all-security-events.md](references/all-security-events.md).
8. **Always bound raw listing and top-N results.** If the user asks for "top X", "last X", or "first X", end with `| sort ... | limit X` (after the ranking/sort). If the user asks to list/show findings but does **not** explicitly ask for all data and the output is not a summary (`summarize` / `makeTimeseries`), add `| limit 50` by default. Do not run unbounded raw projections on security findings. Full rule and exceptions → [common-patterns.md § 16](references/common-patterns.md#16-result-limits-for-top-n-and-raw-listings).
9. **Preserve query shape — do not drop `by:` keys unless the user asks for coarser aggregation.** The canonical cross-provider `summarize` always keys by `{event.provider, product.name, event.type, dt.security.risk.level}`. Dropping any of these silently merges rows from different providers, products, or finding types into a single count and will be penalized by evaluators. Do not replace the four-key grouping with a simpler `by: {dt.security.risk.level}` or `by: {event.type}` unless the user explicitly requests a coarser view. See [common-patterns.md § 15](references/common-patterns.md).

10. **Compliance status uses `compliance.result.status.level`** (`PASSED`/`FAILED`/`MANUAL`/`NOT_RELEVANT`) — never `event.status` or `"PASS"`/`"FAIL"`. Pass rate is computed on per-rule verdicts after the latest-scan dedup join `on: {scan.id}`. Field terminology, the dedup join, and the pass-rate rollup → [compliance.md](references/compliance.md).

11. **Count distinct identities, not rows, after `expand` / `join` / `lookup`** that fan out arrays — use `countDistinctExact(vulnerability.display_id)` / `countDistinctExact(finding.id)`, or `dedup` on identity + group key first. A plain `count()` is safe only when the grain entering the `expand` is already one row per counted item. Examples and the exception → [mistakes-and-troubleshooting.md § Mistakes #56](references/mistakes-and-troubleshooting.md#mistakes-to-avoid).

12. **Interpret empty entity-coverage probes as not covered.** When validating whether a specific entity is covered by a Dynatrace security capability (RVA, SPM/KSPM, RAP, or another DT-native capability), absence of the relevant findings and scan/completion events means the entity is **not covered** by that capability. State the likely cause: the capability is not enabled, or it is not configured / deployed to monitor that entity. Do not soften this into "no findings" when the user asked about coverage. Queries → **dt-sec-contextualization** `runtime-coverage.md`.

13. **Report empty results truthfully — never fabricate numbers.** 0 rows means "no matching data," stated with the scope and filters used; never invent plausible values. Before relaxing a filter, apply the family's documented recovery (RVA 30m→24h latest-known-state, detections 2h→24h widen, RVA filters on null `k8s.*`/`dt.smartscape*` → pivot to `affected_entity.*`/`related_entities.*`) and say so explicitly if you adapt. Recovery details → [vulnerabilities-dynatrace.md](references/vulnerabilities-dynatrace.md) / [detections.md](references/detections.md).

Domain-specific best practices are in the references above; the full diagnostic catalog is [mistakes-and-troubleshooting.md](references/mistakes-and-troubleshooting.md).

## External Documentation

- https://docs.dynatrace.com/docs/secure/threat-observability/concepts
- https://docs.dynatrace.com/docs/semantic-dictionary/model/security-events
- https://docs.dynatrace.com/docs/semantic-dictionary/fields

## Related Skills

- **dt-dql-essentials** — Load when writing or adapting DQL (best practice #1). Core DQL syntax, command reference, function catalog, Smartscape patterns.
- **dt-sec-contextualization** — Load for any entity-mapping question: 2-way match (K8s workload), host-by-IP, cloud Path 1, pod→node topology, cross-evidence correlation, Smartscape id → classic id resolution for RVA, external-finding verification, AI-workload vulnerabilities, coverage.
- **dt-obs-kubernetes** — K8s topology for findings scoped to clusters / workloads
- **dt-obs-hosts** — Host inventory, process-level context when the affected entity is a HOST or PROCESS_GROUP
- **dt-obs-services** — Service-scoped queries: UC-G3 "findings affecting `<service-name>`", vulnerable service to RED metrics
- **dt-obs-aws / dt-obs-azure / dt-obs-gcp** — Cloud Smartscape; enriching external cloud-security findings against resource topology, and hyperscaler-specific field handling (resource IDs, ARNs, account scoping)
- **dt-obs-tracing** — Drill from a vulnerable / attacked entity to representative request traces
- **dt-obs-problems** — Get affected/related entity IDs for a problem before querying security findings (UC-G5)