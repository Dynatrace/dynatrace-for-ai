# AWS Metrics & Performance

DQL timeseries patterns for AWS CloudWatch-sourced metrics. Use during investigation to determine whether a resource is saturated, erroring, or slow.

## Query Template

The `timeseries` command with `by: { dt.smartscape_source.id}` splits results by Dynatrace entity, and a pipe `| filter` stage scopes the series to a specific resource. The `By.<DimensionName>` suffix in the metric key is the CloudWatch dimension used to align the metric to the entity.

```dql-template
timeseries cpu = avg(cloud.aws.ec2.CPUUtilization.By.InstanceId), by: { dt.smartscape_source.id},
  from: <PROBLEM_START - 30m>, to: <PROBLEM_END + 15m>
| filter dt.smartscape_source.id == toSmartscapeId("<ROOT_CAUSE_ENTITY_ID>")
```

Replace `cloud.aws.ec2.CPUUtilization.By.InstanceId` with the relevant metric key, and `<ROOT_CAUSE_ENTITY_ID>` with the Dynatrace entity ID (e.g. `AWS_EC2_INSTANCE-1F335452CC14B245`). Omit the `| filter` clause to get all instances of that metric.

> **Time windows:** The template above uses `<PROBLEM_START>` and `<PROBLEM_END>` for scoping queries to a specific incident window. The per-service examples below use `from: now()-1h` for simplicity — substitute your incident timestamps when investigating a specific problem.

---

## EC2 Metrics

| Metric key | Description | Unit | Investigation threshold |
|---|---|---|---|
| `cloud.aws.ec2.CPUUtilization.By.InstanceId` | CPU utilization | % | > 85% sustained |
| `cloud.aws.ec2.NetworkIn.By.InstanceId` | Inbound network traffic | Bytes | Spike or drop vs baseline |
| `cloud.aws.ec2.NetworkOut.By.InstanceId` | Outbound network traffic | Bytes | Spike or drop vs baseline |
| `cloud.aws.ec2.StatusCheckFailed.By.InstanceId` | Instance or system status check failures | Count | > 0 |
| `cloud.aws.ec2.DiskReadOps.By.InstanceId` | Disk read operations | Count | Spike vs baseline |
| `cloud.aws.ec2.DiskWriteOps.By.InstanceId` | Disk write operations | Count | Spike vs baseline |

Check CPU utilization for a specific instance:

```dql
timeseries cpu = avg(cloud.aws.ec2.CPUUtilization.By.InstanceId), by: { dt.smartscape_source.id},
  from: now()-1h
| filter dt.smartscape_source.id == toSmartscapeId("<ROOT_CAUSE_ENTITY_ID>")
```

Check status check failures (non-zero = instance-level problem):

```dql
timeseries checks = max(cloud.aws.ec2.StatusCheckFailed.By.InstanceId), by: { dt.smartscape_source.id},
  from: now()-1h
| filter dt.smartscape_source.id == toSmartscapeId("<ROOT_CAUSE_ENTITY_ID>")
```

---

## Lambda Metrics

| Metric key | Description | Unit | Investigation threshold |
|---|---|---|---|
| `cloud.aws.lambda.Invocations.By.FunctionName` | Total function invocations | Count | Drop vs baseline (may indicate upstream issue) |
| `cloud.aws.lambda.Errors.By.FunctionName` | Function execution errors | Count | > 0 during incident |
| `cloud.aws.lambda.Duration.By.FunctionName` | Execution duration | Milliseconds | Approaching timeout limit |
| `cloud.aws.lambda.Throttles.By.FunctionName` | Throttled invocations | Count | > 0 (concurrency limit hit) |
| `cloud.aws.lambda.ConcurrentExecutions.By.FunctionName` | Concurrent executions in flight | Count | Near account/function concurrency limit |

Check error rate and duration together:

```dql
timeseries errors = sum(cloud.aws.lambda.Errors.By.FunctionName),
           duration = avg(cloud.aws.lambda.Duration.By.FunctionName),
           by: { dt.smartscape_source.id},
  from: now()-1h
| filter dt.smartscape_source.id == toSmartscapeId("<LAMBDA_ROOT_CAUSE_ENTITY_ID>")
```

> **Note:** `<LAMBDA_ROOT_CAUSE_ENTITY_ID>` is the Dynatrace entity ID for the Lambda function (e.g., `AWS_LAMBDA_FUNCTION-ABC123`).

---

## RDS Metrics

