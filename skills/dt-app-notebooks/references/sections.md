# Notebook Sections

Reference for notebook section types and their structure. Sections are stored in the `sections` array and executed sequentially.

## Section Types

Notebooks support three main section types: **markdown**, **dql**, and **function**.

### Markdown Sections

Markdown sections display formatted text content. They are typically used for documentation, headers, and explanations within the notebook.

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "type": "markdown",
  "markdown": "# Welcome\n\nThis is a **markdown** section."
}
```

**Properties:**
- `id`: Unique section identifier (UUID) (required)
- `type`: Set to `"markdown"` (required)
- `markdown`: String containing markdown or HTML content (required)

**Use Cases:**
- Investigation documentation
- Section headers and dividers
- Findings and conclusions
- Instructions and notes

### DQL Sections

DQL sections execute DQL queries and visualize results. These are the primary sections for displaying metrics, logs, and other observability data.

```json
{
  "id": "query-section-1",
  "type": "dql",
  "title": "Error Rate Over Time",
  "showTitle": true,
  "showInput": true,
  "height": 600,
  "state": {
    "input": {
      "value": "fetch logs | filter status == \"ERROR\" | summarize count()",
      "timeframe": {
        "from": "now()-2h",
        "to": "now()"
      }
    },
    "visualization": "lineChart",
    "visualizationSettings": {},
    "querySettings": {
      "maxResultRecords": 1000
    }
  }
}
```

**Core Properties:**

**Required:**
- `id`: Unique section identifier (UUID)
- `type`: Set to `"dql"`

**Optional:**
- `title`: Section title displayed above the visualization
- `showInput`: Whether to show the DQL query editor (default: `true`)
- `height`: Section height in pixels (default: 400)
- `state`: Complete query execution state (see State Structure below)

### DQL Section State

The `state` object contains the query and visualization configuration:

```json
{
  "input": {
    "value": "fetch logs | summarize count()",
    "timeframe": {
      "from": "now()-2h",
      "to": "now()"
    }
  },
  "visualization": "table",
  "visualizationSettings": {},
  "querySettings": {
    "maxResultRecords": 1000,
    "defaultScanLimitGbytes": 500,
    "maxResultMegaBytes": 50,
    "defaultSamplingRatio": 10000,
    "enableSampling": false
  }
}
```

**State Properties:**

- `input`: Query input parameters
  - `value`: The DQL query string (required)
  - `timeframe`: Time range for the query
  - `filterSegments`: Additional filters applied

- `visualization`: Selected visualization type (see Visualization Types below)

- `visualizationSettings`: Type-specific visualization configuration

- `querySettings`: Query execution parameters
  - `maxResultRecords`: Maximum records to return
  - `defaultScanLimitGbytes`: Scan data limit in GB
  - `maxResultMegaBytes`: Result size limit in MB
  - `defaultSamplingRatio`: Sampling ratio (e.g., 10000 = 1:10000)
  - `enableSampling`: Whether sampling is enabled

### Function Sections

Function sections execute JavaScript/TypeScript code for data transformation and custom logic.

```json
{
  "id": "function-section-1",
  "type": "function",
  "title": "Data Transformation",
  "showInput": true,
  "height": 500,
  "state": {
    "input": {
      "value": "function transform(data) {\n  return data.map(x => x * 2);\n}"
    },
    "visualization": "table"
  }
}
```

**Properties:**
- `id`: Unique section identifier (UUID) (required)
- `type`: Set to `"function"` (required)
- `title`: Section title
- `showInput`: Whether to show the code editor
- `height`: Section height in pixels
- `state`: Execution state (similar structure to DQL section)

## Visualization Types

DQL sections support various visualization types through the `visualization` property:

| Visualization | Description | Best For |
|--------------|-------------|----------|
| `table` | Tabular data display | Raw data, logs, detailed records |
| `lineChart` | Line chart | Time series, trends |
| `areaChart` | Area chart | Cumulative metrics, stacked time series |
| `barChart` | Bar chart | Comparisons, categorical data |
| `categoricalBarChart` | Categorical bar chart | Non-time-based categories |
| `pieChart` | Pie chart | Proportions, distributions |
| `donutChart` | Donut chart | Proportions with center label |
| `singleValue` | Single metric display | KPIs, aggregated values |
| `bandChart` | Band chart | Range/confidence intervals |
| `histogram` | Histogram | Distribution analysis |
| `honeycomb` | Honeycomb chart | Entity relationships |
| `raw` | Raw JSON output | Debugging |

**Selecting Visualization:**

Set `autoSelectVisualization: true` in `visualizationSettings` to let Dynatrace automatically choose the best visualization based on query results. Otherwise, explicitly specify the `visualization` type.

## Visualization Settings

Settings are visualization-specific and control display options.

### Table Settings

```json
{
  "table": {
    "hideColumnsForLargeResults": false,
    "columnOrder": ["[\"timestamp\"]", "[\"status\"]", "[\"message\"]"],
    "linewrapEnabled": true,
    "lineWrapIds": [["content"]],
    "columnWidths": {
      "[\"content\"]": 500
    }
  }
}
```

**Table Properties:**
- `hideColumnsForLargeResults`: Auto-hide columns when result set is large
- `columnOrder`: Array of column names in display order (JSON-stringified arrays)
- `linewrapEnabled`: Enable text wrapping
- `lineWrapIds`: Columns that should wrap text
- `columnWidths`: Column width overrides in pixels

### Chart Settings

```json
{
  "chartSettings": {
    "legend": {
      "hidden": false
    },
    "colorPalette": "log-level",
    "fieldMapping": {
      "leftAxisValues": ["count"],
      "timestamp": "timeframe"
    },
    "curve": "smooth",
    "pointsDisplay": "never"
  },
  "thresholds": [
    {
      "field": "count",
      "isEnabled": true,
      "rules": [
        {
          "color": {
            "Default": "var(--dt-colors-critical-default)"
          },
          "comparator": "≥",
          "value": 100,
          "label": "Critical"
        }
      ]
    }
  ]
}
```

**Chart Properties:**
- `legend`: Legend display settings
- `colorPalette`: Color scheme (`"log-level"`, `"default"`, etc.)
- `fieldMapping`: Maps query fields to chart axes
  - `leftAxisValues`: Fields for left Y-axis
  - `rightAxisValues`: Fields for right Y-axis
  - `timestamp`: Field used as X-axis (time)
- `curve`: Line smoothing (`"smooth"`, `"linear"`, `"step"`)
- `pointsDisplay`: Data point markers (`"never"`, `"always"`, `"auto"`)

**Thresholds:**
- `field`: Field to apply threshold to
- `isEnabled`: Whether threshold is active
- `rules`: Array of threshold rules
  - `comparator`: Comparison operator (`≥`, `>`, `<`, `≤`, `=`)
  - `value`: Threshold value
  - `color`: Color to apply when rule matches
  - `label`: Label for the threshold

### Single Value Settings

```json
{
  "singleValue": {
    "recordField": "count",
    "aggregation": "last",
    "sparkline": {
      "enabled": true
    }
  }
}
```

**Single Value Properties:**
- `recordField`: Field to display
- `aggregation`: How to aggregate multiple values (`"last"`, `"first"`, `"avg"`, `"sum"`, `"min"`, `"max"`)
- `sparkline`: Mini trend chart display settings

## Common Section Properties

### Timeframe

Timeframes can be set at the notebook level (default) or per section:

```json
{
  "from": "now()-2h",
  "to": "now()"
}
```

**Common Patterns:**
- Last 2 hours: `"from": "now()-2h"`, `"to": "now()"`
- Last 24 hours: `"from": "now()-24h"`, `"to": "now()"`
- Last 7 days: `"from": "now()-7d"`, `"to": "now()"`
- Absolute: ISO 8601 timestamps (e.g., `"2026-01-27T10:00:00.000Z"`)

### Section Height

Control vertical space for each section:

- **Default**: 400px
- **Single Value**: 200-300px
- **Charts**: 400-600px
- **Tables**: 500-800px (depending on data)

```json
{
  "height": 600
}
```

### Query Input Visibility

Control whether the DQL query editor is visible:

```json
{
  "showInput": true  // Show query editor
}
```

**When to hide:**
- Polished notebooks for sharing
- KPI dashboards
- Executive summaries

**When to show:**
- Investigation notebooks
- Learning/documentation
- Collaborative analysis

## Section Examples

### Example 1: Investigation Header

```json
{
  "id": "intro-section",
  "type": "markdown",
  "markdown": "# Production Error Investigation\n\n**Date:** 2026-02-06\n**Issue:** High error rate on payment service\n\n## Objective\nIdentify the root cause of the error spike."
}
```

### Example 2: KPI Single Value

```json
{
  "id": "total-errors",
  "type": "dql",
  "title": "Total Errors",
  "showInput": false,
  "height": 200,
  "state": {
    "input": {
      "value": "fetch logs | filter loglevel == \"ERROR\" | summarize count()"
    },
    "visualization": "singleValue",
    "visualizationSettings": {
      "singleValue": {
        "recordField": "count",
        "aggregation": "last"
      }
    }
  }
}
```

### Example 3: Time Series Chart

```json
{
  "id": "error-trend",
  "type": "dql",
  "title": "Error Rate Over Time",
  "height": 400,
  "state": {
    "input": {
      "value": "fetch logs | filter loglevel == \"ERROR\" | summarize count(), by: {bin(timestamp, 5m)}"
    },
    "visualization": "lineChart",
    "visualizationSettings": {
      "chartSettings": {
        "curve": "smooth",
        "legend": {
          "hidden": false
        }
      }
    }
  }
}
```

### Example 4: Detailed Table

```json
{
  "id": "error-details",
  "type": "dql",
  "title": "Recent Error Logs",
  "height": 600,
  "state": {
    "input": {
      "value": "fetch logs | filter loglevel == \"ERROR\" | sort timestamp desc | limit 100"
    },
    "visualization": "table",
    "visualizationSettings": {
      "table": {
        "linewrapEnabled": true,
        "lineWrapIds": [["content"]],
        "columnWidths": {
          "[\"content\"]": 500
        }
      }
    }
  }
}
```

## Best Practices

### Structure
1. **Start with markdown** - Provide context before showing data
2. **Logical flow** - Order sections to tell a story
3. **Group related queries** - Separate groups with markdown headers

### Titles
1. **DQL sections** - Always provide descriptive titles
2. **Clear and concise** - "Error Count by Service" not "Query 1"
3. **Consistent style** - Title case or sentence case throughout

### Heights
1. **Single values** - 200-300px
2. **Charts** - 400-600px
3. **Tables** - 500-800px based on expected row count
4. **Adjust as needed** - Based on actual data volume

### Visualizations
1. **Match data shape** - Time series → line charts, aggregations → bar charts
2. **Auto-select first** - Use `autoSelectVisualization: true` initially
3. **Refine later** - Switch to explicit types for final notebooks

### Query Settings
1. **Set limits** - Always use `limit` in queries or `maxResultRecords` in settings
2. **Scan limits** - Configure `defaultScanLimitGbytes` for large datasets
3. **Enable sampling** - For exploratory queries on massive datasets

## Related Documentation

- [analyzing.md](./analyzing.md) - Extract information from notebooks
- [create-update.md](./create-update.md) - Create and modify notebooks
