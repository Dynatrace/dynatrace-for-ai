# The Validate contract: the pin, the dtctl loop, and where the detail lives

Canonical home for what [Validate](../SKILL.md#4-validate) asserts against. Like
[examples-index.md](examples-index.md), this is a **thin pointer**: it gives the high-level
gate and the `dtctl` loop we run, and links to the contract's own in-repo docs for the
field-level detail — it does **not** restate every field/profile (that copy drifts).

## The contract and its pin

The single source of truth for "what a well-instrumented span must carry" is the file
[`test/e2e/sdk-comparison-baseline.json`](https://github.com/dynatrace-oss/dynatrace-ai-agent-instrumentation-examples/blob/main/test/e2e/sdk-comparison-baseline.json)
in the examples repo — **"the contract"** everywhere below. It's a **Dynatrace acceptance
gate** — a subset of the OTel GenAI
`gen_ai.*` [semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md)
that Dynatrace dashboards consume, with severity, provider profiles, and legacy-field
fallbacks layered on. **Instrument to semconv; validate against this contract.** Same contract
whatever emits the spans — native OTel or a Python OpenInference instrumentor with semconv
dual-write (which also keeps its source `llm.*`/`openinference.*` attributes).

**Read the contract on `main`** rather than pinning a version — that copy is the ground
truth; it carries its own `version` and `changelog` if you need to see what changed.

## What the gate checks (high level)

Read the contract's `comparison_contract` block for the exact rule ids/fields; the shape is:

- **`must_have_all` → FAIL if any absent:** the core five — `service.name`,
  `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`,
  `gen_ai.usage.output_tokens` (token fields have declared legacy fallbacks — see
  `required_resolution`). The contract evaluates this against the **SDK's aggregate
  emitted-attribute set**, built by scanning across all its span kinds — not required on
  every individual span. It does not itself carve out agent/tool operations; the dtctl L3
  loop below breaks the check down `by:{gen_ai.operation.name}` as a stricter, per-span
  diagnostic to localize gaps, on top of this.
- **`must_have_any` → FAIL if none present:** the provider-identity gate —
  `gen_ai.provider.name` **or** `gen_ai.system`. Prefer **`gen_ai.provider.name`**; `gen_ai.system` is **deprecated** in the OTel GenAI semconv and kept only as a fallback for older instrumentations.
- **Provider profiles extend `generic`.** `profile_selection` has a `generic` default plus
  provider profiles — `openai, azure, bedrock, anthropic, google, nvidia, kong`. **Some add
  required fields** (e.g. azure content-filter, bedrock guardrails); **others add only
  optional ones** (e.g. openai's `additional_required_attributes` is empty — its prompt-caching
  attrs are optional). **Pick the profile matching the app's provider** and read its
  `additional_required_attributes` in the contract; validating an Azure/Bedrock app against
  `generic` silently under-checks it.
- **Optional / eval attributes → WARN when absent** (e.g. `gen_ai.conversation.id`).

## The dtctl validation loop

`dtctl` is how we close the loop — it queries the spans in Dynatrace so the assertion is
mechanical, not eyeballed. (The repo asserts the same contract via Go e2e tests; `dtctl` is
our interactive equivalent.)

**First, check dtctl is installed and pointed at the right tenant:** `dtctl version`, then
`dtctl config current-context` and `dtctl auth whoami --plain`. If it's not installed,
install it — commands in the [dtctl README](https://github.com/dynatrace-oss/dtctl). Don't
proceed without it (DQL in the AI Observability app is the manual fallback, but loses the
repeatable assertion).

Then run the checks **in order, broadest first** — each level's failure localizes the fix to
a different backbone stage, so stop at the first failure and fix there before going deeper.
Replace `<svc>` with the app's `service.name`; all queries are verified dtctl/DQL syntax.

**L1 — Any spans at all?** `wait query` polls until a span lands, so it absorbs ingest lag.
Fail here = nothing is arriving → **Instrument** (exporter endpoint/token, `service.name`),
don't check attributes yet.
```dtctl
dtctl wait query 'fetch spans, from: now()-10m
  | filter service.name == "<svc>"
  | limit 1' --for=count=1 --timeout 5m -o json --plain
```

**L2 — Are they GenAI spans, and are they erroring?** Distinguishes "app runs but LLM calls
aren't instrumented" and surfaces error spans.
```dtctl
dtctl query 'fetch spans, from: now()-30m
  | filter service.name == "<svc>"
  | summarize total = count(),
      genai  = countIf(isNotNull(gen_ai.provider.name) or isNotNull(gen_ai.system) or isNotNull(gen_ai.operation.name)),
      errors = countIf(span.status_code == "error")' -o json --plain
```

**L3 — Core contract fields, per operation.** Break down `by:{gen_ai.operation.name}` to
localize gaps — but remember `must_have_all` itself isn't per-span (see above): a multi-op
SDK only fails it if a field is missing from *every* span it emits, not from each one
individually. So a per-op zero here isn't automatically a gap — agent/tool spans
(`invoke_agent`, `execute_tool`) legitimately carry no `gen_ai.response.model` or token
usage; that's expected as long as an inference op (`chat`, `generate_content`,
`text_completion`, ...) on the same service carries them. Treat a field as a real gap only
if it's absent on an inference op that should carry it, or absent across **every** operation
the service emits. The denominator (`spans`) is **not** pre-filtered on `gen_ai.request.model`
presence, so a service whose spans all lack it shows up as `request_model: 0` against a
nonzero `spans` total instead of silently vanishing. Coalesce fallbacks are baked into the
token counts → **Enrich** on a real gap.
```dtctl
dtctl query 'fetch spans, from: now()-30m
  | filter service.name == "<svc>"
  | filter isNotNull(gen_ai.provider.name) or isNotNull(gen_ai.system)
  | summarize spans = count(),
      request_model  = countIf(isNotNull(gen_ai.request.model)),
      response_model = countIf(isNotNull(gen_ai.response.model)),
      input_tokens   = countIf(isNotNull(gen_ai.usage.input_tokens)  or isNotNull(gen_ai.usage.prompt_tokens)),
      output_tokens  = countIf(isNotNull(gen_ai.usage.output_tokens) or isNotNull(gen_ai.usage.completion_tokens)),
      by:{gen_ai.operation.name}' -o json --plain
```

**L4 — Derived metrics landed?** A separate pipeline from spans, so passing L3 but failing L4
means the span→metric step (collector connector / OpenPipeline) is the gap, **not** the SDK.
The `service.name` filter must be a parameter of `timeseries` (where dimensions are in scope),
not a downstream pipe. See the metrics-lag note below before treating this as a failure.

**Discovery first, assertion second — don't let one substitute for the other.** List what
metric keys actually arrived; this is diagnostic only, it doesn't decide pass/fail:
```dtctl
dtctl query 'fetch metric.series, from: now()-20m
  | filter service.name == "<svc>"
  | filter startsWith(metric.key, "gen_ai.")
  | summarize count(), by:{metric.key}' -o json --plain
```
`metric.series` is the metric-key catalog (not `timeseries`), but `service.name` is a flat
field on each record, so filtering on it scopes the discovery to this app's own metrics —
no dimension-bracket syntax needed.

**Then assert against what the selected profile actually requires** — not against whichever
`gen_ai.*` metric happened to show up. Each profile in the contract lists its own metrics
with their own required-vs-recommended level (e.g. one metric that drives a latency view may
be required while another feeding a cost view is only recommended) — look that up for the
app's profile rather than assuming; a recommended metric landing does not satisfy a required
one. Substitute the profile's actual required metric into the query below (it uses one
example metric a native OTel GenAI instrumentation commonly emits):
```dtctl
dtctl wait query 'timeseries dur = avg(gen_ai.client.operation.duration), from: now()-20m, filter: matchesValue(service.name, "<svc>")
  | fieldsAdd total = arraySum(dur)
  | filter isNotNull(total) and total > 0' --for=count=1 --timeout 5m -o json --plain
```
If discovery shows the SDK never emits a metric the profile requires at all (pydantic-ai, for
one, emits only a token-usage metric, never a duration one), that's a real required-metric
gap — route to **Enrich** to derive it (e.g. a collector `spanmetrics`/OpenPipeline connector
deriving it from the span itself), rather than accepting a merely-recommended metric as a
substitute. Only a metric the profile requires but that never lands (and can't be derived) is
a genuine L4 (span→metric pipeline) gap.

**On any failure, don't patch in Validate** — route to the stage the level points at, then
re-run from that level:

| Fails at | Root cause | Route to |
|---|---|---|
| L1 | no export / wrong `service.name` | [Instrument](../SKILL.md#2-instrument) |
| L2 | app runs, LLM calls not instrumented | [Instrument](../SKILL.md#2-instrument) |
| L3 | field missing / mismapped (on an inference op) | [Enrich](../SKILL.md#3-enrich) |
| L4 | span→metric pipeline (only for a metric the SDK actually emits — see L4 note) | [Enrich](../SKILL.md#3-enrich) (collector / OpenPipeline) |

## Where the field-level detail lives (don't re-derive)

The contract ships its own docs in the same repo — read these instead of restating them:

- **`test/e2e/sdk-comparison-baseline.md`** — the repo's own "how to use the baseline"
  guide (how to apply the rules, silent-failure modes, per-view dependencies).
- **`test/e2e/sdk-analysis/<sdk>-<flavor>.md`** — per-recipe **worked verdicts**
  (PASS / PARTIAL) showing which attributes that SDK actually emits and the root cause of
  each gap. If one exists for the detected SDK, it tells you what Enrich must fix.
- **`test/e2e/<sdk>_<flavor>_test.go`** — the executable assertions (incl.
  `_openpipeline_` / `_collector_` variants).

The **contract on `main`** is the ground truth; the `.md` companions may lag it.

## Metrics lag spans

Derived metrics (span-to-metric extraction, whether via a collector connector or
OpenPipeline) lag the spans that produce them by roughly one periodic-reader interval
(tens of seconds). Don't treat a metric as missing if you check for it immediately after
the request that should have produced it — retry the `dtctl` query after a short wait first.

## Example queries

**Inspection only — not an assertion.** These list a span's `gen_ai.*` fields for
eyeballing; they don't check presence the way the L1–L4 `dtctl` loop above does (a
listed field can still be null). Use the L3 query above for an actual pass/fail check.
Load **dt-dql-essentials** first if you need help with DQL syntax.

```dql-template
fetch spans
| filter service.name == "<your-service-name>"
| filter isNotNull(gen_ai.operation.name)
| fields service.name, gen_ai.operation.name, gen_ai.request.model, gen_ai.response.model,
         gen_ai.usage.input_tokens, gen_ai.usage.output_tokens,
         gen_ai.provider.name, gen_ai.system
| limit 20
```

Or via `dtctl query` in the terminal:

```dtctl
dtctl query 'fetch spans | filter service.name == "<your-service-name>" | filter isNotNull(gen_ai.operation.name) | fields service.name, gen_ai.operation.name, gen_ai.request.model, gen_ai.usage.input_tokens | limit 20'
```
