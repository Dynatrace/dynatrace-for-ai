# Compliance Queries — `security.events`

Dynatrace Security Posture Management (SPM / XSPM) compliance findings and
external provider compliance findings.

> **Cross-references:** field reference → [data-model.md § Compliance Fields](data-model.md#compliance-fields-spm) ·
> time-window rules → [common-patterns.md](common-patterns.md).

> **Scope.** SPM has three flavors: KSPM (Kubernetes, DT-native security-analyzer-service), CSPM (cloud
> posture) and VSPM (VMware posture), the latter two via external/partner integrations. The DQL in this file
> targets **KSPM**. CSPM/VSPM ride on the same `security.events` table but use the cross-provider `finding.*`
> namespace, not `compliance.rule.*` — see [all-security-events.md](all-security-events.md) and § External
> Compliance below. KSPM assesses **Kubernetes resources only** (clusters, nodes, pods, deployments,
> statefulsets, daemonsets, jobs, cronjobs, replicasets, replication controllers): there are no DT-native
> findings for AWS / Azure / GCP / host / process entities, so "what's our AWS compliance posture?" needs CSPM
> or another external integration.

> **KSPM standards — `compliance.standard.short_name` is `CIS`, `DORA`, `NIST`, `DISA STIG` or `Security Essentials`.** STIG is the
> full `"DISA STIG"` label, not bare `"STIG"` (`== "STIG"` returns nothing). Scope with
> **`contains(compliance.standard.short_name, "<keyword>", caseSensitive:false)`** instead of equality — it
> tolerates the DISA prefix, version suffixes and case mismatches across all five. PCI DSS, ISO 27001, HIPAA,
> GDPR, BSI C5, TISAX, Cyber Essentials, Essential Eight, etc. arrive only via CSPM/VSPM or other external
> integrations and don't populate the KSPM rule namespace. CIS is mandatory for K8s; DORA / NIST / DISA STIG
> are opt-in (Settings → Application Security → Security Posture Management). Security Essentials rule ids
> carry the `DTSE-` prefix.

> **Snapshot vs. history.** DT SPM queries use a **1-hour fixed window** (`from:now()-1h`), aligned with the
> scan-completion cycle (an ActiveGate ships a fresh configuration dataset, typically hourly per K8s cluster),
> so the latest `COMPLIANCE_SCAN_COMPLETED` event is captured per object and the inner join succeeds. Widening
> adds cost, not history; if no scan completed in the last 1h for an object, its findings do NOT appear
> (inner-join behavior — by design). Widen past 1h only for genuine history questions (e.g. finding age).

> **Rule statuses.** The enum is `PASSED`, `FAILED`, `MANUAL`, `NOT_RELEVANT` — not `PASS`/`FAIL` — in
> `compliance.result.status.level`, **never** `event.status` (a generic `Active`/`Closed` lifecycle field,
> null or wrong on `COMPLIANCE_FINDING` rows).
> — Count failures with an explicit equality: `countIf(compliance.result.status.level == "FAILED")`. A negation
> (`!= "PASSED"`) wrongly folds `MANUAL` and `NOT_RELEVANT` into the failed count.
> — `NOT_RELEVANT` (rule doesn't apply to the object, e.g. a K8s version mismatch) is always excluded by the
> base filter and never counted in pass/fail totals. The SPM app's "Recommended" view excludes it; "Complete"
> includes it.
> — `MANUAL` (the analyzer can't auto-evaluate it; the Dynatrace docs say manual results aren't currently
> actionable) is a triage hint, not a remediable defect — never counted as `PASSED` or in a pass-rate numerator.
> — **Percent compliant** = `Passed / Rules`, rounded to a whole number, with `MANUAL` kept in `Rules`
>   (`Rules` = passed + manual + failed; `NOT_RELEVANT` is not counted). This is exactly what the SPM
>   Overview card shows per standard (for example 89 passed of 134 rules, 33 manual, 12 failed = 66%), and
>   it is the golden's `passRate`. When `Manual > 0`, you may add `Passed / (Passed + Failed)` as an
>   "auto-evaluated only" figure, labelled as such; never present it as the app's percentage. External
>   tools are per-finding rows (rule x object), so their figure is `Passed / Findings`: say so, and do not
>   sum or compare it with KSPM rule counts.
> — Per-rule precedence is `FAILED > MANUAL > PASSED` (Step 2 derives it); any re-derivation must follow it or
> the verdict silently disagrees with the SPM app.
> — The default tool filter is FAILED-only; to compute a pass rate, set `resultStatuses=ALL` so `PASSED` is in
> the denominator.

> **Field rules.**
> — Standard field: `compliance.standard.short_name` (not `compliance.rule.standard`, which does not exist in the Semantic Dictionary).
> — Severity field: `compliance.rule.severity.level` (not bare `compliance.rule.severity`, which resolves to nothing).
> — Latest-scan join uses `on: {scan.id}` shorthand — not `on: {left.scan.id == right.scan.id}` (`left.`/`right.` prefixes are body syntax only, not valid inside `on:`).
> — Pass rate must be computed on **per-rule** verdicts (after Step 2 rollup), not directly on raw per-`(rule, object)` rows.

> **No mute / exemption / waiver mechanism.** Unlike vulnerabilities, compliance findings have no `mute.*`
> namespace in `security.events`; "accepted risk" is not modeled in DQL (the SPM app may surface acceptance
> UI-side, but it isn't exposed to queries). If asked for "accepted compliance findings," explain the data isn't there.

---

## Routing: DT KSPM vs External (CSPM / VSPM / external posture tools)

| Source | `event.type` | Provider filter |
|---|---|---|
| Dynatrace KSPM | `COMPLIANCE_FINDING` | `product.vendor=="Dynatrace"` AND `product.name=="Security Posture Management"` AND `compliance.result.status.level != "NOT_RELEVANT"` |
| External (CSPM/VSPM + other posture tools) | `COMPLIANCE_FINDING` | `filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"` |

The `product.name == "Security Posture Management"` filter is the most precise
KSPM scope — `product.vendor == "Dynatrace"` alone matches RVA, RAP, and
Automated Detections too on certain event types.

Use the KSPM 1h latest-scan pipeline only for Dynatrace SPM/Kubernetes
questions. For AWS / Azure / GCP / PCI / ISO / HIPAA / GDPR and other non-KSPM
compliance questions, route to raw external `COMPLIANCE_FINDING` over `24h+`,
using the external taxonomy (`compliance.standards` / `compliance.policy` /
`compliance.control`), not the KSPM `compliance.rule.*` namespace.

**Section routing for non-obvious intents — jump directly, do not improvise:**

| Intent | Section |
|---|---|
| "configuration drift" / "newly failing rules" / "new violations vs last week" (DT KSPM) | [§ Week-over-Week Config Drift](#dt-spm-week-over-week-config-drift-newly-failing-rules) — prior-period **anti-join**; a `7d` fetch window or a created-time filter is NOT a substitute |
| External violations "by standard" / "by framework" | [§ External Compliance](#external-compliance-queries-cspm--vspm--external-posture-tools) — `compliance.standards` is an **array** (Runecast fills only `compliance.standard.short_name`): use the template's `coalesce` + `expand` before `summarize`, otherwise the per-standard breakdown collapses or drops providers |
| External findings "not present in the previous period" | [§ External Compliance](#external-compliance-queries-cspm--vspm--external-posture-tools) newness anti-join — same anti-join rule as drift |
| Top failing external rules | [§ External Compliance](#external-compliance-queries-cspm--vspm--external-posture-tools) — group by `compliance.control` / `compliance.policy` (+ expanded standard), not by `finding.title` alone |

---

## DT SPM: Base Pattern

> **Answer posture questions overall first; per-cluster only on request.** For
> "what is my compliance posture?" or "what is my DORA/CIS/NIST/STIG posture?" —
> run Steps 1+2 + "Grouped by Standard with Pass Rate" as the primary answer (one
> query). Do **not** generate a per-cluster breakdown unless the user explicitly
> asks ("by cluster", "per system", "which clusters fail"). If asked for both in
> one prompt, run two queries: standard summary first, then the per-cluster 3-step
> variant.

All Dynatrace compliance queries share two building blocks. **Build any query by
combining Step 1 + Step 2 + a variant extension.**

### Step 1 — Base Filter + Latest Scan Join (always identical)

The inner join enriches each finding with the latest scan's `scan.id`, `timestamp`,
`object.name`, and `object.type` per scanned entity (`object.id`).

```dql
fetch security.events, from:now()-1h
| filter event.type == "COMPLIANCE_FINDING"
     AND product.vendor=="Dynatrace"
     AND compliance.result.status.level != "NOT_RELEVANT"
| join [
    fetch security.events, from:now()-1h
    | filter event.type == "COMPLIANCE_SCAN_COMPLETED"
         AND product.vendor == "Dynatrace"
    | sort timestamp asc
    | summarize {
        scan.id = takeLast(scan.id),
        timestamp = takeLast(timestamp),
        object.name = takeLast(object.name),
        object.type = takeLast(object.type)
      }, by: {object.id}
  ], on: {scan.id}
```

### Step 2 — Per-Rule Summarize + Derived Status (shared block)

Groups findings by `compliance.rule.id`. Collects pass/fail/manual counts and all
related entity identifiers.

```dql-snippet
| summarize {
    compliance.rule.severity.level = takeFirst(compliance.rule.severity.level),
    compliance.standard.short_name = takeFirst(compliance.standard.short_name),
    compliance.standard.name = takeFirst(compliance.standard.name),
    compliance.result.count.passed = countIf(compliance.result.status.level == "PASSED"),
    compliance.result.count.failed = countIf(compliance.result.status.level == "FAILED"),
    compliance.result.count.manual = countIf(compliance.result.status.level == "MANUAL"),
    compliance.rule.title = takeFirst(compliance.rule.title),
    affected_entity.types = collectDistinct(object.type),
    affected_entity.ids = collectDistinct(object.id),
    affected_entity.names = collectDistinct(array(object.name, compliance.result.object.name)),
    related_entities.names = arrayConcat(
        arrayRemoveNulls(collectDistinct(compliance.result.object.name)),
        arrayRemoveNulls(collectDistinct(k8s.pod.name)),
        arrayRemoveNulls(collectDistinct(k8s.workload.name)),
        arrayRemoveNulls(collectDistinct(k8s.node.name)),
        arrayRemoveNulls(collectDistinct(k8s.namespace.name)),
        arrayRemoveNulls(collectDistinct(k8s.cluster.name)),
        arrayRemoveNulls(collectDistinct(host.name)),
        arrayRemoveNulls(collectDistinct(azure.resource.name)),
        arrayRemoveNulls(collectDistinct(aws.resource.name)),
        arrayRemoveNulls(collectDistinct(gcp.resource.name))),
    related_entities.ids = arrayConcat(
        arrayRemoveNulls(collectDistinct(dt.smartscape_source.id)),
        arrayRemoveNulls(collectDistinct(dt.smartscape.process)),
        arrayRemoveNulls(collectDistinct(dt.smartscape.host)),
        arrayRemoveNulls(collectDistinct(dt.smartscape.k8s_cluster)),
        arrayRemoveNulls(collectDistinct(dt.smartscape.k8s_node)),
        arrayRemoveNulls(collectDistinct(dt.smartscape.k8s_namespace)),
        arrayRemoveNulls(collectDistinct(dt.smartscape.k8s_pod)),
        arrayRemoveNulls(collectDistinct(k8s.pod.uid)),
        arrayRemoveNulls(collectDistinct(k8s.cluster.uid)),
        arrayRemoveNulls(collectDistinct(azure.resource.id)),
        arrayRemoveNulls(collectDistinct(aws.resource.id)),
        arrayRemoveNulls(collectDistinct(gcp.resource.id)))
  }, by: {compliance.rule.id}
| fieldsAdd compliance.result.status.level =
      if(compliance.result.count.failed > 0, "FAILED",
      else: if(compliance.result.count.manual > 0, "MANUAL",
      else: if(compliance.result.count.passed > 0, "PASSED", else: "NOT_RELEVANT")))
```

The inner join dedupes to the **latest completed scan** per object (without it, repeated scan attempts
double-count findings). Step 2 rolls per-`(rule, object)` rows into per-rule verdicts: any failure → `FAILED`,
else any manual → `MANUAL`, else `PASSED`.

---

## DT SPM: Variant Extensions

Apply Step 1 + Step 2, then append:

| Use case | Append after Step 2 |
|---|---|
| Latest execution — flat list per rule | _(no addition)_ |
| Failed rules only | `\| filter compliance.result.status.level=="FAILED"` |
| Grouped by standard with pass rate | See below |
| Grouped by affected systems | See below (requires Step 2 modification) |
| Rules failing on the most objects | See below |

### Pre-Aggregation Filters (insert between Step 1 and Step 2)

These reduce data volume before the per-rule aggregation. All accept `"ALL"` as a
no-op.

Placeholders (dashboard variables — substitute a literal string, or `ALL` to disable the clause):

- `${systems}` — cluster / account / project name, e.g. `appsec-ai-test` (`k8s.cluster.name`); get it from the cluster list or `fetch security.events | filter event.type=="COMPLIANCE_FINDING" | summarize count(), by:{k8s.cluster.name}`.
- `${standards}` — standard short or full name, e.g. `CIS`, `DORA`.
- `${ruleTitles}` / `${ruleIds}` — exact rule title or id (e.g. `CIS-83103`) from the per-rule summary.

```dql-snippet
// Scope to a specific cluster / system (KSPM + external CSPM/cloud)
| filter ("${systems}" == "ALL" or in("${systems}", arrayRemoveNulls(array(
    k8s.cluster.name,
    aws.account.id,
    aws.account.name,
    azure.subscription.name,
    gcp.project.id
  ))))
// Scope to a compliance standard (short_name OR full name, e.g. "CIS", "DORA", "NIST", "STIG")
| filter ("${standards}" == "ALL" or in("${standards}", arrayRemoveNulls(array(
    compliance.standard.short_name,
    compliance.standard.name
  ))))
// Scope to specific rule titles or rule IDs (exact match)
| filter ("${ruleTitles}" == "ALL" or compliance.rule.title == "${ruleTitles}")
| filter ("${ruleIds}"    == "ALL" or compliance.rule.id    == "${ruleIds}")
```

### Post-Aggregation Filters (insert after Step 2)

Placeholders (dashboard variables — substitute a literal string, or `ALL` to disable the clause):

- `${riskLevels}` — comma-separated severities, e.g. `CRITICAL,HIGH`.
- `${resultStatuses}` — one rule status: `FAILED`, `MANUAL` or `PASSED`.
- `${entityIdsOrNames}` — entity filter: `ALL`, or one or more entity names / ids. Names and `object.id` strings (comma-separated, e.g. `appsec-ai-test`) match as strings. A Smartscape id (e.g. `K8S_CLUSTER-3C526BD42B1D45FA`, from `dt.smartscape.k8s_cluster` or `smartscapeNodes`) is typed in `related_entities.ids`, so it only matches through `toSmartscapeId("${entityIdsOrNames}")` — pass **one** Smartscape id at a time.

```dql-snippet
// Filter by rule severity (CRITICAL / HIGH / MEDIUM / LOW)
| filter ("${riskLevels}"=="ALL" or in(compliance.rule.severity.level, splitString("${riskLevels}",",")))
// Filter by aggregated rule status — default is FAILED (skip PASSED / MANUAL / NOT_RELEVANT)
| filter ("${resultStatuses}" == "ALL" or compliance.result.status.level == "${resultStatuses}")
// Filter by entity (post-aggregation arrays — see common-patterns.md § 5)
| filter ("${entityIdsOrNames}"=="ALL"
      OR in(affected_entity.ids,    splitString("${entityIdsOrNames}",","))
      OR in(affected_entity.names,  splitString("${entityIdsOrNames}",","))
      OR in(related_entities.names, splitString("${entityIdsOrNames}",","))
      OR in(related_entities.ids,   splitString("${entityIdsOrNames}",","))
      OR in(toSmartscapeId("${entityIdsOrNames}"), related_entities.ids))
```

### Grouped by Standard with Pass Rate

```dql-snippet
// Step 1 + Step 2 (as above), then:
| summarize {
    Rules=count(),
    Passed=countIf(compliance.result.status.level=="PASSED"),
    Manual=countIf(compliance.result.status.level=="MANUAL"),
    Failed=countIf(compliance.result.status.level=="FAILED")
  }, by: {compliance.standard.short_name}
| fieldsAdd passRate=round(Passed*100.0/Rules, decimals:0)
| sort passRate asc
```

### CIS-Primary Standard Summary

This is the **scorecard for broad posture / "main summary for counts" questions**
("compliance posture overview", "what's our pass rate"). For compliance/misconfiguration
questions scoped to a **specific entity**, use the [Entity Security-Tab View](#entity-security-tab-view-cis-led-failed-rules)
below instead (failed-rules lists, not a scorecard).

CIS is the **mandatory K8s baseline** (always enabled), so it leads the count summary. Reuse
the per-standard rollup above and force CIS to the top with the numeric-priority sort idiom —
a boolean `sort … == "CIS" desc` is invalid DQL:

```dql-snippet
// Grouped by Standard with Pass Rate (above), replacing its final `sort passRate asc` with:
| fieldsAdd standardPriority=if(compliance.standard.short_name=="CIS", 0, else: 1)
| sort standardPriority asc, Failed desc
```

**Present the CIS row as the headline failed-rule count.** List DORA / NIST / DISA STIG / Security Essentials rows
immediately after as *additional* failed rules — phrase them as "additional failed rules from
`<standard>`, which may overlap with CIS". **Do not sum failed counts across standards:** the
standards overlap, so the same misconfiguration on the same object can fail a CIS rule *and* a
DORA/NIST/STIG rule, and a cross-standard total double-counts the same underlying issues.

### Entity Security-Tab View (CIS-led failed rules)

Use this when the user asks about **compliance / misconfigurations on a specific entity**
(host, K8s node, workload, cluster, …). It mirrors the **Security tab shown on an individual
entity** in the Dynatrace UI: it **defaults to CIS** and **lists failed rules only**. Render
**three tables in order** — it is the entity-scoped counterpart to the broad
[CIS-Primary Standard Summary](#cis-primary-standard-summary) scorecard.

Replace `${entityIdsOrNames}` with the target entity's id(s) / name(s). `NOT_RELEVANT` is
already dropped by the Step-1 base filter, consistent with the tab's failed-only view.

> **Kubernetes scoping note (SPM/KSPM).** For `KUBERNETES_NODE` / `K8S_POD` questions, Dynatrace SPM `COMPLIANCE_FINDING` events are typically emitted per individual K8s resource (e.g. `k8sclusterrole`, `KUBERNETES_NODE`, `CLOUD_APPLICATION_INSTANCE`) and are reliably scoped via `k8s.cluster.name`.
> Resolve the cluster name if needed and filter on `k8s.cluster.name` (and any available `k8s.*` fields); do **not** assume `object.type == KUBERNETES_CLUSTER` or rely on `related_entities.*` for scoping.

> **Window per source.** Tables 1 and 2 (Dynatrace SPM/KSPM) always use `from:now()-1h`.
> Table 3 (external CSPM/VSPM tools) uses `from:now()-24h` — external findings arrive on
> a slower polling cycle and are not inner-joined to a scan event.

**Table 1 — Dynatrace CIS failed rules** (the headline; mirrors the Security tab):

Placeholders: `${entityIdsOrNames}` as described in § Post-Aggregation Filters — `ALL`, an entity name or `object.id` string, or one Smartscape id (matched via `toSmartscapeId`).

```dql-snippet
// Step 1 + Step 2 (as above), then:
| filter compliance.standard.short_name == "CIS"
     AND compliance.result.status.level == "FAILED"
// Scope to the entity (post-aggregation arrays — see common-patterns.md § 5)
| filter ("${entityIdsOrNames}"=="ALL"
      OR in(affected_entity.ids,    splitString("${entityIdsOrNames}",","))
      OR in(affected_entity.names,  splitString("${entityIdsOrNames}",","))
      OR in(related_entities.names, splitString("${entityIdsOrNames}",","))
      OR in(related_entities.ids,   splitString("${entityIdsOrNames}",","))
      OR in(toSmartscapeId("${entityIdsOrNames}"), related_entities.ids))
| fieldsAdd sevPriority = if(compliance.rule.severity.level=="CRITICAL", 0,
                          else: if(compliance.rule.severity.level=="HIGH",   1,
                          else: if(compliance.rule.severity.level=="MEDIUM", 2,
                          else: 3)))
| sort sevPriority asc
| fields Severity  = compliance.rule.severity.level,
         Rule      = compliance.rule.title,
         `Rule ID` = compliance.rule.id,
         Status    = compliance.result.status.level
```

> The view is already scoped to one entity, so omit a per-rule affected-resource column —
> it would carry the rule's full cluster-wide object list (huge and off-topic). The CIS
> **recommendation section is already embedded in `compliance.rule.title`** (e.g.
> "4.5.1 Prefer using secrets as files…"), so no `metadata_json` parse is needed for it.

**Table 2 — additional failed rules from other Dynatrace standards** (DORA / NIST / DISA STIG / Security Essentials).
Same pipeline and `${entityIdsOrNames}` as Table 1, with two changes: replace the CIS filter with
`compliance.standard.short_name != "CIS"` (keep `AND compliance.result.status.level == "FAILED"`), and add
`Standard = compliance.standard.short_name,` as the first column of the final `fields`.

> Label Table 2 as *additional* failed rules **that may overlap with CIS**; **never sum failed counts across
> Tables 1 and 2** (see [CIS-Primary Standard Summary](#cis-primary-standard-summary)).

**Table 3 — externally ingested misconfigurations / compliance findings** (CSPM/VSPM and other
external providers on the entity). Do **not** rebuild this — use the
[External Compliance Queries](#external-compliance-queries-cspm--vspm--external-posture-tools)
patterns below, scoping the
**pre-aggregation** filter to the entity via `object.id` / `dt.smartscape_source.id` /
`k8s.*` (external rows are raw per-finding; the KSPM `affected_entity.*` arrays do not apply).
Use `from:now()-24h` (see the window note above). A 0-row result means no external posture tool reported
on this entity — still state that explicitly.

### Grouped by Affected Systems with Pass Rate

In Step 2, replace `affected_entity.ids` and `affected_entity.names` with a single
record field:

```dql-snippet
// In the Step 2 summarize block, replace:
//   affected_entity.ids = collectDistinct(object.id),
//   affected_entity.names = collectDistinct(array(object.name, compliance.result.object.name)),
// With:
//   affected_entities = collectDistinct(record(object.id, compliance.result.object.name,
//                                              dt.smartscape_source.id)),
// Then after Step 2:
| expand affected_entities
| summarize {
    Rules=count(),
    Passed=countIf(compliance.result.status.level=="PASSED"),
    Manual=countIf(compliance.result.status.level=="MANUAL"),
    Failed=countIf(compliance.result.status.level=="FAILED")
  }, by: {affected_entities}
| fieldsAdd passRate=round(Passed*100.0/Rules, decimals:0)
```

### Rules Failing on the Most Objects

```dql-snippet
// Append after Step 2:
| filter compliance.result.status.level == "FAILED"
| fields compliance.rule.id, compliance.rule.title, compliance.standard.short_name,
         compliance.rule.severity.level, compliance.result.count.failed, affected_entity.names
| sort compliance.result.count.failed desc
| limit 20
```

### Overall Pass Rate

```dql-snippet
// Append after Step 2:
| summarize {
    Rules = count(),
    Passed = countIf(compliance.result.status.level == "PASSED"),
    Manual = countIf(compliance.result.status.level == "MANUAL"),
    Failed = countIf(compliance.result.status.level == "FAILED")
  }
| fieldsAdd overallPassRate = round(Passed * 100.0 / Rules, decimals: 0)
```

---

> **Do not use `scan.result.summary_json`.** `COMPLIANCE_SCAN_COMPLETED` carries this pre-computed blob, but
> agents **must not** parse it for posture answers (not even as a supplementary per-cluster query): it bypasses
> the per-rule pipeline and its pre-aggregated data can't be filtered or broken down by rule or severity. Use the
> `COMPLIANCE_FINDING` pipeline (Steps 1 + 2).

---

## DT SPM: New/Changed Compliance Findings (UC-G2 for compliance)

To find genuinely new compliance violations (not already known from a prior scan
cycle), filter on `finding.time.created` — a string timestamp set when the finding
was first ingested. Works for both DT SPM and external compliance findings:

```dql-snippet
// After Step 1 + Step 2, append:
| filter toTimestamp(finding.time.created) > now() - 24h
| sort finding.time.created desc
```

For SPM the inner-join to `COMPLIANCE_SCAN_COMPLETED` already scopes to the latest
scan; combining with `finding.time.created` narrows further to findings that first
appeared in the current scan window.

---

## DT SPM: Week-over-Week Config Drift (newly failing rules)

"What compliance rules are failing **now** that weren't failing a week ago?" Take this hour's
latest-scan **FAILED** findings and anti-join (outer join + `isNull(right…)`) against the
**FAILED** findings from ~7 days ago. The inner Step-1 scan-join is applied to **both** periods
so each is deduped to its latest scan. Group on `{object.id, compliance.rule.id}` for the diff.

> **Both periods must filter to `compliance.result.status.level == "FAILED"` BEFORE the
> anti-join — not `!= "NOT_RELEVANT"`.** The diff key is `{object.id, compliance.rule.id}`, so if
> the prior period carries PASSED rows, a rule that was **passing** a week ago and is **failing
> now** produces a matching `(object, rule)` pair on both sides and gets wrongly excluded —
> dropping exactly the pass→fail drift the question asks for. Comparing FAILED-vs-FAILED surfaces
> both brand-new `(object, rule)` pairs and genuine pass→fail transitions.

```dql
// This hour's latest scan (Step 1 with a prefix so its fields don't collide)
fetch security.events, from:now()-1h
| filter event.type == "COMPLIANCE_FINDING"
     AND product.vendor == "Dynatrace"
     AND product.name == "Security Posture Management"
     AND compliance.result.status.level == "FAILED"
| join [
    fetch security.events, from:now()-1h
    | filter event.type == "COMPLIANCE_SCAN_COMPLETED" AND product.vendor == "Dynatrace"
    | sort timestamp asc
    | summarize { scan.id = takeLast(scan.id), timestamp = takeLast(timestamp) }, by: {object.id}
  ], on: {scan.id}, prefix:"last_scan."
// Anti-join the scan from ~7 days ago (same Step-1 latest-scan logic, 30m window)
| join kind:outer, on:{object.id, compliance.rule.id}, [
    fetch security.events, from:-7d, to:-7d+30m
    | filter event.type == "COMPLIANCE_FINDING"
         AND product.vendor == "Dynatrace"
         AND product.name == "Security Posture Management"
         AND compliance.result.status.level == "FAILED"
    | join [
        fetch security.events, from:-7d, to:-7d+30m
        | filter event.type == "COMPLIANCE_SCAN_COMPLETED" AND product.vendor == "Dynatrace"
        | sort timestamp asc
        | summarize { scan.id = takeLast(scan.id) }, by: {object.id}
      ], on: {scan.id}
    | dedup {compliance.rule.id, object.id}
    | fields compliance.rule.id, object.id
  ]
| filter isNull(right.object.id)   // present now, absent a week ago
| summarize {
    compliance.rule.severity.level = takeFirst(compliance.rule.severity.level),
    compliance.rule.severity.score = takeFirst(compliance.rule.severity.score),
    compliance.standard.short_name = takeFirst(compliance.standard.short_name),
    compliance.rule.title = takeFirst(compliance.rule.title),
    compliance.result.count.failed = countIf(compliance.result.status.level == "FAILED"),
    last_scan.timestamp = max(last_scan.timestamp),
    k8s.cluster.names = collectDistinct(k8s.cluster.name),
    affected_entity.names = collectDistinct(object.name)
  }, by: {compliance.rule.id}
| filter compliance.result.count.failed > 0
     AND in(compliance.rule.severity.level, array("CRITICAL","HIGH"))
| fieldsAdd severityRank = coalesce(compliance.rule.severity.score, 0)
| sort severityRank desc, compliance.result.count.failed desc, compliance.rule.id asc
| limit 50
```

> The previous-period sub-window uses `to:-7d+30m` (a 30-min slice a week back) so it captures one
> completed scan without pulling 7 days of rows. Adjust the offset for month-over-month, etc.
>
> The `AND in(compliance.rule.severity.level, array("CRITICAL","HIGH"))` clause is part of the
> canonical template because the question asks for "critical and high" drift. It may legitimately
> return zero rows when the period's newly-failing rules are all lower severity. For an
> all-severity drift question ("everything newly failing"), delete that one line and keep
> `| filter compliance.result.count.failed > 0`; to widen instead, add `"MEDIUM"` / `"LOW"` to the array.
>
> **One row per rule, not per scan.** The final `summarize` groups by `compliance.rule.id` only.
> `last_scan.timestamp` differs per scanned cluster, so grouping by it split one rule into one row
> per cluster (DORA-67945 appeared twice) and made `limit 50` trim on those duplicates; it is now
> a `max()` value, and `k8s.cluster.names` lists the clusters where the rule newly fails. For a
> per-cluster question, group `by: {compliance.rule.id, k8s.cluster.name}` instead. The sort
> coalesces `compliance.rule.severity.score` (0-10, populated on every live KSPM row) into
> `severityRank` and ends on `compliance.rule.id`, so ties order deterministically.
>
> **Baseline coverage check (run before the drift query, or when the result looks inflated).**
> Compare the scanned clusters in the current slice with the baseline slice:

```dql
fetch security.events, from:now()-1h
| filter event.type == "COMPLIANCE_SCAN_COMPLETED" AND product.vendor == "Dynatrace"
| summarize { scanned.objects = countDistinctExact(object.id), clusters = collectDistinct(k8s.cluster.name) }
| fieldsAdd period = "current (now-1h)"
| append [
    fetch security.events, from:-7d, to:-7d+30m
    | filter event.type == "COMPLIANCE_SCAN_COMPLETED" AND product.vendor == "Dynatrace"
    | summarize { scanned.objects = countDistinctExact(object.id), clusters = collectDistinct(k8s.cluster.name) }
    | fieldsAdd period = "baseline (-7d, 30m)"
  ]
| fields period, scanned.objects, clusters
```

> **Rule:** if the baseline row lists fewer clusters than the current row, widen the baseline
> (`to:-7d+2h`) in **both** prior-period sub-queries of the drift template and say so in the answer;
> on demo-live the 30m baseline covers 3 of 4 clusters (`demo-kspm` missing) and `to:-7d+2h` covers all 4.
> Keep the default `30m` window otherwise.

---

## DT SPM: Rule Drilldown with Evidence Parsing

For a specific rule, parses JSON evidence attached to each finding and expands
individual findings. **Does not** use the per-rule summarize block (Step 2) —
applies directly after Step 1.

```dql-snippet
// Step 1 (as above), then:
| filter compliance.rule.id == "CIS-75904"
| parse compliance.result.object.evidence_json, "JSON_ARRAY:findings"
| fieldsAdd allFindings = if(iAny(not isNull(findings[])), findings, else: array(record(type = "", description = "", value = "")))
| expand allFindings
| fieldsAdd Result = compliance.result.status.level,
           `Resource name` = object.name,
           Type = object.type,
           `Resource type` = compliance.result.object.type,
           `Related configuration properties` = allFindings,
           System = k8s.cluster.name,
           `Analyzed at` = timestamp
| fieldsAdd systemPriority = if(System == "unguard-dev", 0, else: 1),
            resultPriority = if(Result == "FAILED", 0, else: if(Result == "MANUAL", 1, else: 2))
| sort systemPriority asc, resultPriority asc
| fieldsKeep `Analyzed at`, System, "dt.smartscape*",
            Result, `Resource name`, Type, `Resource type`,
            `Related configuration properties`
```

The evidence array carries `{type, description, value}` records where `type` is
`AUTOMATIC` (analyzer evaluated the property) or `MANUAL` (requires human
input — `value` is typically `"Unknown"`). Filter on `allFindings.type == "MANUAL"`
to surface checks waiting on operator input.

---

## DT SPM: Per-Cluster + Per-Namespace Breakdown

To count **rules** (not object checks) per cluster, first roll up to the per-rule-per-cluster
level (Step 2 variant keyed by `{compliance.rule.id, k8s.cluster.name}`), then count rule
verdicts per cluster (Step 3). Grouping directly by cluster after Step 1 without this
intermediate step counts *object-check results*, not rules — the pass rate will be
inflated and inconsistent with the per-standard summary.

```dql-snippet
// Step 1 (as above), then:
// Step 2 variant — per-rule-per-cluster verdict
| summarize {
    compliance.rule.severity.level = takeFirst(compliance.rule.severity.level),
    passed = countIf(compliance.result.status.level == "PASSED"),
    failed = countIf(compliance.result.status.level == "FAILED"),
    manual = countIf(compliance.result.status.level == "MANUAL"),
    SmartscapeCluster = takeFirst(dt.smartscape.k8s_cluster)
  }, by: {compliance.rule.id, Cluster = k8s.cluster.name}
| fieldsAdd ruleStatus =
      if(failed > 0, "FAILED",
      else: if(manual > 0, "MANUAL",
      else: if(passed > 0, "PASSED", else: "NOT_RELEVANT")))
// Step 3 — per-cluster rule counts
| summarize {
    Rules = count(),
    Passed = countIf(ruleStatus == "PASSED"),
    Manual = countIf(ruleStatus == "MANUAL"),
    Failed = countIf(ruleStatus == "FAILED"),
    CriticalFailed = countIf(ruleStatus == "FAILED" AND compliance.rule.severity.level == "CRITICAL"),
    HighFailed = countIf(ruleStatus == "FAILED" AND compliance.rule.severity.level == "HIGH")
  }, by: {Cluster, SmartscapeCluster}
| fieldsAdd passRate = round(Passed * 100.0 / Rules, decimals: 0)
| sort passRate asc
```

For per-namespace, extend the Step 2 `by` key to
`{compliance.rule.id, Cluster = k8s.cluster.name, Namespace = k8s.namespace.name}`
and the Step 3 `by` key to `{Cluster, Namespace}`.

### Single Cluster / System Summary

When the user asks about a *specific* named cluster, scope with a pre-aggregation filter and
collapse all per-rule rows into a **single summary row**. This avoids a `by: {Cluster}` grouping
and lets the final `summarize` include per-severity failure counts in the same query — one query,
one result row:

Placeholders: `<cluster-name>` — the Kubernetes cluster name as a plain string (`k8s.cluster.name`), e.g. `appsec-ai-test`; list the names with `fetch security.events, from:now()-1h | filter event.type=="COMPLIANCE_FINDING" AND product.vendor=="Dynatrace" | summarize count(), by:{k8s.cluster.name}`. It is a name, not a typed Smartscape id, so no `toSmartscapeId(...)`.

```dql-snippet
// Step 1 (as above), then:
// Pre-aggregation filter — scope to the named cluster
| filter k8s.cluster.name == "<cluster-name>"
// Step 2 (as above, no cluster key needed — already filtered), then:
// Single summarize — rule counts + per-severity failure breakdown in one row (no by: clause)
| summarize {
    Rules = count(),
    Passed = countIf(compliance.result.status.level == "PASSED"),
    Manual = countIf(compliance.result.status.level == "MANUAL"),
    Failed = countIf(compliance.result.status.level == "FAILED"),
    CriticalFailed = countIf(compliance.result.status.level == "FAILED" AND compliance.rule.severity.level == "CRITICAL"),
    HighFailed    = countIf(compliance.result.status.level == "FAILED" AND compliance.rule.severity.level == "HIGH"),
    MediumFailed  = countIf(compliance.result.status.level == "FAILED" AND compliance.rule.severity.level == "MEDIUM"),
    LowFailed     = countIf(compliance.result.status.level == "FAILED" AND compliance.rule.severity.level == "LOW")
  }
| fieldsAdd passRate = round(Passed * 100.0 / Rules, decimals: 0)
```

Step 2 reuses the shared block, so the verdict logic matches every other pattern; its entity collectors add
some cost, which is acceptable once scoped to a single cluster.

If a standard filter is also needed (e.g. "DORA posture on eks-live"), add it as a second
pre-aggregation filter right after the cluster filter:
`| filter contains(compliance.standard.short_name, "dora", caseSensitive:false)`

---

## DT SPM: Severity-Weighted Risk Score

A simple "compliance risk" rollup that weights failures by severity. Use for
prioritization tiles ("which clusters carry the most compliance risk?"):

```dql-snippet
// Step 1 + Step 2 with a `compliance.standard.short_name`-aware grouping if needed, then:
| filter compliance.result.status.level == "FAILED"
| summarize {
    riskScore = sum(if(compliance.rule.severity.level == "CRITICAL", 10,
                    else: if(compliance.rule.severity.level == "HIGH",     7,
                    else: if(compliance.rule.severity.level == "MEDIUM",   4,
                    else: 1)))
                * compliance.result.count.failed),
    failedRules = count(),
    affectedObjects = sum(compliance.result.count.failed)
  }, by: {compliance.standard.short_name}
| sort riskScore desc
```

The severity scores `CRITICAL=10 / HIGH=7 / MEDIUM=4 / LOW=1` match
`compliance.rule.severity.score` (CCSS-derived). Substitute the field if
present on raw events.

---

## DT SPM: MANUAL Deep Dive

`MANUAL` rules require human input — surface them as a separate triage list,
not as failures. Surface the question (description) and the `Unknown` value:

```dql-snippet
// Step 1 (as above), then:
| filter compliance.result.status.level == "MANUAL"
| parse compliance.result.object.evidence_json, "JSON_ARRAY:findings"
| expand finding = findings
| filter finding.type == "MANUAL"
| fieldsAdd System = k8s.cluster.name,
           Resource = object.name,
           ResourceType = compliance.result.object.type,
           Rule = compliance.rule.title,
           RuleID = compliance.rule.id,
           Severity = compliance.rule.severity.level,
           Question = finding.description,
           CurrentValue = finding.value
| fieldsAdd severityPriority = if(Severity == "CRITICAL", 0, else: if(Severity == "HIGH", 1, else: 2))
| sort severityPriority asc
| fieldsKeep timestamp, "dt.smartscape*",
            System, Resource, ResourceType, Rule, RuleID, Severity, Question, CurrentValue
```

Group by `compliance.rule.id` and `Question` to count how many objects share
the same unanswered question — useful for batch resolution via configuration
(e.g. enabling Node Configuration Collector resolves a class of MANUAL checks
at once).

---

## DT SPM: Compliance-Finding Age

Compliance findings don't have a per-finding "first seen" timestamp baked in,
but `finding.time.created` is set when the finding was ingested in the current
scan cycle. To approximate "how long has this rule been failing on this
object", look at the **earliest** `finding.time.created` for the
`(rule, object)` pair across the historical event stream — widening the window
deliberately past 1h:

```dql
fetch security.events, from:now()-30d
| filter event.type == "COMPLIANCE_FINDING"
     AND product.vendor == "Dynatrace"
     AND product.name == "Security Posture Management"
     AND compliance.result.status.level == "FAILED"
| summarize {
    firstFailedAt = takeMin(toTimestamp(finding.time.created)),
    lastSeen = takeMax(toTimestamp(finding.time.created)),
    scans = countDistinctExact(scan.id)
  }, by: {compliance.rule.id, compliance.rule.title,
          object.id, object.name, k8s.cluster.name}
| fieldsAdd ageDays = round((toLong(now()) - toLong(firstFailedAt)) / 1000000000.0 / 86400, decimals: 1)
| sort ageDays desc
| limit 50
```

**Worked single-rule/object form:** substitute the rule and object when the user
asks "this rule on this object." `finding.time.created` is a string timestamp, so
wrap it with `toTimestamp(...)` before `takeMin`, `takeMax`, comparisons, or age
math.

Placeholders:

- `<RULE_ID>` — SPM rule id (`compliance.rule.id`), e.g. `CIS-83103` or `DORA-67955`. Take it from the per-rule summary (Step 2) or the rule drilldown above.
- `<OBJECT_ID>` — scanned-object id (`object.id`), a plain string (a GUID such as `21afbe74-12fc-4fdd-a5c5-d01607e378d9` or a classic-style id), not a typed Smartscape id, so no `toSmartscapeId(...)` wrapper. Take it from the `object.id` of the same rule's FAILED rows (Step 1).

```dql-template
fetch security.events, from:now()-30d
| filter event.type == "COMPLIANCE_FINDING"
     AND product.vendor == "Dynatrace"
     AND product.name == "Security Posture Management"
     AND compliance.result.status.level == "FAILED"
| filter compliance.rule.id == "<RULE_ID>" AND object.id == "<OBJECT_ID>"
| summarize {
    firstFailedAt = takeMin(toTimestamp(finding.time.created)),
    lastSeen = takeMax(toTimestamp(finding.time.created)),
    scans = countDistinctExact(scan.id)
  }, by: {compliance.rule.id, compliance.rule.title, object.id, object.name}
| fieldsAdd ageDays = round((toLong(now()) - toLong(firstFailedAt)) / 1000000000.0 / 86400, decimals: 1)
```

> **Bypassing the 1h window is intentional here.** This question is genuinely
> about history, not snapshot — we want every scan that ever reported FAILED
> for the pair. The inner-join-to-latest-scan trick is dropped, so each scan
> contributes a row, and the dedup is per `(rule, object)`.

---

## External Compliance Queries (CSPM / VSPM / external posture tools)

```dql
fetch security.events, from:now()-24h
| filter event.type == "COMPLIANCE_FINDING"
| filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
| fieldsAdd statusNormalized = coalesce(compliance.result.status.level, compliance.status)
| filterOut statusNormalized == "NOT_RELEVANT"
| summarize findings=count(), by:{event.provider, product.name, dt.security.risk.level, statusNormalized}
| sort findings desc
```

When users ask for "violations", "failed controls", or "misconfigurations",
filter to `statusNormalized == "FAILED"` only if that field is present. Some
external providers send findings without a pass/fail status; for those, treat
each row as a provider-reported finding and group by `finding.title` /
`finding.type`.

### External compliance taxonomy fields

External `COMPLIANCE_FINDING` rows carry their own taxonomy namespace (distinct from KSPM's
`compliance.rule.*` / `compliance.standard.*`):

| Field | Shape | Example | Notes |
|---|---|---|---|
| `compliance.standards` | **array of string** | `["standards/cis-aws-foundations-benchmark/v/5.0.0"]`, `["Azure CSPM"]` | The standards/benchmarks a finding maps to. `expand` it for per-standard rollups. |
| `compliance.control` | string | `"S3.8"` | Provider control identifier. |
| `compliance.policy` | string | _(provider policy name)_ | Present on some providers, absent on others. |
| `compliance.status` | string | `"PASSED"` / `"FAILED"` | Top-level status; external rows usually leave `compliance.result.status.level` null. |
| `compliance.requirements` | array **or** `""` | `["CIS AWS Foundations Benchmark v5.0.0/2.1.4.2"]` | Type-inconsistent across providers — surface only, don't build filters/grouping on it. |

**External compliance by standard/framework** (expand the `compliance.standards` array):

```dql
fetch security.events, from:now()-24h
| filter event.type == "COMPLIANCE_FINDING"
| filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
| fieldsAdd statusNormalized = coalesce(compliance.result.status.level, compliance.status)
| filterOut statusNormalized == "NOT_RELEVANT"
| fieldsAdd standardList = coalesce(compliance.standards, array(compliance.standard.short_name)),
            riskLevel = coalesce(dt.security.risk.level, compliance.rule.severity.level)
| expand compliance.standard = standardList
| filter isNotNull(compliance.standard)
| summarize {
    Findings=count(),
    Failed=countIf(statusNormalized == "FAILED"),
    Critical=countIf(riskLevel == "CRITICAL" AND statusNormalized == "FAILED"),
    High=countIf(riskLevel == "HIGH" AND statusNormalized == "FAILED"),
    SampleTitles=collectDistinct(coalesce(finding.title, compliance.rule.title), maxLength: 10),
    AffectedObjects=countDistinctExact(object.id)
  }, by:{event.provider, product.name, compliance.standard}
| sort Critical desc, High desc, Failed desc, Findings desc
```

> **The standard lives in different fields per provider.** Defender-style CSPM fills the
> `compliance.standards` array; Runecast fills only `compliance.standard.short_name` (plus
> `compliance.rule.id` / `.title` / `.severity.level`) and leaves `compliance.standards`,
> `dt.security.risk.level`, `compliance.control` and `compliance.policy` null. The `coalesce` above
> covers both; filtering on `compliance.standards` alone silently drops Runecast. Providers with
> neither field (e.g. AWS Security Hub "Coverage" findings) would be dropped by `isNotNull(compliance.standard)`;
> use the fallback variant below.

**Discovery — which standard field does each external provider populate?** Run this first when the by-standard
result lacks a provider you expect, or when the provider set is unknown. One row per provider shows how many
`COMPLIANCE_FINDING` rows carry `compliance.standards`, `compliance.standard.short_name`, or neither:

```dql
fetch security.events, from:now()-24h
| filter event.type == "COMPLIANCE_FINDING"
| filterOut event.provider == "Dynatrace" or product.vendor == "Dynatrace"
| summarize {
    Findings=count(),
    withStandards=countIf(isNotNull(compliance.standards)),
    withShortName=countIf(isNotNull(compliance.standard.short_name)),
    withNeither=countIf(isNull(compliance.standards) and isNull(compliance.standard.short_name))
  }, by:{event.provider, product.vendor, product.name}
| sort Findings desc
```

> **Reading the result.** A provider with `withStandards` or `withShortName` > 0 is covered by the by-standard
> query (its `coalesce` handles both). A provider whose rows are all `withNeither` is dropped by
> `isNotNull(compliance.standard)`: report it with the fallback variant below (group by `finding.type` /
> `finding.title`, no standard column) and state in the answer which providers were grouped that way.
> `event.provider` can be null (Runecast), so identify providers by `product.name` as well.

**Fallback variant — providers with neither `compliance.standards` nor `compliance.standard.short_name`.**
Run it in addition to the by-standard query only when a provider is missing from that result. It groups by
`finding.type` and lists `coalesce(finding.title, compliance.rule.title)` as the sample titles, with the same
FAILED filter and `riskLevel` coalesce (no `compliance.standard` column exists for these rows):

```dql
fetch security.events, from:now()-24h
| filter event.type == "COMPLIANCE_FINDING"
| filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
| filter isNull(compliance.standards) and isNull(compliance.standard.short_name)
| fieldsAdd statusNormalized = coalesce(compliance.result.status.level, compliance.status),
            riskLevel = coalesce(dt.security.risk.level, compliance.rule.severity.level),
            findingTitle = coalesce(finding.title, compliance.rule.title)
| filter statusNormalized == "FAILED"
| summarize {
    Failed=count(),
    Critical=countIf(riskLevel == "CRITICAL"),
    High=countIf(riskLevel == "HIGH"),
    SampleTitles=collectDistinct(findingTitle, maxLength: 5),
    AffectedObjects=countDistinctExact(object.id)
  }, by:{event.provider, product.name, finding.type}
| sort Critical desc, High desc, Failed desc
```

**Top failing controls** — variant: after `filter isNotNull(compliance.standard)` in the by-standard query, keep only
FAILED rows and group by one coalesced control key. `compliance.control` (Defender-style), `compliance.rule.id`
(Runecast) and `compliance.policy` are populated per provider, and Runecast has no `dt.security.risk.score`, so the
sort falls back to `AffectedObjects` (`coalesce(maxScore, 0)` keeps null-score rows from sorting first). The final `limit 10`
ranks scored providers ahead of Runecast, so for an all-provider answer rank per provider
(`filter product.name == "<product>"`) instead of relying on one global limit:

```dql-snippet
// …after `filter isNotNull(compliance.standard)` in the by-standard query, replace summarize + sort with:
| filter statusNormalized == "FAILED"
| fieldsAdd control = coalesce(compliance.control, compliance.rule.id, compliance.policy)
| summarize {
    Findings=count(),
    SampleTitles=collectDistinct(coalesce(finding.title, compliance.rule.title), maxLength: 5),
    maxScore=takeMax(dt.security.risk.score),
    AffectedObjects=countDistinctExact(object.id)
  }, by:{event.provider, product.name, compliance.standard, riskLevel, control}
| sort coalesce(maxScore, 0) desc, AffectedObjects desc
| limit 10
```

**Critical/high external compliance findings newly reported in the last 7d (not in the prior 7d):**

```dql
// This-period findings
fetch security.events, from:-7d, to:now()
| filter event.type == "COMPLIANCE_FINDING"
| filterOut event.provider == "Dynatrace" or product.vendor == "Dynatrace"
| filter finding.time.created > now()-7d
| fieldsAdd standardList = coalesce(compliance.standards, array(compliance.standard.short_name)),
            findingKey = coalesce(compliance.rule.id, finding.id),
            riskLevel = coalesce(dt.security.risk.level, compliance.rule.severity.level)
| filter in(riskLevel, array("CRITICAL", "HIGH"))
// Dedup per finding BEFORE expanding standards (newest row wins) so every mapped standard survives
| dedup {object.id, findingKey}, sort:{timestamp desc}
// Anti-join the prior period at finding level: keep only findings absent a week ago
| join kind:outer, on:{object.id, findingKey}, [
    fetch security.events, from:-14d, to:-7d
    | filter event.type == "COMPLIANCE_FINDING"
    | filterOut event.provider == "Dynatrace" or product.vendor == "Dynatrace"
    | filter finding.time.created > now()-14d and finding.time.created < now()-7d
    | fieldsAdd findingKey = coalesce(compliance.rule.id, finding.id)
    | dedup {object.id, findingKey}
    | fields object.id, findingKey
  ]
| filter isNull(right.findingKey)
| expand compliance.standard = standardList
| filter isNotNull(compliance.standard)
| fieldsAdd control = coalesce(compliance.control, compliance.rule.id, compliance.policy)
| summarize {
    Findings=count(),
    SampleTitles=collectDistinct(coalesce(finding.title, compliance.rule.title), maxLength: 5),
    maxScore=takeMax(dt.security.risk.score),
    AffectedObjects=countDistinctExact(object.id)
  }, by:{event.provider, product.name, compliance.standard, riskLevel, control}
| sort coalesce(maxScore, 0) desc, AffectedObjects desc, compliance.standard asc, control asc
```

> **Severity filter is applied to the current period only, before the dedup and join.** It is canonical for the
> "critical and high" question; for every severity, delete the `| filter in(riskLevel, array("CRITICAL", "HIGH"))` line. The prior-period side
> stays unfiltered on severity so a finding that merely escalated from MEDIUM to HIGH is not reported as new.
> `riskLevel` coalesces `compliance.rule.severity.level` so Runecast rows (null `dt.security.risk.level`) are
> kept. Runecast has no `dt.security.risk.score`, so `coalesce(maxScore, 0)` sorts every Runecast row after all
> scored rows (on demo-live: 10 Defender rows ahead of 358 Runecast rows). Do **not** append a global `limit` to
> this result; cap per provider instead (rerun with `filter product.name == "<product>"`; Runecast has a null `event.provider`), otherwise the null-score provider is cut off.

> **Dedup and anti-join are per finding; standards expand last.** `dedup {object.id, findingKey}` after
> `expand compliance.standard` kept one arbitrary standard row per finding, so a finding mapped to several
> standards was counted under only one of them. Deduping first (newest row wins via `sort:{timestamp desc}`),
> anti-joining on `{object.id, findingKey}`, then expanding gives each new finding one row per mapped standard
> and makes per-standard counts deterministic. A finding is "new" or not as a whole; a standard added to an
> existing finding does not make it new. (demo-live has only single-standard rows, so totals match the old shape
> there: Runecast CIS 349, HIPAA 247, PCI DSS 241, GDPR 198, Cyber Essentials 106; Defender Azure CSPM 36.)

> **Anti-join key is `compliance.rule.id`, falling back to `finding.id`.** Runecast mints a new
> `finding.id` on every scan, so a `finding.id` join would call every finding "new"; Defender-style
> CSPM has no `compliance.rule.id` but a stable `finding.id`. The coalesced `findingKey` handles both.

### Scoping external compliance to a provider

External compliance findings come from CSPM/VSPM and other ingested posture tools, each with
its own provider string and standard coverage. To scope to one, use the shared provider pattern
in [all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type);
discover the active providers first (`summarize by {event.provider, product.vendor, product.name}`).
External standard names populate `compliance.standards` (array) or, for Runecast, `compliance.standard.short_name`; coalesce both (see § External compliance by standard).

### Field caveat — KSPM `compliance.rule.*` vs. external taxonomy

Most external rows (Defender-style CSPM) do **not** populate the KSPM rule/standard fields (`compliance.rule.id`,
`compliance.rule.title`, `compliance.rule.severity.level`, `compliance.standard.short_name` / `.name`) — they are
null; Runecast is the exception and fills them. Group, filter and sort by the external taxonomy documented above:
`compliance.standards` (expand the array; coalesce with `compliance.standard.short_name`), `compliance.policy`,
`compliance.control`, with `finding.title` / `finding.type` for display. For status, coalesce both fields:
`coalesce(compliance.result.status.level, compliance.status)`. The KSPM patterns (Steps 1 + 2) are
**incompatible** with external findings: they require `compliance.rule.*` and the inner join to
`COMPLIANCE_SCAN_COMPLETED`, which only DT KSPM emits.

For a cross-provider compliance view (DT KSPM + external aggregated by
`dt.security.risk.level`), see [all-security-events.md](all-security-events.md).

---

## Best Practices

Scope (KSPM is K8s-only, `product.name` pinning), status semantics (`NOT_RELEVANT`, `MANUAL`, precedence),
the 1h window, and the no-mute rule are stated once at the top of this file and in § Routing. Rules unique
to this section:

1. **Severity is `CRITICAL / HIGH / MEDIUM / LOW`** — exactly four. KSPM does not emit `NONE` or
   `NOT_AVAILABLE`. CCSS-derived since 2026-03-10.
2. **Never parse `compliance.rule.metadata_json`** — it is forbidden in this skill.
   Use `compliance.rule.id` (already standard-prefixed and human-recognizable, e.g.
   `CIS-2762`, `STIG-82824`, `DORA-67952`, `NIST-82827`) and `compliance.rule.title` as the
   rule identifiers. The finer benchmark-section citation (CIS `1.2.3`) is intentionally
   not surfaced.
3. **Object identity has two fields on KSPM rows** — `object.type` (normalized
   Dynatrace entity type, uppercase: `KUBERNETES_CLUSTER`, `KUBERNETES_NODE`,
   …) and `compliance.result.object.type` (analyzer's lowercase code:
   `k8scluster`, `k8snode`, …). They're different fields, not synonyms. **On
   external compliance findings**, `object.type` instead carries the
   vendor-reported value as-is (e.g. `AwsEc2Instance`); don't normalize.
4. **`COMPLIANCE_SCAN_COMPLETED` is per-cluster, per-scan-run** — not per-object.
   The inner-join on `scan.id` deduplicates findings to the latest scan; the
   join target itself doesn't carry per-rule info. Per-rule rollups go through
   `COMPLIANCE_FINDING` + Step 2.
5. **No SPM scan-completed events for a specific cluster means no SPM coverage.**
   If a named cluster (for example, `gke-live`) has no `COMPLIANCE_SCAN_COMPLETED`
   events and no matching `COMPLIANCE_FINDING` rows for Security Posture
   Management in the operational window, answer that SPM/KSPM is not covering
   that cluster. The likely cause is that SPM is not enabled, deployed, or
   configured for the cluster — not simply that the cluster has no violations.
6. **Posture questions: one query, overall first.** Follow the Base Pattern callout (standard summary
   first; per-cluster 3-step variant only on request, as a second query). Per-cluster pass rate must go
   through the per-rule-per-cluster Step 2 — see § "Per-Cluster + Per-Namespace Breakdown".
