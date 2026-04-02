# Dashboard Tiles

Each tile displays content or data visualization. Tiles are stored in the
`tiles` object with numeric string keys.

## Tile Types

Dynatrace dashboards support four tile types: **data**, **code**,
**markdown**, and **slo**.

### Markdown Tiles

Markdown tiles display formatted text content. They are typically used for
headers, descriptions, and documentation within the dashboard.

```json
{
  "1": {
    "type": "markdown",
    "content": "# Section Header"
  }
}
```

**Properties:**

- `type`: Set to `"markdown"` (required)
- `content`: Markdown-formatted text content

### Data Tiles

Data tiles execute DQL queries and visualize results. These are the primary
tiles for displaying metrics, logs, and other observability data.

```json
{
  "19": {
    "type": "data",
    "title": "Tile Display Name",
    "query": "timeseries avg(metric), by:{dimension}",
    "visualization": "lineChart",
    "visualizationSettings": {},
    "querySettings": {}
  }
}
```

**Properties:**

- `type`: Set to `"data"` (required)
- `title`: Display title for the tile (shown at top of tile)
- `description`: Optional tile description
- `query`: DQL query executed against Grail
- `visualization`: Chart type for rendering (see Visualization Types below)
- `visualizationSettings`: Visual formatting options (colors, legends, axes)
- `querySettings`: Query execution parameters
- `customLinkSettings`: Custom link configuration
- `queryConfig`: Query configuration
- `davisCopilot`: Davis Copilot configuration
- `davis`: Davis AI configuration
- `timeframe`: Tile-specific timeframe settings
- `segments`: Tile-specific segment settings

### Code Tiles

Code tiles execute JavaScript code and display custom visualizations.

```json
{
  "5": {
    "type": "code",
    "title": "Custom Visualization",
    "input": "// JavaScript code here",
    "visualization": "lineChart",
    "visualizationSettings": {}
  }
}
```

**Properties:**

- `type`: Set to `"code"` (required)
- `title`: Display title for the tile
- `description`: Optional tile description
- `input`: Code input (JavaScript or other language)
- `visualization`: Visualization type for code tile output
- `visualizationSettings`: Visual formatting options
- `customLinkSettings`: Custom link configuration

### SLO Tiles

SLO tiles display Service Level Objective metrics and status.

```json
{
  "8": {
    "type": "slo",
    "title": "Payment Service SLO",
    "input": "slo-identifier-or-query",
    "visualizationSettings": {}
  }
}
```

**Properties:**

- `type`: Set to `"slo"` (required)
- `title`: Display title for the tile
- `description`: Optional tile description
- `input`: SLO identifier or query
- `visualizationSettings`: Visualization-specific settings for SLO display

## Common Tile Properties

### All Tile Types

- `type`: Tile type - must be one of: `"markdown"`, `"data"`, `"code"`, or
  `"slo"` (required)

## Visualization Types

Data tiles support various visualization types through the `visualization`
property. The visualization type determines which `visualizationSettings` are
available and how the query results are rendered.

### Time-Series Charts

These visualizations **require a time dimension** in the query result. Use
`timeseries` or `makeTimeseries` DQL commands to produce suitable data.

- `lineChart`: Line chart — plots values over time; optional categorical
  split via `by:{}`. Supports thresholds.
- `areaChart`: Area chart — filled area under line over time; optional
  categorical split via `by:{}`. Supports thresholds.
- `barChart`: Bar chart (time-series) — vertical bars over time; optional
  categorical split via `by:{}`. Supports thresholds.
- `bandChart`: Band chart — displays upper and lower bounds over time
  (e.g., min/max/avg bands). **Requires time dimension** and at least two
  numeric value columns for the band range. Supports thresholds.

**Required query result field types (lineChart, areaChart, barChart):**

