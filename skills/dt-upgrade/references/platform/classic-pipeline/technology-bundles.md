# Technology Bundle Processors

OpenPipeline technology bundle processors are the gen3 replacement for classic built-in log processing rules. They are Dynatrace-maintained, automatically kept up to date, and normalize log data into consistent attributes aligned with the Semantic Dictionary — they are better maintained than hand-translated DQL copies of classic built-in rules.

## When this applies

When running translation with `--skip-builtin-processing-rules=true` (the recommended flag), all built-in classic rules are excluded from the translation output. For each built-in rule that has a mapping in the table below, add the equivalent technology bundle processor to the artifact — set `enabled: true` if any of the bundle's classic rules were enabled, or `enabled: false` if all were disabled.

## Identify built-in rules during discovery

During Step 1 discovery (see [classic-config-discovery.md](classic-config-discovery.md)), in addition to counting custom rules, identify all built-in rules in `builtin:logmonitoring.log-dpp-rules` and note their `value.enabled` state. Add a technology bundle processor for every built-in rule that has a mapping — set `enabled: true` for rules that were enabled, and `enabled: false` for rules that were disabled. Do not omit disabled rules: preserving them with `enabled: false` keeps the upgrade complete and lets the user re-enable them later if needed.

Present all built-in rules to the user and use the mapping table below to determine which technology bundle processors to add to the artifact.

## Mapping: classic built-in rules to technology bundles

Multiple built-in rules can map to the same technology bundle — add **one technology bundle processor per unique bundle**, not one per classic rule.

| Classic built-in rule | Technology bundle | Category |
|---|---|---|
| `[Built-in] web_server:nginx:access_log` | Nginx | Servers |
| `[Built-in] web_server:nginx:error_log` | Nginx | Servers |
| `[Built-in] db:cassandra:logback` | Cassandra | Databases |
| `[Built-in] db:cassandra:dropped_messages` | Cassandra | Databases |
| `[Built-in] db:cassandra:keyspace_column_family` | Cassandra | Databases |
| `[Built-in] db:elasticsearch:default_log` | Elasticsearch | Databases |
| `[Built-in] db:elasticsearch:slow_log_index` | Elasticsearch | Databases |
| `[Built-in] db:elasticsearch:slow_log_search` | Elasticsearch | Databases |
| `[Built-in] load_balancer:haproxy:http` | HAProxy | Servers |
| `[Built-in] load_balancer:haproxy:tcp` | HAProxy | Servers |
| `[Built-in] load_balancer:haproxy:error` | HAProxy | Servers |
| `[Built-in] load_balancer:haproxy:default` | HAProxy | Servers |
| `[Built-in] cloud:azure:common` | Azure Services | Azure |
| `[Built-in] cloud:aws:common` | AWS Common | AWS |
| `[Built-in] cloud:aws:apigateway` | Amazon API Gateway | AWS |
| `[Built-in] cloud:aws:lambda` | AWS Lambda | AWS |
| `[Built-in] cloud:aws:rds` | Amazon RDS | AWS |
| `[Built-in] cloud:aws:rdsaurora` | Amazon Aurora | AWS |
| `[Built-in] cloud:aws:sns` | Amazon SNS | AWS |
| `[Built-in] cloud:aws:apprunner` | AWS App Runner | AWS |
| `[Built-in] cloud:aws:cloudtrail` | AWS CloudTrail | AWS |

### Built-in rules without a technology bundle equivalent

Built-in rules not listed in the mapping table above (such as `[Built-in] one_agent:log_enrichment:*` enrichment rules) do not have a technology bundle equivalent but the behavior they provide should work out-of-the-box in OpenPipeline.

## Technology bundle processor shape

Add technology bundle processors to the **processing** stage of the pipeline artifact — before the translated custom DQL processors, to match the original ordering where built-in rules ran first.

Each processor uses `"type": "technology"` and a `technology.technologyId` field that identifies the bundle. Include `sampleData` to enable the processor preview feature in the OpenPipeline UI — without it the processor works but preview has no sample to run against:

```json
{
  "id": "processor_Cassandra",
  "type": "technology",
  "description": "Cassandra",
  "enabled": true,
  "sampleData": "...",
  "technology": {
    "technologyId": "databases_cassandra_v2"
  }
}
```

Use [technology_bundles.json](technology_bundles.json) as the ready-to-deploy source — it contains pre-built processor definitions with `sampleData` for all bundles that have classic built-in rule equivalents. Copy the relevant processor objects from there into the artifact's `processing.processors` array.

## technologyId reference

| Technology bundle | technologyId |
|---|---|
| Cassandra | `databases_cassandra_v2` |
| Elasticsearch | `elasticsearch_9430_v2` |
| Nginx | `servers_nginx_v2` |
| HAProxy | `servers_haproxy_v2` |
| Azure Services | `azure_common_technology_v2` |
| AWS Common | `aws_common_001` |
| Amazon API Gateway | `aws_api_gateway_001` |
| AWS Lambda | `aws_lambda_001` |
| Amazon RDS | `aws_rds_001` |
| Amazon Aurora | `amazon_aurora_001` |
| Amazon SNS | `aws_sns_001` |
| AWS App Runner | `aws_app_runner_001` |
| AWS CloudTrail | `aws_cloud_trail_v3` |

To find the `technologyId` for a bundle not listed here, use the technologies API (see [openpipeline-api.md](openpipeline-api.md)) to list all available bundles and their IDs. Alternatively, add the bundle to any pipeline in the OpenPipeline UI, then export it via the Settings API and read the `technology.technologyId` field:

```dtctl
dtctl get settings --schema builtin:openpipeline.logs.pipelines -o json
```

## All available technology bundles

The following bundles are available in OpenPipeline. Not all have classic built-in rule equivalents — they can also be added to new pipelines independently of the upgrade.

### AWS
Amazon API Gateway, Amazon Aurora, Amazon CloudFront, Amazon EKS, Amazon ElastiCache, Amazon MSK Broker, Amazon MSK Connect, Amazon OpenSearch Service, Amazon RDS, Amazon Route 53, Amazon SNS, Amazon VPC Flow, AWS App Runner, AWS CloudTrail, AWS Common, AWS Lambda, AWS Transit Gateway, AWS WAF

### Azure
Azure Application Gateway Logs, Azure Entra ID Audit Logs, Azure Function App Logs, Azure Kubernetes Service (AKS) Logs, Azure Load Balancer Logs, Azure Services

### Applications
.NET, Go, Java, NodeJS, PHP, Python, Ruby

### Databases
Cassandra, Elasticsearch, PostgreSQL, Redis

### Servers
Apache HTTP, Apache Tomcat, HAProxy, JBoss, Microsoft IIS, Nginx

### Message Brokers
Apache Kafka, RabbitMQ

### Development Tools
JFrog Artifactory

### Syslog
Syslog

## References

- [technology_bundles.json](technology_bundles.json) — Ready-to-deploy processor definitions with `sampleData` for all bundles that have classic built-in rule equivalents
- [Public docs: OpenPipeline technology bundle processors](https://docs.dynatrace.com/docs/analyze-explore-automate/logs/lma-log-processing/lma-tech-bundles-processors)
- [classic-config-discovery.md](classic-config-discovery.md) — Discovery queries used to identify which built-in rules are enabled
