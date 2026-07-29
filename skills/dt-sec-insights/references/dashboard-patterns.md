# Dashboard Query Patterns

KPI tiles, top-N tables, trend charts, and container/registry rollups. Each
pattern complements the base queries in [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md),
[compliance.md](compliance.md), and [detections.md](detections.md).

For shared building blocks (risk-level mapping, status aggregation, sem-dict
filter, time-window rules), see [common-patterns.md](common-patterns.md). For
field reference, see [data-model.md](data-model.md).

> **No `dt.system.bucket` filter.** Security event data may live in any bucket;
> bucket scoping risks hiding tile data.

> **Load this reference only for dashboard / chart / KPI requests.** For plain
> investigation, triage, or drill-down, the per-domain references are sufficient.

---

## Contents

- [KPI Tiles (single-value)](#kpi-tiles-single-value)
  - [Open Non-Muted Vulnerability Count (DT RVA)](#open-non-muted-vulnerability-count-dt-rva)
  - [Vulnerabilities with Public Exploit Available](#vulnerabilities-with-public-exploit-available)
  - [Open vs. Resolved Status Counter](#open-vs-resolved-status-counter)
  - [Critical External Findings by Registry](#critical-external-findings-by-registry)
- [Top-N Tables](#top-n-tables)
  - [Top 10 External Vulnerabilities by Affected Object Count](#top-10-external-vulnerabilities-by-affected-object-count)
  - [Top 10 Container-Image Vulnerabilities by Image Count](#top-10-container-image-vulnerabilities-by-image-count)
  - [Top 10 Repositories by Critical+High Findings](#top-10-repositories-by-criticalhigh-findings)
  - [Top 10 Vulnerable Components](#top-10-vulnerable-components)
  - [Findings Distribution by Object Type (HIGH+CRITICAL only)](#findings-distribution-by-object-type-highcritical-only)
  - [Top 10 Affected Hosts (entity-enriched)](#top-10-affected-hosts-entity-enriched)
- [Trend Charts (timeseries)](#trend-charts-timeseries)
  - [Vulnerability Counts Over Time, Stacked by Risk Level](#vulnerability-counts-over-time-stacked-by-risk-level)
- [Provider / Product Coverage Summary](#provider--product-coverage-summary)
  - [Findings vs. Scans Split per Product](#findings-vs-scans-split-per-product)
- [Coverage Donut Variants (smartscapeNodes-driven)](#coverage-donut-variants-smartscapenodes-driven)
  - [Host Coverage by Any External Product (donut)](#host-coverage-by-any-external-product-donut)
  - [Entity-Centric Coverage via `fetch dt.entity.host`](#entity-centric-coverage-via-fetch-dtentityhost)
- [Multi-Type Combined Views](#multi-type-combined-views)
  - [One-Row-Per-Entity Risk Summary (DT RVA + external)](#one-row-per-entity-risk-summary-dt-rva--external)

---

## KPI Tiles (single-value)

### Open Non-Muted Vulnerability Count (DT RVA)

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT","VULNERABILITY_STATUS_CHANGE_EVENT","VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| filter vulnerability.mute.status != "MUTED"
| summarize count()
```

### Vulnerabilities with Public Exploit Available

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT","VULNERABILITY_STATUS_CHANGE_EVENT","VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| filter vulnerability.davis_assessment.exploit_status=="AVAILABLE"
| summarize {Vulnerabilities = countDistinctExact(vulnerability.display_id)}
```

### Open vs. Resolved Status Counter

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT","VULNERABILITY_STATUS_CHANGE_EVENT","VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| summarize {
    Open=countIf(vulnerability.resolution.status=="OPEN"),
    Resolved=countIf(vulnerability.resolution.status=="RESOLVED")
  }
```

### Critical External Findings by Registry

```dql
fetch security.events
| filter event.type=="VULNERABILITY_FINDING" AND dt.security.risk.level=="CRITICAL"
| filter isNotNull(container_image.registry)
| dedup {object.id, vulnerability.id}
| summarize {Findings=count()}, by:{Registry=container_image.registry}
```

---

## Top-N Tables

### Top 10 External Vulnerabilities by Affected Object Count

```dql
fetch security.events
| filter event.type=="VULNERABILITY_FINDING"
| fieldsAdd repository=coalesce(artifact.repository, container_image.repository)
| filterOut isNull(finding.id) OR isNull(object.id) OR isNull(vulnerability.id)
| fieldsAdd component_name=coalesce(software_component.name, component.name),
            component_version=component.version
| dedup {object.id, vulnerability.id, component_name, component_version}, sort: {timestamp desc}
| summarize {
    `Risk score`=toDouble(takeMax(dt.security.risk.score)),
    `Affected objects`=countDistinctExact(object.id),
    `Vulnerable components`=countDistinctExact(component_name)
  }, by:{Vulnerability=vulnerability.title, `Risk level`=dt.security.risk.level}
| sort {`Risk score`, direction:"descending"}
| fields `Risk level`, Vulnerability, `Affected objects`, `Vulnerable components`
| limit 10
```

### Top 10 Container-Image Vulnerabilities by Image Count

```dql
fetch security.events
| filter event.type == "VULNERABILITY_FINDING"
     AND object.type == "CONTAINER_IMAGE"
| fieldsAdd component_name=coalesce(software_component.name, component.name),
      component_version=component.version
| filter isNotNull(component_name)
| dedup {object.id, vulnerability.id, component_name, component_version,
         container_image.registry, container_image.repository}, sort: {timestamp desc}
| summarize {
    `Risk score`=toDouble(takeMax(dt.security.risk.score)),
    `Container images`=countDistinctExact(container_image.digest)
  }, by:{Vulnerability=vulnerability.id, `Risk level`=dt.security.risk.level}
| sort {`Risk score`, direction:"descending"}, {`Container images`, direction:"descending"}
| fields `Risk level`, Vulnerability, `Container images`
| limit 10
```

### Top 10 Repositories by Critical+High Findings

```dql
fetch security.events
| filter event.type == "VULNERABILITY_FINDING"
| fieldsAdd repository=coalesce(artifact.repository, container_image.repository)
| filter isNotNull(repository)
| dedup {repository, vulnerability.id, object.id}
| summarize {
    Findings=count(),
    Critical=countIf(dt.security.risk.level=="CRITICAL"),
    High=countIf(dt.security.risk.level=="HIGH")
  }, by:{Repository=repository}
| sort Critical desc, High desc
| limit 10
```

### Top 10 Vulnerable Components

```dql
fetch security.events
| filter event.type=="VULNERABILITY_FINDING"
| fieldsAdd component_name=coalesce(software_component.name, component.name),
            component_version=component.version
| filter isNotNull(component_name)
| dedup {component_name, component_version, vulnerability.id}
| summarize {
    Findings=count(),
    Critical=countIf(dt.security.risk.level=="CRITICAL"),
    High=countIf(dt.security.risk.level=="HIGH"),
    `Affected images`=countDistinctExact(container_image.digest)
  }, by:{Component=component_name, Version=component_version}
| sort Critical desc
| limit 10
```

### Findings Distribution by Object Type (HIGH+CRITICAL only)

```dql
fetch security.events
| filter event.type=="VULNERABILITY_FINDING" AND in(dt.security.risk.level,{"HIGH","CRITICAL"})
| dedup {object.id, vulnerability.id}, sort: {timestamp desc}
| summarize {Findings=count()}, by:{`Object type`=object.type}
| sort Findings desc
```

### Top 10 Affected Hosts (entity-enriched)

Joins findings to HOST smartscapeNodes for runtime context. For full 3-way
enrichment (container image digest / id paths), see
[dt-sec-contextualization/references/entity-enrichment.md](../../dt-sec-contextualization/references/entity-enrichment.md).

```dql
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT","VULNERABILITY_STATUS_CHANGE_EVENT","VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| summarize {
    Vulnerabilities=count(),
    Critical=countIf(vulnerability.risk.score >= 9)
  }, by:{affected_entity.id, affected_entity.name}
| join [smartscapeNodes HOST], on:{right[id]==left[affected_entity.id]}
| sort Vulnerabilities desc
| limit 10
```

---

## Trend Charts (timeseries)

### Vulnerability Counts Over Time, Stacked by Risk Level

Uses a computed sort key (`riskLevelSorting`) so the visualization stacks levels
in CRITICAL → LOW order:

```dql
fetch security.events
| filter event.type == "VULNERABILITY_FINDING"
| fieldsAdd riskLevelSorting = coalesce(
    if(dt.security.risk.level=="CRITICAL", 1),
    if(dt.security.risk.level=="HIGH",     2),
    if(dt.security.risk.level=="MEDIUM",   3),
    if(dt.security.risk.level=="LOW",      4),
    5)
| makeTimeseries countDistinct(vulnerability.id),
                 by:{riskLevelSorting, dt.security.risk.level},
                 bins: 24
```

For DT RVA equivalents (open vulnerability counts over 7d in 3h buckets), see
[vulnerabilities-dynatrace.md § Time-Series Trends](vulnerabilities-dynatrace.md#dt-rva-time-series-trends-7-days-3h-buckets).

---

## Provider / Product Coverage Summary

### Findings vs. Scans Split per Product

```dql
fetch security.events
| summarize {
    Findings=countIf(in(event.type,{"VULNERABILITY_FINDING","DETECTION_FINDING","COMPLIANCE_FINDING"})),
    Scans=countIf(in(event.type,{"VULNERABILITY_SCAN","COMPLIANCE_SCAN"}))
  }, by:{Provider=event.provider, Product=product.name}
```

This is the canonical "which integrations are active" query — counts both findings
and scan-coverage events per source.

---

## Coverage Donut Variants (smartscapeNodes-driven)

### Host Coverage by Any External Product (donut)

```dql
smartscapeNodes HOST
| dedup id
| join [
    fetch security.events
    | filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
    | filter exists(host.ip)
  ], on:{host.ip}, kind:leftOuter
| summarize count(), by:{covered=if(isNotNull(event.provider), "Covered", else:"Not covered")}
```

### Entity-Centric Coverage via `fetch dt.entity.host`

Alternative to `smartscapeNodes`-based coverage; uses the entity stream directly:

```dql
fetch dt.entity.host
| lookup [
    fetch security.events
    | filter event.type == "VULNERABILITY_SCAN"
    | dedup dt.entity.host
  ], sourceField:id, lookupField:dt.entity.host
| summarize count(), by:{coverage=if(isNotNull(lookup.dt.entity.host), "covered", else: "not covered")}
```

For full coverage analysis broken down by provider/product (and the 3-way
K8s/host match), see [coverage.md](coverage.md).

---

## Multi-Type Combined Views

### One-Row-Per-Entity Risk Summary (DT RVA + external)

To produce a single row per entity with risk counts across vulnerability types,
combine the canonical RVA pattern (from [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md))
with external findings via `union`/`append`, then summarize. Keep this as a
reporting-layer merge — don't try to unify the two query shapes upstream.

```dql
// Branch A: DT RVA per entity
fetch security.events, from:now()-30m
| filter event.provider=="Dynatrace"
| filter in(event.type,{"VULNERABILITY_STATE_REPORT_EVENT","VULNERABILITY_STATUS_CHANGE_EVENT","VULNERABILITY_TRACKING_LINK_CHANGE_EVENT"})
     AND event.level=="ENTITY"
| dedup {vulnerability.display_id, affected_entity.id}, sort:{timestamp desc}
| summarize {
    Critical = countIf(vulnerability.risk.score >= 9),
    High     = countIf(vulnerability.risk.score >= 7 and vulnerability.risk.score < 9),
    Medium   = countIf(vulnerability.risk.score >= 4 and vulnerability.risk.score < 7),
    Low      = countIf(vulnerability.risk.score >= 0.1 and vulnerability.risk.score < 4)
  }, by:{Entity=affected_entity.name}
| append [
    // Branch B: external per object (sample)
    fetch security.events
    | filter event.type=="VULNERABILITY_FINDING"
    | filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"
    | dedup {object.id, vulnerability.id}
    | summarize {
        Critical=countIf(dt.security.risk.level=="CRITICAL"),
        High    =countIf(dt.security.risk.level=="HIGH"),
        Medium  =countIf(dt.security.risk.level=="MEDIUM"),
        Low     =countIf(dt.security.risk.level=="LOW")
      }, by:{Entity=object.name}
  ]
| summarize {
    Critical=sum(Critical), High=sum(High), Medium=sum(Medium), Low=sum(Low)
  }, by:{Entity}
| sort Critical desc, High desc
| limit 25
```

---

## Threat Intelligence Dashboards

Threat-intelligence (`THREAT_REPORT`) tiles use the canonical base (SD guard +
`dedup {threat.report.id}`) — see [threat-intelligence.md](threat-intelligence.md). Two ready-made
sample dashboards live in `evals/skills/dt-sec-insights/sources/sample-dashboards/`:

- **`emerging-threat-intelligence-reports.json`** — overview: unique-reports-over-time by provider
  (`makeTimeseries count(), by:{event.provider}`), total-reports single value, last-10-reports table,
  and top-N IOC/actor/industry/country/tag/technique tiles (`expand` observable →
  `countDistinctExact(threat.report.id)`). Visualizations: **choropleth** for target countries
  (`threat.target.countries.iso_codes`), **categorical bar** (log scale) for actors / industries /
  tags, **bar chart** for the provider trend.
- **`threat-exposure-analysis.json`** — per-report drilldown: select a report, extract its IOCs, then
  correlate against the environment (RVA + external vulnerabilities by CVE, detections by actor IP /
  MITRE technique, logs by `contains(content, …)`, traces by IP/domain/URL). Uses dashboard
  **variables** to carry the IOC lists and `in(field, $Var)` filters (the self-contained-query
  equivalent uses `join` — see [threat-intelligence.md § Threat-Exposure Correlation](threat-intelligence.md#threat-exposure-correlation-ioc--environment)).

> **Tile field nuances:** use `threat.target.industries` (plural) and
> `threat.target.countries.iso_codes` for the map; `coalesce(toTimestamp(threat.report.time.created), timestamp)`
> for report time. These are threat-intel tiles — do **not** add `dt.security.risk.level` coloring
> (the field is null on `THREAT_REPORT`).
