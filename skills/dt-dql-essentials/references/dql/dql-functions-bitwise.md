# DQL Functions — Bitwise

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

_bitwise function_

## `bitwiseAnd`
Calculates the bitwise `and` between two long expressions.
`bitwiseAnd(firstExpression, secondExpression)`
  `firstExpression` (Long) — The first long expression for the binary bitwise operation.
  `secondExpression` (Long) — The second long expression for the binary bitwise operation.
  → Long

## `bitwiseCountOnes`
Counts the bits set to one of a long expression.
`bitwiseCountOnes(expression)`
  `expression` (Long) — The long expression whose bits set to one will be counted.
  → Long

## `bitwiseNot`
Inverts the bits of a long expression.
`bitwiseNot(expression)`
  `expression` (Long) — The long expression whose bits will be inverted.
  → Long

## `bitwiseOr`
Calculates the bitwise `or` between two long expressions.
`bitwiseOr(firstExpression, secondExpression)`
  `firstExpression` (Long) — The first long expression for the binary bitwise operation.
  `secondExpression` (Long) — The second long expression for the binary bitwise operation.
  → Long

## `bitwiseShiftLeft`
Bitwise left shift long expression by a number of given bits.
`bitwiseShiftLeft(expression, numberOfBits)`
  `expression` (Long) — The long expression that will be bitwise shifted left.
  `numberOfBits` (Long) — The number of bits by which the expression will be shifted left.
  → Long

## `bitwiseShiftRight`
Bitwise right shift long expression by a number of given bits.
`bitwiseShiftRight(expression, numberOfBits [, ignoreSign])`
  `expression` (Long) — The long expression that will be bitwise shifted right.
  `numberOfBits` (Long) — The number of bits by which the expression will be shifted right.
  `ignoreSign:?` (Boolean) — The boolean expression that indicates if the sign bit should be ignored (treated like any bit) while shifting. If false, the sign bit is preserved and just the other bits are shifted.  [default:FALSE]
  → Long

## `bitwiseXor`
Calculates the bitwise `xor` between two long expressions.
`bitwiseXor(firstExpression, secondExpression)`
  `firstExpression` (Long) — The first long expression for the binary bitwise operation.
  `secondExpression` (Long) — The second long expression for the binary bitwise operation.
  → Long
