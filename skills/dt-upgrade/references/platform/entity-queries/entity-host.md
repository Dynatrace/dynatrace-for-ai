# Host Migration Guide

Use this guide when the migration centers on `dt.entity.host` or host-related signal dimensions.

## Core mapping

| Classic | Smartscape |
| --- | --- |
| `dt.entity.host` | `dt.smartscape.host` |
| `HOST` node query | `smartscapeNodes HOST` |

## Common field migrations

- `entity.name` → `name`
- host tags in signal queries → `getNodeField(dt.smartscape.host, "tags")`
- host group data → host fields such as `dt.host_group.id`

## Relationship patterns

- host to service via `runs_on`
- host to VM via `runs_on`
- host to disk via `belongs_to`

## Important special case

`dt.entity.host_group` is not a Smartscape node type. Do not traverse to `HOST_GROUP`.

## Example

```dql
smartscapeNodes HOST
| filter `tags:environment`[syn_grail_log] == "bastion"
| fields entity.name = name, id
```

## Related references

- [special-cases.md](special-cases.md)
- [relationship-mappings.md](relationship-mappings.md)
- [examples.md](examples.md)
