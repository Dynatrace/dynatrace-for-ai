# Dynatrace Vulnerabilities — Advanced Workflows

Additional guidance for Dynatrace-native vulnerabilities:
- extended best practices
- AI-workload findings (`VULNERABILITY_FINDING`) scoped to GenAI services

## Contents

- [Best Practices](#best-practices)
- [AI-workload vulnerabilities (Dynatrace findings)](#ai-workload-vulnerabilities-dynatrace-findings)
- [Prerequisite: confirm GenAI entities exist](#prerequisite-confirm-genai-entities-exist)
- [DT findings base](#dt-findings-base)
- [UC-AI1 - Which AI services/processes have vulnerabilities](#uc-ai1---which-ai-servicesprocesses-have-vulnerabilities)
- [UC-AI2 - New AI-workload vulnerabilities this window](#uc-ai2---new-ai-workload-vulnerabilities-this-window)
- [Coverage](#coverage)

---

## Best Practices

1. **Always use the three-event-type union for RVA snapshot queries** (`vulnerabilities-dynatrace.md`) — state reports alone miss transitions. AI-workload queries (UC-AI1 / UC-AI2) use `VULNERABILITY_FINDING` — the three-event union does **not** apply to them.
2. **Dedup on the composite key** `{vulnerability.display_id, affected_entity.id}` - deduping on either field alone corrupts aggregates.
3. **Derive vulnerability-level status in Step 3** - never filter `vulnerability.resolution.status == "OPEN"` before the `fieldsAdd` when answering a vulnerability-level question; the pre-derived field is per-entity. Filtering pre-Stage-3 is fine when the question is genuinely per-entity.
4. **Use shortened runtime-assessment names in Step 3+** - `vulnerability.exposure.status`, `vulnerability.exploit.status`, `vulnerability.vulnerable_function.status`, `vulnerability.data_assets.status`.
5. **Prefer Dynatrace runtime assessments for triage** - `vulnerability.risk.level` is contextual and `vulnerability.risk.score` never exceeds `vulnerability.cvss.base_score`.
6. **`vulnerability.stack` is `CODE` / `CODE_LIBRARY` / `SOFTWARE` / `CONTAINER_ORCHESTRATION`** - not `THIRD_PARTY` / `FIRST_PARTY` / `CODE_LEVEL`.
7. **CLV (`stack=="CODE"`) always scores 10.0** - use `vulnerability.code_location.name` to drill to source.
8. **Exposure precedence is `PUBLIC_NETWORK > NOT_AVAILABLE > NOT_DETECTED`**. Query raw `vulnerability.davis_assessment.exposure_status` for adjacent-network analysis.
9. **`NOT_AVAILABLE` outranks `NOT_DETECTED` / `NOT_IN_USE`** in runtime-assessment precedence.
10. **Keep the summarize block lean** - include only fields required by the user question.
11. **`affected_entity.vulnerable_component.name` is singular per entity**, but collected into plural arrays at vulnerability level.
12. **`vulnerability.parent.*` is deprecated** - do not use it. Use non-deprecated fields and derivations from Step 3.
13. **Mute metadata is per-entity** - do not collapse `mute.reason`, `mute.user`, `mute.comment`, `mute.change_date` to vulnerability-level.
14. **Simple count questions use one summarize with `countIf`** - avoid adding unrequested grouping dimensions.

---

## AI-workload vulnerabilities (Dynatrace findings)

The base RVA pipeline in `vulnerabilities-dynatrace.md` covers state reports.
These workflows use Dynatrace-generated `VULNERABILITY_FINDING` rows scoped to
AI/GenAI workloads.

**Query conventions:**

- **Window `from:now()-30m`** to capture the latest scan cycle.
- **DT-generated findings re-emit every scan run (~15 min)** for all scanned
  processes, hosts, and K8s nodes. Treat the 30m window as the current-cycle
  snapshot and **dedup on `finding.id`**.
- **DT provenance**: `event.provider == "Dynatrace" OR product.vendor == "Dynatrace"`.
- **AI scoping path**: `GENAI_SERVICE -> SERVICE -> PROCESS` from
  `dt-sec-contextualization/references/identity-mapping.md` (Path 4 in Mapping Primitive section).
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

"New" must be modeled as a prior-window anti-join, not only a `finding.time.created` filter.

```dql-template
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_FINDING"
| filter product.feature == "Library Vulnerability Analytics"
| filter in(dt.security.risk.level, {"CRITICAL","HIGH"})
| filter event.provider == "Dynatrace" OR product.vendor == "Dynatrace"
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

## Coverage

For AI-process coverage, use `GENAI_SERVICE -> PROCESS` as denominator and left-lookup
`VULNERABILITY_SCAN`, then report covered vs uncovered entities.

Cross-reference: `dt-sec-contextualization/references/identity-mapping.md` (Path 4 in Mapping Primitive section).
