---
name: dt-obs-frontends
description: Real User Monitoring (RUM), Web Vitals, user sessions, mobile crashes, page performance, user interactions, and frontend errors. Query web and mobile frontend telemetry.
license: Apache-2.0
---

# Frontend Observability Skill

Monitor web and mobile frontends using Real User Monitoring (RUM) with DQL queries.
This skill targets the new RUM experience only; do not use classic RUM data.

## Overview

This skill helps you:
- Monitor Core Web Vitals and frontend performance
- Track user sessions, engagement, and behavior
- Analyze errors and correlate with backend traces
- Optimize mobile app startup and stability
- Diagnose performance issues with detailed timing analysis

**Data Sources:**
- **Metrics**: `timeseries` with `dt.frontend.*` (trends, alerting)
- **Events**: `fetch user.events` (individual page views, requests, clicks, errors)
- **Sessions**: `fetch user.sessions` (session-level aggregates: duration, bounce, counts)


## Quick Reference

### Common Metrics
- `dt.frontend.user_action.count` - User action volume
- `dt.frontend.user_action.duration` - User action duration
- `dt.frontend.request.count` - Request volume
- `dt.frontend.request.duration` - Request latency (ms)
- `dt.frontend.error.count` - Error counts
- `dt.frontend.session.active.estimated_count` - Active sessions
- `dt.frontend.user.active.estimated_count` - Unique users
- `dt.frontend.web.page.cumulative_layout_shift` - CLS metric
- `dt.frontend.web.navigation.dom_interactive` - DOM interactive time
- `dt.frontend.web.page.first_input_delay` - FID metric (legacy; prefer INP)
- `dt.frontend.web.page.largest_contentful_paint` - LCP metric
- `dt.frontend.web.page.interaction_to_next_paint` - INP metric
- `dt.frontend.web.navigation.load_event_end` - Load event end
- `dt.frontend.web.navigation.time_to_first_byte` - Time to first byte

### Common Filters
- `frontend.name` - Filter by frontend name (e.g. `my-frontend`)
- `dt.rum.user_type` - Exclude synthetic monitoring
- `geo.country.iso_code` - Geographic filtering
- `device.type` - Mobile, desktop, tablet
- `browser.name` - Browser filtering

