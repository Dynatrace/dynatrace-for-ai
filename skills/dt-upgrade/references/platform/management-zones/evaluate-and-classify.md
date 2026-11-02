# Evaluate & classify existing Management Zones

The procedure for **Stage 1** of [management-zones.md](management-zones.md): rank zones by real usage, read each zone's definition, and classify whether its filter logic has a **data equivalent on Grail**. Work through this before porting any zone to a Segment.

Everything here is **read-only** — it reads settings and queries usage metrics, and changes nothing. The category it assigns is an input to a human decision, not an instruction to migrate.


## Contents

- [Grail-equivalence categories](#grail-equivalence-categories)
- [Procedure](#procedure)
  - [1. Rank zones by real usage (last 30 days)](#1-rank-zones-by-real-usage-last-30-days)
  - [2. Fetch the zone configurations](#2-fetch-the-zone-configurations)
  - [3. Classify each rule, then each zone](#3-classify-each-rule-then-each-zone)
  - [4. Inspect a single zone's full rule logic (drill-down)](#4-inspect-a-single-zones-full-rule-logic-drill-down)
- [Output](#output)
- [Example result](#example-result-top-zones-by-usage-anonymized)

## Grail-equivalence categories

A Management Zone is a Classic, entity-based (Smartscape) concept; on Grail the equivalent is a DQL-based Segment/filter. Whether a zone translates cleanly depends on its filter mechanism. Each zone sorts into one of four categories:

| Category | Trigger | Grail data equivalence | Migration action |
|----------|---------|------------------------|------------------|
| `continue_mapping` | ME rules **without** propagation + DIMENSION rules, **no** tag keys | ✅ **Direct** — matched fields (account id, service name, metric key, …) exist on the Grail records / metric dimensions | Port directly to a DQL Segment |
| `analyze_tagging` | Any rule using a **tag** (`tag` field, `TAG_KEY_*` operator, `*_TAGS` key, or `tag(...)` inside a selector) | ⚠️ **Conditional** — tags exist on Grail only if propagated onto the records / dimensions | Port, but verify the tag lands on the data (runbook Stages 3–4) |
| `analyze_relationships` | **Any** `*Propagation` flag set on an `attributeRule`, or **selector traversal** (`toRelationship(s)` / `fromRelationship(s)`) | ❌ **None native** — relies on Smartscape topology, which raw Grail records don't carry | Cannot port as-is; resolve/materialize the topology first |
| `decommission_candidate` | Zone has **no rules** at all | n/a — the zone matches nothing | Delete, do not migrate — confirm with the customer first |

**Precedence when a zone hits multiple flags:** `analyze_relationships` > `analyze_tagging` > `continue_mapping`.

> **Match propagation generically, never by name.** The propagation flag set is open-ended — beyond the host/process-group/service trio there are process-group→host, process-group→service, Azure→process-group, Azure→service and custom-device-group variants. Checking only for the names you happen to know mislabels relationship-dependent zones as `continue_mapping`, i.e. as safe to rebuild directly, which is the most damaging mistake available in this step. Treat **any** truthy field whose name ends in `Propagation` as a relationship dependency, including ones not listed here.

### Critical detail: parse SELECTOR strings

A SELECTOR rule stores its logic as an `entitySelector` **string**, e.g.
`type(SERVICE),toRelationships.isNamespaceOfService(type(CLOUD_APPLICATION_NAMESPACE),entityName.in("my-namespace"))`.
Surface-level rule-type counting will misclassify these as simple. You must inspect
the string for `tag(` and `to/fromRelationship(s)` — a relational traversal pushes the
zone to `analyze_relationships` (no Grail equivalent), regardless of rule count.

## Procedure

Read the configuration and classify it yourself.
The rules below are simple field checks, and doing them in the open keeps every category
traceable to the rule that produced it. Both commands are read-only.

### 1. Rank zones by real usage (last 30 days)

```bash
dtctl q 'timeseries queries = sum(dt.sfm.server.management_zones.queries_counter),
  by: { dt.management_zone.id, dt.management_zone.name }, from: -30d
| fields dt.management_zone.name, dt.management_zone.id,
         total = arraySum(queries), intervals = queries
| sort total desc
| limit 1000' -o json
```

**Do not lower the limit to see a top list — rank from the full result.** The `NotFoundMZName` rows and the leftover check below need every row; a cut-off drops them silently. If the row count equals the limit, raise it and re-run. One tenant returned 59 rows, which a `limit 20` hides two thirds of.

> **This metric sees only part of the picture — never treat it as an inventory.** It
> counts query evaluations on the classic entity/metric path. On a tenant with 187
> configured zones it reported only 39, and **log-based zones (see step 3) did not appear
> at all**. Rank with it, but take the zone *inventory* from the configuration in step 2.
> A zone absent here is a zone with no usage signal — not a zone with no usage.

**Split the result before reporting anything.** Every row is one of exactly three
things, and conflating the first two is the most common error in this step:

| Row | Test | Action |
| --- | --- | --- |
| **Configured zone** | name matches a zone in the step-2 config | migrate |
| **`NotFoundMZName`** | literal string `NotFoundMZName` — an ID with no name | **not a zone**; nothing to migrate or delete, exclude from scope and from any "leftover" count — but find what still queries it (below) |
| **Leftover zone** | a *named* row absent from the step-2 config | report to the user, and find what still queries it (below) |

State the arithmetic explicitly in the ranked table you present — *"13 rows = 9 configured
+ 4 `NotFoundMZName` + 0 leftover"*. If you have not run step 2 yet, you cannot classify
rows into the last two buckets; say so rather than guessing.

Notes:
- The **Upgrade Assistant** app ranks management-zone usage from this same metric
  over the same 30-day window. Where the customer has already run it, start from
  its number and reconcile rather than presenting a competing figure — every
  caveat below applies to it equally.
- Zones showing as `NotFoundMZName` are deleted zones that something **still queries by ID** — this is current traffic in the 30-day window, not history. Exclude them from migration scope, but do not dismiss the traffic.
- **Leftover zones** — a named zone that appears in this usage ranking but is *absent*
  from the `builtin:management-zones` config in step 2 is a leftover or renamed zone.
  Something is still querying it, so **report it to the user**; do not silently drop it.
  Cross-check both lists by name rather than assuming the config is complete.
- **Find what queries a zone that no longer exists.** For every `NotFoundMZName` and leftover row, search the zone-scoped consumers for its ID with the three-form search in [management-zones.md](management-zones.md#how-each-function-maps-to-gen3). Metric events and SLOs left pointing at a deleted zone are a confirmed source — they keep evaluating against it, and they are broken today, so list them as consumers to fix rather than as noise. Traffic with no settings reference at all, typically a flat, near-identical series across many IDs, comes from outside settings — an external script or poller iterating a fixed ID list. No read path finds it; report the IDs and the pattern, and ask the customer.
- Usage (how often a zone is queried) is independent of rule complexity: a 2-rule zone
  can rank #2 by usage.
- **Low usage is not the same as unused.** This metric counts *queries* only. A zone that
  exists to grant a team visibility can carry little query traffic and still be
  load-bearing for access control. Never classify a zone as junk on query count alone —
  confirm it is not backing anyone's access before proposing decommission.
- **A flat series is a machine, not a user.** Read the `intervals` array, not just
  `total`. A zone queried by people is bursty — weekday peaks, quiet nights, values
  differing by orders of magnitude between 6-hour buckets. A zone whose intervals
  repeat almost the same number over and over is being polled on a schedule: a
  dashboard left open on a wall, a synthetic check, an export job. On one reference
  tenant, four deleted zones sat at a dead-flat ~432 queries per interval for thirty
  days and one live zone at ~864 varied by barely a factor of two, while the
  genuinely human-queried zones ranged from single digits to the thousands.
  **Consequence:** ranking on `total` alone promotes scheduled jobs to the top of the
  migration list. When a high-`total` zone has a flat `intervals` array, say so
  explicitly — the question for that zone is *"what job is polling this, and does
  that job need migrating?"*, not *"which team depends on this?"*. A zone whose `intervals`
  array dips to zero in some buckets and spikes in others is showing a human-usage
  pattern — those empty buckets are nights and weekends, not gaps in the data. That
  is a different thing from a zone with no queries at all, which is covered above.
- **Do not turn this into a threshold.** There is no cutoff that separates machine
  from human traffic reliably — a wall dashboard a team actually reads is both. The
  interval pattern is evidence to put in front of the customer, not a filter to
  apply on their behalf.

### 2. Fetch the zone configurations

```bash
dtctl get settings --schema "builtin:management-zones" -o json
```

This — not the usage metric — is the authoritative zone inventory.

Each item carries `value.name` and `value.rules[]`. Every rule is one of:

- `type: "DIMENSION"` — matches **mass data directly**, with no entity in between. Carries
  a `dimensionRule` whose **`appliesTo`** is `METRIC`, `LOG`, or `ANY`, and whose
  `conditions[]` use a `conditionType` of `DIMENSION` (with a `key`), `METRIC_KEY`, or
  `LOG_FILE_NAME` (the latter two have no `key`).
- `type: "SELECTOR"` — carries an `entitySelector` **string** (see the note above).
- otherwise an **ME rule** carrying an `attributeRule` object with `conditions[]` and
  optional `*Propagation` flags.

#### Log-based management zones

A zone is *log-based* when it has `DIMENSION` rules with `appliesTo: "LOG"`. These match
log attributes directly — a log field (`conditionType: "DIMENSION"` with e.g.
`key: "status"`), or the source file (`conditionType: "LOG_FILE_NAME"`). No entity and no
topology is involved, so **these are the most portable rules in the whole schema**: the
condition is already a predicate over log records and translates almost literally into a
Segment filter.

They need calling out for three reasons:

- The usage metric in step 1 **does not see them**, so a purely log-based zone looks
  unused and risks being triaged as junk.
- `appliesTo` decides *which data kind* Stage 3 must verify — a `LOG` rule is verified
  against `fetch logs`, a `METRIC` rule against the metric's dimensions. Verifying the
  wrong one proves nothing.
- `appliesTo: "ANY"` applies to both, so it needs verifying on both.

Record `appliesTo` per zone; it is an output column, not an intermediate detail.

### 3. Classify each rule, then each zone

For **each rule**, decide whether it is *relationship-bearing*, *tag-bearing*, or neither:

| Look at | Relationship-bearing when | Tag-bearing when |
|---|---|---|
| `attributeRule` | **any** field whose name ends in `Propagation` is truthy | any entry in `conditions[]` mentions a tag — a `tag` field, an `operator` containing `TAG`, or a `key` ending in `_TAGS` |
| `entitySelector` string | it contains `toRelationship` or `fromRelationship` — match the stem case-insensitively, because the selector grammar also accepts the singular form and a check for the plural silently misses it | it contains `tag(` |
| `type: "DIMENSION"` | never | never |

Relationship wins over tag: a rule that does both counts as relationship-bearing only.

Then for **each zone**, in this order — the first match wins:

1. `value.rules[]` is empty → `decommission_candidate`
2. any rule is relationship-bearing → `analyze_relationships`
3. any rule is tag-bearing → `analyze_tagging`
4. otherwise → `continue_mapping`

Alongside the category, record the **Hard ratio** (relationship-bearing rules / total
rules), the **Tagged ratio** (tag-bearing rules / total rules), and the **data kind**
from `appliesTo`. **Count every rule in the zone, enabled or not** — a disabled rule is
one toggle away from being live, and counting only enabled rules makes the same zone
report two different ratios depending on who looked. Where disabled rules exist, note
them separately (`6/9, 2 disabled`) rather than dropping them from the denominator. The category alone hides how much of a zone is actually difficult —
see [Output](#output).

#### Group zones by discriminator before planning anything

Zones are not independent. Many key off the same scheme — the same host-group prefix, the
same Kubernetes cluster name, the same tag — and on Grail one enriched field plus one
Segment can serve all of them. Before producing any plan:

- **Group zones that resolve to the same discriminator.** Enrich once, build once, and
  cover the whole group. This is the single biggest effort reduction available, and it is
  invisible if zones are worked one at a time.
- **Flag overlapping and near-duplicate zones.** Zones whose rules differ only in name, or
  that are strict subsets of another zone, are consolidation candidates — but the decision
  is the customer's, since an apparent duplicate may exist for an access reason.
- **Report the groups, not just the zones.** "These 14 zones all key off the cluster name"
  is far more actionable than fourteen separate rows.

Work through the zones in **usage order from step 1**, highest first, and report in
batches rather than waiting until every zone is done. On a large tenant the busiest
20–30 zones decide the migration plan; the long tail of unused zones is mostly
decommission triage and can follow.

**On a tenant with more zones than you can read one by one, apply the rules above with a short read-only script** — they are deliberately mechanical so they can be lifted unchanged. A script that classifies wrongly does so silently, so check it before trusting it: every zone with a truthy `*Propagation` field or a selector traversal in either spelling must come out `analyze_relationships`, and every rule must land in exactly one category. Hand-written parsing is where classification goes wrong — read each condition's carrier rather than one fixed field ([mz-export-schema.md](mz-export-schema.md#where-a-conditions-value-lives)), and key results by objectId or zone ID rather than by name, because usage rows repeat names (every `NotFoundMZName` row has the same one). The script only classifies; it never translates a zone.

### 4. Inspect a single zone's full rule logic (drill-down)

Take the zone's UID from the listing in step 2, then fetch that object on its own:

```bash
dtctl get settings <uid> --schema "builtin:management-zones" -o json
```

Read the full rule set before proposing anything for that zone — in particular, read
every `entitySelector` string in full. This is the command to reach for whenever a
zone's category is surprising, or before taking any zone into a customer conversation.

## Output

Report a per-zone table with the usage rank, rule count, the **Hard** and **Tagged**
ratios, the **data kind** (`appliesTo`), the **discriminator group**, and the assigned
category. The category distribution is the
headline migration-effort metric: the share of high-usage zones in
`analyze_relationships` indicates how much topology resolution work the migration
requires (these have **no** direct Grail equivalent).

**Read the ratio, not just the category.** The category is a worst-case label — a single
relationship rule makes the whole zone `analyze_relationships`. `Hard 1/40` (mostly
simple cluster-name matching plus one traversal) and `Hard 38/39` (relational
throughout) carry the same category but are very different jobs: the first is largely
portable with one rule to resolve by hand, the second needs a topology plan. Use the
ratio to order the work and to set expectations with the customer.

**A `decommission_candidate` is not a migration.** A zone with no rules matches nothing,
so report it for deletion rather than porting it — but confirm with the customer first,
and re-read the "low usage is not the same as unused" note above.

## Example result (top zones by usage, anonymized)

| Rank | Management Zone | Rules | Hard | Data kind | Group | Category |
|------|-----------------|------:|-----:|-----------|-------|----------|
| 1 | zone-prod-a | 22 | 20/22 | ME | — | `analyze_relationships` |
| 2 | cloud-metric-streams | 2 | 0/2 | METRIC | metric-key | `continue_mapping` |
| 3 | team-b | 18 | 15/18 | ME | — | `analyze_relationships` |
| 5 | service-c | 7 | 4/7 | ME | — | `analyze_relationships` |
| 6 | sso-prod | 11 | 2/11 | ME | — | `analyze_relationships` |
| 7 | cluster-prod-d | 6 | 6/6 | ME | cluster-name | `analyze_relationships` |
| 8 | central-ops | 39 | 1/39 | ME | cluster-name | `analyze_relationships` |
| 10 | general-e | 7 | 1/7 | ME | cluster-name | `analyze_relationships` |
| — | log-errors-team-x | 3 | 0/3 | LOG | — | `continue_mapping` |

Findings:
- 7 of 8 configured top zones have **no direct Grail equivalence** — the dominant
  migration cost is relationship/topology resolution, not field mapping.
- The ratio changes the plan. `central-ops` (39 rules, 1 hard) and `cluster-prod-d`
  (6 rules, all hard) share a category but not a workload.
- Three zones key off the **same cluster-name discriminator**, so one enrichment and one
  Segment covers all three — plan them as a group, not as three migrations.
- `log-errors-team-x` never appeared in the usage ranking because the metric does not
  count log-based zones. It is also the easiest zone in the table: its conditions are
  already predicates over log records.
- `sso-prod` is the cautionary case: it reads as tag-driven at a glance, and a quick pass
  over it lands on `analyze_tagging` — but two of its rules also traverse relationships.
  Zones like this are exactly why propagation must be matched generically and why every
  selector string has to be read in full. A false "portable" on a busy zone is the worst
  outcome of this whole step.
