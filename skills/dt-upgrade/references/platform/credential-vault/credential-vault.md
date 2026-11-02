# Credential Vault Migration Guide

**Gen3 replacement**:
SDK: `@dynatrace-sdk/client-classic-environment-v2` (entire SDK deprecated) → `@dynatrace-sdk/client-credential-vault` v1.1.0+.
Platform Credential Vault API (`/platform/credential-vault/v1/`), replacing the Classic credential vault API (`/api/v2/credentials`).

**Phase 2 required**: no

## What changes

| | Classic | Latest Dynatrace |
|---|---|---|
| API path | `/api/v2/credentials` | `/platform/credential-vault/v1/entries` |
| SDK package | `@dynatrace-sdk/client-classic-environment-v2` (**deprecated**) | `@dynatrace-sdk/client-credential-vault` v1.1.0+ |
| SDK client | `credentialVaultClient` | `credentialVaultEntriesClient` |
| API token scope | `credentialVault.read` / `credentialVault.write` | `credential-vault:entries:read` / `credential-vault:entries:write` |
| IAM permission | `environment:roles:viewer` | `credential-vault:entries:read` / `credential-vault:entries:write` |
| Workflows authorization setting (non-service-user actors) | `environment-api:credentials:read` | `credential-vault:entries:read` |
| Entry ID prefix | `CREDENTIALS_VAULT-<HEX>` | `CREDENTIAL_VAULT_ENTRY-<HEX>` |

**No ID migration is needed.** Every credential vault entry already has both a Classic ID and a new ID, and both work with the new API and SDK. Do not update existing credential references in monitors, workflows, dashboards, or notebooks, and do not recreate or delete entries. Use the `CREDENTIAL_VAULT_ENTRY-` ID only for new content.

Everything that reads stored credentials is affected:

| Consumer | Code change | Permission change |
|---|---|---|
| Run JavaScript tasks in workflows | Yes, section 5 | Yes, section 3 |
| JavaScript code in dashboards and notebooks | Yes, section 5 | Yes, section 3 |
| App functions and shared helpers that call the credential vault SDK | Yes, section 5 | Check which user or actor runs the code (section 3) |
| HTTP request tasks in workflows (stored credential) | **No** | Yes, section 3 — before the environment moves to the latest Dynatrace (Phase 3) |

This guide covers consumers of stored credentials.

---

## 1. Prerequisite: check that the SDK is available

Before changing any JavaScript code, confirm that `@dynatrace-sdk/client-credential-vault` is available on the target tenant. The JS sandbox rejects unknown `@dynatrace-sdk/*` packages **at load time** — a missing package is a hard error, not a runtime exception you can catch.

**Definitive signal — `dtctl exec` import probe:**

```typescript
// probe-credential-vault-sdk.ts
import { credentialVaultEntriesClient } from '@dynatrace-sdk/client-credential-vault';

export default async function() {
    const entries = await credentialVaultEntriesClient.listCredentialVaultEntries();
    return entries;
}
```

Run the probe:

```dtctl
dtctl exec function -f probe-credential-vault-sdk.ts
```

Interpret the result:

| Result | Meaning |
|--------|---------|
| Function returns successfully | SDK is available — continue with section 2 |
| `"The module \"@dynatrace-sdk/client-credential-vault\" does not exist."` | SDK is not available on this tenant — **stop**; do not change any code |

> **`dtctl get sdk-versions` is unreliable** — it may return an empty array even when packages
> are available. The `exec` import probe is the authoritative check.

**The probe is a precondition.** Do not change any JavaScript code until the probe succeeds on every target tenant. If it fails with the `module ... does not exist` error, stop and report the tenant and the error instead of working around it. If it fails with a 403, the SDK is present but the caller lacks `credential-vault:entries:read`: grant it (section 3) and run the probe again. The SDK does not depend on the move to the latest Dynatrace: once the probe passes, the code can be switched and tested right away.

---

## 2. Order of steps

Do the steps in this order, so the migrated code does not run into a 403:

1. Probe the SDK (section 1).
2. Grant the new permissions to every actor and user (section 3).
3. Check the credential entry settings (section 4).
4. Migrate the JavaScript code (section 5).
5. Run the workflow or code and verify (section 6).
6. Clean up the Classic permissions (section 6), unless the actor still runs HTTP request tasks with stored credentials. Those need the Classic permissions until the move to Phase 3.

HTTP request tasks skip steps 1 and 4: they have no code to migrate. Verify them after the move to Phase 3.

---

## 3. Permissions

Credential vault access uses dedicated permissions instead of the broad Classic `environment:roles:viewer` role. Code that creates, updates, or deletes entries also needs `credential-vault:entries:write`.

