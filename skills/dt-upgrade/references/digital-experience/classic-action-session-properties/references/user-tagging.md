# User tagging

Part of [Classic Action and Session Property Capturing](../classic-action-session-properties.md).
⛔ **Say it plainly: classic user tagging has no Latest Dynatrace setting behind it at all.** There
is no user tag schema and no screen; the target is the single `user.identifier` field. A tag
becomes a captured event property plus one OpenPipeline statement that writes `user.identifier`. Tags live in their own classic array, so an application can have user tags and no
properties.

Classic tags a user by evaluating a list of rules against **every** user action, and the first
rule that matches supplies the tag. Latest Dynatrace has no configuration for this at all: the
target is one fixed field, `user.identifier`, and the only browser-side thing that writes it is
`dynatrace.identifyUser()`.

So a classic user tag migrates as **two halves, and neither is a user tag on its own**:

1. the rule's capture recipe becomes an ordinary `capturedEventProperties` entry under a
   generated key, translated exactly like a row-1 property — and if the same capture is already
   migrating as a property, the tag reuses it rather than capturing the value twice;
2. one OpenPipeline `dql` processor copies the captured value into `user.identifier`.

Apply the settings object without the pipeline and you have the values captured and nobody
identified. Both halves come out of the same `scan` → `plan` → `apply` → `verify` run as the
properties. Classic allows **20** tag rules per application, and each one that migrates spends a
slot in the same per-frontend captured-property budget as the properties do.

## One statement per application, in the classic array order

Repeated `fieldsAdd` to one field is **last**-wins and classic is **first**-wins, so one processor
per tag runs the precedence backwards without reporting it. An application's rules therefore
become a **single** statement, and `coalesce` — first non-null argument — is classic's rule
exactly:

```dql-snippet
fieldsAdd user.identifier = coalesce(
    if(event_properties.user_tag_921 != "", lower(event_properties.user_tag_921)),
    if(event_properties.user_tag_922 != "", event_properties.user_tag_922))
```

Four things there are not stylistic:

- **The argument order is the order of the classic array.** It is not `uniqueId` order and it is
  not decorative. Sorting it, or reading the rules into a map, identifies a different user.
- **Every branch is guarded.** An absent cookie captures as `""` where an unmatched selector
  captures as `null`, and `coalesce` treats `""` as present — so an unguarded branch lets an
  unset cookie shadow every rule after it.
- **The guard tests the captured value**, not the extracted one. A rule whose cleanup matches
  nothing keeps the captured value and does **not** fall through to the next rule — classic stored
  the raw value — so the generated extraction falls back to the captured value.
- **`lower()` sits inside the branch.** Case folding is configured per rule, and classic folds
  *after* applying the cleanup rule, so hoisting it out of the `coalesce` changes the result.

Gate the processor on the sources and **never on `true`** —
`dt.rum.instrumentation.id == "<lowercased hex of the APPLICATION id>" and ((isNotNull(f) and f != "") or …)`.
This matcher is load-bearing in a way a property matcher's is not: the statement assigns a
`coalesce` result, and an all-null `coalesce` writes **null over `user.identifier`**, erasing
whatever your own `identifyUser()` call set on every event where no rule matched.

**Tell the customer the session-level tag behaves as before.** *"The last user action in a session
that contains a tag is used as the tag for the entire session"* is what both platforms do, so
nothing is generated for the session and there is no aggregation directive to declare — but say
that the behaviour is kept, not just that nothing was generated.

**`event_properties.user_tag_<uniqueId>` is a key this migration invented**, and it stays on every
event the rule matched. Classic never had it: the tag's destination was a tag, and in Latest
Dynatrace it is `user.identifier`. So the same offer applies as to a promoted property —
`--drop-event-property` removes each tag carrier once the identifier has been set, and
`--drop-event-property-key user_tag_<uniqueId>=yes` does one of them. Three things specific to
tags:

- **The removal goes after the `coalesce` statement**, which reads every carrier in the
  application. One tag's carrier cannot be removed beside its own rule, because there is no such
  rule — there is one statement for the whole application.
- **A tag that reuses a property's capture removes nothing of its own.** When the same capture is
  already migrating as a property, the tag reads that property's field, and the field belongs to
  the property's row and its decision.
- **Keeping it is the better default while verifying.** `user.identifier` sits in a sensitive
  fieldset you may not be able to read, so the carrier is the only place the captured value is
  visible if the identifier does not arrive. Remove it once
  `characteristics.has_user_identifier` confirms the statement is working.
- ⛔ **Recommend verifying first and adding the removals as a second write — never in the same
  write as the tagging.** The removal processors are last and nothing depends on them, so they
  can be added later at no cost. **Say what removing them costs:** the carrier is what the precise
  per-tag verification query reads, and without it only the weaker whole-application
  `characteristics.has_user_identifier` check is left.

See [Remove the carrier event property, or keep it](session-scoped-properties.md#remove-the-carrier-event-property-or-keep-it)
for the trade-off in full.

## What migrates, and what changes

| Classic user tag source | Outcome |
|---|---|
| Meta tag · cookie · JavaScript variable · CSS selector **with** `@attribute` | Migrates — captured, then copied by the statement |
| Query-string parameter | Migrates — the capture takes the query string and the statement reads the parameter out, as described in [Translating capture expressions](translating-capture-expressions.md) |
| CSS selector **without** `@attribute`, i.e. the element's text | ⛔ Blocked — there is no text-content capture. Expect this one: reading a username out of a welcome message is the classic documentation's own worked example |
| Server-side request attribute | ⛔ Blocked, and not pending. Say: *"Latest Dynatrace does not support request attributes, so this user tag cannot be migrated."* A tag carries either a metadata reference or a request attribute, never both, so this is decidable from the configuration alone. The blocked verdict comes first; the rules for naming a route out of it are under [Row 5](classifying-properties.md) |
| A rule with a `cleanupRule` | `plan` translates the rule when an exact translation exists. When it does not, the entry in `needsYourExpression` says why: write a DQL expression that yields what the rule extracted — and the value unchanged where it matched nothing, as classic kept it — confirm it with the user, and pass it as `plan --expression user_tag_<uniqueId>=<expression>`. Until then the pipeline half **is refused** — the API would take the placeholder as a string literal and write the marker text itself as somebody's identifier |

Two consequences to state out loud, because both are invisible until something breaks:

- **Values are no longer cropped at 100 characters.** Classic silently cropped every captured tag
  at 100; nothing in the Latest Dynatrace path crops, so a tag that used to be truncated now
  arrives in full. That is a gain, and it is also a change — a dashboard filter, a segment, an
  alert or an export that matched the truncated form stops matching.
- **An application whose rules are all blocked loses user tagging entirely.** Report that as an
  explicit unsupported outcome, never as a clean run with nothing to do. A property that cannot
  migrate is a chart nobody can draw; tagging that cannot migrate means the visitors stop being
  identified.

## Checking a migrated tag

**Check `characteristics.has_user_identifier`, never `user.identifier`.** The value sits in a
sensitive fieldset, and a query without that grant reads back null with a `SUCCEEDED` status and
no warning — so a working tag and an unreadable field look identical, and **null values on their
own do not mean the migration failed.** The characteristic is outside the fieldset and is true
exactly when an identifier is set.

**Name `characteristics.is_api_reported` too** — it separates the two ways one got there: `true` where your own
`identifyUser()` call set it, absent where the pipeline did — which is also how you prove the new
statement did not overwrite the identifiers your code already sets. Session records declare no
equivalent characteristic, so check the event records; the queries are in
[Verifying the migration](verifying-the-migration.md).
