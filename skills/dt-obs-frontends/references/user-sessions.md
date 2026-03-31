# User Sessions & Analytics

Track active user sessions, unique users, engagement patterns, and leverage custom properties for business insights.

## Core Session Metrics

**Key Metrics:**

- `dt.frontend.session.active.estimated_count` - Active user sessions
- `dt.frontend.user.active.estimated_count` - Unique active users

**Key Fields (Event-Based):**

- `dt.rum.session.id` - Unique session identifier
- `dt.rum.instance.id` - Unique user/device instance
- `dt.rum.user_tag` - Custom user identifier
- `session_properties.__property_name__` - Custom session properties
- `event_properties.__property_name__` - Custom event properties

**Alerting Thresholds:**

- Critical: Active sessions dropping > 50%
- Track user growth trends for capacity planning

## Active User Session Monitoring

Track active user sessions by application:

```dql
timeseries active_sessions = countDistinct(dt.frontend.session.active.estimated_count),
          by: {frontend.name},
          from: now() - 4h
| sort active_sessions desc

```

**Use Case:** Monitor real-time user engagement and capacity planning.

## Unique Active User Tracking

Monitor unique active users:

```dql
timeseries unique_users = countDistinct(dt.frontend.user.active.estimated_count),
          active_sessions = countDistinct(dt.frontend.session.active.estimated_count),
          by: {frontend.name},
          from: now() - 2h

| fieldsAdd
    app_name = frontend.name,
    sessions_per_user = active_sessions / unique_users
| sort unique_users desc

```

**Use Case:** Understand user engagement patterns and identify power users.

## Geographic User Distribution

Analyze user distribution across regions:

```dql
timeseries unique_users = countDistinct(dt.frontend.user.active.estimated_count),
          active_sessions = countDistinct(dt.frontend.session.active.estimated_count),
          by: {frontend.name, geo.country.iso_code},
          from: now() - 6h

| fieldsAdd
    app_name = frontend.name,
    avg_sessions_per_user = active_sessions / unique_users
| filter unique_users > 5
| sort unique_users desc

```

**Use Case:** Identify key geographic markets and plan regional infrastructure investments.

## Device Type Usage Patterns

Compare user activity across device types:

```dql
timeseries unique_users = countDistinct(dt.frontend.user.active.estimated_count),
          active_sessions = countDistinct(dt.frontend.session.active.estimated_count),
          by: {frontend.name, device.type},
          from: now() - 4h

| fieldsAdd
    app_name = frontend.name,
    session_ratio = active_sessions / unique_users
| sort device.type, unique_users desc

```

**Use Case:** Optimize mobile-first or desktop-first strategies based on device usage.

## Browser Adoption Tracking

Track browser distribution among active users:

```dql
timeseries unique_users = countDistinct(dt.frontend.user.active.estimated_count),
          active_sessions = countDistinct(dt.frontend.session.active.estimated_count),
          by: {frontend.name, browser.name},
          from: now() - 24h,
          interval: 1h
| filter unique_users > 1
| sort browser.name, timeframe desc

```

**Use Case:** Prioritize browser compatibility testing based on actual user distribution.

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

## User Interactions

Analyze user clicks, form inputs, scrolls, and other interactions for UX insights.

**Data Source:** `fetch user.events` with `characteristics.has_user_interaction`

**Key Fields:**

- `interaction.name` - Type: click, change, blur, scroll, touch, etc.
- `ui_element.name` - Element identifier (aria-label, title, name, etc.)
- `ui_element.custom_name` - Custom name via `data-dt-name` attribute
- `ui_element.tag_name` - HTML tag or mobile component type
- `ui_element.features` - Feature grouping via `data-dt-features`

### All User Interactions

Query all interaction types:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_interaction == true
| summarize
    interaction_count = count(),
    session_count = countDistinct(dt.rum.session.id),
    by: {frontend.name, interaction.name}
| sort interaction_count desc

```

### Click Analysis

Analyze button/link clicks:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_interaction == true
| filter interaction.name == "click"
| summarize
    click_count = count(),
    unique_users = countDistinct(dt.rum.instance.id, precision: 9),
    by: {frontend.name, ui_element.resolved_name, ui_element.tag_name}
| sort click_count desc
| limit 30

```

**Use Case:** Identify most-clicked UI elements.

### Feature Usage Analysis

Analyze custom feature areas:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_user_interaction == true
| filter isNotNull(ui_element.features)
| summarize
    interaction_count = count(),
    unique_users = countDistinct(dt.rum.instance.id, precision: 9),
    by: {ui_element.features}
| sort interaction_count desc

```

**Use Case:** Measure feature adoption using `data-dt-features`.

## Page & View Analysis

Analyze page summaries (web) and view summaries (mobile) for engagement metrics.

**Key Fields:**

- `page.url.path` / `view.name` - Page/view identifier
- `page.foreground_time` / `view.foreground_time` - Active time
- `page.background_time` / `view.background_time` - Hidden time
- `view.sequence_number` - View position in session
- `navigation.type` - How user arrived: `navigate`, `reload`, `back_forward`

### Page Views Overview

Query all page views (web):

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_page_summary == true
| summarize
    page_views = count(),
    unique_sessions = countDistinct(dt.rum.session.id),
    unique_users = countDistinct(dt.rum.instance.id, precision: 9),
    by: {frontend.name, page.url.path}
| sort page_views desc
| limit 30

```

**Use Case:** Identify most visited pages.

### Entry Pages

Analyze landing pages:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_page_summary == true
| filter view.sequence_number == 1
| summarize
    entry_count = count(),
    unique_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, page.url.path}
| sort entry_count desc
| limit 20

```

**Use Case:** Optimize landing page performance.

### Views per Session

Analyze session depth:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_page_summary == true or characteristics.has_view_summary == true
| summarize max_sequence = max(view.sequence_number), by: {frontend.name, dt.rum.session.id}
| summarize
    sessions = count(),
    avg_views = avg(max_sequence),
    p50_views = percentile(max_sequence, 50),
    p90_views = percentile(max_sequence, 90),
    by: {frontend.name}

```

**Use Case:** Measure user journey depth.

