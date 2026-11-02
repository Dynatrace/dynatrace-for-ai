# Entity Selector Predicates

Reference for all valid predicates in the entity selector query language, used via the `/api/v2/entities` API.

Multiple predicates are combined with `,` (implicit AND):

```
type("SERVICE"),tag("env:prod"),mzName("Production"),healthState("UNHEALTHY")
```

Each section includes a **Semantic Dictionary Field** column that maps classic entity selector predicates to their corresponding fields in the Dynatrace Semantic Dictionary. These mappings help when migrating from classic entity-based queries to Grail/DQL-based workflows. Calls to ``fieldsSnapshot ...`` allow discovery of available enriched mass data fields or Smartscape Node attributes.

---

## Core / Identity

| Predicate | Example | Semantic Dictionary Field for Migration|
|---|---|---|
| `type` | `type("HOST")` | Not needed for migration, usually implicit through context. |
| `entityId` | `entityId("SERVICE-123ABC")` | Can not be migrated. |
| `entityName` | `entityName("my-service")` | Often enriched on mass data with context specific naming. Examples `host.name`, `dt.host_group.id`, `k8s.*.name`. |
| `entityName.equals` and others | `entityName.equals("my-service")` | See `entityName`, suffix implies type of comparison. |

---

## Management Zone

| Predicate | Aliases | Semantic Dictionary Field |
|---|---|---|
| `mzId` | `managementZoneId` |  |
| `mzName` | `managementZoneName`, `mz` |  |
| `mzName.startsWith` |  |

> **Note:** In Grail, management zones are replaced by ownership and permission models. Can not appear in DQL queries, only directly in query constructs against classic APIs.

---

## Tags

| Predicate | Example | Semantic Dictionary Field |
|---|---|---|
| `tag` | `tag("env:prod")`, `tag("owner:team-a")` |  |

> **Note:** See [mass-data-filtering-strategy.md](mass-data-filtering-strategy.md) for how to resolve tag filter conditions.

---

## Health State

| Predicate | Allowed Values | Semantic Dictionary Field |
|---|---|---|
| `healthState` | `HEALTHY`, `UNHEALTHY` | `availability.state` |

---

## Timestamps

Each supports `.lte`, `.lt`, `.gte`, `.gt` operators. Predicates based on entity lifetime need to be translated to Smartscape Node queries with equivalent filters on ``lifetime``.

| Predicate | Example | Semantic Dictionary Field |
|---|---|---|
| `firstSeenTms` | `firstSeenTms.gte(1609459200000)` | `lifetime` (start component) |
| `lastExecutionTms` | `lastExecutionTms.lte(1609459200000)` | `lastExecutionTimestamp` |
| `modificationTms` | `modificationTms.gt(1609459200000)` | `modificationTimestamp` |
| `creationTimestamp` | `creationTimestamp.gte(1609459200000)` | `creationTimestamp` |
| `resourceCreationTimestamp` | `resourceCreationTimestamp.lt(1609459200000)` | `resourceCreationTimestamp` |
| `resourceDeletionTimestamp` | `resourceDeletionTimestamp.exists` | `resourceDeletionTimestamp` |

> **Note:** `lifetime` is a complex record containing start/end timestamps representing when the entity was first and last seen.

---

## Modifiers / Wrappers

| Predicate | Example | Description | Semantic Dictionary Field |
|---|---|---|---|
| `not(...)` | `not(type("HOST"))` | Negates the wrapped predicate | — (query-level operator) |
| `caseSensitive(...)` | `caseSensitive(entityName.equals("MyService"))` | Makes string matching case-sensitive | — (query-level operator) |
| `deletedEntities.include` | `deletedEntities.include` | Include soft-deleted entities | `resourceDeletionTimestamp` |
| `deletedEntities.exclude` | `deletedEntities.exclude` | Exclude soft-deleted entities | `resourceDeletionTimestamp` |

---

## Filter Predicates

