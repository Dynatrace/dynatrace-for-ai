# Translation Issue Fixes — DQL Processor Script Issues

Processor placeholder patterns and DQL script validation errors encountered when upgrading a classic pipeline, with fix guidance.

See also: [matchers.md](matchers.md) | [misc.md](misc.md)

> **Before modifying any DQL script below, load `dt-dql-essentials` if available** — every fix on this page rewrites DQL.

## Contents

- [Unsupported command — `filterOut` replace with drop processor](#unsupported-command--filterout-replace-with-drop-processor)
  - [Mixed `filterOut` — when the drop condition depends on a runtime-computed value](#mixed-filterout--when-the-drop-condition-depends-on-a-runtime-computed-value)
- [Unsupported classic function — rewrite with DQL equivalent](#unsupported-classic-function--rewrite-with-dql-equivalent)
- [DQL script too long](#dql-script-too-long)
- [Empty DQL script in a placeholder](#empty-dql-script-in-a-placeholder)

## Guiding principle — no silent changes

The translated artifact is a faithful representation of the tenant's production configuration. The goal of every fix is to produce an equivalent result in OpenPipeline — not to simplify, not to clean up, and not to delete. **Every change made to the artifact must be communicated to the user.** Changes that are purely mechanical (rename, quote style, redundant no-op removal) should be described before or as they are applied. Changes that could affect runtime behavior — even in edge cases — must be confirmed by the user before they are made. When in doubt, surface the tradeoff and let the user decide.

## Unsupported command — `filterOut` replace with drop processor

When a classic rule used `filterOut` as its only command, translation cannot produce a valid DQL script and emits a processor placeholder:

```json
{
  "id": "<rule name>",
  "type": "dql",
  "enabled": true,
  "matcher": "<matcher>",
  "description": "Auto-translated DQL script is invalid. There's been an error during parsing: The `filterOut` command isn't enabled.",
  "dql": { "script": "filterOut true" }
}
```

> **Important — `filterOut` is not `filter NOT (...)`:** Do not rewrite this as a DQL `filter NOT (condition)` command. The `filterOut` command is disabled in the OpenPipeline processing stage; any DQL script containing it is rejected by the API regardless of whether the processor is enabled or disabled. The only valid migration is the `drop` processor type shown below.

Replace the processor placeholder with a `drop` processor. The matcher carries over as-is; remove the `dql` field entirely:

```json
{
  "id": "<rule name>",
  "type": "drop",
  "enabled": true,
  "matcher": "<matcher>",
  "description": "<rule name>"
}
```

### Mixed `filterOut` — when the drop condition depends on a runtime-computed value

If the original rule mixed `filterOut` with other commands, do not apply the simple `drop` pattern directly.

`filterOut` and `drop` discard the record entirely — a record that is dropped does not reach subsequent processors. This behavior is both the constraint and the key to migrating correctly: the rule must be split so that the drop processor sees the computed field it needs, and any cleanup after the drop only runs on records that survived.

**Example classic rule auto-translation:**

```
parse content, "LD 'My monitored service call took ' INT:took 'ms'"
| filterOut took < 100
| fieldsRemove took
```

This does three things in sequence: parses `took` from `content`, drops the event if `took < 100`, and removes the `took` field from events that were not dropped. Because `filterOut` discards records completely, the `fieldsRemove` in the original rule only ever ran on survivors. The migration preserves this by splitting across multiple processors.

**Migration approach — split into ordered processors:**

Steps 1 and 3 below require writing new DQL from scratch — load `dt-dql-essentials` if available before drafting them.

Present this plan to the user before applying:

1. **DQL processor** — parse the runtime value out of the raw field and keep it for downstream use.
2. **Drop processor** — use the parsed field as the matcher condition. Because processors run in order, the field computed in step 1 is available here.
3. **DQL processor (cleanup)** — remove the temporary parsed field from events that were not dropped. This processor only runs on events that survived the drop.

Confirm the split with the user. The order and IDs of the new processors must be agreed before inserting them into the artifact.

**Constraints to communicate clearly:**

- Leaving `filterOut` in the DQL script is not a valid option — the API rejects it even when the processor is disabled.
- Keeping the placeholder as-is (disabled, with the invalid script) is also not a valid option for the same reason — the artifact will not pass validation.
- **Do not propose deleting the processor.** The goal is to migrate the rule as precisely as possible. Proposing deletion risks silently changing pipeline behavior and must never be the default suggestion. Only raise deletion as an option if the user explicitly indicates the rule is no longer needed.

## Unsupported classic function — rewrite with DQL equivalent

When a classic processing script used a function that has no direct DQL equivalent, the translation substitutes a `directTransformationUnsupported_<functionName>` placeholder and emits a processor placeholder:

```json
{
  "id": "<rule name>",
  "type": "dql",
  "enabled": true,
  "matcher": "<matcher>",
  "description": "Auto-translated DQL script is invalid. There's been an error during parsing: There's no function `directTransformationUnsupported_<functionName>`.",
  "dql": {
    "script": "... | fieldsAdd result = directTransformationUnsupported_<functionName>(arg1, arg2)"
  }
}
```

The placeholder name encodes what the original function was doing. Use it as the starting point to find a DQL equivalent: check the [log processing public docs](../public-docs-reference.md) for available processing commands and their equivalents, and load `dt-dql-essentials` to explore alternatives together with the user. Replace each placeholder with the correct DQL expression and rewrite the processor script before re-applying.

## DQL script too long

**Why it happens:** The `dql.script` field has an 8192-character limit. Scripts that contain large `CASE WHEN` blocks with many branches, or that parse complex JSON structures using deeply chained field expressions, often exceed this limit.

**API error response:**

```json
{
  "path": "builtin:openpipeline.logs.pipelines/0/processing/processors/44/dql/script",
  "message": "Size must be between 0 and 8192",
  "parameterLocation": "PAYLOAD_BODY",
  "location": null
}
```

**How to fix — try in order:**

Before making any change, explain to the user which processor is affected and what you intend to do. The goal is to reduce script size with no change in logical behavior — any shortening that could alter what the script produces must be confirmed by the user first. All three fixes below edit the DQL script directly — load `dt-dql-essentials` if available before making any of them.

1. **Shorten temporary field names.** Translation sometimes generates verbose intermediate field names (e.g. `temp_parsed_json_value`). Replace them with shorter equivalents (`t`, `v`, `parsed`) that do not collide with existing fields. Even small reductions compound across many field references and can bring the script within the limit. This is a safe mechanical rename — inform the user but no explicit confirmation is required.

2. **Switch string literal quoting.** If the script contains triple-quoted string literals (`'''...'''`) and the string content contains no characters that would require escaping in double-quoted form (no backslash, no embedded double-quote), replace the triple-quote delimiters with double-quotes (`"..."`). Triple-quoted strings cost two extra characters per literal. Verify each literal before switching — if in doubt, leave it triple-quoted. Inform the user of each change made.

3. **Refactor the logic.** If the above steps are insufficient, present the options to the user — for example, splitting the script across two processors (each handling a subset of CASE branches) or dropping branches that cover rarely seen inputs. Do not drop or restructure logic without explicit user approval.

## Empty DQL script in a placeholder

**Why it happens:** An empty `dql.script` (`""`) does not always mean a translation error occurred. Classic log processing commands sometimes cancel each other's effects — for example, a `fields add` followed by a `fields remove` of the same field — and the translation API can simplify these to a no-op during translation, producing an empty script intentionally. A translation error is also possible, but assume the empty result is deliberate until proven otherwise.

**How to fix:**

1. Find the original classic rule by the processor placeholder's `id` in the source schema (Step 1 discovery output contains this).
2. Read the original script carefully and determine what it was doing — field enrichment, parsing, or filtering.
3. Present your analysis to the user: explain what the original rule did and why you believe the empty script is (or is not) a correct simplification.
4. If the processor can be removed — because the original commands cancel out, because OpenPipeline handles the equivalent behavior automatically, or because a technology bundle processor already covers it — propose deletion to the user and wait for explicit confirmation. Never delete it silently.
5. If the original script had meaningful net effect that the empty translation does not reproduce, rewrite it from scratch. Load `dt-dql-essentials` if available, then follow the same rewrite guidance as for other processor placeholders (Step 5 in classic-pipeline.md).
