# DQL Functions — Iterative

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

_iterative function_

## `iAny`
Checks an iterative boolean expression and returns `true` if it was `true` at least once, `false` if not.
`iAny(expression)`
  `expression` (Boolean) — The iterative boolean expression.
  → Boolean

## `iCollectArray`
Collects the results of an iterative expression into an array.
`iCollectArray(expression)`
  `expression` (any) — The iterative expression that should be collected into an array.
  → Array

## `iIndex`
Returns the current index of an iterative expression.
`iIndex()`
  → Long
