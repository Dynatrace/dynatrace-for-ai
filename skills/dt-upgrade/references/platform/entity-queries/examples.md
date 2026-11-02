# Example Migrations

Use these examples as before/after templates.

Keep the same pattern when adding more examples:

1. input query
2. Smartscape translation sketch
3. notes about the mapping

## Contents

- [Contents](#contents)
- [Example 001: `classicEntitySelector` filter without relationships](#example-001-classicentityselector-filter-without-relationships)
- [Example 002: expanding relationships](#example-002-expanding-relationships)
- [Example 003: `classicEntitySelector` with relationships](#example-003-classicentityselector-with-relationships)
- [Example 004: signal query with Smartscape dimension](#example-004-signal-query-with-smartscape-dimension)
- [Example 005: `CLOUD_APPLICATION` to workload node types](#example-005-cloud_application-to-workload-node-types)
- [Example 006: `CLOUD_APPLICATION_INSTANCE` to `K8S_POD`](#example-006-cloud_application_instance-to-k8s_pod)
- [Example 007: signal query with Smartscape tag access](#example-007-signal-query-with-smartscape-tag-access)
- [Example 008: AWS DynamoDB table field projection](#example-008-aws-dynamodb-table-field-projection)
- [Example 009: filter by tags and host group](#example-009-filter-by-tags-and-host-group)
- [Example 010: multi-cloud datacenter traversal with missing relationship handling](#example-010-multi-cloud-datacenter-traversal-with-missing-relationship-handling)
- [Example 011: container plus affected-entity mapping](#example-011-container-plus-affected-entity-mapping)
- [Example 012: mass data migration end-to-end with fieldsSnapshot](#example-012-mass-data-migration-end-to-end-with-fieldssnapshot)

## Example 001: `classicEntitySelector` filter without relationships

**Input**

```dql
fetch dt.entity.host
| filter in(id, classicEntitySelector("type(host),tag([Environment]syn_grail_log:bastion)"))
| fields entity.name, id
```

**Smartscape sketch**

```dql
smartscapeNodes HOST
| filter `tags:environment`[syn_grail_log] == "bastion"
| fields entity.name = name, id
```

**Notes**

- `entity.name` becomes `name`
- tag context `[Environment]` becomes `` `tags:environment` ``

## Example 002: expanding relationships

**Input**

```dql
fetch dt.entity.host
| fieldsAdd runs[dt.entity.service_instance]
| expand service_instance = runs[dt.entity.service_instance]
| fields
    id,
    entity.name,
    service_instance
```

**Smartscape sketch**

```dql
smartscapeEdges runs_on
| filter target_type == "HOST" and source_type == "SERVICE"
| fields
    id = target_id,
    entity.name = getNodeName(target_id),
    `runs[dt.entity.service_instance]` = source_id
```

**Notes**

- use edge records when the output shape is relationship-centric

## Example 003: `classicEntitySelector` with relationships

**Input**

```dql
fetch dt.entity.service
| filter in(id, classicEntitySelector("type(service), fromRelationship.runsOnHost(type(host), tag([Azure]dt_owner_email:team-ops@example.com))"))
| fields id, entity.name
```

**Smartscape sketch**

```dql
smartscapeNodes HOST
| filter `tags:azure`[dt_owner_email] == "team-ops@example.com"
| traverse runs_on, SERVICE, direction:backward
| fields id, entity.name = name
```

**Notes**

- start from the constrained side and traverse backward

## Example 004: signal query with Smartscape dimension

**Input**

```dql
timeseries avg(dt.service.request.response_time),
  by:{ dt.entity.service }
```

**Smartscape sketch**

```dql
timeseries avg(dt.service.request.response_time),
  by:{ dt.smartscape.service }
```

**Notes**

- every `dt.entity.*` signal dimension must be migrated

## Example 005: `CLOUD_APPLICATION` to workload node types

**Input**

```dql
fetch dt.entity.cloud_application
| fields entity.name, kubernetesClusterName, cloudApplicationLabels
```

**Smartscape sketch**

```dql
smartscapeNodes K8S_DEPLOYMENT, K8S_DAEMONSET, K8S_STATEFULSET, K8S_REPLICASET,
  K8S_REPLICATIONCONTROLLER, K8S_JOB, K8S_DEPLOYMENTCONFIG
| fields
    entity.name = name,
    kubernetesClusterName = k8s.cluster.name,
    cloudApplicationLabels = `tags:k8s.labels`
```

**Notes**

- one classic type becomes multiple workload node types

## Example 006: `CLOUD_APPLICATION_INSTANCE` to `K8S_POD`

**Input**

```dql
fetch dt.entity.cloud_application_instance
| fields
    entity.name,
    workloadName,
    namespaceName,
    nodeName,
    kubernetesClusterName = entityName(clustered_by[dt.entity.kubernetes_cluster], type:"dt.entity.kubernetes_cluster")
```

**Smartscape sketch**

```dql
smartscapeNodes K8S_POD
| fields entity.name = name,
  workloadName = k8s.workload.name,
  namespaceName = k8s.namespace.name,
  nodeName = k8s.node.name,
  kubernetesClusterName = k8s.cluster.name
```

**Notes**

- use first-class `k8s.*` fields on `K8S_POD`

## Example 007: signal query with Smartscape tag access

**Input**

```dql
timeseries avg(dt.host.cpu.usage),
  by:{ dt.entity.host }
| filter in(entityAttr(dt.entity.host, "tags"), "Dtp_Capability:grail")
```

**Smartscape sketch**

```dql
timeseries avg(dt.host.cpu.usage),
  by:{ dt.smartscape.host }
| filter getNodeField(dt.smartscape.host, "tags")[Dtp_Capability] == "grail"
```

**Notes**

- migrate the signal dimension and replace classic tag access with `getNodeField()`

## Example 008: AWS DynamoDB table field projection

**Input**

```dql
fetch `dt.entity.cloud:aws:dynamodb:table`
| fields entity.name, aws_account, aws_arn, aws_region, aws_resource_type, aws_service, cloud_provider
```

**Smartscape sketch**

```dql
smartscapeNodes AWS_DYNAMODB_TABLE
| fields
  entity.name = name,
  aws_account = aws.account.id,
  aws_arn = aws.arn,
  aws_region = aws.region,
  parse(aws.resource.type, """ (WORD "::" WORD) "::" WORD:aws_resource_type"""),
  parse(aws.resource.type, """ (WORD "::" WORD):aws_service "::" WORD"""),
  cloud_provider = cloud.provider
```

**Notes**

- prefer native Smartscape cloud fields; parse composite fields only when necessary

## Example 009: filter by tags and host group

**Input**

```dql
timeseries series = avg(dt.host.cpu.usage),
  filter:{
    in(dt.host_group.id, array("dtp-dev101-grail"))
    and in(dt.entity.host, classicEntitySelector("type(host),tag(\"Dtp_Capability:grail\")"))
    and in(dt.entity.host, classicEntitySelector("type(host),tag(\"Dtp_Tier:segment-indexer-traces\")"))
  },
  by:{ dt.entity.host }
```

**Smartscape sketch**

```dql
timeseries series = avg(dt.host.cpu.usage),
  filter:{
    in(dt.host_group.id, array("dtp-dev101-grail"))
    and getNodeField(dt.smartscape.host, "tags")[Dtp_Capability] == "grail"
    and getNodeField(dt.smartscape.host, "tags")[Dtp_Tier] == "segment-indexer-traces"
  },
  by:{ dt.smartscape.host }
```

**Notes**

- host group remains a host field, not a traversed entity

## Example 010: multi-cloud datacenter traversal with missing relationship handling

**Input**

```dql
fetch dt.entity.host
| filterOut isMonitoringCandidate
| fieldsAdd
    dt.entity.aws_availability_zone = belongs_to[dt.entity.aws_availability_zone],
    dt.entity.azure_region = belongs_to[dt.entity.azure_region],
    dt.entity.gcp_zone = belongs_to[dt.entity.gcp_zone]
| fieldsAdd
    awsDataCenterName = entityName(dt.entity.aws_availability_zone),
    azureRegionName = entityName(dt.entity.azure_region),
    gcpZoneName = entityName(dt.entity.gcp_zone)
| fields
    id,
    entity.name,
    dataCenter = coalesce(dt.entity.aws_availability_zone, dt.entity.azure_region, dt.entity.gcp_zone, "NO_DATACENTER"),
    dataCenterName = coalesce(awsDataCenterName, azureRegionName, gcpZoneName, "No Data center")
```

**Smartscape sketch**

```dql
smartscapeNodes HOST
| lookup [
    smartscapeNodes HOST
    | traverse runs_on, {AWS_EC2_INSTANCE, AZURE_VM, GCP_VM_INSTANCE}, direction:forward
    | traverse runs_on, {AWS_AVAILABILITY_ZONE, AZURE_REGION, GCP_ZONE}, direction:forward
    | fields dt.smartscape.host = dt.traverse.history[-2][id], dataCenter = id, dataCenterName = name
  ], sourceField:id, lookupField:dt.smartscape.host, fields:{ dataCenter, dataCenterName }
| fields
    id,
    entity.name = name,
    dataCenter = coalesce(dataCenter, "NO_DATACENTER"),
    dataCenterName = coalesce(dataCenterName, "No Data center")
```

**Notes**

- use `lookup` to preserve hosts without cloud relationships

## Example 011: container plus affected-entity mapping

**Input**

```dql
fetch dt.entity.container_group_instance
| fields
    id,
    containerName = entity.name,
    containerizationType = containerizationType,
    containerGroupId = instance_of[dt.entity.container_group],
    containerGroupName = entityName(instance_of[dt.entity.container_group], type:"dt.entity.container_group")
| lookup [
  fetch dt.davis.events.snapshots
  | filter isNotNull(affected_entity_ids)
  | filter in(affected_entity_types, "dt.entity.container_group_instance")
  | expand affected_entity_ids
  | summarize by:{affected_entity_ids}, events = countDistinct(event.id)
], sourceField:id, lookupField:affected_entity_ids, fields: events
| fieldsAdd events = if(isNull(events), 0, else:events)
| fields id, containerName, containerizationType, containerGroupId, containerGroupName, events
```

**Smartscape sketch**

```dql
smartscapeNodes CONTAINER
| fields
    id,
    containerName = name,
    containerizationType = container.containerization_type,
    containerGroupId = null,
    containerGroupName = null
| lookup [
  fetch dt.davis.events.snapshots
  | filter isNotNull(smartscape.affected_entity.ids)
  | filter in(smartscape.affected_entity.types, "CONTAINER")
  | expand smartscape.affected_entity.ids
  | fields affected_entity_ids = smartscape.affected_entity.ids, event.id
  | summarize by:{affected_entity_ids}, events = countDistinct(event.id)
], sourceField:id, lookupField:affected_entity_ids, fields: events
| fieldsAdd events = if(isNull(events), 0, else:events)
| fields id, containerName, containerizationType, containerGroupId, containerGroupName, events
```

**Notes**

- `container_group_instance` maps to `CONTAINER`
- `container_group` remains unsupported as a standalone entity
- event fields become Smartscape event fields

## Example 012: mass data migration end-to-end with fieldsSnapshot

This example demonstrates the full mass-data-filtering-strategy.md workflow including field discovery and verification.

**Input**

```dql
timeseries avg(dt.host.cpu.idle),
  filter:{ in(dt.entity.host, classicEntitySelector("type(HOST),tag(Dtp_Tier:segment-indexer-traces),hostGroupName(dtp-dev101-grail)")) },
  by:{ dt.entity.host }
```

**Step 1 — Resolve conditions**

Two conditions extracted from the `classicEntitySelector`:
- `tag(Dtp_Tier:segment-indexer-traces)` — resolved via auto-tagging rule config. The rule targets entity type HOST with condition key `HOST_TAGS` referencing a primary tag. Mapped field: tag `Dtp_Tier` with value `segment-indexer-traces`.
- `hostGroupName(dtp-dev101-grail)` — maps to `dt.host_group.id` on HOST node or as enriched dimension.

**Step 2 — Discover available fields**

Mass data discovery:

```dtctl
dtctl query 'fieldsSnapshot metrics, by:{metric.key} | filter metric.key == "dt.host.cpu.idle" | fields field' --plain
```

Output includes: `dt.entity.host`, `dt.smartscape.host`, `dt.host_group.id`, `host.name`, ... (but NOT `Dtp_Tier` or `host.group.name`)

Node discovery:

```dtctl
dtctl query 'fieldsSnapshot smartscape.nodes, by:{node.type} | filter node.type == "HOST" | fields field' --plain
```

Output includes: `host.group.name`, `tags`, `name`, `cloud.provider`, ...

**Step 3 — Select approach**

- `dt.host_group.id` is an enriched dimension on the metric -> **Check 1 applies** for the host group condition.
- `Dtp_Tier` tag is NOT an enriched dimension, but `dt.smartscape.host` exists and `tags` is available on the HOST node -> **Check 2 applies** for the tag condition.

Both conditions can be expressed as inline filters using a mix of direct dimension filter and `getNodeField`.

**Migrated query**

```dql
timeseries avg(dt.host.cpu.idle),
  filter:{
    dt.host_group.id == "dtp-dev101-grail"
    AND getNodeField(dt.smartscape.host, "tags")[Dtp_Tier] == "segment-indexer-traces"
  },
  by:{ dt.smartscape.host }
/* Original: timeseries avg(dt.host.cpu.idle), filter:{ in(dt.entity.host, classicEntitySelector("type(HOST),tag(Dtp_Tier:segment-indexer-traces),hostGroupName(dtp-dev101-grail)")) }, by:{ dt.entity.host } */
```

**Step 4 — Verification**

- Output shape: original had `timeframe`, `interval`, `avg(dt.host.cpu.idle)`, `dt.entity.host`. Migrated has same structure with `dt.smartscape.host` replacing `dt.entity.host`.
- Probe: ran migrated query over last 5 minutes, returned 3 time series matching expected hosts.
- Host group condition confirmed via `dt.host_group.id` enriched dimension; tag condition confirmed via `getNodeField` on `dt.smartscape.host`.

**Mapping Resolution**

- `dt.entity.host` dimension -> `dt.smartscape.host`
- `hostGroupName(X)` -> `dt.host_group.id` (enriched dimension, Check 1)
- `tag(Dtp_Tier:X)` -> `getNodeField(dt.smartscape.host, "tags")[Dtp_Tier]` (Check 2)

**Notes**

- Combines Check 1 (direct dimension) and Check 2 (getNodeField) in the same query when conditions map to different field types
- `fieldsSnapshot` discovery was mandatory to confirm `dt.host_group.id` is enriched but `Dtp_Tier` is not
