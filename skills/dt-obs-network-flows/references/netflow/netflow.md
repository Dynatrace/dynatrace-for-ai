# NetFlow / IPFIX / sFlow

DQL reference for flow data exported by network devices (switches, routers, firewalls) and ingested into Dynatrace through an OpenTelemetry Collector. Each record is one flow record as the exporting device reported it.

> All DQL in this file was validated against a live tenant (with a NetFlow-configured OTel Collector) using `dtctl query`.

## Where the data lives

NetFlow is ingested through an OpenTelemetry Collector as OTLP **log records** — they live in **`logs`** (not an `events` bucket), and every one carries `otel.scope.name == "otelcol/netflowreceiver"`. Ingestion setup and the strongly-recommended dedicated-bucket routing are in **[configuration.md](configuration.md)**.

> **Query the dedicated bucket.** Once netflow is routed to its own bucket (see configuration.md), add `bucket:"<your netflow bucket>"` to every `fetch logs` below. The queries here use the bucket-less `fetch logs | filter otel.scope.name == ...` form — what works before routing is set up, and what was validated on the tenant. Keep the `otel.scope.name` filter either way as a guard.

## Critical Field-Typing Rules

1. **These are `logs`, not `events`.** Query with `fetch logs` and always filter `otel.scope.name == "otelcol/netflowreceiver"` (or scope to the dedicated bucket) — otherwise you scan unrelated log sources.
2. **Byte and packet counters are strings.** `flow.io.bytes` / `flow.io.packets` return as strings (e.g. `"690151"`); wrap with `toDouble(...)` before `sum()`/arithmetic, exactly as the shipped dashboard does.
3. **Ports and IPs are plain strings here** (unlike OneAgent flows). `source.address` / `destination.address` / `destination.port` are strings, not typed `ip_address`/`long` — compare to bare string literals, no `toIp(...)` cast.
4. **No entity context on the endpoints.** Addresses are raw IPs observed on the wire; they are *not* resolved to Dynatrace hosts/processes/pods. There are no `dt.smartscape.*` fields on flow records.

## Direction & semantics — read this

NetFlow direction is **not** the same as OneAgent flow direction:

- Records are **unidirectional**. One conversation appears as **two** records — `A→B` and `B→A`. Summing "bytes between A and B" means accounting for both.
- `source.address` / `destination.address` are the flow's origin and target **as the device saw the packets** — there is **no client/server role field** (no `process_is_server` equivalent). The listening/server side is only inferable conventionally from the well-known port (usually the lower of `source.port` / `destination.port`).
- Unlike OneAgent flows, **`source.port` is populated** (NetFlow reports both ports).
- The reporting device is `flow.sampler_address` (the exporter IP), with the ingress/egress interfaces in `flow.in_if` / `flow.out_if`.

## Data Model

### Core flow fields

| Field | Description |
|---|---|
| `source.address`, `destination.address` | Flow endpoint IPs (strings) as reported by the device |
| `source.port`, `destination.port` | L4 ports (strings) — both populated |
| `network.transport` | `tcp`, `udp`, `icmp`, `esp`, `ah`, … |
| `network.type` | IP version: `ipv4` / `ipv6` |
| `flow.type` | Export protocol: `ipfix`, `netflow_v9`, `netflow_v5`, `sflow` |
| `flow.io.bytes`, `flow.io.packets` | Byte / packet counts (strings → `toDouble`) |
| `flow.start`, `flow.end` | Flow window (epoch nanoseconds, string) |
| `flow.time_received` | When the Collector received the record (epoch ns) |
| `flow.sampling_rate` | Sampling divisor; `0` = unsampled. For sampled exporters, multiply counts by this to estimate real traffic |

### Device / routing fields

