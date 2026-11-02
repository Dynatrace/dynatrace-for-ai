# Static Validation Checklist

This checklist is the **primary way** issues are found in a translated artifact during the upgrade (Step 3a). Walk through **every** common translation artifact issue below and assess whether it is present in the current artifact by statically inspecting the JSON.

This checklist does **not** guarantee the artifact will pass the Settings API — some schema-level constraints can only be confirmed by an actual validate-only run or by the final apply (both of which need write access). Either way, treat any issue found here as a finding to fix using the referenced fix guidance.

> **Same guiding principle applies** — every change made to the artifact must be communicated to the user; behavioral changes must be confirmed before they are made.

## How to use this checklist

Run each check below against the **extracted** artifact (`translated-<scope>-pipeline.json`, i.e. the `.result` of the envelope — not the envelope file). Record every hit against its processor (keyed by stage and `id`) in the worklist file described in [Step 3a of classic-pipeline.md](classic-pipeline.md#3a-assess-the-whole-artifact-against-the-static-checklist); the Step 3b summary counts and the Step 4–5 fixes are driven from it.

Each stage is an object with a `processors` array. The populated stages present in the artifact are `processing`, `securityContext`, `metricExtraction`, `davis`, `storage`. Each property heading below names the stages it applies to — "all stages" means the processors of every stage; a named stage means only that stage's `processors`. Include **disabled** processors (`enabled: false`) in every check — a disabled processor with an invalid field still fails validation and can be re-enabled later.

In the processing stage, apply the checks only to the translated `type: dql` processors. The technology bundle processors appended in Step 2a are a ready-to-deploy processor type and are not assessed.

Perform each check by reading the artifact JSON. Use whatever inspection method you have available — reading the file directly, a JSON query tool, or a small script.

## Checklist

The checklist is organized **by the JSON property/key** each check inspects, so you can assess a processor property-by-property in a single read. For each property below, apply every listed check to the processors in the stages named and record any processor that matches a detection rule against the stage it belongs to. Properties not present on a given processor are simply skipped.

### `id` — all stages

- **Too short** — measure the length of `id`. Any `id` shorter than 4 characters will be rejected. Fix: [misc.md](translation-issue-fixes/misc.md#processor-id-too-short).
- **Too long** — measure the length of `id`. Any `id` longer than 100 characters will be rejected. Truncating to fit can produce duplicate IDs within the same stage — check for uniqueness after trimming. Fix: [misc.md](translation-issue-fixes/misc.md#processor-id-too-long).

### `description` — processing stage

- **Faulty processor (any DQL script issue)** — every processing-stage DQL script issue (`filterOut`, unsupported classic function, script too long, empty script, or any other invalid/partial translation) surfaces through the processor's `description`. First check `.context.warnings` in the **envelope** for `withWarning=true`, then read each processing-stage processor's `description`: a faulty one begins with a documented failure phrase (`DQL translation failed...` / `Auto-translated DQL script is invalid. <reason>`; see [translate-api.md](translate-api.md)). Count each faulty processor as **one** finding — translation reports only the first problem per script, so a processor may hide several and is fixed iteratively. Fix: [Step 5 in classic-pipeline.md](classic-pipeline.md#step-5-fix-processing-stage-dql-processors), recipes in [dql-scripts.md](translation-issue-fixes/dql-scripts.md).

### `matcher` — all stages

- **LQL matcher expression** — check whether the matcher contains `lqlMatch` (`lqlMatchValue`, `lqlMatchFullText`). These are not valid DQL and will be rejected. Fix: [matchers.md](translation-issue-fixes/matchers.md).

### `davis.properties` — davis stage

- **Duplicate dimensions** — check whether any two entries in the array share the same `[strategy, key]` pair. A repeated pair is rejected by the API. Fix: [misc.md](translation-issue-fixes/misc.md#duplicate-dimensions-in-davis-event-extraction).

### `sampleData` — processing stage

- **Too long** — measure its character length. Anything longer than 8192 characters will be rejected. `sampleData` is carried only on processing-stage (`type: dql`) processors. Fix: [misc.md](translation-issue-fixes/misc.md#sampledata-field-too-long).

## Total processor count — all stages combined

- **Too many processors** — sum the lengths of `processors` across every stage present in the artifact (`processing`, `securityContext`, `metricExtraction`, `davis`, `storage`). If the combined total exceeds 1000, the pipeline will be rejected. There is no mechanical fix: the processors must be split across multiple pipelines. Surface this as a blocking warning to the user as soon as it is detected.

## Residual risk that static checks cannot cover

Two categories cannot be confirmed without write access:

- **Deprecated `technology.technologyId`** — a statically well-formed `technologyId` can still be rejected at validation time if it is no longer current. The error message then states the exact replacement value — see [misc.md](translation-issue-fixes/misc.md#deprecated-technologyid-in-a-technology-bundle-processor).
- **Uncatalogued schema constraints** — this checklist covers the most common patterns. The Settings API enforces the full `builtin:openpipeline.<scope>.pipelines` schema validation.

Because of this, recommend that the finished artifact is validated with a real `--validate-only` run — or applied — by someone who holds `settings:objects:write` before it is considered production-ready. The static pass makes the artifact as correct as it can be without write access; it does not replace that final authoritative check.