These accept an optional `.exists` variant (e.g., `ipAddress.exists`).

| Predicate | Aliases | Semantic Dictionary Field |
|---|---|---|
| `ipAddress` | `dt.ip_addresses` | `dt.ip_addresses` / `host.ip` |
| `osType` | — | `os.type` / `osType` |
| `osDetail` | — | `osDetail` |
| `monitoringMode` | — | `dt.agent.monitoring_mode` / `monitoringMode` |
| `hostVirtualizationType` | — | `hypervisor.type` / `hypervisorType` |
| `networkZone` | — | `dt.network_zone.id` / `networkZone` |
| `processType` | — | `processType` |
| `serviceType` | — | `serviceType` |
| `cloudType` | — | `cloud.provider` / `cloudType` |
| `paasVendorType` | — | `paasVendorType` |
| `databaseVendor` | — | `db.system` / `databaseVendor` |
| `databaseName` | — | `db.namespace` / `databaseName` |
| `softwareTechnologies` | `softwareTechnologies.type`, `dt.software_techs`, `dt.software_techs.type` | `softwareTechnologies` |
| `softwareTechnologies.version` | `dt.software_techs.version` | `softwareTechnologies` |
| `kubernetesClusterId` | — | `k8s.cluster.uid` / `kubernetesClusterId` |
| `kubernetesClusterName` | — | `k8s.cluster.name` |
| `kubernetesLabels` | — | `k8s.workload.label.__attribute_name__` / `kubernetesLabels` |
| `kubernetesApiMonitoringState` | — | — (no direct mapping) |
| `kubernetesDistribution` | — | `kubernetesDistribution` |
| `namespaceName` | — | `k8s.namespace.name` / `namespaceName` |
| `containerNames` | `containerName` | `container.name` / `containerNames` |
| `azureSubscriptionUuid` | — | `azure.subscription` / `azureSubscriptionUuid` |
| `azureTenantUuid` | — | `azure.tenant.id` / `azureTenantUuid` |
| `azureManagementGroupUuid` | — | `azure.management_group` / `azureManagementGroupUuid` |
| `azureResourceId` | — | `azure.resource.id` / `azureResourceId` |
| `azureSiteName` | — | `azure.site_name` / `azureSiteName` |
| `state` | — | `state` / `availability.state` |
| `autoInjection` | `globalHookingStatus` | `autoInjection` |
| `applicationInjectionType` | — | `applicationType` |
| `standalone` | — | `standalone` |
| `isContainerDeployment` | — | `isDockerized` / `containerizationType` |
| `requestAttribute` | — | `request_attribute.__attribute_name__` |
| `affectedBySecurityProblem` | — | `vulnerability.*` |
| `exposingSecurityProblem` | — | `vulnerability.*` |
| `reachableThroughSecurityProblem` | — | `vulnerability.*` |
| `queueName` | — | `messaging.destination.name` / `queueName` |
| `queueVendorName` | — | `messaging.system` / `queueVendorName` |
| `queueDestinationType` | — | `messaging.destination.kind` / `queueDestinationType` |
| `cloudNetworkServiceType` | — | `cloudNetworkServiceType` |
| `customDeviceSource` | — | — (no direct mapping) |
| `pluginsRunning` | — | `pluginsRunning` |
| `installerVersion` | — | `dt.agent.installer_version` / `installerVersion` |
| `filesystemType` | — | `storage.disk.fstype` |
| `remoteDiskId` | — | `disk.remote_disk_id` / `remoteDiskId` |

> **Note:** Where two fields are listed (e.g., `os.type` / `osType`), the first is the normalized Semantic Dictionary resource field and the second is the classic shared entity property. Use the normalized field for new Grail/DQL queries and the shared field when querying the classic entity model.

---

## AppSec