| Slot | Accepted DQL types | Count |
|------|--------------------|-------|
| Time | `timestamp`, `timeframe` | exactly 1 |
| Interval | `duration` | exactly 1 (required when Values are numeric arrays from `timeseries`) |
| Values | `long`, `double`, `duration`, numeric `array` | 1 or more |
| Names (Optional, possibly several fields) | any | optional (0 or more) |

> **WARNING — `interval` field and timeseries visualizations:** When Values
> are numeric arrays produced by `timeseries`, the Dynatrace visualization
> engine requires the `interval` field (type `duration`) to interpret those
> arrays as plottable time-series data points. Without `interval`, the
> visualization classifies numeric arrays as unsuitable for the Values slot
> and shows **"Data not suitable"**. This is specific to line, area, bar,
> and band chart visualizations — other visualizations like `table` are
> unaffected. If you use `| fields` after `timeseries`, always include
> `interval` in the field list, or use `| fieldsAdd` instead to avoid
> stripping any fields.

**Required query result field types (bandChart):**

| Slot | Accepted DQL types | Count |
|------|--------------------|-------|
| Time | `timestamp`, `timeframe` | exactly 1 |
| Interval | `duration` | exactly 1 (required when Values are numeric arrays from `timeseries`) |
| Values | `long`, `double`, `duration`, numeric `array` | 1 or more |
| Names (Optional, possibly several fields) | any | optional (0 or more) |
| Band min values | numeric `array` (e.g. timeseries metric column) | exactly 1 |
| Band max values | numeric `array` (e.g. timeseries metric column) | exactly 1 |

### Categorical Charts

These visualizations work with **categorical (non-time) data**. Typically
produced by `summarize ... by:{field}` queries.

- `categoricalBarChart`: Categorical bar chart — groups by a non-time
  field. **No time dimension**; requires a categorical field and a numeric
  value. Supports thresholds.
- `pieChart`: Pie chart — proportional slices. Requires a categorical field
  (categories) and a numeric field (values).
- `donutChart`: Donut chart — like pie chart with a hollow center. Requires
  a categorical field (categories) and a numeric field (values).

**Required query result field types (categoricalBarChart, pieChart, donutChart):**

| Slot | Accepted DQL types | Count |
|------|--------------------|-------|
| Values | `long`, `double`, `duration` | 1 or more |
| Categories | any | 1 or more |

### Single Value & Gauge

These visualizations display **one or a few numeric values**. Queries should
return a single record with a numeric field, or a small number of records.

- `singleValue`: Single value — displays one prominent number with optional
  label, icon, and color thresholds. Query should return a single record
  with a numeric field. Supports thresholds.
- `meterBar`: Meter bar — horizontal bar showing a value within a min/max
  range. Requires a single numeric value. Configure `minValue` and
  `maxValue` in settings.
- `gauge`: Gauge — semicircular dial showing a value within a min/max
  range. Requires a single numeric value. Configure `minValue` and
  `maxValue` in settings.

**Required query result field types (singleValue):**

| Slot | Accepted DQL types | Count | Required |
|------|--------------------|-------|----------|
| Single value | any | exactly 1 | yes |
| Sparkline | numeric `array` | exactly 1 | no (optional) |

**Required query result field types (meterBar):**

| Slot | Accepted DQL types | Count |
|------|--------------------|-------|
| Meter value | `long`, `double`, `duration` | exactly 1 |

**Required query result field types (gauge):**

| Slot | Accepted DQL types | Count |
|------|--------------------|-------|
| Gauge value | `long`, `double`, `duration` | exactly 1 |

### Tabular & Raw

These visualizations display **records as rows** and work with any query
result shape.

- `table`: Table — tabular display of query results. Works with any data
  shape. Supports column formatting and sorting.
- `raw`: Raw — displays the raw JSON result of the query. Works with any
  data shape. Useful for debugging.
- `recordList`: Record list — lists individual records in a card-like
  format. Works with any data shape. Useful for log entries or event lists.

### Distribution & Status

- `histogram`: Histogram — shows frequency distribution of values. Requires
  numeric data that can be binned into ranges. Data mapping: range (bin
  width), values (count/frequency), names (series). Supports thresholds.
