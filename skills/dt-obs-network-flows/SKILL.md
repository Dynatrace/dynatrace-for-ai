---
name: dt-obs-network-flows
description: >-
  Network flow analysis in Dynatrace across three sources: OneAgent flows
  (host/process/pod-to-peer connections in the `default_network_flows` Grail
  bucket), NetFlow/IPFIX/sFlow (via an OpenTelemetry Collector), and cloud flow
  logs (AWS VPC / Transit Gateway; Azure and GCP planned). Use to analyze traffic
  between entities, find top talkers by bandwidth, map communication dependencies,
  investigate connection health (resets, timeouts, retransmissions, RTT), and
  resolve peers to monitored entities. Routes each question to the right source;
  source-specific DQL lives in the reference files.
  Trigger: "network flows", "top talkers", "traffic between hosts", "connection
  resets", "TCP retransmissions", "RTT", "pod connections", "network dependencies",
  "NetFlow", "IPFIX", "sFlow", "VPC flow logs", "cloud network traffic".
  Do NOT use for host NIC throughput or packet drops (use dt-obs-hosts), service
  request rate or latency (use dt-obs-services), or synthetic/uptime monitoring
  (use dt-obs-ext-monitors).
license: Apache-2.0
---

# Network Flows Skill

Analyze network traffic in Dynatrace across three flow data sources. This skill covers the **use cases** network flows enable and routes each question to the right source and reference file. The detailed, source-specific DQL lives in the reference files.

## What Network Flows Tell You

Network flow data answers questions that metrics and traces cannot:

- **Who talks to whom** — communication dependencies between hosts, processes, pods, services, and external endpoints
- **Top talkers** — which entities generate the most traffic, by bytes or connection count
- **Connection health** — resets, timeouts, retransmissions, and round-trip time (RTT) per conversation
- **Traffic composition** — protocol (TCP/UDP), destination ports, direction (client vs server)
- **Peer resolution** — mapping raw IP:port peers back to monitored entities (host, process, pod, service) or flagging them as external

---

## The Three Flow Sources

Choose the source based on **where the traffic is** and **what is capturing it**. When more than one applies, prefer the source with the richest entity context (usually OneAgent).

| Source | Captured by | Data location | Entity context | Use when |
|---|---|---|---|---|
| **OneAgent flows** | OneAgent network agent on the host | **events** in the `default_network_flows` Grail bucket | Rich — the capturing entity (client or server) resolved to host / process / pod smartscape IDs; the remote peer as IP:port | Traffic to/from OneAgent-monitored hosts, processes, or Kubernetes pods. **The default and most detailed source.** |
| **NetFlow / IPFIX / sFlow** | Network devices (switches, routers), ingested via an OpenTelemetry Collector | **logs** (`otel.scope.name == "otelcol/netflowreceiver"`; recommend routing to a dedicated bucket) | Device/interface level — raw IPs, exporter, interfaces; no smartscape entities | Traffic seen by network hardware. Covers east-west and north-south flows at the network layer. |
| **Cloud flow logs** | Cloud provider (AWS VPC / TGW; Azure, GCP not yet documented) | **logs** (`log.type == "aws.vpc"` / `"aws.tgw"`; recommend routing to a dedicated bucket) | Cloud resource level — VPC / subnet / AZ / ENI, TGW attachment; raw IPs, no smartscape entities | Traffic within/across cloud networks, including managed services and resources without an agent. |

### Routing logic

1. **Is the traffic to/from a OneAgent-monitored host, process, or pod?** → OneAgent flows. See [references/oneagent-flows/oneagent-flows.md](references/oneagent-flows/oneagent-flows.md).
2. **Is it device-level or from unmonitored hosts?** → NetFlow. See [references/netflow/netflow.md](references/netflow/netflow.md).
3. **Is it cloud-network / managed-service traffic?** → Cloud flow logs (per provider). AWS: [references/cloud-flows/aws/aws.md](references/cloud-flows/aws/aws.md).

