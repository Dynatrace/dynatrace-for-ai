# Frontend-Backend Linking

Correlate frontend user events and sessions with backend traces and spans. Linking works in both directions: from a frontend request event to the backend span it triggered, and from a backend span back to the request and/or to the originating user session.

**Reference:** https://docs.dynatrace.com/docs/observe/digital-experience/rum/concepts/frontend-backend-linking

**Semantic Dictionary — `frontend.link` sub-attributes:** https://docs.dynatrace.com/docs/shortlink/semantic-dictionary-traces#dynatrace-frontend-backend-tracing-links

## Mechanisms

Three mechanisms populate linking data. They differ in what they require, which request types they cover, and how strong the resulting link is.

| Mechanism | Applies to | Requirement |
|-----------|-----------|-------------|
| **W3C Trace Context** (`traceparent`/`tracestate`) | XHR/Fetch — same-origin by default on web (cross-origin requires special setup); all HTTP requests on mobile | RUM JS 1.331 for full support with tracestate; mobile agent 8.333 (Android/iOS), 8.335 (cross-platform). Works with both OneAgent and OpenTelemetry backends. |
| **Server-Timing header** (`dtTrId`, `dtSInfo`) | Web requests — the HTML document and resources | OneAgent 1.331+; not available for OpenTelemetry backends |
| **Cookie** (currently based on RUM Classic cookies) | Web and mobile | No specific version requirement; weakest mechanism, does not work in all situations, requires OneAgent; not available for OpenTelemetry backends |

W3C Trace Context populates `trace.id` on `user.events` request events (XHR/Fetch on web; all HTTP requests on mobile), enabling the forward direction (request event → span lookup). Server-Timing (web only) populates `trace.id` on `user.events` navigation events (page loads and resources). The Cookie mechanism does not populate `trace.id`.

## Contents