### Common Timeseries Dimensions
Use these for `dt.frontend.*` timeseries splits and breakdowns:
- `frontend.name` - Frontend name
- `geo.country.iso_code`
- `device.type`
- `browser.name`
- `os.name`
- `user_type` - `real_user`, `synthetic`, `robot`

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_page_summary == true
| summarize page_views = count(), by: {frontend.name}
| sort page_views desc
```

### Event Characteristics
- `characteristics.has_page_summary` - Page views (web)
- `characteristics.has_view_summary` - Views (mobile)
- `characteristics.has_navigation` - Navigation events
- `characteristics.has_user_interaction` - Clicks, forms, etc.
- `characteristics.has_request` - Network request events
- `characteristics.has_error` - Error events
- `characteristics.has_crash` - Mobile crashes
- `characteristics.has_long_task` - Long JavaScript tasks
- `characteristics.has_csp_violation` - CSP violations

Full event model: https://docs.dynatrace.com/docs/semantic-dictionary/model/rum/user-events

### Session Data (`user.sessions`)

`user.sessions` contains session-level aggregates produced by the session aggregation service from `user.events`. **Field names differ from `user.events`** — sessions use underscores where events use dots.

**Session identity and context:**
- `dt.rum.session.id` — Session ID (NOT `dt.rum.session_id`)
- `dt.rum.instance.id` — Instance ID
- `frontend.name` - array of frontends involved in session
- `dt.rum.application.type` — `web` or `mobile`
- `dt.rum.user_type` — `real_user`, `synthetic`, or `robot`

**Session aggregates (underscore naming — NOT dot):**

| Field | Description | ⚠️ NOT this |
|-------|-------------|-------------|
| `navigation_count` | Number of navigations | ~~`navigation.count`~~ |
| `user_interaction_count` | Clicks, form submissions | ~~`user_interaction.count`~~ |
| `user_action_count` | User actions | ~~`user_action.count`~~ |
| `request_count` | XHR/fetch requests | ~~`request.count`~~ |
| `event_count` | Total events in session | ~~`event.count`~~ |
| `page_summary_count` | Page views (web) | ~~`page_summary.count`~~ |
| `view_summary_count` | Views (mobile/SPA) | ~~`view_summary.count`~~ |

**Error fields (dot naming — same as events):**
- `error.count`, `error.exception_count`, `error.http_4xx_count`, `error.http_5xx_count`
- `error.anr_count`, `error.csp_violation_count`, `error.has_crash`

**Session lifecycle:**
- `start_time`, `end_time`, `duration` (nanoseconds)
- `end_reason` — `timeout`, `synthetic_execution_finished`, etc.
- `characteristics.is_bounce` — Boolean bounce flag
- `characteristics.has_replay` — Session replay available

**User identity:**
- `dt.rum.user_tag` — User identifier (typically email, username or customerId), set via `dtrum.identifyUser()` API call in the instrumented frontend. **Not always populated** — only present when the frontend explicitly calls `identifyUser()`.
- When `dt.rum.user_tag` is empty, `dt.rum.instance.id` is often the only user differentiator. The value is a random ID assigned by the RUM agent on the client side, so it is not personally identifiable but can be used to distinguish unique users when `user_tag` is not set. On web this is based on a persistent cookie, so it can be deleted by the user.
- The user tag is a **session-level field** — query it from `user.sessions`, not `user.events` (where it may be empty even if the session has one).

**Client/device context:**
- `browser.name`, `browser.version`, `device.type`, `os.name`
- `geo.country.iso_code`, `client.ip`, `client.isp`

**Synthetic-only fields:**
- `dt.entity.synthetic_test`, `dt.entity.synthetic_location`, `dt.entity.synthetic_test_step`

**Time window behavior:**
- `fetch user.sessions, from: X, to: Y` only returns sessions that **started** in `[X, Y]` — NOT sessions that were merely active during that window.
- Sessions can last 8h+ (the aggregation service waits 30+ minutes of inactivity before closing a session).
- To find all sessions active during a time window, extend the lookback by at least 8 hours: e.g., to cover events from the last 24h, query `fetch user.sessions, from: now() - 32h`.
- This matters for correlation queries (e.g., matching `user.events` to `user.sessions` by session ID) — a narrow `user.sessions` window will miss long-running sessions and produce false "orphans."

**Session creation delay:**
- The session aggregation service waits for ~30+ minutes of inactivity before closing a session and writing the `user.sessions` record.
- This means **recent events (last ~1 hour) will not yet have a matching `user.sessions` entry** — this is normal, not a data gap.
- When correlating `user.events` with `user.sessions`, exclude recent data (e.g., use `to: now() - 1h`) to avoid counting in-progress sessions as orphans.

**Zombie sessions (events without a `user.sessions` record):**
- Not every `dt.rum.session.id` in `user.events` will have a corresponding `user.sessions` record. The session aggregation service intentionally skips **zombie sessions** — sessions with no real user activity (zero navigations and zero user interactions).
- Zombie sessions contain only background, machine-driven activity (e.g., automatic XHR requests, heartbeats) with no page views or clicks. Serializing them would add no value to users.
- When correlating `user.events` with `user.sessions`, expect a large number of unmatched session IDs. This is **by design**, not a data gap. Filter to sessions with activity before diagnosing orphans:
  ```dql
  fetch user.events, from: now() - 2h, to: now() - 1h
  | filter isNotNull(dt.rum.session.id)
  | summarize navs = countIf(characteristics.has_navigation == true),
      interactions = countIf(characteristics.has_user_interaction == true),
      by: {dt.rum.session.id}
  | filter navs > 0 or interactions > 0
  ```

**Example — bounce rate and session quality:**
```dql
fetch user.sessions, from: now() - 24h
| filter dt.rum.user_type == "real_user"
| summarize
    total_sessions = count(),
    bounces = countIf(characteristics.is_bounce == true),
    zero_activity = countIf(toLong(navigation_count) == 0 and toLong(user_interaction_count) == 0),
    avg_duration_s = avg(toLong(duration)) / 1000000000
