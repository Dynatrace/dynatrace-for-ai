# SDv1 Global Failure Detection Rules

<!-- Jira: none -->

**Gen3 replacement**: --

**Phase 2 required**: yes

## What changes

Global failure detection rules are no longer evaluated in Phase 3 when they:

- are scoped by **management zones** (a `SERVICE_MANAGEMENT_ZONE` condition),
- carry a **`SERVICE_TAG`** condition, or
- carry a **`PG_TAG`** condition with any ordinary tag key (one not starting with `primary_tags.`;
  a condition survives only when *all* its tag keys are primary).

One such condition takes the **whole rule** out of evaluation, not just that condition — the rule
stops being applied and the next matching rule decides instead. All of them must be reworked while
still in Phase 2.

A `PG_TAG` condition that *mixes* `primary_tags.*` and ordinary keys is skipped **already today**,
before Phase 3 changes anything. Such a rule is not doing what its author intended now, so treat it
as a finding in its own right.

## Prerequisites

It is recommended to run [autotagging.md](../../platform/autotagging/autotagging.md) and
[management-zones.md](../../platform/management-zones/management-zones.md) first, **and apply their
results to the environment**. Once applied, span query results carry the correct `primary_tags.`
when the migrator runs.

This skill can be run regardless, but the migrator may produce suboptimal results.

## Tracking query

Run the bundled script. It reads Settings 2.0 and is read-only:

```bash
dtctl exec function -f scripts/find-affected-rules.ts
```

The script runs inside the Dynatrace JS runtime, where the
`@dynatrace-sdk/client-classic-environment-v2` client authenticates its own requests — so it needs
no token of its own, only an authenticated `dtctl` context pointing at the customer's tenant
(`dtctl config get-contexts` — **check the `Environment` URL, not the context name**). The same file
also works unchanged as a dashboard code tile.

It returns `scanned`, `enabled` and `affected` counts, an `affectedByReason` breakdown, and one
`rules` entry per affected rule with its `id`, `name`, `enabled` flag, the `reasons` it is affected,
and the offending `managementZones` / `nonPrimaryProcessGroupTags` / `serviceTags`. It checks nothing
else — whether a rule can actually be migrated is the migrator's job, not the tracking query's.

## Findings and recommended actions

Report to the user based on what the script returns. Do not go further unprompted.

**No rules returned** (`affected: 0`) — say so plainly and stop:

> No global failure detection rules use deprecated conditions. No action needed for Phase 3.

**Rules returned** — report the count, then one row per rule:

| Rule | Affected because |
|---|---|
| `Ignore all exceptions for the public gateway` | `SERVICE_TAG` condition |
| `Payments timeout handling` | management zone scope |
| `Checkout failure handling` | non-primary `PG_TAG`: `team-payments` |

With many affected rules, group by reason and name the rules per group rather than printing a
hundred-row table.

Then give these recommended actions, in this order:

1. **Offer the bundled migrator.** State what it does and what it costs, then ask before starting
   it:

   > The bundled `fdr-migrator` tool can rework these automatically: it works out which services
   > each rule targets today, queries live spans and entities in Grail for replacement conditions
   > built only from attributes Phase 3 still evaluates, proves against live data that they target
   > exactly the same services, and writes ready-to-deploy Settings 2.0 rule bodies. It is
   > read-only and never writes to your tenant. It needs Python 3.12+, one platform token, and live
   > traffic during the run. Shall I run it?

   Only when the user agrees, follow **[migrator.md](migrator.md)**.
2. **Note what the migrator cannot help with.** Rules whose services carry no traffic in the query
   window, and rules whose target set cannot be reproduced from surviving attributes, need manual
   rework — the migrator identifies which, but cannot fix them.

## Customer actions

- If running the migrator: provide a `dt0s16.*` platform token with `settings:objects:read`,
  `storage:spans:read` and `storage:entities:read`. No write scope is needed or used.
- Review the run output — read `report.html`, and in particular any **Read this first** block,
  which says when a verdict may be an artefact of a short read rather than a fact about the rule.
- Deploy the generated `replacement_rule_body` objects with whatever tooling you prefer — Monaco,
  Terraform, `dtctl`, or a direct `POST` to `/api/v2/settings/objects`. They are the raw Settings
  2.0 create shape, so any of these consume them as-is. They ship **disabled**: review, enable,
  then remove the original so both do not match at once. Failure detection rules are ordered and
  first-match-wins, so deploy each one at the position its `insert_after` names.
- Manually rework any rule reported as **No safe replacement** — the tool could not find a
  surviving-attribute condition set that matches the original exactly.
- Check any rule reported as **Targets nothing today**: it selects nothing before Phase 3 changes
  anything, so it may be dead configuration that can simply be deleted.

## References

- [migrator.md](migrator.md) — running `fdr-migrator` and reading its output. Load only once the
  user has asked to migrate.
- [autotagging.md](../../platform/autotagging/autotagging.md) — converting tags to primary Grail
  tags at source, which is what makes `PG_TAG` conditions survive Phase 3.
- [management-zones.md](../../platform/management-zones/management-zones.md) — the Phase 3
  replacement path for management-zone scoping generally.
- [classic-service-detection-rules.md](../classic-service-detection-rules/classic-service-detection-rules.md)
  and
  [global-request-naming-rules.md](../global-request-naming-rules/global-request-naming-rules.md)
  — sibling references and migrators for service detection and request naming rules; the same
  tenant usually needs all three.
