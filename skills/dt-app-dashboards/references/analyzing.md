# Dashboard Information Extraction

Extract information from dashboard JSON to understand what it shows and
execute its queries.

## Quick Reference

**Two main workflows:**

1. **Look into dashboard** - Read dashboard like a human (global context →
   tiles top-to-bottom)
2. **Search for something** - Find specific content by keyword, then extract
   details

**Key extractions:**

- Global: metadata, variables, layout
- Per tile: title, DQL query, visualization, thresholds, position
- Execution: variables → possible values → query execution

---

## Workflow 1: Look into Dashboard (Human-like)

When you need to understand what a dashboard shows, read it like a human
would: global context first, then tiles from top to bottom.

### Step 1: Read Global Context

**Dashboard metadata:**

```bash
jq '{
  version: .content.version,
  tile_count: (.content.tiles | length),
  variable_count: (.content.variables | length),
  dashboard_height: ([.content.layouts[] | .y + .h] | max)
}' dashboard.json
```

**List variables (filters available to user):**

```bash
jq '.content.variables[] | {
  key: .key,
  type: .type,
  label: .label,
  input: .input,
  defaultValue: .defaultValue
}' dashboard.json
```

**Understanding variable types:**

- `type: "query"` - The `input` field contains a DQL query that returns
  possible values
- `type: "text"` - Free-form text input, use `defaultValue` as reference

**Layout overview (which tiles are where):**

```bash
jq '.content.layouts | to_entries | map({
  id: .key,
  position: "y=\(.value.y) x=\(.value.x)",
  size: "w=\(.value.w) h=\(.value.h)"
}) | sort_by(.position)' dashboard.json
```

### Step 2: Read Tiles Top-to-Bottom

**Sort tiles by visual position:**

```bash
jq '. as $root | .content.layouts | to_entries | sort_by(.value.y, .value.x) | map({
  id: .key,
  y: .value.y,
  x: .value.x,
  tile: $root.content.tiles[.key]
})' dashboard.json
```

**Extract complete tile information:**

```bash
# For a specific tile ID
jq --arg id "4" '.content.tiles[$id] | {
  type: .type,
  title: .title,
  query: .query,
  visualization: .visualization,
  visualizationSettings: .visualizationSettings
}' dashboard.json
```

**What to extract per tile:**

- **title** - What the tile shows
- **query** - DQL query (if data tile)
- **visualization** - Chart type (see tiles.md for full list: lineChart, areaChart, barChart, bandChart, categoricalBarChart, pieChart, donutChart, singleValue, meterBar, gauge, table, raw, recordList, histogram, honeycomb, choroplethMap, dotMap, connectionMap, bubbleMap, heatmap, scatterplot)
- **visualizationSettings.thresholds** - Color thresholds for interpreting values
- **content** - Markdown text (if markdown tile)

**Extract thresholds (for interpreting query results):**

```bash
jq --arg id "4" '.content.tiles[$id].visualizationSettings.thresholds' dashboard.json
```

Example output:

```json
[
  {"color": "#4caf50", "value": 0},
  {"color": "#ff9800", "value": 0.05},
  {"color": "#f44336", "value": 0.10}
]
```

**Find related markdown (context tiles):**

```bash
# Find markdown tiles near a data tile (same row or row above/below)
jq --arg tile_id "4" '. as $root |
  (.content.layouts[$tile_id].y) as $target_y |
  .content.layouts | to_entries |
  map(select(
    (.value.y >= ($target_y - 1)) and (.value.y <= ($target_y + 1)) and
    ($root.content.tiles[.key].type == "markdown")
  )) |
  map({id: .key, content: $root.content.tiles[.key].content})' dashboard.json
```

---

## Workflow 2: Search for Something

When you know what you're looking for (e.g., "SLO data", "error rate"),
search first, then extract details.

### Step 1: Search by Keywords

**Search tile titles:**

```bash
# Case-insensitive search
jq --arg keyword "error" '.content.tiles | to_entries |
  map(select(.value.title // "" | ascii_downcase |
    contains($keyword | ascii_downcase))) |
  map({id: .key, title: .value.title, type: .value.type})' dashboard.json
```

**Search markdown content:**

