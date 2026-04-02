# DQL Functions — Boolean

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

_boolean checks_

## `exists`
Tests if a field exists.
`exists(field)`
  `field` (any) — The name of the field that will be checked if it exists.
  → Boolean

## `in`
Tests if a needle value is contained in any of the haystack parameters.
`in(needle, haystack, …)`
  `needle` (any) — The element(s) to search for (the needle).
  `haystack*` (any) — The elements where to search for the needle element (the haystack).
  → Boolean

## `isFalseOrNull`
Tests if a value is `false` or `null`
`isFalseOrNull(expression)`
  `expression` (Boolean) — The expression to check if it is false or null.
  → Boolean

## `isNotNull`
Tests if a value is not `null`
`isNotNull(expression)`
  `expression` (any) — The expression to check if it is not null.
  → Boolean

## `isNull`
Tests if a value is `null`.
`isNull(expression)`
  `expression` (any) — The expression to check if it is null.
  → Boolean

## `isTrueOrNull`
Tests if a value is `true` or `null`.
`isTrueOrNull(expression)`
  `expression` (Boolean) — The expression to check if it is true or null.
  → Boolean

## `isUid128`
Tests if a uid value is of subtype uid128.
`isUid128(expression)`
  `expression` (UID) — The uid expression that will be checked if it is of subtype uid128.
  → Boolean

## `isUid64`
Tests if a uid value is of subtype uid64.
`isUid64(expression)`
  `expression` (UID) — The uid expression that will be checked if it is of subtype uid64.
  → Boolean

## `isUuid`
Tests if a uid value is of subtype uuid.
`isUuid(expression)`
  `expression` (UID) — The uid expression that will be checked if it is of subtype uuid.
  → Boolean
