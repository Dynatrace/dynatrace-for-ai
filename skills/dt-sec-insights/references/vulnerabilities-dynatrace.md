# Dynatrace Vulnerabilities — `security.events`

Dynatrace-generated vulnerability data: **Runtime Vulnerability Analytics (RVA) state
reports** (the canonical snapshot pipeline below) and **Dynatrace-generated
`VULNERABILITY_FINDING` events** (§ AI-workload vulnerabilities — findings scoped to AI
workloads). For **external** SCA / SAST / image-scanner findings see
[vulnerabilities-external.md](vulnerabilities-external.md).

> **Cross-references:** field reference → [data-model.md](data-model.md) ·
> risk-level mapping, status aggregation precedence, mute-status reporting rule,
> time-window rules → [common-patterns.md](common-patterns.md) · KPIs, top-N
> tables, trend charts → [coverage-and-dashboards.md § Dashboard Query Patterns](coverage-and-dashboards.md#dashboard-query-patterns).

> **Snapshot vs. history.** DT RVA queries start with a **30-minute fixed window**
> (`from:now()-30m`). State reports usually emit every ~15 min; the 30m window
> captures the latest cycle when ingestion is healthy. This is a snapshot window,
> not history. If the 30m snapshot is empty or clearly stale, use the controlled
> 24h latest-known-state fallback below — do not simply widen every RVA query by
> default. For historical trend analysis use `makeTimeseries` over a longer
> window (see § Time-Series Trends).
>
> **Change-event-only queries.** The 30m window rule applies whenever
> `VULNERABILITY_STATE_REPORT_EVENT` is in the event-type filter — that event
> type is what imposes snapshot semantics. If the user asks "what status changes
> happened in the last 7 days?", use a **pure change-event query**: filter only
> `VULNERABILITY_STATUS_CHANGE_EVENT` (and/or `VULNERABILITY_TRACKING_LINK_CHANGE_EVENT`),
> set the fetch window to match the user's time horizon, and omit the snapshot
> dedup. Do **not** widen a snapshot query (one that includes `STATE_REPORT`)
> to gather history — it returns ~50× more rows without adding newer data.

> **The entire `vulnerability.parent.*` namespace is deprecated** — derive every
> vulnerability-level value from per-entity fields and per-entity status arrays in
> Step 3 (`takeMax`/`collectDistinct`; see Best Practices #12).

> **`vulnerability.first_seen` is null on the RVA pipeline — do not use it.** The field is
> commented out of the `entity.state` SD model, so it is null on every
> `VULNERABILITY_STATE_REPORT_EVENT` / `VULNERABILITY_STATUS_CHANGE_EVENT`. To express
> **how long a vulnerability has been open**, use `vulnerability.resolution.change_date`
> (populated on every row). A resolution-time proxy (MTTR) **is** computable from
> `resolution.change_date` without `first_seen` — see
> [§ Resolution time (MTTR proxy)](#resolution-time-mttr-proxy--openresolved-per-affected-object).

> **Vulnerability lifecycle (auto-resolution).** RVA does not require user action
> to resolve a vulnerability — it auto-resolves when the underlying signal
> disappears. **Third-party (`CODE_LIBRARY` / `SOFTWARE`)**: resolved when no
> process group reports the vulnerable component for >2 hours (library upgraded,
> component unused, no traffic post-restart, process stopped). **Code-level
> (`CODE`, CLV)**: resolved when a process restart followed by OneAgent
> re-analysis finds no exploitable data flow. On a re-open (RESOLVED → OPEN), only
> `vulnerability.resolution.change_date` updates (to the re-open transition).

## Contents

- [Routing: DT RVA vs External](#routing-dt-rva-vs-external)
- [Full Snapshot Queries — Steps 1–4 Canonical Pipeline](#dt-rva-full-snapshot-queries)
- [Count by Risk Level](#dt-rva-count-by-risk-level-simplified)
- [Runtime Assessment Workflows](#dt-rva-runtime-assessment-workflows)
- [Lifecycle Workflows](#dt-rva-lifecycle-workflows)
- [Time-Series Trends](#dt-rva-time-series-trends-7-days-3h-buckets)
- [Entity Scoping Workflows](#dt-rva-entity-scoping-workflows) · rankings → [vulnerabilities-entities.md](vulnerabilities-entities.md)
- [Code-Level Vulnerability (CLV) Workflows](#dt-rva-code-level-vulnerability-clv-workflows)
- [Tracking Links & Remediation](#dt-rva-tracking-links--remediation)
- [Mute Audit](#dt-rva-mute-audit-who-muted-what-why-when)
- [Fix-Available Filter](#dt-rva-fix-available-filter)
- [Vulnerable Functions Detail](#dt-rva-vulnerable-functions-detail)
- [Per-Affected-Entity-Type Breakdown](#dt-rva-per-affected-entity-type-breakdown)
- [External Vulnerability Findings](#external-vulnerability-findings)
- [Advanced Workflows And Best Practices](vulnerabilities-dynatrace-advanced.md)

---

## Routing: DT RVA vs External

| Source | `event.type` filter | Provider filter |
|---|---|---|
| Dynatrace RVA | `in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT","VULNERABILITY_STATUS_CHANGE_EVENT","VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})` | `event.provider=="Dynatrace"` AND `event.level=="ENTITY"` |
| External providers | `event.type == "VULNERABILITY_FINDING"` | `filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"` |

### Stack-aware routing inside Dynatrace RVA

`vulnerability.stack` distinguishes the four kinds of vulnerabilities Dynatrace
reports. Each carries different fields and is detected by a different scanner.

| Stack | Source | Notes |
|---|---|---|
| `CODE_LIBRARY` | OSS / Maven / NPM / PyPI / Go modules etc. | Most common third-party CVE class. Carries `affected_entity.vulnerable_component.*`. Dynatrace runtime assessments fully populated. |
| `SOFTWARE` | Runtime / OS packages (RPM, DEB, runtime binaries) | Component matched on host packages or runtime. Dynatrace runtime assessments populated. |
| `CODE` | OneAgent IAST / Attack | **Code-level vulnerability (CLV)**. DSS always **10.0**. Carries `vulnerability.code_location.name`. `vulnerable_function.status` and `exposure.status` are not the relevant signals — entry-point and data-flow proof carry the assessment. Java 8+, .NET, Go only. |
| `CONTAINER_ORCHESTRATION` | Kubernetes / container info | Image- or orchestration-level findings. |

**Filter examples:**

```dql-snippet
| filter vulnerability.stack == "CODE"                                   // CLV only
| filter in(vulnerability.stack, array("CODE_LIBRARY","SOFTWARE"))       // third-party only
| filterOut vulnerability.stack == "CODE"                                // exclude CLV
```

---

## DT RVA: Full Snapshot Queries

RVA stores one state event per `(vulnerability, affected_entity)` pair. All full
snapshot queries share a 4-step pipeline. **Build any snapshot query by combining
Steps 1 + 2 (optional) + 3 + 4.**

### Step 1 — Base Filter + Dedup (always identical)

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT",
                        "VULNERABILITY_STATUS_CHANGE_EVENT",
                        "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
```

### Latest-known-state fallback when 30m is empty or stale

Use this fallback only after the canonical 30m snapshot returns zero rows or
obviously misses known RVA data. **Take Step 1 and change two things:** set
`from:now()-24h`, and add `| sort timestamp desc` immediately before the `dedup`.
The `dedup {vulnerability.display_id, affected_entity.id}` still collapses to one
latest row per `(vulnerability, affected entity)` pair, preserving snapshot semantics
while tolerating scan-cycle or ingest drift.

Report that the result is the "latest known state observed in the last 24h" when
using this fallback. For lifecycle questions ("new in 7d", "resolved in 24h"),
keep the snapshot/fallback fetch separate from the lifecycle predicate and apply
the user's horizon to `vulnerability.resolution.change_date` after the
per-vulnerability summarize.

> **Raw-row listings of state reports.** If you stop after Step 1 (one row per `(vulnerability, entity)` without summarizing), use the RVA entity namespaces in the projection — `dt.smartscape*` / `dt.entity*` / `dt.source*` are **null** on these events:
>
> ```dql
> | fieldsKeep timestamp, "affected_entity*", "related_entities*",
>             vulnerability.display_id, vulnerability.title,
>             vulnerability.risk.score, vulnerability.references.cve,
>             vulnerability.resolution.status, vulnerability.mute.status
> ```
>
> See [common-patterns.md § 17](common-patterns.md#17-entity-identifier-preservation-on-raw-listings).

### Step 2 — Optional Pre-Aggregation Filter (insert after Step 1, before Step 3)

| Scope | Filter to insert |
|---|---|
| Vulnerable component name (e.g. "log4j") | `\| filter contains(affected_entity.vulnerable_component.name,"log4j",caseSensitive:false)` |
| Specific CVE | `\| filter in("CVE-2021-44228", vulnerability.references.cve)` |
| CVE list (IoC / threat-report hunts) | `\| filter in(vulnerability.references.cve, array("CVE-A","CVE-B","CVE-C"))` — array-to-array intersection: matches if **any** of the finding's CVEs is in the target list. Validated form; see `threat-intelligence.md` § CVEs → vulnerabilities for the join-based variant. |
| Specific vulnerability by any ID or title keyword | `\| filter vulnerability.display_id == "<id>" OR vulnerability.id == "<id>" OR vulnerability.external_id == "<id>" OR contains(vulnerability.title,"<id>",caseSensitive:false)` |
| Host name (e.g. "easytravel-demo2") | `\| filter in("easytravel-demo2",related_entities.hosts.names) OR affected_entity.name=="easytravel-demo2"` |
| Specific K8s workload / host / service by name or ID | See [Vulnerabilities on a specific entity](#vulnerabilities-on-a-specific-entity-by-name-or-id) — use `related_entities.<group>.{names,ids}` and `affected_entity.*`; **not §5** (§5 fields are null on RVA events) |

> **Vulnerability ID formats:** `display_id` (`S-8517`), `id` (internal numeric string),
> `external_id` (advisory, e.g. `DTV-2026-GO-0001133` / NVD) — full cheatsheet in
> [data-model.md § Finding ID Format Cheatsheet](data-model.md#finding-id-format-cheatsheet).
> When the format is unknown use the multi-field OR above (the `contains(title,…)` arm is a
> keyword fallback for text, not ID matching). For CVEs use the dedicated
> `in("CVE-…", vulnerability.references.cve)` row (it's an array).

### Step 3 — Summarize to Vulnerability Level + Derived Status (shared block)

> **Use `vulnerability.risk.score` for filtering and ranking — not `cvss.base_score`.**
> `vulnerability.risk.score` is the Dynatrace Security Score (DSS): it is mute-aware (the
> `takeMax(if(mute.status!="MUTED", risk.score, else:0))` expression below excludes muted
> findings from the score), and it incorporates exposure, exploit availability, and
> function-in-use context that raw CVSS lacks. Only use `cvss.base_score` when the user
> explicitly asks for CVSS. The Step 3 derivation uses `vulnerability.risk.score`
> exclusively — do not substitute `cvss.base_score` into the threshold comparisons.

```dql-snippet
| sort {timestamp, direction:"descending"}
| summarize
{
  vulnerability.stack=takeAny(vulnerability.stack),
  vulnerability.type=takeAny(vulnerability.type),
  vulnerability.cvss.base_score=takeFirst(vulnerability.cvss.base_score),
  vulnerability.title=takeFirst(vulnerability.title),
  vulnerability.resolution.change_date=takeMax(vulnerability.resolution.change_date),
  vulnerability.references.cve=takeFirst(vulnerability.references.cve),
  vulnerability.risk.score=round(takeMax(if(vulnerability.mute.status!="MUTED",vulnerability.risk.score,else:0)),decimals:1),
  muteStatuses=collectDistinct(vulnerability.mute.status),
  resolutionStatuses=collectDistinct(vulnerability.resolution.status),
  functionStatuses=collectDistinct(vulnerability.davis_assessment.vulnerable_function_status),
  exposureStatuses=collectDistinct(vulnerability.davis_assessment.exposure_status),
  exploitStatuses=collectDistinct(vulnerability.davis_assessment.exploit_status),
  dataAssetStatuses=collectDistinct(vulnerability.davis_assessment.data_assets_status),
  affected_entity.ids=collectDistinct(affected_entity.id),
  affected_entity.names=collectDistinct(affected_entity.name),
  affected_entity.vulnerable_component.names=arrayRemoveNulls(collectArray(affected_entity.vulnerable_component.name)),
  related_entities.names=arrayConcat(arrayRemoveNulls(collectArray(related_entities.kubernetes_workloads.names, expand:true)),
                                     arrayRemoveNulls(collectArray(related_entities.kubernetes_clusters.names, expand:true)),
                                     arrayRemoveNulls(collectArray(related_entities.applications.names, expand:true)),
                                     arrayRemoveNulls(collectArray(related_entities.services.names, expand:true)),
                                     arrayRemoveNulls(collectArray(related_entities.hosts.names, expand:true)),
                                     arrayRemoveNulls(collectArray(related_entities.databases.names, expand:true))),
  related_entities.ids=arrayConcat(arrayRemoveNulls(collectArray(related_entities.kubernetes_workloads.ids, expand:true)),
                                   arrayRemoveNulls(collectArray(related_entities.kubernetes_clusters.ids, expand:true)),
                                   arrayRemoveNulls(collectArray(related_entities.applications.ids, expand:true)),
                                   arrayRemoveNulls(collectArray(related_entities.services.ids, expand:true)),
                                   arrayRemoveNulls(collectArray(related_entities.hosts.ids, expand:true)),
                                   arrayRemoveNulls(collectArray(related_entities.databases.ids, expand:true)))
},by: {vulnerability.display_id, vulnerability.id}
| fieldsAdd vulnerability.resolution.status=if(in("OPEN",resolutionStatuses), "OPEN", else: "RESOLVED"),
            vulnerability.mute.status=if(in("NOT_MUTED",muteStatuses), "NOT_MUTED", else: "MUTED"),
            vulnerability.vulnerable_function.status=if(in("IN_USE",functionStatuses), "IN_USE",
                   else:if(in("NOT_AVAILABLE",functionStatuses), "NOT_AVAILABLE", else:"NOT_IN_USE")),
            vulnerability.exposure.status=if(in("PUBLIC_NETWORK",exposureStatuses), "PUBLIC_NETWORK",
                   else:if(in("NOT_AVAILABLE",exposureStatuses), "NOT_AVAILABLE", else:"NOT_DETECTED")),
            vulnerability.exploit.status=if(in("AVAILABLE",exploitStatuses), "AVAILABLE", else:"NOT_AVAILABLE"),
            vulnerability.data_assets.status=if(in("REACHABLE",dataAssetStatuses), "REACHABLE",
                   else:if(in("NOT_AVAILABLE",dataAssetStatuses), "NOT_AVAILABLE", else:"NOT_DETECTED")),
            vulnerability.risk.level=if(vulnerability.risk.score>=9,"CRITICAL",
                   else:if(vulnerability.risk.score>=7,"HIGH",
                   else:if(vulnerability.risk.score>=4,"MEDIUM",
                   else:if(vulnerability.risk.score>=0.1,"LOW",
                   else:"NONE"))))
| fieldsRemove muteStatuses, resolutionStatuses, functionStatuses, exposureStatuses, exploitStatuses, dataAssetStatuses
```

**Why each stage exists:** Step 1 dedup keeps one latest row per
`(vulnerability, entity)` pair so per-entity aggregates aren't inflated; Step 3
summarize rolls per-entity rows into one row per vulnerability (so you can filter/sort
by `risk.score`, `references.cve`, `title`); Step 3 `fieldsAdd` derives
**vulnerability-level verdicts** from the per-entity status arrays using the precedence
below (a vulnerability is `OPEN` if any entity is `OPEN`, risk score is the max across
non-muted entities, etc.).

**Precedence rules for `fieldsAdd` derivations** (most-severe first):

| Field | Priority 1 | Priority 2 | Priority 3 | Default |
|---|---|---|---|---|
| `vulnerability.mute.status` | `NOT_MUTED` | — | — | `MUTED` |
| `vulnerability.resolution.status` | `OPEN` | — | — | `RESOLVED` |
| `vulnerability.vulnerable_function.status` | `IN_USE` | `NOT_AVAILABLE` | — | `NOT_IN_USE` |
| `vulnerability.exposure.status` | `PUBLIC_NETWORK` | `NOT_AVAILABLE` | `NOT_DETECTED` | `NOT_DETECTED` |
| `vulnerability.exploit.status` | `AVAILABLE` | — | — | `NOT_AVAILABLE` |
| `vulnerability.data_assets.status` | `REACHABLE` | `NOT_AVAILABLE` | — | `NOT_DETECTED` |
| `vulnerability.davis_assessment.assessment_mode` | `REDUCED` | `NOT_AVAILABLE` | — | `FULL` |

> **`ADJACENT_NETWORK`** intentionally falls through to `NOT_DETECTED` in the derived
> `vulnerability.exposure.status` (query raw `vulnerability.davis_assessment.exposure_status`
> for adjacent-network analysis — see Best Practices). **`assessment_mode` precedence is
> inverted** — `REDUCED` wins (degraded telemetry = more conservative outcome); `FULL` wins
> only when every entity was fully assessed.

**Naming note:** raw events carry full namespace
(`vulnerability.davis_assessment.exposure_status`, etc.); the Stage-3 `fieldsAdd`
collapses them to shortened forms (`vulnerability.exposure.status`, etc.). Downstream
filters and projections use the shortened forms.

> **Scope the summarize.** The summarize block above is the **full** aggregation
> used by the canonical RVA snapshot pattern. Trim to the fields you actually need for each
> specific query to keep results small and token-efficient.

### Step 4 — Final Filter Variants (append after Step 3)

| Use case | Append |
|---|---|
| Open, non-muted (baseline) | `\| filter vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED"` |
| Open + internet-exposed | `\| filter vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED" AND vulnerability.exposure.status=="PUBLIC_NETWORK"` |
| Open + critical with Dynatrace confirming | `\| filter vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED" AND vulnerability.risk.level=="CRITICAL" AND vulnerability.vulnerable_function.status=="IN_USE" AND vulnerability.exposure.status=="PUBLIC_NETWORK" AND vulnerability.exploit.status=="AVAILABLE"` |
| All (no filter) | _(omit)_ |
| Scope to a specific entity | See entity filter note below |

**Entity scoping after Step 3** — Step 3's `summarize` collects the per-entity-row scalars `affected_entity.id` and `affected_entity.name` into the arrays `affected_entity.ids` and `affected_entity.names` (via `collectDistinct`), and `arrayConcat`s the per-category `related_entities.*.ids` / `related_entities.*.names` sub-fields into the flat arrays `related_entities.ids` / `related_entities.names`. Once those arrays exist, entity scoping becomes a single `in()` check:

```dql-snippet
| filter in("<entity_id_or_name>", affected_entity.ids)
      or in("<entity_id_or_name>", affected_entity.names)
      or in("<entity_id_or_name>", related_entities.ids)
      or in("<entity_id_or_name>", related_entities.names)
```

Prefer entity scoping at Step 2 (pre-summarize) when you know the entity up front — it reduces the rows the summarize processes. Use the Step 4 form when the entity constraint is combined with post-summarize fields (`risk.level`, `resolution.status`, etc.) that don't exist before the summarize.

---

## Mute-Status-Separated Count (canonical reporting)

> **For "how many?" questions, use the simple `countIf` form below (one query, one row).**
> The risk-level–grouped form is for detailed breakdown analysis. Do **not** add
> `vulnerability.stack` grouping unless the user explicitly asks about stack type.

### Simple count ("how many?")

Apply Steps 1–3 (full pipeline to vulnerability level), then:

```dql-snippet
| summarize {
    Total        = count(),
    OpenNotMuted = countIf(vulnerability.resolution.status == "OPEN"
                           AND vulnerability.mute.status != "MUTED"),
    OpenMuted    = countIf(vulnerability.resolution.status == "OPEN"
                           AND vulnerability.mute.status == "MUTED"),
    Resolved     = countIf(vulnerability.resolution.status == "RESOLVED"),
    Critical     = countIf(vulnerability.risk.level == "CRITICAL"
                           AND vulnerability.resolution.status == "OPEN"
                           AND vulnerability.mute.status != "MUTED"),
    High         = countIf(vulnerability.risk.level == "HIGH"
                           AND vulnerability.resolution.status == "OPEN"
                           AND vulnerability.mute.status != "MUTED"),
    Medium       = countIf(vulnerability.risk.level == "MEDIUM"
                           AND vulnerability.resolution.status == "OPEN"
                           AND vulnerability.mute.status != "MUTED"),
    Low          = countIf(vulnerability.risk.level == "LOW"
                           AND vulnerability.resolution.status == "OPEN"
                           AND vulnerability.mute.status != "MUTED")
  }
// One row. OpenNotMuted is the primary answer; per-risk and muted/resolved are supplementary.
```

**Detailed breakdown by risk level** — always split by mute status (total counts alone
mislead, since muted vulnerabilities are suppressed but still open). Apply Steps 1–3, then
summarize per risk level:

```dql-snippet
| summarize {
    `Total vulnerabilities`=count(),
    `Open not muted`=countIf(vulnerability.mute.status=="NOT_MUTED" AND vulnerability.resolution.status=="OPEN"),
    `Open muted`=countIf(vulnerability.mute.status=="MUTED" AND vulnerability.resolution.status=="OPEN"),
    Resolved=countIf(vulnerability.resolution.status=="RESOLVED")
  }, by:{vulnerability.risk.level}
```

---

## DT RVA: Count by Risk Level (simplified)

A lighter variant — dedup per entity, then reduce to vulnerability level (no full
Step-3 summarize). Apply **Step 1** (§ DT RVA: Full Snapshot Queries), then:

```dql-snippet
| summarize {vulnerability.risk.score=takeMax(vulnerability.risk.score)}, by: {vulnerability.display_id}
| fieldsAdd vulnerability.risk.level = <derive from risk.score — see common-patterns.md § 1>
| summarize { Vulnerabilities=count(), maxScore=takeMax(vulnerability.risk.score) }, by:{vulnerability.risk.level}
| sort maxScore desc
```

---

## DT RVA: Runtime Assessment Workflows

### Critical that Dynatrace runtime assessment agrees is critical

Strongest signal for remediation priority — append after Step 3:

```dql-snippet
| filter vulnerability.resolution.status=="OPEN"
     AND vulnerability.mute.status!="MUTED"
     AND vulnerability.risk.level=="CRITICAL"
     AND vulnerability.vulnerable_function.status=="IN_USE"
     AND vulnerability.exposure.status=="PUBLIC_NETWORK"
     AND vulnerability.exploit.status=="AVAILABLE"
```

### Runtime-assessment-based risk fanout

```dql-snippet
// After Step 3:
| summarize vulnerabilities=count(),
            by: {
              vulnerability.exploit.status,
              vulnerability.vulnerable_function.status,
              vulnerability.data_assets.status,
              vulnerability.exposure.status
            }
| sort vulnerabilities desc
```

---

## DT RVA: Lifecycle Workflows

### New vulnerabilities in the last 24h / 7 days (UC-V3)

For DT RVA, "new" means the vulnerability first became `OPEN` within the window.
Filter on `vulnerability.resolution.change_date` — the timestamp of the last
status transition. **Keep the 30m snapshot window** — the 24h/7d scope is a
**post-derive filter** on the collapsed rows, not a wider fetch (see the
snapshot-vs-history rule at the top of this file). Apply **Steps 1 + 3**, then:

```dql-snippet
| filter vulnerability.resolution.status=="OPEN"
     AND toTimestamp(vulnerability.resolution.change_date) > now() - 24h
| sort vulnerability.resolution.change_date desc
```

### How long have open vulnerabilities been open

`vulnerability.resolution.change_date` (epoch **nanoseconds**) marks the transition into the
current state; for an OPEN vulnerability it is when it became open. Collect the **earliest**
OPEN transition across the per-entity rows as "open since" via a **non-dotted alias** by casting
in the Step-3 `summarize` (`open_since=toTimestamp(takeMin(if(vulnerability.resolution.status=="OPEN", vulnerability.resolution.change_date, else: null)))`),
then compute the open duration **immediately after the `summarize`**, before the status-deriving `fieldsAdd`. Apply Steps 1 + 3
(this snippet shows the full tail; `open_since` is added to the Step 3 `summarize`):

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT","VULNERABILITY_STATUS_CHANGE_EVENT",
                        "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"}) AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| summarize {
    vulnerability.title=takeFirst(vulnerability.title),
    open_since=toTimestamp(takeMin(if(vulnerability.resolution.status=="OPEN", vulnerability.resolution.change_date, else: null))),
    resolutionStatuses=collectDistinct(vulnerability.resolution.status),
    muteStatuses=collectDistinct(vulnerability.mute.status),
    vulnerability.risk.score=round(takeMax(if(vulnerability.mute.status!="MUTED",vulnerability.risk.score,else:0)),decimals:1)
  }, by:{vulnerability.display_id, vulnerability.id}
| fieldsAdd open_duration = now() - open_since        // compute right after summarize
| fieldsAdd vulnerability.resolution.status=if(in("OPEN",resolutionStatuses),"OPEN",else:"RESOLVED"),
            vulnerability.mute.status=if(in("NOT_MUTED",muteStatuses),"NOT_MUTED",else:"MUTED"),
            vulnerability.risk.level=if(vulnerability.risk.score>=9,"CRITICAL",else:if(vulnerability.risk.score>=7,"HIGH",else:if(vulnerability.risk.score>=4,"MEDIUM",else:if(vulnerability.risk.score>=0.1,"LOW",else:"NONE"))))
| filter vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED"
| sort open_duration desc                             // longest-open first
| fields open_since, open_duration, vulnerability.display_id, vulnerability.title, vulnerability.risk.level
| limit 50
```

### Recently resolved vulnerabilities

```dql-snippet
| filter vulnerability.resolution.status=="RESOLVED"
| filter toTimestamp(vulnerability.resolution.change_date) >= now() - 7d
| sort vulnerability.resolution.change_date desc
```

### Resolution time (MTTR proxy) — open→resolved per affected object

A resolution-time proxy **is** computable from `resolution.change_date` (OPEN→RESOLVED
transition, both carried on `VULNERABILITY_STATUS_CHANGE_EVENT`), without `first_seen`. It equals
true detection-to-resolution **only for vulnerabilities that never reopened**, counts
**auto-resolutions** as resolutions, and is bounded by the change-event fetch window — so treat
it as time-to-resolution-by-any-cause, not patch velocity.

**Method:** per `(vulnerability.id, affected_entity.id)`, diff the OPEN-transition `change_date`
and the RESOLVED-transition `change_date` from `VULNERABILITY_STATUS_CHANGE_EVENT`; average the
diffs = MTTR. Both transitions are emitted as status-change events at transition time — no state
reports needed.

```dql
// CHANGE-EVENT-ONLY — no state reports. Fetch window = OPEN-transition lookback:
// widen it past your oldest open to reduce censoring (it caps measurable TTR).
fetch security.events, from:now()-30d
| filter event.provider=="Dynatrace"
| filter event.type=="VULNERABILITY_STATUS_CHANGE_EVENT" AND event.level=="ENTITY"
| fieldsAdd open_date     = if(vulnerability.resolution.status=="OPEN",     toTimestamp(vulnerability.resolution.change_date)),
            resolved_date = if(vulnerability.resolution.status=="RESOLVED", toTimestamp(vulnerability.resolution.change_date))
| summarize {
    open_date     = takeMax(open_date),       // latest OPEN transition (most recent spell if reopened)
    resolved_date = takeMax(resolved_date)    // latest RESOLVED transition
  }, by: {vulnerability.id, affected_entity.id}
| filter isNotNull(resolved_date)             // resolved pairs only
// optional: report only resolutions within a shorter period, independent of the open lookback
// | filter resolved_date > now()-7d
| fieldsAdd ttr = resolved_date - open_date   // duration; open_date/resolved_date are timestamps
| summarize {
    resolved_pairs = count(),
    censored       = countIf(isNull(open_date)),  // opened before the fetch window → MTTR is a LOWER BOUND
    mttr           = avg(if(ttr>0s, ttr)),
    median_hours   = median(if(ttr>0s, (resolved_date-open_date)/1h)),
    p90_hours      = percentile(if(ttr>0s, (resolved_date-open_date)/1h), 90)
  }
// If censored > 0, widen the fetch window; if it then returns an incomplete-result
// warning, you've hit the read-limit ceiling — report MTTR as a lower bound.
```

**Caveats:**
- **The fetch window is the OPEN lookback, not a snapshot window.** The 30m state-report rule
  does not apply here — this query uses only change events. Widen it to capture long-lived opens
  (open transitions are status-change events, so a wider window reaches them directly — no state
  reports needed).
- **Right-censored at the window** — if `censored > 0`, opens older than the fetch window were
  missed; MTTR is a lower bound. Widen the fetch to reduce it. Verified on demo.live: 121/6,985
  resolved pairs dropped at 30d (max open age 322 d); widening to 90d recovered 47 more but hit
  the 10 s read limit (incomplete result).
- **Performance ceiling** — on high-volume tenants a wide change-event window can still hit the
  10 s read limit. Do not use `samplingRatio` — RESOLVED rows are one-per-pair and would be
  dropped, undercounting. When the incomplete-result warning fires, treat MTTR as a lower bound.
- **Auto-resolution counts** — RVA auto-resolves when the component is absent >2 h; those pairs
  are indistinguishable from patched remediations. On auto-resolution-dominated tenants the
  median will be near 2 h. Always show median + p90 next to the mean so the skew is visible.
- **Entity-weighted** — each `(vuln, entity)` pair contributes one TTR; a vuln on N entities
  counts N×. For per-vulnerability weighting, group `by:{vulnerability.id}` and use
  `takeMin(open_date)` / `takeMax(resolved_date)` across entities.
- Use `/24h` not `/1d` (`/1d` triggers a calendar-duration deprecation warning); `avg(ttr)`
  returns a `duration` value.

---

## DT RVA: Time-Series Trends (7 days, 3h buckets)

Filter for open / non-muted vulnerabilities **after** `dedup` so the trend is
built from deduplicated rows.

> **For trend / "X over time" questions, use `makeTimeseries` — not
> `bin(timestamp, …) + summarize`.** `bin()` produces a flat tabular aggregation
> per bucket; the user asked for a time-series, and downstream chart-tile
> rendering expects a `timeseries`-typed column. See
> [common-patterns.md § Mistakes #9](common-patterns.md#mistakes-to-avoid)
> for the full rationale.

**Open vulnerability count over time:**

```dql
fetch security.events, from:now()-7d
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT",
                        "VULNERABILITY_STATUS_CHANGE_EVENT",
                        "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
  AND event.level=="ENTITY"
| dedup {timestamp, vulnerability.id}
| filter vulnerability.resolution.status == "OPEN"
  AND vulnerability.mute.status != "MUTED"
| makeTimeseries {Vulnerabilities=countDistinctExact(vulnerability.id)}, time: timestamp, interval:3h
| fieldsAdd `Open vulnerabilities`=arrayLast(Vulnerabilities)
```

**Affected entity count over time** — same query with two changes:

- Replace `dedup {timestamp, vulnerability.id}` → `dedup {timestamp, affected_entity.id}`
- Replace `countDistinctExact(vulnerability.id)` → `countDistinctExact(affected_entity.id)`
- Remove the trailing `fieldsAdd arrayLast` line

---

## DT RVA: Entity Scoping Workflows

**Entity rankings** ("most vulnerable hosts / K8s workloads / components", "which
entities are affected by CVE X") and the shared "Resolving RVA entity names via
Smartscape" pattern live in
[vulnerabilities-entities.md](vulnerabilities-entities.md).
**External-scanner vulnerability findings** (incl. component rankings) → moved to
[vulnerabilities-external.md](vulnerabilities-external.md).

This section covers **scoping RVA to a known entity** — listing the affected entities
for a specific vulnerability, or the vulnerabilities on a specific host / workload / CVE.

### Named entity list for a specific vulnerability

Use `VULNERABILITY_STATE_REPORT_EVENT` only (not the 3-event union) — state reports carry the full
entity context; STATUS_CHANGE/TRACKING_LINK_CHANGE are not needed for entity listing. Dedup by
`{affected_entity.id, vulnerability.id}` for one row per affected entity.

> **Always include `affected_entity.*` in the projection.** When `affected_entity.type == "HOST"` or
> `"KUBERNETES_NODE"`, the directly-affected entity is itself a host or node and may not appear in
> `related_entities.hosts.*` — it would be silently omitted if you project only the related arrays.

**Shared base (apply both options below to this):**

```dql
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_STATE_REPORT_EVENT"
     AND event.provider == "Dynatrace"
     AND vulnerability.display_id == "S-2647"
     AND isNotNull(affected_entity.id)
| dedup {affected_entity.id, vulnerability.id}
```

**Option A — Simple list** (return the names array as-is, no expand needed):

```dql-snippet
| fields vulnerability.display_id, vulnerability.title,
         affected_entity.id, affected_entity.name, affected_entity.type,
         related_entities.hosts.names, related_entities.hosts.ids
```

**Option B — One row per host / full detail** (for one-row-per-host fanout or further Smartscape investigation):

```dql-snippet
| expand related_host.id = related_entities.hosts.ids
| lookup [
  smartscapeNodes "*"
], sourceField:related_host.id, lookupField:id_classic, fields:{dt.smartscape_source.id=id, related_host.name=name}
| filterOut isNull(dt.smartscape_source.id)
| fields related_host.id, related_host.name, dt.smartscape_source.id,
         affected_entity.id, affected_entity.name, affected_entity.type
```

`filterOut isNull(dt.smartscape_source.id)` drops IDs with no active Smartscape node (expired or
decommissioned entities). For other entity types, swap `related_entities.hosts.ids/names` for
`related_entities.kubernetes_workloads.ids/names`, `related_entities.services.ids/names`, etc.
`smartscapeNodes "*"` handles all types without narrowing.

If 30m is empty, use the 24h latest-known-state fallback. To look up by advisory ID instead of
`display_id`, use the multi-field OR filter from [§ Step 2](#step-2--optional-pre-aggregation-filter-insert-after-step-1-before-step-3).

---

### Vulnerabilities on a specific entity (by name or ID)

RVA `VULNERABILITY_STATE_REPORT_EVENT` events embed entity refs directly in the payload — the
generic Smartscape/entity namespaces (`dt.smartscape*`, `dt.entity*`, `dt.source*`) are **null** on
RVA events; [common-patterns.md §5](common-patterns.md#5-wide-entity-scoping-or-chain) does **not**
apply here. Use `affected_entity.*` (directly-affected entity) and
`related_entities.<group>.{ids,names}` (blast-radius entities) instead.

Scope **before the Step 3 summarize** (pre-aggregation) for efficiency. Pick the route based on
what the user supplies:

#### Route 1 — Smartscape node ID (two-step: resolve both IDs, then filter with both)

When the user supplies a Smartscape node ID, RVA events may store either the Smartscape node format
or the classic entity ID format in `related_entities.*` — use `toSmartscapeId()` to look up both,
then include both in the RVA filter.

> **Do not use `iAny(array[] == value)` for array membership** — this is not valid DQL. Use
> `in(value, array)` for a single value, or `in({value1, value2}, array)` for a set-literal
> intersection when checking multiple values.

**Step 1 — resolve both IDs from Smartscape:**

```dql
smartscapeNodes "*"
| filter id == toSmartscapeId("K8S_CLUSTER-74407E507406AE84")
| fields id, id_classic
```

Returns:
- `id` — Smartscape node ID (e.g. `K8S_CLUSTER-74407E507406AE84`)
- `id_classic` — classic entity ID (e.g. `KUBERNETES_CLUSTER-B4A001031F545EE3`)

**Step 2 — scope the RVA snapshot with both IDs:**

```dql
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_STATE_REPORT_EVENT"
     AND event.provider == "Dynatrace"
     AND (in({"K8S_CLUSTER-74407E507406AE84","KUBERNETES_CLUSTER-B4A001031F545EE3"}, related_entities.kubernetes_clusters.ids)
          OR in(affected_entity.id, {"K8S_CLUSTER-74407E507406AE84","KUBERNETES_CLUSTER-B4A001031F545EE3"}))
| dedup vulnerability.display_id, sort:{timestamp desc}
| fields vulnerability.display_id, vulnerability.title,
         vulnerability.risk.level, vulnerability.risk.score
| sort vulnerability.risk.score desc
```

Both IDs are included in the set literal because RVA events may store either format. The
`OR in(affected_entity.id, {...})` fallback is included because some entity types (HOST,
KUBERNETES_NODE) can be the directly-affected entity rather than appearing in `related_entities.*`.

> For general `smartscapeNodes` / `id_classic` resolution patterns across entity types see
> [dt-sec-contextualization/references/entity-enrichment.md](../../dt-sec-contextualization/references/entity-enrichment.md).

#### Route 2 — direct display name or already-classic ID (no resolution)

When the user supplies a display name or an entity ID that is already in classic form
(`CLOUD_APPLICATION-…`, `HOST-…`, etc.), filter directly — no resolution step needed.

Insert after Step 1 dedup, before Step 3 summarize:

```dql-snippet
// By display name — checks both blast-radius (related) and directly-affected entity:
| filter in("<workload-name>", related_entities.kubernetes_workloads.names)
       OR affected_entity.name == "<workload-name>"

// By classic ID:
| filter in("<CLOUD_APPLICATION-XXXXXXXXXXXXXXXX>", related_entities.kubernetes_workloads.ids)
       OR affected_entity.id == "<CLOUD_APPLICATION-XXXXXXXXXXXXXXXX>"
```

Always check both `related_entities.<group>.*` **and** `affected_entity.*`. For `hosts` and
`kubernetes_nodes`, the `OR affected_entity.id ==` branch is not merely a safety net — these entity
types frequently appear as the *directly-affected* entity and will not be in `related_entities.hosts.*`
in that case, so omitting the OR silently misses them. For `kubernetes_workloads`, `services`,
`applications`, and `databases`, `affected_entity.*` will not match (those types never appear as
`affected_entity.type`), but including the OR is a safe catch-all that costs nothing.

#### Classic ID prefix gotcha

`related_entities.<group>.ids` carry **classic entity IDs** — the type prefix often differs from the
group name. The headline gotcha: `kubernetes_workloads.ids` stores `CLOUD_APPLICATION-…` IDs (not
`KUBERNETES_WORKLOAD-…`). Observed prefixes:

| Group | Observed classic ID prefix |
|---|---|
| `kubernetes_workloads` | `CLOUD_APPLICATION-` **(not `KUBERNETES_WORKLOAD-`)** |
| `kubernetes_clusters` | `KUBERNETES_CLUSTER-` |
| `hosts` | `HOST-` |
| `services` | `SERVICE-` |
| `applications` | `APPLICATION-` |
| `databases` | `SERVICE-` (same prefix as services — use the group name to distinguish) |

`.names` carry display names and are **positionally paired** with `.ids` — either can match the same
entity, and both routes return identical result sets for the same entity.

#### Choosing the right group

Pick the `related_entities.<group>` matching the entity type:

| Entity type | Use group |
|---|---|
| K8s workload (Deployment, DaemonSet, StatefulSet, …) | `kubernetes_workloads` |
| K8s cluster | `kubernetes_clusters` |
| Host | `hosts` |
| Service | `services` |
| Application (DT-monitored web app) | `applications` |
| Database | `databases` |

For genuinely cross-type "what entities are affected by this CVE?" questions, use the all-types
flat union (`related_entities.ids` / `related_entities.names`) that the canonical Step 3 rollup
builds — see [vulnerabilities-entities.md § Related-entity union](vulnerabilities-entities.md#related-entity-union-blast-radius-across-types).

#### Dedup key when scoping to one entity

When the query is scoped to one entity pre-aggregation, `dedup vulnerability.display_id` alone
counts distinct CVEs on that entity. This intentionally diverges from the canonical
`dedup {vulnerability.display_id, affected_entity.id}` key: with the entity fixed up front,
per-entity dedup would over-count across the blast-radius rows.

#### Typed arrays (Step 2) vs flat rollup (Step 4)

Typed per-group arrays (`related_entities.kubernetes_workloads.{ids,names}`) exist on raw events —
use them for Step 2 pre-aggregation scoping. The flat `related_entities.{ids,names}` arrays exist
only **after** Step 3's `arrayConcat` rollup — use that form only when combining the entity
constraint with post-summarize fields (`risk.level`, `resolution.status`).

---

## DT RVA: Code-Level Vulnerability (CLV) Workflows

CLV findings (`vulnerability.stack == "CODE"`) are detected by OneAgent through
data-flow analysis. They always score 10.0 (Critical) and surface on
**Java 8+, .NET, and Go** processes. Use `vulnerability.code_location.name`
to drill to the source file + line.

### Open CLV findings with code location

Apply **Step 1** + `| filter vulnerability.stack == "CODE"` (Step 2), then a CLV-focused
summarize/projection:

```dql-snippet
| summarize {
    vulnerability.title=takeFirst(vulnerability.title),
    vulnerability.type=takeFirst(vulnerability.type),
    vulnerability.code_location.name=takeFirst(vulnerability.code_location.name),
    vulnerability.technology=takeFirst(vulnerability.technology),
    resolutionStatuses=collectDistinct(vulnerability.resolution.status),
    muteStatuses=collectDistinct(vulnerability.mute.status),
    affected_entity.names=collectDistinct(affected_entity.name),
    affectedEntities=countDistinctExact(affected_entity.id)
  }, by: {vulnerability.display_id, vulnerability.id}
| fieldsAdd vulnerability.resolution.status=if(in("OPEN",resolutionStatuses),"OPEN",else:"RESOLVED"),
            vulnerability.mute.status=if(in("NOT_MUTED",muteStatuses),"NOT_MUTED",else:"MUTED")
| filter vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED"
| fields vulnerability.display_id, vulnerability.title, vulnerability.type,
         vulnerability.technology, vulnerability.code_location.name,
         affected_entity.names, affectedEntities
| sort affectedEntities desc
| limit 50
```

### CLV vs third-party split (count summary)

Apply **Step 1**, then a lighter stack-bucket summary:

```dql-snippet
| summarize { resolutionStatuses=collectDistinct(vulnerability.resolution.status),
              muteStatuses=collectDistinct(vulnerability.mute.status),
              vulnerability.stack=takeFirst(vulnerability.stack),
              riskScore=takeMax(vulnerability.risk.score) },
            by: {vulnerability.display_id, vulnerability.id}
| fieldsAdd resolution=if(in("OPEN",resolutionStatuses),"OPEN",else:"RESOLVED"),
            mute=if(in("NOT_MUTED",muteStatuses),"NOT_MUTED",else:"MUTED"),
            stackBucket=if(vulnerability.stack=="CODE","Code-level (CLV)",
                       else:if(vulnerability.stack=="CODE_LIBRARY","Third-party library",
                       else:if(vulnerability.stack=="SOFTWARE","Runtime / OS package",
                       else:if(vulnerability.stack=="CONTAINER_ORCHESTRATION","Container / K8s",
                       else:"Other"))))
| filter resolution=="OPEN" AND mute=="NOT_MUTED"
| summarize { Vulnerabilities=count(),
              Critical=countIf(riskScore>=9),
              High=countIf(riskScore>=7 AND riskScore<9) },
            by: {Stack=stackBucket}
| sort Vulnerabilities desc
```

---

## DT RVA: Tracking Links & Remediation

Tracking links are user-attached URLs (Jira tickets, wiki pages, runbooks)
emitted via `VULNERABILITY_TRACKING_LINK_CHANGE_EVENT`. Use them to measure
remediation progress.

> **Do not confuse with `vulnerability.external_url`.** Two fields look related but
> are different:
> - `vulnerability.tracking_link.url` — **user-attached** remediation link (Jira
>   ticket, wiki page, runbook). Populated only when someone has actually
>   attached a link in the Dynatrace UI. This is the field for
>   "do we have a tracking link / Jira ticket?" questions.
> - `vulnerability.external_url` — **provider-emitted** reference URL (NVD page,
>   vendor advisory, etc.). Populated by the security scanner for almost every
>   finding. Filtering `external_url != ""` will return nearly every
>   vulnerability and is **not** an answer to "is this tracked for remediation?".
>
> Same distinction for the IDs: `vulnerability.tracking_link.text` is the
> user-typed display text; `vulnerability.external_id` is the provider's CVE/NVD
> identifier.

### Open vulnerabilities WITH a tracking link

Apply Steps 1–3 with these added to the Step 3 `summarize` block:

```dql-snippet
trackingLinkUrls=collectDistinct(vulnerability.tracking_link.url),
trackingLinkTexts=collectDistinct(vulnerability.tracking_link.text),
```

Then append:

```dql-snippet
| fieldsAdd hasTrackingLink=if(arraySize(trackingLinkUrls)>0,true,else:false)
| filter vulnerability.resolution.status=="OPEN"
     AND vulnerability.mute.status!="MUTED"
     AND hasTrackingLink==true
| fields vulnerability.display_id, vulnerability.title, vulnerability.risk.level,
         trackingLinkUrls, trackingLinkTexts
```

### Critical / high vulnerabilities WITHOUT a tracking link (action backlog)

Same as the WITH-link query, but change the filter to `hasTrackingLink==false` and
add `AND in(vulnerability.risk.level, array("CRITICAL","HIGH"))`, then
`| sort vulnerability.risk.score desc`.

### Tracking-link coverage rate

```dql-snippet
| filter vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED"
| summarize { Open=count(), Tracked=countIf(hasTrackingLink==true) }
| fieldsAdd `Tracking coverage %` = round(Tracked*100.0/Open, decimals:1)
```

---

## DT RVA: Mute Audit (who muted what, why, when)

Mute metadata lives on raw events; do **not** collapse to vulnerability-level
when the question is "who muted this and why" — keep the per-entity row. Apply
**Step 1**, then filter to muted rows and project the mute fields:

```dql-snippet
| filter vulnerability.mute.status == "MUTED"
| fields timestamp, vulnerability.display_id, vulnerability.title,
         affected_entity.id, affected_entity.name,
         vulnerability.mute.reason, vulnerability.mute.user,
         vulnerability.mute.comment, vulnerability.mute.change_date
| sort vulnerability.mute.change_date desc
```

**`vulnerability.mute.reason` values:** `FALSE_POSITIVE`, `IGNORE`,
`CONFIGURATION_NOT_AFFECTED`, `OTHER`. (`AFFECTED` always maps to
`mute.status == "NOT_MUTED"` — it's the "not actually muted" reason.)

**Mute-reason breakdown:** on the same Step-1 base + `filter vulnerability.mute.status == "MUTED"`,
replace the `fields` projection with
`| summarize Affected=countDistinctExact(affected_entity.id), Vulnerabilities=countDistinctExact(vulnerability.display_id), by:{vulnerability.mute.reason} | sort Affected desc`.

---

## DT RVA: Fix-Available Filter

`vulnerability.is_fix_available` (boolean) marks vulnerabilities for which
upstream has shipped a fix. Combine with runtime-assessment filters to build a
"fix-now backlog."

Add both the flag and the remediation text to the Step 3 summarize —
`isFixAvailable=takeAny(vulnerability.is_fix_available)` and
`fixRecommendation=takeAny(vulnerability.remediation.description)` — then:

```dql-snippet
| filter vulnerability.resolution.status=="OPEN"
     AND vulnerability.mute.status!="MUTED"
     AND vulnerability.risk.level=="CRITICAL"
     AND isFixAvailable == true
| fields vulnerability.display_id, vulnerability.title, vulnerability.references.cve,
         vulnerability.risk.level, vulnerability.risk.score, isFixAvailable, fixRecommendation
| sort vulnerability.risk.score desc
```

`vulnerability.remediation.description` carries the human-readable fix guidance (e.g. the
target upgrade version) — surface it so the result is actionable, not just a yes/no flag.

---

## DT RVA: Vulnerable Functions Detail

`affected_entity.vulnerable_functions` is the array of FQCN methods the
OneAgent observed executing. Useful when you need "which exact functions
in my code are reaching the vulnerable library?"

Apply **Step 1**, then filter to in-use functions and expand the array:

```dql-snippet
| filter vulnerability.davis_assessment.vulnerable_function_status == "IN_USE"
| expand fn = affected_entity.vulnerable_functions
| filter isNotNull(fn)
| summarize entities=countDistinctExact(affected_entity.id),
            vulnerabilities=countDistinctExact(vulnerability.display_id),
            sampleVulns=arraySlice(collectDistinct(vulnerability.display_id), from: 0, to: 5),
            by: {function=fn}
| sort entities desc
| limit 20
```

> **Requires** the OneAgent `Java vulnerable function reporting` (or equivalent
> per-language) feature to be enabled. If `vulnerable_functions` is consistently
> empty for IN_USE rows, that feature is off.

---

## DT RVA: Per-Affected-Entity-Type Breakdown

`affected_entity.type` is one of `PROCESS_GROUP`, `HOST`, `KUBERNETES_NODE`
(occasionally `PROCESS_GROUP_INSTANCE`). To roll up "how much of this
vulnerability lives on each kind of entity":

Apply **Step 1** (per-entity question — filtering status pre-Stage-3 is fine here), then:

```dql-snippet
| filter vulnerability.resolution.status == "OPEN"
     AND vulnerability.mute.status == "NOT_MUTED"
| summarize Vulnerabilities=countDistinctExact(vulnerability.display_id),
            Entities=countDistinctExact(affected_entity.id),
            by: {affected_entity.type, vulnerability.stack}
| sort Vulnerabilities desc
```

Note: filtering on `vulnerability.resolution.status` / `vulnerability.mute.status`
**before** Stage 3 is acceptable here because we're answering a per-entity
question — we want to count entities whose row was OPEN, not derive a
vulnerability-level verdict.

---

## External Vulnerability Findings

External SCA / SAST / image-scanner findings (`VULNERABILITY_FINDING`, one-shot
events — no RVA dedup/summarize-to-state pipeline) have their own reference:
**[vulnerabilities-external.md](vulnerabilities-external.md)**. It covers the base
external query, the Vulnerabilities-app SD-compatibility check, top-N external
vulnerabilities, vulnerable container images, the "newly reported this period"
anti-join, and the cross-provider view.

---

For AI-workload findings and extended best-practice guidance, use
**[vulnerabilities-dynatrace-advanced.md](vulnerabilities-dynatrace-advanced.md)**.
