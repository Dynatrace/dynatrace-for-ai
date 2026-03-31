# Frontend-Backend Trace Correlation

Correlate frontend requests with backend traces for end-to-end diagnostics.

**Data Source:** `fetch user.events` joined with `fetch spans`

**Key Fields:**

- `trace.id` - W3C trace ID linking frontend to backend
- `span.id` - Frontend span ID
- `request.trace_context_hint` - Whether trace headers were set
- `request.server_timing_hint` - Whether backend trace info was received

## Trace Context Coverage

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

## Slow Requests with Backend Traces

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

## Backend Service Impact on Frontend

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

## Failed Requests with Traces

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

## Cross-Origin Tracing Gaps

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

## Trace Sampling Analysis

Analyze backend trace sampling rates:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| filter request.server_timing_hint == "received"
| summarize
    total = count(),
    sampled = countIf(trace.is_sampled == true),
    not_sampled = countIf(trace.is_sampled == false),
    by: {url.domain}
| fieldsAdd sample_rate = 100.0 * sampled / total
| sort total desc
| limit 20
```

**Use Case:** Monitor backend trace sampling effectiveness.
