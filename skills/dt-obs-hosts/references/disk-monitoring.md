# Disk Monitoring Reference

Disk space, I/O, latency, inode, and fill-prediction queries, plus the corrections that apply when one physical disk is mounted at several points.

- [Disk Space Usage](#disk-space-usage)
- [Disk I/O Performance](#disk-io-performance)
- [Disk Latency Analysis](#disk-latency-analysis)
- [Inode Exhaustion Detection](#inode-exhaustion-detection)
- [Disk Full Prediction](#disk-full-prediction)
- [Shared Disks](#shared-disks)

---

## Disk Space Usage

Track disk space utilization:

```dql
timeseries {
  disk_free_pct = avg(dt.host.disk.free),
  disk_used_bytes = avg(dt.host.disk.used),
  disk_avail_bytes = avg(dt.host.disk.avail)
}, by: {dt.smartscape.host, dt.smartscape.disk}
| fieldsAdd host_name = getNodeName(dt.smartscape.host),
    disk_used_pct = 100 - disk_free_pct[]
| filter arrayAvg(disk_used_pct) > 80
| sort arrayAvg(disk_used_pct) desc
```

Used percent is derived from `dt.host.disk.free`, which is a free-space **percentage** (so
`100 - free = used %`). Prefer `dt.host.disk.free`: it is what the built-in low-space detector
evaluates and is populated wherever disk space is monitored, whereas `dt.host.disk.used.percent`
also exists but is absent in Discovery Mode. Warning/critical thresholds are
80% / 90% (see the Alert Thresholds in the main skill). Very large or auto-scaling cloud disks can
keep percentages low despite high absolute usage; pair this with `disk_avail_bytes` for capacity
decisions.

## Disk I/O Performance

Monitor disk read/write performance:

```dql
timeseries {
  read_bytes_per_sec = avg(dt.host.disk.bytes_read),
  write_bytes_per_sec = avg(dt.host.disk.bytes_written),
  read_ops_per_sec = avg(dt.host.disk.read_ops),
  write_ops_per_sec = avg(dt.host.disk.write_ops)
}, by: {dt.smartscape.host, dt.smartscape.disk}
| fieldsAdd
    host_name = getNodeName(dt.smartscape.host),
    total_throughput = arrayAvg(read_bytes_per_sec) + arrayAvg(write_bytes_per_sec)
| filter total_throughput > 50000000  // > 50 MB/s
| sort total_throughput desc
```

## Disk Latency Analysis

Identify disk latency issues:

```dql
timeseries {
  read_latency = avg(dt.host.disk.read_time),
  write_latency = avg(dt.host.disk.write_time),
  util_pct = avg(dt.host.disk.util_time),
  queue_length = avg(dt.host.disk.queue_length)
}, by: {dt.smartscape.host, dt.smartscape.disk}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| filter arrayAvg(read_latency) > 20 or arrayAvg(write_latency) > 20
| sort arrayAvg(read_latency) desc
```

**Performance Indicators:**
- **< 10ms**: Good (SSD/NVMe)
- **10-20ms**: Acceptable (SSD under load)
- **> 20ms**: Bottleneck - investigate
- **Queue length > 2**: I/O saturation

Network and clustered filesystems commonly report space metrics while returning null for `read_time`, `write_time`, `queue_length`, and `util_time`. Zero rows means not collected, not uncontended — fall back to `dt.host.cpu.iowait` and per-host throughput.

## Inode Exhaustion Detection

Monitor inode usage (Linux and AIX local discs; availability on other platforms may vary):

```dql
timeseries {
  inodes_avail_pct = avg(dt.host.disk.inodes_avail),
  inodes_total = avg(dt.host.disk.inodes_total)
}, by: {dt.smartscape.host, dt.smartscape.disk}
| fieldsAdd
    host_name = getNodeName(dt.smartscape.host),
    inodes_used_pct = 100 - arrayAvg(inodes_avail_pct)
| filter inodes_used_pct > 80
| sort inodes_used_pct desc
```

Inode exhaustion can prevent file creation even with available space.

## Disk Full Prediction

Predict when disks will fill:

```dql
timeseries {
  disk_used = avg(dt.host.disk.used),
  disk_avail = avg(dt.host.disk.avail)
}, by: {dt.smartscape.host, dt.smartscape.disk}, from: -24h, interval: 1h
| fieldsAdd
    host_name = getNodeName(dt.smartscape.host),
    current_used = arrayLast(disk_used),
    current_avail = arrayLast(disk_avail),
    first_used = arrayFirst(disk_used)
| fieldsAdd growth_rate_per_hour = (current_used - first_used) / 24  // 24 = hours in the pinned from:-24h window
// Negative growth indicates cleanup or transient data effects and is excluded from "time to full" prediction.
| fieldsAdd hours_until_full = if(growth_rate_per_hour > 0, current_avail / growth_rate_per_hour, else: -1)
| filter hours_until_full > 0 and hours_until_full < 48
| sort hours_until_full asc
```

Linear prediction assumes steady growth over the sampled window; it is reliable only for disks with consistent write rates (e.g. database volumes, sequential log writers). Cyclical patterns — log rotation, batch jobs, periodic cleanup — can produce misleading or negative growth rates.

---

## Shared Disks

A `dt.smartscape.disk` entity represents a logical storage device. On Unix-like systems one entity maps to one local device (regardless of mount paths); on Windows, one per fixed volume; for remote shares, one per mounted share per host. One physical device can back multiple entities (partitions, LVM) and vice versa (RAID). Confirming that several entities share one device is covered in [../SKILL.md](../SKILL.md); the corrections below apply once they are.

### The Fields

- **`disk.remote_disk_id`** is a signed `long` — compare it unquoted; values are frequently negative. Local disks report `0`; `null` indicates the property has not been populated.
- **Mount path field differs by source** — `name` on `smartscapeNodes "DISK"` (the primary mount path); `disk.name` on `dt.davis.events`. On Unix-like systems the entity may have additional mount paths — use `disk.all_mountpoints` to see all of them.
- **`dt.query`** on the event holds the detector's query (e.g. `min(dt.host.disk.free)`) — read the metric that fired from there, not from the problem title.

### Fan-Out Set

Resolve before anything else — the alerting hosts are a subset of the mounting hosts.

```dql-template
smartscapeNodes "DISK"
| filter `disk.remote_disk_id` == <REMOTE_DISK_ID>
| fields disk_entity = id, mount_name = name, host_name = host.name, host_id = references[belongs_to.host][0]
| sort host_name
```

### Attribution

`dt.host.disk.*` is scoped to a specific disk. `dt.process.io.*` carries **no disk dimension** — a top-ranked writer from [process-monitoring.md](process-monitoring.md#process-io) may be writing entirely to local disk. On a shared disk the actual writer may also run on a host that is not monitored so it never appears in the fan-out set. Process-level results are ranked candidates, never attribution.

Space and inode metrics are identical across mounts, so they cannot identify a responsible host. `dt.host.disk.bytes_written` finds the host writing *now* — useful for an active fill, but a volume that filled earlier and went quiet shows zero on every host. In that case it is a filesystem question answered on-host.

Throughput problems attribute with the triggering metric itself. Latency problems do not attribute — correlate per-host throughput instead.

```dql-template
timeseries contribution = avg(<ATTRIBUTION_METRIC>),
  by: {dt.smartscape.host, dt.smartscape.disk}, interval: 5m, from: -24h
| filter iAny(dt.smartscape.disk == toSmartscapeId(array("<DISK-1>", "<DISK-2>")[]))
| fieldsAdd
    host_name = getNodeName(dt.smartscape.host),
    avg_contribution  = arrayAvg(contribution),
    peak_contribution = arrayMax(contribution)
| sort avg_contribution desc
```

### Blast Radius

Mount points present in the fan-out set but absent from the problem's affected entities are exposed without having alerted.

```dql-template
timeseries val = avg(<TRIGGERING_METRIC>),
  by: {dt.smartscape.host, dt.smartscape.disk}, from: -24h
| filter iAny(dt.smartscape.disk == toSmartscapeId(array("<DISK-1>", "<DISK-2>")[]))
| fieldsAdd
    host_name = getNodeName(dt.smartscape.host),
    current   = arrayAvg(val)
| sort current desc
```

Report the `remote_disk_id`, the full mount and host list, and host names alongside entity IDs, per [../SKILL.md](../SKILL.md#response-construction).

### Environment-Wide Shared Disk Discovery

Inventory which disks are mounted on more than one host, before any problem fires.

```dql
smartscapeNodes "DISK"
| fieldsAdd remote_disk_id = `disk.remote_disk_id`
| filter isNotNull(remote_disk_id) and remote_disk_id != 0
| summarize
    smartscape_disk_ids = collectArray(id),
    mount_hosts         = collectArray(host.name),
    mount_count         = count(),
    by: {remote_disk_id}
| filter mount_count > 1
| sort mount_count desc
```

Each row is one physical disk. A host pair recurring across rows shares several volumes and will tend to produce correlated disk problems.

---

## Related Documentation

- [host-metrics.md](host-metrics.md) — CPU, memory, network, and resource saturation
- [process-monitoring.md](process-monitoring.md#process-io) — process-level I/O detail
- [../SKILL.md](../SKILL.md) — shared disk identification via `disk.remote_disk_id`
