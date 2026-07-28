# OpenPipeline Transform Constraints

Mappings suggested by this skill are implemented as **OpenPipeline processors** at ingest. OpenPipeline runs a **restricted subset of DQL** — fewer commands and fewer functions than the DQL you use to *query* `fetch logs` in Grail. A transform that is valid in a Grail query is **not** guaranteed to be valid in an OpenPipeline processor.

Apply these constraints whenever you propose a transform for a buried `content` field or any other extraction rule.

**Authority:** the live Dynatrace documentation is the source of truth for the exact OpenPipeline command and function set. Do **not** assume a full-DQL function is available in OpenPipeline — verify against the references below before relying on it.

- Commands: https://docs.dynatrace.com/docs/platform/openpipeline/reference/dql/openpipeline-dql-commands
- Functions: https://docs.dynatrace.com/docs/platform/openpipeline/reference/dql/openpipeline-dql-functions
- Operators: https://docs.dynatrace.com/docs/platform/openpipeline/reference/dql/openpipeline-dql-operators
- Matcher: https://docs.dynatrace.com/docs/platform/openpipeline/reference/dql/dql-matcher-in-openpipeline

## TOC

- [Supported processing commands](#supported-processing-commands)
- [Supported function classes](#supported-function-classes)
- [Two field sources](#two-field-sources-root-level-fields-and-the-content-blob)
- [`content` field extraction](#content-field-extraction--do-not-use-parsejson)
- [Iterative operators](#iterative-operators--per-element-array-processing)
- [Matching criteria (processor gating)](#matching-criteria-processor-gating)
- [How to apply](#how-to-apply)

---

## Supported processing commands

| Command | Use |
|---|---|
| `parse` | Parse a field with a DPL pattern into one or more fields |
| `fields` / `fieldsKeep` | Keep only the specified fields |
| `fieldsAdd` | Evaluate an expression and append or replace a field |
| `fieldsRename` | Rename a field |
| `fieldsRemove` | Remove fields |
| `fieldsFlatten` | Extract/flatten fields from a nested record |

Commands outside this set (`fetch`, `filter`, `summarize`, `sort`, `dedup`, `join`, `lookup`, `makeTimeseries`) are query/aggregation constructs — do not propose them as ingest transforms.

---

## Supported function classes

| Class | Notes |
|---|---|
| String | `concat`, `contains`, `replacePattern`, `splitString`, `trim`, `lower`, `upper`, `substring`, `matchesPhrase`, `matchesValue`, and others |
| Conversion / cast | `toString`, `toLong`, `toDouble`, `toBoolean`, `toTimestamp`, `toDuration`, `toIp`, `asString`, `asLong`, `asIp`, `asRecord`, `asArray`, and others |
| Conditional | `coalesce`, `if` |
| Boolean | `isNull`, `isNotNull`, `isTrueOrNull`, `isFalseOrNull` |
| Array | `arraySort`, `arraySum`, `arrayAvg`, `arrayDistinct`, `arrayRemoveNulls`, `arraySize`, and others |
| Network | `ip()`, `ipIn`, `ipIsPrivate`, `isIpV4`, `isIpV6`, and others |
| Time | timestamp operations, duration creation, date extraction |
| Math | `abs`, `sqrt`, `round`, `log`, `power`, and others |
| Hash / bitwise | `hashMd5`, `hashSha256`, bitwise operators |
| General | `in`, `exists`, `record` |

**Not available:** `parseJson`, `jsonPath`, and any aggregation/query function that requires `summarize` (e.g. `count`, `sum`, `avg`) — processors are per-record; there is no grouping or aggregation stage.

**Confirmed idioms (from production processors):** `timestampFromUnixMillis(toLong(x))` (ms epoch → timestamp), `toLong(x)` (status codes / epochs), `array(toIp(x))` (→ `ipAddress[]`), `concat(a, " ", b)`, `coalesce(a, b, …)` (fallback across source paths), nested `if(cond, x, else: if(cond2, y, else: z))`, and operators `==`/`!=`/`>=`/`>`/`<=`/`<`. Assign the built-in `timestamp` to `audit.time` when no vendor timestamp is available. `matchesValue(field, "*pat*")` is usable **inside `fieldsAdd`** (to compute a boolean flag), not only as a matcher. Compute reusable values into a `_`-prefixed helper field and `fieldsRemove` it when done. Backtick-quote field names with dots/hyphens (`` `audit.action` ``, `` `http.request.header.user-agent` ``).

---

## Two field sources: root-level fields and the `content` blob

An ingested log event can expose vendor data in **two places at once** — they are not mutually exclusive:

- **Root-level fields** — some fields are already parsed to the top level of the event at ingest (e.g. `service.name`, `company.name`). Reference them **directly** in `fieldsAdd`, backtick-quoting names with dots or hyphens: `` fieldsAdd `object.id` = `service.name` ``. No parsing needed.
- **The `content` field** — always carries the **full raw (unparsed)** vendor payload. Parse it to reach anything not already at root level.

Prefer a root-level field when the value is already there; parse `content` for buried values.

## `content` field extraction — do NOT use `parseJson`

The natural instinct is `parseJson content, prefix:"c."` — but **`parseJson` is not an OpenPipeline function**.

**Canonical OpenPipeline-valid pattern:**

```dql-snippet
| parse content, "json:content"                 // json DPL token is case-insensitive; parses into a record
| fieldsAdd audit.identity = content[user_name] // subscript: content[key] or content[key][subkey] for nested
| fieldsAdd loglevel = if(content[response] == "DENIED", "ERROR", else: "INFO")
// ... other fieldsAdd statements ...
```

Key points:
- **DPL literal** `"json:<varname>"` — the `json`/`JSON` token is case-insensitive. Two conventions: parse into `content` itself (`"json:content"`, overwrites the working field; the persisted event keeps the raw payload so any processor can re-parse) or into a new record (`"JSON:c"`, then `fieldsRemove c` in cleanup).
- Use **subscript notation** `content[key]` or `content[key][subkey]` (any depth) for nested access — no `fieldsFlatten` needed for targeted extraction.
- **Do not assume a parsed record persists across processors.** Because `content` always retains the raw payload, re-parse `content` in each processor that needs buried values (production integrations commonly do exactly this).
- **`fieldsFlatten content, prefix:"c."`** is an alternative when every JSON key should be promoted to `c.<key>` — less common when targeting specific fields.

---

## Iterative operators — per-element array processing

Three operators are available for per-element array transforms:

| Operator | Use |
|---|---|
| `iAny` | Check a per-element boolean expression; true if satisfied at least once |
| `iCollectArray` | Collect per-element expression results into a new array |
| `iIndex` | Access the current element's index |

Use `iCollectArray` when casting an array of strings to a typed array (e.g. `ipAddress[]` fields like `actor.ips`).

---

## Matching criteria (processor gating)

Processors fire only for records matching a gating condition. Available:

| Feature | Notes |
|---|---|
| `matchesValue(field, "pattern")` | Supports `*` wildcards |
| `matchesPhrase(field, "phrase")` | Case-insensitive; wildcards at phrase start/end only |
| `isNull(field)` / `isNotNull(field)` | Null testing |
| `AND`, `OR`, `NOT` | Logical combination |
| Numeric comparators | `<`, `>`, `==`, `<=`, `>=` |
| `iAny(condition)` | Per-element condition check |

**Gotcha:** `==` is case-sensitive with no wildcards — use `matchesValue()` when casing could vary.

---

## How to apply

- **Workflow A (suggest):** every Transform column entry for a buried `content` field must be expressible with `parse` → `fieldsFlatten`/subscript (not `parseJson`/`jsonPath`). Use `fieldsAdd` with supported function classes only.
- **Workflow B (validate):** flag any provided transform that uses `parseJson`, `jsonPath`, or an unavailable function/command as a major discrepancy and propose the valid alternative.
