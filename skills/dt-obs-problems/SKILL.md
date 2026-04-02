---
name: dt-obs-problems
description: Problem entities, root cause analysis (RCA), impact assessment, and problem correlation. Query and analyze Dynatrace-detected problems and incidents.
license: Apache-2.0
---

# Problem Analysis Skill

Analyze Dynatrace AI-detected problems including root cause identification, impact assessment, and correlation with logs and metrics.

## Overview

Dynatrace automatically detects anomalies, performance degradations, and failures across your environment, creating **problems** that aggregate related alert, warning and info-level events and provide root cause and impact insights.

### What are Problems?

Problems are automatically detected, software and infrastructure health and resilience issues that:

- **Automatically correlate** related alert, warning, and info-level events across services, infrastructure, frontend applications, and user sessions
- **Identify root causes** using causal analysis of Smartscape dependencies
- **Assess business impact** by tracking affected users and services
- **Reduce alert noise** by grouping related symptoms into single problems that share the same root cause and impact
- **Track problem lifecycle** from early detection through resolution

### Event Kinds

The `event.kind` field (stable, permission) identifies the high-level event type:

| `event.kind` value | Description |
|---|---|
| `DAVIS_EVENT` | Davis-detected infrastructure/application events |
| `BIZ_EVENT` | Business events (ingested via API or captured from spans) |
| `RUM_EVENT` | Real User Monitoring events |
| `AUDIT_EVENT` | Administrative/security audit events |

`event.provider` (stable, permission) identifies the event source.

## Problem Categories

Common `event.category` values:

| Category | Description | Example |
|----------|-------------|---------|
| **AVAILABILITY** | Infrastructure or service unavailable | Web service returns no data, synthetic test actively fails, database connection lost |
| **ERROR** | Increased error rates beyond baseline | API error rate jumped from 0.1% to 15% |
| **SLOWDOWN** | Performance degradation | Response time increased from 200ms to 5000ms |
| **RESOURCE** | Resource saturation | Container memory at 95%, causing OOM kills |
| **CUSTOM** | Custom anomaly detections | Business KPI (orders/minute) dropped below threshold |

## Problem Lifecycle

```text
Detection → ACTIVE → Under Investigation → CLOSED
```

- **ACTIVE**: Currently occurring issues requiring attention
- **CLOSED**: Resolved issues used for historical analysis

## Essential Fields

### Common Field Name Mistakes

| ❌ WRONG | ✅ CORRECT | Description |
|---------|-----------|-------------|
| `title` | `event.name` | Problem title/description |
| `status` | `event.status` | Problem lifecycle status |
| `severity` | `event.category` | Problem type/category |
| `start` | `event.start` | Problem start time |

### Correct Status Values

```dql
// ✅ CORRECT: Use these status values
fetch dt.davis.problems
| filter event.status == "ACTIVE"   // Currently occurring problems
//     or event.status == "CLOSED"  // Resolved problems
// ❌ INCORRECT: event.status == "OPEN" does not exist!
| limit 1
```

### Key Fields Reference

```dql
fetch dt.davis.problems, from:now() - 1h
| filter not(dt.davis.is_duplicate)
| fields
    event.start,                          // Problem start timestamp
    event.end,                            // Problem end timestamp (if closed)
    display_id,                           // Human-readable problem ID (P-XXXXX)
    event.name,                           // Problem title
    event.description,                    // Detailed description
    event.category,                       // Problem type
    event.status,                         // ACTIVE or CLOSED
    dt.smartscape_source.id,              // The smartscape ID for the affected resource
    dt.davis.affected_users_count,        // Number of affected users
    smartscape.affected_entity.ids,        // Array of affected entity IDs
    dt.smartscape.service,                // Affected services (may be array)
    dt.davis.root_cause_entity,           // Entity identified as root cause
    root_cause_entity_id,                 // Root cause entity ID
    root_cause_entity_name,               // Human-readable root cause name
    dt.davis.is_duplicate,                // Whether duplicate detection
    dt.davis.is_rootcause                 // Root cause vs. symptom
| limit 10
```

## Standard Query Pattern

Always start problem queries with this foundation:

```dql
fetch dt.davis.problems, from:now() - 2h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| fields event.start, display_id, event.name, event.category
| sort event.start desc
| limit 20
```

**Key components:**

- `fetch dt.davis.problems` - The problems data source
- `not(dt.davis.is_duplicate)` - Filter out duplicate detections
- `event.status == "ACTIVE"` - Show only active problems
- Time range - Always specify a reasonable window

## Common Query Patterns

### Active Problems by Category

```dql
fetch dt.davis.problems
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| summarize problem_count = count(), by: {event.category}
| sort problem_count desc
```

### High-Impact Active Problems (affecting many users)

```dql
fetch dt.davis.problems
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter dt.davis.affected_users_count > 100
| fields event.start, display_id, event.name, dt.davis.affected_users_count, event.category
| sort dt.davis.affected_users_count desc
```

### High-Impact Active Problems (affecting many smartscape entities)

```dql
fetch dt.davis.problems
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter arraySize(affected_entity_ids) > 5
| fields event.start, display_id, event.name, affected_entity_ids, event.category, impacted_entity_count = arraySize(affected_entity_ids)
| sort impacted_entity_count desc
```

### Specific Problem Details

