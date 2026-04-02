# Performance Analysis & Diagnostics

Advanced performance analysis including request timing, navigation patterns, geographic distribution, long tasks, and regression detection.

## Request Performance Metrics

Monitor frontend request performance, response times, and throughput using aggregated RUM metrics.

**Data Source:** `timeseries` with `dt.frontend.request.*` metrics

**Key Metrics:**

- `dt.frontend.request.count` - Total frontend requests
- `dt.frontend.request.duration` - Request response times in milliseconds

**Alerting Thresholds:**

- Critical: p95 duration > SLA threshold (typically 2-3s)
- Warning: p95 duration approaching SLA threshold
- Track performance degradation > 20% hour-over-hour

### Request Throughput Analysis

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

### Request Duration Performance

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

### Request Performance SLA Monitoring

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

## Request Timing Analysis

Analyze W3C Resource Timing data to diagnose WHERE latency occurs in frontend requests.

**Data Source:** `fetch user.events` with `characteristics.has_request == true`

**Key Timing Phases (all in nanoseconds):**

- `performance.domain_lookup_start/end` - DNS resolution
- `performance.connect_start/end` - TCP connection
- `performance.secure_connection_start` - TLS handshake start
- `performance.request_start` - Request sent to server
- `performance.response_start` - First byte received (TTFB)
- `performance.response_end` - Download complete

### Request Timing Breakdown

Analyze timing phases for slow requests:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| filter duration > 1s
| fieldsAdd
    dns_time = performance.domain_lookup_end - performance.domain_lookup_start,
    connect_time = performance.connect_end - performance.connect_start,
    tls_time = performance.connect_end - performance.secure_connection_start,
    server_time = performance.response_start - performance.request_start,
    download_time = performance.response_end - performance.response_start
| summarize
    avg_dns = avg(dns_time),
    avg_connect = avg(connect_time),
    avg_tls = avg(tls_time),
    avg_server = avg(server_time),
    avg_download = avg(download_time),
    request_count = count(),
    by: {url.domain}
| sort avg_server desc
| limit 20
```

**Use Case:** Identify bottleneck phase (DNS, connection, server, download).

### Third-Party Resource Performance

Compare first-party vs third-party resource timing:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| summarize
    avg_duration = avg(duration),
    p75_duration = percentile(duration, 75),
    request_count = count(),
    by: {url.provider, url.domain}
| filter request_count > 50
| sort p75_duration desc
| limit 30
```

**Use Case:** Identify slow third-party resources impacting page performance.

### HTTP Protocol Performance

Analyze performance by HTTP protocol version:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| summarize
    avg_duration = avg(duration),
    p90_duration = percentile(duration, 90),
    request_count = count(),
    by: {performance.next_hop_protocol}
| sort request_count desc
```

**Use Case:** Compare HTTP/1.1 vs HTTP/2 vs HTTP/3 performance.

### Response Size Analysis

Identify oversized responses:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| filter performance.transfer_size > 100000
| fieldsAdd
    compression_ratio = if(performance.encoded_body_size > 0,
        toDouble(performance.decoded_body_size) / toDouble(performance.encoded_body_size),
        else: 1.0)
| summarize
    avg_transfer_size = avg(performance.transfer_size),
    avg_compression_ratio = avg(compression_ratio),
    request_count = count(),
    by: {url.domain, url.path}
| sort avg_transfer_size desc
| limit 20
```

**Use Case:** Find large payloads and compression opportunities.

### Render-Blocking Resources

Identify resources blocking page render:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| filter performance.render_blocking_status == "blocking"
| summarize
    avg_duration = avg(duration),
    request_count = count(),
    by: {url.domain, url.path, performance.initiator_type}
