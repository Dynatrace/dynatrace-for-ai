# DQL Query Optimization Guide

Comprehensive guide to writing efficient DQL queries with best practices, patterns, and performance tips.

## Table of Contents

- [Core Optimization Principles](#core-optimization-principles)
- [Optimal Command Order](#optimal-command-order)
- [Filter Optimization](#filter-optimization)
- [Aggregation Optimization](#aggregation-optimization)
- [Field Selection Optimization](#field-selection-optimization)
- [Time Optimization](#time-optimization)
- [Join Optimization](#join-optimization)
- [Common Anti-Patterns](#common-anti-patterns)
- [Performance Benchmarks](#performance-benchmarks)
- [Optimization Checklist](#optimization-checklist)
- [Query Profiling Tips](#query-profiling-tips)
- [Advanced Optimization Techniques](#advanced-optimization-techniques)

______________________________________________________________________

## Core Optimization Principles

### 1. Bucket Filters

Always apply bucket filters using the ``bucket`` parameter of the ``fetch``, ``timeseries`` or ``metrics`` command.

```dql
fetch logs, bucket:{"mybucket"}
```

Refine a given query using ``dtctl query --include-contributions --metadata=contributions -o json "THE_DQL_QUERY"``. The metadata section of the result indicates how much each bucket contributed via the ``matchedRecordsRatio`` field. Apply a bucket filter based on the contributions ratio per bucket.


---


### 2. Filter Early

Apply filters immediately after fetch to reduce data volume:

✅ **Good:**

```dql
fetch logs, from:now()-1h
| filter loglevel == "ERROR"
| summarize count(), by: {process}
```

❌ **Bad:**

```dql
fetch logs, from:now()-1h
| summarize count(), by: {process, loglevel}
| filter loglevel == "ERROR"
```

**Why it matters:**

- Reduces data processed by subsequent commands
- Lower memory usage
- Faster query execution
- Less data transferred

### 3. Specify Time Ranges

Always use the shortest necessary timeframe:

✅ **Good:**

```dql
fetch logs, from:now()-1h
| filter loglevel == "ERROR"
```

❌ **Bad:**

```dql
fetch logs, from:now()-30d  // 30 days when you need 1 hour
| filter loglevel == "ERROR"
```

**Impact:**

- Dramatically reduces initial data volume
- Faster fetch operations
- Lower resource usage
- More responsive queries

**Best practices:**

- Use `from:` parameter in all queries
- Match timeframe to actual need
- Consider retention policies

### 4. Select Only Needed Fields

Limit fields to reduce data transfer:

✅ **Good:**

```dql
fetch logs
| filter loglevel == "ERROR"
| fields timestamp, content, loglevel
| limit 100
```

❌ **Bad:**

```dql
fetch logs
| filter loglevel == "ERROR"
| limit 100
// Returns all fields (potentially 50+ columns)
```

**Benefits:**

- Smaller result sets
- Faster serialization
- Better UI performance
- Clearer intent

### 5. Limit Grouping Cardinality

Avoid grouping by high-cardinality fields:

✅ **Good:**

```dql
fetch logs, from:now()-1h
| summarize count(), by: {dt.process_group.detected_name}
```

❌ **Bad:**

```dql
fetch logs, from:now()-1h
| summarize count(), by: {user.id}  // Can have millions of unique values
```

**High-cardinality fields to avoid:**

- User IDs
- Session IDs
- Request IDs
- Trace IDs
- Unique identifiers

**Low-cardinality fields (good for grouping):**

- Severity levels (ERROR, WARN, INFO, etc.)
- Services (typically 10-100s)
- Hosts (typically 10-1000s)
- Status codes (limited set)
- Namespaces

### 6. Combine Aggregations

Single query more efficient than multiple:

✅ **Good:**

```dql
fetch logs
| summarize
    total = count(),
    errors = countIf(loglevel == "ERROR"),
    warnings = countIf(loglevel == "WARN")
```

❌ **Bad:**
```dql
fetch logs | summarize total = count()
```

```dql
fetch logs | filter loglevel == "ERROR" | summarize errors = count()
```

```dql
fetch logs | filter loglevel == "WARN" | summarize warnings = count()
```

**Benefits:**

- Single data scan
- Shared filtering and processing
- Consistent time windows
- Lower overall latency

### 7. Use Appropriate Time Bins

Match bin size to data volume and timeframe:

✅ **Good:**

```dql
// 24 hours: use 5-minute bins (288 data points)
fetch logs, from:now()-24h
| summarize count(), by: {bin(timestamp, 5m)}
```

❌ **Bad:**

```dql
// 30 days with 1-minute bins (43,200 data points - too many)
fetch logs, from:now()-30d
| summarize count(), by: {bin(timestamp, 1m)}
```

**Recommended bins:**

| Timeframe | Recommended Bin | Data Points |
| --------- | --------------- | ----------- |
| 1 hour    | 1m              | 60          |
| 6 hours   | 5m              | 72          |
| 24 hours  | 5m or 15m       | 288 or 96   |
| 7 days    | 1h              | 168         |
| 30 days   | 6h or 1d        | 120 or 30   |

______________________________________________________________________

## Optimal Command Order

Follow this order for best performance:

```
1. fetch (with time range)
2. filter (reduce data volume)
3. fieldsAdd (add calculated fields)
4. summarize (aggregate data)
5. filter (filter aggregated results)
6. sort (order results)
7. limit (restrict output)
```

**Example:**

```dql
fetch logs, from:now()-1h                              // 1. Fetch with time
| filter loglevel == "ERROR"                           // 2. Filter early
| fieldsAdd process = getNodeName(dt.smartscape.process)  // 3. Add fields
| summarize error_count = count(), by: {process}       // 4. Aggregate
| filter error_count > 10                              // 5. Filter aggregated
| sort error_count desc                                // 6. Sort
| limit 10                                             // 7. Limit
```

______________________________________________________________________

## Filter Optimization

### Use Specific Filters

More specific filters are more efficient:

✅ **Better:**

```dql
fetch logs
| filter loglevel == "ERROR" and http.status_code == 500
```

❌ **Less efficient:**

```dql
fetch logs
| filter contains(content, "error") and contains(content, "500")
```

### Equality vs Text Search

Simple equality checks faster than text search:

✅ **Faster:**

```dql
fetch logs
| filter loglevel == "ERROR"
| filter http.status_code == 500
```

❌ **Slower:**

```dql
fetch logs
| filter contains(loglevel, "ERROR")
| filter contains(http.status_code, "500")
```

### Use in() for Multiple Values

More efficient than multiple OR conditions:

✅ **Better:**

```dql
fetch logs
| filter in(loglevel, {"ERROR", "FATAL", "WARN"})
```

❌ **Less efficient:**

```dql
fetch logs
| filter loglevel == "ERROR" or loglevel == "FATAL" or loglevel == "WARN"
```

### Filter Before fieldsAdd

Calculate fields only on filtered data:

✅ **Good:**

```dql
fetch logs
| filter loglevel == "ERROR"
| fieldsAdd process = getNodeName(dt.smartscape.process)
```

❌ **Bad:**

```dql
fetch logs
| fieldsAdd process = getNodeName(dt.smartscape.process)
| filter loglevel == "ERROR"
```

______________________________________________________________________

## Aggregation Optimization

### Use countIf Instead of Multiple Filters

More efficient for conditional counts instead of issuing individual queries:

✅ **Good:**

```dql
fetch logs
| summarize
    total = count(),
    errors = countIf(loglevel == "ERROR"),
    warnings = countIf(loglevel == "WARN")
```

❌ **Bad:**

```dql
fetch logs | summarize total = count()
```

```dql
fetch logs | filter loglevel == "ERROR" | summarize errors = count()
```

```dql
fetch logs | filter loglevel == "WARN" | summarize warnings = count()
```

### Limit Grouping Dimensions

Fewer dimensions = better performance:

✅ **Good:**

```dql
fetch logs
| summarize count(), by: {loglevel}
```

❌ **Bad:**

```dql
fetch logs
| summarize count(), by: {
    loglevel,
    host,
    process,
    log.source,
    user.id  // Also high cardinality
}
```

### Avoid Unnecessary Grouping

If you don't need groups, don't group:

✅ **Good:**

```dql
fetch logs
| filter loglevel == "ERROR"
| summarize error_count = count()
```

❌ **Bad:**

```dql
fetch logs
| filter loglevel == "ERROR"
| summarize error_count = count(), by: {loglevel}
// Grouping by severity when already filtered to "ERROR"
```

______________________________________________________________________

## Field Selection Optimization

### Select Fields Early

Remove unnecessary fields early in pipeline:

✅ **Good:**

```dql
fetch logs
| fields timestamp, content, loglevel, http.status_code
| filter loglevel == "ERROR"
| summarize count(), by: {loglevel, http.status_code}
```

❌ **Bad:**

```dql-snippet
fetch logs
| filter loglevel == "ERROR"
| fields timestamp, content, loglevel, http.status_code
| summarize count(), by: {loglevel, http.status_code}
```

### Rename in fields vs fieldsAdd

Use `fields` for rename when possible:

✅ **Better:**

```dql
fetch logs
| fields timestamp, level = loglevel, message = content
```

❌ **Less efficient:**

```dql
fetch logs
| fieldsAdd level = loglevel, message = content
| fields timestamp, level, message
```

______________________________________________________________________

## Time Optimization

### Use Time Alignment

Align to time boundaries for caching:

✅ **Good:**

```dql
fetch logs, from:now()-1h@h, to:now()@h
| summarize count(), by: {bin(timestamp, 5m)}
```

**Benefits:**

- Better cache hit rates
- Reproducible time windows
- Cleaner time boundaries

### Choose Appropriate Timeframes

Match timeframe to use case:

| Use Case         | Timeframe |
| ---------------- | --------- |
| Recent errors    | 15m - 1h  |
| Hourly trends    | 24h       |
| Daily patterns   | 7d        |
| Weekly analysis  | 30d       |
| Long-term trends | 90d       |

### Avoid Overlapping Queries

Consolidate timeframes:

✅ **Good:**

```dql
fetch logs, from:now()-1h
| summarize
    recent = countIf(timestamp > now()-15m),
    total = count()
```

❌ **Bad:**

```dql
fetch logs, from:now()-15m | summarize recent = count()
```

```dql
fetch logs, from:now()-1h | summarize total = count()
```

______________________________________________________________________

## Join optimization

### Use the optimal join execution order

More efficient for queries with a low cardinality left side:

✅ **Good:**

```dql
// left join side timeseries query yields only 100 results while the right join side Smartscape query yields many records and a high cardinality. Thus it is optimal to instruct the join command to execute the left side first.
timeseries cpu=avg(dt.host.cpu.usage), by:{dt.smartscape.k8s_node}
| sort arrayAvg(cpu) desc
| limit 100 
| join [   
    smartscapeNodes K8S_NODE 
    | fields id, tags
], on:left[dt.smartscape.k8s_node]==right[id], executionOrder:leftFirst
| fields timeframe, interval, cpu, node=dt.smartscape.k8s_node, instance_type=right.tags[`beta.kubernetes.io/instance-type`]
```

❌ **Bad:**

```dql-snippet
// left join side log query yields a large result set. Thus it is not optimal to instruct the join command to execute the left side first.
fetch logs, bucket:{prod_logs}
| join [   
    smartscapeNodes K8S_NODE 
    | fields id, tags
], on:left[dt.smartscape.k8s_node]==right[id], executionOrder:leftFirst
| fields timeframe, interval, cpu, node=dt.smartscape.k8s_node, instance_type=right.tags[`beta.kubernetes.io/instance-type`]
| summarize countIf(loglevel=="ERROR"), by:instance_type
```

______________________________________________________________________

## Common Anti-Patterns

### Anti-Pattern 1: Late Filtering

❌ **Bad:**

```dql
fetch logs, from:now()-24h
| fieldsAdd process = getNodeName(dt.smartscape.process)
| summarize count(), by: {loglevel, process}
| filter loglevel == "ERROR"
```

✅ **Good:**

```dql
fetch logs, from:now()-24h
| filter loglevel == "ERROR"
| fieldsAdd process = getNodeName(dt.smartscape.process)
| summarize count(), by: {process}
```

### Anti-Pattern 2: Excessive Timeframe

❌ **Bad:**

```dql
fetch logs, from:now()-90d  // Need last hour
| filter loglevel == "ERROR"
| limit 100
```

✅ **Good:**

```dql
fetch logs, from:now()-1h
| filter loglevel == "ERROR"
| limit 100
```

### Anti-Pattern 3: High-Cardinality Grouping

❌ **Bad:**

```dql
fetch logs, from:now()-1h
| summarize count(), by: {trace_id}  // Millions of unique values
```

✅ **Good:**

```dql
fetch logs, from:now()-1h
| summarize count(), by: {service = getNodeName(dt.smartscape.service)}
```

### Anti-Pattern 4: Multiple Separate Queries

❌ **Bad:**

```dql
// Query 1
fetch logs | filter loglevel == "ERROR" | summarize errors = count()
```

```dql
// Query 2
fetch logs | filter loglevel == "WARN" | summarize warnings = count()
```

```dql
// Query 3
fetch logs | summarize total = count()
```

✅ **Good:**

```dql
fetch logs
| summarize
    total = count(),
    errors = countIf(loglevel == "ERROR"),
    warnings = countIf(loglevel == "WARN")
```

### Anti-Pattern 5: Unnecessary Field Calculations

❌ **Bad:**

```dql
fetch logs
| fieldsAdd
    process = getNodeName(dt.smartscape.process),
    host = getNodeName(dt.smartscape.host),
    service = getNodeName(dt.smartscape.service)
| filter loglevel == "ERROR"
| fields loglevel, process
// Calculated host and service but never used
```

✅ **Good:**

```dql
fetch logs
| filter loglevel == "ERROR"
| fieldsAdd process = getNodeName(dt.smartscape.process)
| fields loglevel, process
```

### Anti-Pattern 6: Excessive Time Bins

❌ **Bad:**

```dql
fetch logs, from:now()-30d
| summarize count(), by: {bin(timestamp, 1m)}
// 43,200 data points
```

✅ **Good:**

```dql
fetch logs, from:now()-30d
| summarize count(), by: {bin(timestamp, 1h)}
// 720 data points
```

### Anti-Pattern 7: Unnecessary entity joins 

❌ **Bad:**

```dql
fetch logs 
| filter getNodeName(dt.smartscape.k8s_cluster)=="prod_useast"
// using an unnecessary join while the kubernetes cluster name is already present on logs
```

✅ **Good:**

```dql
fetch logs 
| filter k8s.cluster.name=="prod_useast"
```

______________________________________________________________________

## Performance Benchmarks

### Impact of Early Filtering

| Pattern                | Relative Performance |
| ---------------------- | -------------------- |
| Filter after fetch     | Baseline (1x)        |
| Filter after fieldsAdd | 2-3x slower          |
| Filter after summarize | 5-10x slower         |

### Impact of Timeframe

| Timeframe | Data Volume | Query Time |
| --------- | ----------- | ---------- |
| 15m       | 1x          | 1x         |
| 1h        | 4x          | 3-4x       |
| 24h       | 96x         | 20-30x     |
| 7d        | 672x        | 100-150x   |

### Impact of Cardinality

| Cardinality        | Groups  | Performance Impact |
| ------------------ | ------- | ------------------ |
| Low (< 10)         | 5-10    | Negligible         |
| Medium (10-100)    | 20-50   | Acceptable         |
| High (100-1000)    | 200-500 | Noticeable         |
| Very High (> 1000) | 1000+   | Severe             |

______________________________________________________________________

## Optimization Checklist

Before running a query, check:

- [ ] Time range specified with `from:`?
- [ ] Time range as short as possible?
- [ ] Filters applied immediately after fetch?
- [ ] Grouping cardinality reasonable (< 1000 groups)?
- [ ] Only needed fields selected?
- [ ] Multiple aggregations combined in single query?
- [ ] Time bins appropriate for timeframe?
- [ ] Commands in optimal order?
- [ ] No high-cardinality dimensions in grouping?
- [ ] Results limited if displaying sample data?

______________________________________________________________________

## Query Profiling Tips

### Add Intermediate Counts

See data volume at each stage:

```dql-snippet
fetch logs, from:now()-1h
| summarize stage1_count = count()  // Check initial volume
```

```dql
fetch logs, from:now()-1h
| filter loglevel == "ERROR"
| summarize stage2_count = count()  // Check after filter
```

```dql
fetch logs, from:now()-1h
| filter loglevel == "ERROR"
| fieldsAdd process = getNodeName(dt.smartscape.process)
| summarize final_count = count(), by: {process}
```

### Test with Smaller Timeframes

Start small, then expand:

```dql
// Start with 5 minutes to test
fetch logs, from:now()-5m
| filter loglevel == "ERROR"
| summarize count(), by: {process}
```

```dql
// Then expand to full timeframe
fetch logs, from:now()-24h
| filter loglevel == "ERROR"
| summarize count(), by: {process}
```

### Use limit During Development

Limit results while testing:

```dql
fetch logs, from:now()-1h
| filter loglevel == "ERROR"
| limit 10  // Add during development, remove for production
```

______________________________________________________________________

## Advanced Optimization Techniques

### Pre-Aggregate with summarize

When doing multiple analyses on same data:

```dql
fetch logs, from:now()-1h
| summarize
    total = count(),
    errors = countIf(loglevel == "ERROR"),
    avg_size = avg(response_size),
    by: {bin(timestamp, 5m), service = getNodeName(dt.smartscape.service)}
// Now multiple analyses can use this aggregated data
```

### Use fieldsAdd for Reusable Calculations

Calculate once, use multiple times:

```dql
fetch logs
| fieldsAdd duration_ms = duration / 1000000
| filter duration_ms > 1000
| summarize
    slow_requests = count(),
    avg_duration = avg(duration_ms),
    p95_duration = percentile(duration_ms, 95)
```

### Combine Filters within a single command

Multiple conditions in one filter:

✅ **Good:**

```dql
fetch logs
| filter loglevel == "ERROR" and http.status_code >= 500 and response_time > 1000
```

❌ **Less readable**

```dql
fetch logs
| filter loglevel == "ERROR"
| filter http.status_code >= 500
| filter response_time > 1000
```
