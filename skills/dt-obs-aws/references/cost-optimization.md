# AWS Cost Optimization

Identify cost savings opportunities and optimize AWS spending.

## Table of Contents

- [Compute Costs](#compute-costs)
- [Storage Costs](#storage-costs)
- [Network Costs](#network-costs)
- [Database Costs](#database-costs)
- [Serverless & Cache Costs](#serverless--cache-costs)
- [Infrastructure Management Costs](#infrastructure-management-costs)
- [Idle Resource Detection](#idle-resource-detection)

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

Analyze IP addresses not associated with any resource:

```dql
smartscapeNodes "AWS_EC2_EIP"
| parse aws.object, "JSON:awsjson"
| fieldsAdd associationId = awsjson[configuration][associationId],
            instanceId = awsjson[configuration][instanceId],
            networkInterfaceId = awsjson[configuration][networkInterfaceId],
            publicIp = awsjson[configuration][publicIp],
            allocationId = awsjson[configuration][allocationId],
            domain = awsjson[configuration][domain]
| filter isNull(associationId) and isNull(instanceId) and isNull(networkInterfaceId)
| fields name, publicIp, allocationId, domain, aws.account.id, aws.region
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

## Idle Resource Detection

Idle resources are running and incurring charges but performing no useful work. Detecting them is one of the highest-impact cost optimization activities because idle resources represent pure waste — they can be terminated, downsized, or cleaned up with no service impact.

The queries below use metric thresholds and entity state to surface idle candidates across common AWS resource types.

### EC2 — Low CPU Utilization

Instances averaging less than 5% CPU over 14 days are likely idle or significantly over-provisioned. These are candidates for downsizing to a smaller instance type or termination if no longer needed.

```dql
timeseries avg_cpu = avg(cloud.aws.ec2.CPUUtilization.By.InstanceId),
  by: { dt.smartscape_source.id },
  from: now()-14d
| filter isNotNull(avg_cpu) 
| fieldsAdd avg_cpu_val = arrayAvg(avg_cpu)
| filter avg_cpu_val < 5.0
| sort avg_cpu_val asc
| fields dt.smartscape_source.id, avg_cpu_val
```

**What to look for:**

- Instances at 0% CPU are almost certainly unused and safe to terminate after confirming no attached services depend on them.
- Instances between 1–5% may be running scheduled jobs or health checks — verify with network I/O metrics before acting.
- Cross-reference with the [Compute Costs](#compute-costs) query to see the instance types involved; large instance types with low CPU yield the biggest savings.

### Lambda — Zero Invocations

Functions with zero invocations over 30 days are likely abandoned or replaced. They still consume storage for deployment packages and may hold reserved concurrency that blocks other functions.

```dql
timeseries total_invocations = sum(cloud.aws.lambda.Invocations.By.FunctionName),
  by: { dt.smartscape_source.id },
  from: now()-30d
| fieldsAdd total = arraySum(total_invocations)
| filter total == 0 or isNull(total)
| fields dt.smartscape_source.id, total
```

**What to look for:**

- Functions with zero invocations for 30 days are strong candidates for deletion.
- Check whether the function is triggered by a schedule that runs less frequently than 30 days (e.g., quarterly reports) before removing.
- Review CloudFormation or IaC ownership to avoid deleting functions that would be recreated on the next deployment.

### DynamoDB — Zero Consumed Capacity

Tables with no read or write activity over 30 days are likely unused. DynamoDB tables in provisioned mode incur charges for allocated capacity even with zero traffic.

```dql
timeseries {
  reads = sum(cloud.aws.dynamodb.ConsumedReadCapacityUnits.By.TableName),
           writes = sum(cloud.aws.dynamodb.ConsumedWriteCapacityUnits.By.TableName)
},
  by: { dt.smartscape_source.id },
  from: now()-30d
| fieldsAdd total_reads = arraySum(reads), total_writes = arraySum(writes)
| filter (total_reads == 0 or isNull(total_reads)) and (total_writes == 0 or isNull(total_writes))
| fields dt.smartscape_source.id, total_reads, total_writes
```

**What to look for:**

- Tables in provisioned mode with zero consumed capacity are paying for unused read/write units — switch to on-demand or delete.
- Tables in on-demand mode with zero traffic have minimal cost but still incur storage charges if they hold data.
- Check for DynamoDB Streams or global table replicas that may justify keeping the table even without direct application traffic.

### EBS — Unattached Volumes

Volumes in the `available` state are not attached to any instance. They still incur storage charges based on size and volume type.

```dql
smartscapeNodes "AWS_EC2_VOLUME"
| parse aws.object, "JSON:awsjson"
| fieldsAdd volumeType = awsjson[configuration][volumeType],
            size = awsjson[configuration][size],
            state = awsjson[configuration][state]
| filter state == "available"
| fields name, aws.resource.id, aws.region, volumeType, size
| sort size desc
```

**What to look for:**

- Large `gp3` or `io2` volumes in `available` state are the most expensive idle resources — prioritize these.
- Volumes left behind after instance termination are a common source of waste. Create a snapshot before deleting if the data may be needed.
- Cross-reference with snapshots to confirm backup exists before cleanup.

### EBS — Attached but Zero I/O

Volumes that are attached to instances but have had no read or write operations over 14 days. These may be leftover data volumes or misconfigured mounts.

```dql
timeseries {
  reads = sum(cloud.aws.ebs.VolumeReadOps.By.VolumeId),
  writes = sum(cloud.aws.ebs.VolumeWriteOps.By.VolumeId)
},
by: { dt.smartscape_source.id },
from: now()-14d
| fieldsAdd total_reads = arraySum(reads), total_writes = arraySum(writes)
| filter (total_reads == 0 or isNull(total_reads)) and (total_writes == 0 or isNull(total_writes))
| fields dt.smartscape_source.id, total_reads, total_writes
```

**What to look for:**

- Volumes with zero I/O that are attached to running instances may be mounted but unused — check the instance OS for unmounted or orphaned block devices.
- Some volumes serve as infrequently-accessed archives; confirm the access pattern before detaching.
- Detaching and snapshotting zero-I/O volumes can recover ongoing storage costs while preserving data.

### Summary

| Resource | Idle Signal | Lookback | Recommended Action |
|---|---|---|---|
| EC2 Instance | Avg CPU < 5% | 14 days | Downsize instance type or terminate |
| Lambda Function | Zero invocations | 30 days | Delete function and deployment package |
| DynamoDB Table | Zero consumed read/write capacity | 30 days | Switch to on-demand or delete table |
| EBS Volume | State is `available` (unattached) | Current | Snapshot and delete |
| EBS Volume | Zero read/write ops (attached) | 14 days | Detach, snapshot, and delete |
