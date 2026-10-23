# Dashboard Variables

Variables provide dynamic filtering across tiles. Defined in
`content.variables` array, referenced in queries as `$key`.

## Required Properties

| Property | Type | Description |
|----------|------|-------------|
| `key` | string | Identifier used as `$key` in queries |
| `type` | string | `"query"`, `"text"`, or `"csv"` |
| `visible` | boolean | Show in dashboard UI |
| `editable` | boolean | Allow users to change value |

## Variable Types

### Query Variables (`type: "query"`)

Dynamic values from DQL. Most common type.

```json
{
  "version": 2, "key": "Service", "type": "query",
  "visible": true, "editable": true,
  "input": "smartscapeNodes SERVICE | fields name | sort name asc",
  "multiple": false
}
```

**Critical:** Query must return **exactly one field**. Multiple fields break
the dropdown. Variable query MUST return at least one row — empty results
mean the dashboard is invalid.

**Getting distinct values for variable dropdowns:**
- For entity names: `smartscapeNodes SERVICE | fields name | sort name asc`
- For logs/events fields: `fetch logs | filter isNotNull(field) | filter field != "" | dedup field | fields field | sort field asc`
- Do **not** use `summarize by: {field}` without an aggregation; use `dedup field` for distinct values
- Filter out empty strings (`field != ""`) to avoid blank variable options and empty tile results

Multi-select with all-selected default:
```json
{
  "version": 2, "key": "Services", "type": "query",
  "visible": true, "editable": true,
  "input": "smartscapeNodes SERVICE | fields name | sort name asc",
  "multiple": true,
  "defaultValue": "3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*"
}
```

### Text Variables (`type: "text"`)

Free-form text input.

```json
{ "version": 1, "key": "Threshold", "type": "text",
  "visible": true, "editable": true, "defaultValue": "" }
```

### CSV Variables (`type: "csv"`)

Static predefined values. **Prefer `type: "query"` when values come from
live data** — CSV values must exactly match real data or tiles show blank.

```json
{ "version": 1, "key": "Status", "type": "csv",
  "visible": true, "editable": true,
  "input": "WARN,ERROR,INFO,NONE", "multiple": true,
  "defaultValue": "3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*" }
```

## Default Values

- **query/csv, `multiple: true`**: use magic token `"3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*"` to select all
- **query/csv, `multiple: false`**: omit `defaultValue` (first value auto-selected). Do NOT use magic token.
- **text**: omit or use `""`. Do NOT use `"*"` (passed literally into query).

## Query Reference Syntax

| Variable Config | Query Pattern |
|----------------|---------------|
| Single-select (`multiple: false`) | `field == $Variable` |
| Multi-select (`multiple: true`) | `in(field, array($Variable))` |

### Modifiers

| Modifier | Use for | Example |
|----------|---------|--------|
| default | String equality, multi-select | `field == $Var`, `in(field, array($Var))` |
| `:noquote` | Numeric/duration parameters | `limit $N:noquote`, `bin(timestamp, $Bin:noquote)` |
| `:backtick` | Field name in `by:{}` or `sort` | `by: {$GroupBy:backtick}` |
| `:triplequote` | String constants in `matchesPhrase()`, `contains()` | `matchesPhrase(content, $Search:triplequote)` |

**Do not double-wrap:** `:backtick` already adds backticks. Write `$GroupBy:backtick`, never `` `$GroupBy:backtick` ``.

For durations: `duration(toLong($Minutes:noquote), unit:"m")`.

## Variable Dependencies

Variables can reference other variables. Dependent variables recalculate when
dependencies change. Circular dependencies are not allowed.

```json
[
  { "key": "Cluster", "type": "query",
    "input": "smartscapeNodes K8S_CLUSTER | fields name" },
  { "key": "Namespace", "type": "query",
    "input": "smartscapeNodes K8S_NAMESPACE | filter k8s.cluster.name == $Cluster | fields name" }
]
```

## Version

Use `version: 2` for new dashboards (supports `fetch`, `expand`, `summarize`).
`version: 1` is legacy.

## Limitations

| Limitation | Workaround |
|-----------|-----------|
| Duration types | `duration()` with conversion: `bin(timestamp, duration(toLong($res:noquote), unit:"m"))` |
| Type mismatches | DQL conversion: `filter amount == toString($amount)` |
| URL size limit | Keep variable values under 30 KB total |
| Explore tiles | Multi-select not supported; use single-select with `=` |
