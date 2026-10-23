# OpenPipeline: shared tenant infrastructure, not app-scoped config

Referenced from [step 4a](../SKILL.md#4-close-the-gaps-the-semconv-option-leaves)/4b and
[dual-write-cardinality.md](dual-write-cardinality.md)/[incomplete-attribute-mappings.md](incomplete-attribute-mappings.md)
whenever OpenPipeline is the chosen mechanism. dt-setup-genai already puts any OpenPipeline
change behind a stop-and-ask; this goes one step further, because a mistake here doesn't stay
scoped to the app being migrated — it can silently change what happens to every other app's
spans on the same tenant.

## Two different objects, two different risk levels

- **A Spans pipeline** (`builtin:openpipeline.spans.pipelines`, multiObject) — one settings
  object per pipeline. Creating a new one is additive and doesn't touch any existing pipeline
  object.
- **The routing table** (`builtin:openpipeline.spans.routing`) — a **single** settings object
  for the entire tenant, holding one `routingEntries` list that every pipeline's matcher lives
  in. There is no way to add "this app's route" without reading and rewriting the whole
  tenant-wide list. This is the part that actually carries shared-infrastructure risk — the
  pipeline object itself is comparatively safe.

## Before proposing any routing change

1. **Fetch the full current list first**, not just a search for whether this service already
   has an entry: `dtctl get settings --schema builtin:openpipeline.spans.routing -o yaml`. Show
   the user the complete `routingEntries` list as it stands today, not a summary — they need to
   see what else is on the tenant before approving a change to a shared object.
2. **Routing is first-match-wins, not fan-out.** An earlier, more specific entry can silently
   shadow a later, broader one even when the later matcher also matches — this has been
   confirmed empirically, not just inferred from the schema (there's no stop/priority field
   either way). Check where the new entry would land in evaluation order, not just that a
   matcher string is correct.
3. **Appending blindly is unsafe precisely because of point 2.** If the tenant already has a
   broader matcher or the usual trailing catch-all (`matcher: "true"`), an entry appended after
   it is unreachable — first-match-wins means the broader entry already won. Preserve every
   existing entry's **relative order**, but insert the new, more specific route **before** the
   first broader/catch-all matcher that would otherwise shadow it. Reordering or removing an
   **existing** entry is a different, higher-stakes request than inserting this migration's own
   route — that needs its own explicit confirmation, separate from "yes, add my route."
4. **Scope the new matcher as tightly as this app allows** — `service.name == "<svc>"` combined
   with a content marker (`isNotNull(gen_ai.provider.name)`, `isNotNull(openinference.span.kind)`,
   or the equivalent for the specific gap being closed). An unscoped or loosely-scoped matcher
   doesn't just mis-tag this app's spans, it can capture spans from any other app on the tenant
   that happens to match — load **dt-setup-genai** and see its own normalizer OpenPipeline variant
   (`references/enrich-normalization.md`) for the same caution applied to its own routing entry.
5. **Read-modify-write discipline when applying**: `dtctl get` on a single-object schema returns
   the object wrapped in a list (`[obj]`) but `dtctl apply` expects a bare object — unwrap it.
   Strip read-only fields (`schemaversion`, `externalid`, `summary`, `modificationinfo`) before
   writing back; they're harmless to drop but will be rejected or cause confusion if resubmitted
   verbatim.
6. **Show the exact diff of the routing list** — old list vs. new list, with the added entry
   highlighted — as part of the stop-and-ask, not just "I'll add a route for this app." A yes to
   "can I add OpenPipeline routing" is not informed consent to whatever the actual list mutation
   turns out to be; the user approves the literal change, not the intent.

## Creating or updating the pipeline object itself

Lower risk than routing, but still a tenant object, still stop-and-ask:

```bash
dtctl create settings -f <file>.yaml --schema builtin:openpipeline.spans.pipelines --scope environment
```

Use `dtctl apply` instead of `create` only when updating an **existing** pipeline by its
`objectId` — confirm the `objectId` belongs to a pipeline this migration created or that the
user has identified as theirs to change, not a same-looking pipeline another app already owns.

## Discovering the exact processor syntax

Don't guess field names for a processor from a doc snippet, including this skill's own
snippets in [dual-write-cardinality.md](dual-write-cardinality.md) and
[incomplete-attribute-mappings.md](incomplete-attribute-mappings.md) — the live schema is the
source of truth and can move independently of this doc:

```bash
dtctl describe settings-schema builtin:openpipeline.spans.pipelines -o json --plain
```

## Who actually applies the change

Prefer handing the user the exact `dtctl` commands and the reviewed diff and letting them run
it themselves, the same way dt-setup-genai hands over the normalizer config rather than
applying it on the skill's behalf. Only run `dtctl create`/`apply` directly if the user
explicitly asks you to do it for them — and even then, the routing-list diff from step 6 above
is what they're approving, not a generic "go ahead."
