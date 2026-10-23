# Trend Detection

Detect growth trends, week-over-week changes, and acceleration patterns in
service and infrastructure metrics. Use `timeseries-novelty-detection` for
structural break and trend onset detection; use the DQL patterns for growth
rate analysis and week-over-week comparisons.

---

## Dynatrace Trend Analyzers

### Change Point Detection

Detects when a metric's baseline permanently shifted (e.g., after a deployment).
Use this before declaring a trend to confirm it is a true structural change
vs. noise.

**Tool**: `timeseries-novelty-detection`
- `timeSeriesData`: `timeseries sum(dt.service.request.count), by:{dt.entity.service}, interval:1h | limit 10`
- `detectionMode`: `ALL`
- `analysisNoveltyType`: `["CHANGE_IN_VALUES", "CHANGE_IN_VARIABILITY"]`
- `minNoveltyScore`: `0.45`
- `significanceLevel`: `HIGH`
- `generalParameters.timeframe.startTime`: `now-30d`

For host CPU upward step changes:

**Tool**: `timeseries-novelty-detection`
- `timeSeriesData`: `timeseries avg(dt.host.cpu.usage), by:{dt.entity.host}, interval:1h | limit 10`
- `detectionMode`: `INCREASE`
- `analysisNoveltyType`: `["CHANGE_IN_VALUES"]`
- `minNoveltyScore`: `0.45`
- `significanceLevel`: `MEDIUM`
- `generalParameters.timeframe.startTime`: `now-30d`

### Trend Onset Detection

Detects when a metric starts moving in a sustained new direction (growing
or declining trend beginning):

**Tool**: `timeseries-novelty-detection`
- `timeSeriesData`: `timeseries avg(dt.service.request.response_time), by:{dt.entity.service}, interval:5m | limit 10`
- `detectionMode`: `ALL`
- `analysisNoveltyType`: `["TREND_IN_VALUES"]`
- `minNoveltyScore`: `0.45`
- `significanceLevel`: `HIGH`
- `filterSpikes`: `true`
- `generalParameters.timeframe.startTime`: `now-14d`

---

## DQL Trend Detection Patterns

Use these with `execute-dql` for quantified growth rates.

### Week-over-Week Request Volume Comparison

```dql
timeseries this_week = sum(dt.service.request.count),
  from: now()-7d, interval: 1h, by: {dt.smartscape.service}
| join [
    timeseries last_week = sum(dt.service.request.count),
      from: now()-14d, to: now()-7d, interval: 1h,
      by: {dt.smartscape.service}
  ], on: {left[dt.smartscape.service] == right[dt.smartscape.service]}
| fieldsAdd this_total = arraySum(this_week)
| fieldsAdd last_total = arraySum(right.last_week)
| filter isNotNull(this_total) and isNotNull(last_total) and last_total > 0
| fieldsAdd wow_change_pct = round((this_total - last_total) / last_total * 100, decimals: 1)
| sort wow_change_pct desc
| limit 20
| fields dt.smartscape.service, this_total, last_total, wow_change_pct
```

### Growth Rate Detection (30-Day Trend)

```dql
timeseries cpu = avg(dt.host.cpu.usage), from: now()-30d, interval: 1d,
  by: {dt.smartscape.host}
| fieldsAdd current = arrayLast(cpu)
| fieldsAdd baseline = arrayFirst(cpu)
| filter isNotNull(current) and isNotNull(baseline)
| fieldsAdd daily_growth = (current - baseline) / 30
| fieldsAdd total_growth_pct = round((current - baseline) / baseline * 100, decimals: 1)
| sort daily_growth desc
| limit 20
| fields dt.smartscape.host, baseline, current, daily_growth, total_growth_pct
```

### Acceleration Detection

Detect whether the rate of change is itself increasing:

```dql
timeseries cpu = avg(dt.host.cpu.usage), from: now()-14d, interval: 1d,
  by: {dt.smartscape.host}
| fieldsAdd diffs = arrayDiff(cpu)
| fieldsAdd avg_acceleration = arrayAvg(diffs)
| fieldsAdd current = arrayLast(cpu)
| filter isNotNull(current) and avg_acceleration > 0
| sort avg_acceleration desc
| limit 20
| fields dt.smartscape.host, current, avg_acceleration
```

### Service Error Rate Trend

```dql
timeseries {
  errors = sum(dt.service.request.failure_count),
  total = sum(dt.service.request.count)
}, from: now()-7d, interval: 1h, by: {dt.smartscape.service}
| fieldsAdd error_rate_now = arrayLast(errors) / arrayLast(total) * 100
| fieldsAdd error_rate_7d_avg = arrayAvg(errors) / arrayAvg(total) * 100
| filter isNotNull(error_rate_now) and error_rate_7d_avg > 0
| fieldsAdd rate_change = error_rate_now - error_rate_7d_avg
| sort rate_change desc
| limit 20
| fields dt.smartscape.service, error_rate_now, error_rate_7d_avg, rate_change
```

### Service Response Time Trend (Week-over-Week)

```dql
timeseries rt_now = avg(dt.service.request.response_time),
  from: now()-7d, interval: 1h, by: {dt.smartscape.service}
| join [
    timeseries rt_prev = avg(dt.service.request.response_time),
      from: now()-14d, to: now()-7d, interval: 1h,
      by: {dt.smartscape.service}
  ], on: {left[dt.smartscape.service] == right[dt.smartscape.service]}
| fieldsAdd avg_now = arrayAvg(rt_now) / 1000
| fieldsAdd avg_prev = arrayAvg(right.rt_prev) / 1000
| filter isNotNull(avg_now) and avg_prev > 0
| fieldsAdd wow_change_pct = round((avg_now - avg_prev) / avg_prev * 100, decimals: 1)
| sort wow_change_pct desc
| limit 20
| fields dt.smartscape.service, avg_now, avg_prev, wow_change_pct
```

---

## Trend Result Presentation

| Column | Content |
|--------|---------|
| Rank | 🥇 🥈 🥉 by growth rate (descending) |
| Service / Host | Entity |
| Baseline | Value at start of window |
| Current | Latest value |
| Growth/Day | Daily rate of change |
| WoW Change | Week-over-week % change |
| Action | ✅ Stable / ⚠️ Monitor / 🔴 Escalate |

---

## Best Practices

- Use `timeseries-novelty-detection` first to confirm a trend is structural,
  not just noise; `filterSpikes: true` removes transient spikes before
  trend analysis
- Use `CHANGE_IN_VALUES` for step changes (permanent baseline shifts);
  use `TREND_IN_VALUES` for gradual directional movement
- Week-over-week joins require identical `interval:` values on both sides
  so join keys align; right-side fields are prefixed with `right.`
- `dt.service.request.response_time` is in microseconds — divide by
  `1000` for ms
- A positive acceleration (`arrayAvg(arrayDiff(arr)) > 0`) means the metric
  is speeding up — worth flagging even if the current value is acceptable
