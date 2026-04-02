# HTTP Span Analysis

HTTP spans capture web requests and API calls. Server spans represent incoming requests; client spans represent outgoing calls to external services.

## Key Attributes

| Attribute | Description |
|-----------|-------------|
| `http.request.method` | GET, POST, PUT, DELETE, etc. |
| `http.response.status_code` | Response code (200, 404, 500, etc.) |
| `http.route` | URL path template (server side) |
| `url.path` | Actual URL path |
| `url.full` | Complete URL (client side) |
| `http.request.body.size` | Request payload bytes |
| `http.response.body.size` | Response payload bytes |
| `http.request.header.__key__` | Request headers (e.g., `http.request.header.content-type`) |
| `http.request.parameter.__key__` | Query/body parameters (e.g., `http.request.parameter.id`) |
| `http.response.header.__key__` | Response headers |

## Server-Side Analysis

### Incoming Request Volume

```dql
fetch spans
| filter span.kind == "server" and isNotNull(http.request.method)
| summarize
    requests = count(),
    avg_duration = avg(duration),
  by: { http.request.method, http.route }
| sort requests desc
```

### Response Code Distribution

```dql
fetch spans
| filter span.kind == "server" and isNotNull(http.response.status_code)
| summarize count(), by: { http.response.status_code }
| sort http.response.status_code asc
```

### Error Rates by Endpoint

```dql
fetch spans
| filter span.kind == "server" and isNotNull(http.route)
| summarize
    total = count(),
    errors = countIf(http.response.status_code >= 400),
  by: { http.route }
| fieldsAdd error_rate = (errors * 100.0) / total
| sort error_rate desc
```

### 5xx Server Errors

```dql
fetch spans
| filter span.kind == "server" and http.response.status_code >= 500
| summarize
    errors = count(),
    example_trace = takeAny(trace.id),
  by: { http.route, http.response.status_code }
| sort errors desc
```

## Client-Side Analysis

### Outgoing HTTP Calls

```dql
fetch spans
| filter span.kind == "client" and isNotNull(http.request.method)
| summarize
    calls = count(),
    avg_duration = avg(duration),
  by: { server.address, http.request.method }
| sort calls desc
```

### External API Dependencies

```dql
fetch spans
| filter span.kind == "client" and isNotNull(url.full)
| fieldsAdd caller_service = getNodeName(dt.smartscape.service)
| summarize
    calls = count(),
    avg_latency = avg(duration),
    p99_latency = percentile(duration, 99),
  by: { caller_service, server.address, server.port }
| sort calls desc
```

### Failed Outgoing Calls

```dql
fetch spans
| filter span.kind == "client" and http.response.status_code >= 400
| summarize count(), by: { server.address, http.response.status_code }
| sort `count()` desc
```

## Performance Analysis

### Endpoint Latency Percentiles

```dql
fetch spans
| filter span.kind == "server" and isNotNull(http.route)
| summarize
    p50 = median(duration),
    p95 = percentile(duration, 95),
    p99 = percentile(duration, 99),
  by: { http.route }
| sort p99 desc
```

### Slow Requests (>1s)

```dql
fetch spans
| filter span.kind == "server" and duration > 1000000000
| fields start_time, trace.id, http.route, http.request.method, duration
| sort duration desc
| limit 50
```

### Latency Timeseries

```dql
fetch spans
| filter span.kind == "server" and isNotNull(http.route)
| makeTimeseries
    avg_duration = avg(duration),
    p99_duration = percentile(duration, 99),
  by: { http.route }
```

## Payload Analysis

### Request/Response Sizes

```dql
fetch spans
| filter span.kind == "server"
| summarize
    avg_request_size = avg(http.request.body.size),
    avg_response_size = avg(http.response.body.size),
    max_response_size = max(http.response.body.size),
  by: { http.route }
| sort max_response_size desc
```

### Large Responses

```dql
fetch spans
| filter http.response.body.size > 1000000
| fields trace.id, http.route, http.response.body.size
| sort http.response.body.size desc
```

## Client IP Analysis

### Requests by Client

```dql
fetch spans
| filter span.kind == "server" and isNotNull(client.ip)
| summarize requests = count(), by: { client.ip, client.isp }
| sort requests desc
| limit 100
```

### Public vs Private Clients

```dql
fetch spans
| filter span.kind == "server" and isNotNull(client.ip)
| summarize count(), by: { client.ip.is_public }
```

## Protocol Versions

### HTTP Version Distribution

```dql
fetch spans
| filter isNotNull(network.protocol.version)
| summarize count(), by: { network.protocol.name, network.protocol.version }
```

## Related Topics

- [Performance Analysis](performance-analysis.md) - Response time analysis
- [Failure Detection](failure-detection.md) - Failure investigation

---

**← Back to**: [Application Tracing Skill](../SKILL.md)
