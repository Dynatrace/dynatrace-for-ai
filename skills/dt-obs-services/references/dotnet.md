# .NET CLR Performance Metrics

Technology-specific metrics for .NET Common Language Runtime monitoring, including garbage collection, memory consumption, JIT compilation, and thread pool management.

## CLR Memory Consumption by Generation

Monitor memory consumption across GC generations:

```dql
timeseries memory_bytes = avg(dt.runtime.clr.memory.consumption),
          by: {dt.smartscape.process, dt.process_group.id, generation = clr.gc.generation},
          from: now() - 2h
| fieldsAdd
    memory_mb = memory_bytes[] / 1048576
| filter arrayAvg(memory_mb) > 1024

```

**Use Case:** Track memory consumption by generation to identify memory pressure.

## Garbage Collection Count by Generation

Analyze GC invocations across generations:

```dql
timeseries gc_rate = avg(dt.runtime.clr.gc.collection_count, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id, generation = clr.gc.generation},
          from: now() - 1h
| filter arrayAvg(gc_rate) > 0.1
| sort gc_rate desc

```

**Use Case:** Monitor GC frequency per generation to detect excessive collections.

## Thread Pool Monitoring

Monitor CLR thread pool threads and work queue:

```dql
timeseries thread_count = avg(dt.runtime.clr.threadpool.threads),
          queued_items = avg(dt.runtime.clr.threadpool.queued_work_items),
          by: {dt.smartscape.process, dt.process_group.id, thread_type = clr.threadpool.thread_type},
          from: now() - 30m
| fieldsAdd
    threads = thread_count,
    queue_depth = queued_items
| filter arrayAvg(queue_depth) > 50 or arrayAvg(thread_count) > 100

```

**Use Case:** Identify thread pool saturation and work item queuing.

## GC Suspension Time Analysis

Monitor the percentage of time the runtime was suspended for GC:

```dql
timeseries gc_suspension = avg(dt.runtime.clr.gc.suspension_time),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    suspension_percent = gc_suspension
| filter arrayAvg(suspension_percent) > 10
| sort suspension_percent desc

```

**Use Case:** Identify excessive GC suspension time impacting application performance.

## JIT Compilation Time Percentage

Monitor JIT compilation overhead:

```dql
timeseries jit_time_percent = avg(dt.runtime.clr.jit.time_percentage),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    jit_overhead = jit_time_percent
| filter arrayAvg(jit_overhead) > 5

```

**Use Case:** Identify JIT compilation overhead during application startup or code generation.

## GC Time Percentage Analysis

Monitor the percentage of time spent in garbage collection:

```dql
timeseries gc_time_percent = avg(dt.runtime.clr.gc.time_percentage),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    gc_overhead = gc_time_percent
| filter arrayAvg(gc_overhead) > 10
| sort gc_overhead desc

```

**Use Case:** Detect excessive time spent in garbage collection.

## Total GC Collection Time

Monitor accumulated garbage collection time:

```dql
timeseries gc_collection_time_us = avg(dt.runtime.clr.gc.collection_time),
          gc_time_per_sec_us = avg(dt.runtime.clr.gc.collection_time, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 2h
| fieldsAdd
    gc_time_ms = gc_collection_time_us[] / 1000,
    gc_time_rate = gc_time_per_sec_us[] / 1000
| filter arrayAvg(gc_time_rate) > 100

```

**Use Case:** Track total GC collection time to identify GC impact on performance.
