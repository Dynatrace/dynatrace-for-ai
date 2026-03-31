# DQL Functions — Time series aggregation for expressions

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

## Table of Contents

[`avg`](#avg) · [`count`](#count) · [`countDistinct`](#countdistinct) · [`countDistinctApprox`](#countdistinctapprox) · [`countDistinctExact`](#countdistinctexact) · [`countIf`](#countif) · [`end`](#end) · [`max`](#max) · [`median`](#median) · [`min`](#min) · [`percentRank`](#percentrank) · [`percentile`](#percentile) · [`percentileFromSamples`](#percentilefromsamples) · [`start`](#start) · [`sum`](#sum)

_makeTimeseries_

## `avg`
Calculates the average of the expression values in each bucket.
`avg(expression [, default] [, rate] [, scalar])`
  `expression` (Double|Duration|Long) — The expression the aggregation function shall be applied to.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  → Array|Double

## `count`
Counts the number of records in each bucket.
`count([[default] [, rate] [, scalar]])`
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  → Array|Double

## `countDistinct`
This function is an alias for countDistinctApprox().
`countDistinct(expression [, precision] [, default] [, rate] [, scalar])`
  `expression` (any) — The expression the aggregation function shall be applied to.
  `precision:?` (Long) — The precision in the interval [3, 16].  [default:14, min:3]
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  → Array|Double

## `countDistinctApprox`
Counts the approximate number of distinct records in each bucket.
`countDistinctApprox(expression [, precision] [, default] [, rate] [, scalar])`
  `expression` (any) — The expression the aggregation function shall be applied to.
  `precision:?` (Long) — The precision in the interval [3, 16].  [default:14, min:3]
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  → Array|Double

## `countDistinctExact`
Counts the precise number of distinct records in each bucket.
`countDistinctExact(expression [, default] [, rate] [, scalar])`
  `expression` (any) — The expression the aggregation function shall be applied to.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  → Array|Double

## `countIf`
Counts the number of records matching the provided condition in each bucket.
`countIf(expression [, default] [, rate] [, scalar])`
  `expression` (Boolean) — The expression the aggregation function shall be applied to.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  → Array|Double

## `end`
Produces an array of timestamps representing the end of the bin.
`end()`
  → Array

## `max`
Calculates the maximum of the expression values in each bucket.
`max(expression [, default] [, rate] [, scalar])`
  `expression` (Double|Duration|Long) — The expression the aggregation function shall be applied to.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  → Array|Double

## `median`
Calculates the median of the expression value in each bucket.
`median(expression [, weight] [, default] [, rate] [, scalar])`
  `expression` (Double|Duration|Long) — The expression the aggregation function shall be applied to.
  `weight:?` (Double|Long) — The weight of the corresponding expression (e.g. its sampling ratio).  [default:1, min:0]
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  → Array|Double

## `min`
Calculates the minimum of the expression values in each bucket.
`min(expression [, default] [, rate] [, scalar])`
  `expression` (Double|Duration|Long) — The expression the aggregation function shall be applied to.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  → Array|Double

## `percentRank`
Calculates the percentile rank for a given value.
`percentRank(expression, value [, default] [, rate] [, scalar])`
  `expression` (Double|Duration|Long) — The expression the aggregation function shall be applied to.
  `value` (Double|Long) — The percentile to compute, between 0 and 100.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  → Array|Double

## `percentile`
Calculates the requested percentile of the expression value in each bucket.
`percentile(expression, percentile [, weight] [, default] [, rate] [, scalar])`
  `expression` (Double|Duration|Long) — The expression the aggregation function shall be applied to.
  `percentile` (Double|Long) — The percentile to compute, between 0 and 100.  [min:0]
  `weight:?` (Double|Long) — The weight of the corresponding expression (e.g. its sampling ratio).  [default:1, min:0]
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  → Array|Double

## `percentileFromSamples`
Calculates the requested percentile of the array expression in each bucket.
`percentileFromSamples(expression, percentile [, originalCount] [, default] [, rate] [, scalar])`
  `expression` (Array) — The expression the aggregation function shall be applied to.
  `percentile` (Double|Long) — The percentile to compute, between 0 and 100.  [min:0]
  `originalCount:?` (Double|Long) — The original element count of the given array expression.  [min:0]
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  → Array|Double

## `start`
Produces an array of timestamps representing the start of the bin.
`start()`
  → Array

## `sum`
Calculates the sum of the expression values in each bucket.
`sum(expression [, default] [, rate] [, scalar])`
  `expression` (Double|Duration|Long) — The expression the aggregation function shall be applied to.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  → Array|Double
