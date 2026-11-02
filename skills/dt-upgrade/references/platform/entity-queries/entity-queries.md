# 2nd Gen Entity Queries

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

- **Situations 1 or 2** — load [mass-data-filtering-strategy.md](mass-data-filtering-strategy.md) and complete **all steps** including field discovery (Step 2) and equivalence verification (Step 4). Do not skip the `fieldsSnapshot` gates — they determine which approach is viable. Only fall back to the Migration Workflow below when the entity-type mapping or relationship traversal is needed to complete a Smartscape subquery.
- **Situation 3** — continue with the Migration Workflow and entity mapping table below.

> Note: Situation 3 has a sub-case where `classicEntitySelector` is used to filter the entities returned by `fetch dt.entity.*`. This is rare and follows the same `smartscapeNodes` path — resolve the selector conditions using [references/mass-data-filtering-strategy.md](mass-data-filtering-strategy.md) Step 1B, then apply them as node filters in `smartscapeNodes`.

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

For the full migration process and output expectations, load [migration-workflow.md](migration-workflow.md).

## Core Entity Mapping Table

Use this compact table first for common migrations. For the full mapping set, load [type-mappings.md](type-mappings.md).

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
| `dt.entity.synthetic_test` | `dt.smartscape.browser_monitor` | `BROWSER_MONITOR` | Browser monitor mapping |
| `dt.entity.synthetic_test_step` | `dt.smartscape.browser_monitor_step` | `BROWSER_MONITOR_STEP` | Individual step within a browser monitor |
| `dt.entity.http_check` | `dt.smartscape.http_monitor` | `HTTP_MONITOR` | HTTP monitor mapping |
| `dt.entity.http_check_step` | `dt.smartscape.http_monitor_step` | `HTTP_MONITOR_STEP` | Individual step within an HTTP monitor |
| `dt.entity.multiprotocol_monitor` | `dt.smartscape.network_availability_monitor` | `NETWORK_AVAILABILITY_MONITOR` | Network availability monitor mapping |
| `dt.entity.synthetic_location` | `dt.smartscape.synthetic_location` | `SYNTHETIC_LOCATION` | Synthetic location mapping |

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
| `affected_entity_ids` and `affected_entity_types` | `smartscape.affected_entity.ids` and `smartscape.affected_entity.types` | Use Smartscape event fields |

For the detailed function-by-function guide, load [dql-function-migration.md](dql-function-migration.md).

## Special Cases

Do not translate these patterns literally:

- **Host group** — no standalone Smartscape entity; use fields on `HOST`
- **Process group** — no standalone Smartscape entity; use fields on `PROCESS`
- **Container group** — no standalone Smartscape entity; preserve output shape with placeholders if needed
- **Classic IDs** — classic entity IDs do not carry over to Smartscape automatically
- **Planned, missing, or not-planned mappings** — check the full mapping table before assuming direct support

Load [special-cases.md](special-cases.md) before migrating these patterns.

## Entity-Focused Guides

When a migration centers on a specific entity family, load the matching detailed guide:

- [entity-host.md](entity-host.md)
- [entity-service.md](entity-service.md)
- [entity-process.md](entity-process.md)
- [entity-container.md](entity-container.md)
- [entity-kubernetes.md](entity-kubernetes.md)
- [entity-cloud-application.md](entity-cloud-application.md)
- [entity-synthetic.md](entity-synthetic.md)

Each guide explains:

- what the classic entity represented
- what the Smartscape replacement is
- which fields usually change
- how relationships are migrated
- common examples and pitfalls


## Reference Map

| File | When to use                                                                                                                |
| --- |----------------------------------------------------------------------------------------------------------------------------|
| [`mass-data-filtering-strategy.md`](mass-data-filtering-strategy.md) | The query filters mass data (timeseries/logs/metrics) by entity conditions — primary strategy guide for Situations 1 and 2 |
| [`auto-tagging-field-mapping.md`](auto-tagging-field-mapping.md) | Resolving a `tag(X)` filter from an auto-tagging rule — maps rule condition keys to semantic dictionary fields             |
| [`entity-selector-predicates.md`](entity-selector-predicates.md) | Looking up an unfamiliar predicate inside a `classicEntitySelector(...)` string                                            |
| [`migration-workflow.md`](migration-workflow.md) | You need the end-to-end migration process, validation checklist, and output structure                                      |
| [`type-mappings.md`](type-mappings.md) | You need the full classic-to-Smartscape entity and field mapping tables                                                    |
| [`dql-function-migration.md`](dql-function-migration.md) | You need to migrate `entityName()`, `entityAttr()`, selectors, relationship fields, signal dimensions, or ID filters       |
| [`relationship-mappings.md`](relationship-mappings.md) | You need to verify valid Smartscape edges and traversal targets                                                            |
| [`special-cases.md`](special-cases.md) | The query uses host group, process group, container group, or unsupported mappings                                         |
| [`quick-reference.md`](quick-reference.md) | You need a compact cheat sheet or gotcha list                                                                              |
| [`examples.md`](examples.md) | You need concrete before/after migration patterns                                                                          |
| [`entity-host.md`](entity-host.md) | The migration centers on hosts, host tags, host groups, or host traversal                                                  |
| [`entity-service.md`](entity-service.md) | The migration centers on services, service relationships, or service signal dimensions                                     |
| [`entity-process.md`](entity-process.md) | The migration centers on process-group-instance or process-group patterns                                                  |
| [`entity-container.md`](entity-container.md) | The migration centers on container-group-instance, container group, or affected-entity event joins                         |
| [`entity-kubernetes.md`](entity-kubernetes.md) | The migration centers on Kubernetes cluster, node, service, namespace, pod, or workload entities                           |
| [`entity-cloud-application.md`](entity-cloud-application.md) | The migration centers on `cloud_application`, `cloud_application_instance`, or `cloud_application_namespace`               |
| [`entity-synthetic.md`](entity-synthetic.md) | The migration centers on synthetic monitors (`synthetic_test`, `http_check`, `multiprotocol_monitor`), steps, or locations                        |

## Related Skills

- Load `dt-dql-essentials` before writing final DQL.

