# Dynatrace AI-Workload Vulnerabilities

Scope: this file reads Dynatrace `VULNERABILITY_FINDING` rows for AI/GenAI workloads and resolves them to GenAI services through Smartscape (`GENAI_SERVICE -> SERVICE -> PROCESS`).
General RVA rules, counts and rankings (dedup key, Step 3 derivation, exposure precedence) are in `dt-sec-insights` `vulnerabilities-dynatrace.md` § Best Practices.
To scope any other finding stream to AI services, see [identity-mapping.md § Path 3](identity-mapping.md#path-3--ai-service--runtime-process-genai_service--service--process) (forward scope, reverse attribution).

> **Do not apply the three-event RVA union here.** UC-AI1 / UC-AI2 use
> `VULNERABILITY_FINDING`; the `VULNERABILITY_STATE_REPORT_EVENT` /
> `STATUS_CHANGE` / `TRACKING_LINK_CHANGE` union from `dt-sec-insights`
> `vulnerabilities-dynatrace.md` does not apply to them. For AI-process **coverage**
> (covered vs. uncovered), use
> [runtime-coverage.md § AI-Process Coverage](runtime-coverage.md#ai-process-coverage).

## Contents

- [AI-workload vulnerabilities (Dynatrace findings)](#ai-workload-vulnerabilities-dynatrace-findings)
- [Prerequisite: confirm GenAI entities exist](#prerequisite-confirm-genai-entities-exist)
- [DT findings base](#dt-findings-base)
- [UC-AI1 - Which AI services/processes have vulnerabilities](#uc-ai1---which-ai-servicesprocesses-have-vulnerabilities)
- [UC-AI2 - New AI-workload vulnerabilities this window](#uc-ai2---new-ai-workload-vulnerabilities-this-window)

---

## AI-workload vulnerabilities (Dynatrace findings)

The base RVA pipeline in `dt-sec-insights` `vulnerabilities-dynatrace.md` covers state reports.
These workflows use Dynatrace-generated `VULNERABILITY_FINDING` rows scoped to
AI/GenAI workloads.

**Query conventions:**

- **Window `from:now()-30m`** to capture the latest scan cycle.
- **DT-generated findings re-emit every scan run (~15 min)** for all scanned
  processes, hosts, and K8s nodes. Treat the 30m window as the current-cycle
  snapshot and **dedup on `finding.id`**.
- **DT provenance**: `event.provider == "Dynatrace" OR product.vendor == "Dynatrace"`.
- **AI scoping path**: `GENAI_SERVICE -> SERVICE -> PROCESS` from
  [identity-mapping.md § Path 3](identity-mapping.md#path-3--ai-service--runtime-process-genai_service--service--process).
- **New AI-workload vulnerabilities require a prior-window anti-join** on the
  scoped identity (for example `{genai_service.id, vulnerability.id}`); do not
  use `finding.time.created` alone, because every scan cycle re-reports the
  current finding set.
- **Library-vulnerability scope**: UC-AI1 and UC-AI2 are scoped to
  `product.feature == "Library Vulnerability Analytics"` findings. Code-level
  vulnerabilities on AI workloads are a separate use case, not yet templated here.

## Prerequisite: confirm GenAI entities exist

Before running any AI-workload vulnerability query, probe for `GENAI_SERVICE` entities
in Smartscape. The UC-AI1 and UC-AI2 templates use an **inner join** on those entities,
so they return zero rows whenever the topology is absent — which is indistinguishable
from "no vulnerabilities" without this check.

```dql
smartscapeNodes "GENAI_SERVICE", from:now()-2h
| fields id, name
| limit 10
```

**Empty-state branches — never skip this check:**

| Result | Meaning | Required response |
|---|---|---|
| Zero rows | No GenAI services are registered in Smartscape — Dynatrace is not monitoring any AI/GenAI workload in this environment | State: "No GenAI-monitored services are registered in Smartscape, so AI-workload vulnerabilities cannot be determined. Enable Dynatrace AI Observability to start monitoring GenAI workloads." **Stop here. Do not run any further queries or alternative approaches.** |
| One or more rows | AI workloads are monitored | Run UC-AI1/UC-AI2 normally. If the findings join then returns zero, report: "GenAI services are registered in Smartscape, but no vulnerabilities were detected on them in the current window." |

**Prohibited fallbacks — do not substitute any keyword-based or heuristic approach.** When
the `GENAI_SERVICE` probe returns zero rows, the answer is "cannot be determined" — full stop.
None of the following are valid substitutes and all must be rejected outright:

- Filtering `affected_entity.name`, `object.name`, `k8s.workload.name`, `k8s.namespace.name`,
  or any name field for AI-related substrings (`"ai"`, `"llm"`, `"genai"`, `"model"`,
  `"inference"`, `"copilot"`, `"ml"`, etc.)
- Matching vulnerable component names against known ML/AI library lists (`torch`,
  `tensorflow`, `keras`, `transformers`, `langchain`, `openai`, `anthropic`, etc.)
- Filtering process names, image names, or labels for AI-related patterns
- Any other name-based, tag-based, or keyword-based proxy for AI-workload scoping

These approaches produce false positives (e.g. `rsva` contains `"ai"`; any service
named `"email"` contains `"ml"`) and false negatives (AI workloads with neutral names).
AI-workload scope **must** flow exclusively through the `GENAI_SERVICE` Smartscape
topology. If that topology is empty, there are no monitored AI workloads — say so and stop.

---

## DT findings base

```dql
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_FINDING"
     AND (event.provider == "Dynatrace" OR product.vendor == "Dynatrace")
     AND dt.smartscape_source.type == "PROCESS"
| dedup {finding.id}, sort:{timestamp desc}
```

## UC-AI1 - Which AI services/processes have vulnerabilities

Use a **lazy two-step pattern** to minimize DQL executions: always run Step 1; run Step 2 only when the user explicitly asks for a per-service breakdown.

### Step 1 — Always run: overall totals + service list (one query)

Resolve names before the `summarize` so both the severity totals and the list of affected service names are returned in a single row.

```dql
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_FINDING"
     AND (event.provider == "Dynatrace" OR product.vendor == "Dynatrace")
     AND dt.smartscape_source.type == "PROCESS"
     AND product.feature == "Library Vulnerability Analytics"
     AND isNotNull(finding.id) AND isNotNull(vulnerability.id)
     AND isNotNull(dt.smartscape.process)
| dedup {finding.id}, sort:{timestamp desc}
| join [
    smartscapeEdges "*", from:-2h
    | filter source_type=="GENAI_SERVICE"
    | fields genai_service.id=source_id, service.id=target_id
    | join [
        smartscapeEdges "*", from:-2h
        | filter source_type=="SERVICE"
        | filter target_type=="PROCESS"
        | fields process.id=target_id, service.id=source_id
      ], on:{service.id}, fields:{process.id}
  ], on:{left[dt.smartscape.process]==right[process.id]}, kind:inner, fields:{genai_service.id}
| lookup [ smartscapeNodes "GENAI_SERVICE", from:-2h ],
    sourceField:genai_service.id, lookupField:id, fields:{genai_service.name=name}
| summarize {
    total_vulnerabilities   = countDistinctExact(vulnerability.id),
    critical                = countDistinctExact(if(dt.security.risk.level == "CRITICAL", vulnerability.id, else: null)),
    high                    = countDistinctExact(if(dt.security.risk.level == "HIGH",     vulnerability.id, else: null)),
    medium                  = countDistinctExact(if(dt.security.risk.level == "MEDIUM",   vulnerability.id, else: null)),
    low                     = countDistinctExact(if(dt.security.risk.level == "LOW",      vulnerability.id, else: null)),
    affected_genai_services = countDistinctExact(genai_service.id),
    affected_processes      = countDistinctExact(dt.smartscape.process),
    service_names           = collectDistinct(genai_service.name)
  }
| fieldsAdd service_names = arraySort(service_names)
```

**Answer format (Step 1):**

1. Summary sentence: "X unique vulnerabilities across N GenAI services (C critical / H high / M medium / L low), spanning P processes."
2. Service list: "Affected services: [values from `service_names`]."

### Step 2 — On demand only: top 10 services with per-severity breakdown

Run this query only when the user explicitly asks for a per-service breakdown or ranking (e.g. "which services are most affected?", "show me the top services", "break it down by service").

```dql
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_FINDING"
     AND (event.provider == "Dynatrace" OR product.vendor == "Dynatrace")
     AND dt.smartscape_source.type == "PROCESS"
     AND product.feature == "Library Vulnerability Analytics"
     AND isNotNull(finding.id) AND isNotNull(vulnerability.id)
     AND isNotNull(dt.smartscape.process)
| dedup {finding.id}, sort:{timestamp desc}
| join [
    smartscapeEdges "*", from:-2h
    | filter source_type=="GENAI_SERVICE"
    | fields genai_service.id=source_id, service.id=target_id
    | join [
        smartscapeEdges "*", from:-2h
        | filter source_type=="SERVICE"
        | filter target_type=="PROCESS"
        | fields process.id=target_id, service.id=source_id
      ], on:{service.id}, fields:{process.id}
  ], on:{left[dt.smartscape.process]==right[process.id]}, kind:inner, fields:{genai_service.id}
| summarize {
    total_vulnerabilities = countDistinctExact(vulnerability.id),
    critical              = countDistinctExact(if(dt.security.risk.level == "CRITICAL", vulnerability.id, else: null)),
    high                  = countDistinctExact(if(dt.security.risk.level == "HIGH",     vulnerability.id, else: null)),
    medium                = countDistinctExact(if(dt.security.risk.level == "MEDIUM",   vulnerability.id, else: null)),
    low                   = countDistinctExact(if(dt.security.risk.level == "LOW",      vulnerability.id, else: null)),
    affected_processes    = countDistinctExact(dt.smartscape.process)
  }, by:{genai_service.id}
| lookup [ smartscapeNodes "GENAI_SERVICE", from:-2h ],
    sourceField:genai_service.id, lookupField:id, fields:{genai_service.name=name}
| sort critical desc, high desc, medium desc, low desc
| limit 10
```

**Answer format (Step 2):** table ranked highest-critical-first: `genai_service.name | critical | high | medium | low | total_vulnerabilities | affected_processes`.

Use `from:-2h` on `smartscapeEdges` so topology edges are available for the 30m finding window. Severity counts are **distinct CVEs** (`vulnerability.id`) per risk level — consistent with `total_vulnerabilities`. Use CVSS bands only when explicitly asked.

## UC-AI2 - New AI-workload vulnerabilities this window

"New" must be modeled as a prior-window anti-join, not only a `finding.time.created` filter. The block has no placeholders — the windows are fixed (current `30m` vs prior `-90m` to `-60m`) and it runs as-is. Zero rows means no new CRITICAL or HIGH Library Vulnerability Analytics finding appeared on a GenAI
service that resolves through the topology edges. It does not cover MEDIUM or LOW findings, other vulnerability
types, or processes whose GenAI topology does not resolve (the inner joins drop them); state that scope when
reporting an empty result and do not say "nothing new" without it.

```dql
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_FINDING"
| filter product.feature == "Library Vulnerability Analytics"
| filter in(dt.security.risk.level, {"CRITICAL","HIGH"})
| filter event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
| filter dt.smartscape_source.type == "PROCESS"
| filter isNotNull(finding.id) AND isNotNull(object.id) AND isNotNull(vulnerability.id) AND isNotNull(dt.smartscape.process)
| dedup {finding.id}, sort:{timestamp desc}
// Resolve genai_service per process BEFORE the anti-join
| join [
  smartscapeEdges "*", from:-2h
  | filter source_type=="GENAI_SERVICE"
  | fields genai_service.id=source_id, service.id=target_id
  | join [
    smartscapeEdges "*", from:-2h
    | filter source_type=="SERVICE"
    | filter target_type=="PROCESS"
    | fields process.id=target_id, service.id=source_id
  ], on:{service.id}, fields:{process.id}
], on:{left[dt.smartscape.process]==right[process.id]}, kind:inner, fields:{genai_service.id}
// Anti-join at {genai_service.id, vulnerability.id} — suppresses any CVE already known for this service
| join kind:outer, on:{genai_service.id, vulnerability.id}, [
    fetch security.events, from:-90m, to:-60m
    | filter event.type == "VULNERABILITY_FINDING"
    | filter product.feature == "Library Vulnerability Analytics"
    | filter in(dt.security.risk.level, {"CRITICAL","HIGH"})
    | filter event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
    | filter dt.smartscape_source.type == "PROCESS"
    | filter isNotNull(finding.id) AND isNotNull(object.id) AND isNotNull(vulnerability.id) AND isNotNull(dt.smartscape.process)
    | dedup {finding.id}, sort:{timestamp desc}
    | join [
      smartscapeEdges "*", from:-2h
      | filter source_type=="GENAI_SERVICE"
      | fields genai_service.id=source_id, service.id=target_id
      | join [
        smartscapeEdges "*", from:-2h
        | filter source_type=="SERVICE"
        | filter target_type=="PROCESS"
        | fields process.id=target_id, service.id=source_id
      ], on:{service.id}, fields:{process.id}
    ], on:{left[dt.smartscape.process]==right[process.id]}, kind:inner, fields:{genai_service.id}
    | dedup {genai_service.id, vulnerability.id}
    | fields genai_service.id, vulnerability.id
]
| filter isNull(right.genai_service.id)
// Summarize across all processes per genai_service
| summarize {
    finding.ids            = collectDistinct(finding.id),
    object.ids             = arrayRemoveNulls(collectDistinct(dt.smartscape_source.id)),
    vulnerability.ids      = collectDistinct(vulnerability.id),
    dt.security.risk.score = toDouble(takeMax(dt.security.risk.score)),
    vulnerable_components  = arrayRemoveNulls(collectDistinct(software_component.purl)),
    first_seen             = takeMin(toTimestamp(finding.time.created))
  }, by:{genai_service.id}
| fieldsAdd dt.security.risk.level = if(dt.security.risk.score >= 9, "CRITICAL",
                                    else:if(dt.security.risk.score >= 7, "HIGH",
                                    else:if(dt.security.risk.score >= 4, "MEDIUM",
                                    else:if(dt.security.risk.score >= 0.1, "LOW", else:"NONE"))))
| lookup [
  smartscapeNodes "GENAI_SERVICE", from:-2h
], sourceField:genai_service.id, lookupField:id, fields:{genai_service.name=name}
| fieldsAdd finding.ids=arraySort(finding.ids), vulnerability.ids=arraySort(vulnerability.ids), object.ids=arraySort(object.ids)
| sort genai_service.name asc
```
