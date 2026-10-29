---
name: dt-obs-azure
description: Azure cloud resources including VMs, VMSS, SQL Database, Storage, AKS, App Service, Functions, VNet networking, load balancers, Event Hubs, Container Apps, and Key Vault. Monitor Azure infrastructure, analyze resource usage, audit security posture, and manage organizational hierarchy across subscriptions and resource groups.
license: Apache-2.0
---

# Azure Cloud Infrastructure

Monitor and analyze Azure resources using Dynatrace Smartscape and DQL. Query Azure services, audit security, manage organizational hierarchy, and plan capacity across your Azure infrastructure.

## When to Use This Skill

Use this skill when the user needs to work with Azure resources in Dynatrace. Load the reference file for the task type:

| Task | File to load |
|---|---|
| Inventory and topology queries | (no additional file — use core patterns below) |
| Query Azure metric timeseries (CPU, latency, throughput) | Load `references/metrics-performance.md` |
| VNet topology, subnets, NSGs, public IPs, VPN, peering | Load `references/vnet-networking-security.md` |
| Azure SQL, Cosmos DB, PostgreSQL, Redis investigation | Load `references/database-monitoring.md` |
| Functions, App Service, AKS infrastructure, Container Apps | Load `references/serverless-containers.md` |
| Azure LB, Application Gateway, Front Door, API Management | Load `references/load-balancing-api.md` |
| WAF rule analysis, false-positive investigation | Load `references/load-balancing-api.md` |
| Event Hubs, Service Bus, Event Grid | Load `references/messaging-integration.md` |
| Storage Accounts, Blob, File, Queue, Table | Load `references/storage-monitoring.md` |
| Unattached resources, tag compliance, lifecycle | Load `references/resource-management.md` |
| Cost savings, unused resources, SKU analysis | Load `references/cost-optimization.md` |
| Capacity headroom, VMSS scaling, quotas | Load `references/capacity-planning.md` |
| Security audit, encryption, public access, Key Vault | Load `references/security-compliance.md` |
| NSG rule analysis (0.0.0.0/0, open ports) | Load `references/security-compliance.md` |
| Storage account encryption/public access audit | Load `references/security-compliance.md` |
| Cost allocation, chargeback, ownership | Load `references/resource-ownership.md` |
| Determine orchestration context (AKS, VMSS, standalone) | Load `references/workload-detection.md` |

---

## Core Concepts

### Entity Types

Azure resources use the `AZURE_*` prefix and can be queried using the `smartscapeNodes` function. All Azure entities are automatically discovered and modeled in Dynatrace Smartscape. Entity type names are derived from the ARM resource provider path: `/Microsoft.Compute/virtualMachines` becomes `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES`. Sub-resources append with underscores: `/Microsoft.Sql/servers/databases` becomes `AZURE_MICROSOFT_SQL_SERVERS_DATABASES`.

