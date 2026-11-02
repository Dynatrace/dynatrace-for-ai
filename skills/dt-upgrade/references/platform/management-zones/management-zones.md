# Management Zones

<!-- Jira: none -->

**Gen3 replacement**: Segments (filtering); IAM policies or dedicated Grail buckets (access control)

**Phase 2 required**: no

Management Zones have no 1:1 replacement, so this reference does not translate them. **Its deliverable is a written migration plan the customer executes** — it recovers each zone's *intent*, works out what would reproduce it on gen3, and writes that up as a reviewable plan.

Use it to:

- rank the customer's zones by usage and sort them by whether their filter logic has a Grail equivalent,
- group zones that share a discriminator, and find where an existing Segment or zone already covers the need,
- establish whether the discriminating field or tag is actually present on the data,
- decide, with the customer, which gen3 primitive replaces each function of a zone,
- hand over a dependency-ordered migration plan with a decommission path.

**This reference plans; it does not migrate.** Every command in it is read-only. It **never creates, edits, or deletes a Segment, bucket, policy, or zone**, and it never applies a change to the environment — the output is a document, and the customer decides what to act on and how to deploy it. There is deliberately no bulk-convert path: several of the decisions are organizational and belong to the customer, and a zone that is silently mis-ported breaks the visibility or access someone depends on.

## Contents

