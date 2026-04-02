# Host Metrics Reference

Detailed host resource monitoring including CPU, memory, disk, and network metrics with performance analysis and troubleshooting guidance.

---

## CPU Monitoring

### CPU Usage Overview

Track overall CPU utilization across hosts:

```dql
timeseries cpu_usage = avg(dt.host.cpu.usage), by: {dt.smartscape.host}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| filter arrayAvg(cpu_usage) > 70
| sort arrayAvg(cpu_usage) desc
```

**Key Metrics:**
- `dt.host.cpu.usage`: Total CPU utilization (0-100%)
- `dt.host.cpu.user`: CPU time in user mode
- `dt.host.cpu.system`: CPU time in kernel mode
- `dt.host.cpu.idle`: CPU idle time
- `dt.host.cpu.iowait`: CPU waiting for I/O (Linux only)

### CPU Component Breakdown

Analyze CPU time distribution:

```dql
timeseries {
  user = avg(dt.host.cpu.user),
  system = avg(dt.host.cpu.system),
  iowait = avg(dt.host.cpu.iowait),
  idle = avg(dt.host.cpu.idle)
}, by: {dt.smartscape.host}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| filter arrayAvg(user) + arrayAvg(system) > 70
```

**Interpretation:**
- High `user`: Application processing load
- High `system`: Kernel operations (context switching, syscalls)
- High `iowait`: Disk bottleneck causing CPU idle time

### CPU Steal Time Detection

Monitor CPU steal time in virtualized environments:

```dql
timeseries {
  cpu_steal = avg(dt.host.cpu.steal),
  cpu_usage = avg(dt.host.cpu.usage)
}, by: {dt.smartscape.host}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| filter arrayAvg(cpu_steal) > 5
| sort arrayAvg(cpu_steal) desc
```

**Thresholds:**
- **< 5%**: Normal virtualization overhead
- **5-10%**: Monitor for contention
- **> 10%**: Hypervisor overload - migrate or scale

### System Load Analysis

Compare system load to CPU core count:

```dql
timeseries {
  load_1m = avg(dt.host.cpu.load),
  load_5m = avg(dt.host.cpu.load5m),
  load_15m = avg(dt.host.cpu.load15m)
}, by: {dt.smartscape.host}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| lookup [
    smartscapeNodes HOST
    | fieldsAdd cpuCores
  ], sourceField:dt.smartscape.host, lookupField:id, fields:{cpuCores}
| fieldsAdd
    load_per_core_1m = arrayAvg(load_1m) / toLong(cpuCores),
    load_per_core_5m = arrayAvg(load_5m) / toLong(cpuCores)
| filter load_per_core_1m > 1.0
```

**Best Practice:** Load per core > 1.0 indicates CPU saturation.

### CPU Spike Detection

Detect sudden CPU spikes:

```dql
timeseries cpu_usage = avg(dt.host.cpu.usage), by: {dt.smartscape.host}, interval: 1m
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| summarize
    min_cpu = min(cpu_usage),
    max_cpu = max(cpu_usage),
    avg_cpu = avg(cpu_usage),
    by: {dt.smartscape.host, host_name}
| fieldsAdd spike_magnitude = max_cpu - min_cpu
| filter spike_magnitude > 50  // 50% CPU spike
| sort spike_magnitude desc
```

### AIX-Specific Metrics

Monitor AIX entitlement and physical CPU consumption:

```dql
timeseries {
  entitlement_used_pct = avg(dt.host.cpu.entc),
  physical_consumed = avg(dt.host.cpu.physc),
  entitlement_config = avg(dt.host.cpu.ent_config)
}, by: {dt.smartscape.host}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| filter arrayAvg(entitlement_used_pct) > 80
```

---

## Memory Monitoring

### Memory Usage Overview

Track memory utilization across hosts:

```dql
timeseries {
  memory_used_pct = avg(dt.host.memory.usage),
  memory_avail_pct = avg(dt.host.memory.avail.percent),
  memory_used_bytes = avg(dt.host.memory.used),
  memory_avail_bytes = avg(dt.host.memory.avail.bytes)
}, by: {dt.smartscape.host}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| filter arrayAvg(memory_used_pct) > 80
| sort arrayAvg(memory_used_pct) desc
```

