# Compliance Queries — `security.events`

Dynatrace Security Posture Management (SPM / XSPM) compliance findings and
external provider compliance findings.

> **Cross-references:** field reference → [data-model.md § Compliance Fields](data-model.md#compliance-fields-spm) ·
> time-window rules → [common-patterns.md](common-patterns.md).

> **SPM has three flavors:** KSPM (Kubernetes — DT-native, the
> security-analyzer-service), CSPM (cloud posture) and VSPM (VMware posture),
> the latter two delivered via an external/partner integration. The DQL patterns
> in this file target **KSPM**.
> CSPM/VSPM ride on the same `security.events` table but use the cross-provider
> `finding.*` namespace, not `compliance.rule.*` — see
> [all-security-events.md](all-security-events.md) and § External Compliance
> below for those.

> **KSPM scope is Kubernetes-only.** The DT-native SPM analyzer assesses K8s
> clusters, nodes, pods, deployments, statefulsets, daemonsets, jobs, cronjobs,
> replicasets, replication controllers. There are no DT-native compliance
> findings against AWS / Azure / GCP / host / process entities. If the user
> asks "what's our AWS compliance posture?" they need CSPM or another external
> integration.

> **KSPM standards — `compliance.standard.short_name` values: `CIS`, `DORA`,
> `NIST`, `DISA STIG`.** Note STIG specifically: the short_name is the full
> `"DISA STIG"` label, not bare `"STIG"`. A filter like
> `compliance.standard.short_name == "STIG"` returns nothing. For all standard
> scoping, prefer **`contains(lower(compliance.standard.short_name), "<keyword>")`**
> over exact equality — it tolerates the DISA prefix, version suffixes, and
> case mismatches uniformly across all four standards. PCI DSS, ISO 27001,
> HIPAA, GDPR, BSI C5, TISAX, Cyber Essentials, Essential Eight, etc. arrive
> only via CSPM/VSPM or other external integrations — they don't
> populate the KSPM rule namespace. CIS is mandatory for K8s; DORA / NIST /
> DISA STIG are opt-in (configurable in Settings → Application Security →
> Security Posture Management).

> **Snapshot vs. history.** DT SPM queries use a **1-hour fixed window**
> (`from:now()-1h`). This is aligned with the scan-completion cycle — it ensures
> the latest `COMPLIANCE_SCAN_COMPLETED` event is captured per object so the
> inner join succeeds. Widening doesn't extend history; if no scan completed in
> the last 1h for an object, that object's findings will NOT appear (inner-join
> behavior — by design). Scans are triggered when an ActiveGate ships a fresh
> configuration dataset (typically hourly per K8s cluster).

> **NOT_RELEVANT.** Always excluded by the base filter. These are rules that
> don't apply to the assessed object (e.g. AWS rule on a GCP resource, or a
> rule that requires a K8s version mismatch). Never count them in pass/fail
> totals. The SPM app's "Recommended" view excludes them by default; "Complete"
> view includes them.

> **MANUAL is currently non-actionable.** A `MANUAL` rule is one the analyzer
> can't auto-evaluate (e.g. it depends on physical-security checks, or
> external-control configuration the analyzer can't see). The Dynatrace docs
> note "Manual results aren't currently actionable" — there's no remediation
> workflow. Treat MANUAL as a triage hint, not a remediable defect, and don't
> include it in pass-rate numerators.

> **No mute / exemption / waiver mechanism.** Unlike vulnerabilities, compliance
> findings have no `mute.*` namespace in `security.events`. "Accepted risk" is
> not modeled in DQL. If asked "show me accepted compliance findings," explain
> the field doesn't exist (the SPM app may surface acceptance UI-side, but it's
> not exposed to queries).

