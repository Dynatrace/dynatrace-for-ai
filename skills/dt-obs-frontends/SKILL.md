---
name: dt-obs-frontends
description: Real User Monitoring (RUM) on Dynatrace — web and mobile frontends. Core Web Vitals, user sessions, page performance, mobile crashes, frontend errors, and frontend-backend linking. Query via `user.events`, `user.sessions`, and `dt.frontend.*` metrics. Does NOT cover synthetic monitoring (HTTP/browser/network checks) — that's a separate domain.
license: Apache-2.0
---

# Frontend Observability (RUM)

Monitor web and mobile frontends using Real User Monitoring with DQL.
Targets **RUM on the latest Dynatrace** — do not use RUM Classic data.

**Concepts and data model:** https://docs.dynatrace.com/docs/observe/digital-experience/new-rum-experience/concepts

## Data Model

Three data sources, each for a different question:

| Source | Use for | Granularity |
|--------|---------|-------------|
| `timeseries dt.frontend.*` | Trends, dashboards, alerting | Aggregated metric |
| `fetch user.events` | Root cause, individual page views / requests / clicks / errors | Per-event |
| `fetch user.sessions` | Bounce rate, session duration, session-level aggregates | Per-session |

**Rule of thumb**: start with metrics for the shape of the problem, drill into events for the why. Use sessions when the question is about user journeys, not individual interactions.

Full event model: https://docs.dynatrace.com/docs/semantic-dictionary/model/rum/user-events

**DQL language reference (functions, syntax, operators):** https://docs.dynatrace.com/docs/platform/grail/dynatrace-query-language

**Key `dt.frontend.*` metrics** (all support dimensions: `frontend.name`, `device.type`, `geo.country.iso_code`, `browser.name`, `os.name`, `dt.rum.user_type`, `dt.smartscape.frontend`):

- `dt.frontend.web.page.largest_contentful_paint` / `dt.frontend.web.page.interaction_to_next_paint` / `dt.frontend.web.page.cumulative_layout_shift` / `dt.frontend.web.page.first_input_delay` — Core Web Vitals
- `dt.frontend.web.navigation.time_to_first_byte` / `dt.frontend.web.navigation.dom_interactive` / `dt.frontend.web.navigation.load_event_end` — Navigation timing
- `dt.frontend.error.count` — Error counts
- `dt.frontend.request.count` / `dt.frontend.request.duration` — Request volume and latency
- `dt.frontend.user_action.count` / `dt.frontend.user_action.duration` — User action volume and duration
- `dt.frontend.session.active.estimated_count` / `dt.frontend.user.active.estimated_count` — Active sessions and users (cardinality metrics; use `countDistinct()` aggregation)

## Common Filters

**All sources (`user.events` + `user.sessions`):**
- `frontend.name` — frontend identifier (preferred for all filtering); array on `user.sessions` (session can span multiple frontends). `dt.smartscape.frontend` is the Smartscape entity reference — use it to access entity attributes such as tags or linked services, not for name-based filtering. Avoid querying Smartscape to resolve a name to an entity ID and then joining with `user.events` — always filter on `frontend.name` directly.
- `dt.rum.user_type` — `real_user`, `synthetic`, `robot`
- `dt.rum.application.type` — `web` or `mobile`
- `dt.rum.session.id`, `dt.rum.instance.id`
- `os.name`, `geo.country.iso_code`, `client.isp`
- `client.ip` — client IP address *(sensitive field — hidden by default; see Field Permissions below)*

**`user.events` — web only:**
- `browser.name`, `browser.version`, `device.type`

**`user.events` — mobile only:**
- `device.model.identifier`, `device.manufacturer`, `app.short_version`

**Common characteristic filters** (scope `user.events` to a specific event type — use as `| filter characteristics.has_X`):
- `characteristics.has_page_summary` — page loads (web)
- `characteristics.has_view_summary` — views (SPA + mobile screens)
- `characteristics.has_navigation` — navigation events
- `characteristics.has_user_action` — user actions
- `characteristics.has_error` — all errors

Full characteristics reference: [references/characteristics.md](references/characteristics.md)

## Field Permissions

Some fields are **sensitive** and belong to the `builtin-sensitive-user-events-and-sessions` fieldset. They are **hidden by default** on both `user.events` and `user.sessions` — users without access see `null`, and queries that filter or group by these fields silently return no results.

Sensitive fields used in this skill:

- `client.ip` — client IP address
- `user.identifier` — real user identity

Grant access with the following policy statement:

```
ALLOW storage:fieldsets:read WHERE storage:fieldset-name="builtin-sensitive-user-events-and-sessions"
```

