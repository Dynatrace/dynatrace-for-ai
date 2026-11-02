# CloudFoundry ActiveGate Integration

<!-- Jira: none -->

**Gen3 replacement**: CloudFoundry Extension

**Phase 2 required**: no

## What changes

Classic CloudFoundry monitoring via ActiveGate — configured through Settings > Cloud and Virtualization > Cloud Foundry with CF API credentials — is removed in Phase 3. The CloudFoundry Extension replaces it. The extension monitors via the CF API and provides richer entity modeling: organizations, spaces, apps, routes, and services each become first-class Dynatrace entities.

## Prerequisites

- Customer has the CF API endpoint URL, authentication endpoint, and credentials (username/password with `cloud_controller.admin_read_only` and `scim.read` permissions) for all monitored CloudFoundry foundations
- At least one ActiveGate with network access to the CloudFoundry API
- CloudFoundry Extension is installed and up to date — install or update via the Dynatrace Hub or Extension Manager

## Instructions

1. Verify the CloudFoundry Extension is installed and up to date — navigate to the Dynatrace Hub or Extension Manager and install or update to the latest version if needed.
2. Run the tracking queries in the Validation section to determine whether the customer is using Classic CloudFoundry monitoring and/or has already adopted the CloudFoundry Extension.
3. If Classic CF foundations are detected (`type="CloudFoundry Classic"`), the customer needs to migrate.
4. Direct the customer to configure the CloudFoundry Extension in the Extension Manager:
   - Open the Dynatrace Hub or Extension Manager
   - Find the CloudFoundry Extension and open its monitoring configuration
   - Add a new endpoint with: CF API URL, authentication endpoint, username, and password
   - Select the ActiveGate that has network access to the CF API
5. Verify monitoring is active by re-running the validation queries to confirm extension entities appear.
6. Once extension monitoring is confirmed, decommission the classic configuration in **Settings > Cloud and Virtualization > Cloud Foundry**.

## Customer actions

- Gather CF API URL, authentication endpoint, and credentials for all monitored CloudFoundry foundations
- Configure the CloudFoundry Extension via Extension Manager for each foundation
- Verify monitoring is active after migration
- Decommission classic ActiveGate CloudFoundry integration settings once confirmed

## Examples

### Tenant with only Classic CloudFoundry monitoring

Tracking query output:

| count | type |
|---|---|
| 0 | CloudFoundry by extension |
| 3 | CloudFoundry Classic |

→ Customer is fully on Classic. Full migration required.

### Tenant mid-migration

| count | type |
|---|---|
| 2 | CloudFoundry by extension |
| 1 | CloudFoundry Classic |

→ Partial migration. Customer has started but not completed the move to CloudFoundry Extension.

### Tenant fully migrated

| count | type |
|---|---|
| 3 | CloudFoundry by extension |
| 0 | CloudFoundry Classic |

→ No action needed.

## Outcome

After migration, all CloudFoundry foundations must appear as `dt.entity.dt:cloudfoundry_foundation` entities (CloudFoundry by extension type). No `dt.entity.cf_foundation` entities (CloudFoundry Classic type) should remain active.

Output a status table based on the tracking query results:

| CloudFoundry by extension count | CloudFoundry Classic count | Status |
|---|---|---|
| \<number\> | \<number\> | \<Classic only / Mid-migration / Fully migrated\> |

## Validation

Run these two queries separately. If the extension entity type is not registered (extension not installed), the extension query will return an error — treat that as count = 0.

**Query 1 — CloudFoundry Classic foundations:**

```dql-snippet
fetch dt.entity.cf_foundation
| summarize count = count()
| fieldsAdd type = "CloudFoundry Classic"
```

**Query 2 — CloudFoundry Extension foundations:**

```dql-snippet
fetch dt.entity.dt:cloudfoundry_foundation
| summarize count = count()
| fieldsAdd type = "CloudFoundry by extension"
```

- `type="CloudFoundry by extension"` — CloudFoundry Extension entities (3rd gen)
- `type="CloudFoundry Classic"` — Classic ActiveGate CloudFoundry entities (2nd gen, removed in Phase 3)

Migration is complete when:

- CloudFoundry Classic count is 0
- If CloudFoundry monitoring is configured, CloudFoundry by extension count is > 0

## References

- [Cloud Foundry extension](https://docs.dynatrace.com/docs/observe/infrastructure-observability/extensions/cloudfoundry) — Dynatrace docs
- [Connect your Cloud Foundry foundations with Dynatrace](https://docs.dynatrace.com/docs/setup-and-configuration/setup-on-container-platforms/cloud-foundry/connect-your-cloud-foundry-foundations-to-dynatrace) — Classic setup docs
