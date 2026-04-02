---
name: dt-obs-logs
description: Log queries, filtering, pattern analysis, and log correlation. Search and analyze application and infrastructure logs.
license: Apache-2.0
---

# Log Analysis Skill

Query, filter, and analyze Dynatrace log data using DQL for troubleshooting and monitoring.

## What This Skill Covers

- Fetching and filtering logs by severity, content, and entity
- Searching log messages using pattern matching
- Calculating error rates and statistics
- Analyzing log patterns and trends
- Grouping and aggregating log data by dimensions

## When to Use This Skill

Use this skill when users want to:
- Find specific log entries (e.g., "show me error logs from the last hour")
- Filter logs by severity, process group, or content
- Search logs for specific keywords or phrases
- Calculate error rates or log statistics
- Identify common error messages or patterns
- Analyze log trends over time
- Troubleshoot issues using log data

## Key Concepts

### Log Data Model
- **timestamp**: When the log entry was created
- **content**: The log message text
- **status**: Log level (ERROR, FATAL, WARN, INFO, etc.)
- **dt.process_group.id**: Associated process group entity
- **dt.process_group.detected_name**: Resolves process group IDs to human-readable names

### Query Patterns
- **fetch logs**: Primary command for log data access
- **Time ranges**: Use `from:now() - <duration>` for time windows
- **Filtering**: Apply severity, content, and entity filters
- **Aggregation**: Group and summarize log data
- **Pattern Detection**: Use `matchesPhrase()` and `contains()` for content search

### Common Operations
- Severity filtering (single or multiple levels)
- Content search (simple and full-text)
- Entity-based filtering (process groups)
- Time-series analysis (bucketing, sorting)
- Error rate calculation
- Pattern analysis (exceptions, timeouts, etc.)

## Core Workflows

### 1. Log Searching
Find specific log entries by time, severity, and content.

**Typical steps**:
1. Define time range
2. Filter by severity (optional)
3. Search content for keywords
4. Select relevant fields
5. Sort and limit results

**Example**:
```dql
fetch logs, from:now() - 1h
| filter status == "ERROR"
| fields timestamp, content, process_group = dt.process_group.detected_name
| sort timestamp desc
| limit 100
```

### 2. Log Filtering
Narrow down logs using multiple criteria (severity, entity, content).

**Typical steps**:
1. Fetch logs with time range
2. Apply severity filters
3. Filter by entity (process_group)
4. Apply content filters
5. Format and sort output

**Example**:
```dql
fetch logs, from:now() - 2h
| filter in(status, {"ERROR", "FATAL", "WARN"})
| summarize count(), by: {dt.process_group.id, dt.process_group.detected_name}
| fieldsAdd process_group = dt.process_group.detected_name
| sort `count()` desc
```

### 3. Pattern Analysis
Identify patterns, trends, and anomalies in log data.

**Typical steps**:
1. Fetch logs with time range
2. Add pattern detection fields
3. Aggregate by entity or time
4. Calculate statistics and ratios
5. Sort by frequency or rate

**Example**:
```dql
fetch logs, from:now() - 2h
| filter status == "ERROR"
| fieldsAdd
    has_exception = if(matchesPhrase(content, "exception"), true, else: false),
    has_timeout = if(matchesPhrase(content, "timeout"), true, else: false)
| summarize
    count(),
    exception_count = countIf(has_exception == true),
    timeout_count = countIf(has_timeout == true),
    by: {process_group = dt.process_group.detected_name}
```

## Key Functions

### Filtering
- `filter status == "ERROR"` - Filter by status level
- `in(status, "ERROR", "FATAL", "WARN")` - Multi-status filter
- `contains(content, "keyword")` - Simple substring search
- `matchesPhrase(content, "exact phrase")` - Full-text phrase search

### Entity Operations
- `dt.process_group.detected_name` - Get human-readable process group name
- `filter process_group == "service-name"` - Filter by specific entity

