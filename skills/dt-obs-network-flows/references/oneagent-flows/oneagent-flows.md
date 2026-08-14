# OneAgent Network Flows

Detailed DQL reference for OneAgent-captured network flows in the `default_network_flows` Grail bucket. Each record is one aggregated connection over the capture interval (default 1 minute), emitted by OneAgent's network agent.

> All DQL in this file was validated against a live tenant with `dtctl query`.

## Prerequisites

- OneAgent 1.337 or later on the monitored hosts.
- `builtin:network-connection-monitoring` enabled (`reportedConnections: all` recommended for full visibility). See [configuration.md](configuration.md).

## Critical Field-Typing Rules

These four rules cause silent wrong results if ignored:

1. **Field prefix is `network_flow.` with an underscore** — not `network.flow.` with a dot. The dotted form silently matches nothing.
2. **Numeric fields are returned as strings** (e.g. `network_flow.bytes.rx` → `"3899"`). Arithmetic (`+`, `sum()`, `avg()`) coerces them automatically, so `sum(network_flow.bytes.rx + network_flow.bytes.tx)` works. Consumer code outside DQL must coerce explicitly.
3. **Optional fields are `null` when absent**, not omitted. Use `coalesce(field, 0)` or `if(isNull(field), …)` in health calculations.
4. **Typed fields need casts in filters:**
   - `network_flow.source.address` / `network_flow.destination.address` are `ip_address` — wrap literals with `toIp("10.0.0.1")`. Comparing to a bare string matches nothing.
   - `dt.smartscape.host` / `dt.smartscape.process` / `dt.smartscape.k8s_pod` are smartscape-id type — wrap literals with `toSmartscapeId("HOST-…")`.
   - `network_flow.tcp.rtt` and `network_flow.tcp.rtt.ack` are `duration` (nanoseconds). Cast to milliseconds with `/ 1ms` to get a plain double.

## Data Model

### Flow measurement fields

| Field | Type | Description |
|---|---|---|
| `flow.start`, `flow.end` | timestamp | Connection window start/end |
| `timestamp` | timestamp | Record ingestion time |
| `network_flow.source.address` | ip_address | **Client** IP — the connection initiator |
| `network_flow.source.port` | string(long) | Client's source port — the ephemeral port, **usually `null`** (not captured) |
| `network_flow.destination.address` | ip_address | **Server** IP — the connection acceptor |
| `network_flow.destination.port` | string(long) | Server's **listening port** (the stable, well-known port) |
| `network_flow.network.transport` | string | `TCP` or `UDP` |
| `network_flow.network.type` | string | `IPV4` or `IPV6` |
| `network_flow.process_is_server` | boolean | Role of the **capturing** entity: `true` = it is the **server** (the `destination` side; connection was inbound); `false` = it is the **client** (the `source` side; connection was outbound) |
| `network_flow.bytes.rx`, `.tx` | string(long) | Bytes received / transmitted |
| `network_flow.packets.rx`, `.tx` | string(long) | Packets received / transmitted |
| `network_flow.packets.retransmitted.rx`, `.tx` | string(long) | Retransmitted packets |
| `network_flow.packets.retransmitted.base.rx`, `.tx` | string(long) | Base counters for retransmission ratio |
| `network_flow.tcp.rtt` | duration | Round-trip time (ns; cast `/ 1ms`) |
| `network_flow.tcp.rtt.ack` | duration | ACK round-trip time (ns; cast `/ 1ms`) |
| `network_flow.tcp.sessions.new` | string(long) | New TCP sessions in the interval (denominator for health ratios) |
| `network_flow.tcp.sessions.reset` | string(long) | Sessions ending in reset |
| `network_flow.tcp.sessions.timeout` | string(long) | Sessions ending in timeout |

### Direction: which side is the capturing entity?

The record is emitted by **one** OneAgent-monitored entity — the **capturing entity**. That entity is *not* always the network source. `source`/`destination` are canonicalized by TCP role, independent of who captured the flow:

- `network_flow.source.address` is always the **client** (connection initiator).
- `network_flow.destination.address` is always the **server** (acceptor), and `network_flow.destination.port` is its **listening port**.

`network_flow.process_is_server` tells you which of those two the capturing entity is:

| `process_is_server` | Capturing entity is the… | It is the flow's… | Remote endpoint is the… |
|---|---|---|---|
| `false` | client (outbound connection) | `source` | `destination` (server) |
| `true` | server (inbound connection) | `destination` | `source` (client) |

> Do **not** assume the capturing entity is the `source` or that the remote endpoint is the `destination` — that only holds for outbound (`process_is_server == false`) flows. For inbound flows it is reversed. (Note: Dynatrace also exposes `dt.source_entity` / `dt.smartscape_source.*` where "source" means *the entity that produced the event* — i.e. the capturing entity — which is a different sense of the word than the network `source` address.)

### Entity / topology dimensions (the capturing entity)

Every `dt.smartscape.*` / `dt.entity.*` field describes the **capturing** entity of the flow — the OneAgent-monitored host/process/pod that observed it (client or server per `process_is_server` above). The **remote endpoint has no smartscape ID**; it is identified only by its IP and port and must be resolved separately (see [Peer Resolution](#peer-resolution)).

- `dt.smartscape.host`, `dt.smartscape.process`, `dt.smartscape.k8s_pod`, `dt.smartscape.k8s_node`, `dt.smartscape.k8s_namespace`, `dt.smartscape.k8s_cluster`, `dt.smartscape.container`
- `dt.entity.host`, `dt.entity.process_group_instance`, `dt.entity.process_group`, `dt.entity.host_group`
- `host.name`, `k8s.cluster.name`, `k8s.namespace.name`, `k8s.node.name`, `dt.host_group.id`
- Cloud dims when present: `cloud.provider`, `aws.region`, `aws.account.id`, `azure.region`, `azure.subscription`

> **Discover the full field set** on your tenant: `fetch events, bucket:{"default_network_flows"} | limit 1`

## Base Query

```dql
fetch events, bucket:{"default_network_flows"}
```

Common filters:

```dql-snippet
| filter dt.smartscape.host == toSmartscapeId("HOST-...")
| filter dt.smartscape.process == toSmartscapeId("PROCESS-...")
| filter dt.smartscape.k8s_pod == toSmartscapeId("K8S_POD-...")
| filter network_flow.process_is_server == true    // inbound (this entity is the server)
| filter network_flow.process_is_server == false   // outbound (this entity is the client)
| filter network_flow.tcp.sessions.reset > 0        // connections that reset
| filter network_flow.tcp.sessions.timeout > 0      // connections that timed out
```

## Use Case Queries

### 1. Top talkers by bandwidth

```dql
fetch events, bucket:{"default_network_flows"}, from:now()-1h
| summarize
    total_bytes = sum(network_flow.bytes.rx + network_flow.bytes.tx),
    flows = count(),
    by: {dt.smartscape.host}
| lookup [smartscapeNodes HOST | fields id, name], sourceField: dt.smartscape.host, lookupField: id, prefix: "host."
| fieldsAdd host_name = host.name, total_mb = round(toDouble(total_bytes) / 1024 / 1024, decimals: 1)
| fields host_name, dt.smartscape.host, total_mb, flows
| sort total_mb desc
| limit 20
```

### 2. Top destinations and top clients

Because `source` = client and `destination` = server, look at each side separately rather than collapsing them into a single "peer" (a peer IP is the client for some flows and the server for others). Add a `filter dt.smartscape.host == toSmartscapeId("…")` to scope either query to one entity.

**Top destinations** — the servers/services receiving the most traffic (grouped with the listening port):

```dql
fetch events, bucket:{"default_network_flows"}, from:now()-1h
| summarize bytes = sum(network_flow.bytes.rx + network_flow.bytes.tx), flows = count(),
    by: {network_flow.destination.address, network_flow.destination.port}
| sort bytes desc
| limit 10
| fieldsAdd bytes_mb = round(toDouble(bytes) / 1024 / 1024, decimals: 1)
| fields network_flow.destination.address, network_flow.destination.port, bytes_mb, flows
```

**Top clients** — the initiators generating the most traffic:

```dql
fetch events, bucket:{"default_network_flows"}, from:now()-1h
| summarize bytes = sum(network_flow.bytes.rx + network_flow.bytes.tx), flows = count(),
    by: {network_flow.source.address}
| sort bytes desc
| limit 10
| fieldsAdd bytes_mb = round(toDouble(bytes) / 1024 / 1024, decimals: 1)
| fields network_flow.source.address, bytes_mb, flows
```

### 3. Protocol distribution

```dql
fetch events, bucket:{"default_network_flows"}, from:now()-1h
| summarize flows = count(), bytes = sum(network_flow.bytes.rx + network_flow.bytes.tx), by: {network_flow.network.transport}
| sort flows desc
```

### 4. Top destination ports

```dql
fetch events, bucket:{"default_network_flows"}, from:now()-1h
| summarize flows = count(), bytes = sum(network_flow.bytes.rx + network_flow.bytes.tx),
    by: {network_flow.destination.port, network_flow.network.transport}
| sort flows desc
| limit 20
```

**Well-known ports:** 80/443 (HTTP/S), 22 (SSH), 3306 (MySQL), 5432 (PostgreSQL), 6379 (Redis), 9092 (Kafka), 10250 (kubelet).

### 5. Bandwidth in bits per second (per connection)

Byte counts are per-interval; divide by the flow duration to get a rate. This is the query the Infrastructure & Ops app uses to feed its Connections table and Network map.

```dql-template
fetch events, bucket:{"default_network_flows"}, from:"<FROM>", to:"<TO>"
| filter dt.smartscape.host == toSmartscapeId("<HOST_ID>")
| fieldsAdd seconds = toDuration(timeframe(from: flow.start, to: flow.end)) / 1s
| fieldsAdd
    rx_bps = network_flow.bytes.rx * 8 / seconds,
    tx_bps = network_flow.bytes.tx * 8 / seconds,
    network_flow.tcp.rtt = network_flow.tcp.rtt / 1ms
| fields network_flow.source.address, network_flow.destination.address, network_flow.destination.port,
    network_flow.process_is_server, network_flow.tcp.rtt,
    network_flow.tcp.sessions.reset, network_flow.tcp.sessions.timeout, network_flow.tcp.sessions.new,
    rx_bps, tx_bps
| sort tx_bps desc
```

For process-level, substitute `dt.smartscape.process == toSmartscapeId("<PROCESS_ID>")`. For pods, `dt.smartscape.k8s_pod == toSmartscapeId("<POD_ID>")`.

### 6. Slowest conversations by RTT

Excludes timed-out sessions, which skew the average.

```dql
fetch events, bucket:{"default_network_flows"}, from:now()-1h
| filter network_flow.tcp.sessions.timeout < 1
| summarize avg_rtt_ms = avg(network_flow.tcp.rtt / 1ms), by: {network_flow.destination.address}
| sort avg_rtt_ms desc
| limit 20
```

### 7. Highest retransmission rate

A sign of an unhealthy network path.

```dql
fetch events, bucket:{"default_network_flows"}, from:now()-1h
| summarize {
    retrans_rx = sum(network_flow.packets.retransmitted.rx),
    retrans_tx = sum(network_flow.packets.retransmitted.tx),
    total_rx = sum(network_flow.packets.rx),
    total_tx = sum(network_flow.packets.tx)
  }, by: {network_flow.destination.address}
| filter total_rx + total_tx > 1000
| fieldsAdd retrans_perc = (retrans_rx + retrans_tx) / (total_rx + total_tx) * 100
| sort retrans_perc desc
| limit 20
```

> `retrans_perc` can exceed 100% because retransmitted and total packet counters use different bases. Use it as a relative ranking signal, not an absolute percentage. The `network_flow.packets.retransmitted.base.*` fields hold the matching base counters if you need a normalized ratio.

### 8. Connectivity (connection health) score

Percentage of TCP sessions that did **not** end in a reset or timeout. If there were no new sessions, connectivity is 100%.

```dql-template
fetch events, bucket:{"default_network_flows"}, from:"<FROM>", to:"<TO>"
| filter dt.smartscape.host == toSmartscapeId("<HOST_ID>")
| summarize {
    total_resets = sum(network_flow.tcp.sessions.reset),
    total_timeouts = sum(network_flow.tcp.sessions.timeout),
    total_new_sessions = sum(network_flow.tcp.sessions.new)
  }
| fieldsAdd connectivity = if(isNull(total_new_sessions) or total_new_sessions == 0, 100.0,
    else: 100.0 - 100.0 * (coalesce(total_resets, 0) + coalesce(total_timeouts, 0)) / total_new_sessions)
```

## Peer Resolution

A flow record carries a smartscape ID only for the **capturing** entity. The **peer** — the remote endpoint on the other side of the connection — has no smartscape ID and must be looked up in Smartscape by IP.

**Pick the peer's IP and port based on `process_is_server`** (the peer is always the opposite side from the capturing entity):

| `process_is_server` | Peer is the… | Peer IP | Peer port |
|---|---|---|---|
| `false` (capture is client) | server | `network_flow.destination.address` | `network_flow.destination.port` (listening port) |
| `true` (capture is server) | client | `network_flow.source.address` | `network_flow.source.port` (ephemeral — usually `null`) |

Then resolve that IP (and port) to a monitored entity with the shared lookups in **[references/peer-resolution/peer-resolution.md](../peer-resolution/peer-resolution.md)** (host → unique pod → service → external). Pass the peer IP/port chosen from the table above as `<IP>` / `<PORT>` — *not* unconditionally the `destination` fields. The process-by-listening-port lookup only resolves when the peer is the **server** (`process_is_server == false`, peer port = `network_flow.destination.port`); a client peer (`process_is_server == true`) uses an ephemeral source port (usually `null`), so resolve it to a host or pod by IP only.

## Enrich the capturing entity's name in aggregations

When grouping by the capturing entity's `dt.smartscape.host` / `.process`, join names via `lookup`:

```dql-snippet
| lookup [smartscapeNodes HOST | fields id, name], sourceField: dt.smartscape.host, lookupField: id, prefix: "host."
| fieldsAdd host_name = host.name
```

## Kubernetes Prerequisite

Flow capture is OneAgent (host-level) data. A pod only has flow data if its **underlying node is host-monitored** — Kubernetes monitoring alone is not enough. Resolve pod → node → host to check:

```dql-template
smartscapeNodes { K8S_POD }
| filter id == toSmartscapeId("<POD_ID>")
| traverse runs_on, "K8S_NODE"
| traverse runs_on, "HOST"
| fields dt.smartscape.host = id
```

Zero records → the node has no host OneAgent, so no flow data exists for that pod.

## Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| IP filter matches nothing | Compared `ip_address` field to bare string | Wrap with `toIp("...")` |
| Smartscape filter matches nothing | Compared smartscape-id field to bare string | Wrap with `toSmartscapeId("...")` |
| RTT values look huge | Raw value is nanoseconds | Cast with `/ 1ms` |
| Only connection failures appear | `reportedConnections: auto` (default) captures only critical events | Set `reportedConnections: all` — see [configuration.md](configuration.md) |
| No flows for specific pods | Node not host-monitored | Verify pod → node → HOST resolves (above) |
| Peer shows as external but should be known | Resolved pods before hosts, or ambiguous IP | Resolve host → pod → service; drop ambiguous (multi-pod) IPs |
