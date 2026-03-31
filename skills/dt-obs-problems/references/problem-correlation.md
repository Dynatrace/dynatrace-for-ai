# Problem Correlation

Correlate DAVIS problems with logs, events, and other telemetry from affected entities to identify root causes through error messages, stack traces, and timeline analysis.

## Overview

When DAVIS detects a problem, use `smartscape.affected_entity.ids` to query logs and telemetry from impacted entities. This correlation helps identify the specific error conditions, configuration changes, or resource constraints that triggered the problem.

## Key Correlation Fields

| Field | Description | Usage |
|-------|-------------|-------|
| `smartscape.affected_entity.ids` | Array of entity IDs directly impacted | Use in subqueries to filter logs/metrics |
| `root_cause_entity_id` | Entity ID identified as root cause | Focus investigation on this entity |
| `dt.davis.event_ids` | Underlying Davis event IDs | Query dt.davis.events for details |
| `event.start` / `event.end` | Problem timeframe | Define log query time window |

## Problem-to-Logs Correlation

### Basic Pattern

```dql
fetch logs
| filter dt.source_entity in [
    fetch dt.davis.problems
    | filter display_id == "P-12345678"
    | fields smartscape.affected_entity.ids
]
| sort timestamp desc
| limit 100
```

### Active Problems with Recent Logs

Find logs from entities affected by currently active problems:

```dql
fetch logs, from:now() - 1h
| filter dt.source_entity in [
    fetch dt.davis.problems, from:now() - 1h
    | filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
    | fields smartscape.affected_entity.ids
]
| filter in(loglevel, {"ERROR", "WARN"})
| fields timestamp, dt.source_entity, loglevel, content
| limit 200
```

### Problem-Specific Error Analysis

Get error logs from a specific problem:

```dql
fetch logs, from:now() - 2h
| filter loglevel == "ERROR"
| filter dt.source_entity in [
    fetch dt.davis.problems
    | filter display_id == "P-12345678"
    | fields smartscape.affected_entity.ids
]
| sort timestamp desc
| limit 100
```

### Log Pattern Detection

Identify common error patterns across problem-affected entities:

```dql
fetch logs, from:now() - 4h
| filter dt.source_entity in [
    fetch dt.davis.problems, from:now() - 4h
    | filter not(dt.davis.is_duplicate)
    | filter event.category == "ERROR"
    | fields smartscape.affected_entity.ids
]
| filter loglevel == "ERROR"
| summarize error_count=count(), by:{content}
| sort error_count desc
| limit 20
```

## Timeline Analysis

### Logs Relative to Problem Occurrence

View logs in temporal context around problem detection:

```dql-snippet
fetch dt.davis.problems
| filter display_id == "P-12345678"
| fields problem_start=event.start, smartscape.affected_entity.ids, timestamp
| join [
    fetch logs
    | filter in(loglevel, {"ERROR", "WARN"})
    | fields content, timestamp, dt.source_entity, loglevel
], on:{left[smartscape.affected_entity.ids] == right[dt.source_entity]}
| fieldsAdd time_offset = timestamp - problem_start
| sort timestamp asc
| fields timestamp, time_offset, loglevel, content
```

### Before and After Problem Start

Query logs with expanded time window to see precursor events:

```dql
// Get problem start time
fetch dt.davis.problems
| filter display_id == "P-12345678"
| fields problem_start = event.start, problem_entities = smartscape.affected_entity.ids
```

```dql
// Query logs from 10 minutes before to 10 minutes after
fetch logs, from:now() - 1h
| filter dt.source_entity in [
    fetch dt.davis.problems
    | filter display_id == "P-12345678"
    | fields smartscape.affected_entity.ids
]
| filter timestamp >= (problem_start - 10m) and timestamp <= (problem_start + 10m)
| sort timestamp asc
```

## Multiple Problems Correlation

### Common Log Patterns Across Problems

Find shared error messages affecting multiple problems:

```dql
fetch logs, from:now() - 2h
| filter loglevel == "ERROR"
| filter dt.source_entity in [
    fetch dt.davis.problems, from:now() - 2h
    | filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
    | fields smartscape.affected_entity.ids
]
| summarize problems_affected = countDistinct(dt.source_entity), by:{content}
| filter problems_affected > 1
| sort problems_affected desc
```

### Cross-Problem Entity Analysis

Identify entities appearing in multiple problems:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate)
| expand smartscape.affected_entity.ids
| summarize 
    problem_count = countDistinct(display_id),
    categories = collectDistinct(event.category),
    by:{smartscape.affected_entity.ids}
