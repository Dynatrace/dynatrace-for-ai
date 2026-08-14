# Common Mistakes & Troubleshooting

Detailed companion to the **Common Mistakes** and **Best Practices** sections in
[SKILL.md](../SKILL.md). Surface this reference when a query is producing
unexpected results or when the user reports counts that disagree with the
Vulnerabilities / Threats & Exploits / SPM apps.

---

## Mistakes to Avoid

1. **Querying `VULNERABILITY_STATE_REPORT_EVENT` alone** → use the three-event-type union (`STATE_REPORT`, `STATUS_CHANGE`, `TRACKING_LINK_CHANGE`).
2. **Deduping on `vulnerability.display_id` alone** → use the composite key `{vulnerability.display_id, affected_entity.id}`, else per-entity context collapses.
3. **Skipping `event.level == "ENTITY"`** on RVA queries → non-entity rows skew aggregations.
4. **`dt.system.bucket` filters** → never filter by bucket; security events may live in any bucket.
5. **`vulnerability.parent.*` (deprecated)** → derive vuln-level values from per-entity arrays: verdicts via `collectDistinct()` + `in()`, scalars via `takeMax/takeFirst`.
6. **Wrong risk field / raw CVSS for triage** → `dt.security.risk.*` on `*_FINDING` events; `vulnerability.risk.*` on RVA state-reports (which lack `dt.security.risk.*`). Both beat `vulnerability.cvss.base_score`.
7. **Counting `NOT_RELEVANT` compliance** → exclude it from pass-rate denominators.
8. **Widening the snapshot fetch window** → `from:now()-30m` (RVA) and `from:now()-1h` (SPM) are snapshot windows, not history — widening them returns ~50× more duplicate state rows, not older or newer state. The only valid reason to widen beyond 30m on RVA events is a **pure change-event query** (`VULNERABILITY_STATUS_CHANGE_EVENT` / `VULNERABILITY_TRACKING_LINK_CHANGE_EVENT` only, no `STATE_REPORT`) where the user asks what changed over a period; in that case, match the window to the user's time horizon and omit the snapshot dedup. For lifecycle metrics (new in 24h, resolved in 7d), keep 30m and apply a **post-derive filter** on `resolution.change_date` after Stage 3. For trends, use `makeTimeseries`.
9. **`bin()` for trend/chart questions** → use `makeTimeseries interval:<N>` (charts need a `timeseries`-typed column); `bin()` is only for tabular bucketed counts. [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md#dt-rva-time-series-trends-7-days-3h-buckets)
10. **Filtering `vulnerability.resolution.status == "OPEN"` pre-Stage-3** → the raw field is per-entity; filter only after the Stage-3 `fieldsAdd` derives the vuln-level verdict.
11. **`vulnerability.first_seen` (null on RVA pipeline — do not use)** → for "newly OPEN" use `toTimestamp(vulnerability.resolution.change_date) > now()-<window>`; for "how long open" aggregate `open_since=toTimestamp(takeMin(if(vulnerability.resolution.status=="OPEN", vulnerability.resolution.change_date, else: null)))` in Step 3, then `fieldsAdd open_duration = now() - open_since` (cast once in the summarize; `change_date` is an epoch-nanoseconds value). `first_seen` is commented out of `entity.state` (0/2124 populated). A resolution-time proxy (MTTR) **is** computable from `resolution.change_date` without `first_seen` — it equals true detection-to-resolution only for vulns that never reopened, counts auto-resolutions, and is bounded by the change-event fetch window; treat it as time-to-resolution-by-any-cause, not patch velocity. See [vulnerabilities-dynatrace.md § Resolution time (MTTR proxy)](vulnerabilities-dynatrace.md#resolution-time-mttr-proxy--openresolved-per-affected-object).
12. **Reading external compliance via `compliance.rule.*`** (null for external) → use `compliance.standards` (expand) / `compliance.policy` / `compliance.control`, plus `finding.title`/`finding.type`.
13. **`event.provider == "Dynatrace"` for compliance** → SPM uses `product.vendor == "Dynatrace"`; RVA uses `event.provider`. Don't mix.
14. **Inventing fields** → inspect a sample row, or [data-model.md](data-model.md), first.
15. **Wrong `vulnerability.stack` values** → enum is `CODE / CODE_LIBRARY / SOFTWARE / CONTAINER_ORCHESTRATION` (not `THIRD_PARTY/FIRST_PARTY/CODE_LEVEL`). CLV = `CODE`; "third-party" = `in(stack, array("CODE_LIBRARY","SOFTWARE"))`.
16. **Filtering CLV by runtime assessment** → CLV always scores 10.0 and skips assessment modifiers; scope with `vulnerability.stack == "CODE"`, drill via `vulnerability.code_location.name`.
17. **Treating `ADJACENT_NETWORK` as public exposure** → the Stage-3 derivation intentionally doesn't promote it; for adjacent-network questions filter the raw `vulnerability.davis_assessment.exposure_status`.
18. **Treating `NOT_AVAILABLE` as harmless** → it means "couldn't tell" (ranked above `NOT_DETECTED`/`NOT_IN_USE`); surface it. `assessment_mode` (`FULL`/`REDUCED`/`NOT_AVAILABLE`) explains partial coverage.
19. **Collapsing mute metadata to vuln level** → `mute.{reason,user,comment,change_date}` are per-entity; keep the per-entity row for the mute audit.
20. **Assuming auto-resolution takes days** → third-party resolves after the component is absent >2h; CLV resolves after a process restart + clean re-analysis.
21. **Querying KSPM for AWS/Azure/GCP** → KSPM is K8s-only; route cloud/host compliance to CSPM/VSPM or external ([all-security-events.md](all-security-events.md)).
22. **Asking KSPM for PCI/ISO/HIPAA/GDPR** → KSPM emits only `CIS`/`DORA`/`NIST`/`DISA STIG`; others arrive via external. STIG's `short_name` is the full `"DISA STIG"` — use `contains(lower(...),"stig")`, not `== "STIG"`.
23. **`compliance.rule.severity.level == "NONE"/"NOT_AVAILABLE"`** → KSPM severity is exactly `CRITICAL/HIGH/MEDIUM/LOW`.
24. **Counting MANUAL as PASSED (or ignoring it)** → MANUAL is in the denominator only, never the numerator; surface as a separate triage queue.
25. **Confusing the two object-type fields (KSPM)** → `object.type` = uppercase DT entity type; `compliance.result.object.type` = analyzer lowercase code (`k8scluster`, …). On external rows `object.type` is the vendor value as-is (e.g. `AwsEc2Instance`) — match it directly.
26. **Inventing `compliance.mute.*` / `compliance.tracking_link.*`** → neither exists; compliance has no mute/waiver/tracking namespace. Explain the limitation rather than guessing fields.
27. **`product.vendor == "Dynatrace"` is shared (RVA/RAP/SPM)** → pin `product.name == "Security Posture Management"` for KSPM-only scoping.
28. **Confusing the two RAP filter axes** → both `event.provider == "OneAgent"` and `product.name == "Runtime Application Protection"` are populated; use the latter (canonical), don't OR/AND them.
29. **`attack.type` / `attack.vector` (not in SD)** → use `finding.type` (vendor-original free-form string, not a normalized enum). Filter with a substring match: `contains(lower(finding.type), "sql")`. Values are display strings like `SQL injection`, `CMD injection` — not underscore enums like `SQL_INJECTION`.
30. **Auto-scoping cross-provider questions to RAP** → attacker-IP/campaign/attack-type analytics are SD-canonical across providers; default to `event.type == "DETECTION_FINDING"` and group by `object.id` (not `dt.entity.process_group`, null for external). Add a provider/RAP filter only when asked.
31. **Expecting MITRE tags on RAP** → only Automated Detections populate `threat.attack.*`; for RAP, map `finding.type` → technique manually.
32. **Inventing `detection.mute.*` / `detection.dismiss.*`** → detections aren't lifecycle-tracked in events; suppression is UI/ingest-side.
33. **Confusing `DETECTION_FINDING` with `DETECTION_EXECUTION_SUMMARY`** → the summary is the per-rule-run audit; don't include it in finding counts.
34. **`event.outcome` as the RAP block signal** → use `finding.action` (`Blocked`/`Audited`/`Allowlisted`).
35. **Using `actor.ips` as-is** → it's `ipAddress[]`; `expand actor.ips` then `fieldsAdd ip = ip(actor.ips)`. `actor.ip`/`actor.location` don't exist; geo is `actor.geo.{country,city,continent}.name` (Experimental); reputation is app-side.
36. **`detection.mitre_ids` (not in SD)** → MITRE is `threat.attack.technique.ids` / a separate `threat.attack.subtechnique.ids` (dotted) / `threat.attack.tactic.ids`. Use `in("T1078", …)`; "parent + subs" = `in("T1110", technique.ids) OR iAny(startsWith(subtechnique.ids[], "T1110."))`.
37. **Filtering CVE arrays as scalars** → `vulnerability.references.cve` is an array; use `in("CVE-…", vulnerability.references.cve)` (or `expand`), not `==`.
38. **Inventing `vulnerability.cve.id` / `vulnerability.cve.ids`** → CVEs live in `vulnerability.references.cve`; use that field for RVA and external `VULNERABILITY_FINDING` correlation.
39. **Ranking hosts by `affected_entity.type == "HOST"`** → RVA attaches to process groups; host context is in `related_entities.hosts.{ids,names}` — expand those.
40. **Assuming one exact `event.provider` per provider** → the name may be in `event.provider` or `product.vendor`; match both with `contains(lower(...))` and discover first. [all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type)
41. **Treating RAP as only `DETECTION_FINDING`** → some tenants expose RAP under `SECURITY_EVENT`; use `in(event.type, {"DETECTION_FINDING","SECURITY_EVENT"})` with `product.name == "Runtime Application Protection"`.
42. **KSPM windows/tools for external compliance** → external is `COMPLIANCE_FINDING` over `24h+` with the external taxonomy; the 1h scan-join is KSPM-only.
43. **Passing two args to `countIf`** → one boolean only: `countIf(vulnerability.risk.level == "CRITICAL")`.
44. **Confusing `vulnerability.external_url` with `vulnerability.tracking_link.url`** → `external_url` is the provider reference (NVD/advisory), populated almost always; the user-attached remediation link is `tracking_link.url`. Same for `external_id` (provider id) vs `tracking_link.text`.
45. **Mixing record-level conditionals with aggregations in one `summarize`** → fails with `INVALID_MIX_OF_AGGREGATIONS_AND_OTHER_EXPRESSIONS`. Derive the conditional in a prior `fieldsAdd` (scalar), or use `takeAny()`. For host ranking, merge `affected_entity.id` into `related_entities.hosts.ids` then resolve via Smartscape. [vulnerabilities-entities.md § Most vulnerable hosts](vulnerabilities-entities.md#most-vulnerable-hosts--dt-rva)
46. **`event.status` for compliance status** → `event.status` is a generic event-lifecycle field (`Active`/`Closed`); it is null or wrong on `COMPLIANCE_FINDING` rows. Use `compliance.result.status.level` instead. See [compliance.md](compliance.md).
47. **`"PASS"` / `"FAIL"` enum values, or `!= "PASSED"` negation for failed count** → the canonical enum is `PASSED`, `FAILED`, `MANUAL`, `NOT_RELEVANT`. Count failures with an explicit `countIf(compliance.result.status.level == "FAILED")`; a negation (`!= "PASSED"`) wrongly folds `MANUAL` and `NOT_RELEVANT` into the failed count.
48. **`on: {left.scan.id == right.scan.id}` join syntax** → `left.`/`right.` prefixes are valid inside the join *body* (e.g. `isNull(right.object.id)`) but not inside the `on:` clause for same-named fields. Use the shorthand `on: {scan.id}` when the field name is identical on both sides.
49. **`compliance.rule.standard` (does not exist) / bare `compliance.rule.severity`** → `compliance.rule.standard` has no entry in the Semantic Dictionary — use `compliance.standard.short_name` (or `.name`) for the standard label. Bare `compliance.rule.severity` resolves to nothing; use `compliance.rule.severity.level` (values `CRITICAL` / `HIGH` / `MEDIUM` / `LOW`).
50. **Computing pass rate directly on raw per-`(rule, object)` rows** → raw rows mix multiple objects per rule; pass rate computed at this level over-counts or under-counts. Run the Step 2 per-rule status rollup first (`summarize … by: {compliance.rule.id}`), then derive `passRate` from the per-rule verdict counts. See [compliance.md § Step 2](compliance.md).
51. **Filtering by a vulnerability ID on only one field when the format is unknown** → `vulnerability.display_id` holds `S-XXXX`, `vulnerability.id` holds the internal numeric string (e.g. `7712027161588397174`), and `vulnerability.external_id` holds provider advisory IDs (e.g. `DTV-2026-GO-0001133`, NVD references). Searching only `display_id` silently returns zero rows for DTV/NVD advisories. Use the multi-field OR filter from [vulnerabilities-dynatrace.md § Step 2](vulnerabilities-dynatrace.md#step-2--optional-pre-aggregation-filter-insert-after-step-1-before-step-3).
52. **Using array indexing (`related_entities.hosts.names[0]` / `.ids[0]`) to extract entity names from RVA events** → array indexing grabs only the first element. For a simple list, project the whole array (`related_entities.hosts.names`) directly. For one-row-per-host fanout, use the named-alias expand form `expand related_host.id = related_entities.hosts.ids` + Smartscape lookup. Also: when `affected_entity.type == "HOST"` or `"KUBERNETES_NODE"`, the directly-affected entity is itself a host and may not appear in `related_entities.hosts.*` — always include `affected_entity.*` in the projection. See [vulnerabilities-dynatrace.md § Named entity list for a specific vulnerability](vulnerabilities-dynatrace.md#named-entity-list-for-a-specific-vulnerability).
53. **`iAny(related_entities.hosts.ids[] == "HOST-...")` — wrong DQL for array membership** → `iAny()` with array indexing is not the correct DQL membership operator. Use `in("HOST-...", related_entities.hosts.ids)` for a single value, or `in({"HOST-A","HOST-B"}, related_entities.hosts.ids)` for a set. Always pair with `OR affected_entity.id == "HOST-..."` (or `OR in(affected_entity.id, {...})`): HOST and KUBERNETES_NODE entities can be the directly-affected entity and will not appear in `related_entities.hosts.*` in that case.
54. **Answering *runtime-entity* coverage with a scan-event summary** → for hosts / processes / workloads / cloud resources, counting `VULNERABILITY_SCAN` events shows only the covered set — there is no denominator, so it cannot give a coverage percentage or reveal uncovered entities. Start from `smartscapeNodes` and `lookup` scan events **and** findings. [coverage.md § DT Runtime Coverage Analysis](coverage.md#dt-runtime-coverage-analysis-smartscapenodes). **Non-runtime** entities (container images, code artifacts) have no Smartscape population, so a distinct-object count from scan/finding events *is* the correct answer — there is no percentage. [coverage.md § Non-Runtime Entity Coverage](coverage.md#non-runtime-entity-coverage-images--artifacts)
55. **`finding.time.created` filter for "new this period and not in the prior period"** → that wording is a set comparison between two periods and requires the prior-period **anti-join** (outer join + `isNull(right.…)`). Providers re-report old findings and created timestamps are vendor-relative, so the created-time shortcut answers a different question. [common-patterns.md § 18](common-patterns.md#18-lifecycle--what-counts-as-new--resolved-per-event-family)
56. **`count()` after `expand` / `join` / `lookup` when the grain is not already one-per-identity** → if component or related-entity arrays are collected then expanded *without* a preceding one-row-per-vulnerability grain, post-`expand` rows duplicate each `(vulnerability, group-key)` pair and `count()` inflates rankings 3–50×. Use `countDistinctExact(vulnerability.display_id)` / `countDistinctExact(finding.id)`, or `dedup` on identity + group key before the `summarize`. (`count()` *is* correct when the pipeline already deduped to one row per vulnerability before the `expand` — e.g. the host/workload rankings in [vulnerabilities-entities.md § Resolving RVA entity names via Smartscape](vulnerabilities-entities.md#resolving-rva-entity-names-via-smartscape).)
57. **Grouping external findings by raw `k8s.namespace.name` / `host.name` / `object.name` / cloud resource IDs as "entity mapping"** → names are not unique and skip topology reconciliation. Use the Smartscape join recipes: 3-way match (K8s workloads), host-by-IP, direct `dt.smartscape_source.id` (cloud). `dt-sec-contextualization/references/entity-enrichment.md`
58. **Parsing or querying `compliance.rule.metadata_json`** → do not use this field; it is forbidden in this skill. Use `compliance.rule.id` (e.g. `CIS-2762`, `STIG-82824`, `DORA-67952`, `NIST-82827`) and `compliance.rule.title` for rule identity instead. The field exists in the data as a standard-specific JSON blob but must never be accessed.

59. **Using any keyword/name/library heuristic as an AI-workload proxy when no GENAI_SERVICE entities are found** → when `smartscapeNodes "GENAI_SERVICE"` returns zero rows, do not run any further queries. No substitute is valid: not entity-name substring matching (`"ai"`, `"llm"`, `"ml"`, `"genai"`, `"model"`, `"inference"`, `"copilot"`, etc.), not component-library matching (torch, tensorflow, langchain, openai, etc.), not K8s namespace/label patterns, not process-name filters. All of these produce false positives and false negatives. Zero GENAI_SERVICE rows means no monitored AI workloads — state that and stop. See [vulnerabilities-dynatrace-advanced.md § Prerequisite: confirm GenAI entities exist](vulnerabilities-dynatrace-advanced.md#prerequisite-confirm-genai-entities-exist).

---

## Best Practices

1. **Start with the canonical window** — RVA `from:now()-30m`, SPM
   `from:now()-1h`, detections / cross-provider `from:now()-2h` (widen only
   when the 2h detection query returns zero rows — see
   [detections.md § Widen-on-empty fallback](detections.md#widen-on-empty-fallback-retrieval-queries)).
   Widen for other event types only when the question explicitly demands history.
2. **Use shortened runtime-assessment status names in output** —
   `vulnerability.exposure.status`, `vulnerability.exploit.status`,
   `vulnerability.vulnerable_function.status`, `vulnerability.data_assets.status`
   — derived in Stage 3 from the raw `vulnerability.davis_assessment.*_status`
   fields.
3. **Use `dt.smartscape.*` for new Smartscape lookups** — `dt.entity.*` is
   deprecated for Smartscape navigation (classic entity IDs like `dt.entity.host`
   remain valid as identifiers).
4. **Coalesce repository fields** —
   `coalesce(artifact.repository, container_image.repository)` for external
   container scanners. See
   [common-patterns.md § 12](common-patterns.md#12-repository--artifact-coalescing).
5. **Use `arraySize()` not `size()`; `lower()` not `toLowercase()`** — DQL
   constraints, see `dt-dql-essentials`.
6. **`arraySlice` requires named parameters** — `arraySlice(arr, from: 0, to: N)` is
   correct; positional form `arraySlice(arr, 0, N)` fails with
   `TOO_MANY_POSITIONAL_PARAMETERS_WITH_OPTIONS`.
7. **`collectDistinct` has no `limit:` parameter** — wrap the call:
   `arraySlice(collectDistinct(field), from: 0, to: N)`.
8. **Python-style slice `arr[0:N]` is rejected inside `summarize`** — use
   `arraySlice(...)` in the summarize expression or in a follow-up `fieldsAdd`.
9. **`count()` must be aliased to be referenced downstream** —
   `summarize total = count() | sort total desc` works;
   `summarize count() | sort count() desc` fails.
10. **Always split mute status when reporting open vulnerabilities** —
   `Open NOT_MUTED`, `Open MUTED`, `Resolved`. Total counts alone are
   misleading.

---

## Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| Open-vulnerability count is unexpectedly low | Muted vulnerabilities are filtered out by default in some workflows; the canonical pattern keeps them but separates them in reporting | Split by mute status; report MUTED separately. See [common-patterns.md § 3](common-patterns.md#3-mute-status-separated-count-canonical-reporting) |
| Compliance pass rate is 0% | The query filtered to FAILED rows only, so PASSED isn't in the denominator | Include all statuses (`PASSED`, `FAILED`, `MANUAL`) and exclude `NOT_RELEVANT`. See [compliance.md](compliance.md) |
| External finding details missing the affected entity | External findings reach Smartscape via 3-way match — only one path may have populated for the row | Use the 3-way enrichment query from `dt-sec-contextualization/references/entity-enrichment.md` |
| Query times out on long time ranges | Raw field selection over a large window — no summarization to bound output size | Add a `summarize` block, shorten the time range, or apply pre-aggregation filters earlier |
| Drill-down by `finding.id` returns nothing | Default time range may be too narrow, or the ID format is wrong for that provider | Widen the time range; verify the exact ID format (UUID for Dynatrace, ARN for AWS, hex hash for AutomationEngine) |
| External compliance group-by `compliance.rule.id` returns null | External compliance findings don't populate `compliance.rule.*` | Group by `compliance.standards` (expand) / `compliance.policy` / `compliance.control`, with `finding.title` / `finding.type` for display |
| RVA snapshot missing a recent vulnerability state change | RVA cycle is ~15m; widening past 30m doesn't help | Wait for the next cycle; or query `VULNERABILITY_STATUS_CHANGE_EVENT` history outside the 30m window |
| Object's compliance findings are missing from results | No `COMPLIANCE_SCAN_COMPLETED` for that object within the 1h window — the inner join drops it | Object wasn't scanned in the last cycle. By design, not a bug. Don't widen beyond 1h to work around this. |
| Coverage query uses `VULNERABILITY_COVERAGE_REPORT_EVENT` | Deprecated event type | Use `VULNERABILITY_SCAN` instead — see [coverage.md](coverage.md) |
| Some expected findings are missing from the T&E or Vulnerabilities apps | The apps require all SD-required fields (`event.id`, `event.provider`, `finding.type`, `finding.id`, `finding.time.created`, `finding.title`, `dt.security.risk.level`, `object.id`, `object.type`). Findings missing any are filtered out. | Run the same query *without* the SD-compliance filter to see which fields are missing. See [detections.md § Threats & Exploits (T&E) App Compatibility](detections.md#threats--exploits-te-app-compatibility) |
| Cross-provider count includes Dynatrace state-report rows multiple times | Missing the double-counting guard | Add `filter product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"` |
| `vulnerability.parent.*` filter behaves unexpectedly | The entire `vulnerability.parent.*` namespace is deprecated | Derive every vulnerability-level value from per-entity fields/arrays in Stage 3 — verdicts via `collectDistinct(...)` + `in(...)`, scalars via `takeMin/takeMax/takeFirst` |
| `filter vulnerability.stack == "THIRD_PARTY"` matches nothing | Wrong enum value | Use `in(vulnerability.stack, array("CODE_LIBRARY","SOFTWARE"))` for third-party; `=="CODE"` for CLV |
| `affected_entity.vulnerable_functions` is empty for IN_USE rows | Per-language vulnerable function reporting feature is disabled on the OneAgent | Enable the feature in OneAgent settings; until then trust the status flag but don't expect FQCN detail |
| `affected_entity.affected_processes.count` is 0 on a HOST/KUBERNETES_NODE row | These fields are populated only when `affected_entity.type == "PROCESS_GROUP"` | Filter to PG entities for process-level rollups; for host-level use `affected_entity.id` directly |
| DSS (`vulnerability.risk.score`) seems to exceed CVSS base score | Reading the wrong field, or comparing per-entity vs. vulnerability-level | DSS modifiers can only reduce CVSS; if values diverge, you're likely projecting raw `vulnerability.cvss.base_score` against post-aggregation `vulnerability.risk.score` |
| All CLV findings show score 10.0 | This is correct — CLV always scores Critical | Don't filter CLV by runtime-assessment modifiers; use `vulnerability.code_location.name` and `affected_entity.id` to drill |
| `filter compliance.standard.short_name == "PCI"` returns nothing on DT-native data | KSPM only emits `CIS` / `DORA` / `NIST` / `DISA STIG` | PCI/ISO/HIPAA/GDPR arrive via CSPM/VSPM or external; remove the `product.vendor == "Dynatrace"` filter and use cross-provider routing |
| `filter compliance.standard.short_name == "STIG"` returns nothing | The KSPM short_name is the full `"DISA STIG"` — bare `"STIG"` doesn't match anything | Use `contains(lower(compliance.standard.short_name), "stig")` (or exact `== "DISA STIG"`). Same caveat applies to other multi-word labels |
| `compliance.rule.id` / `compliance.rule.title` are null for some compliance rows | Those rows are external (CSPM/VSPM or other posture tools) | KSPM patterns (Steps 1+2) don't apply; use the external taxonomy — group by `compliance.standards` (expand) / `compliance.policy` / `compliance.control` and `event.provider` |
| Pass rate seems too high — MANUAL counted as pass | MANUAL must be in the denominator only, not numerator | Rebuild as `Passed * 100 / (Passed + Failed + Manual)`; never `Passed * 100 / (Passed + Failed)` |
| Compliance pass rate seems too low — NOT_RELEVANT included | NOT_RELEVANT must be excluded *before* aggregation | Add `filter compliance.result.status.level != "NOT_RELEVANT"` in Step 1 |
| `COMPLIANCE_SCAN_COMPLETED` event missing for some objects | Scan didn't complete in the 1h window for that cluster | Wait for next ActiveGate dataset push (typically hourly), or use a longer window for history (deliberately bypassing the snapshot pattern) |
| `scan.result.summary_json` used for compliance posture | Bypasses the per-rule pipeline; pre-aggregated blob cannot be filtered or broken down by rule/severity; causes a redundant second query | **Do not use `scan.result.summary_json` for posture questions.** Always route through the `COMPLIANCE_FINDING` canonical pipeline (Steps 1+2 in [compliance.md](compliance.md)). |
| Asked "show muted compliance findings" returns confusing results | Compliance has no mute fields | Explain that mute / waiver isn't modeled in `security.events` for compliance — only vulnerabilities have `mute.*` |
| `object.type` filter doesn't match expected K8s objects | Wrong field — `object.type` is uppercase entity type | Use `compliance.result.object.type` for analyzer codes (`k8scluster`, `k8spod`, …) or `object.type` for entity types (`KUBERNETES_CLUSTER`, …) |
| RAP query with `event.provider == "OneAgent"` returns nothing | Likely a non-RAP filtering issue (window too narrow, wrong event.type, etc.) — both `event.provider == "OneAgent"` and `product.name == "Runtime Application Protection"` are populated on current RAP rows. | Switch to the canonical `product.name == "Runtime Application Protection"`; widen the window; verify `event.type == "DETECTION_FINDING"`. |
| `threat.attack.technique.ids == "T1078"` matches no rows | Field is an array | Use `in("T1078", threat.attack.technique.ids)` or `expand technique = threat.attack.technique.ids` |
| Sub-technique IDs like `T1059.003` don't match `threat.attack.technique.ids` | Sub-techniques live in a separate `threat.attack.subtechnique.ids` array | Query the sub-technique array directly, or OR across both arrays for "parent + sub" coverage |
| MITRE techniques missing on RAP / external detections | Only Automated Detections populates `threat.attack.*` | For RAP, map `finding.type` → MITRE manually; for external, parse `dt.raw_data` if the provider includes MITRE in its raw payload |
| Asked "show muted detections" returns confusing results | Detections have no mute namespace | Explain: detections aren't lifecycle-tracked in `security.events`; suppression is UI-side or ingest-side |
| Rule-execution count includes both findings and summary rows | Mixed event types | Filter `event.type == "DETECTION_EXECUTION_SUMMARY"` only; findings counts go through `DETECTION_FINDING` |
| Block-vs-monitor breakdown uses `event.outcome` and is mostly null | Wrong field | Use `finding.action` (`Blocked` / `Audited` / `Allowlisted`) for RAP |
| Top-attacker query returns null/empty for IP, or mismatched comparisons against other IP fields | Wrong field name, or array not cast to `ip()` | Use `actor.ips` (plural, `ipAddress[]`) — `actor.ip`/`actor.location` don't exist in the SD. `expand actor.ips` then `fieldsAdd ip = ip(actor.ips)`; project `actor.geo.country.name` for geo. Reputation enrichment (AbuseIPDB / VirusTotal) is client-side in the Threats & Exploits app, not in DQL rows |
| `event.status == "PASS"` (or `"FAIL"`) matches nothing on compliance rows | `event.status` is a generic lifecycle field; wrong field for compliance verdicts | Replace with `compliance.result.status.level == "PASSED"` (or `"FAILED"`, `"MANUAL"`, `"NOT_RELEVANT"`). See [compliance.md](compliance.md) |
| Compliance `countIf(... != "PASSED")` over-counts failed rules | Negation includes `MANUAL` and `NOT_RELEVANT` in the failed count | Use an explicit `countIf(compliance.result.status.level == "FAILED")` |
| KSPM join with `on: {left.scan.id == right.scan.id}` fails or returns unexpected columns | `left.`/`right.` prefixes are not valid in `on:` | Use the shorthand `on: {scan.id}` (DQL join shorthand when the field name matches on both sides) |
| Pass rate from KSPM query is wrong (each object inflates the rule count) | Pass rate computed on raw per-`(rule, object)` rows before Step 2 rollup | Apply the Step 2 per-rule summarize first; compute `passRate` from the per-rule verdict counts. See [compliance.md § Step 2](compliance.md) |