- `honeycomb`: Honeycomb — grid of hexagonal cells for status overview.
  Each cell represents an entity. Requires a value field (numeric or
  string) and a names field for cell labels. Good for host/service status
  views.

**Required query result field types (histogram):**

| Slot | Accepted DQL types | Count |
|------|--------------------|-------|
| Range | field with `start` and `end` (range object) | exactly 1 |
| Values | `long`, `double`, `duration` | exactly 1 |
| Names (Optional, possibly several fields) | any | optional (0 or more) |

**Required query result field types (honeycomb):**

| Slot | Accepted DQL types | Count |
|------|--------------------|-------|
| Values | `long`, `double`, `duration` | exactly 1 |
| Names (Optional, possibly several fields) | any | optional (0 or more) |

### Geographic Maps

These visualizations display **location-based data** on a map.

- `choroplethMap`: Choropleth map — colors regions on a world/country map.
  **Requires a string field with ISO 3166 country/subdivision codes** and a
  numeric or string field for color value.
- `dotMap`: Dot map — places dots on a map. **Requires `latitude` and
  `longitude` numeric fields**. Optional radius and color value fields.
- `connectionMap`: Connection map — draws lines between points on a map.
  **Requires `latitude` and `longitude` numeric fields** for each point.
  Optional color value field.
- `bubbleMap`: Bubble map — places sized bubbles on a map. **Requires
  `latitude` and `longitude` numeric fields** and a **numeric radius value
  field**. Optional color value field.

**Required query result field types (choroplethMap):**

| Slot | Accepted DQL types | Count |
|------|--------------------|-------|
| Country/subdivision code | `string` (ISO 3166 codes) | exactly 1 |
| Color value | `long`, `double`, `duration`, `string` | exactly 1 |

**Required query result field types (dotMap, connectionMap):**

| Slot | Accepted DQL types | Count | Required |
|------|--------------------|-------|----------|
| Latitude | `long`, `double`, `duration` | exactly 1 | yes |
| Longitude | `long`, `double`, `duration` | exactly 1 | yes |
| Color value | `long`, `double`, `duration`, `string` | exactly 1 | no (optional) |

**Required query result field types (bubbleMap):**

| Slot | Accepted DQL types | Count | Required |
|------|--------------------|-------|----------|
| Latitude | `long`, `double`, `duration` | exactly 1 | yes |
| Longitude | `long`, `double`, `duration` | exactly 1 | yes |
| Radius value | `long`, `double`, `duration` | exactly 1 | yes |
| Color value | `long`, `double`, `duration`, `string` | exactly 1 | no (optional) |

### Matrix & Correlation

- `heatmap`: Heatmap — two-dimensional matrix with color-coded cells.
  X-axis and Y-axis each accept numeric (range with start/end), time
  (timeseries/makeTimeseries), or string (categorical) fields. Requires a
  numeric or string value field for cell color. Use `summarize` with
  `by:{}` or `timeseries`/`makeTimeseries` to produce suitable data.
- `scatterplot`: Scatterplot — plots individual data points on X/Y axes.
  X-axis accepts timeframe, numeric, or categorical fields. Y-axis accepts
  numeric or categorical fields. Optional names field for series grouping.

**Required query result field types (heatmap):**

| Slot | Accepted DQL types | Count |
|------|--------------------|-------|
| X-axis | `timeframe`, range (object with `start`/`end`), `string` | exactly 1 |
| Y-axis | `timeframe`, range (object with `start`/`end`), `string` | exactly 1 |
| Values | `long`, `double`, `duration`, `string` | exactly 1 |

**Required query result field types (scatterplot):**

| Slot | Accepted DQL types | Count |
|------|--------------------|-------|
| X-axis | `timeframe`, `long`, `double`, `duration`, `string` | exactly 1 |
| Y-axis | `long`, `double`, `duration`, `string` | exactly 1 |
| Names (Optional, possibly several fields) | any | optional (0 or more) |
