# Process Monitoring Reference

Detailed process-level monitoring including CPU, memory, I/O, and network metrics with troubleshooting guidance.

---

## Process CPU and Memory

### Top CPU-Consuming Processes

Identify resource-intensive processes:

```dql
timeseries cpu_usage = avg(dt.process.cpu.usage),
    by: {dt.smartscape.process, dt.process_group.id}
| fieldsAdd process_name = getNodeName(dt.smartscape.process)
| filter arrayAvg(cpu_usage) > 50
| sort arrayAvg(cpu_usage) desc
| limit 20
```

**Metric:** `dt.process.cpu.usage` - Process CPU percentage (100% = 1 full core).

### Process Memory Usage

Monitor process memory consumption:

```dql
timeseries {
  memory_bytes = avg(dt.process.memory.working_set_size),
  memory_pct = avg(dt.process.memory.usage)
}, by: {dt.smartscape.process, dt.process_group.id}
| fieldsAdd
    process_name = getNodeName(dt.smartscape.process),
    memory_gb = arrayAvg(memory_bytes) / 1024 / 1024 / 1024
| filter arrayAvg(memory_pct) > 20 or memory_gb > 4
| sort arrayAvg(memory_pct) desc
| limit 20
```

### Memory Leak Detection

Detect processes with continuously growing memory:

```dql
timeseries memory_bytes = avg(dt.process.memory.working_set_size),
    by: {dt.smartscape.process}, interval: 15m
| fieldsAdd process_name = getNodeName(dt.smartscape.process)
| summarize
    first_value = takeFirst(memory_bytes),
    last_value = takeLast(memory_bytes),
    by: {dt.smartscape.process, process_name}
| fieldsAdd
    growth_bytes = last_value - first_value,
    growth_pct = ((last_value - first_value) / first_value) * 100
| filter growth_pct > 30
| sort growth_pct desc
```

### Page Fault Analysis

Monitor process page faults:

```dql
timeseries page_faults = avg(dt.process.memory.page_faults),
    by: {dt.smartscape.process, dt.process_group.id}
| fieldsAdd process_name = getNodeName(dt.smartscape.process)
| filter arrayAvg(page_faults) > 1000
| sort arrayAvg(page_faults) desc
```

High page faults indicate insufficient memory or swapping.

### GC Suspension Time

Monitor garbage collection impact (Java, .NET):

```dql
timeseries gc_suspension = avg(dt.process.cpu.group_suspension_time),
    by: {dt.smartscape.process, dt.process_group.id}
| fieldsAdd process_name = getNodeName(dt.smartscape.process)
| filter arrayAvg(gc_suspension) > 100000  // > 100ms
| sort arrayAvg(gc_suspension) desc
```

### Resource Exhaustion Events

Detect memory and thread exhaustion:

```dql
timeseries {
  memory_exhausted = sum(dt.process.mem.exhausted_mem),
  threads_exhausted = sum(dt.process.threads_exhausted)
}, by: {dt.smartscape.process, dt.process_group.id}
| fieldsAdd process_name = getNodeName(dt.smartscape.process)
| filter arraySum(memory_exhausted) > 0 or arraySum(threads_exhausted) > 0
| sort arraySum(memory_exhausted) desc
```

**Critical Alert:** Any exhaustion event indicates serious issues (OOM, thread pool exhaustion).

### File Descriptor Usage

Monitor file descriptor limits (Linux):

```dql
timeseries {
  fd_used = avg(dt.process.handles.file_descriptors_used),
  fd_max = avg(dt.process.handles.file_descriptors_max),
  fd_pct_used = avg(dt.process.handles.file_descriptors_percent_used)
}, by: {dt.smartscape.process}
| fieldsAdd process_name = getNodeName(dt.smartscape.process)
| filter arrayAvg(fd_pct_used) > 80
| sort arrayAvg(fd_pct_used) desc
```

### Process Health Score

Calculate process health based on resource usage:

