# Notebook Information Extraction

Extract information from notebook JSON to understand what it contains and execute its queries.

## Quick Reference

**Two main workflows:**
1. **Look into notebook** - Read notebook like a human (metadata → sections top-to-bottom)
2. **Search for something** - Find specific content by keyword, then extract details

**Key extractions:**
- Global: metadata, default timeframe, section count
- Per section: type, title, DQL query, markdown content, visualization
- Execution: query + timeframe → execute → interpret results

---

## Workflow 1: Look into Notebook (Human-like)

When you need to understand what a notebook contains, read it like a human would: global context first, then sections from top to bottom.

### Step 1: Read Global Context

**Notebook metadata:**

```bash
jq '{
  version: .content.version,
  section_count: (.content.sections | length),
  default_timeframe: .content.defaultTimeframe
}' notebook.json
```

**Count sections by type:**

```bash
jq '{
  total_sections: (.content.sections | length),
  by_type: (.content.sections | group_by(.type) | map({
    type: .[0].type,
    count: length
  }))
}' notebook.json
```

**Output:**

```json
{
  "total_sections": 12,
  "by_type": [
    {"type": "markdown", "count": 4},
    {"type": "dql", "count": 7},
    {"type": "davis-copilot", "count": 1}
  ]
}
```

**Understanding notebook structure:**
- **markdown** sections - Documentation and narrative
- **dql** sections - Executable queries with visualizations
- **davis-copilot** sections - AI-powered insights

### Step 2: Read Sections Top-to-Bottom

**List sections in order:**

```bash
jq -r '.content.sections | to_entries[] | 
  "\(.key + 1). [\(.value.type)] \(
    if .value.type == "markdown" then
      .value.markdown[0:60] + "..."
    elif .value.type == "dql" then
      .value.title // "Untitled query"
    else
      "Section"
    end
  )"' notebook.json
```

**Output:**

```
1. [markdown] # Investigation: Log Analysis...
2. [dql] Error count by service
3. [dql] Top error messages
4. [markdown] ## Findings...
5. [dql] Error trend over time
6. [markdown] ## Root Cause Analysis...
```

**Extract complete section information:**

```bash
# For a specific section by index (0-based)
jq '.content.sections[0]' notebook.json

# For a specific section by ID
jq '.content.sections[] | select(.id == "section-2")' notebook.json
```

**What to extract per section:**

For **DQL sections:**
- **title** - What the query shows
- **state.input.value** - DQL query text
- **state.input.timeframe** - Query timeframe
- **state.visualization** - Chart type (lineChart, table, singleValue, etc.)
- **state.visualizationSettings** - Chart configuration

For **markdown sections:**
- **markdown** - Documentation text (supports markdown formatting)

**Extract DQL section details:**

```bash
jq '.content.sections[] | select(.type == "dql") | {
  id: .id,
  title: .title,
  query: .state.input.value,
  visualization: .state.visualization,
  timeframe: .state.input.timeframe
}' notebook.json
```

**Extract markdown content:**

```bash
jq -r '.content.sections[] | select(.type == "markdown") | 
  "## Section \(.id)\n\n\(.markdown)\n"' notebook.json
```

---

## Workflow 2: Search for Something

When you know what you're looking for (e.g., "error analysis", "service metrics"), search first, then extract details.

### Step 1: Search by Keywords

**Search section titles:**

```bash
# Case-insensitive search
jq --arg keyword "error" '.content.sections[] | 
  select(.type == "dql") |
  select(.title // "" | ascii_downcase | contains($keyword | ascii_downcase)) | 
  {id: .id, title: .title}' notebook.json
```

**Search markdown content:**

```bash
jq --arg keyword "findings" '.content.sections[] | 
  select(.type == "markdown") |
  select(.markdown | contains($keyword)) | 
  {id: .id, preview: (.markdown | .[0:100])}' notebook.json
```

**Search DQL queries:**

```bash
# Find sections querying specific data
jq --arg pattern "fetch logs" '.content.sections[] | 
  select(.type == "dql") |
  select(.state.input.value | contains($pattern)) | 
  {id: .id, title: .title, query: .state.input.value}' notebook.json
```

**Search by visualization type:**

```bash
# Find all line chart sections
jq '.content.sections[] | 
  select(.type == "dql") |
  select(.state.visualization == "lineChart") | 
  {id: .id, title: .title}' notebook.json
```

### Step 2: Extract Section Details

Once you have a section ID from search results, extract full details:

```bash
jq --arg id "section-2" '.content.sections[] | select(.id == $id)' notebook.json
```

---

## Essential JSON Extraction Patterns

### List Sections by Type

**Get all DQL sections:**

```bash
jq '.content.sections[] | select(.type == "dql")' notebook.json
```

**Get all markdown sections:**

```bash
jq '.content.sections[] | select(.type == "markdown")' notebook.json
```

**Count sections by type:**

```bash
jq '.content.sections | group_by(.type) | 
  map({type: .[0].type, count: length})' notebook.json
```

