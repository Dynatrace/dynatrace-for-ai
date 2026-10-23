---
name: dt-obs-tracing
description: >-
  Distributed traces, spans, service dependencies, and request flow analysis. Use when
  investigating span-level details, failures, performance bottlenecks, or trace correlation.
  Trigger: "trace analysis", "slow requests", "failed spans", "service dependencies",
  "distributed trace", "span details", "HTTP status codes in traces", "database query spans",
  "messaging spans", "gRPC calls", "Lambda cold starts", "trace ID lookup",
  "exception analysis", "correlate logs and traces", "request attributes".
  Do NOT use for explaining existing queries, product documentation or configuration questions,
  service-level RED metrics (use dt-obs-services), log searching (use dt-obs-logs),
  or problem analysis (use dt-obs-problems).
license: Apache-2.0
---

# Application Tracing Skill

## Overview

Distributed traces in Dynatrace consist of spans - building blocks representing units of work. With Traces in Grail, every span is accessible via DQL with full-text searchability on all attributes. This skill covers trace fundamentals, common analysis patterns, and span-type specific queries.

---

## Use Cases

### 1. Investigate Slow Requests
- **Goal:** Find and diagnose requests exceeding a latency threshold
- **Trigger:** "slow requests", "high latency", "p99 response time", "find traces over 5 seconds"
- **Done:** List of slow traces with duration, endpoint, service, and trace IDs for drilldown

### 2. Analyze Request Failures
- **Goal:** Identify failed requests, failure reasons, and exception patterns
- **Trigger:** "failed spans", "HTTP 500 errors", "exception analysis", "failure rate by service"
- **Done:** Failure breakdown by reason (HTTP code, exception, gRPC status) with exemplar traces

### 3. Map Service Dependencies
- **Goal:** Understand service-to-service communication patterns and external API calls
- **Trigger:** "service dependencies", "what services does X call", "outgoing HTTP calls"
- **Done:** Dependency map showing call counts, latency, and error rates between services

---

## Core Concepts

### Understanding Traces and Spans

**Spans** represent logical units of work in distributed traces:
- HTTP requests, RPC calls, database operations
- Messaging system interactions
- Internal function invocations
- Custom instrumentation points

**Span kinds**:
- `span.kind: server` - Incoming call to a service
- `span.kind: client` - Outgoing call from a service
- `span.kind: consumer` - Incoming message consumption call to a service
- `span.kind: producer` - Outgoing message production call from a service
- `span.kind: internal` - Internal operation within a service

**Root spans**: A request root span (`request.is_root_span == true`) represents an incoming call to a service. Use this to analyze end-to-end request performance.

### Key Trace Attributes

Essential attributes for trace analysis:

| Attribute | Description |
|-----------|-------------|
| `trace.id` | Unique trace identifier |
| `span.id` | Unique span identifier |
| `span.parent_id` | Parent span ID (null for root spans) |
| `request.is_root_span` | Boolean, true for request entry points |
| `request.is_failed` | Boolean, true if request failed |
| `duration` | Span duration in nanoseconds |
| `span.timing.cpu` | Overall CPU time of the span (stable) |
| `span.timing.cpu_self` | CPU time excluding child spans (stable) |
| `dt.smartscape.service` | Service Smartscape node ID |
| `dt.service.name` | Dynatrace service name derived from service detection rules. It is equal to the Smartscape service node name.  |
| `endpoint.name` | Endpoint/route name |

### Service Context

Spans reference services via Smartscape node IDs and the detected service name `dt.service.name` which is also present on every span.

```dql
fetch spans
| summarize spans=count(), by: { dt.smartscape.service, dt.service.name }
```

**Node functions**:
- `getNodeName(dt.smartscape.service)` - Adds `dt.smartscape.service.name` field with the human-readable service name
- `getNodeField(dt.smartscape.service, "attribute_name")` - Access specific node attributes

**📖 Learn more**: See [Entity Lookups](references/entity-lookups.md) for advanced entity selectors, infrastructure correlation, and hardware analysis.

### Sampling and Extrapolation

One span can represent multiple real operations due to:
- **Aggregation**: Multiple operations in one span (`aggregation.count`)
- **ATM (Adaptive Traffic Management)**: Head-based sampling by agent
- **ALR (Adaptive Load Reduction)**: Server-side sampling
- **Read Sampling**: Query-time sampling via `samplingRatio` parameter

