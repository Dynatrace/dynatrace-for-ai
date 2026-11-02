# Global Request Naming Rules

**Gen3 replacement**: --

**Phase 2 required**: yes

## What changes

Global request naming rules will no longer be applied in Phase 3 when they:

- are scoped by **management zones** (the rule's `managementZones` field),
- carry a **`SERVICE_TAG`** condition, or
- carry a **`PROCESS_GROUP_TAG`** condition with any ordinary tag key (one not starting with
  `primary_tags.`; a condition survives only when all its tag keys are primary).

All must be reworked before enabling Phase 3.

`primary_tags.*` conditions survive, but Phase 3 evaluates them on the **span** side — against the
entry-point span's `primary_tags.*` resource attributes, with exact, case-sensitive string equality
— rather than against the process-group entity.

## Prerequisites

It is recommended to run [autotagging.md](../../platform/autotagging/autotagging.md) and
[management-zones.md](../../platform/management-zones/management-zones.md) first, **and apply their
results to the environment**. Once applied, span query results carry the correct `primary_tags.`
when the migrator runs.

This skill can be run regardless, but the migrator may produce suboptimal results.

## Tracking query

Run the bundled script. It reads classic Config v1 and is read-only:

```bash
dtctl exec function -f scripts/find-affected-rules.ts
```

The script runs inside the Dynatrace JS runtime, which authenticates its requests automatically —
so it needs no token of its own, only an authenticated `dtctl` context pointing at the customer's
tenant (`dtctl config get-contexts` — **check the `Environment` URL, not the context name**).

It returns `scanned`, `enabled`, and `affected` counts plus one entry per affected rule with its
`id`, `namingPattern`, and the `reasons` it is affected. It checks nothing else — whether a rule can
actually be migrated is the migrator's job, not the tracking query's.

## Findings and recommended actions

Report to the user based on what the script returns. Do not go further unprompted.

**No rules returned** (`affected: 0`) — say so plainly and stop:

> No global request naming rules use deprecated conditions. No action needed for Phase 3.

**Rules returned** — report the count, then one row per rule:

| Rule | Affected because |
|---|---|
| `PAP API` | `SERVICE_TAG` condition |
| `/public/v0.1/projects/apps/<id>/releases` | management zone scope |
| `Checkout naming` | non-primary `PROCESS_GROUP_TAG`: `team-payments` |

With many affected rules, group by reason and name the rules per group rather than printing a
hundred-row table.

Then give these recommended actions, in this order:

1. **Offer the bundled migrator.** State what it does and what it costs, then ask before starting
   it:

   > The bundled `glob-name-migrator` tool can rework these automatically: it queries live spans and
   > entities in Grail to find replacement conditions that select exactly the same services and
   > endpoints, verifies each one against live data, and writes ready-to-deploy Config v1 rule
   > bodies. It is read-only and never writes to your tenant. It needs Python 3.12+, a platform
   > token, and live traffic during the run. Shall I run it?

   Only when the user agrees, follow **[migrator.md](migrator.md)**.
2. **Note what the migrator cannot help with.** Rules whose endpoints carry no traffic, or whose
   target set cannot be reproduced from surviving attributes, need manual rework — the migrator
   identifies which, but cannot fix them.

## Customer actions

- If running the migrator: provide a `dt0s16.*` platform token with `ReadConfig` +
  `storage:*:read`. No write scope is needed or used.
- Review the run output — read `report/report.html`, paying special attention to ⚠️ Best-Effort
  rules (the replacement matched only after negations, demotions, or a time window shift, so
  double-check it is what you want).
- Deploy the generated `replacement_rule_body` objects with whatever tooling you prefer — Monaco,
  Terraform, `dtctl`, or a direct `POST` to `/api/config/v1/service/requestNaming`. The bodies are
  the raw Config v1 API shape, so any of these consume them as-is. Deploy them **disabled** first,
  review, then enable.
- Manually rework any ❌ Not Coverable rules — the tool could not find a surviving-attribute
  replacement that matches the original exactly.

## References

- [migrator.md](migrator.md) — running `glob-name-migrator` and reading its output. Load only once
  the user has asked to migrate.
- [autotagging.md](../../platform/autotagging/autotagging.md) — converting tags to primary Grail
  tags at source, which is what makes tag conditions survive Phase 3.
- [management-zones.md](../../platform/management-zones/management-zones.md) — the Phase 3
  replacement path for management-zone scoping generally.
- [classic-service-detection-rules.md](../classic-service-detection-rules/classic-service-detection-rules.md)
  — sibling reference and migrator for service detection rules; the same tenant usually needs both.
- [global-failure-detection-rules.md](../global-failure-detection-rules/global-failure-detection-rules.md)
  — sibling reference and migrator for global failure detection rules; the same tenant
  usually needs it too.
