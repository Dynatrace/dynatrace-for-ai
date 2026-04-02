# DQL Functions — Time

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

## Table of Contents

[`formatTimestamp`](#formattimestamp) · [`getDayOfMonth`](#getdayofmonth) · [`getDayOfWeek`](#getdayofweek) · [`getDayOfYear`](#getdayofyear) · [`getHour`](#gethour) · [`getMinute`](#getminute) · [`getMonth`](#getmonth) · [`getSecond`](#getsecond) · [`getWeekOfYear`](#getweekofyear) · [`getYear`](#getyear) · [`now`](#now) · [`unixMillisFromTimestamp`](#unixmillisfromtimestamp) · [`unixNanosFromTimestamp`](#unixnanosfromtimestamp) · [`unixSecondsFromTimestamp`](#unixsecondsfromtimestamp)

_time function_

## `formatTimestamp`
Formats the timestamp according to a format string (using the defined interval).
`formatTimestamp(timestamp [, interval] [, format] [, timezone] [, locale])`
  `timestamp` (Timestamp) — The timestamp expression that should be formatted.
  `interval:?` (Duration) — The duration expression used to align the timestamp.
  `format:?` (String) — The formatting pattern.  [default:"yyyy-MM-dd'T'HH:mm:ss.SSSSSSSSS"]
  `timezone:?` (—) — The timezone used to format the timestamp.
  `locale:?` (—) — The locale used to format the timestamp.
  → String

## `getDayOfMonth`
Extracts the day of month from a timestamp.
`getDayOfMonth(timestamp [, timezone])`
  `timestamp` (Timestamp) — The timestamp expression from which the day of month will be extracted.
  `timezone:?` (—) — The timezone that should be used.
  → Long

## `getDayOfWeek`
Extracts the day of week from a timestamp.
`getDayOfWeek(timestamp [, timezone])`
  `timestamp` (Timestamp) — The timestamp expression from which the day of week will be extracted.
  `timezone:?` (—) — The timezone that should be used.
  → Long

## `getDayOfYear`
Extracts the day of year from a timestamp.
`getDayOfYear(timestamp [, timezone])`
  `timestamp` (Timestamp) — The timestamp expression from which the day of year will be extracted.
  `timezone:?` (—) — The timezone that should be used.
  → Long

## `getHour`
Extracts the hour from a timestamp.
`getHour(timestamp [, timezone])`
  `timestamp` (Timestamp) — The timestamp expression from which the hour will be extracted.
  `timezone:?` (—) — The timezone that should be used.
  → Long

## `getMinute`
Extracts the minute from a timestamp.
`getMinute(timestamp [, timezone])`
  `timestamp` (Timestamp) — The timestamp expression from which the minute will be extracted.
  `timezone:?` (—) — The timezone that should be used.
  → Long

## `getMonth`
Extracts the month from a timestamp.
`getMonth(timestamp [, timezone])`
  `timestamp` (Timestamp) — The timestamp expression from which the month will be extracted.
  `timezone:?` (—) — The timezone that should be used.
  → Long

## `getSecond`
Extracts the second from a timestamp.
`getSecond(timestamp [, timezone])`
  `timestamp` (Timestamp) — The timestamp expression from which the second will be extracted.
  `timezone:?` (—) — The timezone that should be used.
  → Long

## `getWeekOfYear`
Extracts the week of year from a timestamp.
`getWeekOfYear(timestamp [, timezone])`
  `timestamp` (Timestamp) — The timestamp expression from which the week of year will be extracted.
  `timezone:?` (—) — The timezone that should be used.
  → Long

## `getYear`
Extracts the year from a timestamp.
`getYear(timestamp [, timezone])`
  `timestamp` (Timestamp) — The timestamp expression from which the year will be extracted.
  `timezone:?` (—) — The timezone that should be used.
  → Long

## `now`
Returns the current time as fixed timestamp of the query start.
`now()`
  → Timestamp

## `unixMillisFromTimestamp`
Converts a timestamp into milliseconds
`unixMillisFromTimestamp(timestamp)`
  `timestamp` (Timestamp) — The timestamp expression which will be converted to milliseconds since epoch.
  → Long

## `unixNanosFromTimestamp`
Converts a timestamp into nanoseconds
`unixNanosFromTimestamp(timestamp)`
  `timestamp` (Timestamp) — The timestamp expression which will be converted to nanoseconds since epoch.
  → Long

## `unixSecondsFromTimestamp`
Converts a timestamp into seconds
`unixSecondsFromTimestamp(timestamp)`
  `timestamp` (Timestamp) — The timestamp expression which will be converted to seconds since epoch.
  → Long
