---
name: dt-obs-compliance-assistant
description: >-
  Monitor and investigate EU DORA compliance posture using Dynatrace Compliance Assistant.
  Covers compliance score, CIF health, incident lifecycle, and ICT risk inputs
  (vulnerabilities, security detection findings, misconfigurations).
  Trigger: "DORA compliance", "Digital Operational Resilience Act", "compliance score",
  "compliance snapshot", "score tier", "Critical or Important Functions", "CIF", "CIF health",
  "unclassified problems", "potential major incident", "classified major incident",
  "incident classification under DORA", "compliance.incident bizevent",
  "DQL for classified incidents", "set up Compliance Assistant", "DORA onboarding".
  Do NOT use for other compliance frameworks (SOC2, PCI-DSS, HIPAA, ISO 27001),
  generic Davis problems without DORA or CIF context,
  generic security findings not scoped to DORA,
  or score queries without compliance context.
license: Apache-2.0
---

# Compliance Assistant

Track, manage, and investigate EU DORA compliance posture using real-time observability and security insights from the Dynatrace Compliance Assistant app.

---

## Critical Disclaimer

The Dynatrace compliance score and all outputs from Compliance Assistant are **indicative metrics based on real-time observability data and automated systems**. They do **not** replace comprehensive or formal compliance assessments and do **not** constitute a legal determination of a company's compliance status under EU DORA or any other regulation.

**Never claim that a score, tier, or Compliance Assistant output means an organization is legally compliant or non-compliant with EU DORA.** Always present results as operational indicators to support remediation decisions, not as legal or regulatory verdicts.

---

## When to Use This Skill

✅ **Use for:**
- EU DORA compliance posture, compliance score, compliance snapshot, score tier
- Critical or Important Functions (CIFs): health, KPI monitoring, impact analysis, setup questions
- Incident lifecycle under DORA: unclassified problems, potential major incidents, classified major incidents
- ICT risk inputs: vulnerabilities, security detection findings, misconfigurations (ICT asset configuration results)
- Incident classification under EU DORA: materiality thresholds, duration criteria, economic impact
- DQL queries for `compliance.incident` bizevents, CIF health, or unclassified problems on CIFs
- Onboarding, permissions, and settings for Compliance Assistant

