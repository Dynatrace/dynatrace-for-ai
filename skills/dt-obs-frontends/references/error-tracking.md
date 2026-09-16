# Frontend Error Tracking

Comprehensive error analysis using both event-based queries (detailed diagnostics) and metric-based queries (trends and alerting).

**Data Sources:**

- **Metric**: `dt.frontend.error.count` - Aggregated error counts for trends and alerting; supports `error.type` as a dimension (`anr`, `crash`, `csp`, `exception`)
- **Event**: `fetch user.events` with characteristic filters — use `characteristics.has_error` for all errors, or the more specific `characteristics.has_exception`, `characteristics.has_failed_request`, `characteristics.has_crash`, `characteristics.has_anr`, `characteristics.has_csp_violation`

**Reference:** https://docs.dynatrace.com/docs/observe/digital-experience/new-rum-experience/error-inspector

**Error types** (`error.type` values): `anr`, `crash`, `csp`, `exception` — failed requests do not have an `error.type` value; use `characteristics.has_failed_request` instead.

**CSP violations** are a separate event type fully documented in [references/csp-violations.md](references/csp-violations.md).

## Contents

- [Metric-Based Queries](#metric-based-queries)
  - [Error Rate Monitoring](#error-rate-monitoring)
  - [Error Volume by Type](#error-volume-by-type)
  - [Error Spike Detection](#error-spike-detection)
  - [Browser-Specific Errors](#browser-specific-errors)
  - [Geographic Error Patterns](#geographic-error-patterns)
- [Event-Based Queries](#event-based-queries)
  - [Exceptions](#exceptions)
  - [Request Errors](#request-errors)
  - [Errors by Device Type (web only)](#errors-by-device-type-web-only)
  - [Pages with Errors](#pages-with-errors)
  - [Views with Errors](#views-with-errors)
  - [Users with Errors](#users-with-errors)
  - [API-Reported Errors](#api-reported-errors)
- [Frontend-Backend Linking](#frontend-backend-linking)
  - [Backend Service Impact on Frontend](#backend-service-impact-on-frontend)
  - [Failed Requests with Traces](#failed-requests-with-traces)

## Metric-Based Queries

> **`scalar: true` vs array (`[]`) notation:** `scalar: true` collapses the entire time window into one value per row — total across all buckets. Use it for overall rates, sorting, and alerting. Without `scalar: true`, metric columns are arrays (one value per interval); use `[]` notation for per-bucket trend analysis. When filtering or sorting on an array column, choose the aggregation that matches your intent: `arrayMax(col)` for **spike and threshold queries** ("did this ever exceed X in any bucket?") or `arrayAvg(col)` for **sustained-rate ranking** ("what was the typical level?"). Avoid `arrayAvg` of a cardinality metric — it is not a statistically correct overall rate; use `scalar: true` instead.

### Error Rate Monitoring

Track error rates across applications:

```dql
timeseries error_count = sum(dt.frontend.error.count, scalar: true),
          request_count = sum(dt.frontend.request.count, scalar: true),
          by: {frontend.name},
          from: now() - 2h

| fieldsAdd
    error_rate_percent = (error_count / request_count) * 100
| filter error_rate_percent > 1
| sort error_rate_percent desc
```

**Use Case:** **Overall rate** across the time window. Monitor application error rates and create alerts for threshold violations.

### Error Volume by Type

Break down error counts by `error.type` for trend analysis per error category:

```dql
timeseries error_count = sum(dt.frontend.error.count),
          by: {frontend.name, error.type},
          from: now() - 24h
```

**Use Case:** **Per-bucket trend.** Compare exception vs. request vs. CSP violation trends over time; identify which error type is driving a spike.

### Error Spike Detection

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
    error_rate_change = coalesce((error_rate_percent[] - prev_error_rate[]) / (prev_error_rate[]) * 100, 0)
| filter arrayMax(error_rate_change) > 50
| sort arrayMax(error_rate_change) desc
```

**Use Case:** **Per-bucket trend** (compares adjacent 1-hour intervals). `arrayMax` catches brief post-deploy spikes that `arrayAvg` would smooth away. Alert on error spikes indicating deployment issues.

### Browser-Specific Errors

Identify browser compatibility issues:

```dql
timeseries error_count = sum(dt.frontend.error.count, scalar: true),
          request_count = sum(dt.frontend.request.count, scalar: true),
          by: {frontend.name, browser.name},
          from: now() - 4h

| fieldsAdd
    error_rate_percent = (error_count / request_count) * 100
| filter request_count > 100
| sort error_rate_percent desc
```

**Use Case:** **Overall rate** per browser. Prioritize browser-specific bug fixes based on error rates.

### Geographic Error Patterns

Identify region-specific error issues:

```dql
timeseries error_count = sum(dt.frontend.error.count, scalar: true),
          request_count = sum(dt.frontend.request.count, scalar: true),
          by: {frontend.name, geo.country.iso_code},
          from: now() - 6h

| fieldsAdd
    error_rate_percent = (error_count / request_count) * 100
| filter request_count > 50 and error_rate_percent > 2
| sort error_rate_percent desc
```

**Use Case:** **Overall rate** per region. Detect regional infrastructure or connectivity issues.

## Event-Based Queries

### Exceptions

Analyze exceptions across all platforms (web and mobile). For mobile-specific crash and ANR analysis see [mobile-monitoring.md](mobile-monitoring.md).

```dql
fetch user.events, from: now() - 2h
| filter error.type == "exception"
| summarize
    exception_count = count(),
    affected_users = countDistinct(dt.rum.instance.id, precision: 9),
    affected_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, dt.rum.application.type, exception.message, exception.type, error.id}
| sort exception_count desc
| limit 20
```

**Use Case:** Debug exceptions across web and mobile. `error.id` groups similar errors by fingerprint. `dt.rum.application.type` distinguishes web (`exception.type` is a JS class) from mobile (`exception.type` is a Java/Swift/Kotlin class).

#### Exception Source Analysis (web only)

Identify which scripts cause exceptions. **Web (RUM JS) only** — `exception.file.full` is not populated for mobile exceptions.

```dql
fetch user.events, from: now() - 2h
| filter error.type == "exception"
| filter isNotNull(exception.file.full)
| summarize
    exception_count = count(),
    by: {frontend.name, exception.file.provider, exception.file.full, error.source}
| sort exception_count desc
| limit 20
```

**Use Case:** Identify third-party scripts causing exceptions. `exception.file.full` is the JS file URL; `exception.file.provider` shows first-party, third-party, or CDN; `error.source` values: `console`, `document_request`, `exception`, `fetch`, `promise_rejection`, `xhr`.

### Request Errors

Analyze failed API requests:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_failed_request
| summarize
    error_count = count(),
    affected_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, http.response.status_code, url.domain, url.path}
| sort error_count desc
```

**Use Case:** Identify failing backend API calls from frontend applications.

### Errors by Device Type (web only)

Analyze exceptions by device type. **Web (RUM JS) only** — `device.type` is not populated for mobile events.

```dql
fetch user.events, from: now() - 2h
| filter error.type == "exception"
| summarize
    error_count = count(),
    affected_users = countDistinct(dt.rum.instance.id, precision: 9),
    by: {frontend.name, device.type, dt.rum.user_type}
| sort error_count desc
```

**Use Case:** Optimize error handling across desktop, mobile browser, and tablet form factors. `dt.rum.user_type` is included in the `by:` clause for segmentation — the result set shows both real users and synthetic monitors side-by-side, which is useful for comparing error patterns. It is intentionally not used as a filter here.

### Pages with Errors

Find error-prone pages:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_page_summary
| filter error.exception_count > 0
    or error.http_4xx_count > 0
    or error.http_5xx_count > 0
    or error.http_other_count > 0
    or error.csp_violation_count > 0
| summarize
    page_views = count(),
    total_exceptions = sum(error.exception_count),
    total_4xx = sum(error.http_4xx_count),
    total_5xx = sum(error.http_5xx_count),
    total_http_other = sum(error.http_other_count),
    total_csp = sum(error.csp_violation_count),
    dropped_exceptions = sum(error.dropped_exception_count),
    by: {frontend.name, page.name}
| sort total_exceptions desc
| limit 20
```

**Use Case:** Prioritize pages for error fixes. `http_other_count` covers non-standard HTTP status codes (0-99 or 600+). `dropped_exception_count` indicates where exception capture limits were hit.

### Views with Errors

Same analysis for SPA soft navigations (web) and mobile screens — view summaries carry the same 6 error count fields:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_view_summary
| filter error.exception_count > 0
    or error.http_4xx_count > 0
    or error.http_5xx_count > 0
    or error.http_other_count > 0
    or error.csp_violation_count > 0
| summarize
    view_count = count(),
    total_exceptions = sum(error.exception_count),
    total_4xx = sum(error.http_4xx_count),
    total_5xx = sum(error.http_5xx_count),
    total_http_other = sum(error.http_other_count),
    total_csp = sum(error.csp_violation_count),
    dropped_exceptions = sum(error.dropped_exception_count),
    by: {frontend.name, dt.rum.application.type, view.name}
| sort total_exceptions desc
| limit 20
```

**Use Case:** Prioritize error-prone views across SPA routes (web) and mobile screens. `dt.rum.application.type` distinguishes web from mobile.

### Users with Errors

Find anonymous users with high error counts using `dt.rum.instance.id` (persistent device ID, available on every event). For identified users, use the session-level query in [user-sessions.md](user-sessions.md).

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_error
| summarize
    error_count = count(),
    error_types = collectDistinct(error.type),
    by: {frontend.name, dt.rum.instance.id}
| filter error_count > 3
| sort error_count desc
```

**Use Case:** Identify anonymous users experiencing repeated errors. `dt.rum.instance.id` is a pseudonymous device ID — not a real user identity.

### API-Reported Errors

Analyze errors reported programmatically via the mobile SDK (mobile only):

```dql
fetch user.events, from: now() - 2h
| filter characteristics.is_api_reported
| filter characteristics.has_error
| summarize
    error_count = count(),
    affected_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, error.name, error.code, error.reason}
| sort error_count desc
```

**Use Case:** Track custom business errors reported by mobile applications via the SDK.

## Frontend-Backend Linking

For linking mechanisms, key fields, diagnostic queries, and the `frontend.link` span attribute, see [references/frontend-backend-linking.md](frontend-backend-linking.md).

### Backend Service Impact on Frontend

A join of `user.events` against `spans` by `trace.id` is not reliably executable — the spans table is too large for the join right side on production tenants. Use a two-step approach instead.

**Step 1 — Find slow traced requests and identify the bottleneck phase (RUM JS only — `performance.*` timing fields are not available on mobile):**

Filter by `frontend.name` to survey all slow requests across a frontend, or replace it with `dt.rum.session.id` to investigate one specific user session.

```dql
fetch user.events, from: now() - 2h
| filter frontend.name == "my-frontend"
| filter characteristics.has_request
| filter isNotNull(trace.id)
| filter duration > 2s
| filter isNull(performance.incomplete_reason)
| fieldsAdd
    ttfb = performance.response_start - performance.start_time,
    download = performance.response_end - performance.response_start
| fields
    start_time,
    url.domain,
    url.path,
    duration,
    ttfb,
    download,
    trace.id,
    request.trace_context_hint,
    request.server_timing_hint
| sort duration desc
| limit 20
```

High `ttfb` points to backend slowness. High `download` points to large response payload. Requests with `performance.incomplete_reason` set are cross-origin or cached and have no timing data.

**Step 2 — For a specific request, look up its backend spans by `trace.id`:**

```dql
fetch spans, from: "2026-01-01T12:00:00Z", to: "2026-01-01T12:05:00Z"
| filter trace.id == toUid("TRACE-ID-FROM-STEP-1")
| fields span.name, dt.smartscape.service, duration, start_time, span.kind
| sort start_time asc
```

Use a narrow time window (a few minutes around the request's `start_time`) to keep the span-side scan fast. The single `trace.id` filter is reliable at any tenant scale.

> **`toUid()` is required:** `trace.id` in spans is stored as a UID type, not a plain string. Filtering with `trace.id == "hex-string"` silently returns zero results. Always wrap the trace ID string in `toUid()`.

**Use Case:** Determine whether slowness is in the backend. Step 1 uses W3C timing fields to pinpoint the phase without any join; Step 2 retrieves backend span detail for a specific request once a candidate trace ID is identified.

### Failed Requests with Traces

Correlate frontend errors with backend traces:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_failed_request
| filter isNotNull(trace.id)
| fields
    start_time,
    url.full,
    http.response.status_code,
    trace.id
| sort start_time desc
| limit 50
```

**Use Case:** Debug failed requests using backend trace data.