```bash
jq --arg keyword "SLO" '.content.tiles | to_entries |
  map(select(.value.type == "markdown" and
    (.value.content | contains($keyword)))) |
  map({id: .key, preview: (.value.content | .[0:100])})' dashboard.json
```

**Search DQL queries:**

```bash
# Find tiles querying specific data
jq --arg pattern "fetch logs" '.content.tiles | to_entries |
  map(select(.value.query // "" | contains($pattern))) |
  map({id: .key, title: .value.title, query: .value.query})' dashboard.json
```

**Search by visualization type:**

```bash
# Find all single-value tiles (KPIs)
jq '.content.tiles | to_entries |
  map(select(.value.visualization == "singleValue")) |
  map({id: .key, title: .value.title})' dashboard.json
```

### Step 2: Extract Tile Details

Once you have a tile ID from search results, extract full details:

```bash
jq --arg id "4" '. as $root | {
  tile: $root.content.tiles[$id],
  layout: $root.content.layouts[$id],
  variables_used: (
    $root.content.tiles[$id].query // "" |
    scan("\\$[A-Za-z0-9_]+") | unique
  )
}' dashboard.json
```

---

## Extracting and Executing Queries

When using a dashboard as a tool (like a human would), you need to extract
and execute its queries. This is a two-phase process.

### Extract Query with Context

**Get query with interpretation context:**

```bash
jq --arg id "4" '.content.tiles[$id] | {
  title: .title,
  query: .query,
  visualization: .visualization,
  thresholds: .visualizationSettings.thresholds
}' dashboard.json
```

**Why extract these together:**

- **title** - Tells you what the query measures ("Error Rate")
- **query** - The DQL to execute
- **visualization** - How to interpret results (singleValue = one number,
  lineChart = time series)
- **thresholds** - How to interpret values (green < 0.05, red > 0.10)

### Two-Phase Process: Handle Variables

**Phase 1 - Identify if query has variables:**

```bash
# Extract the query
QUERY=$(jq -r --arg id "4" '.content.tiles[$id].query' dashboard.json)

# Check for variables ($VariableName)
echo "$QUERY" | grep -oE '\$[A-Za-z0-9_]+'
```

**Phase 2 - Get possible values for variables:**

If variables found, you MUST get their possible values before executing:

```bash
# Find variable definition
jq -r --arg varkey "ServiceFilter" '.content.variables[] |
  select(.key == $varkey) | {
    key: .key,
    type: .type,
    input: .input,
    defaultValue: .defaultValue
  }' dashboard.json
```

**Critical understanding:**

- If `type == "query"`: Execute the `input` query to get valid values

  ```bash
  # The input query returns possible values
  INPUT_QUERY=$(jq -r --arg varkey "ServiceFilter" \
    '.content.variables[] | select(.key == $varkey) | .input' \
    dashboard.json)
  # Execute INPUT_QUERY to get list of valid services
  ```

- If `type == "text"`: Use `defaultValue` or understand it's free-form

**Replace variable in query:**

```bash
# Replace $ServiceFilter with actual value
QUERY_FILLED=$(echo "$QUERY" | sed 's/\$ServiceFilter/"payment-service"/g')
```

**For multiple variables:**

```bash
# Get all variables used in query
VARS=$(echo "$QUERY" | grep -oE '\$[A-Za-z0-9_]+' | sed 's/\$//' | sort -u)

# For each variable, get definition and replace
for VAR in $VARS; do
  VALUE=$(jq -r --arg key "$VAR" \
    '.content.variables[] | select(.key == $key) | .defaultValue' \
    dashboard.json)
  QUERY=$(echo "$QUERY" | sed "s/\\\$$VAR/\"$VALUE\"/g")
done
```

### Execute the Query

Once variables are replaced, execute the filled query:

```bash
# QUERY_FILLED now contains the complete query with values
# Execute it using your query execution method
# Results should match the visualization type (single value, time series,
# table, etc.)
```

### Complete Workflow Example

