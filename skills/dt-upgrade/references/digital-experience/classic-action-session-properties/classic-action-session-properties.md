# Classic Action and Session Property Capturing

**Gen3 replacement**: Event and session property capturing, config-less properties

**Phase 2 required**: yes

> ⚠ **This page is a map, not the answer.** It carries the shape of the migration and nothing
> else — every number, rule, limit, signature, command and query lives in one of the files in the
> table below. **Open the file for the step or the question you are on before you answer.** An
> answer assembled from this page alone will be confident and wrong about the detail, and the
> detail is the whole question.

## What changes

RUM Classic has three ways to attach a property to a user action or a user session. Latest
Dynatrace has two namespaces on Grail, and they do not line up one-to-one:

| Classic mechanism                                     | Configured where   | Classic scope                       | Grail target                                                                                               |
|-------------------------------------------------------|--------------------|-------------------------------------|------------------------------------------------------------------------------------------------------------|
| Configured capture (`userActionAndSessionProperties`) | Dynatrace settings | action **or** session, per property | `event_properties.*` — configuration reaches this namespace only                                           |
| `dtrum.addActionProperties()`                         | your code          | action                              | `event_properties.*` — API only via `dynatrace.sendEvent` or `dynatrace.addEventModifier`                  |
| `dtrum.sendSessionProperties()`                       | your code          | session                             | `session_properties.*` — API only via `dynatrace.sendSessionPropertyEvent` or `dynatrace.addEventModifier` |

Read the last two columns together, because that asymmetry is the whole migration:
**configuration-driven capture in Latest Dynatrace can only write `event_properties.*`.** A
property classic captured from the page *and* stored on the session has no configuration-only
equivalent, so you choose a disposition per property — rows 2A, 2B and 2C in
[Session-scoped properties](references/session-scoped-properties.md).

Three more differences to settle before you plan anything:

- **Declare before you send.** A property that is not in the capture-properties settings object is
  dropped at ingest with no error anywhere: *"To prevent unconfigured properties from being
  dropped during ingest, you must add each property to the allow list."*
- **A declared key is allowed in both namespaces.** An allow-list entry is a key plus a
  case-sensitivity flag, with no namespace discriminator, so one entry covers both prefixes and the
  namespace is decided at runtime by the call that sends it.
- **Aggregation moves from write time to query time.** Grail keeps the raw values and DQL
  aggregates them however you want, so nothing is lost — but saved queries, dashboards and alerts
  that read a pre-aggregated value now have to aggregate explicitly. Only the OpenPipeline
  promotion (row 2C) keeps the classic setting as configuration.

**Mobile has no configured capture at all.** `builtin:rum.mobile.capture-properties` holds an
allow-list only — there is no DOM or cookie to scrape — so every mobile property is a declaration
plus a code change. Mobile properties are also read from a per-application subresource,
`…/applications/mobile/{id}/userActionAndSessionProperties`, not from the application object.

**Classic user tagging migrates here too, and it has no Latest Dynatrace setting behind it at
all.** A tag becomes a captured event property plus one OpenPipeline statement that copies the
value into `user.identifier`. It lives in a separate classic array, so an application can have
user tags and no properties — see [User tagging](references/user-tagging.md).

## Where the answer is

Each file is self-contained: it carries its own conclusions, not a pointer to them. For this
migration, the tenant is the tool's `DT_CLASSIC_BASE`, not the `dtctl` context.

| Read this                                                                 | It answers                                                                                                          | Step |
|---------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|------|
| [prerequisites-and-limits.md](references/prerequisites-and-limits.md)     | **Prerequisites** — can this environment be migrated at all? Which schema, which token, which permission, which limits, what cost? | before 1 |
| [running-the-migration.md](references/running-the-migration.md)           | **Instructions** — **start with `preflight`** and follow each command's `nextStep`; the seven steps and the artifact each produces: inventory, plan, apply, verify, hand off | 1–7  |
| [classifying-properties.md](references/classifying-properties.md)         | What does this property become? Rows 1–5, the key rules, the worked **examples**, what has no replacement at all    | 3    |
| [session-scoped-properties.md](references/session-scoped-properties.md)   | A configured **session**-scoped property: dispositions 2A, 2B, 2C, and whether to remove the carrier event property | 3    |
| [translating-capture-expressions.md](references/translating-capture-expressions.md) | Turning a classic capture expression into an ordered list of capturing steps                              | 3    |
| [replacing-the-classic-calls.md](references/replacing-the-classic-calls.md) | The four `dtrum` calls, their replacements, published signatures and SDK versions                                 | 3, 7 |
| [writing-the-objects.md](references/writing-the-objects.md)               | The two APIs on two hosts, the backup, the optimistic lock, the shared routing object, and the end state            | 5    |
| [verifying-the-migration.md](references/verifying-the-migration.md)       | The four layers, which one is the gate, and how to read an empty result without calling a good migration broken     | 6    |
| [user-tagging.md](references/user-tagging.md)                             | Classic user tagging, start to finish — the captured property, the `user.identifier` statement, and checking one    | any  |
| [credentials-and-permissions.md](references/credentials-and-permissions.md) | A request came back 401, 403 or 404                                                                               | any  |
| [further-reading.md](references/further-reading.md)                       | **References** — the published Dynatrace documentation every rule here traces to                                    | —    |

**Answer from the files before asking for an artifact.** When someone describes where they are
rather than handing you a file, open the file for that step, say what it does and what holds while
it runs, and ask for the artifact only if the answer actually depends on its contents.
