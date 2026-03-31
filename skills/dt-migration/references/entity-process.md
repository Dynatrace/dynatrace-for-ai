# Process Migration Guide

Use this guide when the migration centers on `dt.entity.process_group_instance` or `dt.entity.process_group`.

## Core mapping

| Classic | Smartscape |
| --- | --- |
| `dt.entity.process_group_instance` | `dt.smartscape.process` |
| `PROCESS` node query | `smartscapeNodes PROCESS` |

## Process-group special case

`dt.entity.process_group` is not a standalone Smartscape node.

Use fields on `PROCESS` instead:

- `dt.process_group.id`
- `dt.process_group.name`
- `dt.process_group.detected_name`

## Relationship patterns

- `PROCESS runs_on HOST`
- `PROCESS runs_on CONTAINER`
- `PROCESS calls PROCESS`

## Example

```dql
smartscapeNodes PROCESS
| summarize by:{ id = dt.process_group.id, entity.name = dt.process_group.detected_name }, process.metadata = takeAny(process.metadata)
```

## Related references

- [special-cases.md](special-cases.md)
- [relationship-mappings.md](relationship-mappings.md)
- [type-mappings.md](type-mappings.md)
