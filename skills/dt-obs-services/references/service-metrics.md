# Service Metrics Reference

Complete reference for service performance monitoring, including RED metrics, advanced service analysis, and service mesh monitoring.

---

## Part 1: Service Metrics (RED Metrics)

Monitor service performance, failures, and traffic using metrics-based timeseries queries.

### Response Time Analysis

#### Basic Response Time Monitoring

```dql
timeseries response_time = avg(dt.service.request.response_time), by: {dt.service.name}
| fieldsAdd avg_response_ms = arrayAvg(response_time) / 1000
| sort avg_response_ms desc

```

**Key Metrics:**

- `dt.service.request.response_time`: Server-side response time (microseconds)
- `dt.service.request.count`: Total request count
- `dt.service.request.failure_count`: Failed request count

#### Response Time Percentiles

```dql
timeseries {
  p50 = percentile(dt.service.request.response_time, 50),
  p95 = percentile(dt.service.request.response_time, 95),
  p99 = percentile(dt.service.request.response_time, 99)
}, by: {dt.service.name}
| fieldsAdd p50_ms = p50[] / 1000, p95_ms = p95[] / 1000, p99_ms = p99[] / 1000
```

#### Response Time by Endpoint

```dql
timeseries response_time = avg(dt.service.request.response_time),
  by: {dt.service.name, endpoint.name}
| fieldsAdd avg_response_ms = arrayAvg(response_time) / 1000
| filter avg_response_ms > 500
| sort avg_response_ms desc
| limit 20

```

#### Performance Degradation Detection

```dql
timeseries recent_avg = avg(dt.service.request.response_time), by: {dt.service.name}, from: now() - 15m
| fieldsAdd recent_avg_ms = arrayAvg(recent_avg) / 1000
| append [
  timeseries baseline_avg = avg(dt.service.request.response_time), by: {dt.service.name}, shift: -15m
  | fieldsAdd baseline_avg_ms = arrayAvg(baseline_avg) / 1000
]
| fieldsAdd degradation_pct = (recent_avg_ms - baseline_avg_ms) * 100 / baseline_avg_ms
| filter degradation_pct > 50
| sort degradation_pct desc
```

### Failure Analysis

#### Error Rate Calculation

```dql
timeseries {
    total_requests = sum(dt.service.request.count),
    failures = sum(dt.service.request.failure_count)
  }, by: {dt.service.name}
| fieldsAdd error_rate_pct = (failures[] * 100.0) / total_requests[]
| filter arrayAvg(error_rate_pct) > 0

```

#### Failure Spikes

```dql
timeseries failures = sum(dt.service.request.failure_count), by: {dt.service.name}
| fieldsAdd {
    max_failures = arrayMax(failures),
    avg_failures = arrayAvg(failures),
    spike_ratio = arrayMax(failures) / arrayAvg(failures)
  }
| filter spike_ratio > 3 and arraySum(failures) > 20
| sort spike_ratio desc

```

#### Failures by HTTP Status

```dql
timeseries failures = sum(dt.service.request.failure_count),
  by: {dt.service.name, http.response.status_code}
| fieldsAdd total_failures = arraySum(failures)
| filter total_failures > 0
| sort total_failures desc

```

### Traffic Analysis

#### Request Throughput

```dql
timeseries requests = sum(dt.service.request.count), by: {dt.service.name}, bins: 100
| fieldsAdd requests_per_second = requests[] / 60

```

#### Peak Traffic Detection

```dql
timeseries requests = sum(dt.service.request.count), by: {dt.service.name}
| fieldsAdd {
    max_requests = arrayMax(requests),
    avg_requests = arrayAvg(requests),
    peak_ratio = arrayMax(requests) / arrayAvg(requests)
  }
| filter peak_ratio > 2
| sort peak_ratio desc

```

#### Traffic Growth

```dql
timeseries recent_total = sum(dt.service.request.count, scalar: true), by: {dt.service.name}, from: -30m, to: now()
| append [
  timeseries baseline_total = sum(dt.service.request.count, scalar: true), by: {dt.service.name}, from: -60m, to: -30m
]
| fieldsAdd growth_pct = ((recent_total - baseline_total) * 100.0) / baseline_total
| filter baseline_total > 100
| sort growth_pct desc

```

### Kubernetes Context

#### Service Performance by Workload

