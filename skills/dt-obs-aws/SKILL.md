---
name: dt-obs-aws
description: AWS cloud resources including EC2, RDS, Lambda, ECS/EKS, VPC networking, load balancers, databases, serverless, messaging, and cost optimization. Monitor AWS infrastructure, analyze resource usage, optimize costs, and ensure security compliance.
license: Apache-2.0
---

# AWS Cloud Infrastructure

Monitor and analyze AWS resources using Dynatrace Smartscape and DQL. Query AWS services, optimize costs, manage security, and plan capacity across your AWS infrastructure.

## When to Use This Skill

Use this skill when the user needs to work with AWS resources in Dynatrace. Load the reference file for the task type:

| Task | File to load |
|---|---|
| Inventory and topology queries | (no additional file — use core patterns above) |
| Query AWS metric timeseries (CPU, errors, latency) | Load `references/metrics-performance.md` |
| VPC topology, security groups, subnet analysis | Load `references/vpc-networking-security.md` |
| RDS, DynamoDB, ElastiCache investigation | Load `references/database-monitoring.md` |
| Lambda, ECS, EKS investigation | Load `references/serverless-containers.md` |
| ALB/NLB topology, API Gateway | Load `references/load-balancing-api.md` |
| SQS, SNS, EventBridge, MSK | Load `references/messaging-event-streaming.md` |
| Unattached resources, tag compliance, lifecycle | Load `references/resource-management.md` |
| Cost savings, unused resources | Load `references/cost-optimization.md` |
| Capacity headroom, subnet IP, ASG limits | Load `references/capacity-planning.md` |
| Security audit, encryption, public access | Load `references/security-compliance.md` |
| SG rule analysis (0.0.0.0/0, open ports) | Load `references/security-compliance.md` |
| S3 public access, bucket encryption | Load `references/security-compliance.md` |
| EBS volume encryption audit | Load `references/security-compliance.md` |
| Cost allocation, chargeback, ownership | Load `references/resource-ownership.md` |

---

## Core Concepts

### Entity Types

AWS resources use the `AWS_*` prefix and can be queried using the `smartscapeNodes` function. All AWS entities are automatically discovered and modeled in Dynatrace Smartscape.

**Compute:** `AWS_EC2_INSTANCE`, `AWS_LAMBDA_FUNCTION`, `AWS_ECS_CLUSTER`, `AWS_ECS_SERVICE`, `AWS_EKS_CLUSTER`
**Networking:** `AWS_EC2_VPC`, `AWS_EC2_SUBNET`, `AWS_EC2_SECURITYGROUP`, `AWS_EC2_NATGATEWAY`, `AWS_EC2_VPCENDPOINT`
**Database:** `AWS_RDS_DBINSTANCE`, `AWS_RDS_DBCLUSTER`, `AWS_DYNAMODB_TABLE`, `AWS_ELASTICACHE_CACHECLUSTER`
**Storage:** `AWS_S3_BUCKET`, `AWS_EC2_VOLUME`, `AWS_EFS_FILESYSTEM`
**Load Balancing:** `AWS_ELASTICLOADBALANCINGV2_LOADBALANCER`, `AWS_ELASTICLOADBALANCINGV2_TARGETGROUP`
**Messaging:** `AWS_SQS_QUEUE`, `AWS_SNS_TOPIC`, `AWS_EVENTS_EVENTBUS`, `AWS_MSK_CLUSTER`

### Common AWS Fields

All AWS entities include:
- `aws.account.id` - AWS account identifier
- `aws.region` - AWS region (e.g., us-east-1)
- `aws.resource.id` - Unique resource identifier
- `aws.resource.name` - Resource name
- `aws.arn` - Amazon Resource Name
- `aws.vpc.id` - VPC identifier (for VPC-attached resources)
- `aws.subnet.id` - Subnet identifier
- `aws.availability_zone` - Availability zone
- `aws.security_group.id` - Security group IDs (array)
- `tags` - Resource tags (use `tags[TagName]`)

### Relationship Types