> **Default tool filter is FAILED-only.** To compute pass rate ("how compliant
> are we?"), set `resultStatuses=ALL` so PASSED is in the denominator.

> **Compliance status field and values — use `compliance.result.status.level`, never `event.status`.**
> The canonical enum is `PASSED`, `FAILED`, `MANUAL`, `NOT_RELEVANT` — not `PASS`/`FAIL`. Always count
> failures with an explicit equality check: `countIf(compliance.result.status.level == "FAILED")`.
> Using a negation (`!= "PASSED"`) wrongly folds `MANUAL` and `NOT_RELEVANT` into the failed count.
> `event.status` is a generic event-lifecycle field (`Active`/`Closed`) unrelated to compliance verdicts;
> it is null or wrong on `COMPLIANCE_FINDING` rows. Additional field rules:
> — Standard field: `compliance.standard.short_name` (not `compliance.rule.standard`, which does not exist in the Semantic Dictionary).
> — Severity field: `compliance.rule.severity.level` (not bare `compliance.rule.severity`, which resolves to nothing).
> — Latest-scan join uses `on: {scan.id}` shorthand — not `on: {left.scan.id == right.scan.id}` (`left.`/`right.` prefixes are body syntax only, not valid inside `on:`).
> — Pass rate must be computed on **per-rule** verdicts (after Step 2 rollup), not directly on raw per-`(rule, object)` rows.

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
| External violations "by standard" / "by framework" | [§ External Compliance](#external-compliance-queries-cspm--vspm--external-posture-tools) — `compliance.standards` is an **array**: always `expand compliance.standard = compliance.standards` before `summarize`, otherwise the per-standard breakdown collapses |
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
        arrayRemoveNulls(collectDistinct(dt.smartscape.k8s_pod)),
        arrayRemoveNulls(collectDistinct(dt.entity.host)),
        arrayRemoveNulls(collectDistinct(dt.entity.process_group)),
        arrayRemoveNulls(collectDistinct(dt.entity.process_group_instance)),
        arrayRemoveNulls(collectDistinct(dt.entity.kubernetes_cluster)),
        arrayRemoveNulls(collectDistinct(k8s.pod.uid)),
        arrayRemoveNulls(collectDistinct(k8s.cluster.uid)),
        arrayRemoveNulls(collectDistinct(dt.entity.cloud_application_namespace)),
        arrayRemoveNulls(collectDistinct(dt.entity.kubernetes_node)),
        arrayRemoveNulls(collectDistinct(azure.resource.id)),
        arrayRemoveNulls(collectDistinct(aws.resource.id)),
        arrayRemoveNulls(collectDistinct(gcp.resource.id)))
  }, by: {compliance.rule.id}
| fieldsAdd compliance.result.status.level =
      if(compliance.result.count.failed > 0, "FAILED",
      else: if(compliance.result.count.manual > 0, "MANUAL",
      else: if(compliance.result.count.passed > 0, "PASSED", else: "NOT_RELEVANT")))
```

**Why each stage exists:**

| Stage | Purpose |
|---|---|
| Top-level filters | Scope to Dynatrace SPM-generated `COMPLIANCE_FINDING` rows; drop `NOT_RELEVANT`. |
| `join` with `COMPLIANCE_SCAN_COMPLETED` | Dedupe to the **latest completed scan** per object. Without the join, repeated scan attempts double-count findings. |
| `summarize … by: {compliance.rule.id}` | Rolls per-(rule, object) rows into per-rule rows with pass/fail/manual counters. |
| `fieldsAdd compliance.result.status.level` | Derives a rule-level verdict: any failure → `FAILED`; otherwise any manual → `MANUAL`; else `PASSED`. |

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
no-op:

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

> **Standard short-name values for KSPM are limited to `CIS`, `DORA`, `NIST`,
> `STIG`.** PCI / ISO / HIPAA / GDPR / BSI / TISAX / Cyber Essentials / Essential
> Eight come only via CSPM/VSPM or other external integrations and
> may or may not populate `compliance.standard.short_name` consistently.

### Post-Aggregation Filters (insert after Step 2)

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
      OR in(related_entities.ids,   splitString("${entityIdsOrNames}",",")))
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
// Step 1 + Step 2 (as above), then:
| summarize {
    Rules=count(),
    Passed=countIf(compliance.result.status.level=="PASSED"),
    Manual=countIf(compliance.result.status.level=="MANUAL"),
    Failed=countIf(compliance.result.status.level=="FAILED")
  }, by: {compliance.standard.short_name}
| fieldsAdd passRate=round(Passed*100.0/Rules, decimals:0)
| fieldsAdd standardPriority=if(compliance.standard.short_name=="CIS", 0, else: 1)
| sort standardPriority asc, Failed desc
```

**Present the CIS row as the headline failed-rule count.** List DORA / NIST / DISA STIG rows
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

