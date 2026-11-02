# Management Zone Classification

A seven-dimension taxonomy for understanding what each management zone does before choosing its Gen3 migration path. Dimensions are **not mutually exclusive** — a zone can match more than one (e.g. `SSO dev` belongs to both Dimension 1 and Dimension 2).

Use this alongside the [management zone migration strategy](management-zones.md#instructions) and [mz-export-schema.md](mz-export-schema.md) for the export file structure.

## Contents

- [Dimension 1 — Product / Team Ownership](#dimension-1--product--team-ownership)
- [Dimension 2 — Stage / Environment](#dimension-2--stage--environment)
- [Dimension 3 — Kubernetes Cluster](#dimension-3--kubernetes-cluster)
- [Dimension 4 — Keptn Project / Quality Gate](#dimension-4--keptn-project--quality-gate)
- [Dimension 5 — Synthetic / Load Testing](#dimension-5--synthetic--load-testing)
- [Dimension 6 — Cloud Provider / Infrastructure](#dimension-6--cloud-provider--infrastructure)
- [Dimension 7 — Metric / Entity Selector Rules](#dimension-7--metric--entity-selector-rules)
- [Classification algorithm](#classification-algorithm)
- [Prioritising migration using the classification](#prioritising-migration-using-the-classification)
- [Related references](#related-references)

---

## Dimension 1 — Product / Team Ownership

Zones scoped to all entities belonging to a product team or organizational unit.

**Rule signals:**
- `SERVICE_TAGS`, `HOST_TAGS`, `PROCESS_GROUP_TAGS` matching team-owned tag names
- `KUBERNETES_CLUSTER_NAME` for team-dedicated clusters

**Naming signals:** a team or product name as the primary noun — a function (`SSO`, `IAM`, `Payments`) or an internal product codename that means nothing outside the organization. Ask the customer what a codename refers to rather than guessing.

**Gen3 migration path:** Set the team identity as `primary_tags.<team>` at the source (see [autotagging.md](../autotagging/autotagging.md) for delivery options). Use the tag in a Segment for filtering and in an IAM policy boundary for access control. When reporting, break down sub-groups by named team or product family; group teams with 1–2 zones under "Other teams".

---

## Dimension 2 — Stage / Environment

Zones scoped to a deployment lifecycle stage, almost always combined with a team dimension.

**Rule signals:**
- `KUBERNETES_CLUSTER_NAME` containing `dev`, `sandbox`, `test`, `prod`, or `staging`
- `keptn_stage:` tag value
- Host group name patterns with stage keyword

**Naming signals:** stage keyword as suffix or embedded (e.g. `SSO dev`, `IAM sandbox`, `Payments - Sandbox`, `Keptn: sockshop staging`)

**Gen3 migration path:** If the cluster name encodes the stage, `k8s.cluster.name` is already a built-in Grail field — no source-side action needed; build Segment filters directly on it. For custom stage tags, define `primary_tags.environment` or `primary_tags.stage` at the source. Report counts per stage: dev, sandbox, test, staging, prod.

---

## Dimension 3 — Kubernetes Cluster

Zones representing a single K8s cluster — all entity types within it (hosts, process groups, services, cloud apps, namespaces).

**Rule signals:**
- `KUBERNETES_CLUSTER_NAME` exact match or regex
- Propagation applied across multiple `entityType` values within the same cluster name

**Naming signals:** cluster name appears verbatim, often behind a bracketed prefix (`[Kubernetes]`, or a site- or platform-specific tag the customer uses) or as `Cluster '...'`

**Gen3 migration path:** `k8s.cluster.name` is a built-in primary Grail field, so no source-side tagging is required **for the field to exist** — which is not the same as the zone being portable. Build Segment filters and IAM policy boundaries on `k8s.cluster.name` only after the three-part test below passes.

Migration cost for this dimension is zero **only when all three hold: no truthy `*Propagation` flag is set** on the zone's rules, **the literals the rules match on still exist in the live field**, and **the field is present and consistent across the data the Segment will filter** (Stage 3 step 3 of [management-zones.md](management-zones.md)). The third condition bites independently of the other two: on the validation tenant `k8s.cluster.name` was missing from 15% of Kubernetes-bearing log records overall and from **100%** of one cluster's estate, because that cluster's connection was disabled. A zone scoped to it passes the first two conditions and is still structurally blind. Any truthy field whose name ends in `Propagation` makes the zone depend on Smartscape topology, which raw Grail records do not carry — that puts the zone in the `analyze_relationships` category, which cannot be ported as-is. Match the suffix generically rather than checking specific flag names: the flag set is open-ended (process-group→host, process-group→service, Azure→process-group, and custom-device-group variants all exist). See [evaluate-and-classify.md](evaluate-and-classify.md#grail-equivalence-categories) for the classification rule.

The field being built-in says nothing about its values: classic rules matching `eks`, `gke` or `linkerd` match nothing where the live `k8s.cluster.name` values are `eks-live`, `gke-live`, `aks-live`. Run Stage 3 step 4 of [management-zones.md](management-zones.md) before calling any rule in this dimension zero-cost — a built-in field with dead literals is the most expensive kind of false pass, because nothing downstream flags it.

---

## Dimension 4 — Keptn Project / Quality Gate

Zones built around Keptn CI/CD projects and their stages, used for quality gate evaluation and performance testing.

**Rule signals:**
- `SERVICE_TAGS` matching `keptn_project:<name>` and/or `keptn_stage:<stage>`

**Naming signals:** name starts with `Keptn:` followed by project name and optional stage (e.g. `Keptn: sockshop dev`, `Keptn: dynatrace qualitygate`)

**Gen3 migration path:** If Keptn sets `keptn_project` tags at the source (via OTEL resource attributes), they flow through as `primary_tags.keptn_project`. If not, add them explicitly via Option B (OTEL resource attributes) — the most natural approach for Keptn-instrumented services.

---

## Dimension 5 — Synthetic / Load Testing

Zones grouping synthetic monitoring, browser monitors, and load test infrastructure.

**Rule signals:**
- `KUBERNETES_CLUSTER_NAME` containing `synthetic` or `loadtest`
- `BROWSER_MONITOR_TAGS` conditions
- Tag-based matching for synthetic node entities

**Naming signals:** name contains `Synthetic`, `loadtest`, `load-test`, or `e2e-load`

**Gen3 migration path:** Verify whether Gen3 Segments support direct scoping of browser monitor entities and synthetic nodes. This dimension may require specific Gen3 Synthetic feature support before migration — assess readiness before committing to a migration approach.

---

## Dimension 6 — Cloud Provider / Infrastructure

Zones scoping entities by the underlying cloud platform rather than by application ownership.

**Rule signals:**
- `HOST_CLOUD_TYPE` enum (`AZURE`, `EC2`, `GOOGLE_CLOUD_PLATFORM`)
- Cloud-provider-prefixed tags: `[AWS]...`, `[GCP]...`, `[Azure]...`

**Naming signals:** cloud provider or region appears in the name (e.g. `AWS`, `Google Cloud`, `Azure`, `Virginia`, `Hong Kong Azure`)

**Gen3 migration path:** `aws.account.id`, `aws.region`, `azure.subscription`, `azure.resource.group`, and `gcp.project.id` are all built-in primary Grail fields — no source-side tagging required. Build Segment filters directly on these fields. A rule keyed on `HOST_CLOUD_TYPE` rather than on an account maps to `cloud.provider`, whose live values are lowercase short names (`aws`, `azure`, `gcp`) — the classic enum (`EC2`, `AZURE`, `GOOGLE_CLOUD_PLATFORM`) must be translated, not ported. Cloud-origin tags in MZ conditions (`[AWS]...`) have no source-side migration equivalent and will not match any auto-tagging rule during cross-reference analysis.

---

## Dimension 7 — Metric / Entity Selector Rules

Zones using `DIMENSION` or `SELECTOR` rule types rather than standard ME attribute matching.

**Rule signals:**
- At least one rule with `type: DIMENSION` (metric dimension filter)
- At least one rule with `type: SELECTOR` (Entity Selector expression)

**Naming signals:** varies — often test, experimental, or platform-internal zones. No reliable naming pattern.

**Gen3 migration path:**
- `DIMENSION` rules filter metrics by metric key — no source-side tagging equivalent. Use Grail metric filters in DQL queries or OpenPipeline metric enrichment.
- `SELECTOR` rules may contain `tag("...")` references (extract and handle as for `_TAGS` conditions) or use non-tag entity attributes — handle each attribute per its type.

> **Classify these zones first.** Dimension 7 zones cannot be migrated via source-side tagging alone and require a separate OpenPipeline or query-level approach. Identifying them early prevents surprises during the main migration wave.

---

## Classification algorithm

For each management zone:

1. Check each of the 7 dimensions in order.
2. A zone matches a dimension if its rules or name match the signals for that dimension.
3. Record all matching dimensions — a zone may appear in multiple.
4. If `rules` is empty and no dimension matches: classify as "empty / manual-only".
5. If rules exist but no dimension matches: classify as "unclassified" — list for manual review.

## Prioritising migration using the classification

**This file is read-only.** Every command here reads configuration; nothing creates, edits, or deletes a Segment, bucket, policy, or zone. Never bulk-translate zones 1:1, and never generate a script to do so — several decisions are organizational and belong to the customer.

**A dimension sets the order in which zones are examined, not a batch to convert together.** Work one zone at a time. Two zones in Dimension 3 share a classification but may have very different enrichment states, propagation flags, and organizational contexts — treat each as its own migration, following the procedure in [management-zones.md](management-zones.md).

**Step 1 — Identify Dimension 7 zones first.** These zones need a non-standard path and risk blocking the wider migration if left for last.

**Step 2 — Examine Dimension 3 and 6 zones next, one at a time.** Both dimensions depend on built-in Grail fields that require zero source-side changes, making them the easiest candidates — but check each zone individually for truthy `*Propagation` flags before treating it as zero-cost (see Dimension 3 above).

**Step 3 — Examine Dimension 1, 2, and 4 zones, one at a time.** These depend on custom business tags that must be defined as `primary_tags.*`. See [autotagging.md](../autotagging/autotagging.md) for the delivery options — source-side (DT_TAGS, K8s annotation, OTEL), central enrichment configuration, or OpenPipeline. Rules that keyed off host groups, host names, or naming conventions are the natural fit for central enrichment configuration.

**Step 4 — Assess Dimension 5 zones.** Synthetic-specific migration depends on Gen3 Synthetic support availability — verify before committing.

## Related references

- [management-zones.md](management-zones.md) — management zone migration strategy and runbook
- [mz-export-schema.md](mz-export-schema.md) — export file structure (rule types, condition keys, tag formats)
- [analyze-exports.md](analyze-exports.md) — offline script to parse exports and cross-reference auto-tag rules
- [autotagging.md](../autotagging/autotagging.md) — source-side primary tag migration for auto-tagging rules
