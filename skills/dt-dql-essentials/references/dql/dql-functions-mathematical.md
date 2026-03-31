# DQL Functions — Mathematical

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

## Table of Contents

[`abs`](#abs) · [`acos`](#acos) · [`asin`](#asin) · [`atan`](#atan) · [`atan2`](#atan2) · [`bin`](#bin) · [`cbrt`](#cbrt) · [`ceil`](#ceil) · [`cos`](#cos) · [`cosh`](#cosh) · [`degreeToRadian`](#degreetoradian) · [`exp`](#exp) · [`floor`](#floor) · [`hexStringToNumber`](#hexstringtonumber) · [`hypotenuse`](#hypotenuse) · [`log`](#log) · [`log10`](#log10) · [`log1p`](#log1p) · [`numberToHexString`](#numbertohexstring) · [`power`](#power) · [`radianToDegree`](#radiantodegree) · [`random`](#random) · [`range`](#range) · [`round`](#round) · [`signum`](#signum) · [`sin`](#sin) · [`sinh`](#sinh) · [`sqrt`](#sqrt) · [`tan`](#tan) · [`tanh`](#tanh)

_mathematical function_

## `abs`
Returns the absolute value of a numeric expression.
`abs(expression)`
  `expression` (Double|Duration|Long) — The numeric expression for which to calculate the absolute value.
  → Double|Duration|Long

## `acos`
Calculate the acos of the given expression as an angle in radians.
`acos(expression)`
  `expression` (Double|Long) — The numeric expression, angle in radians for which to calculate the acos.
  → Double

## `asin`
Calculate the asin of the given expression as an angle in radians.
`asin(expression)`
  `expression` (Double|Long) — The numeric expression, angle in radians for which to calculate the asin.
  → Double

## `atan`
Calculate the atan of the given expression as an angle in radians.
`atan(expression)`
  `expression` (Double|Long) — The numeric expression, angle in radians for which to calculate the atan.
  → Double

## `atan2`
Calculate the atan2 of the given coordinates.
`atan2(ordinate, abscissa)`
  `ordinate` (Double|Long) — The ordinate coordinate.
  `abscissa` (Double|Long) — The abscissa coordinate.
  → Double

## `bin`
Aligns the value of the numeric or timestamp into buckets of the given interval starting at 0 (numeric) or Unix epoch (timestamp).
`bin(expression, interval [, at])`
  `expression` (Double|Duration|Long|Timestamp) — The expression that should be aligned.
  `interval` (Double|Duration|Long) — The interval by which to align the expression.
  `at:?` (Double|Duration|Long|Timestamp) — The offset to which each interval shall be shifted.  [default:NULL]
  → Double|Duration|Long|Timestamp

## `cbrt`
Computes the real cubic root of a numeric expression
`cbrt(expression)`
  `expression` (Double|Long) — The numeric expression for which to calculate the real cubic root.
  → Double

## `ceil`
Returns the smallest integer greater than or equal to the given number.
`ceil(expression)`
  `expression` (Double|Long) — The numeric expression to be rounded up.
  → Double|Long

## `cos`
Calculate the cos of the given expression as an angle in radians.
`cos(expression)`
  `expression` (Double|Long) — The numeric expression, angle in radians for which to calculate the cos.
  → Double

## `cosh`
Calculate the cosh of the given expression as an angle in radians.
`cosh(expression)`
  `expression` (Double|Long) — The numeric expression, angle in radians for which to calculate the cosh.
  → Double

## `degreeToRadian`
Converts an angle measured in degrees to an approximately equivalent angle measured in radians.
`degreeToRadian(expression)`
  `expression` (Double|Long) — The angle to be converted from degrees to radians.
  → Double

## `exp`
Computes the exponential function of a numeric expression.
`exp(expression)`
  `expression` (Double|Long) — The numeric expression for which to calculate the exponential function.
  → Double

## `floor`
Returns the largest integer smaller than or equal to the given number.
`floor(expression)`
  `expression` (Double|Long) — The numeric expression to be rounded down.
  → Double|Long

## `hexStringToNumber`
Converts a hexadecimal string into a number.
`hexStringToNumber(expression)`
  `expression` (String) — The string expression that will be converted to a number.
  → Double|Long

## `hypotenuse`
Calculate the hypotenuse of the right triangle of given sides.
`hypotenuse(x, y)`
  `x` (Double|Long) — Length of the first of the catheti.
  `y` (Double|Long) — Length of the second of the catheti.
  → Double

## `log`
Computes the natural logarithm (base e) of a numeric expression
`log(expression)`
  `expression` (Double|Long) — The numeric expression for which to calculate the natural logarithm (base e).
  → Double

## `log10`
Computes the decadic logarithm (base 10) of a numeric expression.
`log10(expression)`
  `expression` (Double|Long) — The numeric expression for which to calculate the decadic logarithm (base 10).
  → Double

## `log1p`
Computes log(1 + x) of a numeric expression x, where log is the natural logarithm (base e).
`log1p(expression)`
  `expression` (Double|Long) — The numeric expression for which to add one and calculate the natural logarithm (base e).
  → Double

## `numberToHexString`
Converts a number into a hexadecimal string.
`numberToHexString(expression [, minLength])`
  `expression` (Long) — The numeric expression that will be converted to a hexadecimal string.
  `minLength:?` (Long) — The minimum length of the returned hexadecimal string.  [min:0]
  → String

## `power`
Raises a base numeric expression to a given exponent.
`power(base, exponent)`
  `base` (Double|Long) — The numeric expression acting as the base of the power calculation.
  `exponent` (Double|Long) — The numeric expression acting as the exponent of the power calculation.
  → Double

## `radianToDegree`
Converts an angle measured in radians to an approximately equivalent angle measured in degrees.
`radianToDegree(expression)`
  `expression` (Double|Long) — The angle to be converted from radians to degrees.
  → Double

## `random`
Creates a random double value.
`random()`
  → Double

## `range`
Aligns the value of the numeric or timestamp into buckets of the given interval starting at 0 (numeric) or Unix epoch (timestamp) keeping start and end of each interval.
`range(expression, interval [, at])`
  `expression` (Double|Duration|Long|Timestamp) — The expression that should be aligned.
  `interval` (Double|Duration|Long) — The interval by which to align the expression.
  `at:?` (Double|Duration|Long|Timestamp) — The offset to which each interval shall be shifted.  [default:NULL]
  → Record

## `round`
Round the numeric expression to the next long or to the double closest to the provided number of places after the decimal point.
`round(expression [, decimals])`
  `expression` (Double|Long) — Numeric expression to be rounded.
  `decimals:?` (Long) — Number of places after the decimal point.  [default:0, min:0]
  → Double|Long

## `signum`
Returns the signum of a numeric expression, that is, 1 if the expression is positive, -1 if it is negative, or 0 if it is zero.
`signum(expression)`
  `expression` (Double|Long) — The numeric expression for which to calculate the signum.
  → Double|Long

## `sin`
Calculate the sin of the given expression as an angle in radians.
`sin(expression)`
  `expression` (Double|Long) — The numeric expression, angle in radians for which to calculate the sin.
  → Double

## `sinh`
Calculate the sinh of the given expression as an angle in radians.
`sinh(expression)`
  `expression` (Double|Long) — The numeric expression, angle in radians for which to calculate the sinh.
  → Double

## `sqrt`
Computes the positive square root of a numeric expression.
`sqrt(expression)`
  `expression` (Double|Long) — The numeric expression for which to calculate the square root.
  → Double

## `tan`
Calculate the tan of the given expression as an angle in radians.
`tan(expression)`
  `expression` (Double|Long) — The numeric expression, angle in radians for which to calculate the tan.
  → Double

## `tanh`
Calculate the tanh of the given expression as an angle in radians.
`tanh(expression)`
  `expression` (Double|Long) — The numeric expression, angle in radians for which to calculate the tanh.
  → Double