❌ **Do not use for:**
- Regulatory frameworks other than EU DORA — SOC2, PCI-DSS, HIPAA, ISO 27001 are **not supported** by this app
- Generic Davis problems with no DORA, CIF, or compliance context → use `dt-obs-problems`
- Generic vulnerability or security finding queries not scoped to compliance or DORA → use application security skills
- Generic "score" queries without "compliance" or "DORA" — Dynatrace has many scores
- Configuring Business Flow or defining business process steps → see [Business Flow documentation](https://docs.dynatrace.com/docs/observe/business-observability/business-flow)
- Configuring Security Posture Management rules → see [SPM documentation](https://docs.dynatrace.com/docs/secure/application-security/spm)
- General DQL syntax help → use `dt-dql-essentials`

---

## Prerequisites

### Installation

Install Compliance Assistant from [Dynatrace Hub](https://www.dynatrace.com/hub/detail/compliance-assistant/).

### Required Permissions

| Permission | Purpose |
|---|---|
| `storage:buckets:read` | Read buckets |
| `storage:events:read` | Read events |
| `storage:entities:read` | Read entities table |
| `storage:metrics:read` | Required for Istio discovery findings rule |
| `storage:filter-segments:read` | Read filter segments |
| `settings:objects:read` | Read Log ingest settings |
| `settings:schemas:read` | Read settings schemas |
| `state:app-states:read` | Read app state |
| `hub:catalog:read` | Read app version |
| `storage:security.events:read` | Fetch security events |

### Required Data Sources

| Source | Purpose |
|---|---|
| [Business Flow](https://docs.dynatrace.com/docs/observe/business-observability/business-flow) | CIF monitoring and incident detection on business processes — required for incident classification |
| [Vulnerability events](https://docs.dynatrace.com/docs/secure/threat-observability/concepts#vuln-events) | Continuous vulnerability assessment (DORA requirement) |
| [Detection finding events](https://docs.dynatrace.com/docs/secure/threat-observability/concepts#detection) | Continuous cyber threat assessment (DORA requirement) |
| [Compliance events](https://docs.dynatrace.com/docs/secure/threat-observability/concepts#compliance) | ICT asset secure configuration baseline verification (DORA requirement) — powered by [Security Posture Management](https://docs.dynatrace.com/docs/secure/application-security/spm) |

---

## Core Concepts

### Compliance Framework

Compliance Assistant currently supports **EU DORA (Digital Operational Resilience Act)** only. It consolidates observability and security insights into a single compliance posture view for this framework. Support for additional frameworks is planned.

### Dynatrace Score (Compliance Snapshot)

A real-time, tiered score summarizing current ICT risk posture across potential incidents, security detection findings, vulnerabilities, and misconfigurations. The score tier is determined by the most severe active condition; within a tier, the score is reduced by a penalty for each criterion met.

**Score tiers:**

| Tier | Max score | Triggered when… |
|------|-----------|-----------------|
| **On Track** | 100 | No criteria met across incidents, security detection findings, vulnerabilities, misconfigurations |
| **Low** | 99 | Any low-severity finding in security detection findings/vulnerabilities/misconfigurations |
| **Medium** | 79 | Any medium-severity finding, or ≥1 unclassified incident |
| **High** | 59 | Any high-severity finding, or ≥5 unclassified incidents |
| **Critical** | 34 | Any critical security detection finding/vulnerability/misconfiguration, or ≥1 potential major incident |
| **Major** | 5 (fixed) | ≥1 confirmed classified major incident — short-circuits to a fixed score of 5 |

**Penalty mechanic:** Within a tier, score = tier max − (6 × number of criteria met in that tier). For example, Medium tier with 2 criteria met: 79 − 12 = 67.

> This score is a high-level operational indicator. It does **not** confirm regulatory compliance or legal status.

### Critical or Important Functions (CIFs)

Under EU DORA, financial entities must identify and monitor business functions that, if disrupted, could significantly impact financial performance or service continuity. In Compliance Assistant, CIFs are configured by linking [Business Flow](https://docs.dynatrace.com/docs/observe/business-observability/business-flow) business processes to the DORA framework. [Smartscape on Grail](https://docs.dynatrace.com/docs/discover-dynatrace/platform/grail/smartscape-on-grail) provides end-to-end visibility by linking each CIF to its underlying IT components.

### Incident Lifecycle

Davis-detected problems affecting CIF business processes move through three states:

| State | Definition |
|-------|------------|
| **Unclassified problem** | A Davis problem affects a CIF but fewer than 2 DORA materiality thresholds are breached |
| **Potential major incident** | ≥2 monitored DORA materiality thresholds are breached |
| **Classified major incident** | Manually confirmed as major in Compliance Assistant; generates a `compliance.incident` bizevent snapshot |

**EU DORA materiality thresholds monitored:**

| Threshold | Criterion |
|-----------|-----------|
| CIFs affected | Blast radius across critical or important functions |
| Incident duration | 24-hour threshold |
| Economic impact | €100,000 threshold, calculated from estimated cost per minute of affected CIFs × incident duration |

Classification is always a **manual step** performed in the Compliance Assistant app. Do not classify incidents on behalf of the user.

Once classified, the generated `compliance.incident` bizevent can trigger automations via Dynatrace Workflows (e.g., creating a ServiceNow incident or Jira ticket enriched with compliance impact details).

### ICT Risk Inputs

| Signal type | Source | DORA requirement |
|-------------|--------|-----------------|
| **Vulnerabilities** | Vulnerability findings | Continuous vulnerability assessment |
| **Security detection findings** | Detection finding events | Continuous cyber threat assessment |
| **ICT asset configuration results** | Compliance events via Security Posture Management | Secure configuration baseline verification |

---

## DQL Reference

### Classified Major Incidents

Fetch `compliance.incident` bizevents generated when an incident is classified as major. To retrieve a specific incident, filter by `problem.event.id`.

```dql-template
fetch bizevents
| filter event.provider == "dynatrace.compliance.assistant"
| filter event.type == "compliance.incident"
| filter problem.event.id == {{.incident_id:string}}
```

To fetch all classified incidents:

```dql
fetch bizevents
| filter event.provider == "dynatrace.compliance.assistant"
| filter event.type == "compliance.incident"
```

**Key fields** (see [Semantic Dictionary](https://docs.dynatrace.com/docs/semantic-dictionary/model/business-analytics#compliance-assistant-incident-event) for the full schema):

| Field | Type | Description |
|-------|------|-------------|
| `compliance.cifs_impacted.names` | string | Distinct list of names of the Business Flow entities configured as CIFs affected by the incident (e.g., `Account opening; Deposit and trade flow`) |
| `compliance.cifs_impacted.ids` | string | Distinct list of unique identifiers of the Business Flow entities configured as CIFs affected by the incident |
| `compliance.framework` | string | Display name of the compliance framework (e.g., `DORA`) |
| `compliance.incident.classified` | boolean | `true` when the incident has been manually classified as major in line with DORA requirements |
| `compliance.incident.comment` | string | Comment added by the user when classifying the incident as major (e.g., `"The incident was classified as major due to insights on reputational damage and user impact."`) |
| `compliance.incident.duration` | duration | Duration of the incident in nanoseconds, used to evaluate the 24h DORA duration materiality threshold |
| `compliance.incident.duration_criteria` | boolean | `true` if the DORA 24h incident duration materiality threshold was breached |
| `compliance.incident.economic_impact` | double | Estimated economic impact in EUR, calculated from the estimated cost per minute of affected CIFs × incident duration |
| `compliance.incident.economic_impact_criteria` | boolean | `true` if the DORA €100,000 economic impact materiality threshold was breached |
| `compliance.incident.name` | string | Display name of the incident — matches the `event.name` of the underlying `dt.davis.problem` (e.g., `CPU saturation`) |
| `compliance.incident.time.classified` | timestamp | Unix epoch timestamp (nanoseconds) when the incident was classified as major |
| `event.provider` | string | Always `dynatrace.compliance.assistant` for Compliance Assistant incident bizevents |
| `event.type` | string | Always `compliance.incident` for Compliance Assistant incident bizevents |
| `problem.category` | string | Problem category from the underlying Davis problem: `AVAILABILITY`, `ERROR`, `SLOWDOWN`, `RESOURCE_CONTENTION`, `CUSTOM_ALERT`, `MONITORING_UNAVAILABLE` |
| `problem.event.id` | string | Unique identifier of the underlying `dt.davis.problem` — use this to correlate with problem queries |
| `problem.status` | string | Status of the underlying Davis problem: `ACTIVE` or `CLOSED` |

### Unclassified Problems and Potential Major Incidents on CIFs

Finds Davis problems affecting CIFs that have no matching `compliance.incident` bizevent — i.e., problems not yet manually classified. The `isNull(lookup.event.id)` anti-join is the key pattern.

```dql-template
fetch dt.davis.problems, from: {{.from}}, to: {{.to}}
| expand affected_entity_ids
| join [
    smartscapeNodes "*"
  ], on: {left[affected_entity_ids] == right[id_classic]}, prefix: "entities."
| join [
    smartscapeEdges "*"
  ], on: {left[entities.id] == right[target_id]}, prefix: "edges."
| join [
    smartscapeNodes "BIZ_FLOW"
  ], on: {left[edges.source_id] == right[id]}, prefix: "nodes."
| lookup [
    fetch bizevents
    | filter event.provider == "dynatrace.compliance.assistant"
      and event.type == "compliance.incident"
  ], sourceField: `event.id`, lookupField: `problem.event.id`, executionOrder: auto
| filter isNull(lookup.event.id)
| fields display_id,
         name = event.name,
         status = event.status,
         cif = nodes.name,
         affectedEntity = entities.name,
         event.start,
         event.end,
         nodes.bizflow.id,
         category = event.category
| filter in(nodes.bizflow.id, {"{{.cif_id_1}}", "{{.cif_id_2}}"})
| summarize {
    status      = takeFirst(status),
    cifIds      = collectDistinct(nodes.bizflow.id),
    cifs        = collectDistinct(cif),
    start       = min(event.start),
    end         = max(event.end),
    duration    = max(coalesce(event.end, now()) - event.start),
    category    = takeFirst(category)
  }, by: { display_id, name }
| limit {{.max_entries:long}}
```

**Notes:**
- Source is `dt.davis.problems`, not `bizevents`
- `filter isNull(lookup.event.id)` identifies problems with no classified incident bizevent
- `in(nodes.bizflow.id, {...})` restricts to problems whose Smartscape graph touches a configured CIF (`BIZ_FLOW` node)
- Replace `{{.cif_id_1}}`, `{{.cif_id_2}}` with actual Business Flow entity IDs from the DORA framework settings in Compliance Assistant
- For a single CIF, use `| filter nodes.bizflow.id == "{{.cif_id}}"`

### CIF Health (Business Flow KPIs)

Fetches the latest KPI snapshot per CIF. KPI data is emitted by Business Flow (`event.type == "bizflow.kpis"`), not by Compliance Assistant directly.

```dql-template
fetch bizevents, from: now()-24h, to: now()
| filter event.type == "bizflow.kpis"
| filter bizflow.id == "{{.cif_id_1}}" or bizflow.id == "{{.cif_id_2}}"
| fieldsAdd timestamp, bizflowId = bizflow.id, bizflowName = bizflow.name
| sort timestamp asc
| summarize {
    fulfillment   = takeLast(bizflow.analysis.value),
    errors        = takeLast(bizflow.errors.value),
    timestamp     = takeLast(timestamp),
    timeframe     = takeLast(bizflow.query_timeframe.hours),
    frequency     = takeLast(bizflow.query_frequency.hours),
    bizflowName   = takeLast(bizflowName),
    analysisLabel = takeLast(bizflow.analysis.label)
  }, by: { bizflowId }
```

**Notes:**
- Returns one row per CIF; `fulfillment` and `errors` are the latest sampled KPI values
- `analysisLabel` describes what `fulfillment` means for that flow (e.g., "Successful logins")
- `timeframe` and `frequency` reflect the Business Flow's own configured query window
- For a single CIF use `| filter bizflow.id == "<id>"`; for multiple CIFs extend with additional `or bizflow.id == "<id>"` clauses
- If data is missing, check the Business Flow monitoring frequency and evaluation timeframe (see [FAQ](#faq))

---

## Common Workflows

### Check the Compliance Score

1. Confirm the user is asking about DORA — currently the only supported framework
2. Explain the current tier using the score tier table in [Core Concepts](#dynatrace-score-compliance-snapshot)
3. Remind the user the score is an operational indicator, not a legal compliance determination
4. If the score is degraded, identify which signal types are contributing (incidents, security detection findings, vulnerabilities, misconfigurations)
5. Guide remediation using [Improving the Compliance Score](#improving-the-compliance-score)

### Investigate an Incident

1. Confirm whether the user is asking about a **classified** incident (has a `compliance.incident` bizevent) or an **unclassified/potential major** problem
2. For classified incidents: run the classified incidents DQL query, filter by `problem.event.id` if a specific incident is referenced
3. For unclassified/potential major: run the unclassified problems query scoped to the relevant CIF IDs
4. Surface the materiality threshold breach status: `compliance.incident.duration_criteria`, `compliance.incident.economic_impact_criteria`, `compliance.cifs_impacted.*`
5. Do not classify an incident on behalf of the user — classification is a manual step performed in the Compliance Assistant app

### Review CIF Health

1. Identify the CIF's Business Flow ID from the DORA framework settings in Compliance Assistant
2. Run the CIF health query with the relevant `bizflow.id` values
3. Surface `fulfillment`, `errors`, and `analysisLabel` per CIF
4. If data is missing or stale, check the Business Flow monitoring frequency — see [FAQ](#faq)

---

## Improving the Compliance Score

The Dynatrace score reflects current ICT risk posture in real time. To improve it:

1. **Address incidents promptly** — resolve potential major incidents and unclassified problems affecting CIFs
2. **Remediate security detection findings and vulnerabilities** — see [Gain insights](https://docs.dynatrace.com/docs/secure/threat-observability) and [How do I fix detected vulnerabilities?](https://docs.dynatrace.com/docs/secure/application-security/vulnerability-analytics)
3. **Fix ICT asset misconfigurations** — see [Stay compliant with Security Posture Management](https://docs.dynatrace.com/docs/secure/application-security/spm)
4. **Ensure monitoring coverage** — confirm that real-time protection and monitoring are enabled across all CIFs

> Improving the score reduces observable ICT risk. It does **not** constitute formal compliance or legal readiness.

---

## FAQ

### How often are CIF insights updated in Compliance Assistant?

CIF KPI insights (fulfillment and errors) are updated based on the configured generation frequency of KPI monitoring in Business Flow. The evaluation timeframe is also defined per business flow configuration.

To ensure reliable KPI evaluation and avoid missing data from long-running processes, set the evaluation timeframe to at least 3–4× the process's average duration. For example, if a CIF's average duration is 5 minutes, set the evaluation window to at least 15–20 minutes.

### Why are configured CIFs not updating?

If you have recently edited or added business processes configured as entities and selected them as CIFs in Compliance Assistant, it may take up to the maximum defined monitoring frequency for those business processes to be updated. Adjust the monitoring frequency in the business flow configuration to reduce the delay.

---

## References

- [Compliance Assistant documentation](https://docs.dynatrace.com/docs/observe/business-observability/compliance-assistant)
- [Business Flow](https://docs.dynatrace.com/docs/observe/business-observability/business-flow)
- [Security Posture Management](https://docs.dynatrace.com/docs/secure/application-security/spm)
- [Runtime Vulnerability Analytics](https://docs.dynatrace.com/docs/secure/application-security/vulnerability-analytics)
- [Threat Observability concepts](https://docs.dynatrace.com/docs/secure/threat-observability/concepts)
- [Compliance assistant incident event — Semantic Dictionary](https://docs.dynatrace.com/docs/semantic-dictionary/model/business-analytics#compliance-assistant-incident-event)
- [Dynatrace Hub — Compliance Assistant](https://www.dynatrace.com/hub/detail/compliance-assistant/)
