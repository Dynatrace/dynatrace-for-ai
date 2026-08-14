# Workflow Notifications

Send targeted notifications when Dynatrace detects a problem by configuring
problem-triggered workflows. Workflows let you filter exactly which problems
notify which channels, avoiding alert storms and routing incidents to the right team.

## Simple Workflows vs. Standard Workflows

Dynatrace distinguishes two tiers of workflows with different licensing and
capability boundaries.

| | Simple workflows | Standard workflows |
|-|-----------------|-------------------|
| **Included in license** | Yes — no additional consumption cost | No — billed according to the Dynatrace rate card |
| **Task limit** | One task per workflow | Multiple tasks, branching, loops |
| **Run JavaScript / Run workflow actions** | Not available | Available |
| **Typical use case** | Problem notification to a single channel | Multi-step automation, cross-system orchestration |
| **AppEngine function invocations** | One invocation billed per task execution | One invocation billed per task execution |

### Simple workflows

A simple workflow consists of **exactly one trigger and one task**. Its primary
purpose is alert notification: react to a problem event and send a message to a
channel (Slack, email, ServiceNow, webhook, etc.). Because simple workflows are
included in the Dynatrace license at no additional cost, they are the right choice
for all standard notification use cases.

**Note on AppEngine billing:** Even though simple workflows do not consume workflow hours,
each task execution consumes one AppEngine function invocation, which is billed
according to the Dynatrace rate card. This applies consistently across both
workflow tiers.

### Standard workflows

A standard workflow can contain **multiple tasks**, conditional branching, loops,
and **Run JavaScript / Run workflow actions** that execute arbitrary logic. Standard workflows are
suited for automation scenarios that go beyond notification: creating and updating
tickets, enriching problem context by calling external APIs, orchestrating
remediation steps, or coordinating changes across multiple systems. Standard
workflow executions are billed according to the Dynatrace rate card.

---

## Contents

