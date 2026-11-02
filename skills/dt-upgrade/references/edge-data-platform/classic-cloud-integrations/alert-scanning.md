# Alert Scanning

How to scan classic Dynatrace alerts for cloud connection references during migration.

Classic alerts come in three types, each backed by a different settings schema:

| Alert type | Settings schema | Scope |
|---|---|---|
| **Metric Event** | `builtin:anomaly-detection.metric-events` | Custom alerts based on metric keys or metric selector expressions |
| **Infrastructure Anomaly Detection** | `builtin:anomaly-detection.infrastructure-aws` | Out-of-the-box anomaly detection for classic AWS entity types (AWS only) |
| **Anomaly Detector (Custom Alert)** | `builtin:davis.anomaly-detectors` | User-created Davis AI analyzers that may reference classic cloud metrics |

All three are fetched and scanned together when the user selects "Alerts" as an asset type in Stage 2.

---

## Table of Contents

- [1. Metric Events](#1-metric-events)
- [2. Infrastructure Anomaly Detection (AWS Only)](#2-infrastructure-anomaly-detection-aws-only)
- [3. Anomaly Detectors (Custom Alerts)](#3-anomaly-detectors-custom-alerts)
- [4. Remediation Guidance](#4-remediation-guidance)

---

## 1. Metric Events

### Fetch

```
dtctl get settings --schema builtin:anomaly-detection.metric-events -o json
```

This returns all custom metric event alert definitions.

### What to Inspect

Each metric event settings object has this structure:

```json
{
  "objectId": "...",
  "value": {
    "summary": "High Lambda Error Rate",
    "enabled": true,
    "queryDefinition": {
      "type": "METRIC_KEY",
      "metricKey": "dt.cloud.aws.lambda.errors",
      "aggregation": "AVG"
    },
    "modelProperties": {
      "type": "STATIC_THRESHOLD",
      "threshold": 10,
      "alertCondition": "ABOVE",
      "violatingSamples": 3,
      "samples": 5,
      "dealertingSamples": 5,
      "alertOnNoData": false
    }
  }
}
```

There are two `queryDefinition.type` variants:

| Type | Where the metric reference lives |
|---|---|
| `METRIC_KEY` | `queryDefinition.metricKey` — a single metric key string |
| `METRIC_SELECTOR` | `queryDefinition.metricSelector` — a metric selector expression (may contain multiple keys) |

### Detection Logic

For each metric event:

1. Extract the metric text from `queryDefinition.metricKey` or `queryDefinition.metricSelector`
2. **REQUIRED:** Apply classic metric prefix detection from [classic-detection-patterns.md](classic-detection-patterns.md)
3. If classic patterns are detected, record the alert as affected

#### Extracting Individual Keys from Metric Selectors

For `METRIC_SELECTOR` type, the expression may be complex (e.g., `(cloud.aws.lambda.errors_sum:avg) / (cloud.aws.lambda.invocations_sum:avg) * 100`). Extract individual metric keys using the following steps:

**Step 1: Detect prefix type** — scan the expression text for known classic prefixes (e.g., `dt.cloud.aws.`, `cloud.aws.`, `ext:`). This determines which detection patterns apply.

**Step 2: Extract full key tokens** — split the expression on whitespace and operators (e.g., `/`, `*`, `(`, `)`, `,`). For each token, extract the metric key portion using word characters, dots, colons, and hyphens.

**Step 3: Strip aggregation suffixes** — for each extracted token, remove trailing aggregation suffixes (`:avg`, `:min`, `:max`, `:sum`, `:count`, `:value`, `:splitBy`) before matching against classic prefix patterns.

---

## 2. Infrastructure Anomaly Detection (AWS Only)

### What Is It?

Dynatrace provides **built-in, out-of-the-box anomaly detection** for classic AWS infrastructure entity types (EC2, RDS, Lambda, etc.) via the `builtin:anomaly-detection.infrastructure-aws` settings schema. These are auto-managed rules that detect anomalies on classic AWS entities — they are **not** user-created alerts.

This schema only exists for AWS. There is no equivalent schema for Azure or GCP.

### Fetch

```
dtctl get settings --schema builtin:anomaly-detection.infrastructure-aws --scope environment -o json
```

The `--scope environment` flag is required because these settings are environment-scoped, not entity-scoped.

### What to Inspect

Each settings object has this structure:

```json
{
  "objectId": "...",
  "schemaId": "builtin:anomaly-detection.infrastructure-aws",
  "scope": "environment",
  "value": {
    "ec2CandidateHighCpuDetection": {
      "enabled": true,
      "detectionMode": "auto"
    },
    "rdsHighCpuDetection": {
      "enabled": true,
      "detectionMode": "auto"
    },
    "...": "..."
  }
}
```

The `value` object contains detection toggles for classic AWS entity types (EC2, RDS, ELB, Lambda, etc.). The presence of any object in this schema indicates that classic AWS infrastructure anomaly detection is configured for the environment.

### Detection Logic

**Any object returned by the fetch signals that classic AWS infrastructure anomaly detection is active.** Unlike metric events or anomaly detectors, there is no need to inspect individual fields for classic metric patterns — the entire schema is inherently tied to classic AWS entity types.

---

## 3. Anomaly Detectors (Custom Alerts)

### What Are They?

Anomaly Detectors (`builtin:davis.anomaly-detectors`) are **user-created custom alerting rules** that use Davis AI analyzers to detect anomalies based on metric data or DQL expressions. Unlike metric events (which use `STATIC_THRESHOLD` or `METRIC_SELECTOR`), anomaly detectors use named analyzers with typed input fields.

An anomaly detector may reference classic cloud metrics in its analyzer input fields — these need to be updated when migrating to new cloud connections.

> **Schema availability**: The `builtin:davis.anomaly-detectors` schema may not exist on older Dynatrace environments that don't have the Davis AI app installed. Treat a 404 or empty result as zero detectors — not an error.

### Fetch

```
dtctl get settings --schema builtin:davis.anomaly-detectors -o json
```

If the fetch returns 404 or an empty list, treat this alert type as having zero classic references. Do not throw an error or abort the scan — continue to the next asset type.

### What to Inspect

Each anomaly detector settings object has this structure:

```json
{
  "objectId": "...",
  "value": {
    "title": "High Lambda Error Rate Detector",
    "enabled": true,
    "analyzer": {
      "name": "dt.statistics.GenericStatisticsAnalyzer",
      "input": [
        {
          "key": "timeSeriesSelector",
          "value": "dt.cloud.aws.lambda.errors:avg"
        },
        {
          "key": "queryFilter",
          "value": "cloud.provider==\"aws\""
        }
      ]
    }
  }
}
```

The key fields:
- `value.title` or `value.name` — human-readable detector name
- `value.enabled` — whether the detector is active
- `value.analyzer.name` — the analyzer type (e.g., `dt.statistics.GenericStatisticsAnalyzer`)
- `value.analyzer.input[]` — array of `{key, value}` pairs containing the metric references and DQL expressions

### Detection Logic

For each anomaly detector:

1. Extract all `value.analyzer.input[].value` strings
2. For each input value string, **REQUIRED:** apply classic metric prefix detection from [classic-detection-patterns.md](classic-detection-patterns.md)
3. If classic patterns are detected in any input value, extract the individual classic metric keys
4. Record the detector as affected, including:
   - The matching input value strings (for remediation context)
   - The extracted classic metric keys
   - The full analyzer definition (for pre-populating a replacement detector)

#### Example Detection

Given this analyzer input:
```
"value": "dt.cloud.aws.lambda.errors:avg"
```

1. `detect_classic_metrics("dt.cloud.aws.lambda.errors:avg", "aws")` → `["dt.cloud.aws."]`
2. `extract_classic_metric_keys("dt.cloud.aws.lambda.errors:avg", "aws")` → `["dt.cloud.aws.lambda.errors"]`
3. The detector is flagged as affected with `classicPatterns: ["dt.cloud.aws.lambda.errors"]`

---

## 4. Remediation Guidance

### Metric Events

#### Option A: Migrate the Metric Key

1. Identify the classic metric key
2. Look up the new equivalent in [metric-key-mapping.md](metric-key-mapping.md)
3. Update the metric event with the new key
4. Adjust thresholds if the new metric has different units or aggregation

#### Option B: Create an Anomaly Detector (Modern Replacement)

For alerts that use `STATIC_THRESHOLD` model, consider creating an Anomaly Detector instead — this is the modern approach for metric-based alerting in Dynatrace.

Capture these properties from the classic alert for pre-population:
- `modelProperties.threshold`
- `modelProperties.alertCondition` (ABOVE/BELOW)
- `modelProperties.violatingSamples`
- `modelProperties.dealertingSamples`
- `modelProperties.alertOnNoData`
- `modelProperties.samples`

#### Report Format

```
Metric Event: <name> (<objectId>)
Enabled: yes/no
Type: METRIC_KEY | METRIC_SELECTOR
Classic metric(s): dt.cloud.aws.lambda.errors
Model: STATIC_THRESHOLD (threshold: 10, condition: ABOVE)
```

### Infrastructure Anomaly Detection (AWS Only)

Infrastructure anomaly detection for classic AWS entities is **auto-managed by Dynatrace**. No manual migration is required. When the classic connection is removed and the new connection is active:

1. Classic infrastructure anomaly detection (`builtin:anomaly-detection.infrastructure-aws`) will no longer trigger because the classic entity types it monitors will no longer receive data.
2. New Smartscape entity types (e.g., `AWS_EC2_INSTANCE`, `AWS_RDS_DBINSTANCE`) from the new connection have their own built-in anomaly detection managed by Davis AI.

**Action for the user**: No migration action needed. Be aware that:
- Any **customised thresholds** on the classic infrastructure detection (e.g., custom CPU thresholds for EC2) will not carry over automatically to the new connection's built-in detection. Review custom thresholds before disabling the classic connection.
- If custom thresholds exist, consider creating equivalent Anomaly Detectors with the new metric keys to preserve the custom monitoring behaviour.

#### Report Format

```
Infrastructure Detection: AWS Infrastructure Anomaly Detection (<objectId>)
Scope: environment
Status: Active — classic AWS entity types monitored
Action: Informational — auto-replaced by new connection built-in detection
Custom thresholds: Review before cutover
```

### Anomaly Detectors (Custom Alerts)

Anomaly detectors referencing classic cloud metrics need their analyzer inputs updated to use new connection metric keys.

#### Step 1: Identify Classic References

For each affected detector, note:
- Which analyzer input fields contain classic metric references
- The specific classic metric keys used
- The analyzer name and full input configuration

#### Step 2: Look Up New Metric Keys

Use `lookupMetricKey(key, index)` from `scripts/migration-lookup.ts` to find the new equivalents, passing the pre-built `per-key-mappings.json` index.

#### Step 3: Re-create the Detector

Anomaly detectors cannot have their analyzer inputs edited in place through settings — they must be **deleted and re-created** with updated inputs. To re-create:

1. **Capture the full analyzer configuration** from the original detector:
   - `analyzer.name` — the analyzer type
   - `analyzer.input[]` — all input key-value pairs

   > Do not proceed to step 2 until the full detector configuration is captured.

2. **Replace classic metric references** in each input `value` with the new equivalents

   > Verify the new metric keys resolve before proceeding to step 3.

3. **Create a new detector** with the updated analyzer inputs

   > Confirm the new detector is active and firing correctly before proceeding to step 4.

4. **Delete the old detector only after the new one is confirmed working**

#### Migration Strategy

Follow the same zero-gap strategy as metric event alerts:

1. **Stage 4c**: Create a new anomaly detector in *disabled* state with updated metric keys
2. **Stage 4d**: After the new connection ingests data, simultaneously disable the classic detector and enable the new one
3. **After validation**: Delete the old classic detector

#### Report Format

```
Anomaly Detector: <title> (<objectId>)
Enabled: yes/no
Analyzer: <analyzer.name>
Classic metric(s) in inputs: dt.cloud.aws.lambda.errors
Matching input fields:
  - timeSeriesSelector: "dt.cloud.aws.lambda.errors:avg"
New metric key: cloud.aws.lambda.Errors.By.FunctionName (recommended)
```
