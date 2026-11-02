# Management Zone Permission Scopes

<!-- Jira: none -->

**Gen3 replacement**: IAM policies scoped to enriched fields/tags, or Grail bucket permissions

**Phase 2 required**: yes

Companion to [iam-2nd-gen-roles.md](iam-2nd-gen-roles.md). That reference assesses
*how many* groups still use 2nd gen roles; this one answers the question that
follows: **which management zones do those roles actually grant access to, on
which tenant, and through which groups.**

## Contents

- [What this yields](#what-this-yields)
- [Partial retrieval is the normal case](#partial-retrieval-is-the-normal-case)
- [Prerequisites](#prerequisites)
- [OAuth client and scopes](#oauth-client-and-scopes)
- [Instructions](#instructions)
- [Capture format](#capture-format)
- [Outcome](#outcome)
- [Customer actions](#customer-actions)
- [Validation](#validation)
- [References](#references)
- [Documentation](#documentation)

## What this yields

For one Dynatrace account, the complete set of management zones that are
referenced by a permission grant — with the tenant they belong to, the groups
that hold the grant, and the 2nd gen role granted.

**Listing the management zones that exist on a tenant is the wrong starting
point.** Most of them may be unreferenced by any permission. Migration work is
driven by the grants: every group/zone/role triple is one access rule that has
to be rebuilt as an IAM policy or a bucket permission before Phase 3.

The data comes from the Account Management API:

| Call | Yields |
|---|---|
| `GET /iam/v1/accounts/{account-uuid}/groups` | every group in the account |
| `GET /iam/v1/accounts/{account-uuid}/groups/{group-uuid}/permissions` | that group's grants |

A grant carries `permissionName` (the 2nd gen role), `scopeType`, and `scope`.
The tenant is **encoded inside `scope`** rather than being its own field:

| `scopeType` | `scope` contains | Captured |
|---|---|---|
| `management-zone` | `{environment-id}:{management-zone-id}` | yes |
| `tenant` | the environment ID | yes — a grant with no zone restriction |
| `account` | the account UUID | no, counted only |

`tenant`-scoped grants are captured because they are the important contrast: a
group holding `tenant-viewer` at tenant scope sees the whole environment, so it
is not migrated by translating a zone. `account`-scoped grants are out of scope
for a tenant RBAC migration and are only counted, so their omission is visible.

## Partial retrieval is the normal case

**Do not treat full grant capture as a prerequisite for the migration.** The
credential that can read every group's permissions is an account-level OAuth
client with `account-idm-read`, and the person running a zone migration often
does not hold one. When capture is unavailable, the rest of the migration —
zones, auto-tags, segments, buckets — proceeds unchanged, and this section of
the plan is marked **not retrievable with the supplied credentials** rather
than omitted or guessed at.

What is still available, and worth collecting first because it costs nothing
and bounds the problem:

| Source | Yields | Why it helps |
|---|---|---|
| the management zone export you already have | every zone's name and numeric ID | A grant's scope is formatted `{environment-id}:{management-zone-id}`, so this is the complete set of zone IDs any grant could name |
| the role catalogue in [iam-2nd-gen-roles.md](iam-2nd-gen-roles.md) | the 11 tenant-scoped 2nd gen roles | Bounds which roles could be in use before you look at a single group |

State the zone count and the role catalogue, then say plainly that per-group
grants could not be read and name the credential that would be needed. A plan
that names its own gap is useful; a plan that silently omits the access-control
half is not.

**Do not reach for another account endpoint to fill the gap.** This client
requests `account-idm-read` and nothing else, by design — see [Scopes
deliberately NOT requested](#scopes-deliberately-not-requested). Listing
environments needs `account-env-read` and reading policies needs
`iam-policies-management`; neither is granted, both return 403, and requesting
them widens the credential's blast radius to close a gap the customer's account
administrator can close by sending you the group-to-permission list directly.
Ask them for it.

**Never work around the missing credential.** Do not substitute a `dtctl` token,
an OS-keychain entry, or an environment variable for the account OAuth client —
those are tenant-scoped and cannot read account IAM regardless of prefix (see
[.dtmigration.example](.dtmigration.example)). If `.dtmigration` is absent, stop
and ask the user to create it.

**Consequence for the zone list.** Without grants you cannot tell a *filtering*
zone from an *access-control* zone, so every zone has to be treated as
potentially access-bearing. Say so — it is the reason the plan is more
conservative than it would otherwise be, and it is the concrete argument for
obtaining the credential.

## Prerequisites

- **Node 22+** — the script is TypeScript run with native type-stripping, no
  build step and no dependencies.
- **An account-level OAuth client** — see [OAuth client and scopes](#oauth-client-and-scopes)
  below. A tenant API token (`dt0c01.*`) or platform token (`dt0s16.*`) will
  **not** work.
- **A `.dtmigration` file.** Copy [.dtmigration.example](.dtmigration.example) to
  `.dtmigration` in your working directory and fill in the client ID and secret.
  The script parses this file itself, so the credentials never enter the agent's
  transcript. `.dtmigration` is git-ignored; never commit it.
- **The account UUID**, from *Account Management > Account settings*.

## OAuth client and scopes

This reference targets `https://api.dynatrace.com` — the **account**-level
Account Management API, not a tenant environment API. Its operations declare
`security: [{ bearer: [] }]` with `bearerFormat: JWT`, so they authenticate with
a short-lived JWT obtained by an OAuth2 **client-credentials** exchange. Neither
kind of Dynatrace token can be used instead:

| Credential | Prefix | Works here | Why |
|---|---|---|---|
| Account OAuth client | `dt0s02.*` | **yes** | Account-scoped; exchanged for the JWT these endpoints require |
| Platform token | `dt0s16.*` | no | Environment-scoped; cannot authorize account-level calls |
| Classic API token | `dt0c01.*` | no | Environment-scoped, and sent as `Api-Token`, not `Bearer` |

Create the client under
*Account Management > Identity & access management > OAuth clients > Create client*.

### Required scope

| Scope | Needed | Grants |
|---|---|---|
| `account-idm-read` | **required** | Read groups and their permission assignments — both calls this tool makes |

`account-idm-read` alone is sufficient, and is verified working against a live
account. Nothing else is needed: the tool is **strictly read-only** and makes no
`POST`, `PUT` or `DELETE` request.

### Scopes deliberately NOT requested

Grant only `account-idm-read`. These related scopes exist and are **not**
required — requesting them widens the client's blast radius for no benefit:

| Scope | Would grant | Why not |
|---|---|---|
| `account-idm-write` | Create/modify/delete groups, users and permission assignments | This tool only reads. A read-only client cannot damage an account's RBAC if the credential leaks. |
| `iam-policies-management` | Manage IAM policies and policy bindings | Only needed to read or write gen3 policies, which this tool does not touch. |
| `account-env-read` / `account-env-write` | List and manage environments | The tenant ID is decoded from each permission's `scope` field, so no environment listing is required. |
| `account-uac-read` / `account-uac-write` | Read/manage user access control | Out of scope. |
| `account-audit-logs-read` | Read audit logs | Out of scope. |

The OAuth token request the script builds is:

```
POST https://sso.dynatrace.com/sso/oauth2/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
client_id=<DT_IAM_CLIENT_ID>
client_secret=<DT_IAM_CLIENT_SECRET>
scope=account-idm-read
resource=urn:dtaccount:<account-uuid>
```

`resource` identifies the target account and is confirmed working as sent. If a
deployment's SSO rejects it with HTTP 400, set `DT_IAM_OAUTH_RESOURCE=""` in
`.dtmigration` to omit the parameter. Override `DT_IAM_SCOPES` if a stage uses a
different scope name.

### Targeting another stage

Both endpoints default to production. To target a different stage, set
**both** — the SSO host and the API host must belong to the same stage, or the
token is rejected — and use an OAuth client created on that stage, since clients
are not portable across stages:

| Stage | `DT_IAM_TOKEN_URL` | `DT_IAM_API_URL` |
|---|---|---|
| Production (default) | `https://sso.dynatrace.com/sso/oauth2/token` | `https://api.dynatrace.com` |

The resulting JWT is short-lived and held **in memory only** — never written to
disk, never logged, and never included in an error message.

### Troubleshooting the exchange

| Symptom | Likely cause |
|---|---|
| HTTP 401 from the token endpoint | Wrong `DT_IAM_CLIENT_ID` or `DT_IAM_CLIENT_SECRET` |
| HTTP 400 from the token endpoint | `resource` not expected by this SSO — set `DT_IAM_OAUTH_RESOURCE=""` |
| HTTP 403 from `/iam/v1/...` | Client authenticated but lacks `account-idm-read` |
| HTTP 404 from `/iam/v1/...` | Wrong account UUID, or wrong `DT_IAM_API_URL` for the stage |

## Instructions

### Stage 1 — Capture (once per account)

> **This call is expensive: one API request per group.** An account with 500
> groups makes 500 requests. Run it once, then answer every follow-up question
> from the captured files. Do not re-run it to answer a new question.

```bash
node --experimental-strip-types <scripts/extract-mz-permission-scopes.ts> capture \
  --account-id <account-uuid> --output run
```

Writes two files:

- `run.grants.jsonl` — the complete capture, appended as each group is fetched.
- `run.summary.json` — a small rollup, safe to read whole.

Progress goes to stderr. If the run is interrupted or rate-limited, resume it —
already-captured groups are skipped, so only the remainder is re-fetched:

```bash
node --experimental-strip-types <scripts/extract-mz-permission-scopes.ts> capture \
  --account-id <account-uuid> --output run --resume
```

An existing capture is never overwritten without `--resume`.

### Stage 2 — Read the summary

```bash
cat run.summary.json
```

This is the index: every tenant, every management zone with its grant count,
tenant-wide grant counts, group counts by origin, and any errors. It is
kilobyte-sized and is the **only** file to read in full. Use it to scope the
migration and to pick which zone to work on.

Check `"complete": true` before trusting it.

### Stage 3 — Query one zone at a time

> **Never read `run.grants.jsonl` directly.** Not with Read, `cat`, `head`,
> `tail` or `sed`.
>
> Every line of a JSONL file is an independent valid record, so a truncated view
> is **indistinguishable from a smaller complete dataset**. A partial read
> returns well-formed records and no indication that anything is missing, which
> produces confident wrong answers — reporting that a zone has 2 grants when it
> has 17, or that it has none at all when its grants happen to sit further down
> the file. Unlike a truncated JSON document, which fails to parse and so fails
> loudly, this failure is silent.
>
> Use `show`. It reads the whole file correctly, verifies the capture is
> complete, and returns only the records asked for.

```bash
# every grant on one management zone
node --experimental-strip-types <scripts/extract-mz-permission-scopes.ts> show \
  --input run --tenant <tenant-id> --zone <management-zone-id>

# grants that are NOT zone-restricted on a tenant
node --experimental-strip-types <scripts/extract-mz-permission-scopes.ts> show \
  --input run --tenant <tenant-id> --scope-type tenant

# everything one group grants, across tenants
node --experimental-strip-types <scripts/extract-mz-permission-scopes.ts> show \
  --input run --group-name <group-name>

# every grant held by a group of a given origin (ALL_USERS = every account user)
node --experimental-strip-types <scripts/extract-mz-permission-scopes.ts> show \
  --input run --owner ALL_USERS
```

Filters combine with AND, and at least one is required. Matching is exact, so
zone `-100` never matches zone `-1000`.

Management zone IDs are usually negative. Both `--zone -1234567890` and
`--zone=-1234567890` work.

`show` refuses to answer if the capture has no footer, because the run was then
interrupted or the file truncated and any answer could silently omit grants.
Prefer `capture --resume` to finish it; `--allow-incomplete` overrides the check
when a partial answer is genuinely acceptable.

## Capture format

`run.grants.jsonl` holds four record kinds, distinguished by a leading key.

**Header** (line 1, written before the per-group fan-out):

```json
{"_meta":{"kind":"header","accountUuid":"abc-123","groupsTotal":412,"capturedAt":"2026-08-06T09:32:00Z","schemaVersion":1}}
```

**Grant** (one per captured permission):

```json
{"groupUuid":"g-1","groupName":"eng-ebanking","groupOwner":"SAML","permissionName":"tenant-viewer","scopeType":"management-zone","tenantId":"abc12345","managementZoneId":"-1234567890"}
```

`managementZoneId` is `null` for `scopeType: "tenant"`. `createdAt` and
`updatedAt` are present when the API supplies them.

**Group marker** (after each group's grants) — records that a group was
processed even when it produced no grants, which is what makes `--resume`
correct:

```json
{"_group":{"groupUuid":"g-1","grantsEmitted":1,"status":"ok"}}
```

`status` is `ok`, or `gone` when the group was deleted between the listing and
its permissions call (HTTP 410).

**Error** (one per anomaly; also surfaced in the summary):

```json
{"_error":{"groupUuid":"g-9","groupName":"ops","stage":"permissions","reason":"http-error","message":"HTTP 500"}}
```

`reason` is `http-error`, `malformed-scope`, `missing-group-uuid`, or
`count-mismatch`.

**Footer** (last line):

```json
{"_meta":{"kind":"footer","status":"complete","groupsCaptured":412,"grantsTotal":8140,"accountScopedGrantsSkipped":193}}
```

### Line order is not significant

Records are appended as each group's request completes, and requests run
concurrently, so **the line order of two captures of the same account will
differ** even when the data is identical. Nothing depends on it: `show` reads
the whole file and sorts its own output.

To compare two points in time, diff the **summaries** — those are deterministically
ordered and differ only in `capturedAt` when nothing has changed. Diffing two
`.grants.jsonl` files will show spurious reordering.

### Completeness rule

> **A capture is complete if and only if its last line is a `_meta` footer.**
> Header present but footer absent means you are looking at partial data —
> either the run was interrupted, or the file was read with a tool that
> truncated it.

`grantsTotal` lives in the footer rather than the header because it is not
known until the run finishes; rewriting line 1 afterwards would shift every
following byte. `groupsTotal` **is** in the header, since the group listing
precedes the fan-out.

## Outcome

`run.summary.json`:

```json
{
  "accountUuid": "abc-123",
  "capturedAt": "2026-08-06T09:32:00Z",
  "complete": true,
  "summary": {
    "groupsTotal": 412,
    "groupsCaptured": 412,
    "groupsFailed": 0,
    "groupsGone": 0,
    "grantsTotal": 8140,
    "accountScopedGrantsSkipped": 193,
    "tenantsTotal": 6,
    "managementZonesTotal": 143,
    "groupsWithManagementZoneGrants": 87,
    "groupsByOwner": { "LOCAL": 14, "SAML": 61, "SCIM": 11, "DCS": 0, "ALL_USERS": 1 }
  },
  "tenants": [
    {
      "tenantId": "abc12345",
      "tenantWideGrants": 12,
      "managementZones": [
        { "managementZoneId": "-9876543210", "grantCount": 17 },
        { "managementZoneId": "-1234567890", "grantCount": 3 }
      ]
    }
  ],
  "errors": []
}
```

`tenants` and `managementZones` are arrays rather than objects keyed by ID, so
ordering is stable and two runs of the same account produce a diffable file —
useful for tracking migration progress. `errors` is always present and is `[]`
on a clean run, so an incomplete result never has to be inferred.

### Group origin

`groupOwner` records where a group comes from: `LOCAL` (created in Dynatrace),
`SAML`, `SCIM`, `DCS` (from the corresponding identity provider), or `ALL_USERS`
(a special `LOCAL` group that, per the API, is "always assigned to all users in
the account").

Permission grants are handled inside Dynatrace regardless of origin, so `owner`
does not change how a grant is migrated — it is context about the group. It is
worth having for `ALL_USERS`: a management zone grant on that group applies to
every user in the account.

## Customer actions

- Run the capture once per account and review `run.summary.json` to size the
  work: how many tenants, zones and groups are involved.
- For each management zone, use `show` to list the groups and 2nd gen roles that
  reference it. Each group/zone/role triple is one access rule to rebuild.
- Rebuild each rule on gen3 primitives. Follow
  [management-zones.md](../management-zones/management-zones.md): identify the
  zone's discriminator, confirm it is enriched on the data, then express access
  as an IAM policy boundary on that field or as a Grail bucket permission.
- Treat `scope-type tenant` grants separately — they are not zone-scoped, so they
  map to tenant-wide policies rather than to a zone translation.
- Migrate role assignments to policies as described in
  [iam-2nd-gen-roles.md](iam-2nd-gen-roles.md).
- Re-run the capture after migration to confirm the referenced zone set has
  shrunk as expected.

## Validation

Sanity-check a capture before acting on it:

- `"complete": true` in the summary, and `errors` is `[]`. A non-empty `errors`
  means some groups are missing from the result; `capture --resume` retries
  exactly those.
- `groupsCaptured` equals `groupsTotal`, unless `groupsGone` accounts for the
  difference.
- Spot-check one zone: open the management zone in the tenant's account
  management UI and confirm the groups `show --tenant … --zone …` lists match the
  groups with that zone assigned.
- `accountScopedGrantsSkipped` is non-zero on most accounts — account-level
  roles exist and are deliberately not captured.

## References

- [iam-2nd-gen-roles.md](iam-2nd-gen-roles.md) — assessing the 2nd gen role footprint
- [management-zones.md](../management-zones/management-zones.md) — why management zones have no 1:1 gen3 equivalent, and the discriminator-based migration strategy
- [Dynatrace Account Management API](https://api.dynatrace.com) — [OpenAPI spec](https://api.dynatrace.com/spec-json)

## Documentation

- [Migrate roles to policies](https://docs.dynatrace.com/docs/manage/identity-access-management/permission-management/manage-user-permissions-policies/advanced/migrate-roles)
- [Management zones](https://docs.dynatrace.com/docs/manage/identity-access-management/permission-management/management-zones)
- [Create an OAuth client](https://docs.dynatrace.com/docs/manage/identity-access-management/access-tokens-and-oauth-clients/oauth-clients)
