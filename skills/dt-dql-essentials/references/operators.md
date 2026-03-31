# Operators

## `in` operator

The `in` comparison operator evaluates the occurrence of a value returned by the left side's expression within a list of values returned by the right side's DQL subquery.
The `in` operator allows building the comparison set dynamically (vs. statically using the `in()` function).

Syntax: `expression in [execution block]`
- Right side execution block must return one field
- Result of right side block cannot be larger than 128MB

## Examples

Getting events having `analysis.id` equal to `scan.id` (from a specific event in the bizevent table):

```dql
fetch events, from: -24h
| filter analysis.id in [
fetch bizevents, from:-24h
| filter event.type=="COMPLIANCE_SCAN_COMPLETED"
// systemIds are passed from FE when building the query
| filter in(object.id, array("KUBERNETES_CLUSTER-641F38AF23F564F6", "KUBERNETES_CLUSTER-96A48749295CC703", "KUBERNETES_CLUSTER-ECEB343907CBAFCC"))
| dedup object.id, sort: {timestamp, desc}
| fields scan.id
]
```

______________________________________________________________________

## Time alignment `@`

The `@` operator aligns a timestamp to the provided time unit. It rounds down the timestamp to the beginning of the time unit.

Syntax: `[timestamp|duration|calendarDuration] @ unit`

### Critical rules

**CRITICAL:** No space between `@` and the unit — `now()@h` not `now() @h`.

**Order:** Apply offset first, then align — `now()-2h@h`, not `now()@h-2h`.

### `m` vs. `M`

- `m` = **minutes** — e.g. `now()-30m` (30 minutes ago)
- `M` = **months** — e.g. `now()-1M` (1 month ago)

This is a frequent source of errors. Double-check the case.

### Left side

On the left side of the `@` operator, you can use a timestamp expression, a duration expression, or a calendar duration.
If you use the `@` operator without an expression on the left side, it uses `now()` and aligns the current time to the time unit. For example, `@h` is the beginning of the current hour, equivalent to `now()@h`. Expressions of type duration and calendar durations are considered as an offset to `now()`.
For example, `-2M@...` is equivalent to `(now() - 2M)@...`.

### Right side

The time unit can be any DQL supported duration unit including `s` (second), `m` (minute), `h` (hour), or a calendar duration unit like `d` (day), `w` (week), `M` (month), `q` (quarter), and `y` (year).

Duration units (`h`, `m`, `s`, `ms`, `us`, and `ns`) allow adding a factor, for example, `@3h`.
Leaving the factor out is equivalent to setting it to 1. Note the following constraints when adding such factor:

| Unit | Meaning — rounding to beginning of                                                    | Allowed factors                    | Comments                                |
|------|---------------------------------------------------------------------------------------|------------------------------------|-----------------------------------------|
| `ns` | nanosecond                                                                            | all divisors of 1000 are supported |                                         |
| `us` | microsecond                                                                           | all divisors of 1000 are supported |                                         |
| `ms` | millisecond                                                                           | all divisors of 1000 are supported |                                         |
| `s`  | second                                                                                | all divisors of 60 are supported   |                                         |
| `m`  | minute                                                                                | all divisors of 60 are supported   |                                         |
| `h`  | hour                                                                                  | all divisors of 24 are supported   |                                         |
| `d`  | day                                                                                   | any                                | daylight saving time taken into account |
| `w`  | week (Monday)                                                                         |                                    | daylight saving time taken into account |
| `wW` | week starting on chosen day (W=0 or 7 — Sunday, W=1 — Monday, W=2 — Tuesday, etc)    |                                    | daylight saving time taken into account |
| `M`  | month                                                                                 |                                    | daylight saving time taken into account |
| `q`  | quarter                                                                               |                                    |                                         |
| `y`  | year                                                                                  |                                    |                                         |

### Common patterns

| Expression   | Meaning                                                     |
| ------------ | ----------------------------------------------------------- |
| `now()@h`    | Current time, aligned to the hour boundary                  |
| `now()@d`    | Midnight today                                              |
| `now()@w1`   | Monday this week                                            |
| `@w1`        | Monday this week (shorthand for `now()@w1`)                 |
| `@w2`        | Tuesday this week                                           |
| `@w5`        | Friday this week                                            |
| `now()-2h@h` | 2 hours ago, aligned to the hour (offset first, then align) |
| `-1w@w1`     | 1 week ago, aligned to the start of the week (Monday)       |

