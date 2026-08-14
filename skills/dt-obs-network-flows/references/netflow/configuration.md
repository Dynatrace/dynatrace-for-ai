# NetFlow Ingestion & Configuration

How network-device flow data (NetFlow v5/v9, IPFIX, sFlow) gets into Dynatrace, and the one setup step that matters most for querying it: routing to a dedicated bucket.

## Ingestion path (OpenTelemetry Collector)

Network devices export flow records to an **OpenTelemetry Collector** running the **`netflow` receiver**. The Collector converts each flow to an OTLP **log record** and sends it to Dynatrace via the OTLP logs endpoint. The records therefore land in **`logs`** (not an `events` bucket), and every one carries `otel.scope.name == "otelcol/netflowreceiver"`.

Minimal Collector pipeline:

```yaml
receivers:
  netflow:
    scheme: netflow      # netflow (v5/v9/IPFIX) or sflow
    hostname: "0.0.0.0"
    port: 2055
    sockets: 2           # match to CPU cores
    workers: 4           # ~2x sockets

exporters:
  otlphttp:
    endpoint: ${env:DT_ENDPOINT}          # Dynatrace OTLP endpoint
    headers:
      Authorization: "Api-Token ${env:DT_API_TOKEN}"

service:
  pipelines:
    logs:
      receivers: [netflow]
      processors: [batch]
      exporters: [otlphttp]
```

Point network devices at the Collector's `port` (2055 above). For high volume, set `sockets` to the CPU-core count and `workers` to ~2× sockets, and scale out with multiple Collector instances.

See the Dynatrace docs: [NetFlow via the OpenTelemetry Collector](https://docs.dynatrace.com/docs/shortlink/otel-collector-cases-netflow).

## Route NetFlow to a dedicated bucket (do this first)

By default the netflow logs land in the generic **`default_logs`** bucket, mixed in with every other log source. **Strongly recommend routing them to a dedicated bucket** (e.g. `netflow_logs`) via an OpenPipeline routing rule matching `otel.scope.name == "otelcol/netflowreceiver"`, then querying that bucket by name. Flow volume is high (a single exporter ingested ~180k records in 2 hours on the validation tenant), so a dedicated bucket:

- keeps flow queries fast and cheap (scans only flow data, not all logs),
- lets you set a flow-appropriate retention independent of application logs,
- isolates the volume for cost tracking.

Once the dedicated bucket exists, target it in every query — add `bucket:"<your netflow bucket>"` to each `fetch logs`:

```dql-snippet
fetch logs, bucket:"netflow_logs"
| filter otel.scope.name == "otelcol/netflowreceiver"
```

Keep the `otel.scope.name` filter even when scoped to the dedicated bucket — it is a cheap guard against anything else being routed there.

### Find which bucket the logs are currently in

The bucket isn't part of the ingested log payload, but Grail exposes it as a queryable **system metadata field**, `dt.system.bucket`. Group by it to see where netflow logs are actually landing (before routing, this is `default_logs`; after, your dedicated bucket):

```dql
fetch logs, from:now()-2h
| filter otel.scope.name == "otelcol/netflowreceiver"
| summarize count(), by: { dt.system.bucket }
```

## Verify data is arriving

After configuring the Collector (and routing), confirm flow records appear and see which exporters are reporting:

```dql
fetch logs, from:now()-2h
| filter otel.scope.name == "otelcol/netflowreceiver"
| summarize flows = count(), by: { exporter = flow.sampler_address }
| sort flows desc
```

If empty:
- Verify the device is exporting to the Collector's `netflow` receiver port and the `scheme` matches the protocol (`netflow` vs `sflow`).
- Confirm the Collector's `logs` pipeline exports to the Dynatrace OTLP endpoint with a valid token.
- Check that no OpenPipeline rule is dropping the records.

## References

- [NetFlow via the OpenTelemetry Collector](https://docs.dynatrace.com/docs/shortlink/otel-collector-cases-netflow)
