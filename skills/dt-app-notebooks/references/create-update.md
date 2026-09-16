# Notebook Create & Update Workflows

## Mandatory 7-Step Order

1. Define purpose and load required skills, references and assets
2. Explore available data fields/metrics
3. Plan notebook structure: section order, markdown vs DQL sections
4. Design and validate all DQL with `dtctl query '<DQL>'`
5. **(Update only)** Download existing notebook JSON from the server
6. Construct new notebook JSON (create) or modify the downloaded JSON (update)
7. Deploy with `dtctl apply` — when updating, deploy the file downloaded in step 5

---

## Mandatory Requirements

- **DQL validation** — test ALL section queries before adding
- **Skill-based queries** — load domain skills BEFORE generating queries;
  do not invent DQL queries, field names, or data sources
- **Verify field names** — run a sample query (e.g. `| limit 1`) and only use
  fields that actually exist in the result
- **Time-range filters in queries** — hardcoded time filters are fine in
  notebooks. The default timeframe is `content.defaultTimeframe`; each section
  can override via `section.state.input.timeframe`.

## DQL Validation

**Syntax + execution validation is mandatory for all queries.** Section queries
may return empty results (e.g. error logs when no errors exist) — empty is OK,
but the query must execute without errors.

## Creating Notebooks

### Step 1: Define Purpose

Identify metrics, audience, and actions. Then load relevant domain skills.

### Step 2: Explore Data

For fields and metrics already documented in the loaded domain skill, skip
exploration — confirm with one `| limit 1` query. Only run broader discovery
queries for data models not covered by the skill.

### Step 3: Plan Structure

Sections render top-to-bottom in `content.sections` array order. Use markdown sections to introduce groups of DQL sections (e.g. one markdown header followed by 2–3 related DQL sections).

### Step 4: Design and Validate Queries

```dtctl
dtctl query '<your DQL query>'
```

Always use **single quotes** around the DQL string so `$`, `\`, and other
special characters survive argument parsing intact.

Use `limit` to cap results. Use `summarize` before visualization. Source queries
from loaded skills.

### Step 5 (Update only): Download Existing Notebook JSON

**Skip when creating.** Download the current server state **before** making any
modifications:

```dtctl
dtctl get notebook <id> -o json
```

Save the result as `notebook.json`.

This preserves user UI edits since the last deployment. The downloaded file
contains the `id` — do not add or change it manually.

### Step 6: Construct New or Modify Downloaded Notebook JSON

For **new notebooks**, build JSON from scratch (no `id` — server assigns one).
For **updates**, modify the file downloaded in Step 5 — do not construct new
JSON and inject an `id`.

```json
{
  "name": "My Notebook Name",  // "id" is present when updating (from downloaded JSON)
  "type": "notebook",
  "content": {
    "version": "7",
    "defaultTimeframe": { "from": "now()-2h", "to": "now()" },
    "sections": [
      { "id": "1", "type": "markdown", "markdown": "# Title" },
      {
        "id": "2", "type": "dql", "title": "Metric", "showInput": true,
        "state": {
          "input": { "value": "fetch ... | summarize ..." },
          "visualizationSettings": { "autoSelectVisualization": true, "chartSettings": {} },
          "querySettings": {
            "maxResultRecords": 1000, "defaultScanLimitGbytes": 500,
            "maxResultMegaBytes": 1, "defaultSamplingRatio": 10, "enableSampling": false
          }
        }
      }
    ]
  }
}
```

**Visualization tip:** prefer `visualizationSettings.autoSelectVisualization: true`
and omit `state.visualization`. Set both only when the user wants a specific
chart type.

**Checklist before writing JSON:**
- Every `dql` section has: unique `id`, validated DQL, `visualizationSettings`,
  `querySettings`
- Section IDs are unique across the `sections` array
- **When updating:** confirm the JSON is the downloaded file (`id` field
  present), not a freshly constructed one

See [sections.md](./sections.md) for visualization types and field requirements.

### Step 7: Deploy

```dtctl
dtctl apply notebook -f notebook.json -o yaml
# preview without persisting:
dtctl apply notebook -f notebook.json -o yaml --dry-run
```

Validation runs automatically before deployment (every DQL query is executed
against the tenant and visualization compatibility is checked). If validation
fails, fix **all** reported errors before re-running — do not fix one error and
re-deploy in a loop.

**When updating:** ensure `notebook.json` is the file downloaded in Step 5. A
missing `id` field means a fresh JSON is being deployed — a new notebook will
be created instead of updating.

On success, `dtctl apply` outputs the deployment result (action, id, name, url).
Present the URL to the user.

---

## Anti-Patterns

- Inventing queries without loading skills first
- Inventing DQL field names without checking sample output
- Missing `name` in notebook JSON
- Setting a custom `id` on a new notebook (server assigns IDs; only downloaded
  notebooks carry their `id`)
- **Skipping the download when updating** — building JSON from scratch loses
  user UI edits made since last deployment
- **Injecting an `id` into freshly-constructed JSON** — same as above;
  overwrites server state with stale content
- **Downloading but not using the file** — deploying a freshly-constructed JSON
  instead of the downloaded one defeats the download step