```dql-snippet
// Step 1 + Step 2 (as above), then:
| filter compliance.standard.short_name == "CIS"
     AND compliance.result.status.level == "FAILED"
// Scope to the entity (post-aggregation arrays — see common-patterns.md § 5)
| filter ("${entityIdsOrNames}"=="ALL"
      OR in(affected_entity.ids,    splitString("${entityIdsOrNames}",","))
      OR in(affected_entity.names,  splitString("${entityIdsOrNames}",","))
      OR in(related_entities.names, splitString("${entityIdsOrNames}",","))
      OR in(related_entities.ids,   splitString("${entityIdsOrNames}",",")))
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

**Table 2 — additional failed rules from other Dynatrace standards** (DORA / NIST / DISA STIG).
Same pipeline, `compliance.standard.short_name != "CIS"`, with a **Standard** column:

```dql-snippet
// Step 1 + Step 2 (as above), then:
| filter compliance.standard.short_name != "CIS"
     AND compliance.result.status.level == "FAILED"
| filter ("${entityIdsOrNames}"=="ALL"
      OR in(affected_entity.ids,    splitString("${entityIdsOrNames}",","))
      OR in(affected_entity.names,  splitString("${entityIdsOrNames}",","))
      OR in(related_entities.names, splitString("${entityIdsOrNames}",","))
      OR in(related_entities.ids,   splitString("${entityIdsOrNames}",",")))
| fieldsAdd sevPriority = if(compliance.rule.severity.level=="CRITICAL", 0,
                          else: if(compliance.rule.severity.level=="HIGH",   1,
                          else: if(compliance.rule.severity.level=="MEDIUM", 2,
                          else: 3)))
| sort sevPriority asc
| fields Standard  = compliance.standard.short_name,
         Severity  = compliance.rule.severity.level,
         Rule      = compliance.rule.title,
         `Rule ID` = compliance.rule.id,
         Status    = compliance.result.status.level
```

> Label Table 2 as *additional* failed rules **that may overlap with CIS** — the standards
> overlap, so the same misconfiguration on the entity can fail a CIS rule *and* a
> DORA/NIST/STIG rule. **Never sum failed counts across Tables 1 and 2.**

**Table 3 — externally ingested misconfigurations / compliance findings** (CSPM/VSPM and other
external providers on the entity). Do **not** rebuild this — use the
[External Compliance Queries](#external-compliance-queries-cspm--vspm--external-posture-tools)
patterns below, scoping the
**pre-aggregation** filter to the entity via `object.id` / `dt.smartscape_source.id` /
`k8s.*` (external rows are raw per-finding; the KSPM `affected_entity.*` arrays do not apply).
Use `from:now()-24h` for the external query — external findings arrive on a slower polling
cycle and are not inner-joined to a scan event (unlike DT SPM which requires 1h).
A 0-row result means no external posture tool reported on this entity — still state that
explicitly.

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

> **Do not use `scan.result.summary_json`.** Although `COMPLIANCE_SCAN_COMPLETED`
> events carry a pre-computed `scan.result.summary_json` blob, agents **must not**
> parse it for compliance posture answers. It bypasses the per-rule pipeline,
> causes a second parallel query, and yields pre-aggregated data that cannot be
> filtered, extended, or broken down by rule or severity. Always use the
> `COMPLIANCE_FINDING` canonical pipeline (Steps 1 + 2) instead.

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
    compliance.standard.short_name = takeFirst(compliance.standard.short_name),
    compliance.rule.title = takeFirst(compliance.rule.title),
    compliance.result.count.failed = countIf(compliance.result.status.level == "FAILED"),
    k8s.cluster.names = collectDistinct(k8s.cluster.name),
    affected_entity.names = collectDistinct(object.name)
  }, by: {compliance.rule.id, last_scan.timestamp}
| filter compliance.result.count.failed > 0
     AND in(compliance.rule.severity.level, array("CRITICAL","HIGH"))
| sort compliance.result.count.failed desc
| limit 50
```

> The previous-period sub-window uses `to:-7d+30m` (a 30-min slice a week back) so it captures one
> completed scan without pulling 7 days of rows. Adjust the offset for month-over-month, etc. If a
> 30-min slice catches no completed scan, widen it (e.g. `to:-7d+2h`) so the prior-period baseline
> isn't artificially empty — an empty baseline makes every current failure look "newly failing".
>
> The trailing `in(compliance.rule.severity.level, {"CRITICAL","HIGH"})` is an optional prioritizer
> and may legitimately return zero rows when the period's newly-failing rules are all lower
> severity — drop or widen it to see all newly-failing rules.

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
| sort System == "unguard-dev" desc,
       Result == "FAILED" desc, Result == "MANUAL" desc, Result == "PASSED" desc
