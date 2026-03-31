# Automation Events

Workflow automation telemetry in `dt.system.events` with
`event.kind == "WORKFLOW_EVENT"`. Track workflow executions, task/action
performance, failure rates, and lifecycle events.

> **High volume.** Each workflow execution, task execution, and
> action execution emits separate events.

## Contents

- [Discovery Query](#discovery-query)
- [Fields](#fields)
- [Event Types](#event-types)
- [Common Workflows](#common-workflows)
  - [Workflow Execution Overview](#workflow-execution-overview)
  - [Failed Workflows](#failed-workflows)
  - [Workflow Error Rate by Workflow](#workflow-error-rate-by-workflow)
  - [Slowest Workflows](#slowest-workflows-by-duration)
  - [Most Active Workflows](#most-active-workflows)
  - [Trigger Type Analysis](#trigger-type-analysis)
  - [Action App Usage](#action-app-usage)
  - [Execution Volume Trend](#execution-volume-trend)
  - [Sub-Workflow Detection](#sub-workflow-detection)
  - [Throttled Workflows](#throttled-workflows)
  - [Workflow Lifecycle Events](#workflow-lifecycle-events)
- [Best Practices](#best-practices)

## Discovery Query

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "WORKFLOW_EVENT"
| summarize count = count(), by: {event.type}
| sort count desc
```

## Fields

### Common Fields (All Workflow Events)

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | timestamp | When the event was recorded |
| `event.kind` | string | Always `"WORKFLOW_EVENT"` |
| `event.type` | string | Event subtype — see [Event Types](#event-types) |
| `event.id` | string | Unique event identifier |
| `event.provider` | string | Always `"AUTOMATION_ENGINE"` |
| `dt.automation_engine.workflow.id` | string | Workflow UUID |
| `dt.automation_engine.workflow.title` | string | Workflow display name |
| `dt.automation_engine.workflow_execution.id` | string | Execution instance UUID |
| `dt.automation_engine.root_workflow.id` | string | Top-level workflow ID (differs from `workflow.id` for sub-workflows) |
| `dt.automation_engine.root_workflow_execution.id` | string | Top-level execution ID |
| `dt.automation_engine.state` | string | `"RUNNING"`, `"SUCCESS"`, `"ERROR"`, `"CANCELLED"` |
| `dt.automation_engine.state.is_final` | boolean | `true` when execution is complete |
| `dt.automation_engine.is_draft` | boolean | `true` for draft workflow executions |
| `duration` | duration | Execution duration (nanosecond precision) |
| `start_time` | timestamp | Execution start |
| `end_time` | timestamp | Execution end (final states only) |

### Execution-Type-Specific Fields

**WORKFLOW_EXECUTION additional fields:**

| Field | Type | Description |
|-------|------|-------------|
| `dt.automation_engine.workflow.type` | string | `"STANDARD"` |
| `dt.automation_engine.workflow.last_execution_state_flip` | boolean | State changed from previous execution |
| `dt.automation_engine.workflow_execution.actor` | string | User UUID who triggered the workflow |
| `dt.automation_engine.workflow_execution.trigger.type` | string | Trigger type (e.g., `"Event"`, `"Schedule"`) |
| `dt.automation_engine.workflow_execution.trigger.event.id` | string | Triggering event ID |
| `dt.automation_engine.workflow_execution.trigger.event.timestamp` | double | Triggering event timestamp (epoch ns) |

**ACTION_EXECUTION / TASK_EXECUTION additional fields:**

| Field | Type | Description |
|-------|------|-------------|
| `dt.automation_engine.task.name` | string | Task name within the workflow |
| `dt.automation_engine.action.app` | string | App providing the action (ACTION_EXECUTION only) |
| `dt.automation_engine.action.function` | string | Function name (ACTION_EXECUTION only) |
| `dt.automation_engine.action_execution.id` | string | Action execution UUID (ACTION_EXECUTION only) |
| `dt.automation_engine.action_execution.retry.count` | long | Retry attempt number (ACTION_EXECUTION only) |
| `dt.automation_engine.state_info` | string | Error details (when state is `"ERROR"`) |

## Event Types

| Type | Description |
|------|-------------|
| `ACTION_EXECUTION` | Individual action step within a task. Emitted at RUNNING and final state. |
| `TASK_EXECUTION` | Task-level execution (contains one or more actions). Emitted at RUNNING and final state. |
| `WORKFLOW_EXECUTION` | Top-level workflow run. Emitted at RUNNING and final state. |
| `WORKFLOW_UPDATED` | Workflow definition modified |
| `WORKFLOW_THROTTLED` | Workflow execution was rate-limited |
| `WORKFLOW_CREATED` | New workflow created |
| `WORKFLOW_DELETED` | Workflow deleted |

### State Distribution

| State | Description |
|-------|-------------|
| `RUNNING` | Execution in progress (non-final) |
| `SUCCESS` | Completed successfully |
| `ERROR` | Failed with error |
| `CANCELLED` | Manually cancelled |

> **Note:** Each execution emits at least two events — one at `RUNNING` and one
> at the final state. Filter `dt.automation_engine.state.is_final == true` for
> completed executions only.

## Common Workflows

### Workflow Execution Overview

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "WORKFLOW_EVENT"
| filter event.type == "WORKFLOW_EXECUTION"
| filter dt.automation_engine.state.is_final == true
| summarize executions = count(), by: {dt.automation_engine.state}
```

### Failed Workflows

```dql
fetch dt.system.events, from: -24h
| filter event.kind == "WORKFLOW_EVENT"
| filter event.type == "WORKFLOW_EXECUTION"
| filter dt.automation_engine.state == "ERROR"
| filter dt.automation_engine.state.is_final == true
| fields timestamp, dt.automation_engine.workflow.title, dt.automation_engine.workflow.id, dt.automation_engine.workflow_execution.id, duration
| sort timestamp desc
| limit 20
```

### Workflow Error Rate by Workflow

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "WORKFLOW_EVENT"
| filter event.type == "WORKFLOW_EXECUTION"
| filter dt.automation_engine.state.is_final == true
| summarize total = count(), errors = countIf(dt.automation_engine.state == "ERROR"), by: {dt.automation_engine.workflow.title, dt.automation_engine.workflow.id}
| fieldsAdd error_rate = 100.0 * errors / total
| sort error_rate desc
| limit 20
```

### Slowest Workflows (by Duration)

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "WORKFLOW_EVENT"
| filter event.type == "WORKFLOW_EXECUTION"
| filter dt.automation_engine.state.is_final == true
| filter dt.automation_engine.state == "SUCCESS"
| fieldsAdd duration_sec = toDouble(duration) / 1000000000
| sort duration_sec desc
| fields timestamp, dt.automation_engine.workflow.title, duration_sec, dt.automation_engine.workflow.id
| limit 20
```

### Most Active Workflows

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "WORKFLOW_EVENT"
| filter event.type == "WORKFLOW_EXECUTION"
| filter dt.automation_engine.state.is_final == true
| summarize executions = count(), by: {dt.automation_engine.workflow.title, dt.automation_engine.workflow.id}
| sort executions desc
| limit 20
```

### Action App Usage

Identify which automation apps and functions are most used:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "WORKFLOW_EVENT"
| filter event.type == "ACTION_EXECUTION"
| filter dt.automation_engine.state.is_final == true
| summarize executions = count(), errors = countIf(dt.automation_engine.state == "ERROR"), by: {dt.automation_engine.action.app, dt.automation_engine.action.function}
| sort executions desc
| limit 20
```

### Trigger Type Analysis

Identify how workflows are triggered (Event, Schedule, Manual, etc.):

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "WORKFLOW_EVENT"
| filter event.type == "WORKFLOW_EXECUTION"
| filter dt.automation_engine.state.is_final == true
| summarize executions = count(),
    errors = countIf(dt.automation_engine.state == "ERROR"),
    by: {dt.automation_engine.workflow_execution.trigger.type}
| fieldsAdd error_rate = 100.0 * errors / executions
| sort executions desc
```

### Execution Volume Trend

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "WORKFLOW_EVENT"
| filter event.type == "WORKFLOW_EXECUTION"
| filter dt.automation_engine.state.is_final == true
| summarize executions = count(), by: {timeframe = bin(timestamp, 1h), dt.automation_engine.state}
| sort timeframe asc
```

### Sub-Workflow Detection

Identify workflows running as children of other workflows:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "WORKFLOW_EVENT"
| filter event.type == "WORKFLOW_EXECUTION"
| filter dt.automation_engine.state.is_final == true
| filter dt.automation_engine.root_workflow.id != dt.automation_engine.workflow.id
| fields timestamp, dt.automation_engine.workflow.title, dt.automation_engine.workflow.id, dt.automation_engine.root_workflow.id, dt.automation_engine.state
| sort timestamp desc
| limit 20
```

### Throttled Workflows

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "WORKFLOW_EVENT"
| filter event.type == "WORKFLOW_THROTTLED"
| fields timestamp, dt.automation_engine.workflow.title, dt.automation_engine.workflow.id
| sort timestamp desc
```

### Workflow Lifecycle Events

Track creation, update, and deletion of workflow definitions:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "WORKFLOW_EVENT"
| filter in(event.type, "WORKFLOW_CREATED", "WORKFLOW_UPDATED", "WORKFLOW_DELETED")
| fields timestamp, event.type, dt.automation_engine.workflow.title, dt.automation_engine.workflow.id
| sort timestamp desc
```

## Best Practices

1. **Always filter `state.is_final == true` for counts** — Each execution emits
   RUNNING + final state events; counting without filtering doubles the numbers
2. **Duration is Grail type `duration`** — Nanosecond precision. Divide by
   `1000000000` for seconds. Use `toDouble(duration) / 1000000000` for
   fractional seconds (plain division truncates to integer).
3. **Sub-workflows** — Compare `root_workflow.id` vs `workflow.id` to
   distinguish top-level from nested executions
4. **Lifecycle events lack state fields** — `WORKFLOW_CREATED`, `WORKFLOW_UPDATED`,
   `WORKFLOW_DELETED` are definition changes, not executions
