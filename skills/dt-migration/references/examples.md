# Example Migrations

Use these examples as before/after templates.

Keep the same pattern when adding more examples:

1. input query
2. Smartscape translation sketch
3. notes about the mapping

## Contents

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
- [Example 013: `timeseries filter` with tag-based entity sub-query](#example-013-timeseries-filter-with-tag-based-entity-sub-query)
- [Example 014: `timeseries filter` with related-entity traversal subquery](#example-014-timeseries-filter-with-related-entity-traversal-subquery)
- [Example 015: Davis Problems entity filter with edge join and dedup](#example-015-davis-problems-entity-filter-with-edge-join-and-dedup)

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
    service_instance = source_id
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
- use unquoted key syntax for tag-map access: `...[Dtp_Capability]`; quoted keys in this pattern cause a DQL syntax error

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
- use unquoted key syntax for tag-map access: `...[Dtp_Capability]` and `...[Dtp_Tier]`; quoted keys in this pattern cause a DQL syntax error

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
    | traverse runs_on, {AWS_EC2_INSTANCE, AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES,  GCP_COMPUTE_GOOGLEAPIS_COM_INSTANCE}, direction:forward
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
  | filter isNotNull(smartscape.affected_entities)
  | expand smartscape.affected_entities
  | fieldsAdd
      affected_entity_ids = smartscape.affected_entities[id],
      affected_entity_type = smartscape.affected_entities[type]
  | filter affected_entity_type == "CONTAINER"
  | fields affected_entity_ids, event.id
  | summarize by:{affected_entity_ids}, events = countDistinct(event.id)
], sourceField:id, lookupField:affected_entity_ids, fields: events
| fieldsAdd events = if(isNull(events), 0, else:events)
| fields id, containerName, containerizationType, containerGroupId, containerGroupName, events
```

**Notes**

- `container_group_instance` maps to `CONTAINER`
- `container_group` remains unsupported as a standalone entity
- event fields become Smartscape event fields
- filtering the type **after** `expand` is more precise than the classic
  `in(smartscape.affected_entity.types, "CONTAINER")`: each record carries its own `type`, so the
  filter now keeps only the container records instead of every entity on an event that happened to
  include one container

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

## Example 013: `timeseries filter` with tag-based entity sub-query

**Input**

```dql
timeseries usage=avg(dt.host.cpu.usage),
  filter: { in(dt.entity.host, classicEntitySelector("type(host),tags(\"BF\")")) }
```

**Smartscape sketch**

```dql
timeseries usage=avg(dt.host.cpu.usage),
  filter: { dt.smartscape.host in [smartscapeNodes "HOST" | filter tags ~ "BF" | fields id] }
```

**Notes**

- `dt.entity.host` → `dt.smartscape.host` (standard dimension migration)
- `in(dt.entity.host, classicEntitySelector(...))` → `dt.smartscape.host in [...]`: the `in()` function does not accept execution blocks — use the `in` **operator** (`field in [execution block]`) when the right-hand side is a sub-query
- `tags("BF")` in the classic selector matches hosts tagged with `BF`; in Smartscape, `tags ~ "BF"` uses substring matching on the serialized tag string, which also matches tags whose key or value *contains* `BF` — use an exact match if needed: ``tags[`BF`] == <value>`` or ``isNotNull(tags[`BF`]``

## Example 014: `timeseries filter` with related-entity traversal subquery

A `timeseries` query measuring process-group memory, filtered to only the process groups running a specific service.

**Input**

```dql
timeseries memory_usage = avg(dt.process.memory.usage),
  by:{dt.entity.process_group},
  filter:{
    dt.entity.process_group in [
      fetch dt.entity.process_group
      | expand runs[dt.entity.service], alias: services
      | filter services in [
          fetch dt.entity.service
          | filter in(id, {"SERVICE-C55BE95B0B7219CD"})
          | fields id
        ]
      | fields id
    ]
  }
| summarize memory_saturation = avg(arrayAvg(memory_usage))
```

**Smartscape sketch**

```dql
timeseries memory_usage = avg(dt.process.memory.usage, default: 0),
  by:{dt.smartscape.process},
  filter:{
    dt.smartscape.process in [
      smartscapeNodes SERVICE
      | filter in(id, { toSmartscapeId("SERVICE-C55BE95B0B7219CD") })
      | traverse {runs_on}, {PROCESS}, direction: "forward", fieldsKeep: {id, name, type}
      | fields id
    ]
  }
| summarize memory_saturation = avg(arrayAvg(memory_usage))
```

**Notes**

- signal dimension `dt.entity.process_group` → `dt.smartscape.process`
- `fetch dt.entity.process_group | expand runs[dt.entity.service]` subquery → `smartscapeNodes SERVICE | traverse {runs_on}, {PROCESS}, direction: "forward"`
- start from the anchor entity (SERVICE) and traverse forward to PROCESS — the classic `expand` direction is reversed in Smartscape traversal
- `default: 0` added to the aggregation so metric gaps do not produce `null`

## Example 015: Davis Problems entity filter with edge join and dedup

A classic Davis event query filtered by a specific host entity ID.

**Input**

```dql-snippet
fetch events
| filter event.kind == "DAVIS_PROBLEM"
| filter in(dt.entity.host, {"HOST-8CBE06F58F5E99DA"})
| summarize count()
```

**Smartscape sketch**

```dql
fetch events
| filter event.kind == "DAVIS_PROBLEM" AND isNotNull(smartscape.affected_entities)
| expand smartscape.affected_entities
| fieldsAdd ids = smartscape.affected_entities[id]
| filter ids in [
    smartscapeEdges "*"
    | filter in(target_id, { toSmartscapeId("HOST-8CBE06F58F5E99DA") })
    | fields source_id
  ]
| summarize c = count(), by: {event.id}
| summarize number_davis_events = sum(c)
```

**Notes**

- `affected_entity_ids` → `smartscape.affected_entities`; guard with `isNotNull` to drop events not yet indexed in Smartscape. `expand` yields one record per row, then `[id]` projects the scalar ID — the same projection without a preceding `expand` returns `null`
- `smartscapeEdges "*"` joined via `target_id` gives source IDs (edge node IDs) affected by the host
- `by: {event.id}` deduplication is mandatory: one Davis problem affects multiple entities, so `expand` generates one row per affected entity — without dedup the `count()` is inflated
- the double `summarize` pattern first counts rows per event, then sums to a single total
