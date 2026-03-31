# Advanced Frontend Performance Analysis

Advanced performance analysis including geographic distribution, correlations, and regression detection.

**Use Cases:**

- CDN optimization for regional performance
- Correlate performance with error rates
- Detect regressions after deployments
- Compare synthetic vs real user performance

## Geographic Performance Distribution

Compare request performance across regions:

```dql
timeseries request_count = sum(dt.frontend.request.count),
          avg_duration = avg(dt.frontend.request.duration),
          by: {frontend.name, geo.country.iso_code},
          from: now() - 4h

| fieldsAdd
    app_name = frontend.name,
    avg_duration_sec = avg_duration / 1000
| filter request_count > 50
| sort avg_duration desc

```

**Use Case:** Identify geographic regions experiencing poor performance for CDN optimization.

## Performance vs Error Rate Correlation

Correlate slow requests with error occurrences:

```dql
timeseries request_count = sum(dt.frontend.request.count),
          error_count = sum(dt.frontend.error.count),
          avg_duration = avg(dt.frontend.request.duration),
          by: {frontend.name},
          from: now() - 1h

| fieldsAdd
    app_name = frontend.name,
    error_rate_percent = (error_count / request_count) * 100,
    avg_duration_sec = avg_duration / 1000
| filter error_rate_percent > 5
| sort error_rate_percent desc

```

**Use Case:** Identify if slow requests correlate with increased error rates.

## Request Performance Degradation Detection

Monitor request duration trends for regressions:

```dql
timeseries {
    avg_duration = avg(dt.frontend.request.duration),
    p95_duration = percentile(dt.frontend.request.duration, 95),
    request_count = sum(dt.frontend.request.count)
},
  by: {frontend.name},
  from: now() - 24h,
  interval: 1h

| join [
  timeseries {
    prev_avg_duration = avg(dt.frontend.request.duration)
  },
    by: {frontend.name},
    from: now() - 24h,
    interval: 1h,
    shift: 1h

], on: { frontend.name }, fields: { prev_avg_duration }

| fieldsAdd
    app_name = frontend.name,
    duration_change_percent = coalesce((avg_duration[] - prev_avg_duration[]) / (prev_avg_duration[]) * 100, 0)
| filter duration_change_percent > 20
| sort duration_change_percent desc

```

**Use Case:** Detect performance regressions after deployments or infrastructure changes.

## User Type Performance Analysis

Compare performance for different user segments:

```dql
timeseries request_count = sum(dt.frontend.request.count),
          avg_duration = avg(dt.frontend.request.duration),
          p90_duration = percentile(dt.frontend.request.duration, 90),
          by: {frontend.name, dt.rum.user_type},
          from: now() - 4h

| fieldsAdd
    app_name = frontend.name,
    avg_duration_sec = avg_duration / 1000,
    p90_duration_sec = p90_duration / 1000
| filter request_count > 10
| sort dt.rum.user_type, p90_duration desc

```

**Use Case:** Ensure consistent performance across synthetic, real user, and robot traffic.
