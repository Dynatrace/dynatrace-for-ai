# Frontend Request Performance Metrics

Monitor frontend request performance, response times, and throughput using aggregated RUM metrics.

**Data Source:** `timeseries` with `dt.frontend.request.*` metrics

**Key Metrics:**

- `dt.frontend.request.count` - Total frontend requests
- `dt.frontend.request.duration` - Request response times in milliseconds

**Alerting Thresholds:**

- Critical: p95 duration > SLA threshold (typically 2-3s)
- Warning: p95 duration approaching SLA threshold
- Track performance degradation > 20% hour-over-hour

## Request Throughput Analysis

Monitor frontend request volume and patterns:

```dql
timeseries request_count = sum(dt.frontend.request.count),
          by: {frontend.name, device.type},
          from: now() - 2h

| fieldsAdd
    app_name = frontend.name,
    requests_per_minute = request_count[] / 60
| filter arrayAvg(requests_per_minute) > 100
| sort request_count desc

```

**Use Case:** Track frontend request volume by application and device type.

## Request Duration Performance

Analyze frontend request latency:

```dql
timeseries avg_duration = avg(dt.frontend.request.duration),
          p75_duration = percentile(dt.frontend.request.duration, 75),
          p95_duration = percentile(dt.frontend.request.duration, 95),
          by: {frontend.name},
          from: now() - 1h
| filter arrayAvg(p95_duration) > 3000
| sort p95_duration desc

```

**Use Case:** Identify applications with slow request response times.

## Browser-Specific Performance

Detect browser-specific performance degradation:

```dql
timeseries p90_duration = percentile(dt.frontend.request.duration, 90),
          request_count = sum(dt.frontend.request.count),
          by: {frontend.name, browser.name},
          from: now() - 2h

| fieldsAdd
    app_name = frontend.name,
    duration_sec = p90_duration[] / 1000
| filter arrayAvg(request_count) > 100
| sort p90_duration desc

```

**Use Case:** Identify browser compatibility issues or optimization opportunities.

## Device Type Performance Comparison

Compare performance across mobile, desktop, and tablet:

```dql
timeseries request_count = sum(dt.frontend.request.count),
          p50_duration = percentile(dt.frontend.request.duration, 50),
          p90_duration = percentile(dt.frontend.request.duration, 90),
          by: {frontend.name, device.type},
          from: now() - 6h

| fieldsAdd
    app_name = frontend.name,
    p50_sec = p50_duration[] / 1000,
    p90_sec = p90_duration[] / 1000
| filter arrayAvg(request_count) > 20
| sort device.type, p90_duration desc

```

**Use Case:** Optimize mobile experience by identifying performance gaps.

## Operating System Performance

Identify OS-specific performance characteristics:

```dql
timeseries request_count = sum(dt.frontend.request.count),
          p75_duration = percentile(dt.frontend.request.duration, 75),
          p95_duration = percentile(dt.frontend.request.duration, 95),
          by: {frontend.name, os.name},
          from: now() - 2h

| fieldsAdd
    app_name = frontend.name,
    p75_sec = p75_duration[] / 1000,
    p95_sec = p95_duration[] / 1000
| filter arrayAvg(request_count) > 50
| sort p95_duration desc

```

**Use Case:** Optimize for dominant operating systems or identify OS-specific issues.

## Request Performance SLA Monitoring

Track adherence to performance SLAs:

```dql
timeseries request_count = sum(dt.frontend.request.count),
          avg_duration = avg(dt.frontend.request.duration),
          p95_duration = percentile(dt.frontend.request.duration, 95),
          by: {frontend.name},
          from: now() - 1h

| fieldsAdd
    app_name = frontend.name,
    sla_threshold = 2s
| fieldsAdd
    sla_met = if(p95_duration[] < sla_threshold, "yes", else: "no"),
    sla_buffer = sla_threshold - p95_duration[]
| sort sla_buffer asc

```

**Use Case:** Monitor and report on performance SLA compliance.

