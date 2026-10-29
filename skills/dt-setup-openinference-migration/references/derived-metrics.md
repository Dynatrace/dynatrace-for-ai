# Derived metrics: re-creating what the Traceloop swap removes

Used by [step 4d](../SKILL.md#4-close-the-gaps-the-semconv-option-leaves). OpenInference
instrumentors are span-only — they create no metric instruments. Traceloop's instrumentations do,
so after the swap `gen_ai.client.token.usage` and `gen_ai.client.operation.duration` stop
arriving. The AI Observability app's metric-based cost and latency charts then lose the service,
even though its spans are fine. The token counts and durations still exist, as span attributes
and span timing, so the metrics can be derived from them.

## Confirm it's actually gone

Compare against the metric keys recorded in the step 0 baseline
([baseline-and-rollback.md](baseline-and-rollback.md)). Check before building anything — the
tenant may already derive these metrics from spans:

```dql-template
fetch metric.series, from: now()-1h
| filter service.name == "<svc>"
| filter startsWith(metric.key, "gen_ai.client.")
| summarize count(), by:{metric.key}
```

Metrics lag spans by tens of seconds, so retry once before calling them missing.

## Mechanisms, by ingestion shape

- **Collector in the path** — first confirm the collector distro contains the connectors (see
  below), then derive them with connectors on a *separate* pipeline branch that
  filters to LLM spans, so the export pipeline still carries every span. `span_metrics` produces
  the duration histogram; the token counter needs `signal_to_metrics`, because it is built from a
  span attribute (`gen_ai.usage.input_tokens`/`output_tokens`) with a synthesized
  `gen_ai.token.type` dimension. The examples repo's `langgraph/openinference/otel-collector-config.yaml`
  has working `span_metrics`, `signal_to_metrics`, and filter blocks to start from (its input and
  output token definitions share one metric name, and merge into one metric only because their
  name, unit, and description are identical — keep them identical if you adapt it). Take only
  those blocks — not its `gen_ai_normalizer` (see SKILL.md step 3). Keep the dimensions the
  baseline's metrics carried (model, provider, operation name, token type) so existing charts
  still match.
- **No collector, or OneAgent pickup** — OpenPipeline metric extraction on the Spans pipeline.
  Discover the exact processor types and fields from the live schema
  (`dtctl describe settings-schema builtin:openpipeline.spans.pipelines -o json --plain`), not from
  a doc snippet. It is shared tenant infrastructure: read
  [openpipeline-safety.md](openpipeline-safety.md) before proposing it.

Either way this is a stop-and-ask — a collector or tenant change — and the user may prefer to
accept the loss for a service that doesn't use the metric-based charts.

## Collector distro: check the connector is available first

**Before proposing connector-based metrics, check that the collector image in use actually
contains the connectors.** If the app runs the Dynatrace OTel collector distro, look up the
pinned image tag's manifest
(`https://raw.githubusercontent.com/dynatrace/dynatrace-otel-collector/<tag>/manifest.yaml`) and
grep the `connectors:` section for each connector's gomod path (`spanmetricsconnector`,
`signaltometricsconnector`). That distro ships `spanmetricsconnector` but, when last checked
(2026-10-05, release v0.57.0), not `signal_to_metrics` — so the token-usage metric can't be built
there, and a config using it should be rejected at startup as an unknown component.

**Fallback: the Bindplane collector** (`ghcr.io/observiq/bindplane-agent`), which includes the
span-to-metrics connectors. Offer it as the alternative to OpenPipeline for the token metric, as
a stop-and-ask (it changes the collector image). Switch only the affected service's image, not
every service sharing the repo, and confirm with an actual run that the expected metric
datapoints appear before trusting it — a manifest or component list saying "present" isn't proof
the config works.

## Delta temporality

Dynatrace's OTLP metric ingest accepts delta temporality only. Set `aggregation_temporality`
to delta on `span_metrics`, and set `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta` for
any metrics the app exports itself — cumulative metrics are rejected.
