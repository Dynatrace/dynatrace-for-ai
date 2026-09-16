# Dashboard Create & Update Workflows

## Mandatory 7-Step Order

1. Define purpose and load required skills, references and assets
2. Explore available data fields/metrics
3. Plan dashboard structure: variables, tiles, layout
4. Design and validate all DQL with `dtctl query '<DQL>'`
5. **(Update only)** Download existing dashboard JSON from the server
6. Construct new dashboard JSON (create) or modify the downloaded JSON (update)
7. Deploy with `dtctl apply` — when updating, deploy the file downloaded in step 5

---

## Mandatory Requirements

- **No time-range filters in tile queries** — the dashboard UI time-frame
  picker handles this. Only add time filters when user explicitly requests it.
- **DQL validation** — test ALL queries (tile and variable) before adding
- **Skill-based queries** — load domain skills BEFORE generating queries;
  do not invent DQL queries, field names, or data sources
- **Verify field names** — run a sample query (e.g. `limit 1`) and only use
  fields that actually exist in the result

## DQL Validation

**Syntax + execution validation is mandatory for all queries.**

1. Validate tile queries and variable input queries
2. For queries with `$VariableName`: extract the variable's input query,
   execute it to get real values, then test the tile query with those values
3. Variable queries MUST return at least one value; tile queries may return
   empty results (e.g. error logs when no errors exist)

## Creating Dashboards

### Step 1: Define Purpose

Identify metrics, audience, and actions. Then load relevant domain skills.

### Step 2: Explore Data

For fields and metrics already documented in the loaded domain skill, skip exploration — confirm with one `| limit 1` query. Only run broader discovery queries for data models not covered by the skill.

### Step 3: Plan Structure

Sketch approximate layout: number of tiles, positions, variables needed.

#### Layout Grid

Default: **24 columns** (`settings.gridLayout.columnsCount`). Full-width `w: 24`, half `w: 12`, quarter `w: 6`. Height: `h: 1` for headers, `h: 6-8` for charts, `h: 12-16` for detailed views.

Each tile in `tiles` must have a matching entry in `layouts` with `x`, `y`, `w`, `h`. Tiles with `x + w > columnsCount` wrap. Use standard widths for responsiveness.

```json
"layouts": {
  "1": { "x": 0, "y": 0, "w": 24, "h": 1 },
  "2": { "x": 0, "y": 1, "w": 12, "h": 8 },
  "3": { "x": 12, "y": 1, "w": 12, "h": 8 },
  "4": { "x": 0, "y": 9, "w": 24, "h": 8 }
}
```

### Step 4: Design and Validate Queries

```dtctl
dtctl query '<your DQL query>'
```

Always use **single quotes** around the DQL string so `$`, `\`, and other
special characters survive argument parsing intact.

Use `limit` to cap results. Use `summarize` before visualization. Source
queries from loaded skills.

### Step 5 (Update only): Download Existing Dashboard JSON

**Skip when creating.** Download the current server state **before **making any modifications:

```dtctl
dtctl get dashboard <id> -o json
```

Save the result as `dashboard.json`.

This preserves user UI edits since the last deployment. The downloaded file contains the `id` — do not add or change it manually.

### Step 6: Construct New or Modify Downloaded Dashboard JSON

For **new dashboards**, build JSON from scratch (no `id` — server assigns one). For **updates**, modify the file downloaded in Step 5 — do not construct new JSON and inject an `id`.

```json
{
  "name": "My Dashboard Name",  // "id" is present when updating (from downloaded JSON)
  "type": "dashboard",
  "content": {
    "version": 21,
    "variables": [],
    "tiles": {
      "1": { "type": "markdown", "content": "# Title" },
      "2": {
        "type": "data", "title": "Metric",
        "query": "fetch ... | summarize ...",
        "visualization": "lineChart",
        "visualizationSettings": {}, "querySettings": {}
      }
    },
    "layouts": { "1": { "x": 0, "y": 0, "w": 24, "h": 1 }, "2": { "x": 0, "y": 1, "w": 24, "h": 8 } }
  }
}
```

**Checklist before writing JSON:**
- Every data tile has: unique ID, validated DQL, `visualizationSettings`, `querySettings`, matching layout entry
- Every defined variable is referenced in at least one tile query — remove unused variables
- **When updating:** confirm the JSON is the downloaded file (`id` field present), not a freshly constructed one

See [tiles.md](./tiles.md) for visualization types and field requirements.
See [variables.md](./variables.md) for variable definitions and usage patterns.

### Step 7: Deploy

```dtctl
dtctl apply dashboard -f dashboard.json -o yaml
# preview without persisting:
dtctl apply dashboard -f dashboard.json -o yaml --dry-run
```

Validation runs automatically before deployment. If validation fails, fix **all** reported errors before re-running — do not fix one error and re-deploy in a loop.

**When updating:** ensure `dashboard.json` is the file downloaded in Step 5. A missing `id` field means a fresh JSON is being deployed — a new dashboard will be created instead of updating.

On success, `dtctl apply` outputs the deployment result (action, id, name, url). Present the URL to the user.

---

## Anti-Patterns

- Inventing queries without loading skills first
- Inventing DQL field names without checking sample output
- Overlapping layouts
- Hardcoding time-range filters (overrides UI time picker)
- Defining variables that are not referenced in any tile query (every variable must be used as `$key` in at least one tile query)
- Missing `name` in dashboard JSON
- Setting a custom `id` on a new dashboard (server assigns IDs; only downloaded dashboards carry their `id`)
- **Skipping the download when updating** — building JSON from scratch loses user UI edits made since last deployment
- **Injecting an `id` into freshly-constructed JSON** — same as above; overwrites server state with stale content
- **Downloading but not using the file** — deploying a freshly-constructed JSON instead of the downloaded one defeats the download step