**Compute:** `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES`, `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS`, `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS_VIRTUALMACHINES`, `AZURE_MICROSOFT_COMPUTE_DISKS`, `AZURE_MICROSOFT_COMPUTE_SSHPUBLICKEYS`, `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES_EXTENSIONS`
**Networking:** `AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS`, `AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS`, `AZURE_MICROSOFT_NETWORK_NETWORKSECURITYGROUPS`, `AZURE_MICROSOFT_NETWORK_PUBLICIPADDRESSES`, `AZURE_MICROSOFT_NETWORK_NETWORKINTERFACES`, `AZURE_MICROSOFT_NETWORK_LOADBALANCERS`, `AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS`, `AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKGATEWAYS`, `AZURE_MICROSOFT_NETWORK_CONNECTIONS`, `AZURE_MICROSOFT_NETWORK_EXPRESSROUTECIRCUITS`
**Database:** `AZURE_MICROSOFT_SQL_SERVERS`, `AZURE_MICROSOFT_SQL_SERVERS_DATABASES`, `AZURE_MICROSOFT_CACHE_REDIS`, `AZURE_MICROSOFT_CACHE_REDISENTERPRISE`, `AZURE_MICROSOFT_DOCUMENTDB_DATABASEACCOUNTS`
**Storage:** `AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS`, `AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS_BLOBSERVICES_CONTAINERS`, `AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS_FILESERVICES_SHARES`, `AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS_QUEUESERVICES_QUEUES`, `AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS_TABLESERVICES_TABLES`
**Kubernetes/Containers:** `AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS`, `AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS_AGENTPOOLS`, `AZURE_MICROSOFT_CONTAINERREGISTRY_REGISTRIES`, `AZURE_MICROSOFT_APP_CONTAINERAPPS`, `AZURE_MICROSOFT_APP_MANAGEDENVIRONMENTS`, `AZURE_MICROSOFT_APP_JOBS`
**App Service:** `AZURE_MICROSOFT_WEB_SITES`, `AZURE_MICROSOFT_WEB_SERVERFARMS`, `AZURE_MICROSOFT_WEB_SITES_FUNCTIONS`
**Messaging:** `AZURE_MICROSOFT_EVENTHUB_NAMESPACES`, `AZURE_MICROSOFT_EVENTHUB_NAMESPACES_EVENTHUBS`, `AZURE_MICROSOFT_SERVICEBUS_NAMESPACES`, `AZURE_MICROSOFT_SERVICEBUS_NAMESPACES_QUEUES`, `AZURE_MICROSOFT_SERVICEBUS_NAMESPACES_TOPICS`, `AZURE_MICROSOFT_SERVICEBUS_NAMESPACES_TOPICS_SUBSCRIPTIONS`
**Security/Identity:** `AZURE_MICROSOFT_KEYVAULT_VAULTS`, `AZURE_MICROSOFT_MANAGEDIDENTITY_USERASSIGNEDIDENTITIES`
**Monitoring:** `AZURE_MICROSOFT_OPERATIONALINSIGHTS_WORKSPACES`, `AZURE_MICROSOFT_INSIGHTS_COMPONENTS`
**API Management:** `AZURE_MICROSOFT_APIMANAGEMENT_SERVICE`

### Azure Organizational Hierarchy

Azure organizes resources in a three-level hierarchy: **Tenant > Subscription > Resource Group**. Every resource belongs to exactly one resource group within one subscription. Use these fields to scope queries:

```dql-snippet
filter azure.subscription == "08b9810e-..."
```

```dql-snippet
filter azure.resource.group == "my-rg"
```

```dql-snippet
filter azure.location == "eastus"
```

Combine these filters for precise scoping:

```dql-template
smartscapeNodes "AZURE_*"
| filter azure.subscription == "<SUBSCRIPTION_ID>"
    and azure.resource.group == "<RESOURCE_GROUP>"
    and azure.location == "<REGION>"
| summarize count = count(), by: {type}
| sort count desc
```

To see the organizational breakdown across your environment:

```dql
smartscapeNodes "AZURE_*"
| summarize resource_count = count(), by: {azure.subscription, azure.resource.group}
| sort resource_count desc
```

### Common Azure Fields