```bash
# 1. Extract query + context
TILE_DATA=$(jq --arg id "4" '.content.tiles[$id]' dashboard.json)
QUERY=$(echo "$TILE_DATA" | jq -r '.query')
TITLE=$(echo "$TILE_DATA" | jq -r '.title')
VIZ=$(echo "$TILE_DATA" | jq -r '.visualization')

# 2. Check for variables
VARS=$(echo "$QUERY" | grep -oE '\$[A-Za-z0-9_]+' | sed 's/\$//' | sort -u)

# 3. If variables exist, get their possible values
if [ -n "$VARS" ]; then
  for VAR in $VARS; do
    VAR_DEF=$(jq --arg key "$VAR" \
      '.content.variables[] | select(.key == $key)' dashboard.json)
    VAR_TYPE=$(echo "$VAR_DEF" | jq -r '.type')
    
    if [ "$VAR_TYPE" == "query" ]; then
      # Execute the variable's input query to get possible values
      INPUT_QUERY=$(echo "$VAR_DEF" | jq -r '.input')
      echo "Execute: $INPUT_QUERY to get values for $VAR"
    else
      # Use default value
      VALUE=$(echo "$VAR_DEF" | jq -r '.defaultValue')
      QUERY=$(echo "$QUERY" | sed "s/\\\$$VAR/\"$VALUE\"/g")
    fi
  done
fi

# 4. Execute the filled query
# Execute QUERY and interpret results based on VIZ and TITLE
```

---

## Identifying Dashboard Purpose

Quickly understand what a dashboard monitors by analyzing its content.

### Analyze Tile Titles

```bash
# Extract all data tile titles
jq -r '.content.tiles[] | select(.type == "data") | .title' \
  dashboard.json | sort
```

**Purpose inference from titles:**

- "Request Rate", "Error Count", "Response Time" → Service Health
  (RED metrics)
- "CPU Usage", "Memory Usage", "Disk I/O" → Infrastructure Monitoring
- "SLI", "Error Budget", "Burn Rate" → SLO Tracking

### Analyze Data Sources

```bash
# What data is being queried
jq -r '.content.tiles[].query | select(. != null)' dashboard.json |
  grep -oE 'fetch \w+' | sort | uniq -c
```

**Output interpretation:**

```text
3 fetch logs      → Log analysis
2 fetch spans     → Distributed tracing
1 fetch metrics   → Time-series metrics
```

### Analyze Aggregations

```bash
# What calculations are performed
jq -r '.content.tiles[].query | select(. != null)' dashboard.json |
  grep -oE '(count|avg|sum|min|max|percentile)\(' | sort | uniq -c
```

**Dashboard type patterns:**

| Pattern | Type |
| ------- | ---- |
| count(), countIf(status == "ERROR"), avg(duration) | Service Health |
| avg(cpu.usage), avg(memory.usage), by: {host.name} | Infrastructure |
| sli metrics, error budget calculations | SLO Tracking |
| Single values with thresholds | Executive / KPI |

---

## Understanding Tile Relationships

Identify how tiles are related and grouped.

### Tiles Querying Same Data Source

```bash
jq '.content.tiles | to_entries |
  group_by(.value.query | select(. != null) |
    match("fetch (\\w+)").captures[0].string) |
  map({
    data_source: .[0].value.query |
      match("fetch (\\w+)").captures[0].string,
    tile_count: length,
    tiles: [.[] | {id: .key, title: .value.title}]
  })' dashboard.json
```

### Tiles Using Same Variable

```bash
# Find all tiles filtered by same variable
jq --arg var "ServiceFilter" '.content.tiles | to_entries |
  map(select(.value.query // "" | contains("$\($var)"))) |
  map({id: .key, title: .value.title})' dashboard.json
```

### Tiles in Same Visual Row

```bash
# Tiles side-by-side (comparison pattern)
jq '. as $root | .content.layouts | to_entries |
  group_by(.value.y) |
  map(select(length > 1) | {
    row: .[0].value.y,
    tiles: [.[] | {
      id: .key,
      title: $root.content.tiles[.key].title,
      width: .value.w
    }]
  })' dashboard.json
```

**Common patterns:**

- **Same row, same width** - Comparison (e.g., "Current Week" vs
  "Last Week")
- **Same variable** - Filtered views (e.g., all tiles for selected service)
- **Same data source** - Different perspectives on same data

---

## Next Steps

After extracting dashboard information:

1. **Execute queries** - Run DQL queries to see actual data
2. **Interpret results** - Use visualization type and thresholds for context
3. **Follow relationships** - Explore related tiles and variables
4. **Document findings** - Summarize what the dashboard monitors

**Related workflows:**

- [create-update.md](./create-update.md) - Create or modify dashboards
