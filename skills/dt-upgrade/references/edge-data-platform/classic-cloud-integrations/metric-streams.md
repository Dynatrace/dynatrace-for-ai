# AWS Metric Streams Detection and Migration Blocking

How to detect AWS CloudWatch Metric Streams usage and handle migration-blocked accounts.

---

## What Are Metric Streams?

AWS CloudWatch Metric Streams is a push-based metric ingestion method where AWS pushes metrics via Kinesis Data Firehose to the Dynatrace API endpoint. It is a **classic** AWS connection feature — not part of the new connection.

The new AWS connection does **not yet support** Metric Streams. Metric Streams support is planned as a future secondary ingest method. Until then, accounts relying on Metric Streams should be flagged as not-yet supported for the Metric Streams portion.

---

## Detection

### Query: Find Accounts with Active Metric Streams

```dql
fetch metric.series, from:now()-12h
| filter dt.source == "AWS Metric Streams"
| summarize cnt=count(), by:`aws.account.id`
```

Returns AWS account IDs with Metric Streams traffic in the specified timeframe.

### Key Identifiers

| Dimension | Value | Meaning |
|---|---|---|
| `dt.source` | `"AWS Metric Streams"` | Metric came from Metric Streams |
| `aws.account.id` | Numeric string | The AWS account using Metric Streams |

### Metric Key Format

Metric Streams metrics use a distinct camelCase format with dimensions concatenated in the key:

```
cloud.aws.<service>.<camelCaseMetric>By<Dim1><Dim2>...
```

Examples:
- `cloud.aws.lambda.invocationsByAccountIdFunctionNameRegion`
- `cloud.aws.lambda.durationByAccountIdFunctionNameRegion`
- `cloud.aws.ec2.cpuUtilizationByInstanceIdRegion`

This format differs from both:
- Classic non-built-in: `cloud.aws.<service>.<snake_case>`
- New connection: `cloud.aws.<service>.<PascalCase>.By.<Dim>`

---

## Migration Impact

### What CAN Be Migrated

If an account uses Metric Streams but ALSO has classic built-in or non-built-in polling, those portions can migrate independently:

- Classic built-in polling (`dt.cloud.aws.*` metrics + dedicated entity types) → new connection
- Classic non-built-in polling (`cloud.aws.*` snake_case metrics + custom devices) → new connection

### What CANNOT Be Migrated Yet

- Metric Streams-specific metrics (camelCase format) have no equivalent in the new connection
- Dashboards, alerts, and SLOs referencing Metric Streams metric keys cannot be migrated

### Classification Logic

```
If an AWS account has Metric Streams traffic:
  → Add flag: "migration-blocked (Metric Streams)"
  → This flag applies to the Metric Streams portion only
  → Classic polling on the same account CAN still be migrated
```

### Timeframe Sensitivity

The detection query uses the same timeframe as other discovery queries. If the Firehose was paused for longer than the query window, the account will NOT be flagged — this is intentional (no evidence = no flag).

---

## Characteristics Summary

| Aspect | Metric Streams |
|---|---|
| **Data flow** | AWS CloudWatch → Kinesis Data Firehose → Dynatrace API |
| **`dt.source`** | `"AWS Metric Streams"` |
| **`dt.da.source`** | null (NOT from new connection) |
| **Entities** | None (unless AWS Entities for Metric Streaming extension is enabled) |
| **Tags** | Not available |
| **Predefined alerts** | Not available |
| **Metric key format** | `cloud.aws.<service>.<camelCase>By<Dim1><Dim2>` |
| **New connection support** | Not yet — planned for future |
