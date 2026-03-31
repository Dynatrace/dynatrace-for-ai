# GenAI Events

Davis CoPilot and MCP Gateway telemetry in `dt.system.events` with
`event.kind == "GENAI_EVENT"`. Track AI skill invocations, MCP tool usage,
performance, and user feedback.

> **Low volume.** Suitable for detailed analysis without aggressive filtering.

## Contents

- [Discovery Query](#discovery-query)
- [Fields](#fields)
- [Event Types](#event-types)
- [Common Workflows](#common-workflows)
- [Best Practices](#best-practices)

## Discovery Query

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "GENAI_EVENT"
| summarize count = count(), by: {event.type, event.provider}
| sort count desc
```

## Fields

### Common Fields (All GenAI Events)

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | timestamp | When the event was recorded |
| `event.kind` | string | Always `"GENAI_EVENT"` |
| `event.type` | string | Event subtype — see [Event Types](#event-types) |
| `event.provider` | string | `"DAVIS_COPILOT"` or `"MCP_GATEWAY"` |
| `status` | string | `"SUCCESSFUL"` or `"FAILED"` |
| `execution_duration_ms` | long | Execution time in milliseconds |
| `user_email` | string | User email |
| `user_id` | string | User UUID |

### Skill Invocation Fields (event.type = "GenAI Skill Invocation")

| Field | Type | Description |
|-------|------|-------------|
| `skill` | string | Skill name (e.g., `"chat"`, `"dql-generation"`) |
| `topic` | string | Conversation topic (e.g., `"Dynatrace platform problems"`) |
| `user_input` | string | User's prompt/question |
| `response` | string | AI-generated response text |
| `supplementary` | string | Context data provided to the skill |
| `client.application_context` | string | App invoking CoPilot (e.g., `"dynatrace.davis.copilot"`) |
| `client.originating_application_context` | string | App where user initiated the request |

> **Sensitive fields:** `user_input`, `response`, and `supplementary` may contain
> user prompts, generated content, or embedded context. Avoid selecting these
> fields in shared dashboards or exports. Follow your data protection policies
> for access and retention.

### MCP Fields (event.type = "MCP Init" / "MCP Tool Invocation")

| Field | Type | Description |
|-------|------|-------------|
| `server` | string | MCP server name (e.g., `"dynatrace-mcp"`) |
| `tool` | string | Tool invoked (e.g., `"ask-dynatrace-docs"`, `"execute-dql-query"`) |
| `session_id` | string | MCP session UUID |

### Feedback Fields (event.type = "GenAI Feedback")

| Field | Type | Description |
|-------|------|-------------|
| `feedback.type` | string | `"positive"` or `"negative"` |
| `feedback.category` | string | Feedback category (e.g., `"incorrect"`, `"helpful"`) |
| `feedback.text` | string | Free-text user feedback |
| `skill` | string | Skill that generated the response |
| `user_input` | string | Original user prompt |
| `response` | string | AI response that received feedback |

## Event Types

| Type | Provider | Description |
|------|----------|-------------|
| `GenAI Skill Invocation` | `DAVIS_COPILOT` | CoPilot skill execution with full prompt/response |
| `MCP Init` | `MCP_GATEWAY` | MCP server session initialization |
| `MCP Tool Invocation` | `MCP_GATEWAY` | MCP tool call with execution details |
| `GenAI Feedback` | `DAVIS_COPILOT` | User feedback on AI responses |

## Common Workflows

### Most Used Skills

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "GENAI_EVENT"
| filter event.type == "GenAI Skill Invocation"
| summarize invocations = count(), avg_duration_ms = avg(execution_duration_ms), by: {skill}
| sort invocations desc
```

### Most Used MCP Tools

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "GENAI_EVENT"
| filter event.type == "MCP Tool Invocation"
| summarize invocations = count(), avg_duration_ms = avg(execution_duration_ms), by: {tool, server}
| sort invocations desc
```

### Failed AI Invocations

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "GENAI_EVENT"
| filter status == "FAILED"
| fields timestamp, event.type, event.provider, skill, tool, user_email, execution_duration_ms
| sort timestamp desc
```

### Slowest Skill Invocations

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "GENAI_EVENT"
| filter event.type == "GenAI Skill Invocation"
| sort execution_duration_ms desc
| fields timestamp, skill, execution_duration_ms, status, user_email, topic
| limit 20
```

### User Adoption

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "GENAI_EVENT"
| filter event.type == "GenAI Skill Invocation"
| summarize invocations = count(), by: {user_email}
| sort invocations desc
| limit 20
```

### Usage Trend

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "GENAI_EVENT"
| summarize invocations = count(), by: {timeframe = bin(timestamp, 1d), event.type}
| sort timeframe asc
```

### User Feedback Analysis

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "GENAI_EVENT"
| filter event.type == "GenAI Feedback"
| fields timestamp, feedback.type, feedback.category, feedback.text, skill, user_email, user_input
| sort timestamp desc
```

### CoPilot Invocations by Originating App

Identify which Dynatrace apps drive the most CoPilot usage:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "GENAI_EVENT"
| filter event.type == "GenAI Skill Invocation"
| summarize invocations = count(), by: {client.originating_application_context}
| sort invocations desc
```

### MCP Session Analysis

Track MCP session lifecycle — init to tool invocations:

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "GENAI_EVENT"
| filter event.provider == "MCP_GATEWAY"
| summarize events = count(), by: {session_id, event.type}
| sort events desc
| limit 20
```

## Best Practices

1. **`response` and `supplementary` can be very large** — Use `substring()` or
   avoid selecting these fields in high-volume queries
2. **Feedback events are rare but high-value** — Monitor negative feedback for
   quality improvement signals
3. **MCP Init + Tool Invocation share `session_id`** — Join on session to
   correlate init with subsequent tool calls
4. **`client.originating_application_context`** — Shows where the user was
   (e.g., problems page) vs `client.application_context` which is always the
   CoPilot app
