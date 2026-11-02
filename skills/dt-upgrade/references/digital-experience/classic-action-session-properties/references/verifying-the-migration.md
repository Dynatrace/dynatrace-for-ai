# Verifying the migration

Part of [Classic Action and Session Property Capturing](../classic-action-session-properties.md).
This is step 6 and everything after it — the four layers, which of them is the gate, and how to read
an empty result without reporting a migration that worked as a failure.

## The four layers

Four layers, cheapest first. Layers 1 and 2 are the pass/fail gate; layer 4 is delayed
confirmation that needs traffic, so **an application that has received no events is fully migrated
and simply not yet verifiable at layer 4.** The per-layer detail — the field rules for each table,
the promoted-property checks and the browser-side diagnostic — follows below.

| Layer                      | What it proves                                               | Cost                        |
|----------------------------|--------------------------------------------------------------|-----------------------------|
| 1. Configuration read-back | The settings object holds what you intended                  | One request, immediate      |
| 2. Agent configuration     | The environment turned your settings into agent instructions | One request, immediate      |
| 3. Browser-side evaluation | The capture expression resolves on the real page             | Needs a browser on the site |
| 4. Grail data              | Properties are arriving and are queryable                    | Needs traffic               |

**Layer 1 is the primary gate**, the only check that is both immediate and unambiguous. Read the
objects back and confirm four things: every planned key is present, every entry that was there
before still is (this catches a replace where a merge was intended), the capturing steps match step
for step, and no field this migration never authors was dropped.

**Layer 4** starts with a control query that filters on nothing but the application, so that an
empty result means something:

```dql
fetch user.events, from: -2h
| filter dt.openpipeline.source == "rumagent"
| summarize events = count()
```

Then check the properties themselves, and read an empty result against this table before reporting
a failure:

| Layer 1 | Layer 2                                             | Layer 4                          | Conclusion                                                                          |
|---------|-----------------------------------------------------|----------------------------------|-------------------------------------------------------------------------------------|
| pass    | pass                                                | empty                            | Wait for traffic, then check the RUM JavaScript version is 1.341+, then use layer 3 |
| pass    | no `metadataConfig`, only API-reported keys written | empty                            | Expected — the code change has not shipped yet                                      |
| pass    | no `metadataConfig`, captured properties written    | empty                            | A real defect; investigate the configuration that was compiled                      |
| pass    | pass                                                | some keys present, others absent | Per property: rejected by the agent's charset rule, or over the length budget       |
| pass    | pass                                                | the control query is also empty  | The fieldset policy is missing, not the migration                                   |

