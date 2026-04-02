# Serverless (FaaS) Span Analysis

Function-as-a-Service spans capture AWS Lambda, Azure Functions, and GCP Cloud Functions execution. Monitor cold starts, invocations, and performance.

## Key Attributes

- `faas.name`: function name
- `faas.coldstart`: true if cold start
- `faas.trigger`: invocation trigger type
- `cloud.provider`: aws, azure, gcp
- `aws.region` / `azure.location` / `gcp.region`: deployment region

## Function Invocations

### Invocations by Function

```dql
fetch spans
| filter isNotNull(faas.name) and span.kind == "server"
| summarize
    invocations = count(),
    avg_duration = avg(duration),
    p99_duration = percentile(duration, 99),
  by: { faas.name, cloud.provider }
| sort invocations desc
```

### Invocations by Trigger Type

```dql
fetch spans
| filter isNotNull(faas.name)
| summarize count(), by: { faas.trigger, faas.name }
```

Common triggers: `http`, `pubsub`, `datasource`, `timer`, `other`

## Cold Start Analysis

### Cold Start Rate

```dql
fetch spans
| filter isNotNull(faas.name) and span.kind == "server"
| summarize
    total = count(),
    cold_starts = countIf(faas.coldstart == true),
  by: { faas.name }
| fieldsAdd cold_start_rate = (cold_starts * 100.0) / total
| sort cold_start_rate desc
```

### Cold Start Duration Impact

```dql
fetch spans
| filter isNotNull(faas.name)
| fieldsAdd
    cold_duration = if(faas.coldstart == true, duration, else: null),
    warm_duration = if(faas.coldstart != true, duration, else: null)
| summarize
    avg_cold = avg(cold_duration),
    avg_warm = avg(warm_duration),
  by: { faas.name }
| fieldsAdd cold_start_overhead = avg_cold - avg_warm
```

### Cold Starts Over Time

```dql
fetch spans
| filter isNotNull(faas.name)
| makeTimeseries
    cold_starts = countIf(faas.coldstart == true),
    warm_starts = countIf(faas.coldstart != true),
  by: { faas.name }
```

## Cloud Provider Analysis

### AWS Lambda

```dql
fetch spans
| filter isNotNull(aws.arn) and contains(aws.arn, ":function:")
| summarize
    invocations = count(),
    avg_duration = avg(duration),
  by: { faas.name, aws.region }
```

### Azure Functions

```dql
fetch spans
| filter isNotNull(azure.site_name)
| summarize count(), by: { azure.site_name, azure.location }
```

### GCP Cloud Functions

```dql
fetch spans
| filter isNotNull(gcp.resource.name) and contains(gcp.resource.name, "cloudfunctions")
| summarize count(), by: { faas.name, gcp.region }
```

## Performance Monitoring

### Function Duration Percentiles

```dql
fetch spans
| filter isNotNull(faas.name) and span.kind == "server"
| summarize
    p50 = median(duration),
    p95 = percentile(duration, 95),
    p99 = percentile(duration, 99),
  by: { faas.name }
| sort p99 desc
```

### Memory Configuration

```dql
fetch spans
| filter isNotNull(faas.name) and isNotNull(faas.max_memory)
| summarize
    avg_duration = avg(duration),
    max_memory_mb = max(faas.max_memory) / 1048576,
  by: { faas.name }
```

## Event Source Tracing

### Event-Triggered Functions

```dql
fetch spans
| filter isNotNull(faas.event_source)
| summarize count(), by: { faas.event_source, faas.event_name, faas.name }
```

### Document/Data Triggers

```dql
fetch spans
| filter faas.trigger == "datasource"
| summarize count(), by: { faas.document.operation, faas.document.collection }
```

## Error Analysis

### Failed Function Invocations

```dql
fetch spans
| filter isNotNull(faas.name) and request.is_failed == true
| summarize failures = count(), by: { faas.name, faas.trigger }
| sort failures desc
```

## Best Practices

- **Monitor cold start rates** - High rates indicate configuration issues
- **Compare cold vs warm duration** - Quantify cold start overhead
- **Track invocations by trigger** - Understand function usage patterns
- **Filter by `span.kind == "server"`** for function entry points
- **Analyze by region** - Identify geographic performance differences
- **Monitor failure rates** - Track function reliability

## Related Topics

- [Performance Analysis](performance-analysis.md) - Duration analysis
- [Failure Detection](failure-detection.md) - Error investigation

---

**← Back to**: [Application Tracing Skill](../SKILL.md)
