# Dynatrace Vulnerabilities — Advanced Workflows

Additional guidance for Dynatrace-native vulnerabilities:
- extended best practices
- AI-workload findings (`VULNERABILITY_FINDING`) scoped to GenAI services

## Contents

- [Best Practices](#best-practices)
- [AI-workload vulnerabilities (Dynatrace findings)](#ai-workload-vulnerabilities-dynatrace-findings)
- [DT findings base](#dt-findings-base)
- [UC-AI1 - Which AI services/processes have vulnerabilities](#uc-ai1---which-ai-servicesprocesses-have-vulnerabilities)
- [UC-AI2 - New AI-workload vulnerabilities this window](#uc-ai2---new-ai-workload-vulnerabilities-this-window)
- [Coverage](#coverage)

---

## Best Practices

1. **Always use the three-event-type union** - state reports alone miss transitions that happened since the last snapshot.
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

## DT findings base

```dql
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_FINDING"
     AND (event.provider == "Dynatrace" OR product.vendor == "Dynatrace")
     AND dt.smartscape_source.type == "PROCESS"
| dedup finding.id, sort:{timestamp desc}
```

## UC-AI1 - Which AI services/processes have vulnerabilities

```dql
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_FINDING"
     AND (event.provider == "Dynatrace" OR product.vendor == "Dynatrace")
     AND dt.smartscape_source.type == "PROCESS"
| dedup finding.id, sort:{timestamp desc}
| join [
    smartscapeNodes "GENAI_SERVICE", from:now()-2h
    | traverse edgeTypes: {instance_of}, targetTypes: {SERVICE}
    | traverse edgeTypes: {runs_on},     targetTypes: {PROCESS}
  | filter toTimestamp(lifetime[end]) > now()-30m
    | fields dt.smartscape.process = id
    | dedup dt.smartscape.process
  ], on:{dt.smartscape.process}, kind: inner
| summarize {
    findings = count(),
    vulnerabilities = countDistinctExact(vulnerability.id),
    affected_processes = countDistinctExact(dt.smartscape.process)
  }
```

Use a wider Smartscape history window (for example `from:now()-2h`) than the finding
window so topology edges are available, then filter processes alive during the
finding window with `toTimestamp(lifetime[end]) > now()-30m`.

For severity split, use `dt.security.risk.level`. Use CVSS bands only when explicitly asked.

## UC-AI2 - New AI-workload vulnerabilities this window

"New" must be modeled as a prior-window anti-join, not only a `finding.time.created` filter.

```dql-template
fetch security.events, from:now()-30m
| filter event.type == "VULNERABILITY_FINDING"
     AND (event.provider == "Dynatrace" OR product.vendor == "Dynatrace")
     AND in(dt.security.risk.level, {"CRITICAL","HIGH"})
     AND isNotNull(finding.id) AND isNotNull(vulnerability.id) AND isNotNull(dt.smartscape.process)
| dedup finding.id, sort:{timestamp desc}
| fields finding.id, vulnerability.id, dt.smartscape.process, dt.security.risk.level, finding.time.created
| join [
    smartscapeEdges "*", from:-2h
    | filter source_type == "GENAI_SERVICE"
    | fields genai_service.id = source_id, service.id = target_id
    | join [
        smartscapeEdges "*", from:-2h
        | filter source_type == "SERVICE" AND target_type == "PROCESS"
        | fields process.id = target_id, service.id = source_id
      ], on:{service.id}, fields:{process.id}
  ], on:{left[dt.smartscape.process] == right[process.id]}, kind:inner, fields:{genai_service.id}
| dedup {genai_service.id, vulnerability.id}
| join kind:outer, on:{genai_service.id, vulnerability.id}, [
    fetch security.events, from:-90m, to:-60m
    | filter event.type == "VULNERABILITY_FINDING"
         AND (event.provider == "Dynatrace" OR product.vendor == "Dynatrace")
         AND in(dt.security.risk.level, {"CRITICAL","HIGH"})
         AND isNotNull(finding.id) AND isNotNull(vulnerability.id) AND isNotNull(dt.smartscape.process)
    | dedup finding.id, sort:{timestamp desc}
    | fields vulnerability.id, dt.smartscape.process
    | join [
        smartscapeEdges "*", from:-2h
        | filter source_type == "GENAI_SERVICE"
        | fields genai_service.id = source_id, service.id = target_id
        | join [
            smartscapeEdges "*", from:-2h
            | filter source_type == "SERVICE" AND target_type == "PROCESS"
            | fields process.id = target_id, service.id = source_id
          ], on:{service.id}, fields:{process.id}
      ], on:{left[dt.smartscape.process] == right[process.id]}, kind:inner, fields:{genai_service.id}
    | dedup {genai_service.id, vulnerability.id}
    | fields genai_service.id, vulnerability.id
  ]
| filter isNull(right.genai_service.id)
| join [
    smartscapeNodes "GENAI_SERVICE", from:-2h
    | fields genai_service.id = id, genai_service.name = name
  ], on:{genai_service.id}, kind:inner, fields:{genai_service.name}
| summarize {
    new_pairs = count(),
    vulnerability.ids = collectDistinct(vulnerability.id),
    finding.ids = collectDistinct(finding.id),
    first_seen = takeMin(toTimestamp(finding.time.created))
  }, by:{genai_service.id, genai_service.name}
| fieldsAdd vulnerability.ids = arraySort(vulnerability.ids), finding.ids = arraySort(finding.ids)
| sort new_pairs desc, genai_service.name asc
```

## Coverage

For AI-process coverage, use `GENAI_SERVICE -> PROCESS` as denominator and left-lookup
`VULNERABILITY_SCAN`, then report covered vs uncovered entities.

Cross-reference: `dt-sec-contextualization/references/identity-mapping.md` (Path 4 in Mapping Primitive section).
