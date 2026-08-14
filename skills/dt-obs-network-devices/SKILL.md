---
name: dt-obs-network-devices
description: >-
  Analyze SNMP-monitored network devices (switches, routers, firewalls, load
  balancers) in Dynatrace. Three data layers: Smartscape topology
  (`EXT_NETWORK_DEVICE` / `EXT_NETWORK_INTERFACE` nodes, `belongs_to` and
  `calls` edges); `com.dynatrace.extension.network_device.*` metrics (CPU,
  memory, uptime, throughput, saturation, errors); and logs (SNMP traps,
  syslog, auto-discovery). Use to inventory devices, find down or saturated
  interfaces, check device CPU/memory/uptime, map topology and neighbors,
  detect interface errors, and investigate traps and syslog events.
  Trigger: "network device", "switch", "router", "firewall", "SNMP",
  "interface status", "interface down", "interface utilization",
  "link saturation", "device CPU", "device memory", "device uptime",
  "device neighbors", "LLDP", "CDP", "SNMP trap", "syslog".
  Do NOT use for network flow/traffic or top talkers (use dt-obs-network-flows),
  host NIC throughput (use dt-obs-hosts), or service request/latency (use
  dt-obs-services).
license: Apache-2.0
---

# Network Devices Skill

Analyze SNMP-monitored network infrastructure in Dynatrace — switches, routers, firewalls, load balancers, access points, and any other device polled by a **network device extension** (the SNMP-generic and vendor SNMP extensions). This skill covers the **device and interface data model** and routes each question to the right reference file. All DQL lives in the reference files and was validated against a live tenant with `dtctl query`.

## What Network Device Monitoring Tells You

SNMP extensions poll network hardware and expose it in Dynatrace as **three layers**:

- **Topology** — an inventory of devices and their interfaces as Smartscape nodes (`EXT_NETWORK_DEVICE`, `EXT_NETWORK_INTERFACE`), with attributes (vendor, model, OS/firmware, location, contact, IPs, MACs, link speed) and relationships (which interface belongs to which device; which devices are neighbors via LLDP/CDP).
- **Metrics** — time series for device health (CPU, memory, uptime) and per-interface health (operational/admin status, in/out throughput, errors, discards, packet mix), under the `com.dynatrace.extension.network_device.*` namespace.
- **Logs** — event-driven records: SNMP traps (link-up/down, hardware faults), syslog messages (config changes, authentication, interface events), and auto-discovery activity (devices and neighbors found per poll cycle).

This answers questions such as: *Which interfaces are down? Which links are saturated? Is this router's CPU pegged? Which devices rebooted? What is connected to this switch? What traps has this device sent? What syslog errors are recurring?*

## The Three Layers (and how they join)

| Layer | Query with | Grain | Key fields |
|---|---|---|---|
| **Topology** | `smartscapeNodes "EXT_NETWORK_DEVICE"` / `smartscapeNodes "EXT_NETWORK_INTERFACE"` | One row per device / interface (current inventory) | `id`, `name`, `monitoring_mode`, `device_type`, `location`, `ip`, `speed`, edges via `belongs_to` / `calls` |
| **Metrics** | `timeseries … com.dynatrace.extension.network_device.*` | Time series per device / interface | grouped by `dt.smartscape.ext_network_device` and (interface metrics) `dt.smartscape.ext_network_interface` |
| **Logs** | `fetch logs \| filter dt.openpipeline.source == "…"` | Individual log records (traps, syslog, discovery) | joined to topology by expanding the device `ip[]` array and matching `device.address` / `dt.ingest.source.ip` — see [references/logs.md](references/logs.md) |

**The join key is the Smartscape ID.** Every metric carries a `dt.smartscape.ext_network_device` dimension (and interface metrics also carry `dt.smartscape.ext_network_interface`). Use `lookup [smartscapeNodes …]` to attach human-readable device/interface names to metric results, and to attach live metrics to an inventory listing. Both reference files show this pattern.

## Monitoring Mode Determines What Data Exists

Every device has a `monitoring_mode`. **This is the first thing to check** — it decides whether metrics exist at all:

| `monitoring_mode` | Meaning | Has metrics? | Has full attributes? |
|---|---|---|---|
| **`Extension`** | Directly polled by an SNMP extension | **Yes** — full `com.dynatrace.extension.network_device.*` set | Yes |
| **`Discovery`** | Discovered on the network but not directly polled | **No** | Partial |
| **`Neighbor`** | Known only because a polled device names it as an LLDP/CDP neighbor | **No** | Minimal (name, chassis MAC) |

> If a device has no metrics, check its `monitoring_mode` before assuming a data gap — only `Extension`-mode devices are polled. When listing "monitored devices," exclude `Neighbor` (and usually `Discovery`).

## Routing

1. **Inventory, attributes, or topology** (list devices, find a device's interfaces, map neighbors, read model/firmware/location) → [references/topology-model.md](references/topology-model.md).
2. **Health or performance** (CPU, memory, uptime, interface up/down, throughput, saturation, errors) → [references/metrics.md](references/metrics.md).
3. **Event-driven signals** (SNMP traps, syslog messages, discovery activity) → [references/logs.md](references/logs.md).
4. Most real questions combine layers (e.g. *"which interfaces on the core router are down"* = metric status filtered to one device, joined to interface names). The metrics and logs references show these joined queries.

## Related Skills

Network device monitoring is one part of Dynatrace network observability. Route elsewhere when the question is not about device/interface health or topology:

| The user wants… | Use |
|---|---|
| Traffic **between** entities, top talkers, conversations, connection health (the flows *through* the network) | [dt-obs-network-flows](../dt-obs-network-flows/SKILL.md) — including NetFlow/IPFIX/sFlow that these same devices export |
| Host NIC throughput / packet drops on **OneAgent-monitored hosts** (not SNMP devices) | [dt-obs-hosts](../dt-obs-hosts/SKILL.md) → `references/host-metrics.md` |
| Service request rate, latency, error rate | [dt-obs-services](../dt-obs-services/SKILL.md) |
| Setting up or configuring an extension (this skill covers the resulting **data model**, not extension authoring) | [dt-obs-extensions](../dt-obs-extensions/SKILL.md) |
| General Smartscape traversal syntax (`traverse`, `smartscapeEdges`, `references[…]`) | [dt-dql-essentials](../dt-dql-essentials/references/smartscape-topology-navigation.md) |

> **Network devices vs. network flows.** This skill answers *"what is the state of the box and its ports"* (SNMP device/interface health and topology). `dt-obs-network-flows` answers *"what traffic is crossing the network"* (conversations, bytes, talkers). The same router appears in both: here as an `EXT_NETWORK_DEVICE` with interface counters, there as a NetFlow exporter. A future macro **`dt-obs-network`** skill may unify them; until then, cross-link.

## Reference Files

- [references/topology-model.md](references/topology-model.md) — **Validated.** The Smartscape model: `EXT_NETWORK_DEVICE` and `EXT_NETWORK_INTERFACE` node types with full field reference, monitoring modes, and the `belongs_to` / `calls` edges. DQL for device inventory (with filtering by mode/type/location/vendor), listing a device's interfaces, resolving an interface to its device, and mapping device/interface neighbor topology.
- [references/metrics.md](references/metrics.md) — **Validated.** The `com.dynatrace.extension.network_device.*` metric catalog with units, dimensions, and field-typing rules. DQL for device health (top CPU, memory % with fallback, uptime and reboot detection) and interface health (down interfaces, throughput and saturation vs. link speed, error/discard counts, per-device interface detail), each joined to device/interface names.
- [references/logs.md](references/logs.md) — **Validated.** The three log sources: SNMP traps (`extension:com.dynatrace.extension.snmp-traps-generic`), syslog (`extension:syslog`), and auto-discovery activity (`extension:com.dynatrace.extension.snmp-auto-discovery`). Covers the IP-to-Smartscape join pattern (`device.address` / `dt.ingest.source.ip` → `snmp.ip`), field references for all three sources, and DQL for recent traps with device names, trap frequency by OID, error syslog, top event patterns, combined per-device view, and LLDP/CDP neighbor discovery logs.
