# Workload Detection Reference

Identify how an Azure VM or VMSS is orchestrated. Run these detection queries during problem analysis to determine which orchestration system manages the affected resource — this determines the correct resolution path.

## Table of Contents

- [Overview](#overview)
- [1. Load Balancer Detection](#1-load-balancer-detection)
- [2. VMSS Detection](#2-vmss-detection)
- [3. AKS Node Detection](#3-aks-node-detection)
- [4. Standalone VM](#4-standalone-vm)

## Overview

Azure VMs and VMSS instances can be managed by different orchestration systems, each requiring a different resolution approach. Run the detection queries below in order to identify the workload pattern before following a resolution path.

**Detection Hierarchy:**

Run detections in this order — stop at the first match:

1. **Load Balancer / Application Gateway** — is the resource behind a load balancer?
2. **VMSS membership** — is the VM part of a Virtual Machine Scale Set?
3. **AKS node** — is the VMSS managed by AKS?
4. **Standalone VM** — none of the above

**Workload Pattern Summary**

| Indicator | Workload Pattern | Resolution Path |
|---|---|---|
| `aks-managed-poolName` tag present on VMSS | AKS node | Cordon + drain via kubectl; node pool autoscaler handles replacement |
| Part of VMSS (no AKS tags) | VMSS member | VMSS handles replacement via scaling rules |
| Behind Load Balancer / App Gateway | Load balanced | Shift traffic before remediation |
| None of the above | Standalone VM | Direct remediation (restart, resize, replace) |

Replace `<WORKLOAD_VM_ENTITY_ID>` with the Dynatrace entity ID of the affected VM (e.g., `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES-2B0D33F11CE649F4`).

---

## 1. Load Balancer Detection

Determine if the VM is behind an Azure Load Balancer. VMs connect to LBs through NICs → Backend Address Pools → Load Balancers.

**Check if VM's VMSS is in a Load Balancer backend pool:**

```dql-template
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES"
| filter id == toSmartscapeId("<WORKLOAD_VM_ENTITY_ID>")
| traverse "*", "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS"
| traverse "*", "AZURE_MICROSOFT_NETWORK_LOADBALANCERS_BACKENDADDRESSPOOLS"
| fields name, id, azure.resource.group
```

**Find the Load Balancer for the backend pool:**

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS"
| traverse "*", "AZURE_MICROSOFT_NETWORK_LOADBALANCERS_BACKENDADDRESSPOOLS"
| fields name, id, azure.resource.group
```

**Find the VM's subnet (via VMSS, for network context):**

> **Note:** Azure Application Gateways do not have direct Smartscape relationships to subnets or VMs. This query identifies the subnet a VMSS-backed VM belongs to. To confirm App Gateway involvement, check the App Gateway's backend pool configuration separately (see `references/load-balancing-api.md`).

```dql-template
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES"
| filter id == toSmartscapeId("<WORKLOAD_VM_ENTITY_ID>")
| traverse "*", "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS"
| traverse "*", "AZURE_MICROSOFT_NETWORK_VIRTUALNETWORKS_SUBNETS"
| fields name, id, azure.resource.group
```

**If results returned:** The VM is part of a VMSS connected to a subnet. Cross-reference the subnet with load balancer backend pools and Application Gateway configurations to determine if traffic routing is involved.

Identify the Load Balancer SKU and AKS association (if any):

```dql
smartscapeNodes "AZURE_MICROSOFT_NETWORK_LOADBALANCERS"
| parse azure.object, "JSON:azjson"
| fieldsAdd skuName = azjson[configuration][sku][name]
| fieldsAdd aksCluster = azjson[tags][`aks-managed-cluster-name`]
| fields name, skuName, aksCluster, azure.resource.group, azure.location
```

---

## 2. VMSS Detection

Determine if the VM is part of a Virtual Machine Scale Set.

**Check VMSS membership:**

```dql-template
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES"
| filter id == toSmartscapeId("<WORKLOAD_VM_ENTITY_ID>")
| traverse "*", "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS"
| parse azure.object, "JSON:azjson"
| fieldsAdd vmSize = azjson[configuration][sku][name],
            capacity = azjson[configuration][sku][capacity]
| fields name, id, vmSize, capacity, azure.resource.group
```

**If results returned:** The VM is part of a VMSS. Record the VMSS name, current capacity, and VM size. Check if it is AKS-managed (next section).

**If no results:** The VM is standalone — skip to [Section 4](#4-standalone-vm).

Check VMSS-to-AKS association to distinguish generic VMSS from AKS node pools:

```dql
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS"
| parse azure.object, "JSON:azjson"
| fieldsAdd aksPoolName = azjson[configuration][tags][`aks-managed-poolName`],
            aksOrchestrator = azjson[configuration][tags][`aks-managed-orchestrator`]
| filter isNotNull(aksPoolName)
| fields name, id, aksPoolName, aksOrchestrator, azure.resource.group
```

---

## 3. AKS Node Detection

Detect whether the VMSS is an AKS node pool. AKS-managed VMSS instances carry specific tags that identify them.

**Key AKS tags on VMSS:**

| Tag | Description | Example |
|---|---|---|
| `aks-managed-poolName` | AKS node pool name | `spotnodes` |
| `aks-managed-orchestrator` | Kubernetes version | `Kubernetes:1.33.7` |
| `aks-managed-cluster-name` | AKS cluster name (on LB) | `aks-parser-dev` |

**Step 1 — Detect AKS tags on the VMSS:**

```dql-template
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES"
| filter id == toSmartscapeId("<WORKLOAD_VM_ENTITY_ID>")
| traverse "*", "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS"
| parse azure.object, "JSON:azjson"
| fieldsAdd aksPoolName = azjson[configuration][tags][`aks-managed-poolName`],
            aksOrchestrator = azjson[configuration][tags][`aks-managed-orchestrator`]
| filter isNotNull(aksPoolName)
| fields name, id, aksPoolName, aksOrchestrator, azure.resource.group
```

**Step 2 — Find the AKS cluster entity:**

```dql
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS"
| traverse "*", "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS"
| parse azure.object, "JSON:azjson"
| fieldsAdd k8sVersion = azjson[configuration][properties][kubernetesVersion],
            powerState = azjson[configuration][properties][powerState][code]
| fields name, id, k8sVersion, powerState, azure.resource.group, azure.location
```

**Step 3 — Check AKS agent pool details:**

```dql
smartscapeNodes "AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS_AGENTPOOLS"
| parse azure.object, "JSON:azjson"
| fieldsAdd vmSize = azjson[configuration][vmSize],
            nodeCount = azjson[configuration][count],
            minCount = azjson[configuration][minCount],
            maxCount = azjson[configuration][maxCount],
            enableAutoScaling = azjson[configuration][enableAutoScaling],
            mode = azjson[configuration][mode]
| fields name, vmSize, nodeCount, minCount, maxCount, enableAutoScaling, mode
```

**Record:** AKS cluster name, node pool name, Kubernetes version, and autoscaler configuration — needed for resolution guidance (e.g., cordon/drain via kubectl, scale the node pool, or rely on cluster autoscaler for replacement).

---

## 4. Standalone VM

If none of the above detection queries return results, the VM is standalone — not part of a VMSS, not behind a load balancer, and not AKS-managed.

**Gather VM details for direct remediation:**

```dql-template
smartscapeNodes "AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES"
| filter id == toSmartscapeId("<WORKLOAD_VM_ENTITY_ID>")
| parse azure.object, "JSON:azjson"
| fieldsAdd vmSize = azjson[configuration][properties][hardwareProfile][vmSize],
            powerState = azjson[configuration][properties][extended][instanceView][powerState][displayStatus],
            osType = azjson[configuration][properties][storageProfile][osDisk][osType],
            provisioningState = azjson[configuration][properties][provisioningState]
| fields name, id, vmSize, powerState, osType, provisioningState,
         azure.resource.group, azure.location, azure.subscription
```

**Resolution options for standalone VMs:**

- **Restart:** Restart the VM directly via Azure portal or CLI
- **Resize:** Change VM SKU if resource saturation is the issue
- **Replace:** Redeploy the VM if it is in a failed state
