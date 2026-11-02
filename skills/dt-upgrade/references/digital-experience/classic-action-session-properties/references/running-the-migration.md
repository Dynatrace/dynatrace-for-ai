# Running the migration, step by step

Part of [Classic Action and Session Property Capturing](../classic-action-session-properties.md).

⛔ **Run the migration with `migrate_rum_properties.py`, and let it lead.** Start with
`preflight`, then run what each command's `nextStep` names. Every command prints a JSON summary on
stdout carrying `tellTheUser` (say it), `needsApproval` (stop and ask before running that
command), `readFirst` (the section of this reference that explains the step) and, on a refusal,
`whatToDo`. Do not write your own script or `curl` against the tenant for a step the tool has: it
checks things a hand-written request does not. When resuming, or unsure, `status --out-dir <dir>`
names the one command that comes next.

```bash
python3 migrate_rum_properties.py preflight --out-dir "$HOME/dt-rum-migration" \
    [--application APPLICATION-XXXXXXXXXXXXXXXX]
```

**Answer from these files before asking for an artifact.** When someone describes where they are
rather than handing you files, say what the step does and what holds while it runs, then ask for
the file only if the answer actually depends on its contents.

## Step 1 — Preflight

`preflight` names the tenant the tool will talk to and where each setting came from, then checks
the capture schema, `settings.write` (validate-only, nothing is written), the platform token, and
per application whether it is readable, has New RUM enabled and which RUM JavaScript version it
runs. `--application` takes the entity id or the application's exact name; a name resolves only
when one application carries it (`resolvedNames` says to which id), and otherwise the refusal lists
the candidates to ask about. **Confirm the tenant it names with the user before going further** — for this migration the
tenant is the tool's `DT_CLASSIC_BASE`, not the `dtctl` context. `apply` refuses to write without a
`preflight.json` from the last 24 hours covering the applications it writes, because a gate that
passed yesterday on another host proves nothing today. **Artifact:** `preflight.json`.

## Step 2 — Inventory, then read only what the user chooses

**This step is a conversation, because the wrong default is expensive.** The application list
returns ids and names only, and there is no bulk read and no *"has properties"* filter, so finding
out *which* applications carry properties costs **one request per application** — about a second
each, a quarter of an hour on several hundred. Mobile costs more.

| What the listing shows    | What you do                                                                                                          |
|---------------------------|----------------------------------------------------------------------------------------------------------------------|
| A handful (ten or fewer)  | Read them outright and report which carry properties                                                                 |
| More than that            | Report **how many** you found, say you have **not** checked which carry properties and why, and ask which to migrate |
| They name one or a few    | `scan --application <id or name>` for exactly those — naming an id skips the enumeration                             |
| They answer "all of them" | Quote the cost first (*"this takes about twelve minutes"*), then sweep and come back with the list to pick from       |

"All of them" is a legitimate answer. It is not the default, and it is never assumed.
**Artifacts:** `inventory.json`, then `scan.json`.

## Step 3 — Classify and translate

`plan` gives every property a row, 1 to 5, and a row-2 property a disposition (C unless told
otherwise). It translates capture expressions, query-string splits and the cleanup rules it can
translate exactly, and lists what it could not in `needsYourExpression` with the reason and the
`plan --expression` that supplies it. The rules behind each verdict are in
[Classifying properties](classifying-properties.md) and
[Session-scoped properties](session-scoped-properties.md). **Artifact:** `plan.json`.

## Step 4 — Present the plan and stop

Run `report` and present `plan-report.md` **as written** — the properties per application and what
they cost, the row-2 choice per property, Do-Not-Track suppression, the blocked list with its
layer, the user tags in the order they are tried, any application left with no user tagging, the
pipeline, the carrier question and what is still open. Then say the `tellTheUser` lines. Both are
written in what happens and what the user can choose; keep it that way — no decision-table rows,
option letters, flag codes or commands. Those are for you, in the JSON (`ifTheUserChooses`,
`needsApproval`, `expressionsNeeded`, `removeTheEventPropertyWith`). The same holds after the plan:
`apply` and `verify` say in `tellTheUser` what happened, and the commands that follow are in
`nextStep`, `completeWith` and `undo`.

If you shorten the page, keep what changes for the user: which properties need a code change and
the call that sends each, where a cleanup rule that matches nothing keeps the captured value, what
is stored in a different case or decoded differently than before, what cannot migrate, and what is
still open.

Two things the plan cannot decide, so ask: **who may change the route** — pipeline and routing
access are granted separately, and routing is the one that usually stops people — and, only if the
user brings it up, whether the processors should join an existing custom pipeline
(`plan --pipeline-id`) instead of the new one. A separate pipeline is the recommendation: the
processors then run on exactly the route the migration adds, and nobody else's object changes.

**Stop for confirmation before anything is written.** The command a yes leads to is
`needsApproval.command`. **Artifact:** the confirmed plan.

## Step 5 — Apply

`apply` writes both halves, the capture settings and the pipeline with its route; what holds while
it runs, and why the routing object needs care, is in [Writing the objects](writing-the-objects.md).
Run `apply --dry-run` first when the user wants to see the merge. **Artifacts:** `apply.json` and
`backup-<stamp>.json`.

## Step 6 — Verify

`verify` reads the objects back against the plan and the backup, and emits the data-side queries
for when traffic has arrived — see [Verifying the migration](verifying-the-migration.md).
**Artifacts:** `verify.json`, `verify-queries.dql`, and a notebook you can import.

## Step 7 — Hand off the code changes

Give the owner of the application's source `code-changes.json`, which lists the **classic capture
expression per property**: it says *what* the value is, and they supply *when* it becomes known.
To undo a migration, `restore --backup backup-<stamp>.json` puts the objects back as that backup
found them, snapshotting the current state first; `apply` hands you the exact command in `undo`.
Tell the user it can be undone, and run it only when they ask. **Artifact:** `code-changes.json`.

## Replace the classic calls

The four classic calls, their replacements and the published signatures are in
[Replacing the classic calls](replacing-the-classic-calls.md).
