# Classic Pipeline Upgrade

**Gen3 replacement**: OpenPipeline

**Phase 2 required**: no

Upgrade a tenant's Classic Pipeline configuration (Logs or Business events) to an OpenPipeline pipeline. The workflow produces and validates a deployable artifact. The artifact is reviewed and fixed collaboratively with the user if needed, and once it passes dry-run validation the user is advised on how to wire it into Dynamic routing.

## Prerequisites

**OAuth scopes**:

- `settings:objects:read`
- `openpipeline:configurations:read`
- `settings:objects:write` — **optional but recommended**; only needed for the final `--validate-only` dry-run ([Step 7](#step-7-final-validation)).

Most issues are found and fixed statically ([static-validation-checklist.md](static-validation-checklist.md), read-only); some residual risks (e.g. deprecated `technologyId`) can only be confirmed via validate/apply — `settings:objects:write` decides whether that final confirmation is available, so check it up front:

- **With write** → the Step 7 `--validate-only` dry-run confirms the artifact authoritatively.
- **Without write** → the static pass is best-effort only; advise a later `--validate-only` run or apply by a write-capable context before production.

## Instructions

### Step 1: Discovery and upgrade scope

Ask the user whether they already know which classic pipeline scopes have custom configuration, or whether they would like to run discovery queries first to check.

**If they want to run discovery first**, tell the user to confirm they have `settings:objects:read` on all the following schemas before running for it to be successful:

- Logs: `builtin:logmonitoring.log-dpp-rules`, `builtin:logmonitoring.log-security-context-rules`, `builtin:logmonitoring.schemaless-log-metric`, `builtin:logmonitoring.log-events`, `builtin:logmonitoring.log-buckets-rules`
- Business events: `builtin:bizevents-processing-pipelines.rule`, `builtin:bizevents-security-context-rules`, `builtin:bizevents-processing-metrics.rule`, `builtin:bizevents-processing-buckets.rule`

Once confirmed, run the discovery queries from [classic-config-discovery.md](classic-config-discovery.md) and use the results to inform scope selection.

**Confirm upgrade scope** — ask the user which pipeline configuration scope(s) they want to upgrade:

- **Logs only**
- **Business events only**
- **Both Logs and Business events**

If only one scope has custom rules, suggest that one as the default. If both scopes are selected, complete Steps 2–7 fully for one scope before starting the other — running both in parallel makes the workflow hard to track.

### Step 2: Produce the translated pipeline artifact

Before running translation, ask the user the following to determine the correct flags:

- **Disabled rules** — "Do you want disabled classic rules included in the translation?" (default: included — `--skip-disabled-rules` is `false` by default, meaning disabled rules are not skipped; set to `true` to exclude them)
- **Sample data** — "Do you want sample data attached to rules preserved in the output?" (default: included — `--include-sample-data=true`)
- **Built-in processing rules** — ask for logs only, recommend excluding them (`--skip-builtin-processing-rules=true`): OpenPipeline provides equivalent technology bundle processors that are better maintained than translated copies. See [technology-bundles.md](technology-bundles.md) for the mapping. Confirm the user agrees before overriding.
- **Technology bundle processors** — only ask this if built-in rules are being excluded: "Do you want to add technology bundle processors to the artifact for the built-in rules that were excluded? This replaces their functionality in the new pipeline. (Recommended: yes)" If the user says yes, proceed to Step 2a after translation. If no, skip Step 2a — the built-in rules will simply not be present in the new pipeline.

Once flags are confirmed, run the translation using those exact values for each selected scope. The example below uses the recommended defaults — adjust `--skip-disabled-rules` and `--include-sample-data` to match what the user confirmed:

```dtctl
dtctl translate classic-pipelines logs \
  --skip-disabled-rules=false \
  --skip-builtin-processing-rules=true \
  --include-sample-data=true \
  -A -o json > translated-logs-pipeline-envelope.json
dtctl translate classic-pipelines bizevents \
  --skip-disabled-rules=false \
  --include-sample-data=true \
  -A -o json > translated-bizevents-pipeline-envelope.json
```

`--skip-builtin-processing-rules` is ignored for bizevents — it applies to logs only, which is why the question is asked for logs only.

If `translate` is not recognized, use `dtctl get classic-pipelines-translation <logs|bizevents>` with the same flags — it is the previous form of the same command.

Set each flag to match the user's answers from the questions above before running.

The `-A` flag wraps the output in an agent envelope — see the [Translated artifact shape](#translated-artifact-shape) example for the full structure. Before passing the artifact to the Settings API, extract the value of `.result` from the envelope file into a separate file (e.g. `translated-logs-pipeline.json`). Use any JSON tool you have available — for example, with `jq`:

```
jq '.result' translated-logs-pipeline-envelope.json > translated-logs-pipeline.json
```

### Step 2a: Add technology bundle processors (logs only and if user confirmed)

This step applies only to logs and when the user confirmed they want technology bundle processors added. See [translate-api.md](translate-api.md) for the translation output format.

Using all built-in rules identified in Step 1 discovery (see [classic-config-discovery.md](classic-config-discovery.md) and [technology-bundles.md](technology-bundles.md)):

1. For each unique technology bundle identified by the mapping table in [technology-bundles.md](technology-bundles.md), copy the corresponding processor object from [technology_bundles.json](technology_bundles.json) — it contains ready-to-deploy processor definitions including `sampleData` for the OpenPipeline preview feature.
2. Set `enabled: true` if at least one of the bundle's classic rules was enabled; set `enabled: false` only if all the bundle's classic rules were disabled. Do not omit disabled bundles — preserve them as `enabled: false` so the user can re-enable later.
3. Insert the technology bundle processors at the **beginning** of the `processing.processors` array in the artifact — before the translated custom DQL processors. This preserves the original ordering where built-in rules ran first.

Present a summary to the user before inserting:

| Built-in rule(s)                               | Enabled in classic | Technology bundle processor to add                                 |
| ---------------------------------------------- | ------------------ | ------------------------------------------------------------------ |
| e.g. `[Built-in] db:cassandra:*` (3 rules)     | yes                | `processor_Cassandra` (`databases_cassandra_v2`) — `enabled: true` |
| e.g. `[Built-in] web_server:nginx:*` (2 rules) | no                 | `processor_Nginx` (`servers_nginx_v2`) — `enabled: false`          |

### Step 3: Assess all issues before fixing

Before fixing anything, get a full picture of issues across all stages.

#### 3a: Assess the whole artifact against the static checklist

Walk through **every** check in [static-validation-checklist.md](static-validation-checklist.md), assessing the artifact by static inspection of the JSON. The checklist is organized by JSON property/key, so you inspect each property (`id`, `description`, `matcher`, `davis.properties`, `sampleData`) once across the stages it applies to. In the processing stage the `description` is the single signal for all DQL script issues. This is the discovery method for **all** stages — processing, security context, metric extraction, Davis event extraction, and bucket assignment.

Record findings to a **worklist file** — `<scope>-findings.md` (e.g. `logs-findings.md`) in the working directory — **one row per faulty processor**, keyed by its stage and `id` (stage first, since the same `id` can appear in different stages). The processor is the logical unit of work: collect *all* of a processor's issues in its row so Steps 4–5 can resolve them together in one pass rather than revisiting the same processor repeatedly. This file is the single source of truth: the Step 3b counts are read from it, and it keeps progress across turns.

| Stage      | Processor `id` | Issues (checklist property)                         | Status |
| ---------- | -------------- | --------------------------------------------------- | ------ |
| processing | `<id>`         | oversized `sampleData`; LQL `matcher`; DQL `script` | open   |
| davis      | `<id>`         | duplicate dimensions (`davis.properties`)           | open   |

List every issue found on a processor in its `Issues` cell. Leave `Status` as `open` until every issue on that processor is resolved (Steps 4–5).

#### 3b: Present summary

Present a summary to the user with a row per stage, counting the faulty processors recorded in the worklist:

| Stage                        | Processors with issues |
| ---------------------------- | ---------------------- |
| Permission (securityContext) | count for this stage   |
| Metric extraction            | count for this stage   |
| Davis                        | count for this stage   |
| Bucket assignment (storage)  | count for this stage   |
| Processing                   | count for this stage   |

If any findings were recorded, fix them in two passes: first the non-processing stages ([Step 4](#step-4-fix-non-processing-stage-issues)), then the processing-stage DQL processors one by one ([Step 5](#step-5-fix-processing-stage-dql-processors)). If all stages show 0 issues, skip Steps 4–5 and go straight to the remaining checks: [Step 6](#step-6-scan-matchers-for-eventtype-references-logs-only) for the logs scope, or [Step 7](#step-7-final-validation) for bizevents.

### Step 4: Fix non-processing stage issues

Fix every faulty processor in the non-processing stages — Permission (`securityContext`), Metric extraction (`metricExtraction`), Davis (`davis`), and Bucket assignment (`storage`).

Work through these processors one at a time. For each, resolve **all** of its listed issues — using the fix pattern each links to in [translation-issue-fixes/](translation-issue-fixes/), then mark the processor `fixed` in the worklist.

### Step 5: Fix processing-stage DQL processors

Handle the processing stage **processor by processor** — for each translated `type: dql` processor with any open finding, fix everything about it before moving on. (The technology bundle processors appended in [Step 2a](#step-2a-add-technology-bundle-processors-logs-only-and-if-user-confirmed) are a different, ready-to-deploy processor type — they are not checked or modified here.) A DQL processor can carry several issues at once: an out-of-range `id`, an oversized `sampleData`, an LQL `matcher`, and one or more DQL `script` problems etc. For each such processor, work through its open findings — the quick ones first, the script last:

1. **The least invasive fixes** → an out-of-range `id` (too short: expand; too long: truncate, then check uniqueness within the stage) or oversized `sampleData` (truncate at a natural boundary). See [misc.md](translation-issue-fixes/misc.md#processor-id-too-short), [misc.md](translation-issue-fixes/misc.md#processor-id-too-long), and [misc.md](translation-issue-fixes/misc.md#sampledata-field-too-long).

2. **LQL `matcher`** (contains `lqlMatchValue()` or `lqlMatchFullText()`) → look up the original LQL expression in the source schema and translate that to DQL. Do not translate the `lqlMatch*` text from the artifact. When adjusting the expression by hand, load `dt-dql-essentials` if available. See [matchers.md](translation-issue-fixes/matchers.md).

3. **DQL `script`** → the failure surfaces through the processor's `description` (failure phrase; full list in [translate-api.md](translate-api.md)), which reports only the first problem at a time. Fix it:

   - Read the `description`: `DQL translation failed due to an unexpected issue.` (original classic script is in `dql.script` verbatim) or `Auto-translated DQL script is invalid. <reason>` (partial result in `dql.script`).

   - Using the processor `id`, find the matching classic rule (`builtin:logmonitoring.log-dpp-rules` for Logs, `builtin:bizevents-processing-pipelines.rule` for Business events).

   - Rewrite the processor as valid DQL together with the user. Load `dt-dql-essentials` if available; check [dql-scripts.md](translation-issue-fixes/dql-scripts.md) for known patterns; for classic function reference see [Classic log processing functions](public-docs-reference.md).

   - Validate the rewrite with `dtctl verify openpipeline-dql-processor` — not by re-translating, which operates on the classic rules rather than this artifact. The command exits 0 on success and 1 with the first error on failure; repeat rewrite → verify until it passes clean:

     ```dtctl
     # Inline (short scripts)
     dtctl verify openpipeline-dql-processor 'parse content, "IPV4:ip"' --config-id logs
     # From file (multi-line scripts)
     dtctl verify openpipeline-dql-processor -f script.dql --config-id logs
     ```

     Use `--config-id bizevents` when upgrading Business events. If dtctl is unavailable, use the Python SDK examples in [openpipeline-api.md](openpipeline-api.md).

   - Optionally preview the fixed processor against its sample data before committing. Build a processor JSON file from the processor object in the artifact, replacing the nested `"dql": { "script": "..." }` with a flat `"dqlScript": "..."` field — the API requires this form. Keep all other fields (`id`, `type`, `matcher`, `description`, `sampleData`, `enabled`) as-is, then run:

     ```dtctl
     dtctl exec preview-processor -f processor.json --config-id logs
     ```

Once all the processor's issues are resolved, mark it `fixed` in the worklist and move to the next processing processor. When all processing processors are clean, set each fixed processor's `description` to its `id`, then continue to [Step 6](#step-6-scan-matchers-for-eventtype-references-logs-only) (logs) or [Step 7](#step-7-final-validation) (bizevents).

> Log processing commands and DQL are different languages with no 1:1 mapping. A translated processor that compiles correctly may still not behave identically. When rewriting, focus on what the rule is supposed to produce, not on preserving the original syntax. Use `dtctl exec preview-processor -f processor.json --config-id logs` to confirm output before committing the rewrite (see [openpipeline-api.md](openpipeline-api.md) for the processor JSON field structure).

### Step 6: Scan matchers for event.type references (logs only)

Skip this step for the bizevents (business events) scope.

For the logs scope, scan all stages of the artifact for matchers that reference `event.type`. This field was set on records before they entered the customizable part of the classic logs pipeline; it is no longer set automatically in OpenPipeline. A matcher referencing it will silently never match or match in unintended ways, and dry-run validation does not catch this.

Run the scan from [event-type-in-matchers.md](event-type-in-matchers.md) against `translated-logs-pipeline.json`. If the output is an empty array, proceed to Step 7. If any processors are listed, work through each one using the guidance in [event-type-in-matchers.md](event-type-in-matchers.md) before proceeding.

### Step 7: Final validation

Enter this step only when all stages show 0 issues (Step 3b summary) and the Step 6 event.type scan is clear. All issue-finding was already done by the static walkthrough; this step is the authoritative final confirmation and, as set out in [Prerequisites](#prerequisites), needs `settings:objects:write`.

**With `settings:objects:write` — run the dry-run (recommended):**

Validate the complete artifact (processing rules included) to confirm everything passes cleanly:

```dtctl
dtctl create settings -f translated-<scope>-pipeline.json --schema builtin:openpipeline.logs.pipelines --scope environment --validate-only
```

For Business events use `--schema builtin:openpipeline.bizevents.pipelines`. A passing result returns no constraint violations.

If it does return violations, read them and fix each one. If the output is truncated, re-run with `--debug` and redirect both stdout and stderr to a file:

```dtctl
dtctl create settings -f translated-<scope>-pipeline.json --schema builtin:openpipeline.logs.pipelines --scope environment --validate-only --debug > validate-debug.txt 2>&1
```

In the output file, locate the `===> RESPONSE <===` section, find the line containing `"constraintViolations":`, and read each entry's `path` and `message`. Each `path` starts with `builtin:openpipeline.logs.pipelines/0/` (or the bizevents equivalent) followed by the stage, processor index, and field — for example `builtin:openpipeline.logs.pipelines/0/processing/processors/18/sampleData` — which locates the exact processor and field. Fix using [translation-issue-fixes/](translation-issue-fixes/), then re-run — repeat until the dry-run passes with no violations.

**Without `settings:objects:write` — static confirmation only:**

You cannot run the dry-run. Confirm instead that every check in [static-validation-checklist.md](static-validation-checklist.md) comes back clean against the full artifact (processing rules included) and that the Step 6 event.type scan is clear, then restate the residual-risk caveat from [Prerequisites](#prerequisites): the artifact should still be validated or applied by a write-capable context before it is treated as production-ready.

### Step 8: Going live

Once the artifact passes final validation, explain the three ordered actions needed to put the configuration live. Do NOT initiate any of these steps — only walk through them if the user explicitly asks.

There are three ordered actions: putting the pipeline into place first, previewing processors while the pipeline has no routing yet, then wiring the routing to make it live.

**1. Put the pipeline into place**

The artifact must be in place before the routing entry can reference it.

Choose the preferred method:

- **In the app:** Create the pipeline via the OpenPipeline configuration UI using the artifact content.
- **Via Settings API / dtctl:** Submit the artifact to create the pipeline settings object and note the returned `objectId`.
- **Via configuration as code (Monaco / Terraform):** Add the pipeline as a resource using schema ID `builtin:openpipeline.logs.pipelines` (or `builtin:openpipeline.bizevents.pipelines` for Business events).

**2. Preview processors in the app**

With the pipeline in place but no routing entry yet, live data does not flow through it — this is the right moment to validate processor behavior safely. Open **Settings app > OpenPipeline configuration**, navigate to the new pipeline, and use the processor preview feature to run sample data through each processor and confirm the output matches expectations. This lets you catch any behavioral differences between the classic rules and their DQL equivalents before the pipeline receives real traffic. The same preview can also be done from the CLI:

```dtctl
dtctl exec preview-processor -f processor.json --config-id logs
```

The processor JSON file uses the artifact structure with one change: replace the nested `"dql": { "script": "..." }` with a flat `"dqlScript": "..."` field. All other fields (`id`, `type`, `matcher`, `description`, `sampleData`, `enabled`) stay as-is. See [openpipeline-api.md](openpipeline-api.md) for the full field reference.

**3. Wire the routing**

Dynamic routes give you the option to route your ingested data into a pipeline with a matching condition. Select **+ Dynamic route** to get started or learn more in the documentation.

Once you are satisfied with the processor preview, add the pipeline as the last entry in **Dynamic routing** for the scope. The routing array is evaluated top to bottom — first matching entry wins.

- **In the app:** Open **Dynamic routing** in OpenPipeline configuration and add the new last entry.
- **Via Settings API:**

Fetch the current routing settings object:

```dtctl
dtctl get settings --schema builtin:openpipeline.logs.routing -o json > current-routing.json
```

For Business events use `--schema builtin:openpipeline.bizevents.routing`.

The response is a JSON array; routing entries are under `[0].value.routingEntries`. Each entry shape:

```json
{
  "routingEntries": [
    {
      "enabled": true,
      "pipelineType": "custom",
      "pipelineId": "<existing-pipeline-objectId>",
      "matcher": "<matcher>",
      "description": "<existing route description>"
    },
    {
      "enabled": true,
      "pipelineType": "custom",
      "pipelineId": "<existing-pipeline-objectId>",
      "matcher": "<matcher>",
      "description": "<existing route description>"
    },
    {
      "enabled": true,
      "pipelineType": "custom",
      "pipelineId": "<objectId returned in action 1 above>",
      "matcher": "true",
      "description": "<name of the upgraded pipeline>"
    }
  ]
}
```

Append the new entry to `routingEntries`, save the modified `value` object to `updated-routing.json`, then apply:

```dtctl
dtctl apply -f updated-routing.json
```

- **Via configuration as code:** Embed the updated routing table in the same resource configuration as the pipeline.

## Customer actions

- Confirm whether to run discovery queries or provide scope directly; confirm `settings:objects:read` access on all relevant schemas before discovery.
- Confirm whether the context has `settings:objects:write`. Without it, issues are still found and fixed via the static walkthrough, but the finished artifact must later be validated or applied by someone who holds that scope.
- Decide which translation flags to apply (disabled rules, sample data, built-in rules).
- For each processor the agent cannot automatically rewrite: explain the original intent so the DQL rewrite accurately reflects what the rule was doing.
- Review the validation (or static-assessment) output and confirm fixes before the artifact is finalized.
- If they want to apply the pipeline and routing: choose their preferred method (app, Settings API, or config-as-code) and explicitly ask the agent to walk through it.

## Examples

### Translated artifact shape

Running with `-A` wraps the output in an agent envelope with structured metadata:

```json
{
  "ok": true,
  "result": {
    "customId": "defaultTranslatedFromClassic",
    "displayName": "defaultTranslatedFromClassic",
    "processing":        { "processors": [ ... ] },
    "securityContext":   { "processors": [ ... ] },
    "metricExtraction":  { "processors": [ ... ] },
    "davis":             { "processors": [ ... ] },
    "storage":           { "processors": [ ... ] },
    "costAllocation":    {},
    "dataExtraction":    {}
  },
  "context": {
    "verb": "get",
    "resource": "classic-pipelines-translation",
    "warnings": [ "some processing rules could not be translated automatically and need a manual rewrite (withWarning=true)" ],
    "suggestions": [ "Review the translated pipeline, then apply it with 'dtctl create settings --schema builtin:openpipeline.logs.pipelines -f <file>'" ]
  }
}
```

- **`.result`** — the pipeline artifact to pass to the Settings API (stages are at the root of `.result`, e.g. `.result.processing.processors`)
- **`.context.warnings`** — present when translation issues occurred (`withWarning=true`); empty array when translation was clean
- **`.context.suggestions`** — next-step hints to surface to the user

Each stage holds an array of processors at `.result.<stage>.processors`. Every processor — regardless of stage — carries the same top-level fields: `id`, `type`, `enabled`, `matcher`, `description`. Processing-stage (`type: dql`) processors additionally carry an optional `sampleData` string when the artifact was translated with `--include-sample-data=true`. The stage-specific payload sits under a key named after the processor type (`dql`, `securityContext`, `counterMetric`/`valueMetric`, `davis`, `bucketAssignment`).

The Step 3 static checklist inspects these processor paths (all relative to a processor object in `.result.<stage>.processors[]`):

| Checklist property                | JSON path on the processor                                 | Stages scanned                          |
| --------------------------------- | ---------------------------------------------------------- | --------------------------------------- |
| `id` too short / too long         | `.id`                                                      | all                                     |
| `matcher` — LQL / `event.type`    | `.matcher`                                                 | all (`event.type` is logs-only, Step 6) |
| `sampleData` too long             | `.sampleData`                                              | processing (when present)               |
| faulty processor + script subtype | `.description`, then `.dql.script`                         | processing                              |
| duplicate Davis dimensions        | `.davis.properties[].strategy` + `.davis.properties[].key` | davis                                   |
| total processor count > 1000      | count of `.processors[]` across all stages (artifact-level)| all (combined)                          |

Processor shape per stage (each also carries the common top-level fields above):

> **Processor order matters** — in the processing and bucket assignment stages, processors are evaluated in the order they appear in the array. Never reorder processors unless explicitly asked by the user.

**Processing** (`type: dql`) — DQL script processor:

```json
{
  "id": "<rule name>",
  "type": "dql",
  "enabled": true,
  "matcher": "<matcher>",
  "description": "<rule name>",
  "dql": { "script": "<dql script>" },
  "sampleData": "<sample record(s)> (optional; present when translated with sample data)"
}
```

**Security context** (`type: securityContext`):

```json
{
  "id": "<rule name>",
  "type": "securityContext",
  "enabled": true,
  "matcher": "<matcher>",
  "description": "<rule name>",
  "securityContext": { "value": { "type": "field", "field": { "sourceFieldName": "<field name>" } } }
}
```

**Metric extraction** (`type: counterMetric` or `valueMetric`):

```json
{
  "id": "<metric key>",
  "type": "counterMetric",
  "enabled": true,
  "matcher": "<matcher>",
  "description": "<metric key>",
  "counterMetric": {
    "metricKey": "<metric key>",
    "dimensions": [ { "extractionType": "field", "sourceFieldName": "<field name>", "strategy": "equals" } ]
  }
}
```

**Davis event extraction** (`type: davis`):

```json
{
  "id": "<rule name>",
  "type": "davis",
  "enabled": true,
  "matcher": "<matcher>",
  "description": "<rule name>",
  "davis": {
    "properties": [
      { "key": "event.name",                 "strategy": "equals", "value": "<value>" },
      { "key": "event.type",                 "strategy": "equals", "value": "<value>" },
      { "key": "dt.davis.is_merging_allowed","strategy": "equals", "value": "<value>" }
    ]
  }
}
```

**Bucket assignment** (`type: bucketAssignment` or `noStorage`):

```json
{
  "id": "<rule name>",
  "type": "bucketAssignment",
  "enabled": true,
  "matcher": "<matcher>",
  "description": "<rule name>",
  "bucketAssignment": { "bucketName": "<bucket name>" }
}
```

## Outcome

For each upgraded scope (`logs`, `bizevents`), a validated deployable OpenPipeline pipeline artifact is produced. Classic pipeline stages are mapped as follows:

| Classic stage     | OpenPipeline stage                                    |
| ----------------- | ----------------------------------------------------- |
| Processing        | Processing (DQL processor)                            |
| Security context  | Permission                                            |
| Metric extraction | Metric extraction (Counter or Value metric processor) |
| Event extraction  | Davis (Davis event processor)                         |
| Bucket assignment | Bucket assignment or No storage assignment processor  |

## Validation

The translated artifact is correct when [Step 7](#step-7-final-validation) comes back clean — no remaining processor placeholders and, with write access, a `--validate-only` run reporting no constraint violations; without write access, every [static-validation-checklist.md](static-validation-checklist.md) check clear and the event.type scan clear. Before going live, use the processor preview (Step 8) to confirm each DQL processor behaves equivalently to its classic rule.

Report the upgrade status for each scope. Without write access set **Dry-run passed** to `n/a (static)` and add the residual-risk note; the artifact is only fully "ready" once a real validate/apply has run with write access.

| Scope     | withWarning | Processor placeholders fixed | Dry-run passed        | Artifact ready |
| --------- | ----------- | ---------------------------- | --------------------- | -------------- |
| logs      | yes/no      | count                        | yes/no / n/a (static) | yes/no         |
| bizevents | yes/no      | count                        | yes/no / n/a (static) | yes/no         |

## References

- [classic-config-discovery.md](classic-config-discovery.md) — Discovery queries to check which classic pipeline stages have configuration before translating
- [technology-bundles.md](technology-bundles.md) — Technology bundle processor mapping from classic built-in rules, processor shape, and technologyId reference
- [technology_bundles.json](technology_bundles.json) — Ready-to-deploy processor objects with sampleData for all supported bundles
- [translate-api.md](translate-api.md) — Translation output reference: processor placeholder format and Davis event field mapping
- [event-type-in-matchers.md](event-type-in-matchers.md) — Handling `event.type` references in translated logs pipeline matchers (logs only): detection, three fix cases, and behavioral context
- [static-validation-checklist.md](static-validation-checklist.md) — Primary issue-discovery checklist (Step 3a): every common translation artifact issue organized by the JSON property/key it inspects, detected by static inspection with read access only
- [translation-issue-fixes/dql-scripts.md](translation-issue-fixes/dql-scripts.md) — Known processor placeholder patterns and DQL script validation errors with fix guidance
- [translation-issue-fixes/matchers.md](translation-issue-fixes/matchers.md) — LQL matcher validation errors and translation steps
- [translation-issue-fixes/misc.md](translation-issue-fixes/misc.md) — Behavioral differences, duplicate Davis dimensions, deprecated technologyId, processor ID and sampleData size errors
- [openpipeline-api.md](openpipeline-api.md) — Dynatrace Python SDK examples for OpenPipeline (pipeline translation, technology bundle list, matcher translation and verification, DQL processor script verification, processor preview) for when dtctl is unavailable
- [public-docs-reference.md](public-docs-reference.md) — External Dynatrace documentation links with function catalog for classic log processing
