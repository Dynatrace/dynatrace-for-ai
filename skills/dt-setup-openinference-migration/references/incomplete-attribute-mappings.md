# Invocation parameters and guardrail attributes: two different fix tracks

Used by [step 4](../SKILL.md#4-close-the-gaps-the-semconv-option-leaves). Both are gaps the
semconv option alone doesn't close, but they need **different remediation** — don't reach for
the same tool for both. The dividing line is whether the raw data already exists on the span
in some form (pipeline-fixable) or was never captured by the instrumentation at all
(needs app code).

## Invocation parameters: fixable in a collector or OpenPipeline config

OpenInference packs model parameters into a single JSON string at
`llm.invocation_parameters` (`{"temperature": 0.7, "max_tokens": 512, ...}`). Confirm directly
on the migrated app rather than assuming — the semconv option's own dual-write may or may not
also populate the individual `gen_ai.request.temperature` / `gen_ai.request.max_tokens` / etc.
fields the contract checks for one attribute family but not the other; a span with `gen_ai.*`
core fields present can still leave `llm.invocation_parameters` unexploded.

Check with a query rather than assuming either way:

```dql-template
fetch spans, from: now()-30m
| filter service.name == "<svc>" and isNotNull(gen_ai.request.model)
| summarize spans = count(),
    packed      = countIf(isNotNull(llm.invocation_parameters)),
    temperature = countIf(isNotNull(gen_ai.request.temperature))
```

Packed populated while `temperature` is zero means the blob was left unparsed.

If the individual fields are missing, this is data that already exists on the span — just
shaped wrong — so it's fixable without touching app code, same availability logic as step 4's
cardinality table (check which mechanism actually sits in this app's ingestion path from
[references/ingestion-shape.md](ingestion-shape.md)):

- **OTel Collector transform** — parse the JSON once, then set each field that is present:
  ```yaml
  transform/explode_invocation_parameters:
    error_mode: ignore
    trace_statements:
      - context: span
        statements:
          - set(attributes["temp.invocation_parameters"], ParseJSON(attributes["llm.invocation_parameters"])) where attributes["llm.invocation_parameters"] != nil
          - set(attributes["gen_ai.request.temperature"], attributes["temp.invocation_parameters"]["temperature"]) where attributes["temp.invocation_parameters"]["temperature"] != nil
          - set(attributes["gen_ai.request.top_p"], attributes["temp.invocation_parameters"]["top_p"]) where attributes["temp.invocation_parameters"]["top_p"] != nil
          - set(attributes["gen_ai.request.max_tokens"], Int(attributes["temp.invocation_parameters"]["max_tokens"])) where attributes["temp.invocation_parameters"]["max_tokens"] != nil
          - set(attributes["gen_ai.request.frequency_penalty"], attributes["temp.invocation_parameters"]["frequency_penalty"]) where attributes["temp.invocation_parameters"]["frequency_penalty"] != nil
          - set(attributes["gen_ai.request.presence_penalty"], attributes["temp.invocation_parameters"]["presence_penalty"]) where attributes["temp.invocation_parameters"]["presence_penalty"] != nil
          - set(attributes["gen_ai.request.seed"], Int(attributes["temp.invocation_parameters"]["seed"])) where attributes["temp.invocation_parameters"]["seed"] != nil
          - delete_key(attributes, "temp.invocation_parameters")
  ```
  The shape mirrors the examples repo's collector configs: `error_mode: ignore` so a span with
  malformed JSON is skipped instead of failing the batch, the blob parsed once into a temporary
  attribute, each key guarded individually (calls commonly omit fields like `seed`), and the
  temporary attribute deleted at the end. `ParseJSON` returns every JSON number as a float —
  `gen_ai.request.max_tokens` and `gen_ai.request.seed` are integers per the gen_ai semantic
  conventions, so both go through OTTL's `Int(...)`; the other four are genuinely floats. Only set
  fields the target contract profile actually requires — load **dt-setup-genai** and check its
  `validate-contract.md` — don't blanket-explode every possible key if only one or two are
  checked.
- **Dynatrace OpenPipeline** — a DQL processor with the equivalent parse-and-set logic.
  Field-by-field extraction like this is more tractable for a DQL processor than the full
  message-array reconstruction dt-setup-genai's normalizer gate needs a collector for — there's
  no structural reassembly here, just JSON parsing plus per-field assignment. **Read
  [openpipeline-safety.md](openpipeline-safety.md) before proposing this** — it's shared tenant
  infrastructure (the routing entry) and needs the same care as the cardinality removal case,
  not a smaller ask just because the change itself is a field extraction.

If step 4's cardinality removal is also happening, both transforms can live in the same
collector pipeline or the same OpenPipeline processor chain — explode first, then strip the
now-redundant `llm.invocation_parameters` key alongside the other `llm.*`/`openinference.*`
keys.

## Guardrail attributes: likely needs custom instrumentation code — stop and ask

OpenInference has **no standardized guardrail attribute**. `openinference.span.kind =
"GUARDRAIL"` marks the span *kind*, but whether a guardrail actually fired, and what it caught,
is signaled differently — or not at all — per library:

| Source | Signal, if any | Caveat |
|---|---|---|
| OpenAI Agents SDK | a literal `guardrail.triggered` boolean attribute | — |
| AWS Bedrock `apply_guardrail` (standalone API) | `action` inside a JSON `output.value` blob (`"action":"GUARDRAIL_INTERVENED"`); span status flips `error`/`ok` on block/pass | The full assessment breakdown (topic/content/word/PII categories) is **not captured at all** — the instrumentation wrapper never puts AWS's `assessments` array on the span. No pipeline transform can recover data that was never emitted. |
| AWS Bedrock inline Converse guardrails (`guardrailConfig` on `converse`/`converse_stream`) | not captured by the OpenInference instrumentation today | Known upstream gap in `openinference-instrumentation-bedrock`, not a Dynatrace-side gap. Don't confuse this with Bedrock **Agents**' `invoke_agent` API, which the same package *does* capture guardrail trace data for (`inputAssessments`/`outputAssessments` from the agent orchestration trace) — that's a different boto3 call from Converse and isn't the standalone `apply_guardrail` row above either |
| Azure OpenAI content filtering | `gen_ai.prompt.prompt_filter_results` / `gen_ai.completion.content_filter_results` — already present on the LLM span itself, not under a `GUARDRAIL`-kind span at all | JSON serialization (field order/spacing) differs slightly between instrumentation paths; match on content, not exact string form |
| Guardrails AI (`guardrails-ai`, via `openinference-instrumentation-guardrails`) | `output.value` set to the library's own `validation_result.outcome`, on a `GUARDRAIL`-kind span | No dedicated triggered/blocked boolean — `outcome` is Guardrails AI's own result object serialized onto the span; match on its content, not a fixed field |
| GCP safety ratings | no known OpenInference signal | — |

`openinference-instrumentation-guardrails` is **not** the AWS Bedrock guardrail integration
despite the name overlap — it instruments the third-party
[Guardrails AI](https://github.com/guardrails-ai/guardrails) validation framework only (`import
guardrails`, wraps `Runner.step`/`PromptCallableBase.__call__`/`ValidatorServiceBase`). It has
no `boto3`/Bedrock code at all. For Bedrock's own `apply_guardrail`/Converse guardrail config,
the row above (via `openinference-instrumentation-bedrock`) is the relevant one — don't reach
for the Guardrails AI package expecting it to cover Bedrock's native feature.

Even where a signal exists, it isn't reliably "did this block" on its own: e.g. Bedrock's
`guardrail.id`/`guardrail.version` fields (when populated by other paths) are present on
**every** guarded call, triggered or not — presence alone over-counts.

**Because the underlying data is often missing entirely, not just misnamed, this isn't a
transform problem.** Adding it means changing what the app captures — wrapping the guardrail
call to attach the missing attribute explicitly (`set_attribute` at the call site, or a span
processor if the instrumentor creates the span with no call-site handle — the same mechanism
`no-native-instrumentation.md` uses for any attribute the instrumentor omits; load **dt-setup-genai**
to read it). **This is an app-code edit — stop and get
explicit approval before writing it, same as any other code change this skill makes.** If the
user doesn't need guardrail visibility for this migration, it's fine to leave as a known,
documented gap rather than add code for it.

Once the app does capture the signal (natively or via added code), renaming or normalizing it
to whatever shape downstream dashboards expect is back to a pipeline problem — the same
collector/OpenPipeline mechanisms from [dual-write-cardinality.md](dual-write-cardinality.md)
apply. The code-vs-pipeline split is specifically about whether the raw signal exists on the
span at all, not about final attribute naming.
