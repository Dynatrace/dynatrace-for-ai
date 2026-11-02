# Alerting and Problem Notifications

**Gen3 replacement**: DQL-based Anomaly Detector Alerts, Workflow-based notifications

**Phase 2 required**: yes (anomaly detection migration); no (problem notifications)

## Agent Instructions

Load the `dt-alerting` skill before advising on any gen3 alerting setup. That skill covers the full alerting lifecycle end to end — detector category and model selection, DQL query authoring, Davis event storage, problem denoising, and workflow notification routing. Use this reference for upgrade tracking and classic schema identification; use `dt-alerting` for all configuration guidance on the new platform.

## Migration Order

Migrate alerting and problem notification settings in the following sequence. Each step depends on the previous one being complete.

> **Precondition — Management Zone migration must be complete first**
> Classic problem alerting profiles scope notifications by Management Zone. In gen3 that scoping is replaced by source-side entity tagging; Workflow trigger conditions filter on those tags rather than on Management Zone membership. The alerting migration cannot be completed faithfully until Management Zones have been migrated to their gen3 equivalents. See the [Management Zones upgrade reference](../management-zones/management-zones.md) and confirm that migration is complete before proceeding with any step below.

**Step 1 — Migrate classic anomaly detection schemas to gen3 alternatives**

Migrate all classic alerting Settings schema entries listed in the table below to their gen3 replacements before touching notification settings. Load `dt-alerting` for configuration guidance on each target schema. This step must come first because the new detectors determine what Davis events and problems are raised — the notification layer (Step 2) must route problems that already exist on the gen3 platform.

**Step 2 — Migrate problem notification settings to Workflows**

> **Migration strategy — consolidate, don't recreate 1:1**
> Avoid mapping each classic profile-notification pair to one workflow. Instead, try to group entries by destination into fewer workflows.

For each `builtin:problem.notifications` entry:
1. Identify which `builtin:alerting.profile` it references and document that profile's filter criteria (severity levels, event type, Management Zone scope, delay).
2. Create a new Workflow that replaces both settings entries:
   - Set the **problem trigger filter** to replicate the problem alerting profile's filter criteria using equivalent Workflow condition expressions (`event.severity`, `event.category`, `smartscape.affected_entity.ids`, etc.).
   - Add `maintenance.is_under_maintenance != true` to that trigger filter if the notification should stay silent during maintenance. Classic maintenance windows suppressed these notifications implicitly; gen3 windows do not, so the condition has to be written explicitly here. Omitting it moves the gap rather than closing it — the workflow will page during maintenance where the classic notification did not.
   - Set the **workflow action** to match the integration type configured in the problem notification — for webhooks use `dynatrace.automations:http-function`, for ServiceNow use `dynatrace.servicenow:snow-create-incident`, and so on for other connectors.
3. Validate the workflow fires correctly before decommissioning the classic entries.

**Step 3 — Replicate the integration payload using Grail problem record fields**

Map the fields from the classic problem notification payload to the Grail problem record fields that the Workflow problem trigger makes available. The Workflow receives a `dt.davis.problems` record as its trigger context — use those fields to construct the equivalent notification payload.

Key field mappings from classic payload → Grail problem record:

| Classic payload field | Grail problem record field |
|---|---|
| Problem ID | `event.display_id` |
| Problem title | `event.name` |
| Problem severity | `event.severity` |
| Problem category | `event.category` |
| Problem status (OPEN / RESOLVED) | `event.status` |
| Problem start time | `event.start` |
| Problem end time | `event.end` |
| Affected entity names | `affected_entity_ids` (resolve names via `entitySelector`) |
| Root cause entity | `root_cause_entity_id` (use with caution — may be unset or shift during the problem lifecycle; prefer `affected_entity_ids` for routing) |
| Problem URL | `{{ problem_link() }}` |
| Tags on affected entities | `entity_tags` |

See the `dt-alerting` skill (`workflow-notifications.md`) for Workflow configuration patterns.

**Step 4 — Disable migrated classic settings entries**

Once a classic settings entry has been successfully migrated and the gen3 replacement is validated in production, set the classic entry to **Disabled** rather than deleting it immediately. Disabling preserves the configuration as an audit trail and allows quick rollback if an issue is discovered after cutover.

