# Request Attributes

**Gen3 replacement**: --

**Phase 2 required**: yes

## What changes

A request attribute captures through one or more **Data Sources**, each with a **Scope** that
decides which processes it applies to. Phase 3 removes two kinds of Scope condition, and a Data
Source that relies on one stops capturing:

- a **service technology** condition (the Scope's `serviceTechnology`), or
- a **non-primary process group tag** condition (a `tagOfProcessGroup` whose key does not start
  with `primary_tags.`).

Both must be reworked while still in Phase 2. Separately, a request attribute that captures
**only onto external service calls**, or that has no enabled Data Source at all, keeps nothing
Phase 3 preserves — external services are gone in Phase 3 — so it is to be **deleted**, not
migrated.

## Prerequisites

It is recommended to run [autotagging.md](../../platform/autotagging/autotagging.md) first, **and
apply its results to the environment**. Once applied, spans carry the correct `primary_tags.` when
the migrator runs, which is the material it reconstructs a non-primary tag's replacement from.

This skill can be run regardless, but the migrator may produce suboptimal results.

## Tracking query

Run the bundled script. It reads classic Config v1 and is read-only:

```bash
dtctl exec function -f scripts/find-affected-rules.ts
```

The script runs inside the Dynatrace JS runtime, which authenticates its requests automatically —
so it needs no token of its own, only an authenticated `dtctl` context pointing at the customer's
tenant (`dtctl config get-contexts` — **check the `Environment` URL, not the context name**). The
same file also works unchanged as a dashboard code tile.

It returns `scanned`, `enabled` and `affected` counts, an `affectedByReason` breakdown, and one
`rules` entry per affected request attribute with its `id`, `name`, and the `reasons` it is
affected — a service technology scope condition, a non-primary process group tag scope condition,
or both. (The key is named `rules` so that every page in this family returns the same shape, even
though a request attribute is not a rule.) A separate `obsolete` list carries the request
attributes that capture nothing worth keeping — those whose enabled Data Sources all capture on
client-side external service calls, and those with no enabled Data Source at all. Both are to be
**deleted**, not migrated, and both are excluded from `affected`.

It checks nothing else. Whether an affected request attribute can actually be migrated is the
migrator's job, not the tracking query's — and `scanned` / `enabled` describe how much the scan
covered, never a claim about the tenant's request attributes in general.

## Findings and recommended actions

Report to the user based on what the script returns. Do not go further unprompted.

**Nothing affected or obsolete** — say so plainly and stop:

> No request attributes use deprecated conditions and none are obsolete. No action needed for
> Phase 3.

**Something returned** — report the counts, then one row per affected request attribute:

| Request attribute | Affected because |
|---|---|
| `payment.customer` | non-primary `tagOfProcessGroup`: `team:payments` |
| `checkout.region` | service technology scope |

List the `obsolete` request attributes separately — they are deletions, not migrations.

Then give these recommended actions, in this order:

1. **Offer the bundled migrator.** State what it does and what it costs, then ask before
   starting it:

   > The bundled `ra-migrator` tool can rework the affected request attributes automatically: it
   > queries live spans and topology in Grail to reconstruct exactly what each affected Data
   > Source selected, finds replacement Scope conditions that select the same set, verifies each
   > against live data, and writes ready-to-deploy Config v1 bodies. It is read-only and never
   > writes to your tenant. It needs Python 3.12+, one platform token, and live traffic during the
   > run. Shall I run it?

   Only when the user agrees, follow **[migrator.md](migrator.md)**.
2. **Delete the obsolete ones.** The request attributes on the `obsolete` list capture nothing
   Phase 3 keeps; they need deletion, not migration, and the migrator does not touch them.
3. **Note what the migrator cannot help with.** Request attributes whose members carry no live
   traffic, or whose Target Set cannot be reproduced from surviving attributes, need manual
   rework — the migrator identifies which, but cannot fix them.

## Customer actions

- If running the migrator: provide a `dt0s16.*` platform token with scopes
  `ReadConfig, storage:spans:read, storage:entities:read`. No write scope is needed or used.
- Deploy the generated bodies with whatever tooling you prefer — Monaco, Terraform, `dtctl`, or a
  direct API `POST` to `/api/config/v1/service/requestAttributes`. Review, then remove the
  originals so both do not capture at once.
- Delete the request attributes reported as obsolete.
- Manually rework any request attribute the migrator reports as not coverable.

## References

- [migrator.md](migrator.md) — running `ra-migrator` and reading its output. Load only once the
  user has asked to migrate.
- [autotagging.md](../../platform/autotagging/autotagging.md) — converting tags to primary Grail
  tags at source, which is what gives a non-primary `tagOfProcessGroup` a surviving replacement.
- [external-services.md](../external-services/external-services.md) — external service calls are
  removed in Phase 3, which is why a request attribute that captures only onto them is obsolete.
- [global-request-naming-rules.md](../global-request-naming-rules/global-request-naming-rules.md)
  — sibling reference and migrator for request naming rules; the same tenant usually needs both.
- [classic-service-detection-rules.md](../classic-service-detection-rules/classic-service-detection-rules.md)
  — sibling reference and migrator for classic service detection rules.
