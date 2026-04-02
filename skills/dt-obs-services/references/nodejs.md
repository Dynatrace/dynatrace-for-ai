# Node.js Performance Metrics

Technology-specific metrics for Node.js runtime monitoring, including event loop performance, V8 heap memory, garbage collection, and process memory.

## Event Loop Utilization

Monitor event loop utilization percentage:

```dql
timeseries event_loop_util = avg(dt.runtime.nodejs.eventloop.utilization),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    utilization_percent = event_loop_util
| filter arrayAvg(utilization_percent) > 70

```

**Use Case:** Identify event loop saturation causing poor responsiveness.

## V8 Heap Memory Used

Monitor V8 heap memory usage:

```dql
timeseries heap_used = avg(dt.runtime.nodejs.memory.used),
          by: {dt.smartscape.process, dt.process_group.id, heap_space = v8.heap_space.name},
          from: now() - 2h
| fieldsAdd
    heap_used_mb = heap_used[] / 1048576
| filter arrayAvg(heap_used_mb) > 512

```

**Use Case:** Track V8 heap memory usage by heap space.

## V8 Heap Total Memory

Monitor total V8 heap size:

```dql
timeseries heap_total = avg(dt.runtime.nodejs.memory.total),
          by: {dt.smartscape.process, dt.process_group.id, heap_space = v8.heap_space.name},
          from: now() - 30m
| fieldsAdd
    heap_total_mb = heap_total[] / 1048576

```

**Use Case:** Track total allocated heap size by space.

## Event Loop Active Handles

Monitor active event loop handles:

```dql
timeseries active_handles = avg(dt.runtime.nodejs.eventloop.active_handles),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    handle_count = active_handles
| filter arrayAvg(handle_count) > 1000

```

**Use Case:** Detect handle leaks (unclosed connections, timers, file descriptors).

## Process Resident Set Size (RSS)

Monitor process RSS memory:

```dql
timeseries rss_bytes = avg(dt.runtime.nodejs.memory.rss),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 2h
| fieldsAdd
    rss_mb = rss_bytes[] / 1048576
| filter arrayAvg(rss_mb) > 1024

```

**Use Case:** Track total process memory footprint.

## Garbage Collection Time

Monitor GC collection time:

```dql
timeseries gc_time_us = avg(dt.runtime.nodejs.gc.collection_time),
          gc_time_per_sec_us = avg(dt.runtime.nodejs.gc.collection_time, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 30m
| fieldsAdd
    gc_time_ms = gc_time_us[] / 1000,
    gc_time_rate_ms = gc_time_per_sec_us[] / 1000
| filter arrayAvg(gc_time_rate_ms) > 100

```

**Use Case:** Track time spent in garbage collection.

## GC Suspension Time

Monitor GC suspension time percentage:

```dql
timeseries gc_suspension = avg(dt.runtime.nodejs.gc.suspension_time),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 4h
| fieldsAdd
    suspension_percent = gc_suspension
| filter arrayAvg(suspension_percent) > 10

```

**Use Case:** Track the proportion of time spent in GC pauses.

## Memory and Event Loop Overview

Combined Node.js performance view:

```dql
timeseries heap_used = avg(dt.runtime.nodejs.memory.used),
          rss = avg(dt.runtime.nodejs.memory.rss),
          event_loop_util = avg(dt.runtime.nodejs.eventloop.utilization),
          active_handles = avg(dt.runtime.nodejs.eventloop.active_handles),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    heap_mb = heap_used[] / 1048576,
    rss_mb = rss[] / 1048576,
    utilization_percent = event_loop_util,
    handles = active_handles

```

**Use Case:** Monitor overall Node.js health and resource usage.

## Memory Growth Monitoring

Track memory growth over time:

```dql
timeseries rss = avg(dt.runtime.nodejs.memory.rss),
          heap_used = avg(dt.runtime.nodejs.memory.used),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 2h
| fieldsAdd
    rss_mb = rss[] / 1048576,
    heap_mb = heap_used[] / 1048576
| filter arrayAvg(rss_mb) > 100 or arrayAvg(heap_mb) > 50

```

**Use Case:** Monitor high memory usage that may indicate memory leaks.
