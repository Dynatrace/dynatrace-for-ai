---
name: dt-obs-genai
description: >-
  Analyze & debug GenAI/LLM apps: token cost & caching by prompt, model &
  provider; latency/errors; agent & tool loops/failures; conversations;
  guardrails; evaluations; OpenTelemetry/dt-evals setup.
license: Apache-2.0
---

# AI Observability (GenAI) Skill

Analyze AI Observability signals from customer GenAI applications using DQL — golden
signals, LLM signals, token and cost analytics (with usage attribution and prompt-caching
economics), agent signals (including loop/runaway detection and Smartscape topology),
conversation/session-level analytics, guardrails, and evaluation quality.

## When to Use

Use this skill for observability questions about customer GenAI applications — anything
reading OpenTelemetry GenAI spans (`gen_ai.*`) or LLM evaluation bizevents. Example triggers:

- "LLM latency", "error rate by model"
- "token usage by model", "token throughput / TPM", "am I hitting rate limits", "provider throttling or 429s"
- "cost by model and provider", "who is driving token spend", "do I have prompt caching"
- "cost per conversation", "most expensive sessions"
- "failing agent tool calls", "find runaway agents"
- "responses truncated or blocked", "finish reasons"
- "failed evaluations", "quality scores"

## When NOT to Use

Davis CoPilot/MCP telemetry (dt-platform), generic service metrics (dt-obs-services),
logs (dt-obs-logs), or non-GenAI distributed tracing (dt-obs-tracing).

## Example Questions

When suggesting follow-up questions (e.g., "give me one example question per topic"),
use these canonical, ready-to-ask phrasings — one per capability. Keep suggestions
single-clause and avoid the literal phrase "content filter" (use "blocked or
safety-filtered" instead); overly long, multi-clause questions can be rejected.

- **Traffic, errors & latency:** What is my LLM error rate and p95 latency by model in the last 24 hours?
- **Token usage & cost:** Break down token usage and cost by model and provider in the last 24 hours.
- **Agent & tool activity:** Show me failing agent tool calls in the last 24 hours.
- **Conversation analytics:** What are my top 10 most expensive conversations by total token usage in the last 24 hours?
- **Guardrails:** How many responses were blocked or truncated in the last 7 days, and which model was affected most?
- **Evaluation quality:** Show me failed evaluations from the last 24 hours with the judge's explanation and the question-answer pair.

---

## Core Capabilities

### Golden Signals

The four classic observability signals — traffic, errors, latency, and saturation — apply
directly to GenAI applications. Traffic is request throughput over time; errors are spans
where `span.status_code == "error"`; latency is the `duration` field (a Grail duration
value — divide by the `1ms` literal, `duration / 1ms`, for a numeric millisecond value);
saturation is proxied by total token throughput per minute (input + output tokens combined).

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.request.model)
| summarize total = count(), errors = countIf(span.status_code == "error"), by: {gen_ai.request.model}
| fieldsAdd error_rate_pct = if(total > 0, errors * 100.0 / total, else: 0.0)
| sort error_rate_pct desc
```

→ **Full traffic, latency, and saturation queries:** See [references/golden-signals.md](references/golden-signals.md)

### LLM Signals

LLM signals describe which model and provider served each request, what operation type
was invoked (`chat`, `execute_tool`, `invoke_agent`, `create_agent`), and how tokens were
consumed. Use these to benchmark provider latency, compare model performance, and
understand the token distribution across model-provider combinations.

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.request.model)
| summarize p95_ms = percentile(duration, 95) / 1ms, requests = count(), by: {gen_ai.provider.name}
| sort p95_ms desc
```

→ **Slowest models, token usage by model:** See [references/llm-signals.md](references/llm-signals.md)

### Cost and Tokens

