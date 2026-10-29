# Azure Resource Management & Optimization

Analyze Azure resource usage, identify optimization opportunities, and manage resource tagging across subscriptions and resource groups.

## Table of Contents

- [Resource Inventory](#resource-inventory)
- [Tag Compliance](#tag-compliance)
- [Resource Lifecycle](#resource-lifecycle)
- [Regional & Resource Group Distribution](#regional--resource-group-distribution)
- [Storage & Security Resources](#storage--security-resources)

## Resource Inventory

Count all Azure resources by type:

```dql
smartscapeNodes "AZURE_*"
| summarize resource_count = count(), by: {type}
| sort resource_count desc
```

View resource distribution across subscriptions:

```dql
smartscapeNodes "AZURE_*"
| summarize resource_count = count(), by: {azure.subscription, azure.location}
| sort resource_count desc
```

Find resource types spanning multiple regions:

```dql
smartscapeNodes "AZURE_*"
| summarize
    region_count = countDistinct(azure.location),
    total_resources = count(),
    by: {type}
| filter region_count > 1
| sort region_count desc
```

## Tag Compliance

Find completely untagged resources:

```dql
smartscapeNodes "AZURE_*"
| filter isNull(`tags:azure`) or toString(`tags:azure`) == "{}"
| fields type, name, id, azure.subscription, azure.resource.group, azure.location
```

Find resources missing a specific required tag:

```dql-template
smartscapeNodes "AZURE_*"
| filter isNull(`tags:azure`[`<TAG_NAME>`]) or `tags:azure`[`<TAG_NAME>`] == ""
| summarize count = count(), by: {type, azure.subscription}
```

Calculate tag coverage percentages across resource types:

```dql
smartscapeNodes "AZURE_*"
| fieldsAdd has_owner_tag = if(isNotNull(`tags:azure`[`dt_owner_email`]), 1)
| fieldsAdd has_env_tag = if(isNotNull(`tags:azure`[`Environment`]), 1)

| summarize
    total = count(),
    with_env = sum(has_env_tag),
    with_owner = sum(has_owner_tag),
  by: { type }
| fieldsAdd
    env_coverage_pct = (with_env * 100.0) / total,
    owner_coverage_pct = (with_owner * 100.0) / total
| sort env_coverage_pct asc
```

Find resources by tag value:

```dql-template
smartscapeNodes "AZURE_*"
| filter `tags:azure`[`<TAG_NAME>`] == "<TAG_VALUE>"
| summarize count = count(), by: {type, azure.location}
```

Find resources by naming convention:

```dql-template
smartscapeNodes "AZURE_*"
| filter matchesPhrase(name, "<SEARCH_TERM>")
| fields type, name, id, azure.location, azure.resource.group, `tags:azure`[`Environment`]
```

## Resource Lifecycle

Detect deleted resources:

```dql
smartscapeNodes "AZURE_*"
| filter cloud.acquisitionStatus == "DELETED"
| fields type, name, id, azure.subscription, azure.resource.group, azure.location
```

Find resources with acquisition issues:

```dql
smartscapeNodes "AZURE_*"
| filter cloud.acquisitionStatus != "OK"
| fields type, name, id, cloud.acquisitionStatus, azure.subscription
```

Find unattached managed disks:

```dql
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_DISKS"
| parse azure.object, "JSON:azjson"
| fieldsAdd diskState = azjson[configuration][properties][diskState]
| filter diskState == "Unattached"
| fields name, id, azure.resource.group, azure.location, azure.subscription
```

Find unassociated public IPs:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_PUBLICIPADDRESSES"
| parse azure.object, "JSON:azjson"
| fieldsAdd ipConfig = azjson[configuration][properties][ipConfiguration]
| filter isNull(ipConfig)
| fields name, id, azure.resource.group, azure.location, azure.subscription
```

## Regional & Resource Group Distribution

View resources by region:

```dql
smartscapeNodes "AZURE_*"
| summarize resource_count = count(), by: {azure.location}
| sort resource_count desc
```

Count resources per resource group:

```dql
smartscapeNodes "AZURE_*"
| summarize resource_count = count(), by: {azure.resource.group, type}
| sort resource_count desc
```

## Storage & Security Resources

Count storage services:

```dql
smartscapeNodes "AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS",
    "AZURE_MICROSOFT_COMPUTE_DISKS",
    "AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS_BLOBSERVICES_CONTAINERS"
| summarize count = count(), by: {type, azure.location}
| sort count desc
```

Count security resources:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_NETWORKSECURITYGROUPS",
    "AZURE_MICROSOFT_KEYVAULT_VAULTS",
    "AZURE_MICROSOFT_MANAGEDIDENTITY_USERASSIGNEDIDENTITIES"
| summarize count = count(), by: {type}
| sort count desc
```

List storage accounts:

```dql
smartscapeNodes "AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS"
| fields name, azure.subscription, azure.resource.group, azure.location, id
```

List managed disks:

```dql
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_DISKS"
| fields name, id, azure.resource.group, azure.location, azure.subscription
```
