# Azure VNet Networking & Security

Monitor and troubleshoot Azure Virtual Network infrastructure, Network Security Groups, subnets, and connectivity.

## Table of Contents

- [VNet Discovery](#vnet-discovery)
- [NSG Analysis](#nsg-analysis)
- [Subnet & VM Distribution](#subnet--vm-distribution)
- [Internet-Facing Resources](#internet-facing-resources)
- [Network Infrastructure](#network-infrastructure)
- [Availability Zone Distribution](#availability-zone-distribution)

## VNet Discovery

List all VNets:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS"
| fields name, id, azure.subscription, azure.resource.group, azure.location,
    azure.provisioning_state
```

Get VNet address space:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS"
| parse azure.object, "JSON:azjson"
| fieldsAdd addressPrefixes = azjson[configuration][properties][addressSpace][addressPrefixes],
    ddosProtection = azjson[configuration][properties][enableDdosProtection]
| fields name, azure.resource.group, azure.location, addressPrefixes, ddosProtection
```

Get all subnets in a specific VNet via backward traversal (Subnet → VNet):

```dql-template
smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS"
| filter id == toSmartscapeId("<VNET_ENTITY_ID>")
| traverse "*", "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS", direction:backward
| fields name, id, azure.resource.group
```

Count resources connected to each VNet by type (via subnets):

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS"
| traverse "*", "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS"
| fieldsAdd vnetName = name
| lookup [
    smartscapeNodes "AZURE_MICROSOFT_NETWORK_NETWORKINTERFACES_IPCONFIGURATIONS"
    | traverse "*", "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS"
    | fields subnetId = id
  ], sourceField:id, lookupField:subnetId
| summarize resource_count = count(), by: {vnetName}
| sort resource_count desc
```

## NSG Analysis

List all NSGs with their associated resource counts:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_NETWORKSECURITYGROUPS"
| fields name, id, azure.resource.group, azure.location, azure.provisioning_state
```

Find subnets and their associated NSGs (Subnet → NSG forward traversal):

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS"
| traverse "*", "AZURE_MICROSOFT_NETWORK_NETWORKSECURITYGROUPS"
| fieldsAdd sourceId = dt.traverse.history[0][id]
| fieldsAdd nsgName = name, nsgId = id
| lookup [smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "src."
| fields src.name, nsgName, nsgId
```

Find NICs associated with a specific NSG (NIC → NSG backward on NSG):

```dql-template
smartscapeNodes "AZURE_MICROSOFT_NETWORK_NETWORKSECURITYGROUPS"
| filter id == toSmartscapeId("<NSG_ENTITY_ID>")
| traverse "*", "AZURE_MICROSOFT_NETWORK_NETWORKINTERFACES", direction:backward
| fields name, id, azure.resource.group
```

Find VMSS instances associated with an NSG (VMSS → NSG backward on NSG):

```dql-template
smartscapeNodes "AZURE_MICROSOFT_NETWORK_NETWORKSECURITYGROUPS"
| filter id == toSmartscapeId("<NSG_ENTITY_ID>")
| traverse "*", "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS", direction:backward
| fields name, id, azure.resource.group
```

Analyze NSG security rules from azure.object:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_NETWORKSECURITYGROUPS"
| parse azure.object, "JSON:azjson"
| fieldsAdd rules = azjson[configuration][properties][securityRules]
| expand rules
| fieldsAdd ruleName = rules[name],
    direction = rules[properties][direction],
    access = rules[properties][access],
    protocol = rules[properties][protocol],
    sourcePrefix = rules[properties][sourceAddressPrefix],
    destPrefix = rules[properties][destinationAddressPrefix],
    destPort = rules[properties][destinationPortRange],
    priority = rules[properties][priority]
| fields name, ruleName, direction, access, protocol, sourcePrefix, destPrefix, destPort, priority
| sort name, priority asc
```

Find NSGs with inbound rules allowing traffic from the internet:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_NETWORKSECURITYGROUPS"
| parse azure.object, "JSON:azjson"
| fieldsAdd rules = azjson[configuration][properties][securityRules]
| expand rules
| fieldsAdd ruleName = rules[name],
    direction = rules[properties][direction],
    access = rules[properties][access],
    sourcePrefix = rules[properties][sourceAddressPrefix],
    destPort = rules[properties][destinationPortRange],
    priority = rules[properties][priority]
| filter direction == "Inbound" AND access == "Allow"
| filter sourcePrefix == "*" OR sourcePrefix == "Internet" OR sourcePrefix == "0.0.0.0/0"
| fields name, ruleName, sourcePrefix, destPort, priority
| sort priority asc
```

## Subnet & VM Distribution

List all subnets with their parent VNet:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS"
| traverse "*", "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS"
| fieldsAdd sourceId = dt.traverse.history[0][id]
| fieldsAdd vnetName = name
| lookup [smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS" | fields name, azure.resource.group, id], sourceField: sourceId, lookupField: id, prefix: "src."
| fields src.name, vnetName, src.azure.resource.group
```

Count NIC IP configurations per subnet (approximation of VMs per subnet):

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS"
| traverse "*", "AZURE_MICROSOFT_NETWORK_NETWORKINTERFACES_IPCONFIGURATIONS", direction:backward
| fieldsAdd sourceId = dt.traverse.history[0][id]
| lookup [smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "src."
| summarize nic_count = count(), by: {src.name}
| sort nic_count desc
```

Count VMSS instances per subnet:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS"
| traverse "*", "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS", direction:backward
| fieldsAdd sourceId = dt.traverse.history[0][id]
| lookup [smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "src."
| summarize vmss_count = count(), by: {src.name}
| sort vmss_count desc
```

Find VMs in a specific VNet (VM → NIC → IP Config → Subnet → VNet chain):

```dql-template
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES"
| fieldsAdd vmName = name, vmId = id
| traverse "*", "AZURE_MICROSOFT_NETWORK_NETWORKINTERFACES", fieldsKeep:{vmName, vmId}
| traverse "*", "AZURE_MICROSOFT_NETWORK_NETWORKINTERFACES_IPCONFIGURATIONS", direction:backward, fieldsKeep:{vmName, vmId}
| traverse "*", "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS", fieldsKeep:{vmName, vmId}
| traverse "*", "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS", fieldsKeep:{vmName, vmId}
| filter name == "<VNET_NAME>"
| fields vmName, vmId
```

## Internet-Facing Resources

List all public IP addresses:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_PUBLICIPADDRESSES"
| fields name, id, azure.resource.group, azure.location, azure.provisioning_state
```

Find public IPs with their allocation method and assigned address:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_PUBLICIPADDRESSES"
| parse azure.object, "JSON:azjson"
| fieldsAdd ipAddress = azjson[configuration][properties][ipAddress],
    allocationMethod = azjson[configuration][properties][publicIPAllocationMethod],
    sku = azjson[configuration][sku][name]
| fields name, ipAddress, allocationMethod, sku, azure.resource.group, azure.location
```

Find VMs with public IPs (VM → NIC, then check NIC for public IP association):

```dql
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES"
| traverse "*", "AZURE_MICROSOFT_NETWORK_NETWORKINTERFACES"
| fieldsAdd sourceId = dt.traverse.history[0][id]
| parse azure.object, "JSON:azjson"
| fieldsAdd publicIpId = azjson[configuration][properties][ipConfigurations][0][properties][publicIPAddress][id]
| filter isNotNull(publicIpId)
| lookup [smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "vm."
| fields vm.name, vm.id, name, publicIpId
```

## Network Infrastructure

NAT gateways (if present):

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_NATGATEWAYS"
| fields name, id, azure.resource.group, azure.location
```

VPN gateways:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKGATEWAYS"
| parse azure.object, "JSON:azjson"
| fieldsAdd gatewayType = azjson[configuration][properties][gatewayType],
    vpnType = azjson[configuration][properties][vpnType],
    sku = azjson[configuration][properties][sku][name]
| fields name, gatewayType, vpnType, sku, azure.resource.group, azure.location
```

VPN connections:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_CONNECTIONS"
| parse azure.object, "JSON:azjson"
| fieldsAdd connectionType = azjson[configuration][properties][connectionType],
    connectionStatus = azjson[configuration][properties][connectionStatus]
| fields name, connectionType, connectionStatus, azure.resource.group, azure.location
```

ExpressRoute circuits:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_EXPRESSROUTECIRCUITS"
| parse azure.object, "JSON:azjson"
| fieldsAdd serviceProviderName = azjson[configuration][properties][serviceProviderProperties][serviceProviderName],
    bandwidthInMbps = azjson[configuration][properties][serviceProviderProperties][bandwidthInMbps],
    circuitProvisioningState = azjson[configuration][properties][circuitProvisioningState]
| fields name, serviceProviderName, bandwidthInMbps, circuitProvisioningState, azure.location
```

VNet peering connections (embedded in VNet azure.object):

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS"
| parse azure.object, "JSON:azjson"
| fieldsAdd peerings = azjson[configuration][properties][virtualNetworkPeerings]
| expand peerings
| fieldsAdd peeringName = peerings[name],
    peeringState = peerings[properties][peeringState],
    remoteVNetId = peerings[properties][remoteVirtualNetwork][id]
| filter isNotNull(peeringName)
| fields name, peeringName, peeringState, remoteVNetId
```

Network watchers:

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_NETWORKWATCHERS"
| fields name, id, azure.resource.group, azure.location, azure.provisioning_state
```

## Availability Zone Distribution

View VM distribution across availability zones:

```dql
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES"
| traverse "*", "AZURE_MICROSOFT_RESOURCES_LOCATIONS_AVAILABILITYZONES"
| fieldsAdd sourceId = dt.traverse.history[0][id]
| lookup [smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES" | fields name, azure.location, id], sourceField: sourceId, lookupField: id, prefix: "vm."
| fields vm.name, vm.azure.location, name
| sort vm.azure.location, name
```

Summarize VM count per availability zone:

```dql
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES"
| traverse "*", "AZURE_MICROSOFT_RESOURCES_LOCATIONS_AVAILABILITYZONES"
| summarize vm_count = count(), by: {name}
| sort vm_count desc
```

VMSS distribution across availability zones:

```dql
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS"
| traverse "*", "AZURE_MICROSOFT_RESOURCES_LOCATIONS_AVAILABILITYZONES"
| fieldsAdd sourceId = dt.traverse.history[0][id]
| lookup [smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS" | fields name, id], sourceField: sourceId, lookupField: id, prefix: "src."
| fields src.name, name
| sort name
```
