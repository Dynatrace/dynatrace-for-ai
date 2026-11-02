# External Vulnerability Findings — `security.events`

Ingested vulnerability findings from external SCA / SAST / image scanners (Snyk,
Qualys, Tenable, AWS Inspector, GitHub Advanced Security, etc.). For Dynatrace-native
Runtime Vulnerability Analytics (RVA) see [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md).

> **Cross-references:** field reference → [data-model.md § Vulnerability Fields (external)](data-model.md#vulnerability-fields-external--dt-emitted-vulnerability_finding) ·
> provider scoping, double-counting guard, cross-provider summary →
> [all-security-events.md](all-security-events.md) · repository coalescing,
> lifecycle anti-join → [common-patterns.md](common-patterns.md) · mapping findings
> to runtime entities → `dt-sec-contextualization/references/entity-enrichment.md`.

## Contents

- [Rankings (components, container images, code artifacts)](#rankings-components-container-images-code-artifacts) (moved to `vulnerabilities-rankings.md`)
- [Verify external findings against RVA](#verify-external-findings-against-rva)
- [Critical external vulnerabilities newly reported in the last 7d](#critical-external-vulnerabilities-newly-reported-in-the-last-7d-not-in-the-prior-7d)
- [Cross-provider vulnerability view](#cross-provider-vulnerability-view)
- [Mapping external findings to runtime entities](#mapping-external-findings-to-runtime-entities)

External vulnerability findings are one-shot `VULNERABILITY_FINDING` events. They do
**not** need the dedup+summarize-to-state pipeline that DT RVA requires — each row is
already a discrete finding. Dedup is still useful when the same finding is re-ingested.

> **External component fields:** use `software_component.*` as the SD-compatible
> component namespace for external `VULNERABILITY_FINDING` rows (especially
> `software_component.name`, `software_component.purl`, `software_component.type`).
> Some providers still populate legacy `component.name` / `component.version`, so
> use `coalesce(software_component.name, component.name)` for display and dedup
> keys when broad provider compatibility is needed. Do **not** use
> `affected_entity.vulnerable_component.*` on external findings — that namespace is
> Dynatrace RVA-specific.

> **CVE reference field:** use `vulnerability.references.cve` for CVE matching on
> both external `VULNERABILITY_FINDING` rows and DT RVA rows. It is usually an
> array, so prefer `in("CVE-…", vulnerability.references.cve)` or `expand` before
> equality checks. Do **not** query invented fields such as
> `vulnerability.cve.id` or `vulnerability.cve.ids`.

> **Mandatory SD-isNotNull guard (nine fields).** Severity/count summaries (per-object, entity- or name-scoped,
> cross-provider) must carry **all nine**: `event.id`, `event.provider`, `finding.type`, `finding.id`,
> `finding.time.created`, `finding.title`, `dt.security.risk.level`, `object.id`, `object.type` — copy the block from
> the *Summary for named objects* template below and keep it whole when adapting (authoritative:
> [all-security-events.md § Mandatory guards](all-security-events.md#mandatory-guards-for-any-cross-provider-count-or-summary)).
> A three-field subset is not the guard. The distinct-vulnerability rankings (top vulnerabilities, container images,
> code artifacts) use a lighter identity guard on purpose: some providers (Amazon ECR) leave `finding.type` null, so
> the full guard would empty them.

**All external vulnerabilities:**

```dql
fetch security.events
| filter event.type == "VULNERABILITY_FINDING"
| filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
```

**Vulnerabilities-app compatibility check** (validates all SD-required fields are
present):

```dql
fetch security.events
| filter event.type == "VULNERABILITY_FINDING"
| filter isNotNull(event.id)
     and isNotNull(event.provider)
     and isNotNull(finding.type)
     and isNotNull(dt.security.risk.level)
     and isNotNull(dt.security.risk.score)
     and isNotNull(finding.id)
     and isNotNull(finding.title)
     and isNotNull(object.id)
     and isNotNull(object.type)
     and isNotNull(finding.time.created)
```

**Top 10 external vulnerabilities by affected object count:**

One row per vulnerability (`vulnerability.id`), carrying its risk level, finding count, and CVE list.

```dql
fetch security.events
| filter event.type=="VULNERABILITY_FINDING"
| filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
| filterOut isNull(finding.id) OR isNull(object.id) OR isNull(vulnerability.id)
| fieldsAdd component_name = coalesce(software_component.name, component.name),
            component_version = component.version
| dedup {object.id, vulnerability.id, component_name, component_version}, sort: {timestamp desc}
| summarize {
    `Risk score`=toDouble(takeMax(dt.security.risk.score)),
    `Risk level`=takeFirst(dt.security.risk.level),
    Findings=count(),
    `Affected objects`=countDistinctExact(object.id),
    `Vulnerable components`=countDistinctExact(component_name),
    CVEs=collectDistinct(vulnerability.references.cve, expand:true)
  }, by:{Vulnerability=vulnerability.title, vulnerability.id}
| sort {`Risk score`, direction:"descending"}, {`Affected objects`, direction:"descending"}
| fields `Risk level`, `Risk score`, Vulnerability, vulnerability.id, CVEs,
         `Affected objects`, `Vulnerable components`, Findings
| limit 10
```

**Summary of external findings for named objects** (per-object severity counts; the reference shape for any
entity- or name-scoped external summary):

Placeholders: `${objectName}` — case-insensitive fragment of `object.name`, for example `unguard`.

```dql-template
fetch security.events, from:now()-24h
| filter event.type == "VULNERABILITY_FINDING"
| filterOut event.provider == "Dynatrace" or product.vendor == "Dynatrace"
// SD-isNotNull guard — mandatory, keep all nine fields (never trim to a subset)
| filter isNotNull(event.id) AND isNotNull(event.provider) AND isNotNull(finding.type)
     AND isNotNull(finding.id) AND isNotNull(finding.time.created) AND isNotNull(finding.title)
     AND isNotNull(dt.security.risk.level) AND isNotNull(object.id) AND isNotNull(object.type)
| filter contains(object.name, "${objectName}", caseSensitive:false)
| summarize {
    Findings = count(),
    Critical = countIf(dt.security.risk.level == "CRITICAL"),
    High     = countIf(dt.security.risk.level == "HIGH"),
    Medium   = countIf(dt.security.risk.level == "MEDIUM"),
    Low      = countIf(dt.security.risk.level == "LOW"),
    SampleTitles = collectDistinct(finding.title, maxLength: 5)
  }, by: {event.type, event.provider, product.name, object.name, object.type}
| sort Critical desc, High desc, Findings desc
```

## Rankings (components, container images, code artifacts)

"Top vulnerable libraries / container images / code artifacts" over external findings are in
[vulnerabilities-rankings.md](vulnerabilities-rankings.md) (§ UC-V9 and the two sections after it),
next to the RVA rankings. This file keeps the external finding semantics, verification and
newly-reported queries.

## Verify external findings against RVA

Verifying external findings against Dynatrace RVA, and against running K8s workloads or
hosts, is done in dt-sec-contextualization `external-finding-verification.md`. It takes
the finding set produced here and works in two stages: (1) same CVE on both sides via
`vulnerability.references.cve`, then (2) the same runtime entity (direct Smartscape id,
container-image digest to workload, or `host.ip` to HOST). Report the stages separately.
RVA counts and rankings stay in [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md), RVA lifecycle in [vulnerabilities-lifecycle.md](vulnerabilities-lifecycle.md).

## Critical external vulnerabilities newly reported in the last 7d (not in the prior 7d)

"What's genuinely new this week?" — take this period's critical external findings and anti-join
(outer join + `isNull(right…)`) against the prior 7-day period, deduped per `{object.id, vulnerability.id}`:

```dql
// This period's critical external findings
fetch security.events, from:-7d, to:now()
| filter event.type == "VULNERABILITY_FINDING" AND dt.security.risk.level == "CRITICAL"
| filterOut event.provider == "Dynatrace" or product.vendor == "Dynatrace"
| dedup {object.id, vulnerability.id}
// Anti-join the previous 7-day window
| join kind:outer, on:{object.id, vulnerability.id}, [
    fetch security.events, from:-14d, to:-7d
    | filter event.type == "VULNERABILITY_FINDING" AND dt.security.risk.level == "CRITICAL"
    | filterOut event.provider == "Dynatrace" or product.vendor == "Dynatrace"
    | dedup {object.id, vulnerability.id}
    | fields object.id, vulnerability.id
  ]
| filter isNull(right.vulnerability.id)   // present now, absent in the prior period
| fields event.provider, product.name, dt.security.risk.level, dt.security.risk.score,
         finding.time.created, finding.title, vulnerability.id, object.name,
         component.name, repository=coalesce(artifact.repository, container_image.repository)
| sort dt.security.risk.score desc
```

> Adjust `dt.security.risk.level` (or drop it) and the window offsets for other severities / cadences.

**Reading the result.** One row is one affected object, not one vulnerability: a registry scanner such
as Amazon ECR reports one finding per image digest (`object.id` is the image ARN, `object.name` the
repository), so a CVE appears once per image, and Qualys, Snyk and GitHub Advanced Security repeat it
per host or repository. For "how many new vulnerabilities" count `countDistinctExact(vulnerability.id)`;
keep the per-object rows for "which objects". Do not change the key to `object.name`: that hides a new
image in a repository that already had the CVE. The level is vendor-reported, so a `CRITICAL` row can
carry score 0 (for example ECR "Platform End Of Life"); call those out instead of dropping them. The
14-day scan is heavy (about 77 GB on a busy tenant): narrow the window or the provider when asked for
less.

## Cross-provider vulnerability view

To combine Dynatrace-native (canonical RVA pattern) with ingested findings using the
normalized fields `dt.security.risk.level`, `finding.id`, `finding.title`,
`object.id`, `object.name`, `object.type`, see
[all-security-events.md](all-security-events.md).

## Mapping external findings to runtime entities

External findings carry `object.*` / `container_image.*` / cloud-resource identifiers,
not Dynatrace runtime entity IDs. To map them to hosts / K8s workloads / cloud entities
via Smartscape, use the recipes in `dt-sec-contextualization/references/entity-enrichment.md`.
To verify them against Dynatrace RVA on the same runtime entity, use
`dt-sec-contextualization/references/external-finding-verification.md`.