AWS entities use these relationship types:
- `is_attached_to` - Exclusive attachment (e.g., volume to instance)
- `uses` - Dependency relationship (e.g., instance uses security group)
- `runs_on` - Vertical relationship (e.g., instance runs on AZ)
- `is_part_of` - Composition (e.g., instance in cluster)
- `belongs_to` - Aggregation (e.g., service belongs to cluster)
- `balances` - Load balancing (e.g., target group balances instances)
- `balanced_by` - Reverse of balances

### AWS Metric Naming Convention

Dynatrace ingests AWS metrics and exposes them using this naming pattern:

```
cloud.aws.<service>.<MetricName>.By.<DimensionName>
```

The `<service>` is the lowercase AWS service name, `<MetricName>` is the original CloudWatch metric name (case-preserved), and `<DimensionName>` is the CloudWatch dimension used for splitting.

**EC2 examples:**

| CloudWatch metric | Dynatrace metric key |
|---|---|
| `CPUUtilization` (by InstanceId) | `cloud.aws.ec2.CPUUtilization.By.InstanceId` |
| `StatusCheckFailed` (by InstanceId) | `cloud.aws.ec2.StatusCheckFailed.By.InstanceId` |
| `NetworkIn` (by InstanceId) | `cloud.aws.ec2.NetworkIn.By.InstanceId` |
| `DiskReadOps` (by InstanceId) | `cloud.aws.ec2.DiskReadOps.By.InstanceId` |

**Other service examples:**

| CloudWatch metric | Dynatrace metric key |
|---|---|
| RDS `CPUUtilization` (by DBInstanceIdentifier) | `cloud.aws.rds.CPUUtilization.By.DBInstanceIdentifier` |
| Lambda `Invocations` (by FunctionName) | `cloud.aws.lambda.Invocations.By.FunctionName` |
| SQS `ApproximateNumberOfMessagesVisible` (by QueueName) | `cloud.aws.sqs.ApproximateNumberOfMessagesVisible.By.QueueName` |
| ELB `RequestCount` (by LoadBalancer) | `cloud.aws.elasticloadbalancingv2.RequestCount.By.LoadBalancer` |

To query a metric:

```dql-template
timeseries cpu = avg(cloud.aws.ec2.CPUUtilization.By.InstanceId),
           by: {dt.smartscape_source.id},
  from: now()-1h
| limit 10
```

**Important:** Never refer to these as "CloudWatch alerts" or "CloudWatch metrics" in output. Dynatrace monitors AWS resources natively through its AWS integration — these are **Dynatrace metrics** ingested from AWS.

---

## Query Patterns

All AWS queries build on four core patterns. Master these and adapt them to any entity type.

### Pattern 1: Resource Discovery

List resources by type, filter by account/region/VPC/tags, summarize counts:

```dql-template
smartscapeNodes "AWS_*"
| filter aws.account.id == "<AWS_ACCOUNT_ID>" and aws.region == "<AWS_REGION>"
| summarize count = count(), by: {type}
| sort count desc
```

To list a specific type, replace `"AWS_*"` with the entity type (e.g., `"AWS_EC2_INSTANCE"`). Add `| fields name, aws.account.id, aws.region, ...` to select specific columns. Use `tags[TagName]` for tag-based filtering.

### Pattern 2: Configuration Parsing

Parse `aws.object` JSON for detailed configuration fields:

```dql-template
smartscapeNodes "AWS_RDS_DBINSTANCE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd engine = awsjson[configuration][engine]
| summarize db_count = count(), by: {engine, aws.region}
```

Common configuration fields by service:
- **EC2:** `instanceType`, `state[name]`, `networkInterfaces[0][association][publicIp]`
- **RDS:** `engine`, `multiAZ`, `publiclyAccessible`, `storageEncrypted`, `dbInstanceClass`, `storageType`
- **EBS:** `volumeType`, `size`, `state`
- **Lambda:** `runtime`, `memorySize`
- **LB:** `scheme`, `dnsName`
- **KMS:** `keyState`, `keyUsage`
- **ASG:** `minSize`, `maxSize`, `desiredCapacity`
- **Subnet:** `availableIpAddressCount`, `cidrBlock`
- **S3:** `versioningConfiguration[status]`
- **SG:** `securityGroups` (array, use `arraySize()` to count)

