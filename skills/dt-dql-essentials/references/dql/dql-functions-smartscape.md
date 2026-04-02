# DQL Functions — Smartscape

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

_smartscape function_

## `getNodeField`
Returns the field value for a smartscape node.
`getNodeField(expression, name)`
  `expression` (SmartscapeId|String) — The expression to determine the smartscape node ID.
  `name` (String) — The smartscape field name to be queried.
  → any

## `getNodeName`
Returns the name of a smartscape node.
`getNodeName(expression)`
  `expression` (SmartscapeId|String) — The expression to determine the smartscape node ID.
  → String
