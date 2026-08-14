---
name: dt-sec-insights
description: >-
  Query and analyze Dynatrace security data in security.events with DQL:
  vulnerabilities, threat detections, compliance posture, and scan coverage.
  Covers Dynatrace-native Runtime Vulnerability Analytics (RVA — CVEs,
  reachability, exposure, exploit), Runtime Application Protection (RAP),
  Automated Detections, and Security Posture Management
  (KSPM/CSPM), plus external security products and tools. Trigger:
  "open critical vulnerabilities", "vulnerable functions in use and publicly
  exposed", "top vulnerable libraries / K8s workloads", "CIS/DORA compliance
  pass rate", "SQL injection detections", "map external findings to workloads",
  "hosts not covered by scanning". Do NOT use for explaining existing DQL
  (use dt-dql-essentials), Davis problems (dt-obs-problems), logs (dt-obs-logs),
  distributed tracing (dt-obs-tracing), service RED metrics (dt-obs-services),
  or platform usage/audit telemetry (dt-platform).
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
  STIG) plus CSPM/VSPM and external compliance/posture providers.
- **Runtime attacks and threats** — DT-native detections (RAP runtime attacks,
  Automated Detections rules) plus external detection providers.
- **Threat intelligence** — external threat-intelligence reports (AlienVault OTX
  pulses, CrowdStrike Falcon Intelligence) with actor / campaign / targeting context
  and indicators of compromise (IOCs); correlate reported IOCs / CVEs / techniques
  against your monitored environment. **These are threat intel about the wild — not
  findings on your entities — and are queried separately.**
- **Scan coverage analysis** — covered vs. not-covered k8s workloads/hosts/processes, by Dynatrace
  scanning feature (`Library Vulnerability Analytics`, `Operating System
  Vulnerability Analytics`, `Code-level Vulnerability Analytics`) or by external
  product.
- **Entity enrichment** — map external findings to Dynatrace runtime entities
  (hosts, K8s workloads, cloud resources) via Smartscape.
- **Dashboards / KPIs** — tiles, top-N tables, trend charts, coverage donuts.

## When to Use This Skill

✅ **Must-first routing rule:** identify user intent first, then load the matching primary reference from **Quick Start: Find Your Use Case** before generating DQL.

Identify the intent, then load the matching reference before writing DQL.

**Cross-cutting (any / all finding types)**

| Intent / example | Reference | Pattern |
|---|---|---|
| Security posture / overview across all products (incl. DT-native) | `all-security-events.md` § Broad-Question Query Decomposition | 3-stream decomposition (external+detections `24h` / RVA `30m` / KSPM `1h`), merged; **lead the count summary with KSPM compliance — CIS first** (other standards + RVA + detections beneath) → `compliance.md` § CIS-Primary Standard Summary |
| Findings on a specific entity — direct or related (blast radius) | **dt-sec-contextualization** `entity-enrichment.md` · `all-security-events.md` | **Broad entity-security questions must decompose**: external `*_FINDING` by `dt.smartscape_source.id` / `dt.entity.*` / `k8s.*` (`24h`) + DT RVA entity scope (`30m`) + DT SPM entity scope (`1h`) |
| Findings from a specific provider | `all-security-events.md` § Scoping to a Specific Provider | `contains(lower(event.provider \| product.vendor), "<p>")` |
| Which **third-party / external** tools are sending data (DT-native excluded) | `all-security-events.md` § Which external integrations are active | external-only enumeration (single query) |
| Which security products are integrated? / what security data do we have? (default: **include DT-native** RVA + KSPM) | `all-security-events.md` § Broad-Question Query Decomposition | 3-stream decomposition; never a single wide `security.events` scan |
| Which products cover a specific entity | **dt-sec-contextualization** `correlation-and-coverage.md` · `all-security-events.md` | summarize by `product.*`; findings-vs-scans split |

