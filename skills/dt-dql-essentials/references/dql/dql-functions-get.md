# DQL Functions — Get

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

_get function_

## `arrayElement`
Extracts a single element from an array.
`arrayElement(expression, index)`
  `expression` (Array) — The array from which to extract an element.
  `index` (Long) — The index of the element to extract.
  → any

## `getEnd`
Extracts the end timestamp from a timeframe.
`getEnd(timeframe)`
  `timeframe` (Timeframe) — The timeframe expression from which to get the end of the interval.
  → Timestamp

## `getHighBits`
Extracts the most significant bits of a given UID or IP.
`getHighBits(expression)`
  `expression` (IpAddress|UID) — The expression from which to extract the most significant bits.
  → Long

## `getLowBits`
Extracts the least significant bits of a given UID or IP.
`getLowBits(expression)`
  `expression` (IpAddress|UID) — The expression from which to extract the least significant bits.
  → Long

## `getStart`
Extracts the start timestamp from a timeframe.
`getStart(timeframe)`
  `timeframe` (Timeframe) — The timeframe expression from which to get the start of the interval.
  → Timestamp
