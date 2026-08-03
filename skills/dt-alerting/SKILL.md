---
name: dt-alerting
description: "End-to-end Dynatrace alerting lifecycle — anomaly detector setup and model selection (static threshold, adaptive baseline, seasonal baseline), alert event storage in Grail, problem grouping and denoising by root cause analysis, and workflow-based notification routing (email, Slack, ServiceNow, webhook). Use when configuring alerting, choosing between detector types, querying alert event history, understanding why alerts merged into a problem, or setting up problem-triggered notifications."
license: Apache-2.0
---

# dt-alerting

Configure and understand the full alerting lifecycle in Dynatrace — from anomaly
detector setup through Grail event storage, problem grouping, and workflow
notification delivery.

## The Alerting Lifecycle

```
┌─────────────────────────────────────────────────────────────────────┐
│  Alert Sources — five categories, each fires a DAVIS_EVENT          │
│  ─────────────────────────────────────────────────────────────────  │
│  1. DQL-based  · Grail-scheduled server-side detector               │
│  2. Edge       · OneAgent on monitored host or process              │
│  3. Pipeline   · OpenPipeline ingest-stream filter matcher          │
│  4. Synthetic  · Worldwide synthetic checker node                   │
│  5. External   · Events API, Workflow, or OneAgent local ingest     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ DAVIS_EVENT created per trigger per entity
                               ▼
             ┌─────────────────────────────────────┐
             │  Event stored in Grail              │  Persisted and queryable via DQL.
             └──────────────────┬──────────────────┘  One event per trigger per entity.
                                │ correlated by root-cause and impact graph
                                ▼
             ┌─────────────────────────────────────┐
             │  Problem (Denoising)                │  Events sharing the same root-cause
             └──────────────────┬──────────────────┘  and impact graph → one Problem.
                                │ problem event triggers workflow
                                ▼
             ┌─────────────────────────────────────┐
             │  Workflow Notification              │  Filters problems and routes to
             └─────────────────────────────────────┘  email, Slack, ServiceNow, webhook.
```

## When to Use This Skill

- **Detector setup** — "How do I create an anomaly detector?", "What kind of
  detector should I use?", "What is the difference between adaptive and seasonal?"
- **Alert event history** — "Query all alert events for this service", "Show me
  which metrics triggered alerts last week"
- **Problem denoising** — "Why did these two alerts merge into one problem?",
  "How does Davis group alerts?"
- **Notification setup** — "How do I send a Slack message when a problem opens?",
  "Set up a ServiceNow ticket on critical problems"
- **Best practices** — "How do I avoid alert storms?", "Which sensitivity setting
  should I use?"
- **Over-alerting analysis** — "Why am I getting too many alerts?", "How do I
  reduce alert fatigue?", "Which detector is firing the most?", "How do I tune
  sensitivity or thresholds to avoid noise?"
- **Notification routing** — "How do I route alerts to the right team?", "Set up
  scalable problem filters in workflows", "Send Slack notifications only to the
  team responsible for the affected service"

## Agent Instructions

**First step for any alerting setup request** — Before recommending a specific
detector or model, load `references/anomaly-detectors.md` and use its category
and model decision guide to identify which detector category (DQL-based, Edge,
Pipeline, Synthetic, External) and which model (Static, Adaptive, Seasonal)
best fits the user's use-case. Only proceed with configuration guidance once
the right detector type has been established.

**Consolidate, don't multiply** — When a user asks to alert on multiple
entities of the same kind (e.g. "alert on services A, B, and C"), always
recommend a **single combined detector** rather than one detector per entity.
Use `by: { <dimension> }` in the DQL `timeseries` call to split results per
entity, and a single `filter:` clause to scope to the relevant entities.
Pair the combined detector with a **routing label of your own** — a custom attribute set on the
event, for which `alert_group` is a sensible naming convention — and filter the notification
workflow on that attribute. Recommend the convention; never assume the attribute already exists. This keeps the
number of detector configs small and makes the workflow channel reusable for entities added
later.

Example for three services — one detector, one workflow:

```dql
timeseries avg(dt.service.request.response_time),
  by: { dt.smartscape.service },
  filter: { in(dt.smartscape.service, {toSmartscapeId("SERVICE-0000000000000001"), toSmartscapeId("SERVICE-0000000000000002"), toSmartscapeId("SERVICE-0000000000000003")}) }
```

If a new service must be covered, add it to the single `filter:` list — no new detector or
workflow rule needed.