| fieldsAdd bounce_rate_pct = round((bounces * 100.0) / total_sessions, decimals: 1)
```




### Performance Thresholds
- **LCP**: Good <2.5s | Poor >4.0s
- **INP**: Good <200ms | Poor >500ms
- **CLS**: Good <0.1 | Poor >0.25
- **Cold Start**: Good <3s | Poor >5s
- **Long Tasks**: >50ms problematic, >250ms severe

## Core Workflows

### 1. Web Performance Monitoring
Track Core Web Vitals, page performance, and request latency for SEO and UX optimization.

**Primary Files:**
- `references/WebVitals.md` - Core Web Vitals (LCP, INP, CLS)
- `references/performance-analysis.md` - Request and page performance

**Common Queries:**
- All Core Web Vitals summary
- Web Vitals by page/device
- Request duration SLA monitoring
- Page load performance trends

### 2. User Session & Behavior Analysis
Understand user engagement, navigation patterns, and session characteristics. Analyze button clicks, form interactions, and user journeys.

**Data source choice:**
- Use `fetch user.sessions` for session-level analysis (bounce rate, session duration, session counts)
- Use `fetch user.events` for event-level detail (individual clicks, navigation timing, specific pages)

**Primary Files:**
- `references/user-sessions.md` - Session tracking and user analytics
- `references/performance-analysis.md` - Navigation and engagement patterns

**Common Queries:**
- Active sessions by frontend
- Sessions by custom property
- Bounce rate analysis (use `user.sessions` with `characteristics.is_bounce`)
- Session quality (zero-activity sessions via `navigation_count`, `user_interaction_count`)
- Click analysis on UI elements (use `user.events` with `characteristics.has_user_interaction`)
- External referrers (traffic sources)

### 3. Error Tracking & Debugging
Monitor error rates, analyze exceptions, and correlate frontend issues with backend.

**Primary Files:**
- `references/error-tracking.md` - Error analysis and debugging
- `references/performance-analysis.md` - Trace correlation

**Common Queries:**
- Error rate monitoring
- JavaScript exceptions by type
- Failed requests with backend traces
- Request timing breakdown

### 4. Mobile Frontend Monitoring
Track mobile app performance, startup times, and crash analytics for iOS and Android. Analyze app version performance and device-specific issues.

**Primary Files:**
- `references/mobile-monitoring.md` - App starts, crashes, and mobile-specific metrics

**Common Queries:**
- Cold start performance by app version (iOS, Android)
- Warm start and hot start metrics
- Crash rate by device model and OS version
- ANR events (Android)
- Native crash signals
- App version comparison

### 5. Advanced Performance Optimization
Deep performance diagnostics including JavaScript profiling, main thread blocking, UI jank analysis, and geographic performance.

**Primary Files:**
- `references/performance-analysis.md` - Advanced diagnostics and long tasks

**Common Queries:**
- Long JavaScript tasks blocking main thread
- UI jank and rendering delays
- Tasks >50ms impacting responsiveness
- Third-party long tasks (iframes)
- Single-page app performance issues
- Geographic performance distribution
- Performance degradation detection

## Best Practices

1. **Use metrics for trends, events for debugging**
   - Metrics: Timeseries dashboards, alerting, capacity planning
   - Events: Root cause analysis, detailed diagnostics

2. **Filter by frontend in multi-app environments**
   - Always use `frontend.name` for clarity

3. **Match interval to time range**
   - 5m intervals for hours, 1h for days, 1d for weeks

4. **Exclude synthetic traffic when analyzing real users**
   - Filter `dt.rum.user_type` to focus on genuine behavior

5. **Combine metrics with events for complete insights**
   - Start with metric trends, drill into events for details

6. **Extend `user.sessions` time window for correlation queries**
   - `user.sessions` only returns sessions that **started** in the query window
   - Sessions can last 8h+, so extend lookback by at least 8h when joining with `user.events`

## Slow Page Load Playbook

Start by segmenting the problem by page, browser, geo location, and `dt.rum.user_type`.

Heuristics:
- High TTFB -> slow backend
- High LCP with normal TTFB -> render bottleneck
- High CLS -> layout shifts (late-loading content, ads, fonts)
- Long tasks dominate -> JavaScript execution bottlenecks (heavy frameworks, large bundles)

### Backend latency (high TTFB)

```dql
fetch user.events
| filter frontend.name == "my-frontend" and characteristics.has_request == true
| filter page.url.path == "/checkout"
| summarize avg_ttfb = avg(request.time_to_first_byte), avg_duration = avg(duration)
```

If TTFB is high, analyze backend spans by correlating frontend events with backend traces using `dt.rum.trace_id`.

### Heavy JavaScript execution (long tasks)

Long tasks by page:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| summarize
   long_task_count = count(),
   total_blocking_time = sum(duration),
   by: {frontend.name, page.url.path}
| sort total_blocking_time desc
| limit 20
```

Long tasks by script source:

```dql
fetch user.events, from: now() - 2h
| filter frontend.name == "my-frontend"
| filter characteristics.has_long_task == true
| summarize
   long_task_count = count(),
   total_blocking_time = sum(duration),
   by: {long_task.attribution.container_src}
| sort total_blocking_time desc
| limit 20
```

### Large JavaScript bundles

```dql
fetch user.events
| filter frontend.name == "my-frontend"
| filter characteristics.has_request
| filter endsWith(url.full, ".js")
| summarize dls = max(performance.decoded_body_size), by: url.full
| sort dls desc
| limit 20
```

### Large resources