```dql
timeseries {
    response_time = avg(dt.service.request.response_time),
    requests = sum(dt.service.request.count),
    failures = sum(dt.service.request.failure_count)
  }, by: {k8s.workload.name, k8s.namespace.name}
| fieldsAdd response_time_ms = response_time[] / 1000
```

#### Multi-Cluster Comparison

```dql
timeseries {
    avg_response = avg(dt.service.request.response_time),
    total_requests = sum(dt.service.request.count),
    failures = sum(dt.service.request.failure_count)
  }, by: {k8s.cluster.name, dt.service.name}
| fieldsAdd avg_response_ms = avg_response[] / 1000, error_rate = failures[] * 100.0 / total_requests[]
```

---

## Part 2: Service Messaging Metrics

Monitor message-based service communication including publishing, receiving, and processing of messages via queues and topics.

**Key Metrics:**

| Metric Key | Description | Unit |
|------------|-------------|------|
| `dt.service.messaging.publish.count` | Messages sent to queues or topics | count |
| `dt.service.messaging.receive.count` | Messages received from queues or topics | count |
| `dt.service.messaging.process.count` | Messages successfully processed | count |
| `dt.service.messaging.process.failure_count` | Messages that failed processing | count |

### Message Throughput

#### Publish and Receive Rate

```dql
timeseries {
  published = sum(dt.service.messaging.publish.count),
  received = sum(dt.service.messaging.receive.count)
}, by: {dt.service.name}
```

#### Processing Success and Failure Rate

```dql
timeseries {
  processed = sum(dt.service.messaging.process.count),
  failed = sum(dt.service.messaging.process.failure_count)
}, by: {dt.service.name}
| fieldsAdd failure_rate_pct = (failed[] * 100.0) / (processed[] + failed[])
```

### Message Processing Failures

#### Services with Highest Processing Failures

```dql
timeseries failures = sum(dt.service.messaging.process.failure_count), by: {dt.service.name}
| fieldsAdd total_failures = arraySum(failures)
| filter total_failures > 0
| sort total_failures desc
```

#### Processing Failure Spike Detection

```dql
timeseries failures = sum(dt.service.messaging.process.failure_count), by: {dt.service.name}
| fieldsAdd {
    max_failures = arrayMax(failures),
    avg_failures = arrayAvg(failures),
    spike_ratio = arrayMax(failures) / arrayAvg(failures)
  }
| filter spike_ratio > 3 and arraySum(failures) > 10
| sort spike_ratio desc
```

### Consumer Lag Analysis

#### Publish vs Receive Rate Comparison

```dql
timeseries {
  published = sum(dt.service.messaging.publish.count),
  received = sum(dt.service.messaging.receive.count)
}, by: {dt.service.name}
| fieldsAdd lag_indicator = published[] - received[]
| filter arrayAvg(lag_indicator) > 0
| sort lag_indicator desc
```

### Combined Messaging Overview

#### Full Messaging Pipeline Health

```dql
timeseries {
  published = sum(dt.service.messaging.publish.count),
  received = sum(dt.service.messaging.receive.count),
  processed = sum(dt.service.messaging.process.count),
  failed = sum(dt.service.messaging.process.failure_count)
}, by: {dt.service.name}
| fieldsAdd
    total_published = arraySum(published),
    total_received = arraySum(received),
    total_processed = arraySum(processed),
    total_failed = arraySum(failed)
| fieldsAdd processing_failure_rate = if(total_processed + total_failed > 0, (total_failed * 100.0) / (total_processed + total_failed), else: 0)
| sort total_failed desc
```

---

## Part 3: Advanced Service Performance Analysis

Span-based queries for complex service analysis requiring flexible filtering and custom aggregations. For standard metric monitoring, use timeseries queries in Part 1.

### SLA Compliance Tracking

Custom SLA calculation with complex conditions:

```dql
fetch spans, from: now() - 1h
| filter request.is_root_span == true
| fieldsAdd
    meets_sla = if(request.is_failed == false AND duration < 3000000000, 1, else: 0)
| summarize
    total_requests = count(),
    sla_compliant = sum(meets_sla),
    by: {dt.service.name}
| fieldsAdd sla_compliance_percent = (sla_compliant * 100.0) / total_requests
| filter sla_compliance_percent < 99.9
| sort sla_compliance_percent asc

```

