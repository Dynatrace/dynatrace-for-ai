# Classic Full Service Detection (SDv1) Rules

<!-- Jira: none -->

**Gen3 replacement**: --

**Phase 2 required**: yes

## What changes

Classic rule-based service detection rules (`FULL_WEB_REQUEST` and `FULL_WEB_SERVICE`) are
broken by Phase 3 when they:

- are scoped by **management zones** (the rule's `managementZones` field), or
- carry a **`PG_Tag` condition** whose tag key does not start with `primary_tags.`.

Both must be reworked while still in Phase 2.

## Prerequisites

It is recommended to run [autotagging.md](../../platform/autotagging/autotagging.md) and
[management-zones.md](../../platform/management-zones/management-zones.md) first, **and apply
their results to the environment**. Once applied, span query results carry the correct
`primary_tags.` when the migrator runs.

This skill can be run regardless, but the migrator may produce suboptimal results.

## Tracking query

Run the bundled script. It reads Settings 2.0 via `dtctl` and is read-only:

```bash
cd scripts
node --experimental-strip-types find-affected-rules.ts
```

Requires **Node.js 22+** (the script runs via native TypeScript type-stripping, which needs
`--experimental-strip-types`; on Node 23.6+ the flag is optional) and an authenticated
`dtctl` context pointing at the customer's tenant
(`dtctl config get-contexts` — **check the `Environment` URL, not the context name**).

It reports how many enabled rules use a deprecated condition, and for each one the rule name,
type, and why it is affected. It checks nothing else — whether a rule can actually be migrated
is the migrator's job, not the tracking query's.

## Findings and recommended actions

Report to the user based on what the script returns. Do not go further unprompted.

**No rules returned** — say so plainly and stop:

> No classic service detection rules use deprecated conditions. No action needed for Phase 3.

**Rules returned** — report the count, then one row per rule:

| Rule | Type | Affected because |
|---|---|---|
| `Payments API` | FULL_WEB_REQUEST | non-primary `PG_Tag`: `team-payments` |
| `Checkout web service` | FULL_WEB_SERVICE | management zone scope |

Then give these recommended actions, in this order:

1. **Offer the bundled migrator.** State what it does and what it costs, then ask before
   starting it:

   > The bundled `sdr-migrator` tool can rework these automatically: it queries live spans in
   > Grail to find replacement conditions that select exactly the same services, verifies each
   > one against live data, and writes ready-to-deploy Config v1 rule bodies. It is read-only
   > and never writes to your tenant. It needs Python 3.12+, two API tokens, and live traffic
   > during the run. Shall I run it?

   Only when the user agrees, follow **[migrator.md](migrator.md)**.
2. **Note what the migrator cannot help with.** Rules whose endpoints carry no traffic, or whose
   target set cannot be reproduced from surviving attributes, need manual rework — the migrator
   identifies which, but cannot fix them.

## Customer actions

- If running the migrator: provide a `dt0s16.*` platform token (`storage:*:read` + `ReadConfig`)
  and a `dt0c01.*` classic token (Read configuration). No write scope is needed or used.
- Deploy the generated rule bodies with whatever tooling you prefer — Monaco, Terraform,
  `dtctl`, or a direct API `POST`. They ship disabled; review, enable, then remove the
  originals so both do not match at once.
- Manually rework any rule the migrator reports as not coverable.

## References

- [migrator.md](migrator.md) — running `sdr-migrator` and reading its output. Load only once the
  user has asked to migrate.
- [autotagging.md](../../platform/autotagging/autotagging.md) — converting tags to primary Grail
  tags at source, which is what makes `PG_Tag` conditions survive Phase 3.
- [management-zones.md](../../platform/management-zones/management-zones.md) — the Phase 3
  replacement path for management-zone scoping generally.
- [global-request-naming-rules.md](../global-request-naming-rules/global-request-naming-rules.md)
  — sibling reference and migrator for request naming rules; the same tenant usually needs both.
- [global-failure-detection-rules.md](../global-failure-detection-rules/global-failure-detection-rules.md)
  — sibling reference and migrator for global failure detection rules; the same tenant
  usually needs it too.