- [Reference map](#reference-map) — which file owns which part of the migration
- [What changes](#what-changes)
- [Prerequisites](#prerequisites)
- [Instructions](#instructions) — Stages 1–8
- [Customer actions](#customer-actions)
- [Examples](#examples)
- [Outcome](#outcome) — the per-zone disposition table this workflow produces
- [Validation](#validation)
- [Documentation](#documentation)

## Reference map

Load these companion references as needed during migration:

| File | When to use |
| --- | --- |
| [evaluate-and-classify.md](evaluate-and-classify.md) | Stage 1 & 8 — rank zones by usage, fetch configs, sort each into one of the four Grail-equivalence categories; tracking query for Stage 8 decommissioning |
| [mz-classification.md](mz-classification.md) | Stage 1 — classify *what a zone is for* against the 7-dimension discriminator taxonomy, and set migration order |
| [mz-export-schema.md](mz-export-schema.md) | Read a `builtin:management-zones` export — rule types, condition keys, tag formats |
| [analyze-exports.md](analyze-exports.md) | Offline script to parse exports and cross-reference auto-tagging rules against MZ conditions |
| [autotagging.md](../autotagging/autotagging.md) | Stage 4 — migrate the auto-tagging rules that MZ conditions depend on to source-side primary tags |
| [regex-to-dpl.md](../autotagging/regex-to-dpl.md) | Stage 4 — rewrite a classic tag value-extraction rule (regex or `{Source:Attribute}` placeholder) as DPL |
| [iam-2nd-gen-roles.md](../iam-2nd-gen-roles/iam-2nd-gen-roles.md) | Stage 5 — the access-control half: 2nd gen roles → Gen3 default policies |
| [mz-permission-scopes.md](../iam-2nd-gen-roles/mz-permission-scopes.md) | Stage 1 & 5 — which zones are actually referenced by a permission grant, on which tenant, through which groups |
| [auto-tagging-field-mapping.md](../entity-queries/auto-tagging-field-mapping.md) | Stage 3 — MZ/auto-tagging attribute keys → Grail mass-data fields and Smartscape attributes |
| [mass-data-filtering-strategy.md](../entity-queries/mass-data-filtering-strategy.md) | Stage 3 — resolving tag-based filters onto mass data, and the Smartscape-side check for ME zones |
| [entity-queries.md](../entity-queries/entity-queries.md) | Stage 3 & 5 — classic entity queries → Smartscape, with [type-mappings.md](../entity-queries/type-mappings.md) and [relationship-mappings.md](../entity-queries/relationship-mappings.md) |
| [cloud-telemetry-enrichment.md](../../edge-data-platform/cloud-telemetry-enrichment/cloud-telemetry-enrichment.md) | Stage 4 — central ingest enrichment and primary tags |

**The two classifications are orthogonal and both are needed.** `evaluate-and-classify.md` answers *can this zone's filter logic be reproduced on Grail?* (four categories: `continue_mapping`, `analyze_tagging`, `analyze_relationships`, `decommission_candidate`). `mz-classification.md` answers *what is this zone for?* (seven discriminator dimensions). A zone is `continue_mapping` **and** e.g. Dimension 3 (Kubernetes Cluster); the first sets the migration difficulty, the second sets the target field and the grouping. Run both in Stage 1; do not substitute one for the other.

## What changes

In classic (2nd gen), enrichment workers evaluate Management Zone membership by matching rules against the extracted entity model — for example, "zone `ebanking` = all hosts whose host group name starts with `ebanking`". Deciding whether any single datapoint (metric, log, trace) belongs to a zone is therefore resolved **on read**, by traversing entity relationships. Those traversals are effectively JOINs, and they run for every query and every permission check.

This does not scale on Grail. For both filtering and permission evaluation, the new platform **avoids ad-hoc joins at any price**. Instead, the discriminating information is **materialized and enriched directly onto the data** at ingest — as primary Grail fields, tags, and security context. Filters and access rules then operate on those enriched fields, keeping the query execution plan optimized at large scale.

This is why Management Zones were not rebuilt, and why migration **cannot be a 1:1 mapping**. The work is to move the membership logic from on-read rule evaluation to ingest-time enrichment on the data itself. Management Zones are removed in Phase 3, so every in-use zone must be migrated or retired before then.

### How each function maps to gen3

A Management Zone is used in up to three ways. This table maps each usage to its 3rd gen counterpart; Stage 5 chooses between them. The first two are data-plane functions and map cleanly onto enriched fields/tags; the third (administration) has no direct counterpart.

| Management Zone usage (2nd gen) | 3rd gen counterpart |
|---|---|
| **Filtering** data based on a selected Management Zone | **Segment** filtering on an enriched field — a primary field or primary tag |
| **Restricting visibility** to data scoped to a Management Zone | **Record-level permission**, **bucket permission**, or a combination of both |
| **Administration** of the environment within the MZ area (e.g. a host group) | **No direct counterpart** — clarify with the customer during migration (see below) |

**Access control** has two viable paths, depending on what the customer will do with their data layout: **IAM policy boundaries** on the enriched field/tag (see [iam-2nd-gen-roles.md](../iam-2nd-gen-roles/iam-2nd-gen-roles.md)), or **physical partitioning into dedicated Grail buckets** with bucket permissions — which also carry their own retention and ingest cost, a natural fit for chargeback. Where dedicated buckets are acceptable, no MZ equivalent is needed.

The two combine into a **two-tier access model**: a **bucket permission** scopes access at the coarse level (e.g. a whole department), while **record-level permissions** restrict finer slices within a shared bucket (e.g. individual apps whose data lands in the same departmental bucket). The same primary tags that drive bucket routing also drive these record-level rules and the UI Segment filters.

**Administration within the MZ area → no gen3-native counterpart.** In classic, zone-scoped administration covers three things: settings objects scoped to entities in the zone; a few zone-scoped global schemas (`builtin:alerting.maintenance-window`, `builtin:alerting.profile`, `builtin:anomaly-detection.metric-events`, `builtin:monitoring.slo`, `builtin:problem.notifications`); and synthetic monitors in the zone. Spaces are not an answer here either (see below). What can be said today:

- **Scope settings writes by host group** — `settings:objects:write WHERE settings:entity.hostGroup = "<group>"`. `environment:management-zone` additionally covers the five zone-scoped schemas above. Both resolve through the classic settings path, so they work while it does; neither is a gen3-native mechanism, and scope resolution goes through a compatibility mapping that can fail — confirm a policy grants what you expect before relying on it.
- **Do not design this around `dt.security_context`.** Unlike the data plane, settings writes cannot be scoped by security context.
- **Process-group-scoped settings have no replacement.** Process groups are a field on `PROCESS`, not a Smartscape node, so there is neither a node to scope to nor a security context to match. Where a zone's administration purpose rests on them, say so plainly instead of proposing a substitute.

**Finding which of those objects reference a zone takes three searches, not one.** Depending on the schema, a zone is referenced by its settings objectId, by its numeric zone ID, or by name inside a free-text filter string — classic SLOs use `mzName(...)` / `mzId(...)` in their `filter` rather than a dedicated field. Search every form on the raw export text, where filter strings arrive JSON-escaped, so a pattern written for the unescaped form matches nothing. Then confirm each hit sits in a zone-reference field, not in a name or title that merely contains the zone's name. A zone with no usage signal can still back these objects, so run this before any zone is proposed for retirement.

<!-- TODO: revisit when settings writes can be scoped on gen3 scopes directly; today schemas register on environment scope and entity scoping rides the classic path. -->

**Spaces are not a migration target today.** The construct and its primary field are still being built, and nothing is populated on the tenants checked. Do not design a zone around them, and do not offer them as an answer to any of the three functions above. If a customer raises them, say they are not yet available and migrate filtering to a Segment and read access to a security context regardless.

<!-- TODO: Spaces - revisit once the construct is generally available and its primary field is populated on a tenant. Both candidate field names measured zero on a Phase-2 and a Phase-3 tenant, and an unknown field reads the same as an empty one, so the name cannot be settled from a query yet. Then write the decision rule: ownership boundary (one owning Space per signal/object, attribute-driven, IAM conditions on it) versus Segment for filtering. Probably its own reference. -->

### Dead ends that still work in Phase 2

Two constructs below are reachable today and will not survive Phase 3, so do not build a replacement on them. The third is the one that *is* correct, and is easy to mistake for them:

- **Do not** filter a Segment on the **`managementZones` field**. It is present on `dt.entity.*` but reaches **no log records** — it never made it onto the data, and it disappears with Management Zones in Phase 3. A Segment built on it looks correct in Phase 2 and silently empties in Phase 3.
- **Do not** build Segments on classic **`dt.entity.*`** entities. They are replaced by Smartscape; use [type-mappings.md](../entity-queries/type-mappings.md) to find the Smartscape equivalent rather than reasoning about it here.
- **Do** use **`dt.security_context`** where record-level permissions are the goal — it is the only mechanism that survives. But establish **how it is currently derived** before designing anything: by default Grail sets it *from the management zones*, per entity type, and that derivation ends with Management Zones. A tenant can look fully permissioned in Phase 2 and resolve to an empty context in Phase 3.

  The derivation is per entity type and readable if you need to confirm it, but **do not configure it as part of the migration** — the setting does not exist in Phase 3, and pointing a type at `dt.security_context` populates nothing. The work is always to get the context onto the Smartscape data first (Stage 4), then let the zone go.

  ```bash
  dtctl get settings --schema "builtin:monitoredentities.grail.security.context" -o json   # destinationProperty: managementZones = zone-derived
  ```

**Coverage varies by tenant and by data kind — measure it, never assume it.** Two tenants checked during evaluation came out at roughly 58% of log records on one and 0% on the other, with 3.7% on `user.events` where its logs carried none. On that second tenant the values present were verbatim Management Zone names (`[Cloud: AWS]`, `[Cloud: AWS Cloud: VMware]`) — the default zone-derived context described above, which is what disappears in Phase 3. The Stage 3 query measures this per zone; treat any figure quoted here as an example, not a baseline.

## Prerequisites

- **`dtctl`**, authenticated to the target environment. Verify with `dtctl version` and `dtctl config current-context`, and confirm the context points at the environment the customer means. **If either check fails, stop and tell the user** — do not proceed on a guess, and do not fall back to another environment. Every command in this reference is read-only (`dtctl get settings`, `dtctl q`); nothing here writes.
- **Read access** to the `builtin:management-zones` and `builtin:tags.auto-tagging` settings schemas, and Grail read for the usage and verification queries.
- **A platform token** (`dt0s16.*`) with scope `storage:filter-segments:read`, for reading the Segment inventory in Stage 2. This is distinct from the `dtctl` auth and the account OAuth client — do not source it from `dtctl`, an OS keychain, or an unrelated environment variable. If unavailable, Stage 2 falls back to asking the customer for their Segment inventory (see the fallback note in Stage 2).
- **The Dynatrace Python SDK** (`dt>=2.0.0a1`, Python 3.12+) — **every API call in this workflow goes through it**, not through `curl` or a hand-written HTTP client. Keep the version specifier when installing it: 2.x is a pre-release on PyPI, so a bare `dt` resolves to an unrelated 1.x client. If it is not installed, use the Stage 2 fallback rather than substituting a raw request. `dtctl` remains the tool for the settings reads and DQL in Stages 1 and 3 — the SDK covers what `dtctl` does not expose.
- **2nd-gen group permission grants**, captured with [mz-permission-scopes.md](../iam-2nd-gen-roles/mz-permission-scopes.md) — this is the **primary source** for establishing which zones are access-bearing. Classic grants are what actually exist before migration; a zone referenced by a grant is doing access control, and those grants are what Stage 5 must rebuild. If the capture is unavailable, treat every zone as potentially access-bearing — this is the expected case, not a blocker; see [Partial retrieval is the normal case](../iam-2nd-gen-roles/mz-permission-scopes.md#partial-retrieval-is-the-normal-case).
- **A gen3 IAM policy export** (Terraform can retrieve all IAM policies) is a secondary, confirmatory check — useful only where policy migration has already begun. The referencing field is unconfirmed, so it may not be conclusive. Do not wait for it; derive purpose from the grants first.
- **Load the `dt-dql-essentials` skill** — the verification and parity queries in Stages 3 and 7 are DQL, and it carries the scan-cost rules (bucket filter, short time range, filter early) that this workflow depends on. An unbounded readiness query is easy to write here and expensive to run.
- **Load the `dt-migration` skill** — needed for `analyze_relationships` zones, where classic entity selectors and relationship traversals have to be re-expressed against Smartscape.
- **Sibling upgrade references** — see [Reference map](#reference-map); consult them rather than restating them.

> **Cross-feature dependencies** (record on the global upgrade tracking page):
> migrating a Management Zone depends on **Grail onboarding**, **OpenPipeline enrichment**
> (the discriminator must be on the data), **Segments**, **Grail buckets**, and
> **Smartscape entity DQL** (via `dt-migration`) for relationship-bearing zones.

## Instructions

Because there is no 1:1 mapping (see [What changes](#what-changes)), the migration **starts from the data, not from the zone**: use an MZ rule to recover its *intent*, then design the gen3 setup — taking organizational decisions from the customer rather than mechanically translating rules. Work the stages in order **per Management Zone**; the order is dependency-driven: enrichment must exist before anything can filter or restrict on it, and the target topology must be decided before any permission is built.

The stages assess; **Stage 6 writes the migration plan, and that plan is the deliverable.** Never apply a change to the environment, and leave the deployment mechanism (`dtctl`, Monaco, Terraform, UI) to the customer. Present results and **pause** after Stage 1 and Stage 5.

Prefer reuse over creation throughout, and treat a group of zones sharing a discriminator as one migration. A tenant can hold hundreds of zones, so this rarely finishes in one session: carry the per-zone disposition forward and re-read it before resuming. **Write the per-zone inventory for every configured zone even when a round is scoped to a few** — zones outside the round get their Stage 1 category and the status *not in this round*. A narrowed round that records only its own zones leaves the rest with no state to resume from.

> Example discriminator: a customer maps the infrastructure that classic MZ rules matched (host groups, Kubernetes cluster names) onto a primary tag such as `emea_de_ebanking_prod` (region + country + app + stage). Once that tag is on the data, the **same tag** can drive bucket routing, Segment filters, and access control alike.

### Stage 1 — Scope & classify

Rank zones by real usage (last 30 days) and read each zone's definition — see [evaluate-and-classify.md](evaluate-and-classify.md) for the read-only `dtctl` commands and the rule-by-rule classification procedure.

Three things come out of this stage:

1. **Purpose** — is the zone used for **filtering**, **access control**, and/or **administration**? Determine this primarily from the **2nd-gen group permission grants** captured with [mz-permission-scopes.md](../iam-2nd-gen-roles/mz-permission-scopes.md): a zone referenced by a grant is doing access control, and those grants are what Stage 5 must rebuild. **The role on the grant tells the purposes apart:** a zone-scoped `tenant-manage-settings` grant ("Change monitoring settings") means the zone carries **administration** — that group may change settings on the zone's entities and on zone-filtered global objects such as maintenance windows — while the data-reading roles (`tenant-viewer`, `tenant-logviewer`, the replay and sensitive-data roles) mean **access control**. Environment-level settings schemas were never granted through a zone, so they do not appear here. **Capture before Phase 3:** the grants exist only while the zones do, so this evidence cannot be read after opt-in. A zone no grant references is filtering-only and correspondingly cheaper and safer to migrate. A gen3 IAM policy export (Terraform can retrieve all IAM policies) is a secondary, confirmatory check — useful where policy migration has already begun, but not conclusive as the referencing field is unconfirmed. If neither grants nor a policy export are available, treat every zone as potentially access-bearing — see [mz-permission-scopes.md](../iam-2nd-gen-roles/mz-permission-scopes.md#partial-retrieval-is-the-normal-case). Fall back to how else the zone is referenced (queries, dashboards, admin scoping) only for what neither source can answer. This drives Stage 5, and it is the difference between "rebuild a filter" and "rebuild someone's access".
2. **Data kind** — whether the zone's rules match entities, metric dimensions, or **log records** (`appliesTo`). Log-based zones are the most portable rules in the schema and are invisible to the usage metric; both facts matter for planning. See [evaluate-and-classify.md](evaluate-and-classify.md#log-based-management-zones).
3. **Grail-equivalence** — reduce the zone's rules to the **data characteristic** that decides membership (host group name, Kubernetes cluster, environment, team, app, department, …), then classify whether that characteristic has a Grail equivalent. Parsing the rules — including `entitySelector` strings — sorts each zone into one of these categories:

| Category | Filter mechanism | Grail equivalence → next stage |
|---|---|---|
| `continue_mapping` | dimension/ME rules; no tags, no propagation | ✅ direct — the field is already on Grail records/dimensions; port straight to a Segment |
| `analyze_tagging` | any tag-based rule | ⚠️ conditional — only if the tag is enriched on the data; **verify in Stage 3** |
| `analyze_relationships` | any `*Propagation` flag or relationship traversal (`toRelationship(s)`/`fromRelationship(s)`) | ❌ none native — relies on Smartscape topology; must be materialized first |
| `decommission_candidate` | no rules at all | n/a — the zone matches nothing; propose deletion |

Precedence: `analyze_relationships` > `analyze_tagging` > `continue_mapping`. The mix of categories across high-usage zones is the headline migration-effort metric. Read the **Hard ratio** alongside the category — one traversal in a forty-rule zone is a very different job from a zone that is relational throughout.

Finally, **group the zones by discriminator** rather than treating each as its own migration. Many zones key off the same host-group prefix, cluster name or tag, and one enrichment plus one Segment can serve the whole group. Flag overlapping and near-duplicate zones as consolidation candidates for the customer to rule on.

<!-- TODO: unconfirmed which field a gen3 IAM policy uses to reference a management zone (expected: environment:management-zone), which decides whether the policy export can confirm purpose at all. -->

**Gates for this stage:**

- **Do not** treat an `analyze_tagging` zone as portable until Stage 3 confirms the tag is on the data.
- **Do not** port an `analyze_relationships` zone as-is. Hand it to `dt-migration` and [relationship-mappings.md](../entity-queries/relationship-mappings.md), plus a customer conversation about how the relationship should be materialized.
- **Exception — containment propagation can already be materialized.** When the rule carrying a `*Propagation` flag (or a containment traversal such as `isNamespaceOf…` or `isClusterOfNode`) keys on a containment attribute — host group, Kubernetes cluster or namespace, cloud account — and the propagated entities' data carries that same field, the propagation adds nothing a Segment on that field does not already cover. Treat it as materialized **only after Stage 3 measures the field on the propagated data kind** (host → process group: process and span data; process group → service: spans), and record that evidence in the plan. The zone keeps its `analyze_relationships` category in the inventory. This never applies to a propagation keyed on a tag or a name, or to `runsOn` / `calls` traversals — those stay relational.
- **Do not** call a zone unused on query count alone — an access-control zone can be load-bearing and quiet. Confirm it is not backing anyone's access before proposing decommission.
- **Never** bulk-translate zones 1:1, and never generate a script to do so.

#### Conversation Boundary — zone selection

Present the ranked, categorised table, then **pause and ask the user**:

> - Which zones are in scope for this round? (Recommended: pilot one `continue_mapping` zone end to end before scaling. Before recommending a pilot, confirm its discriminator values are live with one cheap check against its recorded data kind and, if the discriminator depends on one, that its integration is enabled — a pilot whose literals match nothing proves nothing, and the full value check only comes in Stage 3, after the choice is made.)
> - For each in-scope zone, what is its purpose — filtering, access control, administration, or a combination?
> - Are the `decommission_candidate` and leftover zones safe to delete, or does something still depend on them? (A `NotFoundMZName` entry in the usage metric is a deleted zone ID that something still queries — it is not a configured zone and there is nothing to delete, but find what queries it; see step 1 of [evaluate-and-classify.md](evaluate-and-classify.md#1-rank-zones-by-real-usage-last-30-days). Verify against the Stage 1 config list before reporting one as leftover.)

Do **not** proceed to Stage 2 without the user's zone selection.

### Stage 2 — Check what already exists before designing anything new

The cheapest migration is one that reuses something already in place. Before designing a replacement, establish whether the need is already met.

**Existing Segments.** List the Segment inventory yourself with the read below, and compare each Segment against the zone's discriminator. Ask the customer only for what the API does not return — who owns each Segment and who depends on it. Three outcomes:

- **Exact cover** — an existing Segment already matches the zone's scope. Reuse it; the zone needs no replacement, only a consumer migration and a decommission.
- **Near cover** — a Segment matches a broader or narrower scope. Widening it, or adding a segment variable, is usually better than creating a parallel Segment that drifts.
- **No cover** — proceed to Stage 5 and design one.

`dtctl` exposes no segments resource, but the inventory is readable through the
**Dynatrace Python SDK** (`dt`) — do not ask the customer for what you can list
yourself, and do not hand-roll the HTTP call:

```python
import os

from dt import PlatformClient

with PlatformClient(
    "https://<env-id>.apps.dynatrace.com", platform_token=os.environ["DT_PLATFORM_TOKEN"]
) as client:
    segments = client.storage.filter_segments.v1
    # Inventory first — lean stays small. owner is null unless you ask for it.
    for segment in segments.lean.list(add_fields=["OWNER"]):
        print(segment.uid, segment.name, segment.owner)

    # Only for candidates worth comparing. Without add_fields there are no includes at all.
    detail = segments.get("<uid>", add_fields=["INCLUDES", "VARIABLES"])
```

> **An include's `filter` is a serialized JSON syntax tree, not DQL text.** It arrives as a string holding `{"type":"Group","children":[{"type":"Statement","key":…,"operator":…,"value":…}]}` with character offsets into the original expression. So comparing a Segment against a zone's discriminator means reading `key`/`operator`/`value` out of that tree — a substring match against DQL will not work, and posting DQL as a filter is rejected as malformed. Treat every include with an empty `filter` as "this whole data object, unfiltered", which is common.

**All API access in this workflow goes through the SDK.** `PlatformClient` carries auth, retry, rate-limit and pagination, and returns typed models instead of raw JSON, so a field rename surfaces as a validation error rather than a silently empty result. `client.query("<dql>")` runs DQL the same way where `dtctl q` is not available. Never fall back to `curl` or a hand-written `requests` call.

**Check both prerequisites before writing any code, and give up fast if either is missing.** `python -c "import dt"` and a set `$DT_PLATFORM_TOKEN` — if either fails, do **not** try to install the SDK, mint a token, or substitute `curl`; go straight to the fallback below and spend the time on Stages 3–5 instead. Both being absent is the common case today, and Stage 2 is the one stage the workflow can complete without.

**If the SDK is unavailable:** ask the customer for their Segment inventory directly and note in the migration plan that the reuse check was performed from a customer-supplied list rather than a live read. **If the SDK is installed but `$DT_PLATFORM_TOKEN` is absent,** direct the user to configure a token with `storage:filter-segments:read` through an approved secret-management mechanism; never request or accept the token in conversation.

**Read the SDK's field names, not the REST JSON's.** The models are snake_case — `include.data_object`, `include.filter`, `segment.is_public` — where the raw API says `dataObject` and `isPublic`. Following the camelCase produced `None` for every include on a validation tenant and an empty reuse result, not an error, so a wrong name reads exactly like "no Segment covers this zone". `data_object` is `logs`, `events`, `_all_data_object` or a `dt.entity.*` type; the last is not a Phase 3 reuse target. Still ask the customer about Segments managed as infrastructure-as-code, since those may exist outside what the API returns at any moment. Built-in (ready-made) Segments are reuse candidates like any other — including for consumers deployed through Terraform or Monaco, which reference them the same way as a customer-defined Segment.

**Existing Management Zones.** Check the zone against the rest of the inventory from Stage 1. If another zone already covers the same scope — or the group it belongs to shares one discriminator — the plan is one replacement for the group, not one per zone. Consolidation is a customer decision: an apparent duplicate may exist for an access reason that is not visible in the rules.

Record the outcome per zone as **reuse / extend / create**, and carry it into the plan. A zone whose answer is *reuse* skips Stages 3–5 entirely — the Segment it reuses already reads enriched data, so there is no gap to verify and no topology to design. It still needs its consumers migrated and a decommission path, so it stays in the plan.

### Stage 3 — Verify enrichment

Before building Segments or policies, confirm the discriminator is actually present on the data. This is the gate that clears an `analyze_tagging` zone; a zone that fails it goes to Stage 4, and the gap *is* the enrichment plan.

**1. Resolve what the zone actually filters on — this step produces the field every later step checks.** Drill down into the single zone's full rule logic (step 3 of [evaluate-and-classify.md](evaluate-and-classify.md)), then map its condition keys to Grail fields with [auto-tagging-field-mapping.md](../entity-queries/auto-tagging-field-mapping.md), which already maps every management-zone attribute key to its mass-data field or Smartscape attribute. For tag-based rules, follow the resolution procedure in [mass-data-filtering-strategy.md](../entity-queries/mass-data-filtering-strategy.md) — it covers the three tag origins (rule-based, imported, manually applied), recursive `*_TAG` resolution, and `valueFormat` placeholders. Do not reproduce those tables here. A `*_TAGS` key (`HOST_TAGS`, `SERVICE_TAGS`, …) resolving to *"See above general notes"* in the mapping table is a **pointer to that procedure, not a missing mapping** — run it and give the zone a verdict; never report a tag-keyed zone as unmappable. Write the resolved field next to each condition key before running any query: a field that was guessed rather than resolved makes every later check pass or fail for the wrong reason.

**2. Read the tagging configuration** for every tag key the zone uses:

```bash
dtctl get settings --schema "builtin:tags.auto-tagging" -o json
```

Read each rule's conditions and its `valueFormat`, not just its name. A `valueFormat` that is a placeholder for an entity attribute means the tag *is* that attribute — filter on the attribute's Grail field directly, with no enrichment needed. Check this before sending a tag-based rule to Stage 4; it can turn a large share of a zone's tag rules into plain field filters.

**3. Confirm the field is on the data** — one data kind at a time, once per bucket the zone's data lands in. Substitute the field resolved in step 1:

```bash
dtctl q 'fetch logs, from: -2m
| filter matchesValue(dt.system.bucket, "<bucket>")
| summarize total = count(), present = countIf(isNotNull(<field>)),
           control = countIf(isNotNull(dt.does_not_exist)),
           sec_ctx = countIf(isNotNull(dt.security_context))' -o json
```

Before trusting the result:

- **`control` must be 0, and a zero `present` proves nothing on its own.** DQL returns null for an unknown field without an error — in `filter` position as well as in `countIf` — so a misspelled field reads exactly like an empty one. Re-check the name against step 1 before calling it an enrichment gap.
- **The timeframe bounds scan cost, not the bucket filter — for every `fetch` in this workflow, not only this one.** The scan limit applies to every data kind, not just logs. Start at `-2m` and widen only if the sample is too small to judge. Run with `-A` and read `metadata.scannedBytes`: a result near the 500 GB scan limit is truncated, and `dtctl` does not warn you. See `dt-dql-essentials` for the optimization rules.
- **Report per bucket — never one bucket, never all at once.** Coverage differs between buckets enough to invert the verdict. List the candidates first (`fetch dt.system.buckets | fields name`).
- **A short window can under-read a source that is enriched late.** Before concluding *absent*, re-run once at a longer window and check that `total` scales with it while `present` does not.
- **A missing field can be a switched-off integration**, which looks identical to lag. For Kubernetes discriminators read the `enabled` flag per connection (`dtctl get settings --schema "builtin:cloud.kubernetes" -o json`); a disabled connection is a customer action, not an enrichment design.

Reconcile the buckets as a decision, not an average: present everywhere the zone's data lands → pass; present in some → a **partial** pass, so either scope the Segment to those buckets and state in the plan what it will not see, or send the gap to Stage 4; absent everywhere → Stage 4.

**Check the data kind the Segment will filter, not logs by default.** Entity (ME) zones are the common case, and their discriminators are often absent from log records. For those, use the node-side equivalent:

```bash
dtctl q 'smartscapeNodes HOST
| summarize total = count(), present = countIf(isNotNull(<field>)),
           control = countIf(isNotNull(dt.does_not_exist)),
           sec_ctx = countIf(arraySize(dt.security_context) > 0)' -o json
```

`smartscapeNodes` is a **root command, not an argument to `fetch`**, and the node type is positional — take it from [type-mappings.md](../entity-queries/type-mappings.md), and further node-side patterns from [dql-function-migration.md](../entity-queries/dql-function-migration.md). A syntax error is not evidence that Smartscape is unavailable. **On nodes, an unset `dt.security_context` is an empty array**, so `isNotNull` counts every node: use `arraySize(...) > 0` node-side and `isNotNull` only on mass data. For metrics, confirm the discriminator is a dimension on the relevant metric keys. **Pass criterion:** present **and consistent** across the entities the zone used to cover — a partially enriched discriminator produces a Segment that silently under-matches.

**`sec_ctx` needs one extra read for an access-bearing zone.** A zero is not automatically a gap: if the entity type's derivation is `managementZones` (see [Dead ends that still work in Phase 2](#dead-ends-that-still-work-in-phase-2)), the field is empty *by design* — permissions run on zones today, which is exactly what breaks in Phase 3. If it resolves to `dt.security_context`, a zero is a genuine gap for Stage 4. Where values are present, read them before trusting them.

**4. Compare the values of the field resolved in step 1, not just its presence.** A field can be present and still carry different values than the rule matched — a classic literal that the enrichment now normalizes differently ports to a Segment matching zero records. List what the field carries, on the same data kind and bucket as step 3, and check every value-comparing literal against it ([operators without a value domain](mz-export-schema.md#the-operator-decides-whether-there-is-a-value-domain) are exempt):

```bash
dtctl q 'fetch logs, from: -2m
| filter matchesValue(dt.system.bucket, "<bucket>")
| summarize records = count(), by: {<field>}
| sort records desc' -o json
```

**Absence from a short window is not absence.** Before calling a literal dead, confirm it over a longer window (with `samplingRatio` to keep the cost down) or on the node side. When the node side and the record side disagree — a value on records with no live node, or the reverse — the data kind the Segment filters decides; record the disagreement in the plan rather than resolving it silently.

A literal with no live counterpart is a **value-domain gap**: either the enrichment normalizes differently than the classic rule did, or the rule matched something that no longer exists. Record it in the plan and fail the zone out of this stage — a field that is present but carries different values is the failure mode that produces a confidently empty Segment.

**5. Branch.** Enriched and consistent → Stage 5. Missing or inconsistent → Stage 4 first. Nothing downstream can be built until the discriminator is reliably on the data.

### Stage 4 — Close the enrichment gap (only if needed)

Design an enrichment plan so the discriminator lands on the data at ingest. **Choose the mechanism by where the discriminator originates — do not default to OpenPipeline.** For the infrastructure attributes most MZ rules key on (host group, host name, host tags), **central enrichment configuration** is the closest 1:1 replacement and needs no per-workload change; OpenPipeline primary tags are the *last resort*, for discriminators that exist only on the record. [autotagging.md](../autotagging/autotagging.md) owns that decision — follow its [migration strategy](../autotagging/autotagging.md#migration-strategy) rather than picking here, and see [cloud-telemetry-enrichment.md](../../edge-data-platform/cloud-telemetry-enrichment/cloud-telemetry-enrichment.md) for the central enrichment configuration. Whichever mechanism is chosen, it is also what [routes records into the correct Grail bucket](https://docs.dynatrace.com/docs/platform/openpipeline/concepts/data-flow).

Produce the plan; the customer applies it. Then re-run Stage 3 — nothing downstream can be built until verification passes.

**Security context is enriched differently from every other discriminator.** Set it with a **security context processor on the Smartscape event** (OpenPipeline config scope `smartscape`), not during node generation: a single span arriving without one can reset the whole value, and different producers writing the same node make entities change owner and flicker in and out of the topology view. Use multiple matchers in the processor so each rule assigns the **complete** intended audience — the array is written, not merged, and there is no field-level merge logic, so a partial write is a silent ownership change. An entity supports at most **10** values; above that, use a shared organizational context rather than enumerating teams. Two exceptions worth knowing: where the context originates at the edge it is set there instead — on **hosts** directly (`oneagentctl --set-host-tag="dt.security_context=<value>"`), and in **Kubernetes** through namespace-label enrichment with `dt.security_context` as the target (Option C in [autotagging.md](../autotagging/autotagging.md)) — this is a narrow carve-out for this one field and is **not** a licence to reach for `oneagentctl` for ordinary discriminators, which [autotagging.md](../autotagging/autotagging.md) still governs. And support differs by entity type: verify on the tenant with the node-side query from Stage 3 which types already carry a context before designing around one.

Three limits to check against the zone's discriminators before promising record-level access:

- **Enforcement is Smartscape-based.** It covers entities whose context is set at the edge; do not assume every surface a zone used to cover is enforced. Verify per data kind rather than generalizing from one passing query.
- **Process groups have no Smartscape node**, so entity-based settings keyed on `PROCESS_GROUP` cannot carry a security context. A zone whose access purpose rests on process-group rules has no record-level replacement — route it to a different mechanism in Stage 5.
- **Verify on Smartscape, not on `dt.entity.*`.** The two sides disagree in both directions, so the classic query is never the answer. A context set with `oneagentctl` shows up on the Smartscape node but **not** via `fetch dt.entity.host | fieldsAdd dt.security_context` — a false negative that sends you enriching what is already enriched. Worse is the false positive: where the entity type's context is *derived* (from management zones or the detected name), `dt.entity.*` returns a populated value that exists only as a read-time resolution in the classic API — the Smartscape nodes for the same hosts return `[]`, and the Grail data carries nothing. Measured on a tenant whose `host` and `service` types resolve to the detected name: every host returned its own name on `dt.entity.host` and an empty array on `smartscapeNodes HOST`. The same applies to entities created by datasource extensions (JMX among them): the context must be set on the host, or it never reaches them.

Once set, the context **propagates to derived data**, including Davis events and problems — so the enrichment does not have to be repeated for those.

If the security context is to carry permissions, the pipeline rules must be applied on **every surface the zone covered** — user events, user sessions, events, timeseries (configured under metrics' own OpenPipeline settings), and Smartscape events. A context applied on one surface leaves the others unfiltered.

> **This stage needs a deployment before the workflow can finish, and that is a known break.** No deployment happens without the customer's go-ahead, so for any zone with an enrichment gap the run **cannot complete in one pass**: the discriminator does not exist on the data until the customer deploys the enrichment, and until it does, Stage 3 cannot pass and the Segment cannot be verified.
>
> Do not paper over this by assuming the enrichment will work. Split the plan at the boundary instead:
>
> - **Part 1 — before deployment.** The enrichment design, and everything that does not depend on it. Hand this over and stop.
> - **Part 2 — after deployment.** Re-verification (Stage 3), the Segment and access design, and the consumption layer. This part is written but explicitly gated: it cannot be validated until Part 1 is live.
>
> Zones with **no** enrichment gap, and zones dispositioned *reuse* in Stage 2, are unaffected — they run straight through. Prefer those for the pilot, precisely because they avoid this round trip.

<!-- TODO: a dedicated autotagging skill is in progress. When it lands, point this stage at it instead of the autotagging upgrade reference, and check whether it can derive the enrichment design rather than leaving it to be written by hand here. -->

### Stage 5 — Decide the target topology

The judgment stage — *not* a mechanical translation. Decide per function (see [How each function maps to gen3](#how-each-function-maps-to-gen3) for the options in detail):

- **Filtering** → one or more **Segments** keyed on the discriminator.
- **Access control** → choose by data volume and org structure:
  - dedicated **Grail bucket** per team/department (physical separation; fits retention + chargeback), coarse access via **bucket permissions**;
  - **record-level permissions** within a shared bucket (apps sharing a department bucket), fine access — write IAM policy conditions with `MATCH`, not `=`: `dt.security_context` is a `string[]`, and some producers (network extensions among them) store several values, which an equality condition silently fails to match;
  - **IAM policy boundary** on the enriched field/tag (no physical separation).

The inputs here are organizational, so they come from the customer: *how is the org structured, who should access which data, expected volume per team*.

**Permissions are suggested, never applied.** Write out the policy statement the design needs — the permission, the condition (a primary field, primary tag or `dt.security_context`), and which group should hold it — and let the customer create and bind it. Binding a policy to a group is what actually grants access, and an over-broad condition is invisible once applied, so this stays a human step even where the plan is agreed. State it as a concrete statement to review rather than prose describing the intent. **You cannot check it against the tenant, even read-only:** policies live on the account API, which an environment token cannot reach — it is rejected outright, and no environment-level policy endpoint exists. So the statement you hand over is unvalidated by construction. Say so when handing it over, and keep it simple enough to be reviewed by eye.

<!-- TODO: MZ "change settings" maps to per-zone policy bindings, which risks policy explosion across many zones without a template. Needs a recommended pattern before it becomes guidance. -->

#### Conversation Boundary — topology decision

Present the options with their trade-offs, then **pause and ask the user**:

> - Should this zone's access control be physical separation (dedicated bucket), record-level permissions in a shared bucket, or an IAM policy boundary?
> - How is the organization structured, and what data volume is expected per team?
> - Who should be able to see which data — and does anyone lose access if we get this wrong?

Do **not** choose on the customer's behalf, and do **not** proceed to Stage 6 without a decision. These are organizational calls with access consequences; a default here is a wrong answer.

### Stage 6 — Write the migration plan

This stage produces the deliverable. Write it for a Dynatrace engineer at the customer who will execute it without you present, so every step must be actionable on its own. Per zone or discriminator group, the plan states:

- **What the zone does today** — its discriminator, purpose, data kind, category and Hard ratio.
- **Disposition** — reuse an existing Segment, extend one, create a new one, or decommission. Say which, and why.
- **Prerequisites** — the enrichment gap from Stage 3, if any, and what closes it.
- **Dead rules** — rules whose literals match nothing live (Stage 3 step 4) or whose pinned entity no longer exists. List them per rule with a **drop** recommendation: they are dead in classic already, so porting them carries the breakage forward. A zone whose rules are all dead is a decommission candidate, not a migration.
- **The target design** — the Segment definition, bucket and routing, and access model chosen in Stage 5, with the customer's rationale recorded alongside it.
- **The build steps, in dependency order** (below).
- **How to verify** — the parity checks from [Validation](#validation).
- **Decommission criteria** — what must be true before the zone is removed.
- **Open questions** — anything still needing a customer decision, stated as a question rather than an assumption.

Order the plan by discriminator group and by usage, so the highest-value work is at the top and shared enrichment is done once.

Build steps, in dependency order. Definitions only — deployment-agnostic, applied by the customer:

1. **Enrichment** in place (Stage 4) — prerequisite for everything below.
2. **Bucket(s) + OpenPipeline routing**, if physical separation was chosen.
3. **Access control** — bucket and/or record-level permissions, or the IAM policy boundary.
4. **Segment(s)** for filtering.
5. **Consumption layer** — migrate dashboards, recreate alerting, wire the Segment filters.

Filtering and access are built independently but share the same enriched tag. Across many zones: enrich a shared discriminator **once**, and pilot one zone end-to-end before scaling.

#### Hand the Segment over — do not create it

**This skill does not create Segments, permissions or policies. It produces definitions and the steps to apply them; the customer applies them.** Write the Segment out so it can be entered without further interpretation:

- **Name** — and the zone it replaces, so the pair is traceable.
- **Visibility** — private to the author or shared. Say which, and why.
- **One include per data kind** the zone covered: the data object (`logs`, `spans`, `events`, …) and the filter expression on the enriched field, written the way it is typed in the UI, e.g. `k8s.cluster.name = "eks-live"`. A zone covering several data kinds needs several includes, each verified in Stage 3. Write the expression, not the stored form: the API keeps it as a syntax tree (see Stage 2), which is another reason the customer creates the Segment in the UI rather than receiving a payload to post.
- **Scope each include to known buckets only where that data object's guidance permits bucket filtering.** It is advisable rather than required — the Segment works without it — but without it every query the Segment is applied to scans all buckets of that data kind until it hits the scan limit, and returns a truncated result rather than an error. Use the buckets Stage 3 measured and record any intentionally unscoped data in the hand-over. **Do not filter `security.events` on `dt.system.bucket`**: security events can reside in any bucket, so such a condition can hide data.
- **Variables**, if the filter is parameterized — the variable query, and for each consumer the value it is pinned to (see below).

Point the customer at the **Segments** app to create it, and tell them where it then has to be selected — the segment picker in the apps, dashboards and notebooks that replace the zone's consumption layer. A Segment nobody selects changes nothing, which is why the consumption layer is build step 5 rather than an afterthought.

Then confirm parity (Stage 7) against what they actually created, not against the definition on paper.

#### One Segment for a zone family — use a variable

**When zones in a group differ only in the value of one discriminator, hand over one Segment with a variable instead of one Segment per zone.** This is the common shape of a zone family: the same rules, repeated per environment, cluster or host group.

- **How a variable works.** It is defined by a DQL query; each output column becomes a variable, referenced in the filter as `<field> = $<column>`. Whoever selects the Segment picks one or more values, and several selected values match any of them.
- **The selection is saved with the consumer.** A dashboard or notebook keeps the values chosen for it, so each migrated consumer is pinned to *Segment + value*. That is what lets one definition replace the whole family, not just serve ad-hoc exploration.
- **The query decides what can be selected.** A value the query does not return cannot be picked, so run the value-domain check (Stage 3 step 4) against the query's output, not only against the data.
- **Write the query against data that survives Phase 3** — Smartscape nodes, metric series, record fields. Never `dt.entity.*`: a variable query built on it stops returning values at opt-in, and existing variable Segments on a tenant may already do this — check them before reusing one.
- **A pattern is not a value.** A zone matching by regex or prefix covers whatever matches, now and later; pinning today's matches goes stale the moment one appears or disappears. Segment filters take prefix, suffix and contains wildcards (`x*`, `*x`, `*x*`), but a regular expression has no direct form there. Rewrite the pattern as wildcards where it can be expressed that way, otherwise enrich a stable field that names the group — and say which in the hand-over.
- **Not for zones that differ in more than the value** — extra rules, other data kinds, or a different discriminator. Those get their own Segment. And a variable Segment still only filters; it restricts nothing.

In the hand-over, write the variable query once and list each consumer with the value it is pinned to.

### Stage 7 — Confirm parity

Once the customer has applied the plan, confirm the Segment returns the same scope the MZ did, that access grants and denials match the old zone permissions, and that dashboards and alerts work on the new scope. See [Validation](#validation) for the queries.

### Stage 8 — Decommission

Track adoption and watch the zone's classic usage trend to zero; remove the Management Zone once it is unused. Re-check that the zone is not backing anyone's access before recommending removal — usage counts queries, not permissions. (Management Zones are removed in Phase 3 regardless.)

### Next steps

Zones scoped alerts and dashboards in classic, so migrating a zone usually unblocks those: continue with [alerting-and-problem-notifications.md](../alerting-and-problem-notifications/alerting-and-problem-notifications.md) for MZ-scoped alerting, and [dashboards-classic.md](../dashboards-classic/dashboards-classic.md) for the consumption layer.

## Customer actions

- **Answer the organizational questions** — org structure, who should access which data, expected volume per team, and each zone's purpose (filtering / access control / administration). Stage 5 cannot be answered without this, and purpose is not reliably discoverable from the configuration.
- **Provide the group-to-permission list** — the 2nd-gen grants naming each zone, captured with [mz-permission-scopes.md](../iam-2nd-gen-roles/mz-permission-scopes.md) or sent by the account administrator. Without it every zone must be treated as potentially access-bearing.
- **Say who owns and uses each existing Segment.** The inventory is readable (Stage 2); ownership and blast radius are not.
- **Rule on consolidation and deletion** — whether near-duplicate zones can share one Segment, and whether `decommission_candidate` and leftover zones are safe to remove.
- **Deploy the enrichment and give the go-ahead** where a zone has an enrichment gap; the second half of that zone's plan cannot be verified until this is done.
- **Apply the plan** — enrichment, buckets and routing, permissions, Segments, consumption layer — using their chosen deployment mechanism, then **retire the zones** before the Phase 3 cutover.
- **Resolve the administration gap** — how administration previously scoped to an MZ area should work in gen3, since there is no equivalent construct.

## Examples

**A large customer, 1000+ teams, Dynatrace as an internal charged-for service.** In 2nd gen, team identity was derived by mapping infrastructure (host groups, cluster names) onto a zone such as `emea_de_ebanking_prod`. In 3rd gen the same identity is one **primary tag on all data**, and that single tag drives bucket routing, access control (bucket permissions coarse, record-level fine) and UI Segment filters alike. There is no automated path between the two: a team that used to open *failed service requests for their app* needs that experience rebuilt on gen3 primitives — enrichment, buckets, routing, dashboard, Segment, alerting. That list is Stage 6's build order, and it is what "migrating a zone" actually costs.

**A zone that looks portable but is not.** A busy zone whose rules are mostly simple cluster-name matching also carries one `SELECTOR` rule reading roughly *"services that run on the database tagged `orders-db-prod`."* That "runs on" is a relationship traversal encoded inside a selector string, so the zone is `analyze_relationships` — a rule-counting tool waves it through, and porting it directly produces a Segment that matches the wrong set. Its **Hard ratio is low**, so most of it is portable; the single traversal is what needs a human and a customer conversation.

## Outcome

**What changes**: nothing, yet. This reference produces a **migration plan document** — a per-zone assessment plus the dependency-ordered steps to carry it out. It is deployment agnostic and **nothing is applied to the environment**; the customer reviews the plan, decides what to accept, and chooses the deployment mechanism (`dtctl`, Monaco, Terraform, UI).

Open the plan with the assessment table:

| Zone | Usage rank | Category | Hard rules | Data kind | Group | Discriminator | Field present? | Values match? | Purpose | Disposition |
|---|---|---|---|---|---|---|---|---|---|---|
| `<name>` | 3 | `analyze_tagging` | 0/11 | ME | team-tag | `<field or tag>` | no | n/a | filtering | enrich, then create Segment |
| `<name>` | 7 | `analyze_relationships` | 6/6 | ME | — | topology traversal | n/a | n/a | access control | hold — customer plan needed |
| `<name>` | 12 | `continue_mapping` | 0/4 | ME | cluster-name | `<cluster field>` | yes | yes | filtering | reuse existing Segment `<name>` |
| `<name>` | 18 | `continue_mapping` | 0/2 | ME | cluster-name | `<cluster field>` | yes | **no — 0/4 literals live** | filtering | value-domain gap — normalize before porting |
| `<name>` | — | `continue_mapping` | 0/3 | LOG | — | `<log field>` | yes | yes | filtering | create Segment (no usage signal — confirm) |
| `<name>` | — | `decommission_candidate` | — | — | — | none | n/a | n/a | unknown | propose deletion, confirm first |

**Both enrichment columns are required, and both are per bucket.** `Field present?` is Stage 3 step 3, `Values match?` is Stage 3 step 4. Where coverage differs by bucket, record the split (`yes (app bucket) / no (default)`) rather than picking the flattering one — a bare `yes` hides a Segment that is blind to most of the tenant's data. A zone that passes the first and fails the second ports to a Segment matching zero records, so a single combined "enriched" verdict reports that zone as ready when it is broken.

Then, per in-scope zone or group, the plan sections listed in Stage 6. A zone marked *reuse* still appears — with the Segment it reuses and its decommission criteria.

## Validation

All checks are read-only. Run them after the customer has applied the plan.

**Scope parity** — the Segment must return the same scope the Management Zone did. Compare counts over the same bounded window, once through the new Segment and once through the classic zone's discriminator:

```bash
dtctl q 'fetch logs, from: -1h
| filter matchesValue(dt.system.bucket, "<bucket>")
| filter <new segment predicate>
| summarize count()' -o json
```

Validate generated DQL before running it:

```bash
dtctl verify query "<generated DQL>"
```

**Access parity** — confirm the new grants and denials match the old zone permissions, including that users who *should not* see the data still cannot. A permission migration that only tests the positive case is untested.

**Tracking query** — count remaining in-use classic zones to track migration progress; this is the same usage query as step 1 of [evaluate-and-classify.md](evaluate-and-classify.md). A zone trending to zero queries is a decommission candidate, subject to the access check in Stage 8.

Caveats:

- **Counts may legitimately differ.** The classic zone resolved membership on read via topology; the Segment matches enriched fields. A small delta can be correct — investigate the direction and cause rather than tuning until the numbers match.
- **Keep parity queries bounded** — short range, one data kind, always a bucket filter. These queries are easy to make expensive.

<!-- TODO: scope end-state - by decision this reference plans and verifies but applies nothing: Segments, permissions and policies are handed over, not created, even though write APIs exist for all three. Revisit only if that decision changes. -->

## Documentation

- [What Management Zones are](https://docs.dynatrace.com/docs/manage/identity-access-management/permission-management/management-zones)
- [Apply and use Management Zones](https://docs.dynatrace.com/docs/manage/identity-access-management/permission-management/management-zones/apply-and-use-management-zones)
- [Upgrade guide (Gen3 concepts overview)](https://docs.dynatrace.com/docs/manage/upgrade-guide-landing-page)
- [Migrate roles to policies](https://docs.dynatrace.com/docs/manage/identity-access-management/permission-management/manage-user-permissions-policies/advanced/migrate-roles)
- [OpenPipeline data flow](https://docs.dynatrace.com/docs/platform/openpipeline/concepts/data-flow)
