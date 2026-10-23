# Ingestion shape: app-owned exporter, OneAgent pickup, or Traceloop-managed

Used by [step 2](../SKILL.md#2-confirm-the-ingestion-shape). The same
`SomeInstrumentor().instrument(config=TraceConfig(enable_genai_semconv=True))` call looks
identical in source regardless of which shape the app is actually in — the difference is
entirely in what surrounds it, so **read the surrounding init code, don't infer from the
instrumentor call alone.**

## Shape A: app-owned trace exporter ("the documented way")

The app builds its own pipeline and calls `set_tracer_provider(...)` before the instrumentor
runs:

1. A `Resource` with at least `service.name`.
2. A `TracerProvider(resource=...)` constructed from it.
3. One or more `add_span_processor(...)` calls, at least one wrapping a `BatchSpanProcessor`
   around an OTLP exporter (`OTLPSpanExporter` in Python, `OTLPTraceExporter` in Node) pointed
   at Dynatrace directly or at a collector.
4. `trace.set_tracer_provider(tracer_provider)` — this makes it the process-wide default
   before any instrumentor's `.instrument()` call runs.

**Illustrative shape** (not a specific real file — verify against the actual app instead of
pattern-matching a remembered example):

```python
resource = Resource.create({"service.name": "my-service"})
tracer_provider = TracerProvider(resource=resource)
tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=...)))
trace.set_tracer_provider(tracer_provider)  # must run before the instrumentor below

SomeInstrumentor().instrument(config=TraceConfig(enable_genai_semconv=True))
```

Because the app owns the `OTLPSpanExporter`, an OTel Collector can be inserted between it and
Dynatrace without touching the app itself — that's what makes the collector-transform option in
step 4 available for this shape. If a codebase has an internal self-monitoring or telemetry
init module that looks like it fits this shape, confirm the actual current instrumentor call in
that file before citing it as an example — don't assume a prior look at the file (your own
memory, another doc, or a work-in-progress branch) still matches what's actually committed
there today.

## Shape B: instrumentation-only, OneAgent picks it up

The code calls only the instrumentor:

```python
LangChainInstrumentor().instrument(config=TraceConfig(enable_genai_semconv=True))
```

— with **no** accompanying `TracerProvider` construction, `add_span_processor` call, or
`set_tracer_provider` call anywhere in the app's init path. On a host where Dynatrace OneAgent
is already injected into the process (`oneagent` process/package present — same host check as
dt-setup-genai's own Detect step), OneAgent captures the spans the instrumentor produces by
hooking the process directly; it doesn't need the app to configure or run any exporter of its
own. **Nothing the app controls sits on the network path from span creation to Dynatrace** —
there is no OTLP call for a collector to intercept — so a collector transform is not an option
for this shape; only Dynatrace OpenPipeline can act on these spans, and only after they've
already been ingested.

## Shape C: Traceloop-managed exporter (a pre-migration state)

The app calls `Traceloop.init()` and the code shows none of the Shape A symbols — but
Traceloop creates them for it. Without an explicit `exporter`/`processor` argument, `init()`
creates and sets the global `TracerProvider` (reusing an SDK provider if one is already set)
and attaches a default `BatchSpanProcessor` + OTLP exporter. The destination comes entirely
from env vars: `TRACELOOP_BASE_URL` (default `https://api.traceloop.com`), `TRACELOOP_HEADERS`,
or `TRACELOOP_API_KEY` — so an app can already be exporting to Dynatrace (or a collector) with no
exporter code at all. `init()` also sets up metrics and logging exporters on the same endpoint.

**Replacing `Traceloop.init()` with only an OpenInference instrumentor removes this export path
and telemetry stops.** Before removing the init: read the `TRACELOOP_*` env vars (and any
deployment config) to find the current destination; add an explicit Shape A provider + exporter
pointing at it (credentials stay in env vars or the secret store — never printed); carry over
metrics/log export if the app relied on it. That makes the app Shape A for step 4. By
contrast, `init_instrumentations(...)` registers instrumentation only — no provider or exporter
— and behaves like Shape B.

## Telling them apart

1. Find where the instrumentor's `.instrument(...)` call lives.
2. Search the same module and its imports for `TracerProvider(`, `add_span_processor(`,
   `set_tracer_provider(`, `OTLPSpanExporter(` / `OTLPTraceExporter` (or a collector-pointed
   `OTEL_EXPORTER_OTLP_ENDPOINT`). Found → Shape A.
3. None of that, but `Traceloop.init(` is called → Shape C (check this *before* concluding B).
4. None of that, no `Traceloop.init(` (e.g. only `init_instrumentations(...)`), and OneAgent is
   confirmed on the host → Shape B.
5. **A host can have both** — an app can own an explicit exporter (e.g. for a dedicated
   self-monitoring pipeline) while OneAgent *also* auto-instruments the same process
   independently. In that case Shape A's availability (a collector can sit in the app-owned
   exporter's path) still holds for the spans going through that exporter; it says nothing
   about whatever OneAgent captures separately on the side. Don't conflate the two pipelines
   when deciding what's fixable in step 4 — trace which pipeline the spans you're trying to
   fix actually came through.
6. **When genuinely unsure, ask** rather than guess from the SDK or the presence of OneAgent
   alone — the shapes require different remediation, and guessing wrong sends
   the user toward a mechanism (a collector) that doesn't exist in their actual path.
