# Mobile App Crashes & ANR Analysis

Analyze crashes and Application Not Responding (ANR) events for mobile applications.

**Data Source:** `fetch user.events` with `characteristics.has_crash` or `characteristics.has_anr`

**Key Fields:**

- `exception.type` - Exception class (e.g., `java.net.ConnectException`)
- `exception.message` - Error description
- `exception.stack_trace` - Full stack trace
- `exception.crash_signal_name` - Signal for native crashes (e.g., `SIGSEGV`)
- `error.is_fatal` - Whether error caused app termination

## All Crashes

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

## ANR Events

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

## Crash Rate by App Version

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

## Crashes by Device Model

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

## Stack Trace Analysis

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

## Native Crash Signals

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

## Crash Trends Over Time

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

## Fatal vs Non-Fatal Errors

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

