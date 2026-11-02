# Running the `fdr-migrator`

Load this only after the tracking query in
[global-failure-detection-rules.md](global-failure-detection-rules.md) found affected rules **and**
the user asked to rework them.

The tool reads every Global Failure Detection Rule, works out which services each affected rule
targets today, queries live spans and entities in Grail for a condition set built only from
attributes Phase 3 still evaluates, proves against live data that the set targets **exactly** the
same services, and writes a ready-to-deploy Settings 2.0 create payload for every rule it can
cover. It is read-only: there is no `apply` command, the token it asks for carries no write scope,
and nothing in the tenant changes. Deploying the result is the customer's step and is out of scope
here.

Its subject is the **affected rules only** — the enabled rules carrying a condition Phase 3 no
longer evaluates. Every other rule is read once so it can be ruled out, and nothing else is asked
about it. Never phrase a finding as a claim about the tenant's rules in general.

## Prerequisites

- **Python 3.12+**.
- The migrator lives in `./migrator/` (same folder as this file). One-time setup, needs network
  access to fetch `httpx` and `pydantic`:

  ```bash
  cd migrator
  python3 -m venv .venv
  .venv/bin/pip install -e .
  ```

  All commands below run as `.venv/bin/fdr-migrator <command>` from `migrator/`.
- **One token** — a Dynatrace **platform token** (`dt0s16.*`) with three read scopes:
  `settings:objects:read`, `storage:spans:read`, `storage:entities:read`.
  - Supplied through the `DT_PLATFORM_TOKEN` environment variable and **nowhere else**. There is
    deliberately no `--token` flag: a token on the command line is readable from the process list
    by any local user and lands in shell history.
  - Classic `dt0c01.*` tokens are rejected with a clear error.
  - Do **not** request any write scope. The tool never writes to the tenant.
- The **tenant URL**, via `--tenant` or the `DT_TENANT` environment variable. Either the classic
  host or the `.apps` platform host works; the migrator derives the platform host from a classic
  one, and passes an unrecognised host through unchanged.
- **Live traffic during the run.** What a rule targets is established from observed spans, so a
  rule whose services are idle over the query window cannot be measured.

## Steps

1. Confirm `DT_TENANT` and `DT_PLATFORM_TOKEN` are set. Ask the customer for the token with the
   three scopes above if it is missing.
2. Check that a run can work at all (read-only — one Settings read and one 5-minute span probe):

   ```bash
   .venv/bin/fdr-migrator check-connection --tenant https://<env>.apps.dynatrace.com
   ```

   ```
   [ok] credential kind: platform token dt0s16.***
   [ok] tenant URL: https://<env>.apps.dynatrace.com
   [ok] Settings 2.0 read: read 50 Global Failure Detection Rule(s)
   [ok] Grail query: query returned 1 span(s)
   ```

   Exit code is 0 only when all four pass. A Grail check that succeeds with **0 spans** is still
   `[ok]` — the grant is proven — but it is a warning worth relaying: span-side work in a run over
   a window like that will find nothing to read.
3. Rework the affected rules. Note the printed report path — its parent directory is the workdir:

   ```bash
   .venv/bin/fdr-migrator run --tenant https://<env>.apps.dynatrace.com
   ```

   Use the **default window** (`2h`). Widen `--window` only reactively, for rules that came back
   under *No traffic in the query window*, and re-run just those with
   `--rule-ids <object-id> ...`. `--window` takes a whole number and a unit — `m`, `h` or `d`
   (`30m`, `2h`, `7d`); anything else is refused rather than silently defaulted.
4. Read `<workdir>/summary.json` for the counts and `<workdir>/report.html` for per-rule detail.
   Classify every rule by bucket (see below), and read the **Read this first** block at the top of
   the report if one is present — it says when a verdict may be an artefact of a short read rather
   than a fact about the rule.
5. The workdir **is** the upgrade package — keep it as-is. Each `artifacts/<object-id>.json` holds
   one complete create payload plus the position it belongs at. Do not re-assemble or hand-edit
   them.
6. Report to the user: the workdir path, the per-bucket counts, and the named rules needing manual
   rework or a re-run. Then stop — deployment is theirs.

## Output

```
workdir/run-20260101T090000/
├── summary.json                  # run metadata, scan figures, bucket counts, one entry per rule
├── report.html                   # bucketed, per-rule human report
├── artifacts/
│   └── <object-id>.json          # one deployable payload per covered rule
└── cache/                        # DQL response cache, not part of the package
```