- For each migrated `builtin:anomaly-detection.metric-events`, `builtin:anomaly-detection.infrastructure-disks`, `builtin:anomaly-detection.disk-rules`, `builtin:anomaly-detection.infrastructure-aws`, or `builtin:availability.process-group-alerting` entry: set `enabled: false` via the Settings v2 API or UI.
- For each migrated `builtin:problem.notifications` entry: set `enabled: false`. The referenced `builtin:alerting.profile` can be disabled at the same time since it is only meaningful when a problem notification setting references it.
- Re-run the Upgrade Inventory Status Report queries to confirm all migrated entries appear in the `inactive` count and none remain active unexpectedly.

---

## Alert Upgrade Status Report

Run these code sections in a Dynatrace notebook to establish a baseline before starting migration. Present the results to the user as a structured status report showing how many classic alerting settings remain active, how many are already deactivated, and how many problem notification entries still need to be replaced by Workflows.

### Summary: all classic alerting schemas at a glance

Fetch all entries for each of the following schemas and count how many are active (`enabled` is not `false`) versus inactive (`enabled: false`). Present the result as a summary table with columns `schemaId`, `active`, `inactive`, `total`.

Schemas to query:
- `builtin:anomaly-detection.metric-events`
- `builtin:anomaly-detection.infrastructure-disks`
- `builtin:anomaly-detection.disk-rules`
- `builtin:anomaly-detection.infrastructure-aws`
- `builtin:availability.process-group-alerting`
- `builtin:alerting.profile`
- `builtin:problem.notifications`

Use the platform settings list tool to retrieve all objects for each schema ID.

### Metric event alerts — list active entries (`builtin:anomaly-detection.metric-events`)

Use the platform settings list tool to retrieve all objects for the `builtin:anomaly-detection.metric-events` schema, then filter to entries where `enabled` is not `false`.

### Problem notifications — list active entries with referenced problem alerting profile

Use the platform settings list tool to retrieve all objects for the `builtin:problem.notifications` schema, filter to entries where `enabled` is not `false`, and for each entry report `objectId`, `value.name`, and `value.alertingProfile` (the problem alerting profile ID is needed for Step 2).

### Problem notifications — actual usage by problem alerting profile and notification

Use the `dt.sfm.server.notifications.problem_notifications` metric to measure how many notifications each configuration actually sent. This complements the configuration inventory above by identifying entries that are active but never fire (migration candidates that can be decommissioned without impact) and by quantifying volume per entry to assess whether limits are being approached.

```dql
timeseries count(dt.sfm.server.notifications.problem_notifications), by: { alerting_profile.id, notification.id}
```

Report the results grouped by `alerting_profile.id` and `notification.id`. Entries with zero counts over the assessment window are unused and can be safely decommissioned. Entries with high counts should be prioritized for migration to avoid notification gaps.

---

## Classic Schemas to Upgrade

The following classic Settings schemas must be migrated to the corresponding gen3 platform settings and mechanisms. The gen3 replacements are covered in detail in the `dt-alerting` skill.

| Classic Schema | Gen3 Replacement | Notes |
|---|---|---|
| `builtin:anomaly-detection.metric-events` | `builtin:davis.anomaly-detectors` | Metric event alerts using metric selectors → DQL-based or metric-key anomaly detectors. Migration wizard available but covers ~80% of cases only. |
| `builtin:alerting.profile` | Workflow trigger filters | Classic problem alerting profiles (Management Zone scoping, severity/event-type filters) → Workflow notification filter conditions. **No explicit migration required** as long as every `builtin:problem.notifications` entry is migrated to a Workflow with an equivalent trigger filter that represents the problem alerting profile filter that was referenced in the problem notification setting. **Precondition**: Management Zone migration must be complete before translating MZ-scoped profiles to Workflow conditions — see the [Management Zones upgrade reference](../management-zones/management-zones.md). |
| `builtin:anomaly-detection.infrastructure-disks` | `builtin:infrastructure.disk.edge.anomaly-detectors` | Classic disk anomaly detection via Grail query → edge-side OneAgent disk detector. Covers low disk space, low inodes, and slow I/O. Seconds-latency vs. minutes; no Grail query load per host. |
| `builtin:anomaly-detection.disk-rules` | `builtin:infrastructure.disk.edge.anomaly-detectors` | Classic per-disk custom rules → edge-side OneAgent disk detector. Migrate custom disk rules to the edge detector's threshold configuration. |
| `builtin:anomaly-detection.infrastructure-aws` | `alerts-cloud-services` | Classic AWS infrastructure anomaly detection settings → cloud services alerts schema. |
| `builtin:availability.process-group-alerting` | `process-availability` | Server-side process group availability check via Grail query → edge-side OneAgent process availability detector. Seconds-latency vs. minutes. |
| Classic problem notification integrations (ServiceNow, PagerDuty, Atlassian JSM, email, webhooks) | Simple workflow | See `dt-alerting` skill (`workflow-notifications.md`) for migration detail. |

