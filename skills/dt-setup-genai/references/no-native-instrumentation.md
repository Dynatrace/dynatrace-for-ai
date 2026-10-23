# When no packaged instrumentation exists at all

If [Detect](../SKILL.md#1-detect) finds no native OTel path **and** no OpenInference
package either, there is no packaged instrumentation for the SDK yet. Don't invent a
bespoke one-off — instead, hand-write manual OTel spans directly against the
[OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/):

1. In enhance-existing mode, attach the manual tracer to the existing `TracerProvider` and reuse its exporter; only in greenfield mode create the fresh `Resource`/`TracerProvider`/exporter described in [Instrument](../SKILL.md#2-instrument)'s common shape.
2. Wrap the SDK call yourself in a span setting the mandatory `gen_ai.*` attributes by
   hand at the call site: `gen_ai.provider.name`, `gen_ai.operation.name`,
   `gen_ai.request.model`, `gen_ai.response.model`, token-usage attributes — matching the
   same contract [Validate](../SKILL.md#4-validate) checks against.
   Only set these attributes if they are made available by the provider. Do not fabricate them
   just for the purpose of matching the contract. If an attribute can not be added, inform the
   user about the gap.

Treat this as a stopgap, not a destination: file it as a gap against the SDK. If native
OTel support later lands, migrate to it; if only an OpenInference instrumentor lands, switch
to that fallback (instrument, then the user-side normalizer gate — see
[enrich-normalization.md](enrich-normalization.md)). Either way, remove the manual span code
once a packaged path exists.
