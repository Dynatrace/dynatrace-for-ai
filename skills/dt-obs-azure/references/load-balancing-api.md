# Azure Load Balancing & API Management

Monitor Azure Load Balancers, Application Gateways, and API Management services.

## Table of Contents

- [Load Balancing & API Entity Types](#load-balancing--api-entity-types)
- [Azure Load Balancer Topology Traversal](#azure-load-balancer-topology-traversal)
- [Application Gateway Configuration](#application-gateway-configuration)
- [WAF Configuration & Rule Analysis](#waf-configuration--rule-analysis)
  - [WAF Mode Detection](#waf-mode-detection)
  - [WAF-Enabled Gateway Inventory](#waf-enabled-gateway-inventory)
  - [WAF Rule Configuration](#waf-rule-configuration)
  - [Disabled Rule Groups](#disabled-rule-groups)
  - [WAF Exclusions](#waf-exclusions)
  - [Firewall Policy Association](#firewall-policy-association)
- [API Management](#api-management)
- [Security & Networking](#security--networking)
- [Cross-Service Analysis](#cross-service-analysis)

## Load Balancing & API Entity Types

All these types support the standard discovery pattern: `smartscapeNodes "<TYPE>" | fields name, id, azure.subscription, azure.resource.group, azure.location, ...`

| Entity Type | Description |
|---|---|
| `AZURE_MICROSOFT_NETWORK_LOADBALANCERS` | Azure Load Balancers (Standard and Basic SKU) |
| `AZURE_MICROSOFT_NETWORK_LOADBALANCERS_FRONTENDIPCONFIGURATIONS` | LB frontend IP configurations |
| `AZURE_MICROSOFT_NETWORK_LOADBALANCERS_BACKENDADDRESSPOOLS` | LB backend address pools |
| `AZURE_MICROSOFT_NETWORK_LOADBALANCERS_LOADBALANCINGRULES` | LB load balancing rules |
| `AZURE_MICROSOFT_NETWORK_LOADBALANCERS_OUTBOUNDRULES` | LB outbound rules |
| `AZURE_MICROSOFT_NETWORK_LOADBALANCERS_INBOUNDNATRULES` | LB inbound NAT rules |
| `AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS` | Application Gateways |
| `AZURE_MICROSOFT_APIMANAGEMENT_SERVICE` | API Management services |

## Azure Load Balancer Topology Traversal

### Complete LB → Backend Pool → VMSS Mapping

This is the most important query — maps load balancers through backend pools to the VMSS instances serving traffic:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS"
| parse azure.object, "JSON:azjson"
| fieldsAdd skuName = azjson[configuration][sku][name]
| traverse "*", "AZURE_MICROSOFT_NETWORK_LOADBALANCERS_BACKENDADDRESSPOOLS", fieldsKeep:{skuName, name, id}
| fieldsAdd poolName = name, poolId = id
| traverse "*", "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS", direction:backward, fieldsKeep:{poolName, poolId}
| fieldsAdd lbName = dt.traverse.history[-2][name],
    lbId = dt.traverse.history[-2][id],
    lbSku = dt.traverse.history[-2][skuName]
| fields lbName, lbSku, poolName, name, id, azure.resource.group
```

### Simpler Traversals

LB to frontend IP configurations:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS"
| traverse "*", "AZURE_MICROSOFT_NETWORK_LOADBALANCERS_FRONTENDIPCONFIGURATIONS"
| fieldsAdd sourceId = dt.traverse.history[0][id]
| lookup [smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "lb."
| fields lb.name, name, id, azure.resource.group
```

LB to backend address pools:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS"
| traverse "*", "AZURE_MICROSOFT_NETWORK_LOADBALANCERS_BACKENDADDRESSPOOLS"
| fieldsAdd sourceId = dt.traverse.history[0][id]
| lookup [smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "lb."
| fields lb.name, name, id
```

LB to load balancing rules:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS"
| traverse "*", "AZURE_MICROSOFT_NETWORK_LOADBALANCERS_LOADBALANCINGRULES"
| fieldsAdd sourceId = dt.traverse.history[0][id]
| lookup [smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "lb."
| fields lb.name, name, id
```

LB to outbound rules:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS"
| traverse "*", "AZURE_MICROSOFT_NETWORK_LOADBALANCERS_OUTBOUNDRULES"
| fieldsAdd sourceId = dt.traverse.history[0][id]
| lookup [smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "lb."
| fields lb.name, name, id
```

### LB to AKS Cluster Mapping

Find which AKS clusters a load balancer is associated with:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS"
| traverse "*", "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS"
| fieldsAdd sourceId = dt.traverse.history[0][id]
| lookup [smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "lb."
| fields lb.name, name, id, azure.resource.group
```

Identify AKS-managed load balancers via tags:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS"
| fieldsAdd aksCluster = `tags:azure`[`aks-managed-cluster-name`]
| filter isNotNull(aksCluster)
| fields name, aksCluster, azure.resource.group, azure.location
```

### Load Balancer Configuration

List all load balancers with SKU:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS"
| parse azure.object, "JSON:azjson"
| fieldsAdd skuName = azjson[configuration][sku][name]
| fields name, skuName, azure.resource.group, azure.location, azure.provisioning_state
```

## Application Gateway Configuration

List Application Gateways with configuration details:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd skuName = azjson[configuration][properties][sku][name],
    skuTier = azjson[configuration][properties][sku][tier],
    skuCapacity = azjson[configuration][properties][sku][capacity],
    operationalState = azjson[configuration][properties][operationalState],
    enableHttp2 = azjson[configuration][properties][enableHttp2]
| fields name, skuName, skuTier, skuCapacity, operationalState, enableHttp2,
    azure.resource.group, azure.location
```

Analyze Application Gateway backend pools:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd backendPools = azjson[configuration][properties][backendAddressPools]
| expand backendPools
| fieldsAdd poolName = backendPools[name]
| fields name, poolName, azure.resource.group
```

Analyze Application Gateway HTTP listeners:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd listeners = azjson[configuration][properties][httpListeners]
| expand listeners
| fieldsAdd listenerName = listeners[name],
    protocol = listeners[properties][protocol],
    hostName = listeners[properties][hostName]
| fields name, listenerName, protocol, hostName
```

Analyze Application Gateway routing rules:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd rules = azjson[configuration][properties][requestRoutingRules]
| expand rules
| fieldsAdd ruleName = rules[name],
    ruleType = rules[properties][ruleType],
    priority = rules[properties][priority]
| fields name, ruleName, ruleType, priority
| sort priority asc
```

Application Gateway sub-resource entities for fine-grained traversal:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS_BACKENDADDRESSPOOLS",
    "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS_HTTPLISTENERS",
    "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS_REQUESTROUTINGRULES",
    "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS_URLPATHMAPS",
    "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS_FRONTENDIPCONFIGURATIONS",
    "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS_FRONTENDPORTS"
| fields type, name, id, azure.resource.group
| sort type
```

## WAF Configuration & Rule Analysis

Queries for investigating Web Application Firewall configuration on Application Gateways. Essential during false-positive incident investigation.

### WAF Mode Detection

List WAF-enabled gateways with their mode (Detection vs Prevention):

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd wafEnabled = azjson[configuration][properties][webApplicationFirewallConfiguration][enabled],
    wafMode = azjson[configuration][properties][webApplicationFirewallConfiguration][firewallMode],
    skuTier = azjson[configuration][properties][sku][tier]
| filter wafEnabled == true
| fields name, wafMode, skuTier, azure.resource.group, azure.location
```

Find gateways in Detection mode only (logging but not blocking — common during rollout or after false-positive issues):

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd wafEnabled = azjson[configuration][properties][webApplicationFirewallConfiguration][enabled],
    wafMode = azjson[configuration][properties][webApplicationFirewallConfiguration][firewallMode]
| filter wafEnabled == true and wafMode == "Detection"
| fields name, wafMode, azure.resource.group, azure.location
```

### WAF-Enabled Gateway Inventory

Full inventory with SKU, WAF status, and rule set info:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd wafEnabled = azjson[configuration][properties][webApplicationFirewallConfiguration][enabled],
    wafMode = azjson[configuration][properties][webApplicationFirewallConfiguration][firewallMode],
    ruleSetType = azjson[configuration][properties][webApplicationFirewallConfiguration][ruleSetType],
    ruleSetVersion = azjson[configuration][properties][webApplicationFirewallConfiguration][ruleSetVersion],
    skuName = azjson[configuration][properties][sku][name],
    skuTier = azjson[configuration][properties][sku][tier]
| fields name, skuName, skuTier, wafEnabled, wafMode, ruleSetType, ruleSetVersion,
    azure.resource.group, azure.location
```

Find gateways with a WAF-capable SKU but WAF not enabled:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd wafEnabled = azjson[configuration][properties][webApplicationFirewallConfiguration][enabled],
    skuTier = azjson[configuration][properties][sku][tier]
| filter contains(toString(skuTier), "WAF") and wafEnabled != true
| fields name, skuTier, wafEnabled, azure.resource.group, azure.location
```

### WAF Rule Configuration

Inspect rule set type, version, and body inspection limits:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd wafEnabled = azjson[configuration][properties][webApplicationFirewallConfiguration][enabled],
    ruleSetType = azjson[configuration][properties][webApplicationFirewallConfiguration][ruleSetType],
    ruleSetVersion = azjson[configuration][properties][webApplicationFirewallConfiguration][ruleSetVersion],
    maxRequestBodySizeInKb = azjson[configuration][properties][webApplicationFirewallConfiguration][maxRequestBodySizeInKb],
    fileUploadLimitInMb = azjson[configuration][properties][webApplicationFirewallConfiguration][fileUploadLimitInMb],
    requestBodyCheck = azjson[configuration][properties][webApplicationFirewallConfiguration][requestBodyCheck]
| filter wafEnabled == true
| fields name, ruleSetType, ruleSetVersion, maxRequestBodySizeInKb, fileUploadLimitInMb, requestBodyCheck,
    azure.resource.group
```

Summarize rule set versions in use across all gateways:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd wafEnabled = azjson[configuration][properties][webApplicationFirewallConfiguration][enabled],
    ruleSetType = azjson[configuration][properties][webApplicationFirewallConfiguration][ruleSetType],
    ruleSetVersion = azjson[configuration][properties][webApplicationFirewallConfiguration][ruleSetVersion]
| filter wafEnabled == true
| summarize count = count(), by: {ruleSetType, ruleSetVersion}
| sort count desc
```

### Disabled Rule Groups

This is the most critical section for false-positive investigation. Disabled rule groups indicate rules that were turned off to avoid blocking legitimate traffic.

Expand disabled rule groups to show which rules are disabled per gateway:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd wafEnabled = azjson[configuration][properties][webApplicationFirewallConfiguration][enabled],
    disabledRuleGroups = azjson[configuration][properties][webApplicationFirewallConfiguration][disabledRuleGroups]
| filter wafEnabled == true
| expand disabledRuleGroups
| fieldsAdd ruleGroupName = disabledRuleGroups[ruleGroupName],
    rules = toString(disabledRuleGroups[rules])
| fields name, ruleGroupName, rules, azure.resource.group
```

Find gateways with no disabled rules (fully enforcing all rule groups):

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd wafEnabled = azjson[configuration][properties][webApplicationFirewallConfiguration][enabled],
    disabledRuleGroups = azjson[configuration][properties][webApplicationFirewallConfiguration][disabledRuleGroups]
| filter wafEnabled == true and (isnull(disabledRuleGroups) or arraySize(disabledRuleGroups) == 0)
| fields name, azure.resource.group, azure.location
```

> **Investigation tip:** Common false-positive rule groups include `REQUEST-942-APPLICATION-ATTACK-SQLI` (SQL injection) and `REQUEST-941-APPLICATION-ATTACK-XSS` (cross-site scripting). If these appear in `disabledRuleGroups`, the team likely encountered false positives from application payloads matching SQL/XSS patterns. Check whether exclusions (below) would be a more targeted fix than disabling entire rule groups.

### WAF Exclusions

Expand WAF exclusions to see which request attributes are excluded from rule evaluation:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd wafEnabled = azjson[configuration][properties][webApplicationFirewallConfiguration][enabled],
    exclusions = azjson[configuration][properties][webApplicationFirewallConfiguration][exclusions]
| filter wafEnabled == true
| expand exclusions
| fieldsAdd matchVariable = exclusions[matchVariable],
    selectorMatchOperator = exclusions[selectorMatchOperator],
    selector = exclusions[selector]
| fields name, matchVariable, selectorMatchOperator, selector, azure.resource.group
```

> **Note:** Common `matchVariable` values are `RequestHeaderNames`, `RequestCookieNames`, `RequestArgNames`, and `RequestBodyPostArgNames`. Exclusions are more targeted than disabling entire rule groups and are the preferred approach for handling false positives.

### Firewall Policy Association

Find gateways with a linked firewall policy (newer policy-based WAF configuration model):

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd firewallPolicyId = azjson[configuration][properties][firewallPolicy][id],
    wafEnabled = azjson[configuration][properties][webApplicationFirewallConfiguration][enabled]
| filter isNotNull(firewallPolicyId)
| fields name, firewallPolicyId, wafEnabled, azure.resource.group, azure.location
```

> **Note:** Azure supports two WAF configuration models: inline `webApplicationFirewallConfiguration` (classic) and linked `firewallPolicy` (newer). When a firewall policy is linked, rule configuration and exclusions are managed on the policy resource rather than inline on the gateway. The queries above inspect inline configuration; policy-based WAF requires querying the policy resource separately.

## API Management

List API Management services with configuration:

```dql
smartscapeNodes "AZURE_MICROSOFT_APIMANAGEMENT_SERVICE"
| parse azure.object, "JSON:azjson"
| fieldsAdd skuName = azjson[configuration][sku][name],
    skuCapacity = azjson[configuration][sku][capacity],
    gatewayUrl = azjson[configuration][properties][gatewayUrl],
    devPortalUrl = azjson[configuration][properties][developerPortalUrl],
    vnetType = azjson[configuration][properties][virtualNetworkType],
    platformVersion = azjson[configuration][properties][platformVersion]
| fields name, skuName, skuCapacity, gatewayUrl, devPortalUrl, vnetType, platformVersion,
    azure.resource.group, azure.location
```

Find API Management policies and subscriptions:

```dql
smartscapeNodes "AZURE_MICROSOFT_APIMANAGEMENT_SERVICE_POLICIES",
    "AZURE_MICROSOFT_APIMANAGEMENT_SERVICE_SUBSCRIPTIONS"
| fields type, name, id, azure.resource.group
```

## Security & Networking

Identify public vs. internal load balancers (check frontend IP configuration for public IP association):

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS"
| traverse "*", "AZURE_MICROSOFT_NETWORK_LOADBALANCERS_FRONTENDIPCONFIGURATIONS"
| fieldsAdd sourceId = dt.traverse.history[0][id]
| parse azure.object, "JSON:azjson"
| fieldsAdd publicIpId = azjson[configuration][properties][publicIPAddress][id],
    privateIp = azjson[configuration][properties][privateIPAddress]
| lookup [smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "lb."
| fieldsAdd lbType = if(isNotNull(publicIpId), "Public", else: "Internal")
| fields lb.name, name, lbType, publicIpId, privateIp
```

Find API Management services exposed without VNet integration:

```dql
smartscapeNodes "AZURE_MICROSOFT_APIMANAGEMENT_SERVICE"
| parse azure.object, "JSON:azjson"
| fieldsAdd vnetType = azjson[configuration][properties][virtualNetworkType]
| filter vnetType == "None"
| fields name, vnetType, azure.resource.group, azure.location
```

## Cross-Service Analysis

Count all load balancing and API resources by type:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS",
    "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS",
    "AZURE_MICROSOFT_APIMANAGEMENT_SERVICE"
| summarize count = count(), by: {type}
| sort count desc
```

Count load balancing resources by region:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS",
    "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS",
    "AZURE_MICROSOFT_APIMANAGEMENT_SERVICE"
| summarize count = count(), by: {type, azure.location}
| sort azure.location, count desc
```

Find all load balancing resources in a specific resource group:

```dql-template
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS",
    "AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS",
    "AZURE_MICROSOFT_APIMANAGEMENT_SERVICE"
| filter azure.resource.group == "<RESOURCE_GROUP>"
| fields type, name, azure.location, azure.provisioning_state
```
