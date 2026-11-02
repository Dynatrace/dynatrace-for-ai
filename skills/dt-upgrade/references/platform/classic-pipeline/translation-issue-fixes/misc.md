# Translation Issue Fixes — Miscellaneous

Settings API validation errors and behavioral differences encountered when upgrading a classic pipeline, with fix guidance.

See also: [dql-scripts.md](dql-scripts.md) | [matchers.md](matchers.md)

## Contents

- [Guiding principle — no silent changes](#guiding-principle--no-silent-changes)
- [Behavioral differences between classic and OpenPipeline](#behavioral-differences-between-classic-and-openpipeline)
- [Duplicate dimensions in Davis event extraction](#duplicate-dimensions-in-davis-event-extraction)
- [Deprecated technologyId in a technology bundle processor](#deprecated-technologyid-in-a-technology-bundle-processor)
- [Processor ID too short](#processor-id-too-short)
- [Processor ID too long](#processor-id-too-long)
- [sampleData field too long](#sampledata-field-too-long)

## Guiding principle — no silent changes

The translated artifact is a faithful representation of the tenant's production configuration. The goal of every fix is to produce an equivalent result in OpenPipeline — not to simplify, not to clean up, and not to delete. **Every change made to the artifact must be communicated to the user.** Changes that are purely mechanical (rename, quote style, redundant no-op removal) should be described before or as they are applied. Changes that could affect runtime behavior — even in edge cases — must be confirmed by the user before they are made. When in doubt, surface the tradeoff and let the user decide.

## Behavioral differences between classic and OpenPipeline

Keep these in mind when fixing non-processing stage issues (Step 4) and rewriting processing-stage DQL processors (Step 5):

| Aspect | Classic pipeline | OpenPipeline | What to check |
|---|---|---|---|
| Data types | String only | String, Number, Boolean | Review processors that relied on implicit string coercion — numeric and boolean values are now typed |
| Field name handling | Case-insensitive | Case-sensitive | Update matchers and field references to match the exact casing used at ingestion |
| Query language | LQL or DQL | DQL only | Translate any remaining LQL matchers — see [matchers.md](matchers.md) |
| Technology parsers | Built-in rules | Technology bundles | Add technology bundle processors to the pipeline artifact — see Step 2a in classic-pipeline.md |

## Duplicate dimensions in Davis event extraction

**Why it happens:** The event extraction translation maps classic event rule fields to Davis property keys (see the field mapping table in [translate-api.md](../translate-api.md)). If two different source fields in the original classic rule resolve to the same Davis property key after translation, the translated Davis processor ends up with duplicate `[strategy, key]` pairs, which the Settings API rejects.

**API error response:**

```json
{
  "code": 400,
  "error": {
    "code": 400,
    "message": "Constraints violated.",
    "constraintViolations": [
      {
        "path": "builtin:openpipeline.logs.pipelines/0/davis/processors/31/davis/properties",
        "message": "[strategy, key] must be unique",
        "parameterLocation": "PAYLOAD_BODY",
        "location": null
      }
    ]
  }
}
```

The `path` tells you which processor index is affected. Multiple processors can fail in one response — fix all of them before re-applying.

**How to fix:**

1. Locate the affected Davis processor by its index in `davis.processors`.
2. Find the duplicate `key` entries in its `properties` array.
3. Look up the original classic event rule by the processor's `id` in the source schema to understand what each property came from and why it mapped to the same key (refer to the field mapping in [translate-api.md](../translate-api.md)).
4. Compare the values of the duplicate entries:
   - **Values differ** — present both to the user and ask which one reflects the intended behavior. Remove the other.
   - **Values are identical** — inform the user that the same value was mapped twice and one entry will be dropped. Remove the duplicate.

**Before (invalid — `dt.event.source` appears twice with different values):**

```json
{
  "id": "<rule name>",
  "type": "davis",
  "enabled": true,
  "matcher": "<matcher>",
  "davis": {
    "properties": [
      { "key": "event.name",                  "strategy": "equals", "value": "<value>" },
      { "key": "event.type",                  "strategy": "equals", "value": "<value>" },
      { "key": "dt.davis.is_merging_allowed", "strategy": "equals", "value": "<value>" },
      { "key": "event.description",           "strategy": "equals", "value": "<value>" },
      { "key": "dt.event.source",             "strategy": "equals", "value": "<value A>" },
      { "key": "dt.event.source",             "strategy": "equals", "value": "<value B>" }
    ]
  }
}
```

Both entries came from `metadata` fields in the classic rule that translated to the same Davis property key. Since the values differ, ask the user which source dimension was the intended one and remove the other.

## Deprecated technologyId in a technology bundle processor

**Why it happens:** The `technologyId` values in [technology_bundles.json](../technology_bundles.json) can become deprecated on the API side when a bundle is superseded by a newer version. When you insert a technology bundle processor whose `technologyId` is no longer current and then validate or apply, the Settings API rejects the payload with a constraint violation pointing to the exact processor and field.

**API error response:**

```json
{
  "code": 400,
  "error": {
    "code": 400,
    "message": "Constraints violated.",
    "constraintViolations": [
      {
        "path": "builtin:openpipeline.logs.pipelines/0/processing/processors/0/technology/technologyId",
        "message": "Value is deprecated for reference 'technology', use 'azure_common_technology_v2' instead",
        "parameterLocation": "PAYLOAD_BODY",
        "location": null
      }
    ]
  }
}
```

The `path` encodes the processor index (e.g. `processors/0`). The `message` states the exact replacement value to use.

**How to fix:**

1. Identify the affected processor by its index in `processing.processors`.
2. Replace its `technology.technologyId` value with the replacement stated in the error message.
3. Re-run validate-only to confirm the violation is resolved.

If multiple processors are affected, all violations are returned in one response — fix all of them before re-applying.

## Processor ID too short

**Why it happens:** OpenPipeline requires processor `id` values to be between 4 and 100 characters. Classic pipeline rules with very short names produce processors that fail this constraint.

**API error response:**

```json
{
  "path": "builtin:openpipeline.logs.pipelines/0/processing/processors/26/id",
  "message": "Size must be between 4 and 100",
  "parameterLocation": "PAYLOAD_BODY",
  "location": null
}
```

**How to fix:** Locate the affected processor by its index and expand the `id` to at least 4 characters while keeping the name meaningful. The `description` field is not changed by the translation and still holds the original classic rule name, so the processor can always be identified by it even after the `id` is adjusted.

## Processor ID too long

**Why it happens:** OpenPipeline requires processor `id` values to be between 4 and 100 characters. Classic pipeline rules with very long names produce processors that exceed this constraint.

**API error response:**

```json
{
  "path": "builtin:openpipeline.logs.pipelines/0/processing/processors/5/id",
  "message": "Size must be between 4 and 100",
  "parameterLocation": "PAYLOAD_BODY",
  "location": null
}
```

**How to fix:**

1. Locate all affected processors by their indices.
2. Truncate each `id` to at most 100 characters. Prefer a natural word boundary (e.g. after a space, hyphen, or underscore) over a mid-word cut.
3. **Check for uniqueness within the stage** — after truncating, compare the trimmed `id` against all other processor IDs in the same stage. If two processors now share the same `id`, append a short disambiguating suffix (e.g. `_2`, `_3`) to make them unique.
4. Tell the user every `id` that was changed and, where a suffix was added, which processors shared a prefix and what suffix was applied to each.

The `description` field is not modified by the translation (by design), so it still holds the original classic rule name. Use it to identify the affected processors for the user — even after the `id` is trimmed, each processor can still be traced back to its source rule by `description`. The only exception is processing-stage DQL processors where the translation has overwritten `description` with a failure message.

## sampleData field too long

**Why it happens:** The `sampleData` field on a processor has an 8192-character limit. Classic pipeline rules with large sample payloads can exceed this limit on translation.

**API error response:**

```json
{
  "path": "builtin:openpipeline.logs.pipelines/0/processing/processors/36/sampleData",
  "message": "Size must be between 0 and 8192",
  "parameterLocation": "PAYLOAD_BODY",
  "location": null
}
```

**How to fix:** Before making any change, tell the user which processor(s) are affected and that their sample data will be shortened to fit the 8192-character limit. Confirm they are happy to proceed — sample data is used for the processor preview UI, not pipeline behavior, so the truncation has no runtime impact, but the user should be aware.

Once confirmed, truncate at a natural boundary rather than mid-string:

- If the value is a JSON array of record objects: drop trailing records until the serialized value fits within 8192 characters, then close the array (`]`). Keep at least one record.
- If the value is a JSON object or free-form multi-line text: truncate at the last complete line or top-level key that keeps the total within 8192 characters.
- Never truncate mid-escape-sequence or mid-JSON-key — the result must remain parseable.
