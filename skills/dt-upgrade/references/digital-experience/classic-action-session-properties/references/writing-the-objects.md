# Writing the objects: apply, lock, route, and the end state

Part of [Classic Action and Session Property Capturing](../classic-action-session-properties.md).
This is step 5 and what it leaves behind. The write spans **two APIs on two hosts with two
credentials**, and the pipeline half is the half that can be clobbered. `apply` performs the whole
sequence; this file says what holds while it runs, so you can answer whether it is safe.

⛔ **The capture half is written to `builtin:rum.web.capture-properties` and nothing else.** If the
environment offers only the deprecated `builtin:rum.web.capture-custom-properties`, `preflight`
reports it: **say it is deprecated, stop and report the environment** — never write the migrated
properties to it as a fallback.

## Step 5 — Apply

```bash
python3 migrate_rum_properties.py apply --out-dir "$HOME/dt-rum-migration" [--dry-run]
```

Four things hold while this step runs, and they are the answer when asked whether it is safe:

- **Merge, never replace** — planned entries go into whatever the settings object already holds, so
  properties configured on an earlier attempt survive. A Gen3 property that already exists with a
  different definition is kept and reported, unless `--overwrite-existing` is passed.
- **The previous value is backed up first**, to `backup-<stamp>.json`.
- **Applications stay isolated** — one failure must not abort the rest.
- **`configLessProperties` is untouched**, and so is classic configuration.

A dry run is a client-side preview, not evidence that the write will succeed.

**Two credentials, two hosts.** The capture settings go through the Environment API with
`DT_CLASSIC_TOKEN`; the pipeline and its route go through the platform Settings API with
`DT_PLATFORM_TOKEN`, because the Environment API no longer serves those schemas. A wrong token
shows up as a `401`, a wrong host as a `404`. `apply --capture-only` writes the first half without
the platform token, and `apply --pipeline-only` writes the second later — the migration is
half-applied until both have run against the same plan, and `status` says which half is missing.

⛔ **Tell the user a new pipeline does nothing until a routing entry points at it** — creating it
changes no data. `apply` writes both, pipeline first; if the route fails after the pipeline was
created, the summary says so and names the command that finishes or undoes it.

**Why the routing object needs care.** Routing is one object the whole environment shares, and the
only one this migration touches that others write too. `apply` reads it by id, saves its full value
as the undo, puts the new entries at the front and writes the whole list back under an optimistic
lock that every write spends. Two consequences to say when asked:

- **An entry you add can be removed by the next thing that writes the object.** If a promoted
  property stops arriving, re-read `routingEntries` before you look at the processor.
- **The undo has an order:** restore the route first, then delete the pipeline. `restore` does it
  that way; the reverse leaves a route pointing at a pipeline that is gone.

**Artifacts:** `backup-<stamp>.json`, `apply.json`.

## Outcome

Per application, one `builtin:rum.web.capture-properties` settings object scoped to the classic
`APPLICATION-…` id, holding two merged lists:

- `capturedEventProperties` — `propertyKey` plus ordered `capturingSteps`, for every property
  Dynatrace captures from the page for you;
- `allowedApiReportedProperties` — `propertyKey` plus `caseInsensitivePropertyKey`, for every
  property your code sends.

Mobile applications get the same shape from `builtin:rum.mobile.capture-properties`, with the
allow-list only. Where the plan has pipeline work, the end state also includes a user-events
pipeline and one route to it, holding — in this order — the query-string splits, the cleanup-rule
extractions, the DNT masking, one promotion per row-2C property, one processor per application that
sets `user.identifier` from its classic user tags, and, if the carrier event properties were
dropped, one removal per key after everything that reads them. So the Grail end state carries each
value in the one namespace classic gave it.

Classic configuration is left exactly as it was, so classic keeps running while you confirm the new
data. For a large API-driven estate, `configLessProperties` is worth naming as an option — it
allows every property and counts none — but it is a preview capability behind a feature flag, so
do not apply it as the default. You can suggest it to the user, but they need to get in contact
with Dynatrace in order to try it.