**Memory Metrics:**
- `dt.host.memory.usage`: Percentage of memory used
- `dt.host.memory.used`: Total memory used (bytes)
- `dt.host.memory.avail.bytes`: Memory available without swapping
- `dt.host.memory.avail.percent`: Percentage of available memory

### Memory Breakdown Analysis

Analyze memory components:

```dql
timeseries {
  memory_used = avg(dt.host.memory.used),
  memory_avail = avg(dt.host.memory.avail.bytes),
  memory_recl = avg(dt.host.memory.recl),
  kernel_memory = avg(dt.host.memory.kernel)
}, by: {dt.smartscape.host}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| lookup [
    smartscapeNodes HOST
    | fields id, memoryTotal
  ], sourceField:dt.smartscape.host, lookupField:id
```

**Component Explanation:**
- `memory_used`: Active application memory
- `memory_recl`: Reclaimable memory (caches, buffers)
- `kernel_memory`: Memory used by kernel

### Swap Usage Monitoring

Monitor swap usage and memory pressure:

```dql
timeseries {
  swap_used = avg(dt.host.memory.swap.used),
  swap_total = avg(dt.host.memory.swap.total),
  swap_avail = avg(dt.host.memory.swap.avail)
}, by: {dt.smartscape.host}
| fieldsAdd
    host_name = getNodeName(dt.smartscape.host),
    swap_used_pct = (arrayAvg(swap_used) / arrayAvg(swap_total)) * 100
| filter swap_used_pct > 30
| sort swap_used_pct desc
```

**Alert Thresholds:**
- **< 30%**: Normal swap usage
- **30-50%**: Monitor for memory pressure
- **> 50%**: Critical - insufficient RAM

### Page Fault Analysis

Monitor page fault rates:

```dql
timeseries page_faults = avg(dt.host.memory.avail.pfps), by: {dt.smartscape.host}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| filter arrayAvg(page_faults) > 1000
| sort arrayAvg(page_faults) desc
```

High page faults indicate memory paging activity affecting performance.

### Memory Pressure Identification

Identify hosts under memory pressure:

```dql
timeseries {
  memory_usage = avg(dt.host.memory.usage),
  swap_used = avg(dt.host.memory.swap.used),
  swap_total = avg(dt.host.memory.swap.total),
  page_faults = avg(dt.host.memory.avail.pfps)
}, by: {dt.smartscape.host}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| fieldsAdd memory_usage_avg = arrayAvg(memory_usage)
| fieldsAdd swap_used_pct = (arrayAvg(swap_used) / arrayAvg(swap_total)) * 100
| fieldsAdd memory_pressure_score = if(memory_usage_avg > 90, 3,
        else: if(memory_usage_avg > 80, 2, else: 1)) +
        if(swap_used_pct > 50, 3,
        else: if(swap_used_pct > 30, 2, else: 0))
| filter memory_pressure_score >= 3
| sort memory_pressure_score desc
```

### Memory Leak Detection

Detect continuously increasing memory usage:

```dql
timeseries memory_used = avg(dt.host.memory.used), by: {dt.smartscape.host}, interval: 15m
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| summarize
    first_value = takeFirst(memory_used),
    last_value = takeLast(memory_used),
    by: {dt.smartscape.host, host_name}
| fieldsAdd
    memory_increase = last_value - first_value,
    increase_pct = ((last_value - first_value) / first_value) * 100
| filter increase_pct > 20  // 20% increase over time window
| sort increase_pct desc
```

---

## Disk Monitoring

### Disk Space Usage

Track disk space utilization:

```dql
timeseries {
  disk_used_pct = avg(dt.host.disk.used.percent),
  disk_used_bytes = avg(dt.host.disk.used),
  disk_avail_bytes = avg(dt.host.disk.avail)
}, by: {dt.smartscape.host, dt.smartscape.disk}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| filter arrayAvg(disk_used_pct) > 80
| sort arrayAvg(disk_used_pct) desc
```