| fieldsKeep `Analyzed at`, System, "dt.smartscape*", "dt.entity*", "dt.source*",
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

```dql-snippet
// Step 1 (as above), then:
// Pre-aggregation filter — scope to the named cluster
| filter k8s.cluster.name == "<cluster-name>"
// Step 2 — per-rule verdict (no cluster key needed; already filtered)
| summarize {
    compliance.rule.severity.level = takeFirst(compliance.rule.severity.level),
    passed = countIf(compliance.result.status.level == "PASSED"),
    failed = countIf(compliance.result.status.level == "FAILED"),
    manual = countIf(compliance.result.status.level == "MANUAL")
  }, by: {compliance.rule.id}
| fieldsAdd ruleStatus =
      if(failed > 0, "FAILED",
      else: if(manual > 0, "MANUAL",
      else: if(passed > 0, "PASSED", else: "NOT_RELEVANT")))
// Single summarize — rule counts + per-severity failure breakdown in one row (no by: clause)
| summarize {
    Rules = count(),
    Passed = countIf(ruleStatus == "PASSED"),
    Manual = countIf(ruleStatus == "MANUAL"),
    Failed = countIf(ruleStatus == "FAILED"),
    CriticalFailed = countIf(ruleStatus == "FAILED" AND compliance.rule.severity.level == "CRITICAL"),
    HighFailed    = countIf(ruleStatus == "FAILED" AND compliance.rule.severity.level == "HIGH"),
    MediumFailed  = countIf(ruleStatus == "FAILED" AND compliance.rule.severity.level == "MEDIUM"),
    LowFailed     = countIf(ruleStatus == "FAILED" AND compliance.rule.severity.level == "LOW")
  }
| fieldsAdd passRate = round(Passed * 100.0 / Rules, decimals: 0)
```

If a standard filter is also needed (e.g. "DORA posture on eks-live"), add it as a second
pre-aggregation filter right after the cluster filter:
`| filter contains(lower(compliance.standard.short_name), "dora")`

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
| sort Severity == "CRITICAL" desc, Severity == "HIGH" desc
| fieldsKeep timestamp, "dt.smartscape*", "dt.entity*", "dt.source*",
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
| summarize firstFailedAt = takeMin(toTimestamp(finding.time.created)),
            lastSeen = takeMax(toTimestamp(finding.time.created)),
            scans = countDistinctExact(scan.id),
            by: {compliance.rule.id, compliance.rule.title,
                 object.id, object.name, k8s.cluster.name}
| fieldsAdd ageDays = round((toLong(now()) - toLong(firstFailedAt)) / 1000000000.0 / 86400, decimals: 1)
| sort ageDays desc
| limit 50
```

**Worked single-rule/object form:** substitute the rule and object when the user
asks "this rule on this object." `finding.time.created` is a string timestamp, so
wrap it with `toTimestamp(...)` before `takeMin`, `takeMax`, comparisons, or age
math.

```dql-template
fetch security.events, from:now()-30d
| filter event.type == "COMPLIANCE_FINDING"
     AND product.vendor == "Dynatrace"
     AND product.name == "Security Posture Management"
     AND compliance.result.status.level == "FAILED"
| filter compliance.rule.id == "<RULE_ID>" AND object.id == "<OBJECT_ID>"
| summarize firstFailedAt = takeMin(toTimestamp(finding.time.created)),
            lastSeen = takeMax(toTimestamp(finding.time.created)),
            scans = countDistinctExact(scan.id),
            by: {compliance.rule.id, compliance.rule.title, object.id, object.name}
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
| filter isNotNull(compliance.standards)
| expand compliance.standard = compliance.standards
| summarize {
    Findings=count(),
    Failed=countIf(statusNormalized == "FAILED"),
    Critical=countIf(dt.security.risk.level == "CRITICAL" AND statusNormalized == "FAILED"),
    High=countIf(dt.security.risk.level == "HIGH" AND statusNormalized == "FAILED"),
    SampleTitles=collectDistinct(finding.title, maxLength: 10),
    AffectedObjects=countDistinctExact(object.id)
  }, by:{event.provider, product.name, compliance.standard}
