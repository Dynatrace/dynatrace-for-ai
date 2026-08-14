# Network Device Logs

Three log sources complement the Smartscape topology and metrics for SNMP-monitored network devices. Use this file for event-driven signals (traps, syslog messages, discovery activity); for inventory and topology, see [topology-model.md](topology-model.md); for time-series health metrics, see [metrics.md](metrics.md).

> All DQL in this file was validated against a live tenant with `dtctl query`.

## Log Sources

| Source | `dt.openpipeline.source` filter | What it contains |
|---|---|---|
| **SNMP Traps** | `"extension:com.dynatrace.extension.snmp-traps-generic"` | Trap PDUs received from devices: interface link-up/down (`IF-MIB::linkUp/linkDown`), hardware faults, threshold crossings, and any other trap the device sends. |
| **Syslog** | `"extension:syslog"` | Device-sent syslog messages: Cisco `%FACILITY-SEV-MNEMONIC` events, config changes, authentication events, interface state changes, and free-form messages. Severity is already parsed into `loglevel` / `status`. |
| **Auto-discovery** | `"extension:com.dynatrace.extension.snmp-auto-discovery"` | SNMP auto-discovery activity: devices and interfaces found during each discovery poll, plus neighbor topology discovered via LLDP/CDP. An audit trail of what the extension found, emitted each poll cycle (not just for new devices). |

## Joining Log Records to Smartscape Nodes

Log records do not carry a `dt.smartscape.ext_network_device` dimension (unlike metrics). The join path depends on the source:

| Source | Log field | Node field | Notes |
|---|---|---|---|
| Traps | `device.address` | `ip[]` on `EXT_NETWORK_DEVICE` (expanded) | Expand the ip array so any of the device's IPs can match — not just the SNMP polling address. `device.name` on the trap record is often empty; use the join for names. |
| Syslog | `dt.ingest.source.ip` | `ip[]` on `EXT_NETWORK_DEVICE` (expanded) | Same expansion. `syslog.hostname` carries what the device sent in the syslog header — may differ from the Smartscape name. |
| Auto-discovery | `dt.smartscape.ext_network_device` | `id` on `EXT_NETWORK_DEVICE` | Direct Smartscape ID — no IP join needed. |

Joining on `snmp.ip` (the polling address alone) works in most environments but fails when a device sends logs or traps from a different IP — common when there is no dedicated out-of-band management network and the device is reachable via multiple addresses. Expanding the `ip` array in the lookup subquery covers all of a device's known addresses:

**Pattern (traps and syslog):**
```dql-snippet
| lookup [smartscapeNodes "EXT_NETWORK_DEVICE" | expand ip | fields id, name, ip],
    sourceField: <log-ip-field>, lookupField: ip, prefix: "node."
```

