# Cloud Flow Logs — AWS

DQL reference for AWS **VPC Flow Logs** and **Transit Gateway (TGW) Flow Logs** ingested into Dynatrace. Each record is one flow as the AWS network fabric reported it — per ENI (VPC logs) or per TGW attachment (TGW logs).

> All DQL in this file was validated against a live tenant ingesting AWS VPC + TGW flow logs, using `dtctl query`. **Only AWS is covered here** — Azure NSG/VNet and GCP VPC flow logs are not yet documented (see [Other providers](#other-providers)).

## Where the data lives

AWS flow logs are ingested as Dynatrace **log records** through the Firehose log-ingest API (not OTLP, and not an `events` bucket) — they live in **`logs`**. Two record types, distinguished by `log.type`:

- **`aws.vpc`** — VPC / subnet / ENI flow logs. Carry `action` (ACCEPT/REJECT), packet-level addresses (`pkt_srcaddr`/`pkt_dstaddr`), `vpc_id`, `subnet_id`, `az_id`, `interface_id`.
- **`aws.tgw`** — Transit Gateway flow logs. Carry `tgw_*` topology fields and `packets_lost_*` counters; **no `action`, no `pkt_*addr`**.

Ingestion setup and the strongly-recommended dedicated-bucket routing are in **[configuration.md](configuration.md)**.

> **Query the dedicated bucket.** Once flow logs are routed to their own bucket (see configuration.md), add `bucket:"<your flow bucket>"` to every `fetch logs` below. The queries here use the bucket-less `fetch logs | filter log.type == ...` form — what works before routing is set up, and what was validated on the tenant. Keep the `log.type` filter either way as a guard and to separate VPC from TGW records.

## Critical Field-Typing Rules

1. **These are `logs`, not `events`.** Query with `fetch logs` and filter `log.type == "aws.vpc"` (or `"aws.tgw"`) — otherwise you scan unrelated log sources. `log.type` is more robust than matching `aws.log_group` on a naming convention.
2. **Always filter `log_status == "OK"`.** Flow logs interleave `NODATA` and `SKIPDATA` capture-gap markers that have **no** flow fields (no addresses, ports, bytes). Without this filter, aggregations silently include useless rows. Both `aws.vpc` and `aws.tgw` records carry `log_status`; the filter applies to both.
3. **Byte and packet counters are strings.** `bytes` / `packets` return as strings (e.g. `"1121"`); wrap with `toLong(...)` (or `toDouble`) before `sum()`/arithmetic, exactly as the shipped dashboard does. TGW loss counters (`packets_lost_total`, …) are strings too.
4. **Addresses and ports are plain strings.** `pkt_srcaddr` / `srcaddr` / `srcport` / `dstport` are strings, not typed `ip_address`/`long` — compare to bare string literals, **no `toIp(...)` cast**.
5. **Use `pkt_srcaddr` / `pkt_dstaddr` for the true endpoints (VPC).** `srcaddr` / `dstaddr` are the addresses *as seen at the reporting ENI* — for traffic through a NAT gateway, load balancer, or other intermediary they are the intermediary's address, while `pkt_srcaddr` / `pkt_dstaddr` are the original packet endpoints. The dashboard keys conversations on `pkt_*addr`; so should you. (TGW logs have only `srcaddr`/`dstaddr`.)
6. **No entity context on the endpoints.** Addresses are raw IPs; they are *not* resolved to Dynatrace hosts/processes/pods. There are no `dt.smartscape.*` fields on flow records.

## Direction & semantics — read this

- **`flow_direction`** is `ingress` / `egress` **relative to the reporting ENI** (or TGW attachment), not client/server. A single conversation is captured at each ENI it traverses, so the same traffic appears as `egress` at the source ENI and `ingress` at the destination ENI. Summing both double-counts — pick one direction, or normalize the address pair client-side (as the inter-VPC query below does).
- **`action`** (`ACCEPT` / `REJECT`, VPC only) reflects the security-group / NACL decision. `REJECT` records are the security signal — blocked connection attempts. TGW logs have no `action`.
- **There is no client/server role field.** Infer the server side conventionally from the well-known port (usually the lower of `srcport` / `dstport`). Both ports are populated.
- **`traffic_path`** (VPC, egress only) codes where egress traffic went (see the mapping in [Egress traffic path](#5-egress-traffic-path)); it is `-` on ingress records.
- **AWS service endpoints:** `pkt_src_aws_service` / `pkt_dst_aws_service` name the AWS service (e.g. `AMAZON`, `EC2`, `S3`) when an endpoint is an AWS service range, else `-`.

## VPC vs Transit Gateway records

| | `aws.vpc` | `aws.tgw` |
|---|---|---|
| Vantage point | An ENI in a VPC/subnet | A Transit Gateway attachment |
| Endpoints | `srcaddr`/`dstaddr` (ENI hop) + `pkt_srcaddr`/`pkt_dstaddr` (true) | `srcaddr`/`dstaddr` only |
| Accept/Reject | `action` present | *(none)* |
| Topology fields | `vpc_id`, `subnet_id`, `az_id`, `interface_id`, `instance_id` | `tgw_id`, `tgw_attachment_id`, `tgw_src_*`/`tgw_dst_*`, `resource_type` |
| Packet loss | *(none)* | `packets_lost_total`, `_blackhole`, `_no_route`, `_mtu_exceeded`, `_ttl_expired` |
| `traffic_path` | egress only | *(none)* |

## Data Model

### VPC flow fields (`log.type == "aws.vpc"`)

| Field | Description |
|---|---|
| `pkt_srcaddr`, `pkt_dstaddr` | **True packet endpoint IPs** (strings) — use these for conversations |
| `srcaddr`, `dstaddr` | Endpoint IPs *as seen at the reporting ENI* (may be an intermediary) |
| `srcport`, `dstport` | L4 ports (strings) — both populated |
| `protocol`, `protocol.name` | IANA protocol number (`6`) and name (`TCP`/`UDP`/`ICMP`/`other`) |
| `bytes`, `packets` | Byte / packet counts (strings → `toLong`) |
| `action` | `ACCEPT` / `REJECT` (security-group + NACL decision) |
| `flow_direction` | `ingress` / `egress` relative to the ENI |
| `log_status` | `OK` (usable) / `NODATA` / `SKIPDATA` — **filter to `OK`** |
| `tcp_flags` | Cumulative TCP flags for the flow |
| `type` | IP version: `IPv4` / `IPv6` |
| `traffic_path` | Egress path code `1`–`8` (see below); `-` on ingress |
| `pkt_src_aws_service`, `pkt_dst_aws_service` | AWS service name for an endpoint, else `-` |
| `vpc_id`, `subnet_id`, `az_id` | VPC / subnet / availability-zone id |
| `interface_id`, `instance_id` | Reporting ENI id / attached EC2 instance (`-` if none) |
| `account_id`, `region` | AWS account and region |
| `start`, `end` | Flow window (epoch seconds, string) |

### Transit Gateway fields (`log.type == "aws.tgw"`)

| Field | Description |
|---|---|
| `srcaddr`, `dstaddr`, `srcport`, `dstport` | Flow endpoints and ports |
| `protocol`, `bytes`, `packets`, `tcp_flags`, `type` | As for VPC |
| `tgw_id`, `tgw_attachment_id` | Transit Gateway and the reporting attachment |
| `tgw_src_vpc_id`, `tgw_dst_vpc_id` | Source / destination VPC of the flow (`-` if outside) |
| `tgw_src_az_id`, `tgw_dst_az_id` | Source / destination AZ |
| `tgw_src_subnet_id`, `tgw_dst_subnet_id`, `tgw_src_eni`, `tgw_dst_eni` | Source/destination subnet and ENI |
| `tgw_pair_attachment_id` | The paired attachment on the other side of the TGW |
| `packets_lost_total` | Total packets dropped by the TGW for the flow |
| `packets_lost_no_route`, `packets_lost_blackhole`, `packets_lost_mtu_exceeded`, `packets_lost_ttl_expired` | Loss broken down by cause |
| `resource_type` | `TransitGateway` |

### AWS / ingestion metadata

`log.type` (`aws.vpc` / `aws.tgw` — the filter that isolates flow logs), `aws.log_group`, `aws.log_stream`, `aws.region`, `aws.account.id` / `cloud.account.id`, `cloud.provider` = `aws`, `aws.data_firehose.arn`, `timestamp`.

> **Discover the full field set** on your tenant: `fetch logs | filter log.type == "aws.vpc" and log_status == "OK" | limit 1`

## Base Query

```dql
fetch logs, from:now()-2h
| filter log.type == "aws.vpc"
| filter log_status == "OK"
```

Common filters:

```dql-snippet
| filter action == "REJECT"                          // blocked traffic only
| filter flow_direction == "egress"
| filter pkt_dstaddr == "10.0.0.100"                 // no toIp() — plain string
| filter dstport == "443"
| filter protocol.name == "TCP"
| filter vpc_id == "vpc-0123456789abcdef0"           // one VPC
| filter pkt_dst_aws_service != "-"                  // traffic to an AWS service
```

## Use Case Queries

These mirror the shipped **Network analytics** dashboard (`dynatrace.infraops.Network-analytics`). The dashboard defaults to `flow_direction = egress`, `action = ACCEPT`, and a `*flow-logs*` log-group filter; the queries below use `log.type` instead (more robust) and state the direction explicitly.

### 1. Top conversations

```dql
fetch logs, from:now()-2h
| filter log.type == "aws.vpc"
| filter log_status == "OK" and action == "ACCEPT"
| summarize { bytes = sum(toLong(bytes)), packets = sum(toLong(packets)), flows = count() },
    by: { src = pkt_srcaddr, dst = pkt_dstaddr, port = dstport, proto = protocol.name }
| sort bytes desc
| limit 20
```

> Traffic is captured per ENI and per direction. To fold `A→B` and `B→A` together, normalize the pair client-side (see the inter-VPC query) or restrict to one `flow_direction`.

### 2. Top talkers — sources and destinations

There is no client/server role, so look at each side separately.

**Top destinations (what receives the most traffic):**

```dql
fetch logs, from:now()-2h
| filter log.type == "aws.vpc"
| filter log_status == "OK" and action == "ACCEPT"
| summarize bytes = sum(toLong(bytes)), by: { dst = pkt_dstaddr }
| sort bytes desc
| limit 10
```

Swap `pkt_dstaddr` → `pkt_srcaddr` for top sources.

### 3. Rejected / blocked traffic (security)

`REJECT` records are attempted connections the security groups or NACLs blocked — surface the top blocked source→port pairs:

```dql
fetch logs, from:now()-2h
| filter log.type == "aws.vpc"
| filter log_status == "OK" and action == "REJECT"
| summarize { attempts = count(), bytes = sum(toLong(bytes)) },
    by: { src = pkt_srcaddr, dst = pkt_dstaddr, port = dstport }
| sort attempts desc
| limit 20
```

### 4. Top ports and protocol breakdown

```dql
fetch logs, from:now()-2h
| filter log.type == "aws.vpc"
| filter log_status == "OK" and action == "ACCEPT"
| summarize { bytes = sum(toLong(bytes)), flows = count() }, by: { port = dstport }
| sort bytes desc
| limit 10
```

Swap the `by:` dimension for `protocol.name` (TCP/UDP/ICMP) or `type` (IPv4/IPv6) for the protocol / IP-version tiles.

### 5. Egress traffic path

`traffic_path` (egress only) codes where AWS routed the traffic. Map it to a label:

```dql
fetch logs, from:now()-2h
| filter log.type == "aws.vpc"
| filter log_status == "OK" and flow_direction == "egress"
| summarize bytes = sum(toLong(bytes)), by: { traffic_path }
| fieldsAdd destination = coalesce(
    if(traffic_path == "1", "Same VPC"),
    if(traffic_path == "2", "Internet/gateway VPC endpoint"),
    if(traffic_path == "3", "Virtual private gateway"),
    if(traffic_path == "4", "Intra-region VPC peering"),
    if(traffic_path == "5", "Inter-region VPC peering"),
    if(traffic_path == "6", "Local gateway"),
    if(traffic_path == "7", "Gateway VPC endpoint (Nitro)"),
    if(traffic_path == "8", "Internet gateway (Nitro)"),
    "Unknown")
| fields destination, traffic_path, bytes
| sort bytes desc
```

### 6. Traffic to AWS services

```dql
fetch logs, from:now()-2h
| filter log.type == "aws.vpc"
| filter log_status == "OK" and pkt_dst_aws_service != "-"
| summarize bytes = sum(toLong(bytes)), by: { service = pkt_dst_aws_service }
| sort bytes desc
```

### 7. Traffic by VPC, subnet, or AZ

```dql
fetch logs, from:now()-2h
| filter log.type == "aws.vpc"
| filter log_status == "OK" and action == "ACCEPT"
| summarize bytes = sum(toLong(bytes)), by: { vpc_id }
| sort bytes desc
```

Swap `vpc_id` for `subnet_id` or `az_id` as needed.

### 8. Inter-VPC traffic (bidirectional)

Pairs each direction of a conversation and sums both, then drops same-VPC traffic — the dashboard's inter-VPC tile. The same pattern with `az_id` gives inter-AZ traffic.

```dql
fetch logs, from:now()-2h
| filter log.type == "aws.vpc"
| filter log_status == "OK" and action == "ACCEPT"
| fieldsAdd bytes = toLong(bytes), key = record(a = pkt_srcaddr, b = pkt_dstaddr)
| summarize { s_bytes = sum(bytes) }, by: { vpc_id, key }
| lookup [
    fetch logs, from:now()-2h
    | filter log.type == "aws.vpc"
    | filter log_status == "OK" and action == "ACCEPT"
    | fieldsAdd bytes = toLong(bytes), key = record(a = pkt_dstaddr, b = pkt_srcaddr)
    | summarize { r_bytes = sum(bytes) }, by: { vpc_id, key }
  ], sourceField: key, lookupField: key, fields: { dst_vpc = vpc_id, r_bytes }
| filter isNotNull(dst_vpc) and vpc_id != dst_vpc
| fieldsAdd bytesTotal = s_bytes + r_bytes
| fieldsAdd pair = if(vpc_id <= dst_vpc, concat(vpc_id, " ⇄ ", dst_vpc), else: concat(dst_vpc, " ⇄ ", vpc_id))
| summarize Traffic = sum(bytesTotal), by: { pair }
| sort Traffic desc
```

> **Multi-region / overlapping RFC1918 note.** The join key is the IP pair only. Peered VPCs (the target of this query) cannot share IP ranges by AWS constraint, so false matches between communicating VPCs cannot occur. In large environments where isolated VPCs in different regions reuse the same RFC1918 space, unrelated flows with the same IP pair could create spurious pairs. If that is a concern, add `| filter region == "<region>"` after each `fetch logs` to scope to one region at a time.

### 9. Traffic over time

```dql
fetch logs, from:now()-2h
| filter log.type == "aws.vpc"
| filter log_status == "OK" and action == "ACCEPT"
| makeTimeseries Traffic = sum(toLong(bytes)), by: { vpc_id }, interval:15m
| sort arraySum(Traffic) desc
| limit 5
```

## Transit Gateway

### Traffic and packet loss per gateway / attachment

TGW logs report drops the gateway made — the key signal VPC logs lack. `packets_lost_no_route` and `_blackhole` point at routing misconfiguration; `_mtu_exceeded` at MTU mismatches; `_ttl_expired` at loops.

```dql
fetch logs, from:now()-2h
| filter log.type == "aws.tgw" and log_status == "OK"
| summarize {
    bytes = sum(toLong(bytes)),
    lost = sum(toLong(packets_lost_total)),
    noRoute = sum(toLong(packets_lost_no_route)),
    blackhole = sum(toLong(packets_lost_blackhole)),
    mtu = sum(toLong(packets_lost_mtu_exceeded)),
    ttl = sum(toLong(packets_lost_ttl_expired))
  },
  by: { tgw_id, src_vpc = tgw_src_vpc_id, dst_vpc = tgw_dst_vpc_id }
| sort bytes desc
| limit 20
```

## Relationship to OneAgent Flows & NetFlow

The same conversation can appear in several sources. Choose per what the user needs:

| | Cloud flow logs (AWS) | OneAgent flows | NetFlow / IPFIX |
|---|---|---|---|
| Vantage point | Cloud fabric (ENI / TGW) | Monitored host/process/pod | Network device |
| Endpoint context | Raw IPs + cloud topology (VPC/subnet/AZ) | Resolved to smartscape entity | Raw IPs only |
| Coverage | All VPC/TGW traffic, incl. managed services & agentless resources | Only OneAgent hosts | Whatever the device sees |
| Security signal | `action` ACCEPT/**REJECT**, TGW packet loss | Connection health (RTT, resets) | TCP flags |
| Directionality | Per-ENI, both directions | One aggregated record with client/server role | Unidirectional |

Lead with **cloud flow logs** for cloud-network questions — cross-VPC/AZ traffic, egress paths, blocked (`REJECT`) traffic, managed-service and agentless-resource coverage, and TGW routing drops. Prefer **OneAgent flows** when both endpoints are OneAgent-monitored (richer entity context and connection health).

## Resolve endpoints to Dynatrace entities

A flow-log endpoint is a raw IP. Resolve it two ways, in this order:

1. **Is the IP a OneAgent-monitored host, pod, or service?** → use the shared [peer / IP resolution](../../peer-resolution/peer-resolution.md) Smartscape lookups (host → pod → service → external). Richest context, and source-agnostic.
2. **Otherwise (agentless EC2, managed service, or you want cloud topology / ownership)** → resolve to the **AWS resource entity** with the AWS-specific lookups below. These cover resources that never run an agent, and add VPC/subnet/security-group/owner-tag context OneAgent doesn't carry.

> The AWS lookups require **AWS monitoring** (Smartscape resource polling) on the account/region — the ENI/instance must be a monitored resource. The DQL below was validated in shape against live `AWS_EC2_NETWORKINTERFACE` / `AWS_EC2_INSTANCE` entities; the flow-record → entity join itself was not exercised end-to-end on the validation tenant (its flow-log VPCs were in regions without AWS resource polling). AWS entity IPs are **not** a clean top-level `ip` array (as hosts/pods have) — they live inside the `aws.object` JSON blob, so IP matching means parsing it.

### By ID — the reporting ENI / instance (preferred)

VPC flow records carry `interface_id` (the reporting ENI); join it directly to `aws.resource.id`. No IP parsing, no ambiguity.

```dql-template
smartscapeNodes { AWS_EC2_NETWORKINTERFACE }
| filter aws.resource.id == "<interface_id>"       // e.g. "eni-0123456789abcdef0"
| fields id, name, eni = aws.resource.id, aws.vpc.id, aws.subnet.id,
    aws.availability_zone, securityGroups = aws.security_group.id, tags = `tags:aws`
```

The flow record's own `instance_id` is often `-`; get the attached instance from the ENI's `aws.object` (or join `instance_id` to `AWS_EC2_INSTANCE.aws.resource.id` when it is populated):

```dql-template
smartscapeNodes { AWS_EC2_INSTANCE }
| filter aws.resource.id == "<instance_id>"         // e.g. "i-0123456789abcdef0"
| fields id, name, instance = aws.resource.id, aws.state, aws.vpc.id, aws.subnet.id, tags = `tags:aws`
```

### By IP — the remote endpoint

The *other* end of a conversation (`pkt_srcaddr` / `pkt_dstaddr`) has no `interface_id`. Match its IP against the private IPs an ENI carries — parse `aws.object` and expand `privateIpAddresses`:

```dql-template
smartscapeNodes { AWS_EC2_NETWORKINTERFACE }
| parse aws.object, "JSON:obj"
| fieldsAdd privIps = obj[configuration][privateIpAddresses][][privateIpAddress]
| filter in("<IP>", privIps)                        // plain string, no toIp()
| fields id, eni = aws.resource.id, instanceId = obj[configuration][attachment][instanceId],
    ownedBy = obj[configuration][description],       // identifies the owning service (see below)
    requesterManaged = obj[configuration][requesterManaged],
    aws.vpc.id, aws.subnet.id, securityGroups = aws.security_group.id, tags = `tags:aws`
```

> The public IP (for internet-facing ENIs) sits at `obj[configuration][association][publicIp]` — add it to the match if you resolve public addresses.

The `securityGroups` and owner `tags:aws` (e.g. `dt_owner_team`, `dt_owner_email`) are the payoff for **`REJECT`** investigation: they tell you which resource and team own the endpoint that was blocked or is generating denied traffic.

### Other AWS services resolve *through* the ENI

Don't look for per-service IP lookups — most managed AWS entities aren't keyed by IP. `AWS_RDS_DBINSTANCE` exposes a **DNS endpoint** (`…rds.amazonaws.com:5432`), not an address; API Gateway is an edge/managed service and generally doesn't appear as a VPC IP at all (only a *private* API does, via a VPC-endpoint ENI). What they share is that every VPC-resident service reaches the wire through a **requester-managed ENI** — so the IP → ENI lookup above already resolves them, and `requesterManaged == true` plus the ENI's `description` tells you *what* the endpoint is:

| ENI `description` pattern | Owning service |
|---|---|
| `arn:aws:ecs:…attachment/…` | ECS task (awsvpc mode) — *(validated on tenant)* |
| `RDSNetworkInterface` | RDS / Aurora database |
| `ELB app/…` · `ELB net/…` | Application / Network Load Balancer |
| `AWS Lambda VPC ENI…` | VPC-attached Lambda |
| `Interface for NAT Gateway nat-…` | NAT Gateway |
| `VPC Endpoint Interface vpce-…` | Interface VPC endpoint (PrivateLink) |
| *(empty)*, `requesterManaged == false` | Customer ENI — an EC2 instance or pod (resolve via [peer resolution](../../peer-resolution/peer-resolution.md)) |

> Only the ECS pattern was directly observed on the validation tenant; the others follow AWS's standard ENI-description conventions. To go from the ENI to the concrete service entity, join the named id (e.g. the `vpce-…` / `nat-…` / db name in the description) to that entity type's `aws.resource.id`, or match the RDS endpoint DNS separately.

## Other providers

Azure (NSG / VNet flow logs) and GCP (VPC Flow Logs) follow the same shape — 5-tuple + action + bytes, landing in `logs` — but their field names and ingestion differ and are **not yet validated**. This reference is AWS-only; extend it per provider when tenant data is available.

## Troubleshooting

| Problem | Cause | Solution |
|---|---|---|
| Query scans huge volumes / slow | Reading all of `default_logs` | Route flow logs to a dedicated bucket and `fetch logs, bucket:"..."` — see [configuration.md](configuration.md) |
| Don't know which bucket flow logs land in | Bucket isn't in the log payload | Group by the `dt.system.bucket` metadata field — see [configuration.md → Find which bucket the logs are currently in](configuration.md#find-which-bucket-the-logs-are-currently-in) |
| Aggregations include junk rows / null addresses | `NODATA` / `SKIPDATA` capture-gap records | Always `filter log_status == "OK"` |
| `sum(bytes)` errors or returns odd values | Counter is a string | Wrap with `toLong(...)` / `toDouble(...)` |
| IP filter matches nothing | Cast a string field with `toIp(...)` | These fields are plain strings — compare to bare string literals |
| Conversation totals look doubled | Traffic captured at both ENIs / both directions | Restrict to one `flow_direction`, or normalize the pair (query 8) |
| Endpoint is a NAT/LB address, not the real client | Used `srcaddr`/`dstaddr` | Use `pkt_srcaddr`/`pkt_dstaddr` for the true endpoints |
| `action` / `pkt_*addr` / `vpc_id` empty | Record is a TGW log (`aws.tgw`) | Those fields are VPC-only; use `tgw_*` fields |
| No data at all | Forwarding misconfigured | See [configuration.md → Verify data is arriving](configuration.md#verify-data-is-arriving) |

## References

- [configuration.md](configuration.md) — ingestion path (Amazon Data Firehose) and dedicated-bucket routing.
- [End-to-end log & network observability on AWS](https://docs.dynatrace.com/docs/shortlink/lma-e2e-observability)
- Shipped dashboard: `dynatrace.infraops.Network-analytics` (Network analytics)
