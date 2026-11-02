# SLO Scanning

How to scan Dynatrace SLOs for classic cloud connection references.

---

## Table of Contents

- [1. Fetch Classic SLOs](#1-fetch-classic-slos)
- [2. What to Inspect](#2-what-to-inspect)
- [3. Detection Logic](#3-detection-logic)
- [4. Remediation Guidance](#4-remediation-guidance)

---

## 1. Fetch Classic SLOs

```dtctl
dtctl get slos -o json
```

This returns all SLO definitions including metric expressions and entity filters.

---

## 2. What to Inspect

Each SLO has two fields that may contain classic references:

| Field | What it contains | Example |
|---|---|---|
| `metricExpression` | Metric selector expression | `(100)*(builtin:cloud.aws.ec2.cpu_usage:avg)` |
| `filter` | Entity selector expression | `type(EC2_INSTANCE),entityName.contains("prod")` |

Both fields may reference classic cloud metrics or entity types.

### SLO Structure

```json
{
  "id": "abc123",
  "name": "AWS EC2 CPU SLO",
  "enabled": true,
  "status": "SUCCESS",
  "evaluationType": "AGGREGATE",
  "target": 99.0,
  "metricExpression": "(100)*(builtin:cloud.aws.ec2.cpu_usage:avg:partition(\"dt.entity.ec2_instance\",type(\"EC2_INSTANCE\")):default(0,always))",
  "filter": "type(EC2_INSTANCE),entityName.startsWith(\"prod\")"
}
```

---

## 3. Detection Logic

### Scanning Metric Expressions

Apply classic metric prefix detection to `metricExpression` (**REQUIRED:** load [classic-detection-patterns.md](classic-detection-patterns.md)):

1. Search for classic metric prefixes: `dt.cloud.aws.*`, `dt.cloud.azure.*`, `builtin:cloud.*`, `ext:cloud.*`, etc.
2. The `builtin:` and `ext:` prefixes are Cassandra-era selectors — definitive classic indicators
3. Entity type references embedded in `partition()` calls (e.g., `partition("dt.entity.ec2_instance",type("EC2_INSTANCE"))`) are also classic indicators

### Scanning Entity Selectors

Apply classic entity selector detection to `filter` (**REQUIRED:** load [classic-detection-patterns.md](classic-detection-patterns.md)):
1. Search for `type(<CLASSIC_TYPE>)` patterns matching classic entity types
2. For AWS: `type(EC2_INSTANCE)`, `type(AWS_LAMBDA_FUNCTION)`, etc.
3. For Azure: `type(AZURE_VM)`, `type(AZURE_SQL_DATABASE)`, etc.
4. For GCP: any `type(CUSTOM_DEVICE)` reference in an SLO entity selector IS a classic entity — there are no `CUSTOM_DEVICE` types in the new GCP connection.

---

## 4. Remediation Guidance

For each affected SLO:

1. Identify the classic metrics and entity references
2. Look up the new metric key in [metric-key-mapping.md](metric-key-mapping.md)
3. Look up the new entity type in [entity-type-mapping.md](entity-type-mapping.md)

   > **Fallback**: If the metric key or entity type is not found in either mapping database or heuristic guide: mark the SLO as **non-migratable** in the assessment report. Do not attempt to guess a mapping — flag it for manual review.

4. Rewrite the affected fields:
   - 4a. **Replace metric key**: substitute the new metric key for the classic one in `metricExpression`
   - 4b. **Replace partition entity type** (if present): update `partition()` to use the new Smartscape node type
   - 4c. **Replace entity selector** (if present in `filter`): rewrite using Smartscape node filters
5. Create a new SLO with the updated definition (classic SLOs cannot be edited to use DQL metrics)

> **Note**: New DQL-based SLOs use a different API surface. Migrating a classic SLO to a DQL-based SLO may require creating a new SLO rather than editing the existing one.

### Report Format

```
SLO: <name> (<id>)
Enabled: yes/no
Status: SUCCESS/FAILURE/WARNING/DISABLED
Evaluation: AGGREGATE/WINDOW
Target: 99.0%
Classic metric(s): builtin:cloud.aws.ec2.cpu_usage
Classic entity selector: type(EC2_INSTANCE)
```
