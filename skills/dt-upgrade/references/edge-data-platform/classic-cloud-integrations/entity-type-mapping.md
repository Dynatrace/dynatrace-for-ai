# Classic → New Entity Type Mapping — Heuristic Fallback Guide

> **Primary approach**: Use the entity mapping databases (`dac-aws-to-2ndgen-entities.json`, `dac-azure-to-2ndgen-entities.json`) to look up exact mappings. The tables below are **heuristic fallbacks** for entity types not found in the mapping database, and for GCP (mapping database not yet available).

Maps classic entity types to their Smartscape on Grail replacements for each cloud provider.

---

## Table of Contents

- [1. AWS Entity Mapping](#1-aws-entity-mapping)
- [2. Azure Entity Mapping](#2-azure-entity-mapping)
- [3. GCP Entity Mapping](#3-gcp-entity-mapping)
- [4. Query Syntax Change](#4-query-syntax-change)

---

## 1. AWS Entity Mapping

### Built-in Entity Types

| Classic Entity Type | Classic Query | New Smartscape Type | New Query |
|---|---|---|---|
| `EC2_INSTANCE` | `fetch dt.entity.ec2_instance` | `AWS_EC2_INSTANCE` | `smartscapeNodes AWS_EC2_INSTANCE` |
| `EBS_VOLUME` | `fetch dt.entity.ebs_volume` | `AWS_EC2_VOLUME` | `smartscapeNodes AWS_EC2_VOLUME` |
| `AWS_LAMBDA_FUNCTION` | `fetch dt.entity.aws_lambda_function` | `AWS_LAMBDA_FUNCTION` | `smartscapeNodes AWS_LAMBDA_FUNCTION` |
| `AUTO_SCALING_GROUP` | `fetch dt.entity.auto_scaling_group` | `AWS_AUTOSCALING_AUTOSCALINGGROUP` | `smartscapeNodes AWS_AUTOSCALING_AUTOSCALINGGROUP` |
| `AWS_APPLICATION_LOAD_BALANCER` | `fetch dt.entity.aws_application_load_balancer` | `AWS_ELASTICLOADBALANCINGV2_LOADBALANCER` | `smartscapeNodes AWS_ELASTICLOADBALANCINGV2_LOADBALANCER` |
| `AWS_NETWORK_LOAD_BALANCER` | `fetch dt.entity.aws_network_load_balancer` | `AWS_ELASTICLOADBALANCINGV2_LOADBALANCER` | `smartscapeNodes AWS_ELASTICLOADBALANCINGV2_LOADBALANCER` |
| `ELASTIC_LOAD_BALANCER` | `fetch dt.entity.elastic_load_balancer` | *(no direct equivalent — Classic ELB not in new connection)* | — |
| `RELATIONAL_DATABASE_SERVICE` | `fetch dt.entity.relational_database_service` | `AWS_RDS_DBINSTANCE` | `smartscapeNodes AWS_RDS_DBINSTANCE` |
| `DYNAMO_DB_TABLE` | `fetch dt.entity.dynamo_db_table` | `AWS_DYNAMODB_TABLE` | `smartscapeNodes AWS_DYNAMODB_TABLE` |

> **Name collision warning**: `AWS_LAMBDA_FUNCTION`, `AWS_APPLICATION_LOAD_BALANCER`, and `AWS_NETWORK_LOAD_BALANCER` share identical type names between classic and new, but they are completely separate entity systems (Cassandra vs Grail).

### Custom Device (Non-Built-in) Entity Types

| Classic Sub-type | Classic Query | New Smartscape Type | New Query |
|---|---|---|---|
| `cloud:aws:s3` | `fetch dt.entity.custom_device \| filter entity.type == "cloud:aws:s3"` | `AWS_S3_BUCKET` | `smartscapeNodes AWS_S3_BUCKET` |
| `cloud:aws:lambda` | *(non-built-in Lambda)* | `AWS_LAMBDA_FUNCTION` | `smartscapeNodes AWS_LAMBDA_FUNCTION` |
| `cloud:aws:rds` | *(non-built-in RDS)* | `AWS_RDS_DBINSTANCE` | `smartscapeNodes AWS_RDS_DBINSTANCE` |
| `cloud:aws:aurora` | *(Aurora)* | `AWS_RDS_DBCLUSTER` | `smartscapeNodes AWS_RDS_DBCLUSTER` |
| `cloud:aws:elasticachecustom` | *(ElastiCache)* | `AWS_ELASTICACHE_CACHECLUSTER` | `smartscapeNodes AWS_ELASTICACHE_CACHECLUSTER` |
| `cloud:aws:sqs` | *(SQS)* | `AWS_SQS_QUEUE` | `smartscapeNodes AWS_SQS_QUEUE` |
| `cloud:aws:sns` | *(SNS)* | `AWS_SNS_TOPIC` | `smartscapeNodes AWS_SNS_TOPIC` |
| `cloud:aws:cloud_front` | *(CloudFront)* | `AWS_CLOUDFRONT_DISTRIBUTION` | `smartscapeNodes AWS_CLOUDFRONT_DISTRIBUTION` |
| `cloud:aws:nat_gateway` | *(NAT Gateway)* | `AWS_EC2_NATGATEWAY` | `smartscapeNodes AWS_EC2_NATGATEWAY` |
| `cloud:aws:eks:cluster` | *(EKS Cluster)* | `AWS_EKS_CLUSTER` | `smartscapeNodes AWS_EKS_CLUSTER` |
| `cloud:aws:dynamodb` | *(non-built-in DynamoDB)* | `AWS_DYNAMODB_TABLE` | `smartscapeNodes AWS_DYNAMODB_TABLE` |
| `cloud:aws:redshift` | *(Redshift)* | `AWS_REDSHIFT_CLUSTER` | `smartscapeNodes AWS_REDSHIFT_CLUSTER` |
| `cloud:aws:api_gateway` | *(API Gateway)* | *(check environment — may be `AWS_APIGATEWAY_RESTAPI`)* | — |
| `cloud:aws:billing` | *(Billing)* | *(no equivalent — billing is not a new connection entity)* | — |

---

## 2. Azure Entity Mapping

### Built-in Entity Types

| Classic Entity Type | New Smartscape Type |
|---|---|
| `AZURE_VM` | `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINES` |
| `AZURE_VM_SCALE_SET` | `AZURE_MICROSOFT_COMPUTE_VIRTUALMACHINESCALESETS` |
| `AZURE_LOAD_BALANCER` | `AZURE_MICROSOFT_NETWORK_LOADBALANCERS` |
| `AZURE_APPLICATION_GATEWAY` | `AZURE_MICROSOFT_NETWORK_APPLICATIONGATEWAYS` |
| `AZURE_REDIS_CACHE` | `AZURE_MICROSOFT_CACHE_REDIS` |
| `AZURE_COSMOS_DB` | `AZURE_MICROSOFT_DOCUMENTDB_DATABASEACCOUNTS` |
| `AZURE_SQL_SERVER` / `AZURE_SQL_DATABASE` | `AZURE_MICROSOFT_SQL_SERVERS_DATABASES` |
| `AZURE_SQL_ELASTIC_POOL` | `AZURE_MICROSOFT_SQL_SERVERS_ELASTICPOOLS` |
| `AZURE_EVENT_HUB_NAMESPACE` | `AZURE_MICROSOFT_EVENTHUB_NAMESPACES` |
| `AZURE_SERVICE_BUS_NAMESPACE` | `AZURE_MICROSOFT_SERVICEBUS_NAMESPACES` |
| `AZURE_FUNCTION_APP` / `AZURE_WEB_APP` | `AZURE_MICROSOFT_WEB_SITES` |
| `AZURE_STORAGE_ACCOUNT` | `AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS` |
| `AZURE_IOT_HUB` | `AZURE_MICROSOFT_DEVICES_IOTHUBS` |
| `AZURE_API_MANAGEMENT_SERVICE` | `AZURE_MICROSOFT_APIMANAGEMENT_SERVICE` |

> **No name collision**: Unlike AWS, Azure classic and new entity types use different naming conventions, making them easy to distinguish.

### Custom Device (Non-Built-in) Entity Types

| Classic Sub-type | New Smartscape Type |
|---|---|
| `cloud:azure:cache:redis` | `AZURE_MICROSOFT_CACHE_REDIS` |
| `cloud:azure:containerservice:managedcluster` | `AZURE_MICROSOFT_CONTAINERSERVICE_MANAGEDCLUSTERS` |
| `cloud:azure:postgresql:flexibleservers` | `AZURE_MICROSOFT_DBFORPOSTGRESQL_FLEXIBLESERVERS` |
| `cloud:azure:cognitiveservices:openai` | `AZURE_MICROSOFT_COGNITIVESERVICES_ACCOUNTS` |
| `cloud:azure:storage:storageaccounts` | `AZURE_MICROSOFT_STORAGE_STORAGEACCOUNTS` |
| `cloud:azure:network:loadbalancers:standard` | `AZURE_MICROSOFT_NETWORK_LOADBALANCERS` |
| `cloud:azure:app:containerapps` | `AZURE_MICROSOFT_APP_CONTAINERAPPS` |
| `cloud:azure:apimanagement:service` | `AZURE_MICROSOFT_APIMANAGEMENT_SERVICE` |

---

## 3. GCP Entity Mapping

GCP has **no dedicated classic entity types** — all classic entities are `CUSTOM_DEVICE` with `cloud:gcp:*` sub-types. New connection entities derive from Cloud Asset Inventory types.

| Classic Sub-type | New Smartscape Type |
|---|---|
| `cloud:gcp:gce_instance` | `GCP_COMPUTE_GOOGLEAPIS_COM_INSTANCE` |
| `cloud:gcp:cloudsql_database` | `GCP_SQLADMIN_GOOGLEAPIS_COM_INSTANCE` |
| `cloud:gcp:cloud_function` | `GCP_CLOUDFUNCTIONS_GOOGLEAPIS_COM_FUNCTION` |
| `cloud:gcp:cloud_run_revision` | `GCP_RUN_GOOGLEAPIS_COM_SERVICE` |
| `cloud:gcp:gcs_bucket` | `GCP_STORAGE_GOOGLEAPIS_COM_BUCKET` |
| `cloud:gcp:k8s_cluster` | `GCP_CONTAINER_GOOGLEAPIS_COM_CLUSTER` |
| `cloud:gcp:pubsub_topic` | `GCP_PUBSUB_GOOGLEAPIS_COM_TOPIC` |
| `cloud:gcp:pubsub_subscription` | `GCP_PUBSUB_GOOGLEAPIS_COM_SUBSCRIPTION` |
| `cloud:gcp:redis_instance` | `GCP_REDIS_GOOGLEAPIS_COM_INSTANCE` |
| `cloud:gcp:spanner_instance` | `GCP_SPANNER_GOOGLEAPIS_COM_INSTANCE` |
| `cloud:gcp:nat_gateway` | `GCP_COMPUTE_GOOGLEAPIS_COM_ROUTER` |
| `cloud:gcp:https_lb` | `GCP_COMPUTE_GOOGLEAPIS_COM_URLMAP` |
| `cloud:gcp:project` | `GCP_CLOUDRESOURCEMANAGER_GOOGLEAPIS_COM_PROJECT` |

> **Name pattern**: New GCP entities use `GCP_<ASSET_INVENTORY_SERVICE>_<RESOURCE_TYPE>` — derived from Cloud Asset Inventory types, not Cloud Monitoring resource types.

---

## 4. Query Syntax Change

| Aspect | Classic | New |
|---|---|---|
| **Query command** | `fetch dt.entity.<type>` | `smartscapeNodes <TYPE>` |
| **Name field** | `entity.name` | `name` |
| **ID field** | `id` (e.g., `EC2_INSTANCE-ABC123`) | `id` (e.g., `AWS_EC2_INSTANCE-ABC123`) |
| **Scope** | `storage:entities:read` | `storage:smartscape:read` |
| **Relationship traversal** | `belongs_to[...]`, `accessible_by[...]` | `traverse`, `references`, `smartscapeEdges` |
| **Custom attributes** | `entity.name`, `awsAccountId`, etc. | `name`, `aws.account.id`, `azure.subscription`, etc. |
| **Filtering** | `filter entity.type == "cloud:aws:s3"` | `filter type == "AWS_S3_BUCKET"` |
