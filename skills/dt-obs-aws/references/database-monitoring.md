# AWS Database Monitoring

Monitor and analyze AWS database services including RDS, DynamoDB, ElastiCache, and Redshift.

## Table of Contents

- [Database Entity Types](#database-entity-types)
- [RDS Monitoring](#rds-monitoring)
- [Other Database Services](#other-database-services)
- [Database Security](#database-security)
- [Cross-Service Analysis](#cross-service-analysis)

## Database Entity Types

All these types support the standard discovery pattern: `smartscapeNodes "<TYPE>" | fields name, aws.account.id, aws.region, ...`

| Entity type | Description |
|---|---|
| `AWS_RDS_DBINSTANCE` | RDS database instances |
| `AWS_RDS_DBCLUSTER` | RDS Aurora clusters |
| `AWS_RDS_DBSUBNETGROUP` | RDS subnet groups |
| `AWS_RDS_OPTIONGROUP` | RDS option groups |
| `AWS_RDS_DBCLUSTERSNAPSHOT` | RDS cluster snapshots |
| `AWS_DYNAMODB_TABLE` | DynamoDB tables |
| `AWS_ELASTICACHE_CACHECLUSTER` | ElastiCache clusters |
| `AWS_ELASTICACHE_SUBNETGROUP` | ElastiCache subnet groups |
| `AWS_REDSHIFT_CLUSTER` | Redshift clusters |
| `AWS_REDSHIFTSERVERLESS_WORKGROUP` | Redshift Serverless workgroups |

## RDS Monitoring

Find Multi-AZ databases:

```dql
smartscapeNodes "AWS_RDS_DBINSTANCE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd multiAZ = awsjson[configuration][multiAZ]
| filter multiAZ == true
| fields name, aws.resource.id, aws.region, aws.availability_zone
```

Analyze by engine type:

```dql
smartscapeNodes "AWS_RDS_DBINSTANCE"
| parse aws.object, "JSON:awsjson"
| fieldsAdd engine = awsjson[configuration][engine]
| summarize db_count = count(), by: {engine, aws.region}
| sort db_count desc
```

Find RDS cluster members (instance → cluster relationship):

```dql
smartscapeNodes "AWS_RDS_DBINSTANCE"
| traverse "is_part_of", "AWS_RDS_DBCLUSTER"
| fields name, aws.resource.id, aws.region
```

## Other Database Services

Find ElastiCache clusters by engine:

```dql
smartscapeNodes "AWS_ELASTICACHE_CACHECLUSTER"
| parse aws.object, "JSON:awsjson"
| fieldsAdd engine = awsjson[configuration][engine]
| summarize cluster_count = count(), by: {engine, aws.region}
```

## Database Security

For public access detection on RDS databases, see the [Public Access Detection](security-compliance.md#public-access-detection) section in `security-compliance.md`.

Analyze database security groups:

```dql
smartscapeNodes "AWS_RDS_DBINSTANCE"
| fields name, aws.resource.id, aws.vpc.id, aws.security_group.id
| expand aws.security_group.id
```

Find what security groups a specific database uses:

```dql
smartscapeNodes "AWS_RDS_DBINSTANCE"
| filter aws.resource.id == "<AWS_RDS_DBINSTANCE_ID>"
| traverse "uses", "AWS_EC2_SECURITYGROUP"
| fields name, aws.resource.id
```

## Cross-Service Analysis

Find all databases in a specific VPC:

```dql
smartscapeNodes "AWS_RDS_DBINSTANCE", "AWS_ELASTICACHE_CACHECLUSTER", "AWS_REDSHIFT_CLUSTER"
| filter aws.vpc.id == "<VPC_ID>"
| fields type, name, aws.resource.id, aws.subnet.id
```

Count databases across regions:

```dql
smartscapeNodes "AWS_RDS_DBINSTANCE", "AWS_DYNAMODB_TABLE", "AWS_ELASTICACHE_CACHECLUSTER"
| summarize db_count = count(), by: {type, aws.region}
| sort aws.region, db_count desc
```
