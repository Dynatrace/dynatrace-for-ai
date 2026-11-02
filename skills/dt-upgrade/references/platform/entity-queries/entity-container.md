# Container Migration Guide

Use this guide when the migration centers on `dt.entity.container_group_instance` or `dt.entity.container_group`.

## Core mapping

| Classic | Smartscape |
| --- | --- |
| `dt.entity.container_group_instance` | `dt.smartscape.container` |
| `CONTAINER` node query | `smartscapeNodes CONTAINER` |

## Container-group special case

`dt.entity.container_group` is not a standalone Smartscape node.

When the old query projects container-group identifiers or names, preserve the output shape with `null` if there is no real equivalent.

## Common field migrations

- `entity.name` → `name`
- `containerizationType` → `container.containerization_type`
- classic affected-entity event joins → `smartscape.affected_entity.ids` and `smartscape.affected_entity.types`

## Relationship patterns

- `CONTAINER runs_on HOST`
- `CONTAINER runs_on K8S_NODE`
- `CONTAINER is_part_of K8S_POD`
- `CONTAINER belongs_to K8S_NAMESPACE`
- `CONTAINER belongs_to K8S_CLUSTER`

## Example

```dql
smartscapeNodes CONTAINER
| fields
    id,
    containerName = name,
    containerizationType = container.containerization_type,
    containerGroupId = null,
    containerGroupName = null
```

## Related references

- [special-cases.md](special-cases.md)
- [examples.md](examples.md)
- [relationship-mappings.md](relationship-mappings.md)
