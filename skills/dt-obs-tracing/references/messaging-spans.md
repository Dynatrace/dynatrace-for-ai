# Messaging Span Analysis

Messaging spans capture async communication via Kafka, RabbitMQ, SQS, and other message brokers. Use these queries to monitor message processing health.

## Key Attributes

- `messaging.system`: broker type (kafka, rabbitmq, aws_sqs, etc.)
- `messaging.destination.name`: queue/topic name
- `messaging.operation.type`: publish, receive, process
- `messaging.batch.message_count`: messages in batch operations
- `span.kind`: producer (send) or consumer (receive/process)

## Message Throughput

### Messages by Destination

```dql
fetch spans
| filter isNotNull(messaging.system)
| summarize
    spans = count(),
    messages = sum(coalesce(messaging.batch.message_count, 1)),
  by: { messaging.system, messaging.destination.name, messaging.operation.type }
| sort messages desc
```

### Producer vs Consumer Volume

```dql
fetch spans
| filter isNotNull(messaging.system)
| summarize messages = sum(coalesce(messaging.batch.message_count, 1)),
  by: { span.kind, messaging.system }
```

## Kafka Analysis

### Consumer Group Lag Indicators

Identify slow consumer groups:

```dql
fetch spans
| filter messaging.system == "kafka" and messaging.operation.type == "process"
| summarize
    processed = count(),
    avg_duration = avg(duration),
    p99_duration = percentile(duration, 99),
  by: { messaging.consumer.group.name, messaging.destination.name }
| sort p99_duration desc
```

### Partition Distribution

```dql
fetch spans
| filter messaging.system == "kafka"
| summarize count(), by: { messaging.destination.name, messaging.destination.partition.id }
| sort `count()` desc
```

## Message Processing Health

### Failed Message Processing

```dql
fetch spans
| filter messaging.operation.type == "process"
| summarize
    total = count(),
    failed = countIf(messaging.is_failed == true),
  by: { messaging.destination.name }
| fieldsAdd failure_rate = (failed * 100.0) / total
| sort failure_rate desc
```

### Batch Processing Failures

```dql
fetch spans
| filter isNotNull(messaging.batch.message_count) and messaging.batch.failed_count > 0
| fields
    start_time,
    trace.id,
    messaging.destination.name,
    messaging.batch.message_count,
    messaging.batch.failed_count,
    messaging.batch.failure_codes
```

## Processing Latency

### End-to-End Message Latency

```dql
fetch spans
| filter messaging.operation.type == "process"
| summarize
    avg_latency = avg(duration),
    p95_latency = percentile(duration, 95),
    p99_latency = percentile(duration, 99),
  by: { messaging.system, messaging.destination.name }
| sort p99_latency desc
```

### Latency Timeseries

```dql
fetch spans
| filter messaging.operation.type == "process"
| makeTimeseries
    avg_duration = avg(duration),
    p99_duration = percentile(duration, 99),
  by: { messaging.destination.name }
```

## Broker Connectivity

### Messages by Broker Server

```dql
fetch spans
| filter isNotNull(messaging.system)
| summarize
    spans = count(),
    services = countDistinct(dt.smartscape.service),
  by: { server.address, server.port, messaging.system }
```

## Best Practices

- **Use `messaging.batch.message_count`** for accurate message counts (defaults to 1)
- **Filter by `messaging.operation.type`** to distinguish publish vs process operations
- **Monitor p99 latency** for consumer groups to detect lag
- **Track failure rates** by destination to identify problematic queues
- **Analyze partition distribution** for Kafka to ensure balanced consumption

## Related Topics

- [Performance Analysis](performance-analysis.md) - Latency analysis techniques
- [Failure Detection](failure-detection.md) - Error investigation

---

**← Back to**: [Application Tracing Skill](../SKILL.md)
