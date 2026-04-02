---
name: dt-migration
description: Migrate Dynatrace classic and Gen2 entity-based DQL, topology navigation, and classic entity selectors to Smartscape equivalents. Use this skill when users want to convert classic entities to Smartscape nodes, rewrite entityName, entityAttr, or classicEntitySelector patterns, or map old relationships to Smartscape traversal.
license: Apache-2.0
---

# Smartscape Migration Skill

This skill helps migrate Dynatrace classic and Gen2 entity-based DQL queries and query patterns to Smartscape-based equivalents.

Use it to:

- convert classic entity types to Smartscape node types
- rewrite classic entity DQL into Smartscape DQL
- migrate `entityName()`, `entityAttr()`, `classicEntitySelector()`, and classic relationship patterns
- explain how classic entity concepts map to Smartscape nodes, edges, fields, and IDs

Load the **dt-dql-essentials** skill before writing final DQL so the translated query also follows current DQL syntax rules.

This skill focuses on Smartscape-oriented DQL migration only. It does not cover asset-level migration workflows.

## Use Cases

Load this skill when the user wants to:

| Use case | What to do |
| --- | --- |
| Convert a classic entity query to Smartscape | Follow the migration workflow, use the mapping table, then load the relevant detailed references |
| Migrate `classicEntitySelector(...)` to Smartscape | Start from the constrained side, convert selector filters to node filters, and replace relationship selectors with `traverse` |
| Understand what a classic entity became in Smartscape | Check the entity mapping table and special cases before translating literally |
| Rewrite classic DQL functions such as `entityName()` or `entityAttr()` | Use the DQL construct guidance and function migration reference |
| Migrate classic topology navigation | Replace relationship fields and selectors with `smartscapeNodes`, `smartscapeEdges`, `traverse`, or `references` |
| Translate signal or event queries using `dt.entity.*` dimensions | Rewrite every entity dimension to the correct `dt.smartscape.*` field and adjust related helpers |

## Migration Workflow

Follow this order:

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
| `classicEntitySelector(...)` | node filters plus `traverse` | Start from the constrained side |
| `dt.entity.*` in signal queries | `dt.smartscape.*` | Applies to `by`, `filter`, `fieldsAdd`, `expand`, and related clauses |
| `belongs_to[...]`, `runs[...]`, `instance_of[...]` | `traverse` or `references[...]` | `references` works only for static edges |
| classic entity ID filters | Smartscape `id` | Do not reuse classic IDs blindly |
| `affected_entity_ids` and `affected_entity_types` | `smartscape.affected_entity.ids` and `smartscape.affected_entity.types` | Use Smartscape event fields |

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
- [references/migration-workflow.md](references/migration-workflow.md) — End-to-end migration process and output expectations
- [references/type-mappings.md](references/type-mappings.md) — Full classic-to-Smartscape type and field mappings
- [references/dql-function-migration.md](references/dql-function-migration.md) — How to migrate classic DQL functions and patterns
- [references/relationship-mappings.md](references/relationship-mappings.md) — Valid Smartscape edges and traversal guidance
- [references/special-cases.md](references/special-cases.md) — Non-literal and unsupported entity migrations
- [references/quick-reference.md](references/quick-reference.md) — Compact rules and gotchas
- [references/examples.md](references/examples.md) — Before/after migration examples