> **Routing tie-breaker:** an unqualified "which security products are integrated? / are we covered? / what do we have?" defaults to the **DT-inclusive 3-stream decomposition** (it *must* query DT vulnerabilities and compliance). Take the external-only single query **only** when the user explicitly scopes to external / third-party tools ("which external tools are sending us data?").

**Vulnerabilities (CVE management)**

| Intent / example | Reference | Pattern |
|---|---|---|
| Counts / severity ("how many critical?", by risk + mute status) | `vulnerabilities-dynatrace.md` | RVA snapshot Steps 1–3 |
| Most vulnerable components / hosts / workloads (rankings) | `vulnerabilities-entities.md` | Steps 1–3 + `expand` typed `related_entities.<group>.ids` → `smartscapeNodes` lookup on `id_classic` — ⚠ `k8s.*`/`dt.entity.*` are null on RVA events |
| CVE / library lookup; "am I vulnerable to log4shell?" | `vulnerabilities-dynatrace.md` § Entity Scoping | Step 2 CVE/component filter; scope RVA to a known entity |
| Blast radius — which entities are affected by CVE X | `vulnerabilities-entities.md` | `related_entities.*` indirect-relation expand |
| Lifecycle — new / resolved / open-duration / MTTR | `vulnerabilities-dynatrace.md` | post-derive `resolution.change_date`; MTTR via change-events-only snippet (§ Resolution time) |
| Runtime advanced — function-in-use, exposure, exploit, data-assets | `vulnerabilities-dynatrace.md` | Davis-assessment `fieldsAdd` (Step 3) |
| External scanner vulns — containers / artifacts / components | `vulnerabilities-external.md` | `VULNERABILITY_FINDING` + external routing |
| Verify external vulnerability findings with RVA | `vulnerabilities-external.md` § Verify external vulnerability findings with RVA · **dt-sec-contextualization** `entity-enrichment.md` | First match the same vulnerability by `vulnerability.references.cve`; then prove runtime relatedness via direct `dt.smartscape*` IDs, container-image digest → running `CONTAINER`, or host `host.ip` → Smartscape HOST |
| "Newly reported this period **and not in the previous period**" (external) | `vulnerabilities-external.md` · `common-patterns.md` § 18 | prior-period **anti-join** (`isNull(right.*)`) — a `finding.time.created` filter is NOT equivalent |
| AI/LLM/GenAI workload vulnerabilities; "which AI services have vulnerabilities?" | `vulnerabilities-dynatrace-advanced.md` § AI-workload vulnerabilities | **Probe `smartscapeNodes "GENAI_SERVICE"` first** — zero rows → report cannot be determined (no GenAI-monitored services); non-zero → DT findings + GENAI scope (`30m`, dedup `finding.id`). ⚠ Zero rows = hard stop — **no fallbacks permitted**: entity/namespace/workload name substrings, ML library component lists, process/image/label patterns are all prohibited substitutes. |
| New AI-workload vulnerabilities this period | `vulnerabilities-dynatrace-advanced.md` § UC-AI2 | prior-window **anti-join** on `{genai_service.id, vulnerability.id}` |

**Detections (threats & attacks)**

| Intent / example | Reference | Pattern |
|---|---|---|
| Severity / time-window overview (DT + external) | `detections.md` · `all-security-events.md` | `DETECTION_FINDING` summary; default unqualified timeframe is `2h`, widen to `24h` only if empty |
| By attack type (`SQL injection`, crypto-mining, …) | `detections.md` | `finding.type` substring match |
| Attacker IPs / campaigns | `detections.md` | `expand actor.ips` + `ip()` |
| MITRE technique / sub-technique | `detections.md` | `threat.attack.*` arrays |
| RAP-only / Automated-Detections-only | `detections.md` § Provider Routing | `product.name=="Runtime Application Protection"` / `event.provider=="Dynatrace Automated Detections"` |
| Map detections to entities; repeated firing | `detections.md` · **dt-sec-contextualization** `entity-enrichment.md` | `object.id` grouping / enrichment |
| A specific external provider | `all-security-events.md` § Scoping to a Specific Provider | provider `contains` idiom |

