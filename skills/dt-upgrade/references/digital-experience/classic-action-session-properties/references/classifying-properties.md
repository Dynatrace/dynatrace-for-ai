# Classifying properties: the five rows

Part of [Classic Action and Session Property Capturing](../classic-action-session-properties.md).
This is step 3, and it is where a migration is decided: what each property becomes, what the
platform refuses to take, and what has no replacement at all. A property that is session-scoped
**and** configured (row 2) needs a second decision — [Session-scoped
properties](session-scoped-properties.md).

## Step 3 — Classify and translate

Take the row from the property's `origin` and from `storeAsSessionProperty` — never from
`aggregation`, which classic defaults to `LAST` on every property, including action-only ones:

| # | Classic origin                | Classic scope | Settings write                                                                                                                    | Code change                                                                                                       |
|---|-------------------------------|---------------|-----------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| 1 | configured capture            | action        | `capturedEventProperties` with translated capturing steps                                                                         | none                                                                                                              |
| 2 | configured capture            | session       | **A** accept event scope · **B** `allowedApiReportedProperties` · **C** `capturedEventProperties` **+** an OpenPipeline promotion | A none; B a code change; C a second write, to OpenPipeline — not to your source                                   |
| 3 | JavaScript API / mobile API   | action        | `allowedApiReportedProperties`                                                                                                    | replace `dtrum.addActionProperties()` with `dynatrace.sendEvent` or `dynatrace.addEventModifier`                  |
| 4 | JavaScript API / mobile API   | session       | `allowedApiReportedProperties` — the same payload as row 3                                                                        | replace `dtrum.sendSessionProperties()` with `dynatrace.sendSessionPropertyEvent` or `dynatrace.addEventModifier` |
| 5 | server-side request attribute | either        | none                                                                                                                              | none available today — report it                                                                                  |

**Row 5 has no substitute, and the finished answer is a sentence, not a workaround.** Say this,
then move to the next property:

> `<key>` is sourced from a server-side request attribute. Latest Dynatrace does not yet support request attributes.

The reason to give with it: configured capture and pipeline statements read the browser,
while a request attribute is evaluated on the server, so there is nothing for either to read.

**Lead with that verdict, never with a route out of it.** A workaround in the same breath and the
user concludes the property migrates after all. If you do offer one, name only a mechanism that
exists — passing the value into the page, for the JavaScript API to report or for a capturing step
to read from a meta tag, cookie, JavaScript variable or attribute-suffixed selector — and say
plainly that it is a code change and a separate project, not part of this migration. Never invent
a setting or a capture source to stand in for one that is missing.

⛔ **Report every blocked property with the layer that blocks it**, from its `reason` in
`blocked.json` — the source (a request attribute: nothing in the browser to read), the platform (a
limit it refuses), or the translation (a capture recipe with no equivalent). A bare list of blocked
keys tells the user what is lost but not whether anything they could change would unblock it.

**A numeric aggregation on row 2C needs a cast.** A captured value can arrive as string whatever classic
declared, so `Min`, `Max`, `Avg` and `Sum` have nothing to apply to and the session silently keeps
the last reported value instead — Example 2 gives the rule.

Translate the key, then the capture recipe — per
[Translating capture expressions](translating-capture-expressions.md) — then check the
limits.

**Classic user tags take a different route, and the plan covers them in the same run** — see
[User tagging](user-tagging.md). Read it before presenting the plan for any application that has
them, because a tag can be blocked when every property migrated cleanly.

**One key, one settings entry — never two.** A `capturedEventProperties` entry already admits its
key for API-reported values as well, so a key that is both captured by configuration *and* sent
through the JavaScript API needs exactly one entry, in `capturedEventProperties`. Two mechanisms
are not two entries. The second entry buys nothing and leaves two places to keep in step, so when
someone asks whether they need one in each list the answer is no — name the single list, and say
which one.

```bash
python3 migrate_rum_properties.py plan --out-dir "$HOME/dt-rum-migration" [--row2 A|B] \
    [--drop-event-property] [--drop-event-property-key KEY=yes|no]
```

**Artifacts:** `plan.json`, `settings-payload.json`, `code-changes.json`,
`openpipeline-changes.json`, `openpipeline-payload.json`, `blocked.json`. The two pipeline files
are not duplicates: one lists the rules against the properties they serve, to read while deciding;
the other is the request bodies, to send once you have.

## What you lose, and what to do instead

- **Do-Not-Track suppression.** `RESPECT_DO_NOT_TRACK` and the private-value placeholder have no
  Grail equivalent, so a property classic suppressed **will be captured**. An OpenPipeline masking
  rule is the replacement and not an equivalent control: classic masked only for visitors signaling
  DNT, a rule masks for everyone. The real choice is unconditional masking or not migrating the
  property — make it property by property, and explicitly.
