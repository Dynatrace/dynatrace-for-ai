# DQL Functions — Create

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

_create function for primitive data types_

## `array`
Creates an `array` from the list of given parameters.
`array(expression, …)`
  `expression*` (any) — An element inside the array.
  → Array

## `duration`
Creates a `duration` from the given amount and time unit.
`duration(value, unit)`
  `value` (Double|Long) — The numeric value for the duration.
  `unit` (String) — The time unit of the duration.
  → Duration

## `ip`
Creates an `ip` from the given string expression.
`ip(expression)`
  `expression` (String) — The string expression for an ip address
  → IpAddress

## `record`
Creates a `record` from the keys and values of the parameters.
`record(expression, …)`
  `expression*` (any) — An expression to add to the record.  [assign:optional]
  → Record

## `smartscapeId`
Creates a `smartscapeId` from the given string and long expression.
`smartscapeId(type, numericId)`
  `type` (String) — The type of smartscapeId as string.
  `numericId` (Long) — The numeric id of smartscapeId as long.
  → SmartscapeId

## `timeframe`
Creates a `timeframe` from the given start and end timestamp or duration.
`timeframe(from [, to])`
  `from` (Duration|String|Timestamp) — The start of the timeframe. Can be a timestamp or a duration. A duration is interpreted as an offset from `now()`.
  `to:?` (Duration|String|Timestamp) — The end of the timeframe. Can be a timestamp or a duration. A duration is interpreted as an offset from `now()`.  [default:now()]
  → Timeframe

## `timestamp`
Creates a `timestamp` from the provided values.
`timestamp(year, month, day, hour, minute, second [, millis] [, micros] [, nanos] [, timezone])`
  `year` (Long) — The year of the timestamp as a number.
  `month` (Long) — The month of the timestamp as a number.
  `day` (Long) — The day of the timestamp as a number.
  `hour` (Long) — The hour of the timestamp as a number.
  `minute` (Long) — The minute of the timestamp as a number.
  `second` (Long) — The second of the timestamp as a number.
  `millis:?` (Long) — The millisecond of the timestamp as a number.  [default:0]
  `micros:?` (Long) — The microsecond of the timestamp as a number.  [default:0]
  `nanos:?` (Long) — The nanosecond of the timestamp as a number.  [default:0]
  `timezone:?` (—) — The timezone used to format the timestamp.
  → Timestamp

## `timestampFromUnixMillis`
Creates a `timestamp` from the given milliseconds since Unix epoch.
`timestampFromUnixMillis(millis)`
  `millis` (Long) — Milliseconds since unix start time.
  → Timestamp

## `timestampFromUnixNanos`
Creates a `timestamp` from the given nanoseconds since Unix epoch.
`timestampFromUnixNanos(nanos)`
  `nanos` (Long) — Nanoseconds since unix start time.
  → Timestamp

## `timestampFromUnixSeconds`
Creates a `timestamp` from the given seconds since Unix epoch.
`timestampFromUnixSeconds(seconds)`
  `seconds` (Long) — Seconds since unix start time.
  → Timestamp

## `uid128`
Creates a `uid` from the given two long expressions.
`uid128(firstExpression, secondExpression)`
  `firstExpression` (Long) — The 1st long expression for a uid.
  `secondExpression` (Long) — The 2nd long expression for a uid.
  → UID

## `uid64`
Creates a `uid` from the given long expression.
`uid64(expression)`
  `expression` (Long) — The long expression for a uid.
  → UID

## `uuid`
Creates a `uuid` from the given two long expressions.
`uuid(mostSignificantBits, leastSignificantBits)`
  `mostSignificantBits` (Long) — The 1st long expression for the most significant bits of a uuid.
  `leastSignificantBits` (Long) — The 2nd long expression for the least significant bits of a uuid.
  → UID
