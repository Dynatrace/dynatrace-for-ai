# The OpenInference fallback gate: normalize before you can validate

Reached from [Detect](../SKILL.md#1-detect) step 3 / [Instrument](../SKILL.md#2-instrument) when
the semconv dual-write flag (`OPENINFERENCE_ENABLE_GENAI_SEMCONV`, set at Instrument) wasn't
available or didn't fill the contract — TS/node instrumentors, older versions, or fields the
mapping leaves empty. Spans then arrive as `llm.*`/`openinference.*`, not `gen_ai.*`, so
[Validate](../SKILL.md#4-validate) can't pass until they're normalized.

The skill **can't do the normalization for the user** — it's a collector or OpenPipeline config on
their tenant. Hand them the normalizer config, **stop until they confirm it's applied**, then resume
enrich → validate. Don't hand-author the mapping — every `<sdk>/openinference/` recipe in the
examples repo ships it ready to reuse.

## Hand the user the normalizer config

Point them at the matching `<sdk>/openinference/` folder in the
[examples repo](https://github.com/dynatrace-oss/dynatrace-ai-agent-instrumentation-examples),
which carries the `llm.*`/`openinference.* → gen_ai.*` normalization already wired up. Two
mechanisms, **not fully equivalent**:

- **OTel Collector transform** — `otel-collector-config.yaml` with a **`gen_ai_normalizer`**
  processor (`sources: - name: openinference`, `remove_originals: true`): maps model,
  provider, token usage, tool, agent, and session attributes, and **reconstructs the
  flattened `llm.input_messages.N.*` / `llm.output_messages.N.*` into the full
  `gen_ai.input.messages` / `gen_ai.output.messages` arrays**. Pick this when full
  message-content reconstruction matters. Worked example (also mirrors request→response
  model and lifts Azure content-filter results):
  [`langgraph/openinference/otel-collector-config.yaml`](https://github.com/dynatrace-oss/dynatrace-ai-agent-instrumentation-examples/blob/main/langgraph/openinference/otel-collector-config.yaml).
- **Dynatrace OpenPipeline** — an `openpipeline-openinference.yaml` Spans pipeline routing
  on presence of the source field. `openinference.span.kind` is set by *every* OpenInference
  instrumentor, so scope the matcher with `service.name` too
  (`isNotNull(openinference.span.kind) AND service.name == "<svc>"`); OpenPipeline routing is
  first-match-wins, so an unscoped matcher would also grab spans from any other OpenInference
  app on the tenant. No collector to run, but DQL processors **can't** reconstruct full
  message arrays — message content ends up incomplete. Example folder shipping this variant:
  [`anthropic/openinference/openpipeline-openinference.yaml`](https://github.com/dynatrace-oss/dynatrace-ai-agent-instrumentation-examples/blob/main/anthropic/openinference/openpipeline-openinference.yaml).

Choose per the trade-off above (collector = full message arrays; OpenPipeline = no collector to
run, incomplete content). Link the user to `main`. Once they confirm the
normalizer is live, re-run [Validate](../SKILL.md#4-validate) from L1.