**Use Case:** Custom SLA thresholds combining failure status and duration.

### Service Health Scoring

Multi-dimensional health assessment:

```dql
fetch spans, from:now()-1h
| filter request.is_root_span == true
| summarize
    total = count(),
    errors = countIf(request.is_failed == true),
    slow = countIf(duration > 3s),
    p95_duration = percentile(duration, 95),
    by: {dt.service.name}
| fieldsAdd
    error_rate = (errors * 100.0) / total,
    slow_rate = (slow * 100.0) / total
| fieldsAdd
    health_status = if(
        error_rate < 1.0 and slow_rate < 5.0, "healthy",
        else: if(error_rate < 5.0, "degraded", else: "critical")
    )
| sort health_status, error_rate desc

```

**Use Case:** Combined health score using multiple conditions and thresholds.

### Operation-Level Performance

Analyze performance by specific operations:

```dql
fetch spans, from: now() - 2h
| filter request.is_root_span == true
| summarize
    request_count = count(),
    avg_duration_ms = avg(duration) / 1000000,
    p95_duration_ms = percentile(duration, 95) / 1000000,
    error_count = countIf(request.is_failed == true),
    by: {dt.service.name, span.name}
| fieldsAdd error_rate = (error_count * 100.0) / request_count
| filter request_count > 10
| sort p95_duration_ms desc
| limit 30

```

**Use Case:** Detailed operation/endpoint analysis with span names.

### Custom Error Classification

Categorize errors with complex logic:

```dql
fetch spans, from: now() - 1h
| filter request.is_root_span == true and request.is_failed == true
| fieldsAdd
    error_category = if(
        http.response.status_code >= 500, "server_error",
        else: if(http.response.status_code >= 400, "client_error",
        else: "other_failure")
    )
| summarize count = count(),
  by: {dt.service.name, error_category, http.response.status_code}
| sort count desc

```

**Use Case:** Custom error categorization beyond standard failure metrics.

### Request Context Analysis

Analyze performance with additional span attributes:

```dql
fetch spans, from: now() - 1h
| filter request.is_root_span == true
| summarize
    request_count = count(),
    avg_duration_ms = avg(duration) / 1000000,
    p95_duration_ms = percentile(duration, 95) / 1000000,
    by: {dt.service.name, http.request.method, http.route}
| filter request_count > 5
| sort p95_duration_ms desc
| limit 50

```

**Use Case:** Performance analysis by HTTP method and route patterns.

### Failure Pattern Detection

Identify failure patterns using Dynatrace failure detection results. This extracts structured failure reasons from `dt.failure_detection.results`, matching exception details from span events.

```dql
fetch spans, from: now() - 2h
| filter request.is_root_span == true and request.is_failed == true

// Extract failure reasons from failure detection results
| expand dt.failure_detection.results
| fieldsAdd reason = dt.failure_detection.results[reason], exception_ids = dt.failure_detection.results[exception_ids]
| fieldsAdd exceptionsFound = iAny(arrayIndexOf(exception_ids, span.events[][exception.id]) > -1)
| expand exception_ids = if(exceptionsFound, exception_ids, else: array(0))
| expand event = if(exceptionsFound, span.events, else: array(0))
| filter isFalseOrNull(exceptionsFound) OR isNull(reason) OR reason != "exception" OR event[exception.id] == exception_ids
| fieldsAdd exceptionName = event[exception.type]
| fieldsAdd failure_reason = if(reason == "span_status", concat("Span status ", span.status_code),
   else: if(reason == "grpc_code", concat("GRPC status ", rpc.grpc.status_code),
   else: if(reason == "http_code", concat("HTTP ", http.response.status_code),
   else: if(reason == "exception", coalesce(exceptionName, "Unknown exception"),
   else: if(isNull(reason), "<No failure reason>",
   else: concat("Unknown reason: ", reason))))))

| summarize
    failure_count = count(),
    unique_errors = countDistinctExact(failure_reason),
    avg_duration_ms = avg(duration) / 1000000,
    by: {dt.service.name, span.name}
| filter failure_count > 3
| sort failure_count desc
| limit 20

```

**Use Case:** Pattern analysis using Dynatrace failure detection to classify failures by HTTP status codes, gRPC codes, exceptions, and span status.

