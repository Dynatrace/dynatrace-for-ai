# Intake And Constraints

## Contents

- [Intake And Output](#intake-and-output)
- [OpenPipeline Constraints](#openpipeline-constraints)
- [Object Type Expectations](#object-type-expectations)


---

## Intake And Output


Use this checklist before building or validating mappings.

## TOC

- [Intake Checklist](#intake-checklist)
- [Required Follow-up Questions](#required-follow-up-questions)
- [Output Contract — Workflow A (Suggestion)](#output-contract--workflow-a-suggestion)
- [Output Contract — Workflow B (Validation)](#output-contract--workflow-b-validation)
- [Confidence Tiers](#confidence-tiers)

---

## Intake Checklist

1. Collect vendor raw API payload samples (JSON).
2. Confirm sample count per finding type:
   - Minimum recommended: 5 samples per finding type.
   - Better: 20+ samples including edge cases (nulls, partial payloads, each severity).
3. Confirm event.type coverage scoped to finding class:
   - Detections: `DETECTION_FINDING` samples.
   - Vulnerabilities: `VULNERABILITY_FINDING` AND `VULNERABILITY_SCAN` samples.
   - Compliance: `COMPLIANCE_FINDING` AND `COMPLIANCE_SCAN` samples.
4. Confirm provider metadata values:
   - `event.provider`
   - `product.vendor`
   - `product.name`
5. Collect all expected `object.type` values from the vendor.
6. Confirm presence or absence of scan references (`scan.id`, `scan.name`) for V/C findings.
7. Ask for known null/missing field behavior from vendor docs.
8. Ask for at least one payload per severity band if available.
9. For vulnerability findings: confirm whether `component.name` / `software_component.name` are provided.
10. For code artifact findings: confirm `artifact.path`, `artifact.repository`, `code.filepath` availability.
11. For container image findings: confirm `container_image.name` / `container_image.id` availability.
12. For Workflow B (validation): classify validation target:
   - Final ingested event
   - Theoretical mapping (pre-ingestion)
13. If validating a final ingested event, identify where the raw vendor payload is recoverable. Note that `dt.raw_data` is **always** populated by OpenPipeline (full ingested envelope), so its presence alone is not a mapping signal — the question is which field carries raw *vendor* content:
   - `event.original_content` for **extension-based / pull integrations** (carries the original vendor API response separately from the SD-mapped envelope)
   - `dt.raw_data` for **push-based integrations** (the envelope itself is the raw ingested vendor payload)
14. If validating a theoretical mapping, confirm that `event.original_content` is not expected as an explicit mapping. (`dt.raw_data` is platform-generated and is never an explicit mapping in any mode.)
15. Ask whether to run optional real-environment validation queries.
16. If yes, collect:
   - `event.provider` to validate
   - time window (start with `24h`)
   - execution method: live DQL execution

## Required Follow-up Questions

Ask these when information is missing:

1. "Please provide 5-20 raw JSON payloads per finding type from the source product."
2. "Which fields are guaranteed by the vendor, and which are optional or context-dependent?"
3. "What are all possible `object.type` values in the payload?"
4. "What `finding.type` values are used and what do they mean?"
5. "How does the vendor severity string map to your expected risk model?"
6. "Do scan findings (`VULNERABILITY_SCAN` or `COMPLIANCE_SCAN`) carry the same `scan.id` as the corresponding findings?"
7. "Do you have examples of payloads with missing or null values from production?"
8. "Are you validating a final ingested event or a theoretical mapping draft?"
9. "If final ingested event: is original API data in `dt.raw_data` or `event.original_content`?"
10. "Do you want optional runtime validation against real tenant data?"
11. "Which provider and time window should runtime queries use?"

## Output Contract — Workflow A (Suggestion)

**Phase 1** (present first, wait for approval):

1. Mapping table: `Source Field | Target Field | Transform | Required | Sample Value | Notes`.
2. Gap summary: required fields that could not be mapped and why.
3. Discrepancy list grouped by severity: critical → major → minor.
4. Confidence tier + missing-evidence note.

**Phase 2** (only after user approves Phase 1):

1. One sample mapped JSON object per `finding.type`.
2. Inline annotations for every applied transform.
3. Note any fields populated with hardcoded constants or auto-derived values.
4. Document any vendor-specific namespace fields (e.g., `wiz.*`, `qualys.*`) included, showing source field and value rationale.

## Output Contract — Workflow B (Validation)

1. Diff-highlighted mapping table: `Source Field | Current Target | Suggested Target | Transform | Status (✅/⚠/➕/❌) | Reason`.
2. Event-type coverage matrix.
3. Required-field pass/fail matrix (see `validation-policy-and-reporting.md § Validation Rules`).
4. Scan reference check for V/C findings.
5. `object.type` namespace pass/fail matrix (see `validation-policy-and-reporting.md § Object-Type Namespace Requirements`).
6. `finding.type` namespace pass/fail matrix.
7. Sample-value comparison notes against `samples/` (conditional — include only when samples were consulted to resolve a specific doubt; omit when primary references were sufficient).
8. Discrepancy list grouped by severity: critical → major → minor.
9. Confidence tier and missing-evidence note.
10. Validation source note:
   - Final ingested event: include which raw-content field was used (`dt.raw_data` or `event.original_content`).
   - Theoretical mapping: explicitly state that platform-generated raw-content fields were not required.
   - Theoretical mapping: explicitly state that ingest-generated fields (`event.id`, `timestamp`) were not required as explicit mappings.
11. Vendor-specific namespace validation:
   - Confirm all vendor-namespace fields (e.g., `wiz.*`) are properly namespaced and documented.
   - List any valuable vendor-specific enrichments included in the mapping.
   - Vendor-namespace fields are not flagged as "unknown" — they represent the expected pattern.
12. Optional runtime validation section (when enabled):
   - provider and window used
   - query result summary (counts)
   - non-zero mismatch/orphan/invalid checks with `warning` vs `fail` classification and suggested fixes
   - scan-related runtime checks (`missing scans`, `orphans`, `missing scan-reference coverage`) are warning-tier unless a stricter policy is explicitly requested
   - sample events per relevant `object.type` fetched with `| limit 1`
   - sample-event structure validation outcome
   - raw-payload-backed mapping suggestions for missing required fields (for example `object.name`)
   - runtime status section title must be `Validation Summary`
   - runtime status output must be a table, not a list
13. If required fields are missing, include a mapping-backfill table with:
   - missing target field
   - source evidence (in order: `dt.raw_data`, then `event.original_content`, then vendor sample if neither payload field is available)
   - candidate source path
   - transform rule
   - confidence and notes

## Confidence Tiers

- `high`: Required fields complete, object.type rules pass, finding.type rules pass, scan references present for V/C, value consistency passes across broad samples.
- `medium`: Core mapping complete but gaps in optional namespaces or type-specific fields, or fewer than 5 samples per type.
- `low`: Missing required fields, absence of scan events for V/C, or too few representative samples.


---

## OpenPipeline Constraints


Mappings suggested by this skill are implemented as **OpenPipeline processors** at ingest. OpenPipeline runs a **restricted subset of DQL** — fewer commands and fewer functions than the DQL you use to *query* `security.events` in Grail. A transform that is valid in a Grail query is **not** guaranteed to be valid in an OpenPipeline processor.

Apply these constraints whenever you propose a value in the **Transform** column of a mapping table (Workflow A suggestion, Workflow B diff). A suggested transform that cannot be expressed with OpenPipeline-available DQL is not actionable.

**Authority:** the live Dynatrace documentation is the source of truth for the exact OpenPipeline command and function set. Do **not** assume a full-DQL function is available in OpenPipeline — verify against the reference below before relying on it.

- Commands: https://docs.dynatrace.com/docs/platform/openpipeline/reference/dql/openpipeline-dql-commands
- Functions: https://docs.dynatrace.com/docs/platform/openpipeline/reference/dql/openpipeline-dql-functions
- Operators: https://docs.dynatrace.com/docs/platform/openpipeline/reference/dql/openpipeline-dql-operators
- Matcher: https://docs.dynatrace.com/docs/platform/openpipeline/reference/dql/dql-matcher-in-openpipeline

## TOC

- [Supported processing commands](#supported-processing-commands)
- [Supported function classes](#supported-function-classes)
  - [Confirmed functions and idioms](#confirmed-functions-and-idioms-from-production-processors)
- [Iterative operators](#iterative-operators--per-element-array-processing)
- [Matching criteria (processor gating)](#matching-criteria-processor-gating)
- [Two field sources](#two-field-sources-root-level-fields-and-the-content-blob)
- [`jsonPath()` is not available](#jsonpath-is-not-available--extract-nested-json-another-way)
- [Producing `ipAddress`-typed values](#producing-ipaddress-typed-values)
- [Processor chain architecture](#processor-chain-architecture)
- [How to apply](#how-to-apply)

---

## Supported processing commands

OpenPipeline DQL processors support this command set:

| Command | Use |
|---|---|
| `parse` | Parse a field with a DPL pattern into one or more fields |
| `fields` / `fieldsKeep` | Keep only the specified fields |
| `fieldsAdd` | Evaluate an expression and append or replace a field |
| `fieldsRename` | Rename a field |
| `fieldsRemove` | Remove fields |
| `fieldsFlatten` | Extract/flatten fields from a nested record |

Commands outside this set (e.g. `fetch`, `filter`/`summarize` as query stages, `join`, `lookup`, `makeTimeseries`, `dedup`, `sort`) are query/aggregation constructs and are not part of the processor transform model — do not propose them as ingest transforms.

---

## Supported function classes

OpenPipeline processors support these function classes. Defer to the live functions reference (URL above) for the exact function list within each class — do not assume a Grail function is available without checking:

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

**Not available:** `parseJson`, `jsonPath`, and any aggregation/query function that requires `summarize` (e.g. `count`, `sum`, `avg`, `countDistinctExact`) — processors are per-record; there is no grouping or aggregation stage.

### Confirmed functions and idioms (from production processors)

| Function / idiom | Use |
|---|---|
| `timestampFromUnixMillis(toLong(field))` | Millisecond-epoch string/number → `timestamp` (e.g. `audit.time`) |
| `toLong(field)` | String → long (epoch values, HTTP status codes, numeric fields) |
| `toIp(field)` / `ip(field)` | String → `ipAddress` (invalid → `null`) |
| `array(value)` | Wrap a single value into a one-element array — e.g. `array(toIp(x))` → `ipAddress[]` |
| `stringLength(field)` | String length; use as an empty-string guard before a cast |
| `concat(a, " ", b)` | String concatenation with a literal separator |
| `coalesce(a, b, c, …)` | First non-null value — fallback resolution across multiple source paths |
| `matchesValue(field, "pat")` | Wildcard value match — **usable inside `fieldsAdd`** to compute a boolean, not only in the matcher (e.g. `fieldsAdd _is_x = matchesValue(\`service.name\`, "*.security.audit")`) |
| built-in `timestamp` | The event's ingest timestamp — assign to `audit.time` when no better source exists |

**Operators in expressions:** `==`, `!=`, `>=`, `>`, `<=`, `<`, `AND`, `OR`, `NOT`, and nested `if(cond, x, else: if(cond2, y, else: z))` for multi-branch logic.

**Helper fields:** compute a value once into a `_`-prefixed temporary field, reuse it across several `fieldsAdd` statements, then `fieldsRemove` it — within the same processor if it is not needed downstream, or in the terminal cleanup processor otherwise.

**Backtick-quoting:** field names containing a hyphen or other non-identifier character **must** be backtick-quoted (`` `http.request.header.user-agent` ``). Dotted names work with or without backticks; backtick-quoting all dotted SD field and source names (`` `audit.action` ``, `` `service.name` ``) is a safe, consistent convention.

---

## Iterative operators — per-element array processing

OpenPipeline provides three iterative operators for expressions that operate element-by-element over an array:

| Operator | Use |
|---|---|
| `iAny` | Check a per-element boolean expression; returns `true` if it was true for at least one element |
| `iCollectArray` | Collect the results of a per-element expression into a new array |
| `iIndex` | Access the current element's index within an iterative expression |

Use `iCollectArray` when you need to apply a transform (e.g. type cast) to every element of an array field. For example, casting a **string-array** source to `ipAddress[]` (SD fields like `host.ip`, `actor.ips`): apply `toIp()` per-element via `iCollectArray` rather than casting the whole array at once. Confirm the exact expression syntax against the operators reference above — do not improvise the iterative syntax.

(When the source is a **single** IP string rather than an array, use the simpler `array(toIp(x))` form shown in **§ Producing `ipAddress`-typed values**; `iCollectArray` is for when the source itself is already an array.)

---

## Matching criteria (processor gating)

Each processor in the chain fires only for events matching its **matching criterion** — a DQL expression evaluated per record. The matcher surface is a subset of full DQL:

**Available:**

| Feature | Notes |
|---|---|
| `matchesValue(field, "pattern")` | Value matching; supports `*` wildcards |
| `matchesPhrase(field, "phrase")` | Phrase matching; case-insensitive; wildcards at phrase start/end only — not mid-string |
| `isNull(field)` / `isNotNull(field)` | Null testing |
| `AND`, `OR`, `NOT` | Logical combination |
| Numeric / equality comparators (`<`, `>`, `==`, `!=`, `<=`, `>=`) | Quantitative and equality comparisons |
| `iAny(condition)` | Check condition across array elements |

**Restrictions and gotchas:**

- `==` in a matching criterion is **case-sensitive** with **no wildcard support** — for case-insensitive or pattern matching, use `matchesValue()`/`matchesPhrase()` instead.
- `matchesPhrase()` wildcards are boundary-only (`*phrase` or `phrase*`), not mid-string (`ph*se` is not valid).
- `matchesValue()` and `matchesPhrase()` are also valid inside `fieldsAdd` expressions (to compute a boolean field), not just as processor gating criteria.

The processor-chain examples earlier in this doc (e.g. `matches: object.type == "HOST"`, `matches: event.type == "VULNERABILITY_FINDING"`) use exact equality — correct for these enum values. Use `matchesValue()` when casing or exact spelling could vary.

---

## Two field sources: root-level fields and the `content` blob

An ingested event can expose vendor data in **two places at once** — they are not mutually exclusive:

- **Root-level fields** — some vendor fields are already parsed to the top level of the event by ingest (e.g. `service.name`, `company.name`). Reference them **directly** in `fieldsAdd`, backtick-quoting names with dots or hyphens: `` fieldsAdd `object.id` = `service.name` ``. No parsing needed.
- **The `content` field** — always carries the **full raw (unparsed)** vendor payload. Parse it to reach anything not already at root level.

Prefer a root-level field when the value you need is already there; parse `content` for buried values.

## `jsonPath()` is not available — extract nested JSON another way

`jsonPath()` is **not enabled** in OpenPipeline processors. Do not suggest a transform that calls `jsonPath()` (or `parseJson` — also unavailable) to pull a value out of a nested JSON payload.

**Canonical OpenPipeline-valid pattern for extracting values from a serialized JSON field:**

```dql-snippet
parse content, "json:content"                          // parse the JSON string in content into a structured record
| fieldsAdd audit.action   = content[event][OperationName]  // subscript access for nested keys
| fieldsAdd audit.identity = content[user_name]             // direct top-level key access
```

- **DPL literal:** `"json:<varname>"` — the `json`/`JSON` type token is **case-insensitive** (both `"json:content"` and `"JSON:c"` are used in production). `<varname>` names the parsed record; two conventions are in use:
  - **Parse into `content` itself** (`"json:content"`) — overwrites the working `content` field with the structured record; the persisted event still retains the raw payload, so any processor can re-parse.
  - **Parse into a new variable** (`"JSON:c"`) — keeps a separate record `c`; remove it in the terminal cleanup processor with `fieldsRemove c`.
- **Do not** use `parseJson` — it is not an OpenPipeline function.
- Use **subscript notation** `content[key]`, `content[key][subkey]`, or deeper (`content[data_changed][added][id]`) directly in `fieldsAdd`. `fieldsFlatten` is not needed for targeted field access.
- **Do not assume a parsed working record persists across processors.** Both patterns exist (a separate `c` variable can persist; `content` re-parsing is per-processor). Because `content` always retains the raw payload, **re-parsing `content` in each processor that needs it is always safe** — prefer that over assuming an earlier processor's parse is still available.
- **`fieldsFlatten content, prefix:"c."`** is an alternative if you want *every* JSON key promoted to a `c.<key>` top-level field — useful when the key set is unknown at authoring time; not needed when targeting specific fields by subscript.

**Describe the mechanism in the Transform column** using the confirmed form (e.g. "`parse content, "json:content"` → `content[metadata][eventType]`") rather than a generic "jsonPath alternative."

---

## Producing `ipAddress`-typed values

IP fields must carry the SD `ipAddress` / `ipAddress[]` type (see `validation-policy-and-reporting.md § Value and Type Checks` rule 16 and the `host.ip` / `actor.ips` / `client.ip` rows in `validation-policy-and-reporting.md § Known Discrepancies`). OpenPipeline's network function **`toIp()`** (also `ip()`) parses and casts a string into the `ip` type (invalid input yields `null`, not an error) — this is the OpenPipeline-valid way to emit an IP-typed value.

**Confirmed production patterns:**

```dql-snippet
// Single ipAddress field, guarding against empty / sentinel values:
| fieldsAdd client.ip = if(stringLength(content[UserIp]) > 0, toIp(content[UserIp]), else: null)
| fieldsAdd client.ip = if(content[ip_address] != "UNKNOWN", toIp(content[ip_address]), else: null)

// ipAddress[] field — wrap the single cast value in array():
| fieldsAdd actor.ips = if(stringLength(content[UserIp]) > 0, array(toIp(content[UserIp])), else: null)
```

Guard against empty strings or vendor sentinels (`""`, `"UNKNOWN"`) with `stringLength(x) > 0` or `x != "UNKNOWN"` before casting, so absent IPs become `null` rather than a failed cast. For a **source that is already an array of strings**, cast each element with `iCollectArray` + `toIp()` (see § Iterative operators).

Do not leave an IP value as a plain string when the SD target is `ipAddress` — a plain string assignment fails the rule-16 type check.

---

## Processor chain architecture

An integration is **not** a single monolithic processor. Design it as an ordered chain of processors, each with a **matching criterion** that gates when it runs:

```
Processor 1 — Generic (matches: all events from this provider)
  → maps common SD fields shared across all event types
  → parses content when common fields are buried (each processor re-parses content as needed)

Processor 2 — Per-subcategory (matches: e.g. object.type == "HOST")
  → adds object-type-specific namespace fields (host.*, aws.*, k8s.*, etc.)
  → references root-level fields directly; re-parses content if it needs buried values

Processor 3 — Per-subcategory (matches: e.g. event.type == "VULNERABILITY_FINDING")
  → adds finding-type-specific fields (software_component.*, vulnerability.*, etc.)

... (one processor per distinct sub-category that needs separate field logic)

Processor N — Cleanup (matches: all events from this provider)
  → removes intermediate fields that were created for processing but are not SD fields
     (e.g. temporary parse results, raw vendor-namespace fields the integration no longer needs)
```

**Key properties of this model:**

- **Sequential execution:** processors run in order; SD fields written by an earlier processor are available to later processors. **Do not** assume a *parsed working record* (e.g. a `content`/`c` JSON parse) is still present downstream — because `content` always retains the raw payload, a processor that needs buried values should re-parse `content` itself (production integrations commonly re-parse `content` in each processor that reads it).
- **Matching criteria gate execution:** each processor fires only for events that match its condition. Use this to scope object-type-specific or finding-type-specific logic rather than putting conditional `fieldsAdd` expressions inside a single processor.
- **Cleanup is a dedicated last processor:** non-SD intermediate fields — raw vendor keys used only as parse inputs, helper fields created mid-chain — must be removed in a terminal cleanup processor using `fieldsRemove`. Do not leave them in the ingested event.

**When suggesting a processor chain (Workflow A):**

Present the processors as an ordered list, not a flat mapping table. For each processor:
1. Name: descriptive label (e.g. `generic`, `host-namespace`, `vulnerability-namespace`, `cleanup`)
2. Matching criterion
3. Commands/fields it adds or transforms
4. Note which fields it inherits from an earlier processor in the chain (no re-parsing needed)

---

## How to apply

- **Workflow A (suggest):** propose a processor chain (generic → per-subcategory → cleanup), not a single processor. Only use transforms expressible with the commands/functions listed above. If a vendor value lives inside a nested JSON blob, parse it in the generic processor via `parse` → `fieldsFlatten`/subscript access — not `jsonPath()` — so subcategory processors receive structured fields.
- **Workflow B (validate):** flag any provided transform that relies on an OpenPipeline-unavailable construct — most commonly `jsonPath()` — as a discrepancy and suggest the OpenPipeline-valid alternative. Also flag a single-processor design when the integration has multiple `object.type` or `event.type` categories — recommend splitting per the chain architecture above. See `validation-policy-and-reporting.md § Value and Type Checks`.


---

## Object Type Expectations


Validate `object.type` and expected companion fields and namespaces.

Baseline: local samples in `../samples/`, field taxonomy in `../references/semantic-reference.md § Data Model Notes`.

## Vendor-Reported `object.type` Values Are Accepted

`object.type` is a **vendor-extensible** field. Whatever the vendor reports as the resource type (for example `AWS::EC2::Instance`, `AWS::IAM::Role`, `AWS::ECS::Cluster`, vendor-specific resource taxonomies) is acceptable as-is. **Do not flag these as discrepancies.**

Smartscape-style canonical enum values (`AwsEc2Instance`, `AwsEksCluster`, `AwsS3Bucket`, etc.) are required **only when the integration opts into runtime contextualization** for an officially supported type — i.e., when downstream consumers (dashboards, segments, joins to `dt.smartscape.*` — or its deprecated `dt.entity.*` alias) need the canonical enum to function. For other types, leave the vendor value untouched.

Validation behavior:

| Situation | Verdict |
|---|---|
| Vendor-reported `object.type` value (e.g. `AWS::EC2::Instance`) on an integration that does not opt into Smartscape joins | ✅ accept — pass |
| Vendor-reported value where the integration explicitly intends Smartscape contextualization for an officially supported type | ⚠ recommend normalization to the canonical enum (e.g. `AwsEc2Instance`); preserve the original under a vendor-namespace field if needed |
| Officially supported type emitted with a malformed canonical value (typo, wrong case) | ⚠ minor — fix typo |
| `object.type` is null or empty | ❌ critical — required field missing |

## Smartscape Enrichment Fields Are Post-Ingest, Not Mapping Inputs

`dt.smartscape.*`, `dt.entity.*`, and `dt.source_entity` are **post-ingest runtime enrichment** fields populated by OpenPipeline after the integration has emitted the event. They are **NOT required in the initial mapping** (Workflow A) and **NOT validated as static-mapping requirements** (Workflow B1).

Where they belong:

| Workflow | Treatment |
|---|---|
| Workflow A — Suggest mapping | Do not include `dt.smartscape.*` / `dt.entity.*` / `dt.source_entity` in the suggested mapping. Integrations don't emit these — OpenPipeline writes them at ingest. |
| Workflow B1 — Static validation | Do not flag absence as a discrepancy. They are not part of the mapping contract. |
| Workflow B2 — Runtime validation | Check whether enrichment is present on ingested events. **Missing enrichment is not a blocker — it is informational.** On-ingest enrichment is the most efficient mechanism, so absence at runtime is worth noting but not failing. |

When runtime enrichment matters most:

- **K8s detection findings** — expect `dt.smartscape.k8s_cluster`, `dt.smartscape.k8s_pod`, `dt.smartscape.k8s_node`, etc. Missing → **warn** (most consumers expect K8s context).
- **Cloud detection findings** (AWS / Azure / GCP) — expect `dt.smartscape.aws_ec2_instance`, `dt.smartscape.aws_eks_cluster`, etc. Missing → **warn**.
- **Other finding types** — missing enrichment is **info** only.

`dt.entity.*` is the **deprecated** alias namespace; `dt.smartscape.*` is the canonical forward-going namespace (per `dt-dql-essentials/references/semantic-dictionary.md` § Legacy Mapping). At runtime:

| Observed | Verdict |
|---|---|
| Both `dt.smartscape.*` and `dt.entity.*` populated | ✅ pass |
| Only `dt.smartscape.*` populated (no `dt.entity.*`) | ✅ pass — completely OK; legacy namespace not required |
| Only `dt.entity.*` populated (no `dt.smartscape.*`) | 🟡 warn — recommend migrating to `dt.smartscape.*` |
| Neither populated on a K8s / cloud detection | 🟡 warn — see rule above |
| Neither populated on other finding types | ℹ info |

For the runtime DQL pack that exercises this check, see `runtime-validation.md § 14) Entity Enrichment Coverage`.

## TOC

- [CODE_ARTIFACT](#code_artifact)
- [CONTAINER_IMAGE](#container_image)
- [HOST](#host)
- [PROCESS / PROCESS_GROUP](#process--process_group)
- [CONTAINER / K8S_POD](#container--k8s_pod)
- [Cloud Types](#cloud-types)
- [URL](#url)
- [Output Format](#output-format)

---

## CODE_ARTIFACT

Seen in: `samples/external-vulnerabilities-code-artifact.json` (Snyk, SonarQube, Sonatype, GitLab, GitHub Advanced Security).

| Field | Required | Notes |
|---|---|---|
| `artifact.name` | yes | File or project name |
| `artifact.id` | yes (if object.id is not enough) | Stable artifact identity |
| `artifact.path` | yes | Relative path in repository |
| `artifact.repository` | yes | Repository identifier |
| `artifact.filename` | recommended | Just the filename without path |
| `artifact.version` | optional | Artifact version if versioned |
| `code.filepath` + `code.line.number` | required when `finding.type` is CODE_ISSUE/CODE_VULNERABILITY/EXPOSED_SECRET | Source location of the finding |

**Note:** `object.id` for CODE_ARTIFACT is often the project UUID (Snyk) or a composite path string. It must be stable across scans for deduplication.

---

## CONTAINER_IMAGE

Seen in: `samples/external-vulnerabilities-container-image.json`.

| Field | Required | Notes |
|---|---|---|
| `container_image.digest` | **yes — primary identifier** | SHA256 image digest (e.g. `sha256:01fa9ee3...`). The only immutable identifier for a container image; required for deduplication across scans and for `dt.smartscape.*` enrichment at runtime. Flag as **major** if absent. Check `event.original_content` impact paths and applicability details — vendors routinely expose digests there even when not surfaced in the top-level payload. |
| `container_image.name` | yes | Image name without tag (e.g. `online-boutique/checkoutservice`); extract from `object.name` before the colon |
| `container_image.tags` | yes | **Array** of image tags (e.g. `["1.0.0"]`); SD field is plural and array-typed. Extract from `object.name` after the colon and wrap in an array, or map directly from the vendor array if available. |
| `container_image.registry` | recommended | Registry hostname (e.g. `dtta.jfrog.io`); often derivable from `jfrog.tenant`, `object.id`, or vendor API metadata |
| `container_image.id` | optional | Vendor-internal image ID if different from digest; do not use as a substitute for `container_image.digest` |

**Note:** Container image findings often lack Smartscape entity IDs at runtime — `dt.smartscape.*` enrichment is post-ingest (see top-of-file rule) and depends on whether the image digest can be matched. Don't include `dt.smartscape.*` in the integration's emitted mapping; check coverage at runtime instead.

**Validation priority for CONTAINER_IMAGE namespace:** check `container_image.digest` first. Absence of `container_image.name`/`container_image.tags` is always flaggable, but a missing digest is the more critical gap because it blocks entity matching and scan deduplication.

---

## HOST

`HOST` is the Smartscape canonical type for generic-host findings — typically traditional vulnerability scans (Qualys, Tenable) targeting a host whose identity is its hostname/IP/FQDN.

This section documents what fields to expect **when `object.type = HOST` is the value the vendor emits or the integration chooses to use**. It is NOT a prescription that all host-shaped findings must be mapped to `HOST`. Per the vendor-reported-values rule at the top of this file, integrations preserve the value the vendor reports (e.g., `AWS::EC2::Instance`, vendor-specific resource taxonomies). Only normalize to a Smartscape canonical value when the integration explicitly opts into runtime contextualization for that officially supported type.

Seen in: `samples/external-vulnerabilities-host.json` (Qualys, Tenable on-prem hosts).

| Field | Required | Notes |
|---|---|---|
| `host.name` OR `host.ip` | at least one required | Primary host identity |
| `host.fqdn` | recommended | Fully qualified domain name |
| `host.ip` | recommended | `ipAddress[]` — list of IPv4 or IPv6 addresses |
| `os.name` | recommended | OS for vulnerability triage context |

---

## PROCESS / PROCESS_GROUP

Seen in: `samples/dynatrace-detections-rap.json`.

For mapping (Workflow A / B1):

| Field | Required | Notes |
|---|---|---|
| `host.name` | recommended | Host context |
| Vendor process identity (`process.executable.name`, `process.pid`, etc.) | recommended where vendor exposes them | OS-level process identity |

`dt.entity.process_group`, `dt.entity.process_group_instance`, `dt.entity.host`, `dt.source_entity`, `dt.smartscape.process` are **post-ingest runtime enrichment** — see top-of-file rule. Do not include them in the mapping. Validate their presence in Workflow B2 if the integration is expected to be Smartscape-correlated.

---

## CONTAINER / K8S_POD

Seen in: `samples/dynatrace-detections-automated.json` (K8s CONTAINER type).

| Field | Required | Notes |
|---|---|---|
| `k8s.cluster.name` | yes | Cluster name or ID |
| `k8s.namespace.name` | yes | Namespace |
| `k8s.pod.name` OR `k8s.pod.uid` | yes | Pod identity |
| `k8s.cluster.uid` | recommended | Stable cluster identifier |

---

## Cloud Types

### AwsEc2Instance

`AwsEc2Instance` is one of several Smartscape canonical types for AWS resources. It is **not** the universal target for every AWS-shaped finding — AWS reports many resource taxonomies (`AWS::IAM::Role`, `AWS::ECS::Cluster`, `AWS::S3::Bucket`, `AWS::Lambda::Function`, `AWS::EKS::Cluster`, `AWS::RDS::DBInstance`, etc.), and the default rule is to preserve whatever value the vendor reports.

Use `AwsEc2Instance` only when the integration explicitly opts into Smartscape runtime contextualization for EC2 instances (joins to `dt.entity.*` / `dt.smartscape.aws_ec2_instance`). For all other AWS resource types — and for EC2 findings where Smartscape correlation isn't a goal — keep the vendor-reported `object.type` value (per the vendor-reported-values rule at the top of this file).

Seen in: `samples/external-detections.json` (GuardDuty via Security Hub).

| Field | Required | Notes |
|---|---|---|
| `aws.resource.id` | yes | Instance ID or ARN |
| `aws.region` | yes | AWS region |
| `aws.account.id` | recommended | AWS account |
| `aws.arn` | recommended | Full ARN |

`dt.smartscape.aws_ec2_instance` / `dt.smartscape_source.id` are **post-ingest runtime enrichment** — see top-of-file rule. Don't include in the mapping; check at runtime.

### AwsEksCluster

Seen in: `samples/external-detections.json` (GuardDuty via Security Hub).

| Field | Required | Notes |
|---|---|---|
| `aws.resource.id` | yes | Cluster ID or ARN |
| `aws.region` | yes | AWS region |
| `aws.account.id` | recommended | AWS account |

`dt.smartscape.aws_eks_cluster` is **post-ingest runtime enrichment** — see top-of-file rule. Don't include in the mapping; check at runtime.

---

## URL

Seen in: `samples/external-detections.json` (Akamai SIEM).

| Field | Required | Notes |
|---|---|---|
| `url.domain` | yes | Domain/host |
| `url.path` | yes | Request path |
| `url.port` | recommended | Port |
| `url.scheme` | recommended | Protocol |
| HTTP context fields | optional | Enrichment for WAF detections |

**Note:** `object.id` for URL findings typically uses `domain:port/path` composite format.

---

## Output Format

Report `object.type` checks using this table:

| object.type | Sample count | Required namespace present | Missing fields | Status |
|---|---|---|---|---|
| `CODE_ARTIFACT` | 7 | artifact.* yes | none | pass |
| `CONTAINER_IMAGE` | 3 | container_image.* yes | none | pass |
| `HOST` | 5 | host.* yes | none | pass |
| `AwsEksCluster` | 2 | aws.* partial | `aws.region` | major |
