# Frontend User Engagement Analysis

Advanced user engagement patterns, activity analysis, and behavioral insights using RUM metrics.

**Best Practices:**

- Identify peak usage hours for maintenance windows
- Track user growth trends over weeks/months
- Monitor version adoption rates
- Segment real users from synthetic monitoring

## User Activity Growth Trends

Monitor user growth and session trends over time:

```dql
timeseries {
    unique_users = countDistinct(dt.frontend.user.active.estimated_count),
    active_sessions = countDistinct(dt.frontend.session.active.estimated_count)
},
  by: {frontend.name},
  from: now() - 7d,
  interval: 1d

| join [
  timeseries {
    prev_unique_users = countDistinct(dt.frontend.user.active.estimated_count)
  },
    by: {frontend.name},
    from: now() - 7d,
    interval: 1d,
    shift: 1d

], on: { frontend.name }, fields: { prev_unique_users }

| fieldsAdd
    app_name = frontend.name,
    user_growth = coalesce((unique_users[] - prev_unique_users[]) / (prev_unique_users[]) * 100, 0)
| sort timeframe desc

```

**Use Case:** Track application adoption and identify growth or churn trends.

## User Type Segmentation

Analyze activity by user type (real users vs synthetic):

```dql
timeseries unique_users = countDistinct(dt.frontend.user.active.estimated_count),
          active_sessions = countDistinct(dt.frontend.session.active.estimated_count),
          by: {frontend.name, dt.rum.user_type},
          from: now() - 4h

| fieldsAdd
    app_name = frontend.name,
    user_category = dt.rum.user_type
| sort user_category, unique_users desc

```

**Use Case:** Distinguish between real user traffic and synthetic monitoring.

## Peak Usage Hour Identification

Identify peak activity periods for capacity planning:

```dql
timeseries {
    unique_users = countDistinct(dt.frontend.user.active.estimated_count),
    active_sessions = countDistinct(dt.frontend.session.active.estimated_count)
},
  by: {frontend.name},
  from: now() - 7d,
  interval: 1h

| fieldsAdd
    app_name = frontend.name,
    hour_of_day = getHour(timeframe)
| summarize
    avg_users = avg(arrayAvg(unique_users)),
    max_users = max(arrayMax(unique_users)),
    avg_sessions = avg(arrayAvg(active_sessions)),
    by: {app_name, hour_of_day}
| sort hour_of_day asc

```

**Use Case:** Optimize resource allocation and maintenance windows.

## User Engagement Intensity

Measure user engagement through session activity:

```dql
timeseries {
    unique_users = countDistinct(dt.frontend.user.active.estimated_count),
    active_sessions = countDistinct(dt.frontend.session.active.estimated_count),
    request_count = sum(dt.frontend.request.count)
},
  by: {frontend.name},
  from: now() - 2h

| fieldsAdd
    app_name = frontend.name,
    requests_per_user = arraySum(request_count) / arraySum(unique_users),
    requests_per_session_val = arraySum(request_count) / arraySum(active_sessions)
| sort requests_per_user desc

```

**Use Case:** Identify highly engaged users and optimize for power user workflows.

## Session Activity Level Classification

Estimate average session activity levels:

```dql
timeseries {
  active_sessions = countDistinct(dt.frontend.session.active.estimated_count, scalar: true),
  request_count = sum(dt.frontend.request.count, scalar: true)
},
  by: {frontend.name},
  from: now() - 1h,
  interval: 5m

| fieldsAdd
    app_name = frontend.name,
    requests_per_session = request_count / active_sessions
| fieldsAdd
    activity_level = if(requests_per_session > 10, "high",
                      else: if(requests_per_session > 3, "medium",
                      else: "low"))
| filter active_sessions > 0

```

**Use Case:** Classify session engagement levels for user behavior analysis.

## Multi-Device Usage Patterns

Identify sessions across multiple device types:

```dql
timeseries sessions_by_device = countDistinct(dt.frontend.session.active.estimated_count),
          by: {frontend.name, device.type},
          from: now() - 4h
| summarize
    total_sessions = sum(sessions_by_device),
    device_types_used = countDistinct(device.type),
    by: {frontend.name}
| fieldsAdd
    multi_device_indicator = if(device_types_used > 1, "yes", else: "no")
| sort total_sessions desc

```

**Use Case:** Understand cross-device usage patterns for seamless experience design.

