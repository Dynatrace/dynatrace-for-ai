# Agent Signals Reference

GenAI agents instrumented with OpenTelemetry GenAI semantic conventions emit spans not only for LLM calls but also for each tool invocation, agent step, and agent lifecycle event. These agent signals let you answer: which tools are called most, which agents are failing, how long individual steps take, and whether any agent is looping on the same tool.

| Signal | Span attribute | Notes |
|---|---|---|
| Operation type | `gen_ai.operation.name` | `execute_tool` for tool calls; `invoke_agent` for agent invocations; `create_agent` for agent creation |
| Tool name | `gen_ai.tool.name` | Name of the tool invoked on `execute_tool` spans |
| Agent name | `gen_ai.agent.name` | Name of the agent; null on `execute_tool` spans in the reference data |
| Failure | `span.status_code == "error"` | Do not use `request.is_failed` (always `0` for GenAI spans) |
| Latency | `duration` | Grail duration value — divide by the `1ms` literal (`duration / 1ms`) for a numeric millisecond value |
| Trace correlation | `trace.id` | Links tool calls and agent spans within the same conversation turn |
| Time bucketing | `start_time` | Use `start_time` for time-series grouping — `timestamp` is null for these spans |

> **Provider note:** `gen_ai.operation.name` is null on many Amazon Bedrock spans but is reliably populated on agent-framework spans (`execute_tool`, `invoke_agent`, `create_agent`). Where needed, `span.name` (e.g., `execute_tool <toolname>`) is a reliable cross-provider fallback.

> **Tool failure nuance:** In the reference data, `execute_tool` spans carry no error status — failures surface on `chat` and `invoke_agent` spans instead. Filtering `execute_tool` for `span.status_code == "error"` returns zero rows. To identify which agents are failing, filter at the GenAI-span level for errors with a populated `gen_ai.agent.name`. See [Failing agent activity](#failing-agent-activity) for the correct approach.

---

## Presence check

Before trusting an empty result, confirm the app is **truly agentic**. Smartscape extracts a `GENAI_AGENT` entity for every instrumented agent, so a single topology read confirms it without scanning span volume. Run this once when you're unsure or a query comes back empty — not before every query.

```dql
smartscapeNodes "GENAI_AGENT"
```

**How to read it:** If this returns rows, the app is agentic and the queries below have data. **Zero rows** means the service is not agentic — it only generates LLM responses (plain `chat` calls), which is an *architectural* fact. In this case, report "no agent signals available", **not** "no failing agents".

---

## Tool usage

Which tools are called most often. Use this to understand the tool call distribution across your agent fleet, identify unexpectedly high call rates, and spot tools that may be driving cost or latency.

```dql
fetch spans, from: now()-24h
| filter gen_ai.operation.name == "execute_tool"
| summarize calls = count(), by: {gen_ai.tool.name}
| sort calls desc
```

**How to read it:** Each row is one tool. `calls` is the total number of times that tool was invoked in the time window. Tools at the top of the list are the highest-frequency entry points into external systems. An unusually high count for a single tool may indicate a retry loop or a misconfigured routing agent.

**Tip:** Add `gen_ai.provider.name` to the `by:` clause to see whether the same tool is invoked via multiple provider backends. To measure tool latency, add `p95_ms = percentile(duration, 95) / 1ms` to the `summarize` step — slow tools are often network-bound external API calls.

---

## Failing agent activity

Error rate and absolute error count for each agent. Use this to identify the most error-prone agents, compare relative error rates, and prioritize which agent to investigate first.

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.agent.name)
| summarize total = count(), errors = countIf(span.status_code == "error"), by: {gen_ai.agent.name}
| fieldsAdd error_rate_pct = if(total > 0, errors * 100.0 / total, else: 0.0)
| sort errors desc
```

**How to read it:** Each row is one agent. `errors` is the absolute count of failed spans for that agent; `error_rate_pct` is the share of spans that ended in error. An agent with a high absolute error count but low rate may be healthy at scale — sort by `error_rate_pct` to prioritise agents that are failing disproportionately. An agent with both a high rate and high absolute count is the primary candidate for root-cause investigation.

**Not every error is a real failure — break errors down by exception type.** A raw `span.status_code == "error"` count can overstate how unstable an agent is, because some exception types are normal control flow rather than faults. The exception detail lives on the span's events. This query reads the `span.events` array; if `span.events` is null across the fleet it returns zero rows — skip it and rely on the agent-level error count above. Run it exactly as written: the `expand` + `fieldsFlatten` sequence on `span.events` is order-sensitive, and reordering or omitting either step returns zero rows or errors.

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.agent.name) and span.status_code == "error"
| filter iAny(span.events[][span_event.name] == "exception")
| expand span.events
| fieldsFlatten span.events, fields: { exception.type }
| summarize errors = count(), by: {gen_ai.agent.name, exception_type = exception.type}
| sort errors desc
```