> **MITRE routing tie-breaker:** a MITRE ATT&CK question routes by intent. "Which techniques did we **detect / observe** (on our entities)?" → `detections.md` (`DETECTION_FINDING`). "Which techniques are **reported in threat intel / campaigns in the wild**?" → `threat-intelligence.md` (`THREAT_REPORT`). Don't merge the two — a report tagged T1059 is not evidence T1059 occurred in your environment.

**Threat intelligence (external reports & IOCs)**

| Intent / example | Reference | Pattern |
|---|---|---|
| Show / list / count threat intelligence reports; reports by provider, actor, malware family, targeted country/industry, TLP, report type | `threat-intelligence.md` | `THREAT_REPORT` + **`dedup {threat.report.id}`** (SD guard first); **never** the four-key finding summarize |
| Top IOCs (CVEs / IPs / domains / URLs / emails / hashes) or MITRE techniques across reports | `threat-intelligence.md` § IOC extraction | `dedup` → `expand` observable → `countDistinctExact(threat.report.id)` |
| **Am I exposed to report X / are these IOCs in my environment?** (threat-exposure) | `threat-intelligence.md` § Threat-Exposure Correlation | `join` report IOCs/CVEs/techniques to `VULNERABILITY_FINDING`/RVA/`DETECTION_FINDING`; **logs/spans IoC hunt → `dt-sec-ioc-hunting`** |

**Compliance (policy violations & benchmarks)**

| Intent / example | Reference | Pattern |
|---|---|---|
| Pass-rate / posture (CIS / DORA / NIST / STIG) | `compliance.md` | **Load `compliance.md` first** — SPM Steps 1–2 + passRate |
| Critical misconfigurations | `compliance.md` | **Load `compliance.md` first** — Steps 1–2 + severity filter |
| Compliance / misconfigurations on a **specific entity** | `compliance.md` § Entity Security-Tab View (entity-scoped `${entityIdsOrNames}` filter) · `entity-enrichment.md` | Mirror the entity **Security tab** (CIS default, failed-only): Table 1 DT CIS failed rules → Table 2 other DT standards (overlap caveat) → Table 3 external misconfigs. Broad posture/count questions instead use § CIS-Primary Standard Summary (scorecard). |
| Map control/standard → entities; per-namespace | `compliance.md` | entity scoping via `compliance.standard.short_name` / `compliance.rule.id` (⚠ never `metadata_json`) |
| Cloud / non-K8s (PCI/ISO/HIPAA/GDPR; AWS/Azure/GCP) | `compliance.md` § External | external taxonomy (`compliance.standards`/`policy`/`control`) |
| External violations grouped by standard / framework | `compliance.md` § External | `compliance.standards` is an **array** — `expand` it before `summarize` |
| Config **drift** / newly failing rules vs previous week (DT) | `compliance.md` § Week-over-Week Config Drift | prior-period **anti-join** — a wide fetch window is NOT a substitute |
| External compliance findings new this period, absent in prior | `compliance.md` § External | prior-period anti-join (same rule as drift) |
| KSPM (Kubernetes-only, DT-native) | `compliance.md` | `product.name=="Security Posture Management"` |

**Coverage, enrichment & dashboards**

| Intent / example | Reference | Pattern |
|---|---|---|
| Coverage / "covered vs not covered" / coverage gaps — hosts / processes / workloads | `coverage-and-dashboards.md` (counting logic) · **dt-sec-contextualization** `correlation-and-coverage.md` (match recipes) | ⚠ **MUST start from `smartscapeNodes` + `lookup` scan events** — summarizing scan events alone has no denominator and cannot answer a coverage question |
| Specific entity coverage by a DT capability (RVA, SPM, RAP, other DT-native) | `coverage-and-dashboards.md` | If no relevant findings or scan/completion events exist for that entity in the capability's operational window, answer **not covered** — capability is likely not enabled or not configured for that entity |
| Map external findings → workloads / hosts / cloud | **dt-sec-contextualization** `entity-enrichment.md` | 3-way match (K8s) / host-by-IP / Path-1 (cloud) — ⚠ **always join to Smartscape; never group findings by raw `object.name` / `k8s.namespace.name` / `host.name` / cloud resource IDs alone** |
| One-row-per-entity risk summary | **dt-sec-contextualization** `entity-enrichment.md` · `coverage-and-dashboards.md` | RVA + external merge |
| Dashboards — KPI tiles, top-N, trends, donuts | `coverage-and-dashboards.md` | `makeTimeseries`, summarization recipes |