| Predicate | Allowed Values | Semantic Dictionary Field |
|---|---|---|
| `coveredByAppSec` | `SUPPORTED`, `MONITORED`, `EXCLUDED` | — (no direct mapping) |
| `coveredByAppSecThirdParty` | `SUPPORTED`, `MONITORED`, `EXCLUDED` | — (no direct mapping) |
| `coveredByAppSecCodeLevel` | `SUPPORTED`, `MONITORED`, `EXCLUDED` | — (no direct mapping) |

> **Note:** AppSec coverage predicates do not have direct Semantic Dictionary equivalents. Related security data is available through `vulnerability.*` and `dt.security.*` signal fields.

---

## Releases

| Predicate | Aliases | Semantic Dictionary Field |
|---|---|---|
| `releasesVersion` | — | `deployment.release_version` / `releasesVersion` |
| `releasesVersion.exists` | — | `deployment.release_version` / `releasesVersion` |
| `releasesStage` | `releasesEnvironment` | `deployment.release_stage` / `releasesStage` |
| `releasesProduct` | `releasesApplication` | `deployment.release_product` / `releasesProduct` |
| `releasesBuildVersion` | — | `deployment.release_build_version` / `releasesBuildVersion` |

---

## Installer

| Predicate | Semantic Dictionary Field |
|---|---|
| `installerPotentialProblem` | `installerPotentialProblem` |
| `installerTrackedDownload` | `installerTrackedDownload` |
| `installerSupportAlert` | `installerSupportAlert` |

---

## Relationship Predicates

Syntax: `fromRelationships.<name>(<entitySelector>)` or `toRelationships.<name>(<entitySelector>)`

Example:

```
type("SERVICE"),fromRelationships.runsOn(type("HOST"),entityName.contains("prod"))
```

The Semantic Dictionary defines normalized relationship types in the `relationships` group of `source/model/dt.entities/model_group_dt_entities.yaml`. Classic entity selector relationship names map to these normalized types as follows:

### Mapping to Semantic Dictionary Relationship Types

| Classic Relationship Name | Semantic Dictionary Relationship |
|---|---|
| `runsOn` / `runsOnHost` / `runsOnResource` | `runs_on` / `runs` |
| `isProcessOf` | `runs` / `runs_on` |
| `calls` | `calls` / `called_by` |
| `manages` | `manages` / `managed_by` |
| `monitors` | `monitors` / `monitored_by` |
| `isChildOf` | `child_of` / `parent_of` |
| `isPartOf` | `part_of` / `consists_of` |
| `isSameAs` | `same_as` |
| `isGroupOf` / `isMemberOf` | `groups` / `group_of` |
| `isInstanceOf` | `instance_of` / `instantiates` |
| `isDatastoreOf` | `serves` / `served_by` |
| `isBalancedBy` | `balanced_by` / `balances` |
| `isAccessibleBy` | `accessible_by` / `can_access` |
| `belongsTo` | `belongs_to` / `contains` |
| `isStepOf` | `part_of` / `consists_of` |
| `sendsToQueue` | `sends_to` / `receives_from` |
| `receivesFromQueue` / `listensOnQueue` | `receives_from` / `sends_to` |
| `indirectlySendsToQueue` | `indirectly_sends_to` |
| `indirectlyReceivesFromQueue` | `indirectly_receives_from` |
| `propagatesTo` | `propagates_to` / `propagated_from` |
| `isHostGroupOf` | `groups` / `group_of` |
| `isServiceOf` / `isServiceOfProcessGroup` | `serves` / `served_by` |

### All Classic Relationship Names (Reference)

