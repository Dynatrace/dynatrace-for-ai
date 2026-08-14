# Network Device Topology Model

The Smartscape model for SNMP-monitored network devices: the `EXT_NETWORK_DEVICE` and `EXT_NETWORK_INTERFACE` node types, their attributes, and the edges between them. Use this file for inventory, device attributes (model, OS, location), and topology (a device's interfaces, neighbor devices).

> All DQL in this file was validated against a live tenant with `dtctl query`. For metrics (CPU, throughput, interface status over time), see [metrics.md](metrics.md).

## Node Types

Two node types make up the model. Query either with `smartscapeNodes "<TYPE>"`.

| Type | Represents | Approx. count per device |
|---|---|---|
| `EXT_NETWORK_DEVICE` | A physical device with network connectivity — switch, router, firewall, load balancer, access point, printer, etc. | 1 |
| `EXT_NETWORK_INTERFACE` | A physical or virtual interface/port on a device | many (an `interface_count` field is on the device) |

Vendor SNMP extensions may add device sub-component node types (e.g. `JUNIPER_ROUTING_ENGINE`, `JUNIPER_FRU`, `JUNIPER_DISK`, `JUNIPER_INSTALLED_APP` linked to the device via `runs_on` / `is_part_of`). These are extension-specific; the portable model is device + interface.

## Monitoring Mode — check this first

`monitoring_mode` decides how much data a device has. **Only `Extension`-mode devices are polled and therefore have metrics** (see [metrics.md](metrics.md)).

| `monitoring_mode` | Meaning | Metrics | Attributes |
|---|---|---|---|
| `Extension` | Directly polled by an SNMP extension | Yes | Full |
| `Discovery` | Discovered on the network, not directly polled | No | Partial |
| `Neighbor` | Named only as an LLDP/CDP neighbor of a polled device | No | Minimal (name, chassis MAC) |

When listing "monitored devices," exclude `Neighbor` (and usually `Discovery`).

## `EXT_NETWORK_DEVICE` Field Reference

| Field | Type | Description |
|---|---|---|
| `id` | smartscapeId | Device entity ID (`EXT_NETWORK_DEVICE-<hex>`). Derived from the chassis MAC. Filter with `toSmartscapeId(…)`. |
| `id_classic` | string | Deprecated Classic `CUSTOM_DEVICE-…` id. |
| `name` | string | Device name (usually the SNMP sysName / hostname). |
| `monitoring_mode` | string | `Extension` / `Discovery` / `Neighbor` (see above). |
| `device_type` | string | Device family (e.g. `cisco`, `cisco-nexus`, `juniper`, `f5-big-ip`, `fortinet-fortigate`, `generic`). Often `null`. |
| `ip` | string[] * | All IP addresses on the device (IPv4 and IPv6). *Typed `ipAddress[]` in the semantic dictionary but returned as `string[]` on this entity — see the IP typing caution.* |
| `mac` | string[] | MAC addresses. |
| `chassis_mac` | string | Chassis MAC — the identity anchor for the device and its interfaces. |
| `description` | string | SNMP sysDescr (vendor/model/OS string). |
| `vendor` | string | Vendor. May be `null`. |
| `os.name`, `firmware_revision`, `hardware_revision`, `software_revision` | string | OS / firmware / hardware / software versions. |
| `serial_number`, `part_number` | string | Hardware identifiers. |
| `location`, `contact` | string | SNMP sysLocation / sysContact. May be `"n/a"`. |
| `capabilities` | string[] | Device capabilities. |
| `lldp.chassis_id`, `cdp.device_id` | string | LLDP/CDP identifiers used to build neighbor edges. |
| `snmp.ip`, `snmp.sys_object_id` | string | SNMP polling IP and sysObjectID (`.1.3.6.1.4.1.…`, encodes vendor/model). |
| `autodiscovery.group_label`, `autodiscovery.config_label`, `autodiscovery.default_extension` | string | Autodiscovery grouping and the extension recommended for the device. |
| `interface_count` | string(long) | Number of interfaces on the device. |
| `dt.security_context` | string[] | Security context (for record-level permissions). |
| `tags` | record | Tags. |
| `lifetime` | timeframe | Entity observation window (`start`/`end`). |

> **Discover the full, current field set on your tenant:** `smartscapeNodes "EXT_NETWORK_DEVICE" | limit 1`

## `EXT_NETWORK_INTERFACE` Field Reference

| Field | Type | Description |
|---|---|---|
| `id` | smartscapeId | Interface entity ID (`EXT_NETWORK_INTERFACE-<hex>`). Derived from device chassis MAC + interface name. |
| `id_classic` | string | Deprecated Classic id. |
| `name` | string | Interface name (e.g. `ge-0/0/11`, `Ethernet1/15`, `Fa0/21`). |
| `description`, `alias` | string | ifDescr / ifAlias — often carries the link's purpose or the far-end device. |
| `interface_type` | string | ifType (e.g. `ethernetCsmacd(6)`). |
| `interface_index` | string(long) | SNMP ifIndex. |
| `operational_status` | string | Operational state, e.g. `up(1)`, `down(2)`. **Use `startsWith(operational_status, "up")`** (see typing note). |
| `admin_status` | string | Administrative state, e.g. `up(1)`, `down(2)`. |
| `speed` | string(long) | Link speed in **Mbps** (`1000` = 1 Gbps, `100000` = 100 Gbps). `toDouble()` for math. |
| `mtu` | string(long) | MTU. |
| `mac` | string[] | Interface MAC(s). |
| `ip` | string[] * | IP(s) on the interface, when any. *Same `ipAddress[]`-vs-`string[]` caveat as the device `ip` field — see the IP typing caution.* |
| `device.chassis_mac` | string | Chassis MAC of the parent device (matches the device's `chassis_mac`). |
| `promiscuous_mode` | string | e.g. `false(2)`. |
| `lifetime` | timeframe | Observation window. |

> Some interfaces appear as duplicate nodes where the attribute fields are `null` (transient/duplicate discovery). Add `| filter isNotNull(operational_status)` when you only want interfaces with a known state.

### Status typing note

`operational_status` and `admin_status` are strings of the form `"<name>(<number>)"` — `"up(1)"`, `"down(2)"`, `"testing(3)"`. Do **not** compare with `== "up"`. Match with `startsWith(operational_status, "up")` / `startsWith(operational_status, "down")` (the metric dimensions `oper.status` / `admin.status` in [metrics.md](metrics.md) follow the same convention).

## Relationships (edges)

| Source | Edge | Target | Kind | Meaning |
|---|---|---|---|---|
| `EXT_NETWORK_INTERFACE` | `belongs_to` | `EXT_NETWORK_DEVICE` | static | Interface is a port on the device (reverse edge: `contains`). |
| `EXT_NETWORK_DEVICE` | `calls` | `EXT_NETWORK_DEVICE` | dynamic | Device-to-device physical adjacency / neighbor link (from LLDP/CDP) — the device topology map, **not** traffic. For traffic between devices, see [dt-obs-network-flows](../../dt-obs-network-flows/SKILL.md). |
| `EXT_NETWORK_INTERFACE` | `calls` | `EXT_NETWORK_INTERFACE` | dynamic | Physical link between two interfaces on neighboring devices. |

Traverse with `traverse`, `smartscapeEdges`, and `references[…]`. For the general syntax (direction, `fieldsKeep`, `dt.traverse.history`, `references` rules) see [dt-dql-essentials → smartscape-topology-navigation.md](../../dt-dql-essentials/references/smartscape-topology-navigation.md). `belongs_to` is a **static forward** edge, so it is available on the interface's `references` field; `calls` is **dynamic**, so it is only reachable via `traverse` / `smartscapeEdges`.

## Use Case Queries

### 1. Device inventory

List monitored devices with their key attributes, excluding neighbor-only entries:

```dql
smartscapeNodes "EXT_NETWORK_DEVICE"
| filterOut monitoring_mode == "Neighbor"
| fields name, monitoring_mode, device_type, vendor, location, ip, interface_count
| sort name asc
```

Common filters:

```dql-snippet
| filter monitoring_mode == "Extension"          // only directly-polled devices
| filter device_type == "juniper"                // one device family
| filter matchesValue(location, "*LON*")         // by location
| filter isNotNull(device_type) and device_type != "generic"                // exclude unclassified devices
```

Count devices by mode or type:

```dql
smartscapeNodes "EXT_NETWORK_DEVICE"
| summarize devices = count(), by: {monitoring_mode, device_type}
| sort devices desc
```

Find the device that owns a given IP. The safe, portable form is to `expand` the array and cast **both sides** to `ipAddress` with `toIp()` — this works whether the field is stored as `ipAddress` or `string` (see the caution below), and matches on IP semantics rather than text (so it also handles IPv6 zero-compression and case):

```dql
smartscapeNodes "EXT_NETWORK_DEVICE"
| expand ip
| filter toIp(ip) == toIp("15.15.16.2")
| fields name, monitoring_mode, device_type
```

#### IP Typing Caution

> **⚠️ Caution — IP field typing.** The semantic dictionary types `ip` (on devices and interfaces) as `ipAddress[]`, but **`EXT_NETWORK_DEVICE` and `EXT_NETWORK_INTERFACE` return it as `string[]`** in production — unlike `HOST` and `NETWORK_INTERFACE`, whose `ip` really is `ipAddress`. Check any entity type by inspecting `type(ip[0])` — e.g. `smartscapeNodes "*" | filter isNotNull(ip) and isNotNull(ip[0]) | fields type, ip_type = type(ip[0]) | summarize count(), by: {type, ip_type}`. Because these two types hold strings, a **one-sided** `toIp()` — `ip == toIp("…")` or `in(toIp("…"), ip)` — matches nothing (it compares an `ipAddress` against a string). Always cast **both** sides with `toIp()` (portable across both storage types).

### 2. A device's interfaces (with node-level status and speed)

Follow `belongs_to` **backward** from the device to its interfaces. Interface state and speed come straight from the node — no metric query needed for a point-in-time view:

```dql-template
smartscapeNodes "EXT_NETWORK_DEVICE"
| filter id == toSmartscapeId("<EXT_NETWORK_DEVICE-ID>")
| traverse edgeTypes: {belongs_to}, targetTypes: {EXT_NETWORK_INTERFACE}, direction: backward
| filter isNotNull(operational_status)
| fields iface = name, operational_status, admin_status, speed_mbps = speed, alias
| sort iface asc
```

To start from a device *name* instead of an ID, filter on `name` in the first stage (`| filter name == "NYC-Cisco-NEXUS9000-SWITCH"`).

Count a device's interfaces by operational state:

```dql-template
smartscapeNodes "EXT_NETWORK_DEVICE"
| filter id == toSmartscapeId("<EXT_NETWORK_DEVICE-ID>")
| traverse edgeTypes: {belongs_to}, targetTypes: {EXT_NETWORK_INTERFACE}, direction: backward
| filter isNotNull(operational_status)
| summarize interfaces = count(), by: {operational_status}
```

### 3. Resolve an interface to its device

`belongs_to` is a static forward edge, so read it directly from the interface's `references` field (no traversal):

```dql
smartscapeNodes "EXT_NETWORK_INTERFACE"
| fieldsAdd device = references[`belongs_to.ext_network_device`][0]
| fields iface = name, device_id = device, device_name = getNodeName(device)
| limit 20
```

### 4. Device neighbor topology (LLDP/CDP map)

List device-to-device neighbor links as source→target name pairs. Using `smartscapeEdges` with `getNodeName` is the most direct way to get the whole map:

```dql
smartscapeEdges "calls"
| filter source_type == "EXT_NETWORK_DEVICE" and target_type == "EXT_NETWORK_DEVICE"
| fields source = getNodeName(source_id), target = getNodeName(target_id)
| sort source asc
```

Neighbors of one specific device (its directly-connected devices):

```dql-template
smartscapeNodes "EXT_NETWORK_DEVICE"
| filter id == toSmartscapeId("<EXT_NETWORK_DEVICE-ID>")
| traverse edgeTypes: {calls}, targetTypes: {EXT_NETWORK_DEVICE}
| fields neighbor = name, neighbor_type = device_type
```

### 5. Attach live metrics to inventory

The inventory (this file) and metrics ([metrics.md](metrics.md)) join on the Smartscape ID. To enrich an inventory listing with a live metric, `lookup` a `timeseries` result keyed by `dt.smartscape.ext_network_device`:

```dql
smartscapeNodes "EXT_NETWORK_DEVICE"
| filter monitoring_mode == "Extension"
| fields id, name, device_type, location
| lookup [
    timeseries cpu = avg(com.dynatrace.extension.network_device.cpu_usage), by: {dt.smartscape.ext_network_device}
    | fieldsAdd cpu_avg = round(arrayAvg(cpu), decimals: 1)
    | fields dt.smartscape.ext_network_device, cpu_avg
  ], sourceField: id, lookupField: dt.smartscape.ext_network_device, prefix: "metric."
| filter isNotNull(metric.cpu_avg)
| fields name, device_type, location, cpu_avg = metric.cpu_avg
| sort cpu_avg desc
```

> The `lookup` yields `null` for `Extension`-mode devices that do not report the metric (not every device exposes every OID). Add `| filter isNotNull(metric.cpu_avg)` when you only want devices with a value.

See [metrics.md](metrics.md) for the reverse pattern (start from metrics, look up names) and the full metric catalog.
