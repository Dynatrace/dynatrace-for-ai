# VMware ActiveGate Integration

**Gen3 replacement**: VMware Extension

**Phase 2 required**: no

## What changes

Classic VMware monitoring via ActiveGate — configured through Settings 2.0 with vCenter/ESXi credentials — is removed in Phase 3. The VMware Extension replaces it. No functionality gaps have been documented at this stage: the extension provides the same monitoring coverage plus additional metrics, topology, logs, and insights.

## Prerequisites

- Customer has access credentials (username/password) for all monitored vCenter and/or ESXi endpoints
- At least one ActiveGate is running on a host with network access to the VMware APIs
- VMware Extension is installed and up to date — install or update via the Dynatrace Hub or Extension Manager

## Instructions

1. Verify the VMware Extension is installed and up to date — navigate to the Dynatrace Hub or Extension Manager and install or update to the latest version if needed.
2. Run the tracking query in the Validation section to determine whether the customer is using Classic VMware monitoring and/or has already adopted the VMware Extension.
3. If Classic VMware entities are detected (`type="VMware Classic"`), the customer needs to migrate.
4. Direct the customer to the **VMware migrator in the Infrastructure & Operations App**:
   - Open the Infrastructure & Operations App
   - Click **Add coverage** in the top-right corner (this option is only visible if Classic VMware monitoring is enabled **and** the VMware Extension is installed)
   - Follow the migration wizard to reconfigure VMware connections using the VMware Extension
5. For each monitored vCenter or ESXi endpoint, the customer must provide:
   - Hostname / IP address
   - Credentials (username and password)
   - The ActiveGate that has network access to the VMware API
6. Re-run the validation query to confirm the migration is complete.

## Customer actions

- Gather credentials for all monitored vCenter and ESXi endpoints
- Use the **Add coverage** option in the Infrastructure & Operations App to set up the VMware Extension connections
- Verify monitoring is active after migration
- Decommission classic ActiveGate VMware integration settings once confirmed

## Examples

### Tenant with only Classic VMware monitoring

Tracking query output:

| count | type |
|---|---|
| 0 | VMware by extension |
| 5 | VMware Classic |

→ Customer is fully on Classic. Full migration required.

### Tenant mid-migration

| count | type |
|---|---|
| 3 | VMware by extension |
| 5 | VMware Classic |

→ Partial migration. Customer has started but not completed the move to VMware Extension.

### Tenant fully migrated

| count | type |
|---|---|
| 5 | VMware by extension |
| 0 | VMware Classic |

→ No action needed.

## Outcome

After migration, all VMware datacenters must appear as `dt.entity.vmware:datacenter` entities (VMware by extension type). No `dt.entity.vmware_datacenter` entities (VMware Classic type) should remain active.

Output a status table based on the tracking query results:

| VMware by extension count | VMware Classic count | Status |
|---|---|---|
| \<number\> | \<number\> | \<Classic only / Mid-migration / Fully migrated\> |

## Validation

Run the following query to detect Classic vs. Extension VMware monitoring:

```dql-snippet
fetch dt.entity.vmware:datacenter
| summarize count()
| fieldsAdd type="VMware by extension"
| append [
  fetch dt.entity.vmware_datacenter
  | summarize count()
  | fieldsAdd type="VMware Classic"
]
```

- `type="VMware by extension"` — VMware Extension entities (3rd gen)
- `type="VMware Classic"` — Classic ActiveGate VMware entities (2nd gen, removed in Phase 3)

Migration is complete when:

- `type="VMware Classic"` count is 0
- If VMware monitoring is configured, `type="VMware by extension"` count is > 0

## References

- [VMware (remote monitoring) extension](https://docs.dynatrace.com/docs/observe/infrastructure-observability/extensions/vmware-remote-monitoring) — Dynatrace docs
