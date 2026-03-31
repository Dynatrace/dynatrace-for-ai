# Page & View Analysis

Analyze page summaries (web) and view summaries (mobile) for engagement metrics.

**Data Source:** `fetch user.events` with `characteristics.has_page_summary` or `characteristics.has_view_summary`

**Key Fields:**

- `page.url.path` / `view.name` - Page/view identifier
- `page.foreground_time` / `view.foreground_time` - Active time
- `page.background_time` / `view.background_time` - Hidden time
- `view.sequence_number` - View position in session
- `navigation.type` - How user arrived: `navigate`, `reload`, `back_forward`

## Page Views Overview

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

## View Summaries (Mobile)

Query mobile view engagement:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_view_summary == true
| summarize
    view_count = count(),
    unique_sessions = countDistinct(dt.rum.session.id),
    avg_foreground_time = avg(view.foreground_time),
    by: {frontend.name, view.name}
| sort view_count desc
| limit 30

```

**Use Case:** Analyze mobile screen engagement.

## Time on Page

Analyze engagement depth:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_page_summary == true
| summarize
    page_views = count(),
    avg_foreground = avg(page.foreground_time),
    p50_foreground = percentile(page.foreground_time, 50),
    p90_foreground = percentile(page.foreground_time, 90),
    by: {frontend.name, page.url.path}
| filter page_views > 50
| sort avg_foreground desc
| limit 20

```

**Use Case:** Identify high-engagement pages.

## Pages with Errors

Find error-prone pages:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_page_summary == true
| filter error.exception_count > 0 or error.http_4xx_count > 0 or error.http_5xx_count > 0
| summarize
    page_views = count(),
    total_exceptions = sum(error.exception_count),
    total_4xx = sum(error.http_4xx_count),
    total_5xx = sum(error.http_5xx_count),
    by: {frontend.name, page.url.path}
| sort total_exceptions desc
| limit 20

```

**Use Case:** Prioritize pages for error fixes.

## Entry Pages

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

## Navigation Type Distribution

Analyze how users arrive:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_page_summary == true
| summarize
    view_count = count(),
    by: {frontend.name, navigation.type}
| sort view_count desc

```

**Use Case:** Understand navigation patterns.

## Single Page App Navigation

Track soft navigations (SPA):

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_view_summary == true
| filter navigation.type == "soft_navigation"
| summarize
    soft_nav_count = count(),
    by: {frontend.name, view.name}
| sort soft_nav_count desc

```

**Use Case:** Monitor SPA route transitions.

## Background Time Analysis

Understand tab switching behavior:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_page_summary == true
| filter page.background_time > 0
| summarize
    pages_with_background = count(),
    avg_background_time = avg(page.background_time),
    total_background = sum(page.background_time),
    by: {frontend.name, page.url.path}
| sort total_background desc
| limit 20

```

**Use Case:** Identify pages where users switch tabs.

## Views per Session

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

