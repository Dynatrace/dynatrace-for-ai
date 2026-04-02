# Long Tasks & Browser Performance

Analyze long-running JavaScript tasks that block the main thread and affect interactivity.

**Data Source:** `fetch user.events` with `characteristics.has_long_task`

**Key Fields:**

- `duration` - Task duration (nanoseconds)
- `long_task.name` - Context attribution: self, same-origin, cross-origin, etc.
- `long_task.attribution.container_*` - Container details for iframe tasks
- `activity.id` - Associated activity (if any)

**Performance Thresholds:**

- Long task: > 50ms (blocks interaction)
- Critical: > 100ms (noticeable lag)
- Severe: > 250ms (frustrating UX)

## Long Tasks Overview

Query all long tasks:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| summarize
    task_count = count(),
    avg_duration = avg(duration),
    p75_duration = percentile(duration, 75),
    p95_duration = percentile(duration, 95),
    max_duration = max(duration),
    by: {frontend.name}

```

**Use Case:** Baseline long task frequency and severity.

## Long Tasks by Page

Identify pages with performance issues:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| summarize
    task_count = count(),
    avg_duration = avg(duration),
    p90_duration = percentile(duration, 90),
    by: {frontend.name, page.url.path}
| sort p90_duration desc
| limit 20

```

**Use Case:** Prioritize pages for JavaScript optimization.

## Long Tasks by Context

Analyze task origin:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| summarize
    task_count = count(),
    avg_duration = avg(duration),
    by: {frontend.name, long_task.name}
| sort task_count desc

```

**Use Case:** Identify first-party vs third-party blocking scripts.

## Third-Party Long Tasks

Find blocking third-party scripts:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| filter in(long_task.name, "cross-origin-ancestor", "cross-origin-descendant", "cross-origin-unreachable")
| summarize
    task_count = count(),
    total_blocking_time = sum(duration),
    by: {frontend.name, long_task.attribution.container_src}
| sort total_blocking_time desc
| limit 15

```

**Use Case:** Evaluate third-party script impact.

## Iframe Long Tasks

Analyze tasks from embedded content:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| filter long_task.attribution.container_type == "iframe"
| summarize
    task_count = count(),
    avg_duration = avg(duration),
    by: {frontend.name, long_task.attribution.container_id, long_task.attribution.container_src}
| sort avg_duration desc

```

**Use Case:** Optimize or lazy-load problematic iframes.

## Critical Long Tasks

Find severely blocking tasks:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| filter duration > 250000000
| summarize
    critical_tasks = count(),
    avg_duration = avg(duration),
    affected_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, page.url.path}
| sort critical_tasks desc
| limit 20

```

**Use Case:** Address worst performance offenders.

## Long Tasks During Activities

Correlate with user activities:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| filter isNotNull(activity.id)
| summarize
    task_count = count(),
    avg_duration = avg(duration),
    by: {frontend.name}

```

**Use Case:** Find tasks blocking user interactions.

## Long Task Trends

Track performance over time:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| summarize
    task_count = count(),
    p75_duration = percentile(duration, 75),
    by: {frontend.name, time_bucket = bin(start_time, 1h)}
| sort time_bucket asc

```

**Use Case:** Detect performance regressions over time.

## Total Blocking Time by Session

Measure session-level blocking:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_long_task == true
| summarize
    total_blocking = sum(duration),
    task_count = count(),
    by: {frontend.name, dt.rum.session.id}
| summarize
    avg_blocking_per_session = avg(total_blocking),
    p90_blocking_per_session = percentile(total_blocking, 90),
    by: {frontend.name}

```

**Use Case:** Benchmark total blocking time impact.