---

## Metric Event Alerts

**Classic schema**: `builtin:anomaly-detection.metric-events`

**Gen3 replacement**: `builtin:davis.anomaly-detectors` (DQL-based Anomaly Detector Alerts)

**Phase 2 required**: yes

### What changes

- Info banner and teaser shown in classic app
- Migration wizard offered that leverages the metric transpiler (works only in ~80% of cases due to the metric transpiler)

### Customer actions

- Rework alerting configs that use Management Zones (requires Management Zone migration to be complete first — see the [Management Zones upgrade reference](../management-zones/management-zones.md))
- Rework alerting configs that use Alerting Rules
- Migrate towards DQL-based alerting configs (`builtin:davis.anomaly-detectors`)
- Set up Workflow-based alert notifications

### Tracking queries

Metric for listing all metric events that use metricSelectors:

```dql
timeseries count(dt.sfm.server.anomaly_detection.metric_events.monitored_dimensions), by:{dt.config.id, dt.config.name}
```

### Documentation

- [Upgrade guide: alert notification](https://docs.dynatrace.com/docs/shortlink/upgrade-guide-alert-notification)

### Best practices

- [Upgrade guide: alert notification](https://docs.dynatrace.com/docs/shortlink/upgrade-guide-alert-notification)

---

## Classic Problem Alerting Profiles

**Classic schema**: `builtin:alerting.profile`

**Gen3 replacement**: Workflow notification trigger filters

### What changes

Classic problem alerting profiles scoped notifications by Management Zone, severity, event type, and delay. Each `builtin:problem.notifications` entry referenced a problem alerting profile to apply that filter before dispatching the notification. In gen3, this filtering logic moves into Workflow trigger conditions and filter expressions. Management Zone-based scoping is replaced by source-side entity tagging — see the [Management Zones upgrade reference](../management-zones/management-zones.md) for the full transition; that migration must be complete before the MZ filter criteria of a problem alerting profile can be faithfully expressed as Workflow conditions.

**Problem alerting profiles do not need to be migrated explicitly.** The profile only mattered because it was referenced by a problem notification setting. Once every `builtin:problem.notifications` entry is migrated to a Workflow, the equivalent filter must be expressed as a Workflow problem trigger condition — replicating what the referenced problem alerting profile was doing. When all problem notifications have been migrated in this way, the problem alerting profiles themselves become unused and can be decommissioned.

### Customer actions

- **Verify the [Management Zones upgrade reference](../management-zones/management-zones.md) migration is complete** before translating any MZ-scoped problem alerting profile into Workflow trigger conditions.
- For each `builtin:problem.notifications` entry, identify which problem alerting profile it referenced and document that profile's filter criteria (severity, event type, Management Zone scope, delay)
- Migrate the problem notification to a Workflow and encode the profile's filter criteria as the Workflow's problem trigger condition (DQL filter expressions on `event.severity`, `event.category`, `smartscape.affected_entity.ids`, etc.)
- Once all problem notifications are migrated, decommission the now-unused problem alerting profiles

### Tracking queries

Use the platform settings list tool to retrieve all objects for the `builtin:alerting.profile` schema.

---

## Process Group Availability

**Classic schema**: `builtin:availability.process-group-alerting`

**Gen3 replacement**: `process-availability` (edge-side OneAgent detector)

### What changes

The legacy process group availability schema evaluated process state by reading process group metrics from Grail on a scheduled query, introducing minutes of detection latency and adding Grail query load proportional to the monitored fleet. The `process-availability` schema moves the check to the OneAgent, eliminating both problems.

### Customer actions

- Identify all `builtin:availability.process-group-alerting` configurations
- Re-create each rule as a `process-availability` Settings v2 object scoped to the appropriate host group or host
- Validate detection latency and alert routing before decommissioning legacy configs

### Tracking queries

Use the platform settings list tool to retrieve all objects for the `builtin:availability.process-group-alerting` schema.
