# Migration Workflow

## Contents

- [Purpose](#purpose)
- [Required Input](#required-input)
- [Step-by-Step Process](#step-by-step-process)
- [Core Rules](#core-rules)
- [Signal and Event Rules](#signal-and-event-rules)
- [Tag Matching Rules](#tag-matching-rules)
- [Traverse Guidance](#traverse-guidance)
- [Output Expectations](#output-expectations)
- [When to Load More References](#when-to-load-more-references)

## Purpose

Use this workflow when converting classic or Gen2 entity-based DQL to Smartscape DQL.

This reference is based on the source prompt pack and keeps the same migration order, but reformats it for skill usage.

## Required Input

The minimum required input is the classic DQL query.

Infer the intent, timeframe, relationships, output shape, and likely Smartscape replacements from the query itself. If something cannot be confirmed from the mapping references, state the assumption explicitly.

## Step-by-Step Process

1. **Consult mappings first.** Do not skip this.
   - [type-mappings.md](type-mappings.md) — classic entity type to Smartscape node type and field mappings
   - [relationship-mappings.md](relationship-mappings.md) — valid edges per type
2. Detect the input pattern:
   - `fetch dt.entity.*`
   - `classicEntitySelector(...)`
   - signal query with `dt.entity.*` dimensions
   - event query using classic entity fields
3. Extract the important parts:
   - entity types
   - filters
   - relationships
   - projected fields
   - timeframe
4. Map types, fields, and edges using the reference files.
5. Build the Smartscape query with the appropriate primitives:
   - `smartscapeNodes`
   - `smartscapeEdges`
   - `traverse`
   - `filter`
   - `fields`, `fieldsAdd`, `fieldsRemove`
   - `getNodeField()` and `getNodeName()` only when needed
6. Validate the translation:
   - timeframe or topology lifetime changes
   - missing or unsupported fields
   - special cases such as host group or process group
7. Return the migrated query along with the mapping resolution and any open assumptions.

## Core Rules

- Node types are uppercase and unquoted: `smartscapeNodes HOST`
- Do **not** use `id_classic`; use Smartscape `id`
- Prefer `name` over `getNodeName()` when querying nodes directly
- `getNodeName()` accepts only an ID; do not pass a `type:` argument
- Avoid `entityAttr()` and `entityName()` in the migrated query; use direct fields or `getNodeField()` / `getNodeName()` as needed
- `| fields` removes all other fields; use `| fieldsAdd` if you need to preserve existing ones
- Prefer `dt.smartscape.<type>` dimensions in signal queries
- `smartscapeNodes` supports `from:` and `to:` for historical topology queries
- Add explicit assumptions when the exact Smartscape equivalent is unclear

## Signal and Event Rules

- Every `dt.entity.*` dimension in signal queries must be migrated to the correct `dt.smartscape.*` field
- This applies to:
  - `by:{}`
  - `filter`
  - `fieldsAdd`
  - `expand`
  - helper functions using entity dimensions
- Event fields migrate as follows:
  - `affected_entity_ids` → `smartscape.affected_entity.ids`
  - `affected_entity_types` → `smartscape.affected_entity.types`
  - `dt.source_entity.type` → `dt.smartscape_source.type`

## Tag Matching Rules

- Node queries:
  - classic `in(tags, "[CONTEXT]key:value")`
  - becomes `` `tags:renamedContext`[key] == "value" ``
- Signal queries:
  - use `getNodeField(dt.smartscape.<type>, "tags:<context>")[key] == "value"`

## Traverse Guidance

- Multiple targets:
  ```dql
  | traverse runs_on, {AWS_EC2_INSTANCE, AZURE_VM, GCP_VM_INSTANCE}
  ```
- Multiple edge types:
  ```dql
  | traverse {runs_on, belongs_to}, {AWS_AVAILABILITY_ZONE, AZURE_REGION}
  ```
- Chained traversal:
  - HOST → VM → DATACENTER

### `fieldsKeep`

`fieldsKeep` preserves source node fields through traversal. After traversal, `id` and `name` refer to the target node, and the source fields are available via `dt.traverse.history`.

```dql
smartscapeNodes CONTAINER
| traverse runs_on, HOST, direction:forward, fieldsKeep:name
| fieldsAdd
    containerName = dt.traverse.history[0][name],
    containerId = dt.traverse.history[0][id],
    hostId = id,
    hostName = name
```

### Preserving entities without relationships

Use `lookup` when you must preserve entities even if the traversal has no match.

```dql
smartscapeNodes HOST
| lookup [
    smartscapeNodes HOST
    | traverse runs_on, {AWS_EC2_INSTANCE, AZURE_VM, GCP_VM_INSTANCE}, direction:forward
    | traverse {runs_on, belongs_to}, {AWS_AVAILABILITY_ZONE, AZURE_REGION, GCP_ZONE}, direction:forward, fieldsKeep:name
    | fieldsAdd dataCenter = id, dataCenterName = name, host_id = dt.traverse.history[0][id]
    | fields host_id, dataCenter, dataCenterName
  ], sourceField:id, lookupField:host_id, fields:{dataCenter, dataCenterName}
| fields id,
    dataCenter = coalesce(dataCenter, "NO_DATACENTER"),
    dataCenterName = coalesce(dataCenterName, "No Data center")
```

## Output Expectations

Every final translation should include:

1. the Smartscape DQL in a code block
2. a **Mapping Resolution** section
3. open assumptions, if any

Suggested format:

```md
## Mapping Resolution

Applied mappings:
- dt.entity.container_group_instance → CONTAINER
- dt.entity.host → HOST

Applied edge mappings:
- CONTAINER runs_on HOST
```

## When to Load More References

- Load [dql-function-migration.md](dql-function-migration.md) when the hard part is a specific function or pattern
- Load [special-cases.md](special-cases.md) when the query mentions host group, process group, container group, or classic IDs
- Load [examples.md](examples.md) when you need a before/after template