```dql
fetch user.events
| filter frontend.name == "my-frontend"
| filter characteristics.has_request
| summarize dls = max(performance.decoded_body_size), by: url.full
| sort dls desc
| limit 20
```

### Cache effectiveness

```dql
fetch user.events, from: now() - 2h
| filter frontend.name == "my-frontend"
| filter characteristics.has_request == true
| fieldsAdd cache_status = if(
   performance.incomplete_reason == "local_cache" or performance.transfer_size == 0 and
   (performance.encoded_body_size > 0 or performance.decoded_body_size > 0),
   "cached",
   else: if(performance.transfer_size > 0, "network", else: "uncached")
  )
| summarize
   request_count = count(),
   avg_duration = avg(duration),
   by: {url.domain, cache_status}
```

### Compression waste

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| filter isNotNull(performance.encoded_body_size) and isNotNull(performance.decoded_body_size)
| filter performance.encoded_body_size > 0
| fieldsAdd
   expansion_ratio = performance.decoded_body_size / performance.encoded_body_size,
   wasted_bytes = performance.decoded_body_size - performance.encoded_body_size
| summarize
   requests = count(),
   avg_expansion_ratio = avg(expansion_ratio),
   total_wasted_bytes = sum(wasted_bytes),
   by: {request.url.host, request.url.path}
| sort total_wasted_bytes desc
| limit 50
```

### Network issues

Compare by location and domain when TTFB is high but backend performance is good:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| summarize
   request_count = count(),
   avg_duration = avg(duration),
   p75_duration = percentile(duration, 75),
   p95_duration = percentile(duration, 95),
   by: {geo.country.iso_code, request.url.domain}
| sort p95_duration desc
| limit 50
```

Analyze DNS time:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| filter isNotNull(performance.domain_lookup_start) and isNotNull(performance.domain_lookup_end)
| fieldsAdd dns_ms = performance.domain_lookup_end - performance.domain_lookup_start
| summarize
   request_count = count(),
   avg_dns_ms = avg(dns_ms),
   p75_dns_ms = percentile(dns_ms, 75),
   p95_dns_ms = percentile(dns_ms, 95),
   by: {request.url.domain}
| sort p95_dns_ms desc
| limit 50
```

Analyze by protocol (http/1.1, h2, h3):

```dql
fetch user.events
| filter characteristics.has_request
| summarize cnt = count(), by: {url.domain, performance.next_hop_protocol}
| sort cnt desc
| limit 50
```

### Third-party dependencies

Analyze request performance by domain:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| summarize
   request_count = count(),
   avg_duration = avg(duration),
   p75_duration = percentile(duration, 75),
   p95_duration = percentile(duration, 95),
   by: {request.url.domain}
| sort p95_duration desc
| limit 50
```

## Troubleshooting

### Handling Zero Results

When queries return no data, follow this diagnostic workflow:

1. **Validate Timeframe**
   - Check if timeframe is appropriate for the data type
   - RUM data may have delay (1-2 minutes for recent events)
   - Verify timeframe syntax: `now()-1h to now()` or similar
   - Try expanding timeframe: `now()-24h` for initial exploration

2. **Verify frontend Configuration**
   - Confirm frontend is instrumented and sending RUM data
   - Check `frontend.name` filter is correct
   - Test without frontend filter to see if any RUM data exists
   - Verify frontend name matches the environment

3. **Check Data Availability**
   - Run basic query: `fetch user.events | limit 1`
   - If no events exist, RUM may not be configured
   - Check if timeframe predates frontend deployment
   - Verify user has access to the environment

4. **Review Query Syntax**
   - Validate filters aren't too restrictive
   - Check for typos in field names or metric names
   - Test query incrementally: start simple, add filters gradually
   - Verify characteristics filters match event types

**When to Ask User for Clarification:**
- No RUM data exists in environment → "Is RUM configured for this frontend?"
- Timeframe unclear → "What time period should I analyze?"
- Expected data missing → "Has this frontend sent data recently?"

### Handling Anomalous Results

When query results seem unexpected or suspicious:

**Unexpected High Values:**
- **Metric spikes**: Verify interval aggregation (avg vs. max vs. sum)
- **Session counts**: Check for bot traffic or synthetic monitoring
- **Error rates**: Confirm error definition matches expectations
- **Performance degradation**: Look for deployment or infrastructure changes

**Unexpected Low Values:**
- **Missing sessions**: Verify `dt.rum.user_type` filter isn't excluding real users
- **Low request counts**: Check if frontend filter is too narrow
- **Few errors**: Confirm error characteristics filter is correct
- **Missing mobile data**: Verify platform-specific fields exist

