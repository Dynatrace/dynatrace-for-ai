# Problem Correlation

Correlate DAVIS problems with logs, events, and other telemetry from affected entities to identify root causes through error messages, stack traces, and timeline analysis.

## Overview

When DAVIS detects a problem, use `smartscape.affected_entities` to query logs and telemetry from impacted entities. This correlation helps identify the specific error conditions, configuration changes, or resource constraints that triggered the problem.

`smartscape.affected_entities` is a **record array**; each record has an `id`, `type`, and `name`. How you access the members depends on whether the query expands the array first:

| Context | Accessor | Result |
|---------|----------|--------|
| No preceding `expand` | `smartscape.affected_entities[][id]` | array of IDs |
| After `expand smartscape.affected_entities` | `smartscape.affected_entities[id]` | one scalar ID per row |

Writing `smartscape.affected_entities[id]` **without** a preceding `expand` returns `null` silently, so it never raises an error and quietly drops every correlation. Two further rules follow from the array shape:

- **`join` needs `expand`.** A join key that is still an array matches nothing. Expand the records first so the key is a scalar.
- **`filter` cannot take a bare iterative expression.** Wrap the comparison in `iAny(...)`. Because `id` is a `smartscapeId` rather than a string, convert it with `toString()` before comparing it to a string; `type` and `name` are plain strings and need no conversion.

## Key Correlation Fields

| Field | Description | Usage |
|-------|-------------|-------|
| `smartscape.affected_entities` | Record array of directly impacted entities (`id`, `type`, `name`) | Project IDs with `[][id]` and use them in subqueries to filter logs/metrics/events/traces |
| `affected_entity_ids` | Array of classic entity IDs directly impacted | Use in subqueries to filter logs/metrics/events/traces |
| `root_cause_entity_id` | Entity ID identified as root cause | Focus investigation on this entity |
| `dt.davis.event_ids` | Underlying Davis event IDs | Query dt.davis.events for details |
| `event.start` / `event.end` | Problem timeframe | Define log query time window |

## Problem-to-Logs Correlation

### Basic Pattern

```dql
fetch logs
| filter dt.smartscape_source.id in [
    fetch dt.davis.problems
    | filter display_id == "P-12345678"
    | fields entity_ids = smartscape.affected_entities[][id]
  ] or dt.source_entity in [
    fetch dt.davis.problems
    | filter display_id == "P-12345678"
    | fields affected_entity_ids
  ]
| sort timestamp desc
| limit 100
```

## Problem-to-Alert-Events Correlation

### Basic Pattern

```dql
fetch dt.davis.events
| filter event.id in [ 
  fetch dt.davis.problems
  | filter display_id == "P-12345678"
  | fieldsKeep dt.davis.event_ids
  ]
```

### Active Problems with Recent Logs

Find logs from entities affected by currently active problems:

```dql
fetch logs, from:now() - 1h
| filter dt.smartscape_source.id in [
    fetch dt.davis.problems, from:now() - 1h
    | filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
    | fields entity_ids = smartscape.affected_entities[][id]
  ] or dt.source_entity in [
    fetch dt.davis.problems, from:now() - 1h
    | filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
    | fields affected_entity_ids
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
| filter dt.smartscape_source.id in [
   fetch dt.davis.problems
    | filter display_id == "P-12345678"
    | fields entity_ids = smartscape.affected_entities[][id]
  ] or dt.source_entity in [
    fetch dt.davis.problems
    | filter display_id == "P-12345678"
    | fields affected_entity_ids
]
| sort timestamp desc
| limit 100
```

### Log Pattern Detection

Identify common error patterns across problem-affected entities:

```dql
fetch logs, from:now() - 4h
| filter dt.smartscape_source.id in [
    fetch dt.davis.problems, from:now() - 4h
    | filter not(dt.davis.is_duplicate)
    | filter event.category == "ERROR"
    | fields entity_ids = smartscape.affected_entities[][id]
]
    or dt.source_entity in [
        fetch dt.davis.problems, from:now() - 4h
        | filter not(dt.davis.is_duplicate)
        | filter event.category == "ERROR"
        | fields affected_entity_ids
]
| filter loglevel == "ERROR"
| summarize error_count=count(), by:{content}
| sort error_count desc
| limit 20
```

## Timeline Analysis

### Logs Relative to Problem Occurrence

View logs in temporal context around problem detection. `expand` produces one row per affected
entity so the join key is a scalar; joining on the unexpanded array matches nothing:

```dql-snippet
fetch dt.davis.problems
| filter display_id == "P-12345678"
| expand smartscape.affected_entities
| fields problem_start=event.start, timestamp, entity_id = smartscape.affected_entities[id]
| join [
    fetch logs
    | filter in(loglevel, {"ERROR", "WARN"})
    | fields content, timestamp, dt.source_entity, loglevel
    | limit 100
], on:{left[entity_id] == right[dt.source_entity]}
| fieldsAdd time_offset = timestamp - problem_start
| sort timestamp asc
| fields timestamp, time_offset, right.loglevel, right.content
```

### Before and After Problem Start

Query logs with expanded time window to see precursor events:

```dql
// Get problem start time
fetch dt.davis.problems
| filter display_id == "P-12345678"
| fieldsAdd problem_start = event.start
| expand smartscape.affected_entities
| fieldsAdd problem_entity = smartscape.affected_entities[id]
```

```dql
// Query logs from 10 minutes before to 10 minutes after
fetch logs, from:now() - 1h
| filter dt.smartscape_source.id in [
    fetch dt.davis.problems
    | filter display_id == "P-12345678"
    | fields entity_ids = smartscape.affected_entities[][id]
]
    or dt.source_entity in [
        fetch dt.davis.problems
        | filter display_id == "P-12345678"
        | fields affected_entity_ids
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
| filter dt.smartscape_source.id in [
    fetch dt.davis.problems, from:now() - 2h
    | filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
    | fields entity_ids = smartscape.affected_entities[][id]
]
    or dt.source_entity in [
        fetch dt.davis.problems, from:now() - 2h
        | filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
        | fields affected_entity_ids
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
| expand smartscape.affected_entities
| fieldsAdd entityId = smartscape.affected_entities[id]
| summarize 
    problem_count = countDistinct(display_id),
    categories = collectDistinct(event.category),
    by:{entityId}
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
| expand smartscape.affected_entities
| fields problem_start = event.start, entity_id = smartscape.affected_entities[id], display_id, event.name, timestamp
| join [
    fetch events
    | filter event.type == "DEPLOYMENT"
], on:{left[entity_id] == right[dt.smartscape.service]}
| fieldsAdd time_since_deployment = problem_start - timestamp
| filter time_since_deployment > 0m and time_since_deployment < 30m
| fields display_id, event.name, time_since_deployment
```

### K8S or Technology Correlation

Check if active problems correlate with K8S deployment. Match on the `type` member rather than on
an ID prefix; `type` is a plain string, so it needs no `toString()` conversion:

```dql
fetch dt.davis.problems, from:now() - 48h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter iAny(smartscape.affected_entities[][type] == "K8S_DEPLOYMENT")
```

Check if active problems correlate with AWS S3 buckets:

```dql
fetch dt.davis.problems, from:now() - 48h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter iAny(smartscape.affected_entities[][type] == "AWS_S3_BUCKET")
```

## Root Cause Correlation

### Root Cause Entity Logs

Focus on logs from the identified root cause entity:

```dql
fetch logs, from:now() - 1h
    | filter dt.smartscape_source.id in [
        fetch dt.davis.problems, from:now() - 1h
        | filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
        | filter isNotNull(root_cause_entity_id)
        | fields root_cause_entity_id
    ]
    or dt.source_entity in [
        fetch dt.davis.problems, from:now() - 1h
        | filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
        | filter isNotNull(root_cause_entity_id)
        | fields root_cause_entity_id
]
| filter loglevel == "ERROR"
| sort timestamp desc
| limit 50
```

