# Frontend Error Tracking

Comprehensive error analysis using both event-based queries (detailed diagnostics) and metric-based queries (trends and alerting).

**Data Sources:**

- **Metric**: `dt.frontend.error.count` - Aggregated error counts for trends and alerting
- **Event**: `fetch user.events` with `error.type` - Detailed error diagnostics with messages

## Metric-Based: Error Rate Monitoring

Track error rates across applications:

```dql
timeseries error_count = sum(dt.frontend.error.count, scalar: true),
          request_count = sum(dt.frontend.request.count, scalar: true),
          by: {frontend.name},
          from: now() - 2h

| fieldsAdd
    app_name = frontend.name,
    error_rate_percent = (error_count / request_count) * 100
| filter error_rate_percent > 1
| sort error_rate_percent desc

```

**Use Case:** Monitor application error rates and create alerts for threshold violations.

## Event-Based: JavaScript Exceptions

Analyze specific JavaScript errors:

```dql
fetch user.events, from: now() - 2h
| filter error.type == "exception"
| summarize
    exception_count = count(),
    affected_users = countDistinct(dt.rum.instance.id, precision: 9),
    affected_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, exception.message, exception.type}
| sort exception_count desc
| limit 20

```

**Use Case:** Debug specific JavaScript errors with detailed exception messages.

## Event-Based: Request Errors

Analyze failed API requests:

```dql
fetch user.events, from: now() - 2h
| filter error.type == "request"
| summarize
    error_count = count(),
    affected_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, error.display_name}
| sort error_count desc

```

**Use Case:** Identify failing backend API calls from frontend applications.

## Metric-Based: Error Spike Detection

Detect sudden increases in error rates:

```dql
timeseries {
    error_count = sum(dt.frontend.error.count),
    request_count = sum(dt.frontend.request.count)
},
  by: {frontend.name},
  from: now() - 24h,
  interval: 1h

| fieldsAdd
    error_rate_percent = (error_count[] / request_count[]) * 100

| join [
  timeseries {
    prev_error_count = sum(dt.frontend.error.count),
    prev_request_count = sum(dt.frontend.request.count)
  },
    by: {frontend.name},
    from: now() - 24h,
    interval: 1h,
    shift: 1h

  | fieldsAdd prev_error_rate = (prev_error_count[] / prev_request_count[]) * 100
], on: { frontend.name }, fields: { prev_error_rate }

| fieldsAdd
    app_name = frontend.name,
    error_rate_change = coalesce((error_rate_percent[] - prev_error_rate[]) / (prev_error_rate[]) * 100, 0)
| filter arrayAvg(error_rate_change) > 50
| sort error_rate_change desc

```

**Use Case:** Alert on error spikes indicating deployment issues.

## Metric-Based: Browser-Specific Errors

Identify browser compatibility issues:

```dql
timeseries error_count = sum(dt.frontend.error.count, scalar: true),
          request_count = sum(dt.frontend.request.count, scalar: true),
          by: {frontend.name, browser.name},
          from: now() - 4h

| fieldsAdd
    app_name = frontend.name,
    error_rate_percent = (error_count / request_count) * 100
| filter request_count > 100
| sort error_rate_percent desc

```

**Use Case:** Prioritize browser-specific bug fixes based on error rates.

## Event-Based: Errors by Device Type

Analyze errors by device:

```dql
fetch user.events, from: now() - 2h
| filter error.type == "exception"
| summarize
    error_count = count(),
    affected_users = countDistinct(dt.rum.instance.id, precision: 9),
    by: {device.type}
| sort error_count desc

```

**Use Case:** Optimize error handling for specific device types.

## Metric-Based: Geographic Error Patterns

Identify region-specific error issues:

```dql
timeseries error_count = sum(dt.frontend.error.count, scalar: true),
          request_count = sum(dt.frontend.request.count, scalar: true),
          by: {frontend.name, geo.country.iso_code},
          from: now() - 6h

| fieldsAdd
    app_name = frontend.name,
    error_rate_percent = (error_count / request_count) * 100
| filter request_count > 50 and error_rate_percent > 2
| sort error_rate_percent desc

```

**Use Case:** Detect regional infrastructure or connectivity issues.

## Pages with Errors

Find error-prone pages:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_page_summary == true
| filter error.exception_count > 0 or error.http_4xx_count > 0 or error.http_5xx_count > 0
| summarize
    page_views = count(),
    total_exceptions = sum(error.exception_count),
    total_4xx = sum(error.http_4xx_count),
    total_5xx = sum(error.http_5xx_count),
    by: {frontend.name, page.url.path}
| sort total_exceptions desc
| limit 20

```

**Use Case:** Prioritize pages for error fixes.

## Users with Errors

Find sessions with error patterns:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_error == true
| summarize
    error_count = count(),
    error_types = collectDistinct(error.type),
    by: {dt.rum.session.id, dt.rum.user_tag}
| filter error_count > 3
| sort error_count desc

```

**Use Case:** Identify frustrated users for follow-up.

## Frontend-Backend Trace Correlation

Correlate frontend errors with backend traces for end-to-end diagnostics.

**Key Fields:**

- `trace.id` - W3C trace ID linking frontend to backend
- `span.id` - Frontend span ID
- `request.trace_context_hint` - Whether trace headers were set
- `request.server_timing_hint` - Whether backend trace info was received

### Trace Context Coverage

Analyze trace correlation success rate:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| summarize
    total_requests = count(),
    traced_requests = countIf(isNotNull(trace.id)),
    by: {request.trace_context_hint, request.server_timing_hint}
| fieldsAdd trace_rate = 100.0 * traced_requests / total_requests
| sort total_requests desc
```

**Use Case:** Identify gaps in end-to-end tracing coverage.

### Slow Requests with Backend Traces

Find slow frontend requests and their backend traces:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| filter duration > 2s
| filter isNotNull(trace.id)
| fields
    start_time,
    url.path,
    duration,
    trace.id,
    span.id,
    http.response.status_code,
    request.server_timing_hint
| sort duration desc
| limit 50
```

**Use Case:** Get trace IDs for investigating slow requests in backend.

### Backend Service Impact on Frontend

Join frontend requests with backend spans:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| filter isNotNull(trace.id)
| filter duration > 1s
| fields trace.id, frontend_duration = duration, url.path
| join [
    fetch spans, from: now() - 2h
    | summarize
        backend_duration = sum(duration),
        span_count = count(),
        services = collectDistinct(dt.smartscape.service),
        by: {trace.id}
], on:trace.id, fields:{backend_duration, span_count, services}
| fieldsAdd
    backend_ratio = 100.0 * backend_duration / frontend_duration
| sort frontend_duration desc
| limit 30
```

**Use Case:** Determine if slowness is frontend or backend.

### Failed Requests with Traces

Correlate frontend errors with backend traces:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_failed_request == true
| filter isNotNull(trace.id)
| fields
    start_time,
    url.full,
    http.response.status_code,
    trace.id,
    error.type,
    error.message
| sort start_time desc
| limit 50
```

**Use Case:** Debug failed requests using backend trace data.

### Cross-Origin Tracing Gaps

Identify requests missing traces due to CORS:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| filter request.trace_context_hint == "cross_origin"
| summarize
    request_count = count(),
    by: {url.domain, url.provider}
| sort request_count desc
| limit 20
```

**Use Case:** Identify third-party domains needing CORS trace headers.

