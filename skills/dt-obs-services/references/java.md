# Java JVM Performance Metrics

Technology-specific metrics for Java Virtual Machine monitoring, including heap memory, garbage collection, threads, and JVM health analysis.

## JVM Memory Analysis

Monitor JVM memory usage patterns:

```dql
timeseries memory_max = avg(dt.runtime.jvm.memory.max),
          memory_total = avg(dt.runtime.jvm.memory.total),
          memory_free = avg(dt.runtime.jvm.memory.free),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 2h
| fieldsAdd
    memory_used = memory_total[] - memory_free[],
    memory_usage_percent = ((memory_total[] - memory_free[]) / memory_max[]) * 100,
    memory_available_mb = memory_free[] / 1048576
| filter arrayAvg(memory_usage_percent) > 80

```

**Use Case:** Identify processes approaching memory limits for capacity planning.

## Garbage Collection Impact Analysis

Analyze GC frequency and duration impact:

```dql
timeseries gc_count = avg(dt.runtime.jvm.gc.collection_count),
          gc_time_ms = avg(dt.runtime.jvm.gc.collection_time),
          gc_count_rate = avg(dt.runtime.jvm.gc.collection_count, rate:1s),
          gc_time_rate = avg(dt.runtime.jvm.gc.collection_time, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id, gc_type = jvm.gc.name},
          from: now() - 1h
| fieldsAdd
    avg_gc_duration_ms = if(gc_count_rate[] > 0, gc_time_rate[] / gc_count_rate[], else: 0)
| filter arrayAvg(gc_count_rate) > 0.17 or arrayAvg(avg_gc_duration_ms) > 100
| sort avg_gc_duration_ms desc

```

**Use Case:** Detect excessive GC activity causing application pauses.

## GC Suspension Time Analysis

Monitor GC pause impact on application responsiveness:

```dql
timeseries gc_suspension_time = avg(dt.runtime.jvm.gc.suspension_time),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    suspension_percent = gc_suspension_time
| filter arrayAvg(suspension_percent) > 5
| sort suspension_percent desc

```

**Use Case:** Track the proportion of time spent in GC pauses relative to elapsed time.

## Total GC Activity Monitoring

Monitor aggregate GC metrics across all pools:

```dql
timeseries total_gc_time = avg(dt.runtime.jvm.gc.total_collection_time),
          total_gc_count = avg(dt.runtime.jvm.gc.total_activation_count),
          gc_time_rate_ms = avg(dt.runtime.jvm.gc.total_collection_time, rate:1s),
          gc_count_rate = avg(dt.runtime.jvm.gc.total_activation_count, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 2h
| fieldsAdd
    avg_gc_duration = if(gc_count_rate[] > 0, gc_time_rate_ms[] / gc_count_rate[], else: 0)
| filter arrayAvg(gc_count_rate) > 0.1 or arrayAvg(avg_gc_duration) > 100

```

**Use Case:** Monitor overall GC behavior across all garbage collection pools.

## Process Group CPU Time During GC Suspensions

Monitor CPU usage during GC suspensions at the process group level:

```dql
timeseries cpu_suspension_rate_us = avg(dt.runtime.jvm.pgi.cpu_time_suspension, rate:1s),
          by: {dt.smartscape.process},
          from: now() - 1h
| fieldsAdd
    cpu_suspension_rate_ms = cpu_suspension_rate_us[] / 1000
| filter arrayAvg(cpu_suspension_rate_ms) > 100
| sort cpu_suspension_rate_ms desc

```

**Use Case:** Track CPU time consumed during garbage collector suspensions for process groups.

## JVM Thread Monitoring

Monitor thread count and identify thread growth:

```dql
timeseries thread_count = avg(dt.runtime.jvm.threads.count),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 4h
| fieldsAdd
    avg_thread_count = arrayAvg(thread_count),
    max_thread_count = arrayMax(thread_count)
| filter avg_thread_count > 500 or max_thread_count > 1000

```

**Use Case:** Identify thread leaks or approaching thread pool limits.

## JVM Memory Pool Analysis

Analyze specific memory pool usage (Old Gen, Young Gen, Metaspace):

```dql
timeseries {
    pool_used = avg(dt.runtime.jvm.memory_pool.used),
    pool_committed = avg(dt.runtime.jvm.memory_pool.committed),
    pool_max = avg(dt.runtime.jvm.memory_pool.max)
},
  by: {dt.smartscape.process, pool_name = jvm.memory.pool.name},
  from: now() - 1h
| fieldsAdd
    pool_usage_percent = (pool_used[] / pool_max[]) * 100,
    pool_used_mb = pool_used[] / 1048576
| filter in(pool_name, "Tenured Gen", "Old Gen", "Metaspace", "PS Old Gen")
| filter arrayAvg(pool_usage_percent) > 85

```

**Use Case:** Monitor critical memory pools like Old Gen and Metaspace for capacity issues.

## JVM Class Loading Anomalies

Detect class loading issues and memory leaks:

```dql
timeseries classes_loaded = avg(dt.runtime.jvm.classes.loaded),
          classes_total = avg(dt.runtime.jvm.classes.total),
          classes_unloaded = avg(dt.runtime.jvm.classes.unloaded),
          class_growth_rate = avg(dt.runtime.jvm.classes.loaded, rate:1s),
          unload_rate = avg(dt.runtime.jvm.classes.unloaded, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 2h
| filter arrayAvg(classes_loaded) > 20000 or arrayAvg(class_growth_rate) > 10

```