## Best Practices

### Absolute Timeframes Require Double Quotes

When using absolute ISO 8601 timestamps for `from` and `to` in any DQL query, **always wrap them in double quotes**. This applies to all data sources including `fetch logs` and `fetch dt.davis.problems`.

```dql
// ✅ CORRECT - absolute timestamps quoted
fetch logs, from: "2026-05-18T22:50:00Z", to: "2026-05-18T23:35:00Z"
| filter dt.smartscape_source.id in [
    fetch dt.davis.problems, from: "2026-05-18T22:00:00Z", to: "2026-05-18T23:35:00Z"
    | filter display_id == "P-12345678"
    | fields entity_ids = smartscape.affected_entities[][id]
  ] or dt.source_entity in [
    fetch dt.davis.problems, from: "2026-05-18T22:00:00Z", to: "2026-05-18T23:35:00Z"
    | filter display_id == "P-12345678"
    | fields affected_entity_ids
  ]
| filter loglevel == "ERROR"
| fields timestamp, dt.source_entity, loglevel, content
| sort timestamp desc
| limit 100
```

### Query Optimization

1. **Match time ranges**: Use same time window for problems and logs
   ```dql-snippet
   // ✅ CORRECT - Time ranges aligned
   fetch logs, from:now() - 1h
   | filter dt.smartscape_source.id in [
       fetch dt.davis.problems, from:now() - 1h
       | fields entity_ids = smartscape.affected_entities[][id]
   ] or dt.source_entity in [
       fetch dt.davis.problems, from:now() - 1h
       | fields affected_entity_ids
   ]
   | limit 100
   ```

2. **Filter early**: Apply `loglevel` filters before joins
   ```dql-snippet
   fetch logs, from:now() - 1h
   | filter loglevel == "ERROR"  // Filter before correlation
    | filter dt.smartscape_source.id in [...] or dt.source_entity in [...]
   ```

3. **Limit results**: Always use `limit` to prevent excessive data
   ```dql-snippet
   fetch logs
    | filter dt.smartscape_source.id in [...] or dt.source_entity in [...]
   | limit 200  // Reasonable limit
   ```

### Investigation Workflow

1. **Identify problem**: Get `display_id` and `smartscape.affected_entities[][id]`
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
| filter dt.smartscape_source.id in [
    fetch dt.davis.problems  // No time range
    | fields entity_ids = smartscape.affected_entities[][id]
]
    or dt.source_entity in [
        fetch dt.davis.problems  // No time range
        | fields affected_entity_ids
]
```

```dql
// ❌ WRONG - Not filtering duplicates
fetch dt.davis.problems
| fields entity_ids = smartscape.affected_entities[][id]  // Includes duplicates
```

```dql
// ✅ CORRECT - Time ranges aligned and duplicates filtered
fetch logs, from:now() - 1h
| filter dt.smartscape_source.id in [
    fetch dt.davis.problems, from:now() - 1h
    | filter not(dt.davis.is_duplicate)
    | fields entity_ids = smartscape.affected_entities[][id]
]
    or dt.source_entity in [
        fetch dt.davis.problems, from:now() - 1h
        | filter not(dt.davis.is_duplicate)
        | fields affected_entity_ids
]
```

### Handle Edge Cases

1. **Active problems have NULL event.end**: Use `coalesce(event.end, now())`
2. **Some problems have no root_cause_entity_id**: Use `isNotNull()` check
3. **`smartscape.affected_entities[][id]` is an array**: Use the `in` operator for filtering. An `in [ ... ]` subquery flattens an array-valued column, so the array can be projected directly
4. **Log timestamps may be slightly off**: Expand time window by 5-10 minutes

## Advanced Patterns

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