> The `ip` field on `EXT_NETWORK_DEVICE` is `string[]` (see the [IP typing caution](topology-model.md#ip-typing-caution) in topology-model.md). After `expand ip`, each element is a plain string — the same type as `device.address` and `dt.ingest.source.ip` on the log records — so the lookup key comparison is string-to-string and resolves correctly.

If `node.name` is still null after the lookup, the source IP is not in the device's `ip` array at all — it may be a Neighbor-mode device (no full inventory) or an unmonitored host. Inspect with: `smartscapeNodes "EXT_NETWORK_DEVICE" | expand ip | filter ip == "<source-ip>" | fields name, monitoring_mode, ip`.

## SNMP Traps

### Field Reference

| Field | Notes |
|---|---|
| `device.address` | Source IP of the trap. Join key to the `ip[]` array on `EXT_NETWORK_DEVICE` (expand + lookup). |
| `device.name` | Device name — often **empty** on the log record; use the Smartscape lookup instead. |
| `snmp.trap_oid` | Trap OID, typically in MIB-symbolic form (e.g. `IF-MIB::linkUp`, `IF-MIB::linkDown`). |
| `if.index` | SNMP interface index from the trap varbind (when the trap is interface-related). |
| `snmp.version` | SNMP version (`1`, `2c`, `3`). |
| `content` | Human-readable description — e.g. `SNMP trap (IF-MIB::linkUp) reported from src:<ip>`. |
| `status` | Always `NONE` (traps carry no log severity). |
| `loglevel` | Always `NONE`. |
| `timestamp` | When the trap was received by the extension. |

### 1. Recent traps with device names

```dql
fetch logs, from: now()-1h
| filter dt.openpipeline.source == "extension:com.dynatrace.extension.snmp-traps-generic"
| lookup [smartscapeNodes "EXT_NETWORK_DEVICE" | expand ip | fields id, name, ip],
    sourceField: `device.address`, lookupField: ip, prefix: "node."
| fields timestamp, device = node.name, `device.address`, `snmp.trap_oid`, content
| sort timestamp desc
```

### 2. Trap frequency by OID and device

Useful for baselining noisy traps (e.g. periodic `IF-MIB::linkUp` floods) before setting up suppression:

```dql
fetch logs, from: now()-24h
| filter dt.openpipeline.source == "extension:com.dynatrace.extension.snmp-traps-generic"
| lookup [smartscapeNodes "EXT_NETWORK_DEVICE" | expand ip | fields id, name, ip],
    sourceField: `device.address`, lookupField: ip, prefix: "node."
| summarize count = count(), by: {device = node.name, oid = `snmp.trap_oid`}
| sort count desc
| limit 20
```

## Syslog

### Field Reference

| Field | Notes |
|---|---|
| `dt.ingest.source.ip` | Source IP of the syslog message. Join key to the `ip[]` array on `EXT_NETWORK_DEVICE` (expand + lookup). |
| `syslog.hostname` | Hostname from the syslog message header (what the device sent). May differ from the Smartscape `name`. |
| `syslog.appname` | Cisco-style `%FACILITY-SEV-MNEMONIC` identifier (e.g. `%LINK-3-UPDOWN`, `%SYS-5-CONFIG_I`). |
| `syslog.message` | Parsed message body (without the syslog header). |
| `syslog.severity` | Numeric severity (0–7, RFC 5424). |
| `syslog.facility` | Numeric facility (0–23, RFC 5424). |
| `syslog.priority` | Combined priority (`facility * 8 + severity`). |
| `content` | Raw syslog line including the header. |
| `status` | Mapped severity: `ERROR`, `WARN`, `INFO`. |
| `loglevel` | Same as `status`. Filter on `status` for simple severity checks. |
| `timestamp` | When the message was received. |

### 3. Recent error syslog with device names

```dql
fetch logs, from: now()-1h
| filter dt.openpipeline.source == "extension:syslog"
| filter status == "ERROR"
| lookup [smartscapeNodes "EXT_NETWORK_DEVICE" | expand ip | fields id, name, ip],
    sourceField: `dt.ingest.source.ip`, lookupField: ip, prefix: "node."
| fields timestamp, device = node.name, `dt.ingest.source.ip`, loglevel, `syslog.appname`, `syslog.message`
| sort timestamp desc
```

### 4. Top error and warning message patterns

Identifies the noisiest event types across all devices — useful for finding recurring faults or tuning noise suppression:

```dql
fetch logs, from: now()-24h
| filter dt.openpipeline.source == "extension:syslog"
| filter status == "ERROR" or status == "WARN"
| summarize count = count(), by: {loglevel, appname = `syslog.appname`}
| sort count desc
| limit 20
```

### 5. All logs for one device (traps + syslog combined)

Scope by device IP for a single-pane view of all event-driven signals from one device. Replace `<device-ip>` with the IP the device uses as a log/trap source — look it up with `smartscapeNodes "EXT_NETWORK_DEVICE" | filter name == "…" | fields ip, snmp.ip`. This query matches on a single source IP; on multi-homed devices the device may send from any of its IPs, so use the lookup-based queries (1–3 above) for full coverage.

```dql-template
fetch logs, from: now()-1h
| filter (dt.openpipeline.source == "extension:com.dynatrace.extension.snmp-traps-generic"
          and `device.address` == "<device-ip>")
      or (dt.openpipeline.source == "extension:syslog"
          and `dt.ingest.source.ip` == "<device-ip>")
| fields timestamp, dt.openpipeline.source, status, content
| sort timestamp desc
```

## Auto-discovery Logs

These logs are written each time the SNMP auto-discovery extension polls, not just when a new device or neighbor appears — they are an audit trail of discovery activity, not a change log. Two sub-types are differentiated by the `content` field:

| `content` value | What it records |
|---|---|
| `"Device discovery"` | A device (and its attributes) found in the current discovery poll. Carries full device attributes and `dt.smartscape.ext_network_device`. |
| `"Neighbor discovery"` | A device-to-device or interface-to-interface neighbor link found via LLDP/CDP. Carries the observing device's Smartscape IDs and `neighbor.*` fields for the far end. |

### Field Reference — Device discovery records

| Field | Notes |
|---|---|
| `dt.smartscape.ext_network_device` | Direct Smartscape ID — join to `EXT_NETWORK_DEVICE.id`. |
| `name` | Device name (same as the Smartscape node `name`). |
| `ip` | Primary IP. |
| `monitoring_mode` | Always `"Discovery"` in autodiscovery logs — the extension does not emit discovery records for `Extension`-mode devices (see [topology-model.md](topology-model.md#monitoring-mode--check-this-first)). |
| `device_type` | Device family (e.g. `fortinet-fortigate`, `cisco-nexus`). |
| `description` | SNMP sysDescr. |
| `location`, `contact` | SNMP sysLocation / sysContact. |
| `chassis_mac`, `mac` | MAC addresses. |
| `snmp.ip`, `snmp.sys_object_id` | SNMP polling address and sysObjectID. |
| `autodiscovery.config_label`, `autodiscovery.group_label`, `autodiscovery.default_extension` | Autodiscovery grouping metadata. |

### Field Reference — Neighbor discovery records

| Field | Notes |
|---|---|
| `dt.smartscape.ext_network_device` | Smartscape ID of the **observing** (polled) device. |
| `dt.smartscape.ext_network_interface` | Smartscape ID of the observing interface that reported the neighbor. |
| `neighbor.device.name` | Neighbor device name. |
| `neighbor.device.ip` | Neighbor device IP (when available). |
| `neighbor.interface.name`, `neighbor.interface.description` | Neighbor interface name/description. |
| `neighbor.ext_network_device`, `neighbor.ext_network_interface` | Smartscape IDs of the neighbor device/interface (when already known). |
| `neighbor.protocol` | Discovery protocol: `lldp` or `cdp`. |

### 6. Device discovery — current inventory from discovery logs

```dql
fetch logs, from: now()-24h
| filter dt.openpipeline.source == "extension:com.dynatrace.extension.snmp-auto-discovery"
| filter content == "Device discovery"
| fields timestamp, device = `dt.smartscape.ext_network_device`, name, ip,
         monitoring_mode, device_type, description, location
| sort timestamp desc
| limit 20
```

> The same device appears once per poll cycle. To find when a device was first discovered, use the Smartscape node's `lifetime` record — it's more efficient than scanning logs:
>
> ```dql
> smartscapeNodes "EXT_NETWORK_DEVICE" | fields name, firstSeen = lifetime[`start`] | sort firstSeen asc
> ```

### 7. Neighbor topology from discovery logs

Shows interface-level adjacency (LLDP/CDP) as the extension observed it — `smartscapeEdges "calls"` are derived from this raw protocol detail:

```dql
fetch logs, from: now()-24h
| filter dt.openpipeline.source == "extension:com.dynatrace.extension.snmp-auto-discovery"
| filter content == "Neighbor discovery"
| lookup [smartscapeNodes "EXT_NETWORK_DEVICE" | fields id, name],
    sourceField: `dt.smartscape.ext_network_device`, lookupField: id, prefix: "source."
| fields timestamp, device = source.name, `dt.smartscape.ext_network_interface`,
         `neighbor.device.name`, `neighbor.device.ip`,
         `neighbor.interface.name`, `neighbor.protocol`
| sort timestamp desc
| limit 20
```