- [Simple Workflows vs. Standard Workflows](#simple-workflows-vs-standard-workflows)
- [How Problem Notifications Work](#how-problem-notifications-work)
- [Trigger: Problem Events](#trigger-problem-events)
- [Filtering Which Problems Notify](#filtering-which-problems-notify)
- [Notification Actions](#notification-actions)
- [Routing Patterns](#routing-patterns)
- [Scalable Multi-Team Routing with `dt.alert_group`](#scalable-multi-team-routing-with-dtalert_group)
- [Best Practices](#best-practices)

---

## How Problem Notifications Work

```
Problem opens / updates / closes
         │
         ▼
Workflow trigger fires (event-driven)
         │
         ▼
Condition filter evaluated
   ├─ condition NOT met → workflow stops, no notification sent
   └─ condition met ──────────────────────────────────────────┐
                                                               │
                                                               ▼
                                                   Notification action executes
                                                   (Slack, email, ServiceNow, …)
```

The key design principle: **notify on problems, not on single Davis events**. A problem
groups all related alerts into one incident record. Triggering on problems means
one notification per incident, not one notification per detector firing.

---

## Trigger: Problem Events

Configure the workflow trigger as **"Problem"** in the Workflows UI or via the
Workflows API. The problem trigger ships with five built-in filter options that
control which problems actually activate the workflow.

### Trigger filters

| Filter | Values / behaviour |
|--------|--------------------|
| **Event status** | `Active only` — fires only when a problem opens or updates; `Active and closed` — also fires on resolution |
| **Affected entity tags** | Restricts the trigger to problems whose affected Smartscape entities carry the selected tags. Leave empty to match all entities |
| **Initial root-cause analysis** | When enabled, the trigger waits for Davis to complete its first root-cause and merge run (~1–2 minutes) before firing. **Recommended: enable.** The workflow then receives a fully enriched problem record including root cause, affected entities, and merged events rather than a partially assembled one |
| **Severity** | Numeric filter on `event.severity` (1 = highest, 5 = lowest). Set a maximum severity level to suppress low-priority problems |
| **Additional custom filter** | Accepts a DQL filter-matcher expression for any condition not covered by the filters above. Only the subset of DQL matchers supported by OpenPipeline is valid here — see the [OpenPipeline DQL matcher reference](https://docs.dynatrace.com/docs/shortlink/dql-matcher-openpipeline) |

### Trigger payload fields

The workflow receives the full problem record as its trigger event. Key fields
available for filtering and notification content:

| Field | Description |
|-------|-------------|
| `{{event.id}}` | Problem ID (internal) |
| `{{event.display_id}}` | Human-readable ID (P-XXXXX) |
| `{{event.name}}` | Problem title |
| `{{event.description}}` | Detailed description in Markdown format |
| `{{event.category}}` | AVAILABILITY, ERROR, SLOWDOWN, INFO, RESOURCE, CUSTOM |
| `{{event.status}}` | ACTIVE or CLOSED |
| `{{event.start}}` | Problem start timestamp |
| `{{root_cause_entity_name}}` | Name of the root cause entity |
| `{{dt.davis.affected_users_count}}` | Number of affected end users |
| `{{event.severity}}` | Numeric severity of the problem (1 = highest, 5 = lowest) |
| `{{affected_entity_ids}}` | List of entity IDs for all Smartscape entities affected by the problem |
| `{{affected_entity_names}}` | Array of display names for all Smartscape entities affected by the problem |
| `{{smartscape.affected_entities}}` | Record array of Smartscape entities directly affected by the problem; each record has `id`, `type`, and `name`. May be `null` — see [Filter by affected entity](#filter-by-affected-entity) |
| `{{smartscape.related_entities}}` | Record array of Smartscape entities related to the problem but not directly affected; same `id` / `type` / `name` record shape |
| `{{k8s.cluster.uid}}` | UID of the Kubernetes cluster associated with the affected entities |
| `{{dt.entity.kubernetes_cluster}}` | Entity ID of the Kubernetes cluster associated with the affected entities |
| `{{k8s.workload.name}}` | Name of the Kubernetes workload associated with the affected entities |
| `{{dt.security_context}}` | Security context tag attached to the affected entities, used for scoping access and routing |
| `{{dt.alert_group}}` | Set of routing group names carried by the problem's contributing events |

---

## Filtering Which Problems Notify

Apply a **condition** on the workflow to prevent every problem from triggering
every notification channel. Conditions use the trigger event fields.

### Filter by category

Send to on-call channel only for availability and error problems:

```
in(event.category, {"AVAILABILITY", "ERROR"})
```

Send to capacity team only for resource problems:

```
event.category == "RESOURCE"
```

### Filter by affected entity

To route a problem to the team responsible for a specific entity, filter on
`smartscape.affected_entities`. This is a record array; each record holds the `id`, `type`, and
`name` of one directly affected Smartscape entity.

`[][id]` iterates the array, and `iAny(...)` matches when any element matches. The `id` member is a
`smartscapeId`, so it must be converted with `toString()` before it is compared to a string —
without the conversion the comparison silently evaluates to false and the workflow never fires:

```
iAny(toString(smartscape.affected_entities[][id]) == "SERVICE-abc123def456")
```

`iAny`, `toString`, `matchesPhrase`, and `==` are all part of the OpenPipeline matcher subset that
the trigger's **Additional custom filter** accepts.

**Do not filter on `root_cause_entity_id`** — Davis may not detect or populate
a root cause for every problem (especially early in the problem lifecycle or for
externally ingested events). Filtering on `root_cause_entity_id` will silently
miss problems where the field is absent.

**`smartscape.affected_entities` is not present on every problem either.** A problem carries
affected entities only when it is scoped to entities in the first place. These cases produce a
`null` array.

For team-level routing that does not depend on a specific entity ID, prefer
filtering on `dt.alert_group` (see [Scalable Multi-Team Routing](#scalable-multi-team-routing-with-dtalert_group)):

```
matchesPhrase(dt.alert_group, "sev1_slack")
```

### Combining conditions

On-call page only for high-impact availability problems in production:

```
event.category == "AVAILABILITY" AND event.severity == 1
```

---

## Notification Actions

Connect the workflow to a notification connector. Dynatrace ships built-in
connectors for common channels; additional channels are available via the HTTP
request action.

### Email

**Action:** `Send email`

Recommended fields to include in the email body:
- Problem title: `{{event.name}}`
- Category: `{{event.category}}`
- Start time: `{{event.start}}`
- Root cause: `{{root_cause_entity_name}}`
- Affected users: `{{dt.davis.affected_users_count}}`
- Direct link: `{{ problem_link() }}`

### Slack

**Action:** `Send Slack message` via Slack connector

Structure the message for quick triage:

```
🔴 *{{event.category}} Problem Detected*
*{{event.name}}*
Root cause: {{root_cause_entity_name}}
Affected users: {{dt.davis.affected_users_count}}
Started: {{event.start}}
<{{ problem_link() }}|View in Dynatrace>
```

Use Slack `blocks` for richer formatting. Route to different channels by
filtering on `dt.alert_group` or `event.severity` in the workflow condition
rather than maintaining separate channel mappings in action configuration.

### ServiceNow

**Action:** `Create ServiceNow incident` via ServiceNow connector

Map fields:
| ServiceNow field | Dynatrace source |
|-----------------|-----------------|
| `short_description` | `{{event.name}}` |
| `description` | `{{event.description}}` |
| `urgency` | Derived from `{{event.severity}}` (maps directly: severity 1 → urgency 1, etc.) |
| `assignment_group` | Derived from `{{dt.alert_group}}` (use the group name that identifies the owning team) |
| `work_notes` | Include Dynatrace problem URL |

Add a separate workflow with the same problem trigger and condition `event.status == "CLOSED"` to automatically close or resolve the ServiceNow ticket on resolution.

### Webhook / HTTP Request

**Action:** `HTTP request`

Use this for any system without a built-in connector (PagerDuty, OpsGenie,
Jira, MS Teams, custom endpoints).

```text
POST https://your-endpoint.example.com/alert
Content-Type: application/json

{
  "problemId": "{{event.display_id}}",
  "title": "{{event.name}}",
  "category": "{{event.category}}",
  "status": "{{event.status}}",
  "rootCause": "{{root_cause_entity_name}}",
  "affectedUsers": "{{dt.davis.affected_users_count}}",
  "url": "{{ problem_link() }}"
}
```

---

## Scalable Multi-Team Routing with `dt.alert_group`

For environments with many teams and many detectors, maintaining per-team
per-detector workflow conditions quickly becomes unmanageable. The recommended
scalable alternative is to standardize routing on two fields: **`dt.alert_group`**
for team-level routing and **`event.severity`** for urgency-based routing.

### How it works

1. **At the alert source**, set the `dt.alert_group` field to a routing target
   identifier when the alert event is raised. The exact mechanism depends on the
   detector type:
   - For Davis anomaly detectors (`builtin:davis.anomaly-detectors`): set
     `dt.alert_group` as a custom property in the `eventTemplate` of the detector
     configuration
   - For externally ingested events: include `dt.alert_group` in the event
     payload sent to the Events API v2
   - For OpenPipeline-sourced events: add a field enrichment rule that sets
     `dt.alert_group`

2. **Dynatrace stores the field**: the `dt.alert_group` value is carried through
   to the Davis event and persisted in Grail as part of the event record. It is
   available as a filter field on the workflow trigger.

3. **Each team's workflow filters on its own `dt.alert_group` value**: the
   workflow condition simply checks `matchesPhrase(dt.alert_group, "<target>")`. Any alert
   event with that routing label activates the workflow; all others are ignored.

### Field semantics: sets and problem-level merging

`dt.alert_group` is not a single string — it is a **set of one or more group
names**. A single event can carry multiple routing targets simultaneously (e.g.
`["slack_sev1", "pagerduty_oncall"]`), and a workflow whose filter matches any
member of that set will activate.

When Davis AI groups multiple contributing events into one problem, the
`dt.alert_group` values from **all** constituent events are **merged into a
combined set** at the problem level. The problem's `dt.alert_group` field is the
union of every group name carried by any of its events. This means:

- A problem that merges events from two different detectors — each with its own
  `dt.alert_group` value — will activate the workflows of **both** routing targets
- A team whose workflow filters on their group name receives the notification even
  if their detector's event was not the root cause, only a contributing event

This merge behaviour is intentional: it ensures that every team whose detector
contributed to a problem is notified, regardless of how Davis grouped or ranked
the contributing events.

### Example

A detector responsible for Sev 1 Slack notifications sets:

```
dt.alert_group = "slack_sev1"
```

The on-call team's workflow uses the **Additional custom filter** on the problem
trigger:

```
matchesPhrase(dt.alert_group, "slack_sev1")
```

Every problem that contains an event carrying `dt.alert_group = "slack_sev1"`
activates that workflow and is delivered to the team's Slack channel — without
the workflow needing to know anything about which specific detector fired or
which entity was affected.

### Why this scales

| Approach | New team onboarding | New detector onboarding |
|----------|--------------------|-----------------------|
| Per-detector conditions | Add a new condition branch to every affected workflow | Update every workflow that should receive the new alert |
| `dt.alert_group` + `event.severity` routing | Team creates one workflow, filters on their `dt.alert_group` value and desired severity range | Detector sets `dt.alert_group`; no workflow changes needed |

Once a team has a workflow that filters on its `dt.alert_group` value, routing
any new alert to that team requires only setting the correct `dt.alert_group` on
the detector. The workflow is unchanged. This decouples detector authorship from
notification routing and makes both independently maintainable.

---

## Best Practices

1. **Trigger on problems, not Davis events** — Davis denoises multiple detector
   firings into one problem. Triggering on raw events bypasses denoising and
   floods channels.

2. **Always filter by at least one condition** — An unconditional workflow notifies
   on every problem in the environment. Start with `dt.alert_group` for team
   routing and `event.severity` for urgency filtering at minimum.

3. **Separate workflows per team using `dt.alert_group`** — One workflow per team
   filtering on their `dt.alert_group` value is easier to maintain and debug than
   one mega-workflow with complex branching.

4. **Include the problem URL in every notification** — use `{{ problem_link() }}`
   so recipients can navigate to the problem in one click.

5. **Handle the resolution event** — Always pair an open-notification workflow
   with a close-notification. Responders need to know when the incident is resolved,
   not just when it opened.

6. **Test with a low-severity detector first** — Create a CUSTOM category detector
   with a threshold that will fire in a test environment to validate the full
   workflow before connecting production alerts to on-call systems.

7. **Never filter on `root_cause_entity_id`** — Davis does not always detect or
   populate a root cause, especially for externally ingested events or early in
   the problem lifecycle. Use
   `iAny(toString(smartscape.affected_entities[][id]) == "<entity-id>")` to target a specific
   entity, or `matchesPhrase(dt.alert_group, "<group>")` for team-based routing. Prefer
   `dt.alert_group`: `smartscape.affected_entities` is `null` for problems that are not scoped to
   entities, so an entity condition silently skips them. Omitting `toString()` also makes the
   comparison silently false, because `id` is a `smartscapeId` rather than a string.

8. **Use workflow execution history for debugging** — Navigate to
   **Automation → Workflows → [your workflow] → Executions** to see the full
   payload, condition result, and action output for each triggered run.
