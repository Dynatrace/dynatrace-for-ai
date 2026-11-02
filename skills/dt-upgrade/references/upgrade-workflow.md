# Upgrade Workflow Reference

Detailed procedures for the five stages described in the `Operating Workflow` section of dt-upgrade `SKILL.md`. Read this before running a Program-tier upgrade, or whenever you need the exact shape of a spec, a plan task, or a verification step.

## Contents

- [Tier classification](#tier-classification)
- [Stage 1: Scope](#stage-1-scope)
- [Stage 2: Plan](#stage-2-plan)
- [Stage 3: Execute](#stage-3-execute)
- [Stage 4: Verify](#stage-4-verify)
- [Stage 5: Wrap up](#stage-5-wrap-up)
- [When something breaks](#when-something-breaks)
- [Git, when present](#git-when-present)
- [Rationalizations](#rationalizations)

## Tier classification

Announce the tier before the first clarifying question so the user can override it.

| Tier | Looks like | Artifacts | Approval gate |
|---|---|---|---|
| **Question** | "Are we ready for Phase 3?", "What replaces management zones?", a single readiness scan with no configuration change | None. Report findings in chat. | Confirm the assessment scope before running queries against the tenant |
| **Single task** | Limited upgrade-related task scoped to an item within Reference Index | Todo list, no spec, no plan file | Present the approach in chat, stop for an explicit yes |
| **Program** | Three or more areas, a cross-cutting change (management zones → segments touches dashboards, alerting, and IAM), or a full tenant upgrade | Spec file, then plan file | Approval after the scope, again after the spec, again after the plan |

When torn between two tiers, take the heavier one. The ratchet is one-way: discovering hidden scope mid-engagement upgrades the tier — say so and step up. Nothing downgrades mid-engagement.

## Stage 1: Scope

**Goal:** know which areas are in play, which objects inside them, and what "done" means, before touching anything.

1. **Validate access and tooling first** — before any discovery query. See below.
2. **Establish tenant context.** Which tenant, which environment, which upgrade phase is it in today, who owns the configuration being changed. Check what the tenant actually uses — do not plan a migration for an area with zero classic usage.
3. **Run the discovery queries** from each candidate area's reference file. Classic Configuration and Classic Usage counts tell you the real workload; Readiness Status tells you the blockers.
4. **Ask clarifying questions one at a time.** Prefer multiple choice. Focus on: which objects are still needed at all (a large fraction of classic config is abandoned and should be deleted, not migrated), what the acceptance criteria are, what the deadline is, what must not break.
5. **Propose the approach.** For a Program tier, offer 2-3 sequencing options with trade-offs and lead with your recommendation — dependency order usually beats area-by-area order, because segments must exist before the dashboards that filter on them.
6. **Stop for approval.** Wait for an explicit yes.
7. **Program tier only:** write the spec to `docs/dt-upgrade/YYYY-MM-DD-<topic>-spec.md`, then self-review it before showing the user.

### Validate access and tooling

Do this before the first query. A scope built on a tenant you cannot actually reach wastes the whole session, and a permission gap found in Stage 3 invalidates the plan.

```bash
dtctl doctor
```

That single command covers the checks that matter: dtctl version, config file validity, current context, environment URL shape and reachability, keyring status, token retrieval, and whether API authentication actually returns a user identity.

**Confirm before continuing:**

| Check | How | If it fails |
|---|---|---|
| dtctl is installed and configured | `dtctl doctor` | Stop. Ask the user to install or configure it — do not fall back to hand-rolled curl calls against an unverified URL |
| The context points at the intended environment | `dtctl config current-context` | Stop and confirm with the user. Running an upgrade against the wrong tenant is the worst failure mode this skill has |

Report what you verified and against which environment before moving on. If the user is working from an upgrade folder with no dtctl context configured, ask which environment to target rather than guessing from a URL in the conversation.

### Spec template

```markdown
# <Topic> Upgrade Spec

**Tenant:** <environment URL or ID>
**Current phase:** <Phase 1 / Phase 2 / Phase 3>
**Date:** YYYY-MM-DD

## Goal

One or two sentences describing the end state.

## Scope

| Area | Reference | Objects in scope | Objects excluded (and why) |
|---|---|---|---|

## Baseline

The discovery query output that established the workload. Paste the actual
numbers — counts of classic objects, usage volumes, readiness failures.

## Target state

What the gen3 configuration looks like when this is done, per area.

## Constraints

Version floors, naming conventions the tenant follows, permissions available,
change windows, objects that must not be deleted, downstream consumers
(config-as-code repos, Terraform, workflows) that also need updating.

## Out of scope

Explicitly listed, so the plan does not quietly grow.

## Acceptance criteria

How we will know each area is done. One line per area.
```

### Spec self-review

Before showing the spec to the user, reread it and fix inline:

1. **Placeholders** — any "TBD", "TODO", or vague requirement. Fix them.
2. **Consistency** — does the target state match the scope table? Do the acceptance criteria cover every in-scope area?
3. **Size** — is this one plan's worth of work, or should it be split into sequential sub-projects with their own spec/plan cycles?
4. **Ambiguity** — could a requirement be read two ways? Pick one and make it explicit.

Then ask the user to review the file before you write the plan.

## Stage 2: Plan

**Goal:** a document a different agent, with no memory of this conversation, could execute correctly.

**Save to:** `docs/dt-upgrade/YYYY-MM-DD-<topic>-plan.md`. Single task tier keeps the plan as a todo list instead.

### Task right-sizing

A task is the smallest unit worth its own review by the user. Fold discovery, config generation, and documentation into the task whose deliverable needs them. Split only where the user could reasonably approve one task and reject its neighbor. Each task ends with something reviewable: a config file, a deleted object, a report.

### Plan document header

```markdown
# <Topic> Upgrade Plan

**Spec:** docs/dt-upgrade/YYYY-MM-DD-<topic>-spec.md
**Tenant:** <environment URL or ID>

**Goal:** One sentence.

**Sequencing:** 2-3 sentences on task order and why — especially any
dependencies between areas.

## Global constraints

The spec's tenant-wide requirements, one line each, exact values copied
verbatim. Every task inherits these.

---
```

### Task structure

````markdown
### Task N: <Area — what changes>

**Reference:** `references/<area>/<file>.md`
**Objects:** <exact IDs, names, or the query that enumerates them>
**Depends on:** Task M (or: nothing)

- [ ] **Step 1: Enumerate the current objects**

Run: <the exact DQL query or API call, copied from the reference>
Expected: <what the output should look like>

- [ ] **Step 2: Generate the gen3 configuration**

Write to: `<exact path>`
Mapping: <field-by-field, classic → gen3, from the reference file>

- [ ] **Step 3: Validate**

<Dry-run POST, schema check, or the reference cross-check — see Stage 4>
Expected: <what a passing result looks like>

- [ ] **Step 4: Present for review**

Show the user the generated config and the mapping decisions that were
not mechanical.

- [ ] **Step 5: Apply** (only after the user approves)

<Exact API call or UI steps>

- [ ] **Step 6: Confirm**

Re-run the area's tracking query. Expected: <the new numbers>
````

### No placeholders

These are plan failures. Never write them:

- "TBD", "TODO", "migrate the rest similarly"
- "Map the fields appropriately" — write the actual field mapping
- "Handle edge cases" — name the edge cases
- "Same as Task N" — repeat it; tasks get read out of order
- A step that says what to do without saying how
- A reference to a query, field, or object type defined nowhere in the plan

### Plan self-review

1. **Spec coverage** — point to the task implementing each spec requirement. List gaps and add tasks for them.
2. **Placeholder scan** — search for the patterns above.
3. **Consistency** — do object names, entity types, and field names match between tasks and match the reference files?
4. **Order** — does every task's dependency come earlier in the plan?

Fix inline, then hand the plan to the user for review.

## Stage 3: Execute

1. **Reread the plan critically.** If you see a gap, a wrong assumption, or a step you do not understand, raise it now — before starting, not halfway through.
2. **Create one todo per task.**
3. **One task at a time.** Mark in progress, follow the steps in order, do not skip validation steps, mark complete only after Stage 4 passes.
4. **Checkpoint between tasks.** Report what changed and what the verification showed. For a long plan, batch the checkpoint every few tasks if the user prefers, but never batch the *approval* for applying changes.
5. **Stop and ask when blocked.** A missing permission, an object the reference does not cover, a field with no gen3 equivalent, an unclear instruction, a repeated verification failure. Never invent a configuration value to keep moving.

### Do not

- Apply a configuration change the user has not seen, unless they have explicitly delegated that area
- Delete a classic object before its gen3 replacement is verified working
- Batch "while I'm here" improvements into a migration task
- Continue past a failed verification because the next task looks independent

## Stage 4: Verify

**Core principle:** evidence before claims. If you have not run the check in this message, you cannot say it passed.

Most of this work is generating configuration, so verification happens after the config exists. Use every check that the object type supports.

| Check | How | Applies to |
|---|---|---|
| **Reference cross-check** | Reread the area's reference file and walk the generated config field by field against the documented mapping. Every field the reference names must be accounted for — mapped, deliberately dropped, or flagged | Everything, always |
| **User review** | Show the config and name the non-mechanical decisions you made | Everything, always |
| **Tracking query** | Re-run the area's Classic Usage / Classic Configuration / New Usage queries and paste the output | Any area whose reference provides them |
| **Pre-write validation** | Only where the area's reference documents one. Use exactly the command or endpoint it names | The few areas that have it |

**Do not assume a dry run exists.** `dtctl apply --dry-run` is a *client-side preview only* — it reports `{"action":"created"}` without contacting the API, even for a schema that does not exist. It confirms the YAML parses and nothing more. For most object types there is no server-side validation step before the real write, so the reference cross-check and the user review are not the fallback — they are the primary verification.

This is why the ordering above matters: the two checks that always apply come first. Never describe a client-side parse as validation, and never claim a config was validated when no validation path existed.

### Claim discipline

| Claim | Requires |
|---|---|
| "The config is valid" | Output from a validation path the area's reference documents — or an explicit statement that no such path exists for this type. `dtctl apply --dry-run` output does not qualify: it is a client-side parse |
| "This matches the reference" | The field-by-field walk, done in this message |
| "The area is migrated" | Tracking query output showing the new state |
| "The gen3 replacement works" | The user confirmed it, or observable evidence from the tenant — not "the API accepted it" |
| "Task complete" | All of the above for that task |

Words like "should", "probably", "looks right", and any celebration before the check has run are the signal that you are about to skip this stage.

## Stage 5: Wrap up

No push, no pull request — ever. Wrapping up means reporting and handing back.

1. **Re-run the readiness scan** for every area touched.
2. **Report:**

```
Upgrade session complete.

Migrated:  <area> — <what changed, with the verification evidence>
Remaining: <area> — <what is left and why>
Blocked:   <area> — <the blocker and who can unblock it>

Artifacts: <spec path>, <plan path>, <config file paths>
```

3. **Offer next steps** and wait:

```
1. Continue with <next area in the plan>
2. Stop here — the plan file tracks what is left
3. Produce a written handover report for the tenant owner
```

4. **If a git branch was created**, add the branch options from the section below.

## When something breaks

A query returns nothing, a POST is rejected, a migrated dashboard renders empty, an alert stops firing. Find the cause before changing anything.

**Step A — Investigate.** Read the whole error, including the response body; the settings API names the offending field and constraint. Reproduce it. Check what changed — the last config you applied, a permission, a tenant setting. In a multi-hop path (query → entity model → dashboard tile), check each hop's output rather than guessing which one is wrong.

**Step B — Compare.** Find a working example: another object of the same type in this tenant, or the worked example in the area's reference file. List every difference between it and the broken one, however small.

**Step C — Hypothesize.** State one cause: "I think X because Y." Change one thing to test it. If wrong, form a new hypothesis — do not stack another change on top.

**Step D — Fix.** Address the cause, not the symptom. Verify per Stage 4.

**After three failed attempts, stop.** Three failures usually means the approach is wrong, not that the fourth fix is the right one. Bring it to the user: the gen3 equivalent may not cover this case, the object may need to be rebuilt rather than converted, or the reference may have a gap worth reporting back to this repository.

### Credentials: suspect them first on 401 and 403

An auth failure looks like a broken request, so it gets debugged as one. Before hypothesizing about payloads, check the credential. `401` means the token was not accepted at all — missing, malformed, expired, or the wrong kind. `403` means the caller was authenticated but the token lacks the scope, or the user's account lacks the permission. The distinction matters: `403` is a grant problem for the user to fix, not something to work around by reshaping the request.

#### Three API surfaces

Credential types are not interchangeable, and the surface you are calling decides which one you need. Get the host right and the credential usually follows.

| Surface | Host | Credential |
|---|---|---|
| **Platform API** | `<env-id>.apps.dynatrace.com/platform/` | Platform token (`dt0s16.*`), or OAuth scoped to the account or environment |
| **Classic API** (SaaS) | `<env-id>.live.dynatrace.com/api/` | Access token (`dt0c01.*`) with the endpoint's scope |
| **Account Management API** | `api.dynatrace.com` | OAuth client credentials scoped to the account, exchanged for a short-lived bearer |

#### What dtctl can and cannot reach

**A subset of classic APIs is proxied through the Platform API — only a subset.** For that proxied subset, dtctl works normally: browser OAuth (`dtctl auth login`) or a platform token, against the `.apps` host. For every classic endpoint that is *not* proxied, there is no dtctl path at all — you need an access token (`dt0c01.*`) sent directly to the `.live` host. Hitting a classic endpoint dtctl does not cover is a routine outcome in upgrade work, not a misconfiguration.

**dtctl does not support `api.dynatrace.com` at all**, and cannot use account OAuth credentials. Two different things are both called "OAuth" here and they are not related:

- *dtctl's browser login* — an interactive OAuth 2.0 flow that stores tokens in the keyring, for the Platform API.
- *Account OAuth credentials* — a true client ID and client secret that only work by being exchanged for a temporary bearer token (roughly 5 minutes) carrying the scopes the account endpoint needs. dtctl has no flag to accept a client ID/secret pair.

So an account-management call is always a direct HTTP call: exchange the credentials for a bearer, then call `api.dynatrace.com` with it. Re-exchange rather than caching — it will expire mid-session.

#### Triage table

| Symptom | Likely cause | What to do |
|---|---|---|
| `403` on an endpoint that worked for a different object type | Token is valid but missing that endpoint's scope, or the account lacks the permission | Name the exact missing scope and ask the user to add it. Do not retry the same call |
| dtctl cannot reach a classic endpoint | That endpoint is not among the classic APIs proxied through the Platform API | Call it directly on the `.live` host with an access token (`dt0c01.*`). Expected, not a fault — say which path you used when reporting results |
| The user has an OAuth client ID and secret, and dtctl cannot use them | Those are account credentials for automated access. dtctl uses browser login or a stored token | For platform work, use `dtctl auth login` or a platform token. Keep the client ID/secret for `api.dynatrace.com`, called directly over HTTP |
| Calling the Account Management API | It accepts neither a platform nor an access token | Exchange the OAuth client credentials for a bearer with the scopes that endpoint needs, then make the call |
| dtctl fails a call the API itself supports | dtctl's coverage is narrower than the APIs' | Fall back to a direct HTTP call with the credential that surface expects. A legitimate path, not a workaround |
| A classic endpoint rejects the token you expected to work | Token requirements are not uniform across classic endpoints, even within Config v1. | Do not assume. Use the token type and scope the area's reference or migrator doc names, and ask the user for that one specifically |

#### Two rules

- **Never echo, log, or paste a token value.** Refer to `$DT_PLATFORM_TOKEN`, `$DT_CLASSIC_TOKEN`, or an elided prefix (`dt0s16.…`).
- **Never ask for a broader scope than the task needs**, and never suggest an account-level or admin credential to get past a `403` on a single endpoint. Name the specific scope.

A credential gap is a blocker, not a puzzle. It stops the task and goes to the user — it does not count against the three-attempt limit, because retrying cannot fix it.

## Git, when present

Check once, at the start of Stage 3:

```bash
git rev-parse --is-inside-work-tree 2>/dev/null
```

**Not a repository:** skip everything below. Do not run `git init`, do not suggest it. Artifacts are ordinary files.

**A repository:**

- Offer a working branch before the first change: `git switch -c dt-upgrade/<area>`. If the user declines, or is already on a suitable branch, proceed there. The branch is a convenience, not a gate.
- Commit after each task passes Stage 4 — one migration unit per commit, so a bad step is revertible. The commit follows verification; it never precedes it.
- **Never `git push`. Never open a pull request. Never force-push.** Even if the remote exists and the branch looks ready. Integration with a remote is the user's decision and outside this skill.
- At wrap-up, if a branch was created, add to the options menu:

  ```
  4. Merge <branch> back into <base> locally
  5. Keep <branch> as-is
  ```

  Confirm the base branch before merging rather than assuming `main`.

## Rationalizations

| Thought | Reality |
|---|---|
| "This area is small, I'll skip the scope approval" | Scope approval never disappears. |
| "The mapping is obvious, I'll just write the config" | The reference exists because the mapping has exceptions. Read it for every task. |
| "They asked for the upgrade, so applying it is approved" | Approval to plan is not approval to apply. Show the config first. |
| "The API accepted it, so it is correct" | Accepted means correct structure. It does not mean it replicates classic behavior. |
| "I'll clean up the classic objects while I'm here" | Deleting classic config before the replacement is verified is unrecoverable for the user. Separate task, separate approval. |
| "One more fix attempt" (after two) | Three failures means the approach is wrong. Stop and discuss. |
| "The plan grew but I'm nearly done" | Hidden scope upgrades the tier. Say so and step up. |
| "Approval for the last area covers this one" | Each area gets its own approval. |
| "The branch is green, I'll push it" | Never. No push, no PR, no exceptions. |
