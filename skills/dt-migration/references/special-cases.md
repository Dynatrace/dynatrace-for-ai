# Special Cases

Use this reference before translating classic entity patterns literally. Several classic entity concepts are not modeled as standalone Smartscape node types.

## Contents

- [Host group](#host-group)
- [Process group](#process-group)
- [Container group](#container-group)
- [Classic IDs](#classic-ids)
- [Missing or planned mappings](#missing-or-planned-mappings)

## Host group

`dt.entity.host_group` is not a separate Smartscape entity.

### What to do instead

- query `HOST`
- use host fields such as `dt.host_group.id`
- if the classic query expects a host-group ID that no longer exists as a standalone entity, preserve the output shape with `null` or use the host-group name if grouping still requires a value

### Example

Classic:

```dql
fetch dt.entity.host
| fields id, entity.name, hostGroupName
```

Smartscape:

```dql
smartscapeNodes HOST
| fields id, entity.name = name, hostGroupName = `dt.host_group.id`
```

## Process group

`dt.entity.process_group` is not a separate Smartscape entity.

### What to do instead

- query `PROCESS`
- use `dt.process_group.id`, `dt.process_group.name`, or `dt.process_group.detected_name`
- summarize if you need one row per process group rather than one row per process

### Example

Classic:

```dql
fetch dt.entity.process_group
| fields id, entity.name, metadata
```

Smartscape:

```dql
smartscapeNodes PROCESS
| summarize by:{ id = dt.process_group.id, entity.name = dt.process_group.detected_name }, process.metadata = takeAny(process.metadata)
```

## Container group

`dt.entity.container_group` is not a separate Smartscape entity.

### What to do instead

- treat `dt.entity.container_group_instance` as `CONTAINER`
- when the classic query asks for container-group identity or name, preserve the output shape with `null` placeholders if there is no real Smartscape equivalent

### Example

Classic:

```dql
fetch dt.entity.container_group_instance
| fields
    id,
    containerGroupId = instance_of[dt.entity.container_group],
    containerGroupName = entityName(instance_of[dt.entity.container_group], type:"dt.entity.container_group")
```

Smartscape:

```dql
smartscapeNodes CONTAINER
| fields
    id,
    containerGroupId = null,
    containerGroupName = null
```

## Classic IDs

Classic entity IDs do not carry over automatically to Smartscape IDs. The suffix changes.

### Rules

- do not reuse classic entity IDs blindly
- do not use `id_classic`
- use Smartscape `id`
- if the correct Smartscape ID is unknown, add an explicit assumption and a lookup hint

Example lookup hint:

```dql
smartscapeNodes HOST
| fields id, name
```

## Missing or planned mappings

The mapping table distinguishes between:

- **available** — direct mapping is already known
- **planned** — a Smartscape replacement is expected but may not be fully usable yet
- **missing** or **unclear** — direct replacement is not confirmed
- **not planned** — do not expect a direct Smartscape entity replacement

### Guidance

- If the mapping is **available**, translate directly.
- If the mapping is **planned**, translate cautiously and call out the assumption.
- If the mapping is **missing** or **unclear**, avoid pretending the mapping is certain.
- If the mapping is **not planned**, work around it with fields, placeholders, or a different starting entity.

## Related references

- [type-mappings.md](type-mappings.md) — full table and status values
- [entity-host.md](entity-host.md) — host and host-group migration patterns
- [entity-process.md](entity-process.md) — process-group-instance and process-group patterns
- [entity-container.md](entity-container.md) — container migration patterns
