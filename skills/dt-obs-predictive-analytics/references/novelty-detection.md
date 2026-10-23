# Novelty Detection

Use `timeseries-novelty-detection` to check whether a time series showed a
significant change in the **character** of its behavior during a given period.
Unlike threshold-based detectors, novelty detection does not require a known
acceptable limit — it learns what "normal" looks like and flags anything that
is structurally new: spikes, drops, step changes, shifts in variability, or
the onset of a sustained trend.

---

## When to Use

| Scenario | Example question |
|----------|-----------------|
| **Spike or drop check** | "Did this metric show any sudden spikes in the last 24 h?" |
| **Step change / baseline shift** | "Did CPU usage permanently jump after last night's deployment?" |
| **Trend onset** | "When did memory start trending upward?" |
| **Variability change** | "Is request latency becoming more erratic than before?" |
| **General novel behavior** | "Did anything unusual happen to this signal in the last 7 days?" |

Use this tool as the **first check** when you suspect something changed but
you do not yet know what kind of change it was. Run it with
`analysisNoveltyType: ["SPIKE", "CHANGE_IN_VALUES", "TREND_IN_VALUES"]` and
let the results tell you the category before you narrow in.

**Do not use anomaly detectors (`adaptive-anomaly-detector`, `seasonal-baseline-anomaly-detector`,
`static-threshold-analyzer`) to answer "did this metric change?" questions.**
Those tools count how long a metric stays outside a learned or fixed threshold — they confirm
*ongoing severity*, not the presence of a change. On a broad fleet query they will flag every
service that has *any* variation, producing low-signal results. Novelty detection is the correct
first tool whenever the question contains "changed", "shifted", "spiked", "dropped", "started",
"when did", or "did anything unusual happen".

---

## Tool Parameters

**Tool**: `timeseries-novelty-detection`

| Parameter | Type | Description |
|-----------|------|-------------|
| `timeSeriesData` | DQL string | A `timeseries` query that returns the signal to analyze. Must use `dt.entity.*` fields in `by:{}` grouping (not `dt.smartscape.*`). Add `\| limit N` to control how many entities are analyzed. |
| `detectionMode` | enum | Direction filter: `ALL` (both), `INCREASE` (rises only), `DECREASE` (drops only) |
| `analysisNoveltyType` | array | Which novelty types to look for — see table below |
| `minNoveltyScore` | float 0.0–1.0 | Confidence threshold; `0.45` is a reasonable default. Raise to `0.6–0.8` to reduce false positives. |
| `significanceLevel` | enum | `LOW`, `MEDIUM`, `HIGH` — filters by statistical significance; prefer `HIGH` for production alerting |
| `filterSpikes` | bool | When `true`, transient spikes are removed before trend/change-point analysis. Set `true` when looking for structural changes, `false` when spikes are themselves the signal of interest. |
| `generalParameters.timeframe.startTime` | string | Analysis window start, e.g. `now-7d`, `now-24h` |

### Novelty Types

| `analysisNoveltyType` value | What it detects |
|-----------------------------|----------------|
| `SPIKE` | Short-lived spike (value shoots up then returns) |
| `CHANGE_IN_VALUES` | Abrupt, permanent shift in the mean — step change or baseline jump |
| `TREND_IN_VALUES` | Sustained directional movement starting from a specific point |
| `CHANGE_IN_VARIABILITY` | The signal becomes significantly more or less noisy |
| `CHANGE_IN_MISSING_VALUES` | The rate of null/missing data points changes |
| `GAP_WITH_MISSING_VALUES` | A contiguous gap of missing data appears |

Combine multiple types in one call: `["SPIKE", "CHANGE_IN_VALUES", "TREND_IN_VALUES"]`.

---

## Worked Examples

### Check for any novel behavior (general anomaly sweep)

Use as a first-pass detector across a set of entities when you suspect
something changed but do not know the shape:

**Tool**: `timeseries-novelty-detection`
- `timeSeriesData`: `timeseries avg(dt.host.cpu.usage), by:{dt.entity.host}, interval:5m | limit 20`
- `detectionMode`: `ALL`
- `analysisNoveltyType`: `["SPIKE", "CHANGE_IN_VALUES", "TREND_IN_VALUES", "CHANGE_IN_VARIABILITY"]`
- `minNoveltyScore`: `0.45`
- `significanceLevel`: `HIGH`
- `generalParameters.timeframe.startTime`: `now-24h`