**How to read it:** Each row is one agent + exception type. Separate genuine faults (e.g. `openai.APIConnectionError`, `openai.AuthenticationError`) from framework control-flow signals. With LangGraph, `langgraph.errors.ParentCommand` is emitted on normal agent-to-agent handoffs — it is not a failure, and counting it inflates a supervisor/orchestrator agent's apparent error rate. Decide per exception type whether it counts as an error before concluding an agent is unstable.

**Confirming the empty execute_tool-error baseline:** The following query is included for diagnostic purposes. If it returns rows in your environment, your instrumentation does propagate errors onto tool spans, and you can filter `execute_tool` directly for failures.

```dql
fetch spans, from: now()-24h
| filter gen_ai.operation.name == "execute_tool"
| filter span.status_code == "error"
| summarize errors = count(), by: {gen_ai.tool.name}
| sort errors desc
```

### Drill into a specific failed run

To go from a failing agent to the exact run, take the `trace.id` of an erroring span and open that trace in the Dynatrace distributed-tracing view — the erroring agent span and its `execute_tool` spans share the same `trace.id`. First surface candidate traces:

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.agent.name) and span.status_code == "error"
| fields start_time, gen_ai.agent.name, span.name, trace.id
| sort start_time desc
| limit 20
```

Then filter to one trace. **`trace.id` is a `uid` type** — use `filter trace.id == toUid("<hex>")` (or `filter toString(trace.id) == "<hex>"`). A plain `trace.id == "<hex>"` comparison **silently returns zero rows**, which looks like a broken drill-in rather than a type mismatch.

```dql
fetch spans, from: now()-24h
| filter trace.id == toUid("<hex>")
| fields start_time, span.name, gen_ai.operation.name, gen_ai.agent.name, gen_ai.tool.name, span.status_code
| sort start_time asc
```

---

## LLM call failures

The [Failing agent activity](#failing-agent-activity) query filters on `gen_ai.agent.name`, which is null on plain `chat` (LLM) spans — so it does **not** cover LLM calls that fail outside an agent context. A question about "agents *and* LLM calls failing" needs this query too: drop the agent filter and group by model.

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.request.model)
| summarize total = count(), errors = countIf(span.status_code == "error"), by: {gen_ai.request.model, gen_ai.provider.name}
| fieldsAdd error_rate_pct = if(total > 0, errors * 100.0 / total, else: 0.0)
| sort errors desc
```

