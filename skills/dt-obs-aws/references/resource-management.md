# AWS Resource Management & Optimization

Analyze AWS resource usage, identify optimization opportunities, and manage resource tagging.

## Table of Contents

- [Resource Inventory](#resource-inventory)
- [Tag Compliance](#tag-compliance)
- [Resource Lifecycle](#resource-lifecycle)
- [Regional & VPC Distribution](#regional--vpc-distribution)
- [Storage & Security Resources](#storage--security-resources)

## Resource Inventory

Count all AWS resources by type:

```dql
smartscapeNodes "AWS_*"
| summarize resource_count = count(), by: {type}
| sort resource_count desc
```

View resource distribution across accounts:

```dql
smartscapeNodes "AWS_*"
| summarize resource_count = count(), by: {aws.account.id, aws.region}
| sort resource_count desc
```

Find resource types spanning multiple regions:

```dql
smartscapeNodes "AWS_*"
| summarize
    region_count = countDistinct(aws.region),
    total_resources = count(),
    by: {type}
| filter region_count > 1
| sort region_count desc
```

## Tag Compliance

Find completely untagged resources:

```dql
smartscapeNodes "AWS_*"
| filter isNull(tags)
| fields type, name, aws.resource.id, aws.account.id, aws.region
```

Find resources missing a specific required tag:

```dql
smartscapeNodes "AWS_*"
| filter isNull(tags[Environment]) or tags[Environment] == ""
| summarize count = count(), by: {type, aws.account.id}
```

Calculate tag coverage percentages across resource types:

```dql
smartscapeNodes "AWS_*"
| fieldsAdd has_owner_tag = if(isNotNull(tags[Owner]), 1)
| fieldsAdd has_env_tag = if(isNotNull(tags[Environment]), 1)

| summarize
    total = count(),
    with_env = sum(has_env_tag),
    with_owner = sum(has_owner_tag),
  by: { type }
| fieldsAdd
    env_coverage_pct = (with_env * 100.0) / total,
    owner_coverage_pct = (with_owner * 100.0) / total
| sort env_coverage_pct asc

```

Find resources by tag value:

```dql
smartscapeNodes "AWS_*"
| filter tags[`<TAG_NAME>`] == "<TAG_VALUE>"
| summarize count = count(), by: {type, aws.region}
```

Find resources by naming convention:

```dql
smartscapeNodes "AWS_*"
| filter matchesPhrase(name, "prod")
| fields type, name, aws.resource.id, aws.region, tags[Environment]
```

## Resource Lifecycle

Detect deleted resources:

```dql
smartscapeNodes "AWS_*"
| filter cloud.acquisition.status == "DELETED"
| fields type, name, aws.resource.id, aws.account.id, aws.region
```

Find resources with acquisition issues:

```dql
smartscapeNodes "AWS_*"
| filter cloud.acquisition.status != "OK"
| fields type, name, aws.resource.id, cloud.acquisition.status, aws.account.id
```

Find unattached EBS volumes:

```dql
smartscapeNodes "AWS_EC2_VOLUME"
| parse aws.object, "JSON:awsjson"
| fieldsAdd state = awsjson[configuration][state]
| filter state == "available"
| fields name, aws.resource.id, aws.availability_zone, aws.account.id
```

Find unassociated Elastic IPs:

```dql
smartscapeNodes "AWS_EC2_EIP"
| parse aws.object, "JSON:awsjson"
| fieldsAdd associationId = awsjson[configuration][associationId]
| filter isNull(associationId)
| fields name, aws.resource.id, aws.region, aws.account.id
```

## Regional & VPC Distribution

View resources by region:

```dql
smartscapeNodes "AWS_*"
| summarize resource_count = count(), by: {aws.region}
| sort resource_count desc
```

Count resources per VPC:

```dql
smartscapeNodes "AWS_*"
| filter isNotNull(aws.vpc.id)
| summarize resource_count = count(), by: {aws.vpc.id, type}
| sort resource_count desc
```

## Storage & Security Resources

Count storage services:

```dql
smartscapeNodes "AWS_S3_BUCKET", "AWS_EC2_VOLUME", "AWS_EFS_FILESYSTEM"
| summarize count = count(), by: {type, aws.region}
| sort count desc
```

Count IAM and security resources:

```dql
smartscapeNodes "AWS_IAM_ROLE", "AWS_IAM_USER", "AWS_IAM_GROUP", "AWS_KMS_KEY", "AWS_EC2_SECURITYGROUP"
| summarize count = count(), by: {type}
| sort count desc
```

List S3 buckets:

```dql
smartscapeNodes "AWS_S3_BUCKET"
| fields name, aws.account.id, aws.region, aws.resource.id
```

Find EC2 snapshots:

```dql
smartscapeNodes "AWS_EC2_SNAPSHOT"
| fields name, aws.resource.id, aws.region, aws.account.id
```