**Alert Thresholds:**
- **< 80%**: Normal usage
- **80-90%**: Warning - plan cleanup
- **> 90%**: Critical - immediate action required

### Disk I/O Performance

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

### Disk Latency Analysis

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

### Inode Exhaustion Detection

Monitor inode usage (Linux):

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

### Disk Full Prediction

Predict when disks will fill:

```dql
timeseries {
  disk_used = avg(dt.host.disk.used),
  disk_avail = avg(dt.host.disk.avail)
}, by: {dt.smartscape.host, dt.smartscape.disk}, interval: 1h
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| summarize
    current_used = takeLast(disk_used),
    current_avail = takeLast(disk_avail),
    first_used = takeFirst(disk_used),
    by: {dt.smartscape.host, dt.smartscape.disk, host_name}
| fieldsAdd growth_rate_per_hour = (current_used - first_used) / 24  // Assuming 24h window
| fieldsAdd hours_until_full = if(growth_rate_per_hour > 0, current_avail / growth_rate_per_hour, else: -1)
| filter hours_until_full > 0 and hours_until_full < 48
| sort hours_until_full asc
```

---

## Network Monitoring

### Network Interface Utilization

Monitor network interface usage:

```dql
timeseries {
  bytes_received = avg(dt.host.net.nic.bytes_rx),
  bytes_sent = avg(dt.host.net.nic.bytes_tx),
  link_util_rx_pct = avg(dt.host.net.nic.link_util_rx),
  link_util_tx_pct = avg(dt.host.net.nic.link_util_tx)
}, by: {dt.smartscape.host, dt.smartscape.network_interface}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| filter arrayAvg(link_util_rx_pct) > 70 or arrayAvg(link_util_tx_pct) > 70
| sort arrayAvg(link_util_rx_pct) desc
```

**Alert Thresholds:**
- **< 70%**: Normal usage
- **70-85%**: High utilization - monitor
- **> 85%**: Network saturation

### Packet Drop Detection

Identify packet drops:

```dql
timeseries {
  packets_dropped_rx = avg(dt.host.net.nic.packets.dropped_rx),
  packets_dropped_tx = avg(dt.host.net.nic.packets.dropped_tx),
  total_packets_rx = avg(dt.host.net.nic.packets.rx),
  total_packets_tx = avg(dt.host.net.nic.packets.tx)
}, by: {dt.smartscape.host, dt.smartscape.network_interface}
| fieldsAdd
    host_name = getNodeName(dt.smartscape.host),
    drop_rate_rx_pct = (arrayAvg(packets_dropped_rx) / arrayAvg(total_packets_rx)) * 100,
    drop_rate_tx_pct = (arrayAvg(packets_dropped_tx) / arrayAvg(total_packets_tx)) * 100
| filter drop_rate_rx_pct > 1 or drop_rate_tx_pct > 1
| sort drop_rate_rx_pct desc
```

**Warning:** Drop rate > 1% indicates network congestion or buffer overflow.

### Network Error Analysis

Monitor packet errors:

```dql
timeseries {
  packet_errors_rx = avg(dt.host.net.nic.packets.errors_rx),
  packet_errors_tx = avg(dt.host.net.nic.packets.errors_tx),
  total_packets_rx = avg(dt.host.net.nic.packets.rx),
  total_packets_tx = avg(dt.host.net.nic.packets.tx)
}, by: {dt.smartscape.host, dt.smartscape.network_interface}
| fieldsAdd
    host_name = getNodeName(dt.smartscape.host),
    error_rate_rx_pct = (arrayAvg(packet_errors_rx) / arrayAvg(total_packets_rx)) * 100,
    error_rate_tx_pct = (arrayAvg(packet_errors_tx) / arrayAvg(total_packets_tx)) * 100
| filter error_rate_rx_pct > 0.1 or error_rate_tx_pct > 0.1
| sort error_rate_rx_pct desc
```

**Critical:** Error rate > 0.1% suggests physical layer issues (cables, NICs).

### Network Quality Score

Calculate network quality score:

```dql
timeseries {
  packets_rx = avg(dt.host.net.nic.packets.rx),
  packets_tx = avg(dt.host.net.nic.packets.tx),
  dropped_rx = avg(dt.host.net.nic.packets.dropped_rx),
  dropped_tx = avg(dt.host.net.nic.packets.dropped_tx),
  errors_rx = avg(dt.host.net.nic.packets.errors_rx),
  errors_tx = avg(dt.host.net.nic.packets.errors_tx)
}, by: {dt.smartscape.host, dt.smartscape.network_interface}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| fieldsAdd drop_rate = ((arrayAvg(dropped_rx) + arrayAvg(dropped_tx)) / (arrayAvg(packets_rx) + arrayAvg(packets_tx))) * 100
| fieldsAdd error_rate = ((arrayAvg(errors_rx) + arrayAvg(errors_tx)) / (arrayAvg(packets_rx) + arrayAvg(packets_tx))) * 100
| fieldsAdd quality_score = 100 - (drop_rate * 10) - (error_rate * 20)
| filter quality_score < 90
| sort quality_score asc
```

### Network Spike Detection

Detect sudden network traffic spikes:

```dql
timeseries bytes_rx = avg(dt.host.net.nic.bytes_rx),
          bytes_tx = avg(dt.host.net.nic.bytes_tx),
    by: {dt.smartscape.host}, interval: 1m
| fieldsAdd total_throughput = bytes_rx[] + bytes_tx[]
| summarize
    avg_throughput = avg(total_throughput),
    max_throughput = max(total_throughput),
    by: {dt.smartscape.host}
| fieldsAdd
    host_name = getNodeName(dt.smartscape.host)
| fieldsAdd
    spike_ratio = max_throughput / avg_throughput
| filter spike_ratio > 5
| sort spike_ratio desc
```

---

## Resource Saturation

### Multi-Resource Saturation Detection

Detect resource saturation across multiple metrics:

```dql
timeseries {
  cpu = avg(dt.host.cpu.usage),
  memory = avg(dt.host.memory.usage),
  disk_util = avg(dt.host.disk.util_time),
  network_rx = avg(dt.host.net.nic.link_util_rx),
  network_tx = avg(dt.host.net.nic.link_util_tx)
}, by: {dt.smartscape.host}
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| fieldsAdd
    cpu_avg = arrayAvg(cpu),
    memory_avg = arrayAvg(memory),
    disk_util_avg = arrayAvg(disk_util),
    network_util_avg = (arrayAvg(network_rx) + arrayAvg(network_tx)) / 2
| fieldsAdd saturated_resources =
        (if(cpu_avg > 85, 1, else: 0)) +
        (if(memory_avg > 85, 1, else: 0)) +
        (if(disk_util_avg > 85, 1, else: 0)) +
        (if(network_util_avg > 85, 1, else: 0))
| filter saturated_resources >= 2
| sort saturated_resources desc
```

### Infrastructure Capacity Planning

Analyze resource trends for capacity planning:

```dql
timeseries {
  cpu = avg(dt.host.cpu.usage),
  memory = avg(dt.host.memory.usage),
  disk = avg(dt.host.disk.used.percent)
}, by: {dt.smartscape.host}, interval: 1h
| fieldsAdd host_name = getNodeName(dt.smartscape.host)
| summarize
    cpu_avg = avg(cpu),
    cpu_p95 = percentile(cpu, 95),
    memory_avg = avg(memory),
    memory_p95 = percentile(memory, 95),
    disk_avg = avg(disk),
    by: {dt.smartscape.host, host_name}
| fieldsAdd
    cpu_capacity_remaining = 100 - cpu_p95,
    memory_capacity_remaining = 100 - memory_p95
| filter cpu_capacity_remaining < 20 or memory_capacity_remaining < 20
| sort cpu_capacity_remaining asc
```

---

## Related Documentation

For process-level resource monitoring, see [process-monitoring.md](process-monitoring.md).  
For infrastructure discovery and inventory, see [inventory-discovery.md](inventory-discovery.md).  
For container metrics, see [container-monitoring.md](container-monitoring.md).
