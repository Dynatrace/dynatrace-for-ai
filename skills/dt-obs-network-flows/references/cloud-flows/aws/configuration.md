# Cloud Flow Logs Ingestion & Configuration (AWS)

How AWS **VPC Flow Logs** and **Transit Gateway (TGW) Flow Logs** get into Dynatrace, and the one setup step that matters most for querying them: routing to a dedicated bucket.

> Validated against a live tenant ingesting AWS VPC + TGW flow logs via Amazon Data Firehose. Azure and GCP are not covered here.

## Ingestion path (Amazon Data Firehose)

The validated path is **push-based via Amazon Data Firehose**:

1. Enable **flow logs** on the VPC / subnet / ENI (or on the Transit Gateway) and publish them to a **CloudWatch Logs** log group.
2. A CloudWatch Logs **subscription filter** streams the log group to an **Amazon Data Firehose** delivery stream.
3. The delivery stream is configured with Dynatrace as its HTTP endpoint — the Firehose log-ingest API `/api/v2/logs/ingest/aws_firehose`.

On arrival Dynatrace recognizes the records (they carry `log.type == "aws.vpc"` or `"aws.tgw"` and an `aws.data_firehose.arn`) and a **built-in processing rule parses the raw `content` line into typed fields** (`pkt_srcaddr`, `dstport`, `action`, `bytes`, …). No manual parse rule is needed for the standard formats.

> **AWS-side flow-log format matters.** The parser expects the AWS *default* v5 fields plus the packet-level extensions (`pkt-srcaddr`, `pkt-dstaddr`, `flow-direction`, `traffic-path`, `pkt-src-aws-service`, `pkt-dst-aws-service`). If you define a **custom** flow-log format in AWS, include those fields or the corresponding Dynatrace attributes will be empty. TGW flow logs carry their own field set (`tgw_*`, `packets_lost_*`) and no `action`/`pkt_*addr`.

An **S3-based** delivery path (flow logs → S3 → Dynatrace) is also documented by Dynatrace; the field set and DQL below are the same once records land. See [AWS log forwarding / end-to-end observability](https://docs.dynatrace.com/docs/shortlink/lma-e2e-observability).

## Route cloud flow logs to a dedicated bucket (do this first)

By default the flow logs land in the generic **`default_logs`** bucket, mixed in with every other log source. **Strongly recommend routing them to a dedicated bucket** (e.g. `cloud_flow_logs`) via an OpenPipeline routing rule matching `log.type == "aws.vpc"` (and `"aws.tgw"`), then querying that bucket by name. Flow volume is high (tens of thousands of records per region in a few hours on the validation tenant), so a dedicated bucket:

- keeps flow queries fast and cheap (scans only flow data, not all logs),
- lets you set a flow-appropriate retention independent of application logs,
- isolates the volume for cost tracking.

Once the dedicated bucket exists, target it in every query — add `bucket:"<your flow bucket>"` to each `fetch logs`:

```dql-snippet
fetch logs, bucket:"cloud_flow_logs"
| filter log.type == "aws.vpc"
```

Keep the `log.type` filter even when scoped to the dedicated bucket — it is a cheap guard against anything else being routed there, and it separates VPC (`aws.vpc`) from TGW (`aws.tgw`) records, which have different fields.

### Find which bucket the logs are currently in

The bucket isn't part of the ingested log payload, but Grail exposes it as a queryable **system metadata field**, `dt.system.bucket`. Group by it to see where the flow logs are actually landing (before routing, this is `default_logs`; after, your dedicated bucket):

```dql
fetch logs, from:now()-2h
| filter log.type == "aws.vpc" or log.type == "aws.tgw"
| summarize count(), by: { log.type, dt.system.bucket }
```

## Verify data is arriving

After configuring forwarding (and routing), confirm records appear and see which log groups / regions are reporting:

```dql
fetch logs, from:now()-2h
| filter log.type == "aws.vpc" or log.type == "aws.tgw"
| summarize records = count(), by: { aws.log_group, log.type }
| sort records desc
```

If empty:
- Confirm flow logs are enabled in AWS and publishing to the CloudWatch log group.
- Check the CloudWatch subscription filter → Firehose delivery stream is active and not failing (Firehose error S3 backup).
- Verify the Firehose HTTP endpoint points at the Dynatrace Firehose log-ingest URL with a valid API token (`logs.ingest` scope).
- Check that no OpenPipeline rule is dropping the records.

## References

- [End-to-end log & network observability on AWS](https://docs.dynatrace.com/docs/shortlink/lma-e2e-observability)
- Shipped dashboard: `dynatrace.infraops.Network-analytics` (Network analytics)
