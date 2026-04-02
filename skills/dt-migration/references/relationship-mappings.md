# Relationship Mappings

Use this reference to verify which Smartscape edges are valid when rewriting classic relationships to `traverse`, `smartscapeEdges`, or `references`.

## Contents

- [How to use this file](#how-to-use-this-file)
- [Edge types](#edge-types)
- [Standardized edge types](#standardized-edge-types)
- [Examples](#examples)
- [Note on completeness](#note-on-completeness)

## How to use this file

- Use `traverse` to navigate edges in topology queries
- Use `smartscapeEdges` when you want edge-centric records
- Use `references[...]` only for static edges

## Edge types

| Source Type | Edge Type | Target Type | Edge Kind |
| --- | --- | --- | --- |
| `AWS_APIGATEWAYV2_STAGE` | `is_attached_to` | `AWS_APIGATEWAYV2_API` | static |
| `AWS_APIGATEWAY_STAGE` | `is_attached_to` | `AWS_APIGATEWAY_RESTAPI` | static |
| `AWS_AUTOSCALING_AUTOSCALINGGROUP` | `contains` | `AWS_EC2_INSTANCE` | static |
| `AWS_AUTOSCALING_AUTOSCALINGGROUP` | `is_attached_to` | `AWS_ELASTICLOADBALANCINGV2_TARGETGROUP` | static |
| `AWS_AUTOSCALING_AUTOSCALINGGROUP` | `is_attached_to` | `AWS_ELASTICLOADBALANCING_LOADBALANCER` | static |
| `AWS_AUTOSCALING_AUTOSCALINGGROUP` | `runs_on` | `AWS_AVAILABILITY_ZONE` | static |
| `AWS_AUTOSCALING_AUTOSCALINGGROUP` | `uses` | `AWS_EC2_LAUNCHTEMPLATE` | static |
| `AWS_AVAILABILITY_ZONE` | `is_part_of` | `AWS_REGION` | static |
| `AWS_CLOUDFRONT_DISTRIBUTION` | `is_attached_to` | `AWS_CERTIFICATEMANAGER_CERTIFICATE` | static |
| `AWS_CLOUDFRONT_DISTRIBUTION` | `is_attached_to` | `AWS_WAFV2_WEBACL` | static |
| `AWS_CLOUDFRONT_DISTRIBUTION` | `routes_to` | `AWS_S3_BUCKET` | static |
| `AWS_CLOUDTRAIL_TRAIL` | `uses` | `AWS_KMS_KEY` | static |
| `AWS_CLOUDTRAIL_TRAIL` | `uses` | `AWS_S3_BUCKET` | static |
| `AWS_DMS_REPLICATIONINSTANCE` | `is_attached_to` | `AWS_EC2_SUBNET` | static |
| `AWS_DMS_REPLICATIONINSTANCE` | `is_attached_to` | `AWS_EC2_VPC` | static |
| `AWS_DMS_REPLICATIONINSTANCE` | `runs_on` | `AWS_AVAILABILITY_ZONE` | static |
| `AWS_DMS_REPLICATIONINSTANCE` | `uses` | `AWS_EC2_SECURITYGROUP` | static |
| `AWS_DYNAMODB_TABLE` | `uses` | `AWS_KMS_KEY` | static |
| `AWS_EC2_EIP` | `is_attached_to` | `AWS_EC2_INSTANCE` | static |
| `AWS_EC2_EIP` | `is_attached_to` | `AWS_EC2_NETWORKINTERFACE` | static |
| `AWS_EC2_INSTANCE` | `is_attached_to` | `AWS_EC2_SUBNET` | static |
| `AWS_EC2_INSTANCE` | `is_attached_to` | `AWS_EC2_VPC` | static |
| `AWS_EC2_INSTANCE` | `runs_on` | `AWS_AVAILABILITY_ZONE` | static |
| `AWS_EC2_INSTANCE` | `uses` | `AWS_EC2_SECURITYGROUP` | static |
| `AWS_EC2_INSTANCE` | `uses` | `AWS_IAM_INSTANCEPROFILE` | static |
| `AWS_EC2_NETWORKINTERFACE` | `is_attached_to` | `AWS_EC2_INSTANCE` | static |
| `AWS_EC2_NETWORKINTERFACE` | `is_attached_to` | `AWS_EC2_SUBNET` | static |
| `AWS_EC2_NETWORKINTERFACE` | `is_attached_to` | `AWS_EC2_VPC` | static |
| `AWS_EC2_NETWORKINTERFACE` | `runs_on` | `AWS_AVAILABILITY_ZONE` | static |
| `AWS_EC2_NETWORKINTERFACE` | `uses` | `AWS_EC2_SECURITYGROUP` | static |
| `AWS_EC2_SUBNET` | `is_attached_to` | `AWS_EC2_VPC` | static |
| `AWS_EC2_SUBNET` | `runs_on` | `AWS_AVAILABILITY_ZONE` | static |
| `AWS_EC2_VOLUME` | `is_attached_to` | `AWS_EC2_INSTANCE` | static |
| `AWS_EC2_VOLUME` | `runs_on` | `AWS_AVAILABILITY_ZONE` | static |
| `AWS_EC2_VOLUME` | `uses` | `AWS_KMS_KEY` | static |
| `AWS_ECS_SERVICE` | `balanced_by` | `AWS_ELASTICLOADBALANCINGV2_TARGETGROUP` | static |
| `AWS_ECS_SERVICE` | `belongs_to` | `AWS_ECS_CLUSTER` | static |
| `AWS_ECS_SERVICE` | `is_attached_to` | `AWS_EC2_SUBNET` | static |
| `AWS_ECS_SERVICE` | `uses` | `AWS_EC2_SECURITYGROUP` | static |
| `AWS_ECS_SERVICE` | `uses` | `AWS_ECS_TASKDEFINITION` | static |
| `AWS_ECS_SERVICE` | `uses` | `AWS_IAM_ROLE` | static |
| `AWS_ECS_TASK` | `belongs_to` | `AWS_ECS_CLUSTER` | static |
| `AWS_ECS_TASK` | `is_part_of` | `AWS_ECS_SERVICE` | static |
| `AWS_ECS_TASK` | `runs_on` | `AWS_AVAILABILITY_ZONE` | static |
| `AWS_ECS_TASK` | `uses` | `AWS_EC2_NETWORKINTERFACE` | static |
| `AWS_ECS_TASK` | `uses` | `AWS_EC2_SUBNET` | static |
| `AWS_ECS_TASK` | `uses` | `AWS_ECS_TASKDEFINITION` | static |
| `AWS_EKS_CLUSTER` | `is_attached_to` | `AWS_EC2_SUBNET` | static |
| `AWS_EKS_CLUSTER` | `is_attached_to` | `AWS_EC2_VPC` | static |
| `AWS_EKS_CLUSTER` | `uses` | `AWS_EC2_SECURITYGROUP` | static |
| `AWS_EKS_CLUSTER` | `uses` | `AWS_IAM_ROLE` | static |
| `AWS_EKS_CLUSTER` | `uses` | `AWS_KMS_KEY` | static |
| `AWS_EKS_NODEGROUP` | `belongs_to` | `AWS_EKS_CLUSTER` | static |
| `AWS_EKS_NODEGROUP` | `is_attached_to` | `AWS_EC2_SUBNET` | static |
| `AWS_EKS_NODEGROUP` | `uses` | `AWS_EC2_LAUNCHTEMPLATE` | static |
| `AWS_EKS_NODEGROUP` | `uses` | `AWS_IAM_ROLE` | static |
| `AWS_ELASTICLOADBALANCINGV2_LOADBALANCER` | `is_attached_to` | `AWS_EC2_SUBNET` | static |
| `AWS_ELASTICLOADBALANCINGV2_LOADBALANCER` | `is_attached_to` | `AWS_EC2_VPC` | static |
| `AWS_ELASTICLOADBALANCINGV2_LOADBALANCER` | `runs_on` | `AWS_AVAILABILITY_ZONE` | static |
| `AWS_ELASTICLOADBALANCINGV2_LOADBALANCER` | `uses` | `AWS_EC2_SECURITYGROUP` | static |
| `AWS_ELASTICLOADBALANCINGV2_TARGETGROUP` | `balanced_by` | `AWS_ELASTICLOADBALANCINGV2_LOADBALANCER` | static |
| `AWS_ELASTICLOADBALANCINGV2_TARGETGROUP` | `balances` | `AWS_EC2_INSTANCE` | static |
| `AWS_ELASTICLOADBALANCING_LOADBALANCER` | `balances` | `AWS_EC2_INSTANCE` | static |
| `AWS_ELASTICLOADBALANCING_LOADBALANCER` | `is_attached_to` | `AWS_EC2_SUBNET` | static |
| `AWS_ELASTICLOADBALANCING_LOADBALANCER` | `is_attached_to` | `AWS_EC2_VPC` | static |
| `AWS_ELASTICLOADBALANCING_LOADBALANCER` | `runs_on` | `AWS_AVAILABILITY_ZONE` | static |
| `AWS_ELASTICLOADBALANCING_LOADBALANCER` | `uses` | `AWS_CERTIFICATEMANAGER_CERTIFICATE` | static |
| `AWS_ELASTICLOADBALANCING_LOADBALANCER` | `uses` | `AWS_EC2_SECURITYGROUP` | static |
| `AWS_LAMBDA_FUNCTION` | `is_attached_to` | `AWS_EC2_SUBNET` | static |
| `AWS_LAMBDA_FUNCTION` | `is_attached_to` | `AWS_EC2_VPC` | static |
| `AWS_LAMBDA_FUNCTION` | `uses` | `AWS_EC2_SECURITYGROUP` | static |
| `AWS_LAMBDA_FUNCTION` | `uses` | `AWS_IAM_ROLE` | static |
| `AWS_LAMBDA_FUNCTION` | `uses` | `AWS_KMS_KEY` | static |
| `AWS_RDS_DBINSTANCE` | `is_attached_to` | `AWS_EC2_SUBNET` | static |
| `AWS_RDS_DBINSTANCE` | `is_attached_to` | `AWS_EC2_VPC` | static |
| `AWS_RDS_DBINSTANCE` | `is_part_of` | `AWS_RDS_DBCLUSTER` | static |
| `AWS_RDS_DBINSTANCE` | `runs_on` | `AWS_AVAILABILITY_ZONE` | static |
| `AWS_RDS_DBINSTANCE` | `uses` | `AWS_EC2_SECURITYGROUP` | static |
| `AWS_RDS_DBINSTANCE` | `uses` | `AWS_KMS_KEY` | static |
| `AWS_RDS_DBINSTANCE` | `uses` | `AWS_RDS_OPTIONGROUP` | static |
| `CONTAINER` | `belongs_to` | `K8S_CLUSTER` | static |
| `CONTAINER` | `belongs_to` | `K8S_NAMESPACE` | static |
| `CONTAINER` | `is_part_of` | `K8S_CRONJOB` | static |
| `CONTAINER` | `is_part_of` | `K8S_DAEMONSET` | static |
| `CONTAINER` | `is_part_of` | `K8S_DEPLOYMENT` | static |
| `CONTAINER` | `is_part_of` | `K8S_JOB` | static |
| `CONTAINER` | `is_part_of` | `K8S_POD` | static |
| `CONTAINER` | `is_part_of` | `K8S_REPLICASET` | static |
| `CONTAINER` | `is_part_of` | `K8S_STATEFULSET` | static |
| `CONTAINER` | `runs_on` | `HOST` | static |
| `CONTAINER` | `runs_on` | `K8S_NODE` | static |
| `DISK` | `belongs_to` | `HOST` | static |
| `HOST` | `calls` | `HOST` | dynamic |
| `HOST` | `runs_on` | `AWS_EC2_INSTANCE` | static |
| `HOST` | `runs_on` | `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES` | static |
| `HOST` | `runs_on` | `GCP_COMPUTE_GOOGLEAPIS_COM_INSTANCE` | static |
| `K8S_CLUSTER` | `uses` | `AWS_EC2_SECURITYGROUP` | static |
| `K8S_CRONJOB` | `belongs_to` | `K8S_CLUSTER` | static |
| `K8S_CRONJOB` | `belongs_to` | `K8S_NAMESPACE` | static |
| `K8S_DAEMONSET` | `belongs_to` | `K8S_CLUSTER` | static |
| `K8S_DAEMONSET` | `belongs_to` | `K8S_NAMESPACE` | static |
| `K8S_DEPLOYMENT` | `belongs_to` | `K8S_CLUSTER` | static |
| `K8S_DEPLOYMENT` | `belongs_to` | `K8S_NAMESPACE` | static |
| `K8S_INGRESS` | `belongs_to` | `K8S_CLUSTER` | static |
| `K8S_INGRESS` | `belongs_to` | `K8S_NAMESPACE` | static |
| `K8S_INGRESS` | `routes_to` | `K8S_SERVICE` | static |
| `K8S_JOB` | `belongs_to` | `K8S_CLUSTER` | static |
| `K8S_JOB` | `belongs_to` | `K8S_NAMESPACE` | static |
| `K8S_JOB` | `is_part_of` | `K8S_CRONJOB` | static |
| `K8S_NAMESPACE` | `belongs_to` | `K8S_CLUSTER` | static |
| `K8S_NODE` | `belongs_to` | `K8S_CLUSTER` | static |
| `K8S_PERSISTENTVOLUMECLAIM` | `belongs_to` | `K8S_CLUSTER` | static |
| `K8S_PERSISTENTVOLUMECLAIM` | `belongs_to` | `K8S_NAMESPACE` | static |
| `K8S_PERSISTENTVOLUMECLAIM` | `uses` | `K8S_PERSISTENTVOLUME` | static |
| `K8S_POD` | `belongs_to` | `K8S_CLUSTER` | static |
| `K8S_POD` | `belongs_to` | `K8S_NAMESPACE` | static |
| `K8S_POD` | `is_part_of` | `K8S_CRONJOB` | static |
| `K8S_POD` | `is_part_of` | `K8S_DAEMONSET` | static |
| `K8S_POD` | `is_part_of` | `K8S_DEPLOYMENT` | static |
| `K8S_POD` | `is_part_of` | `K8S_JOB` | static |
| `K8S_POD` | `is_part_of` | `K8S_REPLICASET` | static |
| `K8S_POD` | `is_part_of` | `K8S_STATEFULSET` | static |
| `K8S_POD` | `runs_on` | `K8S_NODE` | static |
| `K8S_POD` | `uses` | `K8S_CONFIGMAP` | static |
| `K8S_POD` | `uses` | `K8S_PERSISTENTVOLUMECLAIM` | static |
| `K8S_POD` | `uses` | `K8S_SECRET` | static |
| `K8S_REPLICASET` | `belongs_to` | `K8S_CLUSTER` | static |
| `K8S_REPLICASET` | `belongs_to` | `K8S_NAMESPACE` | static |
| `K8S_REPLICASET` | `is_part_of` | `K8S_DEPLOYMENT` | static |
| `K8S_SECRET` | `belongs_to` | `K8S_CLUSTER` | static |
| `K8S_SECRET` | `belongs_to` | `K8S_NAMESPACE` | static |
| `K8S_SERVICE` | `belongs_to` | `K8S_CLUSTER` | static |
| `K8S_SERVICE` | `belongs_to` | `K8S_NAMESPACE` | static |
| `K8S_SERVICE` | `routes_to` | `K8S_POD` | static |
| `K8S_STATEFULSET` | `belongs_to` | `K8S_CLUSTER` | static |
| `K8S_STATEFULSET` | `belongs_to` | `K8S_NAMESPACE` | static |
| `NETWORK_INTERFACE` | `belongs_to` | `HOST` | static |
| `ONEAGENT` | `monitors` | `HOST` | static |
| `PROCESS` | `calls` | `PROCESS` | dynamic |
| `PROCESS` | `runs_on` | `CONTAINER` | static |
| `PROCESS` | `runs_on` | `HOST` | static |
| `SERVICE` | `belongs_to` | `K8S_CLUSTER` | dynamic |
| `SERVICE` | `belongs_to` | `K8S_DEPLOYMENT` | dynamic |
| `SERVICE` | `belongs_to` | `K8S_NAMESPACE` | dynamic |
| `SERVICE` | `belongs_to` | `K8S_STATEFULSET` | dynamic |
| `SERVICE` | `calls` | `SERVICE` | dynamic |
| `SERVICE` | `runs_on` | `CONTAINER` | dynamic |
| `SERVICE` | `runs_on` | `HOST` | dynamic |
| `SERVICE` | `runs_on` | `K8S_POD` | dynamic |
| `SERVICE` | `runs_on` | `PROCESS` | dynamic |

## Standardized edge types

| Edge Type | Description |
| --- | --- |
| `belongs_to` | Membership or containment relationship |
| `calls` | Communication or invocation |
| `contains` | Parent contains child entities |
| `is_attached_to` | Attachment or association |
| `is_part_of` | Composition relationship |
| `routes_to` | Traffic or request routing |
| `runs_on` | Execution environment relationship |
| `uses` | Dependency or utilization relationship |
| `balances` | Load-balancing relationship |
| `balanced_by` | Reverse load-balancing relationship |
| `monitors` | Monitoring relationship |

## Examples

### Querying edges directly

```dql
smartscapeEdges "runs_on"
| filter source_type == "SERVICE" and target_type == "HOST"
| fields source_id, source_name = getNodeName(source_id), target_id, target_name = getNodeName(target_id)
```

### Following an edge with `traverse`

```dql
smartscapeNodes HOST
| filter `tags:azure`[dt_owner_email] == "team-ops@example.com"
| traverse runs_on, SERVICE, direction:backward
```

### Using `references` for static edges

```dql
smartscapeNodes NETWORK_INTERFACE
| fieldsAdd host = references[belongs_to.host]
```

## Note on completeness

This file contains the migration-relevant edge set extracted from the source repository. If a migration depends on an edge not listed here, verify it directly in the target environment before assuming availability.
