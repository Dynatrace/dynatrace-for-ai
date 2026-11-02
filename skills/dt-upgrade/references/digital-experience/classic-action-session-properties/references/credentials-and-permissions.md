# Credentials and permissions

Part of [Classic Action and Session Property Capturing](../classic-action-session-properties.md).
The permission each step needs is in [Prerequisites, permissions, limits and
cost](prerequisites-and-limits.md); this file is for when a request is refused.

## The two credentials are not interchangeable

Neither failure is a scope problem, and widening a token does not fix either:

| What you sent               | Where               | Answer                                           |
|-----------------------------|---------------------|--------------------------------------------------|
| Classic token (`Api-Token`) | a platform API      | *"Unsupported authorization scheme 'Api-Token'"* |
| Platform token (`Bearer`)   | the Environment API | `401 Token exchange failed`                      |

Reading classic applications and reading or writing the capture-properties object through the
Environment API take the **classic** token. `dtctl`, Monaco, Terraform, the platform API and every
verification query take the **platform** token. A step that fails with one of the two messages
above is using the wrong credential, not the wrong scope.

⚠ **A single migration run needs both**, so "which token does this migration use" has no answer.
The Environment API does not necessarily serve the two OpenPipeline schemas — if it doesn't, it answers
`404 … Use 3rd gen Public Settings API instead` — while still answering `200` for
`builtin:rum.web.capture-properties`. So the captures stay on the Environment API with the
classic token and the pipeline and routing objects move to
`{env}.apps.dynatrace.com/platform/settings/v1/objects` with the platform token. Ask for both
before starting, not at the step that needs the second one.

⚠ **That `404` is the one refusal in this migration that does not look like a refusal.** It names
a schema and says the feature is elsewhere, which reads like an environment that has not been
enabled. Nothing needs enabling and no scope needs widening: send the same body to the platform
host.

## Two grants that no scope carries

1. **The settings write needs a policy as well as the scope:**
   `ALLOW settings:objects:write WHERE settings:schemaId = "builtin:rum.web.capture-properties";`
   — and the same pattern for the two OpenPipeline schemas where a rule is in the plan.
2. **The sensitive fieldset is a policy, not a scope**, so re-minting a token never supplies it:
   `ALLOW storage:fieldsets:read WHERE storage:fieldset-name = "builtin-sensitive-user-events-and-sessions";`
   Without it the sensitive RUM fields read as null and queries filtering on them return nothing
   — silently, and indistinguishably from a migration that did not work. This is the reason the
   control query in `## Validation` filters on nothing but the application: if that query is also
   empty, the policy is missing and the migration is not in question.

## The one object a team gatekeeps

Owner-based access control covers OpenPipeline **pipelines** and not **routing**, so
`builtin:openpipeline.user.events.routing` is a single environment-wide object that one team
usually owns. Adding processors to a pipeline the user already owns avoids it entirely —
prefer that where it is available, and expect an organizational wait where it is not.

## Tokens

Never paste a token value into a command, a log or a chat. Refer to `$DT_CLASSIC_TOKEN` and
`$DT_PLATFORM_TOKEN`, ask for exactly the scopes in the row you are working on, and never ask for
an administrator role to clear a refusal — name the scope or the policy that is missing instead.
