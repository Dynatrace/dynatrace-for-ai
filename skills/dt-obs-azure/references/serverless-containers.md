# Azure Serverless & Container Workloads

Monitor Azure Functions, App Service, AKS infrastructure layer, and Container Apps.

## Table of Contents

- [Serverless & Container Entity Types](#serverless--container-entity-types)
- [Azure Functions Monitoring](#azure-functions-monitoring)
- [App Service Monitoring](#app-service-monitoring)
- [AKS Infrastructure Monitoring](#aks-infrastructure-monitoring)
- [Container Apps](#container-apps)
- [Cross-Service Analysis](#cross-service-analysis)

## Serverless & Container Entity Types

All these types support the standard discovery pattern: `smartscapeNodes "<TYPE>" | fields name, id, azure.subscription, azure.resource.group, azure.location, ...`

| Entity Type | Description |
|---|---|
| `AZURE_MICROSOFT_WEB_SITES` | App Service and Function Apps (differentiate via `kind`) |
| `AZURE_MICROSOFT_WEB_SERVERFARMS` | App Service Plans |
| `AZURE_MICROSOFT_WEB_SITES_FUNCTIONS` | Individual functions within a Function App |
| `AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS` | AKS clusters |
| `AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS_AGENTPOOLS` | AKS agent pools |
| `AZURE_MICROSOFT_CONTAINERREGISTRY_REGISTRIES` | Azure Container Registry |
| `AZURE_MICROSOFT_APP_CONTAINERAPPS` | Azure Container Apps |
| `AZURE_MICROSOFT_APP_MANAGEDENVIRONMENTS` | Container Apps managed environments |
| `AZURE_MICROSOFT_APP_JOBS` | Container Apps jobs |

## Azure Functions Monitoring

Function Apps are `AZURE_MICROSOFT_WEB_SITES` entities where the `kind` field contains `functionapp`. Filter using `azure.object` to separate them from App Service.

List all Function Apps:

```dql
smartscapeNodes "AZURE_MICROSOFT_WEB_SITES"
| parse azure.object, "JSON:azjson"
| fieldsAdd kind = azjson[configuration][kind]
| filter contains(kind, "functionapp")
| fieldsAdd state = azjson[configuration][properties][state],
    defaultHostName = azjson[configuration][properties][defaultHostName],
    runtime = azjson[configuration][properties][siteConfig][linuxFxVersion],
    httpsOnly = azjson[configuration][properties][httpsOnly]
| fields name, kind, state, defaultHostName, runtime, httpsOnly,
    azure.resource.group, azure.location
```

Find Function Apps on consumption (Dynamic) plans vs. dedicated plans:

```dql
smartscapeNodes "AZURE_MICROSOFT_WEB_SITES"
| parse azure.object, "JSON:azjson"
| fieldsAdd kind = azjson[configuration][kind],
    sku = azjson[configuration][properties][sku]
| filter contains(kind, "functionapp")
| summarize func_count = count(), by: {sku}
| sort func_count desc
```

Find Function Apps and their App Service Plans (Web Site → Server Farm traversal):

```dql
smartscapeNodes "AZURE_MICROSOFT_WEB_SITES"
| parse azure.object, "JSON:azjson"
| fieldsAdd kind = azjson[configuration][kind]
| filter contains(kind, "functionapp")
| traverse "*", "AZURE_MICROSOFT_WEB_SERVERFARMS"
| fieldsAdd sourceId = dt.traverse.history[0][id]
| fieldsAdd planName = name, planId = id
| lookup [smartscapeNodes "AZURE_MICROSOFT_WEB_SITES" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "app."
| fields app.name, planName, planId
```

List individual functions within Function Apps (Function → Web Site backward traversal):

```dql-template
smartscapeNodes "AZURE_MICROSOFT_WEB_SITES"
| filter name == "<FUNCTION_APP_NAME>"
| traverse "*", "AZURE_MICROSOFT_WEB_SITES_FUNCTIONS", direction:backward
| fields name, id, azure.resource.group
```

Find Function Apps with VNet integration (check for virtual network subnet ID):

```dql
smartscapeNodes "AZURE_MICROSOFT_WEB_SITES"
| parse azure.object, "JSON:azjson"
| fieldsAdd kind = azjson[configuration][kind],
    vnetSubnetId = azjson[configuration][properties][virtualNetworkSubnetId]
| filter contains(kind, "functionapp")
| filter isNotNull(vnetSubnetId)
| fields name, vnetSubnetId, azure.resource.group, azure.location
```

## App Service Monitoring

List all App Service web apps (exclude Function Apps):

```dql
smartscapeNodes "AZURE_MICROSOFT_WEB_SITES"
| parse azure.object, "JSON:azjson"
| fieldsAdd kind = azjson[configuration][kind]
| filter not(contains(kind, "functionapp"))
| fieldsAdd state = azjson[configuration][properties][state],
    defaultHostName = azjson[configuration][properties][defaultHostName],
    runtime = azjson[configuration][properties][siteConfig][linuxFxVersion],
    httpsOnly = azjson[configuration][properties][httpsOnly]
| fields name, kind, state, defaultHostName, runtime, httpsOnly,
    azure.resource.group, azure.location
```

List all App Service Plans with SKU details:

```dql
smartscapeNodes "AZURE_MICROSOFT_WEB_SERVERFARMS"
| parse azure.object, "JSON:azjson"
| fieldsAdd skuName = azjson[configuration][sku][name],
    skuTier = azjson[configuration][sku][tier],
    skuCapacity = azjson[configuration][sku][capacity]
| fields name, skuName, skuTier, skuCapacity, azure.resource.group, azure.location
```

Find stopped App Service apps:

```dql
smartscapeNodes "AZURE_MICROSOFT_WEB_SITES"
| parse azure.object, "JSON:azjson"
| fieldsAdd state = azjson[configuration][properties][state]
| filter state == "Stopped"
| fields name, state, azure.resource.group, azure.location
```

Find apps with public network access enabled:

```dql
smartscapeNodes "AZURE_MICROSOFT_WEB_SITES"
| parse azure.object, "JSON:azjson"
| fieldsAdd publicAccess = azjson[configuration][properties][publicNetworkAccess],
    httpsOnly = azjson[configuration][properties][httpsOnly]
| fields name, publicAccess, httpsOnly, azure.resource.group, azure.location
```

## AKS Infrastructure Monitoring

> **Note:** This section covers the Azure infrastructure layer of AKS (clusters, agent pools, VMSS backing). For Kubernetes workload-level monitoring (pods, deployments, services), use the **dt-obs-kubernetes** skill.

List all AKS clusters with configuration:

```dql
smartscapeNodes "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS"
| parse azure.object, "JSON:azjson"
| fieldsAdd k8sVersion = azjson[configuration][properties][kubernetesVersion],
    currentVersion = azjson[configuration][properties][currentKubernetesVersion],
    powerState = azjson[configuration][properties][powerState][code],
    networkPlugin = azjson[configuration][properties][networkProfile][networkPlugin],
    rbac = azjson[configuration][properties][enableRBAC],
    fqdn = azjson[configuration][properties][fqdn],
    skuTier = azjson[configuration][sku][tier]
| fields name, k8sVersion, currentVersion, powerState, networkPlugin, rbac, fqdn, skuTier,
    azure.resource.group, azure.location
```

Find AKS cluster networking configuration:

```dql
smartscapeNodes "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS"
| parse azure.object, "JSON:azjson"
| fieldsAdd networkPlugin = azjson[configuration][properties][networkProfile][networkPlugin],
    loadBalancerSku = azjson[configuration][properties][networkProfile][loadBalancerSku],
    podCidr = azjson[configuration][properties][networkProfile][podCidr],
    serviceCidr = azjson[configuration][properties][networkProfile][serviceCidr],
    nodeResourceGroup = azjson[configuration][properties][nodeResourceGroup]
| fields name, networkPlugin, loadBalancerSku, podCidr, serviceCidr, nodeResourceGroup
```

Find agent pools for an AKS cluster (Agent Pool → AKS backward traversal):

```dql-template
smartscapeNodes "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS"
| filter name == "<AKS_CLUSTER_NAME>"
| traverse "*", "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS_AGENTPOOLS", direction:backward
| fields name, id, azure.resource.group
```

Find VMSS backing an AKS cluster (VMSS → AKS backward traversal):

```dql-template
smartscapeNodes "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS"
| filter name == "<AKS_CLUSTER_NAME>"
| traverse "*", "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS", direction:backward
| parse azure.object, "JSON:azjson"
| fieldsAdd vmSize = azjson[configuration][sku][name],
    capacity = azjson[configuration][sku][capacity],
    poolName = `tags:azure`[`aks-managed-poolName`]
| fields name, vmSize, capacity, poolName, azure.resource.group
```

Find AKS clusters with deallocated power state:

```dql
smartscapeNodes "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS"
| parse azure.object, "JSON:azjson"
| fieldsAdd powerState = azjson[configuration][properties][powerState][code]
| filter powerState == "Deallocated"
| fields name, powerState, azure.resource.group, azure.location
```

List Container Registries:

```dql
smartscapeNodes "AZURE_MICROSOFT_CONTAINERREGISTRY_REGISTRIES"
| fields name, id, azure.resource.group, azure.location, azure.provisioning_state
```

## Container Apps

List all Container Apps with running status:

```dql
smartscapeNodes "AZURE_MICROSOFT_APP_CONTAINERAPPS"
| parse azure.object, "JSON:azjson"
| fieldsAdd runningStatus = azjson[configuration][properties][runningStatus],
    provisioningState = azjson[configuration][properties][provisioningState],
    latestRevision = azjson[configuration][properties][latestReadyRevisionName]
| fields name, runningStatus, provisioningState, latestRevision,
    azure.resource.group, azure.location
```

Find Container App scaling configuration:

```dql
smartscapeNodes "AZURE_MICROSOFT_APP_CONTAINERAPPS"
| parse azure.object, "JSON:azjson"
| fieldsAdd minReplicas = azjson[configuration][properties][template][scale][minReplicas],
    maxReplicas = azjson[configuration][properties][template][scale][maxReplicas]
| fields name, minReplicas, maxReplicas, azure.resource.group, azure.location
```

Find Container App container images:

```dql
smartscapeNodes "AZURE_MICROSOFT_APP_CONTAINERAPPS"
| parse azure.object, "JSON:azjson"
| fieldsAdd containers = azjson[configuration][properties][template][containers]
| expand containers
| fieldsAdd image = containers[image],
    cpu = containers[resources][cpu],
    memory = containers[resources][memory]
| fields name, image, cpu, memory, azure.resource.group
```

Find Container App ingress configuration:

```dql
smartscapeNodes "AZURE_MICROSOFT_APP_CONTAINERAPPS"
| parse azure.object, "JSON:azjson"
| fieldsAdd ingressFqdn = azjson[configuration][properties][configuration][ingress][fqdn],
    external = azjson[configuration][properties][configuration][ingress][external],
    targetPort = azjson[configuration][properties][configuration][ingress][targetPort]
| fields name, ingressFqdn, external, targetPort, azure.resource.group
```

Find Container Apps and their managed environments (Container App → Managed Environment traversal):

```dql
smartscapeNodes "AZURE_MICROSOFT_APP_CONTAINERAPPS"
| traverse "*", "AZURE_MICROSOFT_APP_MANAGEDENVIRONMENTS"
| fieldsAdd sourceId = dt.traverse.history[0][id]
| fieldsAdd envName = name, envId = id
| lookup [smartscapeNodes "AZURE_MICROSOFT_APP_CONTAINERAPPS" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "app."
| fields app.name, envName, envId
```

List Container App managed environments:

```dql
smartscapeNodes "AZURE_MICROSOFT_APP_MANAGEDENVIRONMENTS"
| fields name, id, azure.resource.group, azure.location, azure.provisioning_state
```

List Container App jobs:

```dql
smartscapeNodes "AZURE_MICROSOFT_APP_JOBS"
| fields name, id, azure.resource.group, azure.location, azure.provisioning_state
```

## Cross-Service Analysis

Count all serverless and container resources by type:

```dql
smartscapeNodes "AZURE_MICROSOFT_WEB_SITES", "AZURE_MICROSOFT_WEB_SERVERFARMS",
    "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS",
    "AZURE_MICROSOFT_APP_CONTAINERAPPS", "AZURE_MICROSOFT_CONTAINERREGISTRY_REGISTRIES"
| summarize count = count(), by: {type}
| sort count desc
```

Count all serverless and container resources by region:

```dql
smartscapeNodes "AZURE_MICROSOFT_WEB_SITES", "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS",
    "AZURE_MICROSOFT_APP_CONTAINERAPPS"
| summarize count = count(), by: {type, azure.location}
| sort azure.location, count desc
```

Find all resources in a specific resource group:

```dql-template
smartscapeNodes "AZURE_MICROSOFT_WEB_SITES", "AZURE_MICROSOFT_WEB_SERVERFARMS",
    "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS",
    "AZURE_MICROSOFT_APP_CONTAINERAPPS", "AZURE_MICROSOFT_APP_MANAGEDENVIRONMENTS"
| filter azure.resource.group == "<RESOURCE_GROUP>"
| fields type, name, azure.location, azure.provisioning_state
```
