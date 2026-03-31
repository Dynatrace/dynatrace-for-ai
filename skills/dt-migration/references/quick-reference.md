# Quick Reference

Use this page as a compact cheat sheet during Smartscape migration.

## Core rules

- Use `smartscapeNodes`, `smartscapeEdges`, and `traverse` for topology queries
- Smartscape node `type` values are uppercase and unquoted in `smartscapeNodes`
- Prefer Smartscape dimensions (`dt.smartscape.<type>`) in signal queries
- Prefer direct node fields like `name`; use `getNodeName()` only when you only have an ID
- Use `getNodeField(dt.smartscape.<type>, "tags:<context>")[key] == "value"` for tag matching in signal queries
- Classic tag filter `in(tags, "[CONTEXT]key:value")` becomes `` `tags:renamedContext`[key] == "value" `` in node queries
- Do **not** use `id_classic`; use Smartscape `id`
- `| fields` drops other fields; use `| fieldsAdd` when you need to preserve them

## Traversal tips

- Multiple target types:
  ```dql
  | traverse runs_on, {AWS_EC2_INSTANCE, AZURE_VM, GCP_VM_INSTANCE}
  ```
- Multiple edge types:
  ```dql
  | traverse {runs_on, belongs_to}, {AWS_AVAILABILITY_ZONE, AZURE_REGION}
  ```
- Preserve source fields through traversal:
  ```dql
  | traverse runs_on, HOST, direction:forward, fieldsKeep:name
  ```
- Starting node after traversal:
  - `dt.traverse.history[0][id]`

## Event field updates

- `affected_entity_ids` → `smartscape.affected_entity.ids`
- `affected_entity_types` → `smartscape.affected_entity.types`
- `dt.source_entity.type` → `dt.smartscape_source.type`

## Common gotchas

### `getNodeName()` takes no `type:` argument

```dql-snippet
getNodeName(someId)
```

not:

```dql-snippet
getNodeName(someId, type: "HOST")
```

### Host group is not an entity

Do not traverse to `HOST_GROUP`. Use host fields like `dt.host_group.id` on `HOST`.

### All `dt.entity.*` dimensions must become `dt.smartscape.*`

Apply this everywhere in signal and event queries:

- `timeseries by:{}`
- `filter`
- `fieldsAdd`
- `expand`
- `summarize by:{}`

### `references` is for static edges

Use `references[...]` when the relationship is static. Use `traverse` for general navigation.

### `smartscapeNodes` supports `from:` and `to:`

Use historical topology when the classic query has an explicit timeframe.

## Where to go next

- Full mappings: [type-mappings.md](type-mappings.md)
- Full edges: [relationship-mappings.md](relationship-mappings.md)
- Function migration: [dql-function-migration.md](dql-function-migration.md)
- Examples: [examples.md](examples.md)
