# Dashboard Variables

Variables are dashboard parameters that can be referenced in tile queries. They
provide dynamic filtering and parameterization capabilities across multiple
tiles.

## Variable Definition

Variables are defined in the `content.variables` array of the dashboard JSON.

Use this dashboard wrapper format:

```json
{
  "name": "My Dashboard",
  "type": "dashboard",
  "content": {
    "version": 21,
    "variables": [
      {
        "version": 2,
        "key": "ServiceFilter",
        "type": "query",
        "visible": true,
        "editable": true,
        "input": "smartscapeNodes SERVICE | fields name",
        "multiple": false
      }
    ],
    "tiles": {},
    "layouts": {}
  }
}
```

## Required Properties

All dashboard variables must include these properties:

### Universal Required Properties

| Property | Type | Description |
| --------- | ------- | ---------------------------------------- |
| `key` | string | Variable identifier used in queries as `$key` |
| `type` | string | Variable type discriminator |
| `visible` | boolean | Show in dashboard UI variable picker |
| `editable` | boolean | Allow users to change value in UI |

**Example values for `key`:** `"ServiceFilter"`, `"ClusterName"`,
`"Environment"`

**Example values for `type`:** `"query"`, `"text"`, `"csv"`

**Example values for `visible` and `editable`:** `true`, `false`

### Type-Specific Required Properties

#### For `type: "query"` Variables

Query variables are dynamically populated by executing a DQL query.

| Property | Type | Description |
| --------- | ------- | ------------------------------------------ |
| `input` | string | DQL query that generates variable values |
| `version` | number | Query variable schema version (`1` or `2`) |
| `multiple` | boolean | Allow multiple value selection |

**Recommended**: Use `version: 2` for new dashboards (supports advanced DQL
features).

#### For `type: "text"` Variables

Text variables allow users to enter arbitrary text values.

| Property | Type | Description |
| --------- | ------- | --------------------------------------------- |
| `version` | number | Text variable schema version (typically `1`) |

#### For `type: "csv"` Variables

CSV variables provide a static comma-separated list of possible values.

| Property | Type | Description |
| --------- | ------- | --------------------------------------------- |
| `input` | string | Comma-separated list of values |
| `version` | number | CSV variable schema version (typically `1`) |
| `multiple` | boolean | Allow multiple value selection |

### Optional Properties

| Property | Type | Applies To |
| --------------- | ---------------- | ----------- |
| `defaultValue` | string or array | All types |

**Description:** Default value(s) when dashboard loads

Robust reasonable default values (strongly preferred):
- For `type: "query"` or type `csv`, if `multiple: true`, use dynatrace magic token "3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*" which will select all options
- For `type: "query"` or type `csv`, if `multiple: false`, do not define `defaultValue` property (first value will be selected by default). Do NOT use the magic token in this case.
- For `type: "text"`: do not define `defaultValue` property or use an empty string "" to match any text. Do NOT use "*" or magic token.

Alternative default values (use only if necessary, double-checked and confirmed working):
- For `type: "query"` or type `csv`, if `multiple: true`, use array of strings which are subset of values returned by the query
- For `type: "query"` or type `csv`, if `multiple: false`, use one of the values returned by the query
- For `type: "text"`: Use a string which represents reasonable filtering and does not produce empty dashboard

## Variable Types

### Query Variables (`type: "query"`)

Dynamic variables populated by executing a DQL query. Most common type in
production dashboards.

**IMPORTANT: Validation requirement (must check):** Before using a query variable in
tiles, verify that the variable query actually returns rows in the target
environment and that the referenced field(s) exists in the data. If the
query returns no rows (for example due to non-existing field), the variable resolves to
no values, the dashboard is considered invalid and cannot be deployed.

**CRITICAL CONSTRAINT**: Query must return **exactly one field**. Multiple
fields will interleave values in the dropdown (broken).

✅ **Correct:**

```dql
smartscapeNodes SERVICE | fields name | sort name asc
```

❌ **Wrong (returns 2 fields):**

```dql
smartscapeNodes SERVICE | fields id, name | sort name asc
// Result: SERVICE-123, BookingService, SERVICE-345, PaymentService
// (useless!)
```

