# Database Span Analysis

Database operations in traces appear as client spans with database-specific attributes. Database spans can be aggregated (one span representing multiple calls).

## Basic Database Queries

### List Database Operations

Query database activity:

```dql
fetch spans
| filter isNotNull(db.query.text)
| summarize spans=count(), by: { db.system, db.operation.name, db.collection.name }
```

### Database Spans by Service

Identify which services make database calls:

```dql
fetch spans
| filter span.kind == "client" and isNotNull(db.namespace)
| fieldsAdd getNodeName(dt.smartscape.service)
| summarize {
    spans=count(),
    avg_duration=avg(duration)
  }, by: { dt.smartscape.service.name, db.system, db.namespace }
| sort spans desc
```

## Top Database Statements

### Extrapolated Statement Counts

Count actual database calls (not just spans) per service:

```dql
fetch spans
| filter span.kind == "client" and isNotNull(db.namespace)
| fieldsAdd getNodeName(dt.smartscape.service)

// Calculate multiplicity for extrapolation
| fieldsAdd sampling.probability = (power(2, 56) - coalesce(sampling.threshold, 0)) * power(2, -56)
| fieldsAdd sampling.multiplicity = 1/sampling.probability
| fieldsAdd multiplicity = coalesce(sampling.multiplicity, 1)
                         * coalesce(aggregation.count, 1)
                         * dt.system.sampling_ratio

| summarize {
    db_calls = sum(multiplicity)
  }, by: {
    dt.smartscape.service.name,
    code.function,
    db.system,
    db.namespace,
    db.query.text
  }

| sort db_calls desc
| limit 100
```

## Database Performance

### Statement Duration Analysis

Analyze database call durations with aggregation awareness:

```dql
fetch spans
| filter span.kind == "client" and isNotNull(db.query.text)

// Calculate average duration for aggregated spans
| fieldsAdd aggregation.duration_avg = coalesce(
    aggregation.duration_sum / aggregation.count,
    duration
)

// Calculate multiplicity
| fieldsAdd sampling.probability = (power(2, 56) - coalesce(sampling.threshold, 0)) * power(2, -56)
| fieldsAdd sampling.multiplicity = 1/sampling.probability
| fieldsAdd multiplicity = coalesce(sampling.multiplicity, 1)
                         * coalesce(aggregation.count, 1)
                         * dt.system.sampling_ratio

| summarize {
    operation_count = sum(multiplicity),
    avg_duration = sum(aggregation.duration_avg * multiplicity) / sum(multiplicity),
    p95_duration = percentile(aggregation.duration_avg, 95)
  }, by: { db.system, db.operation.name, db.collection.name }
| sort operation_count desc
| limit 50
```

### Slow Database Queries

Find slowest database statements:

```dql
fetch spans
| filter span.kind == "client" and isNotNull(db.query.text)
| fieldsAdd aggregation.duration_avg = coalesce(
    aggregation.duration_sum / aggregation.count,
    duration
)
| filter aggregation.duration_avg > 100ms
| fields
    trace.id,
    db.system,
    db.query.text,
    duration=aggregation.duration_avg,
    aggregated_calls=aggregation.count
| sort duration desc
| limit 50
```

## Database Attributes

Common database span attributes:

- `db.system` - Database type (e.g., postgresql, mysql, mongodb)
- `db.namespace` - Database name
- `db.query.text` - SQL/query statement
- `db.operation.name` - Operation type (SELECT, INSERT, UPDATE, etc.)
- `db.collection.name` - Table/collection name
- `db.affected_item_count` - Number of rows/documents affected

## Best Practices

- **Always extrapolate** - Use multiplicity factor when counting database operations
- **Use `aggregation.duration_avg`** - Calculate `aggregation.duration_sum / aggregation.count` for accurate durations
- **Filter by `span.kind == "client"`** and `isNotNull(db.namespace)` to identify database spans
- **Check `aggregation.count`** - Indicates one span represents multiple operations
- **Consider read sampling** - Use `samplingRatio` for better performance on large datasets
- **Include service context** - Add `getNodeName(dt.smartscape.service)` to identify which service makes calls

## Related Topics

- [Sampling and Extrapolation](sampling-extrapolation.md) - Detailed extrapolation formulas
- [Performance Analysis](performance-analysis.md) - Duration analysis techniques

---

**← Back to**: [Application Tracing Skill](../SKILL.md)
