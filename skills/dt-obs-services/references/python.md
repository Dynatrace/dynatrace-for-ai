# Python Runtime Performance Metrics

Technology-specific metrics for Python runtime monitoring, including garbage collection by generation, thread count, and memory block allocation.

## Python Thread Count

Monitor active Python threads:

```dql
timeseries thread_count = avg(dt.runtime.python.threads),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    threads = thread_count
| filter arrayAvg(thread_count) > 50

```

**Use Case:** Monitor Python thread count for multi-threaded applications.

## Python Heap Allocated Blocks

Monitor number of allocated memory blocks:

```dql
timeseries allocated_blocks = avg(dt.runtime.python.heap.allocated_blocks),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 2h
| fieldsAdd
    blocks = allocated_blocks,
    block_growth = arrayDelta(allocated_blocks)
| filter arrayAvg(allocated_blocks) > 1000000 or arrayAvg(block_growth) > 100000

```

**Use Case:** Track memory block allocation for memory leak detection.

## Python GC Collection Count by Generation

Analyze GC collections by generation:

```dql
timeseries gc_count = avg(dt.runtime.python.gc.collection_count),
          collection_rate = avg(dt.runtime.python.gc.collection_count, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id, generation = python.gc.generation},
          from: now() - 30m
| fieldsAdd
    collections = gc_count
| filter arrayAvg(collection_rate) > 1

```

**Use Case:** Monitor GC frequency per generation.

## Python GC Collected Objects

Track objects collected by GC:

```dql
timeseries collected_objects = avg(dt.runtime.python.gc.collected_objects),
          collection_rate = avg(dt.runtime.python.gc.collected_objects, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id, generation = python.gc.generation},
          from: now() - 1h
| fieldsAdd
    objects_collected = collected_objects
| filter arrayAvg(collection_rate) > 1000

```

**Use Case:** Monitor objects collected during garbage collection.

## Python GC Uncollectable Objects

Monitor uncollectable objects:

```dql
timeseries uncollectable = avg(dt.runtime.python.gc.uncollectable_objects),
          by: {dt.smartscape.process, dt.process_group.id, generation = python.gc.generation},
          from: now() - 30m
| fieldsAdd
    uncollectable_count = uncollectable
| filter arrayAvg(uncollectable_count) > 100

```

**Use Case:** Identify objects that cannot be collected due to circular references.

## Python GC Collection Time

Monitor time spent in garbage collection:

```dql
timeseries gc_time_us = avg(dt.runtime.python.gc.collection_time),
          gc_time_per_sec_us = avg(dt.runtime.python.gc.collection_time, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id, generation = python.gc.generation},
          from: now() - 1h
| fieldsAdd
    gc_time_ms = gc_time_us[] / 1000,
    gc_time_rate = gc_time_per_sec_us[] / 1000
| filter arrayAvg(gc_time_rate) > 100

```

**Use Case:** Track GC pause times by generation.

## Python GC Overview

Combined GC metrics view:

```dql
timeseries gc_count = avg(dt.runtime.python.gc.collection_count),
          gc_collected = avg(dt.runtime.python.gc.collected_objects),
          gc_time = avg(dt.runtime.python.gc.collection_time),
          collection_rate = avg(dt.runtime.python.gc.collection_count, rate:1s),
          object_rate = avg(dt.runtime.python.gc.collected_objects, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id, generation = python.gc.generation},
          from: now() - 2h
| fieldsAdd
    collections = gc_count,
    objects_collected = gc_collected,
    time_us = gc_time

```

**Use Case:** Monitor overall Python garbage collection health.
