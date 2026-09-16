# Dashboard Analysis & Information Extraction

**Fetch the JSON first:** `dtctl get dashboard <id> -o json` returns the full content (`.content.tiles`, `.content.variables`). `describe` returns metadata only — no tiles.

## Two Main Workflows

1. **Look into dashboard** — read global context, then tiles top-to-bottom
2. **Search for something** — find specific content by keyword

---

## Workflow 1: Read Dashboard

### Global Context

Read `.content.version` for the schema version, count entries in `.content.tiles` for total tile count, and count entries in `.content.variables` for total variable count.

For each variable in `.content.variables[]`, note its `key`, `type`, `input`, and `defaultValue` — these are the filters available to the user.

### Tiles Top-to-Bottom

To read tiles in display order, iterate `.content.layouts` entries sorted by `.value.y` then `.value.x`. For each entry, look up the corresponding tile in `.content.tiles[id]`.

For a specific tile, look it up by ID in `.content.tiles["<id>"]` and read: `title`, `query`, `visualization`, and `visualizationSettings`.

Per tile, extract: **title** (what it shows), **query** (DQL), **visualization**
(chart type), **thresholds** (color interpretation), **content** (markdown text).

---

## Workflow 2: Search

To search by title: iterate `.content.tiles` and find entries where `.value.title` (case-insensitive) contains the keyword.

To search by query content: iterate `.content.tiles` and find entries where `.value.query` contains the search pattern.

---

## Executing Queries from Dashboard

1. **Extract query** with title, visualization, and thresholds for context
2. **Check for variables** (`$VarName` references)
3. **Resolve variables**: if `type=="query"`, execute the variable's `input`
   query to get valid values; if `type=="text"`, use `defaultValue`
4. **Substitute** variable values into the query
5. **Execute** and interpret results based on visualization type and thresholds

---

## Purpose Identification

Analyze tile titles and data sources to infer dashboard purpose:
- "Request Rate", "Error Count", "Response Time" → Service Health (RED)
- "CPU Usage", "Memory Usage" → Infrastructure Monitoring
- "SLI", "Error Budget" → SLO Tracking
- Single values with thresholds → Executive / KPI dashboard

To identify data sources, scan `.content.tiles[].query` for `fetch <entity>` patterns to see which Dynatrace entity types are queried.
