# DQL Functions — Entities

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

_entities function_

## `classicEntitySelector`
Returns entities matching the specified entity selector.
`classicEntitySelector(entitySelector)`
  `entitySelector` (String) — The entity selector string.
  → Array

## `entityAttr`
Returns the attribute value for an entity.
`entityAttr(expression, name [, type])`
  `expression` (any) — The expression to determine the entity ID.
  `name` (—) — The entity attribute name that to be queried.
  `type:?` (—) — The entity type that to be queried.
  → any

## `entityName`
Returns the name of an entity.
`entityName(expression [, type])`
  `expression` (any) — The expression to determine the entity ID.
  `type:?` (—) — The entity type that to be queried.
  → String