| sort Critical desc, High desc, Failed desc, Findings desc
```

> Providers that don't populate `compliance.standards` won't appear after `filter isNotNull(...)`.
> For those, fall back to grouping by `finding.title` / `finding.type` (see Field caveat below).

**Top failing controls by policy/control** — variant: swap the `by:` clause after `expand`:

```dql-snippet
// …after `expand compliance.standard = compliance.standards`, replace the summarize `by:` with:
  }, by:{event.provider, product.name, compliance.standard, dt.security.risk.level,
         compliance.policy, compliance.control}
| sort Critical desc, High desc, Findings desc
| limit 10
```

**Critical/high external compliance findings newly reported in the last 7d (not in the prior 7d):**

```dql
// This-period findings
fetch security.events, from:-7d, to:now()
| filter event.type == "COMPLIANCE_FINDING"
     AND product.vendor != "Dynatrace" AND event.provider != "Dynatrace"
| filter finding.time.created > now()-7d
| filter isNotNull(compliance.standards)
| expand compliance.standard = compliance.standards
| dedup {object.id, finding.id}
// Anti-join the prior period: keep only findings absent a week ago
| join kind:outer, on:{object.id, finding.id}, [
    fetch security.events, from:-14d, to:-7d
    | filter event.type == "COMPLIANCE_FINDING"
         AND product.vendor != "Dynatrace" AND event.provider != "Dynatrace"
    | filter finding.time.created > now()-14d and finding.time.created < now()-7d
    | filter isNotNull(compliance.standards)
    | expand compliance.standard = compliance.standards
    | dedup {object.id, finding.id}
    | fields object.id, finding.id
  ]
| filter isNull(right.finding.id)
| summarize {
    Findings=count(),
    SampleTitles=collectDistinct(finding.title, maxLength: 5),
    maxScore=takeMax(dt.security.risk.score),
    AffectedObjects=countDistinctExact(object.id)
  }, by:{event.provider, product.name, compliance.standard, dt.security.risk.level,
         compliance.policy, compliance.control}
