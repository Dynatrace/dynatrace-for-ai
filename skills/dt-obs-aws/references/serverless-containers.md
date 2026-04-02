# AWS Serverless & Container Workloads

Monitor AWS Lambda, ECS, EKS, and App Runner services.

## Table of Contents

- [Serverless & Container Entity Types](#serverless--container-entity-types)
- [Lambda Monitoring](#lambda-monitoring)
- [ECS Monitoring](#ecs-monitoring)
- [EKS Monitoring](#eks-monitoring)
- [App Runner](#app-runner)
- [Cross-Service Analysis](#cross-service-analysis)

## Serverless & Container Entity Types

All these types support the standard discovery pattern: `smartscapeNodes "<TYPE>" | fields name, aws.account.id, aws.region, ...`

| Entity type | Description |
|---|---|
| `AWS_LAMBDA_FUNCTION` | Lambda functions |
| `AWS_LAMBDA_EVENTSOURCEMAPPING` | Lambda event source mappings |
| `AWS_ECS_CLUSTER` | ECS clusters |
| `AWS_ECS_SERVICE` | ECS services |
| `AWS_ECS_TASK` | Running ECS tasks |
| `AWS_ECS_TASKDEFINITION` | ECS task definitions |
| `AWS_ECS_CONTAINERINSTANCE` | EC2 instances used by ECS |
| `AWS_EKS_CLUSTER` | EKS clusters |
| `AWS_EKS_NODEGROUP` | EKS node groups |
| `AWS_APPRUNNER_SERVICE` | App Runner services |
| `AWS_APPRUNNER_VPCCONNECTOR` | App Runner VPC connectors |

## Lambda Monitoring

Find Lambda functions with VPC access — use for networking troubleshooting and dependency mapping. For a security audit of VPC attachment coverage, see [security-compliance.md#public-access-detection](security-compliance.md#public-access-detection).

```dql
smartscapeNodes "AWS_LAMBDA_FUNCTION"
| filter isNotNull(aws.vpc.id)
| fields name, aws.resource.id, aws.vpc.id, aws.subnet.id, aws.security_group.id
```

Filter functions by tag:

```dql
smartscapeNodes "AWS_LAMBDA_FUNCTION"
| filter tags[Environment] == "production"
| fields name, aws.resource.id, aws.region
```

## ECS Monitoring

Map ECS services to their clusters using traversal:

```dql
smartscapeNodes "AWS_ECS_SERVICE"
| traverse "belongs_to", "AWS_ECS_CLUSTER"
| fields name, aws.resource.id, aws.region
```

Find which services use which task definitions:

```dql
smartscapeNodes "AWS_ECS_SERVICE"
| traverse "uses", "AWS_ECS_TASKDEFINITION"
| fields name, aws.resource.id
```

Analyze ECS service networking (subnet attachment):

```dql
smartscapeNodes "AWS_ECS_SERVICE"
| traverse "is_attached_to", "AWS_EC2_SUBNET"
| fields name, aws.resource.id, aws.vpc.id
```

Find ECS service security groups:

```dql
smartscapeNodes "AWS_ECS_SERVICE"
| traverse "uses", "AWS_EC2_SECURITYGROUP"
| fields name, aws.resource.id
```

## EKS Monitoring

List EKS clusters with VPC context:

```dql
smartscapeNodes "AWS_EKS_CLUSTER"
| fields name, aws.account.id, aws.region, aws.vpc.id
```

## App Runner

Find App Runner VPC connectors (for private connectivity):

```dql
smartscapeNodes "AWS_APPRUNNER_VPCCONNECTOR"
| fields name, aws.resource.id, aws.vpc.id
```

## Cross-Service Analysis

Count all container platforms by type and region:

```dql
smartscapeNodes "AWS_ECS_CLUSTER", "AWS_EKS_CLUSTER", "AWS_APPRUNNER_SERVICE"
| summarize count = count(), by: {type, aws.region}
| sort count desc
```