The Standard User, Pro User, and Admin User default policies already include `credential-vault:entries:read`. Actors and users on custom policies need it added. Custom policies and policy boundaries can remove a permission that a default policy grants.

If a permission is missing, the call fails with a **403** error.

### Workflows

Every workflow runs under an actor (a user or service user). The actor needs permissions in two places:

- **IAM policies** — for every actor, including service users.
- **Workflows authorization settings** — only if the actor is not a service user. The user turns on the permission under Workflows > Settings > Authorization settings > **Secondary permissions**. Only that user can change their own settings; an administrator cannot do it for them.

| Task type | Actor permissions |
|---|---|
| Run JavaScript | `credential-vault:entries:read` (plus `:write` if the code modifies entries) in IAM, and in authorization settings for non-service-user actors |
| HTTP request (stored credential) | No change to the task. Until the move to Phase 3, the actor needs **both** the Classic permissions (`environment:roles:viewer`, `environment-api:credentials:read`) and the new `credential-vault:entries:read`. Do not remove the Classic permissions before the move |

To find the actor of a workflow, open it in the workflow editor, select the options icon next to **Run** and **Executions**, and check the details pane.

**Find the actors of HTTP request tasks that use credentials.** Run this query in Notebooks. It returns one row per actor with the last call, the number of calls, the number of denied calls (403), and the IDs of the workflows:

```dql
fetch dt.system.events, from:-30d
| filter event.kind == "AUDIT_EVENT" and event.provider == "API_GATEWAY"
| filter dt.app.id == "dynatrace.automations" and dt.app.function == "api/http-function"
| filter startsWith(resource, "/platform/classic/environment-api/v2/credentials")
      or startsWith(resource, "/platform/credential-vault/")
| summarize
  {
    last_used   = max(timestamp),
    calls       = count(),
    denied      = countIf(event.outcome == "403"),
    workflows   = collectDistinct(details.dt.automation_engine.workflow.id)
  },
  by: { user.id }
| lookup [
    fetch dt.system.events, from:-30d
    | filter event.kind == "BILLING_USAGE_EVENT" and isNotNull(user.email)
    | summarize n = count(), by: { user.id, user.email }
  ], sourceField: user.id, lookupField: user.id, fields: { user.email }
| fieldsAdd service_user = if(isNull(user.email), "unknown",
                           else: if(endsWith(user.email, "@service.sso.dynatrace.com"), "yes", else: "no"))
| fields user.id, user.email, service_user, last_used, calls, denied, workflows
| sort last_used desc
```

The `service_user` column is `unknown` if the user ID can't be resolved to an email address. If some workflows run less often than every 30 days, increase the `from:` timeframe.

**Optional: use a service user as actor.** For workflows that several people edit or that serve production, a service user as actor keeps the actor from changing when someone edits the workflow, and the workflow no longer depends on one user's authorization settings. Assigning one requires `iam:service-users:use`.

### Dashboards and notebooks

JavaScript code in dashboards and notebooks runs with the permissions of the user who runs it. Authorization settings and service users do not apply. Every user who runs the code needs `credential-vault:entries:read` (plus `:write` if the code modifies entries) through an IAM policy.

---

## 4. Credential entry settings

No change to the entries is needed for the upgrade. Workflows, dashboards, and notebooks can only use a credential if its app scope and access settings allow it:

| Consumer | Required entry setting |
|---|---|
| HTTP request tasks | **Dynatrace apps with access**: All applications or Workflows is selected |
| Run JavaScript tasks, and JavaScript in dashboards and notebooks | **Allow access without app context** is turned on |
| All of the above | The workflow actor or the user who runs the code owns the credential or is listed under **Users with access**. To list a service user, enter its email address (shown under Service users) |

---

## 5. JavaScript — SDK migration

Check all of these locations — most teams have calls in more than one:

| Where the call lives | Typical path |
|---|---|
| Workflow JavaScript tasks | `workflows/**/*.js`, `*.workflow.json` |
| App functions | `api/**`, `*.function.ts` |
| Workflow actions | `*.action.ts` |
| Shared helpers | `shared/**`, `lib/**`, `src/auth/**` |
| Dashboard and notebook JavaScript code | Code tiles and cells that call `credentialVaultClient` |

For list, create, get, update, and delete operations, switch to the new Credential Vault SDK — different package, different client name, different method name, and *credentials* becomes *entries*:

**Before:**

```typescript
import { credentialVaultClient } from '@dynatrace-sdk/client-classic-environment-v2';
const list = await credentialVaultClient.getCredentials();
```

**After:**

```typescript
import { credentialVaultEntriesClient } from '@dynatrace-sdk/client-credential-vault';
const list = await credentialVaultEntriesClient.listCredentialVaultEntries();
```

