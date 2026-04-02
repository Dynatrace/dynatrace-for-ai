# DQL Functions — Flow

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

_boolean flow control_

## `coalesce`
Returns the first non-`null` argument, if any, otherwise `null`.
`coalesce(expression, …)`
  `expression*` (any) — Returned if previous arguments are null.
  → any

## `if`
Evaluates the condition, and returns the value of either the then or else parameter, depending on whether the condition evaluated to `true` (then) or `false` or `null` (else - or `null` if the else parameter is missing).
`if(condition, then [, else])`
  `condition` (Boolean) — The condition to check.
  `then` (any) — The expression if the condition is true.
  `else:?` (any) — The expression if the condition is false or null.  [default:NULL]
  → any
