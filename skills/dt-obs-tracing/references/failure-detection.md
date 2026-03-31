# Failure Detection Analysis

Dynatrace applies failure detection rules to identify failed requests. Use these queries to analyze failure patterns and investigate root causes.

## Key Attributes

- `request.is_failed`: true if request is considered failed
- `dt.failure_detection.results[]`: array of detection results
- `dt.failure_detection.results[].reason`: why failure was detected
- `dt.failure_detection.results[].verdict`: failure or success

### Failure Reasons

| Reason | Description |
|--------|-------------|
| `http_code` | HTTP response code triggered failure |
| `grpc_code` | gRPC status code triggered failure |
| `exception` | Exception caused failure |
| `span_status` | Span status indicated failure |
| `custom_rule` | Custom failure detection rule matched |

## Failure Overview

### Failed Request Summary

```dql
fetch spans
| filter request.is_root_span == true
| summarize
    total = count(),
    failed = countIf(request.is_failed == true),
  by: { getNodeName(dt.smartscape.service) }
| fieldsAdd failure_rate = (failed * 100.0) / total
| sort failure_rate desc
```

### Failures by Endpoint

```dql
fetch spans
| filter request.is_root_span == true and request.is_failed == true
| summarize failures = count(), by: { endpoint.name, http.route }
| sort failures desc
```

## Failure Reason Analysis

### Breakdown by Reason

```dql
fetch spans
| filter request.is_failed == true and isNotNull(dt.failure_detection.results)
| expand dt.failure_detection.results
| summarize count(), by: { dt.failure_detection.results[reason] }
```

### HTTP Code Failures

```dql
fetch spans
| filter request.is_failed == true
| filter iAny(dt.failure_detection.results[][reason] == "http_code")
| summarize count(), by: { http.response.status_code, endpoint.name }
| sort `count()` desc
```

### Exception-Based Failures

```dql
fetch spans
| filter request.is_failed == true
| filter iAny(dt.failure_detection.results[][reason] == "exception")
| expand span.events
| filter span.events[span_event.name] == "exception"
| summarize count(), by: { span.events[exception.type] }
```

## Failure Patterns

### Failure Rate Over Time

```dql
fetch spans
| filter request.is_root_span == true
| makeTimeseries
    total = count(),
    failed = countIf(request.is_failed == true),
  by: { getNodeName(dt.smartscape.service) }
```

### Correlate Failures with Response Codes

```dql
fetch spans
| filter request.is_root_span == true
| summarize
    total = count(),
    failed = countIf(request.is_failed == true),
  by: { http.response.status_code }
| sort failed desc
```

## Custom Rule Investigation

### Custom Rule Matches

```dql
fetch spans
| filter request.is_failed == true
| filter iAny(dt.failure_detection.results[][reason] == "custom_rule")
| expand dt.failure_detection.results
| filter dt.failure_detection.results[reason] == "custom_rule"
| summarize count(), by: { dt.failure_detection.results[custom_rule_name] }
```

## Failure Investigation

### Recent Failed Requests

```dql
fetch spans
| filter request.is_root_span == true and request.is_failed == true
| fields
    start_time,
    trace.id,
    endpoint.name,
    http.response.status_code,
    duration
| sort start_time desc
| limit 100
```

### Failed Requests with Verdict Details

```dql
fetch spans
| filter request.is_failed == true
| expand dt.failure_detection.results
| fields
    trace.id,
    endpoint.name,
    reason = dt.failure_detection.results[reason],
    verdict = dt.failure_detection.results[verdict]
| limit 50
```

## Exception Analysis

Exceptions in distributed traces are stored as `span.events` within individual spans. DQL provides powerful ways to query, filter, and analyze exceptions including full-text search on messages and stack traces.

### Finding Exceptions

Filter for spans containing exceptions:

```dql
fetch spans
| filter iAny(span.events[][span_event.name] == "exception")
| limit 100
```

### Exclude Specific Exceptions

Filter out known exceptions:

```dql
fetch spans
| filter iAny(span.events[][span_event.name] == "exception")
| filter iAny(not contains(span.events[][exception.message], "404"))
| expand span.events
| fields span.events
| fieldsFlatten span.events
| fieldsRemove span.events
| limit 1
```

### Stack Trace Analysis

Search for specific patterns in stack traces:

```dql
fetch spans
| filter iAny(contains(span.events[][exception.stack_trace], "invoke"))
| expand span.events
| fields span.events
| fieldsFlatten span.events
| fieldsRemove span.events
| limit 1
```

### Exception Aggregations

Count by exception type:

```dql
fetch spans
| filter iAny(span.events[][span_event.name] == "exception")
| expand span.events
| fieldsFlatten span.events, fields: { exception.type }
| summarize count(), by: { exception.type }
```

### Exception Count with Trace Exemplars

Include example trace IDs for investigation:

```dql
fetch spans
| filter iAny(span.events[][span_event.name] == "exception")
| expand span.events
| fieldsFlatten span.events, fields: { exception.type }
| summarize {
    count(),
    trace=takeAny(record(start_time, trace.id))
  }, by: { exception.type }
| fields exception.type, `count()`, trace.id=trace[trace.id], start_time=trace[start_time]
```

### Exception Timeseries

Chart exception frequency over time:

```dql
fetch spans, from:now() - 24h
| filter iAny(span.events[][span_event.name] == "exception")
| expand span.events
| fieldsFlatten span.events, fields: { exception.type }
| makeTimeseries count(), by: { exception.type }
```

### Parsing Exception Messages

Extract structured data from exception messages:

```dql
fetch spans, from:now() - 2h
| filter iAny(contains(span.events[][exception.message], "Book in Storage is not found by isbn"))
| expand span.events
| fields span.events
| fieldsFlatten span.events
| fieldsRemove span.events
// Parse code and ISBN from message like: "404 NOT_FOUND \"Book in Storage is not found by isbn: 9999999998823\""
| parse span.events.exception.message, "INT:code LD 'not found by isbn:' LD:isbn '\"'"
| summarize count(), by: { isbn, code }
| sort `count()` desc
| limit 10
```

## Best Practices

- **Use `iAny()`** to check for conditions within failure detection arrays and span events
- **Expand and flatten** `dt.failure_detection.results` and `span.events` to access attributes
- **Full-text search** works on both `exception.message` and `exception.stack_trace`
- **Include trace exemplars** using `takeAny(record(start_time, trace.id))` for drilldown
- **Parse exception messages** with DQL `parse` command to extract structured information
- **Monitor failure rates** by calculating percentage: `(failed_requests / total_requests) * 100`

---

**← Back to**: [Application Tracing Skill](../SKILL.md)
