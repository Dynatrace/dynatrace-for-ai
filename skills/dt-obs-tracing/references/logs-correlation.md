# Logs and Traces Correlation

Logs can be enriched with `trace_id` and `span_id` to enable correlation with distributed traces. OneAgent can automatically enrich logs with trace context.

## Finding Logs with Trace Context

### Logs with Trace IDs

List logs containing trace context:

```dql
fetch logs, from:now() - 2h
| filter isNotNull(trace_id)
| limit 10
```

## Filtering Traces by Log Content

### Find Traces from Log Search

Find traces containing specific log messages:

```dql
fetch spans, from:now() - 30m
| filter trace.id in [
    fetch logs
    | filter isNotNull(trace_id)
    | filter contains(content, "books returned")
    | fields toUid(trace_id)
]
| limit 1
```

**Note**: Subqueries in `in` statements have size limits. If the subquery result is too large, you'll get an `IN_KEYWORD_TABLE_SIZE` DQL error.

### Analyze Spans Emitting Specific Logs

Find performance of spans that emitted logs with specific content:

```dql
fetch spans, from:now() - 30m
| filter span.id in [
    fetch logs
    | filter isNotNull(span_id)
    | filter contains(content, "J. K. Rowling")
    | fields toUid(span_id)
]

// Pick span name or code location
| fieldsAdd name = coalesce(span.name, concat(code.namespace, ".", code.function))

| summarize {
    count(),
    avg(duration),
    p99=percentile(duration, 99),
    trace.id=takeAny(trace.id)
  }, by: { k8s.pod.name, name }
```

## Joining Spans and Logs

### Basic Join

Join spans with logs on trace ID:

```dql
fetch spans, from:now() - 30m
| join [ fetch logs | fieldsAdd trace.id = toUid(trace_id) ]
  , on: { trace.id }
  , fields: { content, loglevel }
| fields start_time, trace.id, span.id, code=concat(code.namespace, ".", code.function), loglevel, content
| limit 100
```

### Left-First Execution

Control join execution order for performance:

```dql
fetch spans, from:now() - 30m
| join [ fetch logs | fieldsAdd trace.id = toUid(trace_id) ]
  , on:{ trace.id }
  , fields: { content, loglevel }
  , executionOrder:leftFirst
| fields start_time, trace.id, span.id, code=concat(code.namespace, ".", code.function), loglevel, content
| limit 100
```

## Correlation Patterns

### Logs for Failed Requests

Find logs associated with failed requests:

```dql
fetch logs, from:now() - 1h
| filter isNotNull(trace_id)
| filter trace_id in [
    fetch spans
    | filter request.is_root_span == true
    | filter request.is_failed == true
    | fields toString(trace.id)
]
| fields timestamp, loglevel, content, trace_id
| sort timestamp desc
| limit 100
```

### Exception Logs with Trace Context

Correlate error logs with their traces:

```dql
fetch logs, from:now() - 1h
| filter loglevel == "ERROR"
| filter isNotNull(trace_id)
| fieldsAdd trace_id_uid = toUid(trace_id)
| join [
    fetch spans
    | filter request.is_root_span == true
    | fields trace.id, endpoint.name, duration
  ]
  , on: { left[trace_id_uid] == right[trace.id] }
  , fields: { endpoint.name, duration }
| fields timestamp, content, endpoint.name, duration, trace_id
| sort timestamp desc
| limit 50
```

## Best Practices

- **Convert trace_id** from string to UID using `toUid()` when joining
- **Be aware of subquery limits** - large `in` subqueries may fail with `IN_KEYWORD_TABLE_SIZE` error
- **Use `executionOrder:leftFirst`** to optimize join performance when left side is smaller
- **Filter logs early** - apply log filters before joining with spans
- **Include `trace_id` and `span_id`** in log output for troubleshooting
- **OneAgent auto-enrichment** - configure OneAgent to automatically add trace context to logs

## Related Topics

- [Failure Detection](failure-detection.md) - Investigate failures using logs and traces

---

**← Back to**: [Application Tracing Skill](../SKILL.md)