**When to extrapolate**: Always extrapolate when counting actual operations (not just spans). Use the multiplicity factor:

```dql
fetch spans
| fieldsAdd sampling.probability = (power(2, 56) - coalesce(sampling.threshold, 0)) * power(2, -56)
| fieldsAdd sampling.multiplicity = 1 / sampling.probability
| fieldsAdd multiplicity = coalesce(sampling.multiplicity, 1)
                         * coalesce(aggregation.count, 1)
                         * dt.system.sampling_ratio
| summarize operation_count = sum(multiplicity)
```

**📖 Learn more**: See [Sampling and Extrapolation](references/sampling-extrapolation.md) for detailed formulas and examples.

## Common Query Patterns

### Basic Span Access

Fetch spans and explore by type:

```dql
fetch spans | limit 1
```

Explore spans by function and type:

```dql
fetch spans
| summarize count(), by: { span.kind, code.namespace, code.function }
```

### Request Root Filtering

List request root spans (incoming service calls):

```dql
fetch spans
| filter request.is_root_span == true
| fields trace.id, span.id, start_time, response_time = duration, endpoint.name
| limit 100
```

### Service Performance Summary

Analyze service performance with error rates:

```dql
fetch spans
| filter request.is_root_span == true
| summarize
    total_requests = count(),
    failed_requests = countIf(request.is_failed == true),
    avg_duration = avg(duration),
    p95_duration = percentile(duration, 95),
    by: {dt.service.name}
| fieldsAdd error_rate = (failed_requests * 100.0) / total_requests
| sort error_rate desc
```

### Trace ID Lookup

Find all spans in a specific trace:

```dql
fetch spans
| filter trace.id == toUid("abc123def456")
| fields span.name, duration, dt.service.name
```

## Performance Analysis

### Response Time Percentiles

Calculate percentiles by endpoint:

```dql
fetch spans
| filter request.is_root_span == true
| summarize {
    requests=count(),
    avg_duration=avg(duration),
    p95=percentile(duration, 95),
    p99=percentile(duration, 99)
  }, by: { endpoint.name }
| sort p99 desc
```

**💡 Best practice**: Use percentiles (p95, p99) over averages for performance insights.

### Slow Trace Detection

Find requests exceeding a threshold:

```dql
fetch spans, from:now() - 2h
| filter request.is_root_span == true
| filter duration > 5s
| fields trace.id, span.name, dt.service.name, duration
| sort duration desc
| limit 50
```

### Duration Buckets with Exemplars

```dql
fetch spans, from:now() - 24h
| filter http.route == "/api/v1/storage/findByISBN"
| summarize {
    spans=count(),
    trace=takeAny(record(start_time, trace.id))
  }, by: { bin(duration, 10ms) }
| fields `bin(duration, 10ms)`, spans, trace.id=trace[trace.id], start_time=trace[start_time]
```

### Performance Timeseries

Extract response time as timeseries:

```dql
fetch spans, from:now() - 24h
| filter request.is_root_span == true
| makeTimeseries {
    requests=count(),
    avg_duration=avg(duration),
    p95=percentile(duration, 95),
    p99=percentile(duration, 99)
  }, by: { endpoint.name }
```

**📖 Learn more**: See [Performance Analysis](references/performance-analysis.md) for advanced patterns and timeseries techniques.

## Failure Investigation

### Failed Request Summary

Summarize failures by service:

```dql
fetch spans
| filter request.is_root_span == true
| summarize
    total = count(),
    failed = countIf(request.is_failed == true),
  by: { dt.service.name }
| fieldsAdd failure_rate = (failed * 100.0) / total
| sort failure_rate desc
```

### Failure Reason Analysis

Breakdown by failure detection reason:

```dql
fetch spans
| filter request.is_failed == true and isNotNull(dt.failure_detection.results)
| expand dt.failure_detection.results
| summarize count(), by: { dt.failure_detection.results[reason] }
```

**Failure reasons**:
- `http_code` - HTTP response code triggered failure
- `grpc_code` - gRPC status code triggered failure
- `exception` - Exception caused failure
- `span_status` - Span status indicated failure
- `custom_rule` - Custom failure detection rule matched

