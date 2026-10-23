# Dual-write cardinality: the removal decision and how to apply it

Used by [step 4a](../SKILL.md#4-close-the-gaps-the-semconv-option-leaves). Reached once step
3's semconv option is confirmed on and `gen_ai.*` is flowing. **Stop and ask before applying
either mechanism below** — removing attributes is a tenant/infrastructure change, and some
consumers may still read the legacy fields (older dashboards, saved DQL, external tooling). If
OpenPipeline is the chosen mechanism, its risk goes beyond the usual stop-and-ask — read
[openpipeline-safety.md](openpipeline-safety.md) first; it's shared tenant infrastructure, not
config scoped to this app.

## Confirm the dual-write first

Send one request through the migrated app, then list the resulting span's attributes
(`dtctl query` or DQL — load **dt-dql-essentials** for syntax if needed):

```dql-template
fetch spans
| filter service.name == "<svc>"
| filter isNotNull(gen_ai.operation.name)
| fields service.name, gen_ai.provider.name, gen_ai.operation.name, gen_ai.request.model,
         llm.system, llm.model_name, openinference.span.kind
| limit 5
```

Both the `gen_ai.*` and `llm.*`/`openinference.*` columns populated on the same span confirms
the dual-write. If the legacy columns are empty, there's nothing to remove — skip this step.

## Check which removal mechanism is actually available

Don't propose a mechanism that isn't on the table for this app's ingestion shape (see
[ingestion-shape.md](ingestion-shape.md)):

- **Collector**: is one already running in this app's actual egress path — not just present
  somewhere in the repo for an unrelated purpose? Check whether the app's OTLP exporter
  endpoint points at a local/internal collector address (e.g. `localhost:4318`, an internal
  collector service DNS name) rather than directly at `$DT_ENDPOINT`. If it points straight at
  Dynatrace, there's no collector today — see the stop-and-ask above; adding one is an
  infrastructure change dt-setup-genai already treats as out of scope for a skill to just do.
- **OpenPipeline**: does a Spans pipeline already exist that would touch this service's spans?
  `dtctl get settings --schema builtin:openpipeline.spans.pipelines -o yaml` lists what's
  deployed; check the routing entries (`builtin:openpipeline.spans.routing`) for a matcher that
  already covers `service.name == "<svc>"` before assuming a new pipeline is needed. Creating
  or editing one needs `settings:objects:write` on the target environment, is a stop-and-ask
  (tenant change), and — because the routing list is shared tenant-wide, not scoped to this
  app — needs the extra care in [openpipeline-safety.md](openpipeline-safety.md).

Only the OneAgent-pickup ingestion shape forces OpenPipeline as the sole option; for the
app-owned-exporter shape, the choice is a genuine trade-off the user should make, not something
this skill defaults for them.

## Mechanism 1: OTel Collector transform (app-owned exporter, collector in the path)

Add a `transform` processor stripping the legacy attribute families by prefix, after
`gen_ai.*` is confirmed present — don't delete before confirming, or a mapping bug becomes data
loss:

```yaml
transform/strip_openinference_legacy:
  trace_statements:
    - context: span
      statements:
        - delete_matching_keys(attributes, "^llm\\..*")
        - delete_matching_keys(attributes, "^openinference\\..*")
```

Insert this processor in the collector's `traces` pipeline **after** any processor that still
depends on the legacy attributes (there shouldn't be one, since `gen_ai.*` is already present
via the semconv option).

The `gen_ai_normalizer` is not part of this migration by default. If Validate later shows gaps
and the user approves it, note that it *reads* `llm.*`/`openinference.*` to produce `gen_ai.*`
and (with `remove_originals: true`) deletes the originals. Don't run it on spans that already
carry `gen_ai.*` from the semconv option without checking what it overwrites, and don't also run
the strip transform on spans it already cleaned.

## Mechanism 2: Dynatrace OpenPipeline (OneAgent pickup, or app-owned exporter without a collector)

An OpenPipeline Spans pipeline processor removing the same attribute families. **Read
[openpipeline-safety.md](openpipeline-safety.md) in full before touching this** — the matcher
below is only safe once scoped and reviewed the way that file describes; routing is a single
object shared by every pipeline on the tenant, not config local to this app.

- Matcher: `isNotNull(gen_ai.provider.name) and isNotNull(openinference.span.kind) and service.name == "<svc>"` —
  requiring both `gen_ai.provider.name` (confirms the semconv option is on) and
  `openinference.span.kind` (confirms it's still OpenInference-sourced) avoids catching spans
  from an unrelated native-OTel or non-dual-write source. This is the same tightly-scoped-matcher
  reasoning dt-setup-genai applies to its own normalizer OpenPipeline variant
  (`references/enrich-normalization.md`) — load that skill to read it.
- Processor: a DQL-based field-removal step dropping the `llm.*`/`openinference.*` keys. Discover
  the exact processor type and field name from the live schema, not from this or any doc snippet
  — see openpipeline-safety.md's schema-discovery command.
- Deployment mechanics (pipeline object vs. the shared routing list, read-modify-write
  discipline, who actually runs `dtctl apply`): all in
  [openpipeline-safety.md](openpipeline-safety.md) — don't skip straight to running commands
  from memory of a similar case.

Unlike the collector transform, OpenPipeline processors act after ingestion and cannot
reconstruct or restructure fields the way an OTTL statement can — for straight deletion (this
case) that's not a limitation, but don't assume the same processor could also do the fuller
`llm.*` → `gen_ai.*` remapping from dt-setup-genai's normalizer gate; that one needs the
collector's message-array reconstruction where full content matters.

## After removal

Re-run the confirm query above — the `llm.*`/`openinference.*` columns should now be null while
`gen_ai.*` stays populated. Then resume [Validate](../SKILL.md#5-validate).