**How to read it:** Each row is a model+provider combination across all GenAI spans (including `chat`), not only agent spans. Answer "which agents and LLM calls are failing most often" by running both this query and [Failing agent activity](#failing-agent-activity). For the full traffic/error golden-signal view, see [golden-signals.md](golden-signals.md).

---

## Agent steps by latency

P50 and P95 latency for each operation type in the agent pipeline. Use this to identify which step type dominates end-to-end latency and to detect regressions in specific operation categories.

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.operation.name) and gen_ai.operation.name != "goto"
| summarize steps = count(), p50_ms = percentile(duration, 50) / 1ms, p95_ms = percentile(duration, 95) / 1ms, by: {gen_ai.operation.name}
| sort p95_ms desc
```

**How to read it:** Each row is one operation type. `p50_ms` is the median step duration; `p95_ms` is the tail latency. `invoke_agent` spans typically carry the longest latency because they wrap the full LLM call and downstream tool invocations. `execute_tool` spans reflect the latency of the external tool itself. `create_agent` spans are usually sub-millisecond initialization events. A large gap between P50 and P95 on `invoke_agent` suggests occasional long-running conversation turns — investigate the traces at the tail.

**Unit note:** Convert with the `1ms` duration literal (`/ 1ms`), not `/ 1000000.0` — dividing a duration by a plain number stays a nanosecond duration; only the literal yields a real millisecond number.

**Tip:** Break out latency by agent name by adding `gen_ai.agent.name` to the `by:` clause. This reveals whether a latency regression is isolated to one agent or systemic across the fleet.

---

## Agent loops and runaway detection

A common agentic failure mode is the **loop**: an agent calls the same tool over and over within a single turn, or an orchestrator bounces between sub-agents without converging. Loops burn tokens and latency without making progress, and they are the usual cause of the token spikes flagged in [cost-and-tokens.md → Token usage spikes](cost-and-tokens.md#token-usage-spikes). The signature is a single `trace.id` (one turn) or `gen_ai.conversation.id` (one session) accumulating an abnormal number of repeated calls.

**Repeated tool calls within a turn:**

```dql
fetch spans, from: now()-24h
| filter gen_ai.operation.name == "execute_tool"
| summarize calls = count(), by: {trace.id, gen_ai.tool.name}
| filter calls > 10
| sort calls desc
```

**How to read it:** Each row is a tool that was invoked more than 10 times inside one trace (turn). Healthy turns call a tool a handful of times; a count in the dozens or hundreds for one `(trace.id, gen_ai.tool.name)` pair is a loop. Lower the `> 10` threshold to widen the net or raise it to surface only severe runaways. Take the `trace.id` and open the trace to see what the agent was reacting to on each iteration.

**Runaway turns by total step count:**

```dql
fetch spans, from: now()-24h
| filter gen_ai.operation.name == "execute_tool" or gen_ai.operation.name == "invoke_agent"
| summarize steps = count(), distinct_tools = countDistinct(gen_ai.tool.name), input_tokens = sum(gen_ai.usage.input_tokens), output_tokens = sum(gen_ai.usage.output_tokens), by: {trace.id}
| filter steps > 50
| sort steps desc
```

**How to read it:** Each row is one turn (trace) that executed more than 50 agent steps. The ratio of `steps` to `distinct_tools` is the key tell: many steps but only one or two distinct tools is a tight loop on those tools, whereas many steps across many tools is a genuinely complex (but possibly mis-planned) task. The token columns quantify the cost of the runaway. Adjust the `> 50` threshold to your fleet's normal step count — establish the baseline with `| summarize p95 = percentile(steps, 95), max_steps = max(steps)` on the per-trace step counts first.

**Tip:** When `gen_ai.conversation.id` is available (see [conversation-analytics.md](conversation-analytics.md)), swap `trace.id` for `gen_ai.conversation.id` in the `by:` clause to catch loops that span multiple turns — for example an orchestrator that re-delegates to the same sub-agent across a whole session. Add `gen_ai.agent.name` to attribute the loop to a specific agent.

> **Session ID = the agent trajectory.** A single agentic interaction usually spans **multiple turns**, and each turn is a separate `trace.id`. When the application instruments the interaction with a session identifier — carried on the spans as `gen_ai.conversation.id` — that one id stitches all those traces into a single session, the same way a RUM session id ties together a user's page views. This is what connects the raw span data, the per-turn agentic traces, and the end-to-end **agent trajectory**: filter to one `gen_ai.conversation.id` and order its spans by `start_time` to replay the whole trajectory across turns; group the loop and runaway queries above by `gen_ai.conversation.id` to see behaviour at session scope rather than per turn. It does not require frontend-to-backend correlation — it only needs the session id to be instrumented on the agentic interaction itself. See [conversation-analytics.md](conversation-analytics.md) for session-level cost, depth, and error queries.

---

## Agent topology (Smartscape entities)

> **Preview — feature-flag gated.** GenAI Smartscape entities are extracted at ingest behind a feature flag. On tenants where this is disabled, the `smartscapeNodes "GENAI_*"` queries below return zero rows even though the application is fully instrumented — that is the feature being off, not missing telemetry. Confirm with the span-based presence check in [SKILL.md → Empty-State Check](../SKILL.md#empty-state-check) before reporting an empty topology.

The signals above are derived by scanning spans. When the question is about *structure* rather than *behaviour* — "which agents exist", "which models does this agent use", "which provider serves this model" — query the Smartscape entities instead. Dynatrace extracts four GenAI node types from spans at ingest, so a topology or inventory query reads a small set of Smartscape objects rather than scanning the full span volume. This is cheaper (fewer bytes read) and faster for relationship questions, but it carries no per-request metrics — for latency, errors, and token counts, stay on spans.

| Node type | Represents | Example name |
|---|---|---|
| `GENAI_AGENT` | An instrumented agent | `supervisor`, `FAQ_agent`, `flight_state_and_weather_agent` |
| `GENAI_MODEL` | A model the fleet calls | `gpt-4o-mini`, `gemini-2.0-flash-001`, `claude-2.1` |
| `GENAI_PROVIDER` | A provider / framework | `openai`, `amazon`, `Langchain`, `azure.ai.openai` |
| `GENAI_SERVICE` | The GenAI application service | `ai-travel-advisor-agent-test` |

Note that the same agent name (e.g. `supervisor`) can appear as multiple `GENAI_AGENT` entities — one per provider/framework it runs under — so de-duplicate by name when counting distinct agents.

### Inventory: list GenAI entities

What agents, models, providers, and services exist in the environment. Use this as the entry point for any topology question and to confirm the feature is producing entities.

```dql
smartscapeNodes "GENAI_*"
| fields id, type, name
| sort type, name
```

**How to read it:** Each row is one Smartscape entity. `type` is the node type (`GENAI_AGENT`, `GENAI_MODEL`, `GENAI_PROVIDER`, `GENAI_SERVICE`); `name` is the agent/model/provider/service name. To count distinct agents regardless of how many providers they run under, add `| filter type == "GENAI_AGENT" | dedup name | summarize agents = count()`.

**Tip:** Narrow to a single type with the node-type argument — `smartscapeNodes "GENAI_AGENT"` — rather than filtering after the fetch. `smartscapeNodes` includes large object fields by default; project only the columns you need with `fields`.

### Topology: agent → model / provider relationships

How the GenAI entities connect. Use this to map which models and providers each agent depends on, and to find the blast radius of a model or provider (which agents would be affected if it degrades).

```dql
smartscapeEdges "*"
| filter startsWith(source_type, "GENAI") or startsWith(target_type, "GENAI")
| summarize edges = count(), by: {source_type, type, target_type}
| sort edges desc
```

**How to read it:** Each row is one relationship shape — a `source_type` connected to a `target_type` by edge `type`. In the reference data the GenAI edges observed are `uses` (`GENAI_AGENT` → `GENAI_MODEL`), `calls` (`GENAI_AGENT` → `GENAI_PROVIDER`), and `belongs_to` (between `GENAI_PROVIDER` and `GENAI_MODEL`). **Discover the edge types and directions in your own environment with this query before relying on them** — a wrong edge type or direction returns zero rows silently, not an error. See [dt-dql-essentials → Smartscape Topology Navigation](../../dt-dql-essentials/references/smartscape-topology-navigation.md) for the full `smartscapeEdges` / `traverse` reference.

**Walk from one agent to the models it uses** (full `traverse` syntax and `toSmartscapeId()` rules live in the dt-dql-essentials reference above):

```dql
smartscapeNodes "GENAI_AGENT"
| filter name == "supervisor"
| traverse edgeTypes: {uses}, targetTypes: {GENAI_MODEL}, direction: forward
| fields model_id = id, model = name
```

**How to read it:** Each row is one model the matched agent(s) use. Reverse the question — "which agents use this model?" — by starting from `GENAI_MODEL` and traversing `direction: backward`. Validate the edge type with the topology query above first if you get no rows.

**Tip:** Prefer Smartscape entities for inventory and dependency questions (cheap, structural) and spans for behaviour (latency, errors, tokens). To go from a topology finding back to live behaviour, take the agent `name` and filter spans on `gen_ai.agent.name == "<name>"` using the queries earlier in this reference.