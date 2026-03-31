# Request Attributes and Request-Level Analysis

Query request attributes, captured attributes, and aggregate spans by request.

## Overview

Requests in Dynatrace are represented by spans marked as request roots (`request.is_root_span: true`). These represent incoming calls to services. Request attributes and captured attributes provide custom metadata for request-level analysis, while `request.id` enables aggregation of all spans within a single request.

## Request Root Spans

### List Request Roots

Fetch individual request root spans:

```dql
fetch spans
| filter request.is_root_span == true
| fields trace.id, span.id, start_time, response_time = duration, endpoint.name
| limit 100

```

### Failed Request Analysis

Chart failed requests over time:

```dql
fetch spans, from:now() - 7d
| filter request.is_root_span == true
| makeTimeseries {
    failed_requests=countIf(request.is_failed == true)
  }, by: {endpoint.name}

```

Filter for specific endpoint:

```dql
fetch spans
| filter request.is_root_span == true
| filter endpoint.name == "/api/v1/payment"
| filter request.is_failed == true
| fields trace.id, endpoint.name, duration, start_time
| limit 100

```

## Request Aggregation

Aggregate all spans belonging to a request using `request.id`. All spans in a request carry this ID.

**Note**: `request.id` is only available for OneAgent-based traces, not API-ingested traces.

### Aggregated Request Metrics

Calculate metrics across all spans in each request:

```dql
fetch spans
| filter isNotNull(request.id)
| summarize {
    spans = count(),
    client_spans = countIf(span.kind == "client"),
    span_events = sum(arraySize(span.events)),

    // Select the request root span
    request_root = takeMin(record(
        root_detection_helper = coalesce(if(request.is_root_span, 1), 2),
        start_time, endpoint.name, duration
      ))
}, by: { trace.id, request.id }

// Reset to NULL if root not found
| fieldsAdd request_root=if(request_root[root_detection_helper] < 2, request_root)
| fieldsFlatten request_root
| fieldsRemove request_root.root_detection_helper, request_root

| fields
    start_time = request_root.start_time,
    endpoint = request_root.endpoint.name,
    response_time = request_root.duration,
    spans,
    client_spans,
    span_events,
    trace.id

| limit 100

```

This query:

- Counts total spans per request
- Counts outgoing calls (client spans)
- Sums span events (e.g., exceptions)
- Extracts request root span details

## Request Performance by Endpoint

### Response Time Statistics

Analyze endpoint performance:

```dql
fetch spans
| filter request.is_root_span == true
| summarize {
    requests=count(),
    avg_duration=avg(duration),
    p95=percentile(duration, 95),
    p99=percentile(duration, 99),
    failed=countIf(request.is_failed == true)
  }, by: { endpoint.name }
| fieldsAdd failure_rate = (failed * 100.0) / requests
| sort p99 desc

```

### Service Request Breakdown

Requests by service and endpoint:

```dql
fetch spans
| filter request.is_root_span == true
| fieldsAdd getNodeName(dt.smartscape.service)
| summarize {
    requests=count(),
    failed=countIf(request.is_failed == true),
    avg_duration=avg(duration)
  }, by: { dt.smartscape.service.name, endpoint.name }
| fieldsAdd failure_rate = (failed * 100.0) / requests
| sort requests desc

```

## Request Attributes

Request attributes appear on request root spans with the key `request_attribute.<name>`:

```dql
fetch spans
| filter request.is_root_span == true
| filter isNotNull(request_attribute.PaidAmount)
| makeTimeseries sum(request_attribute.PaidAmount)

```

For attributes with special characters, use backticks:

```dql
fetch spans
| filter isNotNull(`request_attribute.My Customer ID`)

```

## Captured Attributes

Attributes captured from method parameters appear as `captured_attribute.<name>` (always as arrays):

```dql
fetch spans
| filter isNotNull(captured_attribute.BookID_purchased)
| fields trace.id, span.id, code.namespace, code.function, captured_attribute.BookID_purchased
| limit 1

```

## Best Practices

- **Filter for request roots** using `request.is_root_span == true`
- **Check `request.is_failed`** to identify failed requests
- **Use `request.id`** to aggregate spans within a single request (OneAgent traces only)
- **Use `takeMin(record(...))`** with detection helper to reliably extract request root from aggregation
- **Monitor failure rates** by calculating percentage: `(failed_requests / total_requests) * 100`
- **Include endpoint name** for meaningful breakdowns
- **Request attributes** data types depend on configuration ("All values" creates arrays)