**Minimal Query Variable (Single Selection):**

```json
{
  "version": 2,
  "key": "Service",
  "type": "query",
  "visible": true,
  "editable": true,
  "input": "smartscapeNodes SERVICE | fields name | sort name asc",
  "multiple": false
}
```

**Query Variable (Multiple Selection):**

```json
{
  "version": 2,
  "key": "Services",
  "type": "query",
  "visible": true,
  "editable": true,
  "input": "smartscapeNodes SERVICE | fields name | sort name asc",
  "multiple": true,
  "defaultValue": "3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*"
}
```

**Hidden Query Variable:**
This variable is not visible to the user but can be still used in the tile queries.
```json
{
  "version": 2,
  "key": "ClusterID",
  "type": "query",
  "visible": false,
  "editable": true,
  "input": "smartscapeNodes K8S_CLUSTER | filter name==$Cluster | fields id",
  "multiple": false
}
```

### Text Variables (`type: "text"`)

Simple text input variables where users enter arbitrary text values.

```json
{
  "version": 1,
  "key": "Threshold",
  "type": "text",
  "visible": true,
  "editable": true,
  "defaultValue": ""
}
```

### CSV Variables (`type: "csv"`)

Static list of predefined values. Useful when values don't change or don't
come from data sources.

⚠️ **CSV variables are error-prone.** The hardcoded values must exactly match
real values in the data. If they don't, tile queries using the variable will
silently return empty results, producing blank dashboard tiles. **Prefer
`type: "query"` variables** when the values come from live data. Only use CSV
for well-known, stable enumerations (e.g. log levels).

```json
{
  "version": 1,
  "key": "Status",
  "type": "csv",
  "visible": true,
  "editable": true,
  "input": "WARN,ERROR,INFO,NONE",
  "multiple": true,
  "defaultValue": "3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*"
}
```

**When to use:**

- Static enumerations (log levels, environments, regions)
- Small, unchanging value sets
- Faster than query variables (no query execution)

**Usage in query:**

```dql-template
fetch logs | filter in(loglevel, array($Status))
```

## Variable Reference Syntax

Variables are referenced in tile queries using the **`$VariableName` syntax**
(using the `key` property value).

### Basic Usage

**Single-select variables:**

```dql-template
fetch logs | filter host.name == $Host
```

**Multi-select variables:**

```dql-template
fetch logs | filter in(host.name, array($Host))
```

| Variable Type | Query Pattern |
| -------------- | ------------------------------- |
| Single-select | `field == $Variable` |
| Multi-select | `in(field, array($Variable))` |

**Use cases:**

- **Single-select:** Exact match for one value
- **Multi-select:** Match any of selected values

### Variable Replacement Strategies

By default, variable values are wrapped in double quotes. Use replacement
strategies to control quoting behavior:

| Strategy | Syntax | Wrapping |
| ------------ | ---------------------- | -------------- |
| Default | `$varName` | `"value"` |
| No quote | `$varName:noquote` | `value` |
| Backtick | `$varName:backtick` | `` `value` `` |
| Triple quote | `$varName:triplequote` | `"""value"""` |

**Use cases:**

- **Default:** Strings, entity names
- **No quote:** Numbers, units, functions
- **Backtick:** Field identifiers
- **Triple quote:** Raw JSON content

**Examples:**

| Strategy | Example Query |
| ------------ | -------------------------------------------- |
| Default | `filter service == $Service` |
| No quote | `limit $TopN:noquote` |
| Backtick | `fields $FieldName:backtick` |
| Triple quote | `parse content, $Schema:triplequote` |

**Detailed examples:**

```dql-template
// Default: strings
fetch logs | filter service.name == $Service
// Result: filter service.name == "payment-service"
```

```dql-template
// No quote: numbers
fetch logs | limit $TopN:noquote
// Result: limit 100
```

```dql-template
// Backtick: field names
fetch logs | fields $FieldName:backtick
// Result: fields `host.name`
```

```dql-template
// Triple quote: raw content
fetch logs | parse content, $JsonSchema:triplequote
// Result: parse content, """{"type":"object"}"""
```

## Common Variable Patterns

### Pattern 1: Entity Selector Variable (Single-Select)