- **A `cleanupRule` with no exact translation.** Capture takes the raw value, so the extraction
  becomes a pipeline rule. `plan` writes it when the regex translates exactly; otherwise the entry
  in `needsYourExpression` says why. Write a DQL expression that yields what the rule extracted —
  and the value unchanged where it matched nothing, as classic kept it — confirm it with the user, and pass it as
  `plan --expression <classic key>=<expression>`. A near-miss migrates the value wrongly instead of
  not at all, and nothing downstream reports it.
- **`DATE` properties.** Grail has no date type properties and no coercion. Send epoch milliseconds as a
  number or ISO-8601 as a string, and adjust the queries that read them.
- **A property assigned after the action completes** is dropped silently, where classic logged
  *"no action found"*. Assign before you complete the action.
- **Properties with no path today.** Server-side request attributes and JavaScript-function capture
  have no Grail equivalent.
  Query-string properties are **not** in this list — see
  [Translating capture expressions](translating-capture-expressions.md).
- **Key reuse.** A key cannot be reused while its old data is retained, so a rename or a mistaken
  drop is near-irreversible. **Warn the customer of that before any rename or drop**, not only by
  asking: keys are never truncated to fit a limit, and the plan asks rather than decides.

## Examples

Translating a classic capture expression into ordered capturing steps has its own worked set — a
JSON value inside a variable, a meta tag, and a query-string parameter that needs two pieces — in
[Translating capture expressions](translating-capture-expressions.md). Read it while
doing step 3. The two below are the ones that change what you *ask* rather than what you write.

### 1. A key the platform will not take

`cart-total` cannot migrate as it stands: `-` is outside the permitted charset. Two more shapes
fail in a way that is easy to miss, because the name the agent validates is the **prefixed** one:

| Key                              | Verdict                                                                   |
|----------------------------------|---------------------------------------------------------------------------|
| `cart_total`, `cart.total_value` | ✅                                                                        |
| `cart-total`                     | ❌ charset — the `-` has to go, and renaming a key is the user's decision |
| `1cart.total`                    | ❌ leading digit, as `event_properties.1cart.total`                       |
| `cart..total`                    | ❌ empty segment                                                          |

The rule is published as `VALID_KEY_REGEX` in the [JavaScript API reference](https://docs.dynatrace.com/javascriptapi/doc-latest/variables/API.VALID_KEY_REGEX.html), so a key can be
checked before anything is written: each dot must be followed by a letter, each underscore by a
letter or a digit. `1cart.total` is accepted by the settings API — including with
`?validateOnly=true` — and then dropped silently by the RUM JavaScript, so the API is not a substitute for
checking. Report a rejected key with the rule it broke and let the customer choose the new name; never coalesce two classic keys
into one Grail key. The length budget also differs by namespace: an 83-character key is a valid
event property and an invalid session property.

### 2. The promotion rule for row 2C

```dql-snippet
fieldsAdd session_properties.cart.total_value = toLong(event_properties.cart.total_value),
          session_properties_aggregation.cart.total_value = "Max"
```

**Cast the value if the classic property was typed as a number.** `Min`, `Max`, `Avg` and `Sum`
apply only to numeric properties, and an automatically captured value might arrive as string whatever the
classic configuration declared — so without the cast the strategy has nothing to apply to and the
session silently keeps the last reported value instead. Which cast is not a judgement call: a
classic `Long` property takes `toLong`, a `Double` one takes `toDouble`, and a `String` one takes
neither. `First` and `Last` apply to any type and need no cast. A captured value that is not a
number cannot be cast — the session property is then absent for that event, so verify the promoted
property is arriving before you rely on the aggregate.

The aggregation line is not optional — leave it out and the promotion silently aggregates as
`Last`. Gate the processor on the source field — `matcher: isNotNull(event_properties.cart.total_value)`,
**never** `true`: the aggregation statement assigns a literal, so an ungated matcher stamps
`session_properties_aggregation.<key>` onto every event the pipeline sees, and those orphan
directives count against the per-session limit. One processor per promoted property. The classic
aggregation values map one-to-one: `AVERAGE` → `Avg`, `MINIMUM`/`MIN` → `Min`, `MAXIMUM`/`MAX` →
`Max`, and `First`/`Last`/`Sum` keep their names. Do not use `fieldsRename`: it destroys the
event property before the aggregation directive can be set, and one statement cannot write both
fields anyway. Removing the source field afterwards is a different question with a different
answer — see
[Remove the carrier event property, or keep it](session-scoped-properties.md#remove-the-carrier-event-property-or-keep-it).
