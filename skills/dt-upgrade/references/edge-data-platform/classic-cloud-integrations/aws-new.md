# AWS New Connection Reference

Distilled reference for the new AWS connection (Smartscape on Grail).
## Contents
- [Architecture](#architecture)
- [Entity Model](#entity-model)
- [Metric Key Format](#metric-key-format)
- [Key Detection Queries](#key-detection-queries)
- [Migration Notes](#migration-notes)
---

## Architecture

| Property | Value |
|---|---|
| Pipeline | Cloud-native Data Acquisition (DA) |
| Settings schema | `builtin:hyperscaler-authentication.connections.aws` |
| Auth | IAM cross-account role-based or AWS Web Identity |
| `dt.da.source` | `aws-metric-poller` (metrics), `aws-smartscape-poller-*` (topology) |
| Entity model | Smartscape on Grail (`AWS_*` types) |
| ActiveGate | Not required |
| Polling interval | 5 minutes (7-minute delay) |

---

## Key Smartscape Entity Types

| Smartscape Type | AWS Service |
|---|---|
| `AWS_ACCOUNT` | Account (topology container) |
| `AWS_REGION` | Region (topology container) |
| `AWS_EC2_INSTANCE` | EC2 |
| `AWS_EC2_VOLUME` | EBS |
| `AWS_LAMBDA_FUNCTION` | Lambda |
| `AWS_RDS_DBINSTANCE` | RDS |
| `AWS_RDS_DBCLUSTER` | Aurora |
| `AWS_DYNAMODB_TABLE` | DynamoDB |
| `AWS_S3_BUCKET` | S3 |
| `AWS_ELASTICLOADBALANCINGV2_LOADBALANCER` | ALB/NLB |
| `AWS_AUTOSCALING_AUTOSCALINGGROUP` | Auto Scaling |
| `AWS_ELASTICACHE_CACHECLUSTER` | ElastiCache |
| `AWS_EKS_CLUSTER` | EKS |
| `AWS_CLOUDFRONT_DISTRIBUTION` | CloudFront |
| `AWS_SNS_TOPIC` | SNS |
| `AWS_EC2_NATGATEWAY` | NAT Gateway |
| `AWS_KINESISFIREHOSE_DELIVERYSTREAM` | Kinesis Firehose |
| `AWS_LOGS_LOGGROUP` | CloudWatch Logs |
| `AWS_ECR_REPOSITORY` | ECR |
| `AWS_ROUTE53_HEALTHCHECK` | Route 53 |

---

## Metric Key Format

```
cloud.aws.<service>.<MetricName>.By.<Dim1>.<Dim2>...
```

- Service: lowercase CloudWatch namespace (e.g., `ec2`, `lambda`, `rds`)
- MetricName: CloudWatch PascalCase name (e.g., `CPUUtilization`, `Invocations`)
- Dimensions: PascalCase, dot-separated, alphabetically ordered

### Enrichment Dimensions

| Dimension | Description |
|---|---|
| `dt.da.source` | `aws-metric-poller` |
| `dt.smartscape_source.type` | Entity type (e.g., `AWS_EC2_INSTANCE`) |
| `dt.smartscape_source.id` | Entity ID |
| `aws.account.id` | AWS account ID |
| `aws.region` | AWS region |
| `aws.tag.<Key>` | AWS tags (up to 20) |

### Dimensions NOT Present (vs Classic)

`dt.source_entity`, `dt.source_entity.type`, `dt.entity.cloud:aws:account`, `dt.source` — all absent on new connection metrics.

---

## Detection Queries

### Find all new connection metrics
```dql
fetch metric.series, from:now()-1h
| filter dt.da.source == "aws-metric-poller"
| summarize cnt=count(), by:{metric.key, dt.smartscape_source.type}
```

### List all AWS Smartscape entity types
```dql
smartscapeNodes "*"
| filter startsWith(type, "AWS_")
| summarize cnt=count(), by:{type}
| sort cnt desc
```

### Enumerate monitored accounts
```dql
smartscapeNodes AWS_ACCOUNT, from:now()-12h
| fields id, name, `aws.account.id`
```

### Detect new connections via Settings API
```
dtctl get settings --schema builtin:hyperscaler-authentication.connections.aws -o json
```

Only connections with `SVC:com.dynatrace.da` as a consumer perform metric/Smartscape polling.

---

## Consumers

| Consumer | Purpose |
|---|---|
| `SVC:com.dynatrace.da` | Metric polling + Smartscape topology |
| `APP:dynatrace.biz.carbon` | Cost & Carbon Optimization |
| `SVC:com.dynatrace.openpipeline` | Log/event pipeline ingest |
| `NONE` | Connection exists but inactive |

---

## Migration Notes

- Metric ingest is configurable and can be disabled — always combine Settings API + Smartscape + metric queries for complete detection.
- Classic entity IDs do NOT carry over to Smartscape. New entity IDs follow `<TYPE>-<HEX>` format.
- The shared `cloud.aws.*` prefix requires `dt.da.source` disambiguation. See [disambiguation.md](disambiguation.md).