```dql
timeseries {
  cpu = avg(dt.process.cpu.usage),
  memory = avg(dt.process.memory.usage),
  page_faults = avg(dt.process.memory.page_faults)
}, by: {dt.smartscape.process}
| fieldsAdd process_name = getNodeName(dt.smartscape.process)
| fieldsAdd cpu_avg = arrayAvg(cpu)
| fieldsAdd memory_avg = arrayAvg(memory)
| fieldsAdd page_faults_avg = arrayAvg(page_faults)
| fieldsAdd health_score = 100 -
        if(cpu_avg > 80, 30, else: if(cpu_avg > 60, 15, else: 0)) -
        if(memory_avg > 80, 30, else: if(memory_avg > 60, 15, else: 0)) -
        if(page_faults_avg > 5000, 20, else: if(page_faults_avg > 1000, 10, else: 0))
| filter health_score < 70
| sort health_score asc
```

---

## Process I/O

### Top I/O Consuming Processes

Identify processes with highest I/O:

```dql
timeseries {
  bytes_read = avg(dt.process.io.bytes_read),
  bytes_written = avg(dt.process.io.bytes_written),
  bytes_total = avg(dt.process.io.bytes_total)
}, by: {dt.smartscape.process, dt.process_group.id}
| fieldsAdd
    process_name = getNodeName(dt.smartscape.process),
    io_mb_per_sec = arrayAvg(bytes_total) / 1024 / 1024
| filter io_mb_per_sec > 10
| sort arrayAvg(bytes_total) desc
| limit 20
```

### Read-Heavy Processes

Identify read-intensive processes:

```dql
timeseries {
  bytes_read = avg(dt.process.io.bytes_read),
  bytes_written = avg(dt.process.io.bytes_written)
}, by: {dt.smartscape.process}
| fieldsAdd
    process_name = getNodeName(dt.smartscape.process),
    read_write_ratio = arrayAvg(bytes_read) / arrayAvg(bytes_written)
| filter read_write_ratio > 5 and arrayAvg(bytes_read) > 10000000
| sort arrayAvg(bytes_read) desc
```

### Write-Heavy Processes

Identify write-intensive processes:

```dql
timeseries {
  bytes_read = avg(dt.process.io.bytes_read),
  bytes_written = avg(dt.process.io.bytes_written)
}, by: {dt.smartscape.process}
| fieldsAdd
    process_name = getNodeName(dt.smartscape.process),
    write_read_ratio = arrayAvg(bytes_written) / arrayAvg(bytes_read)
| filter write_read_ratio > 5 and arrayAvg(bytes_written) > 10000000
| sort arrayAvg(bytes_written) desc
```

### Requested vs Actual I/O

Compare requested I/O to actual I/O (Linux/AIX):

```dql
timeseries {
  req_bytes_read = avg(dt.process.io.req_bytes_read),
  req_bytes_write = avg(dt.process.io.req_bytes_write),
  actual_bytes_read = avg(dt.process.io.bytes_read),
  actual_bytes_written = avg(dt.process.io.bytes_written)
}, by: {dt.smartscape.process}
| fieldsAdd
    process_name = getNodeName(dt.smartscape.process),
    read_cache_hit_pct = ((arrayAvg(req_bytes_read) - arrayAvg(actual_bytes_read)) / arrayAvg(req_bytes_read)) * 100,
    write_cache_hit_pct = ((arrayAvg(req_bytes_write) - arrayAvg(actual_bytes_written)) / arrayAvg(req_bytes_write)) * 100
| filter arrayAvg(req_bytes_read) > 0 and arrayAvg(req_bytes_write) > 0
| sort read_cache_hit_pct asc
```

**Metric Explanation:**
- `req_bytes_read/write`: Requested I/O (includes cache)
- `bytes_read/written`: Actual disk I/O (storage layer)
- Low cache hit rate indicates poor caching effectiveness

### I/O Spike Detection

