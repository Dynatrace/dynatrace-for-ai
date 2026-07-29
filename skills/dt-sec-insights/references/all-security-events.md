# All Security Events (Cross-Provider Summary)

Unified view across Dynatrace-native **and** external security findings —
vulnerabilities, detections, compliance findings, and scan events from
Dynatrace RVA / SPM / RAP and any external security tool ingested via OpenPipeline.

> **Use this when the question spans providers.** For Dynatrace-native only, or advanced use cases per type,
> use [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md), [compliance.md](compliance.md),
> or [detections.md](detections.md).

## Contents

- [When to Use](#when-to-use)
- [Providers & Products](#providers--products)
- [Semantic-Dictionary Fields](#semantic-dictionary-fields)
- [Canonical Cross-Provider Query](#canonical-cross-provider-query)
- [Double-Counting Guard](#double-counting-guard)
- [Broad-Question Query Decomposition](#broad-question-query-decomposition)
- [Time Window Guidance](#time-window-guidance-for-cross-provider-queries)
- [Security Posture Overview](#security-posture-overview--products-and-volumes-uc-g8) (UC-G8)
- [Recent Findings Stream](#recent-cross-provider-findings-stream-uc-g2) (UC-G2)
- [Findings for a Specific Entity](#security-findings-for-a-specific-entity-uc-g3--uc-g4) (UC-G3/G4)
- [Common Workflows](#common-workflows)
- [Event Type Reference](#event-type-reference)
- [Best Practices](#best-practices)

---

## When to Use

Use this pattern when a user asks:

- "What security findings do we have across all tools?"
- "Which providers are reporting detections this week?"
- "How many critical findings across Dynatrace and our external security tools?"
- "What integrations are sending us security data?"

For single-provider / single-event-type questions, use the more specific
references — they give tighter queries and richer fields.

---

## Providers & Products

Dynatrace-native sources use these provenance fields:

| `event.provider` | `product.name` | Notes |
|---|---|---|
| `Dynatrace` | (varies) | Dynatrace-native (RVA, SPM, internal). Filter native vulnerability/compliance via `product.vendor == "Dynatrace"`. |
| `OneAgent` | `Runtime Application Protection` | Dynatrace RAP — runtime attack detections. Both `event.provider == "OneAgent"` and `product.name == "Runtime Application Protection"` are populated; either filter works (skill prefers the latter as canonical). Passes the cross-provider double-counting guard (see Canonical Cross-Provider Query below). |
| `Dynatrace Automated Detections` | `Automated Detections` | Dynatrace built-in / custom detection rules — emits both `DETECTION_FINDING` and `DETECTION_EXECUTION_SUMMARY` |

External findings arrive from any ingested security tool (cloud-security posture/threat
services, SAST/SCA scanners, SIEM/SOAR, WAF/edge, etc.). They are intentionally **not**
enumerated here — the skill stays provider-neutral. Always discover what's actually active
in the tenant rather than assuming a provider name. This discovery enumerates **external +
DT-detection** providers; the double-counting guard keeps it off the high-cardinality DT
RVA/KSPM snapshot streams (whose presence is confirmed separately via the constrained-window
queries — see [Broad-Question Query Decomposition](#broad-question-query-decomposition)):

```dql
fetch security.events, from: -24h
| filter product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"
| summarize count = count(), by: {event.provider, product.name, product.vendor, event.type}
| sort count desc
```

> **Window cost note:** even with the double-counting guard, the external
> `VULNERABILITY_FINDING` streams are high-volume — a `-7d` discovery scan can approach or
> exceed the 500 GB scan limit (≈9.5 GB at `-24h` vs. 500 GB+ at `-7d` on a busy tenant).
> `-24h` is the safe **default** when no window is specified; active integrations emit well
> within a day. **Honor an explicitly requested window** (e.g. "in the last 7 days" → `-7d`) —
> just expect the larger scan and add `scanLimitGBytes` if it trips the limit.

### Scoping to a Specific Provider (any finding type)

This pattern is shared by detections, external vulnerabilities, and external compliance —
the per-domain references link here rather than restating it.

**Step 1 — discover the exact provider strings.** Run the discovery query above first. Provider identity may live in `event.provider`, `product.vendor`, or both — and a single integration can appear under two paths (e.g. direct ingest **and** via AWS Security Hub).

**Step 2 — scope with exact match once strings are confirmed.** Prefer exact equality over fuzzy `contains` — it avoids false positives from providers whose names share a substring with the target:

```dql-snippet
// Exact match (preferred for known provider — substitute strings from discovery)
| filter event.provider == "<ExactProviderString>"
      OR product.name == "<ExactProductString>"
```

If the same integration appears via multiple paths (e.g. `event.provider == "Amazon GuardDuty"` for the direct integration and `event.provider == "AWS Security Hub" AND product.name == "GuardDuty"` for the Security Hub relay), combine both exact conditions with `OR`.

**During discovery only — fuzzy match.** Use `contains(lower(...))` only when the exact string is not yet known:

```dql-snippet
| filter contains(lower(event.provider), "<provider>")
      OR contains(lower(product.vendor), "<provider>")
```

- **All external** (exclude Dynatrace-native): `filterOut event.provider=="Dynatrace" or product.vendor=="Dynatrace"`.
- For **hyperscaler-specific** provider field handling (cloud resource IDs, ARNs, account /
  subscription / project scoping), use the dedicated AWS / Azure / GCP skills — this skill
  keys off the generic `object.*` / `dt.security.*` namespaces.

---

## Semantic-Dictionary Fields

Cross-provider queries rely on the normalized semantic-dictionary fields that every
provider populates. These are the fields to filter, summarize, and project on
when mixing providers:

| Field | Description |
|---|---|
| `event.id` | Unique event identifier |
| `event.provider` | Source integration |
| `event.type` | Finding / scan event type |
| `finding.id` | Unique finding identifier |
| `finding.title` | Human-readable finding title |
| `finding.type` | Finding type |
| `finding.time.created` | When the finding was created by the source |
| `dt.security.risk.level` | Normalized risk: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `NONE`, `NOT_AVAILABLE` |
| `object.id` | Affected object ID |
| `object.name` | Affected object display name |
| `object.type` | Affected object type |
| `product.name`, `product.vendor` | Generating product/vendor |

**Mandatory for all cross-provider counts and summaries.** These guards filter out non-conformant rows that the Threats & Exploits app UI silently ignores. Without them, DQL counts include malformed provider/product/entity rows, making DQL totals exceed app totals. Never drop these guards on cross-provider count, percentage, or summary queries:

```dql-snippet
| filter isNotNull(event.id)
     AND isNotNull(event.provider)
     AND isNotNull(finding.type)
     AND isNotNull(finding.id)
     AND isNotNull(finding.time.created)
     AND isNotNull(finding.title)
     AND isNotNull(dt.security.risk.level)
     AND isNotNull(object.id)
     AND isNotNull(object.type)
```

---

## Canonical Cross-Provider Query

The canonical cross-provider summary template — combines external findings and Dynatrace `DETECTION_FINDING` rows under the SD contract:

```dql
fetch security.events, from: -24h
| filter product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
// All three finding types are required — dropping any one omits an entire category:
// VULNERABILITY_FINDING covers external scanners; DETECTION_FINDING covers RAP + external;
// COMPLIANCE_FINDING covers KSPM + external posture tools.
// Require semantic-dictionary-compliant rows
| filter isNotNull(event.id)
     AND isNotNull(event.provider)
     AND isNotNull(finding.type)
     AND isNotNull(finding.id)
     AND isNotNull(finding.time.created)
     AND isNotNull(finding.title)
     AND isNotNull(dt.security.risk.level)
     AND isNotNull(object.id)
     AND isNotNull(object.type)
// Compliance: only failed (skip PASSED, MANUAL, NOT_RELEVANT)
| filter (not exists(compliance.result.status.level)
     OR compliance.result.status.level == "FAILED"
     OR compliance.status == "FAILED")
| summarize {
    finding.count = count(),
    affected_object.types = arrayRemoveNulls(collectDistinct(object.type)),
    affected_smartscape.node.ids = arrayRemoveNulls(collectDistinct(dt.smartscape_source.id)),
    finding.ids = arrayRemoveNulls(collectDistinct(finding.id)),
    finding.titles = arrayRemoveNulls(collectDistinct(finding.title)),
    finding.times = collectDistinct(finding.time.created),
    affected_object.ids = arrayRemoveNulls(collectDistinct(object.id)),
    affected_object.names = arrayRemoveNulls(collectDistinct(object.name)),
    vulnerable_components = arrayConcat(
      arrayRemoveNulls(collectDistinct(software_component.name)),
      arrayRemoveNulls(collectDistinct(component.name))
    )
  }, by: {event.provider, product.name, event.type, dt.security.risk.level}
| sort finding.count desc
| limit 100
```

### Mandatory guards for any cross-provider count or summary

The canonical query above includes four structural guards. **All four must be applied together** for cross-provider count/percentage/summary questions — dropping any one silently corrupts the result. Treat them as mandatory boilerplate, not optional optimization:

1. **SD-isNotNull guard** — `isNotNull(event.id) AND isNotNull(event.provider) AND isNotNull(finding.type) AND ...` drops rows that don't satisfy the Semantic Dictionary contract. Without it, the Threats & Exploits app filters them out but DQL counts them, so DQL totals exceed app totals. The short form `filterOut isNull(event.type) or isNull(object.id) or isNull(finding.id)` catches most malformed rows; the full 9-field guard in the canonical query above is authoritative.
2. **Cross-finding-type union** — `filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})` restricts to the three normalized finding streams. All three are required — dropping any one omits an entire category. Do not narrow to a single event type for a cross-provider summary.
3. **Compliance-FAILED guard** — `filter (not exists(compliance.result.status.level) or compliance.result.status.level == "FAILED" or compliance.status == "FAILED")` skips PASSED / MANUAL / NOT_RELEVANT compliance rows.
4. **Double-counting guard** — `filter product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"` (see § below).

**Use `summarize` — never raw row projection past `limit 50`.** The cross-provider stream is high-volume; raw `| fields ... | sort timestamp desc | limit 50` will pick rows from whichever provider happens to emit first and silently truncate the breadth the question asked for. The canonical pattern is `fetch → filter → summarize → sort → limit`.

If any guard is intentionally dropped (e.g. the UC-G2 raw stream below), state the reason and the consequence in your final answer.

---

## Double-Counting Guard

When mixing providers, Dynatrace-native **vulnerability** and **compliance**
findings should be read via the dedicated tools (see
[vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md), [compliance.md](compliance.md)) which
correctly dedup state reports and scans. In a cross-provider summary, **exclude
Dynatrace-generated vulnerabilities and compliance findings** to avoid counting
each state-report row and every scan attempt:

```dql-snippet
| filter product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"
```

This allows:

- **Dynatrace detections** (one-shot `DETECTION_FINDING` — safe to include)
- **All external findings** (not from Dynatrace at all)

and excludes:

- Dynatrace vulnerability state reports (inflate counts massively)
- Dynatrace compliance findings (per-(rule, object, scan) rows)

To see Dynatrace-native vulnerability / compliance counts alongside external
findings, compute them separately via [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md)
and [compliance.md](compliance.md) and merge the results at the presentation
layer. For broad/overview questions, the
[Broad-Question Query Decomposition](#broad-question-query-decomposition) below
operationalizes this into a concrete 3-query plan.

---

## Broad-Question Query Decomposition

A **broad question** spans all finding categories **including Dynatrace-native** rather
than one stream — e.g. "which security products are integrated?", "give me a security
posture overview", "what security data do we have across everything?", or any cross-category
count. **Default these to DT-inclusive** — they *must* query DT vulnerabilities (RVA) and
compliance (KSPM), not just external findings. Do **not** answer them with a single wide
`fetch security.events` over every event type: that scans the high-cardinality DT RVA
state-report stream (emitted every ~15 min per `(vulnerability, entity)` pair) and the DT
KSPM compliance stream, which is expensive even at `24h` **and** double-counts snapshot rows.

> **Not this:** the single external-only
> [Which external integrations are active](#which-external-integrations-are-active-and-volume)
> query applies **only** when the user explicitly scopes to external / third-party tools — e.g.
> "which **external** integrations / tools are sending us data?". A bare "which security products
> are integrated?" is **DT-inclusive by default** → use the decomposition (which queries RVA and
> KSPM). When in doubt, decompose.

Instead, **decompose into three independent queries, each on its own window, and
merge at the presentation layer:**

| Stream | Covers | Query | Window |
|---|---|---|---|
| **A — External + DT detections** | all external providers (vulnerability / detection / compliance findings) + DT RAP & Automated Detections | [Canonical Cross-Provider Query](#canonical-cross-provider-query) (double-counting + SD guards) | `24h` (widen as the question needs) |
| **B — DT vulnerabilities (RVA)** | Dynatrace-native CVEs / runtime vulnerabilities | canonical RVA pipeline → [vulnerabilities-dynatrace.md § DT RVA: Full Snapshot Queries](vulnerabilities-dynatrace.md) | `30m` fixed |
| **C — DT compliance (KSPM)** | Dynatrace-native CIS / DORA / NIST / STIG | canonical SPM pipeline → [compliance.md § DT SPM: Base Pattern](compliance.md) | `1h` fixed |

Stream A's double-counting guard
(`product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"`) deliberately
excludes DT RVA and DT KSPM — they are **absent from Stream A by design** and must
be picked up by Streams B and C. A `30m` RVA snapshot and a `1h` KSPM snapshot report
each product's **current finding count** without scanning history.

> **Empty snapshot ≠ not integrated.** A `0` result from a 30m/1h snapshot means *no
> recent findings* — not that the product is absent. Before reporting RVA or KSPM as
> "not integrated", confirm presence with a wider low-cardinality probe over `24h` — RVA
> `VULNERABILITY_STATE_REPORT_EVENT` filtered to `event.provider=="Dynatrace"`, KSPM
> `COMPLIANCE_SCAN_COMPLETED` filtered to `product.vendor=="Dynatrace"` (RVA keys off
> `event.provider`, SPM off `product.vendor` — see [data-model.md § Provider Taxonomy](data-model.md)).
> These marker streams are far cheaper than the full finding streams, so a `24h` presence check
> stays inexpensive.

**Prohibitions:**

- Never answer a broad question with a single unguarded `fetch security.events`
  over all event types, or a `from: -7d` full-table scan to "list every provider".
- Never widen Streams B/C to `24h` to fold them into Stream A — that reintroduces
  the cost blowup and double-counting the guard exists to prevent.

To present the merged result, label each stream's rows by source (external provider
name / `Dynatrace RVA` / `Dynatrace KSPM`) and concatenate — the three streams are
disjoint by construction.

> **Presentation order — lead with compliance (CIS).** When merging the streams for a
> broad question, present **Stream C's KSPM compliance failed-rule count as the headline
> summary**, with **CIS first** (CIS is the mandatory K8s baseline; sort it to the top via
> [compliance.md § CIS-Primary Standard Summary](compliance.md)). List the other KSPM
> standards (DORA / NIST / DISA STIG) immediately after as *additional* failed rules that
> may overlap with CIS — never sum failed counts across standards. Then show Stream B (RVA
> vulnerabilities) and Stream A (external + DT detections) beneath. This is a **presentation**
> choice only — the streams stay disjoint by construction (a correctness property); leading
> with compliance does not merge or re-weight the underlying counts.

**Entity-scoped broad questions follow the same decomposition.** If the user asks
for "security findings" on a specific entity (host, K8s node, workload, cluster,
service), do not query only RVA/SPM. Run Stream A scoped to the entity with the
wide entity OR-chain (`dt.smartscape_source.id`, `dt.entity.*`, `object.*`,
relevant `k8s.*`) and merge it with
Stream B (RVA `affected_entity.*` / `related_entities.*`) and Stream C (SPM object
scope). A 0-row Stream A result means **no external findings matched that entity**
for the stated window — it is still part of the answer. Apply the same CIS-led
presentation order above.

When the user explicitly asks about *compliance / misconfigurations* on the entity (rather
than all findings), render Stream C as the **Entity Security-Tab View** — three tables
mirroring the entity Security tab (CIS default, failed-only):
**Table 1** Dynatrace CIS failed rules → **Table 2** other DT standards (DORA/NIST/STIG,
overlap caveat) → **Table 3** the external `COMPLIANCE_FINDING` subset of Stream A (externally
ingested misconfigurations) scoped to the entity. See
[compliance.md § Entity Security-Tab View](compliance.md) (broad posture/count questions
instead use § CIS-Primary Standard Summary).

---

## Time Window Guidance for Cross-Provider Queries

The canonical cross-provider pattern in this file **always** includes the double-counting guard:

```dql-snippet
| filter product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"
```

This guard excludes DT RVA vulnerability state reports and DT KSPM compliance findings — the high-cardinality snapshot streams that carry strict 30m / 1h window requirements. Because those streams are already filtered out, **cross-provider queries are not snapshot-constrained**.

Default windows by query class:

| Query class | Default window | Notes |
|---|---|---|
| Cross-provider summary (count/breakdown/aggregation) | **`24h`** | Summaries aggregate over time; start broad to avoid undercounting |
| Cross-provider retrieval (raw finding listing) | `2h` first attempt | Widen to `24h` only if zero rows returned |

`from:now()-24h` is the reliable default for summary questions. Starting at `2h` for retrieval queries limits data volume on first attempt; widening is safe since the double-counting guard is already in place.

For the domain-specific snapshot constraints (RVA 30m fixed window, SPM 1h scan-completion join, detection stream guidance), see the specialist references:
- [vulnerabilities-dynatrace.md § Snapshot vs. History](vulnerabilities-dynatrace.md) — RVA 30m fixed window
- [compliance.md § Snapshot vs. History](compliance.md) — SPM 1h fixed window
- [detections.md](detections.md) — detection streams have no snapshot constraint; use the window that covers the attack history the question requires

**Matching a UI app's view.** If the user asks "what does the Threats & Exploits / SPM / Vulnerabilities app show right now?", apply the app's default time-picker value. App defaults are defined in [SKILL.md § Default Time Ranges](../SKILL.md#default-time-ranges-in-the-dynatrace-apps).

---

## Security Posture Overview — Products and Volumes (UC-G8)

A posture overview ("which products are reporting findings?", "which products cover entity X?")
is a **broad question** — resolve it with the
[Broad-Question Query Decomposition](#broad-question-query-decomposition): run the three streams
separately and merge. Do **not** run a single `fetch security.events` over all event types —
that double-counts the DT RVA/KSPM snapshot streams and scans them needlessly.

**Stream A — external + DT-detection products and volumes** (guarded, `24h`):

```dql
fetch security.events, from:now()-24h
| filterOut isNull(event.type) or isNull(object.id) or isNull(finding.id)
| filter product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"
| summarize {
    Findings=countIf(in(event.type,{"VULNERABILITY_FINDING","DETECTION_FINDING","COMPLIANCE_FINDING"})),
    Scans=countIf(in(event.type,{"VULNERABILITY_SCAN","COMPLIANCE_SCAN"}))
  }, by:{Product=product.name, Provider=event.provider}
| sort Findings desc
```

**Stream B — DT RVA vulnerability count** (`30m` fixed): run the canonical RVA pipeline
([vulnerabilities-dynatrace.md § DT RVA: Full Snapshot Queries](vulnerabilities-dynatrace.md)) and take its
vulnerability count.

**Stream C — DT KSPM compliance count** (`1h` fixed): run the canonical SPM pipeline
([compliance.md § DT SPM: Base Pattern](compliance.md)) and take its failed-control count.

Merge: present Stream A's per-product rows, then append `Dynatrace RVA` (Stream B count) and
`Dynatrace KSPM` (Stream C count) as their own product rows. The double-counting guard keeps the
three streams disjoint, so the merged list has exactly one row per integrated product.

## Recent Cross-Provider Findings Stream (UC-G2)

Latest 100 ingested findings across all providers. For genuinely "new" findings use
`toTimestamp(finding.time.created) > now() - 24h`. This approach works for all
`*_FINDING` event types.

> **Always include the double-counting guard, even on this raw stream.** Earlier
> versions of this section dropped the `product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"` guard with the rationale "we already filter to `*_FINDING`
> event types, so state-report duplication isn't possible." That's true for the
> three event types listed, but the moment a downstream question becomes "give me
> a summary of what arrived" / "by provider" / "by risk level", the model adds a
> `summarize count()` to this stream and Dynatrace-native vulnerability and
> compliance findings *do* get double-counted (per-(rule, object, scan) rows on
> SPM, per-(vuln, entity) on RVA `VULNERABILITY_FINDING`). Keep the guard in by
> default — it's a one-line filter on an already-filtered stream, and it makes
> the snippet copy-paste-safe for the common hybrid case where a user asks for a
> "recent" feed but expects a digested summary.

```dql
fetch security.events, from:now()-24h
| filterOut isNull(event.type) or isNull(object.id) or isNull(finding.id)
| filter in(event.type,{"VULNERABILITY_FINDING","DETECTION_FINDING","COMPLIANCE_FINDING"})
| filter product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"
| sort timestamp desc
| limit 100
```

To keep results lean while preserving entity context, add a `fieldsKeep` projection (see [common-patterns.md § 17](common-patterns.md)):

```dql
fetch security.events, from:now()-24h
| filterOut isNull(event.type) or isNull(object.id) or isNull(finding.id)
| filter in(event.type,{"VULNERABILITY_FINDING","DETECTION_FINDING","COMPLIANCE_FINDING"})
| filter product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"
| sort timestamp desc
| limit 100
| fieldsKeep timestamp, "dt.smartscape*", "dt.entity*", "dt.source*",
            event.type, event.provider, product.name,
            finding.id, finding.title, dt.security.risk.level,
            object.id, object.name, object.type
```

For new findings only in a specific window:

```dql
fetch security.events, from:now()-24h
| filterOut isNull(event.type) or isNull(object.id) or isNull(finding.id)
| filter in(event.type,{"VULNERABILITY_FINDING","DETECTION_FINDING","COMPLIANCE_FINDING"})
| filter toTimestamp(finding.time.created) > now() - 24h
| summarize findings=count(), by:{event.type, event.provider, dt.security.risk.level}
| sort findings desc
```

> **DT RVA exception:** for newly-OPEN Dynatrace vulnerabilities use
> `toTimestamp(vulnerability.resolution.change_date) > now() - 24h` after the
> canonical RVA pipeline (see [vulnerabilities-dynatrace.md](vulnerabilities-dynatrace.md)).

---

## Security Findings for a Specific Entity (UC-G3 / UC-G4)

For a named entity, find all security findings across types. Use the entity OR-chain
from [common-patterns.md § 5](common-patterns.md#5-wide-entity-scoping-or-chain)
to match the entity across the rich scoping-field set.

**Direct findings** (entity is the `object.id`/`object.name`):

```dql
fetch security.events, from:now()-24h
| filterOut isNull(event.type) or isNull(object.id) or isNull(finding.id)
| filter in(event.type,{"VULNERABILITY_FINDING","DETECTION_FINDING","COMPLIANCE_FINDING"})
| filter product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"
| filter object.name == "my-service" OR object.id == "PROCESS_GROUP-1234567890ABCDEF"
| summarize {
    findings=count(),
    Critical=countIf(dt.security.risk.level=="CRITICAL"),
    High=countIf(dt.security.risk.level=="HIGH")
  }, by:{event.type, event.provider, product.name}
| sort Critical desc
```

**Including indirect/related entities (UC-G4):** for DT RVA vulnerabilities,
run the canonical pipeline and then filter on `related_entities.names` or
`related_entities.ids` after Step 3 to capture findings where the entity is a
related (not directly affected) entity:

```dql-snippet
// After Steps 1–3 of the RVA pipeline:
| filter in("my-service", related_entities.names)
      OR in("PROCESS_GROUP-1234...", related_entities.ids)
```

**Note:** UC-G5 (problem-scoped security) first requires extracting affected entity
IDs from the problem via a separate skill (`dt-obs-problems`), then passing those
IDs into the entity OR-chain above. This is a multi-skill workflow — the security
query itself is identical to UC-G4.

---

## Common Workflows

### What's hitting us, by provider and risk

```dql
fetch security.events, from: -24h
| filterOut isNull(event.type) or isNull(object.id) or isNull(finding.id)
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"
| filter (not exists(compliance.result.status.level)
     OR compliance.result.status.level == "FAILED"
     OR compliance.status == "FAILED")
| summarize findings = count(),
            by: {event.provider, event.type, dt.security.risk.level}
| sort findings desc
```

### Cross-provider critical findings summary (canonical recipe)

All four mandatory guards applied; all three finding types included; all four `by:` keys preserved. Use this as the reference template for any "critical findings across providers" question:

```dql
fetch security.events, from: -24h
// Double-counting guard: exclude DT vulnerability/compliance state reports; keep DT detections
| filter product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"
// All three finding types required — do not drop any
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
// SD-isNotNull guard: mandatory — prevents malformed rows from inflating counts
| filter isNotNull(event.id) AND isNotNull(event.provider) AND isNotNull(finding.type)
     AND isNotNull(finding.id) AND isNotNull(finding.time.created) AND isNotNull(finding.title)
     AND isNotNull(dt.security.risk.level) AND isNotNull(object.id) AND isNotNull(object.type)
// Compliance guard: count only failed controls
| filter (not exists(compliance.result.status.level)
     OR compliance.result.status.level == "FAILED"
     OR compliance.status == "FAILED")
| filter dt.security.risk.level == "CRITICAL"
// Preserve all four by: keys — do not drop any
| summarize {
    findings.count = count(),
    finding.titles = arraySlice(collectDistinct(finding.title), from: 0, to: 5),
    affected_object.ids = arrayRemoveNulls(collectDistinct(object.id)),
    affected_object.names = arraySlice(collectDistinct(object.name), from: 0, to: 10)
  }, by: {event.provider, product.name, event.type, dt.security.risk.level}
| sort findings.count desc
| limit 50
```

### Which external integrations are active (and volume)

Enumerate the **external** security tools sending data, with event volume and first/last-seen.
This is the integration-health question — distinct from a DT-inclusive posture overview (for
that, use the [Broad-Question Query Decomposition](#broad-question-query-decomposition)). Exclude
Dynatrace-native sources; the `FirstSeen`/`LastSeen` grain makes a multi-day window meaningful,
so `-7d` is the natural default here (honor an explicitly requested window):

```dql
fetch security.events, from:now()-7d
| filter isNotNull(event.provider) and event.provider != "Dynatrace"
| summarize {
    Events = count(),
    EventTypes = collectDistinct(event.type),
    Findings = countIf(in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})),
    Scans = countIf(in(event.type, {"VULNERABILITY_SCAN", "COMPLIANCE_SCAN"})),
    FirstSeen = takeMin(timestamp),
    LastSeen = takeMax(timestamp)
  }, by: {event.provider, product.vendor}
| sort Events desc
```

> **Scan-cost caveat:** external `VULNERABILITY_FINDING` volume is high (millions of rows on a
> busy tenant) — a `-7d` scan here can approach the 500 GB limit. If you only need *current*
> activity rather than 7-day first/last-seen, narrow to `-24h`; otherwise add `scanLimitGBytes`
> to the `fetch`.

### GuardDuty risk and resource summary (named-provider exact-match example)

GuardDuty data may arrive via two paths in the same tenant — match both. The exact provider strings below were verified via the discovery query (`event.provider == "Amazon GuardDuty"` for the direct integration, `event.provider == "AWS Security Hub" AND product.name == "GuardDuty"` for the Security Hub relay). **Run the discovery query on your tenant first to confirm which paths are active.**

```dql
fetch security.events, from: -24h
// Exact-match both GuardDuty ingestion paths
| filter (event.provider == "Amazon GuardDuty")
      OR (event.provider == "AWS Security Hub" AND product.name == "GuardDuty")
| filter event.type == "DETECTION_FINDING"
// SD-isNotNull guard — mandatory
| filter isNotNull(event.id) AND isNotNull(event.provider) AND isNotNull(finding.type)
     AND isNotNull(finding.id) AND isNotNull(finding.time.created) AND isNotNull(finding.title)
     AND isNotNull(dt.security.risk.level) AND isNotNull(object.id) AND isNotNull(object.type)
// Preserve identity: object.type, object.id, object.name, and event.provider distinguish resources
| summarize {
    findings.count = count(),
    finding.titles = collectDistinct(finding.title),
    affected_object.ids = collectDistinct(object.id),
    affected_object.names = collectDistinct(object.name)
  }, by: {event.provider, product.name, dt.security.risk.level, object.type}
| sort findings.count desc
```

### Findings on a specific cloud resource

Use the entity OR-chain from
[common-patterns.md § 5](common-patterns.md).

### Look up a finding by ID or title across providers

```dql-template
fetch security.events, from: -24h
| filter in(event.type, {"VULNERABILITY_FINDING", "DETECTION_FINDING", "COMPLIANCE_FINDING"})
| filter finding.id == "<FINDING_ID>"
     or scan.id == "<SCAN_ID>"
     or contains(finding.title, "<TITLE_SUBSTRING>")
     or contains(event.description, "<DESCRIPTION_SUBSTRING>")
| sort timestamp desc
| limit 5
| fieldsKeep timestamp, "dt.smartscape*", "dt.entity*", "dt.source*",
            event.type, event.provider, finding.id, finding.title,
            dt.security.risk.level, object.id, object.name, object.type,
            event.description
```

---

## Event Type Reference

| `event.type` | Families that emit it |
|---|---|
| `VULNERABILITY_STATE_REPORT_EVENT` | Dynatrace RVA |
| `VULNERABILITY_STATUS_CHANGE_EVENT` | Dynatrace RVA |
| `VULNERABILITY_TRACKING_LINK_CHANGE_EVENT` | Dynatrace RVA |
| `VULNERABILITY_FINDING` | External SCA / SAST / image scanners (ingested) |
| `VULNERABILITY_SCAN` | Dynatrace RVA + external scan coverage events |
| `DETECTION_FINDING` | Dynatrace RAP + Automated Detections + external detection sources (ingested) |
| `COMPLIANCE_FINDING` | Dynatrace SPM + external compliance / posture tools (ingested) |
| `COMPLIANCE_SCAN` | External compliance scan coverage events |
| `COMPLIANCE_SCAN_COMPLETED` | Dynatrace SPM scan completion markers |
| `VULNERABILITY_COVERAGE_REPORT_EVENT` | **Deprecated** — use `VULNERABILITY_SCAN` |
| `THREAT_REPORT` | External threat-intelligence platforms (AlienVault OTX, CrowdStrike Falcon Intelligence). **Threat intelligence, not a finding** — **excluded from every cross-provider query on this page** (no `finding.*` / `object.*` / `dt.security.risk.level`, not part of the double-counting guard or the 3-stream decomposition). Query separately via [threat-intelligence.md](threat-intelligence.md). |

---

## Best Practices

1. **Lead with the semantic-dictionary filter** — cross-provider queries should
   only consider rows that populate the normalized fields.
2. **Always apply the double-counting guard** —
   `product.vendor != "Dynatrace" OR event.type == "DETECTION_FINDING"`. This is
   the canonical filter for cross-provider summaries — drops Dynatrace-native vulnerabilities and compliance (covered by the RVA and SPM snapshot patterns) while keeping Dynatrace detections.
3. **Use the correct default window for the query class.** For cross-provider
   summary/aggregation queries, start at `24h` (summaries aggregate over time; a
   narrow window silently undercounts). For retrieval queries (listing raw findings,
   "show latest detections"), start at `2h` and widen to `24h` only if zero rows
   are returned. See [common-patterns.md § 7](common-patterns.md) for the full table.
4. **Decompose broad questions; compute DT-native vulnerability/compliance separately** —
   for posture overviews, "which products are integrated", and other cross-category questions,
   follow the [Broad-Question Query Decomposition](#broad-question-query-decomposition): Stream A
   (external + DT detections, `24h`, guarded), Stream B (DT RVA, `30m`), Stream C (DT KSPM, `1h`),
   merged at reporting. Never a single wide `fetch security.events` over all event types.
5. **Use `dt.security.risk.level` for cross-provider risk** — it's the normalized
   field. Provider-specific severity fields (`vulnerability.risk.level`,
   `compliance.rule.severity.level`) exist, but only within their own event-type
   family.
