---
name: dt-obs-analytics
description: >-
  Analyze dashboards and notebooks using Davis analyzers — anomaly detection, novelty scoring,
  and correlation. Use when the user references a specific Dynatrace dashboard or notebook
  (by URL, UUID, or name) and asks what it shows, which DQL queries it runs, whether a tile
  looks off, or wants to find anomalies, score novelty, or correlate its metrics.
  The trigger is a dashboard or notebook as the data source, not a general DQL question.
  This skill extracts timeseries queries efficiently without reading the full raw document JSON,
  then optionally runs Davis analyzers on the extracted metrics.
  Trigger phrases: "what's wrong on this dashboard", "analyze this notebook", "find anomalies",
  "novelty score", "correlate metrics", "extract DQL from dashboard", "dashboard URL", "tile",
  "run-analyzer", "timeseries extraction", "Davis analyzer".
license: Apache-2.0
---

# Analytics — Dashboard & Notebook Query Extraction

A pipeline of three platform JavaScript scripts under `scripts/` — two extractors feeding a shared analyzer runner:

```
scripts/extract-timeseries-dashboard.js ──┐
scripts/extract-timeseries-notebook.js  ──┴──► queryset.json ──► scripts/run-analyzer.js (any Davis analyzer)
```

Each script is invoked via:
```bash
dtctl exec function -f scripts/<script>.js --payload '<json>' -o json
```

`-o json` wraps the function return value under `.result`. When you need to inspect the result, read it directly from the output — no `jq` required. Pass the full raw output as `queries` to `run-analyzer.js` and it unwraps automatically.

## Parsing a dashboard URL

When the entry point is a Dynatrace dashboard URL, extract the three components the scripts need:

```
https://<tenant>/ui/apps/dynatrace.dashboards/dashboard/<ID>#from=<from>&to=<to>&vfilter_<name>=<val>...
```

| URL part | Script destination |
|---|---|
| Path segment after `/dashboard/` (before `#`) | `id` in extract-timeseries-dashboard.js payload |
| `#from=` value (URL-decode `%3A` → `:`) | `timeframe.startTime` in run-analyzer.js (only needed if running analysis) |
| `#to=` value (URL-decode) | `timeframe.endTime` in run-analyzer.js (only needed if running analysis) |
| `vfilter_<name>=<value>` params | `variables` map in run-analyzer.js (strip `vfilter_` prefix) |

The timeframe in the URL fragment is the dashboard's *display* window. It is **not** injected into the extracted DQL — the **extractor** returns the DQL verbatim with its original `$variable` tokens and any embedded `| timeframe` clauses intact. Use the parsed `from`/`to` values only when calling `run-analyzer.js` to set the analysis window. If the user just wants to list the queries, the timeframe is informational only.

Note: when you pass `run-analyzer.js` an **absolute** `timeframe.startTime` (not a `now...` expression), it strips any embedded `| timeframe ...` stage from the DQL before analysis, so the analyzer honors your requested window rather than the query's baked-in one. For relative (`now...`) windows the embedded `| timeframe` is left intact. This means the query actually analyzed can differ from the extracted text — expected behavior, noted here so results line up with the window you asked for.

Quick bash parse (pure bash + sed/awk — no python needed):
```bash
DASHBOARD_URL="https://abc123.apps.dynatrace.com/ui/apps/dynatrace.dashboards/dashboard/5bea16c7-029b-43b6-9735-459db2d25bbf#from=2026-05-28T04%3A00Z&to=2026-05-28T05%3A00Z&vfilter_host_group=prod&vfilter_workload=my-svc"

# Minimal URL-decoder: turn %XX into \xXX and let printf interpret it.
urldecode() { local s="${1//+/ }"; printf '%b' "${s//%/\\x}"; }

DOC_ID=$(echo "$DASHBOARD_URL" | sed 's/#.*//' | awk -F/ '{print $NF}')
FROM=$(urldecode "$(echo "$DASHBOARD_URL" | sed -n 's/.*[#&]from=\([^&]*\).*/\1/p')")
TO=$(urldecode "$(echo "$DASHBOARD_URL"   | sed -n 's/.*[#&]to=\([^&]*\).*/\1/p')")
HOST_GROUP=$(echo "$DASHBOARD_URL" | sed -n 's/.*[#&]vfilter_host_group=\([^&]*\).*/\1/p')
WORKLOAD=$(echo "$DASHBOARD_URL"   | sed -n 's/.*[#&]vfilter_workload=\([^&]*\).*/\1/p')
```

