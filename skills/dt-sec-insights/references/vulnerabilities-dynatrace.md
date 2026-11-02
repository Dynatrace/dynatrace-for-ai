# Dynatrace Vulnerabilities — `security.events`

Dynatrace-generated vulnerability data: **Runtime Vulnerability Analytics (RVA) state
reports** (the canonical snapshot pipeline below) and **Dynatrace-generated
`VULNERABILITY_FINDING` events** (§ AI-workload vulnerabilities — findings scoped to AI
workloads). For **external** SCA / SAST / image-scanner findings see
[vulnerabilities-external.md](vulnerabilities-external.md).

> **Cross-references:** field reference → [data-model.md](data-model.md) ·
> risk-level mapping, status aggregation precedence, mute-status reporting rule,
> time-window rules → [common-patterns.md](common-patterns.md) · KPIs, top-N
> tables, trend charts → [dashboard-patterns.md](dashboard-patterns.md).

> **Snapshot vs. history.** DT RVA queries start with a **30-minute fixed window**
> (`from:now()-30m`). State reports usually emit every ~15 min; the 30m window
> captures the latest cycle when ingestion is healthy. This is a snapshot window,
> not history. If the 30m snapshot is empty or clearly stale, use the controlled
> 24h latest-known-state fallback below — do not simply widen every RVA query by
> default. For historical trend analysis use `makeTimeseries` over a longer
> window (see [vulnerabilities-lifecycle.md § Time-Series Trends](vulnerabilities-lifecycle.md#dt-rva-time-series-trends-7-days-3h-buckets)).
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
> [vulnerabilities-lifecycle.md § Resolution time (MTTR proxy)](vulnerabilities-lifecycle.md#resolution-time-mttr-proxy--openresolved-per-affected-object).

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
- [Mute-Status-Separated Count](#mute-status-separated-count-canonical-reporting)
- [Runtime Assessment Workflows](#dt-rva-runtime-assessment-workflows)
- [Entity Scoping Workflows](#dt-rva-entity-scoping-workflows) (routing: rankings → [vulnerabilities-rankings.md](vulnerabilities-rankings.md); one entity → [One known entity](#one-known-entity--step-2-scope))
- [External Vulnerability Findings](#external-vulnerability-findings)
- [Best Practices](#best-practices)
- Lifecycle (new / resolved / open-duration / MTTR), time-series trends, CLV, tracking links, mute audit, fix-available, vulnerable functions, per-entity-type breakdown → [vulnerabilities-lifecycle.md](vulnerabilities-lifecycle.md)
- AI-workload vulnerabilities → dt-sec-contextualization `ai-workload-vulnerabilities.md`

---

## Routing: DT RVA vs External

| Source | `event.type` filter | Provider filter |
|---|---|---|
| Dynatrace RVA | `in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT","VULNERABILITY_STATUS_CHANGE_EVENT","VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})` | `event.provider=="Dynatrace"` AND `event.level=="ENTITY"` |
| External providers | `event.type == "VULNERABILITY_FINDING"` | `filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"` |

Lifecycle (new / resolved / open-duration / MTTR), trends over time, CLV drill-down, tracking links, mute audit, fix-available, vulnerable functions and per-entity-type breakdown live in [vulnerabilities-lifecycle.md](vulnerabilities-lifecycle.md); those queries reuse Steps 1–3 below.

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
| filter vulnerability.stack == "CODE_LIBRARY"                           // third-party libraries
| filter in(vulnerability.stack, array("CODE_LIBRARY","SOFTWARE"))       // + runtime/OS packages
| filterOut vulnerability.stack == "CODE"                                // exclude CLV
```

"Third-party library" means `CODE_LIBRARY` only; add `SOFTWARE` only when the user asks for runtime / OS packages too.

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

> **Raw-row listings of state reports** (stopping after Step 1, no summarize): `dt.smartscape*` is **null** on these events, so project the RVA entity namespaces (`fieldsKeep timestamp, "affected_entity*", "related_entities*", …`) per [common-patterns.md § 17](common-patterns.md#17-entity-identifier-preservation-on-raw-listings).

### Step 2 — Optional Pre-Aggregation Filter (insert after Step 1, before Step 3)

| Scope | Filter to insert |
|---|---|
| Vulnerable component name (e.g. "log4j") | `\| filter contains(affected_entity.vulnerable_component.name,"log4j",caseSensitive:false)` |
| Specific CVE | `\| filter in("CVE-2021-44228", vulnerability.references.cve)` |
| CVE list (IoC / threat-report hunts) | `\| filter in(vulnerability.references.cve, array("CVE-A","CVE-B","CVE-C"))` — array-to-array intersection: matches if **any** of the finding's CVEs is in the target list. Validated form; see `dt-sec-ioc-hunting` `hunt-security-events.md` § Report-driven correlation for the join-based variant. |
| Specific vulnerability by any ID or title keyword | `\| filter vulnerability.display_id == "<id>" OR vulnerability.id == "<id>" OR vulnerability.external_id == "<id>" OR contains(vulnerability.title,"<id>",caseSensitive:false)` |
| One known entity (host / K8s workload / service, by name or id) | Not a one-line literal: see [One known entity](#one-known-entity--step-2-scope) (typed `related_entities.<group>.{names,ids}` OR `affected_entity.*`; **not** common-patterns §5, its fields are null on RVA events). Keyword / substring across entities: the Step 4 fragment |

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

> **Copy the Step 3 summarize block intact** for any listing or ranking question (it keeps `vulnerability.stack`,
> `resolution.change_date`, `affected_entity.ids`, `vulnerable_component.names`, `related_entities.ids`). It is lean
> **only** in variants explicitly labelled "trimmed" (entity rankings, grouped counts): they may drop collectors.

### Step 4 — Final Filter Variants (append after Step 3)

| Use case | Append |
|---|---|
| Open, non-muted (baseline) | `\| filter vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED"` |
| Open + internet-exposed | `\| filter vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED" AND vulnerability.exposure.status=="PUBLIC_NETWORK"` |
| Open + critical with Dynatrace confirming | `\| filter vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED" AND vulnerability.risk.level=="CRITICAL" AND vulnerability.vulnerable_function.status=="IN_USE" AND vulnerability.exposure.status=="PUBLIC_NETWORK" AND vulnerability.exploit.status=="AVAILABLE"` |
| All (no filter) | _(omit)_ |
| Scope to a specific entity | See entity filter note below |

**Entity scoping after Step 3** — Step 3's `summarize` collects the per-entity-row scalars `affected_entity.id` and `affected_entity.name` into the arrays `affected_entity.ids` and `affected_entity.names` (via `collectDistinct`), and `arrayConcat`s the per-category `related_entities.*.ids` / `related_entities.*.names` sub-fields into the flat arrays `related_entities.ids` / `related_entities.names`. Once those arrays exist, entity scoping becomes a single `in()` check.

**Placeholders:** `<entity_id_or_name>` — one entity, as a plain string: either its display name (e.g. `unguard-proxy-service-*`) or its **classic** (2nd-gen) id as the RVA events carry it (e.g. `PROCESS_GROUP-0E4D22455A8B9A25`, `HOST-AA17D60ECB741637`). Take the value from an earlier RVA result (`affected_entity.ids` / `affected_entity.names` / `related_entities.*`), or resolve a Smartscape id through `smartscapeNodes` (`id_classic`) as described in `dt-sec-contextualization` `rva-entity-resolution.md` § Smartscape id -> classic id. These are plain strings in string arrays, so no `toSmartscapeId()` wrapper is needed here. The block is a fragment: append it after Step 3.

```dql-snippet
| filter in("<entity_id_or_name>", affected_entity.ids)
      or in("<entity_id_or_name>", affected_entity.names)
      or in("<entity_id_or_name>", related_entities.ids)
      or in("<entity_id_or_name>", related_entities.names)
```

Prefer entity scoping at Step 2 (pre-summarize) when you know the entity up front — it reduces the rows the summarize processes. Use the Step 4 form when the entity constraint is combined with post-summarize fields (`risk.level`, `resolution.status`, etc.) that don't exist before the summarize.

**Keyword / substring scope** ("unguard entities", no single entity named) — same placement, with a `Match` field saying whether the keyword hit the directly affected entity or only a related one.

**Placeholders:** `<kw>` — the keyword, lowercase (e.g. `unguard`); it is compared against `lower(...)` of the name arrays, so keep it lowercase. Append after Step 3 (full block, since `affected_entity.names` / `related_entities.names` must exist):

```dql-snippet
| filter vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED"
| filter iAny(contains(lower(affected_entity.names[]),"<kw>"))
      OR iAny(contains(lower(related_entities.names[]),"<kw>"))
| fieldsAdd Match = if(iAny(contains(lower(affected_entity.names[]),"<kw>")), "direct", else: "related")
```

---

## Mute-Status-Separated Count (canonical reporting)

> **For "how many?" questions, use the simple `countIf` form below (one query, one row).**
> The risk-level–grouped form is for detailed breakdown analysis. Do **not** add
> `vulnerability.stack` grouping unless the user explicitly asks about stack type.

### Simple count ("how many?")

Apply Steps 1–3 (full pipeline to vulnerability level), then:

```dql-snippet
| summarize {
    Total=count(),
    OpenNotMuted=countIf(vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED"),
    OpenMuted=countIf(vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status=="MUTED"),
    Resolved=countIf(vulnerability.resolution.status=="RESOLVED"),
    Critical=countIf(vulnerability.risk.level=="CRITICAL" AND vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED"),
    High=countIf(vulnerability.risk.level=="HIGH" AND vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED"),
    Medium=countIf(vulnerability.risk.level=="MEDIUM" AND vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED"),
    Low=countIf(vulnerability.risk.level=="LOW" AND vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED")
  }
// One row. OpenNotMuted is the primary answer; per-risk and muted/resolved are supplementary.
```

**Grouped breakdown by risk level and mute status** — total counts alone mislead, since
muted vulnerabilities are suppressed but still open. Self-contained, with Step 3 trimmed to the
fields this count needs. Muted rows score 0 (mute-aware score), so they land under level `NONE`:

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT",
                        "VULNERABILITY_STATUS_CHANGE_EVENT",
                        "VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| sort {timestamp, direction:"descending"}
| summarize {
    vulnerability.risk.score=round(takeMax(if(vulnerability.mute.status!="MUTED",vulnerability.risk.score,else:0)),decimals:1),
    muteStatuses=collectDistinct(vulnerability.mute.status),
    resolutionStatuses=collectDistinct(vulnerability.resolution.status)
  }, by: {vulnerability.display_id, vulnerability.id}
| fieldsAdd vulnerability.resolution.status=if(in("OPEN",resolutionStatuses), "OPEN", else: "RESOLVED"),
            vulnerability.mute.status=if(in("NOT_MUTED",muteStatuses), "NOT_MUTED", else: "MUTED"),
            vulnerability.risk.level=if(vulnerability.risk.score>=9,"CRITICAL",
                   else:if(vulnerability.risk.score>=7,"HIGH",
                   else:if(vulnerability.risk.score>=4,"MEDIUM",
                   else:if(vulnerability.risk.score>=0.1,"LOW",
                   else:"NONE"))))
| fieldsRemove muteStatuses, resolutionStatuses
| filter vulnerability.resolution.status=="OPEN"
| summarize {Vulnerabilities=countDistinctExact(vulnerability.display_id), maxScore=takeMax(vulnerability.risk.score)},
            by:{vulnerability.risk.level, vulnerability.mute.status}
| sort maxScore desc
```

---

## DT RVA: Runtime Assessment Workflows

### Critical that Dynatrace runtime assessment agrees is critical

Strongest remediation-priority signal: the Step 4 row "Open + critical with Dynatrace confirming".

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

## DT RVA: Entity Scoping Workflows

Route by the question; every route reuses Steps 1–3 above.

| Question | Where |
|---|---|
| Rankings: most vulnerable hosts / K8s workloads / components | [vulnerabilities-rankings.md](vulnerabilities-rankings.md) (typed `related_entities.<group>.ids`, grouped on in-event ids and names; Smartscape resolution: dt-sec-contextualization `rva-entity-resolution.md` § Resolving a ranking result) |
| Vulnerabilities of ONE known entity (name, classic id, or Smartscape id) | [One known entity](#one-known-entity--step-2-scope) below |
| Affected entities of ONE vulnerability (named list, blast radius) | [vulnerabilities-rankings.md § Named entity list for a specific vulnerability](vulnerabilities-rankings.md#named-entity-list-for-a-specific-vulnerability) |
| Keyword / substring scope across entities | the Step 4 post-summarize entity fragment, including its `Match` variant |
| External-scanner findings (incl. component rankings) | [vulnerabilities-external.md](vulnerabilities-external.md) |

Never scope RVA events with the cross-provider `dt.smartscape*` OR-chain ([common-patterns.md § 5](common-patterns.md#5-wide-entity-scoping-or-chain)): those fields are null on RVA events.

### One known entity — Step 2 scope

Build the query as Step 1 + this Step 2 filter + Step 3 intact + the Step 4 baseline (drop that last
filter to include resolved and muted vulnerabilities). RVA events store **classic** ids, so a
Smartscape id (`<TYPE>-` + 16 hex characters) must be resolved to `id_classic` first
(`dt-sec-contextualization` `rva-entity-resolution.md` § Smartscape id -> classic id); a display name or a
classic id needs no lookup.

**Placeholders:**

- `<VALUES>` — the entity identifiers as comma-separated quoted strings, written inside the set literal `{…}`: any mix of the classic id, the Smartscape id, or the display name, e.g. `"K8S_CLUSTER-F867CA38C2E66AF1","KUBERNETES_CLUSTER-8D1821868AEBCC21"` or `"unguard-proxy-service"`. Plain strings, no `toSmartscapeId()` (these arrays hold strings).
- `<GROUP>` — the `related_entities.<GROUP>` matching the entity type in the table below.

```dql-snippet
| filter in({<VALUES>}, related_entities.<GROUP>.ids)
      OR in({<VALUES>}, related_entities.<GROUP>.names)
      OR in(affected_entity.id, {<VALUES>})
      OR in(affected_entity.name, {<VALUES>})
```

`related_entities.<GROUP>.ids` carry classic ids whose prefix often differs from the group name
(`kubernetes_workloads.ids` hold `CLOUD_APPLICATION-…`, not `KUBERNETES_WORKLOAD-…`); `.names` are
display names paired with `.ids`, and either arm matches the same entity.

| Entity type | `related_entities.<GROUP>` | Classic id prefix |
|---|---|---|
| K8s workload (Deployment, DaemonSet, StatefulSet, …) | `kubernetes_workloads` | `CLOUD_APPLICATION-` |
| K8s cluster | `kubernetes_clusters` | `KUBERNETES_CLUSTER-` |
| Host | `hosts` | `HOST-` |
| Service | `services` | `SERVICE-` |
| Database | `databases` | `SERVICE-` (the group name distinguishes) |
| Application (DT-monitored web app) | `applications` | `APPLICATION-` |

- **Keep the `affected_entity.*` arms.** For HOST and KUBERNETES_NODE the entity is usually the
  directly-affected one and is absent from `related_entities.hosts.*`; without the arms it is silently
  missed. For the other types they never match but cost nothing.
- **Typed vs flat arrays.** The typed `related_entities.<GROUP>.*` arrays exist on raw events (use them
  for this pre-summarize scope); the flat `related_entities.{ids,names}` exist only after Step 3 (use
  the Step 4 fragment when combining the entity with post-summarize fields such as `risk.level`).
- **Empty 30m snapshot** — use the 24h latest-known-state fallback above and say so.

---

## External Vulnerability Findings

External SCA / SAST / image-scanner findings (`VULNERABILITY_FINDING`, one-shot
events — no RVA dedup/summarize-to-state pipeline) have their own reference:
**[vulnerabilities-external.md](vulnerabilities-external.md)**. It covers the base
external query, the Vulnerabilities-app SD-compatibility check, top-N external
vulnerabilities, vulnerable container images, the "newly reported this period"
anti-join, and the cross-provider view.

---

## Best Practices

1. **Always use the three-event-type union for RVA snapshot queries** — state reports alone miss transitions. AI-workload queries (UC-AI1 / UC-AI2, dt-sec-contextualization `ai-workload-vulnerabilities.md`) use `VULNERABILITY_FINDING` — the three-event union does **not** apply to them.
2. **Dedup on the composite key** `{vulnerability.display_id, affected_entity.id}` - deduping on either field alone corrupts aggregates.
3. **Derive vulnerability-level status in Step 3** - never filter `vulnerability.resolution.status == "OPEN"` before the `fieldsAdd` when answering a vulnerability-level question; the pre-derived field is per-entity. Filtering pre-Stage-3 is fine when the question is genuinely per-entity.
4. **Use the shortened runtime-assessment names from Step 3 on** (`vulnerability.exposure.status`, `.exploit.status`, `.vulnerable_function.status`, `.data_assets.status`; see the Step 3 naming note).
5. **Prefer Dynatrace runtime assessments for triage** - `vulnerability.risk.level` is contextual and `vulnerability.risk.score` never exceeds `vulnerability.cvss.base_score`.
6. **`vulnerability.stack` is `CODE` / `CODE_LIBRARY` / `SOFTWARE` / `CONTAINER_ORCHESTRATION`** - not `THIRD_PARTY` / `FIRST_PARTY` / `CODE_LEVEL`.
7. **CLV (`stack=="CODE"`) always scores 10.0** - see [vulnerabilities-lifecycle.md § CLV Workflows](vulnerabilities-lifecycle.md#dt-rva-code-level-vulnerability-clv-workflows).
8. **Exposure precedence** is in the Step 3 table; query raw `vulnerability.davis_assessment.exposure_status` for adjacent-network analysis.
9. **`NOT_AVAILABLE` outranks `NOT_DETECTED` / `NOT_IN_USE`** (Step 3 precedence table).
10. **Lean summarize only in variants labelled "trimmed"** - everywhere else copy Step 3 intact (Step 3 note).
11. **`affected_entity.vulnerable_component.name` is singular per entity**, but collected into plural arrays at vulnerability level.
12. **Never use `vulnerability.parent.*`** (deprecated; derive from Step 3).
13. **Mute metadata is per-entity** - never collapse it to vulnerability-level ([vulnerabilities-lifecycle.md § Mute Audit](vulnerabilities-lifecycle.md#dt-rva-mute-audit-who-muted-what-why-when)).
14. **Simple count questions use one summarize with `countIf`** - avoid adding unrequested grouping dimensions.

---

For AI-workload findings (`GENAI_SERVICE`-scoped `VULNERABILITY_FINDING`), use
**dt-sec-contextualization** `ai-workload-vulnerabilities.md`.
