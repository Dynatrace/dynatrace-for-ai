# Mapping Workflow

## TOC

- [Workflow A — Suggest a New Mapping](#workflow-a--suggest-a-new-mapping)
- [Workflow B — Validate a Provided Mapping](#workflow-b--validate-a-provided-mapping)
- [Shared: Verifying Against the Live Semantic Dictionary](#shared-verifying-against-the-live-semantic-dictionary)
- [Shared: Semantic Field Priority Order](#shared-semantic-field-priority-order)
- [Shared: Baseline Comparison](#shared-baseline-comparison)
- [Mapping Table Template](#mapping-table-template)

---

## Workflow A — Suggest a New Mapping

Triggered when the user provides only raw vendor API payloads (no mapping draft exists).

### A.1 Normalize Inputs

1. Flatten any nested vendor JSON paths to dot notation.
2. Record source type per field: string, number, boolean, array, object.
3. Track nullability and optionality frequency across samples.
4. Note which fields appear in all samples vs. only some.

### A.2 Build Mapping Candidate

Map vendor fields to semantic targets following the priority order in
[Shared: Semantic Field Priority Order](#shared-semantic-field-priority-order).

When proposing a target field that is **not already documented** in our local references, verify it against the live SD before committing — see [Shared: Verifying Against the Live Semantic Dictionary](#shared-verifying-against-the-live-semantic-dictionary). This prevents proposing non-existent or deprecated fields and ensures `supported_values` for enum-typed targets are correct.

Every value you put in the **Transform** column must be implementable as an **OpenPipeline processor** at ingest — OpenPipeline runs a restricted DQL subset, not full Grail query DQL. Do not propose transforms that rely on unavailable constructs (most notably `jsonPath()` for nested-JSON extraction).

**Structure the implementation as a processor chain, not a single processor.** The canonical pattern is: one generic processor (common SD fields, shared JSON parsing) → per-subcategory processors scoped by matching criterion (object-type or finding-type-specific namespaces) → a cleanup processor (removes intermediate non-SD fields). Processors execute in order; fields written by an earlier processor are available in already-parsed form to all later ones — no re-parsing needed.

See [intake-and-constraints.md](intake-and-constraints.md) for the chain architecture, supported command set, `jsonPath()` alternative, and `ip()` cast for `ipAddress`-typed fields.

### A.3 Resolve Doubts via Baseline Comparison (conditional)

If any field, enum value, value format, or namespace choice remains unresolved after applying the priority order and local references, consult the baseline samples — see [Shared: Baseline Comparison](#shared-baseline-comparison). Skip this step when the primary references unambiguously answer every open question.

### A.4 Phase 1 Output — Mapping Table

Present the mapping table and discrepancy/gap summary.
**Stop here and wait for user approval before proceeding to Phase 2.**

Use the [Mapping Table Template](#mapping-table-template).

### A.5 Phase 2 Output — Sample JSON (after user approval only)

1. Produce one representative mapped JSON object per `finding.type` observed in the vendor samples.
2. Use only target (semantic dictionary) field names as JSON keys.
3. Populate values from the actual vendor sample payloads.
4. Add an inline JSON comment (or a companion note block) for every field where a transform was applied:
   - Enum normalization: `// normalized from "critical" -> "CRITICAL"`
   - Type cast: `// cast from string to number`
   - Constant default: `// hardcoded constant: "SECURITY_EVENT"`
   - Derived/computed: `// derived from finding.severity via auto-map`

---

## Workflow B — Validate a Provided Mapping

Triggered when the user provides an existing mapping (JSON output or mapping table) along with the original vendor API responses.

### B.0 Determine Validation Input Mode

1. Ask whether the user is validating a **final ingested event** or a **theoretical mapping**.
2. If final ingested event, ask where original vendor payload is stored:
   - `dt.raw_data` (push-based integrations)
   - `event.original_content` (extension-based integrations, pull-based)
3. If theoretical mapping, do not require either field because both are platform-generated and may be absent.

### B.1 Normalize Both Inputs

1. Parse the provided mapping into the standard mapping table format.
2. For final ingested event validation:
   - Parse the chosen raw-content field (`dt.raw_data` or `event.original_content`) as the source payload.
   - Normalize raw payload and ingested event payload side-by-side.
3. For theoretical mapping validation:
   - Normalize vendor API responses the same way as A.1.
4. Identify the full set of `object.type` and `finding.type` values across both inputs.

### B.2 Apply All Validation Rules

Run every rule in [validation-policy-and-reporting.md](validation-policy-and-reporting.md) against the provided mapping.
Record outcome per rule: pass / fail / warning.

For any unknown field, ambiguous enum value, type mismatch, or namespace question that the local references do not unambiguously resolve, verify against the live SD — see [Shared: Verifying Against the Live Semantic Dictionary](#shared-verifying-against-the-live-semantic-dictionary). The live SD is authoritative when local references and SD disagree.

### B.2a Backfill Missing Fields From Original Payload

When required semantic fields are missing (for example `object.name`):

1. Inspect raw source payload in this order:
   - `dt.raw_data` (push-based integrations)
   - `event.original_content` (extension-based integrations, pull-based)
   - vendor API sample payloads (when neither final-ingested payload field is available)
2. Locate source-path candidates for each missing target field.
3. Define transform rules needed to map the source value into semantic format.
4. Add explicit `➕ add` entries to the diff table for each proposed backfill mapping.
5. If no source path exists, mark as unresolved evidence gap and request additional payload samples.

### B.3 Resolve Doubts via Baseline Comparison (conditional)

If any field, enum value, value format, or namespace choice remains unresolved after applying the validation rules and completing the backfill step above, consult the baseline samples — see [Shared: Baseline Comparison](#shared-baseline-comparison). Skip this step when the primary references unambiguously answer every open question.

### B.4 Produce Diff-Highlighted Mapping Table

The output table has the same columns as the suggestion table, plus a `Status` column:

| Source Field | Current Target | Suggested Target | Transform | Status | Reason |
|---|---|---|---|---|---|
| `vendor.id` | `event.id` | `event.id` | direct | ✅ ok | |
| `vendor.score` | `dt.security.risk.score` | `dt.security.risk.score` | string→number | ⚠ change | score must be numeric, not string |
| `vendor.repoName` | `artifact.name` | `artifact.repository` | direct | ⚠ change | repository name belongs in artifact.repository |
| — | — | `component.name` | constant | ➕ add | required for VULNERABILITY_FINDING |
| `vendor.internalRef` | `internal.ref` | — | — | ❌ remove | unknown field, not in SD or local references |

Marker legend:

- ✅ ok — no change needed
- ⚠ change — keep field but adjust target, transform, or value
- ➕ add — missing field that must be added to the mapping
- ❌ remove — field should be removed or renamed with justification

After the diff table, include the full coverage/discrepancy report in the same
structure as Workflow A Phase 1 output (coverage matrix, object-type checks,
finding-type checks, discrepancies list).

Formatting requirement for Workflow B:

- Use tables for validation output sections (coverage, discrepancies, runtime checks, remediation summary).
- Do not present validation summaries as bullet lists.

### B.5 Optional Runtime Validation (Tenant-Backed)

If user requests real-environment validation:

0. **REQUIRED:** Load the security (AppSec) events supporting skill per `runtime-validation.md § Step 0` BEFORE composing runtime DQL. Do not start writing queries until it is loaded.
1. Ask for `event.provider` and time window.
2. Confirm that live tenant access is available for DQL execution.
3. Run the query pack in `runtime-validation.md`.
4. Attach runtime result summary to the final validation output:
   - findings present
   - scans present (warning if absent when expected)
   - orphan findings without scans (warning when non-zero)
   - scan reference coverage on findings (warning when missing)
   - risk-level validity
   - risk score vs level mismatches
   - object.type distribution sanity
   - sample events per relevant object.type using `| limit 1`
   - sample-event structure validation outcome
   - missing-field mapping-backfill suggestions from raw payload analysis
   - `Validation Summary` table using `🟢 pass`, `🟡 warn`, `🔴 fail`

---

## Shared: Verifying Against the Live Semantic Dictionary

When the local references don't unambiguously resolve a field, enum, type, or namespace question, verify against the live SD. See `semantic-reference.md § Semantic Dictionary` in this skill's references for the canonical guidance: queryable Grail tables (`dt.semantic_dictionary.fields`, `dt.semantic_dictionary.models`), DQL patterns, when-to-query decision matrix, and the authority rule (live SD wins on disagreement).

---

## Shared: Semantic Field Priority Order

Map vendor fields to semantic targets in this order:

1. **Event core**: `event.id`, `event.kind`, `event.type`, `event.provider`, `timestamp` (note: `event.id` and `timestamp` are ingest-generated and do not require explicit source mapping in theoretical validation)
2. **Finding core**: `finding.id`, `finding.title`, `finding.time.created`, `finding.type`, `finding.severity`
3. **Risk**: `dt.security.risk.level`, `dt.security.risk.score`
4. **Object core**: `object.id`, `object.name`, `object.type`
5. **Product/provider**: `product.vendor`, `product.name`
6. **Scan reference** (V/C only): `scan.id`, `scan.name`
7. **Type-specific namespaces** (per `object.type` and `finding.type` rules):
   - `artifact.*` for CODE_ARTIFACT
   - `container_image.*` for CONTAINER_IMAGE
   - `component.*` / `software_component.*` for vulnerability findings
   - `code.*` for CODE_ISSUE / CODE_VULNERABILITY
   - `host.*`, `k8s.*`, `aws.*`, etc.
8. **High-value optional enrichment**:
   - `vulnerability.references.cve`, `vulnerability.cvss.base_score`, `vulnerability.exploit.status`
   - `vulnerability.cvss.version` as number-only version token (`3.1`, `4.0`)
   - `vulnerability.remediation.fix_versions` (array of versions; omit when empty)
   - `actor.ips`, `rule.id`, `rule.name` (detections; use `rule.name`, not `rule.title`)
   - Vendor-namespaced extensions (e.g. `snyk.*`, `github.*`) — may carry the same value as an SD-canonical field when the SD field is simultaneously populated, serving as a familiar query alias for users accustomed to vendor naming. Apply the *Vendor Namespace Duplication Check* from [validation-policy-and-reporting.md](validation-policy-and-reporting.md) to detect the only actionable case: the SD field is empty while the vendor field carries the value.

---

## Shared: Baseline Comparison

Consult `../samples/` **only when a specific doubt is unresolved** after checking the primary references: `semantic-reference.md`, `validation-policy-and-reporting.md`, `intake-and-constraints.md`. Do not open or scan the samples directory as a routine step on every workflow run.

**Triggers that justify a sample lookup:**

1. A field, enum value, or namespace question the primary references do not unambiguously answer.
2. Evaluating whether a new field or value pattern has precedent in existing integrations.
3. Verifying a value format (enum casing, type) when the SD omits examples.
4. Backfill: looking for candidate source paths in comparable integration payloads when neither `dt.raw_data` nor `event.original_content` provides a source path (last-resort step in B.2a).

**When samples are consulted, apply these checks:**

1. Flag target fields not seen in any local sample as potential unknowns — but verify against the live SD before classifying (see [Shared: Verifying Against the Live Semantic Dictionary](#shared-verifying-against-the-live-semantic-dictionary)).
2. Identify richer semantic fields available in comparable integrations that are missing.
3. Flag value-pattern contradictions vs. samples (wrong enum case, wrong type).
4. Flag known-discrepancy fields — classify as `info` only (see `validation-policy-and-reporting.md § Known Discrepancies`).

---

## Mapping Table Template

For Workflow A Phase 1 and Workflow B diff table respectively:

**Workflow A — Suggestion table:**

| Source Field | Target Field | Transform | Required | Sample Value | Notes |
|---|---|---|---|---|---|
| `vendor.findingId` | `finding.id` | direct | yes | `abc-123` | stable unique ID |
| `vendor.severity` | `dt.security.risk.level` | enum map | yes | `critical` → `CRITICAL` | auto-mapped if omitted |
| — | `event.kind` | constant `SECURITY_EVENT` | yes | `SECURITY_EVENT` | always required |

**Workflow B — Diff table:**

| Source Field | Current Target | Suggested Target | Transform | Status | Reason |
|---|---|---|---|---|---|
| `vendor.findingId` | `finding.id` | `finding.id` | direct | ✅ ok | |
| `vendor.risk` | `risk_level` | `dt.security.risk.level` | enum map | ⚠ change | wrong target field name |
