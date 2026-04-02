# RPC Span Analysis

Remote Procedure Call (RPC) spans cover gRPC, SOAP, Java RMI, and other RPC frameworks. These queries help monitor inter-service communication.

## Key Attributes

- `rpc.system`: framework (grpc, jax_ws, dotnet_wcf, etc.)
- `rpc.service`: service name being called
- `rpc.method`: method invoked
- `rpc.grpc.status_code`: gRPC-specific status
- `network.protocol.name`: protocol (grpc, soap, rest_http)

## RPC Traffic Overview

### Calls by Service and Method

```dql
fetch spans
| filter isNotNull(rpc.system)
| summarize
    calls = count(),
    avg_duration = avg(duration),
  by: { rpc.system, rpc.service, rpc.method }
| sort calls desc
```

### Client vs Server Spans

```dql
fetch spans
| filter isNotNull(rpc.system)
| summarize count(), by: { span.kind, rpc.system }
```

## gRPC Analysis

### gRPC Status Code Distribution

```dql
fetch spans
| filter rpc.system == "grpc"
| summarize count(), by: { rpc.grpc.status_code, rpc.service, rpc.method }
| sort `count()` desc
```

Common gRPC status codes:

- 0: OK
- 2: UNKNOWN
- 4: DEADLINE_EXCEEDED
- 13: INTERNAL
- 14: UNAVAILABLE

### gRPC Errors

```dql
fetch spans
| filter rpc.system == "grpc" and rpc.grpc.status_code != 0
| summarize
    errors = count(),
    example_trace = takeAny(trace.id),
  by: { rpc.service, rpc.method, rpc.grpc.status_code }
| sort errors desc
```

### gRPC Latency by Method

```dql
fetch spans
| filter rpc.system == "grpc" and span.kind == "server"
| summarize
    calls = count(),
    avg_latency = avg(duration),
    p99_latency = percentile(duration, 99),
  by: { rpc.service, rpc.method }
| sort p99_latency desc
```

## SOAP/Web Services

### SOAP Operations

```dql
fetch spans
| filter contains(toString(rpc.system), "ws") or network.protocol.name == "soap"
| summarize count(), by: { rpc.service, rpc.method, rpc.namespace }
```

## Service Dependencies

### RPC Call Graph

Identify service-to-service RPC dependencies:

```dql
fetch spans
| filter isNotNull(rpc.system) and span.kind == "client"
| fieldsAdd caller = getNodeName(dt.smartscape.service)
| summarize
    calls = count(),
    avg_latency = avg(duration),
  by: { caller, server.address, rpc.service }
| sort calls desc
```

### Server Endpoints

```dql
fetch spans
| filter isNotNull(rpc.system) and span.kind == "server"
| fieldsAdd service = getNodeName(dt.smartscape.service)
| summarize
    requests = count(),
    p95_latency = percentile(duration, 95),
  by: { service, rpc.service, rpc.method }
```

## Performance Monitoring

### RPC Latency Timeseries

```dql
fetch spans
| filter isNotNull(rpc.system) and span.kind == "server"
| makeTimeseries
    avg_duration = avg(duration),
    p99_duration = percentile(duration, 99),
    calls = count(),
  by: { rpc.service }
```

### Slow RPC Calls

```dql
fetch spans
| filter isNotNull(rpc.system) and duration > 1000000000
| fields start_time, trace.id, rpc.service, rpc.method, duration, server.address
| sort duration desc
| limit 50
```

## Best Practices

- **Filter by `span.kind`** - "client" spans show outgoing calls, "server" spans show incoming
- **Monitor gRPC status codes** - Non-zero codes indicate errors
- **Track latency by method** - Identify slow RPC operations
- **Map service dependencies** - Use client spans to understand service call graphs
- **Include service context** - Add `getNodeName(dt.smartscape.service)` for clarity

## Related Topics

- [Performance Analysis](performance-analysis.md) - Latency analysis
- [Failure Detection](failure-detection.md) - Error investigation

---

**← Back to**: [Application Tracing Skill](../SKILL.md)