- [From User Event to Backend Span](#from-user-event-to-backend-span)
  - [Trace Context Coverage](#trace-context-coverage)
  - [Trace Context Hint Analysis](#trace-context-hint-analysis)
  - [Slow Requests with Backend Traces](#slow-requests-with-backend-traces)
  - [Cross-Origin Tracing Gaps](#cross-origin-tracing-gaps)
- [From Backend Span to User Event or Session](#from-backend-span-to-user-event-or-session)
  - [Backend-to-Frontend Lookup](#backend-to-frontend-lookup)

## From User Event to Backend Span

When a `user.events` request event has a populated `trace.id`, it can be correlated with the backend span that processed it. The hint fields explain the linking status for each request.

**Key fields on `user.events` request events:**

- `trace.id` — W3C trace ID; present when the RUM agent propagated trace headers or received them via Server-Timing
- `span.id` — Frontend span ID; present only when the RUM agent propagated trace headers
- `request.trace_context_hint` — Why W3C headers were or were not propagated by the RUM agent (does not indicate whether the backend received or used them)
- `request.server_timing_hint` — Whether the backend returned a Server-Timing header with trace info

### Trace Context Coverage

Coverage per frontend — which frontends have tracing gaps?

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request
| summarize
    total_requests = count(),
    traced_requests = countIf(isNotNull(trace.id)),
    by: {frontend.name}
| fieldsAdd trace_rate = 100.0 * traced_requests / total_requests
| sort trace_rate asc
```

**Use Case:** Identify frontends with low end-to-end tracing coverage.

### Trace Context Hint Analysis

For untraced requests, `request.trace_context_hint` explains why the RUM agent could not propagate W3C trace context headers.

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request
| filter isNull(trace.id)
| summarize
    untraced_count = count(),
    by: {frontend.name, request.trace_context_hint, url.domain, url.path}
| sort untraced_count desc
| limit 20
```

**Use Case:** Diagnose why trace headers were not set. A high count for `cross_origin` on a domain indicates CORS configuration is preventing trace propagation for those endpoints.

### Slow Requests with Backend Traces

Find slow frontend requests and collect their trace IDs for backend investigation:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request
| filter duration > 2s
| filter isNotNull(trace.id)
| fields
    start_time,
    url.domain,
    url.path,
    duration,
    trace.id,
    span.id,
    http.response.status_code,
    request.trace_context_hint,
    request.server_timing_hint
| sort duration desc
| limit 50
```

**Use Case:** Get trace IDs for investigating slow requests in the backend. `request.trace_context_hint` shows how the RUM agent set headers; `request.server_timing_hint` shows how the backend communicated trace info back.

### Cross-Origin Tracing Gaps

Identify requests missing traces due to CORS:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request
| filter request.trace_context_hint == "cross_origin"
| summarize
    request_count = count(),
    by: {url.domain, url.provider}
| sort request_count desc
| limit 20
```

**Use Case:** Identify third-party domains where CORS prevents trace header propagation. Configure `Timing-Allow-Origin` on those domains or add them to the allowed-origins list in the RUM configuration.

## From Backend Span to User Event or Session

Backend spans carry a `frontend.link` record attribute when OneAgent was able to establish a back-reference to the originating RUM user event or session. The Semantic Dictionary defines four variants based on which mechanism established the link — for the full sub-attribute list per variant, see the [Semantic Dictionary reference](https://docs.dynatrace.com/docs/shortlink/semantic-dictionary-traces#dynatrace-frontend-backend-tracing-links).

The key practical distinction across the four variants:
- **TraceContext** variant populates `dt.rum.session.id`, `dt.rum.instance.id`, and `span.id` — the `span.id` uniquely identifies the exact user event that triggered the request.
- **Server-Timing + Cookie** variant populates `dt.rum.session.id`, `dt.rum.instance.id`, and `dt.rum.is_linking_candidate` — you can navigate to the session or find the specific request event using the span's `trace.id`.
- **Cookie** variant populates `dt.rum.session.id` and `dt.rum.instance.id` — you can navigate to the session, but not to a specific request event (the Cookie variant does not populate `trace.id` on the user event).
- **Server-Timing only** variant populates only `dt.rum.is_linking_candidate` — no session or instance ID available. The span's own `trace.id` can still be used to find the corresponding request event in `user.events`.

### Backend-to-Frontend Lookup

Navigate from a backend span to the originating user session or specific request event using `frontend.link` sub-attributes. The session ID is sufficient to reach the session or browse its events; `trace.id` is needed only if you want to locate the exact request event that triggered the span.

**Path A — Look up the user session** (when `dt.rum.session.id` is populated: TraceContext, Server-Timing + Cookie, or Cookie variants):

**Step 1 — Find backend spans with a session link:**

```dql
fetch spans, from: now() - 2h
| filter isNotNull(frontend.link[dt.rum.session.id])
| fields
    trace.id,
    span.name,
    endpoint.name,
    duration,
    rum_session_id = frontend.link[dt.rum.session.id],
    rum_instance_id = frontend.link[dt.rum.instance.id]
| sort duration desc
| limit 50
```

**Step 2 — Look up the user session:**

```dql
fetch user.sessions, from: now() - 32h
| filter dt.rum.session.id == "SESSION-ID-FROM-STEP-1"
| fields
    frontend.name,
    start_time,
    end_time,
    user_action_count,
    error.count,
    dt.rum.user_type,
    browser.name,
    geo.country.iso_code
```

Use an extended lookback (`from: now() - 32h`) — see [user-sessions.md](user-sessions.md) for session time window behavior. Sessions are written to `user.sessions` only after ~35 minutes of inactivity, so very recent or still-active sessions will not appear there yet.

**Step 2b — For in-progress or recent sessions: look up events by session ID:**

`user.events` contains `dt.rum.session.id` on every event and is written immediately — use this when `user.sessions` returns no results for a recent session.

```dql
fetch user.events, from: now() - 2h
| filter dt.rum.session.id == "SESSION-ID-FROM-STEP-1"
| fields
    start_time,
    page.name,
    view.name,
    frontend.name,
    duration,
    error.type
| sort start_time asc
```

**Path B — Look up the specific user event by `trace.id`** (TraceContext variant → `user.events` request event; Server-Timing variant → `user.events` navigation event):

**Step 1 — Find spans with a frontend link:**

```dql
fetch spans, from: now() - 2h
| filter isNotNull(frontend.link)
| fields
    trace.id,
    span.name,
    endpoint.name,
    duration,
    rum_span_id = frontend.link[span.id],
    is_linking_candidate = frontend.link[dt.rum.is_linking_candidate]
| sort duration desc
| limit 50
```

**Step 2a — TraceContext variant: look up the exact user event by `span.id`:**

When `frontend.link[span.id]` is populated (TraceContext only), `span.id` identifies the exact `user.events` request event — more precise than `trace.id`, which may match multiple events in a trace.

> **`toUid()` is required:** `trace.id` and `span.id` on `user.events` are UID-typed. Filtering with plain strings (for example, `trace.id == "hex-string"`) can silently return zero results.

```dql
fetch user.events, from: now() - 2h
| filter trace.id == toUid("TRACE-ID-FROM-STEP-1")
| filter span.id == toUid("SPAN-ID-FROM-STEP-1")
| fields
    start_time,
    page.name,
    view.name,
    frontend.name,
    url.domain,
    url.path,
    duration,
    trace.id
```

**Step 2b — TraceContext or Server-Timing: look up by `trace.id`:**

```dql
fetch user.events, from: now() - 2h
| filter trace.id == toUid("TRACE-ID-FROM-STEP-1")
| fields
    start_time,
    page.name,
    view.name,
    frontend.name,
    url.domain,
    url.path,
    duration,
    request.server_timing_hint
```

**Use Case:** Navigate from a backend span to the originating user session or user event. Path A gives session context; use Step 2b if the session is still active. Path B locates the specific user event — Step 2a gives an exact match (TraceContext, returns a request event); Step 2b finds by `trace.id` alone (returns a request event for TraceContext, a navigation event for Server-Timing).
