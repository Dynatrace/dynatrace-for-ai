# AWS Classic Connection Reference

Distilled reference for the classic AWS monitoring integration.

---

## Three Classic Flavours

AWS has three distinct classic metric ingestion paths:

| Flavour | Metric prefix (Grail) | Entity type | `dt.da.source` | `dt.source` |
|---|---|---|---|---|
| **Built-in polling** | `dt.cloud.aws.<service>.*` | Dedicated (e.g., `EC2_INSTANCE`) | null | null |
| **Non-built-in polling** | `cloud.aws.<service>.<snake_case>` | `CUSTOM_DEVICE` (`cloud:aws:*`) | null | null |
| **Metric Streams** | `cloud.aws.<service>.<camelCase>By<Dims>` | None (unless extension) | null | `"AWS Metric Streams"` |

---

## Built-in Entity Types

`EC2_INSTANCE`, `EBS_VOLUME`, `AWS_LAMBDA_FUNCTION`, `AUTO_SCALING_GROUP`, `AWS_APPLICATION_LOAD_BALANCER`, `AWS_NETWORK_LOAD_BALANCER`, `ELASTIC_LOAD_BALANCER`, `RELATIONAL_DATABASE_SERVICE`, `DYNAMO_DB_TABLE`, `AWS_CREDENTIALS`, `AWS_AVAILABILITY_ZONE`

## Non-Built-in Entity Types (Custom Device Sub-types)

`cloud:aws:s3`, `cloud:aws:rds`, `cloud:aws:aurora`, `cloud:aws:elasticachecustom`, `cloud:aws:sqs`, `cloud:aws:sns`, `cloud:aws:lambda`, `cloud:aws:cloud_front`, `cloud:aws:nat_gateway`, `cloud:aws:api_gateway`, `cloud:aws:billing`, `cloud:aws:wafv2`, `cloud:aws:kinesis`, `cloud:aws:redshift`, `cloud:aws:eks:cluster`, `cloud:aws:ecs`, `cloud:aws:ecs:cluster`, and many more.

Full list: `cloud:aws:acmprivateca`, `cloud:aws:api_gateway`, `cloud:aws:app_runner`, `cloud:aws:appstream`, `cloud:aws:appsync`, `cloud:aws:athena`, `cloud:aws:aurora`, `cloud:aws:autoscaling`, `cloud:aws:billing`, `cloud:aws:cloud_front`, `cloud:aws:cloudhsm`, `cloud:aws:cloudsearch`, `cloud:aws:codebuild`, `cloud:aws:datasync`, `cloud:aws:dax`, `cloud:aws:dms`, `cloud:aws:documentdb`, `cloud:aws:dxcon`, `cloud:aws:dynamodb`, `cloud:aws:ebs`, `cloud:aws:ec2_spot`, `cloud:aws:ecs`, `cloud:aws:ecs:cluster`, `cloud:aws:efs`, `cloud:aws:eks:cluster`, `cloud:aws:elasticache`, `cloud:aws:elasticbeanstalk`, `cloud:aws:elastictranscoder`, `cloud:aws:es`, `cloud:aws:events`, `cloud:aws:fsx`, `cloud:aws:gamelift`, `cloud:aws:glue`, `cloud:aws:inspector`, `cloud:aws:kafka`, `cloud:aws:lambda`, `cloud:aws:lex`, `cloud:aws:logs`, `cloud:aws:media_tailor`, `cloud:aws:mediaconnect`, `cloud:aws:mediapackagelive`, `cloud:aws:mediapackagevod`, `cloud:aws:nat_gateway`, `cloud:aws:neptune`, `cloud:aws:opsworks`, `cloud:aws:qldb`, `cloud:aws:rds`, `cloud:aws:redshift`, `cloud:aws:robomaker`, `cloud:aws:route53`, `cloud:aws:route53resolver`, `cloud:aws:s3`, `cloud:aws:sage_maker:endpoint`, `cloud:aws:sage_maker:endpoint_instance`, `cloud:aws:sns`, `cloud:aws:sqs`, `cloud:aws:storagegateway`, `cloud:aws:swf`, `cloud:aws:transfer`, `cloud:aws:transitgateway`, `cloud:aws:vpn`, `cloud:aws:wafv2`, `cloud:aws:workmail`, `cloud:aws:workspaces`

---

## Settings & Configuration

| Schema / API | Purpose |
|---|---|
| `builtin:cloud.aws` | Classic AWS connection settings (Settings 2.0) |
| Config API: `GET /api/config/v1/aws/credentials` | Legacy classic connection config |
| `builtin:hyperscaler-authentication.connections.aws` | **New** connection (NOT classic) |

---

## Key Detection Queries

### Enumerate classic connections
```dql
fetch dt.entity.aws_credentials, from:now()-12h
| fieldsAdd awsAccountId, entity.name, id, lifetime
| fieldsRemove can_access
```

### Classic metric source classification
```dql
fetch metric.series, from:now()-1h
| filter startsWith(metric.key, "cloud.aws.") OR startsWith(metric.key, "dt.cloud.aws.")
| summarize cnt=count(), by:{dt.da.source, dt.source_entity.type, dt.source}
| sort cnt desc
```

### Custom device type counts
```dql
fetch dt.entity.custom_device
| filter contains(toString(entity.type), "cloud:aws")
| summarize cnt=count(), by:{entity.type}
| sort cnt desc
```

---

## Entity Hierarchy

```
AWS_CREDENTIALS (connection)
├── AWS_AVAILABILITY_ZONE
├── EC2_INSTANCE, EBS_VOLUME, AWS_LAMBDA_FUNCTION (built-in)
├── AUTO_SCALING_GROUP, load balancers, RDS, DynamoDB (built-in)
└── CUSTOM_DEVICE_GROUP → CUSTOM_DEVICE (cloud:aws:*) (non-built-in)
```

---

## Migration Notes

- Built-in and non-built-in can coexist for different services on the same connection.
- Some services exist as BOTH built-in entities AND custom devices (e.g., Lambda, RDS, DynamoDB) with different metric key formats.
- Metric Streams accounts need special handling — see [metric-streams.md](metric-streams.md).
- Entity type name collisions exist between classic and new for `AWS_LAMBDA_FUNCTION`, `AWS_APPLICATION_LOAD_BALANCER`, `AWS_NETWORK_LOAD_BALANCER` — despite identical names, they are separate entity systems.