For notebooks: path segment after `/notebook/`, or `#share=` value for `/document/v0/#share=<ID>` links.

## Step 1 — Extract queries

### From a dashboard

```bash
# All tiles
dtctl exec function -f scripts/extract-timeseries-dashboard.js \
  --payload '{"id":"<dashboard-id-or-name>"}' -o json

# Only tiles whose title matches a name the user mentioned (e.g. "CPU usage", "Kafka lag")
dtctl exec function -f scripts/extract-timeseries-dashboard.js \
  --payload '{"id":"<dashboard-id>","titleFilter":"CPU usage"}' -o json
```

**When the user names a specific tile, chart, or section**, pass its name as `titleFilter` rather than extracting the full dashboard. `titleFilter` is a case-insensitive substring or `/regex/flags` pattern. This keeps the queryset small and focused.

**When it is not clear which tile(s) the user wants**, do NOT extract all DQL — dashboards can have 20–50 tiles and returning all queries causes significant context bloat. Instead use a two-step flow:

1. List tile names with `listOnly: true` (no DQL, just titles):
   ```bash
   dtctl exec function -f scripts/extract-timeseries-dashboard.js \
     --payload '{"id":"<dashboard-id>","listOnly":true}' -o json
   # Returns: {"result":{"ok":true,"tiles":[{"id":"...","title":"CPU Usage","visualization":"lineChart"},...]}}
   ```
2. Show the tile names to the user and ask which tile(s) they mean.
3. Re-run with `titleFilter` for only the tile(s) of interest.

This avoids pulling 20–50 DQL queries into context when only 1–2 are relevant.

Payload knobs:
- `id` (required) — dashboard ID (UUID) or exact name. Preset IDs like `my.dynatrace.infraops.preview.*` work.
- `titleFilter` — case-insensitive substring (`"CPU usage"`) or `/regex/flags` (`"/^kafka/i"`).
- `listOnly` — when `true`, returns `tiles: [{id, title, visualization}]` without DQL. Use for disambiguation.
- `compact` — when `true`, returns only `{id, title, dqlQuery}` per tile (drops description, visualization, isTimeseries). Saves ~40% per-tile tokens. In `listOnly` mode, drops visualization too.
- `includeSkipped` — when `true`, returns the full `skipped[]` array. Default: only `skippedCount` is returned.

Response envelope:
```json
{
  "ok": true,
  "documentId": "...", "documentName": "...", "documentVersion": 7,
  "queries": [
    { "id": "<tile-key>", "title": "...", "description": "...",
      "dqlQuery": "timeseries avg(dt.host.cpu.usage)",
      "visualization": "lineChart", "isTimeseries": true }
  ],
  "skipped": [{ "id": "...", "reason": "non-data tile (markdown)" }]
}
```

On failure: `{ "ok": false, "error": { "code": "...", "message": "..." } }`.

### From a notebook

Same envelope, different schema walk:

```bash
# All cells
dtctl exec function -f scripts/extract-timeseries-notebook.js \
  --payload '{"id":"<notebook-id-or-name>"}' -o json

# A specific section (if cell titles are set)
dtctl exec function -f scripts/extract-timeseries-notebook.js \
  --payload '{"id":"<notebook-id>","titleFilter":"JVM memory"}' -o json
```

Notebook cells often have empty titles — prefer addressing cells by `id` from the envelope if targeting a specific one.

## Step 2 — Run an analyzer

Save the extractor output to a file, then pass it via shell substitution — the shell reads the file, so the JSON never enters the model's context:

```bash
# Run extractor, save output
dtctl exec function -f scripts/extract-timeseries-dashboard.js \
  --payload '{"id":"<id>","titleFilter":"CPU usage","compact":true}' -o json > queryset.json

# Shell substitution: $(cat queryset.json) is expanded by the shell, not the model
dtctl exec function -f scripts/run-analyzer.js \
  --payload '{
    "analyzerName": "dt.statistics.NoveltyScoreAnalyzer",
    "queries": '"$(cat queryset.json)"',
    "timeframe": { "startTime": "...", "endTime": "..." },
    "analyzerParams": { ... }
  }' -o json
```

