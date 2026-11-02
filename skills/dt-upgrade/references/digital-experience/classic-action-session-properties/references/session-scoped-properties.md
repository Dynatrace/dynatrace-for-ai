# Session-scoped properties: the row-2 decision, and the carrier

Part of [Classic Action and Session Property Capturing](../classic-action-session-properties.md).
Configuration in Latest Dynatrace can only write `event_properties.*`, so a property classic
captured from the page **and** stored on the session has no configuration-only equivalent. One of
three dispositions is chosen per property, and 2C brings a second, optional decision with it.

## Choose per property, for a configured session-scoped property (row 2)

| Option                                   | What you get                                                                                                                                                                                            | What it costs                                                                                                                                                                        |
|------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **A** — accept event scope               | Nothing to deploy; the migration is complete when the object is applied                                                                                                                                 | The value lands on every event that captures it instead of once per session, so queries aggregate over `user.events` with `takeFirst`/`takeLast` on the `event_properties` namespace |
| **B** — keep session scope, with code    | True session scope, and the value is sent exactly when the user decides                                                                                                                                 | A release: declare the key, then call `dynatrace.sendSessionPropertyEvent()` where the value becomes known                                                                           |
| **C** — keep session scope, without code | True session scope, no release, and the classic `aggregation` setting survives as configuration — including the numeric strategies, which need the value cast to the type the classic property declared | A pipeline and a routing entry, both generated from the plan; the permission to write them, and a shared routing object to merge into. The value also lands in `event_properties.<key>`, which classic never had — removable, and worth offering |

Option A is the cheapest, and right when a DQL query the user controls is what reads the data. Option C
is right when something *else* reads `user.sessions` — a dashboard, a segment, a saved query, an
alert — because event-scoped data never reaches `user.sessions` on its own and nothing reconstructs
it later. This also applies to Dynatrace apps like the Users & Sessions app.

⛔ **C is the default; do not ask before planning it.** `plan` without `--row2` plans every such
property as C and says so in `tellTheUser`. The letters are the CLI's, not the user's: the user
hears *on the session, set by a pipeline rule* (C), *per event* (A) and *on the session, set by your
code* (B), as `tellTheUser` and `plan-report.md` say them. Tell the user that the default means
pipeline changes — a pipeline and its route — written after the capture settings. If the user does
not want pipeline changes, offer the other two; `ifTheUserChooses` in the `plan` output names the
re-run each answer means — a property whose only reader is a query the user controls is better off
per event.

Once C is chosen the pipeline is not an extra. Configured capture writes event properties and only
event properties, so a C property is still unmigrated after the settings object is applied, and the
pipeline is the only way to finish it without shipping a release. It is also the part with no
judgement left in it — the classic key, its `aggregation` and the application id determine the
processor, its matcher and its route completely — which is why the plan emits the bodies rather than
a description of them. It is a **user-events** pipeline, not a user-sessions one. A promoted key
needs no declaration anywhere: ingest, including the allow-list, completes before OpenPipeline sees
the record.

## Remove the carrier event property, or keep it

Row 2C finishes with the value in **two** namespaces: `event_properties.<key>`, which the
configured capture writes, and `session_properties.<key>`, which the promotion copies it into.
Classic had one. A property classic scoped to the session *was* a session property and nothing
else, so the event-scoped copy is not a migrated feature — it is the carrier the promotion had to
read, left behind afterwards.

**Suggest removing it, and let the user decide.** The plan keeps it unless asked, so a plan
generated before this existed does not change under anyone:

| How the plan is run                               | What you get                                                                                                                                       |
|---------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------|
| *(default)*                                       | Both namespaces. Every promoted row carries the flag `event-property-kept-beside-the-session-property`, and the summary repeats the suggestion once |
| `--drop-event-property`                           | Every promoted property loses its carrier, and every user tag loses the key this migration invented for it                                        |
| `--drop-event-property-key <classic key>=yes\|no` | One key, either way, overriding the default                                                                                                        |

What removing it buys, and what it costs:

- **It restores the scope classic had.** One value in one namespace, and the namespace the
  property was configured with. Nothing can read `event_properties.<key>` and mistake it for a
  session property, because the field is not there.
- **It saves no money.** A session property bills on its presence in the session, and that is the
  copy that stays. Call this a fidelity choice; never present it as a cost saving.