Reference: [Field permissions](https://docs.dynatrace.com/docs/shortlink/rum-on-grail-permissions#field-permissions)

## Drill-Down Pattern

Most investigations follow this layered approach regardless of the specific problem domain (errors, performance, background activity, etc.):

**1. Identify the frontend**

Start by grouping `by: {frontend.name}` to find which application is affected. Filter by `dt.rum.application.type` (`web` or `mobile`) if you need to split web from mobile analysis upfront.

**2. Find the affected page or view**

Both fields are available on all events (not scoped to a specific characteristic):

- `page.name` — the page URL normalised to a Dynatrace entity name; **web only**
- `view.name` — the SPA route or mobile screen name; available on **web and mobile**

Both can be present on the same event. For web SPAs, `page.name` reflects the top-level document while `view.name` reflects the current route — grouping by `view.name` gives finer granularity. For mobile, use `view.name` only.

**Additional narrowing dimensions**

| Dimension | Field | Platform | When to use |
|-----------|-------|----------|-------------|
| Specific request / endpoint | `url.domain`, `url.path` | web + mobile | Performance or error pattern on a specific API call |
| Individual user session | `dt.rum.session.id` | web + mobile | Reproduce a specific user's journey; connects to session replay |
| Device form factor | `device.type` | web only | Desktop vs mobile browser vs tablet pattern |
| Browser compatibility | `browser.name`, `browser.version` | web only | Issue only on certain browsers |
| App version | `app.short_version` | mobile only | Regression introduced in a specific app release |
| Geography | `geo.country.iso_code` | web + mobile | Regional infrastructure or CDN issue |
| Synthetic vs real traffic | `dt.rum.user_type` | web + mobile | Exclude synthetic monitors before user-facing analysis |

## Workflows

Each workflow maps to one or more references. Load the reference when you start the workflow, not upfront.

| Workflow | Reference |
|----------|-----------|
| Event characteristics — types, filters, event_type derivation | [references/characteristics.md](references/characteristics.md) |
| Web Vitals (LCP, FCP, FID, INP, CLS) | [references/web-vitals.md](references/web-vitals.md) |
| Session, bounce, engagement analysis | [references/user-sessions.md](references/user-sessions.md) |
| User actions — interaction lifecycle, completion reasons, timeouts | [references/user-actions.md](references/user-actions.md) |
| Errors, exceptions, failed requests | [references/error-tracking.md](references/error-tracking.md) |
| Frontend-backend linking — mechanisms, trace coverage, `frontend.link` | [references/frontend-backend-linking.md](references/frontend-backend-linking.md) |
| CSP violations — security policy enforcement and blocked resources | [references/csp-violations.md](references/csp-violations.md) |
| Mobile app starts, crashes, ANR, native signals | [references/mobile-monitoring.md](references/mobile-monitoring.md) |
| Request latency, long tasks, JS profiling, geo performance | [references/web-performance-analysis.md](references/web-performance-analysis.md) |
| Visibility changes — tab switching, background time, engagement quality | [references/visibility-changes.md](references/visibility-changes.md) |
| Slow page load — backend vs render vs network vs JS triage | [references/slow-page-load-playbook.md](references/slow-page-load-playbook.md) |
| Diagnosing zero results, anomalies, ambiguous data | [references/troubleshooting.md](references/troubleshooting.md) |

## Performance Thresholds (quick reference)

- **LCP**: Good < 2.5 s | Poor > 4.0 s
- **INP**: Good < 200 ms | Poor > 500 ms
- **CLS**: Good < 0.1 | Poor > 0.25
- **FCP**: Good < 1.8 s | Poor > 3.0 s
- **TTFB**: Good < 800 ms | Poor > 1800 ms
- **Mobile cold start**: Good < 3 s | Poor > 5 s
- **Mobile warm start**: Good < 1.5 s | Poor > 2 s
- **Mobile hot start**: Good < 500 ms | Poor > 1 s
- **Long tasks**: > 50 ms problematic, > 250 ms severe

*Web vitals thresholds (LCP, INP, CLS, FCP, TTFB): https://web.dev/articles/vitals*

## When to Use

Use this skill for real-user web and mobile frontend telemetry — Core Web Vitals, sessions, clicks, errors, crashes, request latency from the browser/app, and frontend-backend linking.

Use a different skill for:

- Synthetic monitors / availability checks → `dt-obs-synthetic`
- Backend services, traces, spans → `dt-obs-services`, `dt-obs-tracing`
- Infrastructure, hosts → `dt-obs-hosts`
- Logs → `dt-obs-logs`
- Problems and incidents → `dt-obs-problems`
