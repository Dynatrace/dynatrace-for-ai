# Performance Analysis

Analyze response times, percentiles, and create timeseries from span data using DQL aggregation functions.

## Response Time Analysis

### Service Response Times with Percentiles

Calculate average, median, and percentiles:

```dql
fetch spans
| filter contains(http.route, "storage")
| summarize {
    count(),
    avg=avg(duration),
    p50=median(duration),
    p99=percentile(duration, 99)
  }, by: { http.request.method, http.route }
```

### Response Time Buckets

Group requests into duration buckets with trace exemplars:

```dql
fetch spans, from:now() - 24h
| filter http.route == "/api/v1/storage/findByISBN"
| summarize {
    spans=count(),
    trace=takeAny(record(start_time, trace.id))
  }, by: { bin(duration, 10ms) }
| fields `bin(duration, 10ms)`, spans, trace.id=trace[trace.id], start_time=trace[start_time]
```

This creates 10ms buckets and captures an example trace from each bucket for investigation.

## Timeseries Extraction

### Basic Timeseries

Extract average response time as timeseries:

```dql
fetch spans, from:now() - 24h
| filter http.route == "/api/v1/storage/findByISBN"
| makeTimeseries { avg=avg(duration) }, by: { http.route }, bins:250
```

### Multi-Metric Timeseries

Create timeseries with multiple metrics:

```dql
fetch spans, from:now() - 24h
| filter request.is_root_span == true
| makeTimeseries {
    requests=count(),
    avg_duration=avg(duration),
    p95=percentile(duration, 95),
    p99=percentile(duration, 99)
  }, by: { endpoint.name }
```

### Failed Requests Over Time

Chart failure rates as timeseries:

```dql
fetch spans, from:now() - 7d
| filter request.is_root_span == true
| makeTimeseries {
    failed_requests=countIf(request.is_failed == true)
  }, by: {endpoint.name}
```

## Endpoint Performance

### Top Slow Endpoints

Identify slowest endpoints:

```dql
fetch spans, from:now() - 1h
| filter request.is_root_span == true
| summarize {
    requests=count(),
    avg_duration=avg(duration),
    p95=percentile(duration, 95),
    p99=percentile(duration, 99)
  }, by: { endpoint.name }
| sort p99 desc
| limit 10
```

### Performance by Service and Endpoint

Break down performance by service:

```dql
fetch spans
| filter request.is_root_span == true
| fieldsAdd getNodeName(dt.smartscape.service)
| summarize {
    requests=count(),
    avg_response_time=avg(duration)
  }, by: { dt.smartscape.service, dt.smartscape.service.name, endpoint.name }
| sort requests desc
```

## Best Practices

- **Use percentiles** (`p50`, `p95`, `p99`) over averages for better performance insights
- **Include trace exemplars** with `takeAny(record(start_time, trace.id))` for drilldown capability
- **Use `bin()`** to create duration buckets for distribution analysis
- **Set appropriate `bins` parameter** in `makeTimeseries` (default varies, 250 is common)
- **Filter by `request.is_root_span`** when analyzing end-to-end request performance
- **Combine with service context** using `getNodeName(dt.smartscape.service)` for service-level analysis

---

**← Back to**: [Application Tracing Skill](../SKILL.md)