`run-analyzer.js` unwraps the `{"result":{...}}` dtctl envelope automatically — pass the raw saved output as-is. No `jq` or parsing step is needed: normalization of the array / envelope / dtctl-output shapes happens inside the script.

For large querysets (many tiles), the inline `$(cat ...)` form can hit shell argument-length limits. Build the payload file and use dtctl's `--data` flag instead — still no `jq` and still out of model context:

```bash
{ printf '{"analyzerName":"dt.statistics.NoveltyScoreAnalyzer","timeframe":{"startTime":"now-1h","endTime":"now"},"queries":'
  cat queryset.json
  printf '}'; } > payload.json

dtctl exec function -f scripts/run-analyzer.js --data payload.json -o json
```

Key payload knobs for `run-analyzer.js`:
- `minScore` — drop results below this threshold (e.g. `0.5`). Auto-detects score field from `noveltyScore`, `anomalyScore`, `correlationCoefficient`, `correlation`, `coefficient`. Pass `scoreField` to override.
- `scoreField` — explicit field name to read score from (e.g. `"noveltyScore"`).

The `queries` field accepts any of: a raw array, the extractor envelope (`{queries:[...]}`), or the full dtctl output (`{"result":{"queries":[...]}}`). All three are normalized automatically.

### Common analyzers

| Goal | analyzerName | analyzerParams |
|---|---|---|
| Find anomalous metrics | `dt.statistics.anomaly_detection.SeasonalBaselineAnomalyDetectionAnalyzer` | `{ "trainingTimeframe": { "startTime": "now-8d", "endTime": "now-1d" } }` (optional) |
| Score how novel each metric is | `dt.statistics.NoveltyScoreAnalyzer` | `{ "detectionMode": "ALL", "minNoveltyScore": 0 }` (optional) |
| Correlate against a primary metric | `dt.statistics.SimplePearsonCorrelationAnalyzer` | set `metricQuery` instead (changes call shape) |

### Correlation mode

Pass `metricQuery` to correlate every query in the set against a single primary DQL string:

```bash
dtctl exec function -f scripts/run-analyzer.js \
  --payload '{
    "analyzerName": "dt.statistics.SimplePearsonCorrelationAnalyzer",
    "queries": '"$(cat queryset.json)"',
    "metricQuery": "<dqlQuery of the primary tile, copied from extractor output>",
    "timeframe": { "startTime": "...", "endTime": "..." }
  }' -o json
```

When chaining from a previous analyzer run (e.g. anomaly detection → correlation), use `metricQueryFrom` instead. The script picks the highest-scored result's `dqlQuery` automatically:

```bash
dtctl exec function -f scripts/run-analyzer.js \
  --payload '{
    "analyzerName": "dt.statistics.SimplePearsonCorrelationAnalyzer",
    "queries": '"$(cat queryset.json)"',
    "metricQueryFrom": '"$(cat findings.json)"',
    "timeframe": { "startTime": "...", "endTime": "..." }
  }' -o json
```

`metricQuery` takes precedence if both are set.

### Variable substitution

Dashboard queries often contain `$variable` tokens (from URL `vfilter_*` params). Pass them via `variables` to substitute before execution:

```bash
dtctl exec function -f scripts/run-analyzer.js \
  --payload '{
    "analyzerName": "dt.statistics.anomaly_detection.SeasonalBaselineAnomalyDetectionAnalyzer",
    "queries": [...],
    "timeframe": { "startTime": "2026-05-28T04:00Z", "endTime": "2026-05-28T05:00Z" },
    "variables": { "host_group": "prod", "workload": "my-svc" }
  }' -o json
```

Build `variables` from `vfilter_*` URL params by stripping the `vfilter_` prefix. Trailing `*` wildcards are stripped automatically. Unresolved tokens are cleaned up from DQL filter clauses rather than left to error.

### Response shape

```json
{
  "ok": true,
  "checkedAt": "...",
  "analyzerName": "...",
  "summary": { "checked": 12, "completed": 11, "errors": 1 },
  "results": [
    {
      "id": "tile-key", "title": "CPU usage", "dqlQuery": "...",
      "output": <raw analyzer output>,
      "executionStatus": "COMPLETED"
    }
  ],
  "errors": [ { "id": "...", "error": "..." } ]
}
```

