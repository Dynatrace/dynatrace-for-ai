# event.type in Matcher Fields

In the classic logs pipeline, Dynatrace set an `event.type` field on records before they entered the customizable part of the pipeline. Known values include e.g. `LOG` (standard log records) and `K8S` (Kubernetes events). The field was therefore available to matchers in all stages — processing, security context, metric extraction, event extraction, and bucket assignment.

In OpenPipeline, `event.type` is no longer set automatically. More importantly, the routing of record types has changed: only log records flow through the logs pipeline. Records that previously carried non-LOG values (e.g. `K8S`) are now Davis events or system events and flow through separate pipelines.

**Important caveat:** the simplifications below assume `event.type` is not set by any DQL processor in the processing stage of the translated artifact. A processor that runs `fieldsAdd event.type = "someValue"` makes the field available to all downstream processors and post-processing stage matchers. Before suggesting any change, ask the user whether any processing stage processor writes to `event.type`, or offer to scan the `dql.script` fields of all processing stage processors in the artifact for occurrences of `event.type`. Note that such a scan requires DQL knowledge to interpret correctly — `event.type` may appear as a field reference (meaningful) or inside a string literal (not meaningful); load `dt-dql-essentials` if available before drawing conclusions from the scan.

This scan applies **only to the logs pipeline**. Skip this step for the bizevents scope.

## How to detect

Scan `matcher` fields across all stages of the translated logs artifact — processing, securityContext, metricExtraction, davis, and storage. For each processor in each stage, check whether the `matcher` value contains `event.type`. Include disabled processors — a disabled processor with this issue can become active later and will silently fail at that point.

If the output is an empty array, no action is needed. If any processors are listed, first address the caveat above — ask the user whether any processing stage processor writes to `event.type`, or offer to scan the processing stage DQL scripts for them — then assess each affected processor using the guidance below before proceeding to final validation.

## For each affected processor