| Relationship Name | Relationship Name |
|---|---|
| `isProcessOf` | `runsOn` |
| `runsOnHost` | `runsOnResource` |
| `calls` | `manages` |
| `monitors` | `isChildOf` |
| `isPartOf` | `isSameAs` |
| `isGroupOf` | `isMemberOf` |
| `isInstanceOf` | `isDatastoreOf` |
| `isSiteOf` | `isBalancedBy` |
| `isServiceOf` | `isServiceOfProcessGroup` |
| `isApplicationMethodOf` | `isApplicationMethodOfGroup` |
| `isServiceMethodOf` | `isServiceMethodOfService` |
| `isNetworkClientOf` | `isNetworkClientOfProcessGroup` |
| `isNetworkClientOfHost` | `isDiskOf` |
| `isEbsVolumeOf` | `isNetworkInterfaceOf` |
| `isDockerContainerOf` | `isDockerContainerOfPg` |
| `isHostOfContainer` | `isAccessibleBy` |
| `belongsTo` | `isStepOf` |
| `sendsToQueue` | `receivesFromQueue` |
| `listensOnQueue` | `indirectlySendsToQueue` |
| `indirectlyReceivesFromQueue` | `isHostGroupOf` |
| `isClusterOfNode` | `isClusterOfHost` |
| `isClusterOfNamespace` | `isClusterOfPg` |
| `isClusterOfCa` | `isClusterOfCai` |
| `isClusterOfService` | `isClusterOfKubernetesSvc` |
| `isNodeOfHost` | `isNamespaceOfCa` |
| `isNamespaceOfCai` | `isNamespaceOfPg` |
| `isNamespaceOfService` | `isNamespaceOfKubernetesSvc` |
| `isKubernetesSvcOfCai` | `isKubernetesSvcOfCa` |
| `isPgOfCa` | `isPgOfCai` |
| `isPgOfCg` | `isPgAppOf` |
| `isCgiOfHost` | `isCgiOfCa` |
| `isCgiOfCai` | `isCgiOfCluster` |
| `isMainPgiOfCgi` | `isPgiOfCgi` |
| `isApplicationOfSyntheticTest` | `isLocatedIn` |
| `isServedByDcrumService` | `hostsComputeNode` |
| `propagatesTo` | `isUserActionOf` |
| `isOpenstackAvZoneOf` | `isMemberOfScalingGroup` |
| `isProcessRunningOpenstackVm` | `isCfFoundationOfHost` |
| `isBoshDeploymentOfHost` | `isSystemProfileOf` |
| `isSoftwareComponentOfPgi` | `isRuntimeComponentOf` |
| `isRuntimeOfPgi` | `runsOnProcessGroupInstance` |
| `isAzrServiceBusNamespaceOfQueue` | `isAzrServiceBusNamespaceOfTopic` |
| `isAzrEventHubNamespaceOfEventHub` | `isAzrStorageAccountOfAzrEventHub` |
| `isAzrAppServicePlanOf` | `isAzrSubscriptionOfCredentials` |
| `isAzrSubscriptionOfAzrTenant` | `isAzrSubscriptionOfAzrMgmtGroup` |
| `isAzrMgmtGroupOfAzrTenant` | `isAzrSqlServerOfElasticPool` |
| `isAzrSqlServerOfDatabase` | `isAzrSQLDatabaseOfElasticPool` |
| `candidateTalksWith` | `talksWithCandidate` |

> **Note:** The Semantic Dictionary normalizes the many specific classic relationship names (e.g., `isClusterOfNode`, `isNamespaceOfPg`) into a smaller set of generic relationship types (e.g., `cluster_of`, `contains`). The classic names remain valid for entity selector queries against the v2 API.

---

## Postfix Operators

All string predicates support these operators. Numeric and timestamp predicates support comparison operators.

| Operator | Type | Description |
|---|---|---|
| *(bare)* | string | Default equals match |
| `.equals` | string | Exact match |
| `.contains` | string | Substring match |
| `.startsWith` | string | Prefix match |
| `.in` | string | Multi-value list, e.g. `entityName.in("a","b","c")` |
| `.exists` | any | Field existence check |
| `.gte` | numeric / timestamp | Greater than or equal |
| `.gt` | numeric / timestamp | Greater than |
| `.lte` | numeric / timestamp | Less than or equal |
| `.lt` | numeric / timestamp | Less than |
| `.include` | modifier | Inclusion modifier |
| `.exclude` | modifier | Exclusion modifier |