The `output` field is the raw analyzer result. Interpret it based on the analyzer:
- **Anomaly detection**: look for `anomalyScore`, `anomalies[]`, or `raisedAlerts[]` in each output entry. Score ≥ 0.7 → abnormal, ≥ 0.4 → borderline.
- **Novelty**: look for `noveltyScore` (or the closest score-like numeric field). Score ≥ 0.7 → novel.
- **Correlation**: look for `correlationCoefficient`. Sort by `|correlationCoefficient|` descending; drop entries where `|correlationCoefficient| < 0.5`.

## End-to-end: "what's abnormal on this dashboard?"

```bash
# 1. Extract queries — shell reads file, JSON stays out of model context
dtctl exec function -f scripts/extract-timeseries-dashboard.js \
  --payload '{"id":"5bea16c7-029b-43b6-9735-459db2d25bbf","compact":true}' \
  -o json > queryset.json

# 2. Run anomaly detection — $(cat queryset.json) expanded by shell, not model
dtctl exec function -f scripts/run-analyzer.js \
  --payload '{
    "analyzerName": "dt.statistics.anomaly_detection.SeasonalBaselineAnomalyDetectionAnalyzer",
    "queries": '"$(cat queryset.json)"',
    "timeframe": { "startTime": "2026-05-28T04:00Z", "endTime": "2026-05-28T05:00Z" },
    "variables": { "host_group": "prod", "workload": "my-svc" }
  }' -o json > findings.json

# 3. Correlate — metricQueryFrom picks the top finding automatically
dtctl exec function -f scripts/run-analyzer.js \
  --payload '{
    "analyzerName": "dt.statistics.SimplePearsonCorrelationAnalyzer",
    "queries": '"$(cat queryset.json)"',
    "metricQueryFrom": '"$(cat findings.json)"',
    "timeframe": { "startTime": "2026-05-28T04:00Z", "endTime": "2026-05-28T05:00Z" }
  }' -o json
```

## Verifying a single extracted query

Read the `dqlQuery` field from the extractor output and pass it directly:

```bash
dtctl query --query "<dqlQuery copied from extractor output>" -o json | head -40
```

## Gotchas

- **Never read raw dashboard JSON yourself.** `dtctl get dashboard <id> -o json` is typically 50–200 KB. The extractor reads it on the platform and returns a compact envelope (~5–15 KB).
- **Never extract all tiles when only one is needed.** A 50-tile dashboard returns 50 DQL queries into context. If the user names a tile, use `titleFilter`. If it's ambiguous, use `listOnly: true` first to ask which tile — then extract only that one.
- **Variables are required for filtered dashboards.** Queries with unsubstituted `$variable` tokens silently drop entity filters (e.g. `in(field, $undefined)` evaluates to `true`). Always pass `variables` when the URL has `vfilter_*` params.
- **Schema drift.** If a tile lands in `skipped` with reason `no DQL query found`, the dashboard schema has a query location the extractor doesn't know about — add it to the `pickQuery` candidate list in the script.
- **Analyzer availability.** Not all Davis analyzers are available on every tenant. If a call comes back with `Could not find an analyzer with name '...'` or `is not a function`, list what's actually registered: `dtctl get analyzers -o json`.
- **Statistical fallback removed.** `run-analyzer.js` only calls Davis analyzers. For historical anomaly detection, pass a long `trainingTimeframe` via `analyzerParams` (e.g. `{ "trainingTimeframe": { "startTime": "now-30d", "endTime": "now-1d" } }`), or query the DQL directly.
- **Comments in queries.** Queries starting with `// comment` lines are classified correctly by the extractor (leading line/block comments are stripped before the `timeseries` check).

## Scripts reference

- [scripts/extract-timeseries-dashboard.js](scripts/extract-timeseries-dashboard.js) — extracts timeseries DQL from a dashboard
- [scripts/extract-timeseries-notebook.js](scripts/extract-timeseries-notebook.js) — same for notebooks
- [scripts/run-analyzer.js](scripts/run-analyzer.js) — generic Davis analyzer runner