**Note:** The `dt.failure_detection.results` attribute contains structured failure analysis data. The query expands these results and matches exception IDs against span events to extract exception types. Failure reasons are classified into categories: `http_code`, `grpc_code`, `exception`, `span_status`.

---

## Part 4: Service Mesh Metrics

Monitor service mesh ingress performance, failures, and traffic patterns.

### Mesh Response Time

#### Basic Mesh Performance

```dql
timeseries response_time = avg(dt.service.request.service_mesh.response_time), by: {dt.service.name}
| fieldsAdd avg_response_ms = arrayAvg(response_time) / 1000
| sort avg_response_ms desc

```

**Key Metrics:**

- `dt.service.request.service_mesh.response_time`: Mesh ingress response time (microseconds)
- `dt.service.request.service_mesh.count`: Mesh request count
- `dt.service.request.service_mesh.failure_count`: Mesh failure count

#### Mesh vs Direct Overhead

```dql
timeseries {
    direct_p95 = percentile(dt.service.request.response_time, 95),
    mesh_p95 = percentile(dt.service.request.service_mesh.response_time, 95)
  }, by: {dt.service.name}
| fieldsAdd direct_p95_ms = direct_p95[] / 1000, mesh_p95_ms = mesh_p95[] / 1000
| fieldsAdd mesh_overhead = mesh_p95_ms - direct_p95_ms
| filter arrayAvg(mesh_overhead) > 0
| sort mesh_overhead desc
```

#### Mesh Performance Degradation

```dql
timeseries recent_avg = avg(dt.service.request.service_mesh.response_time), by: {dt.service.name}, from: now() - 15m
| fieldsAdd recent_avg_ms = arrayAvg(recent_avg) / 1000
| append [
  timeseries baseline_avg = avg(dt.service.request.service_mesh.response_time), by: {dt.service.name}, from: now() - 30m, to: now() - 15m
  | fieldsAdd baseline_avg_ms = arrayAvg(baseline_avg) / 1000
]
| fieldsAdd degradation_pct = (recent_avg_ms - baseline_avg_ms) * 100 / baseline_avg_ms
| filter degradation_pct > 30
| sort degradation_pct desc
```

### Mesh Failures

#### Mesh Error Rate

```dql
timeseries {
    total_requests = sum(dt.service.request.service_mesh.count),
    failures = sum(dt.service.request.service_mesh.failure_count)
  }, by: {dt.service.name}
| fieldsAdd error_rate_pct = (failures[] * 100.0) / total_requests[]
| filter arrayAvg(error_rate_pct) > 0

```

#### Mesh Failures by Status Code

```dql
timeseries {
    requests = sum(dt.service.request.service_mesh.count),
    failures = sum(dt.service.request.service_mesh.failure_count)
  }, by: {dt.service.name, http.response.status_code}
| fieldsAdd failure_pct = (failures[] * 100.0) / requests[]

```

### Mesh Traffic

#### Mesh Request Volume

```dql
timeseries requests = sum(dt.service.request.service_mesh.count), by: {dt.service.name}
| fieldsAdd total_requests = arraySum(requests)
| sort total_requests desc

```

#### Mesh gRPC Traffic

```dql
timeseries {
    requests = sum(dt.service.request.service_mesh.count),
    failures = sum(dt.service.request.service_mesh.failure_count)
  }, by: {dt.service.name, rpc.grpc.status_code}
| filter isNotNull(rpc.grpc.status_code)

```

### Mesh Kubernetes Context

#### Mesh Performance by Workload

```dql
timeseries {
    response_time = avg(dt.service.request.service_mesh.response_time),
    failures = sum(dt.service.request.service_mesh.failure_count),
    total = sum(dt.service.request.service_mesh.count)
  }, by: {k8s.workload.name, k8s.namespace.name}
| fieldsAdd response_time_ms = response_time[] / 1000, error_rate = failures[] * 100.0 / total[]
```

#### Mesh Multi-Cluster Performance

```dql
timeseries {
    avg_response = avg(dt.service.request.service_mesh.response_time),
    p95_response = percentile(dt.service.request.service_mesh.response_time, 95)
  }, by: {k8s.cluster.name, dt.service.name}
| fieldsAdd avg_response_ms = avg_response[] / 1000, p95_response_ms = p95_response[] / 1000
```
