# Runtime Validation (Optional)

Use this optional phase to validate mappings against real tenant data after ingestion.

## TOC

- [Goal](#goal)
- [Step 0 — Load Required Skills (REQUIRED)](#step-0--load-required-skills-required)
- [Inputs To Ask For](#inputs-to-ask-for)
- [Execution Options](#execution-options)
- [Query Pack](#query-pack)
- [Additional Crucial Runtime Checks](#additional-crucial-runtime-checks)
- [Output](#output)

---

## Goal

Confirm that mapped events are present in `security.events` and that values are consistent
with SD expectations and integration intent.

## Step 0 — Load Required Skills (REQUIRED)

**Before composing or running ANY runtime DQL in this workflow, you MUST load `dt-dql-essentials` and use this skill's references (`semantic-reference.md`, `validation-policy-and-reporting.md`, and this file).** Do NOT start writing queries until they are loaded.

1. **DQL Essentials skill** — provides DQL syntax, function reference, and query construction patterns (joins, `fieldsAdd`, `summarize`, `countIf`, time-window expressions, etc.).
2. **This skill's references** (`semantic-reference.md`, `validation-policy-and-reporting.md`, `runtime-validation.md`) — provide `security.events` query patterns, provider scoping, event-type filtering conventions, field guidance, and time-window pitfalls specific to this Grail table.

This file (`runtime-validation.md`) defines **what** to validate. The references above define **how** to write correct DQL: DQL Essentials covers general query mechanics; this skill's references cover `security.events`-specific patterns, provenance rules, and common mistakes.

Skipping these skills produces queries that may run but miss provenance scoping, use incorrect join syntax, mis-classify provider families, or apply stale time-window patterns.

Important runtime interpretation:

- Missing scan events (when scans are expected) is a `warning`, not an automatic failure.
- Orphan findings (findings without matched scans) is a `warning`, not an automatic failure.
- Missing `scan.id` / `scan.name` coverage on vulnerability or compliance findings during runtime validation is a `warning`, not an automatic failure.
- Structural/type violations in required semantic fields remain `fail` conditions.

## Inputs To Ask For

1. `event.provider` value to validate (required).
2. Time window (recommended: start with `24h`, widen as needed).
3. Execution path: live DQL execution against the connected tenant.
4. Whether scans are expected for this integration.
5. Optional bucket restriction if tenant requires it.

Note: Default queries below intentionally avoid `dt.system.bucket` filters to reduce false negatives.
Add a bucket filter only if the user explicitly requests or requires it.

## Execution

Run each DQL query against the connected tenant using the available DQL execution tool and capture result counts and sample rows.

## Query Pack

Set `event.provider` filter to the actual provider value. Time window defaults to `24h` — widen as needed.

### 1) Findings Exist For Provider

Count findings for this provider across `VULNERABILITY_FINDING`, `DETECTION_FINDING`, and `COMPLIANCE_FINDING`, grouped by `event.type`. ≥1 per expected type is pass; 0 findings is fail. Use the canonical query pattern in this file.

### 2) Scans Exist For Provider

Count scans for this provider across `VULNERABILITY_SCAN` and `COMPLIANCE_SCAN`, grouped by `event.type`. Interpret zero counts per the guidance below. Use the canonical query pattern in this file.

Interpretation:

- If scans are expected and counts are zero, mark `warning` and continue validation.
- If scans are not expected for the integration, mark `not_applicable`.

### 3) Scan Linkage Coverage On Findings

Count findings that are missing `scan.id`, grouped by `event.type`. This is a direct null-count — do **not** use a join to compute this. A join on `scan.id` produces a fan-out when `scan.id` is null on both sides (each null-keyed finding matches every null-keyed scan row), inflating the count well beyond the true finding total and making the result meaningless.

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "COMPLIANCE_FINDING"})
| summarize
    total = count(),
    missing_scan_id = countIf(isNull(scan.id) or scan.id == ""),
    by:{event.type}
| sort total desc
```

Interpretation — apply the following conditional rule:

- **No scans exist for this provider** (Q2 = 0): `scan.id` absence on findings is expected. Many push-based integrations (e.g. Wiz, some Snyk push configs) emit finding events only and have no scan concept. Mark `not_applicable` and document.
- **Scans exist for this provider** (Q2 > 0): every finding should carry a `scan.id`. Any finding with `missing_scan_id > 0` means the integration is selectively linking some findings to scans but not others — mark `warning` and inspect `dt.raw_data` on an affected finding to determine whether the scan reference is present in the raw payload but not being mapped.

### 3b) Referenced Scan Existence Check (When scan.id Is Populated)

Run this only when Q3 shows `missing_scan_id < total` — i.e. at least some findings carry a `scan.id`. This check verifies that each referenced `scan.id` resolves to an actual scan event in the same time window.

Use `fields:{right.scan.id=scan.id}` to explicitly alias the right-side projected field — this disambiguates it from the left-side `scan.id` and ensures `right.scan.id` is correctly populated after the join.

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "COMPLIANCE_FINDING"})
| filter isNotNull(scan.id) and scan.id != ""
| join [
    fetch security.events, from:now()-24h
    | filter event.provider == "<PROVIDER>"
    | filter in(event.type, {"VULNERABILITY_SCAN", "COMPLIANCE_SCAN"})
  ], kind:leftOuter, on:{left[`scan.id`] == right[`scan.id`]}, fields:{right.scan.id=scan.id}
| filter isNull(right.scan.id)
| summarize unmatched_scan_refs = count(), by:{event.type}
```

Interpretation:

- `unmatched_scan_refs = 0`: every `scan.id` on a finding resolves to a scan event in the same time window. **Pass.**
- `unmatched_scan_refs > 0`: some findings reference a `scan.id` that has no corresponding scan event in the queried window. Mark `warning` and widen to `now()-7d` to check whether the scan event was ingested earlier (time-window gap). If still absent after widening, the integration is emitting `scan.id` on findings without a corresponding scan event.
- If scans are not expected for this integration (Q2 = 0), skip this check and mark `not_applicable`.

### 4) Risk Level Distribution (Allowed SD Values)

Count findings grouped by `dt.security.risk.level`, sort descending. Use the result to confirm only SD-valid values are present and to inform Q6/Q6b score-vs-level checks. Use the canonical query pattern in this file.

Invalid-value check — explicitly check for out-of-enum values (the valid SD enum is `{"CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE", "NOT_AVAILABLE"}`):

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter isNotNull(dt.security.risk.level)
| filter not in(dt.security.risk.level, {"CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE", "NOT_AVAILABLE"})
| summarize invalid_levels = count(), by:{dt.security.risk.level}
```

### 5) Findings By Object Type

Group findings by `object.type`, sort descending. Confirm observed types match the integration's expected scope (e.g., `CONTAINER_IMAGE` for container scanners). Unexpected or absent object types warrant a warning. Extend to all event types including scans if needed. Use the canonical query pattern in this file.

### 6) Risk Score Vs Risk Level Consistency (CVSS-Aligned Thresholds)

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter isNotNull(dt.security.risk.score) and isNotNull(dt.security.risk.level)
| fieldsAdd expected_risk_level = if(dt.security.risk.score >= 9.0, "CRITICAL",
    else: if(dt.security.risk.score >= 7.0, "HIGH",
    else: if(dt.security.risk.score >= 4.0, "MEDIUM",
    else: if(dt.security.risk.score >= 0.1, "LOW", else: "NONE"))))
| summarize
    total = count(),
    mismatches = countIf(dt.security.risk.level != expected_risk_level)
```

Mismatch details — individual rows (use to pull specific event examples for the report):

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter isNotNull(dt.security.risk.score) and isNotNull(dt.security.risk.level)
| fieldsAdd expected_risk_level = if(dt.security.risk.score >= 9.0, "CRITICAL",
    else: if(dt.security.risk.score >= 7.0, "HIGH",
    else: if(dt.security.risk.score >= 4.0, "MEDIUM",
    else: if(dt.security.risk.score >= 0.1, "LOW", else: "NONE"))))
| filter dt.security.risk.level != expected_risk_level
| fieldsKeep timestamp, event.type, finding.id, finding.title, finding.severity, dt.security.risk.score, dt.security.risk.level, expected_risk_level
| sort timestamp desc
| limit 100
```

Mismatch details grouped by vendor severity — use this to diagnose **why** mismatches occur. The `finding.severity` column reveals whether the integration derives `dt.security.risk.level` from the vendor's own severity label (e.g. vendor "High" → level `HIGH`) while `dt.security.risk.score` reflects CVSS (which may push the finding to `CRITICAL`). Two root-cause patterns to look for:

- **Score = 0 with non-NONE level** — `dt.security.risk.score` is being set to `0` as a default rather than omitted when no numeric score is available; `0` maps to `NONE` and will always mismatch any non-NONE level.
- **Score ≥ 9.0 with level = HIGH** — the integration derives `dt.security.risk.level` from the vendor's proprietary severity tier (which may cap at "High") instead of from CVSS bands; when the CVSS score is ≥ 9.0 the DT-normalized level should be `CRITICAL`.

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter (dt.security.risk.level == "CRITICAL" and (dt.security.risk.score < 9.0  or dt.security.risk.score > 10.0))
      or (dt.security.risk.level == "HIGH"     and (dt.security.risk.score < 7.0  or dt.security.risk.score > 8.9))
      or (dt.security.risk.level == "MEDIUM"   and (dt.security.risk.score < 4.0  or dt.security.risk.score > 6.9))
      or (dt.security.risk.level == "LOW"      and (dt.security.risk.score < 0.1  or dt.security.risk.score > 3.9))
      or (dt.security.risk.level == "NONE"     and dt.security.risk.score != 0)
| summarize
    count = count(),
    distinct_scores = collectDistinct(dt.security.risk.score),
    by:{event.type, finding.severity, dt.security.risk.level}
| sort count desc
```

### 6b) Risk Score Range Per Risk Level (Per-Level Summary)

Summarize `dt.security.risk.score` distribution for each observed `dt.security.risk.level` and
flag rows whose score falls outside the band defined for that level. Bands reuse the
CVSS-aligned thresholds from Q6 to keep the two checks consistent (no band drift).

| level | expected score band |
|---|---|
| CRITICAL | ≥ 9.0 |
| HIGH | 7.0 – 8.9 |
| MEDIUM | 4.0 – 6.9 |
| LOW | 0.1 – 3.9 |
| NONE | 0.0 |

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter isNotNull(dt.security.risk.score) and isNotNull(dt.security.risk.level)
| fieldsAdd expected_risk_level = if(dt.security.risk.score >= 9.0, "CRITICAL",
    else: if(dt.security.risk.score >= 7.0, "HIGH",
    else: if(dt.security.risk.score >= 4.0, "MEDIUM",
    else: if(dt.security.risk.score >= 0.1, "LOW", else: "NONE"))))
| summarize
    count = count(),
    min_score = min(dt.security.risk.score),
    max_score = max(dt.security.risk.score),
    avg_score = round(avg(dt.security.risk.score), decimals: 2),
    out_of_band = countIf(dt.security.risk.level != expected_risk_level),
    by:{dt.security.risk.level}
| sort dt.security.risk.level asc
```

Interpretation:

- `out_of_band == 0` for every level → `pass`. Each level's observed scores fit its CVSS band.
- `out_of_band > 0` on any level → `warning`. Drill into the offending rows with the Q6 mismatch-details query (filtered by the level of interest).
- `min_score` / `max_score` exceeding the band edges (without raising `out_of_band`) — **do NOT automatically flag as a warning**. This commonly indicates the integration maps `dt.security.risk.score` from a vendor post-assessment adjusted score (e.g. JFrog applicability-adjusted severity, Snyk effective severity, Qualys QDS) rather than raw CVSS. Vendor-adjusted scoring is the **recommended pattern**: it augments CVSS by accounting for exploit applicability and reachability, reducing noise from theoretical vulnerabilities. The original CVSS float is preserved in `vulnerability.cvss.base_score`. Treat as `pass` when the vendor is known to provide an adjusted score; note it as informational in the report. Only escalate to `warning` if the integration claims CVSS-aligned bands but the evidence suggests otherwise.
- Levels missing from the result that are present in Q4 mean the integration emits the level without a score — combine with Q4 + Q7 null-rate output rather than failing this check.

## Additional Crucial Runtime Checks

### 7) Missing Core Required Fields (Null/Empty Audit)

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING", "VULNERABILITY_SCAN", "COMPLIANCE_SCAN"})
| summarize
    total = count(),
    missing_event_id = countIf(isNull(event.id) or event.id == ""),
    missing_event_kind = countIf(isNull(event.kind) or event.kind == ""),
    missing_product_vendor = countIf(isNull(product.vendor) or product.vendor == ""),
    missing_product_name = countIf(isNull(product.name) or product.name == ""),
    missing_object_type = countIf(isNull(object.type) or object.type == ""),
    missing_object_id = countIf(isNull(object.id) or object.id == "")
```

### 8) Raw Payload Availability For Final-Ingested Validation

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING", "VULNERABILITY_SCAN", "COMPLIANCE_SCAN"})
| summarize
    total = count(),
    missing_raw_payload = countIf((isNull(dt.raw_data) or dt.raw_data == "") and (isNull(event.original_content) or event.original_content == ""))
```

### 9) Scan Time Consistency

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_SCAN", "COMPLIANCE_SCAN"})
| filter isNotNull(scan.time.started) and isNotNull(scan.time.completed)
| fieldsAdd invalid_duration = toTimestamp(scan.time.completed) < toTimestamp(scan.time.started)
| summarize invalid_scan_time_ranges = countIf(invalid_duration), total = count()
```

### 9a) Scan Reference Coverage On Findings

Run this for vulnerability and compliance findings to see whether findings carry `scan.id`
and `scan.name` directly.

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "COMPLIANCE_FINDING"})
| summarize total = count(), missing_scan_id = countIf(isNull(scan.id) or scan.id == ""), missing_scan_name = countIf(isNull(scan.name) or scan.name == ""), by:{event.type}
| sort total desc
```

Interpretation:

Apply the same conditional rule as Q3:

- **No scans exist for this provider** (Q2 = 0): `scan.id` and `scan.name` absence is expected. Mark `not_applicable`.
- **Scans exist for this provider** (Q2 > 0): `missing_scan_id > 0` should raise a `warning` (aligns with Q3). `missing_scan_name > 0` is a separate `warning` — `scan.name` is the human-readable label used for display and filtering; its absence indicates the integration does not populate a name for the scan reference even when a `scan.id` is present.

### 10) Sample Finding Event For A Specific Object Type (`| limit 1`)

Run once per selected `object.type` from the Q5 distribution check.

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter object.type == "<OBJECT_TYPE>"
| sort timestamp desc
| limit 1
```

Recommended quick structure check fields:

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter object.type == "<OBJECT_TYPE>"
| sort timestamp desc
| limit 1
| fieldsKeep timestamp, event.id, event.kind, event.type, event.provider, product.vendor, product.name, finding.id, finding.title, finding.time.created, finding.type, object.id, object.name, object.type, scan.id, scan.name, dt.security.risk.level, dt.security.risk.score
```

### 11) Sample Scan Event For A Specific Object Type (`| limit 1`, Optional)

Run this only when scans are expected and present.

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_SCAN", "COMPLIANCE_SCAN"})
| filter object.type == "<OBJECT_TYPE>"
| sort timestamp desc
| limit 1
| fieldsKeep timestamp, event.id, event.kind, event.type, event.provider, product.vendor, product.name, scan.id, scan.name, scan.time.started, scan.time.completed, object.id, object.name, object.type
```

**After fetching sample events in Q10/Q11, apply the static checks in `validation-policy-and-reporting.md` to the fetched events — including the Vendor Namespace Duplication Check. Static checks apply equally to fetched and pasted samples.**

### 12) Raw Payload Backfill Analysis For Missing Required Fields

When required semantic fields are missing (for example `object.name`), inspect original payload
content and propose mapping candidates.

Sample query to pull rows with missing `object.name` and raw payload context:

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter isNull(object.name) or object.name == ""
| fieldsKeep timestamp, event.id, event.type, finding.id, object.id, object.type, dt.raw_data, event.original_content
| sort timestamp desc
| limit 20
```

Interpretation:

- Parse raw payload in priority order: `dt.raw_data` (push-based), then `event.original_content` (extension-based, pull-based), then vendor samples if neither payload field is available.
- For each missing field, return at least one concrete source path candidate and transform note.
- If neither payload contains candidate source values, mark as evidence gap and request additional vendor samples.

### 13) Vendor Namespace Duplication Check (Scale Confirmation Only)

The core detection for this check is a **static field-comparison** on a sample event — no DQL query needed. See `validation-policy-and-reporting.md § Vendor Namespace Duplication Check → How to apply` for the static inspection procedure. Use the sample already fetched in Q10.

**Severity verdicts, the canonical relationship-to-SD-field table, and the common-duplication-patterns table are in `validation-policy-and-reporting.md § Vendor Namespace Duplication Check` — do not duplicate them in the report.**

The DQL below is **optional scale confirmation only** — run it against the live environment to count duplication frequency across many events. It is not required for initial detection.

For each candidate pair identified in the static inspection, count how often the vendor field equals the SD field. Replace `<SD_FIELD>` and `<VENDOR_FIELD>` per pair; add as many `dup_<name>_*` counters as needed. Example below uses `<VENDOR_PREFIX> = wiz` with common compliance pairs.

> **Rule-identity fields are migrating to the generic `rule.*` namespace** (`compliance.rule.title` → `rule.name`, `compliance.rule.description` → `rule.description`; see `semantic-reference.md § Rule Identity Namespace`). The example pairs below use the **legacy `compliance.rule.*` names because that is what current runtime data still emits** — the query must match live events. Once the runtime emits `rule.name` / `rule.description`, pair the vendor field against those canonical fields instead (and check both during the transition).

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| summarize
    total = count(),
    // Pair: compliance.rule.title  ↔  <VENDOR_PREFIX>.rule.name
    dup_rule_title_both_present = countIf(isNotNull(compliance.rule.title) and isNotNull(wiz.rule.name)),
    dup_rule_title_match        = countIf(compliance.rule.title == wiz.rule.name),
    // Pair: compliance.rule.description  ↔  <VENDOR_PREFIX>.rule.description
    dup_rule_desc_both_present = countIf(isNotNull(compliance.rule.description) and isNotNull(wiz.rule.description)),
    dup_rule_desc_match        = countIf(compliance.rule.description == wiz.rule.description),
    // Pair: compliance.remediation.description  ↔  <VENDOR_PREFIX>.finding.remediation
    dup_remediation_both_present = countIf(isNotNull(compliance.remediation.description) and isNotNull(wiz.finding.remediation)),
    dup_remediation_match        = countIf(compliance.remediation.description == wiz.finding.remediation),
    // Pair: finding.severity  ↔  <VENDOR_PREFIX>.finding.severity
    dup_severity_both_present = countIf(isNotNull(finding.severity) and isNotNull(wiz.finding.severity)),
    dup_severity_match        = countIf(finding.severity == wiz.finding.severity)
    // Add additional pairs as identified in the Q13 static inspection.
```

Map `dup_<pair>_match` vs `dup_<pair>_both_present` to a verdict + severity using the verdict table in `validation-policy-and-reporting.md § Vendor Namespace Duplication Check`. Optional drilldown for partial-overlap pairs (rows where SD and vendor disagree) — replace `<SD_FIELD>` and `<VENDOR_FIELD>` per pair:

```dql-template
// Replace `compliance.rule.title` and `wiz.rule.name` below with the actual SD field and vendor field per pair.
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter isNotNull(`compliance.rule.title`) and isNotNull(`wiz.rule.name`) and `compliance.rule.title` != `wiz.rule.name`
| fieldsKeep timestamp, event.id, finding.id, `compliance.rule.title`, `wiz.rule.name`
| sort timestamp desc
| limit 50
```

Report per-pair results in a table with columns `SD field`, `Vendor field`, `Both present`, `Match count`, `Verdict`. When both fields are populated (regardless of value match), note it as an acceptable alias — no action required. If the SD field is empty while the vendor field is populated, flag as **major** (missed mapping). If no vendor-namespace fields are present, state that explicitly.

### 14) Entity Enrichment Coverage

`dt.smartscape.*` and `dt.entity.*` are post-ingest enrichment populated by OpenPipeline — they are NOT integration-emitted fields. This check audits whether enrichment is actually working at runtime. **Missing enrichment is not a blocker** (see `intake-and-constraints.md § Smartscape Enrichment Fields Are Post-Ingest`); severity depends on context — K8s and cloud detection findings warrant `warn`, others are `info`.

`dt.entity.*` is the **deprecated** alias namespace; `dt.smartscape.*` is the canonical forward-going namespace. A row that has `dt.smartscape.*` but no `dt.entity.*` is **completely OK** — do NOT flag the missing legacy alias. The check below uses presence of *either* namespace as "enriched."

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| fieldsAdd has_smartscape = isNotNull(dt.smartscape_source.id) or isNotNull(dt.smartscape.host) or isNotNull(dt.smartscape.process) or isNotNull(dt.smartscape.k8s_cluster) or isNotNull(dt.smartscape.k8s_node) or isNotNull(dt.smartscape.k8s_pod) or isNotNull(dt.smartscape.aws_ec2_instance) or isNotNull(dt.smartscape.aws_eks_cluster) or isNotNull(dt.smartscape.service)
| fieldsAdd has_entity_legacy = isNotNull(dt.entity.host) or isNotNull(dt.entity.process_group) or isNotNull(dt.entity.process_group_instance) or isNotNull(dt.entity.kubernetes_cluster) or isNotNull(dt.entity.kubernetes_node) or isNotNull(dt.entity.cloud_application_namespace) or isNotNull(dt.source_entity)
| fieldsAdd is_enriched = has_smartscape or has_entity_legacy
| summarize
    total = count(),
    enriched = countIf(is_enriched),
    smartscape_only = countIf(has_smartscape and not has_entity_legacy),
    legacy_only = countIf(has_entity_legacy and not has_smartscape),
    none = countIf(not is_enriched),
    by:{event.type, object.type}
| sort total desc
```

Interpretation per `(event.type, object.type)` row:

| Outcome | Verdict | Severity tier |
|---|---|---|
| `enriched == total` (all rows enriched) | enrichment OK | 🟢 pass |
| `smartscape_only > 0` and no legacy-only rows | enrichment OK on canonical namespace | 🟢 pass |
| `legacy_only > 0` (dt.entity.* present, dt.smartscape.* missing on those rows) | OK to keep, but recommend migrating ingestion to populate `dt.smartscape.*` | 🟡 warn (migration suggestion) |
| `none > 0` on `DETECTION_FINDING` rows where `object.type` is K8s (`K8S_POD`, `CONTAINER`) or cloud (`AwsEc2Instance`, `AwsEksCluster`, etc.) | enrichment expected for these classes | 🟡 warn |
| `none > 0` on other finding-types / object-types | enrichment may legitimately not apply | ℹ info |
| `none == total` on K8s / cloud detection findings | enrichment pipeline likely not configured for this provider | 🟡 warn (escalate to investigate OpenPipeline config) |

Optional drilldown — list rows with no enrichment so the operator can spot-check whether the underlying entity actually exists in this tenant:

```dql-template
fetch security.events, from:now()-24h
| filter event.provider == "<PROVIDER>"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter isNull(dt.smartscape_source.id) and isNull(dt.smartscape.host) and isNull(dt.smartscape.process) and isNull(dt.smartscape.k8s_cluster) and isNull(dt.smartscape.k8s_pod) and isNull(dt.smartscape.aws_ec2_instance) and isNull(dt.smartscape.aws_eks_cluster) and isNull(dt.entity.host) and isNull(dt.entity.process_group) and isNull(dt.source_entity)
| fieldsKeep timestamp, event.id, event.type, object.type, object.id, object.name, finding.id
| sort timestamp desc
| limit 20
```

## Output

Every runtime check from this query pack must end up as a row in a single **`Validation Summary` table** (no bullet-list replacement) with status icons `🟢 pass` / `🟡 warn` / `🔴 fail`. Each row should also carry: query reference, result-count summary, and (for non-passes) a suggested fix or follow-up.

### Per-check status mapping

| Check (query #) | 🟢 pass | 🟡 warn | 🔴 fail |
|---|---|---|---|
| Findings exist for provider (Q1) | ≥1 finding | — | 0 findings |
| Scans exist when expected (Q2) | ≥1 scan | 0 scans (expected) | — |
| Orphan findings (Q3) | 0 orphans | non-zero orphans | — |
| Scan-reference coverage on V/C findings (Q9a) | full coverage | missing coverage | — |
| `dt.security.risk.level` values valid (Q4) | all in SD enum | — | any invalid |
| `object.type` distribution sanity (Q5) | matches integration scope | unexpected mix | impossible types |
| Risk score-vs-level consistency (Q6) | 0 mismatches | — | non-zero mismatches |
| Per-level risk-score band conformance (Q6b) | `out_of_band == 0` everywhere | `out_of_band > 0` on any level | — |
| Required-field null audit (Q7) | 0 nulls | — | any nulls in required fields |
| Raw-payload availability (Q8) | full coverage | — | missing on rows expected to carry it |
| Scan time consistency (Q9) | 0 invalid intervals | half-populated (started or completed missing) | invalid intervals |
| Per-`object.type` sample structure (Q10–Q11) | required fields present on sample | scan-event sample missing optional fields | required fields missing on sample |
| Missing-field backfill suggestions (Q12) | n/a (no missing fields) | gap with raw-payload candidate | gap with no candidate (evidence gap) |
| Vendor-namespace duplication (Q13 — static, evaluated on Q10 sample) | no vendor-namespace fields, OR all vendor-namespace fields have their SD counterparts populated with no redundant pairs | redundant pair found (vendor field mirrors populated SD field — `info`, no removal required) | SD field empty or null while vendor field is populated (missed mapping) |
| Entity enrichment coverage (Q14) | all K8s / cloud detection rows enriched (`dt.smartscape.*` or legacy `dt.entity.*` populated) | unenriched K8s / cloud detection rows; or legacy-only `dt.entity.*` (recommend migration to `dt.smartscape.*`); or unenriched non-detection rows where enrichment was expected | — (Q14 never produces `🔴 fail`; missing enrichment is not a blocker) |

### When required fields are missing

Include a mapping-backfill table (per `intake-and-constraints.md § Output Contract — Workflow B (Validation)`, item 13) sourcing candidates in priority order: `dt.raw_data` → `event.original_content` → vendor API samples.