A migrated user tag is checked differently, on a characteristic rather than on the value — see
[Checking a migrated tag](user-tagging.md#checking-a-migrated-tag).

Counts will not match classic exactly — session boundaries and aggregation differ — so compare
presence and orders of magnitude, not equality. And a session is counted for every application the
visitor used, which is correct rather than double counting.

## Layer 2 — reading the agent configuration

The environment compiles `capturedEventProperties` into the application's `metadataConfig`.
Three things to know before you compare it against the plan:

- accessors are HTML-entity encoded, so `'` arrives as `&#39` with no trailing semicolon — decode
  first, or every selector containing a quote looks like a mismatch;
- a step with a blank capture value is skipped, so the accessor chain can legitimately be
  **shorter** than the configured step list;
- **no `metadataConfig` at all is the correct result** when only `allowedApiReportedProperties`
  was written. `allowedApiReportedProperties` and `configLessProperties` are ingest-side only and
  never appear here.

## Layer 3 — evaluating the rule in the browser

When a property is declared correctly and no data appears, the question is *"does this expression
resolve on this page?"* — which separates a translation problem from a delivery problem. Both
answers need a browser on the real site, so this is a diagnostic to hand to whoever owns the
application:

- **walk the accessor chain by hand** in the console, in the order layer 2 reported it, and stop at
  the first step that returns `null` or `undefined` — that is the step that failed. For
  `localStorage.userInformation.$username` that is `localStorage.getItem("userInformation")`, then
  `JSON.parse(…)`, then `.$username`;
- **run the published health check**: `await dynatrace.loadDebugTools()`, then
  `dynatrace.debugtools.runHealthCheck()`. `debugtools` is `undefined` until it is loaded — or
  present from the start when the Health Check module is in the agent configuration — so check it
  before calling it.

## Layer 4 — the queries

An event property, with the application identified by the lowercased hex of its classic id:

```dql-snippet
fetch user.events, from: -2h
| filter dt.openpipeline.source == "rumagent"
| filter dt.rum.instrumentation.id == "<lowercased hex of the APPLICATION id>"
| filter characteristics.has_user_action == true
| summarize present = countIf(isNotNull(event_properties.cart_total)),
            absent = countIf(isNull(event_properties.cart_total))
```

A session property, with the application resolved through Smartscape:

```dql-snippet
fetch user.sessions, from: -2h
| filter dt.openpipeline.source == "rumagent"
| expand dt.smartscape.frontend
| lookup [ smartscapeNodes "FRONTEND" | filter id_classic == "APPLICATION-<HEX>" | fields id ],
  sourceField: dt.smartscape.frontend, lookupField: id
| filter isNotNull(lookup.id)
| summarize present = countIf(isNotNull(session_properties.cart_total))
```

A migrated user tag, counted on the characteristic rather than on the value:

```dql-snippet
fetch user.events, from: -2h
| filter dt.openpipeline.source == "rumagent"
| filter dt.rum.instrumentation.id == "<lowercased hex of the APPLICATION id>"
| filter isNotNull(event_properties.user_tag_921) and event_properties.user_tag_921 != ""
| summarize tagged = count(),
            identified = countIf(characteristics.has_user_identifier == true),
            fromMigration = countIf(characteristics.has_user_identifier == true
                                    and isNull(characteristics.is_api_reported))
```

`tagged` and `identified` should agree. Run the same shape with the source filter **negated** and
`yourOwn = countIf(characteristics.is_api_reported == true)` to prove the pipeline did not erase
identifiers your own `identifyUser()` call set — that is the failure an unguarded matcher causes,
and the positive query cannot see it.

Seven things about reading the results:

1. **`absent` normally dominates, and that is healthy.** A property attaches to some of an
   application's events, not all of them; a non-zero `present` is the pass condition.
2. **The two tables name an application differently.** `dt.rum.instrumentation.id` is the
   lowercased hex of the classic id and exists on `user.events` only; sessions are reached by
   resolving `dt.smartscape.frontend` through Smartscape, as above. A filter on a field the table
   does not have matches nothing, with no error — so check every field reference against the table
   it is used on.
3. **Filter on `dt.openpipeline.source == "rumagent"` every time.** Synthetic records can be the
   overwhelming majority of both tables and carry none of these fields, so an unfiltered query
   reads as a failed migration.
4. **`characteristics.*` fields are null, never false**, on records without the trait — `== true`
   is safe, `== false` is a bug. Test a session property with
   `isNotNull(session_properties.<key>)` rather than `characteristics.has_session_properties`,
   which goes true on a record whose only session-namespace field is an aggregation directive.
5. **A promoted property needs three queries:** the key under `event_properties.` on
   `user.events`, the key under `session_properties.` on `user.sessions`, and a negative check
   that `session_properties_aggregation.<key>` is **null** on events that never carried it. Read
   `dt.openpipeline.pipelines` on the rows too — it is the only way to tell *"the route never
   matched"* from *"the rule is wrong"*, and the first is the likelier mistake.
   **Two of those three change when the carrier is removed** — see below.
6. **A user tag is checked on `characteristics.has_user_identifier`, not on `user.identifier`.**
   The value is in a sensitive fieldset and the refusal is silent — nulls, `SUCCEEDED`, no
   warning — so counting the value cannot tell a failed migration from a token that may not read
   it. The characteristic is outside the fieldset. `characteristics.is_api_reported` is `true`
   for an identifier the JavaScript API set and absent for one the pipeline set, which is what
   makes the negated query above sharp. `user.sessions` declares no characteristic for the
   identifier at all, so the same question cannot be asked there.
7. **`dt.support.dropped_custom_properties`** lists the prefixed keys ingest rejected, per event,
   and separates *not sent* from *sent and rejected*. It cannot fire for a key only a pipeline
   writes, because ingest completes first.

### When the carrier event property was removed

**Exactly one field is removed: `event_properties.<key>`.** The session property the promotion
wrote, the `session_properties_aggregation.<key>` directive beside it and the
`capturedEventProperties` entry that produced the value are all left alone — removing any of them
would undo the migration rather than finish it. This is the opt-in described under
[Remove the carrier event property, or keep it](session-scoped-properties.md#remove-the-carrier-event-property-or-keep-it).

What it costs is verification: three of the checks above **select on the removed field**, so each
one keeps returning a number and the number stops meaning what it did. The plan rewrites them; if
you are checking by hand, these are the substitutions.

⛔ **The event-property query is not run at all — tell the customer to stop running it.** There is
nothing left to count, so a key that migrated correctly comes back `present = 0` and reads as a
failure. Somebody still running it will conclude a good migration broke.

**The gate check inverts.** The orphan-directive query looks for an aggregation directive written
onto an event that never carried the value:

```dql-snippet
| filter isNotNull(session_properties_aggregation.cart_total) and isNull(event_properties.cart_total)
```

Once the carrier is removed, `isNull(event_properties.cart_total)` is true on **every** record —
so a correctly gated rule reports every one of its own events as an orphan.

Ask a question that survives the removal instead. The promotion writes the value and the
directive in **one statement**, so on a healthy event the two are always present together, and an
event carrying the directive with no value beside it is broken. That combination is what the
replacement counts:

```dql
fetch user.events, from: -2h
| filter dt.openpipeline.source == "rumagent"
| filter dt.rum.instrumentation.id == "<lowercased hex of the APPLICATION id>"
| filter isNotNull(session_properties_aggregation.cart_total)
| filter isNull(session_properties.cart_total)
| summarize directivesWithoutAValue = count()
```

⚠ **Read the two `filter` lines as the defect they are looking for, not as an intended end
state.** They select the events where the directive was written and the value was not; you expect
**none**, so `directivesWithoutAValue = 0` is the pass. If that number is not zero the promotion
is half-working, and there are two ways it gets there — an ungated matcher stamping the directive
onto events that never carried the property, or, on a numeric property, a cast that failed and
dropped the value while the directive, which is a literal, was written anyway. This query cannot
tell them apart; read the processor's matcher first, it is the cheaper of the two to check.

⛔ **The cast check cannot be run, and say so out loud — it is the one that fails towards a pass.**
`toLong(event_properties.<key>)` has no input once the carrier is gone, so the original check counts
zero rows and **reads as a pass**: a customer who keeps running it gets a green answer from a query
that can no longer fail. ✅ The replacement above does catch a failed cast — a failed cast is exactly
a directive with no value — but catching it is not the same as telling the customer the old check
has stopped working. **Report both.**

**The session-property query is unaffected**, and it becomes the primary evidence: the promoted
value arriving in `user.sessions` is the whole point, and removing the carrier does not touch it.

**A migrated user tag loses its selector the same way.** The tag query above filters on
`event_properties.user_tag_921` to find the events a rule matched. With the carrier removed there
is no such filter, so the query degrades to the whole application:

```dql
fetch user.events, from: -2h
| filter dt.openpipeline.source == "rumagent"
| filter dt.rum.instrumentation.id == "<lowercased hex of the APPLICATION id>"
| summarize events = count(),
            identified = countIf(characteristics.has_user_identifier == true),
            fromMigration = countIf(characteristics.has_user_identifier == true
                                    and isNull(characteristics.is_api_reported))
```

`identified` and `events` will **not** agree here, and they should not: not every event in an
application matches a tag rule. A non-zero `fromMigration` is the pass condition. The negated
query that proves your own `identifyUser()` calls survived also loses its filter — with no
carrier to negate, run it on `characteristics.is_api_reported == true` across the application and
confirm the count did not fall to zero. If an application mixes dropped and kept tag carriers,
the kept ones still give the sharp form; use it on those.

**So take the sharp checks before the removals go in.** The removal processors are the last ones
in the pipeline and nothing depends on them, so they can be a second write — verify the tag with
its carrier still present, then add them. That ordering is the same one the promoted properties
want, and it is the reason the plan keeps the carrier by default.

Scopes for all of these: `storage:buckets:read`, `storage:user.events:read`,
`storage:user.sessions:read` and `storage:smartscape:read` — without them these queries return
nulls and empty results rather than an error.

Reading `user.identifier` itself needs one more, `storage:fieldsets:read`. It is a selectable
token scope, but a token's effective rights are the intersection of its scopes and the
permissions of whoever created it, so selecting it grants nothing unless that user holds the
sensitive-fieldset permission. None of the checks above need it; only comparing a tag's **value**
against classic does.