> The three sources overlap. A pod-to-pod flow may appear in both OneAgent flows (with full pod context) and cloud flow logs (as ENI-to-ENI). Lead with the source that carries the entity context the user needs, and mention the alternative only if the primary source has no data.

---

## Related Network Data in Dynatrace

Network flows are one part of Dynatrace's network observability. Route to these when the question is not about flows:

| The user wants… | Use |
|---|---|
| Host NIC throughput, link utilization, packet drops/errors | [dt-obs-hosts](../dt-obs-hosts/SKILL.md) → `references/host-metrics.md` (Network Monitoring section) |
| Process-level network I/O and TCP connection quality metrics | [dt-obs-hosts](../dt-obs-hosts/SKILL.md) → `references/process-monitoring.md` |
| Kubernetes pod connections and cluster network topology | [dt-obs-kubernetes](../dt-obs-kubernetes/SKILL.md) |
| Service request rate, latency, error rate | [dt-obs-services](../dt-obs-services/SKILL.md) |
| External / synthetic uptime and network-availability monitors | [dt-obs-ext-monitors](../dt-obs-ext-monitors/SKILL.md) |
| Network devices — switches, routers, firewalls (SNMP/monitoring) | `dt-obs-network-devices` *(planned — not yet available)* |

> A future macro **`dt-obs-network`** skill may connect all network concepts (devices, hosts/process/pod metrics, flows, availability monitors, cloud network monitoring). Until it exists, this skill carries the flow-specific cross-links above.

---

## Reference Files

- [references/oneagent-flows/oneagent-flows.md](references/oneagent-flows/oneagent-flows.md) — **Validated.** Data model, field reference, and DQL for the `default_network_flows` bucket: top talkers, traffic maps, protocol/port breakdowns, connection health (resets/timeouts/retransmissions/RTT), bandwidth in bps, and which side of a flow is the peer.
- [references/peer-resolution/peer-resolution.md](references/peer-resolution/peer-resolution.md) — **Validated.** Shared Smartscape lookups that resolve a raw flow IP (and optional port) to a monitored host, process, Kubernetes pod, or service (host → pod → service → external). Used by both OneAgent flows and NetFlow.
- [references/oneagent-flows/configuration.md](references/oneagent-flows/configuration.md) — Enabling and tuning `builtin:network-connection-monitoring` (the setting that produces OneAgent flow data).
- [references/netflow/netflow.md](references/netflow/netflow.md) — **Validated.** NetFlow/IPFIX/sFlow ingested via an OpenTelemetry Collector into `logs`: data model, direction semantics (unidirectional, no client/server role), and DQL for top conversations/talkers/ports, protocol breakdowns, traffic-over-time, and per-exporter/per-interface views.
- [references/netflow/configuration.md](references/netflow/configuration.md) — OTel Collector `netflow`-receiver ingestion path and the dedicated-bucket routing recommendation for netflow logs.
- [references/cloud-flows/aws/aws.md](references/cloud-flows/aws/aws.md) — **Validated (AWS).** AWS VPC Flow Logs and Transit Gateway flow logs ingested into `logs`: `aws.vpc`/`aws.tgw` field model (incl. `pkt_srcaddr` vs `srcaddr`, `log_status` filtering), and DQL for top conversations/talkers/ports, rejected-traffic (security), egress `traffic_path`, per-VPC/subnet/AZ, inter-VPC, traffic-over-time, and TGW packet-loss. Also AWS entity resolution — ENI/instance by id or IP-in-`aws.object` — for agentless resources the shared peer lookups miss.
- [references/cloud-flows/aws/configuration.md](references/cloud-flows/aws/configuration.md) — Amazon Data Firehose ingestion path for AWS flow logs and the dedicated-bucket routing recommendation.

  *(Azure NSG/VNet and GCP VPC flow logs are not yet documented; add them as sibling `cloud-flows/<provider>/` folders when tenant data is available.)*