### Extract DQL Queries

**Get all queries with titles:**

```bash
jq '.content.sections[] | select(.type == "dql") | {
  id: .id,
  title: .title,
  query: .state.input.value
}' notebook.json
```

**Get query with timeframe:**

```bash
jq '.content.sections[] | select(.type == "dql") | {
  id: .id,
  title: .title,
  query: .state.input.value,
  timeframe: .state.input.timeframe
}' notebook.json
```

**Extract just the query text:**

```bash
jq -r '.content.sections[] | select(.type == "dql") | 
  .state.input.value' notebook.json
```

### Get Section Metadata

**Extract section properties:**

```bash
jq '.content.sections[] | {
  id: .id,
  type: .type,
  title: .title,
  height: .height,
  showInput: .showInput
}' notebook.json
```

**Get section with visualization:**

```bash
jq '.content.sections[] | select(.type == "dql") | {
  id: .id,
  title: .title,
  visualization: .state.visualization,
  hasResults: (.state.result != null)
}' notebook.json
```

### Extract Visualization Settings

**Get chart settings:**

```bash
jq '.content.sections[] | 
  select(.type == "dql") | 
  select(.state.visualization | test("Chart")) | {
    id: .id,
    visualization: .state.visualization,
    chartSettings: .state.visualizationSettings.chartSettings
  }' notebook.json
```

**Get table settings:**

```bash
jq '.content.sections[] | 
  select(.type == "dql") |
  select(.state.visualization == "table") | {
    id: .id,
    title: .title,
    tableSettings: .state.visualizationSettings.table
  }' notebook.json
```

**Extract field mappings (for charts):**

```bash
jq '.content.sections[] | 
  select(.type == "dql") | {
    id: .id,
    visualization: .state.visualization,
    fieldMapping: .state.visualizationSettings.chartSettings.fieldMapping
  }' notebook.json
```

### Parse Timeframes

**Get default timeframe:**

```bash
jq '.content.defaultTimeframe' notebook.json
```

**Output:**

```json
{
  "from": "now()-2h",
  "to": "now()"
}
```

**Get section-specific timeframes:**

```bash
jq '.content.sections[] | 
  select(.type == "dql") | {
    id: .id,
    title: .title,
    timeframe: .state.input.timeframe
  }' notebook.json
```

**Find sections with custom timeframes (different from default):**

```bash
jq --argjson default "$(jq '.content.defaultTimeframe' notebook.json)" \
  '.content.sections[] | 
  select(.type == "dql") |
  select(.state.input.timeframe != $default) | {
    id: .id,
    title: .title,
    timeframe: .state.input.timeframe
  }' notebook.json
```

### Get Notebook Metadata

**Basic notebook information:**

```bash
jq '{
  id: .id,
  name: .name,
  owner: .owner,
  isPrivate: .isPrivate,
  version: .version
}' notebook.json
```

**Comprehensive notebook summary:**

```bash
jq '{
  id: .id,
  name: .name,
  version: .version,
  sections: {
    total: (.content.sections | length),
    dql: ([.content.sections[] | select(.type == "dql")] | length),
    markdown: ([.content.sections[] | select(.type == "markdown")] | length)
  },
  visualizations: (
    [.content.sections[] | select(.type == "dql") | .state.visualization] | 
    group_by(.) | 
    map({type: .[0], count: length})
  ),
  defaultTimeframe: .content.defaultTimeframe
}' notebook.json
```

**Output:**

```json
{
  "id": "305651f9-4e49-4ce1-9d31-3fd7c7eab32b",
  "name": "Production Error Analysis",
  "version": 42,
  "sections": {
    "total": 8,
    "dql": 5,
    "markdown": 3
  },
  "visualizations": [
    {"type": "lineChart", "count": 2},
    {"type": "table", "count": 2},
    {"type": "singleValue", "count": 1}
  ],
  "defaultTimeframe": {
    "from": "now()-2h",
    "to": "now()"
  }
}
```

---

## Executing Queries

When using a notebook as a tool (like a human would), you need to extract and execute its queries.

### Extract Query with Context

**Get query with interpretation context:**

```bash
jq --arg id "section-2" '.content.sections[] | select(.id == $id) | {
  title: .title,
  query: .state.input.value,
  timeframe: .state.input.timeframe,
  visualization: .state.visualization
}' notebook.json
```

**Why extract these together:**
- **title** - Tells you what the query measures ("Error Rate")
- **query** - The DQL to execute
- **timeframe** - When to query (use section timeframe or default)
- **visualization** - How to interpret results (singleValue = one number, lineChart = time series)

### Execute the Query

**Workflow:**
1. Extract query + timeframe + visualization
2. Execute query using your query execution method
3. Interpret results based on visualization type

**Example extraction for execution:**