### Aggregation
- `count()` - Count all log entries
- `countIf(condition)` - Conditional count
- `by: {dimension}` - Group by entity or time bucket
- `bin(timestamp, 5m)` - Time bucketing for trends

### Field Operations
- `fields timestamp, content, status` - Select specific fields
- `fieldsAdd name = expression` - Add computed fields
- `if(condition, true_value, else: false_value)` - Conditional logic

## Common Patterns

### Content Search
Simple substring search:
```dql
fetch logs, from:now() - 1h
| filter contains(content, "database")
| fields timestamp, content, status
```

Full-text phrase search:
```dql
fetch logs, from:now() - 1h
| filter matchesPhrase(content, "connection timeout")
| fields timestamp, content, process_group = dt.process_group.detected_name
```

### Error Rate Calculation
Calculate error rates over time:
```dql
fetch logs, from:now() - 2h
| summarize
    total_logs = count(),
    error_logs = countIf(status == "ERROR"),
    by: {time_bucket = bin(timestamp, 5m)}
| fieldsAdd error_rate = (error_logs * 100.0) / total_logs
| sort time_bucket asc
```

### Top Error Messages
Find most common errors:
```dql
fetch logs, from:now() - 24h
| filter status == "ERROR"
| summarize error_count = count(), by: {content}
| sort error_count desc
| limit 20
```

### Process Group-Specific Logs
Filter logs by process group:
```dql
fetch logs, from:now() - 1h
| fieldsAdd process_group = dt.process_group.detected_name
| filter process_group == "payment-service"
| filter status == "ERROR"
| fields timestamp, content, status
| sort timestamp desc
```

### Structured / JSON Log Parsing
Many applications emit JSON-formatted log lines. Use `parse` to extract fields instead of dumping raw content:

```dql
fetch logs, from:now() - 1h
| filter status == "ERROR"
| parse content, "JSON:log"
| fieldsAdd level = log[level], message = log[msg], error = log[error]
| fields timestamp, level, message, error
| sort timestamp desc
| limit 50
```

Aggregate by a parsed field:
```dql
fetch logs, from:now() - 4h
| filter status == "ERROR"
| parse content, "JSON:log"
| fieldsAdd message = log[msg]
| summarize error_count = count(), by: {message}
| sort error_count desc
| limit 20
```

**Notes:**
- `parse content, "JSON:log"` creates a record field `log` — access nested values with `log[key]`
- Filter logs with `contains()` **before** `parse` to reduce parsing overhead
- Works with any JSON-structured field, not just `content`

## Best Practices

1. **Always specify time ranges** - Use `from:now() - <duration>` to limit data
2. **Apply filters early** - Filter by severity and entity before aggregation
3. **Use appropriate search methods** - `contains()` for simple, `matchesPhrase()` for exact
4. **Limit results** - Add `| limit 100` to prevent overwhelming output
5. **Sort meaningfully** - Sort by timestamp for recent logs, by count for top errors
6. **Name entities** - Use `dt.process_group.detected_name` or `getNodeName()` for human-readable output
7. **Use time buckets for trends** - `bin(timestamp, 5m)` for time-series analysis

## Integration Points

- **Entity model**: Uses `dt.process_group.id` for service correlation
- **Time series**: Supports temporal analysis with `bin()` and time ranges
- **Content search**: Full-text search capabilities via `matchesPhrase()`
- **Aggregation**: Statistical analysis using `summarize` and conditional functions

## Limitations & Notes

- Log availability depends on OneAgent configuration and log ingestion
- Full-text search (`matchesPhrase`) may have performance implications on large datasets
- Entity names require proper OneAgent monitoring for resolution
- Time ranges should be reasonable (avoid unbounded queries)

## Related Skills

- **dt-dql-essentials** - Core DQL syntax and query structure for log queries
- **dt-obs-tracing** - Correlate logs with distributed traces using trace IDs
- **dt-obs-problems** - Correlate logs with DAVIS-detected problems
