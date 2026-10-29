# Detecting an existing Traceloop/OpenLLMetry setup

Used by [step 1](../SKILL.md#1-detect-the-existing-traceloopopenllmetry-setup). The goal is
to confirm this is a migration (this skill applies) rather than a first-time instrumentation
(dt-setup-genai applies), and to enumerate every SDK the existing setup wraps so step 3 swaps
all of them, not just the first one found.

## What to grep for

- **The SDK dependency itself**: `traceloop-sdk` in `pyproject.toml` / `requirements.txt` /
  `package.json`. This is the unambiguous signal — if present, the app is on Traceloop.
- **Init call**: `Traceloop.init(` (Python) or the Node equivalent
  `require('@traceloop/node-server-sdk')` / `Traceloop.initialize(`.
- **Env vars only Traceloop reads**: `TRACELOOP_API_KEY`, `TRACELOOP_BASE_URL`,
  `TRACELOOP_TRACE_CONTENT`, `TRACELOOP_ASSOCIATION_PROPERTIES`. Any of these present without
  a corresponding OTel-standard equivalent nearby is a strong signal.
- **Span attributes on already-flowing telemetry**: if spans are already visible in Dynatrace,
  `traceloop.entity.name`, `traceloop.entity.path`, or `traceloop.association.properties.*`
  are Traceloop-specific and won't appear from a native-OTel or OpenInference source.

## The package-name trap

Some Traceloop-authored instrumentation packages are published under the generic
`opentelemetry-instrumentation-<sdk>` name on PyPI/npm — the same naming pattern a genuine
OTel-contrib package uses. **Don't infer "native OTel" from the package name alone.** Check:

- The package's actual source repo / maintainer (PyPI project page, npm `repository` field, or
  the installed package's own `__init__.py` / `LICENSE` header) — Traceloop-authored packages
  point back to `github.com/traceloop/...`.
- Whether it reads `TRACELOOP_TRACE_CONTENT` for its message-content capture toggle instead of
  the OTel-standard `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` — if so, it's a
  Traceloop package regardless of its distribution name.

This is the same trap dt-setup-genai's own Instrument step and its `examples-index.md` flag for
greenfield instrumentation — load the **dt-setup-genai** skill to read it. It applies identically
here, just discovered in an already-instrumented app instead of chosen fresh.

## Enumerate every wrapped SDK

A single `Traceloop.init()` call typically auto-instruments every supported SDK it finds
installed (OpenAI, Anthropic, Bedrock, LangChain, ...) — it isn't scoped to one. List the
app's actual LLM/agent-framework dependencies (same dependency-manifest read as dt-setup-genai's
own Detect step) rather than assuming the app only uses whichever SDK the first grep hit
happened to mention. Each one needs its own `openinference-instrumentation-<sdk>` package in
step 3 — if there's more than one, load **dt-setup-genai** and follow its `multi-sdk-apps.md`.
