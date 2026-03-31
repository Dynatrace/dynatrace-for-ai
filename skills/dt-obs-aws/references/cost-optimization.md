# AWS Cost Optimization

Identify cost savings opportunities and optimize AWS spending.

## Table of Contents

- [Compute Costs](#compute-costs)
- [Storage Costs](#storage-costs)
- [Network Costs](#network-costs)
- [Database Costs](#database-costs)
- [Serverless & Cache Costs](#serverless--cache-costs)
- [Infrastructure Management Costs](#infrastructure-management-costs)

## Compute Costs

Analyze running instance types for right-sizing:

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd instanceType = awsjson[configuration][instanceType],
            state = awsjson[configuration][state][name]
| filter state == "running"
| summarize instance_count = count(), by: {instanceType, aws.region}
| sort instance_count desc
```

Find recently terminated instances:

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| filter aws.state == "terminated"
| fields name, aws.resource.id, aws.region, aws.account.id, id
| limit 20
```

## Storage Costs

Analyze EBS volumes by type and state (identify unattached volumes):

```dql
smartscapeNodes "AWS_EC2_VOLUME"
| parse aws.object, "JSON:awsjson"
| fieldsAdd volumeType = awsjson[configuration][volumeType],
            size = awsjson[configuration][size],
            state = awsjson[configuration][state]
| summarize total_volumes = count(), total_size_gb = sum(size), by: {volumeType, state}
| sort total_size_gb desc
```

Check S3 bucket versioning for storage cost analysis:

```dql
smartscapeNodes "AWS_S3_BUCKET"
| parse aws.object, "JSON:awsjson"
| fieldsAdd versioning = awsjson[configuration][versioningConfiguration][status]
| summarize bucket_count = count(), by: {versioning, aws.region}
```

Count RDS cluster snapshots for backup cost analysis:

```dql
smartscapeNodes "AWS_RDS_DBCLUSTERSNAPSHOT"
| parse aws.object, "JSON:awsjson"
| fieldsAdd snapshotType = awsjson[configuration][snapshotType]
| summarize snapshot_count = count(), by: {snapshotType, aws.region}
| sort snapshot_count desc
```

## Network Costs

Analyze NAT gateway costs by VPC:

```dql
smartscapeNodes "AWS_EC2_NATGATEWAY"
| parse aws.object, "JSON:awsjson"
| fieldsAdd state = awsjson[configuration][state]
| filter state == "available"
| summarize nat_count = count(), by: {aws.vpc.id, aws.availability_zone}
| sort nat_count desc
```

Analyze VPC endpoint types for cost optimization:

```dql
smartscapeNodes "AWS_EC2_VPCENDPOINT"
| parse aws.object, "JSON:awsjson"
| fieldsAdd vpcEndpointType = awsjson[configuration][vpcEndpointType],
            serviceName = awsjson[configuration][serviceName]
| summarize endpoint_count = count(), by: {vpcEndpointType, serviceName, aws.vpc.id}
| sort endpoint_count desc
```

## Database Costs

Analyze RDS instance costs by class:

```dql
smartscapeNodes "AWS_RDS_DBINSTANCE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd instanceClass = awsjson[configuration][dbInstanceClass]
| summarize db_count = count(), by: {instanceClass, aws.region}
| sort db_count desc
```

## Serverless & Cache Costs

Identify Lambda runtime distribution (for upgrade planning):

```dql
smartscapeNodes "AWS_LAMBDA_FUNCTION"
| parse aws.object, "JSON:awsjson"
| fieldsAdd runtime = awsjson[configuration][runtime]
| summarize function_count = count(), by: {runtime, aws.region}
| sort function_count desc
```

Review ElastiCache node types:

```dql
smartscapeNodes "AWS_ELASTICACHE_REPLICATIONGROUP"
| parse aws.object, "JSON:awsjson"
| fieldsAdd nodeType = awsjson[configuration][cacheNodeType]
| summarize cluster_count = count(), by: {nodeType, aws.region}
| sort cluster_count desc
```

## Infrastructure Management Costs

Find KMS keys pending deletion:

```dql
smartscapeNodes "AWS_KMS_KEY"
| parse aws.object, "JSON:awsjson"
| fieldsAdd keyState = awsjson[configuration][keyState]
| filter keyState == "PendingDeletion"
| fields name, aws.resource.id, aws.region, aws.account.id
```

Review CloudFormation stack states:

```dql
smartscapeNodes "AWS_CLOUDFORMATION_STACK"
| parse aws.object, "JSON:awsjson"
| fieldsAdd stackStatus = awsjson[configuration][stackStatus]
| summarize stack_count = count(), by: {stackStatus, aws.region}
| sort stack_count desc
```