| sort avg_duration desc
| limit 20
```

**Use Case:** Optimize critical rendering path.

## Navigation Patterns

Analyze user navigation flows, referrers, and navigation types in web applications.

**Data Source:** `fetch user.events` with `characteristics.has_navigation`

**Key Fields:**

- `navigation.type` - navigate, reload, back_forward, soft_navigation, prerender
- `navigation.tab_state` - new, existing, duplicated
- `view.source.*` - Previous view information
- `page.source.url.*` - Referrer URL components

### External Referrers

Analyze traffic sources:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_navigation == true
| filter navigation.type == "navigate"
| filter isNotNull(page.source.url.domain)
| summarize
    referral_count = count(),
    unique_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, page.source.url.domain}
| sort referral_count desc
| limit 20

```

**Use Case:** Identify top traffic sources.

### Internal Navigation Flows

Track page-to-page navigation:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_navigation == true
| filter isNotNull(view.source.url.path)
| summarize
    flow_count = count(),
    by: {frontend.name, view.source.url.path, page.url.path}
| sort flow_count desc
| limit 30

```

**Use Case:** Visualize common user journeys.

### Page Reload Analysis

Monitor page reloads:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_navigation == true
| filter navigation.type == "reload"
| summarize
    reload_count = count(),
    unique_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, page.url.path}
| sort reload_count desc
| limit 20

```

**Use Case:** Identify pages with high reload rates (potential UX issues).

## Long Tasks & JavaScript Performance

Analyze long-running JavaScript tasks that block the main thread and affect interactivity.

**Data Source:** `fetch user.events` with `characteristics.has_long_task`

**Key Fields:**

- `duration` - Task duration (nanoseconds)
- `long_task.name` - Context attribution: self, same-origin, cross-origin, etc.
- `long_task.attribution.container_*` - Container details for iframe tasks

**Performance Thresholds:**

- Long task: > 50ms (blocks interaction)
- Critical: > 100ms (noticeable lag)
- Severe: > 250ms (frustrating UX)

### Long Tasks Overview

Query all long tasks:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| summarize
    task_count = count(),
    avg_duration = avg(duration),
    p75_duration = percentile(duration, 75),
    p95_duration = percentile(duration, 95),
    max_duration = max(duration),
    by: {frontend.name}

```

**Use Case:** Baseline long task frequency and severity.

### Long Tasks by Page

Identify pages with performance issues:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| summarize
    task_count = count(),
    avg_duration = avg(duration),
    p90_duration = percentile(duration, 90),
    by: {frontend.name, page.url.path}
| sort p90_duration desc
| limit 20

```

**Use Case:** Prioritize pages for JavaScript optimization.

### Third-Party Long Tasks

Find blocking third-party scripts:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| filter in(long_task.name, "cross-origin-ancestor", "cross-origin-descendant", "cross-origin-unreachable")
| summarize
    task_count = count(),
    total_blocking_time = sum(duration),
    by: {frontend.name, long_task.attribution.container_src}
| sort total_blocking_time desc
| limit 15

```

**Use Case:** Evaluate third-party script impact.

### Critical Long Tasks

Find severely blocking tasks:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| filter duration > 250000000
| summarize
    critical_tasks = count(),
    avg_duration = avg(duration),
    affected_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, page.url.path}
| sort critical_tasks desc
| limit 20

```

**Use Case:** Address worst performance offenders.

## Advanced Performance Analysis

Advanced performance analysis including geographic distribution, correlations, and regression detection.

### Geographic Performance Distribution

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

### Performance vs Error Rate Correlation

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

### Request Performance Degradation Detection

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

### Time on Page

Analyze engagement depth:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_page_summary == true
| summarize
    page_views = count(),
    avg_foreground = avg(page.foreground_time),
    p50_foreground = percentile(page.foreground_time, 50),
    p90_foreground = percentile(page.foreground_time, 90),
    by: {frontend.name, page.url.path}
| filter page_views > 50
| sort avg_foreground desc
| limit 20

```

**Use Case:** Identify high-engagement pages.

### ISP Performance Analysis

Identify network provider issues:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| summarize
    avg_duration = avg(duration),
    p90_duration = percentile(duration, 90),
    request_count = count(),
    by: {client.isp, geo.country.iso_code}
| filter request_count > 100
| sort p90_duration desc
| limit 20
```

**Use Case:** Detect ISP-specific performance degradation.

