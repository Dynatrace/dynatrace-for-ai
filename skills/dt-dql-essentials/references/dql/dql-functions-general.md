# DQL Functions — General

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

_function_

## `jsonField`
Parses a JSON string and extracts one field.
`jsonField(expression, fieldName [, seek])`
  `expression` (String) — The json string that should be parsed.
  `fieldName` (String) — The string literal with the name of the field to be extracted.
  `seek:?` (Boolean) — Flag indicating if the function should search for JSON object in the expression.  [default:FALSE]
  → Array|Boolean|Double|Long|Record|String

## `jsonPath`
Parses a JSON string and extracts one field described by a path.
`jsonPath(expression, jsonPath [, seek])`
  `expression` (String) — The json string that should be parsed.
  `jsonPath` (—) — The string literal with the JSON-path to be extracted.
  `seek:?` (Boolean) — Flag indicating if the function should search for JSON object in the expression.  [default:FALSE]
  → Array|Boolean|Double|Long|Record|String

## `lookup`
Returns a record containing all lookup fields.
`lookup(lookupTable [, sourceField ,] lookupField [, executionOrder])`
  `lookupTable` (—) — Sub-query for records with fields to add or overwrite in the input.
  `sourceField:?` (any) — Specifies a field of the source ("left").
  `lookupField:` (any) — Specifies a field of the lookup ("right").
  `executionOrder:?` (—) — Defines which side of the join will be executed first.  [default:auto]
  `broadcast:?` (—) — Defines broadcasting strategy.  [default:enabled]
  → Record

## `parse`
Extracts a single value from a string as specified in the pattern or a record if there are multiple named matchers.
`parse(expression, pattern)`
  `expression` (String) — A field or string expression to parse.
  `pattern` (—) — The parse pattern.
  `baseTime:?` (Timestamp) — A timestamp expression providing the base time for date/time parsing.
  → any

## `parseAll`
Extracts several values from a string as specified in the pattern.
`parseAll(expression, pattern)`
  `expression` (String) — A field or string expression to parse.
  `pattern` (—) — The parse pattern.
  `baseTime:?` (Timestamp) — A timestamp expression providing the base time for date/time parsing.
  → Array

## `type`
Returns the type of a value as `string`.
`type(expression [, withSubtype])`
  `expression` (any) — The expression to get the type of.
  `withSubtype:?` (Boolean) — Whether the type string should include subtype information if available.  [default:FALSE]
  → String