```json
{
  "version": 2,
  "key": "Host",
  "type": "query",
  "visible": true,
  "editable": true,
  "input": "smartscapeNodes HOST | fields name | sort name asc",
  "multiple": false
}
```

**Usage:** `fetch logs | filter host.name == $Host`

**Multi-select alternative:** Set `"multiple": true` (omit `defaultValue`
or list specific values), then use `filter in(host.name, array($Host))` in
queries.

### Pattern 2: Tag Filter Variable (Single-Select)

```json
{
  "version": 2,
  "key": "Environment",
  "type": "query",
  "visible": true,
  "editable": true,
  "input": "<DQL query - see below>",
  "multiple": false
}
```

**DQL query for `input`:**

```dql
data record(tags = "*")
| append [
  smartscapeNodes SERVICE
  | expand tags
  | filter startsWith(tags, "env:")
  | sort tags asc
]
```

**Usage:** `smartscapeNodes SERVICE | expand tags | filter
matchesValue(tags, $Environment)`

**Multi-select alternative:** Set `"multiple": true` (set `defaultValue`
to `"3420b2ac-f1cf-4b24-b62d-61ba1ba8ed05*"`), then use `filter in(tags, array($Environment))` in
queries.

### Pattern 3: Numeric Limit Variable

```json
{
  "version": 2,
  "key": "TopN",
  "type": "query",
  "visible": true,
  "editable": true,
  "input": "<DQL query - see below>",
  "multiple": false,
  "defaultValue": "10"
}
```

**DQL query for `input`:**

```dql
data record(limit = 5), record(limit = 10), record(limit = 25),
record(limit = 50)
```

**Usage:** `fetch logs | summarize count(), by: {service.name} | sort count
desc | limit $TopN:noquote`

### Pattern 4: Static Enumeration Variable

```json
{
  "version": 1,
  "key": "LogLevel",
  "type": "csv",
  "visible": true,
  "editable": true,
  "input": "DEBUG,INFO,WARN,ERROR,FATAL",
  "multiple": true,
  "defaultValue": "ERROR"
}
```

**Usage:** `fetch logs | filter in(loglevel, array($LogLevel))`

## Variable Versions

| Version | Features |
| --------- | -------------------------------------------- |
| Version 1 | Basic DQL, `smartscapeNodes` (legacy) |
| Version 2 | Advanced DQL (`fetch`, `expand`, `summarize`) |

**Recommendations:**

- **Version 1:** Use for compatibility
- **Version 2:** **Use for new dashboards**

## Variable Dependencies

Variables can reference other variables in their definitions. When a dependency
changes, dependent variables recalculate automatically.

**Example:**

```json
[
  {
    "key": "Cluster",
    "type": "query",
    "input": "smartscapeNodes K8S_CLUSTER | fields name"
  },
  {
    "key": "Namespace",
    "type": "query",
    "input": "<DQL query - see below>"
  }
]
```

**DQL query for Namespace `input`:**

```dql-template
smartscapeNodes K8S_NAMESPACE
| filter belongs_to == $Cluster
| fields name
```

**Rules:**

- Dependent variable recalculates when dependency changes
- Loops are not allowed (A depends on B, B cannot depend on A)

## Limitations and Workarounds

| Limitation | Workaround |
| ------------------- | ----------------------------------- |
| **Duration types** | Use `duration()` with conversion |
| **Type mismatches** | Use DQL conversion functions |
| **URL size limit** | Keep variable values under 30 KB total |
| **Explore tiles** | Multi-select not supported |

**Duration types example:**

```dql-snippet
summarize by: {bin(timestamp, duration(toLong($resolution:noquote), unit:"m"))}, count()
```

**Type mismatches example:**

```dql-snippet
filter amount == toString($amount)
```

**URL size limit workaround:**

Split large variables or use shorter values

**Explore tiles workaround:**

Use single-select with `=` operator only

**Key points:**

- Variables return strings; convert for numeric/duration usage
- Variables defined at the dashboard level are available to all tiles within
  that dashboard. Each tile can reference any dashboard variable using the
  `$VariableName` syntax (where `VariableName` matches the `key` property) in
  its query.