| Metric key | Description | Unit | Investigation threshold |
|---|---|---|---|
| `cloud.aws.rds.CPUUtilization.By.DBInstanceIdentifier` | Database CPU utilization | % | > 85% sustained |
| `cloud.aws.rds.DatabaseConnections.By.DBInstanceIdentifier` | Active database connections | Count | Near `max_connections` limit |
| `cloud.aws.rds.FreeStorageSpace.By.DBInstanceIdentifier` | Free storage remaining | Bytes | Trending toward 0 |
| `cloud.aws.rds.ReadLatency.By.DBInstanceIdentifier` | Average read I/O latency | Seconds | > 0.020s (20ms) for production workloads |
| `cloud.aws.rds.WriteLatency.By.DBInstanceIdentifier` | Average write I/O latency | Seconds | > 0.020s (20ms) for production workloads |

Check CPU and connections for a specific RDS instance:

```dql
timeseries cpu = avg(cloud.aws.rds.CPUUtilization.By.DBInstanceIdentifier),
           connections = avg(cloud.aws.rds.DatabaseConnections.By.DBInstanceIdentifier),
           by: { dt.smartscape_source.id},
  from: now()-1h
| filter dt.smartscape_source.id == toSmartscapeId("<RDS_ROOT_CAUSE_ENTITY_ID>")
```

> **Note:** `<RDS_ROOT_CAUSE_ENTITY_ID>` is the Dynatrace entity ID for the RDS instance (e.g., `AWS_RDS_DBINSTANCE-ABC123`).

---

## SQS Metrics

| Metric key | Description | Unit | Investigation threshold |
|---|---|---|---|
| `cloud.aws.sqs.ApproximateNumberOfMessagesVisible.By.QueueName` | Messages waiting to be processed | Count | Growing over time (consumer lag) |
| `cloud.aws.sqs.NumberOfMessagesSent.By.QueueName` | Messages sent per period | Count | Drop vs baseline |
| `cloud.aws.sqs.ApproximateAgeOfOldestMessage.By.QueueName` | Age of oldest unprocessed message | Seconds | Exceeds your SLA threshold |

Check queue depth over time:

```dql
timeseries depth = max(cloud.aws.sqs.ApproximateNumberOfMessagesVisible.By.QueueName),
           age = max(cloud.aws.sqs.ApproximateAgeOfOldestMessage.By.QueueName),
           by: { dt.smartscape_source.id},
  from: now()-1h
| filter dt.smartscape_source.id == toSmartscapeId("<SQS_ROOT_CAUSE_ENTITY_ID>")
```

> **Note:** `<SQS_ROOT_CAUSE_ENTITY_ID>` is the Dynatrace entity ID for the SQS queue (e.g., `AWS_SQS_QUEUE-ABC123`).

---

## ALB Metrics

| Metric key | Description | Unit | Investigation threshold |
|---|---|---|---|
| `cloud.aws.applicationelb.RequestCount.By.LoadBalancer` | Total requests processed | Count | Drop vs baseline |
| `cloud.aws.applicationelb.TargetResponseTime.By.LoadBalancer` | Average response time from targets | Seconds | > p99 baseline |
| `cloud.aws.applicationelb.HTTPCode_ELB_5XX_Count.By.LoadBalancer` | 5xx errors from targets | Count | > 0 during incident |
| `cloud.aws.applicationelb.HealthyHostCount.By.TargetGroup` | Healthy targets per target group | Count | Drop (indicates unhealthy instances) |

> **Important:** `HealthyHostCount.By.TargetGroup` is scoped to a target group entity — use the Dynatrace entity ID for the target group as `<ROOT_CAUSE_ENTITY_ID>` when running that query.

Check request count and 5xx errors for a load balancer:

```dql
timeseries requests = sum(cloud.aws.applicationelb.RequestCount.By.LoadBalancer),
           errors5xx = sum(cloud.aws.applicationelb.HTTPCode_ELB_5XX_Count.By.LoadBalancer),
           by: { dt.smartscape_source.id},
  from: now()-1h
//| filter dt.smartscape_source.id == toSmartscapeId("<ROOT_CAUSE_ENTITY_ID>")
```
> **Important:**  If this returns empty the load balancer might not have any traffic during the selected time window.

Check healthy host count for a specific target group:

```dql
timeseries healthy = min(cloud.aws.applicationelb.HealthyHostCount.By.LoadBalancer.TargetGroup),
  by: { dt.smartscape_source.id , TargetGroup},
  from: now()-1h
| filter dt.smartscape_source.id == toSmartscapeId("<ROOT_CAUSE_ENTITY_ID>")
```

---

## ECS Metrics

| Metric key | Description | Unit | Investigation threshold                                                                                                                              |
|---|---|---|------------------------------------------------------------------------------------------------------------------------------------------------------|
| `cloud.aws.ecs.CPUUtilization.By.ClusterName.ServiceName` | ECS service CPU utilization | % | > 85% sustained                                                                                                                                      |
| `cloud.aws.ecs.MemoryUtilization.By.ClusterName.ServiceName` | ECS service memory utilization | % | > 85% sustained                                                                                                                                      |
| `cloud.aws.ecs_containerinsights.RunningTaskCount.By.ClusterName.ServiceName` | Number of running tasks | Count | Drop vs desired count (task crash loop or placement failure) **Important:** This metric is part of ECS Container Insights and might not be available |

