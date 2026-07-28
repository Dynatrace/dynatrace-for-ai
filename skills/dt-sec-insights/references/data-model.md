# Security Events Data Model

Canonical reference for `fetch security.events` — event types, providers, fields,
entity scoping. Use this as the field dictionary when building any DQL query against
`security.events`.

> **No bucket filter.** Security event data may live in any bucket; do **not**
> apply `dt.system.bucket == "..."` filters in queries.

---

## Contents

- [Event Types (`event.type`)](#event-types-eventtype)
  - [RVA cadence](#rva-cadence)
- [Provider Taxonomy](#provider-taxonomy)
- [Common Fields (semantic dictionary required)](#common-fields-semantic-dictionary-required)
- [Entity Scoping Fields](#entity-scoping-fields)
- [Vulnerability Fields (RVA — post-aggregation)](#vulnerability-fields-rva--post-aggregation)
- [Vulnerability Fields (external — raw stream)](#vulnerability-fields-external--raw-stream)
- [Compliance Fields (SPM — post-aggregation)](#compliance-fields-spm--post-aggregation)
- [Coverage Fields (`VULNERABILITY_SCAN`)](#coverage-fields-vulnerability_scan)
- [Threat Intelligence Fields (`THREAT_REPORT`)](#threat-intelligence-fields-threat_report)
- [Finding ID Format Cheatsheet](#finding-id-format-cheatsheet)

---

## Event Types (`event.type`)

| Value | Description | Where it comes from |
|---|---|---|
| `DETECTION_FINDING` | Behavioral detection / threat alert | DT RAP (OneAgent — `product.name == "Runtime Application Protection"`), DT Automated Detections (`event.provider == "Dynatrace Automated Detections"`), AutomationEngine, and external detection sources (cloud-security / SIEM / WAF, ingested) |
| `DETECTION_EXECUTION_SUMMARY` | Audit row emitted **per Automated Detections rule run** — was the rule triggered, how many records scanned, did it succeed or warn | DT Automated Detections only. Both `event.provider == "Dynatrace Automated Detections"` and `product.name == "Automated Detections"` are populated; either filter works equivalently. This skill prefers `event.provider == "Dynatrace Automated Detections"` to keep the filter symmetric with `DETECTION_FINDING` queries. One row per rule execution; carries `execution.id`, scan stats (`eventsWritten`, `scannedRecords`, `scannedBytes`), `analysisTimeframeStart` / `End`, status (`SUCCESS` / `SUCCESS_W_WARNINGS` / `FAILURE`). Not a finding; query separately when investigating "did my rule fire?" |
| `THREAT_REPORT` | Threat intelligence report (external campaign / adversary report / IOC feed) — **NOT a finding** | External TI platforms — AlienVault OTX (`event.provider == "AlienVault OTX"`), CrowdStrike Falcon Intelligence (`event.provider == "CrowdStrike"`). Describes threats **in the wild**, not on your entities: no `finding.*` / `object.*` / `dt.security.risk.level`, no affected entity, no scan cycle. Dedup by `threat.report.id`. Query via [threat-intelligence.md](threat-intelligence.md) — **excluded from cross-provider finding summaries and the double-counting guard.** |
| `VULNERABILITY_FINDING` | Software / component vulnerability | **External SCA / SAST / image scanners** (ingested). **Also emitted by Dynatrace's vulnerability-scan-service** as the raw per-scan finding feed — but use the RVA state-report types below for queries about "current Dynatrace vulnerabilities." |
| `COMPLIANCE_FINDING` | Misconfiguration / policy violation | DT SPM (`product.vendor == "Dynatrace"`) and external compliance / posture tools (ingested) |
| `VULNERABILITY_SCAN` | Coverage event — a vulnerability scan ran | DT RVA (`product.vendor == "Dynatrace"`) and external. Lowercase `dt.source_entity.type` (`process_group_instance` / `host`). |
| `COMPLIANCE_SCAN` | Coverage event — a compliance scan ran | DT and external |
| `VULNERABILITY_STATE_REPORT_EVENT` | DT RVA per-entity vulnerability snapshot | Dynatrace RVA only (`event.provider == "Dynatrace"`, `event.level == "ENTITY"`) |
| `VULNERABILITY_STATUS_CHANGE_EVENT` | DT RVA state transition (open→resolved, mute, etc.) | Dynatrace RVA only — emitted **on change**, immediate |
| `VULNERABILITY_TRACKING_LINK_CHANGE_EVENT` | DT RVA tracking-link / ticket update (Jira, wiki, …) | Dynatrace RVA only — emitted **on change**, immediate |
| `COMPLIANCE_SCAN_COMPLETED` | DT SPM scan-completion marker (used as inner-join target) | Dynatrace SPM only |
| `VULNERABILITY_COVERAGE_REPORT_EVENT` | **Deprecated** — use `VULNERABILITY_SCAN` instead | Dynatrace RVA (legacy) |
| `VULNERABILITY_ASSESSMENT_CHANGE_EVENT` | **Legacy** — assessment-change deltas; not used by current RVA aggregation pipeline. | Dynatrace RVA (legacy) |

**Critical routing rules:**

- DT RVA uses the three RVA-internal types — **not** `VULNERABILITY_FINDING`. The
  three must be queried together as a union via `in(event.type, {…})`.
- DT SPM uses `COMPLIANCE_FINDING` joined with `COMPLIANCE_SCAN_COMPLETED` on
  `scan.id`.
- External vulnerability / compliance findings always use `VULNERABILITY_FINDING`
  / `COMPLIANCE_FINDING`.
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

---

## Provider Taxonomy

| `event.provider` | `product.name` | `product.vendor` | Notes |
|---|---|---|---|
| `Dynatrace` | (varies) | `Dynatrace` | DT RVA / DT KSPM. Also the provider on RAP detection findings (see next row). Excluded from cross-provider summaries unless `event.type == "DETECTION_FINDING"` (double-counting guard). |
| `OneAgent` | `Runtime Application Protection` | `Dynatrace` | DT RAP — runtime attack detections via OneAgent. Both `event.provider == "OneAgent"` and `product.name == "Runtime Application Protection"` are populated on every RAP row; either filter works equivalently. This skill prefers `product.name == "Runtime Application Protection"` as the canonical form (matches the official Dynatrace docs naming). |
| `Dynatrace Automated Detections` | `Automated Detections` | `Dynatrace` | DT detection rules engine (threat-detection-service) — both custom and built-in rules. Hardcoded provider; emits both `DETECTION_FINDING` and `DETECTION_EXECUTION_SUMMARY`. |
| `Dynatrace` | `Security Posture Management` | `Dynatrace` | DT KSPM compliance findings + scan-completed events. |
| `AutomationEngine` | `AutomationEngine` | `Dynatrace` | Custom workflow detections from the AutomationEngine product. |
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
| `finding.time.created` | string timestamp | When the finding was created — required (use `toTimestamp()` for comparison) |
| `dt.security.risk.level` | string | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `NONE`, `NOT_AVAILABLE` — required |
| `dt.security.risk.score` | double | Numeric 0–10; present on `*_FINDING` events — **not** present on DT RVA state-report events (use `vulnerability.risk.score` there) |
| `object.id` | string | ID of affected object — required (or `object.name`) |
| `object.name` | string | Name of affected object — required (or `object.id`) |
| `object.type` | string | **For Dynatrace-emitted events** (RVA, RAP, KSPM, Automated Detections), this is always one of the supported Smartscape entity types: `PROCESS_GROUP`, `CONTAINER`, `CONTAINER_IMAGE`, `K8S_POD`, `KUBERNETES_CLUSTER`, `KUBERNETES_NODE`, `HOST`, etc. (uppercase, snake-style). **For external / third-party events**, `object.type` carries the vendor-reported value as-is — e.g. `AwsEc2Instance`, `AwsEksCluster`, `AWS::EC2::Instance`. Don't try to normalize external object types to Smartscape types — accept them as the vendor reports. |
| `product.name` | string | Product within the provider — e.g. `OneAgent` (DT) |
| `product.vendor` | string | `Dynatrace` or external vendor |

**Object types observed (Dynatrace-emitted, normalized):** `PROCESS_GROUP`,
`CONTAINER`, `CONTAINER_IMAGE`, `K8S_POD`, `KUBERNETES_CLUSTER`,
`KUBERNETES_NODE`, `HOST`. **External-emitted (vendor-reported, as-is):**
`AwsEc2Instance`, `AwsEksCluster`, `AWS::EC2::Instance`, etc. Match on the
exact vendor string when filtering external; on the normalized Smartscape
type when filtering Dynatrace-emitted.

---

## Entity Scoping Fields

When filtering findings by entity ID/name, use one (or all in an OR chain — see
[common-patterns.md § 5](common-patterns.md#5-wide-entity-scoping-or-chain)).

> **Entity-identifier namespaces split by event family.** Which fields carry entity refs depends on the event type — they are NOT interchangeable:
>
> | Event family | Entity namespaces present | Entity namespaces absent |
> |---|---|---|
> | `DETECTION_FINDING`, `COMPLIANCE_FINDING`, external `VULNERABILITY_FINDING`, `VULNERABILITY_SCAN`, `COMPLIANCE_SCAN` | `dt.smartscape*` (3rd-gen), `dt.entity*` (2nd-gen); `dt.source_entity` only as a legacy / event-family-specific fallback | `affected_entity.*`, `related_entities.*` (RVA-specific, null here) |
> | `VULNERABILITY_STATE_REPORT_EVENT`, `VULNERABILITY_STATUS_CHANGE_EVENT`, `VULNERABILITY_TRACKING_LINK_CHANGE_EVENT` (RVA) | `affected_entity.*` (classic ID + name + type, resolved in-event), `related_entities.{kubernetes_workloads,kubernetes_clusters,applications,services,hosts,databases}.{ids,names}` (blast-radius classic IDs + names; `.ids` type prefix ≠ group name — see [vulnerabilities-dynatrace.md § Classic ID prefix gotcha](vulnerabilities-dynatrace.md#classic-id-prefix-gotcha)) | `dt.smartscape*`, `dt.entity*`, `dt.source_entity` (null on RVA events) |
>
> For raw-listing projection guidance per event family see [common-patterns.md § 17](common-patterns.md#17-entity-identifier-preservation-on-raw-listings).

### Smartscape (preferred for new queries)

`dt.entity.*` is deprecated for Smartscape navigation; classic entity IDs like
`dt.entity.host` remain valid as identifiers.

| Field | Example |
|---|---|
| `dt.smartscape_source.id` | Smartscape node ID for the source entity |
| `dt.smartscape.process` / `.host` / `.k8s_cluster` / `.k8s_node` / `.k8s_pod` | Per-type Smartscape node IDs |
| `dt.source_entity` | Legacy / event-family-specific classic entity ID; prefer `dt.smartscape_source.id`, `dt.smartscape.*`, `dt.entity.*`, `object.*`, image digest, or host IP paths for new correlation queries |

### Classic entity IDs

| Field | Example |
|---|---|
| `dt.entity.host` | `HOST-XXXXXXXXXXXXXXXX` |
| `dt.entity.process_group` / `process_group_instance` | `PROCESS_GROUP[-INSTANCE]-XXXXXXXXXXXXXXXX` |
| `dt.entity.kubernetes_cluster` / `kubernetes_node` | `KUBERNETES_*-XXXXXXXXXXXXXXXX` |
| `dt.entity.cloud_application_namespace` | `CLOUD_APPLICATION_NAMESPACE-XXXXXXXXXXXXXXXX` |

### Kubernetes

| Field | Example |
|---|---|
| `k8s.pod.uid` / `k8s.cluster.uid` | UUIDs |
| `k8s.cluster.name` / `k8s.namespace.name` / `k8s.node.name` / `k8s.pod.name` / `k8s.workload.name` | Names |

### Cloud

| Field | Example |
|---|---|
| `aws.resource.id` / `aws.resource.name` | AWS ARN / friendly name |
| `azure.resource.id` / `azure.resource.name` | Azure |
| `gcp.resource.id` / `gcp.resource.name` | GCP |

### Object-level (raw stream)

| Field | Notes |
|---|---|
| `object.id`, `object.name` | Direct match on the finding's object |
| `host.name` | Host name (string) |
| `host.ip` | IP address — array; use `expand` + `ip()` to normalize |

---

## Detection Fields (`DETECTION_FINDING`)

Detection findings are **one-shot events** — there's no per-(rule, entity) aggregation
pipeline like RVA's state-report stream or KSPM's scan-completed join. Each row is a
discrete detection. Different sources populate different sub-namespaces.

### Cross-provider core (all detections)

| Field | Notes |
|---|---|
| `finding.id`, `finding.title`, `finding.description`, `finding.type` | Cross-provider normalized |
| `finding.severity` | Vendor-supplied severity string (provider-native scale) |
| `finding.score` | Vendor-supplied score |
| `finding.time.created` (raw) / `finding.created_time` | When the detection was generated. String timestamp; use `toTimestamp()` for comparison. |
| `finding.remediation` | Free-text remediation guidance (DT Automated Detections populates this from rule template; some external providers also populate it) |
| `dt.security.risk.level` | Cross-provider normalized: `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` / `NONE` / `NOT_AVAILABLE`. Always prefer this over `finding.severity` for cross-provider comparisons. |
| `dt.security.risk.score` | Normalized 0–10 score. External severities map: `Critical → 10.0`, `High → 8.9`, `Medium → 6.9`, `Low → 3.9`, other → `0.0` |
| `event.description` | Provider-supplied detection description; useful for search by attack pattern keyword |
| `event.outcome` | When populated, indicates whether the detection led to a real action (e.g. `success` / `failure`). Sparse — many providers don't emit it. **Prefer `finding.action` for RAP** (see below). |
| `dt.raw_data` | Original ingested JSON for external findings — useful for fields not normalized to the SD. Parse with `parse … "JSON:raw"`. |

### DT Automated Detections (`event.provider == "Dynatrace Automated Detections"`)

Emitted by threat-detection-service when a user-defined or built-in rule fires.

| Field | Notes |
|---|---|
| `detection.id` | Rule UUID — stable across executions of the same rule |
| `detection.title` | Rule title (configurable) |
| `detection.description` | Rule description |
| `detection.owner_id` | User ID of the rule owner |
| `threat.attack.technique.ids` | **Array** of MITRE ATT&CK technique IDs (T-prefixed, e.g. `["T1059", "T1078"]`). Primary pivot for heat maps. Empty / null if the rule isn't tagged. |
| `threat.attack.subtechnique.ids` | **Array** of sub-technique IDs (dotted, e.g. `["T1059.003", "T1078.004"]`). **Independent** from `technique.ids` — no positional alignment; parent technique is encoded in the ID itself (`T1059.003` → `T1059`). |
| `threat.attack.tactic.ids` | **Array** of MITRE tactic IDs (TA-prefixed, e.g. `["TA0002"]`). |
| `threat.attack.technique.names` / `subtechnique.names` / `tactic.names` | Optional companion `.names` arrays — positional with `.ids` when populated. |
| `threat.attack.version` | ATT&CK framework version, e.g. `"15.1"`. Useful for audit / reproducibility across renumbering. |
| `execution.id` | Execution UUID — joins this finding to its `DETECTION_EXECUTION_SUMMARY` row |
| `execution.actor_id` | Actor that triggered the execution (scheduler / on-demand user) |
| `finding.event_properties` | User-defined custom properties from the rule template (free-form key/value map) |

> **`finding.severity` enum for Automated Detections** is `CRITICAL`, `HIGH`,
> `MEDIUM`, `LOW`, `NONE` — **five values, including `NONE`** (used for
> informational-only rules). Cross-provider `dt.security.risk.level` may also
> add `NOT_AVAILABLE`.

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
| `finding.type` | Original vendor-reported attack type — **free-form `string`, not a normalized enum** (SD `finding.yaml`: "Original type of the finding reported by the vendor"). Values vary by vendor and version; observed RAP examples: `SQL injection`, `CMD injection`, `JNDI injection`, `SSRF`. Filter with `contains(lower(finding.type), …)` rather than exact match; discover live values with the summarize-by-`finding.type` query in `detections.md`. The legacy `attack.type` / `attack.vector` names from older RAP-namespace docs are not in the Semantic Dictionary. |
| `finding.action` | What OneAgent did about the attack — `Blocked`, `Audited` (monitor mode — detected only), `Allowlisted` (allowed by an explicit allowlist rule). The "blocked vs monitored" breakdown query keys off this field. |
| `actor.ips` | Array of attacker source IPs (`ipAddress[]`, **Stable**). One row may carry multiple IPs (IPv4 + IPv6, proxy chains). For top-IP queries, `expand actor.ips` then cast with `ip(actor.ips)` so downstream IP comparisons / CIDR checks type-check correctly. Enrichable via the Security Enrichment app (AbuseIPDB / VirusTotal / custom). |
| `actor.geo.country.name` | Country name (Experimental); also `actor.geo.city.name`, `actor.geo.continent.name`, `actor.geo.location.lat`/`lon`. May be null when enrichment isn't configured. |
| `dt.security.rap.target.{id,type,name}` | What was attacked — for SQL injection this is the database entity (`HOST-…`), for service-targeted attacks it's the service. `object.*` carries the entity where the exploit happened; `dt.security.rap.target.*` is the underlying target. |
| `url.path` | HTTP path targeted (when applicable) |
| `dt.smartscape.process` / `dt.smartscape.host` | Smartscape entity IDs of the attacked process / host |

> RAP-specific drilldown into entry-point payloads (`entry_point.url.path`,
> `entry_point.payload`, `entry_point.function.name`,
> `entry_point.user_controlled_inputs`), sink-code (`sink.code.function`,
> `sink.code.namespace`), and code-location (`code.function`, `code.namespace`,
> `code.filepath`, `code.line.number`) lives in product-emitted fields outside
> the SD stable namespace. The Threats & Exploits app is the supported
> surface for full attack reconstruction.

> **RAP control mode is configured at OneAgent**, not in queries. Modes are
> `Off` (not detected — no event), `Monitor` (detected only — `finding.action == "Audited"`),
> `Block` (detected and stopped — `finding.action == "Blocked"`). Per-PG / per-vulnerability-type
> custom rules can override the global mode.

### Detection finding by event-storage bucket (informational only)

| `dt.system.bucket` | Source | Retention |
|---|---|---|
| `default_securityevents_builtin` | DT-native (RVA / RAP / KSPM / Automated Detections) | 3 years |
| `default_securityevents` | External / OpenPipeline ingest | 1 year |

> **Do NOT add `dt.system.bucket` filters to queries.** Security event data
> may live in any bucket (custom routing rules, retention overrides). Bucket
> filters can hide data. The bucket field is informational metadata for
> understanding *why* retention differs between sources, not a filter axis.

---

## Vulnerability Fields (RVA — raw + post-aggregation)

The raw `VULNERABILITY_STATE_REPORT_EVENT` carries one row per
`(vulnerability, affected_entity)` pair. The canonical RVA Stage-3 `fieldsAdd`
(see [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md)) collapses these per-entity rows
into vulnerability-level verdicts. Some fields below exist only in the raw
stream, some only post-aggregation, some in both.

### Identity / metadata

| Field | Values / notes |
|---|---|
| `vulnerability.display_id` | Human-readable, e.g. `S-12345` |
| `vulnerability.id` | Internal UUID |
| `vulnerability.external_id` | **Provider-emitted reference identifier** (e.g. NVD CVE ID, MITRE ID). Not a user-attached tracking ticket — for that, see `vulnerability.tracking_link.*` further down. |
| `vulnerability.external_url` | **Provider-emitted reference URL** (NVD page, vendor advisory, etc.). **NOT the user-attached remediation/Jira link** — that field is `vulnerability.tracking_link.url`. Filtering `vulnerability.external_url != ""` to find "vulnerabilities with a tracking link" is a common mistake; it returns vulnerabilities that have any vendor reference URL, which is almost all of them. |
| `vulnerability.title` | Short description |
| `vulnerability.description` | Long description |
| `vulnerability.type` | Classification (e.g. CWE family) |
| `vulnerability.technology` | Target tech (e.g. `Java`, `.NET`, `Go`, `Node.js`) |
| `vulnerability.stack` | `CODE` (CLV — OneAgent IAST/Attack), `CODE_LIBRARY` (matched on software components), `SOFTWARE` (matched on runtime / OS packages), `CONTAINER_ORCHESTRATION` (Kubernetes-level). See `TechnologyStack` enum. |
| `vulnerability.code_location.name` | CLV only — source file + line of vulnerable code |
| `vulnerability.is_fix_available` | Boolean — `true` if a fix exists upstream |
| `vulnerability.remediation.description` | Free-text guidance |
| `vulnerability.references.cve` | CVE ID (string or array) |
| `vulnerability.references.cwe` | CWE ID(s) |
| `vulnerability.references.owasp` | OWASP category reference(s) |

### Scoring

| Field | Values / notes |
|---|---|
| `vulnerability.cvss.base_score` | CVSS base score (0–10), `vulnerability.cvss.version` and `vulnerability.cvss.vector` accompany |
| `vulnerability.cvss.version` | `2.0`, `3.0`, `3.1`, `4.0` |
| `vulnerability.cvss.vector` | Static CVSS vector string |
| `vulnerability.risk.score` | Dynatrace Security Score (DSS) — context-aware, **never exceeds CVSS base**. Per-entity in raw events; collapsed to vulnerability-level via `takeMax` (muted entities contribute 0). |
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
| `vulnerability.davis_assessment.exposure_status` | `vulnerability.exposure.status` | `PUBLIC_NETWORK` > `NOT_AVAILABLE` > `NOT_DETECTED`. Raw values include `ADJACENT_NETWORK`, but it's intentionally **not** treated as public exposure — falls through to `NOT_DETECTED` in the derived field. Query the raw field directly for adjacent-network analysis. |
| `vulnerability.davis_assessment.exploit_status` | `vulnerability.exploit.status` | `AVAILABLE` > `NOT_AVAILABLE` |
| `vulnerability.davis_assessment.vulnerable_function_status` | `vulnerability.vulnerable_function.status` | `IN_USE` > `NOT_AVAILABLE` > `NOT_IN_USE` |
| `vulnerability.davis_assessment.data_assets_status` | `vulnerability.data_assets.status` | `REACHABLE` > `NOT_AVAILABLE` > `NOT_DETECTED` |
| `vulnerability.davis_assessment.assessment_mode` | (kept long-form in projections) | `FULL` (all entities full-stack) > `REDUCED` (some entity in Foundation/Infra-Only) > `NOT_AVAILABLE` |
| `vulnerability.davis_assessment.assessment_mode_reasons` | — | array; values: `LIMITED_BY_CONFIGURATION`, `LIMITED_AGENT_SUPPORT` (note: underscore, not dot) |

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
| `vulnerability.resolution.change_date` | `takeMax` | Last status transition timestamp (nanoseconds). For OPEN vulnerabilities indicates for how long they are in that status. |
| `vulnerability.mute.status` | derived: `if(in("NOT_MUTED", muteStatuses), "NOT_MUTED", else: "MUTED")` | Per-entity mute; vulnerability is fully muted only if every entity is muted |
| `vulnerability.mute.reason` | (raw, per-entity) | `FALSE_POSITIVE`, `IGNORE`, `AFFECTED` (=> NOT_MUTED), `CONFIGURATION_NOT_AFFECTED`, `OTHER` |
| `vulnerability.mute.user` | (raw, per-entity) | User who set the mute |
| `vulnerability.mute.comment` | (raw, per-entity) | Free-text reason |
| `vulnerability.mute.change_date` | (raw, per-entity) | Mute timestamp |
| `vulnerability.tracking_link.url` | (raw, per-entity; emitted by `VULNERABILITY_TRACKING_LINK_CHANGE_EVENT`) | Jira / wiki / ticket URL |
| `vulnerability.tracking_link.text` | (raw, per-entity) | Display text for the link |

> **Mute states observed in the UI** include `Muted (Open)` (vulnerability
> remains open but every entity is silenced) and `Muted (Resolved)` (a muted
> vulnerability auto-resolved). These compose from the OPEN/RESOLVED + MUTED/NOT_MUTED
> per-entity arrays — they're **not separate enum values** in `security.events`.

### Affected / related entity fields

| Field | Values / notes |
|---|---|
| `affected_entity.id` | Smartscape / classic entity ID |
| `affected_entity.name` | Display name |
| `affected_entity.type` | `PROCESS_GROUP`, `HOST`, `KUBERNETES_NODE`, `PROCESS_GROUP_INSTANCE` (rare). See `MonitoredEntityType`. |
| `affected_entity.affected_processes.count` | Process instances inside the PG that carry the vulnerability |
| `affected_entity.affected_processes.ids` | Array of `PROCESS_GROUP_INSTANCE-...` IDs |
| `affected_entity.vulnerable_component.id` | Internal component ID |
| `affected_entity.vulnerable_component.name` | Library/component name (e.g. `log4j-core 2.14.1`) |
| `affected_entity.vulnerable_component.short_name` | Short label |
| `affected_entity.vulnerable_component.package_name` | Package name (e.g. `org.apache.logging.log4j:log4j-core`) |
| `affected_entity.vulnerable_functions` | Array of FQCN method names actually executed (e.g. `org.apache.http.client.utils.URIUtils#decode`). **Requires** the OneAgent `Java vulnerable function reporting` (or equivalent) feature. |
| `affected_entity.vulnerable_functions_not_in_use` | FQCN methods present but not executed (note: underscore, not dot — internal/experimental in SD) |
| `affected_entity.vulnerable_functions_not_available` | FQCN methods that could not be evaluated (note: underscore, not dot — internal/experimental in SD) |
| `affected_entity.reachable_data_assets.ids` | Database IDs reachable from this entity (the Davis "reachable data assets" dimension — distinct from the blast-radius `related_entities.databases.*` group) |
| `related_entities.{kubernetes_workloads,kubernetes_clusters,applications,services,hosts,databases}.{ids,names}` | Indirect blast-radius entities (arrays of classic IDs + display names). `.ids` carry classic entity IDs; the type prefix may differ from the group name (e.g. `kubernetes_workloads.ids` → `CLOUD_APPLICATION-…`; `databases.ids` → `SERVICE-…`). `.names` are positionally paired with `.ids`. |

> **PG-only collateral.** `affected_processes.*` fields are non-empty **only**
> when `affected_entity.type == "PROCESS_GROUP"`. HOST and KUBERNETES_NODE
> entities don't carry them.

> **Runtime-assessment status field naming.** Raw events carry the long names
> `vulnerability.davis_assessment.vulnerable_function_status`, etc. Stage-3
> `fieldsAdd` collapses them to the shortened forms — those are the names
> used in filters, projections, and downstream queries.

---

## Vulnerability Fields (external + DT-emitted `VULNERABILITY_FINDING`)

`VULNERABILITY_FINDING` events come from two sources:

- **External SCA / SAST / image scanners** ingested via OpenPipeline.
- **vulnerability-scan-service (Dynatrace)** — emits one `VULNERABILITY_FINDING`
  per matched vulnerability inside a scan, **plus** one `VULNERABILITY_SCAN`
  per scan request. These are the "raw" findings that feed RVA's state-report
  aggregation; normally you query the state-report stream instead. To exclude
  Dynatrace-emitted findings: `filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"`.

External `VULNERABILITY_FINDING` events do NOT carry the RVA-derived fields.
They use the cross-provider normalized fields documented in [§ Common Fields](#common-fields-semantic-dictionary-required).

| Field | Notes |
|---|---|
| `vulnerability.references.cve` | CVE ID (also on RVA) |
| `vulnerability.id` | Provider's vulnerability identifier |
| `software_component.name` | Vulnerable library |
| `software_component.purl` | Package URL (PURL) — canonical identifier for SOFTWARE_COMPONENT scans |
| `software_component.type` | E.g. `MAVEN`, `NPM`, `PYPI`, `GO`, `RPM`, `DEB` |
| `component.name` / `component.version` | Alternate component fields (used by some external scanners) |
| `dt.entity.software_component` | DT-emitted PURL-based component entity ID (SOFTWARE_COMPONENT scans only) |
| `container_image.digest` / `.id` / `.registry` / `.repository` | Container image dimensions |
| `artifact.repository` | Artifact repository (alternative to `container_image.repository`; coalesce them — see [common-patterns.md § 12](common-patterns.md#12-repository--artifact-coalescing)) |

> **Container-image dedup precedence.** For "distinct images" counts, key dedup on the most
> specific identifier present: `container_image.digest` (immutable) > `container_image.id` >
> `container_image.registry` + `container_image.repository`. Scanners vary in which they populate.

> **Severity normalization.** When external findings are ingested, severities
> are mapped to the normalized risk score: `Critical → 10.0`, `High → 8.9`,
> `Medium → 6.9`, `Low → 3.9`, `Other / unknown → 0.0`. Use
> `dt.security.risk.level` rather than provider-specific severity fields for
> cross-provider comparisons.

> **`finding.id` composition.** `finding.id` is a deterministic hash of
> `object.id` + `vulnerability.id` + `component.name` + `component.version` +
> `product.name` + `product.vendor`. `dedup finding.id` is the canonical grain for
> Dynatrace-generated findings — it collapses the same finding re-emitted each scan
> cycle (~15 min) to a single latest row.

> **DT-generated `VULNERABILITY_FINDING` entity/scope fields.** DT-generated findings
> carry `dt.security.risk.level` / `dt.security.risk.score`, `software_component.purl`,
> `finding.time.created`, and `dt.smartscape.process` with `dt.smartscape_source.type`
> — scope by entity via Smartscape. They do **not** carry the embedded
> `affected_entity.*` / `related_entities.*` arrays that RVA state reports do.

---

## Compliance Fields (SPM)

Dynatrace Security Posture Management (SPM / XSPM) has three flavors:

| Flavor | What | Source | `product.name` | `event.provider` |
|---|---|---|---|---|
| **KSPM** | Kubernetes — CIS, DORA, NIST, DISA STIG | DT-native (security-analyzer-service) | `Security Posture Management` | `Dynatrace` |
| **CSPM** | Cloud posture — AWS / Azure / GCP foundations, plus broad standards (PCI DSS, ISO 27001, HIPAA, GDPR, …) | external/partner integration | (varies) | (varies) |
| **VSPM** | VMware posture — DISA STIG, NIST | external/partner integration | (varies) | (varies) |

**KSPM is the only DT-native flavor** — its events fit the `event.provider == "Dynatrace"` AND `product.vendor == "Dynatrace"` filter. CSPM/VSPM and other external compliance providers populate the cross-provider `finding.*` namespace but **do not** populate `compliance.rule.*` consistently — see § Compliance Fields (external).

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
| `compliance.rule.id` | `<STANDARD>-<NUMBER>` — e.g. `CIS-2762`, `STIG-V-242400`, `DORA-9`, `NIST-AU-2` |
| `compliance.rule.title` | Human-readable rule name |
| `compliance.rule.severity.level` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` — **exactly four values**. KSPM does not emit `NONE` / `NOT_AVAILABLE`. |
| `compliance.rule.severity.score` | Numeric severity (0–10): `CRITICAL=10`, `HIGH=7`, `MEDIUM=4`, `LOW=1` (CCSS-based since 2026-03-10) |
| `compliance.rule.metadata_json` | ❌ **Do not use.** Field exists in the data (standard-specific JSON blob) but the skill must **never** query or parse it. Use `compliance.rule.id` / `compliance.rule.title` for rule identity instead. |
| `compliance.standard.short_name` | KSPM-native: `CIS`, `DORA`, `NIST`, `DISA STIG`. **Note the full `"DISA STIG"` label — `short_name == "STIG"` matches nothing.** Prefer `contains(lower(compliance.standard.short_name), "stig")` for filtering — it tolerates version suffixes and the DISA prefix. PCI / ISO / HIPAA / GDPR appear only via CSPM/VSPM or external integrations. |
| `compliance.standard.name` | Versioned full name — e.g. `"CIS Kubernetes 1.6.0"`, `"NIST SP 800-53 Rev. 5.2.0"`, `"DISA STIG Kubernetes V2R5"` |
| `compliance.standard.url` | Reference URL for the standard |

### KSPM result + evidence fields

| Field | Values / notes |
|---|---|
| `compliance.result.status.level` | `FAILED`, `MANUAL`, `PASSED`, `NOT_RELEVANT` — **exactly four**. No ERROR/UNKNOWN. |
| `compliance.result.status.score` | Numeric: `FAILED=10.0`, `MANUAL=7.0`, `PASSED=4.0`, `NOT_RELEVANT=1.0` |
| `compliance.result.description` | Optional status-detail text (nullable) |
| `compliance.result.count.passed` / `.failed` / `.manual` | **Post-aggregation only** — counters derived in the per-rule summarize (Step 2). Not on raw events. |
| `compliance.result.object.type` | Lowercase analysis-object code: `k8scluster`, `k8snode`, `k8spod`, `k8sdeployment`, `k8sstatefulset`, `k8sreplicaset`, `k8sdaemonset`, `k8sjob`, `k8scronjob`, `k8sreplicationcontroller`. **Different field from the cross-provider `object.type`** which carries the Dynatrace entity type (`KUBERNETES_CLUSTER`, etc.). |
| `compliance.result.object.name` | Resource name (pod / deployment / cluster name) |
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

### KSPM `COMPLIANCE_SCAN_COMPLETED` fields

| Field | Notes |
|---|---|
| `scan.id` | UUID — joins the scan-completed row to all `COMPLIANCE_FINDING` rows it produced |
| `scan.time_completed` | Nanosecond timestamp of scan completion |
| `scan.result.summary_json` | JSON with pre-computed pass percentages — schema below |
| `object.id` / `object.name` / `object.type` | Cluster identifier (`KUBERNETES_CLUSTER`) |
| `dt.entity.kubernetes_cluster`, `k8s.cluster.name`, `k8s.cluster.uid` | Cluster identifiers |

### `scan.result.summary_json` schema

```json
{
  "compliancePercentage": 85,
  "standardResultSummaries": [
    {"standardCode": "CIS",  "compliancePercentage": 85},
    {"standardCode": "DORA", "compliancePercentage": 92}
  ]
}
```

`compliancePercentage` is the overall pass rate across all enabled standards;
`standardResultSummaries` breaks it down. Use this for fast UC-C0 dashboards
without a full `COMPLIANCE_FINDING` join.

### KSPM-assessed object types (Kubernetes only)

KSPM is **K8s-only today** — no AWS/Azure/GCP/host-level rules in the
DT-native pipeline. Cloud and VMware coverage flows through CSPM/VSPM.
The `compliance.result.object.type` codes are: `k8scluster`, `k8snode`,
`k8spod`, `k8sdeployment`, `k8sstatefulset`, `k8sreplicaset`, `k8sdaemonset`,
`k8sjob`, `k8scronjob`, `k8sreplicationcontroller`.

### Severity precedence + per-rule status derivation

Per-(rule, object) rows are aggregated to per-rule rows by Step 2 (see
[compliance.md](compliance.md)). Status precedence:

```
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
| `compliance.status` | Some providers populate this as a top-level string (`FAILED` / `PASSED`) instead of `compliance.result.status.level`; check both when filtering external |
| `compliance.standards` (array), `compliance.policy`, `compliance.control` | External compliance taxonomy — group/filter by these (`expand` the `compliance.standards` array). See [compliance.md § External compliance taxonomy fields](compliance.md#external-compliance-taxonomy-fields). |
| `event.provider` / `product.vendor` / `product.name` | Provider identification — scope via [all-security-events.md § Scoping to a Specific Provider](all-security-events.md#scoping-to-a-specific-provider-any-finding-type) |
| `object.*` | Affected entity (cloud resource identifier, etc.) |

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
| `dt.source_entity` | Entity ID that was scanned (PROCESS_GROUP_INSTANCE-… or HOST-…) |
| `dt.source_entity.type` | **Lowercase** — `process_group_instance` or `host`. Scan service supports only these two types. |
| `product.name` | `Runtime Vulnerability Analytics` |
| `product.vendor` | `Dynatrace` |
| `product.feature` | RVA scan mode — see table below. Populated on CLV scan events (`Code-level Vulnerability Analytics`); **null on third-party / OS scan events** — `filterOut product.feature == "Code-level Vulnerability Analytics"` keeps both null and explicitly-non-CLV rows, which is what coverage queries want. Always populated on the paired `VULNERABILITY_FINDING` events. |
| `scan.id` | Scan request UUID — links a `VULNERABILITY_SCAN` to its `VULNERABILITY_FINDING`s |
| `scan.time.started` / `scan.time.completed` | Server-side scan timestamps (nanoseconds) |
| `dt.entity.host`, `dt.entity.process_group_instance` | Identifiers for dedup and lookup-against-smartscapeNodes |

### `product.feature` values for RVA

| Value | Stack | Where populated |
|---|---|---|
| `Library Vulnerability Analytics` | `CODE_LIBRARY` | `VULNERABILITY_FINDING` only (third-party / OSS library scanning, SOFTWARE_COMPONENT SBOM). On `VULNERABILITY_SCAN` events for the same scope, `product.feature` is null. |
| `Operating System Vulnerability Analytics` | `SOFTWARE` | `VULNERABILITY_FINDING` only (OS package scanning, RPM/DEB). On `VULNERABILITY_SCAN` events for the same scope, `product.feature` is null. |
| `Code-level Vulnerability Analytics` | `CODE` | Both `VULNERABILITY_SCAN` and `VULNERABILITY_FINDING` (OneAgent IAST/Attack-detected CLV; Java 8+, .NET, Go only). |

For coverage queries against `VULNERABILITY_SCAN`:
`filter product.feature == "Code-level Vulnerability Analytics"` scopes to CLV scans;
`filterOut product.feature == "Code-level Vulnerability Analytics"` scopes to third-party / OS scans (which have null `product.feature`). See [coverage-and-dashboards.md](coverage-and-dashboards.md) for canonical patterns.

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
`dt.security.risk.level`/`score`, `dt.smartscape*`/`dt.entity*`, and no scan events. One event per
published report; **dedup by `threat.report.id`** (reports re-ingest on update). Full query patterns
and the threat-exposure correlation workflow → [threat-intelligence.md](threat-intelligence.md).

### Report identity & provenance (required)

| Field | Notes |
|---|---|
| `threat.report.id` | Vendor-assigned report ID — **dedup key** (stable across revisions) |
| `threat.report.name` | Report title (e.g. `CSA-260753 …`, `IMMEDIATE THREAT: …`) |
| `threat.report.description` | Summary / abstract (≤2 KB) |
| `threat.report.time.created` / `.updated` | `timestamp` type (nullable) — use `coalesce(toTimestamp(…), timestamp)` |
| `threat.report.author` | Publishing author / team (optional) |
| `threat.report.references.urls` / `.tags` | Report URLs / free-form tags (optional arrays) |

### Adversary context (recommended)

| Field | Notes |
|---|---|
| `threat.actor.names` | Attributed threat-actor names/aliases (array) |
| `threat.target.countries.names` / `.iso_codes` | Targeted countries (full names / ISO 3166-1 alpha-2 — use `.iso_codes` for maps) |
| `threat.target.industries` | Targeted industry verticals (**plural** — `threat.target.industry` singular does not exist) |
| `threat.malware.families` | Malware family names (array) |
| `threat.attack.{tactic,technique,subtechnique}.{ids,names}`, `threat.attack.version` | MITRE ATT&CK of the **reported campaign** (separate arrays). Membership via `in(value, array)`. This is intel about threats in the wild — **not** ATT&CK observed on your entities (that's `detections.md`). |

### Observables / IOCs (optional)

| Field | Notes |
|---|---|
| `threat.observables.ips` | IOC IPv4/IPv6 (`ipAddress[]`) |
| `threat.observables.domains` / `.urls` / `.emails` | Domain / URL / email IOCs |
| `threat.observables.cves` | Referenced CVE IDs |
| `threat.observables.hashes.md5` / `.sha1` / `.sha256` | File-hash IOCs |

### Vendor extensions (additive — no SD counterpart)

| Field | Notes |
|---|---|
| `alienvault.pulse.public` / `alienvault.pulse.tlp` | AlienVault OTX: public flag / TLP (`WHITE` \| `GREEN`) |
| `crowdstrike.report.slug` / `.type` / `.type.id` / `.type.name` | CrowdStrike: report slug + type (`Notice` \| `Tipper` \| `Periodic Report` \| `Intelligence Report` \| `Recon+`) |

---

## Finding ID Format Cheatsheet

`finding.id` is provider-specific — match exactly when drilling down:

| Provider | Format example |
|---|---|
| Dynatrace | UUID — `a9bc7599-2b1b-45b7-8f6c-6ab57ad4c343` |
| AutomationEngine | 64-char hex hash |
| External providers | Provider-specific format — e.g. a cloud resource ARN or a provider-native finding ID; consult the sample data / discover per provider |