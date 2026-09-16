# User Actions

Analyze user actions that capture interaction lifecycles, resource loading, and DOM mutations.

**Concepts:** https://docs.dynatrace.com/docs/observe/digital-experience/new-rum-experience/web-frontends/concepts/user-actions

**Data Source:** `fetch user.events` with `characteristics.has_user_action`

**Key Fields:**

- `user_action.instance_id` - Unique user action ID
- `user_action.type` - Action type: `api`, `hard_navigation`, `same_view`, `soft_navigation` (`xhr` deprecated since RUM JS 1.339, replaced by `same_view`)
- `user_action.name` - Action name
- `user_action.complete_reason` - How the action ended: `completed`, `completed_by_api`, `interrupted_by_api`, `interrupted_by_automatic`, `page_hide`, `timeout`
- `user_action.mutation_count` - DOM mutations during the action
- `user_action.requests.count` - Requests during the action
- `user_action.requests.pending_request_count` - Requests still pending at completion
- `user_action.resources.count` - Resources loaded during the action
- `user_action.resources.<initiator>.count` - Resources by initiator type (for example: `xmlhttprequest`)
- `interaction.type` - Interaction type (experimental): `blur`, `change`, `click`, `drag`, `drop`, `focus`, `key_press`, `long_press`, `mouse_over`, `resize`, `scroll`, `touch`, `zoom`
- `ui_element.name` - Resolved UI element name
- `ui_element.tag_name` - UI element type
- `characteristics.is_api_reported` - True when reported via API

## Contents

