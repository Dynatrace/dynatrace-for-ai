# DQL Functions — Time series aggregation for metrics

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

## Table of Contents

[`avg`](#avg) · [`count`](#count) · [`countDistinct`](#countdistinct) · [`end`](#end) · [`max`](#max) · [`median`](#median) · [`min`](#min) · [`percentRank`](#percentrank) · [`percentile`](#percentile) · [`start`](#start) · [`sum`](#sum)

_timeseries_

## `avg`
Calculates the average of the metric values in each bucket.
`avg(metricKey [, rollup] [, default] [, rate] [, scalar] [, filter])`
  `metricKey` (—) — The metric key the aggregation function shall be applied to.
  `rollup:?` (—) — The rollup type that shall be used for the metric.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  `filter:?` (Boolean) — Filter condition that shall be applied for this aggregation.
  → Array|Double

## `count`
Calculates the number of time bins with values.
`count(metricKey [, default] [, scalar] [, filter])`
  `metricKey` (—) — The metric key the aggregation function shall be applied to.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  `filter:?` (Boolean) — Filter condition that shall be applied for this aggregation.
  → Array|Double

## `countDistinct`
Calculates the number of distinct values in each bucket.
`countDistinct(metricKey [, default] [, scalar] [, filter])`
  `metricKey` (—) — The metric key the aggregation function shall be applied to.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  `filter:?` (Boolean) — Filter condition that shall be applied for this aggregation.
  → Array|Double

## `end`
Produces an array of timestamps representing the end of the bin.
`end()`
  → Array

## `max`
Calculates the maximum of the metric values in each bucket.
`max(metricKey [, rollup] [, default] [, rate] [, scalar] [, filter])`
  `metricKey` (—) — The metric key the aggregation function shall be applied to.
  `rollup:?` (—) — The rollup type that shall be used for the metric.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  `filter:?` (Boolean) — Filter condition that shall be applied for this aggregation.
  → Array|Double

## `median`
Calculates the median of the metric values in each bucket.
`median(metricKey [, rollup] [, default] [, rate] [, scalar] [, filter])`
  `metricKey` (—) — The metric key the aggregation function shall be applied to.
  `rollup:?` (—) — The rollup type that shall be used for the metric.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  `filter:?` (Boolean) — Filter condition that shall be applied for this aggregation.
  → Array|Double

## `min`
Calculates the minimum of the metric values in each bucket.
`min(metricKey [, rollup] [, default] [, rate] [, scalar] [, filter])`
  `metricKey` (—) — The metric key the aggregation function shall be applied to.
  `rollup:?` (—) — The rollup type that shall be used for the metric.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  `filter:?` (Boolean) — Filter condition that shall be applied for this aggregation.
  → Array|Double

## `percentRank`
Calculates the percentile rank for a given value.
`percentRank(metricKey, value [, rollup] [, default] [, rate] [, scalar] [, filter])`
  `metricKey` (—) — The metric key the aggregation function shall be applied to.
  `value` (Double|Long) — The percentile to compute, between 0 and 100.
  `rollup:?` (—) — The rollup type that shall be used for the metric.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  `filter:?` (Boolean) — Filter condition that shall be applied for this aggregation.
  → Array|Double

## `percentile`
Calculates the requested percentile of the metric values in each bucket.
`percentile(metricKey, percentile [, rollup] [, default] [, rate] [, scalar] [, filter])`
  `metricKey` (—) — The metric key the aggregation function shall be applied to.
  `percentile` (Double|Long) — The percentile to compute, between 0 and 100.  [min:0]
  `rollup:?` (—) — The rollup type that shall be used for the metric.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  `filter:?` (Boolean) — Filter condition that shall be applied for this aggregation.
  → Array|Double

## `start`
Produces an array of timestamps representing the start of the bin.
`start()`
  → Array

## `sum`
Calculates the sum of the metric values in each bucket.
`sum(metricKey [, rollup] [, default] [, rate] [, scalar] [, filter])`
  `metricKey` (—) — The metric key the aggregation function shall be applied to.
  `rollup:?` (—) — The rollup type that shall be used for the metric.
  `default:?` (Double|Long) — The default value to fill gaps.  [default:NULL]
  `rate:?` (Duration) — The rate the series values shall be scaled to.
  `scalar:?` (Boolean) — Flag to indicate that a single scalar value spanning the whole timeframe shall be calculated.  [default:FALSE]
  `filter:?` (Boolean) — Filter condition that shall be applied for this aggregation.
  → Array|Double