| Field | Description |
|---|---|
| `flow.sampler_address` | **Exporter (device) IP** — who reported the flow |
| `flow.in_if`, `flow.out_if` | Ingress / egress SNMP interface index |
| `flow.next_hop`, `flow.next_hop_as` | Next-hop IP and its AS |
| `flow.src_as`, `flow.dst_as` | Source / destination BGP AS number |
| `flow.src_net`, `flow.dst_net` | Source / destination prefix mask length |
| `flow.src_vlan`, `flow.dst_vlan`, `flow.vlan_id` | VLAN tags |
| `flow.src_mac`, `flow.dst_mac` | L2 MAC addresses |
| `flow.observation_domain_id`, `flow.observation_point_id`, `flow.sequence_num` | IPFIX/NetFlow observation identifiers |

### Packet-header fields

`flow.tcp_flags`, `flow.ip_tos`, `flow.ip_ttl`, `flow.ip_flags`, `flow.icmp_type`, `flow.icmp_code`, `flow.fragment_id`, `flow.fragment_offset`, `flow.ipv6_flow_label`, `flow.forwarding_status`.

### OTel scaffolding

`otel.scope.name` = `"otelcol/netflowreceiver"` (the filter that isolates netflow logs), `receiver` = `"netflow"`, `content` = `""` (empty body), `timestamp`.

> **Discover the full field set** on your tenant: `fetch logs | filter otel.scope.name == "otelcol/netflowreceiver" | limit 1`

## Base Query

```dql
fetch logs
| filter otel.scope.name == "otelcol/netflowreceiver"
```

Common filters:

```dql-snippet
| filter source.address == "10.0.0.75"                 // no toIp() — plain string
| filter destination.port == "443"
| filter network.transport == "tcp"
| filter flow.type == "ipfix"
| filter flow.sampler_address == "20.20.21.1"          // one exporter/device
```

## Use Case Queries

These mirror the shipped **Netflow Overview** dashboard (`com-dynatrace-extension-netflow-overview`).

### 1. Top conversations

```dql
fetch logs, from:now()-2h
| filter otel.scope.name == "otelcol/netflowreceiver"
| summarize { bytes=sum(toDouble(flow.io.bytes)), packets=sum(toDouble(flow.io.packets)), flows=count() },
    by: { source=source.address, destination=destination.address, port=destination.port, transport=network.transport }
| sort bytes desc
| limit 20
```

> Conversations are unidirectional. To fold `A→B` and `B→A` together, normalize the pair client-side (sort the two IPs) or run the query once per direction.

### 2. Top talkers — sources and destinations