```bash
# Extract query with all execution context
SECTION_ID="section-2"

QUERY=$(jq -r --arg id "$SECTION_ID" \
  '.content.sections[] | select(.id == $id) | .state.input.value' \
  notebook.json)

TIMEFRAME=$(jq -r --arg id "$SECTION_ID" \
  '.content.sections[] | select(.id == $id) | 
  if .state.input.timeframe then .state.input.timeframe 
  else .content.defaultTimeframe end | 
  "from=\(.from) to=\(.to)"' \
  notebook.json)

VIZ=$(jq -r --arg id "$SECTION_ID" \
  '.content.sections[] | select(.id == $id) | .state.visualization' \
  notebook.json)

echo "Query: $QUERY"
echo "Timeframe: $TIMEFRAME"
echo "Visualization: $VIZ"

# Execute QUERY with TIMEFRAME using your query execution method
# Interpret results based on VIZ type
```

### Parse Cached Results

If the notebook has cached query results, you can extract them:

**Get result records:**

```bash
jq --arg id "section-2" '.content.sections[] | 
  select(.id == $id) | 
  .state.result.value.records' notebook.json
```

**Get execution metadata:**

```bash
jq '.content.sections[] | select(.type == "dql") | {
  id: .id,
  title: .title,
  recordCount: (.state.result.value.records | length),
  executionTime: .state.result.value.metadata.grail.executionTimeMilliseconds,
  scannedRecords: .state.result.value.metadata.grail.scannedRecords,
  scannedBytes: .state.result.value.metadata.grail.scannedBytes
}' notebook.json
```

**Check for query errors:**

```bash
jq '.content.sections[] | 
  select(.type == "dql") |
  select(.state.state == "error") | {
    id: .id,
    title: .title,
    error: .state.result
  }' notebook.json
```

---

## Identifying Notebook Purpose

Quickly understand what a notebook is for by analyzing its content.

### Analyze Section Flow

**Show section types in sequence:**

```bash
jq -r '.content.sections[] | .type' notebook.json
```

**Output:**

```
markdown
dql
dql
markdown
dql
markdown
```

**Pattern interpretation:**
- **markdown → queries → findings** - Investigation notebook
- **minimal markdown, many queries** - Dashboard-style monitoring
- **high markdown ratio** - Documentation/tutorial

### Analyze Query Subjects

**Extract data sources:**

```bash
jq -r '.content.sections[] | 
  select(.type == "dql") | 
  .state.input.value' notebook.json | 
  grep -oE 'fetch [a-z]+' | 
  sort | uniq -c
```

**Output:**

```
  3 fetch logs
  2 fetch spans
  1 fetch events
```

**Extract filters and aggregations:**

```bash
jq -r '.content.sections[] | 
  select(.type == "dql") | 
  .state.input.value' notebook.json | 
  grep -oE '(filter|summarize|by:)[^|]+' | 
  head -10
```

**Output:**

```
filter status == "ERROR"
filter service.name == "payment-service"
summarize count = count()
by: {error.type, error.message}
filter timestamp >= now() - 2h
```

### Extract Key Themes

**Get markdown headings:**

```bash
jq -r '.content.sections[] | 
  select(.type == "markdown") | 
  .markdown' notebook.json | 
  grep -E '^#+ '
```

**Output:**

```
# Investigation: High Error Rate on Payment Service
## Objective
## Timeline
## Findings
## Root Cause
## Recommendations
```

**Purpose:** Structured technical investigation of a specific incident

---

## Understanding Section Relationships

### Sections Using Same Data Source

**Group sections by data source:**

```bash
jq '.content.sections[] | 
  select(.type == "dql") | {
    id: .id,
    title: .title,
    dataSource: (.state.input.value | match("fetch (\\w+)").captures[0].string)
  } | group_by(.dataSource)' notebook.json
```

### Sections with Similar Visualizations

**Find all sections with same visualization type:**

```bash
jq --arg viz "lineChart" '.content.sections[] | 
  select(.type == "dql") |
  select(.state.visualization == $viz) | {
    id: .id,
    title: .title
  }' notebook.json
```

### Sequential Analysis Pattern

**Detect investigation pattern (markdown → queries → findings):**

```bash
jq -r '.content.sections | to_entries | 
  .[] | "\(.key + 1). \(.value.type) - \(
    if .value.type == "markdown" then
      (.value.markdown | split("\n")[0])
    else
      .value.title // "Untitled"
    end
  )"' notebook.json
```

**Common patterns:**
- **Investigation**: Header → data queries → findings → conclusion
- **Dashboard**: Minimal markdown → multiple related queries
- **Documentation**: Headers + explanations + example queries + more explanations

---

## Next Steps

After extracting notebook information:

1. **Execute queries** - Run DQL queries to see actual data
2. **Interpret results** - Use visualization type for context
3. **Follow relationships** - Explore related sections
4. **Document findings** - Summarize what the notebook shows

**Related workflows:**
- [create-update.md](./create-update.md) - Create or modify notebooks
- [sections.md](./sections.md) - Section types and structure reference
