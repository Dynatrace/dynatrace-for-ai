# Problem Trending and Timeseries Analysis

Analyze problem patterns over time to identify trends, detect recurring issues, and understand frequency changes.

## Key Concepts

**`makeTimeseries`** vs **`bin()`**:
- `makeTimeseries`: Handles problem lifecycle spans (start to end)
- `bin()`: Groups discrete timestamps into intervals

**Problem Lifecycle**:
- `event.start`: When problem began
- `event.end`: When resolved (NULL if active)
- Use `spread: timeframe()` to show problems across duration

## Active Problems Over Time

Chart currently active problem count, typically visualized as red bar chart:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| makeTimeseries
    active_problems = count(),
    interval: 1h,
    spread: timeframe(from:event.start, to:coalesce(event.end, now()))
```

## Problem Creation Rate

Track when new problems are detected:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate)
| summarize new_problems = count(), by:{start_bin = bin(event.start, 1h)}
| sort start_bin asc
```

## Category Trends

Track problem trends by category:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate)
| summarize problem_count = count(), by:{event.category, start_day = bin(event.start, 1d)}
| sort start_day asc
```

## Service-Specific Trending

Monitor problem frequency for a service:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate)
| filter in(dt.entity.service, "SERVICE-00E66996F1555897") or in(dt.smartscape.service, toSmartscapeId("SERVICE-00E66996F1555897"))
| summarize by:{start_day = bin(event.start, 24h)}, {
    total_problems = count(),
    active = countIf(event.status == "ACTIVE"),
    closed = countIf(event.status == "CLOSED")
}
| sort start_day asc
```

## Peak Problem Hours

When problems occur most frequently:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate)
| fieldsAdd hour_of_day = formatTimestamp(event.start, format:"HH")
| summarize problem_count = count(), by:{hour_of_day, event.category}
| sort hour_of_day asc
```

## Problem Duration Trending

Analyze if problems take longer to resolve:

```dql
fetch dt.davis.problems, from:now() - 30d
| filter not(dt.davis.is_duplicate) and event.status == "CLOSED"
| fieldsAdd duration_minutes = (event.end - event.start) / 60000000000
| summarize by:{start_day = bin(event.start, 24h)}, {
    avg_duration = avg(duration_minutes),
    p95_duration = percentile(duration_minutes, 95)
}
| sort start_day asc
```

## Recurring Problem Detection

Find problems repeating on similar schedules:

```dql
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| fieldsAdd
    day_of_week = formatTimestamp(event.start, format:"EEEE"),
    hour = formatTimestamp(event.start, format:"HH")
| summarize problem_count = count(), by:{day_of_week, hour}
| filter problem_count > 3
| sort problem_count desc
```

## Impact Trending

Track user impact over time:

```dql
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| filter isNotNull(dt.davis.affected_users_count)
| summarize
    total_users_affected = sum(dt.davis.affected_users_count),
    avg_users_per_problem = avg(dt.davis.affected_users_count),
    by:{bin(event.start, 1h)}
```

## Best Practices

### makeTimeseries Guidelines

```dql
// ✅ GOOD - Show durations accurately
fetch dt.davis.problems, from:now() - 24h
| filter event.status == "ACTIVE"
| makeTimeseries
    count(),
    interval: 15m,
    spread: timeframe(from:event.start, to:coalesce(event.end, now()))
```

### Common Pitfalls

```dql
// ❌ WRONG - Not filtering duplicates
fetch dt.davis.problems, from:now() - 7d
| summarize count(), by:{bin(event.start, 1h)}
```

```dql
// ✅ CORRECT - Always filter duplicates
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| summarize count(), by:{bin(event.start, 1h)}
```

### Handle Null Timestamps

Active problems have NULL event.end - use `coalesce(event.end, now())` in spread.
