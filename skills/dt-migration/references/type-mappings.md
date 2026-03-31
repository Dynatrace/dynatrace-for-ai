# Type and Field Mappings

Use this reference when you need the full classic-to-Smartscape mapping set.

## Contents

- [How to read this table](#how-to-read-this-table)
- [Type mappings](#type-mappings)
- [Special cases: entities that are no longer standalone types](#special-cases-entities-that-are-no-longer-standalone-types)
- [Field mappings](#field-mappings)
- [Related references](#related-references)

## How to read this table

- **Classic entity type and field name** appears in classic queries such as `fetch dt.entity.<type>` or signal filters using `dt.entity.*`
- **Smartscape id field name** is the signal or helper field to use in Smartscape-aware signal queries
- **Smartscape type** is the node type used with `smartscapeNodes`
- **Status** indicates how certain the mapping is:
  - `available` — already available
  - `planned` — expected to be available
  - `unclear` — direct mapping not confirmed
  - `not planned` — no direct Smartscape replacement should be assumed

## Type mappings

| Classic entity type and field name | Smartscape id field name | Smartscape type | Status |
| --- | --- | --- | --- |
| `dt.entity.application` | `dt.smartscape.frontend` | `FRONTEND` | available |
| `dt.entity.auto_scaling_group` | `dt.smartscape.aws_autoscaling_autoscalinggroup` | `AWS_AUTOSCALING_AUTOSCALINGGROUP` | available |
| `dt.entity.aws_availability_zone` | `dt.smartscape.aws_availability_zone` | `AWS_AVAILABILITY_ZONE` | available |
| `dt.entity.aws_credentials` | `dt.smartscape.aws_account` | `AWS_ACCOUNT` | available |
| `dt.entity.aws_lambda_function` | `dt.smartscape.aws.lambda_function` | `AWS_LAMBDA_FUNCTION` | available |
| `dt.entity.azure_region` | `dt.smartscape.azure_microsoft_resources_locations` | `AZURE_MICROSOFT_RESOURCES_LOCATIONS` | available |
| `dt.entity.azure_subscription` | `dt.smartscape.azure_microsoft_resources_subscriptions` | `AZURE_MICROSOFT_RESOURCES_SUBSCRIPTIONS` | available |
| `dt.entity.azure_vm` | `dt.smartscape.azure_microsoft_compute_virtualmachines` | `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES` | available |
| `dt.entity.azure_vm_scale_set` | `dt.smartscape.azure_microsoft_compute_virtualmachinescalesets` | `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS` | available |
| `dt.entity.cloud:aws:lambda` | `dt.smartscape.aws.lambda_function` | `AWS_LAMBDA_FUNCTION` | available |
| `dt.entity.cloud:gcp:cloudsql_database` | `<missing>` | `<missing>` | unclear |
| `dt.entity.cloud_application` | `dt.smartscape.k8s_deployment`, `dt.smartscape.k8s_daemonset`, `dt.smartscape.k8s_statefulset`, `dt.smartscape.k8s_replicaset`, `dt.smartscape.k8s_replicationcontroller`, `dt.smartscape.k8s_job`, `dt.smartscape.k8s_deploymentconfig` | `K8S_DEPLOYMENT`, `K8S_DAEMONSET`, `K8S_STATEFULSET`, `K8S_REPLICASET`, `K8S_REPLICATIONCONTROLLER`, `K8S_JOB`, `K8S_DEPLOYMENTCONFIG` | available |
| `dt.entity.cloud_application_instance` | `dt.smartscape.k8s_pod` | `K8S_POD` | available |
| `dt.entity.cloud_application_namespace` | `dt.smartscape.k8s_namespace` | `K8S_NAMESPACE` | available |
| `dt.entity.container_group` | `<removed>` | `<removed>` | not planned |
| `dt.entity.container_group_instance` | `dt.smartscape.container` | `CONTAINER` | available |
| `dt.entity.custom_application` | `dt.smartscape.frontend` | `FRONTEND` | available |
| `dt.entity.custom_device` | `<removed>` | `<removed>` | not planned |
| `dt.entity.custom_device_group` | `<removed>` | `<removed>` | not planned |
| `dt.entity.disk` | `dt.smartscape.disk` | `DISK` | available |
| `dt.entity.ec2_instance` | `dt.smartscape.aws_ec2_instance` | `AWS_EC2_INSTANCE` | available |
| `dt.entity.ebs_volume` | `dt.smartscape.aws_ec2_volume` | `AWS_EC2_VOLUME` | available |
| `dt.entity.elasticsearch:cluster` | `<missing>` | `<missing>` | unclear |
| `dt.entity.elasticsearch:index` | `<missing>` | `<missing>` | unclear |
| `dt.entity.elasticsearch:node` | `<missing>` | `<missing>` | unclear |
| `dt.entity.elasticsearch:thread_pool` | `<missing>` | `<missing>` | unclear |
| `dt.entity.environment` | `<removed>` | `<removed>` | not planned |
| `dt.entity.gcp_zone` | `<missing>` | `<missing>` | unclear |
| `dt.entity.haproxy-prometheus:server` | `<missing>` | `<missing>` | unclear |
| `dt.entity.host` | `dt.smartscape.host` | `HOST` | available |
| `dt.entity.host_group` | `<removed>` | `<removed>` | not planned |
| `dt.entity.http_check` | `dt.smartscape.http_check` | `HTTP_CHECK` | planned |
| `dt.entity.http_check_step` | `dt.smartscape.http_check_step` | `HTTP_CHECK_STEP` | planned |
| `dt.entity.kafka:consumer` | `<missing>` | `<missing>` | unclear |
| `dt.entity.kafka:producer` | `<missing>` | `<missing>` | unclear |
| `dt.entity.kafka:topic` | `<missing>` | `<missing>` | unclear |
| `dt.entity.kubernetes_cluster` | `dt.smartscape.k8s_cluster` | `K8S_CLUSTER` | available |
| `dt.entity.kubernetes_node` | `dt.smartscape.k8s_node` | `K8S_NODE` | available |
| `dt.entity.kubernetes_service` | `dt.smartscape.k8s_service` | `K8S_SERVICE` | available |
| `dt.entity.network_interface` | `dt.smartscape.network_interface` | `NETWORK_INTERFACE` | available |
| `dt.entity.os:service` | `dt.smartscape.os_service` | `OS_SERVICE` | planned |
| `dt.entity.process_group` | `<removed>` | `<removed>` | not planned |
| `dt.entity.process_group_instance` | `dt.smartscape.process` | `PROCESS` | available |
| `dt.entity.relational_database_service` | `dt.smartscape.aws_rds_dbinstance` | `AWS_RDS_DBINSTANCE` | available |
| `dt.entity.service` | `dt.smartscape.service` | `SERVICE` | available |
| `dt.entity.service_instance` | `dt.smartscape.service_deployment` | `SERVICE_DEPLOYMENT` | planned |
| `dt.entity.standardised:slo` | `<missing>` | `<missing>` | unclear |
| `dt.entity.synthetic_location` | `dt.smartscape.synthetic_location` | `SYNTHETIC_LOCATION` | planned |
| `dt.entity.synthetic_test` | `dt.smartscape.synthetic_test` | `SYNTHETIC_TEST` | planned |
| `dt.entity.synthetic_test_step` | `dt.smartscape.synthetic_test_step` | `SYNTHETIC_TEST_STEP` | planned |

## Special cases: entities that are no longer standalone types

### Host group

| Classic | Smartscape |
| --- | --- |
| `dt.entity.host_group` | Not a separate Smartscape entity |
| `entity.name`, `entityName(dt.entity.host_group)` | available as `dt.host_group.id` on `HOST`; despite the field name, it is the usable host-group label |
| `id` | no standalone host-group ID in Smartscape |

Example:

```dql
smartscapeNodes HOST
| fields id, entity.name = name, hostGroupName = `dt.host_group.id`
```

### Process group

| Classic | Smartscape |
| --- | --- |
| `dt.entity.process_group` | Not a separate Smartscape entity |
| `entity.name`, `entityName(dt.entity.process_group)` | available as `dt.process_group.name` or `dt.process_group.detected_name` on `PROCESS` |
| `id` | available as `dt.process_group.id` on `PROCESS` |

Example:

```dql
smartscapeNodes PROCESS
| summarize by:{ id = dt.process_group.id, entity.name = dt.process_group.detected_name }, process.metadata = takeAny(process.metadata)
```

### Container group

| Classic | Smartscape |
| --- | --- |
| `dt.entity.container_group` | Not a separate Smartscape entity |
| `instance_of[dt.entity.container_group]` | unsupported as entity relation |
| `entityName(instance_of[dt.entity.container_group], type:"dt.entity.container_group")` | unsupported; preserve output shape with `null` if needed |

`dt.entity.container_group_instance` still maps to `CONTAINER`.

## Field mappings

Use these field migrations when the classic field name, not just the entity type, needs updating.

| Classic field | Smartscape field | Notes |
| --- | --- | --- |
| `affected_entity_ids` | `smartscape.affected_entity.ids` | Davis events field for affected entity IDs |
| `affected_entity_types` | `smartscape.affected_entity.types` | Davis events field for affected entity types; values become uppercase Smartscape type names |
| `dt.source_entity.type` | `dt.smartscape_source.type` | Davis events field for source entity type |
| `containerizationType` | `container.containerization_type` | Planned Smartscape container field |
| `customPgMetadata` | `process.metadata` | Classic process-group metadata now lives on process |
| `customHostMetadata` | `host.custom.metadata` | Custom host metadata field |

## Related references

- [special-cases.md](special-cases.md)
- [dql-function-migration.md](dql-function-migration.md)
- [entity-cloud-application.md](entity-cloud-application.md)
