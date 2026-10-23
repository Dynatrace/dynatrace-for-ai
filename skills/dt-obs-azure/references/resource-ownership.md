# Azure Resource Ownership & Chargeback

Track resource ownership and enable cost allocation across teams using Azure resource tags, subscriptions, and resource groups.

## Table of Contents

- [Tag-Based Ownership Pattern](#tag-based-ownership-pattern)
- [Common Ownership Tags](#common-ownership-tags)
- [Service-Specific Ownership](#service-specific-ownership)
- [Multi-Subscription Resource Summary](#multi-subscription-resource-summary)

## Tag-Based Ownership Pattern

All ownership queries follow the same pattern — filter by a tag, then summarize by that tag and a grouping dimension:

```dql-template
smartscapeNodes "AZURE_*"
| filter isNotNull(`tags:azure`[`<TAG_NAME>`])
| summarize resource_count = count(), by: {`tags:azure`[`<TAG_NAME>`], type}
| sort resource_count desc
```

Replace `<TAG_NAME>` with any tag from the table below. Replace `type` with `azure.location`, `azure.subscription`, or `azure.resource.group` for alternative groupings. Replace `"AZURE_*"` with a specific entity type to scope to one service.

## Common Ownership Tags

| Tag | Use case | Typical values |
|---|---|---|
| `dt_owner_email` | Individual accountability | Email address |
| `dt_owner_team` | Team-level allocation | Team names |
| `ACE:CREATED-BY` | Resource creator tracking | Email address |
| `project` | Project-based grouping | Project identifiers (e.g., `azure-demo`) |
| `managed-by` | Management tool tracking | Tool names (e.g., `dynatrace`) |
| `CostCenter` | Financial chargeback | Cost center codes |
| `Environment` | Environment segmentation | `production`, `staging`, `dev` |

## Service-Specific Ownership

To scope ownership queries to a specific Azure service, replace `"AZURE_*"` with the entity type:

| Entity type | Example use case |
|---|---|
| `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES` | VM costs by department/team |
| `AZURE_MICROSOFT_WEB_SITES` | App Service / Functions costs by application |
| `AZURE_MICROSOFT_SQL_SERVERS_DATABASES` | Database ownership tracking |
| `AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS` | AKS cluster ownership by business unit |
| `AZURE_MICROSOFT_COMPUTE_DISKS` | Disk costs by project |
| `AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS` | Storage account ownership by team |
| `AZURE_MICROSOFT_APP_CONTAINERAPPS` | Container App ownership by team |

For service-specific queries, you can also select detail fields instead of summarizing:

```dql
smartscapeNodes "AZURE_MICROSOFT_SQL_SERVERS_DATABASES"
| filter isNotNull(`tags:azure`[`dt_owner_email`])
| fields name, id, `tags:azure`[`dt_owner_email`], azure.resource.group, azure.location
```

Ownership by resource group (useful when tags are not consistently applied):

```dql
smartscapeNodes "AZURE_*"
| summarize resource_count = count(), by: {azure.resource.group, type}
| sort resource_count desc
| limit 50
```

## Multi-Subscription Resource Summary

Summarize resources across subscriptions (independent of tags):

```dql
smartscapeNodes "AZURE_*"
| summarize resource_count = count(), by: {azure.subscription, type}
| sort resource_count desc
| limit 50
```

Summarize resources by subscription and resource group:

```dql
smartscapeNodes "AZURE_*"
| summarize resource_count = count(), by: {azure.subscription, azure.resource.group}
| sort resource_count desc
| limit 50
```
