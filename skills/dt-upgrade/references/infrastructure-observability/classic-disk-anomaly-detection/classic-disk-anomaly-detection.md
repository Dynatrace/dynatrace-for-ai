# Classic Disk Anomaly Detection

**Gen3 replacement**: Disk Edge

**Phase 2 required**: yes

## What changes

Classic disk anomaly detection evaluates disk metrics by running Grail queries server-side on a scheduled basis, introducing minutes of detection latency and adding Grail query load proportional to the monitored fleet. Disk Edge moves detection to the OneAgent at the edge — anomalies are detected within seconds with no Grail query overhead.

Two classic schemas are retired:

- `builtin:anomaly-detection.infrastructure-disks` — global disk anomaly settings applied to all disks across all hosts
- `builtin:anomaly-detection.disk-rules` — per-disk custom rules that override global settings for disks matching name or tag filters

Both are replaced by `builtin:infrastructure.disk.edge.anomaly-detectors` — a policy-based schema scoped at tenant, host group, or host level. Each policy defines which disks it applies to and what thresholds trigger alerts.

## Prerequisites

- OneAgent version 1.293 or later on all monitored hosts (Disk Edge alerting requirement — see [Settings API — Disk Edge schema](https://docs.dynatrace.com/docs/discover-dynatrace/references/dynatrace-api/environment-api/settings/schemas/builtin-infrastructure-disk-edge-anomaly-detectors))
- Permissions to read and write Settings v2 objects (`settings:objects:read`, `settings:objects:write`)

## Instructions

1. Read all active `builtin:anomaly-detection.infrastructure-disks` entries:
   ```bash
   dtctl get settings --schema builtin:anomaly-detection.infrastructure-disks -o json --plain
   ```
2. Read all active `builtin:anomaly-detection.disk-rules` entries:
   ```bash
   dtctl get settings --schema builtin:anomaly-detection.disk-rules -o json --plain
   ```
3. Using the migration mapping below, convert the active classic settings into the equivalent Disk Edge policy objects (`builtin:infrastructure.disk.edge.anomaly-detectors`).
4. Present the proposed Disk Edge policies to the customer and ask for confirmation before creating them.
5. Once confirmed, write each policy to a YAML file and apply it:
   ```bash
   dtctl apply -f disk-edge-policy.yaml
   ```
6. Verify the policies were created:
   ```bash
   dtctl get settings --schema builtin:infrastructure.disk.edge.anomaly-detectors -o json --plain
   ```
7. Disable classic entries by setting `enabled: false` and applying the update — do not delete them to preserve rollback capability.

## Migration mapping

### Global settings → Disk Edge

| Classic field (`infrastructure-disks`) | Disk Edge alert type |
|---|---|
| `diskLowSpaceDetection` / `freeSpacePercentage` (%) | `AVAILABLE_DISK_SPACE_PERCENT_BELOW` |
| `diskSlowWritesAndReadsDetection` / `writeAndReadTime` (ms) | `READ_TIME_EXCEEDING` + `WRITE_TIME_EXCEEDING` (create one alert for each) |
| `diskLowInodesDetection` / auto mode | `AVAILABLE_INODES_PERCENT_BELOW` (auto mode) |
| `diskLowInodesDetection` / `freeInodesPercentage` (%) | `AVAILABLE_INODES_PERCENT_BELOW` with threshold |

### Per-disk rules → Disk Edge

| Classic field (`disk-rules`) | Disk Edge equivalent |
|---|---|
| `metric: LOW_DISK_SPACE` / `thresholdPercent` | Alert type `AVAILABLE_DISK_SPACE_PERCENT_BELOW` |
| `metric: LOW_INODES` / `thresholdPercent` | Alert type `AVAILABLE_INODES_PERCENT_BELOW` |
| `metric: READ_TIME_EXCEEDING` / `thresholdMilliseconds` | Alert type `READ_TIME_EXCEEDING` |
| `metric: WRITE_TIME_EXCEEDING` / `thresholdMilliseconds` | Alert type `WRITE_TIME_EXCEEDING` |
| `diskNameFilter` (`CONTAINS` / `EQUALS` / `STARTS_WITH`) | `diskNameFilters` using `$contains(<value>)` / `$eq(<value>)` / `$prefix(<value>)` |
| `tagFilters` (host tags) | Host group or host scope, or `detectionConditions` on host metadata |

## Examples

### Global low disk space and slow I/O alerts

Classic (`builtin:anomaly-detection.infrastructure-disks`):

```json
{
  "disk": {
    "diskLowSpaceDetection": {
      "enabled": true,
      "detectionMode": "custom",
      "customThresholds": { "freeSpacePercentage": 3 }
    },
    "diskSlowWritesAndReadsDetection": {
      "enabled": true,
      "detectionMode": "custom",
      "customThresholds": { "writeAndReadTime": 200 }
    },
    "diskLowInodesDetection": {
      "enabled": true,
      "detectionMode": "auto"
    }
  }
}
```

Disk Edge equivalent — one policy at tenant scope covering all three detections:

```json
{
  "policyName": "Global disk anomaly detection",
  "enabled": true,
  "operatingSystem": ["WINDOWS", "LINUX", "AIX"],
  "diskNameFilters": [],
  "detectionConditions": [],
  "alerts": [
    { "alertType": "AVAILABLE_DISK_SPACE_PERCENT_BELOW", "threshold": 3 },
    { "alertType": "READ_TIME_EXCEEDING", "threshold": 200 },
    { "alertType": "WRITE_TIME_EXCEEDING", "threshold": 200 },
    { "alertType": "AVAILABLE_INODES_PERCENT_BELOW" }
  ]
}
```

Note: `diskSlowWritesAndReadsDetection` uses a single `writeAndReadTime` threshold in the classic schema; Disk Edge splits read and write into separate alert types — set the same threshold for both.

`dtctl apply` YAML format for the policy above:

```yaml
- schemaId: builtin:infrastructure.disk.edge.anomaly-detectors
  scope: environment
  value:
    policyName: Global disk anomaly detection
    enabled: true
    operatingSystem:
      - WINDOWS
      - LINUX
      - AIX
    diskNameFilters: []
    detectionConditions: []
    alerts:
      - alertType: AVAILABLE_DISK_SPACE_PERCENT_BELOW
        threshold: 3
      - alertType: READ_TIME_EXCEEDING
        threshold: 200
      - alertType: WRITE_TIME_EXCEEDING
        threshold: 200
      - alertType: AVAILABLE_INODES_PERCENT_BELOW
```

### Per-disk rule for data partitions

Classic (`builtin:anomaly-detection.disk-rules`):

```json
{
  "name": "Data partitions low space",
  "enabled": true,
  "metric": "LOW_DISK_SPACE",
  "thresholdPercent": 5,
  "diskNameFilter": { "operator": "STARTS_WITH", "value": "/data" }
}
```

Disk Edge equivalent — tenant-scope policy with disk name filter:

```json
{
  "policyName": "Data partitions low space",
  "enabled": true,
  "operatingSystem": ["LINUX"],
  "diskNameFilters": ["$prefix(/data)"],
  "detectionConditions": [],
  "alerts": [
    { "alertType": "AVAILABLE_DISK_SPACE_PERCENT_BELOW", "threshold": 5 }
  ]
}
```

## Outcome

After migration, all disk anomaly detection must be handled by `builtin:infrastructure.disk.edge.anomaly-detectors` policies. Both classic schemas must have all entries disabled.

## Validation

Use the platform settings list tool to retrieve all objects for each schema and count active (`enabled: true`) versus inactive (`enabled: false`) entries:

Schemas to check:

- `builtin:anomaly-detection.infrastructure-disks`
- `builtin:anomaly-detection.disk-rules`

Migration is complete when:

- All `builtin:anomaly-detection.infrastructure-disks` entries have `enabled: false`
- All `builtin:anomaly-detection.disk-rules` entries have `enabled: false`
- At least one `builtin:infrastructure.disk.edge.anomaly-detectors` policy is active and covers the equivalent detection scope

## References

- [Settings API — Disk Edge schema](https://docs.dynatrace.com/docs/discover-dynatrace/references/dynatrace-api/environment-api/settings/schemas/builtin-infrastructure-disk-edge-anomaly-detectors)
- [Settings API — Disk anomaly detection rules schema](https://docs.dynatrace.com/docs/discover-dynatrace/references/dynatrace-api/environment-api/settings/schemas/builtin-anomaly-detection-disk-rules)
- [Settings API — Infrastructure disk schema](https://docs.dynatrace.com/docs/discover-dynatrace/references/dynatrace-api/environment-api/settings/schemas/builtin-anomaly-detection-infrastructure-disks)
