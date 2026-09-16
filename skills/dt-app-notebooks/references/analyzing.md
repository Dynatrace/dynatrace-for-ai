# Notebook Analysis & Information Extraction

**Fetch the JSON first:** `dtctl get notebook <id> -o json` returns the full content (`.content.sections`). `describe` returns metadata only — no sections.

## Two Main Workflows

1. **Look into the notebook** — read global context, then sections in display order
2. **Search for something** — find specific content by keyword

---

## Workflow 1: Read Notebook

### Global Context

Read `.content.version` for the schema version, `.content.defaultTimeframe` for the notebook's default time range, and count entries in `.content.sections` for total section count.

### Sections in Display Order

Sections render top-to-bottom in array order.

Iterate `.content.sections` in order. For each section, read: `id`, `type`, `title`, `state.input.value` (the DQL query), and `state.visualization`.

For a specific section, find the entry where `.id == "<id>"` and read: `title`, `state.input.value`, `visualization`, and `state.visualizationSettings`.

Per section, extract: **title** (what it shows), **query** (DQL), **visualization**
(chart type), **thresholds** (color interpretation), **markdown** (markdown text).

---

## Workflow 2: Search

To search by title: iterate `.content.sections` and find entries where `.title` (case-insensitive) contains the keyword.

To search by query content: iterate `.content.sections` and find entries where `.state.input.value` contains the search pattern.

---

## Executing Queries from a Section

1. **Extract query** (`section.state.input.value`) with title, visualization,
   and thresholds for context
2. **Check for hardcoded timeframe** (`section.state.input.timeframe`) — if
   absent, the notebook's `content.defaultTimeframe` applies
3. **Execute** the query and interpret results based on visualization type and
   thresholds

---

## Purpose Identification

Analyze section titles and data sources to infer notebook purpose:
- "Request Rate", "Error Count", "Response Time" → Service Health (RED)
- "CPU Usage", "Memory Usage" → Infrastructure Monitoring
- "SLI", "Error Budget" → SLO Tracking
- Single values with thresholds → Executive / KPI overview

To identify data sources, scan `.content.sections[].state.input.value` for `fetch <entity>` patterns to see which Dynatrace entity types are queried.
