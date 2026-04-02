# Go Runtime Performance Metrics

Technology-specific metrics for Go runtime monitoring, including goroutines, garbage collection, memory management, and scheduler performance.

## Goroutine Count Monitoring

Monitor goroutine count and identify leaks:

```dql
timeseries goroutine_count = avg(dt.runtime.go.scheduler.goroutine_count),
          by: {dt.smartscape.process, dt.process_group.id, goroutine_owner = go.goroutine.owner},
          from: now() - 4h
| fieldsAdd
    avg_goroutines = arrayAvg(goroutine_count),
    max_goroutines = arrayMax(goroutine_count)
| filter avg_goroutines > 10000 or max_goroutines > 15000

```

**Use Case:** Identify goroutine leaks causing resource exhaustion.

## GC Suspension Time Analysis

Monitor garbage collection suspension time:

```dql
timeseries gc_suspension = avg(dt.runtime.go.gc.suspension_time),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    suspension_percent = gc_suspension
| filter arrayAvg(suspension_percent) > 5
| sort suspension_percent desc

```

**Use Case:** Track the proportion of time spent in GC pauses.

## Go Heap Memory Analysis

Analyze Go heap size and state:

```dql
timeseries heap_bytes = avg(dt.runtime.go.memory.heap),
          by: {dt.smartscape.process, dt.process_group.id, heap_state = go.heap.state},
          from: now() - 2h
| fieldsAdd
    heap_mb = heap_bytes[] / 1048576
| filter arrayAvg(heap_mb) > 1024

```

**Use Case:** Track heap memory usage by state (allocated, idle, etc.).

## Go Memory Usage by Type

Monitor Go memory used by type:

```dql
timeseries memory_used = avg(dt.runtime.go.memory.used),
          by: {dt.smartscape.process, dt.process_group.id, memory_type = go.memory_type},
          from: now() - 30m
| fieldsAdd
    memory_used_mb = memory_used[] / 1048576
| filter arrayAvg(memory_used_mb) > 512

```

**Use Case:** Track memory usage across different memory types.

## Go Memory Committed

Monitor committed memory:

```dql
timeseries memory_committed = avg(dt.runtime.go.memory.committed),
          by: {dt.smartscape.process, dt.process_group.id, memory_type = go.memory_type},
          from: now() - 1h
| fieldsAdd
    memory_committed_mb = memory_committed[] / 1048576
| filter arrayAvg(memory_committed_mb) > 2048

```

**Use Case:** Track committed memory to identify memory growth.

## GC Collection Count

Monitor garbage collection frequency:

```dql
timeseries gc_count_per_sec = avg(dt.runtime.go.gc.collection_count, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 30m
| fieldsAdd
    gc_per_minute = gc_count_per_sec[] * 60
| filter arrayAvg(gc_per_minute) > 60

```

**Use Case:** Monitor GC frequency to detect excessive collections.

## GC Collection Time

Monitor total garbage collection time:

```dql
timeseries gc_time_sec = avg(dt.runtime.go.gc.collection_time),
          gc_time_per_sec = avg(dt.runtime.go.gc.collection_time, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    gc_time = gc_time_sec,
    gc_time_rate = gc_time_per_sec
| filter arrayAvg(gc_time_rate) > 0.1

```

**Use Case:** Track time spent in garbage collection.

## CGo Calls Monitoring

Track Go to C (CGo) call frequency:

```dql
timeseries cgo_call_rate = avg(dt.runtime.go.cgo_calls, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| filter arrayAvg(cgo_call_rate) > 100

```

**Use Case:** Monitor CGo overhead for applications with C integration.

## Memory Limit Monitoring

Monitor Go runtime memory limit:

```dql
timeseries memory_limit = avg(dt.runtime.go.memory.limit),
          memory_used = avg(dt.runtime.go.memory.used),
          by: {dt.smartscape.process, memory_type = go.memory_type},
          from: now() - 2h
| fieldsAdd
    limit_mb = memory_limit[] / 1048576,
    used_mb = memory_used[] / 1048576
| filter arrayAvg(memory_limit) > 0

```

**Use Case:** Track memory usage against configured memory limits.

## Heap Object Count

Track allocated Go objects on the heap:

```dql
timeseries object_count = avg(dt.runtime.go.memory.heap.object_count),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 4h
| fieldsAdd
    avg_objects = arrayAvg(object_count),
    max_objects = arrayMax(object_count)
| filter avg_objects > 10000000 or max_objects > 15000000

```

**Use Case:** Monitor live object count for memory leak detection.

## Worker Thread Monitoring

Monitor Go worker thread count:

```dql
timeseries worker_threads = avg(dt.runtime.go.scheduler.worker_thread_count),
          by: {dt.smartscape.process, dt.process_group.id, thread_state = go.thread.state},
          from: now() - 1h
| fieldsAdd
    threads = worker_threads
| filter arrayAvg(threads) > 100

```

**Use Case:** Monitor scheduler worker threads.

## Global Goroutine Queue Size

Monitor the global goroutine run queue:

```dql
timeseries queue_size = avg(dt.runtime.go.scheduler.queue_size),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    global_queue = queue_size
| filter arrayAvg(global_queue) > 100

```

**Use Case:** Identify scheduler contention with large global queue.

## Idle Scheduling Context Count

Monitor idle scheduling contexts:

```dql
timeseries idle_contexts = avg(dt.runtime.go.scheduler.context.idle_count),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    idle_count = idle_contexts

```

**Use Case:** Monitor idle scheduling contexts.

## System Call Count

Monitor Go runtime system calls:

```dql
timeseries syscall_rate = avg(dt.runtime.go.sys_calls, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| filter arrayAvg(syscall_rate) > 1000

```

**Use Case:** Monitor system call frequency.

## GC Goal Percentage

Monitor GC heap size target:

```dql
timeseries gc_goal = avg(dt.runtime.go.gc.goal),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    goal_percent = gc_goal

```

**Use Case:** Track GC heap size target percentage.

## HTTP Requests (Go)

Monitor total HTTP requests:

```dql
timeseries request_rate = avg(dt.runtime.go.http.requests, rate:1s),
          by: {dt.smartscape.process, status_code = http.response.status_code},
          from: now() - 1h

```

**Use Case:** Track HTTP traffic flow.

## HTTP Latency (Go)

Monitor HTTP response latency:

```dql
timeseries latency_sec = avg(dt.runtime.go.http.latency),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    latency_ms = latency_sec[] * 1000
| filter arrayAvg(latency_ms) > 100

```

**Use Case:** Monitor application response time to clients.
