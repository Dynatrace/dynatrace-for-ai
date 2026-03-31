# User Sessions & Custom Properties

Analyze user sessions and leverage custom session/event properties for business insights.

**Data Source:** `fetch user.events` with session and event properties

**Key Fields:**

- `dt.rum.session.id` - Unique session identifier
- `dt.rum.instance.id` - Unique user/device instance
- `dt.rum.user_tag` - Custom user identifier
- `session_properties.__property_name__` - Custom session properties
- `event_properties.__property_name__` - Custom event properties

## Sessions with User Tags

Query tagged user sessions:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_tag == true
| summarize
    session_count = countDistinct(dt.rum.session.id),
    event_count = count(),
    by: {frontend.name, dt.rum.user_tag}
| sort session_count desc
| limit 50

```

**Use Case:** Analyze behavior of specific identified users.

## Sessions by Custom Property

Aggregate by session property (e.g., subscription tier):

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_session_properties == true
| summarize
    session_count = countDistinct(dt.rum.session.id),
    user_count = countDistinct(dt.rum.instance.id, precision: 9),
    by: {frontend.name}

```

**Use Case:** Segment users by custom business attributes.

## Event Properties Analysis

Query events with custom properties:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_event_properties == true
| summarize
    event_count = count(),
    session_count = countDistinct(dt.rum.session.id),
    by: {frontend.name}

```

**Use Case:** Track custom business events and conversions.

## Session Duration Analysis

Analyze session lengths:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_page_summary == true or characteristics.has_view_summary == true
| summarize
    session_duration = sum(duration),
    by: {frontend.name, dt.rum.session.id}
| summarize
    avg_duration = avg(session_duration),
    p50_duration = percentile(session_duration, 50),
    p90_duration = percentile(session_duration, 90),
    by: {frontend.name}

```

**Use Case:** Understand user engagement depth.

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

## Session Journey Overview

Trace user journey through an app:

```dql
fetch user.events, from: now() - 2h
| filter dt.rum.session.id == "<session_id>"
| fields
    start_time,
    characteristics.classifier,
    view.name,
    page.url.path,
    interaction.name,
    error.type
| sort start_time asc

```

**Use Case:** Debug specific user session issues.

## New vs Returning Users

Analyze user retention patterns:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_navigation == true
| summarize
    sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, dt.rum.instance.id}
| summarize
    single_session_users = countIf(sessions == 1),
    returning_users = countIf(sessions > 1),
    by: {frontend.name}

```

**Use Case:** Measure user retention and engagement.

## Geographic Session Distribution

Sessions by location:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_navigation == true
| summarize
    session_count = countDistinct(dt.rum.session.id),
    user_count = countDistinct(dt.rum.instance.id, precision: 9),
    by: {frontend.name, geo.country.iso_code, geo.region.name}
| sort session_count desc

```

**Use Case:** Target regional performance optimization.