Check CPU and memory for an ECS service:

```dql
timeseries cpu = avg(cloud.aws.ecs.CPUUtilization.By.ClusterName.ServiceName),
           mem = avg(cloud.aws.ecs.MemoryUtilization.By.ClusterName.ServiceName),
           by: { dt.smartscape_source.id},
  from: now()-1h
| filter dt.smartscape_source.id == toSmartscapeId("<ECS_CLUSTER_ROOT_CAUSE_ENTITY_ID>")
```

> **Note:** `<ECS_CLUSTER_ROOT_CAUSE_ENTITY_ID>` is the Dynatrace entity ID for the ECS cluster (e.g., `AWS_ECS_CLUSTER-ABC123`).

---

## DynamoDB Metrics

| Metric key | Description | Unit | Investigation threshold |
|---|---|---|---|
| `cloud.aws.dynamodb.ConsumedReadCapacityUnits.By.TableName` | Read capacity consumed | Count | Approaching provisioned RCU limit |
| `cloud.aws.dynamodb.ConsumedWriteCapacityUnits.By.TableName` | Write capacity consumed | Count | Approaching provisioned WCU limit |
| `cloud.aws.dynamodb.SystemErrors.By.TableName` | DynamoDB system errors | Count | > 0 |
| `cloud.aws.dynamodb.SuccessfulRequestLatency.By.Operation.TableName` | Successful request latency | Milliseconds | > 10ms (single-digit millisecond expected) |

Check capacity consumption and latency for a table:

```dql
timeseries reads = avg(cloud.aws.dynamodb.ConsumedReadCapacityUnits.By.TableName),
           writes = avg(cloud.aws.dynamodb.ConsumedWriteCapacityUnits.By.TableName),
           latency = avg(cloud.aws.dynamodb.SuccessfulRequestLatency.By.Operation.TableName),
           by: { dt.smartscape_source.id, TableName},
  from: now()-1h
| filter dt.smartscape_source.id == toSmartscapeId("<DYNAMODB_TABLE_ROOT_CAUSE_ENTITY_ID>")
```

> **Note:** `<DYNAMODB_TABLE_ROOT_CAUSE_ENTITY_ID>` is the Dynatrace entity ID for the DynamoDB table (e.g., `AWS_DYNAMODB_TABLE-ABC123`).


Check if provisioned capacity is being approached:

```dql
timeseries readsProvisioned = avg(cloud.aws.dynamodb.ProvisionedReadCapacityUnits.By.TableName),
    writesProvisioned = avg(cloud.aws.dynamodb.ProvisionedWriteCapacityUnits.By.TableName),
    readsConsumed = avg(cloud.aws.dynamodb.ConsumedReadCapacityUnits.By.TableName),
    writesConsumed = avg(cloud.aws.dynamodb.ConsumedWriteCapacityUnits.By.TableName),
  by: { dt.smartscape_source.id, TableName},
  from: now()-1h
| filter dt.smartscape_source.id == toSmartscapeId("<DYNAMODB_TABLE_ROOT_CAUSE_ENTITY_ID>")
```    

> **Note:** `<DYNAMODB_TABLE_ROOT_CAUSE_ENTITY_ID>` is the Dynatrace entity ID for the DynamoDB table (e.g., `AWS_DYNAMODB_TABLE-ABC123`).
> **Note:** `This can be empty if the table is using on_demand instead of provisioned throughput`).


---

## Combining Entity Queries with Metrics

Find a set of entities by filter, then query metrics for all of them. Example: are all EC2 instances in a VPC experiencing high CPU, or just one?

**Step 1 — Find resource IDs for the group:**

```dql
smartscapeNodes "AWS_EC2_INSTANCE"
| filter aws.vpc.id == "<VPC_ID>"
| fields name, aws.resource.id
```

**Step 2 — Query metrics for all instances in the group (no filter = all series):**

```dql
timeseries cpu = avg(cloud.aws.ec2.CPUUtilization.By.InstanceId),
           by: { dt.smartscape_source.id},
  from: now()-1h
```

Cross-reference the `dt.smartscape_source.id` dimension values against the entity IDs from Step 1 to identify which instances in the VPC are affected.

---

## Metric Availability Note

Not all metrics are ingested by default — depends on which services are enabled in the AWS integration configuration. If a timeseries query returns no data:

1. Verify the entity exists: run the `smartscapeNodes` query from Step 1 of `rca-workflow.md`
2. Confirm the metric is collected in the AWS integration settings

Do **not** interpret empty timeseries results as "no problem" — it may mean the metric is not configured for this resource type.