Each run gets its own directory; an earlier run's directory is never written into or removed.

**Console summary** — the report path, the window every finding is relative to, and the buckets:

```
Report: workdir/run-20260101T090000/report.html
Window: 2h (from:"2026-01-01T07:00:00Z", to:"2026-01-01T09:00:00Z")
     2  covered
     0  not-coverable
     0  selects-nothing
     0  no-traffic
     0  no-verdict
     0  unprocessable
```

Exit codes: **0** the run finished, **1** at least one rule could not be processed, **2** the run
never started or was aborted (missing or wrong-kind token, missing tenant, unreadable `--window`,
or a failure that ended the pass and left no report).

**`summary.json`** keeps the three kinds of figure apart, which is what stops a subset run being
read as a tenant total:

```json
{
  "run": {
    "platform_url": "https://<env>.apps.dynatrace.com",
    "window": "2h",
    "timeframe": "from:\"2026-01-01T07:00:00Z\", to:\"2026-01-01T09:00:00Z\"",
    "workdir": "workdir/run-20260101T090000",
    "requested_rule_ids": [],
    "unmatched_rule_ids": [],
    "requested_not_affected": [],
    "primary_tags_unavailable": false,
    "primary_tag_keys_capped": false
  },
  "scan":     { "rules_read": 50, "enabled": 48, "affected": 31,
                "affected_reasons": { "service-tag": 28, "non-primary-pg-tag": 3,
                                      "management-zone": 1 } },
  "outcomes": { "covered": 2, "not-coverable": 0, "selects-nothing": 0,
                "no-traffic": 0, "no-verdict": 0, "unprocessable": 0 },
  "rules":    [ { "object_id": "…", "name": "…", "outcome": "covered", "reason": "exact",
                  "affected_reasons": ["service-tag"], "detail": "",
                  "artifact": "workdir/…/artifacts/….json" } ]
}
```

- `scan` describes the **pass over the ruleset**, not findings: every rule was read so the affected
  ones could be found.
- `outcomes` and `rules` describe the **affected rules only**.
- A non-empty `requested_rule_ids` means the run was restricted, so the outcome counts are about
  those rules and are not tenant totals. `unmatched_rule_ids` are ids the tenant holds no rule for;
  `requested_not_affected` are ids that name a real rule which is disabled or carries nothing
  deprecated.
- `primary_tags_unavailable` / `primary_tag_keys_capped` — the read that says which primary tag
  keys the tenant carries did not answer, or came back capped. Either one means a rule reported as
  having no safe replacement may well have one; say so when relaying the results.

### Buckets

Every affected rule lands in exactly one bucket, and carries the exact terminal `reason` code
alongside it. The bucket groups; the code says what actually happened. Relay both.

| Bucket in `report.html` | `outcome` | `reason` codes it holds | Meaning | Action |
|---|---|---|---|---|
| Replacement found | `covered` | `exact` | A condition set built only from still-evaluated attributes targets exactly what the rule targets today, proved against live data. | Review the body, then create it and enable it in place of the original. |
| No safe replacement | `not-coverable` | `over-selecting`, `service-type-only`, `empty-replacement`, `no-expressible-candidate`, `too-many-conditions`, `untranslatable` | Measured, and no set reproduces the target set without a condition Phase 3 drops — every set also selected services the rule does not, or the rule carries something inexpressible. | Manual rework. The attributes the rule's services offered are listed per rule in the report. |
| Targets nothing today | `selects-nothing` | `dead-today`, `empty-scope`, `matches-nothing`, `only-external-services` | The rule targets nothing before anything changes: its zone, tag or name resolved to nothing, or it reaches only external services. | Check whether what it refers to still exists; if not it is dead configuration and may be deletable. |
| No traffic in the query window | `no-traffic` | `dormant` | The services carried no failure-detection traffic in the window, so there was nothing to measure against. A statement about the window, not the rule. | Re-run with a wider `--window` over a stretch the services served traffic in. |
| No verdict reached | `no-verdict` | `incomplete-read`, `query-too-large`, `unverified`, `under-selecting` | A measurement did not complete. Nothing says the rule cannot be reworked, only that this run could not establish it. | Read the per-rule detail, then narrow the window or the rule's scope and run again. |
| Could not be processed | `unprocessable` | `unclassifiable`, `processing-error` | The tool has no reading for the rule, or it failed working on it. Not fixable by editing the rule, and unchanged by a re-run. | Report to Dynatrace with the rule and the diagnostics shown. |

