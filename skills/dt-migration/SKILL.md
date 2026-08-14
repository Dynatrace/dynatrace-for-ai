---
name: dt-migration
description: Migrate Dynatrace classic and Gen2 entity-based DQL to Smartscape equivalents. Covers three scenarios. (1) mass data queries filtered by classic entity conditions — migrate to direct dimension filters first, Smartscape only as fallback; (2) mass data queries using entity subqueries for filtering — same dimension-first strategy; (3) pure entity list queries — migrate fetch dt.entity.* to smartscapeNodes. Also handles entityName, entityAttr, classicEntitySelector, and classic relationship patterns.
license: Apache-2.0
---

# Smartscape Migration Skill

This skill migrates Dynatrace classic and Gen2 entity-based DQL queries and query patterns to Smartscape-based equivalents.

Load the **dt-dql-essentials** skill before writing final DQL so the translated query also follows current DQL syntax rules.

This skill focuses on Smartscape-oriented DQL migration only. It does not cover asset-level migration workflows.

## Query Purpose Classification

**Start here.** The correct migration strategy depends on what the query is actually trying to do — not just which classic constructs it uses.

There are three distinct situations:

| # | Situation | Classic anti-pattern | Migration strategy |
| --- | --- | --- | --- |
| 1 | Mass data query filtered by entity conditions | `classicEntitySelector(...)` inline in `filter:` of a timeseries, logs, or metrics query | Resolve entity conditions to raw data dimensions first. Smartscape is a fallback, not the default. |
| 2 | Mass data query using entity subquery for filtering | `fetch dt.entity.*` inside `in [...]`, `lookup [...]`, or `join [...]` to filter the outer mass data query | Same dimension-first strategy. Rewrite as raw dimension filter or `in [smartscapeNodes ...]` subquery. |
| 3 | Pure entity list query | `fetch dt.entity.*` used standalone or as the primary result source | `smartscapeNodes` is the only valid path. No raw dimension alternative exists. |

**Decision:**

- **Situations 1 or 2** — load [references/mass-data-filtering-strategy.md](references/mass-data-filtering-strategy.md) and complete **all steps** including field discovery (Step 2) and equivalence verification (Step 4). Do not skip the `fieldsSnapshot` gates — they determine which approach is viable. Only fall back to the Migration Workflow below when the entity-type mapping or relationship traversal is needed to complete a Smartscape subquery.
- **Situation 3** — continue with the Migration Workflow and entity mapping table below.

> Note: Situation 3 has a sub-case where `classicEntitySelector` is used to filter the entities returned by `fetch dt.entity.*`. This is rare and follows the same `smartscapeNodes` path — resolve the selector conditions using [references/mass-data-filtering-strategy.md](references/mass-data-filtering-strategy.md) Step 1B, then apply them as node filters in `smartscapeNodes`.

## Migration Workflow

Follow this order for **Situation 3** (pure entity list queries) and for constructing Smartscape subqueries in Situations 1 and 2:

1. Identify the classic input pattern:
   - `fetch dt.entity.*`
   - `classicEntitySelector(...)`
   - relationship field access such as `belongs_to[...]`, `runs[...]`, `instance_of[...]`
   - signal or event queries using `dt.entity.*`
2. Identify the involved classic entity types.
3. Look up the Smartscape replacement in the core entity mapping table below.
4. Check which classic DQL constructs need explicit migration.
5. Rewrite the query using Smartscape primitives:
   - `smartscapeNodes`
   - `smartscapeEdges`
   - `traverse`
   - `references`
   - `getNodeName()`
   - `getNodeField()`
6. Check for special cases, unsupported entities, or ID assumptions.
7. Load the matching detailed references for the specific entity family or migration pattern.

For the full migration process and output expectations, load [references/migration-workflow.md](references/migration-workflow.md).

## Core Entity Mapping Table

Use this compact table first for common migrations. For the full mapping set, load [references/type-mappings.md](references/type-mappings.md).

