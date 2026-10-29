# Multiple SDKs in one app

Run [Detect](../SKILL.md#1-detect) once per SDK — each gets its own routing key and its
own native-OTel decision; they don't have to land on the same side. Then:

- Reuse one existing `TracerProvider`/exporter when the app already has one; only in greenfield mode create **one** shared `Resource`/`TracerProvider` for the app (not one per SDK), then attach each SDK's instrumentor to it.
- If every SDK has a native OTel path, nothing else changes.
- If any SDK has no native OTel path, use its OpenInference fallback if available. A
  semconv-dual-write path can continue directly; otherwise stop at the user-side normalizer
  gate (see [enrich-normalization.md](enrich-normalization.md)). If no OpenInference package
  exists, use [no-native-instrumentation.md](no-native-instrumentation.md). The normalizer
  must handle each source shape independently and non-destructively (one branch per
  spans doesn't touch another SDK's spans in the same trace.
- [Validate](../SKILL.md#4-validate)'s mandatory-field assertion still applies per span,
  not per app — a span from a native-OTel SDK and a normalized span from a fallback
  (OpenInference) SDK in the same trace are validated independently, each against the
  profile matching **its own** `gen_ai.provider.name` (generic + that provider's
  `additional_required_attributes`, per [validate-contract.md](validate-contract.md)) —
  not one shared profile for the whole trace.
