# DQL Functions — Cast

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

_cast function_

## `asArray`
Returns `array` value if the value is `array`, otherwise `null`.
`asArray(value)`
  `value` (Array) — The expression to cast as an array.
  → Array

## `asBinary`
Returns `binary` value (byte array) if the value is `binary`, otherwise `null`.
`asBinary(value)`
  `value` (Binary) — The expression to cast as a byte array.
  → Binary

## `asBoolean`
Returns `boolean` value if the value is `boolean`, otherwise `null`.
`asBoolean(value)`
  `value` (Boolean) — The expression to cast as a boolean.
  → Boolean

## `asDouble`
Returns `double` value if the value is `double`, otherwise `null`.
`asDouble(value)`
  `value` (Double) — The expression to cast as a double.
  → Double

## `asDuration`
Returns `duration` value if the value is `duration`, otherwise `null`.
`asDuration(value)`
  `value` (Duration) — The expression to cast as a duration.
  → Duration

## `asIp`
Returns `ip_address` value if the value is `ip_address`, otherwise `null`.
`asIp(value)`
  `value` (IpAddress) — The expression to cast as an ip address.
  → IpAddress

## `asLong`
Returns `long` value if the value is `long`, otherwise `null`.
`asLong(value)`
  `value` (Long) — The expression to cast as a long.
  → Long

## `asNumber`
Returns same value if the value is `integer`, `long`, `double`, otherwise `null`.
`asNumber(value)`
  `value` (Double|Long) — The expression to cast as a number.
  → Double|Long

## `asRecord`
Returns `record` value if the value is `record`, otherwise `null`.
`asRecord(value)`
  `value` (Record) — The expression to cast as a record.
  → Record

## `asSmartscapeId`
Returns `smartscapeId` value if the value is `smartscapeId`, otherwise `null`.
`asSmartscapeId(value)`
  `value` (SmartscapeId) — The expression to cast as a smartscape id.
  → SmartscapeId

## `asString`
Returns `string` value if the value is `string`, otherwise `null`.
`asString(value)`
  `value` (String) — The expression to cast as a string.
  → String

## `asTimeframe`
Returns `timeframe` value if the value is `timeframe`, otherwise `null`.
`asTimeframe(value)`
  `value` (Timeframe) — The expression to cast as a timeframe.
  → Timeframe

## `asTimestamp`
Returns `timestamp` value if the value is `timestamp`, otherwise `null`.
`asTimestamp(value)`
  `value` (Timestamp) — The expression to cast as a timestamp.
  → Timestamp

## `asUid`
Returns `uid` value if the value is `uid`, otherwise `null`.
`asUid(value)`
  `value` (UID) — The expression to cast as a uid.
  → UID
