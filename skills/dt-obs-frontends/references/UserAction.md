# User Actions

Analyze user actions that capture interaction lifecycles, resource loading, and DOM mutations.

**Data Source:** `fetch user.events` with `characteristics.has_user_action == true`

**Key Fields:**

- `user_action.instance_id` - Unique user action ID
- `user_action.type` - Action type: `api`, `soft_navigation`, `xhr`
- `user_action.name` - Action name (preferred; `user_action.custom_name` is deprecated)
- `user_action.complete_reason` - How the action ended (for example: `completed`, `timeout`)
- `user_action.mutation_count` - DOM mutations during the action
- `user_action.requests.count` - Requests during the action
- `user_action.requests.pending_request_count` - Requests still pending at completion
- `user_action.resources.count` - Resources loaded during the action
- `user_action.resources.<initiator>.count` - Resources by initiator type (for example: `xmlhttprequest`)
- `interaction.name` - Interaction type (for example: `click`)
- `ui_element.name` - Resolved UI element name
- `ui_element.tag_name` - UI element type
- `characteristics.is_api_reported` - True when reported via API

## User Action Overview

Query all user actions:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action == true
| summarize
    action_count = count(),
    unique_sessions = countDistinct(dt.rum.session.id),
    avg_duration = avg(duration),
    by: {frontend.name}
```

**Use Case:** Baseline user action volume and duration.

## Completion Reasons

Analyze how user actions end:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action == true
| summarize
    action_count = count(),
    by: {frontend.name, user_action.complete_reason}
| sort action_count desc
```

**Use Case:** Identify timeouts and interruptions.

## Action Type Distribution

Break down user actions by type:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action == true
| summarize
    action_count = count(),
    avg_duration = avg(duration),
    by: {frontend.name, user_action.type}
| sort action_count desc
```

**Use Case:** Compare API-reported, soft navigation, and XHR-driven actions.

## Actions by Interaction

Map actions to interaction types:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action == true
| summarize
    action_count = count(),
    avg_duration = avg(duration),
    avg_requests = avg(user_action.requests.count),
    by: {frontend.name, interaction.name}
| sort action_count desc
```

**Use Case:** Understand which interactions trigger the most actions.

## Resource-Heavy Actions

Find actions loading many resources:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action == true
| filter user_action.resources.count > 10
| fieldsAdd action_name = coalesce(user_action.name, user_action.custom_name, interaction.name)
| summarize
    action_count = count(),
    avg_resources = avg(user_action.resources.count),
    avg_duration = avg(duration),
    by: {frontend.name, action_name}
| sort avg_resources desc
| limit 20
```

**Use Case:** Optimize actions that load too many resources.

## Actions with Pending Requests

Find actions that complete with in-flight requests:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action == true
| filter user_action.requests.pending_request_count > 0
| summarize
    action_count = count(),
    avg_pending = avg(user_action.requests.pending_request_count),
    by: {frontend.name, user_action.complete_reason}
| sort avg_pending desc
```

**Use Case:** Identify actions completing before requests finish.

## DOM Mutation Analysis

Analyze DOM change patterns:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action == true
| filter user_action.mutation_count > 0
| summarize
    action_count = count(),
    avg_mutations = avg(user_action.mutation_count),
    max_mutations = max(user_action.mutation_count),
    by: {frontend.name}
```

**Use Case:** Detect excessive DOM manipulation.

## Timed-Out Actions

Analyze actions that timed out:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action == true
| filter user_action.complete_reason == "timeout"
| fieldsAdd action_name = coalesce(user_action.name, user_action.custom_name, interaction.name)
| summarize
    timeout_count = count(),
    avg_duration = avg(duration),
    avg_pending = avg(user_action.requests.pending_request_count),
    by: {frontend.name, action_name}
| sort timeout_count desc
| limit 20
```

**Use Case:** Fix slow actions that time out.

## Interrupted Actions

Analyze interrupted user flows:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action == true
| filter in(user_action.complete_reason, "interrupted_by_navigation", "interrupted_by_request", "interrupted_by_api")
| summarize
    interrupted_count = count(),
    by: {frontend.name, user_action.complete_reason, interaction.name}
| sort interrupted_count desc
```

**Use Case:** Understand action interruption patterns.

## User Action Web Vitals

Get Web Vitals captured during user actions:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action == true
| filter isNotNull(web_vitals.largest_contentful_paint)
| summarize
    action_count = count(),
    p75_lcp = percentile(web_vitals.largest_contentful_paint, 75),
    p75_cls = percentile(web_vitals.cumulative_layout_shift, 75),
    by: {frontend.name}
```

**Use Case:** Correlate user actions with Core Web Vitals.

## API-Reported Actions

Analyze actions reported via the API:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_action == true
| filter characteristics.is_api_reported == true
| fieldsAdd action_name = coalesce(user_action.name, user_action.custom_name)
| summarize
    action_count = count(),
    avg_duration = avg(duration),
    by: {frontend.name, action_name}
| sort action_count desc
```

**Use Case:** Track custom business actions reported by API.