Look at each side separately (there is no client/server role, so don't collapse them into a "peer").

**Top sources:**

```dql
fetch logs, from:now()-2h
| filter otel.scope.name == "otelcol/netflowreceiver"
| summarize bytes=sum(toDouble(flow.io.bytes)), by: { source=source.address }
| sort bytes desc
| limit 10
```

**Top destinations:**

```dql
fetch logs, from:now()-2h
| filter otel.scope.name == "otelcol/netflowreceiver"
| summarize bytes=sum(toDouble(flow.io.bytes)), by: { destination=destination.address }
| sort bytes desc
| limit 10
```

### 3. Top destination ports

```dql
fetch logs, from:now()-2h
| filter otel.scope.name == "otelcol/netflowreceiver"
| summarize { bytes=sum(toDouble(flow.io.bytes)), packets=sum(toDouble(flow.io.packets)) },
    by: { port=destination.port }
| sort bytes desc
| limit 10
```

### 4. Transport, IP version, and export-protocol breakdown

```dql
fetch logs, from:now()-2h
| filter otel.scope.name == "otelcol/netflowreceiver"
| summarize bytes=sum(toDouble(flow.io.bytes)), by: { transport=network.transport }
| sort bytes desc
```

Swap the `by:` dimension for `network.type` (IPv4/IPv6) or `flow.type` (ipfix / netflow_v9 / sflow) to reproduce the dashboard's "Network Protocol" and "Flow Type" tiles.

### 5. Traffic over time

```dql
fetch logs, from:now()-2h
| filter otel.scope.name == "otelcol/netflowreceiver"
| fieldsAdd bytes=toDouble(flow.io.bytes)
| makeTimeseries { total=sum(bytes) }, interval:10m
```

Add `, by:{source.address}` to `makeTimeseries` to split the series per top talker (as the dashboard does).

## Devices & Interfaces

### Per-exporter traffic

`flow.sampler_address` is the exporter (device) IP — the portable way to break traffic down by reporting device.

```dql
fetch logs, from:now()-2h
| filter otel.scope.name == "otelcol/netflowreceiver"
| summarize { bytes=sum(toDouble(flow.io.bytes)), flows=count() }, by: { exporter=flow.sampler_address }
| sort bytes desc
```

### Per-interface utilization

```dql
fetch logs, from:now()-2h
| filter otel.scope.name == "otelcol/netflowreceiver"
| summarize bytes=sum(toDouble(flow.io.bytes)),
    by: { exporter=flow.sampler_address, in_if=flow.in_if, out_if=flow.out_if }
| sort bytes desc
| limit 20
```

`in_if` / `out_if` are SNMP interface indexes. Mapping an index to an interface name requires the device's SNMP interface table (from device monitoring), which flow records do not carry.

### Exporter/device entities (extension-dependent)

If the **NetFlow extension** is installed, it materializes `dt.entity.network:netflow_source` and `dt.entity.network:device` entities (with a `same_as` link between them) and drives the dashboard's "Netflow sources" tile via `dt.log.status_per_entity_count`. Those entity types are **not present without the extension** — the `flow.sampler_address` grouping above is the portable fallback and needs no extension.

## Relationship to OneAgent Flows

The same conversation can appear in both sources. Choose per what the user needs:

| | NetFlow / IPFIX / sFlow | OneAgent flows |
|---|---|---|
| Vantage point | Network device (switch/router) | Monitored host/process/pod |
| Endpoint context | Raw IPs only | Resolved to smartscape host/process/pod |
| Directionality | Unidirectional (two records per conversation) | One aggregated record with client/server role |
| Coverage | Any traffic the device sees, incl. unmonitored hosts | Only traffic to/from OneAgent hosts |
| Health metrics | Byte/packet counts, TCP flags | RTT, retransmissions, resets, timeouts |

Lead with **OneAgent flows** when both endpoints are monitored (richer context, connection health). Use **NetFlow** for traffic OneAgent cannot see — device-to-device, unmonitored hosts, north-south at the network edge. To resolve a raw NetFlow IP to a Dynatrace entity, feed it into the shared [peer / IP resolution](../peer-resolution/peer-resolution.md) Smartscape lookups (host → pod → service → external).

## Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| Query scans huge volumes / slow | Reading all of `default_logs` | Route netflow to a dedicated bucket and `fetch logs, bucket:"..."` — see [configuration.md](configuration.md) |
| Don't know which bucket netflow lands in | Bucket isn't in the log payload | Group by the `dt.system.bucket` metadata field — see [configuration.md → Find which bucket the logs are currently in](configuration.md#find-which-bucket-the-logs-are-currently-in) |
| `sum(flow.io.bytes)` errors or returns odd values | Counter is a string | Wrap with `toDouble(...)` |
| IP filter matches nothing | Cast a string field with `toIp(...)` | These fields are plain strings — compare to bare string literals |
| Bytes look far too low | Exporter is sampling | Multiply by `flow.sampling_rate` (when non-zero) |
| Conversation totals look halved | Flows are unidirectional | Account for both `A→B` and `B→A` records |
| No `netflow_source` / `device` entities | NetFlow extension not installed | Group by `flow.sampler_address` instead |
| No data at all | Collector/receiver misconfigured | See [configuration.md → Verify data is arriving](configuration.md#verify-data-is-arriving) |

## References

- [configuration.md](configuration.md) — ingestion path and dedicated-bucket routing.
- [NetFlow via the OpenTelemetry Collector](https://docs.dynatrace.com/docs/shortlink/otel-collector-cases-netflow)
- Shipped dashboard: `com-dynatrace-extension-netflow-overview` (Netflow Overview)