| filter problem_count > 1
| sort problem_count desc
```

## Problem-to-Events Correlation

### Underlying Davis Events

Retrieve Davis events contributing to the problem:

```dql
fetch dt.davis.events
| filter event.id in [
    fetch dt.davis.problems
    | filter display_id == "P-12345678"
    | fields dt.davis.event_ids
]
| fields event.start, event.name, event.description, dt.source_entity
| sort event.start asc
```

### Deployment Correlation

Check if problems correlate with recent deployments:

```dql
fetch dt.davis.problems, from:now() - 2h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| fields problem_start = event.start, display_id, event.name, smartscape.affected_entity.ids, timestamp
| join [
    fetch events
    | filter event.type == "DEPLOYMENT"
], on:{left[smartscape.affected_entity.ids] == right[dt.smartscape.service]}
| fieldsAdd time_since_deployment = problem_start - timestamp
| filter time_since_deployment > 0 and time_since_deployment < 30m
| fields display_id, event.name, time_since_deployment
```

## Root Cause Correlation

### Root Cause Entity Logs

Focus on logs from the identified root cause entity:

```dql
fetch logs, from:now() - 1h
| filter dt.source_entity in [
    fetch dt.davis.problems, from:now() - 1h
    | filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
    | filter isNotNull(root_cause_entity_id)
    | fields root_cause_entity_id
]
| filter loglevel == "ERROR"
| sort timestamp desc
| limit 50
```

### Infrastructure Root Cause with Service Logs

When infrastructure causes service problems, correlate both:

```dql
fetch dt.davis.problems, from:now() - 2h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter matchesPhrase(root_cause_entity_id, "HOST-")
| fields display_id, root_cause_entity_id, smartscape.affected_entity.ids
// Query logs from affected services, not the host itself
| join [
    fetch logs
    | filter in(loglevel, {"ERROR", "WARN"})
], on:{left[smartscape.affected_entity.ids] == right[dt.source_entity]}
```

## Best Practices

### Query Optimization

1. **Match time ranges**: Use same time window for problems and logs
   ```dql
   // ✅ CORRECT - Time ranges aligned
   fetch logs, from:now() - 1h
   | filter dt.source_entity in [
       fetch dt.davis.problems, from:now() - 1h
       | fields smartscape.affected_entity.ids
   ]
   ```

2. **Filter early**: Apply `loglevel` filters before joins
   ```dql
   fetch logs, from:now() - 1h
   | filter loglevel == "ERROR"  // Filter before correlation
   | filter dt.source_entity in [...]
   ```

3. **Limit results**: Always use `limit` to prevent excessive data
   ```dql
   fetch logs
   | filter dt.source_entity in [...]
   | limit 200  // Reasonable limit
   ```

### Investigation Workflow

1. **Identify problem**: Get `display_id` and `smartscape.affected_entity.ids`
2. **Expand time window**: Query logs from before problem start to after resolution
3. **Filter by severity**: Start with ERROR, expand to WARN if needed
4. **Look for patterns**: Use `summarize` to find recurring messages
5. **Focus on root cause**: If identified, query logs from `root_cause_entity_id`
6. **Check timeline**: Use joins to see temporal relationships
7. **Correlate with events**: Check for deployments, configuration changes

### Common Pitfalls

```dql
// ❌ WRONG - Missing time range alignment
fetch logs, from:now() - 1h
| filter dt.source_entity in [
    fetch dt.davis.problems  // No time range
    | fields smartscape.affected_entity.ids
]
```

```dql
// ❌ WRONG - Not filtering duplicates
fetch dt.davis.problems
| fields smartscape.affected_entity.ids  // Includes duplicates
```

```dql
// ✅ CORRECT - Time ranges aligned and duplicates filtered
fetch logs, from:now() - 1h
| filter dt.source_entity in [
    fetch dt.davis.problems, from:now() - 1h
    | filter not(dt.davis.is_duplicate)
    | fields smartscape.affected_entity.ids
]
```

### Handle Edge Cases

1. **Active problems have NULL event.end**: Use `coalesce(event.end, now())`
2. **Some problems have no root_cause_entity_id**: Use `isNotNull()` check
3. **smartscape.affected_entity.ids is an array**: Use `in` operator for filtering
4. **Log timestamps may be slightly off**: Expand time window by 5-10 minutes

## Advanced Patterns

### Multi-Layer Correlation

Correlate problems → events → logs in a single query:

```dql-snippet
fetch dt.davis.problems, from:now() - 1h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| fields display_id, event.start, dt.davis.event_ids, smartscape.affected_entity.ids
| join [
    fetch dt.davis.events
], on:{left[dt.davis.event_ids] == right[event.id]}
| join [
    fetch logs
    | filter loglevel == "ERROR"
    | fields content, timestamp, dt.source_entity
], on:{left[smartscape.affected_entity.ids] == right[dt.source_entity]}
| fields display_id, event.name, event.description, timestamp, content
```

### Problem Frequency vs Log Volume

Check if log volume spikes correlate with problem frequency:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate)
| summarize problem_count = count(), by:{time_bucket = bin(event.start, 1h)}
| join [
    fetch logs, from:now() - 24h
    | filter loglevel == "ERROR"
    | summarize log_count = count(), by:{time_bucket = bin(timestamp, 1h)}
], on:{left[time_bucket] == right[time_bucket]}
| fieldsAdd log_count = right.log_count
| fields time_bucket, problem_count, log_count
| sort time_bucket asc
```

## Related Documentation

- **impact-analysis.md**: Assessing business and technical impact
- **../SKILL.md**: Core problem analysis concepts
