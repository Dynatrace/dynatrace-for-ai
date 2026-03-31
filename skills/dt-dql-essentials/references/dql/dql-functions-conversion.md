# DQL Functions — Conversion

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

_conversion function_

## `toArray`
Returns the value if it is an `array`. Otherwise, converts a value to the single element array holding that value.
`toArray(value)`
  `value` (any) — The expression to convert to an array if possible.
  → Array

## `toBoolean`
Converts a value to `boolean` if the value is of a suitable type. If the argument is an `array`, the element at position 0 is converted.
`toBoolean(value)`
  `value` (Array|Boolean|Double|Long|String) — The expression to convert to a boolean if possible.
  → Boolean

## `toDouble`
Converts a value to `double` if the value is of a suitable type. If the argument is an `array`, the element at position 0 is converted.
`toDouble(value)`
  `value` (Array|Boolean|Double|Duration|IpAddress|Long|String|Timestamp|UID) — The expression to convert to a double if possible.
  → Double

## `toDuration`
Converts a value to `duration` if the value is of a suitable type. If the argument is an `array`, the element at position 0 is converted.
`toDuration(value)`
  `value` (Array|Double|Duration|Long|String|Timeframe) — The expression to convert to a duration if possible.
  → Duration

## `toIp`
Converts a value to `ip_address` if the value is of a suitable type. If the argument is an `array`, the element at position 0 is converted.
`toIp(value)`
  `value` (Array|Double|IpAddress|Long|String) — The expression to convert to an ip address if possible.
  → IpAddress

## `toLong`
Converts a value to `long` if the value is of a suitable type. If the argument is an `array`, the element at position 0 is converted.
`toLong(value)`
  `value` (Array|Boolean|Double|Duration|IpAddress|Long|String|Timestamp|UID) — The expression to convert to a long if possible.
  → Long

## `toSmartscapeId`
Converts a value to `smartscapeId` if the value is of a suitable type. If the argument is an `array`, the element at position 0 is converted.
`toSmartscapeId(value)`
  `value` (Array|SmartscapeId|String) — The expression to convert to a smartscape id if possible.
  → SmartscapeId

## `toString`
Returns the string representation of a value.
`toString(value)`
  `value` (any) — The expression to convert to a string if possible.
  → String

## `toTimeframe`
Converts a value to `timeframe` if the value is of a suitable type. If the argument is an `array`, the element at position 0 is converted.
`toTimeframe(value)`
  `value` (Array|String|Timeframe) — The expression to convert to a timeframe if possible.
  → Timeframe

## `toTimestamp`
Converts a value to `timestamp` if the value is of a suitable type. If the argument is an `array`, the element at position 0 is converted.
`toTimestamp(value)`
  `value` (Array|Double|Long|String|Timestamp) — The expression to convert to a timestamp if possible.
  → Timestamp

## `toUid`
Converts a value to `uid` if the value is of a suitable type. If the argument is an `array`, the element at position 0 is converted.
`toUid(value)`
  `value` (Array|Double|Long|String|UID) — The expression to convert to a uid if possible.
  → UID

## `toVariant` (deprecated)
Converts a value to `variant` with boxed element inside.
`toVariant(value)`
  `value` (any) — The expression to convert to a variant if possible.
  → any