| Classic / Gen2 entity | Smartscape field | Smartscape node type | Notes |
| --- | --- | --- | --- |
| `dt.entity.host` | `dt.smartscape.host` | `HOST` | Standard host mapping |
| `dt.entity.service` | `dt.smartscape.service` | `SERVICE` | Standard service mapping |
| `dt.entity.process_group_instance` | `dt.smartscape.process` | `PROCESS` | Process instance maps directly |
| `dt.entity.container_group_instance` | `dt.smartscape.container` | `CONTAINER` | Container-group instance maps directly |
| `dt.entity.kubernetes_cluster` | `dt.smartscape.k8s_cluster` | `K8S_CLUSTER` | Kubernetes cluster |
| `dt.entity.kubernetes_node` | `dt.smartscape.k8s_node` | `K8S_NODE` | Kubernetes node |
| `dt.entity.kubernetes_service` | `dt.smartscape.k8s_service` | `K8S_SERVICE` | Kubernetes service |
| `dt.entity.cloud_application` | multiple workload fields | multiple K8S workload node types | Maps to multiple workload types; load the cloud-application guide |
| `dt.entity.cloud_application_instance` | `dt.smartscape.k8s_pod` | `K8S_POD` | Classic cloud app instance becomes pod |
| `dt.entity.cloud_application_namespace` | `dt.smartscape.k8s_namespace` | `K8S_NAMESPACE` | Namespace mapping |
| `dt.entity.application` | `dt.smartscape.frontend` | `FRONTEND` | Frontend application mapping |
| `dt.entity.aws_lambda_function` | `dt.smartscape.aws.lambda_function` | `AWS_LAMBDA_FUNCTION` | Cloud-function entity mapping |

## DQL Constructs to Inspect During Migration

These classic constructs usually need explicit rewriting:

| Classic construct | Typical Smartscape replacement | Notes |
| --- | --- | --- |
| `entityName(x)` | `name` or `getNodeName(x)` | Prefer `name` when querying nodes directly |
| `entityAttr(x, "...")` | direct node field or `getNodeField(x, "...")` | Prefer direct fields when available |
| `classicEntitySelector(...)` | node filters plus `traverse` | Start from the constrained side; for mass data queries see mass-data-filtering-strategy.md first |
| `dt.entity.*` in signal queries | `dt.smartscape.*` | Applies to `by`, `filter`, `fieldsAdd`, `expand`, and related clauses |
| `belongs_to[...]`, `runs[...]`, `instance_of[...]` | `traverse` or `references[...]` | `references` works only for static edges |
| classic entity ID filters | Smartscape `id` | Do not reuse classic IDs blindly |
| `affected_entity_ids` and `affected_entity_types` | `smartscape.affected_entities` | One record array replaces the two parallel arrays; each record has `id`, `type`, and `name` |

For the detailed function-by-function guide, load [references/dql-function-migration.md](references/dql-function-migration.md).

## Special Cases

Do not translate these patterns literally:

- **Host group** — no standalone Smartscape entity; use fields on `HOST`
- **Process group** — no standalone Smartscape entity; use fields on `PROCESS`
- **Container group** — no standalone Smartscape entity; preserve output shape with placeholders if needed
- **Classic IDs** — classic entity IDs do not carry over to Smartscape automatically
- **Planned, missing, or not-planned mappings** — check the full mapping table before assuming direct support

Load [references/special-cases.md](references/special-cases.md) before migrating these patterns.

## Entity-Focused Guides

When a migration centers on a specific entity family, load the matching detailed guide:

- [references/entity-host.md](references/entity-host.md)
- [references/entity-service.md](references/entity-service.md)
- [references/entity-process.md](references/entity-process.md)
- [references/entity-container.md](references/entity-container.md)
- [references/entity-kubernetes.md](references/entity-kubernetes.md)
- [references/entity-cloud-application.md](references/entity-cloud-application.md)

Each guide explains:

- what the classic entity represented
- what the Smartscape replacement is
- which fields usually change
- how relationships are migrated
- common examples and pitfalls

## References

- [references/README.md](references/README.md) — Reference index and reading guide
- [references/mass-data-filtering-strategy.md](references/mass-data-filtering-strategy.md) — **Start here for Situations 1 and 2.** Mandatory steps: resolve conditions, run fieldsSnapshot discovery, select approach, write query, verify equivalence
- [references/auto-tagging-field-mapping.md](references/auto-tagging-field-mapping.md) — Maps auto-tagging rule condition keys to semantic dictionary fields (mass data and Smartscape node attributes)
- [references/entity-selector-predicates.md](references/entity-selector-predicates.md) — Full predicate vocabulary for `classicEntitySelector` expressions
- [references/migration-workflow.md](references/migration-workflow.md) — End-to-end migration process and output expectations
- [references/type-mappings.md](references/type-mappings.md) — Full classic-to-Smartscape type and field mappings
- [references/dql-function-migration.md](references/dql-function-migration.md) — How to migrate classic DQL functions and patterns
- [references/relationship-mappings.md](references/relationship-mappings.md) — Valid Smartscape edges and traversal guidance
- [references/special-cases.md](references/special-cases.md) — Non-literal and unsupported entity migrations
- [references/quick-reference.md](references/quick-reference.md) — Compact rules and gotchas
- [references/examples.md](references/examples.md) — Before/after migration examples
