# Dashboard Create & Update Workflows

## 🚨 Mandatory 7-Step Order (Do Not Reorder)

For any dashboard create/update task, follow these steps in this exact order:

1. Define purpose and load required skills, references and assets
2. Explore available data fields/metrics
3. Plan dashboard structure: logic, variables, tiles and layout
4. Design and validate all variable/tile DQL with `dtctl query "<DQL>" --plain`
5. Construct/update dashboard JSON
6. Run `scripts/validate_dashboard.sh`
7. Deploy with `scripts/deploy_dashboard.sh`

Details, examples, and checks for every step are in this file below.

---

## Table of Contents

- [Overview](#overview)
- [MANDATORY Requirements](#mandatory-requirements)
- [Skill-Based Query Generation](#skill-based-query-generation)
- [Dashboard Examples](#dashboard-examples)
- [Creating Dashboards](#creating-dashboards)
  - [Step 0: Load Skills](#step-0-load-skills-templates-references-and-examples)
  - [Step 1: Define Purpose](#step-1-define-purpose)
  - [Step 2: Explore Data](#step-2-explore-data)
  - [Step 3: Plan Dashboard Structure](#step-3-plan-dashboard-structure)
  - [Step 4: Design and validate queries](#step-4-design-and-validate-queries)
  - [Step 5: Define dashboard JSON file](#step-5-define-dashboard-json-file)
  - [Step 6: Validate Dashboard](#step-6-validate-dashboard)
  - [Step 7: Deploy Dashboard](#step-7-deploy-dashboard)
- [Updating Dashboards](#updating-dashboards)
- [Anti-Patterns](#anti-patterns)
- [Related Resources](#related-resources)

Comprehensive guide for creating new Dynatrace dashboards and updating existing
ones.

## Overview

**When to Create vs Update:**

- **Create** - New dashboard from scratch
- **Update** - Modify existing dashboard (tiles, queries, layouts, variables)

**Key Principles:**

- Exploration of available data fields before creating queries
- DQL validation (MANDATORY for all queries)
- Skill-based query generation (MANDATORY - do not invent queries)
- Validation (MANDATORY before save/upload)
- Follow structured workflow steps

---

## MANDATORY Requirements

### Workflow Compliance Protocol

**Important instructions for creating or modifying any dashboard:**

- [ ] **Load this reference** - Read complete workflow first
- [ ] **No time-range filters in tile queries** - The dashboard UI time-frame
  picker handles this automatically. Only add time filters when the user
  explicitly requests a fixed time window.
- [ ] **Explore data fields** - Explore which fields are available in the data
- [ ] **DQL validation** - Test ALL queries before adding
- [ ] **Run `validate_dashboard.sh`** before deploying (MANDATORY) — validates
  schema structure, variable resolution, and all tile queries
- [ ] **Skill-based queries** - Load relevant skills BEFORE generating queries
- [ ] **Follow workflow steps** - Complete in order

### DQL Validation

⚠️ **MANDATORY: Validate ALL queries before adding to dashboard**

**What to validate:**

- Tile queries (`tiles[].query`)
- Variable input queries (`variables[].input`)
- Queries with variable references (`$VariableName`)

**How to validate:**

**1. Syntax Validation (CRITICAL - MUST NEVER FAIL):**

DQL queries MUST be validated for correct syntax before adding to dashboard
JSON. Publishing dashboards with invalid query syntax is UNACCEPTABLE and will
cause runtime failures.

**2. Execution Verification (REQUIRED):**

Queries MUST be executed to verify they return structurally correct data that
makes sense for the visualization. Empty results are acceptable for **tile
queries** (e.g., error logs when no errors exist), but the query structure and
field types must be validated. **Variable queries MUST return at least one
value** — a variable query returning no values is a failure.

**Variable Replacement Testing:**

When queries contain `$VariableName`:

1. **Extract variable definition** to get actual test values:

```bash
# Get variable input query
jq -r '.variables[] | select(.key == "ServiceFilter") | .input' dashboard.json
# Output: smartscapeNodes SERVICE | fields name | sort name asc
```

2. **Execute variable query** to get real values that will populate the
   dropdown/filter. This query MUST return valid results.

3. **Test tile query with actual values** from variable results:
   - Use real values returned by the variable query
   - Test with multiple representative values
   - Test with wildcard values if the variable supports them
   - Verify results match expected visualization format

**Key principle:** Use real values from the variable's own query, not invented
values.

See [variables.md](./variables.md) for variable reference syntax and patterns.

### DQL Execution Validation

⚠️ **MANDATORY: Run before deploying any dashboard**

The `validate_dashboard.sh` script executes ALL dashboard queries (including
variable resolution) against the live Dynatrace environment and reports
success/failure for each tile.

The script is at `scripts/validate_dashboard.sh` inside this skill's directory
(the same `dt-app-dashboards` folder that contains this file).

```bash
# Validate by file — use the skill directory you already loaded
bash <dt-app-dashboards-skill-dir>/scripts/validate_dashboard.sh dashboard.json

# Validate by dashboard ID (existing dashboard)
bash <dt-app-dashboards-skill-dir>/scripts/validate_dashboard.sh <dashboard-id>
```

**Important:** Replace `<dt-app-dashboards-skill-dir>` with the actual absolute path where the dashboard skill was loaded from.

---

## Skill-Based Query Generation

🚨 **MANDATORY: Load skills BEFORE generating queries. DO NOT invent queries.**

### Why Mandatory

Skills contain validated patterns, correct data sources, proper aggregations,
and field names. Creating queries without skills results in incorrect data
sources, invalid fields, and poor performance.

### Workflow

1. **Identify Required Skills** - Determine what skills we need for the queries
2. **Load Skills** - Load them using the `skill` tool
3. **Generate queries** - Use the knowledge from the skill to generate the
   required queries
4. **Test queries** - Run the query and see if the structure match the used
   visualization

---

## Dashboard Examples

See [assets/ExampleDashboard.json](../assets/ExampleDashboard.json) for
complete tile examples with different visualizations.

**How to use examples:**

1. **List all example tile titles** to see what's available:

```bash
jq -r '.tiles[] | .title' assets/ExampleDashboard.json
```

2. **Query specific tile by title** to get complete structure:

```bash
# Get tile with specific title
jq '.tiles[] | select(.title == "Line visualization")' assets/ExampleDashboard.json

# See tile structure with layout
jq '{tile: .tiles["0"], layout: .layouts["0"]}' assets/ExampleDashboard.json
```

3. **Extract visualization patterns** for your dashboard:

```bash
# Get all visualization types used
jq -r '.tiles[] | .visualization' assets/ExampleDashboard.json | sort -u

# Get visualizationSettings for specific type
jq '.tiles[] | select(.visualization == "areaChart") | .visualizationSettings' assets/ExampleDashboard.json
```

**Tile titles explain the example** - query by title to find the pattern you
need.

---

## Creating Dashboards

### Step 0: Load Skills, templates, references, and examples

Load all skills, templates, references, and examples.

### Step 1: Define Purpose

Answer these questions:

- **Metrics?** (requests, errors, latency, etc.)
- **Audience?** (executives, SREs, developers)
- **Actions?** (troubleshoot, monitor, compare)

**Then:** Identify domain → Search skills → Load skills

### Step 2: Explore Data

- Explore which fields are available in the data
- Understand the data structure and available metrics

### Step 3: Plan Dashboard Structure

- Plan the approximate layout and structure of the dashboard
- Determine the number of tiles and their approximate positions

### Step 4: Design and validate queries
- Design queries based on the data exploration and planned structure
- Take care of both variable-input queries and tile queries
- Validate queries to ensure they run successfully and return the expected data using `dtctl query "<your DQL query>" --plain`

**Workflow:**

1. Load skills (if not already)
2. Extract patterns from skills
3. Adapt for use case
4. Validate query using `dtctl query "<your DQL query>" --plain` and verify referenced fields exist
5. Add to tile

**Query structure:**

```dql-template
fetch [source]
| filter [conditions]
| summarize [aggregations], by: {dimensions}
| sort [field] desc
| limit [count]
```

**Best practices:**

- Use `limit` (e.g., `limit 100`)
- Add `summarize` before visualization
- Descriptive field names
- Source from skills
- Verify field names before use: run a sample query (for example, `limit 1`),
  inspect returned fields, and only use fields that exist
- **Do NOT add time-range filters** to tile queries unless the user explicitly
  requests a fixed time window. The dashboard UI time-frame picker handles
  this automatically; hardcoded filters override it.

### Step 5: Define dashboard JSON file

The JSON file must have `name` and `type` at the top level. Always set `name`
before deploying — omitting it creates an "Untitled dashboard".

```json
{
  "name": "My Dashboard Name",
  "type": "dashboard",
  "content": {
    "version": 21,
    "variables": [],
    "tiles": { ... },
    "layouts": { ... }
  }
}
```

### Step 5.1: Add Variables (Optional)

```json
{
  "variables": [{
    "version": 2,
    "key": "ServiceFilter",
    "type": "query",
    "visible": true,
    "editable": true,
    "input": "smartscapeNodes SERVICE | fields name | sort name asc",
    "multiple": false
  }]
}
```

**Usage in queries:**

```dql-template
// Single-select (multiple: false)
fetch logs | filter service.name == $ServiceFilter
```

```dql-template
// Multi-select (multiple: true) — use in() + array()
fetch logs | filter in(service.name, array($ServiceFilter))
```
Make sure the query inputs to variables are valid and return expected results.
See [variables.md](./variables.md) for details on how to define and use different variable types, preferred default values, and other advanced features.


### Step 5.2: Create Tiles

**Header tile:**

```json
{
  "tiles": {
    "1": {"type": "markdown", "content": "# Dashboard Title"}
  },
  "layouts": {
    "1": {"x": 0, "y": 0, "w": 20, "h": 1}
  }
}
```

**Data tile:**

```json
{
  "tiles": {
    "2": {
      "type": "data",
      "title": "Metric Name",
      "query": "fetch ... | summarize ...",
      "visualization": "lineChart",
      "visualizationSettings": {},
      "querySettings": {}
    }
  },
  "layouts": {
    "2": {"x": 0, "y": 1, "w": 20, "h": 8}
  }
}
```

**Checklist:**

- [ ] Unique tile ID
- [ ] Valid DQL query (validated)
- [ ] visualizationSettings present (even if empty)
- [ ] querySettings present (even if empty)
- [ ] Matching layout entry

**Visualization types:**

- Time-series (MUST have time dimension via `timeseries`/`makeTimeseries`, optional categorical split): `lineChart`, `areaChart`, `barChart`, `bandChart`
- Categorical (no time dimension, use `summarize ... by:{field}`): `categoricalBarChart`, `pieChart`, `donutChart`
- Single value / gauge (single record with numeric field): `singleValue`, `meterBar`, `gauge`
- Tabular / raw (any data shape): `table`, `raw`, `recordList`
- Distribution / status: `histogram` (numeric bins), `honeycomb` (entity status grid)
- Geographic maps: `choroplethMap` (ISO 3166 codes), `dotMap` / `connectionMap` / `bubbleMap` (latitude + longitude fields)
- Matrix / correlation: `heatmap` (X/Y axes: numeric, time, or string), `scatterplot` (X/Y numeric or categorical)

See [tiles.md → Visualization Types](./tiles.md#visualization-types) for the
full required query result field types per visualization.

### Step 5.3: Configure Layouts

Position tiles on 20-unit grid:

```json
{
  "layouts": {
    "1": {"x": 0, "y": 0, "w": 20, "h": 1},   // Header
    "2": {"x": 0, "y": 1, "w": 10, "h": 8},   // Left
    "3": {"x": 10, "y": 1, "w": 10, "h": 8},  // Right
    "4": {"x": 0, "y": 9, "w": 20, "h": 8}    // Full width
  }
}
```

**Tips:** Start with `y: 0`, use consistent heights, avoid overlaps

### Step 6: Validate Dashboard

- Check the dashboard structure:

📋 **Structure:**

- [ ] Version set to 21
- [ ] Tile IDs match layout IDs
- [ ] Data tiles have visualizationSettings/querySettings
- [ ] No overlapping layouts
- [ ] All tiles fit within 20-unit width

- run `validate_dashboard.sh` to validate the dashboard

```bash
bash <dt-app-dashboards-skill-dir>/scripts/validate_dashboard.sh dashboard.json
```

The script will validate the dashboard and print any errors or warnings.

### Step 7: Deploy Dashboard

**Deploy using `deploy_dashboard.sh`:**

```bash
bash <dt-app-dashboards-skill-dir>/scripts/deploy_dashboard.sh dashboard.json
```

The script validates, deploys, and prints the **clickable dashboard URL as
the last line of stdout**. Present that URL to the user.

---

## Updating Dashboards

### Modification Workflow

1. **Baseline validation** - Run `validate_dashboard.sh` before changes
2. **Identify changes** - What needs modification?
3. **Locate elements** - Find tiles/layouts/variables by ID
4. **Apply modifications** - Add, remove, or update
5. **Validate** - Run `validate_dashboard.sh`
6. **Deploy** - Upload

### Locating Elements

```bash
# List tiles
jq '.content.tiles | to_entries[] | {id: .key, title: .value.title, 
type: .value.type}' dashboard.json

# Find by content
jq '.content.tiles | to_entries[] | select(.value.query | 
contains("error"))' dashboard.json

# Check layouts
jq '.content.layouts | to_entries[] | {id: .key, position: .value}' 
dashboard.json
```

### Adding Tiles

1. Find next tile ID: `jq '.content.tiles | keys | map(tonumber) | max'
   dashboard.json`
2. Load skill and create query
3. Validate query
4. Add tile and layout
5. Run `validate_dashboard.sh`

**Positioning:**

- Below: Use `max(y + h)` as new `y`
- Between: Shift tiles below
- Side-by-side: Same `y`, different `x`

### Removing Tiles

1. Identify tile ID
2. Delete from both `tiles` AND `layouts`
3. Adjust layout if needed (shift tiles up)
4. Run `validate_dashboard.sh`

### Updating Queries

⚠️ **MANDATORY: Validate before saving**

**Workflow:**

1. Copy original for rollback
2. Load skills if significant change
3. Modify query
4. Validate query and verify referenced fields exist (MANDATORY)
5. Update tile
6. Run `validate_dashboard.sh`

### Managing Variables

**Add variable:**

1. Define and validate input query
2. Add to `variables` array
3. Reference in queries (`$VariableName`)
4. Run `validate_dashboard.sh`
5. Test with different values

**Modify variable:**

1. Update input query
2. Validate new query
3. Run `validate_dashboard.sh`

**Remove variable:**

1. Remove from `variables` array
2. Remove all `$VariableName` references from queries
3. Validate modified queries
4. Run `validate_dashboard.sh`

### Post-Modification Validation & Deployment

Run `validate_dashboard.sh` and deploy the dashboard.

---

## Anti-Patterns

❌ **Inventing queries without skills** - Always load skills first  
❌ **Inventing DQL field names** - Check sample output first and only use
existing fields  
❌ **Skipping validation** - Run `validate_dashboard.sh` before deploying  
❌ **Queries without limits** - Always cap result sets  
❌ **Overlapping layouts** - Check coordinates carefully  
❌ **Missing required properties** - visualizationSettings, querySettings
required  
❌ **Not testing variables** - Test queries with different variable values
❌ **Hardcoding time-range filters in queries** - The dashboard UI time-frame
picker handles time scoping automatically. Hardcoded filters override the UI
picker, preventing users from changing the time window. Only add time filters
when the user explicitly requests a fixed time window.  
❌ **Missing dashboard name** - Set `name` in the JSON before deploying; updating it after creation requires a get→modify→reapply cycle  
❌ **Installing extra validation tools** - `validate_dashboard.sh` handles all validation; do not install `jsonschema` or similar

---

## Related Resources

**Reference Files:**

- [tiles.md](./tiles.md) - Tile types, visualization settings
- [layouts.md](./layouts.md) - Grid system, layout patterns
- [variables.md](./variables.md) - Variable types, properties, patterns
- [analyzing.md](./analyzing.md) - Dashboard structure analysis and JSON
  extraction