> **Naming convention worth suggesting — but create it, don't assume it.** A routing attribute named
> `alert_group` is a good convention to standardize on, and it is reasonable to *recommend* that a
> customer adopt it across detectors, ingested events, and pipeline rules. What matters is that it is
> **an attribute they define and populate**, not something Dynatrace supplies. Always confirm it is
> present on the customer's own records before designing routing around it — an attribute nothing
> sets yields a trigger that silently matches nothing, which is indistinguishable from a quiet estate.

> **⚠️ Unverified as a built-in field — `dt.alert_group`.** Earlier revisions of this skill presented
> `dt.alert_group` as a platform-provided routing field, with per-detector-type assignment
> mechanisms and set-union-on-merge semantics at the problem level. As of 2026-08-03 that field
> **could not be substantiated** against docs.dynatrace.com (workflow trigger pages, anomaly
> detection app), a live tenant's `dt.semantic_dictionary.fields`, or web search. The guidance
> below has been rewritten around the documented trigger surface. **Do not reintroduce
> `dt.alert_group` without a primary source.**

### Intent Mapping

| User Request | Action | Reference |
|---|---|---|
| "how to alert on ...", "create an alert on ...", "create anomaly detector", "set up alerting", "configure alert rule" | Explain detector categories and variants, guide through model selection | anomaly-detectors.md |
| "what kinds of anomaly detectors", "edge alert", "pipeline alert", "synthetic alert", "OneAgent alert" | Explain the five alert source categories and their trade-offs | anomaly-detectors.md |
| "static vs adaptive", "which detector model", "seasonal detector" | Compare models, apply decision guide | anomaly-detectors.md |
| "query alert history", "which alerts fired", "Davis events in Grail" | Query `dt.davis.events` in Grail via `fetch dt.davis.events` | davis-events.md |
| "why did alerts merge", "problem grouping", "denoising" | Do NOT explain merging rules here — load `dt-obs-problems` and refer to `problem-merging.md` for the full merge logic | dt-obs-problems/references/problem-merging.md |
| "send Slack notification", "email on problem", "ServiceNow ticket", "notify on alert" | Explain problem-triggered workflow setup | workflow-notifications.md |
| "alert storm", "too many notifications", "reduce noise" | Filtering strategy, denoising, sensitivity tuning | workflow-notifications.md + anomaly-detectors.md |

> **Analyzing existing problems** — If the user wants to query or investigate
> active/closed problems (root cause, impact, trending), load `dt-obs-problems`
> instead. This skill covers *configuration and flow*, not problem query analytics.

> **Detector health monitoring** — If the user asks whether detectors are
> running or failing, load `dt-platform` (ANALYZER_EXECUTION_EVENT,
> ANOMALY_DETECTOR_STATUS_EVENT). This skill covers *setup*, not operational health.

## Prerequisites

- Access to a Dynatrace environment with Settings v2 write permissions for
  detector configuration
- For querying alert history: DQL permissions on `dt.davis.events`
- Load `dt-dql-essentials` before writing DQL queries

## Knowledge Base Structure

| # | Reference | Content |
|---|-----------|---------|
| 1 | [anomaly-detectors.md](references/anomaly-detectors.md) | Detector types, model selection, configuration, best practices |
| 2 | [davis-events.md](references/davis-events.md) | Davis event storage in Grail, key fields, DQL query patterns |
| 3 | [workflow-notifications.md](references/workflow-notifications.md) | Problem-triggered workflows, filtering, notification channels |

## Key Concepts

### Alert Source Categories

Five fundamental categories of anomaly detectors, distinguished by where detection
runs and how the alert event reaches Dynatrace:

| # | Category | Detection runs on | Latency | Alert logic owner |
|---|----------|-------------------|---------|-------------------|
| 1 | **DQL-based** | Grail (server-side, scheduled) | Minutes | Dynatrace |
| 2 | **Edge** | OneAgent on the monitored host/process | Seconds | Dynatrace (OneAgent) |
| 3 | **Pipeline** | OpenPipeline ingest path (in-stream) | Near-zero | Dynatrace (pipeline rule) |
| 4 | **Synthetic** | Synthetic checker node (worldwide) | Seconds | Dynatrace (synthetic node) |
| 5 | **External** | Customer / external tool | Caller-defined | Customer |

See `references/anomaly-detectors.md` for the full breakdown of each category,
including trade-offs and configuration entry points.