> The exported client is named `credentialVaultEntriesClient` in the new package, not `credentialVaultClient`. Update all call sites, not just the import line.

The `id` parameter is now `entryId`. For example, reading a secret:

**Before:**

```typescript
import { credentialVaultClient } from '@dynatrace-sdk/client-classic-environment-v2';
const { token } = await credentialVaultClient.getCredentialsDetails({ id: 'CREDENTIALS_VAULT-XXXXXXXXXXXXXXXX' });
```

**After:**

```typescript
import { credentialVaultEntriesClient } from '@dynatrace-sdk/client-credential-vault';
const { token } = await credentialVaultEntriesClient.getCredentialVaultEntryDetails({ entryId: 'CREDENTIAL_VAULT_ENTRY-XXXXXXXXXXXXXXXX' });
```

> The existing `CREDENTIALS_VAULT-` ID is also accepted as `entryId`; you don't need to change it.

The same swap applies to all methods:

| Operation | Classic | New |
|-----------|---------|-----|
| List | `getCredentials()` | `listCredentialVaultEntries()` |
| Create | `createCredentials(...)` | `createCredentialVaultEntry({ body })` |
| Get (metadata only) | `getCredentials({ id })` | `getCredentialVaultEntry({ entryId })` |
| Get details (includes secret) | `getCredentialsDetails({ id })` | `getCredentialVaultEntryDetails({ entryId })` |
| List details | `getCredentialsDetailsList()` | `listCredentialVaultEntryDetails()` |
| Update | `updateCredentials({ id, ... })` | `updateCredentialVaultEntry({ entryId, body })` |
| Delete | `removeCredentials({ id })` | `deleteCredentialVaultEntry({ entryId })` |

> **Secrets**: migrate `getCredentialsDetails` / `getCredentialsDetailsList` to
> `getCredentialVaultEntryDetails` / `listCredentialVaultEntryDetails`, **not** to
> `getCredentialVaultEntry`. The plain `getCredentialVaultEntry` returns entry metadata only and
> does not include the secret value.

---

## 6. Verify and clean up

1. Run the workflow or the code and confirm it completes successfully. For Run JavaScript tasks, dashboards, and notebooks, this works before the move to the latest Dynatrace. For HTTP request tasks, verify after the move to Phase 3, or at the next scheduled execution.
2. Then remove `environment:roles:viewer` from the actor or user, unless they need it for other purposes. **Do not remove it while the actor still runs HTTP request tasks with stored credentials**, until the environment has moved to Phase 3.
3. If the actor is not a service user, they can also turn off `environment-api:credentials:read` in their authorization settings, under the same condition.

To check read access for a given user or actor, run the probe from section 1 as that user: it calls `listCredentialVaultEntries()`, which needs `credential-vault:entries:read`.

---

## Troubleshooting

| Symptom | Cause | Remedy |
|---------|-------|--------|
| 403 when reading a credential | Actor or user lacks `credential-vault:entries:read` in IAM (HTTP request tasks before Phase 3: also `environment:roles:viewer`); a custom policy or policy boundary can remove what a default policy grants | Add the permission to the policy; check policy boundaries |
| 403 in a workflow although IAM is correct | Actor is not a service user and `credential-vault:entries:read` is not turned on under Secondary permissions in authorization settings (HTTP request tasks before Phase 3: also `environment-api:credentials:read`) | The actor turns on the permission themselves; an administrator cannot do it |
| Workflow suddenly fails to read a credential | The actor changed because someone else edited the workflow | Reassign the intended actor, or use a service user as actor |
| Credential can't be used although permissions are correct | Entry settings don't allow the consumer (section 4), or the actor or user is not the owner or listed under **Users with access** | Fix the entry settings |
| Module `@dynatrace-sdk/client-credential-vault` does not exist | SDK not available on the tenant | Stop; do not migrate the code (section 1) |
| Platform token returns 401 | Token lacks the required scope | Create a new platform token with the correct scopes; scopes cannot be changed on an existing token |

---

## References

- [Credential vault API (Classic, deprecated)](https://docs.dynatrace.com/docs/dynatrace-api/environment-api/credential-vault)
- [Platform Credential Vault API v1](https://docs.dynatrace.com/docs/dynatrace-api/platform-api/platform-credential-vault-v1)
- [Classic Environment v2 SDK: `credentialVaultClient` (deprecated)](https://developer.dynatrace.com/develop/sdks/client-classic-environment-v2/#credentialvaultclient)
- [Credential Vault SDK (`@dynatrace-sdk/client-credential-vault`)](https://developer.dynatrace.com/develop/sdks/client-credential-vault/)