Detect sudden I/O spikes:

```dql
timeseries io_total = avg(dt.process.io.bytes_total),
    by: {dt.smartscape.process}, interval: 1m
| fieldsAdd process_name = getNodeName(dt.smartscape.process)
| summarize
    avg_io = avg(io_total),
    max_io = max(io_total),
    by: {dt.smartscape.process, process_name}
| fieldsAdd spike_ratio = max_io / avg_io
| filter spike_ratio > 10
| sort spike_ratio desc
```

---

## Process Network

### Network Traffic by Process

Identify network-intensive processes:

```dql
timeseries {
  bytes_sent = avg(dt.process.network.bytes_tx),
  bytes_received = avg(dt.process.network.bytes_rx),
  throughput = avg(dt.process.network.throughput)
}, by: {dt.smartscape.process, dt.process_group.id}
| fieldsAdd
    process_name = getNodeName(dt.smartscape.process),
    total_traffic = arrayAvg(bytes_sent) + arrayAvg(bytes_received)
| filter total_traffic > 1000000  // > 1 MB/s
| sort total_traffic desc
| limit 20
```

### Request Rate Analysis

Monitor request rates per process:

```dql
timeseries requests_per_sec = avg(dt.process.network.load),
    by: {dt.smartscape.process, dt.process_group.id}
| fieldsAdd process_name = getNodeName(dt.smartscape.process)
| filter arrayAvg(requests_per_sec) > 100
| sort arrayAvg(requests_per_sec) desc
```

### TCP Connection Quality

Monitor TCP session health:

```dql
timeseries {
  new_sessions = avg(dt.process.network.sessions.new_aggr),
  session_timeouts = avg(dt.process.network.sessions.timeout_aggr),
  session_resets = avg(dt.process.network.sessions.reset_aggr)
}, by: {dt.smartscape.process, dt.process_group.id}
| fieldsAdd
    process_name = getNodeName(dt.smartscape.process),
    timeout_rate_pct = (arrayAvg(session_timeouts) / arrayAvg(new_sessions)) * 100,
    reset_rate_pct = (arrayAvg(session_resets) / arrayAvg(new_sessions)) * 100
| filter timeout_rate_pct > 5 or reset_rate_pct > 5
| sort timeout_rate_pct desc
```

**Alert Thresholds:**
- **Timeout rate > 5%**: Connection establishment issues
- **Reset rate > 5%**: Unexpected connection terminations

### Network Latency Monitoring

Monitor round-trip time and latency:

```dql
timeseries {
  rtt_ms = avg(dt.process.network.round_trip),
  latency_ms = avg(dt.process.network.latency)
}, by: {dt.smartscape.process, dt.process_group.id}
| fieldsAdd process_name = getNodeName(dt.smartscape.process)
| filter arrayAvg(rtt_ms) > 100 or arrayAvg(latency_ms) > 100
| sort arrayAvg(rtt_ms) desc
```

**Metrics:**
- `round_trip`: TCP handshake RTT
- `latency`: Time between data send and ACK

### Packet Retransmission Analysis

Monitor packet retransmissions:

```dql
timeseries {
  retransmit_packets = avg(dt.process.network.packets.re_tx_aggr),
  retransmit_base = avg(dt.process.network.packets.base_re_tx_aggr),
  packets_received = avg(dt.process.network.packets.rx)
}, by: {dt.smartscape.process, dt.process_group.id}
| fieldsAdd
    process_name = getNodeName(dt.smartscape.process),
    retransmit_pct = (arrayAvg(retransmit_packets) / arrayAvg(retransmit_base)) * 100
| filter retransmit_pct > 1
| sort retransmit_pct desc
```

**Warning:** Retransmit rate > 1% indicates network quality degradation.

### Process Network Health Score

Calculate network health score:

```dql
timeseries {
  new_sessions = avg(dt.process.network.sessions.new_aggr),
  timeouts = avg(dt.process.network.sessions.timeout_aggr),
  resets = avg(dt.process.network.sessions.reset_aggr),
  retransmits = avg(dt.process.network.packets.re_tx_aggr),
  base_retransmits = avg(dt.process.network.packets.base_re_tx_aggr)
}, by: {dt.smartscape.process}
| fieldsAdd
    process_name = getNodeName(dt.smartscape.process),
    timeout_rate = (arrayAvg(timeouts) / arrayAvg(new_sessions)) * 100,
    reset_rate = (arrayAvg(resets) / arrayAvg(new_sessions)) * 100,
    retransmit_rate = (arrayAvg(retransmits) / arrayAvg(base_retransmits)) * 100
| fieldsAdd
    health_score = 100 -
        if(timeout_rate > 10, 40, else: if(timeout_rate > 5, 20, else: 0)) -
        if(reset_rate > 10, 40, else: if(reset_rate > 5, 20, else: 0)) -
        if(retransmit_rate > 5, 20, else: if(retransmit_rate > 1, 10, else: 0))
| filter health_score < 80
| sort health_score asc
```

### Bandwidth Consumption Ranking

Rank processes by bandwidth consumption:

```dql
timeseries throughput = avg(dt.process.network.throughput),
    by: {dt.smartscape.process}
| fieldsAdd process_name = getNodeName(dt.smartscape.process)
| summarize
    avg_throughput = avg(throughput),
    max_throughput = max(throughput),
    total_data = sum(throughput),
    by: {dt.smartscape.process, process_name}
| fieldsAdd
    avg_mbps = avg_throughput / 125000,  // Convert to Mbps
    total_gb = total_data / 1024 / 1024 / 1024
| sort total_gb desc
| limit 20
```

---

## Process Inventory and Lifecycle

### All Processes Overview

Fetch all process instances:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd name, dt.process_group.detected_name, process.containerized
| sort name asc
| limit 100
```

### Process Groups Summary

Group processes by process group:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd dt.process_group.id, dt.process_group.detected_name
| summarize instance_count = count(), by: {dt.process_group.id, dt.process_group.detected_name}
| sort instance_count desc
```

**Key Concept:** Process groups aggregate similar processes (e.g., multiple Apache workers).

### Containerized vs Native Processes

Compare containerized and native processes:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd process.containerized, dt.process_group.detected_name
| summarize
    total_processes = count(),
    containerized = countIf(process.containerized == true),
    native = countIf(process.containerized == false or isNull(process.containerized)),
    by: {process.containerized}
```

### Process Technology Detection

Identify processes by detected technology:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd name, dt.process_group.detected_name, process.bitness
| filter contains(dt.process_group.detected_name, "Java")
    or contains(dt.process_group.detected_name, "Node")
    or contains(dt.process_group.detected_name, "Python")
    or contains(dt.process_group.detected_name, "Apache")
    or contains(dt.process_group.detected_name, "nginx")
| sort dt.process_group.detected_name
| limit 50
```

**Common Technologies:** Java, Node.js, Python, Apache, nginx, IIS, MySQL, PostgreSQL, Oracle

### Process Listen Ports

Identify processes by listening ports:

```dql
smartscapeNodes "PROCESS"
| fieldsAdd name, process.listen_ports, dt.process_group.detected_name
| filter isNotNull(process.listen_ports) and arraySize(process.listen_ports) > 0
| expand port = process.listen_ports
| summarize
    process_count = countDistinct(id),
    by: {port, dt.process_group.detected_name}
| sort toLong(port) asc
```

**Use Case:** Discover port conflicts or identify services by standard ports (80, 443, 3306, etc.).

---

## Related Documentation

For host-level resource monitoring, see [host-metrics.md](host-metrics.md).  
For container and Kubernetes monitoring, see [container-monitoring.md](container-monitoring.md).  
For technology inventory and discovery, see [inventory-discovery.md](inventory-discovery.md).
