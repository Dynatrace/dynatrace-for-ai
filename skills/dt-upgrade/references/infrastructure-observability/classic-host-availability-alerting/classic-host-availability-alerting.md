# Classic Host Availability Alerting

**Gen3 replacement**: Custom alerts (`builtin:davis.anomaly-detectors`) created from the Infrastructure & Operations app templates

**Phase 3 required**: yes

## What changes

Classic host availability alerting is built into Dynatrace. It raises a problem when a host or its
monitoring connection is lost, with no configuration required. In Phase 3 and later, nothing is
configured by default: hosts that go down raise no alert until a custom alert exists. A customer
upgrading to Phase 3 must replace each classic setting with a custom alert, or availability
coverage is silently lost.

The classic behavior lives in `builtin:anomaly-detection.infrastructure-hosts`
(`host.connectionLostDetection`), which has two toggles:

| Classic field | UI label | Values |
|---|---|---|
| `enabled` | Detect host or monitoring connection lost problems | `true` (default), `false` |
| `onGracefulShutdowns` | Graceful host shutdowns | `DONT_ALERT_ON_GRACEFUL_SHUTDOWN` (default), `ALERT_ON_GRACEFUL_SHUTDOWN` |

`onGracefulShutdowns` applies only while `enabled` is `true`. The schema allows scopes `HOST`,
`HOST_GROUP`, and `environment`, with at most one object per scope.

## Prerequisites

