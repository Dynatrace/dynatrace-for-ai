# Common Query Building Blocks

Cross-cutting patterns reused across vulnerability, compliance, detection, coverage,
and entity-enrichment queries. Each block is named so per-domain references can
point here without repeating code.

> **No default `dt.system.bucket` filter; add one only when the user explicitly names a bucket.** Security events land in the default bucket
> `default_security` (the name varies per tenant), but users can route them to any custom bucket, so bucket scoping is irrelevant and can hide data.

---

## Contents

- [Common Query Building Blocks](#common-query-building-blocks)
  - [Contents](#contents)
  - [1. Risk Score → Risk Level Mapping](#1-risk-score--risk-level-mapping)
  - [5. Wide Entity Scoping OR Chain](#5-wide-entity-scoping-or-chain)
  - [6. Provider / Product Filter (case-insensitive)](#6-provider--product-filter-case-insensitive)
  - [7. Time Window Conventions](#7-time-window-conventions)
  - [8. Dynatrace-vs-External Routing Logic](#8-dynatrace-vs-external-routing-logic)
  - [12. Repository / Artifact Coalescing](#12-repository--artifact-coalescing)
  - [13. K8s Workload Resolution from CONTAINER smartscapeNode](#13-k8s-workload-resolution-from-container-smartscapenode)
  - [15. Default Summarization Recipe (cross-provider summary)](#15-default-summarization-recipe-cross-provider-summary)
  - [16. Result Limits for Top-N and Raw Listings](#16-result-limits-for-top-n-and-raw-listings)
  - [17. Entity-Identifier Preservation on Raw Listings](#17-entity-identifier-preservation-on-raw-listings)
    - [Cross-provider `*_FINDING` and scan-coverage events](#cross-provider-_finding-and-scan-coverage-events)
    - [RVA state/change events](#rva-statechange-events)
    - [When NOT to apply this](#when-not-to-apply-this)
    - [Don't double-list on RVA Stage 3 output](#dont-double-list-on-rva-stage-3-output)
  - [18. Lifecycle — what counts as "new" / "resolved" (per event family)](#18-lifecycle--what-counts-as-new--resolved-per-event-family)
  - [19. First seen / last seen](#19-first-seen--last-seen)
  - [Common Mistakes & Troubleshooting](#common-mistakes--troubleshooting)

---

## 1. Risk Score → Risk Level Mapping

The same thresholds apply to both score fields:

| Score field | Level field | Used in |
|---|---|---|
| `vulnerability.risk.score` | `vulnerability.risk.level` | DT RVA per-entity raw events and Stage-3 derivation |
| `dt.security.risk.score` | `dt.security.risk.level` | Cross-provider `*_FINDING` events (normalized score set at ingest) |

**Threshold table (identical for both):**

| Score | Level |
|---|---|
| ≥ 9.0 | CRITICAL |
| ≥ 7.0 | HIGH |
| ≥ 4.0 | MEDIUM |
| ≥ 0.1 | LOW |
| else | NONE |

**DT RVA (derive `vulnerability.risk.level` from score):**

```dql-snippet
| fieldsAdd vulnerability.risk.level=if(vulnerability.risk.score>=9,"CRITICAL",
                                     else:if(vulnerability.risk.score>=7,"HIGH",
                                     else:if(vulnerability.risk.score>=4,"MEDIUM",
                                     else:if(vulnerability.risk.score>=0.1,"LOW",
                                     else:"NONE"))))
```

**Cross-provider (derive `dt.security.risk.level` from score, when not already set):**

```dql-snippet
| fieldsAdd dt.security.risk.level=if(dt.security.risk.score>=9,"CRITICAL",
                                   else:if(dt.security.risk.score>=7,"HIGH",
                                   else:if(dt.security.risk.score>=4,"MEDIUM",
                                   else:if(dt.security.risk.score>=0.1,"LOW",
                                   else:"NONE"))))
```

`vulnerability.risk.score` is Dynatrace's contextual DSS (factors in exposure,
exploit availability, function usage) — never exceeds CVSS base. Prefer `risk.score`
for prioritization; report `vulnerability.cvss.base_score` only when the user asks
about CVSS. `dt.security.risk.score` is the normalized cross-provider score set at
ingest (external severity strings map to fixed values: Critical → 10.0, High → 8.9,
Medium → 6.9, Low → 3.9).

---

## 5. Wide Entity Scoping OR Chain

Match a user-supplied entity ID or name against every supported scoping field by building
a per-row array of field values and checking membership with `in()`.

**Single value (most common — inline the known ID/name):**

**Placeholders:** `<entity_id_or_name>` — one entity as a plain string: an id (typed Smartscape ids are fine, e.g. `PROCESS-2BFEC6517F8B5A64`, `HOST-D987BB6363604FE6`; cloud ids such as `i-0abc1234def567890`) or a display name (`host.name`, `object.name`, `k8s.*.name`). Take it from a previous result row or from `smartscapeNodes "<TYPE>" | fields id, name`. Do **not** wrap it in `toSmartscapeId()` here — the `toString()` calls below convert the typed fields so the comparison is string-to-string. The block is a filter fragment: append it after `fetch security.events, from:now()-24h` and an `event.type` filter.

```dql-snippet
| filter in("<entity_id_or_name>", arrayRemoveNulls(array(
    toString(dt.smartscape_source.id),
    toString(dt.smartscape.process),
    toString(dt.smartscape.host),
    toString(dt.smartscape.k8s_cluster),
    toString(dt.smartscape.k8s_node),
    toString(dt.smartscape.k8s_pod),
    toString(dt.smartscape.container), toString(dt.smartscape.k8s_namespace),
    toString(k8s.cluster.uid), toString(k8s.pod.uid),
    toString(aws.resource.id), toString(azure.resource.id), toString(gcp.resource.id),
    object.id, object.name, host.name,
    k8s.cluster.name, k8s.namespace.name, k8s.node.name,
    aws.resource.name, azure.resource.name, gcp.resource.name
  )))
```

**Multiple values (spread the user-supplied list):**

**Placeholders:** `<id1>`, `<id2>` — entity ids or names as plain strings (same kinds of values as above); add or remove entries to match the list. Written as `array("…","…")` (parentheses) — the set is the first argument of `in()`, so a row matches when any listed value appears in its field array.

```dql-snippet
| filter in(array("<id1>","<id2>"), arrayRemoveNulls(array(
    toString(dt.smartscape_source.id),
    toString(dt.smartscape.process),
    toString(dt.smartscape.host),
    toString(dt.smartscape.k8s_cluster),
    toString(dt.smartscape.k8s_node),
    toString(dt.smartscape.k8s_pod),
    toString(dt.smartscape.container), toString(dt.smartscape.k8s_namespace),
    toString(k8s.cluster.uid), toString(k8s.pod.uid),
    toString(aws.resource.id), toString(azure.resource.id), toString(gcp.resource.id),
    object.id, object.name, host.name,
    k8s.cluster.name, k8s.namespace.name, k8s.node.name,
    aws.resource.name, azure.resource.name, gcp.resource.name
  )))
```

Smartscape ID fields (`dt.smartscape.*`, `dt.smartscape_source.id`) are typed as
`SmartscapeId`; `toString()` converts them to string for uniform comparison with
user-supplied strings. `arrayRemoveNulls()` drops fields that are null on a given event
row — most events populate only a subset of these fields.

> **This OR-chain does NOT apply to RVA state/change events** (`VULNERABILITY_STATE_REPORT_EVENT`,
> `VULNERABILITY_STATUS_CHANGE_EVENT`). Those events embed entity refs in `affected_entity.*` and
> `related_entities.<group>.{ids,names}` — all §5 fields (`dt.smartscape*`, etc.) are
> **null** on them. For entity scoping on RVA events see
> [vulnerabilities-dynatrace.md § One known entity](vulnerabilities-dynatrace.md#one-known-entity--step-2-scope)
> and [§17 RVA state/change events below](#rva-statechange-events).

> **For entity-scoping on non-`security.events` row sets** (IoC matches, `smartscapeNodes` rows,
> enrichment output): use **dt-sec-contextualization** →
> `dt-sec-contextualization/references/entity-enrichment.md` (§ Entity-Scoping OR-Chain).

**Trim to the relevant fields.** Omit namespaces that can't match the entity type in
question (e.g. drop `k8s.*` / cloud resource fields when searching for a host or process).

**Placeholders:** `<entity_id_or_name>` — as above (a host or process id/name here).

```dql-snippet
// Host/process scope only
| filter in("<entity_id_or_name>", arrayRemoveNulls(array(
    toString(dt.smartscape_source.id),
    toString(dt.smartscape.process),
    toString(dt.smartscape.host),
    object.id, object.name, host.name
  )))
```

---

## 6. Provider / Product Filter (case-insensitive)

Check whether the user-supplied value matches either `event.provider` (vendor name, e.g. `"crowdstrike"`), `product.vendor` or `product.name` (specific product, e.g. `"falcon"`). `matchesValue` is case-insensitive by default, so no `lower()` is needed (and `lower()` on a field defeats the index).

**Single value (discovery / unknown string):**

**Placeholders:** `<provider_or_product>` — the vendor or product keyword as plain text, e.g. `crowdstrike` or `falcon`; casing does not matter (`matchesValue` is case-insensitive). Use it as a filter fragment after `fetch security.events` and an `event.type` filter.

```dql-snippet
| filter matchesValue(event.provider, "<provider_or_product>")
      OR matchesValue(product.vendor, "<provider_or_product>")
      OR matchesValue(product.name, "<provider_or_product>")
```

**Multiple values (discovery / unknown strings):**

**Placeholders:** `<p1>`, `<p2>` — keywords as above, written inside a set literal `{"…","…"}` (curly braces); add entries as needed.

```dql-snippet
| filter matchesValue(event.provider, {"<p1>", "<p2>"})
      OR matchesValue(product.vendor, {"<p1>", "<p2>"})
      OR matchesValue(product.name, {"<p1>", "<p2>"})
```

**Known provider — exact match preferred.** Once the provider string is confirmed via the discovery query (see [all-security-events.md § Providers & Products](all-security-events.md)), use exact equality to avoid false positives from providers whose names share a substring:

**Placeholders:** `<ExactProviderString>` / `<ExactProductString>` — the exact `event.provider` / `product.name` values from the discovery query (plain strings, case as shown, e.g. `Amazon GuardDuty` / `GuardDuty`).

```dql-snippet
| filter event.provider == "<ExactProviderString>"
      OR product.name == "<ExactProductString>"
```

A provider may appear via two ingestion paths (e.g. direct integration and via AWS Security Hub). Combine both exact values with `OR` when both paths are active in the tenant.

Reserve `contains(<field>, "…", caseSensitive:false)` for initial discovery or when the exact string is not yet known.

---

## 7. Time Window Conventions

| Pattern | Window | Why |
|---|---|---|
| DT RVA snapshots | **30m fixed** | Snapshot — captures latest 15-min state-report cycle; do not widen |
| DT KSPM snapshots | **1h fixed** | Aligned with scan-completion cycle inner-join; do not widen |
| RAP / external detection retrieval or current summary | `2h` first attempt | Event stream; matches Threats & Exploits app default — widen to `24h` only if zero rows returned |
| Cross-provider summary (aggregated count/breakdown) | **24h** | Summaries aggregate over time; broader window gives representative coverage |
| Single-finding drill-down (by id/title) | `24h` default | Point lookup |
| Coverage analysis | `7d` for discovery; `2h–24h` for recent scans | `VULNERABILITY_SCAN` events are sparse |

**Critical:** RVA and SPM are *snapshot* tools, not history. The 30m / 1h windows
are operational — they only ensure the latest state report or completed scan is
captured. They do NOT look back further. Don't widen them.

**Retrieval vs. summary distinction:** for detection queries, both retrieval and unqualified current summaries ("how many detections do I have?", "detections by severity", "show me latest detections") start at `2h` to match the Threats & Exploits app default, then widen to `24h` only when zero rows are returned. For non-detection cross-provider summaries (counts, breakdowns, "how many critical findings across providers") start at `24h` — these aggregate over time and a narrow window silently undercounts.

**DT-inclusive broad / posture-overview questions** ("which security products are integrated incl. Dynatrace-native?", posture overview, cross-category counts that include DT vulnerabilities/compliance) are **not** a single window — decompose into three streams, each on its own window (external + DT detections `24h`; DT RVA `30m`; DT KSPM `1h`), and merge. (A narrower "which external integrations are sending data?" stays a single external-only query.) See [all-security-events.md § Broad-Question Query Decomposition](all-security-events.md#broad-question-query-decomposition).

> **Detection-retrieval widen-on-empty rule:** start at `2h`; widen only when zero rows
> are returned. The authoritative fallback query and the list of intentionally-wider
> history/analytics exceptions live in
> [detections.md § Widen-on-empty fallback](detections.md).

> **Entity coverage empty-result rule:** when validating whether a **specific
> entity** is covered by a Dynatrace security capability, 0 relevant findings plus
> 0 relevant scan/scan-completed/coverage events means the entity is **not
> covered** by that capability. Explain that the capability is likely not enabled,
> not deployed, or not configured for that entity; do not present this as merely
> "no findings". See **dt-sec-contextualization** `runtime-coverage.md`.

---

## 8. Dynatrace-vs-External Routing Logic

The cross-provider summary pattern excludes Dynatrace-native VULNERABILITY/COMPLIANCE findings (they
belong to the RVA and SPM snapshot patterns), but keeps Dynatrace-native DETECTION findings:

```dql-snippet
| filterOut (product.vendor == "Dynatrace" or event.provider == "Dynatrace") and event.type != "DETECTION_FINDING"
```

**Implication:** for full coverage of vulnerabilities or compliance, **pair**
the Dynatrace RVA snapshot pattern (vulnerabilities) or the Dynatrace SPM snapshot
pattern (compliance) with the cross-provider summary. Only `DETECTION_FINDING` is
fully covered by the cross-provider summary alone.

The guard is null-safe (explicit Dynatrace exclusion on both `product.vendor` and `event.provider`,
so null-vendor external rows such as Runecast stay in); rationale in
[all-security-events.md § Double-Counting Guard](all-security-events.md#double-counting-guard).

---

## 12. Repository / Artifact Coalescing

External container scanners use one of two repository fields. Coalesce so a single
column works for both:

```dql-snippet
| fieldsAdd repository=coalesce(artifact.repository, container_image.repository)
```

---

## 13. K8s Workload Resolution from CONTAINER smartscapeNode

A CONTAINER node is part of exactly one workload — fan out the workload reference
via nested `coalesce`:

```dql-snippet
| expand dt.k8s.workload.id=coalesce(references[is_part_of.k8s_deployment],
                            coalesce(references[is_part_of.k8s_daemonset],
                              coalesce(references[is_part_of.k8s_cronjob],
                                coalesce(references[is_part_of.k8s_statefulset],
                                  coalesce(references[is_part_of.k8s_job],
                                    references[is_part_of.k8s_replicaset])))))
```

For HOST resolution (CONTAINER → host) use `references[runs_on.host]` instead.

---

## 15. Default Summarization Recipe (cross-provider summary)

Without a user-specified summarization, the cross-provider summary pattern collapses
results by provider × product × event type × risk level. This is the safe default
for any time window:

> **Do not drop `by:` keys without an explicit user request.** The four keys —
> `{event.provider, product.name, event.type, dt.security.risk.level}` — are mandatory for any
> cross-provider count or summary. Dropping any one silently merges rows from different providers,
> products, or finding types into a single count, corrupting the result.
>
> For container images and external findings, also preserve `object.name` (user-friendly display
> name for the scanned artifact), `object.id`, and the repository/digest identity fields
> (`container_image.digest`, `coalesce(artifact.repository, container_image.repository)`) in the
> `summarize` or projection **before ranking**. Pair `object.name` with `digest` or `repository` —
> names alone are not unique across registries or providers.

```dql-snippet
| summarize {
    findings.count = count(),
    finding.distinct.count = countDistinctExact(finding.id),
    affected_object.count = countDistinctExact(object.id),
    finding.ids = collectDistinct(finding.id, maxLength:10),
    finding.titles = collectDistinct(finding.title, maxLength:10),
    affected_object.types = collectDistinct(object.type, maxLength:10),
    affected_object.ids = collectDistinct(object.id, maxLength:10),
    affected_object.names = collectDistinct(object.name, maxLength:10),
    affected_smartscape.node.ids = arrayRemoveNulls(collectDistinct(coalesce(dt.smartscape_source.id,
                                                                             dt.smartscape.process,
                                                                             dt.smartscape.host,
                                                                             dt.smartscape.k8s_cluster,
                                                                             dt.smartscape.k8s_node,
                                                                             dt.smartscape.k8s_pod), maxLength:10)),
    vulnerable_components = arrayRemoveNulls(collectDistinct(coalesce(software_component.name, component.name), maxLength:10))
  }, by: {event.provider, product.name, event.type, dt.security.risk.level}
```

For longer time ranges (>24h), **always** apply a summarization — raw field
selection past 24h hits performance limits.

---

## 16. Result Limits for Top-N and Raw Listings

Security findings can be high-volume. Any query that returns raw rows (no
`summarize` / `makeTimeseries`) must be bounded unless the user explicitly asks
for all rows or an export-style result.

**Required limit rule:**

| User intent | Required query shape |
|---|---|
| "top X" / "last X" / "first X" | `| sort <ranking fields> desc` then `| limit X` |
| "top findings" with no number | Treat as top 50: `| sort <ranking fields> desc` then `| limit 50` |
| "show/list/latest findings" with no explicit "all" | Add `| limit 50` after the final `sort` |
| Pure summary (`summarize`, `makeTimeseries`, pass-rate, counts) | No default raw-row limit required; optionally limit high-cardinality grouped rankings |
| Explicit "all" / export request | Do not silently truncate; warn about volume and prefer a summary or scoped filters |

**Placement:** apply `limit` after deduplication, enrichment, final projection, and the
final user-relevant `sort`. A limit before `summarize`, `join`, or entity enrichment
can bias counts or drop matching entities.

```dql-snippet
| fieldsKeep timestamp, finding.id, finding.title, dt.security.risk.level,
         object.name, object.type, "dt.smartscape*"
| sort dt.security.risk.score desc, timestamp desc
| limit 50
```

For top-N summary tables, keep the aggregation grain first, then sort and limit:

```dql-snippet
| summarize Findings=countDistinctExact(finding.id), by:{event.provider, product.name, object.type}
| sort Findings desc
| limit 50
```

---

## 17. Entity-Identifier Preservation on Raw Listings

When a query projects raw rows for a listing (top / latest / list / drill-down — no `summarize`), keep the entity-identifier namespaces in the projection. Users asking for findings almost always want to know which entity each finding is on.

**The namespaces split by event family — they are NOT interchangeable:**

### Cross-provider `*_FINDING` and scan-coverage events

Applies to `DETECTION_FINDING`, `COMPLIANCE_FINDING`, external `VULNERABILITY_FINDING`, `VULNERABILITY_SCAN`, `COMPLIANCE_SCAN`. Post-ingest enrichment populates the generic Smartscape namespaces on these events.

Placeholders: none — the second line lists example finding fields; keep the ones you need. The block is a projection fragment appended to a listing query.

```dql-snippet
| fieldsKeep timestamp, "dt.smartscape*",
            finding.id, finding.title, dt.security.risk.level,
            object.id, object.name, object.type
```

What the wildcards match:

| Wildcard | Generation | Covers |
|---|---|---|
| `dt.smartscape*` | 3rd-gen (Smartscape) | `dt.smartscape_source.id` + `dt.smartscape_source.type` (UPPERCASE entity type of the source, e.g. `PROCESS`, `HOST`, `K8S_CLUSTER`, `AWS_EC2_INSTANCE`) and `dt.smartscape.process` / `.host` / `.container` / `.k8s_cluster` / `.k8s_node` / `.k8s_namespace` / `.k8s_pod` |

Legacy note: the old `dt.source_entity` / `dt.source_entity.type` pair (lowercase value such as `process_group_instance`) is superseded by `dt.smartscape_source.id` / `dt.smartscape_source.type`. It is populated only on Dynatrace process-sourced scan, finding and detection events, so do not project it, filter on it, or use it as a correlation key.

### RVA state/change events

Applies to `VULNERABILITY_STATE_REPORT_EVENT`, `VULNERABILITY_STATUS_CHANGE_EVENT`, `VULNERABILITY_TRACKING_LINK_CHANGE_EVENT`. These events embed resolved entity refs directly in the event payload; the generic `dt.smartscape*` namespace is **null** on RVA events — including them would produce empty columns.

```dql-snippet
| fieldsKeep timestamp, "affected_entity*", "related_entities*",
            vulnerability.display_id, vulnerability.title, vulnerability.risk.score,
            vulnerability.resolution.status, vulnerability.mute.status
```

`affected_entity.*` carries the directly affected entity (2nd-gen ID + name + type + vulnerable-component info, resolved in-event). `related_entities.{kubernetes_workloads,kubernetes_clusters,applications,services,hosts,databases}.{ids,names}` carries the indirect blast-radius entities (classic IDs + names) as arrays. Note: `.ids` carry classic entity IDs whose type prefix may differ from the group name — see the prefix table in [vulnerabilities-dynatrace.md § One known entity](vulnerabilities-dynatrace.md#one-known-entity--step-2-scope).

### When NOT to apply this

Pure summary queries — counts, pass rates, breakdown-by-risk-level, "how many" questions — should not project entity fields; aggregate them into the `summarize` block instead (see §15 cross-provider summary recipe and §16 RVA Stage 2 related-entity aggregation).

### Don't double-list on RVA Stage 3 output

If the query starts from the canonical RVA Stage 3 pipeline ([vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md)), Stage 3 already `collectDistinct`'s `affected_entity.ids/names` and `arrayConcat`'s `related_entities.*` into per-vulnerability arrays. Do not re-add `fieldsKeep "affected_entity*"` on top — those columns are already present as scalars in the post-summarize result.

---

## 18. Lifecycle — what counts as "new" / "resolved" (per event family)

"New" and "resolved" are detected differently per family — use the right signal:

| Family | "New" signal | "Resolved" signal |
|---|---|---|
| External findings (one-shot `*_FINDING`) | `toTimestamp(finding.time.created) > now()-Nd` | not modeled — compare presence across periods (anti-join; see the "new-not-in-prior-period" patterns in [vulnerabilities-external.md](vulnerabilities-external.md) / [compliance.md](compliance.md)) |
| DT-generated vulnerability findings (`VULNERABILITY_FINDING`) | finding rows re-emit every scan run (~15 min); use current-vs-prior **anti-join** on the scoped identity, such as `{genai_service.id, vulnerability.id}` for AI workloads | not modeled on the finding stream — compare presence across periods or use RVA lifecycle only when explicitly routed to state reports |
| DT RVA vulnerabilities (snapshot) | newly **OPEN**: `toTimestamp(vulnerability.resolution.change_date) > now()-Nd` (no "first-ever-seen" variant — `vulnerability.first_seen` is null on this pipeline) | `vulnerability.resolution.status == "RESOLVED"` (use `resolution.change_date` for when) |
| DT SPM compliance (per-rule/object snapshot) | rule-object pair absent in the prior scan period — period-over-period anti-join (see [compliance.md](compliance.md) § Week-over-Week Config Drift) | pair present in the prior period, absent now |

Keep the RVA/SPM snapshot fetch window fixed (30m / 1h) — apply the "new" horizon as a
**post-derive filter**, never by widening the fetch (see § 7).

### Two distinct "new" intents — do not conflate them

1. **"New(ly created) in the last N days"** — a property of each finding in
   isolation. The created-time filter from the table above is the correct and
   complete answer.
2. **"Reported in this period AND NOT in the previous period"** (also: "newly
   failing", "drift vs last week", "what appeared this week that wasn't there
   before") — a **set comparison between two periods**. This REQUIRES the
   prior-period anti-join (outer join + `isNull(right.…)`); a
   `finding.time.created` filter is **not equivalent**: external providers
   re-report long-known findings on every scan, `finding.time.created` is
   unreliable or vendor-relative for many providers, and the created-time
   shortcut silently misses findings that existed before but were first
   *reported to Dynatrace* this period. Canonical anti-join templates:
   - external vulnerabilities → [vulnerabilities-external.md § Critical external vulnerabilities newly reported in the last 7d](vulnerabilities-external.md#critical-external-vulnerabilities-newly-reported-in-the-last-7d-not-in-the-prior-7d)
   - external compliance → [compliance.md § External Compliance](compliance.md)
   - DT KSPM drift → [compliance.md § Week-over-Week Config Drift](compliance.md#dt-spm-week-over-week-config-drift-newly-failing-rules)

---

## 19. First seen / last seen

"Since when?", "first seen", "last seen", "when did this last occur" — pick the row for the data
family, then use the listed timestamp. This is the single home for these recipes; the per-domain
references point here or to the linked section.

| Question about | First seen | Last seen | Recipe |
|---|---|---|---|
| External findings (vulnerability / detection / compliance) | `takeMin(toTimestamp(finding.time.created))` — when the **source** created it | `takeMax(timestamp)` — last time it was **reported** to Dynatrace | Recipe A |
| DT detections (RAP, Automated Detections) | same fields (`finding.time.created` ≈ event time) | same fields | Recipe A with the RAP / Automated-Detections filter from [detections.md § Provider Routing](detections.md); per attacker IP see [detections.md § Top attacker IPs](detections.md) |
| External compliance — how long has a rule been failing on an object | same, grouped per `(finding.title, object.id)` | same | Recipe A, add `finding.title, object.id` to `by:` (30d window) |
| DT KSPM compliance | `takeMin` over history | `takeMax` over history | [compliance.md § DT SPM: Compliance-Finding Age](compliance.md) |
| DT RVA vulnerability "open since" / how long open | earliest OPEN transition of `vulnerability.resolution.change_date` | still open now (30m snapshot) | [vulnerabilities-lifecycle.md § How long have open vulnerabilities been open](vulnerabilities-lifecycle.md#how-long-have-open-vulnerabilities-been-open) — never `vulnerability.first_seen` (null on ENTITY rows) |
| Scans — when was X last scanned / scanner activity | `takeMin(coalesce(scan.time.completed, timestamp))` | `takeMax(...)` of the same | Recipe B |
| Is an integration still sending data / since when | `takeMin(timestamp)` | `takeMax(timestamp)` | [all-security-events.md § Which external integrations are active](all-security-events.md#which-external-integrations-are-active-and-volume) |

**Which timestamp.** `timestamp` is the event / ingest time and is re-stamped every time a scanner
re-reports a finding. `finding.time.created` is whatever the source writes: the **original creation
time** for some providers (Snyk findings up to ~57 days older than their ingest, Defender for Cloud
compliance findings back to 2025) but the **report / scan time** for others (Sonatype, Qualys, SonarQube — within about an hour of `timestamp` — and
DT RAP / KSPM, equal to it). So `takeMin(finding.time.created)` is "first created at the
source (or first reported, for report-time providers)", not "first seen by Dynatrace"; for the
latter use `takeMin(timestamp)` over a wide window. `event.start`, `event.end` and
`finding.time.modified` are not populated on security events — do not use them. On scans,
`scan.time.completed` is the source-side completion time (can predate ingest), so `coalesce(..., timestamp)`.

**Recipe A — findings (provider-scoped).**

**Placeholders:** `<ExactProviderString>` / `<ExactProductString>` — the exact `event.provider` / `product.name` strings from the discovery query in [all-security-events.md § Providers & Products](all-security-events.md#providers--products) (plain strings, e.g. `Amazon GuardDuty` / `GuardDuty`). Scope to a provider first: an unscoped `-30d` scan of external findings can exceed the scan limit. To answer per finding, rule or object, add `finding.title` and/or `object.id` to `by:` (or filter on `finding.id`).

```dql-template
fetch security.events, from:now()-30d
| filter event.provider == "<ExactProviderString>"
      OR product.name == "<ExactProductString>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter (not exists(compliance.result.status.level)
     OR compliance.result.status.level == "FAILED"
     OR compliance.status == "FAILED")
| summarize {
    Findings = countDistinctExact(finding.id),
    FirstCreated = takeMin(toTimestamp(finding.time.created)),
    LastCreated = takeMax(toTimestamp(finding.time.created)),
    LastReported = takeMax(timestamp)
  }, by: {event.provider, product.name, event.type}
| sort LastReported desc
```

**Recipe B — scans and scanner activity.** No placeholders; add `| filter event.provider == "<ExactProviderString>"` after the `event.type` filter to scope to one scanner.

```dql
fetch security.events, from:now()-7d
| filter in(event.type, {"VULNERABILITY_SCAN", "COMPLIANCE_SCAN", "COMPLIANCE_SCAN_COMPLETED"})
| summarize {
    Scans = count(),
    FirstScan = takeMin(coalesce(scan.time.completed, timestamp)),
    LastScan = takeMax(coalesce(scan.time.completed, timestamp))
  }, by: {event.provider, product.vendor, product.name, event.type}
| sort LastScan desc
```

**Pitfalls**

- **The window bounds "first seen".** `takeMin` / `takeMax` see only rows inside the `from:` window, so the result is the first seen **within the window**. When `FirstCreated` / `FirstScan` lands near the window start, treat it as "at least since" and widen (7d → 30d) for the true first seen, or say the answer is bounded by the window (and by bucket retention). Keep external-finding scans provider-scoped when widening.
- **Cast before comparing.** Wrap `finding.time.created` in `toTimestamp(...)` before `takeMin` / `takeMax` / `now() - ...`; `timestamp` is already a timestamp.
- **Created-time is not "new vs. the prior period".** "Appeared this week that wasn't there before" is the anti-join in § 18, not a first-seen filter.
- **No "resolved" for external findings.** `LastReported` means "still being reported at that time", not "closed at that time".

---

## Common Mistakes & Troubleshooting

Mistakes to avoid, best practices, and troubleshooting for unexpected results now live in
[mistakes-and-troubleshooting.md](mistakes-and-troubleshooting.md), the single home for that catalog.
Load it when a query returns unexpected results or counts disagree with the Vulnerabilities / Threats & Exploits / SPM apps.