Only `covered` rules produce a file under `artifacts/`. A rule in any other bucket keeps the
condition set that was **attempted** — the report shows it, so a manual reworker starts from what
the tool already found — but nothing is written out and there is nothing to deploy.

## The emitted artifact

One file per covered rule, holding the reasoning and the deployable body together:

```json
{
  "rule_id": "<object-id>",
  "name": "Ignore all exceptions for the public gateway",
  "outcome": "exact",
  "insert_after": "<object-id of the rule this one sits behind>",
  "deprecated_conditions": [
    { "reason": "service-tag",
      "condition": { "attribute": "SERVICE_TAG",
                     "predicate": { "predicateType": "TAG_KEY_EQUALS",
                                    "tagKeys": ["team-gateway"] } } }
  ],
  "surviving_conditions": [],
  "dropped_duplicates": [],
  "replacement_rule_body": {
    "schemaId": "builtin:failure-detection.environment.rules",
    "scope": "environment",
    "value": {
      "name": "Ignore all exceptions for the public gateway",
      "description": "Apply the 'Ignore all exceptions' parameter set to all services with the given tag key",
      "parameterId": "<object-id of the parameter set>",
      "enabled": false,
      "conditions": [
        { "attribute": "SERVICE_NAME",
          "predicate": { "predicateType": "STARTS_WITH",
                         "textValues": ["ApiGateway Public ("], "caseSensitive": true } },
        { "attribute": "PG_NAME",
          "predicate": { "predicateType": "STRING_EQUALS",
                         "textValues": ["apigateway-public main"], "caseSensitive": true } }
      ]
    }
  }
}
```

What that shows about every emitted body:

- The deprecated condition — here a `SERVICE_TAG` — is **gone**, replaced by conditions on
  attributes Phase 3 still evaluates that were verified to select the same services. Surviving
  conditions the customer wrote are copied through byte-identical.
- It is a **create payload**, not the original object with fields subtracted: `schemaId`, `scope`
  and `value`, and nothing else. Every server-assigned field (`objectId`, `summary`, `created`,
  `modified`, `updateToken`, …) is absent, because a create rejects them.
- `parameterId` is carried over exactly as stored — it points at the parameter set that decides
  what the rule *does*, which the migrator never changes.
- `enabled` is always **`false`**, whatever the original was, so landing the object changes nothing
  until someone turns it on.
- `insert_after` is a **sibling of the body, not part of it**. Failure detection rules are ordered
  and first-match-wins, so position is part of the meaning: pass it as the `insertAfter` member of
  the create. An empty string means *first position* — deploy the object ahead of every other rule.
- `dropped_duplicates` lists conditions left out for saying exactly what another already says; an
  empty list is the normal case.

**Deploying** is the customer's step. `POST /api/v2/settings/objects` takes a **JSON array** of
create objects, so one body becomes `[{…replacement_rule_body…, "insertAfter": "<insert_after>"}]`.
Monaco, Terraform and `dtctl` consume the same shape. Note this is the **Settings 2.0**
representation, which is also what the tracking query reads — one rule, one representation, so
nothing here needs converting.

## Validation

- **Tool self-verification** — a body is written only when the replacement condition set was
  proved, with live queries over the run's single fixed window, to select exactly the services the
  rule selects today. There is no partial or best-effort match: a comparison that does not hold
  produces no file. Files therefore exist *only* for `covered` rules.
- **Agent checks** — every `covered` entry in `summary.json` has a non-null `artifact` and that
  file exists; the bucket counts sum to the number of entries in `rules`; every
  `replacement_rule_body` carries `"enabled": false` and exactly the three members `schemaId`,
  `scope`, `value`; no body contains `objectId`, `summary`, `created`, `modified` or `updateToken`.
- **Hand-off** — report the workdir path and the per-bucket counts, and confirm nothing was
  uploaded. Nothing in the tenant changes until the customer deploys, so do not re-run the tracking
  query as a check — it will return exactly the same rules it did before the run.
- **Post-deployment (customer)** — deploy disabled, review, then enable the replacement and remove
  or disable the original so both do not match at once. Because the rules are first-match-wins,
  check the replacement landed at the position `insert_after` named.
