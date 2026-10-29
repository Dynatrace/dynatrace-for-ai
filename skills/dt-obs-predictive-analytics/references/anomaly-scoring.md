# Anomaly Scoring and Detection

Detect anomalies using Dynatrace analyzer tools. Use the DQL patterns
below for transparent, tunable scoring when you need explicit deviation
numbers alongside the analyzer output.

---

## Dynatrace Anomaly Detection Tools

> **When to use this reference vs. novelty detection**
>
> The three anomaly detector tools (`adaptive`, `seasonal`, `static`) answer **"is this metric currently violating an expected range?"** They operate on a sliding window of recent samples and fire when enough consecutive samples breach a learned or fixed threshold. Use them to rank entities by ongoing severity or to confirm a sustained problem.
>
> Use `timeseries-novelty-detection` (see `references/novelty-detection.md`) when the question is **"did this metric change?"** — no threshold required, answers *whether* the signal's character shifted and *when*. Running an anomaly detector fleet-wide to find "what changed" typically flags every service with any variation; novelty detection is the correct tool for that question.

| Tool | Answers | Best For |
|------|---------|---------|
| `adaptive-anomaly-detector` | "Is it currently above/below normal?" | General-purpose; learns threshold from signal distribution |
| `seasonal-baseline-anomaly-detector` | "Is it above/below normal *for this time of day/week*?" | Metrics with daily/weekly/variable seasonality |
| `static-threshold-analyzer` | "Is it above/below a fixed limit?" | Known, fixed upper/lower limits (e.g., CPU > 90%) |
| `timeseries-novelty-detection` | "Did the signal's behavior change?" | Step changes, spikes, trend onset — no threshold needed |

All tools return a `raisedAlerts` array per entity; an empty `output` array
means no anomalies were detected in the analysis window.

### Adaptive Anomaly Detection

Learns a dynamic threshold from the signal's own distribution.
Good default for most host and service metrics.

**Tool**: `adaptive-anomaly-detector`
- `timeSeriesData`: `timeseries avg(dt.host.cpu.usage), by:{dt.entity.host}, interval:1m | limit 20`
- `numberOfSignalFluctuations`: `1.0` — multiplier for threshold width; increase to reduce sensitivity
- `alertCondition`: `ABOVE`
- `violatingSamples`: `3` — consecutive violations required before alerting
- `slidingWindow`: `5`
- `generalParameters.timeframe.startTime`: `now-24h`

### Seasonal Baseline Anomaly Detection

Accounts for daily/weekly patterns. `tolerance` controls sensitivity —
lower value = more alerts (valid range 0.1–10.0; default 4.0).

**Tool**: `seasonal-baseline-anomaly-detector`
- `timeSeriesData`: `timeseries sum(dt.service.request.count), by:{dt.entity.service}, interval:5m | limit 10`
- `tolerance`: `3.0`
- `violatingSamples`: `3`
- `slidingWindow`: `5`
- `alertCondition`: `OUTSIDE`
- `generalParameters.timeframe.startTime`: `now-7d`

### Static Threshold Detection

Use when the acceptable limit is known and stable (e.g., CPU > 90%).
`threshold` must be in the base unit of the queried metric (response time
metrics use microseconds — set 5 seconds as `5000000`, not `5000`).

**Tool**: `static-threshold-analyzer`
- `timeSeriesData`: `timeseries avg(dt.host.cpu.usage), by:{dt.entity.host}, interval:1m | limit 20`
- `threshold`: `90`
- `alertCondition`: `ABOVE`
- `violatingSamples`: `3`
- `slidingWindow`: `5`
- `generalParameters.timeframe.startTime`: `now-24h`

### Novelty Detection

Detects previously unseen patterns, including step changes, trend onsets,
and isolated spikes. Use `analysisNoveltyType` to focus on specific event types.

**Tool**: `timeseries-novelty-detection`
- `timeSeriesData`: `timeseries sum(dt.service.request.failure_count), by:{dt.entity.service}, interval:5m | limit 10`
- `detectionMode`: `ALL`
- `minNoveltyScore`: `0.45` (0.0–1.0; higher = fewer but more confident detections)
- `significanceLevel`: `HIGH`
- `analysisNoveltyType`: `["CHANGE_IN_VALUES", "SPIKE", "TREND_IN_VALUES"]`
- `generalParameters.timeframe.startTime`: `now-7d`

Available novelty types: `CHANGE_IN_VALUES`, `CHANGE_IN_VARIABILITY`,
`CHANGE_IN_MISSING_VALUES`, `GAP_WITH_MISSING_VALUES`, `TREND_IN_VALUES`, `SPIKE`.

---

## Anomaly Types

| Type | Description | Detection Approach |
|------|-------------|-------------------|
| **Point** | Single isolated spike | `adaptive-anomaly-detector` + DQL p95 |
| **Contextual** | Anomalous only in a specific context (e.g., 3 AM spike) | `seasonal-baseline-anomaly-detector` |
| **Collective** | Sustained group deviation | `adaptive-anomaly-detector` with wider `slidingWindow` |
| **Step change** | Abrupt permanent baseline shift | `timeseries-novelty-detection` with `CHANGE_IN_VALUES` |
| **Novel pattern** | Previously unseen shape | `timeseries-novelty-detection` with `SPIKE` or `TREND_IN_VALUES` |

---

## Result Presentation

| Column | Content |
|--------|---------|
| Rank | 🥇 🥈 🥉 by deviation magnitude |
| Signal / Entity | Metric name and entity |
| Observed | Actual value at anomaly point |
| Expected | Baseline or forecast band |
| Deviation | % or absolute deviation |
| Type | Point / Contextual / Collective / Step / Novel |
| Action | ✅ Monitor / ⚠️ Investigate / 🔴 Escalate |

---

## Best Practices

- Compare anomaly candidates against the same time window in the prior
  day/week before escalating
- Consider seasonality — a spike at Monday 9 AM may be expected
- Correlate Davis AI findings with DQL scores to prioritize what matters
- `dt.service.request.response_time` is in microseconds — divide by
  `1000` for ms before scoring
- For `static-threshold-analyzer`, always set `threshold` in the metric's
  base unit (microseconds for response time, percent for CPU)
- `violatingSamples` must not exceed `slidingWindow`