**Inconsistent Data:**
- **Metrics vs. Events mismatch**: Different aggregation methods are expected
- **Geographic anomalies**: Check timezone assumptions
- **Device distribution skew**: May reflect actual user base
- **Version mismatches**: Verify app version filtering logic

### Decision Tree: Ask vs. Investigate

```
Query returns unexpected results
│
├─ Is this a zero-result scenario?
│  ├─ YES → Follow "Handling Zero Results" workflow
│  └─ NO → Continue
│
├─ Can I validate the result independently?
│  ├─ YES → Run validation query
│  │        ├─ Validation confirms result → Report findings
│  │        └─ Validation contradicts → Investigate further
│  └─ NO → Continue
│
├─ Is the anomaly clearly explained by data?
│  ├─ YES → Report with explanation
│  └─ NO → Continue
│
├─ Do I need domain knowledge to interpret?
│  ├─ YES → Ask user for context
│  │        Example: "The error rate is 15%. Is this expected for your frontend?"
│  └─ NO → Continue
│
└─ Is the issue ambiguous or requires clarification?
   ├─ YES → Ask specific question with data context
   │        Example: "I see two frontends named 'web-app'. Which frontend name should I use?"
   └─ NO → Investigate and report findings with caveats
```

### Common Investigation Steps

**For Performance Issues:**
1. Compare to baseline: Query same metric for previous week
2. Segment by dimension: Break down by device, browser, geography
3. Check for outliers: Use percentiles (p50, p95, p99) vs. averages
4. Correlate with deployments: Filter by app version or time windows

**For Data Availability Issues:**
1. Start broad: Query all RUM data without filters
2. Add filters incrementally: Isolate which filter eliminates data
3. Check related metrics: If events missing, try timeseries
4. Validate entity relationships: Confirm frontend-to-service links

**For Unexpected Patterns:**
1. Expand timeframe: Look for historical context
2. Cross-reference data sources: Compare events and metrics
3. Check sampling: Verify no sampling is affecting results
4. Consider external factors: Holidays, outages, traffic changes

### Red Flags: When to Stop and Ask

**Always ask the user when:**
- ❌ No RUM data exists anywhere in the environment
- ❌ Multiple frontends match the user's description
- ❌ Results contradict user's stated expectations explicitly
- ❌ Data suggests monitoring is misconfigured
- ❌ Query requires business context (e.g., "acceptable error rate")
- ❌ Timeframe is ambiguous and affects interpretation significantly

**Example clarifying questions:**
- "I found two frontends named 'checkout'. Which one: `checkout-web` or `checkout-mobile`?"
- "The query returns 0 results for the past hour. Should I expand the timeframe, or do you expect real-time data?"
- "The average LCP is 8 seconds, which exceeds the 4-second threshold. Is this frontend known to have performance issues?"
- "I see only synthetic traffic. Should I include `dt.rum.user_type='REAL_USER'` to focus on real users?"

## When to Use This Skill

**Use frontend-observability skill when:**
- Monitoring web or mobile frontend performance
- Analyzing Core Web Vitals for SEO
- Tracking user sessions, engagement, or behavior
- Analyzing click events and button interactions
- Debugging frontend errors or slow requests
- Correlating frontend issues with backend traces
- Optimizing mobile app startup or crash rates (iOS, Android)
- Analyzing app version performance
- Diagnosing UI jank and main thread blocking
- Analyzing security compliance (CSP violations)
- Profiling JavaScript performance (long tasks)

**Do NOT use for:**
- Backend service monitoring (use services skill)
- Infrastructure metrics (use infrastructure skill)
- Log analysis (use logs skill)
- Business process monitoring (use business-events skill)

## Progressive Disclosure

### Always Available
- **FrontendBasics.md** - RUM fundamentals and quick reference

### Loaded by Workflow
- **Web Performance**: WebVitals.md, performance-analysis.md
- **User Behavior**: user-sessions.md, performance-analysis.md
- **Error Analysis**: error-tracking.md, performance-analysis.md
- **Mobile Apps**: mobile-monitoring.md

### Load on Explicit Request
- Advanced diagnostics (long tasks, user actions)
- Security compliance (CSP violations, visibility tracking)
- Specialized mobile features (platform-specific phases)

## Reference Files

### Core Reference Documents
- `references/WebVitals.md` - Core Web Vitals monitoring
- `references/user-sessions.md` - Session and user analytics
- `references/error-tracking.md` - Error analysis and debugging
- `references/mobile-monitoring.md` - Mobile app performance and crashes
- `references/performance-analysis.md` - Advanced performance diagnostics

