# Service Migration Guide

Use this guide when the migration centers on `dt.entity.service` or service-related signal dimensions.

## Core mapping

| Classic | Smartscape |
| --- | --- |
| `dt.entity.service` | `dt.smartscape.service` |
| `SERVICE` node query | `smartscapeNodes SERVICE` |

## Common migration patterns

- `entity.name` → `name`
- service signal dimension `dt.entity.service` → `dt.smartscape.service`
- classic selectors constrained by host or process often become `traverse runs_on, SERVICE, direction:backward`
- `id` stays the same yet needs to be converted in a DQL to `toSmartscapeId("$id")`, where `$id` is replaced with the actual id

## Signal filter with hardcoded service ID

Both the inline `filter:` form inside `timeseries` and the pipe `| filter` form use the same pattern:

```
# before
| filter in(dt.entity.service, {"SERVICE-ID"})
filter: in(dt.entity.service, {"SERVICE-ID"})

# after
| filter in(dt.smartscape.service, { toSmartscapeId("SERVICE-ID") })
filter: in(dt.smartscape.service, { toSmartscapeId("SERVICE-ID") })
```

## Common relationships

- `SERVICE runs_on HOST`
- `SERVICE runs_on PROCESS`
- `SERVICE runs_on CONTAINER`
- `SERVICE calls SERVICE`

## Example

```dql
smartscapeNodes HOST
| filter `tags:azure`[dt_owner_email] == "team-ops@example.com"
| traverse runs_on, SERVICE, direction:backward
| fields id, entity.name = name
```

## Related references

- [relationship-mappings.md](relationship-mappings.md)
- [dql-function-migration.md](dql-function-migration.md)
- [examples.md](examples.md)
