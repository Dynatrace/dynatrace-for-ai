# Examples index: how to read the examples repo

Used by [Detect](../SKILL.md#1-detect) (native-OTel-vs-fallback) and
[Instrument](../SKILL.md#2-instrument) (recipe shape). This is a **thin pointer**, not a
mirror — the [examples repo](https://github.com/dynatrace-oss/dynatrace-ai-agent-instrumentation-examples)
is the source of truth and moves often, so we describe its **structure** (stable) and let
the agent read the current repo, rather than copying a recipe list that would go stale.

## Repo layout: `<sdk>/<flavor>/`

Every demo lives at `<sdk>/<flavor>/` — e.g. `openai/opentelemetry/`,
`aws-bedrock/openinference/`. The **flavor folder is the routing decision**, so the agent
derives the path by listing the SDK's folder in the repo instead of trusting a table here:

| Flavor folder | Backbone path | Meaning |
|---|---|---|
| `opentelemetry/` (also `opentelemetry-node/`) | **native OTel (supported end-to-end)** | native OTel `gen_ai.*` — the preferred path this skill instruments |
| `openinference/` | **fallback** | OpenInference instrumentor. Closes the loop only if the recipe emits `gen_ai.*` (Python semconv dual-write, `OPENINFERENCE_ENABLE_GENAI_SEMCONV`); otherwise the skill stops at a normalizer gate (see [enrich-normalization.md](enrich-normalization.md)) |
| `oneagent/` | **zero-code host** | OneAgent captures it; skip the code-change path (see [enhance-existing.md](enhance-existing.md)) |
| `zero-code/` | **native OTel, no code** | auto-instrumentation entrypoint (currently `google-adk`) |

**How to route a detected SDK:**
1. `ls <sdk>/` in the repo. Prefer `opentelemetry/` (native OTel — instrument it) if
   present; `oneagent/` means the zero-code host path is available too. If the only in-code
   folder is `openinference/`, that's the **fallback** — instrument it; it closes the loop
   only if the recipe emits `gen_ai.*` (Python semconv dual-write), else the skill stops at a
   normalizer gate before Validate (see [enrich-normalization.md](enrich-normalization.md)).
1a. **Prefer the genuine OTel-published instrumentor over a Traceloop/OpenLLMetry one.** Some
   `opentelemetry/` recipes use a Traceloop package that captures prompt/response **content by
   default** — e.g. reach for `opentelemetry-instrumentation-botocore` rather than the repo's
   `aws-bedrock/opentelemetry/` (`opentelemetry-instrumentation-bedrock`) until that recipe
   migrates. If a Traceloop package is the only native option, it's a last resort **and** a
   **stop-and-ask** (see SKILL.md's stop-and-ask list) — the name doesn't reveal the default, and
   skipping the vendor init (e.g. `Traceloop.init()`) does **not** opt you out.
2. If the SDK has no folder at all, fall back to Detect's ordered check (OTel registry →
   vendor docs → `openinference-instrumentation-<sdk>`), and check the
   [Dynatrace Hub](https://www.dynatrace.com/hub/?filter=ai-ml-observability) for coverage
   not yet demoed here.

Not every SDK has every flavor — many have only `opentelemetry/`, and a few (e.g.
`anthropic`) have **no** `opentelemetry/` at all (only `oneagent/` + `openinference/`), so
their only in-code path is the fallback. Always confirm by listing the folder.

## What's inside a recipe folder

Each recipe is runnable and follows one interface (from the repo README):

```text
cd <sdk>/<flavor>
make install   # install dependencies
make run       # start the app (port 8000)
make request   # send a test request (second terminal)
make help      # all targets
```

A recipe folder typically contains: the app code (`app.py` / `main.py`, or `src/` +
`package.json` for node), `Makefile`, `.env.sample`, `README.md`, dependency manifest
(`pyproject.toml` / `requirements.txt` / `package.json`), and — where a pipeline is needed
— `otel-collector-config.yaml` and/or `openpipeline-*.yaml`. Reuse those collector /
OpenPipeline configs as the starting point for [Enrich](../SKILL.md#3-enrich); don't
hand-author from scratch.

**Recipe code can lag the installed SDK's current API** — a pinned recipe shows the shape,
but the SDK it targets moves. Before copying its init code verbatim, check it against the
version actually resolved into the app (e.g. pydantic-ai dropped `Agent(instrument=...)` in
favour of `capabilities=[Instrumentation(settings=...)]`); if the recipe's call signature
doesn't exist in the installed package, read the installed source for the current one rather
than forcing the stale call.

## The contract and its in-repo companions

The validation target lives in the same repo and comes with usage docs and worked
examples — reference these instead of re-deriving:

- **[`test/e2e/sdk-comparison-baseline.json`](https://github.com/dynatrace-oss/dynatrace-ai-agent-instrumentation-examples/blob/main/test/e2e/sdk-comparison-baseline.json)**
  — the pass/fail contract, and the ground truth. See
  [validate-contract.md](validate-contract.md) for how [Validate](../SKILL.md#4-validate)
  asserts against it. **The contract is the version-of-record**; the `.md` companions below may
  lag it — trust the contract.
- **`test/e2e/sdk-comparison-baseline.md`** — the repo's own "how to use the baseline"
  guide (how an agent should apply the rules). Read it before asserting.
- **`test/e2e/sdk-analysis/<sdk>-<flavor>.md`** — per-recipe **worked verdicts**
  (PASS / PARTIAL) listing which attributes that SDK actually emits, which views it
  covers, and the root cause of each gap. If an analysis file exists for the SDK you
  detected, read it first — it predicts the gaps Enrich will need to close.
- **`test/e2e/<sdk>_<flavor>_test.go`** — the executable checks that assert each recipe
  (including `_openpipeline_` / `_collector_` variants) against the contract.

## Link to `main`

When you hand the user a repo link, link to `main` — it's the current source of truth and the
same ref this skill reads the contract on throughout. (The repo moves, so a pinned SHA goes
stale; `main` keeps everyone on one ref.)