### Pattern 3: Relationship Traversal

Follow relationships between resources:

```dql-template
smartscapeNodes "AWS_ELASTICLOADBALANCINGV2_LOADBALANCER"
| parse aws.object, "JSON:awsjson"
| fieldsAdd dnsName = awsjson[configuration][dnsName], scheme = awsjson[configuration][scheme]
| traverse "balanced_by", "AWS_ELASTICLOADBALANCINGV2_TARGETGROUP", direction:backward, fieldsKeep:{dnsName, id}
| fieldsAdd targetGroupName = aws.resource.name
| traverse "balances", "AWS_EC2_INSTANCE", fieldsKeep: {targetGroupName, id}
| fieldsAdd loadBalancerDnsName = dt.traverse.history[-2][dnsName],
            loadBalancerId = dt.traverse.history[-2][id],
            targetGroupId = dt.traverse.history[-1][id]
```

Key traversal pairs:
- **LB → Target Groups:** `traverse "balanced_by", "AWS_ELASTICLOADBALANCINGV2_TARGETGROUP", direction:backward`
- **Target Group → Instances:** `traverse "balances", "AWS_EC2_INSTANCE"`
- **Target Group → Lambda Function:** `traverse "balances", "AWS_LAMBDA_FUNCTION"`
- **ECS Service → Cluster:** `traverse "belongs_to", "AWS_ECS_CLUSTER"`
- **ECS Service → Task Def:** `traverse "uses", "AWS_ECS_TASKDEFINITION"`
- **RDS Instance → Cluster:** `traverse "is_part_of", "AWS_RDS_DBCLUSTER"`
- **RDS Cluster → KMS Key:** `traverse "uses", "AWS_KMS_KEY"`
- **Instance → SG:** `traverse "uses", "AWS_EC2_SECURITYGROUP"`
- **Instance → Availability Zone:** `traverse "runs_on", "AWS_AVAILABILITY_ZONE"`
- **Instance → Subnet:** `traverse "is_attached_to", "AWS_EC2_SUBNET"`
- **Instance → VPC:** `traverse "is_attached_to", "AWS_EC2_VPC"`
- **Instance → Volume:** `traverse "is_attached_to", "AWS_EC2_VOLUME", direction: backward`
- **Lambda Function → IAM Role:** `traverse "uses", "AWS_IAM_ROLE"`
- **Lambda Function → Api Gateway V2:** `traverse "uses", "AWS_APIGATEWAYV2_INTEGRATION", direction: backward`
- **Instance → HOST:** `traverse "runs_on", "HOST", direction: backward`
- **SG blast radius:** query instances, traverse to SGs, `summarize count(), by: {sg.name}`
- Use `fieldsKeep` to carry fields through traversals, `dt.traverse.history[-N]` to access ancestor fields

### Pattern 4: Tag-Based Ownership

Group resources by any tag for ownership/chargeback:

```dql-template
smartscapeNodes "AWS_*"
| filter isNotNull(tags[<TAG_NAME>])
| summarize resource_count = count(), by: {tags[<TAG_NAME>], type}
| sort resource_count desc
```

Replace `CostCenter` with any tag: `Owner`, `Team`, `Project`, `Environment`, `Application`, `Department`, `BusinessUnit`. Replace `"AWS_*"` with a specific type to scope to one service.

Find untagged resources: `| filter arraySize(tags) == 0`

---

## Reference Guide

Load reference files for detailed queries when the core patterns above need service-specific adaptation.

