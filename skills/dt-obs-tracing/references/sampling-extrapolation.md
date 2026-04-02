# Sampling and Extrapolation

One span can represent multiple real operations due to aggregation or sampling. Extrapolation is needed to accurately count operations.

## Types of Sampling

### Aggregation

Certain operations (especially database calls) can be aggregated into a single span. Aggregated spans contain `aggregation.count` attribute.

### Adaptive Traffic Management (ATM)

Rate-limiting, head-based sampling that adaptively reacts to request rates. Decision made at trace start by the agent.

### Adaptive Load Reduction (ALR)

Server-side sampling to protect backend infrastructure from overload.

### Read Sampling

Control data volume read in queries via `samplingRatio` parameter:

- Available rates: `1`, `10`, `100`, `1000`, `10000`, `100000`
- `1` = 100% of data, `100` = 1% of data
- Actual ratio accessible via `dt.system.sampling_ratio`
- Sampling is trace-aware: either all spans of a trace or none

## Extrapolation Formula

Calculate multiplicity factor to extrapolate span counts to actual operation counts:

```dql
fetch spans, from:now() - 1h
| filter request.is_root_span == true
| fieldsAdd sampling.probability = (power(2, 56) - coalesce(sampling.threshold, 0)) * power(2, -56)
| fieldsAdd sampling.multiplicity = 1 / sampling.probability
| fieldsAdd multiplicity = coalesce(sampling.multiplicity, 1)
                         * coalesce(aggregation.count, 1)
                         * dt.system.sampling_ratio
| limit 10
```

## Request Count Extrapolation

### Extrapolated Request Counting

Count requests with proper extrapolation:

```dql
fetch spans
, samplingRatio:100  // Read only 1% of data

| filter request.is_root_span == true

// Calculate multiplicity factor
| fieldsAdd sampling.probability = (power(2, 56) - coalesce(sampling.threshold, 0)) * power(2, -56)
| fieldsAdd sampling.multiplicity = 1/sampling.probability
| fieldsAdd multiplicity = coalesce(sampling.multiplicity, 1)
                         * coalesce(aggregation.count, 1)
                         * dt.system.sampling_ratio

| summarize
    span_count=count(),
    request_count_extrapolated = sum(multiplicity)
```

## Database Call Extrapolation

### Database Operations with Extrapolation

Count and time database calls accurately:

```dql
fetch spans
, samplingRatio:100  // Read only 1% of data

| filter isNotNull(db.query.text)

// Calculate multiplicity factor
| fieldsAdd sampling.probability = (power(2, 56) - coalesce(sampling.threshold, 0)) * power(2, -56)
| fieldsAdd sampling.multiplicity = 1 / sampling.probability
| fieldsAdd multiplicity = coalesce(sampling.multiplicity, 1)
                         * coalesce(aggregation.count, 1)
                         * dt.system.sampling_ratio

// Calculate average duration for aggregated spans
| fieldsAdd aggregation.duration_avg = coalesce(aggregation.duration_sum / aggregation.count, duration)

| summarize {
    operation_count_extrapolated = sum(multiplicity),
    operation_duration_extrapolated = sum(aggregation.duration_avg * multiplicity) / sum(multiplicity)
}
```

## Working with Aggregated Spans

### Duration Calculation

For aggregated database spans, calculate average duration:

```dql
fetch spans, from:now() - 1h
| filter isNotNull(db.query.text)
| fieldsAdd aggregation.duration_avg = coalesce(
    aggregation.duration_sum / aggregation.count,
    duration
)
| limit 10
```

### Database Analysis by Statement

Extrapolated database calls per service:

```dql
fetch spans
| filter span.kind == "client" and isNotNull(db.namespace)
| fieldsAdd getNodeName(dt.smartscape.service)

// Calculate multiplicity
| fieldsAdd sampling.probability = (power(2, 56) - coalesce(sampling.threshold, 0)) * power(2, -56)
| fieldsAdd sampling.multiplicity = 1/sampling.probability
| fieldsAdd multiplicity = coalesce(sampling.multiplicity, 1)
                         * coalesce(aggregation.count, 1)
                         * dt.system.sampling_ratio

| summarize {
    db_calls = sum(multiplicity)
  }, by: { dt.smartscape.service.name, code.function, db.system, db.namespace, db.query.text }
| sort db_calls desc
| limit 100
```

## Best Practices

- **Always extrapolate** when counting operations (not just spans)
- **Use `samplingRatio` parameter** to reduce data read for better performance
- **Check for `aggregation.count`** to identify aggregated spans
- **Calculate `multiplicity`** as product of: sampling multiplicity × aggregation count × read sampling ratio
- **Use `aggregation.duration_avg`** for duration analysis on aggregated spans
- **Fallback to `duration`** when `aggregation.duration_sum` is not present
- **Read sampling is trace-aware** - you get complete traces or none at a given ratio

---

**← Back to**: [Application Tracing Skill](../SKILL.md)
