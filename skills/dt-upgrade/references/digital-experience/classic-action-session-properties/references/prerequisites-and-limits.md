# Prerequisites, permissions, limits and cost

Part of [Classic Action and Session Property Capturing](../classic-action-session-properties.md).
**Read this before step 1** — every gate that stops a migration before it starts is here, and so are
the three numbers people ask for afterwards: what the published limits are, whether they can be
raised, and what the migration costs.

## Prerequisites

| Prerequisite                                | What to check                                                                                                                                                                                                                                                                                                                        |
|---------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| New RUM enabled on the application          | Only possible **while RUM Classic is still active**                                                                                                                                                                                                                                                                                  |
| The capture-properties schema resolves      | `builtin:rum.web.capture-properties`, resolved at run time rather than hard-coded. Some environments still answer with the deprecated `builtin:rum.web.capture-custom-properties`; if that is the only one, **stop and report it** rather than migrate onto it                                                                       |
| SaaS                                        | Grail, DQL and this schema are unavailable on Dynatrace Managed                                                                                                                                                                                                                                                                      |
| RUM JavaScript version                      | **1.341+** for properties configured in the UI. Below it the configuration transfers correctly and captures nothing — so an empty result on an application that migrated cleanly is a **version** problem. **The fix is a tag update. Do not migrate the application again**, and do not read the empty result as a failed migration |
| The application calls the `dynatrace.*` API | For an API-origin property the declaration exists, but nothing sends a value until the code change ships                                                                                                                                                                                                                             |
| OpenPipeline access                         | For five ordinary parts of this migration: session-scoped configured properties, query-string splitting, classic cleanup rules, masking properties classic suppressed, and **every** classic user tag                                                                                                                                                            |

## Permissions

| What you are doing                                                       | Credential                                                        | Scopes                                                                                                                                           |
|--------------------------------------------------------------------------|-------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| Read classic applications and their properties                           | classic token (`Api-Token` on `{env}.live.dynatrace.com/api/`)    | `ReadConfig`                                                                                                                                     |
| Read and write the capture-properties object through the Environment API | classic token                                                     | `settings.read`, `settings.write`                                                                                                                |
| Apply the object with `dtctl`, Monaco, Terraform or the platform API     | platform token (`Bearer` on `{env}.apps.dynatrace.com/platform/`) | `settings:schemas:read`, `settings:objects:read`, `settings:objects:write`                                                                       |
| Add or edit an OpenPipeline rule                                         | platform token                                                    | `settings:objects:read`, `settings:objects:write` on `builtin:openpipeline.user.events.pipelines` and `builtin:openpipeline.user.events.routing` |
| Run the verification queries                                             | platform token                                                    | `storage:buckets:read`, `storage:user.events:read`, `storage:user.sessions:read`, `storage:smartscape:read`                                      |

Four failures that are not scope problems — the two credentials being non-interchangeable, the
two policy grants that no scope carries, and the one object a team gatekeeps — are in
[Credentials and permissions](credentials-and-permissions.md). Read it the moment a
request is refused, before widening anything.

Never paste a token value into a command, a log or a chat: refer to `$DT_CLASSIC_TOKEN` and
`$DT_PLATFORM_TOKEN`, and ask for exactly the scopes in the row you are working on.

## Limits

Published, and worth checking before the write:

| Limit                                                                          | Value                                                                                              |
|--------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| Field name, *including* the `event_properties.` / `session_properties.` prefix | **100** characters — so **83** usable for an event property key, **81** for a session property key |
| Characters allowed in a field name                                             | letters, numbers, underscores and dots                                                             |
| String value                                                                   | **1,000** characters                                                                               |
| Captured event properties, per frontend                                        | **100**                                                                                            |
| Allowed API-reported properties, per frontend                                  | **200**                                                                                            |
| Properties per event                                                           | **50**                                                                                             |
| Session properties per session                                                 | **500**                                                                                            |

**Every one of these is adjustable upward per environment, but requires contacting Dynatrace representatives.**

Report what the migration is about to write and let the platform
answer — if one binds, the write fails with a message naming it precisely.

## Cost

RUM includes **up to 20 session properties for each application at no additional cost**, and
additional ones are billed *"at Real User Monitoring Property rates for each session in which the
property appears."* Report the count per application and let the user decide whether it is
acceptable — that is a decision, not a validation step. Two things worth saying unprompted:

- **A parallel run does not double-bill.** *"When migrating an existing RUM Classic application to
  Latest Dynatrace, Dynatrace protects you from double billing and charges only for the maximum number of
  properties configured in either RUM Classic or Latest Dynatrace."*
- **OpenPipeline costs nothing extra, but what it writes is billable.** A promoted property is
  present in the session and counts like any other, so call that path *at worst cost-neutral*,
  never *free*.