| Reference | When to load                                                     | Key content |
|---|------------------------------------------------------------------|---|
| [vpc-networking-security.md](references/vpc-networking-security.md) | VPC topology, security groups, subnets, NAT, VPN, peering        | VPC resource mapping, SG blast radius, public IP detection |
| [database-monitoring.md](references/database-monitoring.md) | RDS, DynamoDB, ElastiCache, Redshift                             | Multi-AZ checks, engine distribution, subnet groups, dependencies |
| [serverless-containers.md](references/serverless-containers.md) | Lambda, ECS, EKS, App Runner                                     | VPC-attached functions, service-to-cluster mapping, container networking |
| [load-balancing-api.md](references/load-balancing-api.md) | ALB/NLB topology, API Gateway, CloudFront                        | LB→TG→Instance traversal, listener config, API stage management |
| [messaging-event-streaming.md](references/messaging-event-streaming.md) | SQS, SNS, EventBridge, Kinesis, MSK                              | Queue/topic inventory, streaming analysis, name pattern matching |
| [resource-management.md](references/resource-management.md) | Resource audits, tag compliance, lifecycle                       | Unattached resources, deleted resources, tag coverage analysis |
| [cost-optimization.md](references/cost-optimization.md) | Cost savings, unused resources, sizing                           | EBS costs, instance types, runtime distribution, snapshot analysis |
| [capacity-planning.md](references/capacity-planning.md) | Capacity analysis, scaling, IP utilization                       | ASG headroom, subnet IP counts, ECS desired vs running |
| [security-compliance.md](references/security-compliance.md) | Security audits, encryption, public access                       | SG rule analysis (0.0.0.0/0, open ports), S3 public access block, EBS encryption, SG blast radius, public DB/LB detection, IAM roles |
| [resource-ownership.md](references/resource-ownership.md) | Chargeback, ownership, cost allocation                           | Tag-based grouping, multi-account summaries |
| [events.md](references/events.md) | Load to check Auto Scaling, Health, and CloudFormation events | CloudFormation, Auto Scaling, AWS Health events |
| [workload-detection.md](references/workload-detection.md) | Load to determine orchestration context and resolution path      | LB, ASG, ECS, EKS, Batch detection for blast radius analysis |
| [metrics-performance.md](references/metrics-performance.md) | Load to query metric timeseries for a specific resource          | DQL timeseries patterns for EC2, Lambda, RDS, SQS, ELB, ECS, DynamoDB |

---

## Best Practices

### Query Optimization
1. Filter early by account and region
2. Use specific entity types (avoid `"AWS_*"` wildcards when possible)
3. Limit results with `| limit N` for exploration
4. Use `isNotNull()` checks before accessing nested fields

### Configuration Parsing
1. Always parse `aws.object` with JSON parser: `parse aws.object, "JSON:awsjson"`
2. Use consistent field naming: `fieldsAdd configField = awsjson[configuration][field]`
3. Check for null values after parsing
4. Use `toString()` for complex nested objects

### Security Fields
1. Security group IDs are arrays - use `contains()` or `expand`
2. Parse `aws.object` for detailed security context
3. Check `publiclyAccessible`, `storageEncrypted`, and similar flags

### Tagging Strategy
1. Use `tags[TagName]` for filtering
2. Check `arraySize(tags)` for untagged resources
3. Track tag coverage with summarize operations

---

## Limitations and Notes

### Smartscape Limitations
- AWS object configuration requires parsing with `parse aws.object, "JSON:awsjson"`
- AWS metrics are available as Dynatrace metrics using the `cloud.aws.*` naming convention (see [AWS Metric Naming Convention](#aws-metric-naming-convention))
- Resource discovery depends on AWS integration configuration
- Tag synchronization may have slight delays

### Relationship Traversal
- Use `direction:backward` for reverse relationships (e.g., target group → load balancer)
- Use `fieldsKeep` to maintain important fields through traversal
- Access traversal history with `dt.traverse.history[-N]`
- Complex topologies may require multiple traverse operations

### General Tips
- Use `getNodeName()` for human-readable resource names
- Handle null values gracefully with `isNotNull()` and `isNull()`
- Combine region and account filters for large environments
- Use `countDistinct()` for unique resource counts
