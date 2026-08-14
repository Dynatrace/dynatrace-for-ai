# DQL Function and Pattern Migration

Use this reference when the migration is driven by a classic DQL construct rather than by a single entity type.

## Contents

- [`entityName()`](#entityname)
- [`entityAttr()`](#entityattr)
- [`classicEntitySelector()`](#classicentityselector)
- [Classic relationship fields](#classic-relationship-fields)
- [Signal dimensions](#signal-dimensions)
- [Event fields](#event-fields)
- [Classic IDs](#classic-ids)

## `entityName()`

### Typical replacements

- When querying Smartscape nodes directly, prefer `name`
- When you only have an ID in a signal or edge query, use `getNodeName(id)`

### Examples

```dql
fetch dt.entity.host
| fields entity.name, id
```

becomes:

```dql
smartscapeNodes HOST
| fields entity.name = name, id
```

If the migrated query works on edge records or signal dimensions:

```dql-snippet
| fields target_name = getNodeName(target_id)
```

### Important rule

`getNodeName()` accepts only an ID. Do not pass a `type:` argument.

## `entityAttr()`

### Typical replacements

- Prefer a direct node field when Smartscape exposes one
- Otherwise use `getNodeField(id_or_dimension, "field")`

### Example

Classic signal-style tag access often appears as:

```dql-snippet
| filter in(entityAttr(dt.entity.aws_lambda_function, "tags"), "[AWS]dt_owner_team:team-mirage")
```

Smartscape form:

```dql-snippet
| filter getNodeField(dt.smartscape.aws_lambda_function, "tags:aws")[dt_owner_team] == "team-mirage"
```

## `classicEntitySelector()`

### Migration strategy

1. Parse the selector for the constrained entity and relationships
2. Start from the constrained side if possible
3. Convert selector filters to Smartscape node filters
4. Replace `fromRelationship.*` and `toRelationship.*` with `traverse`

### Example without relationships

```dql
fetch dt.entity.host
| filter in(id, classicEntitySelector("type(host),tag([Environment]syn_grail_log:bastion)"))
| fields entity.name, id
```

becomes:

```dql
smartscapeNodes HOST
| filter `tags:environment`[syn_grail_log] == "bastion"
| fields entity.name = name, id
```

### Example with relationships

```dql
fetch dt.entity.service
| filter in(id, classicEntitySelector("type(service), fromRelationship.runsOnHost(type(host), tag([Azure]dt_owner_email:team-ops@example.com))"))
| fields id, entity.name
```

becomes:

```dql
smartscapeNodes HOST
| filter `tags:azure`[dt_owner_email] == "team-ops@example.com"
| traverse runs_on, SERVICE, direction:backward
| fields id, entity.name = name
```

## Classic relationship fields

Classic entity queries often expose relationships as projected fields such as:

- `belongs_to[...]`
- `runs[...]`
- `instance_of[...]`
- `clustered_by[...]`

### Typical replacements

- Use `traverse` for relationship navigation
- Use `smartscapeEdges` when the result should be an edge-centric record set
- Use `references[...]` for static edges when simple field access is enough

### `references[...]`

Use `references` only for static edges.

Example:

```dql
fetch dt.entity.network_interface
| fieldsAdd host = belongs_to[dt.entity.host]
```

becomes:

```dql
smartscapeNodes NETWORK_INTERFACE
| fieldsAdd host = references[belongs_to.host]
```

## Signal dimensions

Every classic entity dimension in signal queries must be migrated.

### Rule

- `dt.entity.host` → `dt.smartscape.host`
- `dt.entity.service` → `dt.smartscape.service`
- `` `dt.entity.os:service` `` → `dt.smartscape.os_service`

Apply this rule everywhere in the signal query, not only in the main `by` clause.

### Example

```dql
timeseries avg(dt.service.request.response_time),
  by:{ dt.entity.service }
```

becomes:

```dql
timeseries avg(dt.service.request.response_time),
  by:{ dt.smartscape.service }
```

## Event fields

Use these field migrations in Davis event queries:

| Classic field | Smartscape field |
| --- | --- |
| `affected_entity_ids` | `smartscape.affected_entities` (project IDs with `smartscape.affected_entities[][id]`) |
| `affected_entity_types` | `smartscape.affected_entities` (project types with `smartscape.affected_entities[][type]`) |
| `dt.source_entity.type` | `dt.smartscape_source.type` |

The same applies to `related_entity_ids` and `related_entity_types`, which become
`smartscape.related_entities`.

### Record array access

`smartscape.affected_entities` is a `record[]`; each record has an `id`, `type`, and `name`. A
single record array replaces the two parallel arrays, which also removes the old caveat that the
ID and type arrays were not ordered the same way — each record now carries its own matching type.

How you access a member depends on whether the query expands the array first:

| Context | Accessor | Result |
| --- | --- | --- |
| No preceding `expand` | `smartscape.affected_entities[][id]` | array of IDs |
| After `expand smartscape.affected_entities` | `smartscape.affected_entities[id]` | one scalar ID per row |

Writing `smartscape.affected_entities[id]` **without** a preceding `expand` returns `null`
silently — no error is raised, so the query appears to work while dropping every value.

Two further rules follow from the array shape:

- **`join` needs `expand`.** A join key that is still an array matches nothing.
- **`filter` cannot take a bare iterative expression.** Wrap the comparison in `iAny(...)`.
  Because `id` is a `smartscapeId`, convert it with `toString()` before comparing it to a string;
  `type` and `name` are plain strings and need no conversion. Example, filtering the un-expanded
  array directly (no `expand` needed here):

```dql
fetch dt.davis.events
| filter iAny(toString(smartscape.affected_entities[][id]) == "HOST-8CBE06F58F5E99DA")
```

Note: The format of smartscape entity ids on events/problems changed.
Queries might be still using the old formats, e.g., 
`smartscape.affected_entity.ids`, `smartscape.affected_entity.types`, `smartscape.related_entity.ids`,`smartscape.related_entity.types`.
These are deprecated.

```dql
// Old: two parallel arrays, types not aligned with ids
fetch dt.davis.events
| filter isNotNull(smartscape.affected_entity.ids)
| filter in(smartscape.affected_entity.types, "SERVICE")
| expand smartscape.affected_entity.ids
```

```dql
// New: one record array, each record carries its own type
fetch dt.davis.events
| filter isNotNull(smartscape.affected_entities)
| expand smartscape.affected_entities
| fieldsAdd
    entityId = smartscape.affected_entities[id],
    entityType = smartscape.affected_entities[type]
| filter entityType == "SERVICE"
```

### Important value rule

When the field contains entity types, use uppercase Smartscape type values such as `HOST`, `SERVICE`, or `CONTAINER`, not classic values like `dt.entity.host`.

## Classic IDs

Classic entity IDs do not automatically carry over to Smartscape.

### Rule

- `id_classic` is valid **only inside a `smartscapeNodes` lookup predicate** to resolve a classic ID to its Smartscape equivalent
- do not use `id_classic` as an output field or join key in signal queries
- once you have the Smartscape ID, wrap it with `toSmartscapeId()` in signal filters

### Lookup query

Use the variadic `in()` form to resolve one or more classic IDs in a single query:

```dql
smartscapeNodes "*" | filter in(id_classic, {"$classic-id-placeholder"}) | fields id, id_classic, name, type
```

Replace `$classic-id-placeholder` with the actual classic entity ID (e.g. `HOST-8CBE06F58F5E99DA`). For multiple IDs, add them as additional arguments: `in(id_classic, {"A", "B", "C"})`.

When the entity type changes (e.g. `CLOUD_APPLICATION-xxx` → `K8S_DEPLOYMENT-yyy`), the lookup is mandatory because the new ID has a different prefix — `toSmartscapeId("CLOUD_APPLICATION-xxx")` does not resolve to the correct Smartscape node.

### Usage in signal filter

```dql-snippet
| filter in(dt.smartscape.host, { toSmartscapeId("HOST-ABC123") })
```