- **It breaks anything already reading `event_properties.<key>`.** On a fresh migration there is
  nothing to break. On an application that has been running on row 2C for a while there may be a
  dashboard, a segment, a saved query or an alert built against the carrier — ask before removing.
- **It costs you a diagnostic.** With both fields present, comparing the per-event count against
  the per-session count separates a capture that never fired from a promotion that did not run.
  Once the carrier is gone, an empty session property has one fewer explanation you can rule out.
- **It applies from the moment it is written.** Records ingested before the change keep the
  carrier; records after it do not.
- **It can flip `characteristics.has_event_properties` on the application.** That characteristic
  is re-derived per record, not stored once, so removing the *last* `event_properties.*` key an
  application writes makes it go **missing** on every record after the change. That is the
  derivation working correctly — the record genuinely has no event properties — but a dashboard,
  a segment, a saved query or an alert that filters on it silently stops matching. Check for one
  before removing the carrier of an application's only captured property.

Two mechanics that are not stylistic:

- ⛔ **The removal is a second processor, never a `fieldsRename` — and tell the user why when they
  propose a rename.** The promotion writes two fields, the value and
  `session_properties_aggregation.<key>`, and a rename writes neither.
- ⛔ **Every removal runs after everything that reads the field — say that processors in a stage
  execute in array order.** The plan holds all removals back and emits them at the end of the
  application's list rather than beside the rule that produced each one. **Say also that user
  tagging is one `coalesce` statement per application**, reading every tag carrier, so no
  removal position beside a single property's rule can be right for it. This is load-bearing when a single
  captured property feeds both a promotion and a user tag: a removal emitted beside the promotion
  would delete the value before the tagging statement ever read it.

```dql-snippet
fieldsRemove event_properties.cart_total
```

with `matcher: isNotNull(event_properties.cart_total)`, on the same user-events pipeline, after
the promotion.

**The capture-properties entry stays.** Only the field is removed, and only in the pipeline. The
`capturedEventProperties` entry is what produces the value for the promotion to read, so deleting
it leaves the promotion with nothing and the session property empty.

**Verify the promotion, then remove the carrier.** The removal and the promotion run in the same
processing stage, and that stage runs ahead of the session aggregation the directive drives. On
the event this is measured, not inferred: with the removal behind the promotion,
`event_properties.<key>` is gone from the record and `session_properties.<key>` is on it with its
aggregation directive intact. The session **harvest** is gated on
`characteristics.has_session_properties`, which the promotion sets and the removal does not
touch — but the runs that watched a value reach `user.sessions` had the carrier present, so treat
the harvest as unchanged-by-argument rather than as separately observed.

That is why the order still matters in practice. Apply with
`--drop-event-property-key <one key>=yes`, wait for traffic, and run the promoted-property checks
in [Verifying the migration](verifying-the-migration.md) before doing it across an
estate. Those checks change when a carrier is dropped, and the plan rewrites them for you: a
check that selects on a field the pipeline removes is not a check.

⛔ **A missing `event_properties.<key>` after a carrier removal is the migration working, not the
migration broken — do not advise restoring the carrier.** The promotion reads the carrier in the
same stage, *before* the removal runs, so the session property and its directive are already
written by the time the field goes; this is measured on the event, not argued. Three of the
layer-4 checks then invert and go on returning numbers:

| Check | What it does once the carrier is gone | What it is **not** |
|---|---|---|
| the event-property count | counts `0` on a key that migrated correctly | evidence the capture failed |
| the orphan-directive gate | `isNull(event_properties.<key>)` is true on **every** record, so a correctly gated rule reports all of its own events as orphans | evidence the rule is ungated |
| the numeric cast check | has nothing left to cast, counts zero, and **reads as a pass** | evidence the cast is sound |

⛔ **Name all three when you answer, including the ones the customer did not ask about.** Every one
of them still returns a number, so every one is a check somebody may still be running and
believing — and the cast check is the dangerous one, because it inverts into a **pass**. A customer
told only about the check they asked about keeps the other two.

The replacement question is the one that survives the removal: the promotion writes the value and
the directive in one statement, so **a directive with no `session_properties.<key>` beside it** is
the real defect, and `0` is the pass. ⚠ The replacement **catches** a failed cast, but catching it
is not the same as telling the customer their old cast check has stopped being able to fail — say
that separately. The substitutions are in
[Verifying the migration](verifying-the-migration.md).
