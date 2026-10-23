# Enhance-existing: per-case breakdown

Enhance-existing is the **default**. Treat the task as enhance-existing when **any** of these
holds:

- The user points you at an existing repository or application.
- A sibling recipe already implements the same provider, SDK, or instrumentation family — read
  it from the examples repo before writing your own.
- Existing workflows, Makefiles, manifests, tests, or env-var conventions govern the new code.
- The file you add is new **but lands in an established repo** — a new directory or file is
  **not** greenfield just because it doesn't exist yet. The enclosing repo is the contract.

Greenfield is the narrow exception: no repo, sibling, build, test, or deployment contract to
preserve. **When unsure, it's enhance-existing.**

**Before proposing changes:**
1. Inspect the closest sibling implementation.
2. Inventory the existing env vars, lifecycle, dependencies, tracing setup, and test conventions.
3. Prepare a **minimal** diff that conforms to them.
4. Show the diff and get approval before editing (per SKILL.md's stop-and-ask on app-code edits).
5. Preserve existing conventions unless the user asks to change them, or a demonstrated
   incompatibility forces it.

[Detect](../SKILL.md#1-detect) must identify what's already active before
[Instrument](../SKILL.md#2-instrument) touches anything, because it changes what's safe
to do:

- **OneAgent already installed on the host** → skip Instrument's code-change path
  entirely; the remaining work is [Enrich](../SKILL.md#3-enrich) (entity naming,
  correlation) and [Validate](../SKILL.md#4-validate).

- **An existing OTel `TracerProvider`/exporter already configured for other
  telemetry** → Instrument must attach a *new span processor to the existing provider*,
  not create a second provider or rely on a second `set_tracer_provider(...)` call —
  global provider registration is one-shot in these SDKs, so new instrumentation may
  bypass the existing exporter while existing spans continue using the original
  provider. The "Common shape" list builds a fresh `Resource` + `TracerProvider` — that
  shortcut is **not safe to copy verbatim** here: an OTel `Resource` is immutable once a
  `TracerProvider` is constructed with it, so it can't be patched retroactively.
  `gen_ai.agent.name` and other span-level attributes the existing provider is missing
  can be added as span/span-processor-level attributes instead (or in Enrich). But
  `service.name` lives on the **Resource**, not the span — it can't be fixed this way.
  If the existing provider's `service.name` is wrong or missing for this app, that's a
  provider-level gap (recreate the provider, or accept the shared service identity);
  flag it to the user rather than papering over it with a span attribute. Only reuse the
  existing provider's exporter wiring, not its resource.

- **Partial/incomplete instrumentation already present** (e.g. spans exist but are
  missing `gen_ai.*` fields) → skip straight to Enrich with the existing span shape as
  input, then Validate; Instrument may not need to change at all.

Service/entity naming must avoid colliding with the existing app's identity
(`service.name` or OneAgent process-group title) unless the goal is intentionally to
merge into the same entity.
