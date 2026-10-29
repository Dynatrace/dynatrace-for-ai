# Baseline and rollback state

Used by [step 0](../SKILL.md#0-capture-baseline-and-rollback-state). The migration changes
which attributes a span carries — Traceloop's `gen_ai.prompt.*` / `gen_ai.completion.*` /
`traceloop.*` fields become the semconv `gen_ai.*` set (plus the legacy `llm.*` /
`openinference.*` dual-write) — so capture what exists today *before* editing anything. Without
it, "did the migration regress anything" has no reference point, and an undo has no recipe.

## Baseline: what the service emits today

Query the service's current spans and save the output (a file or the ticket, not just the chat):

```dql-template
fetch spans, from: now()-24h
| filter service.name == "<svc>"
| summarize spans = count(),
    provider      = countIf(isNotNull(gen_ai.provider.name) or isNotNull(gen_ai.system)),
    request_model = countIf(isNotNull(gen_ai.request.model)),
    input_tokens  = countIf(isNotNull(gen_ai.usage.input_tokens) or isNotNull(gen_ai.usage.prompt_tokens)),
    output_tokens = countIf(isNotNull(gen_ai.usage.output_tokens) or isNotNull(gen_ai.usage.completion_tokens)),
    by:{gen_ai.operation.name}
```

Record the service's `gen_ai.*` metric keys too — OpenInference instrumentors emit no
metrics, so these vanish after the swap unless step 4d re-creates them:

```dql-template
fetch metric.series, from: now()-24h
| filter service.name == "<svc>"
| filter startsWith(metric.key, "gen_ai.")
| summarize count(), by:{metric.key}
```

Also record which of the Traceloop-specific attributes (`traceloop.entity.name`,
`traceloop.span.kind`, `gen_ai.prompt.*`) are actually populated — step 5's comparison needs
to know what disappears, not just what appears.

## Consumers of the old attributes

List what reads the attributes that will change: dashboards, notebooks, alert/anomaly settings,
metric extractions, OpenPipeline rules, saved DQL. Search their definitions for the attribute
names from the baseline. Anything that reads a Traceloop-only field breaks silently after the
swap — surface those to the user before step 3, not after.

## Rollback

- Do the migration on its own branch/commit so it reverts as one unit.
- Keep the Traceloop dependency's pinned version recoverable from version control (don't just
  delete it from the lockfile with no history).
- Note every env var the Traceloop setup used (`TRACELOOP_*`, plus any exporter endpoint/header
  vars) so the old init can be restored exactly.
- If steps 4a/4b applied a collector transform or OpenPipeline change, record exactly what was
  created (collector config diff; pipeline `objectId` and the routing-list diff from
  [openpipeline-safety.md](openpipeline-safety.md)) so each can be removed independently.
- Roll out to one service or environment first when more than one app shares the setup.