```dql
fetch dt.davis.problems
| filter display_id == "P-XXXXXXXXXX"
| fields event.start, event.end, event.name, event.description, affected_entity_ids, dt.davis.affected_users_count, root_cause_entity_id, root_cause_entity_name
```

### Service-Specific Problem History

```dql
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| filter in(dt.entity.service, "SERVICE-XXXXXXXXX") or in(dt.smartscape.service, toSmartscapeId("SERVICE-XXXXXXXXX"))
| summarize problems = count(), by: {event.category, event.status}
```

### Important: Entity Filter DO and DON'T

- **DO** use array-safe filters and include both deprecated and Smartscape service fields when filtering by service ID:

    ```dql
    | filter in(dt.entity.service, "SERVICE-00E66996F1555897") or in(dt.smartscape.service, toSmartscapeId("SERVICE-00E66996F1555897"))
    ```

- **DON'T** use scalar equality on service fields or only one field variant:

    ```dql
    // Wrong: not array-safe and misses Smartscape-only matches
    | filter dt.entity.service == "SERVICE-00E66996F1555897"
    ```

## Root Cause Analysis Patterns

### Basic Root Cause Query

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| fields
    display_id,
    event.name,
    event.description,
    root_cause_entity_id,
    root_cause_entity_name,
    smartscape.affected_entity.ids
```

### Root Cause by Entity Type

Identify which entity types most frequently cause problems:

```dql
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| filter isNotNull(root_cause_entity_id)
| summarize problem_count = count(), by:{root_cause_entity_name}
| sort problem_count desc
| limit 20
```

### Affected entity is an AWS resource 

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter matchesPhrase(arrayToString(smartscape.affected_entity.types, delimiter:","), "AWS_")
```


### Infrastructure Root Cause with Service Impact

```dql
fetch dt.davis.problems, from:now() - 30m
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter matchesPhrase(root_cause_entity_id, "HOST-")
| filter isNotNull(dt.smartscape.service)
| fields display_id, event.name, root_cause_entity_name, dt.smartscape.service
```

### Problem Blast Radius

Calculate entity impact per root cause:

```dql
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| filter isNotNull(root_cause_entity_id)
| fieldsAdd affected_count = arraySize(smartscape.affected_entity.ids)
| summarize
    avg_affected = avg(affected_count),
    max_affected = max(affected_count),
    problem_count = count(),
    by:{root_cause_entity_name}
| sort avg_affected desc
```

### Recurring Root Causes

Identify entities repeatedly causing problems:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate)
| filter isNotNull(root_cause_entity_id)
| summarize
    problem_count = count(),
    first_occurrence = min(event.start),
    last_occurrence = max(event.start),
    by:{root_cause_entity_id, root_cause_entity_name}
| filter problem_count > 3
| sort problem_count desc
```

## Problem Trending and Pattern Analysis

Track problem trends over time, identify recurring issues, and analyze resolution performance.

**Primary Files:**
- `references/problem-trending.md` - Timeseries analysis and pattern detection

**Common Use Cases:**
- Active problems over time with `makeTimeseries`
- Problem creation rate by category
- Recurring problem detection by schedule
- Resolution time trends and P95 duration analysis

**Key Techniques:**
- **`makeTimeseries`** vs **`bin()`**: Choose the right approach for lifecycle spans vs discrete events
- **NULL handling**: Use `coalesce(event.end, now())` for active problems
- **Peak hours analysis**: Identify when problems occur most frequently
- **Impact trending**: Track user impact changes over time

See `references/problem-trending.md` for complete query patterns and best practices.

## Best Practices

### Essential Rules

1. **Always filter duplicates**: Use `not(dt.davis.is_duplicate)` to avoid counting the same problem multiple times
2. **Use correct status values**: `"ACTIVE"` or `"CLOSED"`, never `"OPEN"`
3. **Specify time ranges**: Always include time bounds to optimize performance
4. **Include display_id**: Essential for problem identification and linking
5. **Test incrementally**: Add one filter or field at a time when building queries
6. **Filter early**: Apply `not(dt.davis.is_duplicate)` immediately after fetch

### Query Development

- **Start simple**: Begin with basic filtering, then add complexity
- **Test fields first**: Run with `| limit 1` to verify field names exist
- **Use meaningful time ranges**: Too broad wastes resources, too narrow misses data
- **Document problem IDs**: Always capture and store `display_id` for reference

### Root Cause Verification

- Always filter `isNotNull(root_cause_entity_id)` when required
- Cross-reference events using `dt.davis.event_ids`
- Consider time delays: root cause may appear in logs minutes before problem

### Time Range Guidelines

```dql
// ✅ GOOD - Specific time range
fetch dt.davis.problems, from:now() - 4h
```

```dql
// ❌ BAD - Scans all historical data
fetch dt.davis.problems
```

## Related Documentation

- **references/problem-trending.md**: Problem trending and timeseries analysis patterns
- **references/problem-correlation.md**: Correlating problems with logs and other telemetry
- **references/impact-analysis.md**: Business and technical impact assessment
- **references/problem-merging.md**: When and why DAVIS merges events into problems

## Related Skills

- **dt-dql-essentials** - Core DQL syntax and query structure for problem queries
- **dt-obs-logs** - Correlate problems with application and infrastructure logs
- **dt-obs-tracing** - Investigate problems through distributed trace analysis