### HTTP Code Failures

Find failures by HTTP status code:

```dql
fetch spans
| filter request.is_failed == true
| filter iAny(dt.failure_detection.results[][reason] == "http_code")
| summarize count(), by: { http.response.status_code, endpoint.name }
| sort `count()` desc
```

### Recent Failed Requests

List recent failures with details:

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

**📖 Learn more**: See [Failure Detection](references/failure-detection.md) for exception analysis and custom rule investigation.

## Service Dependencies

### Service-to-Service Analysis

Analyze service communication patterns:

```dql
fetch spans, from:now() - 1h
| filter isNotNull(server.address)
| fieldsAdd
    remote_side = server.address
| summarize
    call_count = count(),
    avg_duration = avg(duration),
    by: {dt.service.name, remote_side}
| sort call_count desc
```

### Outgoing HTTP Calls

Identify external API dependencies:

```dql
fetch spans
| filter span.kind == "client" and isNotNull(http.request.method)
| summarize
    calls = count(),
    avg_latency = avg(duration),
    p99_latency = percentile(duration, 99),
  by: { dt.service.name, server.address, server.port }
| sort calls desc
```

## Trace Aggregation

### Complete Trace Analysis

Aggregate all spans in a trace to understand full request flow:

```dql
fetch spans, from:now() - 30m
| summarize {
    spans = count(),
    client_spans = countIf(span.kind == "client"),

    // Endpoints involved in the trace
    endpoints = toString(arrayRemoveNulls(collectDistinct(endpoint.name))),

    // Extract the first request root in the trace
    trace_root = takeMin(record(
        root_detection_helper = coalesce(
            if(request.is_root_span, 1),
            if(isNull(span.parent_id), 2),
            3),
        start_time, endpoint.name, duration
      ))
}, by: { trace.id }

| fieldsFlatten trace_root
| fieldsRemove trace_root.root_detection_helper, trace_root

| fields
    start_time = trace_root.start_time,
    endpoint = trace_root.endpoint.name,
    response_time = trace_root.duration,
    spans,
    client_spans,
    endpoints,
    trace.id
| sort start_time
| limit 100
```

**Root detection strategy**: Use `takeMin(record(...))` with a detection helper to reliably find the root request:
1. Priority 1: Spans with `request.is_root_span == true`
2. Priority 2: Spans without parent (root spans)
3. Priority 3: All other spans

### Multi-Service Traces

Find traces spanning multiple services:

```dql
fetch spans, from:now() - 1h
| summarize {
    services = collectDistinct(dt.service.name),
    trace_root = takeMin(record(root_detection_helper = coalesce(if(request.is_root_span, 1), 2), endpoint.name))
}, by: { trace.id }
| fieldsAdd service_count = arraySize(services)
| filter service_count > 1
| fields endpoint = trace_root[endpoint.name], service_count, services = toString(services), trace.id
| sort service_count desc
| limit 50
```

## Request-Level Analysis

### Request Attributes

Access custom request attributes captured by OneAgent on request root spans:

```dql
fetch spans
| filter request.is_root_span == true
| filter isNotNull(request_attribute.PaidAmount)
| makeTimeseries sum(request_attribute.PaidAmount)
```

**Field patterns**: `request_attribute.<name>`, `captured_attribute.<name>` (always arrays)

→ [Request Attributes](references/request-attributes.md) — full patterns for request attributes, captured attributes, and request ID aggregation

## Span Types

| Span Type | Detection | Key Fields | Reference |
|-----------|-----------|------------|-----------|
| HTTP server (incoming) | `span.kind == "server" and isNotNull(http.request.method)` | `http.route`, `http.request.method`, `http.response.status_code` | [http-spans.md](references/http-spans.md) |
| HTTP client (outgoing) | `span.kind == "client" and isNotNull(http.request.method)` | `server.address`, `server.port` | [http-spans.md](references/http-spans.md) |
| Database | `span.kind == "client" and isNotNull(db.system)` | `db.system`, `db.namespace`, `db.query.text` | [database-spans.md](references/database-spans.md) |
| Messaging | `isNotNull(messaging.system)` | `messaging.system`, `messaging.destination.name`, `messaging.operation.type` | [messaging-spans.md](references/messaging-spans.md) |
| RPC / gRPC | `isNotNull(rpc.system)` | `rpc.system`, `rpc.service`, `rpc.method`, `rpc.grpc.status_code` | [rpc-spans.md](references/rpc-spans.md) |
| Serverless / FaaS | `isNotNull(faas.name) and span.kind == "server"` | `faas.name`, `faas.trigger.type`, `cloud.provider` | [serverless-spans.md](references/serverless-spans.md) |