### Detector Models at a Glance

| Model | Threshold | Best for |
|-------|-----------|----------|
| **Static** | Fixed value you define | Known hard limits (e.g. error rate > 5%) |
| **Adaptive baseline** | Learned from recent history | Metrics with no fixed limit but clear normal behavior |
| **Seasonal baseline** | Learned with time-of-day / day-of-week awareness | Traffic, request rate, or any metric with recurring patterns |

### Davis Events vs. Problems

| Concept | Table | Scope |
|---------|-------|-------|
| **Davis event** | `fetch dt.davis.events` | One record per detector trigger per entity |
| **Problem** | `fetch dt.davis.problems` | One record per correlated group of events sharing root-cause and impact |

A single problem typically contains multiple events. Querying problems gives
the operational view; querying events gives the raw alert history.

### Problem Denoising

For questions about why alerts merged into a problem or how Davis groups
events, load `dt-obs-problems` — the merge logic and rules are documented in
`dt-obs-problems/references/problem-merging.md`. This skill covers alert
*configuration and flow* only.

## Quick Start

### Check What Alerts Fired in the Last 24 Hours

```dql
fetch dt.davis.events, from: -24h
| filter event.status == "ACTIVE"
| summarize alert_count = count(), by: {event.name, event.category, dt.smartscape_source.id}
| sort alert_count desc
| limit 20
```

### Check Alert Volume by Category

```dql
fetch dt.davis.events, from: -24h
| summarize count = count(), by: {event.category, event.status}
| sort count desc
```

### See All Active Problems (→ load dt-obs-problems for full query patterns)

```dql
fetch dt.davis.problems, from: -24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| fields event.start, display_id, event.name, event.category
| sort event.start desc
| limit 20
```

## Best Practices

1. **Match the model to the metric's behavior** — Use static for hard SLO
   boundaries, adaptive for metrics without a natural fixed limit, seasonal for
   anything that follows business hours or weekly patterns.
2. **Scope detectors narrowly** — An entity selector that covers only relevant
   entities reduces noise and makes problems more actionable.
3. **Tune sensitivity before going to production** — Start with LOW sensitivity
   and move to MEDIUM or HIGH only after observing false-positive rates.
4. **Use the trigger's `Delay` option to suppress transient problems** — a problem trigger can postpone *"until the problem has been open for at least the configured duration"* (5, 10, 15, 30, 60, 120, 240, 1440, or 10080 minutes), evaluated on `dt.duration_marker`. Note the conflicting upgrade-guide statement that the classic Duration filter has "currently no alternative" — verify in-tenant.
5. **Let Davis denoise before notifying** — Trigger workflow notifications on
   *problems*, not individual alert events. A problem groups correlated alerts
   so you notify once per incident, not once per metric.
6. **Filter notifications by severity level** — Route `event.severity <= 2` problems to
   on-call channels immediately; route `event.severity >= 3` problems to lower-
   urgency channels. Either set severity in the detector config or assign in a pipeline rule or workflow.
6. **Route on a custom attribute you define** — Dynatrace documents no built-in team, owner, or routing-group field on a problem trigger. The documented recommendation is to filter trigger conditions on *"Primary Grail fields, Security context, Custom attributes"* — so set your own routing label where the event is raised (detector event template, Events API payload, or an OpenPipeline enrichment rule) and match it in the workflow's additional custom filter query.
8. **Combine same-condition alerts into one detector and one workflow** — When
   alerting on multiple entities with the same metric and threshold, merge them
   into a single DQL-based detector using `by: { <dimension> }` and a combined
   `filter:` clause. Assign the same routing attribute to every condition in that detector
   and point the workflow notification channel at that single value. One detector + one workflow per logical alert group scales better than
   N detectors + N notification rules, and adding a new entity is a one-line
   filter change rather than a full detector/workflow addition.

## Related Skills

- **dt-obs-problems** — Querying, analyzing, and trending detected problems
- **dt-obs-predictive-analytics** — Ad-hoc anomaly and novelty detection using
  MCP analyzer tools (not persistent alert configs)
- **dt-platform** — Operational health of anomaly detectors (execution events,
  failure rates)
- **dt-platform-costs** — Query costs generated by anomaly detector DQL
- **dt-sdlc-quality-gates** — Site Reliability Guardian for deployment gate alerting
- **dt-dql-essentials** — DQL syntax for writing detector queries and alert history
  queries
