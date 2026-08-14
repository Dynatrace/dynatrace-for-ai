# Network Device Metrics

The `com.dynatrace.extension.network_device.*` metric catalog and the DQL for device and interface health. Use this file for CPU, memory, uptime, interface status over time, throughput, saturation, and errors. For inventory, attributes, and topology, see [topology-model.md](topology-model.md).

> All DQL in this file was validated against a live tenant with `dtctl query`.
>
> **Only `Extension`-mode devices produce these metrics** (see [topology-model.md → monitoring mode](topology-model.md#monitoring-mode--check-this-first)). `Discovery`- and `Neighbor`-mode devices are topology-only.

## The join to topology

Every metric carries a `dt.smartscape.ext_network_device` dimension; every **interface** metric also carries `dt.smartscape.ext_network_interface`. Group by these to get one series per device/interface, then attach names from the node:

- `getNodeName(dt.smartscape.ext_network_device)` — just need the name
- `getNodeField(dt.smartscape.ext_network_device, "field")` — need one specific field
- `lookup [smartscapeNodes "EXT_NETWORK_DEVICE" | fields id, …]` — need more than one field from the node

This is the bridge between this file and [topology-model.md](topology-model.md).

> **Metric dimensions use dotted names** (`oper.status`, `admin.status`, `device.type`, `if.name`) that mirror the underscore-style Smartscape node fields (`operational_status`, `admin_status`, `device_type`, `name`). Attribute *filtering and inventory* belong on the nodes ([topology-model.md](topology-model.md)); the metric dimensions here are for grouping time series.

## Critical field-typing rules

1. **`timeseries` returns arrays.** Each metric value is an array of per-bucket points. Reduce with `arrayAvg()`, `arraySum()`, `arrayLast()`, `arrayFirst()` before sorting or comparing.
2. **The `.count` metrics are per-interval deltas, not monotonic counters.** The value in a bucket is the amount during that bucket, so do **not** subtract successive samples. For a **rate**, take the per-bucket average with `arrayAvg()` and divide by the *bucket* interval in seconds — e.g. bits/sec = `arrayAvg(bytes) * 8 / (interval / 1e9)` (`interval` is nanoseconds). For a **window total** use `arraySum()` (this is a count, not a rate — see query 6).
3. **Use `union: true` to keep rows; do not gap-fill rates with `default: 0`.** `union: true` stops a `timeseries` that combines several metrics/series from dropping a row when one of them is missing. Do **not** add `default: 0` to an aggregation you feed into a **rate** (`arrayAvg`): it turns empty buckets into zeros that pull the average down whenever the query `interval` is finer than the device's polling interval (e.g. 1-minute buckets over a device polled every 5 minutes understate throughput ~5×). `arrayAvg` already skips null buckets — i.e. it averages the buckets that actually have data, which is the correct rate — so leave gaps null and wrap only the final scalar in `coalesce(arrayAvg(...), 0)` when you need a guaranteed number. For **totals** (`arraySum`) gap-filling is moot: `arraySum` ignores nulls, so `default: 0` changes nothing.
4. **Numeric dimensions and node fields are strings.** `if.speed` / node `speed`, and metric dimension values, come back as strings → wrap with `toDouble()` for math.
5. **`sysuptime` is in centiseconds** (1/100 s). Seconds = `/100`; days = `/100/86400`.
6. **Status dimensions are `"<name>(<n>)"` strings** (`"up(1)"`, `"down(2)"`). Match with `startsWith(oper.status, "up")`, not `== "up"`.
7. **Smartscape-ID filters need `toSmartscapeId(…)`** (e.g. filtering a metric to one device).

## Metric Catalog

All keys are prefixed `com.dynatrace.extension.network_device.`. Device metrics group by `dt.smartscape.ext_network_device`; interface metrics also by `dt.smartscape.ext_network_interface`.

### Device-level

| Metric | Unit | Notes |
|---|---|---|
| `sysuptime` | centiseconds | Time since last reboot. Extra dims: `sys.name`, `chassis.mac`, `device.address`, `monitoring.mode`, `device.type`, `sys.description`, `lldp.chassis.id`, `cdp.device.id`. |
| `cpu_usage` | percent | System CPU %. (`cpu_ratio`, a 0–1 form, is documented but was not present on the tested tenant — prefer `cpu_usage`.) |
| `memory_used` | kilobyte | Memory used. |
| `memory_free` | kilobyte | Memory free. |
| `memory_total` | kilobyte | Total memory. |
| `memory_usage` | percent | Memory used %. **Sparse** — many devices report `memory_used`/`memory_free` but not this; compute a fallback (see query 2). |

Device metric dims also include `sys.name`, `device.address`, `chassis.mac`.

### Interface-level

| Metric | Unit | Notes |
|---|---|---|
| `if.status` | state | Interface state. Extra dims: `oper.status`, `admin.status`, `if.speed`, `if.name`, `if.descr`, `if.alias`, `mac.address`. |
| `if.bytes_in.count` / `if.bytes_out.count` | byte | Traffic per interval (→ throughput; see query 5). |
| `if.in.errors.count` / `if.out.errors.count` | count | Packet errors per interval. |
| `if.in.discards.count` / `if.out.discards.count` | count | Discarded packets per interval. |
| `if.in.crc_errors.count` | count | Inbound CRC errors. |
| `if.in.broadcast_pkts.count` / `if.out.broadcast_pkts.count` | count | Broadcast packets. |
| `if.in.multicast_pkts.count` / `if.out.multicast_pkts.count` | count | Multicast packets. |
| `if.in.ucast_pkts.count` / `if.out.ucast_pkts.count` | count | Unicast packets. |
| `if.lastchange` | ticks | `sysUpTime` at the interface's last state change (`ifLastChange`). |

Interface metric dims also include `sys.name`, `device.address`, `chassis.mac`, `if.name`.

> **Discover the current metric set on your tenant:** `fetch metric.series | filter startsWith(metric.key, "com.dynatrace.extension.network_device") | dedup metric.key | fields metric.key | sort metric.key asc`

## Device Health Queries

### 1. Top devices by CPU

```dql
timeseries cpu = avg(com.dynatrace.extension.network_device.cpu_usage), by: {dt.smartscape.ext_network_device}
| fieldsAdd cpu_avg = round(arrayAvg(cpu), decimals: 1),
            device = getNodeName(dt.smartscape.ext_network_device)
| fields device, cpu_avg
| sort cpu_avg desc
| limit 20
```

### 2. Device memory usage %, with fallback

`memory_usage` is sparse, so `coalesce` it with a value computed from `memory_used` / `memory_free`:

```dql
timeseries {
    usage = avg(com.dynatrace.extension.network_device.memory_usage),
    used  = avg(com.dynatrace.extension.network_device.memory_used),
    free  = avg(com.dynatrace.extension.network_device.memory_free)
  }, by: {dt.smartscape.ext_network_device}, union: true
| fieldsAdd mem_pct = round(coalesce(arrayAvg(usage), arrayAvg(used) * 100 / (arrayAvg(used) + arrayAvg(free))), decimals: 1),
            device = getNodeName(dt.smartscape.ext_network_device)
| filter isNotNull(mem_pct)
| fields device, mem_pct
| sort mem_pct desc
| limit 20
```

### 3. Uptime and reboot detection

`sysuptime` is centiseconds. A device that rebooted inside the window shows the counter dropping (last < first):

```dql
timeseries uptime = avg(com.dynatrace.extension.network_device.sysuptime), by: {dt.smartscape.ext_network_device}
| fieldsAdd uptime_days = round(arrayLast(uptime) / 100 / 86400, decimals: 1),
            rebooted = arrayLast(uptime) < arrayFirst(uptime),
            device = getNodeName(dt.smartscape.ext_network_device)
| fields device, uptime_days, rebooted
| sort uptime_days asc
| limit 20
```

## Interface Health Queries

### 4. Interfaces that are administratively up but operationally down

The classic "port down" signal — the admin wants it up, but the link is down:

```dql
timeseries status = avg(com.dynatrace.extension.network_device.if.status),
    by: {dt.smartscape.ext_network_interface, dt.smartscape.ext_network_device, oper.status, admin.status}
| filter startsWith(admin.status, "up") and startsWith(oper.status, "down")
| fieldsAdd device = getNodeName(dt.smartscape.ext_network_device),
            interface = getNodeName(dt.smartscape.ext_network_interface)
| fields device, interface, admin.status, oper.status
| sort device asc
```

### 5. Top interfaces by throughput, with saturation vs. link speed

Throughput is the byte counters converted to bits/sec, computed **per direction**. Interface `speed` is a **one-way** capacity (Mbps) and links are full-duplex, so saturation is the *busier* direction against `speed` — summing both directions against a one-way capacity would overstate utilization (a fully-used duplex link would read ~200%). Keep `interval` at least as coarse as the device's polling interval so buckets are not artificially empty (see rule 3), and drop `speed == 0` interfaces (loopbacks, virtual ports) to avoid divide-by-zero:

```dql
timeseries {
    bytes_in  = sum(com.dynatrace.extension.network_device.if.bytes_in.count),
    bytes_out = sum(com.dynatrace.extension.network_device.if.bytes_out.count)
  }, by: {dt.smartscape.ext_network_interface, dt.smartscape.ext_network_device}, union: true, interval: 5m
| fieldsAdd mbps_in  = coalesce(arrayAvg(bytes_in), 0)  * 8 / (toDouble(interval) / 1000000000) / 1000000,
           mbps_out = coalesce(arrayAvg(bytes_out), 0) * 8 / (toDouble(interval) / 1000000000) / 1000000
| lookup [smartscapeNodes "EXT_NETWORK_INTERFACE" | fields id, name, speed], sourceField: dt.smartscape.ext_network_interface, lookupField: id, prefix: "iface."
| fieldsAdd device = getNodeName(dt.smartscape.ext_network_device)
| filter toDouble(iface.speed) > 0
| fieldsAdd saturation_pct = round(if(mbps_in > mbps_out, mbps_in, else: mbps_out) / toDouble(iface.speed) * 100, decimals: 1)
| fields device, interface = iface.name, speed_mbps = iface.speed,
         mbps_in = round(mbps_in, decimals: 1), mbps_out = round(mbps_out, decimals: 1), saturation_pct
| sort saturation_pct desc
| limit 20
```

### 6. Interfaces with the most errors and discards

```dql
timeseries {
    errors   = sum(com.dynatrace.extension.network_device.if.in.errors.count),
    discards = sum(com.dynatrace.extension.network_device.if.in.discards.count)
  }, by: {dt.smartscape.ext_network_interface, dt.smartscape.ext_network_device}, union: true
| fieldsAdd total = arraySum(errors) + arraySum(discards)
| filter total > 0
| fieldsAdd device = getNodeName(dt.smartscape.ext_network_device),
            interface = getNodeName(dt.smartscape.ext_network_interface)
| fields device, interface, errors = arraySum(errors), discards = arraySum(discards), total
| sort total desc
| limit 20
```

Swap `if.in.*` for `if.out.*` for the egress direction, or add `if.in.crc_errors.count` for CRC-specific faults.

### 7. All interfaces on one device (status + throughput)

Scope any interface query to a single device with a `filter:` on `dt.smartscape.ext_network_device` inside `timeseries`. This is the drill-down behind "show me the ports on the core router":

```dql-template
timeseries {
    status    = avg(com.dynatrace.extension.network_device.if.status),
    bytes_in  = sum(com.dynatrace.extension.network_device.if.bytes_in.count),
    bytes_out = sum(com.dynatrace.extension.network_device.if.bytes_out.count)
  }, by: {dt.smartscape.ext_network_interface, oper.status, admin.status},
     filter: {dt.smartscape.ext_network_device == toSmartscapeId("<EXT_NETWORK_DEVICE-ID>")},
     union: true, interval: 5m
| fieldsAdd mbps = round((coalesce(arrayAvg(bytes_in), 0) + coalesce(arrayAvg(bytes_out), 0)) * 8 / (toDouble(interval) / 1000000000) / 1000000, decimals: 1),
            interface = getNodeName(dt.smartscape.ext_network_interface)
| fields interface, oper.status, admin.status, mbps
| sort mbps desc
```

Get the device ID from [topology-model.md](topology-model.md) (e.g. filter `smartscapeNodes "EXT_NETWORK_DEVICE"` by `name`).
