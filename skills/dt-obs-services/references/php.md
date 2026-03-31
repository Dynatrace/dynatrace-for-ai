# PHP Runtime Performance Metrics

Technology-specific metrics for PHP runtime monitoring, including OPcache performance, JIT compilation, garbage collection, and interned strings management.

## OPcache Hit Ratio Analysis

Monitor OPcache hit ratio:

```dql
timeseries opcache_hits = avg(dt.runtime.php.opcache.hits),
          opcache_misses = avg(dt.runtime.php.opcache.misses),
          hit_rate = avg(dt.runtime.php.opcache.hits, rate:1s),
          miss_rate = avg(dt.runtime.php.opcache.misses, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    hit_rate_percent = (hit_rate[] / (hit_rate[] + miss_rate[])) * 100
| filter arrayAvg(hit_rate_percent) < 95

```

**Use Case:** Monitor OPcache efficiency and identify cache misses.

## OPcache Memory Usage

Monitor OPcache memory consumption:

```dql
timeseries memory_used = avg(dt.runtime.php.opcache.memory.used),
          memory_free = avg(dt.runtime.php.opcache.memory.free),
          memory_wasted = avg(dt.runtime.php.opcache.memory.wasted),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 30m
| fieldsAdd
    used_mb = memory_used[] / 1048576,
    free_mb = memory_free[] / 1048576,
    wasted_mb = memory_wasted[] / 1048576,
    total_mb = (memory_used[] + memory_free[] + memory_wasted[]) / 1048576,
    usage_percent = (memory_used[] / (memory_used[] + memory_free[] + memory_wasted[])) * 100
| filter arrayAvg(usage_percent) > 90

```

**Use Case:** Monitor OPcache memory utilization and fragmentation.

## OPcache Cached Scripts and Keys

Monitor cached items in OPcache:

```dql
timeseries cached_scripts = avg(dt.runtime.php.opcache.cached_scripts),
          cached_keys = avg(dt.runtime.php.opcache.cached_keys),
          max_keys = avg(dt.runtime.php.opcache.max_cached_keys),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    scripts = cached_scripts,
    keys = cached_keys,
    max_capacity = max_keys,
    key_usage_percent = (cached_keys[] / max_keys[]) * 100
| filter arrayAvg(key_usage_percent) > 85

```

**Use Case:** Monitor OPcache capacity and approaching limits.

## OPcache Restart Monitoring

Track OPcache restarts by type:

```dql
timeseries restarts_manual = avg(dt.runtime.php.opcache.restarts_manual),
          restarts_oom = avg(dt.runtime.php.opcache.restarts_out_of_memory),
          restarts_hash = avg(dt.runtime.php.opcache.restarts_has),
          manual_restart_rate = avg(dt.runtime.php.opcache.restarts_manual, rate:1s),
          oom_restart_rate = avg(dt.runtime.php.opcache.restarts_out_of_memory, rate:1s),
          hash_restart_rate = avg(dt.runtime.php.opcache.restarts_has, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 2h
| fieldsAdd
    total_restart_rate = manual_restart_rate[] + oom_restart_rate[] + hash_restart_rate[]
| filter arrayAvg(total_restart_rate) > 0.001

```

**Use Case:** Identify OPcache restart causes (OOM, hash collision, manual).

## PHP Garbage Collection Metrics

Monitor PHP GC collected objects:

```dql
timeseries collected_rate = avg(dt.runtime.php.gc.collected_count, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 4h
| filter arrayAvg(collected_rate) > 1000

```

**Use Case:** Track garbage collection activity.

## PHP GC Effectiveness

Monitor garbage collection effectiveness:

```dql
timeseries gc_effectiveness = avg(dt.runtime.php.gc.effectiveness),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    effectiveness_percent = gc_effectiveness
| filter arrayAvg(effectiveness_percent) < 50

```

**Use Case:** Identify inefficient garbage collection cycles.

## PHP GC Duration

Monitor garbage collection duration:

```dql
timeseries gc_duration = avg(dt.runtime.php.gc.duration_ms),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 30m
| fieldsAdd
    duration_ms = gc_duration
| filter arrayAvg(duration_ms) > 100

```

**Use Case:** Identify long GC pauses impacting performance.

## OPcache Interned Strings

Monitor interned string buffer usage:

```dql
timeseries strings_count = avg(dt.runtime.php.opcache.number_of_strings),
          strings_memory = avg(dt.runtime.php.opcache.strings_used_memory),
          strings_buffer = avg(dt.runtime.php.opcache.strings_buffer_size),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    string_count = strings_count,
    memory_used_mb = strings_memory[] / 1048576,
    buffer_size_mb = strings_buffer[] / 1048576,
    usage_percent = (strings_memory[] / strings_buffer[]) * 100
| filter arrayAvg(usage_percent) > 85

```

**Use Case:** Monitor interned string buffer utilization.

## OPcache Blocklist Misses

Monitor blocklist miss rate:

```dql
timeseries miss_rate = avg(dt.runtime.php.opcache.blocklist_misses, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 2h
| filter arrayAvg(miss_rate) > 10

```

**Use Case:** Track blocklist efficiency.

## JIT Buffer Usage

Monitor JIT buffer allocation:

```dql
timeseries jit_buffer_size = avg(dt.runtime.php.jit.buffer_size),
          jit_buffer_free = avg(dt.runtime.php.jit.buffer_free),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 30m
| fieldsAdd
    buffer_size_mb = jit_buffer_size[] / 1048576,
    buffer_free_mb = jit_buffer_free[] / 1048576,
    buffer_used_mb = (jit_buffer_size[] - jit_buffer_free[]) / 1048576,
    usage_percent = ((jit_buffer_size[] - jit_buffer_free[]) / jit_buffer_size[]) * 100
| filter arrayAvg(usage_percent) > 85

```

**Use Case:** Monitor JIT buffer capacity and usage.

## OPcache Overall Performance

Combined OPcache metrics view:

```dql
timeseries hits = avg(dt.runtime.php.opcache.hits),
          misses = avg(dt.runtime.php.opcache.misses),
          memory_used = avg(dt.runtime.php.opcache.memory.used),
          cached_scripts = avg(dt.runtime.php.opcache.cached_scripts),
          hit_rate = avg(dt.runtime.php.opcache.hits, rate:1s),
          miss_rate = avg(dt.runtime.php.opcache.misses, rate:1s),
          by: {dt.smartscape.process, dt.process_group.id},
          from: now() - 1h
| fieldsAdd
    hit_ratio = (hit_rate[] / (hit_rate[] + miss_rate[])) * 100,
    memory_mb = memory_used[] / 1048576,
    scripts = cached_scripts

```

**Use Case:** Monitor overall OPcache health and performance.
