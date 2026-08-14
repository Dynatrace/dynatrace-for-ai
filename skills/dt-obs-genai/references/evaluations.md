# Evaluations Reference

Dynatrace AI Observability captures LLM evaluation results as **bizevents** — not spans. Each evaluation run emits one bizevent per evaluator per response, giving you structured quality scores alongside the exact question and answer that were judged. The queries in this file use `fetch bizevents` with `event.type == "gen_ai.evaluation.result"`.

Although the results live in bizevents, each one is anchored to the trace that produced the evaluated response: the bizevent carries the `trace.id` of the originating run. That means an evaluation is never a dead end — once you have a failing bizevent you can pivot straight to its distributed trace and inspect the spans (the chat call, tool invocations, and agent steps) that generated the answer the judge scored. See [Correlating evaluations to traces](#correlating-evaluations-to-traces).

**Fields**

| Field | Type | Notes |
|---|---|---|
| `gen_ai.evaluation.name` | string | Evaluator name (e.g., `faithfulness`, `answer-completeness`, `prompt-injection`) |
| `gen_ai.evaluation.score.value` | float 0–1 | Numeric quality score; higher is better for most evaluators |
| `gen_ai.evaluation.score.label` | string | `pass` or `fail` — threshold set by the evaluation spec |
| `gen_ai.evaluation.explanation` | string | Free-text explanation produced by the LLM judge |
| `gen_ai.evaluation.input.question` | string | The user question that was evaluated |
| `gen_ai.evaluation.input.answer` | string | The model answer that was evaluated |
| `gen_ai.evaluation.input.system_prompt` | string | System prompt active at evaluation time |
| `gen_ai.response.id` | string | 16-hex identifier matching `span_id` in the bizevent — does NOT match the `chatcmpl-…` format of the chat span's `gen_ai.response.id` |
| `trace.id` | uid | Trace that produced the evaluated response — pivot to the originating distributed trace (see [Correlating evaluations to traces](#correlating-evaluations-to-traces)) |
| `dt.eval.run_id` | string | Evaluation run identifier (e.g., `run-2026-06-24T13-07-19-422e8bb1`) |
| `timestamp` | timestamp | Event time — use `timestamp` for time bucketing (bizevents use `timestamp`; spans use `start_time`) |

---

## Evaluation quality scores

Average score and evaluation count per evaluator, sorted by average score ascending. Use this to identify which evaluators are flagging the lowest-quality responses and to compare the health of different quality dimensions at a glance.

```dql
fetch bizevents, from: now()-24h
| filter event.type == "gen_ai.evaluation.result"
| summarize evaluations = count(), avg_score = avg(gen_ai.evaluation.score.value), by: {gen_ai.evaluation.name}
| sort avg_score asc
```

**How to read it:** Each row is one evaluator. `avg_score` is the mean quality score across all responses evaluated in the window. Scores range from 0 to 1; scores near 1.0 indicate consistently high-quality output for that dimension. Evaluators at the top of the list (lowest `avg_score`) are the dimensions most in need of attention.

**Tip:** Add `gen_ai.request.model` to the `by:` clause to compare score distributions across models. Add a `| filter gen_ai.evaluation.score.label == "fail"` stage before the `summarize` to focus the average on failing responses only.

---

## Failed evaluations

Recent evaluations where the response did not meet the evaluator's pass threshold, with the question and answer that triggered the failure. Use this to directly inspect what went wrong — the explanation from the LLM judge is included alongside the exact Q&A pair.

```dql
fetch bizevents, from: now()-24h
| filter event.type == "gen_ai.evaluation.result"
| filter gen_ai.evaluation.score.label == "fail"
| fields timestamp, gen_ai.evaluation.name, gen_ai.evaluation.score.value, gen_ai.evaluation.explanation, gen_ai.evaluation.input.question, gen_ai.evaluation.input.answer
| sort timestamp desc
```

**How to read it:** Each row is one failed evaluation. `gen_ai.evaluation.explanation` is the LLM judge's reasoning for the failure — it identifies why the answer did not satisfy the evaluator's rubric. `gen_ai.evaluation.input.question` and `gen_ai.evaluation.input.answer` are the exact user turn and model response that were judged. Common failure patterns include faithfulness failures (model asserts facts not in the retrieved context), answer-completeness failures (response is too brief or omits key detail), and prompt-injection failures (evaluator detects instruction leakage in the output).

**Tip:** Add `| filter gen_ai.evaluation.name == "faithfulness"` before the `filter` on `score.label` to focus on a single evaluator. Add `dt.eval.run_id` to the `fields` list to group failures by evaluation run.

**Fail rate by evaluator:** To see how many responses fail each evaluator and what share of total evaluations that represents:

```dql
fetch bizevents, from: now()-24h
| filter event.type == "gen_ai.evaluation.result"
| summarize fails = countIf(gen_ai.evaluation.score.label == "fail"), total = count(), by: {gen_ai.evaluation.name}
| fieldsAdd fail_rate_pct = if(total > 0, fails * 100.0 / total, else: 0.0)
| sort fails desc
```

**How to read it:** Each row is one evaluator. `fails` is the absolute count of failed evaluations; `fail_rate_pct` is the proportion that failed. A high `fail_rate_pct` on an evaluator points to a systematic gap in that quality dimension (e.g. answer completeness or faithfulness), while a 0% rate on safety evaluators such as `bias`, `toxicity`, and `pii-leakage` indicates no detected safety issues for those dimensions.

---

## Correlating evaluations to traces

A failed evaluation tells you *that* a response was bad; the trace tells you *why*. Because every evaluation bizevent carries the `trace.id` of the run that produced the evaluated response, you can pivot from a quality failure to the underlying spans — the chat call, its model and token usage, and any tool or agent steps that fed the answer.

First, surface the failures with their trace IDs:

```dql
fetch bizevents, from: now()-24h
| filter event.type == "gen_ai.evaluation.result"
| filter gen_ai.evaluation.score.label == "fail"
| fields timestamp, trace.id, gen_ai.evaluation.name, gen_ai.evaluation.score.value, gen_ai.evaluation.input.question
| sort timestamp desc
```

Then take a `trace.id` from a row and fetch every span in that trace (replace the placeholder with a real trace-id hex):

```dql-template
fetch spans, from: now()-24h
| filter trace.id == toUid("<trace-id-hex>")
| fields start_time, span.name, gen_ai.operation.name, gen_ai.request.model, gen_ai.usage.input_tokens, gen_ai.usage.output_tokens, duration, span.status_code
| sort start_time asc
```

**How to read it:** The first query lists failing evaluations with the `trace.id` of each judged response. The second expands one trace into its constituent spans in execution order — the `chat` span is the LLM call that produced the answer, and any `execute_tool` / `invoke_agent` spans are the surrounding agent activity. Reading them together shows whether a faithfulness failure traces back to, say, a tool that returned empty context or a model that was silently swapped (`gen_ai.response.model`).

**`trace.id` is a `uid`, not a string.** Filter spans with `filter trace.id == toUid("<hex>")` (or `filter toString(trace.id) == "<hex>"`). A plain `trace.id == "<hex>"` comparison silently returns zero rows. This matches the trace-correlation guidance in [agent-signals.md](agent-signals.md#failing-agent-activity).

**Tip:** To go the other direction — from a known bad trace to its quality verdict — filter the bizevents query on `filter trace.id == toUid("<hex>")` to retrieve every evaluator's score and explanation for that specific run.