# AWS Messaging & Event Streaming

Monitor SQS queues, SNS topics, EventBridge, Kinesis, and MSK clusters.

## Table of Contents

- [Messaging Entity Types](#messaging-entity-types)
- [Service-Specific Queries](#service-specific-queries)
- [Name Pattern Matching](#name-pattern-matching)
- [MSK Multi-AZ Distribution](#msk-multi-az-distribution)
- [Cross-Service Analysis](#cross-service-analysis)

## Messaging Entity Types

All these types support the standard discovery pattern: `smartscapeNodes "<TYPE>" | fields name, aws.account.id, aws.region, aws.resource.id`

| Entity type | Description |
|---|---|
| `AWS_SQS_QUEUE` | SQS queues |
| `AWS_SNS_TOPIC` | SNS topics |
| `AWS_EVENTS_EVENTBUS` | EventBridge event buses |
| `AWS_KINESISFIREHOSE_DELIVERYSTREAM` | Kinesis Firehose delivery streams |
| `AWS_MSK_CLUSTER` | Managed Streaming for Kafka clusters |
| `AWS_STEPFUNCTIONS_STATEMACHINE` | Step Functions state machines |

To filter any type by tag, region, or account, apply standard filters: `| filter tags[Environment] == "production"` or `| filter aws.account.id == "<AWS_ACCOUNT_ID>"`.

To summarize by region: `| summarize count = count(), by: {aws.region}`.

## Service-Specific Queries

Filter for non-default EventBridge event buses:

```dql
smartscapeNodes "AWS_EVENTS_EVENTBUS"
| filter name != "default"
| fields name, aws.resource.id, aws.region
```

Find MSK clusters in a specific VPC:

```dql
smartscapeNodes "AWS_MSK_CLUSTER"
| filter aws.vpc.id == "<VPC_ID>"
| fields name, aws.resource.id, aws.subnet.id
```

## Name Pattern Matching

Find queues or topics by name pattern using `matchesPhrase`:

```dql
smartscapeNodes "AWS_SQS_QUEUE"
| filter contains(name, "sqs")
| fields name, aws.resource.id, aws.region
```

Replace `"AWS_SQS_QUEUE"` with `"AWS_SNS_TOPIC"` or any other type. Replace `"orders"` with the relevant pattern.

## MSK Multi-AZ Distribution

Check Kafka cluster availability zone distribution:

```dql
smartscapeNodes "AWS_MSK_CLUSTER"
| fields name, aws.resource.id, aws.availability_zone, aws.vpc.id
| expand aws.availability_zone
```

## Cross-Service Analysis

Count all messaging resources by type:

```dql
smartscapeNodes "AWS_SQS_QUEUE", "AWS_SNS_TOPIC", "AWS_EVENTS_EVENTBUS", "AWS_KINESISFIREHOSE_DELIVERYSTREAM", "AWS_MSK_CLUSTER", "AWS_STEPFUNCTIONS_STATEMACHINE"
| summarize total = count(), by: {type}
| sort total desc
```

Filter to a specific account:

```dql
smartscapeNodes "AWS_SQS_QUEUE", "AWS_SNS_TOPIC", "AWS_EVENTS_EVENTBUS", "AWS_MSK_CLUSTER"
| filter aws.account.id == "123456789012"
| fields type, name, aws.region, aws.resource.id
```
