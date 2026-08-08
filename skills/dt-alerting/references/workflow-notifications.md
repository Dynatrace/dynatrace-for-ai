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
- [Scalable Multi-Team Routing](#scalable-multi-team-routing)
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

The documented problem-trigger configuration options:

| Filter | Values / behaviour |
|--------|--------------------|
| **Problem state** | Active only; or active and closed |
| **Event category** | Which Davis categories activate the workflow |
| **Severity** | Filters by level threshold |
| **Affected entities** | Tag-based — all entities, all defined tags, or any defined tag |
| **Delay** *(advanced)* | Postpones *"the trigger until the problem has been open for at least the configured duration."* Allowed values in minutes: 5, 10, 15, 30, 60, 120, 240, 1440, 10080. Evaluated on `dt.duration_marker`, *"a field set by Dynatrace Intelligence that accumulates from the moment the problem was first created."* *"The trigger fires once when the threshold is crossed on the active phase and, if selected, also once on closure."* |
| **Updates** *(advanced)* | Re-trigger when selected fields change |
| **Additional custom filter query** *(advanced)* | A DQL matcher over the problem record |

There is **no management-zone filter, no segment filter, and no built-in team / owner /
routing-group field.**

> **Conflict to be aware of.** The alert-notification upgrade guide states the classic **Duration**
> filter is *"No longer supported. Currently there is no alternative to deliver problems that are
> active longer than X minutes"* — while the trigger documentation describes the **Delay** option
> above, which does exactly that. Both were live 2026-08-03. Most likely the upgrade guide predates
> Delay and was not re-tensed, but verify in-tenant rather than repeating either claim as settled.

Source: [Event triggers for workflows (DT docs)](https://docs.dynatrace.com/docs/analyze-explore-automate/workflows/trigger/event-trigger).

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
| `{{k8s.cluster.uid}}` | UID of the Kubernetes cluster associated with the affected entities |
| `{{dt.entity.kubernetes_cluster}}` | Entity ID of the Kubernetes cluster associated with the affected entities |
| `{{k8s.workload.name}}` | Name of the Kubernetes workload associated with the affected entities |
| `{{dt.security_context}}` | Security context tag attached to the affected entities |

> **Verify payload field names against your own trigger before using them.** This table has not been
> re-confirmed field-by-field against primary documentation; treat unfamiliar entries as unverified.

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
`smartscape.affected_entity.ids`. This field is reliably populated for all problems
and contains the entity IDs of every Smartscape entity directly affected.

```
matchesPhrase(smartscape.affected_entity.ids, "SERVICE-abc123def456")
```

**Verify a field exists on your own problem records before filtering on it.** Davis does not
populate every field on every problem — a root cause in particular may be absent early in the
lifecycle or for externally ingested events, so a condition built on one silently drops those
problems. Several entity-array field names in circulation are undocumented; confirm before use.

For team-level routing that does not depend on a specific entity, filter on a **custom attribute you
set** (see [Scalable Multi-Team Routing](#scalable-multi-team-routing)):

```
matchesValue(<your-routing-attribute>, "<team>")
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
filtering on your routing attribute or `event.severity` in the workflow condition
rather than maintaining separate channel mappings in action configuration.

### ServiceNow

**Action:** `Create ServiceNow incident` via ServiceNow connector

Map fields:
| ServiceNow field | Dynatrace source |
|-----------------|-----------------|
| `short_description` | `{{event.name}}` |
| `description` | `{{event.description}}` |
| `urgency` | Derived from `{{event.severity}}` (maps directly: severity 1 → urgency 1, etc.) |
| `assignment_group` | Derived from your routing attribute (the value identifying the owning team) |
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

## Scalable Multi-Team Routing

**Reach for Ownership first — it is the built-in mechanism.** *"Ownership assignment is based on tags.
Tags are key-value pairs stored in Smartscape nodes."* Dynatrace ships `owner` and `dt.owner` as default
keys in every monitoring environment, plus up to three custom keys, assignable via Kubernetes labels,
`oneagentctl --set-host-property owner-1=team-automation`, or process-group environment variables.
Because ownership is entity tags, the problem trigger's **affected-entity tag filter** routes on it
directly — no DQL required.

Two further pieces:

- **Carrying ownership on the event.** Set `dt.owner` as an event property on the alert configuration
  (documented example `"dt.owner": "app-team-us-23"`), then map it onto the problem via
  **Settings → Dynatrace Intelligence → Root cause analysis → Problem fields**. Without that mapping the
  field never reaches the problem record and the trigger silently matches nothing. The mapping is **not
  retroactive**: *"Problem records in Grail are immutable … previously recorded problems that were closed
  before the modifications will not change."* Create it before any parallel-run window, not during one.
  The docs do **not** specify a field-count limit, what happens when merged events carry conflicting
  values for the same field, or how array-valued fields behave — test, do not assume. (An earlier
  revision of this skill asserted set-union-on-merge semantics here; that was never documented.)
- **Contact details at run time.** The Ownership app's `get_owners` action returns *"ownership team info
  with contact details for Slack/Teams/Email/JIRA"*, so one workflow can route dynamically instead of one
  workflow per team. `import_teams` *"imports and auto-syncs ownership team data … and accepts info from
  ServiceNow and Entra ID."*

> **⚠️ "Available" is not "populated."** The default keys existing says nothing about whether any entity
> carries an owner, whether team records exist, whether contact details are filled in, or whether the
> Problem fields mapping was ever created. Measure coverage before designing routing on it — e.g.
> `smartscapeNodes "HOST" | fieldsAdd o = tags[\`dt.owner\`] | summarize count(), by:{isNotNull(o)}`.
> On the tenant used to verify this (2026-08-03) the answer was **zero of 8 hosts**. Unpopulated
> ownership yields workflows that never fire, which is indistinguishable from a quiet estate.

### Visibility is a different axis — do not solve it with a trigger

A trigger condition decides whether a *notification fires*. It does not decide who may **read** the
problem. Reading is an IAM **policy boundary**, e.g. `storage:dt.security_context IN ("app-23");`
attached to an **Event Read** permission and assigned to a user group — *"This allows you to segregate
and manage access to the Dynatrace Grail data lake based on reading permissions for various user
groups."*

Note the asymmetry with `dt.owner`: *"All fields that occur on single violation events and are defined
by the Dynatrace permission system as record permissions are automatically mapped onto problems."* So
`dt.security_context` needs **no** Problem fields mapping — but it does still have to be set on the
events. The docs make no statement about arrays, multiple contributing values, or conflict resolution
here; do not assume behavior an earlier revision of this skill asserted.

Where ownership genuinely does not fit, team routing is something you construct.

The documented guidance is to filter trigger conditions on *"Primary Grail fields, Security context,
Custom attributes."* In practice that gives three routing dimensions:

| Dimension | Where it comes from | How the trigger uses it |
|---|---|---|
| **Affected-entity tags** | Your tagging standard, propagated onto entities | First-class trigger option |
| **Severity** | Set on the detector, or assigned downstream | First-class trigger option |
| **A custom attribute** | A routing label *you* define and set at the alert source | Additional custom filter query |

Set the custom attribute where the event is raised — a detector's event template, an Events API v2
payload, or an OpenPipeline enrichment rule — then match it in the workflow's additional custom
filter query with `matchesValue`.

**Suggest a name, and say plainly that it must be created.** `alert_group` is a good convention and
worth recommending, because the pattern's whole value comes from every alert source using the *same*
attribute name. But it is a customer-defined attribute, not a Dynatrace-provided field: it will not
appear on any event until something sets it. Verify it is populated on real records before a
workflow depends on it — a trigger matching an attribute nothing sets never fires, and looks exactly
like a healthy quiet estate.

**Why this scales:** onboarding a new detector to an existing team becomes a matter of setting the
same attribute on it; the workflow is unchanged. Detector authorship and notification routing stay
independently maintainable.

> **Matcher surface differs per context.** The DQL matcher is a restricted subset of DQL, not full
> DQL. Its core functions are `matchesPhrase`, `matchesValue`, `isNotNull`, `isNull` with logical
> operators. Support beyond that varies by surface — do not assume numeric comparisons or iterative
> expressions are available in a workflow trigger. Confirm in the trigger UI.

Sources: [Alerting and notifications (DT docs)](https://docs.dynatrace.com/docs/analyze-explore-automate/alerting-and-notifications),
[DQL matcher in OpenPipeline (DT docs)](https://docs.dynatrace.com/docs/platform/openpipeline/reference/dql/dql-matcher-in-openpipeline).

## Best Practices

1. **Trigger on problems, not Davis events** — Davis denoises multiple detector
   firings into one problem. Triggering on raw events bypasses denoising and
   floods channels.

2. **Always filter by at least one condition** — An unconditional workflow notifies
   on every problem in the environment. Start with affected-entity tags or a custom routing
   attribute for team routing, and `event.severity` for urgency filtering, at minimum.

3. **Separate workflows per team** — One workflow per team, filtering on that team's routing
   value, is easier to maintain and debug than one mega-workflow with complex branching.

4. **Include the problem URL in every notification** — use `{{ problem_link() }}`
   so recipients can navigate to the problem in one click.

5. **Handle the resolution event** — Always pair an open-notification workflow
   with a close-notification. Responders need to know when the incident is resolved,
   not just when it opened.

6. **Test with a low-severity detector first** — Create a CUSTOM category detector
   with a threshold that will fire in a test environment to validate the full
   workflow before connecting production alerts to on-call systems.

7. **Verify any field name before building a condition on it.** Davis does not populate every
   field on every problem, and several field names in circulation are not documented. Check the
   field exists on your own problem records before a workflow depends on it.

8. **Use workflow execution history for debugging** — Navigate to
   **Automation → Workflows → [your workflow] → Executions** to see the full
   payload, condition result, and action output for each triggered run.
