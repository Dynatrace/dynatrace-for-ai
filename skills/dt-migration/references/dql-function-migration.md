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
| `affected_entity_ids` | `smartscape.affected_entity.ids` |
| `affected_entity_types` | `smartscape.affected_entity.types` |
| `dt.source_entity.type` | `dt.smartscape_source.type` |

### Important value rule

When the field contains entity types, use uppercase Smartscape type values such as `HOST`, `SERVICE`, or `CONTAINER`, not classic values like `dt.entity.host`.

## Classic IDs

Classic entity IDs do not automatically carry over to Smartscape.

### Rule

- never use `id_classic`
- when comparing to a Smartscape ID literal, wrap it with `toSmartscapeId()`

Example:

```dql-snippet
| filter in(dt.smartscape.host, { toSmartscapeId("HOST-ABC123") })
```

### Open assumption pattern

If the classic query filters by a specific classic entity ID and the matching Smartscape ID is unknown, call that out as an assumption and tell the user how to look it up.

Example note:

```dql
// ASSUMPTION: Replace the old classic host ID with the matching Smartscape host ID.
// Look it up with:
smartscapeNodes HOST | fields id, name
```
