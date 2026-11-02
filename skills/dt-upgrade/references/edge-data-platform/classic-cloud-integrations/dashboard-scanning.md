# Dashboard Scanning

How to scan Dynatrace dashboards for classic cloud connection references.

---

## Table of Contents

- [1. Two Dashboard Formats](#1-two-dashboard-formats)
- [2. New Dashboard Scanning via dtctl](#2-new-dashboard-scanning-via-dtctl)
- [3. Classic Dashboard Scanning](#3-classic-dashboard-scanning)
- [4. What to Scan For](#4-what-to-scan-for)

---

## 1. Two Dashboard Formats

Dynatrace environments may contain both classic and new dashboards:

| Format | Storage | API | Content |
|---|---|---|---|
| **New dashboards** | Document Service | `@dynatrace-sdk/client-document` / dtctl | JSON with DQL-based tiles |
| **Classic dashboards** | Dashboards Config API v1 | `/api/config/v1/dashboards` | JSON with metric selector tiles |

DQL **cannot** query dashboard content. The Document Service stores content as opaque blobs. Scanning must download and parse each dashboard's JSON.

---

## 2. New Dashboard Scanning via dtctl

### List All Dashboards

```
dtctl get dashboards \
  --admin-access \
  --filter "not (originAppId exists and originAppId starts-with 'dynatrace.') and (type == 'dashboard')" \
  -o json
```

Returns only non-preset dashboard document metadata (id, name, owner). The `--filter` expression does two things: it excludes preset dashboards (those with `originAppId` starting with `dynatrace.`) and it restricts results to type `dashboard` (required because using `--filter` triggers a dtctl bug where other document types — notebooks, workflows, filter-presets — are incorrectly included in the response). See [Admin Access](#admin-access) for why `--admin-access` is needed and what happens when the permission is absent.

### Admin Access

By default, `dtctl get dashboards` returns only dashboards visible to the authenticated user (own + shared). Other users' private dashboards are not visible, producing an incomplete migration assessment.

Use `--admin-access` to return all dashboards in the environment:

```
dtctl get dashboards --admin-access ...
```

**Permission required**: The OAuth client used by dtctl must include the `document:documents:admin` scope. This is a Dynatrace platform OAuth permission. Without it, the API returns HTTP 403: *"Insufficient permissions to request admin-access"*.

**Graceful fallback**: When fetching dashboards, attempt `--admin-access` first. If the call fails, retry without it and note:
```
⚠ --admin-access unavailable — add `document:documents:admin` OAuth permission for complete scan
```
The dashboard count line will include `(user-visible only — add document:documents:admin for complete scan)` to flag the incomplete coverage.

### Download and Inspect a Dashboard

```
dtctl get dashboard <id> -o json
```

Returns the full dashboard JSON including tile definitions.

### What to Look For in Tiles

In the downloaded JSON, tiles contain DQL queries:

```json
{
  "tiles": {
    "tile-1": {
      "type": "data",
      "query": "fetch dt.entity.ec2_instance | ...",
      ...
    },
    "tile-2": {
      "type": "data",
      "queries": [
        { "query": "timeseries avg(dt.cloud.aws.ec2.cpu.usage)" }
      ]
    }
  }
}
```

For each tile, extract:
- `tile.query` — single DQL query string
- `tile.queries[].query` — array of DQL query strings

Then apply the detection patterns from [classic-detection-patterns.md](classic-detection-patterns.md) to each query string.

### Filtering: Skip Preset Dashboards

Preset dashboards are maintained by Dynatrace and auto-updated during migration — they should not be scanned.

**Identification**: Dashboards where `originAppId` starts with `dynatrace.` are preset dashboards. Examples: `dynatrace.clouds` (Clouds App), `dynatrace.kubernetes` (Kubernetes App), `dynatrace.synthetic`, etc. Any `dynatrace.*` prefix indicates a Dynatrace-managed preset.

**Server-side filter (the only mechanism)**: Use `--filter` to exclude presets at the list stage. The filter must also include a type restriction due to a dtctl bug (see below):

```
--filter "not (originAppId exists and originAppId starts-with 'dynatrace.') and (type == 'dashboard')"
```

Testing confirmed:
- The compound `not (originAppId exists and ...)` form is required — the simpler `not (originAppId starts-with 'dynatrace.')` incorrectly excludes user dashboards that have no `originAppId` field (19 dashboards missed in testing)
- Parentheses after `not` are mandatory — `not originAppId ...` without parens returns HTTP 400
- **`and (type == 'dashboard')` is required**: using `--filter` without this triggers a dtctl bug where non-dashboard types (notebooks, workflows, filter-presets) appear in `get dashboards` results

**Note on `--add-fields "originAppId"`**: This flag returns HTTP 400 for `originAppId` — the field cannot be surfaced in list responses. It is also absent from individual document fetch responses. The server-side `--filter` is the only way to act on this field.

---

## 3. Classic Dashboard Scanning — Out of Scope

Classic dashboards use the Config API v1 (`/api/config/v1/dashboards`), which `dtctl` does not support. **Classic dashboard scanning is out of scope for automated assessment.**

If the environment has classic dashboards with cloud monitoring tiles, they must be reviewed manually. The relevant classic detection patterns are documented in [classic-detection-patterns.md](classic-detection-patterns.md) for reference.

Classic dashboard tiles use metric selectors (not DQL). The key fields to inspect manually:

| Tile type | Where to find the metric reference |
|---|---|
| Data explorer | `queries[].metric` — metric selector expression |
| Custom chart | `filterConfig.chartConfig.series[].metric` |
| SLO | `metric` — metric expression |
| Markdown | Raw text — may contain metric key references |

---

## 4. What to Scan For

For each dashboard tile content, check for:

| Pattern | Detection rule | Severity |
|---|---|---|
| `fetch dt.entity.<classic_type>` | Classic entity reference | Definitive classic |
| `dt.cloud.aws.*` / `dt.cloud.azure.*` | Classic built-in metric | Definitive classic |
| `builtin:cloud.*` / `ext:cloud.*` | Cassandra-era classic metric | Definitive classic |
| `cloud.aws.<service>.<snake_case>` | Classic non-built-in (AWS) | Definitive classic (after disambiguation) |
| `cloud.gcp.<api>_googleapis_com.*` | Classic GCP metric | Definitive classic (after disambiguation) |
| `cloud.azure.microsoft_*` | Ambiguous — could be classic or new | Flag for review |

### Report Format

For each affected dashboard, report:

```
Dashboard: <name> (<id>)
Owner: <owner>
Tile(s) with classic references:
  - Tile "<tile_name>": dt.cloud.aws.ec2.cpu.usage
  - Tile "<tile_name>": fetch dt.entity.ec2_instance
```