Token consumption is the primary cost driver. Dynatrace stores `gen_ai.usage.input_tokens`
and `gen_ai.usage.output_tokens` on every span — there is no stored cost field; estimated
cost must be derived by multiplying token sums by the per-model price you supply. Use these
queries to identify the highest-spend model-provider combinations and detect token-burn spikes.

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.usage.input_tokens) or isNotNull(gen_ai.usage.output_tokens)
| summarize input_tokens = sum(gen_ai.usage.input_tokens), output_tokens = sum(gen_ai.usage.output_tokens), total_tokens = sum(gen_ai.usage.input_tokens) + sum(gen_ai.usage.output_tokens), by: {gen_ai.provider.name, gen_ai.request.model}
| sort total_tokens desc
```

→ **Token spikes, cost estimation, most expensive prompts, usage attribution, prompt-caching economics:** See [references/cost-and-tokens.md](references/cost-and-tokens.md)

### Agent Signals

GenAI agents emit spans for each tool invocation (`execute_tool`), agent step
(`invoke_agent`), and agent creation (`create_agent`). Use agent signals to identify
which tools are called most often and which agents are failing. For *structural*
questions — which agents, models, and providers exist and how they connect — query the
GenAI Smartscape entities (`GENAI_AGENT`, `GENAI_MODEL`, `GENAI_PROVIDER`, `GENAI_SERVICE`)
instead of scanning spans; this is a feature-flag-gated preview.

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.agent.name)
| summarize total = count(), errors = countIf(span.status_code == "error"), by: {gen_ai.agent.name}
| fieldsAdd error_rate_pct = if(total > 0, errors * 100.0 / total, else: 0.0)
| sort errors desc
```

→ **Tool usage, failing agents, agent step latency, loop/runaway detection, Smartscape topology:** See [references/agent-signals.md](references/agent-signals.md)

### Conversation Analytics

Per-span and per-trace signals measure one request or one turn. When the application
propagates `gen_ai.conversation.id`, you can roll spans up to the **session** level — cost
per conversation, how deep conversations run, and which sessions are runaway-expensive or
error-prone. This is the unit that matters for chargeback and user-perceived reliability.

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.conversation.id)
| summarize turns = countDistinct(trace.id), total_tokens = sum(gen_ai.usage.input_tokens) + sum(gen_ai.usage.output_tokens), errors = countIf(span.status_code == "error"), by: {gen_ai.conversation.id}
| sort total_tokens desc
```

→ **Cost/depth per conversation, session error rate:** See [references/conversation-analytics.md](references/conversation-analytics.md)

### Guardrails

Guardrails surface as `gen_ai.response.finish_reasons` on the span — `content_filter` means a
safety filter blocked or redacted output, `length` means the response was truncated at the
token limit — and as the proactive safety evaluators (`prompt-injection`, `pii-leakage`,
`toxicity`, `bias`) in the evaluation bizevents. Use these to quantify blocked and truncated
responses and tie them back to the LLM-judge safety verdicts.

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.response.finish_reasons)
| fieldsAdd finish_reason = gen_ai.response.finish_reasons
| expand finish_reason
| summarize calls = count(), by: {finish_reason, gen_ai.request.model}
| sort calls desc
```

→ **Blocked (safety-filtered), truncated (length), finish-reason breakdown:** See [references/guardrails.md](references/guardrails.md)

### Evaluation Quality

Evaluation results are captured as **bizevents** (not spans) with
`event.type == "gen_ai.evaluation.result"`. Each evaluator emits one bizevent per
response, carrying the score, pass/fail label, explanation, and the exact Q&A pair.
Use evaluation queries to monitor quality dimensions and surface failed responses
with the LLM judge's reasoning. Each bizevent also carries the `trace.id` of the run that
produced the evaluated response, so you can pivot from a quality failure to the spans that
caused it.

```dql
fetch bizevents, from: now()-24h
| filter event.type == "gen_ai.evaluation.result"
| filter gen_ai.evaluation.score.label == "fail"
| fields timestamp, gen_ai.evaluation.name, gen_ai.evaluation.score.value, gen_ai.evaluation.explanation, gen_ai.evaluation.input.question, gen_ai.evaluation.input.answer
| sort timestamp desc
```

→ **Quality scores, failed evaluations, fail rates:** See [references/evaluations.md](references/evaluations.md)

### Empty-State Check

When any signal query returns no rows, do not report "no data found" — first confirm
whether the application sends GenAI telemetry at all. These two presence checks show
which signal families are present:

