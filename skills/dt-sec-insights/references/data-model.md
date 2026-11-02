# Security Events Data Model

Canonical reference for `fetch security.events` — event types, providers, fields,
entity scoping. Use this as the field dictionary when building any DQL query against
`security.events`.

> **No default bucket filter.** Security events land in a default security bucket (the name varies
> per tenant — e.g. `default_security`, `default_securityevents`, `default_securityevents_builtin`), but users
> can route them to any custom bucket; do **not** apply
> `dt.system.bucket == "..."` filters in default queries (add one only when the user
> explicitly names a bucket to search).

> **Verification basis.** Field names and enums below were checked against the Semantic Dictionary
> (SD, `main`) **and** against live `security.events` data from Dynatrace demo environments (24 h–7 d windows;
> Automated Detections and `THREAT_REPORT` are not present in every tenant and were checked where available). Where runtime
> and SD disagree, this file documents what the runtime **emits** and flags the SD name as
> "SD:". Values marked "not observed" are defined in SD or documented upstream but had zero rows on
> the checked tenants — treat them as possible, not guaranteed. Fill-rate figures are tenant
> snapshots, not guarantees.

---

## Contents

- [Event Types (`event.type`)](#event-types-eventtype)
  - [RVA cadence](#rva-cadence)
  - [RVA event levels (`event.level`)](#rva-event-levels-eventlevel)
- [Provider Taxonomy](#provider-taxonomy)
- [Common Fields (semantic dictionary required)](#common-fields-semantic-dictionary-required)
- [Entity Scoping Fields](#entity-scoping-fields)
- [Detection Fields (`DETECTION_FINDING`)](#detection-fields-detection_finding)
- [Vulnerability Fields (RVA — raw + post-aggregation)](#vulnerability-fields-rva--raw--post-aggregation)
- [Vulnerability Fields (external + DT-emitted `VULNERABILITY_FINDING`)](#vulnerability-fields-external--dt-emitted-vulnerability_finding)
- [Compliance Fields (SPM)](#compliance-fields-spm)
- [Compliance Fields (external — CSPM / VSPM / external posture tools)](#compliance-fields-external--cspm--vspm--external-posture-tools)
- [Coverage Fields (`VULNERABILITY_SCAN`)](#coverage-fields-vulnerability_scan)
- [Threat Intelligence Fields (`THREAT_REPORT`)](#threat-intelligence-fields-threat_report)
- [Finding ID Format Cheatsheet](#finding-id-format-cheatsheet)
- [SD changes in flight (not emitted yet)](#sd-changes-in-flight-not-emitted-yet)

---

## Event Types (`event.type`)

| Value | Description | Where it comes from |
|---|---|---|
| `DETECTION_FINDING` | Behavioral detection / threat alert | DT RAP (OneAgent — `(product.name == "Runtime Application Protection" OR event.provider == "OneAgent")`), DT Automated Detections (`event.provider == "Dynatrace Automated Detections"`), AutomationEngine, and external detection sources (cloud-security / SIEM / WAF, ingested) |
| `DETECTION_EXECUTION_SUMMARY` | Audit row emitted **per Automated Detections rule run** — was the rule triggered, how many records scanned, did it succeed or warn | DT Automated Detections only. Both `event.provider == "Dynatrace Automated Detections"` and `product.name == "Automated Detections"` are populated; either filter works equivalently. This skill prefers `event.provider == "Dynatrace Automated Detections"` to keep the filter symmetric with `DETECTION_FINDING` queries. One row per rule execution; carries `execution.id`, `execution.stats.*`, `execution.result.status`, `execution.query.timeframe.*` (field names → [§ Automated Detections](#dt-automated-detections-eventprovider--dynatrace-automated-detections)). Not a finding; query separately when investigating "did my rule fire?". Not present in every tenant. SD: model is internal. |
| `THREAT_REPORT` | Threat intelligence report (external campaign / adversary report / IOC feed) — **NOT a finding** | External TI platforms — AlienVault OTX (`event.provider == "AlienVault OTX"`), CrowdStrike Falcon Intelligence (`event.provider == "CrowdStrike"`). Describes threats **in the wild**, not on your entities: no `finding.*` / `object.*` / `dt.security.risk.level`, no affected entity, no scan cycle. Dedup by `threat.report.id`. Query via [threat-intelligence.md](threat-intelligence.md) — **excluded from cross-provider finding summaries and the double-counting guard.** |
| `VULNERABILITY_FINDING` | Software / component vulnerability | **External SCA / SAST / image scanners** (ingested). **Also emitted by Dynatrace's vulnerability-scan-service** as the raw per-scan finding feed (`event.provider` is `Dynatrace` on some tenants and **null** on others for library findings; `OneAgent` for code-level findings) — but use the RVA state-report types below for queries about "current Dynatrace vulnerabilities." |
| `COMPLIANCE_FINDING` | Misconfiguration / policy violation | DT SPM (`product.vendor == "Dynatrace"`) and external compliance / posture tools (ingested) |
| `VULNERABILITY_SCAN` | Coverage event — a vulnerability scan ran | DT RVA (`product.vendor == "Dynatrace"`) and external. `dt.smartscape_source.type` is UPPERCASE (`PROCESS` on all Dynatrace/OneAgent scans). |
| `COMPLIANCE_SCAN` | Coverage event — a compliance scan ran (per-assessment rows: `scan.id`, `scan.title`, `assessment.id`, `compliance.control`) | **External only** in observed data (Microsoft Defender for Cloud); Dynatrace KSPM does not emit it — it emits `COMPLIANCE_SCAN_COMPLETED`. SD: model is internal. |
| `VULNERABILITY_STATE_REPORT_EVENT` | DT RVA per-entity vulnerability snapshot | Dynatrace RVA only (`event.provider == "Dynatrace"`, `event.level == "ENTITY"`) |
| `VULNERABILITY_STATUS_CHANGE_EVENT` | DT RVA state transition (open→resolved, mute, etc.) | Dynatrace RVA only — emitted **on change**, immediate |
| `VULNERABILITY_TRACKING_LINK_CHANGE_EVENT` | DT RVA tracking-link / ticket update (Jira, wiki, …) | Dynatrace RVA only — emitted **on change**, immediate. **Not observed** (0 rows over a 30-day look-back) and not defined in SD: `vulnerability.tracking_link.*` appears on a handful of state-report / status-change rows instead. Keep it in the RVA union; do not rely on it to find links. |
| `COMPLIANCE_SCAN_COMPLETED` | Scan-completion marker (used as inner-join target) | Dynatrace SPM (`product.name == "Security Posture Management"`); the Runecast Analyzer integration also emits it with `product.vendor == "Dynatrace"`. `event.provider` is null on both. |
| `VULNERABILITY_COVERAGE_REPORT_EVENT` | **Deprecated** — use `VULNERABILITY_SCAN` instead | Dynatrace RVA (legacy). Not observed; not in SD. |
| `VULNERABILITY_ASSESSMENT_CHANGE_EVENT` | Assessment-change deltas (carries `vulnerability.previous.davis_assessment.*`); `event.level == "VULNERABILITY"` | Dynatrace RVA. **Still emitted** (regularly) although removed from the SD. Not part of the three-type RVA union; no per-entity detail. |
| `ANNOTATION`, `VULNERABILITY_EXTERNAL_ID_CHANGE_EVENT` | SD-defined only (`ANNOTATION` = assessment / comment annotations, SD model internal) | **Not observed** in the data checked. Do not build queries on them. |

**Critical routing rules:**

- DT RVA uses the three RVA-internal types — **not** `VULNERABILITY_FINDING`. The
  three must be queried together as a union via `in(event.type, {…})`.
- DT SPM uses `COMPLIANCE_FINDING` joined with `COMPLIANCE_SCAN_COMPLETED` on
  `scan.id`.
- External vulnerability / compliance findings always use `VULNERABILITY_FINDING`
  / `COMPLIANCE_FINDING`.
- A few unmapped ingest rows carry a **null `event.type`** (raw vendor payloads that no OpenPipeline rule classified, e.g. Azure secure-score controls); they never match a type filter — ignore them.
- **`THREAT_REPORT` is threat intelligence, not a finding** — never mix it into the
  cross-provider `*_FINDING` summary or the DT-inclusive posture overview. It has its own
  query patterns in [threat-intelligence.md](threat-intelligence.md).

### RVA cadence

- `VULNERABILITY_STATE_REPORT_EVENT` is emitted every ~15 minutes per
  `(vulnerability, affected_entity)` pair.
- `VULNERABILITY_STATUS_CHANGE_EVENT` is emitted on transition (immediate).
- `VULNERABILITY_TRACKING_LINK_CHANGE_EVENT` is emitted on tracking-link update
  (immediate).
- The 30-minute RVA snapshot window guarantees at least one state-report cycle
  is captured.

### RVA event levels (`event.level`)

The three RVA event types (and the legacy assessment-change type) are emitted at **two levels**,
distinguished by `event.level` (SD enum: `ENTITY`, `VULNERABILITY`):

| `event.level` | Grain | Entity fields |
|---|---|---|
| `ENTITY` | one row per `(vulnerability, affected_entity)` (the high-volume level — roughly 5× the vulnerability-level state reports) | `affected_entity.*`, `related_entities.<group>.{ids,names,count}` |
| `VULNERABILITY` | one pre-aggregated row per vulnerability | `affected_entities.*` (**plural**, aggregate counts/arrays), `related_entities.<group>.count` only |

**Always filter `event.level == "ENTITY"`** for per-entity queries and for the Stage-3 collapse —
otherwise vulnerability-level rows are double-counted. Vulnerability-level rows are a distinct
population: `vulnerability.first_seen` is populated on them (100 %) while `vulnerability.parent.first_seen` is null,
the reverse of ENTITY rows (see [Identity / metadata](#identity--metadata)); `event.id` is
`<vulnerability.id>_<epoch-ns>` there and null on ENTITY rows.

---

## Provider Taxonomy

| `event.provider` | `product.name` | `product.vendor` | Notes |
|---|---|---|---|
| `Dynatrace` | **null** | **null** | DT RVA **entity/vulnerability events** (`VULNERABILITY_STATE_REPORT_EVENT`, `…STATUS_CHANGE_EVENT`, `…TRACKING_LINK…`, legacy `…ASSESSMENT_CHANGE_EVENT`). These carry **no** `product.name` / `product.vendor` (they carry `event.provider_product == "Runtime Vulnerability Analytics"` instead). Excluded from cross-provider summaries (double-counting guard). |
| `OneAgent` | `Runtime Application Protection` (RAP) / `Runtime Vulnerability Analytics` (code-level) | `Dynatrace` | DT RAP — runtime attack detections via OneAgent (`DETECTION_FINDING`; all rows checked carry both `event.provider == "OneAgent"` and `product.name == "Runtime Application Protection"`). The same provider also emits the **code-level** `VULNERABILITY_FINDING` / `VULNERABILITY_SCAN` rows (`product.name == "Runtime Vulnerability Analytics"`, `product.feature == "Code-level Vulnerability Analytics"`). Legacy RAP rows with `product.name == "Application Security"` exist only in some tenants (ingested source, no `finding.action`), so the templates use the combined filter `(product.name == "Runtime Application Protection" OR event.provider == "OneAgent")`. |
| `Dynatrace Automated Detections` | `Automated Detections` | `Dynatrace` | DT detection rules engine (threat-detection-service) — both custom and built-in rules. Hardcoded provider; emits both `DETECTION_FINDING` and `DETECTION_EXECUTION_SUMMARY`. Ingested (`dt.openpipeline.source` is not `built-in-security-events`). **Not present in every tenant.** |
| **null** | `Security Posture Management` | `Dynatrace` | DT KSPM compliance findings + scan-completed events. **`event.provider` is null on some tenants** — scope with `product.name == "Security Posture Management"` (or `product.vendor == "Dynatrace"`), never `event.provider`. |
| `AutomationEngine` | `AutomationEngine` | `Dynatrace` | Custom workflow detections from the AutomationEngine product. **Not observed** in the data checked — documented upstream only. |
| `Dynatrace` **or null** (tenant-dependent) | `Runtime Vulnerability Analytics` | `Dynatrace` | DT RVA **library** `VULNERABILITY_FINDING` and non-code-level `VULNERABILITY_SCAN` (`product.feature == "Library Vulnerability Analytics"` on findings, null on scans). `event.provider` is `Dynatrace` on some tenants and null on others, so an `event.provider`-only filter silently misses them on the latter — use `product.vendor == "Dynatrace"`, the only portable scope. |
| **null** | `Runecast Analyzer` | null on findings; `Dynatrace` on `COMPLIANCE_SCAN_COMPLETED` | VMware / multi-cloud posture partner integration (CIS, NIST, DISA STIG, VMware SCG, DORA, ISO 27001, PCI DSS, GDPR, HIPAA, BSI). Emits the full KSPM-style `compliance.rule.*` / `compliance.result.*` schema. |
| _external cloud-security / SIEM / SOAR_ | (varies) | (non-`Dynatrace`) | Cloud posture/threat services, identity/sign-in, WAF/edge, SIEM detections — ingested via OpenPipeline |
| _external SCA / SAST / image scanners_ | (varies) | (non-`Dynatrace`) | Software-composition, code, and container-image scanners — may carry provider-specific namespaces (e.g. `<vendor>.*`) |
| _custom / OCSF ingest_ | (varies) | (varies) | Anything conforming to the SD `*_FINDING` schema via custom HTTP / OpenPipeline |
| `AlienVault OTX` | `AlienVault OTX` | `LevelBlue` | **Threat intelligence** (`event.type == "THREAT_REPORT"`) — OTX pulses + IOCs. Not a finding; see [threat-intelligence.md](threat-intelligence.md). |
| `CrowdStrike` | `Falcon Intelligence` | `CrowdStrike` | **Threat intelligence** (`event.type == "THREAT_REPORT"`) — Falcon Intelligence reports + IOCs. Not a finding; see [threat-intelligence.md](threat-intelligence.md). |

External rows are deliberately not enumerated — discover the active providers and scope to one
via [all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type).

**Routing form for "all Dynatrace-generated detections":**

```dql
fetch security.events, from:now()-2h
| filter event.type == "DETECTION_FINDING"
| filter product.vendor == "Dynatrace"
```

The `event.provider` distinction (`OneAgent` vs `Dynatrace Automated Detections`)
is informational metadata — only split when the user specifically asks for one.

---

## Common Fields (semantic dictionary required)

All cross-provider queries rely on these normalized fields:

| Field | Type | Notes |
|---|---|---|
| `event.id` | string | Unique event ID — required |
| `event.type` | string | See table above — required |
| `event.provider` | string | Integration name — required |
| `finding.id` | string | Provider-specific (UUID, ARN, hash) — required |
| `finding.type` | string | Sub-classification — required |
| `finding.title` | string | Human-readable description — required |
| `finding.time.created` | timestamp | When the finding was created — required. Native `timestamp` type on all providers (no `toTimestamp()` needed). `finding.created_time` does not exist. |
| `dt.security.risk.level` | string | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `NONE`, `NOT_AVAILABLE` — required |
| `dt.security.risk.score` | double | Numeric 0–10; present on `*_FINDING` events — **not** present on DT RVA state-report events (use `vulnerability.risk.score` there) |
| `object.id` | string | ID of affected object — required (or `object.name`) |
| `object.name` | string | Name of affected object — required (or `object.id`) |
| `object.type` | string | The affected object's type — **not a guaranteed Smartscape type, even on Dynatrace-emitted events** (SD types it as a free string). Observed: DT library `VULNERABILITY_FINDING` / non-code-level `VULNERABILITY_SCAN` → lowercase `process_group_instance`; DT RAP and code-level (CLV) findings/scans → `PROCESS`; KSPM → `KUBERNETES_CLUSTER`, `KUBERNETES_NODE`, `CLOUD_APPLICATION_INSTANCE` (pods), `CLOUD_APPLICATION_NAMESPACE` and lowercase `k8s…` codes for roles/bindings/service accounts (`K8S_POD` was not observed); Automated Detections → empty string `""`. **For external / third-party events** it is the vendor-reported value as-is — e.g. `AwsEc2Instance`, `AWS::EC2::Instance`, `AccessKey`, `CODE_ARTIFACT`, `CODE_REPOSITORY`, `HOST`, `CONTAINER_IMAGE`, Azure resource-type strings. Match the exact string for the family you query; for Smartscape typing use `dt.smartscape_source.type` (uppercase, e.g. `PROCESS`, `K8S_CLUSTER`) instead. |
| `product.name` | string | Product within the provider — e.g. `Runtime Application Protection`, `Runtime Vulnerability Analytics`, `Security Posture Management`, `Automated Detections` (DT). **Null on DT RVA entity/vulnerability events.** |
| `product.vendor` | string | `Dynatrace` or external vendor |

**Which common fields each family actually carries** (✓ = populated, ✗ = absent/null):

| Family | `event.id` | `finding.id/title/type/severity` | `dt.security.risk.*` | `object.*` | `product.*` |
|---|---|---|---|---|---|
| DT RVA entity events (state / status) | ✗ | ✗ | ✗ (use `vulnerability.risk.*`) | ✗ (use `affected_entity.*`) | ✗ |
| DT `VULNERABILITY_FINDING` / `VULNERABILITY_SCAN` | ✓ | findings ✓ (scans ✗) | findings ✓ (score 98.9 %) | ✓ | ✓ |
| DT KSPM `COMPLIANCE_FINDING` / `COMPLIANCE_SCAN_COMPLETED` | ✗ | `finding.id` ✓ (UUID); `title`/`type`/`severity` ✗ | ✗ (use `compliance.rule.severity.*`) | ✓ | ✓ |
| DT RAP / Automated Detections `DETECTION_FINDING` | ✓ | ✓ | ✓ | ✓ (`object.type` empty on Automated Detections) | ✓ |
| External findings (GuardDuty, Defender, Sentinel, scanners) | ✓ | ✓ | ✓ | ✓ | ✓ |

So "required" in the table above holds for `*_FINDING` events from detections, vulnerability scanners and
external tools — **not** for KSPM compliance findings or RVA entity events. Cross-provider summaries that need
`finding.title` / `dt.security.risk.level` must not expect KSPM rows.

---

## Entity Scoping Fields

When filtering findings by entity ID/name, use one (or all in an OR chain — see
[common-patterns.md § 5](common-patterns.md#5-wide-entity-scoping-or-chain)).

> **Entity-identifier namespaces split by event family.** Which fields carry entity refs depends on the event type — they are NOT interchangeable:
>
> | Event family | Entity namespaces present | Entity namespaces absent |
> |---|---|---|
> | `DETECTION_FINDING`, `COMPLIANCE_FINDING`, external `VULNERABILITY_FINDING`, `VULNERABILITY_SCAN`, `COMPLIANCE_SCAN` | `dt.smartscape*` (3rd-gen), `k8s.*` / cloud resource ids | `affected_entity.*`, `related_entities.*` (RVA-specific, null here) |
> | `VULNERABILITY_STATE_REPORT_EVENT`, `VULNERABILITY_STATUS_CHANGE_EVENT`, `VULNERABILITY_TRACKING_LINK_CHANGE_EVENT` (RVA) | `affected_entity.*` (classic ID + name + type, resolved in-event), `related_entities.{kubernetes_workloads,kubernetes_clusters,applications,services,hosts,databases}.{ids,names}` (blast-radius classic IDs + names; `.ids` type prefix ≠ group name — see `vulnerabilities-dynatrace.md` § One known entity) | `dt.smartscape*`, `dt.source_entity` (null on RVA events) |
>
> For raw-listing projection guidance per event family see [common-patterns.md § 17](common-patterns.md#17-entity-identifier-preservation-on-raw-listings).

### Smartscape (preferred for new queries)

The classic `dt.entity.*` fields are deprecated — do not use them; use the
`dt.smartscape.*` / `k8s.*` / cloud-resource fields below. `dt.smartscape.*` are 3rd-gen
ids (join `smartscapeNodes` on `id`); RVA `affected_entity.*` / `related_entities.*` carry
2nd-gen ids (join on `id_classic`).

| Field | Example |
|---|---|
| `dt.smartscape_source.id` | Smartscape node ID for the source entity |
| `dt.smartscape.process` / `.host` / `.container` / `.k8s_cluster` / `.k8s_node` / `.k8s_namespace` / `.k8s_pod` / `.k8s_deployment` | Per-type Smartscape node IDs (`PROCESS-…`, `HOST-…`). Enrichment-dependent: RAP carries all of them (100 %); KSPM carries `.k8s_cluster` (100 %), `.k8s_namespace` (66 %), `.k8s_node` (34 %), `.k8s_pod` (29 %) and **no** `.host` / `.process`; DT scans carry `.process` / `.host` (95 %) and — on some tenants — no `.host` for Kubernetes workloads (other tenants populate it), so do not use `.host` null-ness to detect K8s. Not in any SD security model except `dt.smartscape.aws_ec2_instance` on `COMPLIANCE_SCAN` — SD does not promise them. |
| `dt.smartscape_source.type` | Uppercase Smartscape type of `dt.smartscape_source.id` — `PROCESS` (RAP, DT scans), `K8S_CLUSTER` / `K8S_NAMESPACE` / `K8S_NODE` / `K8S_POD` / `K8S_DEPLOYMENT` / … (KSPM), cloud types on external. Absent on RVA entity events. |
| `dt.source_entity` / `dt.source_entity.type` | **Deprecated** (SD: use `dt.smartscape_source.id` / `.type`) legacy classic entity ID / lowercase type — still populated on RAP, KSPM and DT scan events, but do not use; use `dt.smartscape_source.id` / `dt.smartscape_source.type`, `dt.smartscape.*`, `object.*`, image digest, or host IP paths for new correlation queries. All `dt.entity.*` are likewise deprecated in SD (replacement: `dt.smartscape.<type>`). |

### Kubernetes

| Field | Example |
|---|---|
| `k8s.pod.uid` / `k8s.cluster.uid` | UUIDs |
| `k8s.cluster.name` / `k8s.namespace.name` / `k8s.node.name` / `k8s.pod.name` / `k8s.workload.name` | Names |

### Cloud

| Field | Example |
|---|---|
| `aws.resource.id` / `aws.resource.name` | AWS resource identifier (SD: unique immutable id — **not guaranteed to be an ARN**; `aws.arn` exists in SD but only on `COMPLIANCE_SCAN`) / friendly name |
| `azure.resource.id` / `azure.resource.name` | Azure |
| `gcp.resource.name` | GCP (there is **no** `gcp.resource.id`; SD attaches `gcp.resource.name` to no security model, so confirm it is populated for your provider) |

### Object-level (raw stream)

| Field | Notes |
|---|---|
| `object.id`, `object.name` | Direct match on the finding's object |
| `host.name` | Host name (string) |
| `host.ip` | IP address — array; use `expand` + `ip()` to normalize. SD lists it on `VULNERABILITY_FINDING` only (0 % on RAP) |

---

## Detection Fields (`DETECTION_FINDING`)

Detection findings are **one-shot events** — there's no per-(rule, entity) aggregation
pipeline like RVA's state-report stream or KSPM's scan-completed join. Each row is a
discrete detection. Different sources populate different sub-namespaces.

### Cross-provider core (all detections)

| Field | Notes |
|---|---|
| `finding.id`, `finding.title`, `finding.description`, `finding.type` | Cross-provider normalized |
| `finding.severity` | Vendor-supplied severity string (provider-native scale **and casing**: RAP / Automated Detections / GuardDuty `UPPERCASE`, Defender / Sentinel `Title case` — compare case-insensitively or use `dt.security.risk.level`). SD enum: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFORMATIONAL` (no `NONE`). |
| `finding.score` | Vendor-supplied score (type `long` or `double` depending on provider) |
| `finding.time.created` | When the detection was generated (`timestamp`). |
| `finding.remediation` | Free-text remediation guidance. **Not in SD**; runtime-emitted by Automated Detections only (≈36 % of findings), null on RAP. |
| `dt.security.risk.level` | Cross-provider normalized: `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `NONE` / `NOT_AVAILABLE`. Always prefer this over `finding.severity` for cross-provider comparisons. |
| `dt.security.risk.score` | Normalized 0–10 score; mapping `Critical → 10.0`, `High → 8.9`, `Medium → 6.9`, `Low → 3.9`, other → `0.0` is the documented rule, but providers can deviate (observed: GuardDuty `MEDIUM` → 5). Use `dt.security.risk.level` for banding. |
| `event.description` | Provider-supplied detection description (GuardDuty); null on RAP |
| `event.outcome` | Sparse — 0 % on RAP and the other providers checked; do not filter on it. **Prefer `finding.action` for RAP** (see below). |
| `dt.raw_data` | Original ingested JSON for external findings (100 % on GuardDuty, Defender, Sentinel, threat reports; **0 %** on DT-emitted rows and Runecast) — useful for fields not normalized to the SD. Parse with `parse … "JSON:raw"`. |

### DT Automated Detections (`event.provider == "Dynatrace Automated Detections"`)

Emitted by threat-detection-service when a user-defined or built-in rule fires. Not present in every tenant; field
names and fill rates below were verified on a tenant that has it.

| Field | Notes |
|---|---|
| `detection.id` | Rule UUID — stable across executions of the same rule |
| `detection.title` | Rule title (configurable). SD: the field is `detection.name` (experimental, internal) — **not emitted yet**; use `detection.title` |
| `detection.description` | Rule description |
| `detection.owner.id` | User ID of the rule owner (**not** `detection.owner_id`; SD agrees: `detection.owner.id`) |
| `threat.attack.technique.ids` | **Array** of MITRE ATT&CK technique IDs (T-prefixed, e.g. `["T1059", "T1078"]`). Primary pivot for heat maps. Empty `[]` if the rule isn't tagged — observed non-empty on only ≈12 % of findings (one rule). |
| `threat.attack.subtechnique.ids` | **Array** of sub-technique IDs (dotted, e.g. `["T1059.003", "T1078.004"]`). **Independent** from `technique.ids` — no positional alignment; parent technique is encoded in the ID itself (`T1059.003` → `T1059`). Not populated in the data checked, so the independence is SD-documented, not data-verified. |
| `threat.attack.tactic.ids` | **Array** of MITRE tactic IDs (TA-prefixed, e.g. `["TA0002"]`). Not populated on Automated Detections. |
| `threat.attack.technique.names` / `subtechnique.names` / `tactic.names` | Optional companion `.names` arrays — positional with `.ids` when populated (null on Automated Detections; populated by some external detections, e.g. Sentinel `tactic.names`). |
| `threat.attack.version` | ATT&CK framework version, e.g. `"15.1"`. Not populated on Automated Detections. |
| `execution.id` | Execution UUID — joins this finding to its `DETECTION_EXECUTION_SUMMARY` row. SD: `scan.id` (not emitted yet) |
| `execution.actor.id` | Actor that triggered the execution (scheduler / on-demand user). SD: `scan.actor.id` |
| `dt.alert_group` | Alert-group value on every Automated Detections finding (not in the SD security models) |
| `object.id` / `object.name` | Populated; `object.type` is the **empty string** `""`, not null — `filter isNotNull(object.type)` does not exclude these rows |

> **Execution summary (`DETECTION_EXECUTION_SUMMARY`) fields** — runtime names (SD target names in parentheses; SD
> lowercases the status values and moves everything under `scan.*`, but the runtime does not emit those yet):
>
> | Field | Notes |
> |---|---|
> | `execution.id`, `detection.id`, `detection.title`, `detection.owner.id`, `execution.actor.id` | Identity of the run and its rule |
> | `execution.result.status` (SD `scan.result.status`) | Only `SUCCESS` observed; `SUCCESS_W_WARNINGS` / `FAILURE` are documented but **not observed** |
> | `execution.stats.events_written` / `.scanned_records` / `.scanned_bytes` (SD `scan.stats.*`) | Run statistics, 100 % populated. The camelCase names `eventsWritten`, `scannedRecords`, `scannedBytes` do **not** exist as fields |
> | `execution.query.timeframe.start` / `.end` (SD `scan.query.timeframe.*`) | Analysis window (84 % populated); also `execution.query.dql`, `execution.query.id` |
> | `execution.time.scheduled` / `.started` / `.completed`, `execution.retries.left` / `.max`, `execution.result.notifications` | Timing / retry detail |
>
> Most executions emit **no** finding: in a 24 h sample about a third of executions had both a summary and findings, two thirds only a summary,
> and none had findings without a summary.

> **`finding.severity` enum for Automated Detections.** Observed values are `CRITICAL` and `MEDIUM` only; the SD enum is `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFORMATIONAL`
> — **there is no `NONE` in SD** (an earlier version of this file listed `NONE` for informational-only rules; not
> observed). `dt.security.risk.level` has its own closed enum (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `NONE`,
> `NOT_AVAILABLE`); `NONE` / `NOT_AVAILABLE` were not observed on detections.

> **No mute / dismiss / suppress fields.** Detections have no equivalent of
> `vulnerability.mute.*`. Suppression is handled UI-side (Threats & Exploits
> app filters) or via Application Protection rules (at OneAgent ingest time
> for RAP) — neither writes to `security.events`.

### Runtime Application Protection (`product.name == "Runtime Application Protection"`)

Emitted by OneAgent when an attack pattern is detected (SQL injection, command
injection, JNDI injection, SSRF, path traversal). Java 8+, .NET, and Go (Go
limited to SQL/command injection; JNDI/SSRF are Java-only).

| Field | Notes |
|---|---|
| `finding.type` | Original vendor-reported attack type — **free-form `string`, not a normalized enum** (SD `finding.yaml`: "Original type of the finding reported by the vendor"). Values vary by vendor and version; observed RAP values (7 d sample): `SSRF`, `JNDI injection`, `SQL injection`, `CMD injection`. Filter with `contains(finding.type, "…", caseSensitive:false)` rather than exact match; discover live values with the summarize-by-`finding.type` query in `detections.md`. The legacy `attack.type` / `attack.vector` names from older RAP-namespace docs are not in the Semantic Dictionary. |
| `finding.action` | What OneAgent did about the attack — `Audited` (monitor mode — detected only) and `Blocked` observed; `Allowlisted` (explicit allowlist rule) is documented but **not observed**. These capitalized values are the legacy RAP vocabulary (SD's deprecated `dt.security.rap.action`: `BLOCKED` / `ALLOWLISTED` / `AUDITED`) emitted as-is; SD's own `finding.action` enum is lowercase `allowed` / `denied` / `observed` / `modified` (internal) — don't filter on the SD values. The "blocked vs monitored" breakdown query keys off this field. |
| `finding.id` | Short ID of the form `A-1YIXMY9H` — **not a UUID** |
| `actor.ips` | Array of attacker source IPs (`ipAddress[]`, **Stable**; 100 % on RAP). One row may carry multiple IPs (IPv4 + IPv6, proxy chains). For top-IP queries, `expand actor.ips` then cast with `ip(actor.ips)` so downstream IP comparisons / CIDR checks type-check correctly. Enrichable via the Security Enrichment app (AbuseIPDB / VirusTotal / custom). |
| `actor.geo.country.name` | Country name (Experimental); also `actor.geo.city.name`, `actor.geo.location.lat`/`lon`. **0 % on RAP**; populated on some external detections (GuardDuty ≈56 %). `actor.geo.continent.name` not observed. |
| `dt.security.rap.target.{id,type,name}` | What was attacked — for SQL injection this is the database, for service-targeted attacks it's the service. `type` (lowercase, e.g. `host`, `database`) and `name` are 100 %, `id` only ≈19 %. `object.*` carries the entity where the exploit happened (`object.type == "PROCESS"`); `dt.security.rap.target.*` is the underlying target. |
| `entry_point.url.path` / `.payload` / `.function.name` / `.user_controlled_inputs` | The HTTP path, payload and function the attack entered through — 100 % on RAP. (`url.path`, `sink.code.*`, `code.*` are 0 % on RAP.) |
| `dt.smartscape.process` / `.host` / `.container` / `.k8s_*` | Smartscape entity IDs of the attacked process / host / container / Kubernetes entities (100 % on RAP) |

> RAP **attack reconstruction** (full payload, sink code, code location) is product-emitted outside the SD stable
> namespace (`entry_point.*` is in an SD-internal group; SD lists `sink.code.*` and `code.*` but RAP does not emit
> them). The Threats & Exploits app is the supported surface for it.

> **RAP control mode is configured at OneAgent**, not in queries. Modes are
> `Off` (not detected — no event), `Monitor` (detected only — `finding.action == "Audited"`),
> `Block` (detected and stopped — `finding.action == "Blocked"`). Per-PG / per-vulnerability-type
> custom rules can override the global mode.

### Event provenance: source, provider (filter by provider, not bucket)

| Attribute | Built-in security events (Dynatrace RVA, RAP, SPM) | Ingested events (external products **and Automated Detections**) |
|---|---|---|
| `dt.openpipeline.source` | `built-in-security-events` | `/platform/ingest/v1/security.events` (or a custom source, e.g. `data_extraction`) |

> **Bucket (informational).** Bucket names and retention differ per tenant (for example
> `default_security` and `default_securityevents`), and users can re-route events to any
> custom bucket (routing rules, retention overrides), so the bucket name is not a reliable
> scope. **Do NOT add `dt.system.bucket` filters to default queries** — a wrong bucket
> name returns zero rows with no error (a false "nothing found"). If the user explicitly
> names a bucket to search, filter on exactly that name.

Scope to Dynatrace-generated data with provider attributes instead:

| Need | Filter | Note |
|---|---|---|
| RVA (`VULNERABILITY_STATE_REPORT_EVENT`, `…STATUS_CHANGE_EVENT`, `…TRACKING_LINK_CHANGE_EVENT`, `event.level == "ENTITY"`) | `event.provider == "Dynatrace"` | All RVA events (entity **and** vulnerability level) carry it (checked on several tenants); they carry no `product.vendor`. Add `event.level == "ENTITY"` for per-entity grain |
| Other Dynatrace families (`COMPLIANCE_FINDING`, library `VULNERABILITY_FINDING`/`VULNERABILITY_SCAN`) | `product.vendor == "Dynatrace"` | `event.provider` is **null** on KSPM everywhere checked; on library vulnerability findings/scans it is null on some tenants and `Dynatrace` on others. Code-level findings/scans carry `event.provider == "OneAgent"`. For `COMPLIANCE_SCAN_COMPLETED` add `product.name == "Security Posture Management"` — Runecast also emits it with `product.vendor == "Dynatrace"` |
| Automated Detections (`DETECTION_FINDING`) | `event.provider == "Dynatrace Automated Detections"` | **Not** a built-in security event: it is ingested, so `dt.openpipeline.source == "built-in-security-events"` excludes it by design |
| All built-in security events (RVA, RAP, SPM) | `dt.openpipeline.source == "built-in-security-events"` | Optional broad scope; also includes `event.provider == "OneAgent"` (RAP) events. Never use it to reach detections |

`dt.openpipeline.source` is a valid broad scope for the built-in families (RVA, RAP, SPM), but
prefer the specific provider or vendor filter for the finding family you are querying. (`product.provider` is not a field;
the vendor attribute is `product.vendor`.)

---

## Vulnerability Fields (RVA — raw + post-aggregation)

The raw `VULNERABILITY_STATE_REPORT_EVENT` carries one row per
`(vulnerability, affected_entity)` pair. The canonical RVA Stage-3 `fieldsAdd`
(see [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md)) collapses these per-entity rows
into vulnerability-level verdicts. Some fields below exist only in the raw
stream, some only post-aggregation, some in both. All tables describe **`event.level == "ENTITY"`** rows unless stated
(see [RVA event levels](#rva-event-levels-eventlevel)); RVA entity events carry no `event.id`, `finding.*`, `object.*`,
`product.*`, `dt.security.risk.*`, `dt.smartscape*` or `k8s.*` fields.

### Identity / metadata

| Field | Values / notes |
|---|---|
| `vulnerability.display_id` | Human-readable, e.g. `S-12345` |
| `vulnerability.id` | Internal UUID |
| `vulnerability.external_id` | **Provider-emitted reference identifier** (e.g. NVD CVE ID, MITRE ID); ≈99.8 % populated. Not a user-attached tracking ticket — for that, see `vulnerability.tracking_link.*` further down. |
| `vulnerability.external_url` | **Provider-emitted reference URL** (NVD page, vendor advisory, etc.) — present but the **empty string `""` on ≈66 % of rows**. **NOT the user-attached remediation/Jira link** — that field is `vulnerability.tracking_link.url`. Filtering `vulnerability.external_url != ""` to find "vulnerabilities with a tracking link" is a common mistake; it returns vulnerabilities that have any vendor reference URL (≈1/3 of rows), not the ones with a link. |
| `vulnerability.title` | Short description |
| `vulnerability.description` | Long description |
| `vulnerability.type` | Classification (e.g. CWE family) |
| `vulnerability.technology` | Target tech — **uppercase enum values** `JAVA`, `DOTNET`, `GO`, `PHP`, `NODE_JS` (SD) plus `PYTHON`, `KUBERNETES` observed; not display names like `Java` / `.NET` / `Node.js` |
| `vulnerability.stack` | `CODE` (CLV — OneAgent IAST/Attack), `CODE_LIBRARY` (matched on software components), `SOFTWARE` (matched on runtime / OS packages), `CONTAINER_ORCHESTRATION` (Kubernetes-level). See `TechnologyStack` enum. |
| `vulnerability.code_location.name` | CLV only — source file + line of vulnerable code |
| `vulnerability.is_fix_available` | Boolean — `true` if a fix exists upstream |
| `vulnerability.remediation.description` | Free-text guidance |
| `vulnerability.references.cve` | CVE IDs — **always an array** (`string[]`, SD and runtime agree); can be empty `[]` (CLV) or `[null]` (some external scanners). ≈99 % non-empty on RVA entity rows. See [§ SD changes in flight](#sd-changes-in-flight-not-emitted-yet) — slated for rename to `vulnerability.cve_ids`. |
| `vulnerability.references.cwe` | CWE ID(s) |
| `vulnerability.references.owasp` | OWASP category reference(s) |
| `vulnerability.first_seen` | First-detection timestamp. **Null on `event.level == "ENTITY"` rows; 100 % populated on `event.level == "VULNERABILITY"` rows.** On ENTITY rows the only populated first-detection timestamp is `vulnerability.parent.first_seen` (100 %; `vulnerability.parent.*` is a stable-in-SD but skill-avoided namespace — see [mistakes-and-troubleshooting.md](mistakes-and-troubleshooting.md)). |
| `vulnerability.davis_assessment.level` | DSS-derived level per entity / vulnerability (`LOW`…`NONE`) — populated; SD stable |
| `vulnerability.risk.scale` / `vulnerability.url` | Populated on RVA events (SD stable): scoring scale label / link to the vulnerability in Dynatrace |

### Scoring

| Field | Values / notes |
|---|---|
| `vulnerability.cvss.base_score` | CVSS base score (0–10), `vulnerability.cvss.version` and `vulnerability.cvss.vector` accompany. ≈89.5 % populated on RVA entity rows. **External scanners are type-inconsistent:** `double`, `long`, or `string` (Qualys) — wrap with `toDouble()` for cross-provider math. |
| `vulnerability.cvss.version` | `2.0`, `3.0`, `3.1`, `4.0` (or null) — string-typed |
| `vulnerability.cvss.vector` | Static CVSS vector string |
| `vulnerability.risk.score` | Dynatrace Security Score (DSS) — context-aware, **never exceeds CVSS base**. Per-entity in raw events; collapsed to vulnerability-level via `takeMax` (muted entities contribute 0). **Sentinel `-1`:** ≈10 % of ENTITY rows (`SOFTWARE` / `CODE_LIBRARY` stacks with `risk.level == "NONE"` and null CVSS) carry `-1` (same for `vulnerability.davis_assessment.score`), meaning "not scored"; exclude `< 0` (or rely on `risk.level`) before averaging / `min()`. |
| `vulnerability.risk.level` | Derived in Stage 3: ≥9 CRITICAL / ≥7 HIGH / ≥4 MEDIUM / ≥0.1 LOW / else NONE |
| `vulnerability.davis_assessment.score` | Per-entity DSS (raw stream only) |
| `vulnerability.davis_assessment.vector` | Modified CVSS vector if DSS adjusted CVSS |

> **DSS for CLV is always 10.0 (Critical).** Code-level vulnerabilities skip the
> DSS modifiers — entry points and data-flow proof of exploitability are
> sufficient to score Critical.

### Dynatrace runtime assessment statuses (raw stream)

Per-entity statuses; collapsed to vulnerability-level by Stage-3 `fieldsAdd`
into the shortened names below. **Precedence** (most-severe first) drives the
collapse — if any entity has the most-severe status, the vulnerability inherits
it.

| Raw field (per-entity) | Stage-3 short name | Values (precedence top → bottom) |
|---|---|---|
| `vulnerability.davis_assessment.exposure_status` | `vulnerability.exposure.status` | `PUBLIC_NETWORK` > `NOT_AVAILABLE` > `NOT_DETECTED`. Raw values include `ADJACENT_NETWORK` (observed on ENTITY rows only), but it's intentionally **not** treated as public exposure — falls through to `NOT_DETECTED` in the derived field. Query the raw field directly for adjacent-network analysis. |
| `vulnerability.davis_assessment.exploit_status` | `vulnerability.exploit.status` | `AVAILABLE` > `NOT_AVAILABLE` |
| `vulnerability.davis_assessment.vulnerable_function_status` | `vulnerability.vulnerable_function.status` | `IN_USE` > `NOT_AVAILABLE` > `NOT_IN_USE` |
| `vulnerability.davis_assessment.data_assets_status` | `vulnerability.data_assets.status` | `REACHABLE` > `NOT_AVAILABLE` > `NOT_DETECTED` |
| `vulnerability.davis_assessment.assessment_mode` | (kept long-form in projections) | `FULL` (all entities full-stack) > `REDUCED` (some entity in Foundation/Infra-Only) > `NOT_AVAILABLE`. Observed: `FULL`, `NOT_AVAILABLE`; `REDUCED` not observed. |
| `vulnerability.davis_assessment.assessment_mode_reasons` | — | array; SD values `LIMITED_BY_CONFIGURATION`, `LIMITED_AGENT_SUPPORT` (underscore, not dot) — **always empty `[]` in every sample checked**, so value semantics are unverified |

> **Why `NOT_AVAILABLE` outranks `NOT_DETECTED` / `NOT_IN_USE`.** Missing
> telemetry is treated as "could be exploitable" — surfaces gaps for
> investigation rather than hiding them under a clean-looking `NOT_DETECTED`.

> **CLV scope.** `vulnerable_function.status` and `exposure.status` are
> populated only for `CODE_LIBRARY` / `SOFTWARE` (third-party). For CLV
> (`CODE`), the entry-point and data-flow proof carries the assessment.

### Lifecycle / workflow (per-entity raw, vulnerability-level after Stage 3)

| Raw field (per-entity) | Stage-3 derivation | Notes |
|---|---|---|
| `vulnerability.resolution.status` | derived: `if(in("OPEN", resolutionStatuses), "OPEN", else: "RESOLVED")` | Auto-resolved when no PG reports the vulnerable library for >2 h (third-party) or process restarts and OneAgent finds no exploitable data flow (CLV) |
| `vulnerability.resolution.change_date` | `takeMax` | Last status transition timestamp (nanoseconds). Latest entity transition, not first-open (use `takeMin` over OPEN rows for open-since). |
| `vulnerability.mute.status` | derived: `if(in("NOT_MUTED", muteStatuses), "NOT_MUTED", else: "MUTED")` | Per-entity mute; vulnerability is fully muted only if every entity is muted |
| `vulnerability.mute.reason` | (raw, per-entity) | SD enum: `FALSE_POSITIVE`, `IGNORE`, `AFFECTED` (=> NOT_MUTED), `CONFIGURATION_NOT_AFFECTED`, `OTHER`. Observed: `OTHER`, `IGNORE`, `AFFECTED`; the other two appear only under the deprecated `vulnerability.parent.mute.reason`. Sparse (<0.2 % of rows). |
| `vulnerability.mute.user` | (raw, per-entity) | User who set the mute |
| `vulnerability.mute.comment` | (raw, per-entity) | Free-text reason |
| `vulnerability.mute.change_date` | (raw, per-entity) | Mute timestamp |
| `vulnerability.tracking_link.url` | (raw, per-entity; documented as emitted by `VULNERABILITY_TRACKING_LINK_CHANGE_EVENT`) | Jira / wiki / ticket URL. Practically absent (a handful of state-report / status-change rows per day) and the dedicated event type has not been observed. |
| `vulnerability.tracking_link.text` | (raw, per-entity) | Display text for the link |

> **Mute states observed in the UI** include `Muted (Open)` (vulnerability
> remains open but every entity is silenced) and `Muted (Resolved)` (a muted
> vulnerability auto-resolved). These compose from the OPEN/RESOLVED + MUTED/NOT_MUTED
> per-entity arrays — they're **not separate enum values** in `security.events`.

### Affected / related entity fields

| Field | Values / notes |
|---|---|
| `affected_entity.id` | Classic (2nd-gen) entity ID — join `smartscapeNodes` on `id_classic` |
| `affected_entity.name` | Display name |
| `affected_entity.type` | `PROCESS_GROUP` (98.6 %), `KUBERNETES_NODE` (1.1 %), `HOST` (0.3 %) observed; `PROCESS_GROUP_INSTANCE` not observed. See `MonitoredEntityType`. |
| `affected_entity.affected_processes.names` / `.ids` | Process instances inside the PG that carry the vulnerability (ids non-empty on ≈98.6 % of rows). **There is no `affected_entity.affected_processes.count`** (not in SD, null at runtime); the count lives on vulnerability-level rows as `affected_entities.affected_processes.count`, or compute `arraySize(…ids)` |
| `affected_entity.vulnerable_component.id` | Internal component ID |
| `affected_entity.vulnerable_component.name` | Library/component name (e.g. `log4j-core 2.14.1`) |
| `affected_entity.vulnerable_component.short_name` | Short label |
| `affected_entity.vulnerable_component.package_name` | Package name (e.g. `org.apache.logging.log4j:log4j-core`) |
| `affected_entity.vulnerable_functions` | Array of FQCN method names actually executed (e.g. `org.apache.http.client.utils.URIUtils#decode`). **Requires** the OneAgent `Java vulnerable function reporting` (or equivalent) feature. |
| `affected_entity.vulnerable_functions_not_in_use` | FQCN methods present but not executed (note: underscore, not dot — internal/experimental in SD) |
| `affected_entity.vulnerable_functions_not_available` | FQCN methods that could not be evaluated (note: underscore, not dot — internal/experimental in SD) |
| `affected_entity.management_zones.ids` / `.names` | Management zones of the affected entity (SD stable; ≈86 % populated) |
| `affected_entity.reachable_data_assets.ids` | Database IDs reachable from this entity (the Davis "reachable data assets" dimension — distinct from the blast-radius `related_entities.databases.*` group) |
| `related_entities.{kubernetes_workloads,kubernetes_clusters,applications,services,hosts,databases}.{ids,names}` | Indirect blast-radius entities (arrays of classic IDs + display names). `.ids` carry classic entity IDs; the type prefix may differ from the group name (e.g. `kubernetes_workloads.ids` → `CLOUD_APPLICATION-…`; `databases.ids` → `SERVICE-…`; `applications.ids` → `APPLICATION-…`, `CUSTOM_APPLICATION-…` or `MOBILE_APPLICATION-…`). `.names` are positionally paired with `.ids`. |

> **Blast-radius presence (ENTITY rows):** `.ids` non-empty — `hosts` 98.6 %, `services` 87 %, `databases` 59 %, `kubernetes_clusters` 40 %, `kubernetes_workloads` 39 %, `applications` 39 %. Every group also carries `related_entities.<group>.count` (SD stable) — prefer it for "how many" questions.

> **PG-only collateral.** `affected_processes.*` fields are non-empty **only**
> when `affected_entity.type == "PROCESS_GROUP"`. HOST and KUBERNETES_NODE
> entities don't carry them.

> **Runtime-assessment status field naming.** Raw events carry the long names
> `vulnerability.davis_assessment.vulnerable_function_status`, etc. Stage-3
> `fieldsAdd` collapses them to the shortened forms — those are the names
> used in filters, projections, and downstream queries.

### Change-event fields (`…STATUS_CHANGE_EVENT`, vulnerability-level rows)

Populated on status-change events and verified against both SD (stable) and runtime data; none were documented previously.

| Field | Notes |
|---|---|
| `event.status_transition` | `CLOSE`, `REOPEN`, `NEW_OPEN` — the transition this event records (SD experimental) |
| `event.status` | `OPEN`, `MUTED`, `RESOLVED` — resulting state |
| `event.change_list` | Names the attributes that changed; each name matches a `vulnerability.previous.*` field |
| `event.trigger.type` / `event.trigger.user` | What caused the change (and the user, when manual) |
| `vulnerability.previous.*` | Prior values of the changed attributes (`resolution.status`, `risk.*`, `mute.*`, `davis_assessment.*`, `cvss.*`, `tracking_link.*`); use for "what changed" without self-joining. `…ASSESSMENT_CHANGE_EVENT` carries `vulnerability.previous.davis_assessment.*` |

---

## Vulnerability Fields (external + DT-emitted `VULNERABILITY_FINDING`)

`VULNERABILITY_FINDING` events come from two sources:

- **External SCA / SAST / image scanners** ingested via OpenPipeline.
- **vulnerability-scan-service (Dynatrace)** — emits one `VULNERABILITY_FINDING`
  per matched vulnerability inside a scan (`event.provider` null, `product.name == "Runtime Vulnerability Analytics"`;
  code-level findings carry `event.provider == "OneAgent"`), **plus** one `VULNERABILITY_SCAN`
  per scan request. These are the "raw" findings that feed RVA's state-report
  aggregation; normally you query the state-report stream instead. To exclude
  Dynatrace-emitted findings: `filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"`.

External `VULNERABILITY_FINDING` events do NOT carry the RVA-derived fields.
They use the cross-provider normalized fields documented in [§ Common Fields](#common-fields-semantic-dictionary-required).

| Field | Notes |
|---|---|
| `vulnerability.references.cve` | CVE ID (also on RVA) |
| `vulnerability.id` | Provider's vulnerability identifier. `vulnerability.display_id`, `.external_id`, `.stack`, `.technology`, `vulnerability.davis_assessment.*`, `vulnerability.resolution.*`, `vulnerability.mute.*` are **null** on Dynatrace library `VULNERABILITY_FINDING` rows (they exist on RVA entity events) |
| `software_component.name` | **Null on Dynatrace library findings** — use `component.name` / `component.version` (100 % there) or the PURL |
| `software_component.purl` | Package URL (PURL) — canonical identifier; 100 % on DT library findings, on Sonatype among external scanners |
| `software_component.type` | **`library`** on Dynatrace findings (the only value observed). The package ecosystem (`MAVEN`, `NPM`, `PYPI`, …) is not here — it lives in `software_component.ecosystem` (external only: Sonatype, Dependabot). `RPM` / `DEB` / OS-package components were not observed (no `Operating System Vulnerability Analytics` rows). |
| `component.name` / `component.version` | Alternate component fields (used by some external scanners) |
| `container_image.digest` / `.registry` / `.repository` / `.tags` | Container image dimensions — populated only by image scanners (Amazon ECR, Defender); `container_image.id` is 0 % everywhere |
| `artifact.repository` / `artifact.path` | Artifact repository / path (alternative to `container_image.repository`; coalesce them — see [common-patterns.md § 12](common-patterns.md#12-repository--artifact-coalescing)). `artifact.repository` on Snyk, Sonatype, SonarQube, GitHub; `artifact.path` on Snyk, SonarQube, GitHub (not Sonatype). `software_component.path` is SD-defined (#2081) but **0 % emitted** so far |

> **Container-image dedup precedence.** For "distinct images" counts, key dedup on the most
> specific identifier present: `container_image.digest` (immutable) >
> `container_image.registry` + `container_image.repository`. Scanners vary in which they populate.

> **Severity normalization.** When external findings are ingested, severities
> are mapped to the normalized risk score: `Critical → 10.0`, `High → 8.9`,
> `Medium → 6.9`, `Low → 3.9`, `Other / unknown → 0.0`. Providers can deviate when they
> supply their own score (observed: Sonatype `critical` → `HIGH` / 8.7). External `finding.severity` uses mixed vendor
> scales (`medium`, `MINOR`, `severe`, `Unknown`, …). Use
> `dt.security.risk.level` rather than provider-specific severity fields for
> cross-provider comparisons. `dt.security.risk.score` / `finding.score` are `double` or `long` depending on the provider.

> **`finding.id` composition.** `finding.id` is a deterministic hash of
> `object.id` + `vulnerability.id` + `component.name` + `component.version` +
> `product.name` + `product.vendor`. `dedup finding.id` is the canonical grain for
> Dynatrace-generated findings — it collapses the same finding re-emitted each scan
> cycle (~15 min) to a single latest row (measured ≈7× re-emission over 30 min; `finding.id` is a 36-char UUID on 100 % of them).

> **DT-generated `VULNERABILITY_FINDING` entity/scope fields.** DT-generated findings
> carry `dt.security.risk.level` / `dt.security.risk.score`, `software_component.purl`,
> `finding.time.created`, and `dt.smartscape.process` with `dt.smartscape_source.type`
> — scope by entity via Smartscape. They do **not** carry the embedded
> `affected_entity.*` / `related_entities.*` arrays that RVA state reports do. Library findings have
> `object.type == "process_group_instance"`, `vulnerability.risk.level` equal to `finding.severity` (uppercase) and
> `vulnerability.remediation.status`; code-level (CLV) findings carry `vulnerability.type`, `vulnerability.references.cwe`,
> `sink.code.*`, `code.*` and `entry_points[]` but **no** software component, CVE or CVSS.
>
> **Name collision:** SD also defines `vulnerability.exploit.status` on `VULNERABILITY_FINDING` (external scanners,
> e.g. exploit availability). The RVA Stage-3 field of the same name is a *derived* value from
> `vulnerability.davis_assessment.exploit_status` — never mix the two.

---

## Compliance Fields (SPM)

Dynatrace Security Posture Management (SPM / XSPM) has three flavors:

| Flavor | What | Source | `product.name` | `event.provider` |
|---|---|---|---|---|
| **KSPM** | Kubernetes — CIS, DORA, NIST, DISA STIG, Dynatrace Security Essentials | DT-native (security-analyzer-service) | `Security Posture Management` | **null** (`product.vendor == "Dynatrace"`) |
| **CSPM** | Cloud posture — AWS / Azure / GCP foundations, plus broad standards (PCI DSS, ISO 27001, HIPAA, GDPR, …) | external/partner integration | (varies) | (varies) |
| **VSPM** | VMware posture — DISA STIG, NIST | external/partner integration (e.g. `Runecast Analyzer`, which also covers AWS security groups and emits the full KSPM-style schema) | (varies) | null (Runecast) |

**KSPM is the only DT-native flavor** — scope it with `product.name == "Security Posture Management"` (`product.vendor == "Dynatrace"` is enough for `COMPLIANCE_FINDING`, but also matches Runecast's `COMPLIANCE_SCAN_COMPLETED` rows); **`event.provider` is null** on every KSPM row, so an `event.provider == "Dynatrace"` filter returns nothing. KSPM `COMPLIANCE_FINDING` rows carry **no** `event.id`, `finding.title` / `type` / `severity` / `description` and no `dt.security.risk.*` — rule identity and severity are `compliance.rule.*`. CSPM/VSPM and other external compliance providers mostly populate the cross-provider `finding.*` namespace and do not populate `compliance.rule.*` consistently (Runecast is the exception) — see § Compliance Fields (external).

### KSPM event types

| Event type | Granularity | Use |
|---|---|---|
| `COMPLIANCE_FINDING` | One row per `(rule, object)` pair | Per-rule findings, evidence drill, status, severity. NOT_RELEVANT rows are emitted; filter them out. |
| `COMPLIANCE_SCAN_COMPLETED` | One row per scan run (per cluster) | Scan-level summary; carries pre-computed pass-rate JSON via `scan.result.summary_json`. Used as inner-join target on `scan.id` to dedup findings to the latest scan. |

> **No `COMPLIANCE_SCAN_STARTED`.** The lifecycle is implicit — a scan begins
> when a configuration dataset arrives, finishes when `COMPLIANCE_SCAN_COMPLETED`
> is emitted. There is no per-scan progress event.

### KSPM rule + standard fields

| Field | Values / notes |
|---|---|
| `compliance.rule.id` | `<STANDARD>-<NUMBER>` — e.g. `CIS-83637`, `STIG-V-242400`, `DORA-9`, `NIST-AU-2`, `DTSE-83208` (Security Essentials). Proposed to move to `rule.id` / `rule.name` (SD branch, **0 % emitted**) — keep querying `compliance.rule.*` — see [§ SD changes in flight](#sd-changes-in-flight-not-emitted-yet). |
| `compliance.rule.title` | Human-readable rule name |
| `compliance.rule.severity.level` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` — **exactly four values observed** (SD enum is open for custom values). KSPM does not emit `NONE` / `NOT_AVAILABLE`. |
| `compliance.rule.severity.score` | Numeric severity (0–10): `CRITICAL=10`, `HIGH=7`, `MEDIUM=4`, `LOW=1` (CCSS-based since 2026-03-10) |
| `compliance.rule.metadata_json` | ❌ **Do not use.** Field exists in the data (standard-specific JSON blob) but the skill must **never** query or parse it. Use `compliance.rule.id` / `compliance.rule.title` for rule identity instead. |
| `compliance.standard.short_name` | KSPM-native: `CIS`, `DORA`, `NIST`, `DISA STIG`, `Security Essentials`. **Note the full `"DISA STIG"` label — `short_name == "STIG"` matches nothing** (but `standardCode == "STIG"` **is** the code inside `scan.result.summary_json`, and the Security Essentials code there is `DTSE`). Prefer `contains(compliance.standard.short_name, "stig", caseSensitive:false)` for filtering — it tolerates version suffixes and the DISA prefix. PCI / ISO / HIPAA / GDPR appear only via CSPM/VSPM or external integrations (Runecast: `CIS`, `NIST`, `DISA STIG`, `VMware SCG`, `DORA`, `ISO 27001`, `PCI DSS`, `BSIC5`, `GDPR`, `HIPAA`, `BSI IT-Grundschutz`). |
| `compliance.standard.name` | Versioned full name — e.g. `"CIS Kubernetes - v2.0.1"`, `"STIG Kubernetes - Ver 2, Rel 6"`, `"Dynatrace Security Essentials for Kubernetes"` (exact wording varies by release; null on Runecast) |
| `compliance.standard.url` | Reference URL for the standard |

### KSPM result + evidence fields

| Field | Values / notes |
|---|---|
| `compliance.result.status.level` | `FAILED`, `MANUAL`, `PASSED`, `NOT_RELEVANT` — **exactly four**. No ERROR/UNKNOWN. |
| `compliance.result.status.score` | Numeric: `FAILED=10.0`, `MANUAL=7.0`, `PASSED=4.0`, `NOT_RELEVANT=1.0` |
| `compliance.result.description` | Optional status-detail text (nullable) |
| `compliance.result.count.passed` / `.failed` / `.manual` | **Post-aggregation only** — counters derived in the per-rule summarize (Step 2). Not on raw events. |
| `compliance.result.object.type` | Lowercase analysis-object code: `k8scluster`, `k8snode`, `k8spod`, `k8sdeployment`, `k8sstatefulset`, `k8sreplicaset`, `k8sdaemonset`, `k8sjob`, `k8scronjob`, `k8snamespace`, `k8sclusterrole`, `k8srole`, `k8sclusterrolebinding`, `k8srolebinding`, `k8sserviceaccount` (`k8sreplicationcontroller` is documented but was not observed). **Different field from the cross-provider `object.type`**, which carries the Dynatrace-side type (`KUBERNETES_CLUSTER`, `CLOUD_APPLICATION_INSTANCE`, … — see [Common Fields](#common-fields-semantic-dictionary-required)). |
| `compliance.result.object.name` | Resource name (pod / deployment / cluster name). SD marks it **deprecated** (no replacement named) but it is still 100 % populated; the cross-provider `object.name` is the forward-safe choice |
| `compliance.result.object.evidence_json` | JSON array of discovered configuration values — see schema below |

### `compliance.result.object.evidence_json` schema

```json
[
  {"type": "AUTOMATIC", "description": "Property '--enable-admission-plugins' value", "value": "restricted"},
  {"type": "MANUAL",    "description": "Question about external control",            "value": "Unknown"}
]
```

- `type`: `AUTOMATIC` (analyzer evaluated the property) or `MANUAL` (requires
  human input — value is typically `"Unknown"` when MANUAL is emitted).
- Long values (>3000 chars) are truncated by the analyzer to fit Grail record limits.
- Parse via `parse compliance.result.object.evidence_json, "JSON_ARRAY:findings"` then expand for per-property drilldown.

### `COMPLIANCE_SCAN_COMPLETED` fields (KSPM; Runecast carries the same core)

| Field | Notes |
|---|---|
| `scan.id` | UUID — joins the scan-completed row to all `COMPLIANCE_FINDING` rows it produced |
| `scan.time.completed` | `timestamp` of scan completion (the underscore spelling `scan.time_completed` does not exist) |
| `scan.result.summary_json` | JSON with pre-computed pass percentages — schema below |
| `object.id` / `object.name` / `object.type` | Cluster identifier (`KUBERNETES_CLUSTER` for KSPM; Runecast carries its own AWS / vCenter object) |
| `dt.smartscape.k8s_cluster`, `k8s.cluster.name`, `k8s.cluster.uid` | Cluster identifiers (KSPM) |
| `event.id`, `event.provider` | **Null** — there is no `event.id` on these rows |

### `scan.result.summary_json` schema

```json
{
  "standardResultSummaries": [
    {"standardCode": "CIS", "compliancePercentage": 85,
     "ruleCountsByStatusBySeverity": {
       "FAILED":       {"CRITICAL": 1, "HIGH": 4, "MEDIUM": 9, "LOW": 2},
       "MANUAL":       {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 3, "LOW": 0},
       "PASSED":       {"CRITICAL": 5, "HIGH": 20, "MEDIUM": 40, "LOW": 8},
       "NOT_RELEVANT": {"CRITICAL": 0, "HIGH": 2, "MEDIUM": 5, "LOW": 1}}},
    {"standardCode": "DORA", "compliancePercentage": 92, "ruleCountsByStatusBySeverity": { "…": "…" }}
  ]
}
```

There is **no top-level `compliancePercentage`** (0 % of rows checked). The array has one entry
per enabled standard — observed codes `CIS`, `DORA`, `DTSE`, `NIST`, `STIG` — each with its own
`compliancePercentage` and a status × severity rule-count matrix (values above are illustrative). Use it for fast
UC-C0 dashboards without a full `COMPLIANCE_FINDING` join.

### KSPM-assessed object types (Kubernetes only)

KSPM is **K8s-only today** — no AWS/Azure/GCP/host-level rules in the
DT-native pipeline. Cloud and VMware coverage flows through CSPM/VSPM.
The `compliance.result.object.type` codes are listed in [KSPM result + evidence fields](#kspm-result--evidence-fields)
(workload kinds plus namespaces, roles, role bindings and service accounts).

### Severity precedence + per-rule status derivation

Per-(rule, object) rows are aggregated to per-rule rows by Step 2 (see
[compliance.md](compliance.md)). Status precedence:

```text
any FAILED  → rule = FAILED
else any MANUAL → rule = MANUAL
else any PASSED → rule = PASSED
else            → rule = NOT_RELEVANT
```

> **MANUAL is currently non-actionable in the SPM app** — there's no
> remediation workflow for it. It surfaces "we couldn't auto-determine; check
> manually." Treat MANUAL as a triage hint, not a remediable defect.

> **No mute / exemption mechanism** in the KSPM event stream. Findings have
> no equivalent of `vulnerability.mute.{status,reason,user,comment}`. "Accepted
> risk" is not modeled in `security.events` — it's a downstream UI/policy
> concept that doesn't surface in DQL. If users ask "show me accepted-risk
> compliance findings," explain that the field doesn't exist.

## Compliance Fields (external — CSPM / VSPM / external posture tools)

External `COMPLIANCE_FINDING` events use the cross-provider normalized
`finding.*` namespace and **do not** populate `compliance.rule.*` consistently.

| Field | Notes |
|---|---|
| `finding.id`, `finding.title`, `finding.type`, `finding.time.created` | Use these for filtering, grouping, and drilldown — `compliance.rule.*` will be null on most external rows |
| `dt.security.risk.level` | Cross-provider severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `NONE`, `NOT_AVAILABLE`) |
| `compliance.status` | Some providers (observed: Microsoft Defender for Cloud) populate this as a top-level string (`FAILED` / `PASSED`) instead of `compliance.result.status.level`; check both when filtering external. **Not an SD field.** Runecast uses the full `compliance.result.*` schema instead. |
| `compliance.standards` (array), `compliance.policy`, `compliance.control` | External compliance taxonomy — group/filter by these (`expand` the `compliance.standards` array). See [compliance.md § External compliance taxonomy fields](compliance.md#external-compliance-taxonomy-fields). |
| `event.provider` / `product.vendor` / `product.name` | Provider identification — scope via [all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type) |
| `object.*` | Affected entity (cloud resource identifier, etc.) |
| `dt.raw_data` | Original payload — 100 % on Defender, 0 % on Runecast |

External `COMPLIANCE_SCAN` rows (Defender) are per-assessment, not per-run: `scan.id`, `scan.title`, `assessment.id`, `compliance.control`, singular `compliance.standard`, `compliance.status`; no `object.*`, no scan-time fields.

> **DT SPM query patterns (Steps 1 + 2) don't work for external compliance** —
> the inner join to `COMPLIANCE_SCAN_COMPLETED` is KSPM-only, and `compliance.rule.*`
> columns are null on external rows. Use the cross-provider patterns in
> [all-security-events.md](all-security-events.md) for unified queries.

---

## Coverage Fields (`VULNERABILITY_SCAN`)

`VULNERABILITY_SCAN` events are emitted by vulnerability-scan-service once per
SBOM scan request. They mark "this entity was assessed at this time."

| Field | Notes |
|---|---|
| `dt.smartscape_source.id` | Smartscape node ID of the scanned entity (`PROCESS-…`). **Tenant-dependent gap:** missing on ≈4.5 % of non-CLV scans on one tenant checked, 100 % populated on another. Rows without it still carry the deprecated `dt.source_entity` / `dt.entity.host`; check the fill rate before trusting a coverage denominator built only on `dt.smartscape_source.id` |
| `dt.smartscape_source.type` | **UPPERCASE** — `PROCESS` on every Dynatrace / OneAgent scan event (no `HOST` value observed). External scanners may carry cloud-resource types (e.g. `AZURE_MICROSOFT_CONTAINERREGISTRY_REGISTRIES`) or none. Legacy `dt.source_entity(.type)` is deprecated (see § Smartscape). |
| `event.provider` | `Dynatrace` or **null** (tenant-dependent) on non-code-level scans, `OneAgent` on code-level (CLV) scans — scope DT scans with `product.vendor == "Dynatrace"` |
| `object.type` | `process_group_instance` (non-CLV) / `PROCESS` (CLV); external: `CODE_ARTIFACT`, `CODE_REPOSITORY`, `HOST`, `CONTAINER_IMAGE` |
| `product.name` | `Runtime Vulnerability Analytics` |
| `product.vendor` | `Dynatrace` (external scanners: their own name — SonarQube, Qualys, Snyk, Sonatype, GitHub, Amazon ECR, Defender) |
| `product.feature` | RVA scan mode — see table below. Populated on CLV scan events (`Code-level Vulnerability Analytics`); **null on third-party / OS scan events** — `filterOut product.feature == "Code-level Vulnerability Analytics"` keeps both null and explicitly-non-CLV rows, which is what coverage queries want. Always populated on the paired `VULNERABILITY_FINDING` events. |
| `scan.id` | Scan request UUID — links a `VULNERABILITY_SCAN` to its `VULNERABILITY_FINDING`s |
| `scan.time.started` / `scan.time.completed` | Server-side scan timestamps (`timestamp`). The underscore spellings do not exist. **Both are absent (0 %) on code-level scans**; Qualys and GitHub scans carry only `completed` |
| `dt.smartscape.host`, `dt.smartscape.process` | Identifiers for dedup and lookup-against-smartscapeNodes (join on `id`); 95.5 % populated on non-CLV scans. `dt.smartscape.host` is null on every Kubernetes-workload scan on one tenant checked and populated on all of them on another — behaviour is tenant-dependent, so neither rely on it for K8s workloads nor use its null-ness to identify K8s scans (use `dt.smartscape.k8s_cluster` / `k8s.cluster.name`) |

### `product.feature` values for RVA

| Value | Stack | Where populated |
|---|---|---|
| `Library Vulnerability Analytics` | `CODE_LIBRARY` | `VULNERABILITY_FINDING` only (third-party / OSS library scanning, SOFTWARE_COMPONENT SBOM). On `VULNERABILITY_SCAN` events for the same scope, `product.feature` is null. |
| `Operating System Vulnerability Analytics` | `SOFTWARE` | `VULNERABILITY_FINDING` only (OS package scanning, RPM/DEB). On `VULNERABILITY_SCAN` events for the same scope, `product.feature` is null. **Not observed** in the data checked. |
| `Code-level Vulnerability Analytics` | `CODE` | Both `VULNERABILITY_SCAN` and `VULNERABILITY_FINDING` (OneAgent IAST/Attack-detected CLV; Java 8+, .NET, Go only). |

For coverage queries against `VULNERABILITY_SCAN`:
`filter product.feature == "Code-level Vulnerability Analytics"` scopes to CLV scans;
`filterOut product.feature == "Code-level Vulnerability Analytics"` scopes to third-party / OS scans (which have null `product.feature`). See **dt-sec-contextualization** `runtime-coverage.md` for canonical patterns.

> **Scanning is event-driven, not periodic.** Scans run when an agent submits
> an SBOM. There is no fixed cadence; in practice every monitored process
> generates frequent SBOMs. A scan event missing for an entity in the last
> 24h–7d is a meaningful signal that scanning didn't happen, not just a quiet
> period. Coverage analysis windows: `7d` for "is this entity ever scanned",
> `2h–24h` for "recently scanned".

---

## Threat Intelligence Fields (`THREAT_REPORT`)

`THREAT_REPORT` events are **threat intelligence reports** (external campaigns / IOC feeds), **not
findings**. They carry **none** of the finding/entity/risk fields above — no `finding.*`, `object.*`,
`dt.security.risk.level`/`score`, `dt.smartscape*`, and no scan events. One event per
published report; **dedup by `threat.report.id`** (reports re-ingest on update). Full query patterns
and the threat-exposure correlation workflow → [threat-intelligence.md](threat-intelligence.md).
Not present in every tenant (verified where available). Re-ingestion is heavy: expect many rows per report ID.

### Report identity & provenance (required)

| Field | Notes |
|---|---|
| `threat.report.id` | Vendor-assigned report ID — **dedup key** (stable across revisions) |
| `threat.report.name` | Report title (e.g. `CSA-260753 …`, `IMMEDIATE THREAT: …`) |
| `threat.report.description` | Summary / abstract (≤2 KB) |
| `threat.report.time.created` / `.updated` | SD type `timestamp`, but **delivered as strings** in the data checked (100 % populated) — keep `coalesce(toTimestamp(…), timestamp)` |
| `threat.report.author` | Publishing author / team (optional) |
| `threat.report.references.urls` | Report URLs (optional array) |
| `threat.report.tags` | Free-form tags (optional array). There is **no** `threat.report.references.tags` (0 %, not in SD) |

### Adversary context (recommended)

| Field | Notes |
|---|---|
| `threat.actor.names` | Attributed threat-actor names/aliases (array). AlienVault OTX packs all aliases into **one comma-joined string in a 1-element array** — split before matching |
| `threat.target.countries.names` / `.iso_codes` | Targeted countries (full names / ISO 3166-1 alpha-2 — use `.iso_codes` for maps) |
| `threat.target.industries` | Targeted industry verticals (**plural** — `threat.target.industry` singular does not exist) |
| `threat.malware.families` | Malware family names (array) |
| `threat.attack.{tactic,technique,subtechnique}.{ids,names}`, `threat.attack.version` | MITRE ATT&CK of the **reported campaign** (separate arrays). Membership via `in(value, array)`. In the data checked, only `*.ids` and `technique.names` / `tactic.names` are populated (technique / subtechnique ids ≈83 %); `subtechnique.names` and `threat.attack.version` were never populated, and CrowdStrike carries no `tactic.ids`. This is intel about threats in the wild — **not** ATT&CK observed on your entities (that's `detections.md`). |

### Observables / IOCs (optional)

| Field | Notes |
|---|---|
| `threat.observables.ips` | IOC IPv4/IPv6 (`ipAddress[]`) |
| `threat.observables.domains` / `.urls` / `.emails` | Domain / URL / email IOCs (`.emails` ≈0–14 %) |
| `threat.observables.cves` | Referenced CVE IDs |
| `threat.observables.hashes.md5` / `.sha1` / `.sha256` | File-hash IOCs |

### Vendor extensions (additive — no SD counterpart)

| Field | Notes |
|---|---|
| `alienvault.pulse.public` / `alienvault.pulse.tlp` | AlienVault OTX: public flag / TLP (observed `WHITE` and `GREEN`) |
| `crowdstrike.report.slug` / `.type` / `.type.id` / `.type.name` | CrowdStrike: report slug + type. Observed: `.type` = `"CrowdStrike Alert"`, `.type.id` = `"356"`, `.type.name` = `"Notice"`; the other upstream names (`Tipper`, `Periodic Report`, `Intelligence Report`, `Recon+`) were not seen — filter on `.type.name` |

---

## Finding ID Format Cheatsheet

`finding.id` is provider-specific — match exactly when drilling down:

| Provider | Format example |
|---|---|
| Dynatrace (RVA findings, KSPM, Automated Detections) | UUID — `a9bc7599-2b1b-45b7-8f6c-6ab57ad4c343` |
| Dynatrace RAP | Short ID — `A-1YIXMY9H` (not a UUID) |
| AutomationEngine | 64-char hex hash (documented upstream; not observed in the data checked) |
| Amazon GuardDuty, Runecast | 32-char hex |
| Microsoft Defender / Sentinel | Detections: UUID; Defender compliance: the Azure resource path |
| External vulnerability scanners | UUID (Snyk Code), ARN, URL, composite path, numeric or hash — discover per provider |

---

## SD changes in flight (not emitted yet)

Defined in the Semantic Dictionary but not yet released, or pending deprecations — **do not write queries against these**
until they appear in runtime data (verify with a `countIf(isNotNull(...))` first):

| Change | Effect on this file |
|---|---|
| `rule.id` / `rule.name` / `rule.description` / `rule.type` replace `compliance.rule.id` / `.title` | 0 % emitted; keep `compliance.rule.*` |
| `vulnerability.cve_ids` / `.cwe_ids` / `.owasp_ids` replace `vulnerability.references.cve` / `.cwe` / `.owasp`; `vulnerability.external_id` / `.external_url` deprecated; `vulnerability.id` redefined (DTVR ids); `vulnerability.exploit.status` / `.remediation.status` become closed enums | Today's `references.*` names stay valid until the rename ships |
| `finding.status` / `finding.assignee` / `finding.activity` on `DETECTION_FINDING` | Not emitted |
| `vulnerable_functions.usage.*` on `VULNERABILITY_FINDING` | Finding-side equivalent of `affected_entity.vulnerable_functions*`; not emitted |
| `vulnerability.category` (`SOURCE_CODE`, `LIBRARY`, `OPERATING_SYSTEM`, …) | Overlaps `vulnerability.stack`; not emitted |

Also already on SD `main` but not emitted by the runtime: `detection.name`, `scan.*` names for Automated Detections
executions (runtime emits `execution.*`), `software_component.path`, `finding.action` lowercase enum values.