- `dt.host.availability` and `dt.host.maintenance` metrics available for the hosts in scope
- Permissions to read and write Settings v2 objects (`settings:objects:read`, `settings:objects:write`)
- OneAgent 1.337 or later on the hosts that must keep alerting. This is the Phase 3 minimum, listed
  in [overview.md](../../overview.md), and a blocker for the opt-in. The detectors identify a host by
  the `dt.smartscape.host` dimension of `dt.host.availability`. Older agents can report the metric
  without that dimension, so a detector never sees them. See the [coverage check](#coverage-check)
- Gen3 maintenance windows migrated first, so the maintenance suppression in the templates matches
  the customer's real windows. Check what exists with
  `dtctl get settings --schema builtin:maintenance-windows -o json`, and see
  [classic-maintenance-windows.md](../classic-maintenance-windows/classic-maintenance-windows.md)
- A problem notification path that does not depend on classic alerting profiles, which Phase 3
  removes. See [alerting-and-problem-notifications.md](../../platform/alerting-and-problem-notifications/alerting-and-problem-notifications.md).
  A custom alert raises a problem, but nothing notifies anyone until a workflow does.

## Instructions

1. Read the classic settings at every scope. Without `--scope`, the list returns one object per
   scope that has been customised: `environment`, each `HOST_GROUP-…`, and each `HOST-…`. It returns
   nothing when the schema is still at its defaults, which means connection lost detection is on and
   graceful shutdowns do not alert:
   ```dtctl
   dtctl get settings --schema builtin:anomaly-detection.infrastructure-hosts -o json
   ```
   Read `value.host.connectionLostDetection` on each object. When `enabled` is `false`,
   `onGracefulShutdowns` is absent. `--scope` takes an entity ID such as `HOST-XXXXXXXXXXXXXXXX`, not
   the scope name `HOST`.
2. Check which hosts can alert at all, with the [coverage check](#coverage-check). A custom alert
   only sees hosts that return `dt.host.availability` with the `dt.smartscape.host` dimension, and a
   OneAgent below 1.337 blocks Phase 3.
   Report every gap to the customer before planning detectors.
3. Drop stale overrides. A `HOST-…` or `HOST_GROUP-…` object can outlive the host or group it was
   set for. Skip those, and tell the customer how many you skipped. See
   [Stale overrides](#stale-overrides).
4. Work out the effective setting of the remaining scopes and the detectors and exclusions they
   need, using the [mapping](#migration-mapping) and [scoping](#scoping) rules below.
5. Ask the customer which `actor` the detectors should run as: a service user (recommended for a
   long-lived detector) or the current user. Do not choose for them.
6. Present the proposed custom alerts, their exclusions, the coverage gaps, and the actor, and ask
   for confirmation before creating anything.
7. Create the custom alerts from the [YAML](#detector-yaml) below and apply each:
   ```dtctl
   dtctl apply -f host-unavailable.yaml
   ```
   In the local CLI, `dtctl apply --dry-run` is client-side only, so it proves nothing about the object. Rely on the read-back.
8. Read the detectors back and compare them to the YAML:
   ```dtctl
   dtctl get settings --schema builtin:davis.anomaly-detectors -o json
   ```
9. Tell the customer that, until they disable the classic setting, a host outage raises both the
   classic problem and the custom alert's problem. Once they have confirmed the new detectors
   behave as expected, disable the classic setting by setting `connectionLostDetection.enabled:
   false` at every scope that has an object. Classic detection is on by default, so when no
   `environment` object exists, also create one with `enabled: false`; otherwise the defaults stay
   active. Do not delete the objects. That is a separate step and needs its own approval.

### Coverage check

Classic alerting watched hosts through the classic entity model. A custom alert only sees hosts
whose `dt.host.availability` series carries the `dt.smartscape.host` dimension, and Phase 3 needs
OneAgent 1.337 or later. Run both checks. Smartscape holds the agent version: the `ONEAGENT` node's
`dt.agent.module.version`, reached through its `monitors` relationship to the `HOST`.

First, list the hosts a custom alert cannot see, with their agent version. A host with
`reportsWithoutSmartscapeDimension` true has the metric, but without the dimension:

```dql
smartscapeNodes ONEAGENT
| traverse "monitors", "HOST", direction: forward, fieldsKeep: {dt.agent.module.version}
| fieldsAdd agentVersion = dt.traverse.history[0][dt.agent.module.version]
| lookup [timeseries a = sum(dt.host.availability), by: {dt.smartscape.host} | fields dt.smartscape.host, hasSmartscapeAvailability = true], sourceField: id, lookupField: dt.smartscape.host, fields: {hasSmartscapeAvailability}
| filter isNull(hasSmartscapeAvailability)
| lookup [timeseries a = sum(dt.host.availability), by: {dt.entity.host} | fields dt.entity.host, hasEntityAvailability = true], sourceField: id_classic, lookupField: dt.entity.host, fields: {hasEntityAvailability}
| fieldsAdd reportsWithoutSmartscapeDimension = coalesce(hasEntityAvailability, false)
| fields id, name, os.type, agentVersion, reportsWithoutSmartscapeDimension
| sort agentVersion
```

Second, list every host below the minimum version, whether or not it currently reports. The first
check misses an older agent that still reports with the dimension:

```dql
smartscapeNodes ONEAGENT
| traverse "monitors", "HOST", direction: forward, fieldsKeep: {dt.agent.module.version}
| fieldsAdd agentVersion = dt.traverse.history[0][dt.agent.module.version]
| filter toLong(splitString(agentVersion, ".")[1]) < 337
| fields id, name, os.type, agentVersion
| sort agentVersion
```

Group the rows of both checks and tell the customer about each group:

| Row | What it means |
|---|---|
| Second check, or an `agentVersion` below 1.337 | **Blocker.** The OneAgent is older than the Phase 3 minimum of 1.337. Upgrade it before the opt-in. A host that is covered today can stop being covered in Phase 3. |
| `reportsWithoutSmartscapeDimension` is true | The agent reports the metric without `dt.smartscape.host`, which usually means the agent is too old. Treat it as the blocker above. |
| Version 1.337 or later, no availability at all | Unexplained. Do not claim the detectors cover it. Tell the customer the cause is not known. |
| `os.type` is `OS_TYPE_ZOS` | Classic host availability alerting is not believed to have applied to z/OS hosts, so this is not a regression. Confirm with the customer. |

The first query uses the default 2-hour window, so a host that has been down for longer also appears.
Check whether it is a known outage before calling it a coverage gap.

### Stale overrides

Classic scopes use entity IDs. Check each against the tenant before planning around it:

- `HOST-…`: the classic ID equals the Smartscape ID. List the override hosts that still exist. A
  host that exists but returns no availability data is a [coverage gap](#coverage-check), not a
  stale override:
  ```dql-template
  smartscapeNodes HOST, from: now()-30d
  | filter in(id, array(toSmartscapeId("HOST-<id1>"), toSmartscapeId("HOST-<id2>")))
  | fields id, name
  ```
- `HOST_GROUP-…`: the classic ID is not the value on hosts. A host carries the group name in
  `dt.host_group.id`. Resolve the entity ID to a name:
  ```dql-template
  fetch dt.entity.host_group, from: now()-30d
  | filter id == "HOST_GROUP-<id>"
  | fields id, entity.name
  ```

An ID with no match is stale: skip it. `smartscapeNodes HOST_GROUP` does not return host groups, so
use the entity lookup above. That lookup returns entities seen in the last 30 days, not live
topology, so a match means "seen recently". Confirm with the customer when a group looks recently
decommissioned.

## Migration mapping

| Classic `connectionLostDetection` | Custom alert template |
|---|---|
| `enabled: true`, `DONT_ALERT_ON_GRACEFUL_SHUTDOWN` | Host or monitoring unavailable |
| `enabled: true`, `ALERT_ON_GRACEFUL_SHUTDOWN` | Host or monitoring unavailable, including graceful shutdowns |
| `enabled: false` | None. Do not create an alert for this scope. |

Classic settings inherit: the most specific scope wins (`HOST`, then `HOST_GROUP`, then
`environment`). Custom alerts do not. Every detector is environment-wide, and none overrides
another. The mapping above gives the template for one scope; see [Scoping](#scoping) for how to
combine scopes.

Both templates use the same alert parameters:

| Parameter | Value |
|---|---|
| `alertCondition` | `BELOW` |
| `threshold` | `1` |
| `violatingSamples` | `2` |
| `slidingWindow` | `2` |
| `dealertingSamples` | `1` |
| `alertOnMissingData` | `false` |

## Scoping

Classic settings can differ per host and host group. A custom alert cannot: `builtin:davis.anomaly-detectors`
only allows `environment` scope, and a detector has no per-host override to turn alerting off. The
only control is the query. A detector alerts on every host its query returns, so to leave a host or
host group out, change the query to exclude it.

Plan so that every host is covered by exactly one detector, or by none. Classify each host by its
effective classic setting (host, else host group, else environment), then compare that with the
environment setting. A host in a group whose override disables detection still alerts if it has its
own enabled override.

| Live override compared with the environment setting | What to do |
|---|---|
| Same setting | Nothing. The environment detector covers it. |
| `enabled: false` | Exclude the host or host group from every detector. |
| Other graceful shutdown choice | Exclude it from the environment detector. Create the other template's detector and restrict it to that host or host group. |
| Environment `enabled: false`, override enabled | No environment detector. Create the matching template and restrict it to the host or host group. |

Insert the filters directly after `fieldsAdd dt.smartscape_source.id = dt.smartscape.host` in either
template. Host groups need a lookup, because the host group is a field of the `HOST` node, not of
the metric. Compare host IDs with `toSmartscapeId()`, because the metric dimension is a Smartscape
ID and a plain string never matches.

The query returns one row with no host (`dt.smartscape.host` is null). In an exclusion filter, guard
with `isNull` so that row is kept: a bare `not in(...)` on a null value drops it, so a host exclusion
looks like it removed one extra host.

Exclude hosts and host groups:

```dql-snippet
| lookup [smartscapeNodes HOST | fields id, dt.host_group.id], sourceField: dt.smartscape.host, lookupField: id, fields: {dt.host_group.id}
| filter isNull(dt.host_group.id) or not in(dt.host_group.id, array("<group-name-1>", "<group-name-2>"))
| filter isNull(dt.smartscape.host) or not in(dt.smartscape.host, array(toSmartscapeId("HOST-<id1>"), toSmartscapeId("HOST-<id2>")))
```

Restrict a detector to hosts and host groups:

```dql-snippet
| lookup [smartscapeNodes HOST | fields id, dt.host_group.id], sourceField: dt.smartscape.host, lookupField: id, fields: {dt.host_group.id}
| filter in(dt.host_group.id, array("<group-name-1>", "<group-name-2>")) or in(dt.smartscape.host, array(toSmartscapeId("HOST-<id1>")))
```

To restrict to hosts only, drop the `lookup` and the group clause and keep
`| filter in(dt.smartscape.host, array(toSmartscapeId("HOST-<id1>")))`. The lookup is only needed for
host groups.

Host group names come from the [stale overrides](#stale-overrides) lookup.

The templates only evaluate hosts that return `dt.host.availability`, and `alertOnMissingData` is
`false`. A host that reports no availability data in the query window raises no alert. Tell the
customer about the hosts the [coverage check](#coverage-check) lists, and do not describe the
detectors as covering every host Dynatrace knows about.

After changing a query, the stored detector no longer matches the app's template. That is expected;
record the exclusions in the detector `description` so the next reader sees why.

## Templates

Both queries return one `availability` series per host. The alert fires
when `availability` is below 1.

### Host or monitoring unavailable

Does not alert on a graceful shutdown. This is the equivalent of `DONT_ALERT_ON_GRACEFUL_SHUTDOWN`.

```dql
timeseries {
    up       = sum(dt.host.availability, rollup: sum, default: 0, filter: availability.state == "up"),
    mw       = sum(dt.host.maintenance, default: 0, filter: maintenance.is_under_maintenance),
    anchor = sum(dt.host.maintenance, default: 0)
  },
  by: { dt.smartscape.host },
  union: true,
  interval:1m
| fieldsAdd dt.smartscape_source.id = dt.smartscape.host
//This logic artificially inflates the host availability timeseries to avoid triggering alerts during a scheduled maintenance window.
| fieldsAdd availability = if(mw[] > 0.0, 1.0, else: if(up[] > 0.0, 1.0, else: 0.0))
//This lookup is responsible for obtaining last known availability state not to raise alerts after a graceful shutdown.
| lookup [
    timeseries availability = sum(dt.host.availability),
    by: {availability.state, dt.smartscape.host},
    interval: 1m, from: now()-13h, to: now()
    | fieldsAdd lastState = record(
              latestStatusIndex = arrayLastIndexOf(availability, arrayLast(availability)),
              availability.state
            )
    | summarize record = takeMax(lastState), by: {dt.smartscape.host}
    | fields lastState = record[availability.state], dt.smartscape.host
  ], sourceField:dt.smartscape_source.id, lookupField:dt.smartscape.host, fields: {lastState}
//This logic artificially inflates the host availability timeseries to avoid triggering alerts after a graceful shutdown.
| fieldsAdd availability = if(lastState == "shutdown_host", iCollectArray(availability[]+1), else: availability)
| fieldsKeep timeframe, interval, dt.smartscape_source.id, availability
```

### Host or monitoring unavailable, including graceful shutdowns

Alerts on a graceful shutdown. This is the equivalent of `ALERT_ON_GRACEFUL_SHUTDOWN`. It is the
first template without the `lookup` and the shutdown inflation.

```dql
timeseries {
    up       = sum(dt.host.availability, rollup: sum, default: 0, filter: availability.state == "up"),
    mw       = sum(dt.host.maintenance, default: 0, filter: maintenance.is_under_maintenance),
    anchor = sum(dt.host.maintenance, default: 0)
  },
  by: { dt.smartscape.host },
  union: true,
  interval:1m
| fieldsAdd dt.smartscape_source.id = dt.smartscape.host
//This logic artificially inflates the host availability timeseries to avoid triggering alerts during a scheduled maintenance window.
| fieldsAdd availability = if(mw[] > 0.0, 1.0, else: if(up[] > 0.0, 1.0, else: 0.0))
| fieldsKeep timeframe, interval, dt.smartscape_source.id, availability
```

## Detector YAML

Applying this YAML produced detectors identical to the ones the Infrastructure & Operations app
creates from the templates. A field-by-field diff of the stored objects differed only in title,
`enabled`, `objectId`, and whitespace in the query. Set the placeholders per template:

| Placeholder | Host or monitoring unavailable | Including graceful shutdowns |
|---|---|---|
| `<query>` | first query above | second query above |
| `<event description>` | `Host or monitoring unavailable due to connectivity issues or server outage` | `Host or monitoring unavailable due to connectivity issues, server outage or a graceful shutdown` |
| `<actor>` | UUID of the service user or user the customer chose in step 5 | same |

The app gives both detectors the title `Host or monitoring unavailable`. Title the second
`Host or monitoring unavailable (including graceful shutdowns)` so the two can be told apart. When
you add exclusions or a restriction, put them in the `description`.

Indent the query by 12 spaces under `value: |-`. A wrong indent changes the stored query or breaks
the YAML, and a local `--dry-run` does not catch it, so check the read-back.

```yaml
- schemaId: builtin:davis.anomaly-detectors
  scope: environment
  value:
    title: Host or monitoring unavailable
    description: Detects when a host stops reporting availability data while not covered by a maintenance window.
    enabled: true
    source: Infrastructure & Operations
    analyzer:
      name: dt.statistics.ui.anomaly_detection.StaticThresholdAnomalyDetectionAnalyzer
      input:
        - key: query.expression
          value: |-
            <query, indented under value>
        - key: alertOnMissingData
          value: "false"
        - key: violatingSamples
          value: "2"
        - key: threshold
          value: "1"
        - key: dealertingSamples
          value: "1"
        - key: slidingWindow
          value: "2"
        - key: alertCondition
          value: BELOW
    eventTemplate:
      properties:
        - key: event.name
          value: Host or monitoring unavailable
        - key: event.type
          value: AVAILABILITY_EVENT
        - key: event.description
          value: <event description>
        - key: event.infraops_ready_made_alert_type
          value: HOST_UNAVAILABLE
        - key: dt.smartscape_source.id
          value: "{dt.smartscape_source.id}"
    executionSettings:
      actor: <actor>
      queryOffset: 2
```

## Outcome

Every host with an effective classic `connectionLostDetection.enabled: true` is covered by exactly
one custom alert, with the graceful shutdown choice the customer confirmed. Stale overrides were
skipped. The customer has been told about duplicate alerts until classic is disabled, and has
disabled it after confirming the new detectors behave as expected.

## Validation

- Every live scope with `connectionLostDetection.enabled: true` has a matching custom alert, and
  every excluded host or host group matches a classic `enabled: false` or a different template
- The stored detector matches the [YAML](#detector-yaml) apart from title, whitespace, and any
  documented exclusions
- After the customer disables classic, `dtctl get settings --schema builtin:anomaly-detection.infrastructure-hosts`
  shows `enabled: false` on every object, including one at `environment` scope
- Optional: stop a test host and confirm the custom alert raises a problem, then repeat with a
  graceful shutdown against both templates and with a host inside a maintenance window. The
  template queries are app-provided and were tested end to end outside this reference, so this
  checks the customer's setup, not the templates.

## References

- [Settings API — Infrastructure host anomaly detection schema](https://docs.dynatrace.com/docs/discover-dynatrace/references/dynatrace-api/environment-api/settings/schemas/builtin-anomaly-detection-infrastructure-hosts)
- [alerting-and-problem-notifications.md](../../platform/alerting-and-problem-notifications/alerting-and-problem-notifications.md) — the other classic alerting schemas