❌ **Don't use for:**

- Dynatrace-detected problems → `dt-obs-problems`
- Application/infrastructure logs → `dt-obs-logs`
- Distributed tracing → `dt-obs-tracing`
- Service performance/RED metrics → `dt-obs-services`

## Introduction to AppSec Data

All security events are stored in **`security.events`** and are categorized by `event.type`:

- **RVA vulnerabilities** — `VULNERABILITY_STATE_REPORT_EVENT` (15-minute snapshots per entity)
- **KSPM compliance** — `COMPLIANCE_FINDING` (per `(rule, K8s object)`, joined with `COMPLIANCE_SCAN_COMPLETED` on `scan.id` for latest-scan dedup)
- **External compliance (CSPM / VSPM / external posture tools)** — `COMPLIANCE_FINDING` with the external taxonomy (`compliance.standards` / `compliance.policy` / `compliance.control`); `compliance.rule.*` typically null
- **Detections** — `DETECTION_FINDING` (RAP via `product.name == "Runtime Application Protection"`), `SECURITY_EVENT` (RAP events in some tenants), Automated Detections via `event.provider == "Dynatrace Automated Detections"`, external security tools; plus `DETECTION_EXECUTION_SUMMARY` for per-rule-run audit (Automated Detections only)
- **Scan coverage** — `VULNERABILITY_SCAN`, `COMPLIANCE_SCAN`
- **Threat intelligence** — `THREAT_REPORT` (external TI platforms: AlienVault OTX pulses, CrowdStrike Falcon Intelligence). **A separate class of data — not a finding:** no `finding.*` / `object.*` / `dt.security.risk.level`, no affected entity, no scan cycle. **Never folded into the cross-provider finding summary or the posture-overview decomposition** — queried on its own via [threat-intelligence.md](references/threat-intelligence.md). Dedup by `threat.report.id`.

Full taxonomy and field reference → [data-model.md](references/data-model.md)

### Critical Constraint: Snapshot Windows

DT RVA and KSPM are **snapshot tools**, not event streams. The minimum
query window required for each pipeline:

- **RVA**: `30m` fixed window (captures latest 15-min cycle); if a 30m snapshot is empty or clearly stale, use the controlled 24h latest-known-state fallback in [vulnerabilities-dynatrace.md](references/vulnerabilities-dynatrace.md#latest-known-state-fallback-when-30m-is-empty-or-stale)
- **KSPM**: `1h` fixed window (needs latest `COMPLIANCE_SCAN_COMPLETED` marker for the inner-join)
- **External findings (incl. CSPM/VSPM)**: `2h–24h+` (no snapshot semantics — these are one-shot events)

Widening these windows does NOT look back further — they only capture the latest report/scan cycle. For historical trends, use `makeTimeseries` over longer windows.

> **DT-generated `VULNERABILITY_FINDING` vs. RVA state reports.** Dynatrace-generated
> `VULNERABILITY_FINDING` queries (e.g. AI-workload scoping in
> [vulnerabilities-dynatrace-advanced.md § AI-workload vulnerabilities](references/vulnerabilities-dynatrace-advanced.md#ai-workload-vulnerabilities-dynatrace-findings))
> also use a `30m` window, but dedup on **`finding.id`** because DT findings are
> re-emitted on every scan run (~15 min) — distinct from the RVA state-report
> `30m` window, which dedups on **`{vulnerability.display_id, affected_entity.id}`**.
> Do not mix the two dedup grains.

### Default Time Ranges in the Dynatrace Apps

The UI apps show pre-set defaults in their time picker. When a user
references "the app's view" without giving an explicit window, match
these to align query results with what the user sees in the UI:

| App | Default time picker |
|---|---|
| Vulnerabilities app | 30 minutes |
| Threats & Exploits app | 2 hours |
| Security Posture Management app | 2 hours |

These app defaults are *broader* than the minimum snapshot windows above
(e.g. SPM app = 2h vs. KSPM pipeline minimum = 1h). The minimum window is
what the inner-join / latest-cycle dedup needs to function; the app default
is what the user sees on first load. Use the **minimum window** when
generating canonical pipeline DQL; use the **app default** when the user
asks "what does the SPM app show me right now?" or builds a dashboard tile
intended to match the app view.

See [vulnerabilities-dynatrace.md § Snapshot vs. History](references/vulnerabilities-dynatrace.md) for details.

## How This Skill Is Organized

The skill is split into two parts for scalability:

1. **SKILL.md** (this file) — Entry point, quick lookup, routing to the right reference
2. **references/** — Detailed guidance by capability or domain:
   - [**data-model.md**](references/data-model.md) — Reference for `fetch security.events` — event types, providers, fields, entity scoping.
   - [**common-patterns.md**](references/common-patterns.md) — Cross-cutting patterns, common mistakes to avoid, and query troubleshooting reference.
  - [**vulnerabilities-dynatrace.md**](references/vulnerabilities-dynatrace.md) — Dynatrace Runtime Vulnerability Analytics (RVA): snapshot pipeline, counts, lifecycle, runtime assessment, CLV, tracking, mute, and entity scoping.
  - [**vulnerabilities-dynatrace-advanced.md**](references/vulnerabilities-dynatrace-advanced.md) — Advanced DT vulnerability guidance: best practices and AI-workload (`VULNERABILITY_FINDING`) query workflows.
  - [**vulnerabilities-external.md**](references/vulnerabilities-external.md) — External SCA / SAST / image-scanner vulnerability findings (`VULNERABILITY_FINDING`).
   - [**vulnerabilities-entities.md**](references/vulnerabilities-entities.md) — DT RVA entity rankings: "most vulnerable hosts / K8s workloads / components" + CVE blast radius.
   - [**compliance.md**](references/compliance.md) — Dynatrace Security Posture Management (SPM / XSPM) compliance findings and external provider compliance findings.
   - [**detections.md**](references/detections.md) — Runtime Application Protection (RAP) detections, Automated Detection rules, and external provider detections.
   - [**threat-intelligence.md**](references/threat-intelligence.md) — External threat-intelligence reports (`THREAT_REPORT`): AlienVault OTX / CrowdStrike Falcon Intelligence, IOC extraction, and threat-exposure correlation. Not findings — queried separately.
   - [**all-security-events.md**](references/all-security-events.md) — Cross-provider queries, double-counting guard, unified summaries
   - [**coverage-and-dashboards.md**](references/coverage-and-dashboards.md) — Entity coverage counting logic (`smartscapeNodes` denominator, covered vs. not-covered) and dashboard patterns (KPI tiles, top-N, trend charts, coverage donuts).
   - **entity-enrichment** — Moved to **dt-sec-contextualization** `references/entity-enrichment.md` (3-way match / host-by-IP / cloud). Load `dt-sec-contextualization` for any entity-mapping question.

## Universal Best Practices

1. **Always load dt-dql-essentials first** — DQL syntax and function names differ from SQL. Confirm all functions in `dt-dql-essentials` before generating queries.
2. **Ground every query in the routed reference's canonical template — do not improvise DQL.** Identify intent, load the matching reference (per *When to Use*), and build from its canonical pipeline / named building block. Do **not** invent field names, enum values, join syntax, or pipeline shape from SQL habits. Deviate from a template only with syntax explicitly shown in a skill example or validated in `dt-dql-essentials`. If no template covers the request, say so and adapt the closest one — never fabricate fields or values.
3. **No `dt.system.bucket` filters** — security event data may live in any bucket; filtering by bucket risks hiding findings.
4. **Use the correct provenance field for the family** — RVA uses `event.provider == "Dynatrace"`, SPM/detections use `product.vendor == "Dynatrace"`. See [data-model.md § Provider Taxonomy](references/data-model.md).
5. **Always include an explicit `from:` clause — use the correct window for the query class:**

   | Query class | Default window | Notes |
   |---|---|---|
   | DT RVA snapshots | `30m` fixed | Captures latest 15-min state-report cycle — do not widen |
   | DT KSPM snapshots | `1h` fixed | Aligned with scan-completion cycle inner-join — do not widen |
  | RAP / external detection retrieval or current summary | `2h` first attempt | Matches Threats & Exploits app default. Widen to `24h` only if zero rows returned or if the user explicitly asks for a longer window (see [detections.md § Widen-on-empty fallback](references/detections.md)) |
   | Cross-provider summary (aggregated) | `24h` | Summaries aggregate over time; start broad |

   Omitting `from:` falls back to a default window that doesn't match snapshot semantics and produces drift between query runs. The 30m / 1h windows are *not* arbitrary — they're tied to the underlying RVA / SPM scan cadence. See [common-patterns.md § 7](references/common-patterns.md) for the full window reference.

   **Decompose DT-inclusive broad / posture-overview questions** ("which security products are integrated incl. Dynatrace-native?", posture overview, cross-category counts that include DT vulnerabilities/compliance) — never answer with one wide scan over all of `security.events`. Run three separate queries and merge: Stream A external + DT detections (`24h`, double-counting guard), Stream B DT RVA (`30m`), Stream C DT KSPM (`1h`). This keeps the high-cardinality snapshot streams in their tight windows and avoids double-counting. A narrower "which **external** integrations are sending data?" stays a single external-only query. See [all-security-events.md § Broad-Question Query Decomposition](references/all-security-events.md#broad-question-query-decomposition).
6. **Preserve entity identifiers on raw listings** (top / latest / list / show-me — no `summarize`) so users see which entity each finding is on. The namespaces split by family and are **not** interchangeable: cross-provider `*_FINDING` / scan events use the generic `dt.smartscape*` / `dt.entity*` / `dt.source*` fields; RVA state/change events leave those null and carry refs in `affected_entity*` / `related_entities*`. Not for pure count / pass-rate summaries. Field lists and wildcard reference → [common-patterns.md § 17](references/common-patterns.md#17-entity-identifier-preservation-on-raw-listings).
7. **Broad entity-security questions require the external stream too.** For prompts like "security findings of this host / K8s node / workload / cluster", do not stop after DT RVA and SPM. Also run the external/cross-provider `*_FINDING` stream scoped with the wide entity OR chain (`dt.smartscape_source.id`, `dt.entity.*`, `object.*`, and relevant `k8s.*` fields) in `24h`, then merge with RVA (`30m`) and SPM (`1h`). Treat `dt.source_entity` as a legacy/scan fallback, not a primary cross-provider scoping path. If the external branch returns 0 rows, report "no external findings found" with the scope used. Load **dt-sec-contextualization** → `entity-enrichment.md` for the Smartscape join. See also [all-security-events.md](references/all-security-events.md).
8. **Always bound raw listing and top-N results.** If the user asks for "top X", "last X", or "first X", end with `| sort ... | limit X` (after the ranking/sort). If the user asks to list/show findings but does **not** explicitly ask for all data and the output is not a summary (`summarize` / `makeTimeseries`), add `| limit 50` by default. Do not run unbounded raw projections on security findings. Full rule and exceptions → [common-patterns.md § 16](references/common-patterns.md#16-result-limits-for-top-n-and-raw-listings).
9. **Preserve query shape — do not drop `by:` keys unless the user asks for coarser aggregation.** The canonical cross-provider `summarize` always keys by `{event.provider, product.name, event.type, dt.security.risk.level}`. Dropping any of these silently merges rows from different providers, products, or finding types into a single count and will be penalized by evaluators. Do not replace the four-key grouping with a simpler `by: {dt.security.risk.level}` or `by: {event.type}` unless the user explicitly requests a coarser view. See [common-patterns.md § 15](references/common-patterns.md).

10. **Compliance status uses `compliance.result.status.level`** (`PASSED`/`FAILED`/`MANUAL`/`NOT_RELEVANT`) — never `event.status` or `"PASS"`/`"FAIL"`. Pass rate is computed on per-rule verdicts after the latest-scan dedup join `on: {scan.id}`. Field terminology, the dedup join, and the pass-rate rollup → [compliance.md](references/compliance.md).

11. **Count distinct identities, not rows, after `expand` / `join` / `lookup`** that fan out arrays — use `countDistinctExact(vulnerability.display_id)` / `countDistinctExact(finding.id)`, or `dedup` on identity + group key first. A plain `count()` is safe only when the grain entering the `expand` is already one row per counted item. Examples and the exception → [common-patterns.md § Mistakes #55](references/common-patterns.md#mistakes-to-avoid).

12. **Interpret empty entity-coverage probes as not covered.** When validating whether a specific entity is covered by a Dynatrace security capability (RVA, SPM/KSPM, RAP, or another DT-native capability), absence of the relevant findings and scan/completion events means the entity is **not covered** by that capability. State the likely cause: the capability is not enabled, or it is not configured / deployed to monitor that entity. Do not soften this into "no findings" when the user asked about coverage. Counting logic → [coverage-and-dashboards.md](references/coverage-and-dashboards.md); match recipes → **dt-sec-contextualization** `correlation-and-coverage.md`.

13. **Report empty results truthfully — never fabricate numbers.** 0 rows means "no matching data," stated with the scope and filters used; never invent plausible values. Before relaxing a filter, apply the family's documented recovery (RVA 30m→24h latest-known-state, detections 2h→24h widen, RVA filters on null `k8s.*`/`dt.entity.*`/`dt.smartscape*` → pivot to `affected_entity.*`/`related_entities.*`) and say so explicitly if you adapt. Recovery details → [vulnerabilities-dynatrace.md](references/vulnerabilities-dynatrace.md) / [detections.md](references/detections.md).

For domain-specific best practices and the full diagnostic catalog, see the references listed in the "How This Skill Is Organized" section above.

## External Documentation

- https://docs.dynatrace.com/docs/secure/threat-observability/concepts
- https://docs.dynatrace.com/docs/semantic-dictionary/model/security-events
- https://docs.dynatrace.com/docs/semantic-dictionary/fields

## Related Skills

- **dt-dql-essentials** — Load first. Core DQL syntax, command reference, function catalog, Smartscape patterns.
- **dt-sec-contextualization** — Load for any entity-mapping question: 3-way match (K8s workload), host-by-IP, cloud Path 1, pod→node topology, cross-evidence correlation, coverage match recipes.
- **dt-obs-kubernetes** — K8s topology; useful for security findings scoped to clusters / workloads
- **dt-obs-hosts** — Host inventory, process-level context; useful when a finding's affected entity is a HOST or PROCESS_GROUP
- **dt-obs-services** — Service-scoped queries; useful for UC-G3 "findings affecting `<service-name>`" and tracing from a vulnerable service to RED metrics
- **dt-obs-aws / dt-obs-azure / dt-obs-gcp** — Cloud Smartscape; useful for enriching external cloud-security findings against the provider's resource topology, and for hyperscaler-specific provider field handling (cloud resource IDs, ARNs, account scoping)
- **dt-obs-tracing** — Drill from a vulnerable / attacked entity to representative request traces
- **dt-obs-problems** — Get affected/related entity IDs for a problem before querying security findings (UC-G5)