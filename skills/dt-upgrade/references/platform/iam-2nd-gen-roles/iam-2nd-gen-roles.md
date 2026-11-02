# IAM 2nd Gen Roles

**Gen3 replacement**: IAM default policies

**Phase 2 required**: yes

## Contents

- [What changes](#what-changes)
- [Prerequisite](#prerequisite)
- [How 2nd gen roles map to default policies](#how-2nd-gen-roles-map-to-default-policies)
  - [The default monitoring set](#the-default-monitoring-set)
  - [Boundaries, and the question to ask about spans](#boundaries-and-the-question-to-ask-about-spans)
  - [Grail table permissions reference](#grail-table-permissions-reference)
- [Customer actions](#customer-actions)
- [Documentation](#documentation)

## What changes

- Number of groups with 2nd gen roles only
- Number of groups using default policies
- List of groups for both categories with links to account management

> To enumerate which management zones and tenants those role grants actually
> cover — the concrete migration backlog — use
> [mz-permission-scopes.md](mz-permission-scopes.md).

> **Check the Upgrade Assistant app first.** It reports the 2nd gen role footprint
> from its own readiness query over a **365-day** look-back — longer than anything
> here, and a number the customer may already have seen. Start from it and
> reconcile rather than presenting a competing figure; it counts role usage, so it
> does not replace the per-zone grant capture that
> [mz-permission-scopes.md](mz-permission-scopes.md) produces.

## Prerequisite

**The customer's management zones must already have been transitioned to a set of
primary Grail fields.** A boundary can only restrict a default policy by
referencing a field that exists on the data, so until the zones' discriminators
are enriched as primary fields there is nothing for a boundary to match on and
the role-to-policy migration cannot reproduce the old access scoping.

Do this first. [management-zones.md](../management-zones/management-zones.md) is
the reference for it, and covers the categorization each zone needs before any
policy work starts:

| Step | Where |
|---|---|
| Categorize the zone — is it used for **filtering**, **access control**, or both? Determined primarily from the 2nd gen grants that reference the zone; the two functions map to [different Gen3 concepts](../management-zones/management-zones.md#how-each-function-maps-to-gen3) and are migrated separately. | [Stage 1 — Scope & classify](../management-zones/management-zones.md#stage-1--scope--classify) |
| Identify the zone's **discriminator** — the attribute that decides membership (host group, Kubernetes cluster, department, stage, …) | [Stage 1 — Scope & classify](../management-zones/management-zones.md#stage-1--scope--classify) |
| Confirm the discriminator is actually **enriched on the data** as a primary field or tag; if not, enrich it in OpenPipeline first | [Stage 3 — Verify enrichment](../management-zones/management-zones.md#stage-3--verify-enrichment) |

Only the **access control** function is this reference's concern; a zone used
purely for filtering becomes a Segment and needs no policy or boundary at all.

If that categorization and enrichment work is outstanding, it is a blocker for
this migration, not something to work around.

## How 2nd gen roles map to default policies

This covers every tenant-scoped role the Account Management API can return, so a
role not listed here does not exist.

| 2nd gen role | Gen3 default policy |
|---|---|
| `tenant-viewer` | **Standard User**, plus the **default monitoring set**: `spans`, `events`, `metrics`, `entities`, `smartscape` |
| `tenant-manage-settings` | **Admin User** + **Data Processing and Storage** + **All Grail data read access** |
| `tenant-logviewer` | `Read Logs` |
| `tenant-view-sensitive-request-data` | `Read Sensitive Data` |
| `tenant-replay-sessions-with-masking` | `Read User Replays` **and** `Read User Events` |
| `tenant-replay-sessions-without-masking` | `Read User Replays` **and** `Read User Events` |
| `tenant-view-security-problems` | `Read Security Events` |
| `tenant-manage-support-tickets` | **not migrated** |
| `tenant-agent-install` | no equivalent policy — **ignore** |
| `tenant-configure-request-capture-data` | no equivalent policy — **ignore** |
| `tenant-manage-security-problems` | no equivalent policy — **ignore** |

Account-scoped roles (`account-viewer`, `account-company-info`,
`account-user-management`, `account-saml-flexible-federation`) are outside this
migration and are left as they are.

Assign default policies rather than custom ones wherever they fit; reach for a
custom policy only when no default expresses the required access.

### The default monitoring set

`tenant-viewer` is understood as **access to typical observability data**, so it
maps to **Standard User** plus read access to that data — the default monitoring
set:

`spans` · `events` · `metrics` · `entities` · `smartscape`

Logs are **not** in it: log access was its own role (`tenant-logviewer`) and
stays its own policy (`Read Logs`). The same holds for the other data-specific
roles in the table above — sensitive request data, session replays and security
events each keep their own policy rather than arriving with `tenant-viewer`.

### Boundaries, and the question to ask about spans

Boundaries are how a management zone's access-control function is rebuilt: they
restrict a default policy to the **primary Grail fields** the zone was
transitioned to, so the zone's membership logic becomes a condition on enriched
data instead of a zone lookup.

This is why the [prerequisite](#prerequisite) matters — the boundary references
those fields by name. Work the migration per management zone, not per role: for
each zone, take the fields it became and express them as a boundary on the
default policies that replace its role grants.

**Spans are a specific case worth raising with the customer.** Management zones
did not restrict spans in 2nd gen, so leaving spans unrestricted after migration
**mimics the previous behavior**. Applying a boundary to spans would therefore
tighten access beyond what the customer had. This is a question to ask during
migration — whether to preserve the old, unrestricted span access or deliberately
take the opportunity to narrow it — not a default to apply silently either way.

Use [mz-permission-scopes.md](mz-permission-scopes.md) to get the actual list of
zones, groups and roles per tenant, then work that list zone by zone.

### Grail table permissions reference

The default read policies above are built on these table permissions:

| Permission | Table |
|---|---|
| `storage:logs:read` | logs |
| `storage:spans:read` | spans |
| `storage:events:read` | events |
| `storage:bizevents:read` | bizevents |
| `storage:metrics:read` | metrics (timeseries) |
| `storage:entities:read` | entities |
| `storage:smartscape:read` | smartscape nodes and edges |
| `storage:security.events:read` | security.events |
| `storage:user.events:read` | user.events |
| `storage:user.sessions:read` | user.sessions |
| `storage:system:read` | all system tables, e.g. `dt.system.events` |

Two things that catch people out:

- **`storage:buckets:read` is required in addition to any table permission.**
  Tables span buckets, so a table permission alone returns nothing. This is the
  most common cause of a policy that looks correct but yields no data.
- **A condition on a table permission can only widen access, never narrow it.**
  Conditional table permissions are purely additive: a row is readable if *any*
  entry matches it, and conditional entries are dropped outright when the same
  table already carries unconditional access. So `DENY storage:logs:read WHERE …`
  does not carve a hole in an existing grant the way it reads. Denying a subset of
  a table requires a bucket-level DENY instead — which is the main reason to reach
  for dedicated Grail buckets rather than record-level rules. This is specific to
  **table** permissions: `DENY … WHERE` behaves normally on other permission
  families, so do not generalise the restriction to IAM as a whole.

## Customer actions

- **First**: transition management zones to a set of primary Grail fields — this
  is a [prerequisite](#prerequisite), without it boundaries have nothing to
  reference
- Assess the current role-based footprint
- Enumerate which management zones and tenants the role grants cover, per tenant,
  with [mz-permission-scopes.md](mz-permission-scopes.md)
- Transition role assignments on the tenant to default policy assignments (best practice)
- Restrict those default policies with boundaries on the primary Grail fields the
  zones became
- Decide with the customer whether to leave spans unrestricted, which mimics the
  2nd gen behavior where management zones did not restrict spans
- Alternatively, customers can use custom policies

## Documentation

- [Migrate roles to policies](https://docs.dynatrace.com/docs/manage/identity-access-management/permission-management/manage-user-permissions-policies/advanced/migrate-roles)
- [Dynatrace default policies reference](https://docs.dynatrace.com/docs/manage/identity-access-management/permission-management/default-policies)
- [Permissions in Grail](https://docs.dynatrace.com/docs/platform/grail/organize-data/assign-permissions-in-grail)
- [IAM policy reference (storage permissions)](https://docs.dynatrace.com/docs/manage/identity-access-management/permission-management/manage-user-permissions-policies/advanced/iam-policystatements)
- [Policy boundaries](https://docs.dynatrace.com/docs/manage/identity-access-management/permission-management/manage-user-permissions-policies/iam-policy-boundaries)