**⚠️ Database spans**: Can be aggregated (one span = multiple calls). Always use `aggregation.count` extrapolation for accurate operation counts.

**📖 Detailed patterns per span type:** See the reference files above.

## Advanced Topics

### Exception Analysis

Exceptions are stored as `span.events` within spans:

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

**💡 Tip**: Use `iAny()` to check conditions within span event arrays.

→ [Logs Correlation](references/logs-correlation.md) — joining logs and traces, filtering traces by log content
→ [Network Analysis](references/networking-analysis.md) — client IPs, DNS resolution, subnet analysis

## Best Practices

| Area | Rule |
|------|------|
| **Filtering** | Apply `request.is_root_span == true` and endpoint filters first |
| **Sampling** | Use `samplingRatio` (e.g., `100` = read 1%) for performance |
| **Percentiles** | Use p95/p99 over averages for performance analysis |
| **Root spans** | Use `request.is_root_span == true` for end-to-end analysis |
| **Trace grouping** | Group by `trace.id` for complete trace metrics |
| **Request grouping** | Group by `request.id` for OneAgent-only request metrics |
| **Extrapolation** | Always apply multiplicity for accurate operation counts |
| **Exemplars** | Use `takeAny(record(start_time, trace.id))` to enable UI drilldown |

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Duration values seem wrong (too large) | `duration` is in nanoseconds, not milliseconds | Divide by `1000000` or compare with `5s` (DQL duration literal) |
| Span counts don't match expected request volume | Sampling or aggregation not accounted for | Use multiplicity extrapolation — see Sampling and Extrapolation reference |
| `getNodeName(dt.smartscape.service)` returns null | Service not yet resolved or OneAgent not monitoring | Verify OneAgent monitors the service; entity resolution may have a short delay |
| `request.is_root_span` filter returns nothing | Querying OpenTelemetry-only traces without OneAgent | Use `isNull(span.parent_id)` as fallback for root span detection |
| `trace.id` filter returns no results | Trace ID not converted to UID format | Use `filter trace.id == toUid("abc123...")` for string-based trace IDs |
| Database span counts are too low | Database spans are aggregated (one span = N calls) | Always use `aggregation.count` extrapolation for database operation counts |

## Related Skills

- **dt-dql-essentials** — Core DQL syntax for querying trace data
- **dt-app-dashboards** — Embed trace queries in dashboards
- **dt-migration** — Smartscape entity model and relationship navigation

---

## References

Detailed documentation for specific topics:

- **[Performance Analysis](references/performance-analysis.md)** - Advanced timeseries, duration buckets, endpoint ranking
- **[Failure Detection](references/failure-detection.md)** - Failure reasons, exception investigation, custom rules
- **[Sampling and Extrapolation](references/sampling-extrapolation.md)** - Multiplicity calculation, database extrapolation
- **[Request Attributes](references/request-attributes.md)** - Request attributes, captured attributes, request ID aggregation
- **[Entity Lookups](references/entity-lookups.md)** - Advanced node lookups, infrastructure correlation, hardware analysis
- **[HTTP Span Analysis](references/http-spans.md)** - Status codes, payload analysis, client IPs
- **[Database Span Analysis](references/database-spans.md)** - Extrapolated counts, slow queries, statement analysis
- **[Messaging Span Analysis](references/messaging-spans.md)** - Kafka, RabbitMQ, SQS throughput and latency
- **[RPC Span Analysis](references/rpc-spans.md)** - gRPC, SOAP, service dependencies
- **[Serverless Span Analysis](references/serverless-spans.md)** - Lambda, Azure Functions, cold start analysis
- **[Logs Correlation](references/logs-correlation.md)** - Joining logs and traces, correlation patterns
- **[Network Analysis](references/networking-analysis.md)** - IP addresses, DNS resolution, communication mapping
