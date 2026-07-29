# Validation Policy And Reporting

## Contents

- [Validation Rules](#validation-rules)
- [Known Discrepancies](#known-discrepancies)
- [Report Format](#report-format)


---

## Validation Rules


Apply all rules to both user-provided mappings and generated mappings. Rules are grouped by topic.

## TOC

- [Validation Rules](#validation-rules)
	- [TOC](#toc)
	- [Event-Type Coverage](#event-type-coverage)
		- [Alternative — Reclassification Path](#alternative--reclassification-path)
	- [Required Fields — All Findings](#required-fields--all-findings)
	- [Risk Fields and Auto-Mapping](#risk-fields-and-auto-mapping)
	- [Scan Reference Requirement (Static Mapping Validation)](#scan-reference-requirement-static-mapping-validation)
	- [Scan Event Field Scope](#scan-event-field-scope)
	- [Vulnerability Findings — Component Namespace](#vulnerability-findings--component-namespace)
		- [`software_component.supplier.name` — User-Friendly Supplier Name](#software_componentsuppliername--user-friendly-supplier-name)
	- [External Compliance Integration — Field Conventions](#external-compliance-integration--field-conventions)
	- [Object-Type Namespace Requirements](#object-type-namespace-requirements)
	- [finding.type Namespace Requirements](#findingtype-namespace-requirements)
	- [Known SD Discrepancies and Unknown Fields](#known-sd-discrepancies-and-unknown-fields)
		- [Acceptable Discrepancies](#acceptable-discrepancies)
		- [Unknown Fields](#unknown-fields)
		- [Vendor-Specific Extensions (Expected and Valued)](#vendor-specific-extensions-expected-and-valued)
		- [Vendor Namespace Duplication Check](#vendor-namespace-duplication-check)
	- [Value and Type Checks](#value-and-type-checks)
		- [Provider-Vendor Canonicalization Check](#provider-vendor-canonicalization-check)
	- [Cross-Integration Comparison](#cross-integration-comparison)
	- [Validation Input Mode And Raw Content Fields](#validation-input-mode-and-raw-content-fields)
	- [Optional Runtime Validation Checks](#optional-runtime-validation-checks)
	- [Discrepancy Severity](#discrepancy-severity)
	- [Acceptance Criteria](#acceptance-criteria)

---

## Event-Type Coverage

Validate that the integration supports the correct `event.type` values:

| Finding class | Required event.type | Scan event.type |
|---|---|---|
| Detection | `DETECTION_FINDING` | — (not applicable) |
| Vulnerability | `VULNERABILITY_FINDING` | `VULNERABILITY_SCAN` |
| Compliance | `COMPLIANCE_FINDING` | `COMPLIANCE_SCAN` |
| Threat intelligence | `THREAT_REPORT` | — (no scan cycle) |

- Detections are push-based; they have no scan cycle. Flag a mapping critical if it adds scan events for detections.
- **Threat intelligence** (`THREAT_REPORT`) reports are ingested from external TI platforms (AlienVault OTX pulses, CrowdStrike Falcon Intelligence, STIX/TAXII feeds) via extension/pull integrations. Like detections, they have **no scan cycle** — flag a mapping critical if it emits `*_SCAN` events for threat-intel. They are also **not findings**: see [§ Required Fields — Threat Intelligence](#required-fields--threat-intelligence) for the distinct required set. `THREAT_REPORT` carries no `object.*`, so the object-type-namespace and `finding.type`-namespace rules do **not** apply.
- Vulnerability and compliance integrations that omit scan events are missing coverage signals — flag as **major**.

### Alternative — Reclassification Path

When a detection-class mapping incorrectly emits `*_SCAN` events, do not stop at "remove the scan events." Investigate whether the integration class itself is wrong before recommending the fix.

If the vendor's "scan-complete" / "system-scan-summary" / "assessment" payload is actually a **vulnerability assessment** (per-asset vulnerability state at a point in time), the integration class is **vulnerability**, not detection. In that case:

1. Reclassify: `event.type` for the underlying records becomes `VULNERABILITY_FINDING`, paired with `VULNERABILITY_SCAN` coverage events.
2. Do **not** drop the scan-style payload — it carries real coverage data, just on the wrong event-type.
3. Re-derive the finding mapping from the vendor's assessment records (one finding per (asset × vulnerability) row).
4. Emit one `VULNERABILITY_SCAN` per scan cycle × scanned object, not per finding.

If the vendor really is a detection engine (alerts on observed adversary behavior, not vulnerability state), then the original "remove the scan events" guidance applies and the heartbeat/coverage signal should be routed to a non-`security.events` channel (operational telemetry or vendor-namespaced product metrics).

The validator must offer both branches in the discrepancy report so the integration owner picks the correct one.

---

## Required Fields — All Findings

> **Applies to finding + scan classes only — NOT to `THREAT_REPORT`.** Threat-intelligence
> reports are not findings: they have no `finding.id`/`finding.title`/`finding.time.created`/
> `finding.type`/`finding.severity`, no `object.*`, and no `dt.security.risk.level`. Validating a
> `THREAT_REPORT` mapping against the table below would wrongly flag every one of those as
> critical-missing. Use [§ Required Fields — Threat Intelligence](#required-fields--threat-intelligence) instead.

Fail validation (`critical`) if any of these are absent and cannot be derived:

| Field | Notes |
|---|---|
| `event.id` | Unique event identity. **Auto-generated on ingest** — not required in the mapping. Ingestion platform (OpenPipeline) generates UUID if absent. |
| `event.kind` | Should be `SECURITY_EVENT` |
| `event.type` | One of the values in the event-type coverage table |
| `event.provider` | Integration name |
| `product.name` | Product within provider |
| `product.vendor` | Vendor name |
| `timestamp` | Ingestion time. **Auto-populated on ingest** — not required as an explicit mapping in theoretical mapping validation. |
| `finding.id` | Provider-specific finding identity; must be stable and non-null |
| `finding.title` | Human-readable description |
| `finding.time.created` | Detection occurrence timestamp — when the finding was most recently detected in the current scan run. Map from the vendor's `last_updated`/`updateDate`/`updated_at`/`last_seen`/scan date. **Not** from `creationDate`/`created_at`/`first_seen_at` (immutable after initial creation, not updated on re-detection). |
| `finding.type` | Sub-classification (e.g. `DEPENDENCY_VULNERABILITY`, `CODE_ISSUE`, `EXPOSED_SECRET`) |
| `finding.severity` | Vendor severity string — used as input to risk auto-mapping if `dt.security.risk.level` is absent |
| `object.id` | ID of the affected object |
| `object.name` | Name of the affected object |
| `object.type` | Type of the affected object |

---

## Required Fields — Threat Intelligence

For `event.type == "THREAT_REPORT"` (external threat-intelligence reports — AlienVault OTX,
CrowdStrike Falcon Intelligence, STIX/TAXII). These are **not findings**; validate against this set,
**not** the "All Findings" table. Fail validation (`critical`) if any of these are absent and cannot be derived:

| Field | Notes |
|---|---|
| `event.id` | Auto-generated on ingest — not required in the mapping. |
| `event.kind` | Should be `SECURITY_EVENT` |
| `event.type` | `THREAT_REPORT` |
| `event.provider` | TI platform / feed name (e.g. `AlienVault OTX`, `CrowdStrike`) |
| `event.name` | Event label (e.g. `Threat report event`) |
| `product.vendor` | Vendor (e.g. `LevelBlue`, `CrowdStrike`) |
| `product.name` | Product (e.g. `AlienVault OTX`, `Falcon Intelligence`) |
| `timestamp` | Auto-populated on ingest — not required as an explicit mapping. |
| `threat.report.id` | Vendor report ID — stable, non-null; **dedup key** (reports re-ingest on update) |
| `threat.report.name` | Report title |
| `threat.report.description` | Report summary / abstract |
| `threat.report.time.created` | Report creation timestamp (RFC3339 / ISO8601) |
| `threat.report.time.updated` | Report last-modified timestamp |

**Do NOT require** (absent by design; flagging them is a false positive): `finding.*`, `object.*`,
`object.type`, `dt.security.risk.level` / `dt.security.risk.score`, `scan.id` / `scan.name`,
`component.*` / `software_component.*`.

**Recommended** (populate when the source provides them; missing → `minor`): `threat.actor.names`,
`threat.target.countries.names` / `.iso_codes`, `threat.target.industries`, `threat.malware.families`,
`threat.attack.{tactic,technique,subtechnique}.{ids,names}`, `threat.attack.version`.

**Optional** IOCs / metadata: `threat.report.author` / `.references.urls` / `.tags`,
`threat.observables.{ips,domains,urls,emails,cves,hashes.md5,hashes.sha1,hashes.sha256}`.

- **No scan reference** — `THREAT_REPORT` has no scan cycle; do not require or flag `scan.id`.
- **No object-type / finding.type namespace checks** — `THREAT_REPORT` has no `object.type` or `finding.type`; skip those namespace rules entirely.
- **Vendor extensions** `alienvault.pulse.*` and `crowdstrike.report.*` are additive (no SD counterpart) — accept them; they are not duplication (see [Known Discrepancies](#known-discrepancies) and the Vendor Namespace Duplication Check below).
- All `threat.*` fields are SD **experimental** — verify current stability against the live SD per the authority rule before relying on a specific field.

---

## Risk Fields and Auto-Mapping

`dt.security.risk.level` and `dt.security.risk.score` MAY be absent if `finding.severity` carries standard values that enable auto-mapping.

**Auto-mapping rule** (Dynatrace OpenPipeline behavior):

- `finding.severity` values `critical|CRITICAL|BLOCKER` → `dt.security.risk.level = CRITICAL`
- `high|HIGH|MAJOR` → `HIGH`
- `medium|MEDIUM|WARNING` → `MEDIUM`
- `low|LOW|MINOR|INFO|INFORMATIONAL` → `LOW`
- `dt.security.risk.score` is auto-derived from `dt.security.risk.level` when absent.

If `finding.severity` uses non-standard values or is absent and `dt.security.risk.level` is also absent, flag as **critical**.

If `dt.security.risk.score` is provided as a string instead of a number, flag as **major** (type mismatch).

---

## Scan Reference Requirement (Static Mapping Validation)

For `VULNERABILITY_FINDING` and `COMPLIANCE_FINDING` events in static mapping validation:

- `scan.id` — **required** (flag as major if absent)
- `scan.name` — recommended (flag as minor if absent)

Detection findings (`DETECTION_FINDING`) do **not** require scan references.

---

## Scan Event Field Scope

Scan events (`VULNERABILITY_SCAN`, `COMPLIANCE_SCAN`) are **coverage events** — they record that a specific object (code artifact, container image, host, etc.) was assessed at a point in time. They are not finding containers.

**Allowed on scan events:**

- Standard event fields: `event.id`, `event.kind`, `event.type`, `event.provider`, `event.description`
- Scan identity: `scan.id`, `scan.name`, `scan.status`, `scan.time.started`, `scan.time.completed`
- Object identity: `object.id`, `object.name`, `object.type`, plus the object-type namespace fields (`artifact.*`, `container_image.*`, `host.*`, etc.)
- Provider / product: `product.vendor`, `product.name`
- Vendor-namespace project/scan-level context: e.g. `checkmarx.project.*`, `wiz.scan.*` (NOT severity-derived — see below)
- Total finding count for the scanned object (e.g. `scan.findings.total`) — acceptable as a coverage stat **only when scoped to the same object the scan event covers**

**Not allowed on scan events:**

- Per-finding identity or characteristic fields: `finding.id`, `finding.title`, `finding.time.created`, `finding.type`, `finding.severity`, `finding.score`, `finding.url`, `finding.status`
- Vendor-namespace per-finding fields: `*.finding.*` sub-namespaces (e.g. `checkmarx.finding.*`) — these encode per-finding metadata and belong on finding events only
- Vulnerability-specific fields: `vulnerability.*`, `dt.security.risk.level`, `dt.security.risk.score`
- Component fields: `component.*`, `software_component.*`
- **Severity-derived insights of any granularity** — including aggregate severity-broken counts (`scan.findings.critical`, `scan.findings.high`, `scan.findings.medium`, `scan.findings.low`, `scan.summary.severity.*`), "highest severity found" indicators, or any vendor-namespace mirror of these (e.g. `<vendor>.scan.highest_severity.*`, `<vendor>.scan.severity_breakdown.*`). Severity insights belong on the corresponding finding events; to derive them for a scan, query the finding events joined on `scan.id`.

**Validation rule:**

When `finding.*`, `*.finding.*`, or any severity-derived field appears on a scan event, inspect each field individually:

| Observed field | Classification | Action |
|---|---|---|
| Per-finding identity or characteristic (ID, title, type, severity of a specific finding) | **major** | Flag and suggest removal |
| Vendor `*.finding.*` sub-namespace on a scan event | **major** | Flag and suggest removal; these fields belong on finding events |
| Severity-derived aggregate counts on a scan event (`scan.findings.critical`, `scan.findings.high`, `<vendor>.scan.severity_breakdown.*`, etc.) | **major** | Flag and suggest removal. Severity insights live on finding events; consumers derive them by joining finding events on `scan.id`. Do not propose moving these under a vendor namespace — that just relocates the same problem |
| "Highest severity found" / single-most-severe-finding indicators on a scan event (whether canonical or vendor-namespaced) | **major** | Flag and suggest removal — same reasoning |
| Total scanned-object finding count (e.g. `scan.findings.total`, no severity breakdown) scoped to the same object as the scan event | acceptable | Note as informational coverage stat; flag as **minor** if field naming is ambiguous |
| Aggregate scan-level summary spanning multiple objects (e.g. project-wide or tenant-wide totals) on a per-object scan event | **minor** | Suggest moving under `<vendor>.scan.summary.*` or removing — does not match per-object coverage model. Severity-broken multi-object aggregates remain disallowed under the rule above |

---

## Vulnerability Findings — Component Namespace

For `event.type = VULNERABILITY_FINDING`, the mapping must include at minimum:

- `component.name` — **required** (major if absent)

Highly recommended:

- `component.version`
- `software_component.name` (for `DEPENDENCY_VULNERABILITY` finding.type — see below)
- `software_component.purl` — SD-canonical experimental field (SD 1.320.0); validates as a proper PURL string (e.g. `pkg:maven/...`, `pkg:npm/...`, `pkg:go/...`). Do **not** flag as unknown or extension.
- `vulnerability.references.cve` when the vendor provides CVE data

### `software_component.supplier.name` — User-Friendly Supplier Name

`software_component.supplier.name` carries a user-friendly supplier / project / publisher label. It is acceptable for this value to overlap with `component.name` or `software_component.name` when the supplier is the same logical organization that ships the package — for example, Black Duck's `componentName = "Netty Project"` is simultaneously the SCA group label *and* the supplier identifier.

Do **not** flag this overlap as duplication. Flag as **minor** only when:

- The supplier value is set to a literal copy of the package coordinates (e.g. `software_component.supplier.name = "io.netty:netty-buffer"`) rather than a human-readable supplier label, **or**
- The vendor exposes a distinct supplier / maintainer / publisher field that would be a better source than the package name.

---

## External Compliance Integration — Field Conventions

`compliance.result.*` and `compliance.standard.*` are **reserved for Dynatrace SPM internal events**. External (non-DT) compliance integrations MUST NOT use these namespaces. Rule identity, by contrast, uses the **generic `rule.*` namespace** for all compliance findings (external and SPM) — see `semantic-reference.md § Rule Identity Namespace`.

### Rule Fields (External Compliance)

External compliance integrations MUST use the generic `rule.*` namespace for rule identity and context:

| Target Field | Required | Notes |
|---|---|---|
| `rule.id` | yes | Stable unique rule identifier |
| `rule.name` | yes | Rule name. Use `rule.name`, **not** `rule.title`. (Canonical rule-identity field, aligned to OTel/OCSF/ECS.) |
| `rule.description` | recommended | Full rule description |
| `rule.type` | optional | Rule category or type classification |

`compliance.rule.id` / `compliance.rule.title` are the **legacy** form of `rule.id` / `rule.name`. On a new mapping, propose the generic `rule.*` fields. When validating an already-ingested or live event, accept legacy `compliance.rule.id` / `compliance.rule.title` (still emitted in current runtime) but recommend migration — do **not** flag them as major. Flag `compliance.result.*`, `compliance.standard.*`, or `compliance.rule.severity.*` on an external integration event as **major** — those remain SPM-internal.

### Status Fields (External Compliance)

External compliance integrations MUST use finding-level fields for result status:

| Target Field | Required | Notes |
|---|---|---|
| `finding.severity` | yes | Standard SD severity string (e.g. `HIGH`, `MEDIUM`, `LOW`, `NONE`) — also drives `dt.security.risk.level` auto-mapping |
| `finding.result` | recommended | Per-finding result status from the vendor (`PASS`, `FAIL`, `MANUAL`, etc.). Source from the vendor `result` field. |
| `finding.status` | optional | Workflow state (e.g. `OPEN`, `RESOLVED`) |

Flag any `compliance.result.*` field on an external integration event as **major** — these fields are SPM-internal.

### Acceptable Compliance Extensions (Cross-Integration Standard)

The following fields are **not** in the Semantic Dictionary but are an established cross-integration extension pattern for compliance findings. Do **not** flag them as unknown:

| Field | SD status | Pattern | Notes |
|---|---|---|---|
| `compliance.control` | absent | cross-integration extension | Vendor rule short-ID or control reference (e.g. Wiz `shortId`). Confirm field name is consistent across integrations. |
| `compliance.standards` | absent | cross-integration extension | Array of compliance framework names associated with the finding. |
| `compliance.requirements` | absent | cross-integration extension | Array of requirement/sub-category references within the frameworks. |

`compliance.standard.name`, `compliance.standard.short_name`, and `compliance.standard.url` are **SPM-only** SD fields — do not use them in external integrations. Flag as **major** if present.

---

## Object-Type Namespace Requirements

For each observed `object.type`, validate the presence of its expected namespace:

| object.type | Required namespace | Minimum expected fields | Severity if missing |
|---|---|---|---|
| `CODE_ARTIFACT` | `artifact.*` | `artifact.name` or `artifact.id`, `artifact.path`, `artifact.repository` | major |
| `CONTAINER_IMAGE` | `container_image.*` | `container_image.digest` (primary — immutable identity, required for deduplication and Smartscape enrichment); `container_image.name` (supplementary) | major |
| `HOST` | `host.*` | `host.name` or `host.ip` | major |
| `K8S_POD` | `k8s.*` | `k8s.pod.name`, `k8s.namespace.name`, `k8s.cluster.name` | major |
| `AwsEc2Instance` | `aws.*` | `aws.resource.id`, `aws.region` | major |
| `AwsEksCluster` | `aws.*` | `aws.resource.id`, `aws.region` | major |
| `URL` | URL fields | `url.domain` or `url.path` | major |
| `PROCESS` / `PROCESS_GROUP` | none required for static mapping | `dt.entity.*` / `dt.smartscape.*` / `dt.source_entity` are post-ingest enrichment, not mapping inputs (see `intake-and-constraints.md § Smartscape Enrichment Fields Are Post-Ingest`); validate at runtime in Workflow B2 only | n/a (not flagged in static validation) |

See `intake-and-constraints.md § Object Type Expectations` for full companion field tables and samples.

---

## finding.type Namespace Requirements

For each observed `finding.type`, validate the presence of its expected namespace:

| finding.type | Required namespace | Minimum expected fields | Severity if missing |
|---|---|---|---|
| `DEPENDENCY_VULNERABILITY` | `software_component.*` | `software_component.name` | major |
| `CODE_ISSUE` | `code.*` | `code.filepath` or `code.line.number` | major |
| `CODE_VULNERABILITY` | `code.*` | `code.filepath` or `code.line.number` | major |
| `CODE` | `code.*` | `code.filepath` | major |
| `EXPOSED_SECRET` (in code artifact) | `code.*` | `code.filepath` | major |
| `CONFIGURATION_ISSUE` | none mandatory | — | info only |

---

## Known SD Discrepancies and Unknown Fields

### Acceptable Discrepancies

Fields listed in § Known Discrepancies (in this file) are **acceptable** deviations.
Do not raise critical or major issues for them.

Examples of acceptable absences: `event.start`, `event.end`.
Examples of acceptable extensions: `finding.severity`, `event.category`, `actor.*`.

### Unknown Fields

Classify a field by working through this resolution order — stop as soon as one step resolves it:

1. **Local references** (§ Known Discrepancies in this file, `semantic-reference.md § Data Model Notes`) — if listed as acceptable or documented, it is **not unknown**.
2. **Live SD** (`dt.semantic_dictionary.fields`) — if present there (even if absent from local references), it is **not unknown**; note the drift in the validation report and flag a PR follow-up. See `mapping-workflow.md § Shared: Verifying Against the Live Semantic Dictionary` for DQL patterns.
3. **Baseline samples** (`samples/`) — consult **only** when steps 1 and 2 leave the field unresolved. If the field appears in any local sample it is a likely known pattern; verify against the live SD before accepting it and note the gap in local references.
4. **Genuinely unknown** — absent from all three sources above: raise a **major** discrepancy and ask:

- What is the purpose of this field?
- Does it overlap with any existing SD field?
- Should it be namespaced under the vendor name (e.g. `vendorname.field`)?

### Vendor-Specific Extensions (Expected and Valued)

Vendor-namespace fields (`wiz.*`, `snyk.*`, `qualys.*`, `tenable.*`, etc.) are an expected and valued extension pattern — **not** "unknown" fields. See `§ Vendor-Specific Namespaces (Expected & Valued) in this file for the canonical pattern, criteria, and per-finding-class examples.

Apply the *Vendor Namespace Duplication Check* below to detect the one actionable case: when the SD field is absent or empty while the vendor field carries the value.

### Vendor Namespace Duplication Check

Vendor-namespace fields may carry the same value as SD-canonical fields — this is acceptable to keep (users may be accustomed to querying by vendor field names), but it should be flagged as **redundant** at `info` severity because the SD field already carries the value and the vendor field adds no new information. Every vendor-namespace field should be compared against the SD field that carries the same semantic meaning. Apply this rule in **all validation modes** — Workflow A (mapping suggestion), Workflow B1 (static), and Workflow B2 (runtime).

For each `<vendor>.<path>` field in the mapping (or in the live event), classify against its SD counterpart:

| Relationship to SD field | Verdict | Severity |
|---|---|---|
| Vendor field value is **identical** to the SD field value (exact match) | Redundant — SD field is populated with the same value; vendor field adds no new information. Acceptable to keep for query familiarity but flag as redundant. | `info` |
| Vendor field is a **trivial transformation** of the SD field (case change, whitespace, simple cast) | Redundant — same reasoning as identical match. Flag as redundant. | `info` |
| Vendor field carries **strictly more detail** than the SD field (richer structure, additional sub-keys) | Acceptable — keep, document the additive value | `pass` |
| Vendor field is a **subset / summary** of the SD field | Redundant — the SD field is richer; vendor field adds no new information. Flag as redundant. | `info` |
| Vendor field carries data **the SD field does not capture at all** (e.g., vendor-internal IDs, vendor-specific tags) | Acceptable — this is the intended use of the vendor namespace | `pass` |
| Vendor field is **populated while the SD field is empty / null** | Mapping bug — backfill the SD field from the vendor value | `major` |

**Common duplication patterns to look for explicitly:**

| SD-canonical field | Common vendor mirror to check | Verdict when SD field is populated |
|---|---|---|
| `rule.name` (canonical; legacy `compliance.rule.title`) | `<vendor>.rule.name`, `<vendor>.rule.title` | Redundant (`info`) — flag as redundant, no removal required |
| `compliance.remediation.description` | `<vendor>.finding.remediation`, `<vendor>.rule.remediation_instructions` | Redundant (`info`) — flag as redundant, no removal required |
| `rule.description` (canonical; legacy `compliance.rule.description`) | `<vendor>.rule.description` | Redundant (`info`) — flag as redundant, no removal required |
| `finding.severity` | `<vendor>.finding.severity` | Redundant (`info`) — flag as redundant, no removal required |
| `finding.title` | `<vendor>.finding.title`, `<vendor>.finding.name` | Redundant (`info`) — flag as redundant, no removal required |
| `finding.time.created` | `<vendor>.finding.last_seen_at`, `<vendor>.finding.updated_at`, `<vendor>.finding.updateDate` | Redundant (`info`) — flag as redundant, no removal required. Note: `<vendor>.finding.created_at` / `<vendor>.finding.first_seen_at` carry a **different semantic** (initial creation date) — do not flag them as duplicates of `finding.time.created`, and do not use them as its source. |
| `vulnerability.cvss.base_score` | `<vendor>.cvss_base_score` | Redundant (`info`) — flag as redundant, no removal required |
| `object.id`, `object.name` | `<vendor>.resource.id`, `<vendor>.resource.name` | Redundant (`info`) — flag as redundant, no removal required |

**For all rows above:** if the SD field is **empty or absent** while the vendor field is populated, flag as **major** (missed mapping — backfill the SD field from the vendor value).

**Output expectation:** the validation report must include a **Vendor Namespace Duplication** subsection listing each vendor-namespace field alongside its SD counterpart and whether the SD field is populated. When both are populated with the same value, flag the vendor field as **redundant** (`info`) — no removal required, but the redundancy should be noted. The only actionable finding is when the SD field is empty or absent while the vendor field is populated — flag that as **major**. If no vendor-namespace fields are present, state that explicitly.

**How to apply (static inspection — works on any sample event):**

Enumerate the top-level vendor-namespace keys in the event (from `dt.raw_data`, the mapping table, or a pasted payload). For each key whose prefix matches a vendor namespace (e.g., `wiz.*`, `snyk.*`, `qualys.*`), look up the corresponding SD-canonical field in the *Common duplication patterns* table above. Compare the value of the vendor field against the value of the SD field in the same event. Apply the verdict table to classify each pair.

This check is a **static field-comparison** on a single sample event. It does not require a live environment connection — it applies equally to:
- A mapping table or pasted sample payload (Workflow B1 static validation).
- A sample event fetched from the live environment (Workflow B2 runtime validation, after Q11/Q12).

For optional **scale confirmation** across many live events, see `runtime-validation.md § Vendor Namespace Duplication Check`.

---

## Value and Type Checks

Flag these:

1. `dt.security.risk.score` provided as string instead of number → **major**
2. Timestamps not in RFC3339 / ISO8601 format → **major**
3. Required ID fields that are empty or null → **critical**
4. Arrays mapped to scalar targets without explicit transformation → **major**
5. Object/record values mapped directly to string fields → **major**
6. Enum values outside known sets (`dt.security.risk.level`, `event.type`) → **critical**
7. `vulnerability.remediation.fix_version` (singular) used instead of `vulnerability.remediation.fix_versions` → **major**
8. `vulnerability.remediation.fix_versions` present but not an array of strings → **major**
9. `vulnerability.remediation.fix_versions` present as empty array or null → **minor** (remove field instead)
10. `vulnerability.external_url` must be a single string URL; arrays or multi-value encodings in this field → **major**
11. `vulnerability.cvss.version` must be version number only (e.g. `3.1`, `4.0`); prefixed/text variants like `CVSSv3`, `Cvss3`, `v3.1` → **major**
12. `vulnerability.cvss.*` fields must describe a **single CVSS version per finding** — the version the vendor uses as the authoritative source for the finding's severity. When the vendor exposes multiple CVSS versions in parallel (e.g. CVSS3 and CVSS4), select the version the vendor itself relies on for that finding (typically the latest available), and populate `vulnerability.cvss.version`, `vulnerability.cvss.base_score`, and `vulnerability.cvss.vector` from that version only. Do **not** introduce version-suffixed fields such as `vulnerability.cvss.v3.vector` or `vulnerability.cvss.v4.vector` → **major**. The non-authoritative CVSS version's data should be dropped, not preserved alongside.
13. Vendor-namespace field whose value is identical (or a trivial transform) of an SD-canonical field's value → **info** (redundant — SD field is populated with the same value; vendor field adds nothing new but may be kept for query familiarity). Escalate to **major** if the SD field is empty while the vendor field is populated — that is a missed mapping. See *Vendor Namespace Duplication Check*.
14. `product.vendor` and `event.provider` refer to the same vendor but differ only by casing or punctuation normalization (for example `Crowdstrike` vs `CrowdStrike`) → **minor** normalization inconsistency. Keep semantic value stable, but normalize to a single canonical spelling for reliable grouping/filtering.
15. For final ingested events with `event.original_content` populated: compare `finding.severity` against the vendor's own severity field inside `event.original_content` (typically `severity`, `issue_severity`, or equivalent). If the values differ semantically (e.g. vendor says `"Medium"` but `finding.severity` = `"LOW"`), flag as **major** — the mapped field disagrees with the vendor's own classification. Verify the correct source field and backfill `finding.severity`; re-derive `dt.security.risk.level` and `dt.security.risk.score` from the corrected value. Note: case-only differences (e.g. `"medium"` vs `"MEDIUM"`) are **minor** normalization; semantic differences in risk band are **major**.
16. IP-typed SD fields mapped or received as plain `string` instead of `ipAddress` (or `ipAddress[]` for arrays) → **major** (type mismatch). Affected fields: `actor.ips` (`ipAddress[]`), `host.ip` (`ipAddress[]`), `client.ip` (`ipAddress`). Arrays of IP strings are not automatically equivalent to `ipAddress[]`; the mapping must explicitly target the correct SD type. The OpenPipeline-valid cast is the `ip()` network function (see `intake-and-constraints.md § Producing ipAddress-typed values`).
17. A suggested or provided **transform relies on a DQL construct not available in OpenPipeline processors** → **major**. Transforms run as OpenPipeline processors at ingest, which support a restricted DQL subset. Flag the unavailable construct and suggest the OpenPipeline-valid alternative. Common violations: `jsonPath()` or `parseJson` for nested-JSON extraction (use `parse` JSON DPL → `fieldsFlatten`/subscript access instead); query/aggregation commands (`summarize`, `join`, `lookup`, `makeTimeseries`, `dedup`, `sort`, `filter` as a query stage) — processors are per-record and these are not available; any function not in the supported function classes (string, conversion/cast, conditional, boolean, array, network, time, math, hash, general). See `intake-and-constraints.md`.

### Provider-Vendor Canonicalization Check

Run this in static validation outputs whenever both fields are present:

- Compare `lower(product.vendor)` vs `lower(event.provider)`.
- If equal but raw strings differ, classify as a **case-only mismatch** (`minor`).
- If not equal, classify as a **semantic mismatch** (`major`) unless the mapping contract explicitly documents different intended meanings for provider vs vendor.

Expected validation output:

| Condition | Verdict | Severity | Action |
|---|---|---|---|
| Exact match (`product.vendor == event.provider`) | pass | `pass` | none |
| Same semantic value after normalization (`lower(...)` equal), raw values differ | normalization mismatch | `minor` | normalize canonical spelling |
| Different semantic values (`lower(...)` differ) | mapping mismatch | `major` | align mapping or document intentional divergence |

---

## Cross-Integration Comparison

Consult `samples/` for cross-integration confirmation **only when the primary references leave a specific mapping choice uncertain** — an unfamiliar field, a suspicious value pattern, or weak evidence on an optional namespace. Do not run this check unconditionally on every mapping.

When samples are consulted:

1. Detect target field usage not seen in any local sample — flag as a candidate unknown and verify against the live SD before classifying.
2. Detect weak mappings where richer SD fields are populated in comparable integrations.
3. Detect value-pattern contradictions across providers (e.g. mixed case on enum-like fields).

---

## Validation Input Mode And Raw Content Fields

Workflow B validations must first identify input mode:

1. **Final ingested event validation**
	- `dt.raw_data` is **always** populated by OpenPipeline at ingest with the full raw event envelope as received. Its presence is platform behavior, not a mapping signal — do **not** flag dual presence with `event.original_content` as a discrepancy, and do not recommend dropping `dt.raw_data` from the integration.
	- `event.original_content` is set by **extension-based / pull integrations** to carry the original vendor API response payload separately from the SD-mapped fields.
	- Canonical raw-content source for comparison:
	  - **Extension-based / pull integrations:** prefer `event.original_content` (it carries vendor-raw content, distinct from the SD-mapped envelope that lives in `dt.raw_data`).
	  - **Push-based integrations:** use `dt.raw_data` — the envelope is the raw ingested vendor payload in this case.
	- For extension-based / pull integrations, `event.original_content` must be populated on **every event the integration emits**, including scan events (`VULNERABILITY_SCAN`, `COMPLIANCE_SCAN`). The scan-event `event.original_content` should carry the raw vendor content that the scan event was derived from — for example, the journal / scan-completion payload, the assessment summary, or the equivalent vendor record. Missing `event.original_content` on a scan event from an extension-based integration is a **major** mapping gap.
	- If no raw vendor payload is recoverable from either field, flag as **major** (insufficient evidence for final-ingested validation).

2. **Theoretical mapping validation**
	- Validate mapping table/output directly against vendor API samples.
	- Do not require `dt.raw_data` or `event.original_content`; absence is expected and should not be flagged.
	- Do not fail validation for missing explicit mappings of ingest-generated fields (`event.id`, `timestamp`).

---

## Optional Runtime Validation Checks

When tenant-backed validation is requested, run query checks from `runtime-validation.md`.

Minimum runtime checks:

1. Findings exist for requested `event.provider`.
2. Scans exist for the same provider (when scans are expected); if not, raise a `warning` and continue.
3. Findings-to-scan linkage (`scan.id`) has no unexplained orphan findings; non-zero orphan counts raise a `warning`.
4. Scan reference coverage on `VULNERABILITY_FINDING` and `COMPLIANCE_FINDING` rows is present or explained; missing coverage raises a `warning`.
5. `dt.security.risk.level` values are valid SD values.
6. `object.type` distribution is plausible for integration scope.
7. `dt.security.risk.score` aligns with expected risk level thresholds.
8. Sample events are fetched with `| limit 1` for relevant `object.type` values and checked for required semantic field structure.
9. Vendor-namespace fields do not duplicate SD-canonical field values (see *Vendor Namespace Duplication Check*); duplicate pairs raise a `warning` (or a missed-mapping `fail` if the SD field is empty while the vendor field is populated).

---

## Discrepancy Severity

| Severity | Criteria |
|---|---|
| `critical` | Missing required field that cannot be auto-derived; invalid `event.type`; null required ID; invalid risk level enum |
| `major` | Missing object-type namespace; missing finding.type namespace; missing scan reference for V/C in static mapping validation; missing `component.name` for vulnerability; unknown field; type mismatch; weak risk mapping |
| `minor` | Missing optional enrichment; `scan.name` absent; optional CVE reference absent; minor naming inconsistency; optional remediation field present but empty |
| `info` | SD divergence that is already on the known-discrepancies list |

---

## Acceptance Criteria

A mapping passes validation when:

1. All required semantic fields are present or auto-derivable.
2. No critical discrepancies remain unresolved.
3. All major discrepancies have either been fixed or carry explicit documented justification.
4. `object.type` namespace checks pass for all observed object types.
5. `finding.type` namespace checks pass for all observed finding types.
6. Static mapping includes scan references for vulnerability and compliance findings.
7. Non-vendor-namespace unknown fields have been explained and accepted or removed. **Vendor-namespace fields** (e.g., `wiz.*`, `snyk.*`) do not require explanation — they are valued context and are not counted as "unknown".
8. Validation input mode is explicitly documented (final ingested vs theoretical), and raw-content source is identified when applicable.
9. If runtime validation is enabled, failed runtime checks are documented with remediation actions.
10. Runtime warnings (for example missing scans or orphan findings) are documented with probable causes and follow-up actions; warnings alone do not fail the mapping.
11. Runtime validation output should use a `Validation Summary` table with statuses `🟢 pass`, `🟡 warn`, `🔴 fail` (not a bullet-list summary).
12. Unknown fields have been explained and accepted or removed.


---

## Known Discrepancies


Documented deviations between the Semantic Dictionary (SD) definition for
`security.events` and the fields observed in real integration sample payloads.

**This list defines the acceptance baseline.** When validating a new mapping:

- Fields on this list that are absent or divergent are **acceptable** — do not
  raise a critical or major discrepancy for them.
- Fields that appear in **both** this list and the candidate mapping confirm
  alignment with existing integrations.
- Fields that are **not** on this list, not in the SD, and not in any local
  sample in `samples/` must be **questioned** (see `§ Known SD Discrepancies and Unknown Fields in this file`).

Reference: https://docs.dynatrace.com/docs/semantic-dictionary/model/security-events

---
## Vendor-Specific Namespaces (Expected & Valued)

Vendor-namespace fields (e.g., `wiz.*`, `snyk.*`, `qualys.*`, `tenable.*`, `sonatype.*`, `gitlab.*`, `github.*`) are **not** considered discrepancies or "unknown" fields.

They represent an **expected and valued** extension pattern across all finding types:

- **Detection findings**: `dt.security.rap.*` (DT RAP internal), `rule.id` / `rule.name` (SIEM/WAF)
- **Vulnerability findings**: `snyk.*`, `qualys.*`, `tenable.*`, `sonatype.*`, `github.*`, `gitlab.*`
- **Compliance findings**: `wiz.*`, `qualys.*`, `crowdstrike.*`
- **Threat intelligence reports** (`THREAT_REPORT`): `alienvault.pulse.*` (AlienVault OTX — `.public`, `.tlp`), `crowdstrike.report.*` (CrowdStrike Falcon Intelligence — `.slug`, `.type`, `.type.id`, `.type.name`). No SD counterpart — additive vendor context.

**Vendor namespace fields should appear in mappings** to preserve valuable vendor-specific context and provide audit traceability back to source systems.

When validating mappings, do not flag vendor-namespace fields as "unknown" — confirm they are:
1. Properly namespaced (lowercase vendor prefix + field name)
2. Sourced from documented vendor API fields
3. Values are well-formed and meaningful

---

## TOC

- [All Finding Types](#all-finding-types)
- [Detection Findings](#detection-findings)
- [Vulnerability Findings](#vulnerability-findings)
- [Compliance Findings](#compliance-findings)

---

## All Finding Types

| Field | SD Status | Sample Status | Acceptable? | Notes |
|---|---|---|---|---|
| `object.type` (vendor-reported value) | Required | Vendor-extensible | ✅ Yes | `object.type` accepts whatever the vendor reports (e.g. `AWS::EC2::Instance`, `AWS::IAM::Role`, vendor-specific resource taxonomies). Smartscape-style canonical enum (`AwsEc2Instance`) is required ONLY when the integration opts into runtime contextualization for an officially supported type. See `intake-and-constraints.md § Vendor-Reported object.type Values Are Accepted` |
| `event.start` | Required | Absent | ✅ Yes | SD requires earliest activity timestamp; `timestamp` / `finding.time.created` used instead |
| `event.end` | Required | Absent | ✅ Yes | SD requires latest activity timestamp; same rationale as `event.start` |
| `event.name` | Absent | Present (all) | ✅ Yes | User-friendly label for the `event.type` value; set as a constant per integration following the pattern `"<Type> event"` — e.g. `DETECTION_FINDING` → `"Detection finding event"`, `VULNERABILITY_FINDING` → `"Vulnerability finding event"`, `COMPLIANCE_FINDING` → `"Compliance finding event"`, `VULNERABILITY_SCAN` → `"Vulnerability scan event"`, `COMPLIANCE_SCAN` → `"Compliance scan event"` |
| `event.description` | Absent | Present (most) | ✅ Yes | Free-text description; common enrichment extension |
| `event.category` | Absent | Present (most) | ✅ Yes | High-level category (e.g. `VULNERABILITY_MANAGEMENT`); not in SD |
| `event.version` | Optional | Present (most) | ✅ Yes | Schema/format version from external providers |
| `finding.severity` | Absent | Present (all) | ✅ Yes | Vendor-reported severity string. SD normalised equivalent is `dt.security.risk.level`; both coexist |
| `finding.score` | Absent | Present (many) | ✅ Yes | Vendor numeric score. SD equivalent is `dt.security.risk.score` |
| `finding.description` | Absent | Present (many) | ✅ Yes | Extended description; acceptable extension |
| `finding.url` | Absent | Present (most) | ✅ Yes | Deep-link to finding in source system |
| `finding.status` | Absent | Present (some) | ✅ Yes | Open/closed/detected status from external providers |
| `finding.tags[]` | Absent | Present (some) | ✅ Yes | Freeform classification tags (e.g. CodeQL categories) |
| `dt.security.risk.score` | Absent on DETECTION | Present (all) | ✅ Yes | Normalised numeric score; not in SD for Detection Finding |
| `dt.openpipeline.source` | Absent | Present (all) | ✅ Yes | Platform ingestion metadata |
| `dt.openpipeline.pipelines[]` | Absent | Present (all) | ✅ Yes | Pipeline processing metadata |
| `dt.security_context` | Absent | Present (some) | ✅ Yes | Cost/security context metadata |
| `dt.cost.*` | Absent | Present (some) | ✅ Yes | Cost attribution metadata |

---

## Detection Findings

Fields observed in `samples/external-detections.json`, `samples/dynatrace-detections-rap.json`, `samples/dynatrace-detections-automated.json`.

| Field / Namespace | SD Status | Acceptable? | Notes |
|---|---|---|---|
| `actor.ips[]` | Absent | ✅ Yes | Source IP addresses; DT RAP, Automated K8s, external. SD type: `ipAddress[]` |
| `actor.geo.*` | Absent | ✅ Yes | Geo-enrichment from external providers (city, country, continent, region, lat/lon) |
| `actor.fqdns` | Absent | ✅ Yes | Reverse-DNS resolved hostname(s) — AWS Security Hub |
| `detection.id` / `.title` / `.description` | Absent | ✅ Yes | DT Automated Detections internal rule metadata |
| `detection.owner.id` | Absent | ✅ Yes | DT detection rule ownership |
| `detection.mitre.ids[]` | Absent | ⚠ Legacy | Older DT detection rule definition pattern. **Do NOT use for new mappings** — emit `threat.attack.*` instead (see row below). Existing integrations may keep `detection.mitre.ids[]` for backward compatibility. |
| `detection.action` / `detection.type` | Absent | ✅ Yes | Action / rule-type from external providers |
| `threat.attack.*` | **SD-canonical** | ✅ Yes — **canonical SD pattern** | The canonical SD namespace for MITRE ATT&CK enrichment on detection findings (defined in `source/fields/signal_fields/threat.yaml` in the SD repo). Use this for ALL new detection mappings. Key fields: `threat.attack.tactic.ids[]` (TA-prefixed), `threat.attack.tactic.names[]`, `threat.attack.technique.ids[]` (T-prefixed), `threat.attack.technique.names[]`, `threat.attack.subtechnique.ids[]` (dotted, e.g. `T1059.003`), `threat.attack.subtechnique.names[]`, `threat.attack.version`. Supersedes `detection.mitre.ids[]`. Note: `mitre.attack.enterprise.*` does **not** exist in the SD — do not use or suggest it. |
| `entry_point.*` / `user_controlled_input.*` | Absent | ✅ Yes | DT RAP attack entry-point detail; flat namespace vs SD structured array |
| `dt.security.rap.target.*` | Absent | ✅ Yes | DT RAP target type/name |
| `dt.security.evidence.*` | Absent | ✅ Yes | DT evidence DQL query data |
| `http.request.*` / `http.response.*` | Absent | ✅ Yes | WAF / SIEM HTTP context; not in SD security-events model |
| `url.*` / `client.ip` | Absent | ✅ Yes | URL components and client IP from network layer. `client.ip` SD type: `ipAddress` (scalar) |
| `rule.id` / `rule.name` / `rule.description` / `rule.type` | Absent | ✅ Yes | Generic rule-identity namespace; SIEM/WAF rule identifiers from external providers. Use `rule.name`, **not** `rule.title`. Legacy `rule.title` still appears on current detection events (e.g. `samples/external-detections.json`) — accept it on ingested/live events, recommend migration to `rule.name`. See `semantic-reference.md § Rule Identity Namespace` |
| `execution.id` / `execution.actor.id` | Absent | ✅ Yes | DT AutomationEngine workflow execution context |
| `span.id` / `trace.id` / `trace.is_sampled` | Absent | ✅ Yes | DT RAP distributed tracing context |
| `dt.agent.module.*` | Absent | ✅ Yes | OneAgent module metadata |
| `dt.smartscape.*` | Not in SD | ✅ Yes — post-ingest enrichment | Platform enrichment populated by OpenPipeline at ingest. NOT an integration-emitted field — do not include in mapping; check at runtime only. **Canonical / preferred namespace** (`dt.entity.*` is its deprecated alias). See `intake-and-constraints.md § Smartscape Enrichment Fields Are Post-Ingest`. |
| `dt.entity.*` | Not in SD | ✅ Yes — post-ingest enrichment, deprecated alias | Same as `dt.smartscape.*` but the **deprecated** namespace. Existing rows that carry `dt.entity.*` are valid; new mappings/queries should prefer `dt.smartscape.*`. A row with `dt.smartscape.*` populated and no `dt.entity.*` is completely OK — do NOT flag the missing legacy alias. |
| `event.original_content` | Absent | ✅ Yes | Raw original event payload; WAF / SIEM integrations |
| `server.address` | Absent | ✅ Yes | Akamai SIEM server address |

---

## Vulnerability Findings

Fields observed in `samples/external-vulnerabilities-*.json`.

| Field / Namespace | SD Status | Acceptable? | Notes |
|---|---|---|---|
| `vulnerability.exploit.status` | SD optional | ✅ Yes | Exploit availability; present in some integrations |
| `vulnerability.remediation.*` | SD optional | ✅ Yes | Remediation status, fix versions, description |
| `vulnerability.cvss.*` | SD optional | ✅ Yes | CVSS base score and vector |
| `vulnerability.references.cwe` | Absent | ✅ Yes | CWE references alongside CVE |
| `code.*` | Absent (SD optional for CODE_ARTIFACT) | ✅ Yes | Source file path and line numbers; expected for CODE_ISSUE / CODE_VULNERABILITY |
| `artifact.*` | Absent from SD | ✅ Yes | Code artifact identity; expected for `CODE_ARTIFACT` object type. Also acceptable on `CONTAINER_IMAGE` findings and scans when a specific file within the image is the discovery source — for example, a Helm chart template, Dockerfile, or dependency manifest that references or contains the vulnerable package. In this case `artifact.*` describes the source file that led to the finding, not the scanned image itself. Do not flag `artifact.*` on `CONTAINER_IMAGE` events as a namespace mismatch when this discovery-path context is present. |
| `container_image.*` | Absent | ✅ Yes | Only for CONTAINER_IMAGE findings |
| `software_component.*` | SD optional | ✅ Yes | Vulnerable component details; expected for DEPENDENCY_VULNERABILITY |
| Vendor namespaces (`snyk.*`, `sonatype.*`, `gitlab.*`, `github.*`, `qualys.*`, `tenable.*`) | Absent | ✅ Yes | Vendor-specific context; acceptable extension pattern |
| Threat-intel vendor namespaces (`alienvault.pulse.*`, `crowdstrike.report.*`) | Absent | ✅ Yes | Additive `THREAT_REPORT` context (TLP / public flag / report slug + type). No SD counterpart — not duplication |
| `threat.report.*` / `threat.actor.*` / `threat.target.*` / `threat.malware.*` / `threat.attack.*` / `threat.observables.*` | SD experimental | ✅ Yes | Canonical `THREAT_REPORT` fields; verify stability against live SD |
| `finding.status` | Absent | ✅ Yes | Open/detected/fixed status from source (GitLab, SonarQube) |
| `finding.tags[]` | Absent | ✅ Yes | Category tags from CodeQL / GitHub scanning |
| `finding.time.created` mapped to scan/analysis date or vendor `last_updated`/`updateDate`/`updated_at` field | SD required | ✅ Yes — general pattern | `finding.time.created` represents the **detection occurrence timestamp** — when the finding was detected in the current scan run. Vendor fields named `creationDate`, `created_at`, or `first_seen_at` are **not** the correct source: they capture only the initial issue creation and are not updated on subsequent scans. Map from the vendor's `last_updated`, `updateDate`, `updated_at`, `last_seen`, or the scan/analysis date instead. Do not flag this mapping choice as a discrepancy. |
| `dt.security.risk.score` diverging from `vulnerability.cvss.base_score` | — | ✅ Yes — **recommended pattern** | Vendor post-assessment scoring (e.g. JFrog applicability-adjusted severity, Snyk effective severity, Qualys QDS) augments the raw CVSS base score by factoring in exploit context, applicability, and reachability — intentionally lowering scores on theoretical vulnerabilities to deprioritize noise. `dt.security.risk.score` SHOULD reflect the vendor's adjusted score; `vulnerability.cvss.base_score` SHOULD preserve the original CVSS for reference. Both fields coexisting with different values is correct and expected. **Do NOT flag score divergence between these two fields as a discrepancy.** Only flag if (a) `dt.security.risk.score` is identical to `vulnerability.cvss.base_score` for all events while the vendor is known to provide an adjusted score, or (b) the score-to-level mapping is internally inconsistent (Q6 mismatch > 0). |

---

## Compliance Findings

Fields observed in `samples/external-compliance.json`, `samples/dynatrace-compliance.json`.

**Key convention:** rule identity uses the generic `rule.*` namespace for **all** compliance findings — external and SPM alike (`rule.id` / `rule.name` / `rule.description` / `rule.type`; use `rule.name`, **not** `rule.title`). `compliance.result.*` and `compliance.standard.*` remain SPM-internal; external integrations use `finding.*` for result status. See `semantic-reference.md § Rule Identity Namespace` and `§ External Compliance Integration in this file — Field Conventions` for the full rule set.

| Field / Namespace | SD Status | Acceptable? | Notes |
|---|---|---|---|
| `rule.id` / `rule.name` / `rule.description` / `rule.type` | Absent from SD (proposed, experimental) | ✅ Yes — **cross-integration standard** | The correct targets for rule identity and context on compliance findings (external and SPM). `rule.name` is the canonical rule-name field — do **not** use `rule.title`. Legacy `compliance.rule.id` / `compliance.rule.title` migrate here. |
| `finding.result` | Absent from SD | ✅ Yes — **cross-integration standard** | Per-finding PASS/FAIL/MANUAL result status on external compliance findings. Source from vendor `result` field. |
| `finding.status` | Absent | ✅ Yes | Workflow state (e.g. `OPEN`, `RESOLVED`); acceptable alongside `finding.result` |
| `compliance.status` | Absent | ✅ Yes | Legacy parallel status field; acceptable |
| `compliance.control` | Absent | ✅ Yes — cross-integration extension | Vendor rule short-ID or control reference (e.g. Wiz `shortId`). Present across multiple integrations; do not flag as unknown. |
| `compliance.standards` | Absent | ✅ Yes — cross-integration extension | Array of compliance framework names. Present across multiple integrations; do not flag as unknown. |
| `compliance.requirements` | Absent | ✅ Yes — cross-integration extension | Array of requirement/sub-category references within the frameworks. Present across multiple integrations; do not flag as unknown. |
| `scan.id` / `scan.name` | Absent from SD core | Required by this skill | Static mapping requirement: both vulnerability and compliance findings should carry scan reference; runtime gaps are warning-tier when caused by time-window/linkage limits |
| `compliance.rule.id` / `compliance.rule.title` | Legacy SPM rule identity | ⚠ Legacy — migrate to `rule.*` | Superseded by generic `rule.id` / `rule.name`. Accept on current ingested/live events (still emitted in runtime), but recommend migration. On a **new external mapping**, propose `rule.id` / `rule.name` instead — do not introduce `compliance.rule.id` / `compliance.rule.title`. |
| `compliance.rule.severity.*` | Present for DT SPM | SPM-only | No `rule.*` equivalent in the proposal; stays compliance-namespaced. Flag as **major** on an external integration event. |
| `compliance.result.*` namespace | Present for DT SPM | ❌ Must be absent for external integrations | SPM-only. Flag as **major** on any external integration event. Replace with `finding.result` / `finding.severity`. |
| `compliance.standard.*` namespace (`compliance.standard.name`, `.short_name`, `.url`) | Present for DT SPM | ❌ Must be absent for external integrations | SPM-only. Flag as **major** on any external integration event. |


---

## Report Format


## TOC

- [Workflow A — Phase 1 Output (Suggestion Table)](#workflow-a--phase-1-output-suggestion-table)
- [Workflow A — Phase 2 Output (Sample JSON)](#workflow-a--phase-2-output-sample-json)
- [Workflow B Output (Validation with Diff Table)](#workflow-b-output-validation-with-diff-table)
- [Shared Sections](#shared-sections)

---

## Workflow A — Phase 1 Output (Suggestion Table)

Present this block first. Do not generate Phase 2 until the user approves.

### 1. Mapping Summary

- Vendor:
- Finding types covered:
- Sample count per type:
- Confidence: `high | medium | low`

### 2. Mapping Table

| Source Field | Target Field | Transform | Required | Sample Value | Notes |
|---|---|---|---|---|---|
| `vendor.id` | `event.id` | direct | yes | `abc-123` | |
| `vendor.severity` | `dt.security.risk.level` | enum map | yes | `critical` → `CRITICAL` | |
| — | `event.kind` | constant | yes | `SECURITY_EVENT` | always required |

### 3. Gap Summary

List required fields that could not be satisfactorily mapped:

| Required Field | Status | Reason |
|---|---|---|
| `finding.time.created` | ❌ missing | not provided by vendor API |
| `scan.id` | ⚠ partial | present only in scan events, not findings |

### 4. Discrepancies

| Severity | Category | Issue | Impact | Suggested Fix |
|---|---|---|---|---|
| critical | required-field | `finding.id` not mapped | cannot deduplicate | map stable vendor finding ID |
| major | type-mismatch | score is string not number | weak sorting | cast to numeric |
| minor | enrichment | missing `product.vendor` | weaker attribution | map constant vendor name |

### 5. Additional Sample Requests

1. Payloads with null and missing fields.
2. Payloads from each finding type and severity band.
3. Payloads for each `object.type`.
4. At least one payload per product variant/version if the vendor has multiple feeds.

---

## Workflow A — Phase 2 Output (Sample JSON)

Produce only after user approves Phase 1. One block per `finding.type`.

```json
// Example: DEPENDENCY_VULNERABILITY (Snyk Open Source)
// Transforms applied:
//   vendor.severity "medium" -> dt.security.risk.level "MEDIUM"  [enum map]
//   event.kind = "SECURITY_EVENT"                                [constant]
//   scan.id copied from scan event payload                       [cross-event join]
{
  "event.id": "63f9f2e2-436c-423a-94c1-2139ed9b2fb6",
  "event.kind": "SECURITY_EVENT",
  "event.type": "VULNERABILITY_FINDING",
  "event.provider": "Snyk",
  "timestamp": "2026-04-24T13:35:45.397000000Z",
  "product.vendor": "Snyk",
  "product.name": "Snyk Open Source",
  "finding.id": "35c68ba5-cfbe-49f3-a0a3-1a9c25a05944/OpenTelemetry.Instrumentation.Http1.0.0-rc7",
  "finding.title": "Improper Removal of Sensitive Information Before Storage or Transfer",
  "finding.time.created": "2026-03-17T20:22:49.375000000Z",
  "finding.type": "DEPENDENCY_VULNERABILITY",
  "finding.severity": "medium",
  "dt.security.risk.level": "MEDIUM",
  "dt.security.risk.score": 6.9,
  "object.id": "4ed0e723-9ae9-40c4-ad19-ba217633091c",
  "object.name": "AdService.csproj",
  "object.type": "CODE_ARTIFACT",
  "artifact.name": "AdService.csproj",
  "artifact.path": "src/ad-service/AdService.csproj",
  "artifact.repository": "DynatraceAppSec/unguard",
  "component.name": "OpenTelemetry.Instrumentation.Http",
  "component.version": "1.0.0-rc7",
  "software_component.name": "OpenTelemetry.Instrumentation.Http",
  "software_component.version": "1.0.0-rc7",
  "vulnerability.references.cve": ["CVE-2024-32028"],
  "vulnerability.cvss.base_score": 4.1,
  "scan.id": "8dd82cb0-bbc8-41ea-94aa-07ff1a6f6637",
  "scan.name": "8dd82cb0-bbc8-41ea-94aa-07ff1a6f6637"
}
```

---

## Workflow B Output (Validation with Diff Table)

### 1. Mapping Summary

Same header as Workflow A Phase 1.

### 2. Diff-Highlighted Mapping Table

Marker legend: ✅ ok · ⚠ change · ➕ add · ❌ remove

| Source Field | Current Target | Suggested Target | Transform | Status | Reason |
|---|---|---|---|---|---|
| `vendor.id` | `event.id` | `event.id` | direct | ✅ ok | |
| `vendor.score` | `dt.security.risk.score` | `dt.security.risk.score` | string→number | ⚠ change | must be numeric |
| `vendor.repoName` | `artifact.name` | `artifact.repository` | direct | ⚠ change | repo belongs in `artifact.repository` |
| — | — | `component.name` | constant/map | ➕ add | required for VULNERABILITY_FINDING |
| `vendor.internalRef` | `internal.ref` | — | — | ❌ remove | unknown field, not in SD or local references |

### 3. Gap Summary

Same format as Workflow A Phase 1.

### 4. Coverage Matrices

**Event-type coverage:**

| event.type | Status |
|---|---|
| `VULNERABILITY_FINDING` | ✅ mapped |
| `VULNERABILITY_SCAN` | ❌ missing |

**Object-type namespace check:**

| object.type | Namespace | Status | Missing Fields |
|---|---|---|---|
| `CODE_ARTIFACT` | `artifact.*` | ✅ pass | — |
| `HOST` | `host.*` | ⚠ partial | `host.ip` missing |

**finding.type namespace check:**

| finding.type | Namespace | Status | Missing Fields |
|---|---|---|---|
| `DEPENDENCY_VULNERABILITY` | `software_component.*` | ✅ pass | — |
| `CODE_ISSUE` | `code.*` | ❌ fail | `code.filepath` absent |

### 5. Discrepancies

Same format as Workflow A Phase 1.

### 6. Improvement Plan

1. Immediate blockers to resolve (critical discrepancies).
2. High-value additions (major discrepancies).
3. Additional payloads requested.
4. Regression checks for future vendor schema changes.

### 7. Validation Summary (Optional Runtime Validation)

Include this section only when tenant-backed validation is requested.

Present this section as a table-driven summary. Do not replace it with bullet-list status output.

- Provider: `<event.provider>`
- Time window: `<window>`
- Execution path: live DQL execution

Status legend for runtime tables:

- `🟢 pass` — check passed
- `🟡 warn` — notable issue, but not a blocking runtime failure
- `🔴 fail` — blocking runtime failure or required-structure violation

| Runtime Check | Result | Evidence |
|---|---|---|
| Findings exist for provider | `🟢 pass` / `🔴 fail` | count + event types |
| Scans exist for provider | `🟢 pass` / `🟡 warn` | count + scan types |
| Orphan findings without scan | `🟢 pass` / `🟡 warn` | orphan count |
| Scan reference coverage on findings | `🟢 pass` / `🟡 warn` | missing `scan.id` / `scan.name` counts |
| Risk level values valid | `🟢 pass` / `🔴 fail` | invalid values (if any) |
| Risk score-level consistency | `🟢 pass` / `🔴 fail` | mismatch count |
| Object type distribution sanity | `🟢 pass` / `🟡 warn` / `🔴 fail` | grouped counts |
| Required-field null audit | `🟢 pass` / `🔴 fail` | null-count summary |
| Raw payload availability | `🟢 pass` / `🔴 fail` | missing payload count |
| Sample finding events per object.type (`| limit 1`) | `🟢 pass` / `🔴 fail` | sampled object types + query refs |
| Sample scan events per object.type (`| limit 1`) | `🟢 pass` / `🟡 warn` / `🔴 fail` | sampled scan object types or reason |
| Sample-event structure validation | `🟢 pass` / `🔴 fail` | required field checks on samples |
| Missing-field mapping suggestions | `🟢 pass` / `🟡 warn` / `🔴 fail` | candidate source paths/transforms in priority order: `dt.raw_data`, then `event.original_content`, then vendor samples |

If any check fails, add a one-line remediation action under the table.
If a check is `warn`, add a one-line likely cause and follow-up action under the table.

If required fields are missing, include a dedicated mapping-backfill table:

| Missing Target Field | Source Evidence | Candidate Source Path | Transform | Confidence | Notes |
|---|---|---|---|---|---|
| `object.name` | `dt.raw_data` | `resources[0].details.instanceName` | direct | high | fallback to `object.id` if name absent |
| `object.name` | `event.original_content` | `asset.displayName` | direct | medium | use only when `dt.raw_data` is unavailable |

---

## Shared Sections

These sections appear in both workflows when relevant.

### Confidence Assignment

- `high`: all required fields mapped, all namespace checks pass, scan refs present for V/C.
- `medium`: core mapped but gaps in type-specific namespaces or fewer than 5 samples per type.
- `low`: missing required fields, absent scan events for V/C, or too few samples.