```dql
fetch spans, from: now()-24h
| summarize 
    has_genai = countIf(isNotNull(gen_ai.request.model)), 
    has_tokens = countIf(isNotNull(gen_ai.usage.input_tokens) or isNotNull(gen_ai.usage.output_tokens)), 
    has_agents = countIf(isNotNull(gen_ai.agent.name)), 
    has_tools = countIf(gen_ai.operation.name == "execute_tool"), 
    has_conversation = countIf(isNotNull(gen_ai.conversation.id)), 
    has_finish_reason = countIf(isNotNull(gen_ai.response.finish_reasons)), 
    has_cached_tokens = countIf(isNotNull(gen_ai.usage.cache_read.input_tokens) or isNotNull(gen_ai.usage.cache_creation.input_tokens)),
    total = count()
    
```

```dql
fetch bizevents, from: now()-24h
| filter event.type == "gen_ai.evaluation.result"
| summarize evals = count()
```

If `has_genai` is zero, report that the application appears not to be instrumented for AI
Observability yet — not "no data found". If `has_genai` is non-zero but a specific family
(`has_tokens`, `has_agents`, `has_tools`, `has_conversation`, `has_finish_reason`,
`has_cached_tokens`, `evals`) is zero, only that signal type is missing — for example
`has_conversation == 0` means session-level analytics are unavailable because the app does
not propagate a conversation id, and `has_cached_tokens == 0` means prompt-caching telemetry
is not being reported. These optional families may use different attribute names depending on
the provider/SDK; verify before reporting them absent.

---

## Agent Instructions

### Act First, Refine Later

When a user asks for analysis, proceed immediately with sensible defaults. Do not ask
for parameter values you can reasonably assume.

**Default values when not specified:**

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| Timeframe | Last 24 h (`from: now()-24h`) | Covers a full operational day without being too narrow |
| Model scope | All models (no model filter) | Shows the full picture; user can narrow after seeing results |
| Provider scope | All providers | Same rationale as model scope |
| Token threshold | None | Show all — let the data reveal the outliers |

**Exception — cost prices.** Per-model prices are the one input you cannot
default (there is no cost field in the data). Ask the user for them before
estimating USD; never use prices from memory. See [cost-and-tokens.md](references/cost-and-tokens.md).

### Empty-State Rule

When any signal query returns no rows, run the two presence checks in the
**Empty-State Check** capability above before responding — never reply "no data found".
If `has_genai` is zero, report that the application appears not to be instrumented for AI
Observability yet; if only a specific family is zero, say which signal type is missing.

### Scope Boundary

