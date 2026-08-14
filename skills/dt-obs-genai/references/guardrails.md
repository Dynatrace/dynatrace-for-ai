# Guardrails Reference

Guardrails are the controls that keep a GenAI application's output safe and well-formed. They surface in two places in Dynatrace telemetry:

1. **On the span, after the fact** — the model's `gen_ai.response.finish_reasons` records *why* generation stopped. A `content_filter` reason means a provider-side safety filter blocked or redacted the output; a `length` reason means the response was truncated at the token limit (a silent quality and cost problem). These are observed outcomes on every chat span.
2. **As proactive evaluations** — the safety evaluators (`prompt-injection`, `pii-leakage`, `toxicity`, `bias`) run an LLM judge over responses and emit pass/fail bizevents. Those live in [evaluations.md](evaluations.md) — this file covers the span-level finish-reason signals and points back to the evaluators for the judged guardrails.

> **Field-presence caveat.** `gen_ai.response.finish_reasons` is populated by most chat instrumentations but not all (it is frequently null on tool/agent spans, and some providers omit it). Run the presence check below first. The field is an **array** of reason strings in the OpenTelemetry conventions, but some pipelines flatten it to a single string — the discovery query reveals which shape your tenant uses, and the breakdown query handles the array form with `expand`. Verify on your tenant before relying on these queries.

| Field | Notes |
|---|---|
| `gen_ai.response.finish_reasons` | Why generation stopped — array of: `stop` (normal), `length` (truncated), `content_filter` (blocked/redacted), `tool_calls` (handed off to a tool) |
| `gen_ai.request.model` / `gen_ai.provider.name` | Attribute guardrail trips to a model and provider |
| `gen_ai.response.model` | The actually-served model — content filtering can differ by model version |
| `start_time` | Use for time bucketing — `timestamp` is null for GenAI spans |

---

## Presence check

Confirms whether finish reasons are recorded before you analyze them.

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.request.model)
| summarize calls = count(), with_finish_reason = countIf(isNotNull(gen_ai.response.finish_reasons))
```

**How to read it:** `with_finish_reason` is how many GenAI spans carry a finish reason. If it is `0` while `calls` is non-zero, this guardrail signal is not being captured — report that finish-reason data is unavailable rather than "no guardrail trips". For the safety-evaluator guardrails (`prompt-injection`, `pii-leakage`, `toxicity`, `bias`), use the presence check in [SKILL.md → Empty-State Check](../SKILL.md#empty-state-check) for evaluation bizevents instead.

---

## Finish-reason breakdown

How model calls are terminating, per model. Use this to see the baseline mix of normal completions versus truncations, filter trips, and tool hand-offs.

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.response.finish_reasons)
| fieldsAdd finish_reason = gen_ai.response.finish_reasons
| expand finish_reason
| summarize calls = count(), by: {finish_reason, gen_ai.request.model}
| sort calls desc
```

**How to read it:** Each row is one finish reason for one model. `stop` is a clean completion and should dominate. Any meaningful share of `length` or `content_filter` is the signal to act on (see the two queries below). `tool_calls` is normal for agentic workloads — it means the model chose to invoke a tool rather than answer directly.

**Shape note:** `expand` breaks an array field into one row per element. If your tenant stores `finish_reasons` as a single string rather than an array, `expand` is a no-op and the query still works; if the discovery shows bracketed values like `[stop]`, the `expand` is doing the work. To check the shape, run `... | filter isNotNull(gen_ai.response.finish_reasons) | fields gen_ai.response.finish_reasons | limit 5`.

---

## Blocked or safety-filtered responses

Calls where a provider safety filter tripped. Use this to quantify how often guardrails are blocking or redacting output and which models/providers trip them most — a rising trend can indicate adversarial input, a prompt regression, or an over-tight filter harming legitimate responses.

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.response.finish_reasons)
| fieldsAdd finish_reason = gen_ai.response.finish_reasons
| expand finish_reason
| filter finish_reason == "content_filter"
| summarize blocked = count(), by: {gen_ai.request.model, gen_ai.provider.name}
| sort blocked desc
```

**How to read it:** Each row is a model+provider combination and `blocked` is the number of responses the safety filter stopped. Correlate a spike here with the `prompt-injection` evaluator in [evaluations.md](evaluations.md#failed-evaluations): simultaneous `content_filter` trips and prompt-injection failures point to an attack or a jailbreak attempt rather than benign over-filtering.

**Tip:** Add `bin(start_time, 1h)` to the `by:` clause to turn this into a trend and detect a sudden surge. To inspect what triggered a block, take the `trace.id` of an affected span (add it to a `fields` projection) and open the trace.

---

## Truncated responses (length)

Calls cut off at the token limit. Use this to find responses that were silently truncated — a common, easily-missed cause of incomplete or low-quality answers, and a signal to raise `max_tokens` or tighten prompts.

```dql
fetch spans, from: now()-24h
| filter isNotNull(gen_ai.response.finish_reasons)
| fieldsAdd finish_reason = gen_ai.response.finish_reasons
| expand finish_reason
| summarize calls = count(), truncated = countIf(finish_reason == "length"), by: {gen_ai.request.model}
| fieldsAdd truncation_rate_pct = if(calls > 0, truncated * 100.0 / calls, else: 0.0)
| sort truncation_rate_pct desc
```

**How to read it:** Each row is one model. `truncated` is the number of responses that hit the output-token ceiling; `truncation_rate_pct` is the share of that model's responses cut off. A high truncation rate explains `answer-completeness` evaluation failures (see [evaluations.md](evaluations.md)) — the answer was not low-effort, it was clipped. Models with a high truncation rate are candidates for a higher `max_tokens` setting or more concise prompting.

**Tip:** Cross-reference truncation with output-token usage from [cost-and-tokens.md](cost-and-tokens.md): models that are both truncating and topping the output-token distribution are hitting a hard ceiling on long generations.