All Azure entities include:
- `azure.subscription` — Azure subscription GUID
- `azure.resource.group` — Resource group name
- `azure.location` — Azure region (e.g., `eastus`, `polandcentral`)
- `azure.resourceType` — ARM resource type (e.g., `microsoft.compute/virtualmachines`)
- `azure.provisioning_state` — Provisioning state (e.g., `Succeeded`)
- `azure.object` — Full ARM resource JSON (see [Configuration Parsing](#configuration-parsing-with-azureobject))
- `cloud.provider` — Always `azure`
- `` `tags:azure` `` — Azure resource tags (use `` `tags:azure`[`key`] ``)

Some entity types also have:
- `azure.resourceId` — Full ARM resource ID (VMs and some others)
- `azure.resourceName` — Resource name (VMs and some others)
- `azure.availabilityZones` — Availability zone list (VMs)

### Relationship Types

Azure entity relationships can be traversed using `traverse`. The `dt.traverse.relationship` field is **not populated** for Azure entities, so you must use `"*"` as the relationship name in all traversal commands.

Key traversal pairs:
- **VM → Disks:** `traverse "*", "AZURE_MICROSOFT_COMPUTE_DISKS"`
- **VM → NICs:** `traverse "*", "AZURE_MICROSOFT_NETWORK_NETWORKINTERFACES"`
- **VM → VMSS:** `traverse "*", "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS"`
- **VM → Availability Zones:** `traverse "*", "AZURE_MICROSOFT_RESOURCES_LOCATIONS_AVAILABILITYZONES"`
- **VM ← Extensions:** `traverse "*", "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES_EXTENSIONS", direction:backward`
- **VMSS → AKS Clusters:** `traverse "*", "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS"`
- **VMSS → Subnets:** `traverse "*", "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS"`
- **VMSS → NSGs:** `traverse "*", "AZURE_MICROSOFT_NETWORK_NETWORKSECURITYGROUPS"`
- **VMSS → LB Backend Pools:** `traverse "*", "AZURE_MICROSOFT_NETWORK_LOADBALANCERS_BACKENDADDRESSPOOLS"`
- **Subnet → VNet:** `traverse "*", "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS"`
- **Subnet → NSG:** `traverse "*", "AZURE_MICROSOFT_NETWORK_NETWORKSECURITYGROUPS"`
- **Subnet ← VMSS:** `traverse "*", "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS", direction:backward`
- **NSG ← NICs:** `traverse "*", "AZURE_MICROSOFT_NETWORK_NETWORKINTERFACES", direction:backward`
- **NSG ← Subnets:** `traverse "*", "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS", direction:backward`
- **LB → Backend Pools:** `traverse "*", "AZURE_MICROSOFT_NETWORK_LOADBALANCERS_BACKENDADDRESSPOOLS"`
- **LB → Frontend IPs:** `traverse "*", "AZURE_MICROSOFT_NETWORK_LOADBALANCERS_FRONTENDIPCONFIGURATIONS"`
- **LB → LB Rules:** `traverse "*", "AZURE_MICROSOFT_NETWORK_LOADBALANCERS_LOADBALANCINGRULES"`
- **SQL Server ← SQL Databases:** `traverse "*", "AZURE_MICROSOFT_SQL_SERVERS_DATABASES", direction:backward`
- **Storage Account ← Blob Containers:** `traverse "*", "AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS_BLOBSERVICES_CONTAINERS", direction:backward`
- **Storage Account ← File Shares:** `traverse "*", "AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS_FILESERVICES_SHARES", direction:backward`
- **AKS ← VMSS:** `traverse "*", "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS", direction:backward`
- **AKS ← Agent Pools:** `traverse "*", "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS_AGENTPOOLS", direction:backward`
- **AKS ← NSGs:** `traverse "*", "AZURE_MICROSOFT_NETWORK_NETWORKSECURITYGROUPS", direction:backward`
- **AKS ← Public IPs:** `traverse "*", "AZURE_MICROSOFT_NETWORK_PUBLICIPADDRESSES", direction:backward`
- **AKS → Public IPs:** `traverse "*", "AZURE_MICROSOFT_NETWORK_PUBLICIPADDRESSES"`
- **Web Site → App Service Plan:** `traverse "*", "AZURE_MICROSOFT_WEB_SERVERFARMS"`
- **Web Site ← Functions:** `traverse "*", "AZURE_MICROSOFT_WEB_SITES_FUNCTIONS", direction:backward`
- **Container App → Managed Environment:** `traverse "*", "AZURE_MICROSOFT_APP_MANAGEDENVIRONMENTS"`
- **EventHub Namespace ← Event Hubs:** `traverse "*", "AZURE_MICROSOFT_EVENTHUB_NAMESPACES_EVENTHUBS", direction:backward`
- **ServiceBus Namespace ← Queues:** `traverse "*", "AZURE_MICROSOFT_SERVICEBUS_NAMESPACES_QUEUES", direction:backward`
- **ServiceBus Namespace ← Topics:** `traverse "*", "AZURE_MICROSOFT_SERVICEBUS_NAMESPACES_TOPICS", direction:backward`
- **ServiceBus Topic ← Subscriptions:** `traverse "*", "AZURE_MICROSOFT_SERVICEBUS_NAMESPACES_TOPICS_SUBSCRIPTIONS", direction:backward`
- Use `fieldsKeep:{field1, field2}` to carry fields through multi-hop traversals
- After a **single-hop** traverse, use `dt.traverse.history[0][id]` to get the source entity ID, then `lookup` to resolve the source entity name:
  ```dql-snippet
  | fieldsAdd sourceId = dt.traverse.history[0][id]
  | lookup [smartscapeNodes "SOURCE_TYPE" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "src."
  ```
- After **multi-hop** traversals, `dt.traverse.history[-N]` works for fields carried via `fieldsKeep`

### Azure Metric Naming Convention

Dynatrace ingests Azure Monitor metrics and exposes them using this naming pattern:

```
cloud.azure.<provider_namespace>.<resource_type>.<MetricName>
```

The `<provider_namespace>` uses underscores within the namespace (e.g., `microsoft_compute`) and `<resource_type>` is lowercase (e.g., `virtualmachines`). Hierarchy levels are dot-separated: `microsoft_sql.servers.databases`. `<MetricName>` is the Azure Monitor metric name.

**Examples:**

| Azure Monitor metric | Dynatrace metric key |
|---|---|
| VM `Percentage CPU` | `cloud.azure.microsoft_compute.virtualmachines.PercentageCPU` |
| SQL DB `cpu_percent` | `cloud.azure.microsoft_sql.servers.databases.cpu_percent` |
| Storage `Ingress` | `cloud.azure.microsoft_storage.storageaccounts.Ingress` |
| Event Hub `IncomingMessages` | `cloud.azure.microsoft_eventhub.namespaces.IncomingMessages` |
| Service Bus `IncomingMessages` | `cloud.azure.microsoft_servicebus.namespaces.IncomingMessages` |
| App Service `HttpResponseTime` | `cloud.azure.microsoft_web.sites.HttpResponseTime` |
| Load Balancer `ByteCount` | `cloud.azure.microsoft_network.loadbalancers.ByteCount` |
| AKS `node_cpu_usage_percentage` | `cloud.azure.microsoft_containerservice.managedclusters.node_cpu_usage_percentage` |
| Cosmos DB `TotalRequestUnits` | `cloud.azure.microsoft_documentdb.databaseaccounts.TotalRequestUnits` |
| Redis `serverLoad` | `cloud.azure.microsoft_cache.redis.serverLoad` |
| App Gateway `TotalRequests` | `cloud.azure.microsoft_network.applicationgateways.TotalRequests` |

To query a metric:

```dql-template
timeseries cpu = avg(cloud.azure.microsoft_compute.virtualmachines.PercentageCPU),
           by: {dt.smartscape_source.id},
  from: now()-1h
| limit 10
```

**Important:** Never refer to these as "Azure Monitor alerts" or "Azure Monitor metrics" in output. Dynatrace monitors Azure resources natively through its Azure integration — these are **Dynatrace metrics** ingested from Azure.

### Configuration Parsing with azure.object

The `azure.object` field contains the full ARM resource JSON. Parse it with the `azjson` alias:

```dql-snippet
parse azure.object, "JSON:azjson"
```

The JSON is wrapped in a `configuration` key:

```json
{
  "configuration": {
    "id": "<ARM resource ID>",
    "name": "<resource name>",
    "type": "<ARM resource type>",
    "location": "<region>",
    "sku": { ... },
    "properties": { ... },
    "zones": [...]
  },
  "tags": { ... }
}
```

Access patterns:
- Properties: `azjson[configuration][properties][field]`
- SKU: `azjson[configuration][sku][name]`
- Kind: `azjson[configuration][kind]`
- Zones: `azjson[configuration][zones]`
- Tags: read `` `tags:azure`[`key`] `` directly instead of parsing `azure.object`. It holds both top-level `tags` and AKS-managed `configuration.tags`

Common configuration fields by service:
- **VM:** `properties.hardwareProfile.vmSize`, `properties.storageProfile.imageReference.offer`, `properties.storageProfile.osDisk.osType`, `properties.extended.instanceView.powerState.displayStatus`
- **VMSS:** `sku.name` (VM size), `sku.capacity` (instance count), AKS system tags such as `` `tags:azure`[`aks-managed-poolName`] ``
- **NSG:** `properties.securityRules[]` (custom rules array), `properties.securityRules[].properties.direction`, `properties.securityRules[].properties.access`, `properties.securityRules[].properties.sourceAddressPrefix`
- **Storage Account:** `kind` (e.g., StorageV2), `sku.name`, `properties.accessTier`, `properties.supportsHttpsTrafficOnly`, `properties.allowBlobPublicAccess`, `properties.encryption.keySource`
- **SQL Server:** `properties.fullyQualifiedDomainName`, `properties.publicNetworkAccess`, `properties.minimalTlsVersion`
- **SQL Database:** `sku.name` (tier), `sku.capacity` (DTU/vCore), `properties.status`, `properties.zoneRedundant`
- **AKS:** `properties.kubernetesVersion`, `properties.powerState.code`, `properties.networkProfile.networkPlugin`, `properties.enableRBAC`
- **Web Site:** `kind` (e.g., `functionapp,linux`), `properties.state`, `properties.defaultHostName`, `properties.siteConfig.linuxFxVersion`
- **Container App:** `properties.runningStatus`, `properties.template.containers[].image`, `properties.template.scale.minReplicas`, `properties.template.scale.maxReplicas`
- **Event Hub Namespace:** `sku.name`, `properties.kafkaEnabled`, `properties.zoneRedundant`
- **Service Bus Namespace:** `sku.name` (Basic/Standard/Premium), `properties.zoneRedundant`, `properties.minimumTlsVersion`, `properties.publicNetworkAccess`, `properties.disableLocalAuth`, `properties.status`
- **Service Bus Queue:** `properties.maxSizeInMegabytes`, `properties.enablePartitioning`, `properties.deadLetteringOnMessageExpiration`, `properties.maxDeliveryCount`, `properties.lockDuration`, `properties.requiresDuplicateDetection`, `properties.status`
- **Key Vault:** `properties.enableRbacAuthorization`, `properties.enableSoftDelete`, `properties.publicNetworkAccess`
- **Redis:** `properties.sku.name`, `properties.hostName`, `properties.redisVersion`, `properties.enableNonSslPort`
- **Cosmos DB:** `kind` (e.g., GlobalDocumentDB), `properties.EnabledApiTypes`, `properties.consistencyPolicy.defaultConsistencyLevel`
- **Load Balancer:** `sku.name`, `` `tags:azure`[`aks-managed-cluster-name`] ``
- **App Gateway:** `properties.sku.name`, `properties.sku.tier`, `properties.operationalState`, `properties.webApplicationFirewallConfiguration.enabled`, `properties.webApplicationFirewallConfiguration.firewallMode` (Detection/Prevention), `properties.webApplicationFirewallConfiguration.ruleSetType`, `properties.webApplicationFirewallConfiguration.ruleSetVersion`, `properties.webApplicationFirewallConfiguration.disabledRuleGroups[]`, `properties.webApplicationFirewallConfiguration.exclusions[]`, `properties.firewallPolicy.id`

---

## Query Patterns

All Azure queries build on four core patterns. Master these and adapt them to any entity type.

### Pattern 1: Resource Discovery

List resources by type, filter by subscription/resource group/region/tags, summarize counts:

```dql-template
smartscapeNodes "AZURE_*"
| filter azure.subscription == "<SUBSCRIPTION_ID>" and azure.location == "<REGION>"
| summarize count = count(), by: {type}
| sort count desc
```

To list a specific type, replace `"AZURE_*"` with the entity type (e.g., `"AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES"`). Add `| fields name, azure.subscription, azure.resource.group, azure.location, ...` to select specific columns. Use `` `tags:azure`[`TagName`] `` for tag-based filtering.

### Pattern 2: Configuration Parsing

Parse `azure.object` JSON for detailed configuration fields:

```dql-template
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES"
| parse azure.object, "JSON:azjson"
| fieldsAdd vmSize = azjson[configuration][properties][hardwareProfile][vmSize],
            osType = azjson[configuration][properties][storageProfile][osDisk][osType]
| summarize vm_count = count(), by: {vmSize, osType, azure.location}
```

### Pattern 3: Relationship Traversal

Follow relationships between resources. Use `"*"` for the relationship name since Azure does not populate `dt.traverse.relationship`:

```dql-template
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS"
| parse azure.object, "JSON:azjson"
| fieldsAdd lbSku = azjson[configuration][sku][name]
| traverse "*", "AZURE_MICROSOFT_NETWORK_LOADBALANCERS_BACKENDADDRESSPOOLS", fieldsKeep:{lbSku, name, id}
| fieldsAdd backendPoolName = name
| traverse "*", "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS", direction:backward, fieldsKeep:{backendPoolName, id}
| fieldsAdd loadBalancerName = dt.traverse.history[-2][name],
            loadBalancerId = dt.traverse.history[-2][id],
            backendPoolId = dt.traverse.history[-1][id]
```

Key differences from AWS traversals:
- Always use `"*"` as the relationship name (relationship type names are empty for Azure)
- Azure relationships primarily follow a parent-child hierarchy: sub-resources link backward to parent resources
- AKS is a major relationship hub with backward links from VMSS, NSGs, LBs, Public IPs, Agent Pools, and Managed Identities

### Pattern 4: Tag-Based Ownership

Group resources by any tag for ownership/chargeback:

```dql-template
smartscapeNodes "AZURE_*"
| filter isNotNull(`tags:azure`[`<TAG_NAME>`])
| summarize resource_count = count(), by: {`tags:azure`[`<TAG_NAME>`], type}
| sort resource_count desc
```

Common Azure tags: `` `tags:azure`[`ACE:CREATED-BY`] ``, `` `tags:azure`[`dt_owner_email`] ``, `` `tags:azure`[`dt_owner_team`] ``, `` `tags:azure`[`project`] ``, `` `tags:azure`[`managed-by`] ``. Replace `"AZURE_*"` with a specific type to scope to one service.

Find untagged resources: `` | filter isNull(`tags:azure`) or toString(`tags:azure`) == "{}" ``

---

## Reference Guide

Load reference files for detailed queries when the core patterns above need service-specific adaptation.

| Reference | When to load | Key content |
|---|---|---|
| [vnet-networking-security.md](references/vnet-networking-security.md) | VNet topology, subnets, NSGs, public IPs, VPN, peering | VNet/subnet mapping, NSG blast radius, public IP detection |
| [database-monitoring.md](references/database-monitoring.md) | Azure SQL, Cosmos DB, Redis Cache | Service tier distribution, zone redundancy, public access checks |
| [serverless-containers.md](references/serverless-containers.md) | Functions, App Service, AKS infra, Container Apps | Runtime distribution, App Service Plan mapping, AKS node pools |
| [load-balancing-api.md](references/load-balancing-api.md) | Load Balancers, Application Gateways, API Management | LB backend pool traversal, App Gateway routing, APIM config |
| [messaging-integration.md](references/messaging-integration.md) | Event Hubs, Service Bus, Event Grid | Namespace inventory, Kafka enablement, throughput unit analysis |
| [storage-monitoring.md](references/storage-monitoring.md) | Storage Accounts, Blob, File, Queue, Table | SKU distribution, access tier, encryption audit, public access |
| [resource-management.md](references/resource-management.md) | Resource audits, tag compliance, lifecycle | Unattached disks, tag coverage, provisioning state analysis |
| [cost-optimization.md](references/cost-optimization.md) | Cost savings, unused resources, sizing | VM SKU analysis, unattached disks, deallocated VMs |
| [capacity-planning.md](references/capacity-planning.md) | Capacity analysis, scaling, utilization | VMSS headroom, subnet IP counts, AKS node pool sizing |
| [security-compliance.md](references/security-compliance.md) | Security audits, encryption, public access, Key Vault | NSG rule analysis, TLS version audit, public endpoint detection, encryption checks |
| [resource-ownership.md](references/resource-ownership.md) | Chargeback, ownership, cost allocation | Tag-based grouping, subscription/resource-group summaries |
| [workload-detection.md](references/workload-detection.md) | Determine orchestration context and resolution path | AKS node, VMSS member, standalone VM detection for blast radius analysis |
| [metrics-performance.md](references/metrics-performance.md) | Query metric timeseries for a specific resource | DQL timeseries patterns for VM, SQL, Storage, Event Hub, LB, App Service, AKS, Cosmos DB, Redis, App Gateway |

---

## Best Practices

### Query Optimization
1. Filter early by subscription, resource group, and region
2. Use specific entity types (avoid `"AZURE_*"` wildcards when possible)
3. Limit results with `| limit N` for exploration
4. Use `isNotNull()` checks before accessing nested fields

### Configuration Parsing
1. Always parse `azure.object` with JSON parser: `parse azure.object, "JSON:azjson"`
2. Use consistent field naming: `fieldsAdd configField = azjson[configuration][properties][field]`
3. Access SKU via `azjson[configuration][sku][name]` (not inside `properties`)
4. Check for null values after parsing — not all entity types have the same properties structure
5. Use `toString()` for complex nested objects

### Organizational Hierarchy
1. Always scope queries by `azure.subscription` in multi-subscription environments
2. Use `azure.resource.group` to narrow to a team or application boundary
3. Combine `azure.location` for region-specific analysis
4. Use `summarize ... by: {azure.subscription, azure.resource.group}` for organizational breakdowns

### Tagging Strategy
1. Use `` `tags:azure`[`key`] `` for filtering (backtick-quoted key names)
2. Filter `` isNull(`tags:azure`) or toString(`tags:azure`) == "{}" `` for untagged resources
3. Track tag coverage with summarize operations
4. Common ownership tags: `dt_owner_email`, `dt_owner_team`, `ACE:CREATED-BY`

---

## Limitations and Notes

### Smartscape Limitations
- Azure object configuration requires parsing with `parse azure.object, "JSON:azjson"`
- Azure metrics are available as Dynatrace metrics using the `cloud.azure.*` naming convention (see [Azure Metric Naming Convention](#azure-metric-naming-convention))
- Resource discovery depends on Azure integration configuration in Dynatrace
- Tag synchronization may have slight delays

### Relationship Traversal
- **Azure relationship type names are empty** — always use `"*"` as the relationship name in `traverse` commands
- Use `direction:backward` for reverse relationships (e.g., sub-resources to parent)
- Use `fieldsKeep` to maintain important fields through traversal
- Access traversal history with `dt.traverse.history[0][id]` for single-hop source entity ID; use `lookup` to resolve source entity name
- For multi-hop traversals, `dt.traverse.history[-N]` accesses fields carried via `fieldsKeep`
- Azure relationships primarily follow parent-child hierarchy patterns
- AKS is a major relationship hub — expect many backward relationships converging on AKS cluster entities

### AKS Coverage
- This skill covers AKS **infrastructure-layer** entities only (clusters, agent pools, VMSS, networking)
- For Kubernetes **workload-layer** observability (pods, deployments, services, namespaces), defer to the `dt-obs-kubernetes` skill

### General Tips
- Use `getNodeName()` for human-readable resource names
- Handle null values gracefully with `isNotNull()` and `isNull()`
- Combine subscription, resource group, and region filters for large environments
- Use `countDistinct()` for unique resource counts
- The `azure.resourceType` field is lowercase ARM format (e.g., `microsoft.compute/virtualmachines`) — useful for filtering but not for entity type matching