**Use Case:** Identify classloader leaks or excessive dynamic class generation.

## Young Generation GC Pressure

Focus on Young Gen GC metrics for throughput issues:

```dql
timeseries {
    young_gc_count = avg(dt.runtime.jvm.gc.collection_count),
    young_gc_time_ms = avg(dt.runtime.jvm.gc.collection_time),
    young_gen_used = avg(dt.runtime.jvm.memory_pool.used)
},
  by: {dt.smartscape.process, gc_type = jvm.gc.name},
  from: now() - 30m
| filter in(gc_type, "PS Scavenge", "ParNew", "G1 Young Generation", "Copy")
| fieldsAdd
    gc_overhead_percent = (arrayAvg(young_gc_time_ms) / (30 * 60 * 1000)) * 100,
    young_gen_used_mb = young_gen_used[] / 1048576
| filter gc_overhead_percent > 10

```

**Use Case:** Monitor minor GC overhead affecting application throughput.

## JVM Full GC Event Tracking

Track major GC events that cause significant pauses:

```dql
timeseries full_gc_count = avg(dt.runtime.jvm.gc.collection_count),
          full_gc_time_ms = avg(dt.runtime.jvm.gc.collection_time),
          memory_total = avg(dt.runtime.jvm.memory.total),
          memory_free = avg(dt.runtime.jvm.memory.free),
          gc_count_per_sec = avg(dt.runtime.jvm.gc.collection_count, rate:1s),
          gc_time_per_sec = avg(dt.runtime.jvm.gc.collection_time, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id, gc_type = jvm.gc.name},
          from: now() - 6h
| filter in(gc_type, "PS MarkSweep", "ConcurrentMarkSweep", "G1 Old Generation", "MarkSweepCompact")
| fieldsAdd
    memory_used = memory_total[] - memory_free[],
    gc_count_rate = gc_count_per_sec[] * 3600,
    gc_time_rate = gc_time_per_sec
| fieldsAdd
    avg_pause_duration_ms = if(gc_count_rate[] > 0, gc_time_rate[] / gc_count_rate[] * 3600, else: 0),
    memory_used_gb = memory_used[] / 1073741824
| filter arrayAvg(gc_count_rate) > 5 or arrayAvg(avg_pause_duration_ms) > 1000
```

**Use Case:** Alert on excessive Full GC activity indicating heap sizing issues.

## JVM CPU vs GC Time Correlation

Correlate CPU usage with GC overhead:

```dql
timeseries {
    cpu_usage = avg(dt.process.cpu.usage),
    gc_time_ms = avg(dt.runtime.jvm.gc.collection_time),
    gc_count = avg(dt.runtime.jvm.gc.collection_count),
    memory_total = avg(dt.runtime.jvm.memory.total),
    memory_free = avg(dt.runtime.jvm.memory.free)
},
  by: {dt.smartscape.process, dt.process_group.id},
  from: now() - 1h
| fieldsAdd
    memory_usage = ((memory_total[] - memory_free[]) / memory_total[]) * 100,
    avg_gc_count = arrayAvg(gc_count)
| filter arrayAvg(cpu_usage) > 50 and avg_gc_count > 0.1

```

**Use Case:** Identify when high CPU usage is caused by garbage collection.

## JVM Memory After GC Trend

Monitor memory usage after GC to detect memory leaks:

```dql
timeseries {
    memory_total = avg(dt.runtime.jvm.memory.total),
    memory_free = avg(dt.runtime.jvm.memory.free),
    memory_max = avg(dt.runtime.jvm.memory.max),
    gc_count = avg(dt.runtime.jvm.gc.collection_count)
},
  by: {dt.smartscape.process},
  from: now() - 24h
| fieldsAdd
    memory_used = memory_total[] - memory_free[],
    memory_usage_percent = ((memory_total[] - memory_free[]) / memory_max[]) * 100,
    memory_used_gb = (memory_total[] - memory_free[]) / 1073741824,
    avg_gc_count = arrayAvg(gc_count)
| filter avg_gc_count > 0.01

```

**Use Case:** Track post-GC memory trends to identify memory leaks over time.

## JVM Metaspace Growth Monitoring

Detect Metaspace exhaustion (Java 8+):

```dql
timeseries metaspace_used = avg(dt.runtime.jvm.memory_pool.used),
          metaspace_committed = avg(dt.runtime.jvm.memory_pool.committed),
          metaspace_max = avg(dt.runtime.jvm.memory_pool.max),
          by: {dt.smartscape.process, pool_name = jvm.memory.pool.name},
          from: now() - 12h
| filter pool_name == "Metaspace"
| fieldsAdd
    metaspace_usage_percent = (metaspace_used[] / metaspace_max[]) * 100,
    metaspace_used_mb = metaspace_used[] / 1048576
| filter arrayAvg(metaspace_usage_percent) > 80 or arrayMax(metaspace_used_mb) > 512

```

**Use Case:** Prevent OutOfMemoryError for Metaspace with early detection.
