# Mobile Application Monitoring

Track mobile app performance, startup times, crash analytics, and mobile-specific metrics.

## Mobile App Start Performance

Analyze mobile application startup performance across cold, warm, and hot starts.

**Data Source:** `fetch user.events` with `characteristics.has_app_start`

**Key Fields:**

- `app_start.type` - Start type: `cold`, `warm`, `hot`
- `duration` - Total startup duration (nanoseconds)
- Platform-specific phase timings in `app_start.android.*`, `app_start.ios.*`, `app_start.flutter.*`

**Performance Thresholds:**

- Cold start: Good < 3s | Acceptable < 5s | Poor > 5s
- Warm start: Good < 1.5s | Acceptable < 2s | Poor > 2s
- Hot start: Good < 500ms | Acceptable < 1s | Poor > 1s

### App Start Overview

Query all app starts:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_app_start == true
| summarize
    start_count = count(),
    avg_duration = avg(duration),
    p50_duration = percentile(duration, 50),
    p90_duration = percentile(duration, 90),
    by: {frontend.name, app_start.type}
| sort app_start.type asc

```

**Use Case:** Baseline startup performance by type.

### Cold Start Analysis

Analyze initial app launches:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_app_start == true
| filter app_start.type == "cold"
| summarize
    cold_starts = count(),
    p50_duration = percentile(duration, 50),
    p75_duration = percentile(duration, 75),
    p95_duration = percentile(duration, 95),
    by: {frontend.name}

```

**Use Case:** Optimize initial app launch experience.

### Startup by App Version

Track startup improvements across releases:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_app_start == true
| filter app_start.type == "cold"
| summarize
    start_count = count(),
    p50_duration = percentile(duration, 50),
    by: {frontend.name, app.version}
| filter start_count > 10
| sort app.version desc

```

**Use Case:** Validate startup optimizations in releases.

### Startup by Device

Identify slow devices:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_app_start == true
| filter app_start.type == "cold"
| summarize
    start_count = count(),
    avg_duration = avg(duration),
    p90_duration = percentile(duration, 90),
    by: {device.manufacturer, device.model, os.version}
| filter start_count > 20
| sort p90_duration desc
| limit 20

```

**Use Case:** Target optimization for popular slow devices.

### Android Startup Phases

Analyze Android-specific phases:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_app_start == true
| filter os.name == "Android"
| summarize
    avg_app_oncreate = avg(app_start.android.application.on_create.end_time - app_start.android.application.on_create.start_time),
    avg_activity_oncreate = avg(app_start.android.activity.on_create.end_time - app_start.android.activity.on_create.start_time),
    avg_activity_onstart = avg(app_start.android.activity.on_start.end_time - app_start.android.activity.on_start.start_time),
    by: {frontend.name, app_start.type}

```

**Use Case:** Identify Android lifecycle bottlenecks.

### iOS Startup Phases

Analyze iOS-specific phases:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_app_start == true
| filter os.name == "iOS"
| summarize
    avg_pre_runtime = avg(app_start.ios.pre_runtime_init.end_time - app_start.ios.pre_runtime_init.start_time),
    avg_runtime_init = avg(app_start.ios.runtime_init.end_time - app_start.ios.runtime_init.start_time),
    avg_uikit_init = avg(app_start.ios.uikit_init.end_time - app_start.ios.uikit_init.start_time),
    avg_frame_render = avg(app_start.ios.initial_frame_render.end_time - app_start.ios.initial_frame_render.start_time),
    by: {frontend.name, app_start.type}

```

**Use Case:** Identify iOS initialization bottlenecks.

### Startup Trends

Track startup performance over time:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_app_start == true
| filter app_start.type == "cold"
| summarize
    p75_duration = percentile(duration, 75),
    by: {frontend.name, time_bucket = bin(start_time, 1d)}
| sort time_bucket asc

```

**Use Case:** Monitor startup regressions over time.

### Hot Start Analysis

Analyze background-to-foreground transitions:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_app_start == true
| filter app_start.type == "hot"
| summarize
    hot_starts = count(),
    p50_duration = percentile(duration, 50),
    p90_duration = percentile(duration, 90),
    by: {frontend.name}

```

**Use Case:** Optimize app resume experience.

## Mobile App Crashes & ANR Analysis

Analyze crashes and Application Not Responding (ANR) events for mobile applications.

**Data Source:** `fetch user.events` with `characteristics.has_crash` or `characteristics.has_anr`

**Key Fields:**

- `exception.type` - Exception class (e.g., `java.net.ConnectException`)
- `exception.message` - Error description
- `exception.stack_trace` - Full stack trace
- `exception.crash_signal_name` - Signal for native crashes (e.g., `SIGSEGV`)
- `error.is_fatal` - Whether error caused app termination

### All Crashes

Query all mobile crashes:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_crash == true
| summarize
    crash_count = count(),
    affected_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, exception.type, error.display_name}
| sort crash_count desc
| limit 20

```

**Use Case:** Prioritize crash fixes by frequency and user impact.

### ANR Events

Query Application Not Responding events (Android):

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_anr == true
| summarize
    anr_count = count(),
    affected_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, exception.message}
| sort anr_count desc

```

**Use Case:** Identify blocking operations causing ANRs.

### Crash Rate by App Version

Track crash rate across versions:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_crash == true
| summarize
    crash_count = count(),
    by: {frontend.name, app.version}
| sort app.version desc

```

**Use Case:** Detect version-specific regressions after releases.

### Crashes by Device Model

Identify device-specific issues:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_crash == true
| summarize
    crash_count = count(),
    affected_users = countDistinct(dt.rum.instance.id, precision: 9),
    by: {device.model, device.manufacturer, os.name, os.version}
| sort crash_count desc
| limit 20

```

**Use Case:** Prioritize device-specific bug fixes.

### Stack Trace Analysis

Get detailed crash information:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_crash == true
| fields
    start_time,
    app.version,
    exception.type,
    exception.message,
    exception.stack_trace,
    os.name,
    device.model
| sort start_time desc
| limit 50

```

**Use Case:** Debug specific crash with full context.

### Native Crash Signals

Analyze native crashes by signal:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_crash == true
| filter isNotNull(exception.crash_signal_name)
| summarize
    crash_count = count(),
    by: {exception.crash_signal_name, exception.type}
| sort crash_count desc

```

**Use Case:** Identify memory issues (SIGSEGV), abort signals (SIGABRT).

### Crash Trends Over Time

Track crash frequency:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_crash == true
| summarize
    crash_count = count(),
    by: {frontend.name, time_bucket = bin(start_time, 1d)}
| sort time_bucket asc

```

**Use Case:** Correlate crash spikes with releases or events.

### Fatal vs Non-Fatal Errors

Compare error severity:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_error == true
| summarize
    total = count(),
    fatal_count = countIf(error.is_fatal == true),
    by: {frontend.name}
| fieldsAdd non_fatal_count = total - fatal_count

```

**Use Case:** Balance crash-free rate vs overall error handling.

## Mobile View Summaries

Query mobile view engagement:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_view_summary == true
| summarize
    view_count = count(),
    unique_sessions = countDistinct(dt.rum.session.id),
    avg_foreground_time = avg(view.foreground_time),
    by: {frontend.name, view.name}
| sort view_count desc
| limit 30

```

**Use Case:** Analyze mobile screen engagement.

