# Davis Events in Grail

Every anomaly detector trigger produces a **Davis event** — a structured record
stored in Grail that captures what was detected, on which entity, and for how long.
Davis events are the raw material from which AI root-cause analysis builds problems.

## Contents

- [What is a Davis Event?](#what-is-a-davis-event)
- [Davis Event Categories](#davis-event-categories)
- [Key Fields](#key-fields)
- [event.provider — Alert Source and Licensing](#eventprovider--alert-source-and-licensing)
- [Settings Reference — Tracing Alerts Back to Their Config](#settings-reference--tracing-alerts-back-to-their-config)
- [DQL Query Patterns](#dql-query-patterns)
- [Relationship to Problems](#relationship-to-problems)
- [Davis Event Lifecycle](#davis-event-lifecycle)

---

## What is a Davis Event?

A Davis event is created when an anomaly detector (built-in (=health alert) or custom) determines
that a metric has violated its threshold. Each Davis event:

- Represents **one condition violation on one entity**
- Is stored in Grail and queryable via DQL
- Has an active window (`event.start` to `event.end`)
- Is independently matched against other Davis events by Dynatrace root-cause analysis for problem grouping

One detector firing on 10 different service entities creates 10 separate Davis
events — not one. Davis AI then decides which of those Davis events to group into a
single problem.

---

## Davis Event Categories

The `event.category` field classifies what kind of condition was detected:

| Category | Triggered by |
|----------|-------------|
| `AVAILABILITY` | Entity became unavailable — synthetic failure, process down, service unreachable |
| `ERROR` | Error rate exceeded threshold — service errors, database errors |
| `SLOWDOWN` | Response time or throughput degraded below / above threshold |
| `RESOURCE` | Resource saturation — CPU, memory, disk, network |
| `INFO` | Information context changes — Deployment or config changes, process restarts, other infos |
| `CUSTOM` | User-defined event rule without a specific semantic category |

---

## Key Fields

| Field | Description |
|-------|-------------|
| `event.id` | System-generated unique identifier for the Davis event — the ultimate technical identity of an individual Davis event record |
| `event.kind` | Always `"DAVIS_EVENT"` for detector-triggered alerts |
| `event.name` | Alert title — set by the detector's `eventTemplate.title`; should be short, precise, and follow a consistent naming convention (see below) |
| `event.category` | Alert category (AVAILABILITY, ERROR, SLOWDOWN, RESOURCE, CUSTOM) |
| `event.status` | `"ACTIVE"` — threshold still breached; `"CLOSED"` — condition resolved |
| `event.status_transition` | Describes the lifecycle update that produced this Davis event record: `CREATED` — first occurrence; `UPDATED` — properties changed while active; `REFRESHED` — keep-alive report received within the timeout window; `TIMED_OUT` — no refresh arrived before `dt.davis.timeout` expired, Davis event closed; `RECOVERED` — condition cleared normally |
| `timestamp` | UNIX Epoch time in nanoseconds when the Davis event originated — set by the source when available, otherwise populated at ingest time. Required for all Davis events. For correlated Davis events (e.g. ITIL updates) this may differ from `event.start`, as it represents when the specific update record was created rather than when the condition first began |
| `event.start` | Timestamp when the threshold was first breached |
| `event.end` | Timestamp when the condition cleared (null while still ACTIVE) |
| `event.description` | Long-form description of the Davis event (up to 10,000 characters, Markdown format) |
| `event.provider` | Identification for the detector source category of the Davis event |
| `dt.smartscape_source.id` | Smartscape entity ID of the affected resource |
| `dt.smartscape_source.type` | Smartscape entity type of the affected resource (e.g. `SERVICE`, `HOST`, `PROCESS`, `K8S_POD`, `K8S_DEPLOYMENT`). These are Smartscape type names, not classic ones — `PROCESS`, not `PROCESS_GROUP_INSTANCE`; `K8S_DEPLOYMENT`, not `CLOUD_APPLICATION` |
| `event.severity` | ITIL-aligned incident severity: `1` (Critical) · `2` (High) · `3` (Medium) · `4` (Low) · `5` (Informational) — lower number = more severe (see below) |
| `dt.davis.timeout` | Keep-alive window in minutes — the event stays `ACTIVE` for this duration after the last report; a new report with the same `event.name` and identifying fields must arrive within the window to extend it, otherwise the event closes automatically |
| `dt.event.correlation_tag` | Optional tag added by the event source to split otherwise identical events into separate active instances. By default Dynatrace derives the correlation ID from `event.name`, `dt.source_entity`, and `event.provider`; setting this field appends an extra component to that hash so two reports with the same name and entity but different tags are tracked as independent events |
| `dt.query` | Optional DQL timeseries query attached to the event; rendered as a chart in the Dynatrace UI to visually explain the metric violation that triggered the alert |
| `dt.davis.is_frequent_event` | Optional boolean set by the system when it identifies the event as frequent or spammy — useful for filtering out noise in over-alerting analysis |
| `dt.davis.is_merging_allowed` | Whether Davis AI is allowed to merge this event into a problem |
| `dt.davis.status` | Internal Davis status — distinct from `event.status` |
| `dt.alert_group` | Davis event field used for routing to the right workflow notification channels |
| `maintenance.is_under_maintenance` | Optional boolean indicating that the affected entity was under a scheduled maintenance window when this event was raised — useful for suppressing or deprioritising alerts that fired during planned downtime |

### Naming convention for event.name

`event.name` is the primary identifier humans and workflow filters see — it
appears in problem titles, notification messages, and DQL results. Inconsistent
names make it hard to filter, aggregate, or route alerts reliably.

**Rule of thumb — use the pattern: `{Component} {Condition} {Direction/Threshold}`**

| Part | What to put there | Examples |
|------|-------------------|---------|
| Component | The service, technology, or resource being monitored | `Payment Service`, `Kubernetes Node`, `PostgreSQL` |
| Condition | The metric or health aspect that is violated | `Error Rate`, `CPU Usage`, `Response Time`, `Pod Restart Count` |
| Direction / Threshold | The breach direction or limit that makes the alert actionable | `High`, `> 5%`, `Critical`, `Saturated` |

**Good examples**
- `Payment Service Error Rate High`
- `Kubernetes Node CPU Saturated`
- `PostgreSQL Connection Pool Exhausted`
- `Synthetic Check Availability Failed`

**Avoid**
- Generic names like `Alert`, `Threshold Exceeded`, `Metric Alert` — these are
  meaningless in aggregated views
- Including dynamic values (entity names, current metric values) in the title —
  use `event.description` for those; titles should be stable so they can be used
  as filter keys in workflows and DQL queries
- Mixing naming styles across detectors — decide on one pattern and apply it
  consistently so `summarize ... by {event.name}` produces clean groupings

### Severity levels for event.severity

`event.severity` carries an ITIL-aligned integer that expresses how critical the
condition is. The scale runs from 1 (most severe) to 5 (least severe):

| Value | ITIL level | Typical meaning |
|-------|-----------|-----------------|
| `1` | Critical | Complete outage or data loss — immediate action required |
| `2` | High | Major degradation with significant user impact |
| `3` | Medium | Partial degradation or elevated error rates — investigate soon |
| `4` | Low | Minor anomaly, no immediate user impact |
| `5` | Informational | Awareness only — no action required |

**Setting and overriding severity**

The alert source (detector configuration) should always set an explicit, meaningful
default severity (1–5) — do not rely on a platform default. A well-chosen default makes workflow filters and notification
routing work without manual triage.

At the same time, the detector configuration should expose a user-facing override
so that teams can adjust the default severity for their context without modifying
the detector logic. This is especially important for shared or platform-managed
detectors where the right severity differs by team or environment (e.g. the same
CPU detector may warrant severity `2` in production but severity `4` in a dev
environment).

---

## event.provider — Alert Source and Licensing

`event.provider` identifies which Dynatrace subsystem or integration raised the
Davis event. It is **automatically assigned by the Dynatrace platform** — a
Davis event client (external caller, workflow, Events API) cannot set or override it.

### Why it matters

1. **Source traceability** — `event.provider` tells you exactly where in the
   alerting pipeline a Davis event originated, which is the first step when
   investigating over-alerting or unexpected alert volume.
2. **Licensing** — Dynatrace uses `event.provider` to determine whether a Davis event
   is covered by your existing license or whether it is priced separately under
   the event rate card. Understanding which providers are active helps control
   costs.

### Known provider values

| `event.provider` value | Alert source |
|------------------------|-------------|
| `metric_events` | DQL-based anomaly detectors (custom metric alert rules) |
| `Baseline` | Built-in Dynatrace health detectors for services and applications |
| `KUBERNETES_ANOMALY_DETECTION` | Kubernetes anomaly detection running on ActiveGate |
| `Kubernetes_events` | Events imported directly from a Kubernetes cluster |
| `synthetic` | Synthetic monitors (browser, HTTP, scripted) |
| `opentelemetry` | OpenTelemetry-based alert sources |

> This list is not exhaustive. Use the DQL query below to discover all providers
> active in your environment.

### Query: report active event.provider sources

```dql
fetch dt.davis.events, from: -24h
| filter event.status == "ACTIVE"
| summarize alert_count = count(), by: {event.provider}
| sort alert_count desc
| limit 100
```

Run this query to see which providers are generating the most alert volume —
useful as a starting point for over-alerting analysis or license attribution.

---

## Settings Reference — Tracing Alerts Back to Their Config

Most (but not all) Davis events carry two fields that link the Davis event back to the
exact Dynatrace settings entry that produced it:

| Field | Meaning |
|-------|---------|
| `dt.settings.object_id` | Unique ID of the single settings object (the detector config entry) that raised this Davis event |
| `dt.settings.schema_id` | Name of the settings schema (the "table") in which that object lives |

### object_id vs. schema_id

- **`dt.settings.object_id`** identifies one specific detector configuration — the
  individual rule you created or that Dynatrace auto-generated. Two detectors of
  the same type will have different object IDs.
- **`dt.settings.schema_id`** identifies the *type* of detector. Different detector
  categories always use different schema tables, so the schema ID tells you which
  part of the alerting pipeline the setting belongs to (e.g. DQL-based metric
  events vs. built-in service health vs. synthetic).

Not all Davis events carry these fields. External Davis events pushed via the Events API and
some built-in Davis events may have no settings reference.

### One setting, many Davis events

A single settings object can be responsible for one Davis event or thousands,
because a detector's entity selector or DQL query can match any number of
entities. One alerting rule checking 5,000 Kubernetes pods will produce up to
5,000 simultaneous Davis events if all pods breach the threshold at once.

**Implication for over-alerting analysis:** a high Davis event count against one
`dt.settings.object_id` does not automatically mean the setting is misconfigured
— it may simply cover many entities. Always cross-reference the Davis event count with
the number of distinct entities (`dt.smartscape_source.id`) the setting is
actually firing on before concluding that a detector is too broad or too
sensitive.

### Query: alert volume per settings object

```dql
fetch dt.davis.events, from: -24h, to: now()
| filter isNotNull(dt.settings.object_id)
| summarize count = count(), by: {dt.settings.object_id, dt.settings.schema_id, event.name, event.category}
| sort count desc
| limit 100
```

This query is the starting point for identifying which detector configurations
generate the most Davis events. To go deeper, add
`distinctCount(dt.smartscape_source.id) as entity_count` to the summarize clause
— a high `count` combined with a low `entity_count` (many Davis events from few
entities) is a stronger signal of a noisy or over-sensitive detector than raw
volume alone.

---

## DQL Query Patterns

### Active Davis Events

```dql
fetch dt.davis.events, from: -24h
| filter event.status == "ACTIVE"
| fields event.start, event.name, event.category, dt.smartscape_source.id, event.provider
| sort event.start desc
| limit 50
```

### Alert Volume by Category and Status

```dql
fetch dt.davis.events, from: -24h
| summarize count = count(), by: {event.category, event.status}
| sort count desc
```

### Davis Events for a Specific Entity

```dql
fetch dt.davis.events, from: -24h
| filter dt.smartscape_source.id == "SERVICE-XXXXXXXXXX"
| fields event.start, event.end, event.name, event.category, event.status
| sort event.start desc
```

### Alert Frequency Over Time (hourly)

```dql
fetch dt.davis.events, from: -7d
| makeTimeseries alerts = count(), interval: 1h, by: {event.category}
```

### Davis Events That Did NOT Merge Into a Problem

```dql
fetch dt.davis.events, from: -24h
| filter event.status == "CLOSED"
| filter dt.davis.is_merging_allowed == false
| fields event.start, event.end, event.name, dt.smartscape_source.id
| sort event.start desc
| limit 20
```

### Long-Duration Active Davis Events (potential stuck alerts)

```dql
fetch dt.davis.events, from: -7d
| filter event.status == "ACTIVE"
| fieldsAdd duration_h = (now() - event.start) / 1h
| filter duration_h > 2
| fields event.start, event.name, event.category, dt.smartscape_source.id, duration_h
| sort duration_h desc
| limit 20
```

---

## Relationship to Problems

Davis events and problems are separate but linked:

```
Davis event (fetch dt.davis.events)
    │
    │  Davis AI evaluates: same entity? same time window? same root-cause graph?
    │
    └──► Problem (dt.davis.problems) — one problem per correlated Davis event group
```

Key distinctions:

| Dimension | Davis event | Problem |
|-----------|-------------|---------|
| Granularity | One per detector trigger per entity | One per correlated incident |
| Purpose | Raw alert signal | Operational incident view |
| DQL table | `fetch dt.davis.events` | `fetch dt.davis.problems` |
| Deduplication | Every firing creates a new Davis event | `dt.davis.is_duplicate` flags merged copies |
| Useful for | Alert history, detector audit, raw volume | Root cause analysis, impact, notifications |

### Merge logic summary

Davis merges Davis events into one problem when:
1. Active time windows overlap
2. Source entities are the same or topologically related (same host, same call chain)
3. `dt.davis.is_merging_allowed` is `true` on both Davis events

See `dt-obs-problems/references/problem-merging.md` for the full merge decision logic.

---

## Davis Event Lifecycle

```
Detector threshold breached
    │
    ▼
event.status = "ACTIVE", event.start = now()
    │
    │  (if merging allowed and related Davis events exist)
    ▼
Davis creates or extends a Problem — problem groups this Davis event
    │
    │  (threshold no longer breached)
    ▼
event.status = "CLOSED", event.end = now()
    │
    │  (if all contributing Davis events are closed)
    ▼
Problem closes — event.status = "CLOSED" on the problem record
```

A Davis event stays `ACTIVE` as long as the metric remains in violation. If the metric
briefly recovers and then re-violates within the `dealertingWindow`, the same Davis event
stays `ACTIVE` rather than creating a new one — this prevents flapping.