Inspect the matcher expression to determine which of the four cases applies. The resolutions below rewrite DQL matcher expressions by hand — load `dt-dql-essentials` if available before simplifying one, and verify the result with `dtctl verify openpipeline-matcher` ([Verify after fix](#verify-after-fix)). For each case, the suggested resolution assumes `event.type` is not set earlier in the pipeline — always state this assumption explicitly when presenting the suggestion to the user.

### Case 1 — Condition matches the `LOG` value

Examples: `event.type == "LOG"`, `matchesValue(event.type, "LOG")`, `event.type != "k8s"`

In the classic logs pipeline, all standard log records had `event.type` set to `LOG`. In OpenPipeline, only log records flow through the logs pipeline — records that previously carried non-LOG values now route to separate pipelines. Therefore, unless a preceding processor sets `event.type` to something else, a condition matching `LOG` covers all records in the logs pipeline today and is effectively always true.

**Suggested resolution:** Simplify the matcher using standard boolean rules, unless `event.type` is set earlier in the pipeline. Present the suggestion to the user and confirm before applying.

- **Sole condition** (`event.type == "LOG"` is the entire matcher) → replace the matcher value with `"true"`.
- **AND combination** (`event.type == "LOG" AND <rest>`) → remove the `event.type == "LOG"` sub-expression; the matcher becomes `<rest>`.
- **OR combination** (`event.type == "LOG" OR <rest>`) → the whole expression is always true; replace the matcher value with `"true"`.

Examples:

| Original matcher                                | Suggested simplified matcher |
| ----------------------------------------------- | ---------------------------- |
| `event.type == "LOG"`                           | `true`                       |
| `event.type == "LOG" AND log.source == "myapp"` | `log.source == "myapp"`      |
| `event.type == "LOG" OR log.source == "myapp"`  | `true`                       |

### Case 2 — Condition matches a non-LOG value

Examples: `event.type == "k8s"`, `matchesValue(event.type, "k8s")`

Records that previously carried non-LOG values no longer flow through the OpenPipeline logs pipeline — they are now Davis events or system events and flow through separate pipelines. Unless a preceding processor sets `event.type` to a non-LOG value, this processor will be dead code that never runs. This is not a matcher syntax problem; it is a fundamental change in how records are routed.

**Suggested resolution:** Communicate this verbosely to the user before making any change. The message must be clear:

> The records this processor previously matched (those with `event.type == "<value>"`) no longer flow through the logs pipeline in OpenPipeline — they are now routed as Davis events or system events to separate OpenPipeline configurations. Unless a preceding processor in this artifact sets `event.type` to `"<value>"`, this processor will never run. If equivalent processing is still needed for those records, it must be set up separately in the corresponding OpenPipeline configuration. We suggest removing this processor from the logs artifact.

After the user acknowledges, ask for explicit confirmation before removing the processor.

### Case 3 — `isNotNull` or presence check

Examples: `isNotNull(event.type)`

In the classic logs pipeline, `event.type` was always set before the pipeline ran, so a presence check was always `true`. In OpenPipeline, the field is not set automatically — unless a preceding processor explicitly populates it. If no preceding processor writes `event.type`, the original intent of this check was effectively "match all records" and the sub-expression can be removed.

**Suggested resolution:** Use DQL boolean simplification to remove the sub-expression without changing the remaining logic, unless `event.type` is set earlier in the pipeline. Present the suggestion to the user and confirm before applying.

Examples:

| Original matcher                                  | Suggested simplified matcher     |
| ------------------------------------------------- | -------------------------------- |
| `isNotNull(event.type)`                           | `true`                           |
| `isNotNull(event.type) AND log.source == "myapp"` | `log.source == "myapp"`          |
| `isNotNull(event.type) OR log.source == "myapp"`  | `true` (whole OR is always true) |

Apply standard boolean rules: anything AND true → the other operand; anything OR true → true. Be precise — do not collapse more of the expression than the `isNotNull(event.type)` sub-expression and its direct boolean operator.

### Case 4 — Compound null-safe expression

Examples: `(not matchesValue(event.type, "k8s") or isNull(event.type))`, `(event.type == "LOG" or isNull(event.type))`

In classic, this pattern was used as a null-safe guard — the `isNull` arm defended against records where `event.type` was absent, while the main condition filtered by value. Because `event.type` is not set automatically in OpenPipeline, `isNull(event.type)` is always `true` (unless a preceding processor populates the field), which makes the entire OR sub-expression always `true` regardless of the other arm.

**Suggested resolution:** Unless `event.type` is set earlier in the pipeline, the whole compound sub-expression collapses to `true` and can be dropped from the AND chain. Present the suggestion to the user and confirm before applying.

Example:

Before:

```json
"matcher": "matchesValue(dt.entity.cloud_application, \"CLOUD_APPLICATION-81EB731A662D12B3\") and (not matchesValue(event.type, \"k8s\") or isNull(event.type)) and matchesValue(status, \"ERROR\")"
```

After:

```json
"matcher": "matchesValue(dt.entity.cloud_application, \"CLOUD_APPLICATION-81EB731A662D12B3\") and matchesValue(status, \"ERROR\")"
```

If the compound sub-expression is the sole condition (not part of an AND chain), replace the matcher value with `"true"`.

## Key constraint

Do not change any matcher without the user's confirmation. A matcher change affects which records the processor runs on — it is a behavioral change. Always state the assumption that `event.type` is not set earlier in the pipeline when presenting a suggestion. If the user confirms it is set by a preceding processor, skip the suggested simplification for affected processors and leave those matchers unchanged.

## Verify after fix

After applying any matcher simplification, verify the resulting expression before updating the artifact:

```dtctl
dtctl verify openpipeline-matcher '<simplified-expression>' --config-id logs --context <stage>
```

Valid `--context` values: `processing`, `securityContext`, `metricExtraction`, `davis`, `bucketAssignment`. Note: the bucket-assignment stage is keyed `storage` in the artifact but the context value here is `bucketAssignment`. The command exits 0 on success and 1 with an error message on failure. For multi-line expressions, pass via a file:

```dtctl
dtctl verify openpipeline-matcher -f matcher.dql --config-id logs --context processing
```
