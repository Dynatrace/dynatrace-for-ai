# AWS Resource Ownership & Chargeback

Track resource ownership and enable cost allocation across teams.

## Table of Contents

- [Tag-Based Ownership Pattern](#tag-based-ownership-pattern)
- [Common Ownership Tags](#common-ownership-tags)
- [Service-Specific Ownership](#service-specific-ownership)
- [Multi-Account Resource Summary](#multi-account-resource-summary)

## Tag-Based Ownership Pattern

All ownership queries follow the same pattern — filter by a tag, then summarize by that tag and a grouping dimension:

```dql-template
smartscapeNodes "AWS_*"
| filter isNotNull(tags[`<TAG_NAME>`])
| summarize resource_count = count(), by: {tags[`<TAG_NAME>`], type}
| sort resource_count desc
```

Replace `<TAG_NAME>` with any tag from the table below. Replace `type` with `aws.region` or `aws.account.id` for alternative groupings. Replace `"AWS_*"` with a specific entity type to scope to one service.

## Common Ownership Tags

| Tag | Use case | Typical values |
|---|---|---|
| `CostCenter` | Financial chargeback | Cost center codes |
| `Owner` | Individual accountability | Email or username |
| `Team` | Team-level allocation | Team names |
| `Project` | Project-based grouping | Project identifiers |
| `Application` | Application ownership | Application names |
| `Environment` | Environment segmentation | `production`, `staging`, `dev` |
| `Department` | Departmental allocation | Department names |
| `BusinessUnit` | Business unit grouping | BU identifiers |

## Service-Specific Ownership

To scope ownership queries to a specific AWS service, replace `"AWS_*"` with the entity type:

| Entity type | Example use case |
|---|---|
| `AWS_EC2_INSTANCE` | Instance costs by department/team |
| `AWS_LAMBDA_FUNCTION` | Serverless costs by application |
| `AWS_RDS_DBCLUSTER` | Database ownership tracking |
| `AWS_EKS_CLUSTER` | Kubernetes cluster ownership by business unit |
| `AWS_EC2_VOLUME` | Storage costs by project |
| `AWS_S3_BUCKET` | Bucket ownership by team |

For service-specific queries, you can also select detail fields instead of summarizing:

```dql
smartscapeNodes "AWS_RDS_DBCLUSTER"
| filter isNotNull(tags[Owner])
| fields name, aws.resource.id, tags[Owner], aws.region
```

## Multi-Account Resource Summary

Summarize resources across accounts (independent of tags):

```dql
smartscapeNodes "AWS_*"
| summarize resource_count = count(), by: {aws.account.id, type}
| sort resource_count desc
| limit 50
```
