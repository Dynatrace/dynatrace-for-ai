# Running the `glob-name-migrator`

Load this only after the tracking query in
[global-request-naming-rules.md](global-request-naming-rules.md) found affected rules **and** the
user asked to migrate them.

The tool reads each rule, queries live spans and entities in Grail to discover
surviving-attribute conditions that select **exactly** the same services and endpoints, verifies
the match against live data, and writes a ready-to-deploy Config v1 replacement body for every
coverable rule. It is read-only: the agent never uploads rules. Deploying the result is the
customer's step and is out of scope here.

## Prerequisites

- **Python 3.12+**.
- The migrator lives in `./migrator/` (same folder as this file). One-time setup, needs network
  access to fetch `httpx` and `pydantic`:

  ```bash
  cd migrator
  python3 -m venv .venv
  .venv/bin/pip install -e .
  ```

  All commands below run as `.venv/bin/glob-name-migrator <command>` from `migrator/`.
- A Dynatrace **platform token** (`dt0s16.*`) with scopes **`ReadConfig`** and
  **`storage:*:read`**, supplied via the `DT_PLATFORM_TOKEN` environment variable.
  - If it is not already set, ask the customer for it.
  - Classic `dt0c01.*` tokens are rejected.
  - Do **not** request `WriteConfig` — the agent never uploads rules.
- The **tenant URL** (either the classic host or the `.apps` platform host). The migrator derives
  the other automatically.
- **Live traffic during the run.** Replacements are derived from observed spans; a rule whose
  endpoints are dormant cannot be resolved.

## Steps

1. Confirm setup and `DT_PLATFORM_TOKEN` are in place. Ask the customer for the token if missing.
2. Check connectivity and inventory (both read-only). `list-rules` prints every rule by `id` and
   name — it does **not** flag deprecated conditions, so it is a sanity check on connectivity and
   scope, not a substitute for the tracking query:

   ```bash
   .venv/bin/glob-name-migrator dql-smoke --tenant https://<env>.dynatrace.com
   .venv/bin/glob-name-migrator list-rules --tenant https://<env>.dynatrace.com
   ```

3. Assess and generate replacements (read-only). Note the printed `workdir:` path:

   ```bash
   .venv/bin/glob-name-migrator run --tenant https://<env>.dynatrace.com
   ```

   Use the **default window** (`from:now()-2h, to:now()`). Widen `--query-timeframe` only
   reactively, for rules whose endpoints turned out to be dormant; re-run just those with
   `--rule-ids <id> ...`.

4. From the workdir, read `report/summary.json` (machine index) and open `report/report.html`
   (human summary). Classify every rule by bucket: ✅ Fully Resolved, ⚠️ Best-Effort,
   ❌ Not Coverable, 💥 Failures.
5. The workdir **is** the upgrade package — keep it as-is. For each ✅/⚠️ rule, the deployable
   Config v1 object is the `replacement_rule_body` field inside its `report/<rule-id>.json`. Do
   **not** re-assemble it into a different folder layout or hand-edit the bodies.
6. **Never run `apply`.** The agent does not upload rules; the customer deploys the package.
7. Report to the user: the workdir path, the per-bucket counts, and the named rules needing manual
   rework or review. Then stop — deployment is theirs.

## Output

**`run` console summary** — counts of what was inspected, skipped, and migrated:

```
workdir: .../migrator/workdir/run-20260612-084741
inspected 144 rule(s); 30 had no deprecated conditions (skipped); 114 sent through the migrator
case counts (migrating only): {'A': 0, 'C': 114}
translation status: {'fully_migratable': 114, 'partial': 0, 'fully_unmigratable': 0}
verification: {'exact_match': 0, 'no_replacement': 0, 'failed': 0}
```

**Report buckets** in `report/report.html`:

- ✅ **Fully Resolved** — exact match, no negations or demotions needed. Ship as-is.
- ⚠️ **Best-Effort (Negations / Demotions Applied)** — exact, but only after refinement. Ship,
  flag for review.
- ❌ **Not Coverable** — no replacement found. Hand off for manual rework.
- 💥 **Failures** — a stage errored out. Report with the card's reason.

**Per-rule report** (`report/<rule-id>.json`) — field structure (the `deprecated_conditions` and
`surviving_conditions` shown are from a real rule, `PAP API`; `verdict_status` and
`replacement_rule_body` are shown as they appear for a **coverable** rule):

```json
{
  "rule_id": "<rule-id>",
  "naming_pattern": "PAP API",
  "case": "C",
  "verdict_status": "exact_match",
  "deprecated_conditions": [
    { "attribute": "SERVICE_TAG", "operator": "TAG_KEY_EQUALS",
      "dql": "matchesValue(tags, {\"IAM_RP\", \"IAM_RP:*\"})" }
  ],
  "surviving_conditions": [
    { "attribute": "WEBREQUEST_URL_PATH", "operator": "CONTAINS",
      "dql": "contains(url.path, \"/api/\")" }
  ],
  "proposed_conditions": [ "..." ],
  "replacement_rule_body": { "...": "Config v1 RequestNamingDto, ready to deploy" }
}
```

The **deprecated** condition (a `SERVICE_TAG`) is what Phase 3 removes. The
`replacement_rule_body` is a copy of the original rule with `managementZones` emptied and the
deprecated conditions replaced by verified surviving-attribute conditions that select the same
services and endpoints. It is populated only for ✅/⚠️ rules; ❌ Not Coverable rules have an empty
`proposed_conditions` and no body. (Note: the sample run above is against a data-less test tenant,
so it produced no exact matches — `verdict_status: "exact_match"` here illustrates the
coverable-rule shape, not that run's actual verdict.)

Note these bodies use the **Config v1** shape (`namingPattern`, `conditions[].comparisonInfo`),
which is the same representation the tracking query reads — unlike the service detection rules
flow, where the tracking query and the migrator read two different representations.

## Validation

- **Tool self-verification** — `run` only marks a rule as an exact match when its replacement
  filter selects exactly the original target set (verified with live queries); `summary.json`
  records the per-rule verdict and the aggregate counts.
- **Agent checks** — every ✅ Fully Resolved / ⚠️ Best-Effort rule in `summary.json` has a
  populated `replacement_rule_body` in its `report/<rule-id>.json`, and `apply` was never run.
- **Hand-off** — report the workdir path and per-bucket counts, and confirm nothing was uploaded.
  Deployment (Monaco, Terraform, `dtctl`, or a direct `POST` to
  `/api/config/v1/service/requestNaming`) is the customer's step. Nothing in the tenant changes
  until they take it, so do not re-run the tracking query as a check — it will return exactly the
  same rules it did before the run.
- **Post-deployment (customer)** — after deploying the replacements disabled and enabling them,
  confirm requests are still labelled as expected and the deprecated conditions are gone.