### Spike and drop detection (isolated events)

Check whether a service's error rate showed any sudden spikes or drops in a
recent incident window:

**Tool**: `timeseries-novelty-detection`
- `timeSeriesData`: `timeseries sum(dt.service.request.failure_count), by:{dt.entity.service}, interval:1m | limit 10`
- `detectionMode`: `ALL`
- `analysisNoveltyType`: `["SPIKE"]`
- `minNoveltyScore`: `0.5`
- `significanceLevel`: `MEDIUM`
- `filterSpikes`: `false`
- `generalParameters.timeframe.startTime`: `now-6h`

### Step change after a deployment

Confirm whether a deployment caused a permanent baseline shift (not just a
transient spike):

**Tool**: `timeseries-novelty-detection`
- `timeSeriesData`: `timeseries avg(dt.service.request.response_time), by:{dt.entity.service}, interval:5m | limit 10`
- `detectionMode`: `INCREASE`
- `analysisNoveltyType`: `["CHANGE_IN_VALUES"]`
- `minNoveltyScore`: `0.55`
- `significanceLevel`: `HIGH`
- `filterSpikes`: `true`
- `generalParameters.timeframe.startTime`: `now-48h`

### Trend onset detection

Identify when a gradual upward or downward trend began:

**Tool**: `timeseries-novelty-detection`
- `timeSeriesData`: `timeseries avg(dt.host.memory.usage.percent), by:{dt.entity.host}, interval:1h | limit 15`
- `detectionMode`: `INCREASE`
- `analysisNoveltyType`: `["TREND_IN_VALUES"]`
- `minNoveltyScore`: `0.45`
- `significanceLevel`: `HIGH`
- `filterSpikes`: `true`
- `generalParameters.timeframe.startTime`: `now-30d`

### Variability change (signal becoming erratic)

Detect when a metric that was previously stable starts fluctuating:

**Tool**: `timeseries-novelty-detection`
- `timeSeriesData`: `timeseries avg(dt.service.request.response_time), by:{dt.entity.service}, interval:5m | limit 10`
- `detectionMode`: `ALL`
- `analysisNoveltyType`: `["CHANGE_IN_VARIABILITY"]`
- `minNoveltyScore`: `0.45`
- `significanceLevel`: `MEDIUM`
- `generalParameters.timeframe.startTime`: `now-14d`

---

## Interpreting Results

The tool returns a `raisedAlerts` array per entity. Each alert includes:
- The **novelty type** that was detected
- A **novelty score** (0.0–1.0) — higher means more confident
- The **time range** where the novelty was detected

An empty `output` array (or no `raisedAlerts` entries) means the signal
showed no significant novel behavior in the analysis window.

| Novelty Score | Interpretation |
|--------------|---------------|
| 0.0–0.44 | Below threshold — not reported (filtered by `minNoveltyScore`) |
| 0.45–0.59 | Probable novelty — worth investigating |
| 0.60–0.79 | Likely novelty — act or escalate |
| 0.80–1.0 | High-confidence novelty — treat as confirmed |

---

## Result Presentation

| Column | Content |
|--------|---------|
| Rank | 🥇 🥈 🥉 by novelty score descending |
| Entity | Host, service, or other entity |
| Novelty Type | SPIKE / CHANGE_IN_VALUES / TREND_IN_VALUES / CHANGE_IN_VARIABILITY |
| Score | 0.0–1.0 confidence |
| Detected Window | Start–end of the novel period |
| Action | ✅ No action / ⚠️ Investigate / 🔴 Escalate |

---

## Best Practices

- Set `filterSpikes: true` when looking for structural changes (step changes,
  trends) — spikes inflate variance and can obscure change-point detection
- Set `filterSpikes: false` when spikes *are* the signal of interest
- Use `INCREASE` / `DECREASE` mode to reduce noise when the anomaly direction
  is known from context (e.g., "CPU went up after deploy")
- Combine with `adaptive-anomaly-detector` or `seasonal-baseline-anomaly-detector`
  for cross-validation: novelty detection finds *when* the character changed;
  threshold detectors confirm *how much* it exceeds acceptable limits
- `dt.service.request.response_time` is in microseconds — results are returned
  in that unit; divide by `1000` when presenting ms values
- Keep `| limit N` in the DQL query low (10–20) for faster results; increase
  only when a full fleet sweep is required