| sort maxScore desc, Findings desc
```

### Scoping external compliance to a provider

External compliance findings come from CSPM/VSPM and other ingested posture tools, each with
its own provider string and standard coverage. To scope to one, use the shared provider pattern
in [all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type);
discover the active providers first (`summarize by {event.provider, product.vendor, product.name}`).
External standard names populate `compliance.standards` (not `compliance.standard.short_name`).

### Field caveat — KSPM `compliance.rule.*` vs. external taxonomy

External compliance findings use a **different** compliance namespace than KSPM. They do **not**
populate the KSPM rule/standard fields (`compliance.rule.id`, `compliance.rule.title`,
`compliance.rule.severity.level`, `compliance.standard.short_name` / `.name`) — those will
be null. Instead, external rows carry the
**external taxonomy** documented above: `compliance.standards` (array), `compliance.control`,
`compliance.policy`, `compliance.status`, `compliance.requirements`.

- For external findings, group/filter/sort by `compliance.standards` (expand the array),
  `compliance.policy`, `compliance.control` — and `finding.title` / `finding.type` for
  display. Do **not** use `compliance.rule.*` or `compliance.standard.short_name` on them.
- The DT KSPM query patterns (Steps 1 + 2 above) are **incompatible** with external
  compliance findings — they require the KSPM `compliance.rule.*` namespace and the
  inner-join to `COMPLIANCE_SCAN_COMPLETED` (which only DT KSPM emits).
- Status: external rows usually populate the top-level `compliance.status`
  (`FAILED` / `PASSED`) rather than `compliance.result.status.level` — coalesce both
  (`coalesce(compliance.result.status.level, compliance.status)`) when filtering.
- `compliance.requirements` is type-inconsistent (array on some providers, `""` on others) —
  surface it if asked, but don't build filters or grouping on it.

For a cross-provider compliance view (DT KSPM + external aggregated by
`dt.security.risk.level`), see [all-security-events.md](all-security-events.md).

---

## Best Practices

1. **KSPM is K8s-only.** If the user's question implies AWS/Azure/GCP/host
   compliance, route them to CSPM/external — DT-native KSPM has no rules for
   those scopes.
2. **Pin `product.name == "Security Posture Management"`** for KSPM scoping
   when precision matters; `product.vendor == "Dynatrace"` alone is shared
   with RVA and other DT products.
3. **Always exclude `NOT_RELEVANT`** in the base filter and in pass-rate math.
   It's the docs' "Recommended" view default for a reason.
4. **MANUAL is not a defect** — surface it separately, never count it as
   PASSED, never count it in numerator of "pass rate." It's an open question.
5. **Per-rule status precedence is `FAILED > MANUAL > PASSED`** — Step 2's
   `fieldsAdd` derives this. If you re-derive it elsewhere, follow the same
   precedence (or the per-rule verdict will silently disagree with the SPM app).
6. **Severity is `CRITICAL / HIGH / MEDIUM / LOW`** — exactly four. KSPM does
   not emit `NONE` or `NOT_AVAILABLE`. CCSS-derived since 2026-03-10.
7. **Never parse `compliance.rule.metadata_json`** — it is forbidden in this skill.
   Use `compliance.rule.id` (already standard-prefixed and human-recognizable, e.g.
   `CIS-2762`, `STIG-82824`, `DORA-67952`, `NIST-82827`) and `compliance.rule.title` as the
   rule identifiers. The finer benchmark-section citation (CIS `1.2.3`) is intentionally
   not surfaced.
8. **Object identity has two fields on KSPM rows** — `object.type` (normalized
   Dynatrace entity type, uppercase: `KUBERNETES_CLUSTER`, `KUBERNETES_NODE`,
   …) and `compliance.result.object.type` (analyzer's lowercase code:
   `k8scluster`, `k8snode`, …). They're different fields, not synonyms. **On
   external compliance findings**, `object.type` instead carries the
   vendor-reported value as-is (e.g. `AwsEc2Instance`); don't normalize.
9. **Don't expect mute / waiver fields.** Compliance findings have no
   `mute.*` namespace — that's vulnerability-only. If a user asks "show me
   accepted-risk findings," explain the data isn't there.
10. **`COMPLIANCE_SCAN_COMPLETED` is per-cluster, per-scan-run** — not per-object.
    The inner-join on `scan.id` deduplicates findings to the latest scan; the
    join target itself doesn't carry per-rule info. Per-rule rollups go through
    `COMPLIANCE_FINDING` + Step 2.
11. **No SPM scan-completed events for a specific cluster means no SPM coverage.**
  If a named cluster (for example, `gke-live`) has no `COMPLIANCE_SCAN_COMPLETED`
  events and no matching `COMPLIANCE_FINDING` rows for Security Posture
  Management in the operational window, answer that SPM/KSPM is not covering
  that cluster. The likely cause is that SPM is not enabled, deployed, or
  configured for the cluster — not simply that the cluster has no violations.
12. **Widen past 1h only when answering history questions** (e.g. compliance-
    finding age). The 1h default is a snapshot window — widening it in the
    snapshot pattern won't add data, only cost.
13. **One query for compliance posture.** For "what is my compliance posture?"
    run a single query: Steps 1 + 2 + "Grouped by Standard with Pass Rate"
    extension. Do not add a supplementary `scan.result.summary_json` query for
    per-cluster scores. If the user explicitly asks for a per-cluster breakdown
    in the same prompt, run the 3-step per-cluster variant from
    § "Per-Cluster + Per-Namespace Breakdown" as a second query — not a third.
14. **Per-cluster pass rate requires a per-rule-per-cluster Step 2.** Grouping
    directly by `k8s.cluster.name` after Step 1 counts object-check results, not
    rules — the pass rate will be inflated and inconsistent with the per-standard
    summary. Always run the 3-step pipeline: Step 1 → per-rule-per-cluster
    summarize → per-cluster rule counts. See § "Per-Cluster + Per-Namespace
    Breakdown".
14. **Answer posture questions overall first; per-cluster only on request.**
    For "what is my DORA/CIS/NIST posture?" — the primary answer is one query:
    Steps 1+2 + "Grouped by Standard with Pass Rate" (filtered to the named
    standard). Do **not** jump to a per-cluster breakdown unless the user
    explicitly asks for it ("by cluster", "per system", "which clusters fail").
    If asked for both in one prompt, run two queries: standard summary first,
    then the per-cluster 3-step variant.