- [Metric-Based Queries](#metric-based-queries)
  - [User Action Volume](#user-action-volume)
  - [User Action Duration](#user-action-duration)
  - [Action Timeout Rate](#action-timeout-rate)
- [Event-Based Queries](#event-based-queries)
  - [User Action Overview](#user-action-overview)
  - [Completion Reasons](#completion-reasons)
  - [Action Type Distribution](#action-type-distribution)
  - [Actions by Interaction](#actions-by-interaction)
  - [Resource-Heavy Actions](#resource-heavy-actions)
  - [Actions with Pending Requests](#actions-with-pending-requests)
  - [DOM Mutation Analysis](#dom-mutation-analysis)
  - [Timed-Out Actions](#timed-out-actions)
  - [Interrupted Actions](#interrupted-actions)
  - [User Action Web Vitals](#user-action-web-vitals)
  - [API-Reported Actions](#api-reported-actions)

## Metric-Based Queries

**Key Metrics:**

- `dt.frontend.user_action.count` — total user action count
- `dt.frontend.user_action.duration` — user action duration in milliseconds

**Available Dimensions:** `frontend.name`, `user_action.type`, `user_action.complete_reason`, `dt.rum.application.type`

> **`scalar: true` vs array (`[]`) notation:** `scalar: true` collapses the entire time window into one value per row — use it for overall rates, sorting, and alerting. Without `scalar: true`, metric columns are arrays (one value per interval); use `[]` notation for per-bucket trend analysis. When filtering or sorting on an array column, choose the aggregation that matches your intent: `arrayMax(col)` for **spike and threshold queries** ("did this ever exceed X in any bucket?") or `arrayAvg(col)` for **sustained-rate ranking** ("what was the typical level?"). Avoid `arrayAvg` of a cardinality metric — it is not a statistically correct overall rate; use `scalar: true` instead.

### User Action Volume

Track action volume trends by type:

```dql
timeseries action_count = sum(dt.frontend.user_action.count),
          by: {frontend.name, user_action.type},
          from: now() - 24h
```

**Use Case:** **Per-bucket trend.** Monitor user action volume by type (`hard_navigation`, `soft_navigation`, `same_view`, `api`) to detect traffic drops or spikes.

### User Action Duration

Track action duration trends for performance regression detection:

```dql
timeseries avg_duration = avg(dt.frontend.user_action.duration),
          p75_duration = percentile(dt.frontend.user_action.duration, 75),
          p95_duration = percentile(dt.frontend.user_action.duration, 95),
          by: {frontend.name},
          from: now() - 2h
| filter arrayMax(p95_duration) > 3000
| sort arrayMax(p95_duration) desc
```

**Use Case:** **Per-bucket trend.** Identify frontends where p95 user action duration spiked above 3000ms in any bucket. `arrayMax` catches brief post-deploy spikes that `arrayAvg` would smooth away.

### Action Timeout Rate

Find frontends with high action timeout rates:

```dql
timeseries
    total = sum(dt.frontend.user_action.count, scalar: true),
    timeouts = sum(dt.frontend.user_action.count, filter:{user_action.complete_reason == "timeout"}, scalar: true),
    by: {frontend.name},
    from: now() - 2h
| fieldsAdd timeout_rate = 100.0 * timeouts / total
| filter total > 10
| sort timeout_rate desc
```

**Use Case:** **Overall rate** across the time window. Actions timing out indicate slow backend responses or overly complex pages. `filter total > 10` avoids noise from low-traffic frontends.

## Event-Based Queries

### User Action Overview

Query all user actions:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action
| summarize
    action_count = count(),
    unique_sessions = countDistinct(dt.rum.session.id),
    avg_duration = avg(duration),
    by: {frontend.name, user_action.name, user_action.type}
| sort action_count desc
```

**Use Case:** Baseline user action volume and duration, broken down by action name and type.

### Completion Reasons

Analyze how user actions end:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action
| summarize
    action_count = count(),
    by: {frontend.name, user_action.complete_reason}
| sort action_count desc
```

**Use Case:** Identify timeouts and interruptions.

### Action Type Distribution

Break down user actions by type:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action
| summarize
    action_count = count(),
    avg_duration = avg(duration),
    by: {frontend.name, user_action.type}
| sort action_count desc
```

**Use Case:** Compare API-reported, soft navigation, and same-view actions.

### Actions by Interaction

Map actions to interaction types:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action
| summarize
    action_count = count(),
    avg_duration = avg(duration),
    avg_requests = avg(user_action.requests.count),
    by: {frontend.name, interaction.type}
| sort action_count desc
```

**Use Case:** Understand which interactions trigger the most actions.

### Resource-Heavy Actions

Find actions loading many resources:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action
| filter user_action.resources.count > 10
| summarize
    action_count = count(),
    avg_resources = avg(user_action.resources.count),
    avg_duration = avg(duration),
    by: {frontend.name, user_action.name}
| sort avg_resources desc
| limit 20
```

**Use Case:** Optimize actions that load too many resources.

### Actions with Pending Requests

Find actions that complete with in-flight requests:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action
| filter user_action.requests.pending_request_count > 0
| summarize
    action_count = count(),
    avg_pending = avg(user_action.requests.pending_request_count),
    by: {frontend.name, user_action.complete_reason}
| sort avg_pending desc
```

**Use Case:** Identify actions completing before requests finish.

### DOM Mutation Analysis

Analyze DOM change patterns:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action
| filter user_action.mutation_count > 0
| summarize
    action_count = count(),
    avg_mutations = avg(user_action.mutation_count),
    max_mutations = max(user_action.mutation_count),
    by: {frontend.name}
```

**Use Case:** Detect excessive DOM manipulation.

### Timed-Out Actions

Analyze actions that timed out:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action
| filter user_action.complete_reason == "timeout"
| summarize
    timeout_count = count(),
    avg_duration = avg(duration),
    avg_pending = avg(user_action.requests.pending_request_count),
    by: {frontend.name, user_action.name}
| sort timeout_count desc
| limit 20
```

**Use Case:** Fix slow actions that time out.

### Interrupted Actions

Analyze interrupted user flows:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action
| filter in(user_action.complete_reason, "interrupted_by_automatic", "interrupted_by_api")
| summarize
    interrupted_count = count(),
    by: {frontend.name, user_action.complete_reason, interaction.type}
| sort interrupted_count desc
```

**Use Case:** Understand action interruption patterns.

### User Action Web Vitals

Get Web Vitals captured during user actions:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action
| filter isNotNull(web_vitals.largest_contentful_paint)
| summarize
    action_count = count(),
    p75_lcp = percentile(web_vitals.largest_contentful_paint, 75),
    p75_inp = percentile(web_vitals.interaction_to_next_paint, 75),
    p75_fid = percentile(web_vitals.first_input_delay, 75),
    p75_cls = percentile(web_vitals.cumulative_layout_shift, 75),
    by: {frontend.name}
```

**Use Case:** Correlate user actions with Core Web Vitals.

### API-Reported Actions

Analyze actions reported via the API:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action
| filter characteristics.is_api_reported
| summarize
    action_count = count(),
    avg_duration = avg(duration),
    by: {frontend.name, user_action.name}
| sort action_count desc
```

**Use Case:** Track custom business actions reported by API.