This skill covers AI Observability signals for **customer GenAI applications** only.
Product documentation and configuration how-to questions (e.g., "How do I configure
the Dynatrace OTLP endpoint?") go to `ask-dynatrace-docs` — this skill does not
contain product configuration how-tos.

### Understanding User Intent

**Map user requests and prompt-starter phrasings to capabilities:**

| User Request / Prompt Starter | Capability | Reference File |
|-------------------------------|------------|----------------|
| "Understand AI Observability signals" | All signal categories overview | This SKILL.md |
| "Analyze LLM latency and errors", "LLM errors", "error rate by model" | Golden Signals | [golden-signals.md](references/golden-signals.md) |
| "Which models are slowest right now?", "compare latency across providers" | LLM Signals | [llm-signals.md](references/llm-signals.md) |
| "Show token usage by model", "token usage spikes" | Cost and Tokens | [cost-and-tokens.md](references/cost-and-tokens.md) |
| "Break down cost by model and provider", "which prompts are most expensive?" | Cost and Tokens | [cost-and-tokens.md](references/cost-and-tokens.md) |
| "Trace a failing agent run", "show failed tool calls" | Agent Signals | [agent-signals.md](references/agent-signals.md) |
| "Break down agent steps by latency" | Agent Signals | [agent-signals.md](references/agent-signals.md) |
| "Map agent topology", "which models does this agent use?", "list GenAI agents/models/providers" | Agent Signals (Smartscape) | [agent-signals.md](references/agent-signals.md) |
| "Is an agent stuck in a loop?", "find runaway agents", "what caused the token spike?" | Agent Signals (loops) | [agent-signals.md](references/agent-signals.md) |
| "Cost per conversation", "most expensive sessions", "how deep do conversations run?" | Conversation Analytics | [conversation-analytics.md](references/conversation-analytics.md) |
| "Stitch together an agent trajectory", "filter by session id", "connect traces across a session" | Conversation Analytics | [conversation-analytics.md](references/conversation-analytics.md) |
| "How often are responses blocked/filtered?", "are responses being truncated?", "finish reasons" | Guardrails | [guardrails.md](references/guardrails.md) |
| "Cost by application/user/tenant", "who is driving token spend?" | Cost and Tokens (attribution) | [cost-and-tokens.md](references/cost-and-tokens.md) |
| "Do I have prompt caching?", "cache hit rate", "caching savings" | Cost and Tokens (caching) | [cost-and-tokens.md](references/cost-and-tokens.md) |
| "Summarize evaluation quality scores", "show low-scoring responses", "show failed evaluations" | Evaluation Quality | [evaluations.md](references/evaluations.md) |
| "What signals am I missing?", "why is there no data?" | Empty-State Check | This SKILL.md |

---

## Common Workflows

### Workflow: Cost Investigation

```
1. Run token usage by model and provider (cost-and-tokens.md → "Token usage by model and provider")
2. Identify the top model-provider combinations by total_tokens
3. For the top offenders, run token usage spikes to check for abnormal time windows
4. Use the cost-estimation template in "Most expensive prompts and models" to estimate USD spend — ask the user for per-model prices first (see "Exception — cost prices" under Agent Instructions)
5. Check for prompt-size outliers: high input_tokens / output_tokens ratio indicates large context windows
6. Attribute spend to a consumer (cost-and-tokens.md → "Usage attribution") and check whether prompt caching is enabled and effective (cost-and-tokens.md → "Prompt caching economics")
```

### Workflow: Token-Spike / Runaway Investigation

```
1. Run token usage spikes (cost-and-tokens.md → "Token usage spikes") to find the abnormal time window
2. Within that window, run repeated-tool-calls and runaway-turn queries (agent-signals.md → "Agent loops and runaway detection")
3. For a flagged trace.id, open the trace to see what the agent looped on
4. If conversation ids are present, re-run the loop query grouped by gen_ai.conversation.id to catch cross-turn loops (conversation-analytics.md)
```

### Workflow: Failing Agent Run

```
1. Run failing agent activity query (agent-signals.md → "Failing agent activity")
2. Sort by errors desc to find the most error-prone agent
3. Take the trace.id from a failing span and open in Dynatrace distributed-tracing view
4. Check agent steps by latency (agent-signals.md) to see which operation type is slowest
```

### Workflow: Guardrail & Safety Review

```
1. Run the guardrails presence check (guardrails.md) to confirm finish reasons are recorded
2. Run the finish-reason breakdown, then the blocked (content_filter) and truncated (length) queries
3. Correlate safety-filter spikes with the prompt-injection evaluator and truncation with answer-completeness failures (evaluations.md)
4. For a specific block or failure, take the trace.id and pivot to the originating spans (evaluations.md → "Correlating evaluations to traces")
```

### Workflow: Evaluation Review

```
1. Run evaluation quality scores (evaluations.md → "Evaluation quality scores") to rank evaluators by avg_score asc
2. Focus on the lowest-scoring evaluator
3. Run failed evaluations (evaluations.md → "Failed evaluations") to surface the exact Q&A pairs and LLM judge explanations
4. Use the "Fail rate by evaluator" query to see how many responses fail each evaluator and the share of total evaluations
5. To root-cause a specific failure, take its trace.id and pivot to the originating spans (evaluations.md → "Correlating evaluations to traces")
```

---

## References

- [references/golden-signals.md](references/golden-signals.md) — traffic, errors, latency, saturation
- [references/llm-signals.md](references/llm-signals.md) — slowest models, provider latency, token usage by model
- [references/cost-and-tokens.md](references/cost-and-tokens.md) — token usage, spikes, cost-estimation template, usage attribution, prompt-caching economics
- [references/agent-signals.md](references/agent-signals.md) — tool usage, failing agents, step latency, loop/runaway detection, Smartscape agent topology (preview)
- [references/conversation-analytics.md](references/conversation-analytics.md) — session-level cost, depth, and error rate (`gen_ai.conversation.id`)
- [references/guardrails.md](references/guardrails.md) — blocked (safety-filtered) and truncated (length) responses via finish reasons
- [references/evaluations.md](references/evaluations.md) — quality scores, failed evals, fail-rate, trace correlation (bizevents)
