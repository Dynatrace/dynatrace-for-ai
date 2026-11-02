# Dynatrace Vulnerabilities — Lifecycle, Trends and Remediation

Load this when the question is about vulnerability lifecycle (new / resolved / open-duration / MTTR), trends over time, code-level (CLV) findings, tracking links, mute audit, fix-available, vulnerable functions or the per-entity-type breakdown; counts, rankings, CVE lookups and entity scope stay in [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md).

> **Prerequisite.** Apply Steps 1–3 from [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md) (base filter + dedup, optional Step 2 filter, summarize to vulnerability level) wherever a section below says "Steps 1 + 3", "Step 1" or "Step 3"; the 30m snapshot window, the 24h latest-known-state fallback and the lifecycle / `first_seen` notes also live there.

## Contents

- [Lifecycle Workflows](#dt-rva-lifecycle-workflows) (new / resolved, open-duration, [Resolution time (MTTR proxy)](#resolution-time-mttr-proxy--openresolved-per-affected-object))
- [Time-Series Trends](#dt-rva-time-series-trends-7-days-3h-buckets)
- [Code-Level Vulnerability (CLV) Workflows](#dt-rva-code-level-vulnerability-clv-workflows)
- [Tracking Links & Remediation](#dt-rva-tracking-links--remediation)
- [Mute Audit](#dt-rva-mute-audit-who-muted-what-why-when)
- [Fix-Available Filter](#dt-rva-fix-available-filter)
- [Vulnerable Functions Detail](#dt-rva-vulnerable-functions-detail)
- [Per-Affected-Entity-Type Breakdown](#dt-rva-per-affected-entity-type-breakdown)

---

## DT RVA: Lifecycle Workflows

### New vulnerabilities in the last 24h / 7 days (UC-V3)

For DT RVA, "new" means the vulnerability became `OPEN` within the window. Filter on
`vulnerability.resolution.change_date` (`takeMax` in Step 3 = the **last** status transition), so a vulnerability
opened long ago that re-opened on a new entity also counts as new; for strict first-opened use `open_since`
(`takeMin` over OPEN rows) in the next section. **Keep the 30m snapshot window** — the 24h/7d scope is a
**post-derive filter** on the collapsed rows, not a wider fetch (see the snapshot-vs-history rule at the top of
[vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md)). Apply **Steps 1 + 3**, then:

```dql-snippet
| filter vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED"
     AND toTimestamp(vulnerability.resolution.change_date) > now() - 24h
| sort vulnerability.resolution.change_date desc
```

For recently **resolved** instead, swap the first filter for `vulnerability.resolution.status=="RESOLVED" AND toTimestamp(vulnerability.resolution.change_date) >= now() - 7d`.

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
> [mistakes-and-troubleshooting.md § Mistakes #9](mistakes-and-troubleshooting.md#mistakes-to-avoid)
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
| makeTimeseries {Vulnerabilities=countDistinctApprox(vulnerability.id, precision:16)}, time: timestamp, interval:3h
| fieldsAdd `Open vulnerabilities`=arrayLast(Vulnerabilities)
```

`countDistinctApprox` at `precision:16` is used instead of `countDistinctExact` because
the exact variant raises an "exceeded 100000 distinct values" warning on large tenants.
The result is an approximation; on one small tenant (169 open vulnerabilities, 57 buckets)
it matched the exact count in every bucket. Switch back to `countDistinctExact` if an
audit-grade exact number is required.

**Affected entity count over time** — same query, but `dedup {timestamp, affected_entity.id}`, `countDistinctApprox(affected_entity.id, precision:16)`, and no trailing `fieldsAdd arrayLast`.

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
    vulnerability.references.cve=takeFirst(vulnerability.references.cve),
    open_since=toTimestamp(takeMin(if(vulnerability.resolution.status=="OPEN", vulnerability.resolution.change_date, else: null))),
    resolutionStatuses=collectDistinct(vulnerability.resolution.status),
    muteStatuses=collectDistinct(vulnerability.mute.status),
    affected_entity.names=collectDistinct(affected_entity.name),
    affectedEntities=countDistinctExact(affected_entity.id)
  }, by: {vulnerability.display_id, vulnerability.id}
| fieldsAdd vulnerability.resolution.status=if(in("OPEN",resolutionStatuses),"OPEN",else:"RESOLVED"),
            vulnerability.mute.status=if(in("NOT_MUTED",muteStatuses),"NOT_MUTED",else:"MUTED")
| filter vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED"
| fields open_since, vulnerability.display_id, vulnerability.title, vulnerability.type,
         vulnerability.technology, vulnerability.code_location.name, vulnerability.references.cve,
         affected_entity.names, affectedEntities
| sort affectedEntities desc
| limit 50
```

### CLV vs third-party split (count summary)

Apply **Step 1**, then a lighter stack-bucket summary. It uses the mute-aware score from Step 3, groups
by `{Stack, vulnerability.stack}` (the raw stack value stays visible next to the bucket, which also keeps the
`Other` bucket traceable), and carries a `None` column so the per-level columns add up to `Vulnerabilities`:

```dql-snippet
| sort {timestamp, direction:"descending"}
| summarize { resolutionStatuses=collectDistinct(vulnerability.resolution.status),
              muteStatuses=collectDistinct(vulnerability.mute.status),
              vulnerability.stack=takeFirst(vulnerability.stack),
              riskScore=round(takeMax(if(vulnerability.mute.status!="MUTED",vulnerability.risk.score,else:0)),decimals:1) },
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
              High=countIf(riskScore>=7 AND riskScore<9),
              Medium=countIf(riskScore>=4 AND riskScore<7),
              Low=countIf(riskScore>=0.1 AND riskScore<4),
              None=countIf(riskScore<0.1) },
            by: {Stack=stackBucket, vulnerability.stack}
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

With `hasTrackingLink` from the query above, after the open / non-muted filter: `| summarize { Open=count(), Tracked=countIf(hasTrackingLink==true) } | fieldsAdd \`Tracking coverage %\` = round(Tracked*100.0/Open, decimals:1)`.

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

Apply **Step 1**, then filter to open, non-muted, in-use rows (per-entity question: pre-Stage-3
filtering is fine, as in the per-entity-type breakdown below) and roll up per function:

```dql-snippet
| filter vulnerability.resolution.status=="OPEN" AND vulnerability.mute.status!="MUTED"
     AND vulnerability.davis_assessment.vulnerable_function_status=="IN_USE"
| expand fn = affected_entity.vulnerable_functions
| filter isNotNull(fn)
| summarize { entities=countDistinctExact(affected_entity.id),
              vulnerabilities=countDistinctExact(vulnerability.display_id),
              vulnerability.risk.score=round(takeMax(vulnerability.risk.score),decimals:1),
              vulnerability.ids=collectDistinct(vulnerability.display_id),
              vulnerability.cves=collectDistinct(vulnerability.references.cve, expand:true),
              vulnerability.titles=collectDistinct(vulnerability.title) }, by: {function=fn}
| fieldsAdd vulnerability.risk.level=if(vulnerability.risk.score>=9,"CRITICAL",else:if(vulnerability.risk.score>=7,"HIGH",else:if(vulnerability.risk.score>=4,"MEDIUM",else:if(vulnerability.risk.score>=0.1,"LOW",else:"NONE"))))
| sort vulnerability.risk.score desc, entities desc
| limit 20
```

> **Requires** the OneAgent `Java vulnerable function reporting` (or equivalent per-language)
> feature. If `vulnerable_functions` is consistently empty for IN_USE rows, it is off.

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
