# DQL Commands

Param notation: `name` = required positional · `name:` = required named · suffix `*` = variadic · suffix `?` = optional · types listed as `|`-separated names or `any` (all scalar+collection types)

## Table of Contents

[`append`](#append) · [`data`](#data) · [`dedup`](#dedup) · [`describe`](#describe) · [`expand`](#expand) · [`fetch`](#fetch) · [`fields`](#fields) · [`fieldsAdd`](#fieldsadd) · [`fieldsFlatten`](#fieldsflatten) · [`fieldsKeep`](#fieldskeep) · [`fieldsRemove`](#fieldsremove) · [`fieldsRename`](#fieldsrename) · [`fieldsSnapshot`](#fieldssnapshot) · [`fieldsSummary`](#fieldssummary) · [`filter`](#filter) · [`filterOut`](#filterout) · [`join`](#join) · [`joinNested`](#joinnested) · [`limit`](#limit) · [`load`](#load) · [`lookup`](#lookup) · [`makeTimeseries`](#maketimeseries) · [`metrics`](#metrics) · [`parse`](#parse) · [`search`](#search) · [`smartscapeEdges`](#smartscapeedges) · [`smartscapeNodes`](#smartscapenodes) · [`sort`](#sort) · [`summarize`](#summarize) · [`timeseries`](#timeseries) · [`traverse`](#traverse)

## `append`
Merges the current list of records with another list of records.
`append source`
  `source` (—) — The sub-query to append.

## `data`
Creates a static dataset to work with.
`data [json ,] record, …`
  `json:?` (String) — A JSON string that holds an object or an array of objects that will represent the data set.
  `record*` (Record) — One of the static records that should be part of the data set.
  `expression*` (any) — An expression to add to the record.  [assign:optional]

## `dedup`
Removes duplicates from a list of records.
`dedup expression, … [, sort: expression [asc|desc], …]`
  `expression*` (any) — An expression defining the how duplicate entries should be sorted (the first record by this order will be kept).
  `direction:*?` (—) — An expression defining the how duplicate entries should be sorted (the first record by this order will be kept).  [default:"ascending"]
  `filterPushThrough:?` (Boolean) — Whether the filter should be push through the dedup command.  [default:FALSE]
  `limit:?` (Long) — The maximum number of records returned by the dedup command.  [default:9223372036854775807]
  `expression*` (any) — An expression for which all different unique values should be kept.

## `describe`
Describes the schema of a given data object.
`describe dataObject`
  `dataObject` (—) — The data object to describe.

## `expand`
Expands an array into separate records.
`expand expression [, limit]`
  `expression` (Array) — A field or an array expression that should be expanded.  [assign:optional]
  `limit:?` (Long) — The maximum number of items to expand.  [default:2147483647, min:1]

## `fetch`
Loads data from the resource.
`fetch dataObject [, bucket: name, …] [, from] [, to] [, timeframe] [, samplingRatio] [, scanLimitGBytes]`
  `dataObject` (—) — The data object to fetch data for.
  `name*` (—) — A bucket (name or pattern) to retrieve data from.
  `from:?` (Duration|Long|String|Timestamp) — The start of the timeframe (if no explicit timeframe is specified). A duration is interpreted as an offset from `now()`.  [min:0]
  `to:?` (Duration|Long|String|Timestamp) — The end of the timeframe (if no explicit timeframe is specified). A duration is interpreted as an offset from `now()`.  [min:0]
  `timeframe:?` (String|Timeframe) — The desired timeframe (if not specified, global timeframe is used).
  `samplingRatio:?` (Double|Long) — The desired sampling ratio.  [min:1]
  `scanLimitGBytes:?` (Long) — The maximum number of gigabytes that shall be scanned during loading data.

## `fields`
Keeps only the specified fields.
`fields expression, …`
  `expression*` (any) — An expression that will be retained in the result list.  [assign:optional]

## `fieldsAdd`
Evaluates an expression and appends or replaces a field.
`fieldsAdd expression, …`
  `expression*` (any) — An expression, its result will be added to the record list.  [assign:optional]

## `fieldsFlatten`
Adds fields from a record to the current record list.
`fieldsFlatten expression [, prefix] [, fields: { [field, …] }] [, depth]`
  `expression` (Record) — An expression returning the record from which to add the fields.
  `prefix:?` (—) — Prefix that is applied to all fields that are going to be added.
  `field*` (any) — Field to add from the record.  [assign:optional]
  `depth:?` (Long) — Flatten nested records until the specified depth is reached.  [default:1, min:1]

## `fieldsKeep`
Keeps the fields in the result.
`fieldsKeep field, …`
  `field*` (any) — A field or fields based on a pattern to keep in the record list.

## `fieldsRemove`
Removes fields from the result.
`fieldsRemove field, …`
  `field*` (any) — A field or fields based on a pattern to remove from the record list.

## `fieldsRename`
Renames a field.
`fieldsRename field, …`
  `field*` (any) — A field to rename (needs to be fully qualified).  [assign:mandatory]

## `fieldsSnapshot`
Loads a fields snapshot for a data source.
`fieldsSnapshot dataObject [, by: { [field, …] }] [, bucket: name, …]`
  `dataObject` (—) — The data object for which to load the fields snapshot.
  `field*` (any) — A field name from the result schema to group by.
  `name*` (—) — A bucket for which to retrieve fields.

## `fieldsSummary`
Calculates the facets for the listed fields.
`fieldsSummary [topValues] [, extrapolateSamples ,] field, …`
  `topValues:?` (Long) — The number of top values for each field.  [default:20]
  `extrapolateSamples:?` (Boolean) — Whether the result should be extrapolated using the sampling rate.  [default:FALSE]
  `field*` (any) — A field identifier.

## `filter`
Reduces the number of records in a list by excluding all records not matching a specific condition.
`filter condition`
  `condition` (Boolean) — The condition all records have to fulfill.

## `filterOut`
Removes records that match a specific condition.
`filterOut condition`
  `condition` (Boolean) — The condition all records have to fulfill.

## `join`
Joins all records from the source and the sub-query as long as they fulfill the join condition.
`join joinTable [, kind] [, executionOrder ,] on: condition, … [, prefix] [, fields: { [field, …] }]`
  `joinTable` (—) — Sub-query for records with fields to add or overwrite in the input.
  `kind:?` (—) — Defines how records get joined.  [default:inner]
  `executionOrder:?` (—) — Defines which side of the join will be executed first.  [default:auto]
  `broadcast:?` (—) — Defines broadcasting strategy.  [default:enabled]
  `condition*` (—) — Records must match this condition in order to be joined.
  `prefix:?` (—) — Specifies a prefix string for all new fields.  [default:"right."]
  `field*` (any) — A field from the sub-query to add to the source.  [assign:optional]

## `joinNested`
Joins all records from the source and the sub-query as long as they fulfill the join condition. The matching results from the sub-query are added as an array of nested records.
`joinNested joinTable, alias, on: condition, … [, executionOrder] [, fields: { [field, …] }]`
  `joinTable` (—) — Sub-query for records with fields to add or overwrite in the input.  [assign:mandatory]
  `condition*` (—) — Records must match this condition in order to be joined.
  `executionOrder:?` (—) — Defines which side of the join will be executed first.  [default:auto]
  `broadcast:?` (—) — Defines broadcasting strategy.  [default:enabled]
  `field*` (any) — A field from the sub-query to add to the source.  [assign:optional]

## `limit`
Limits the number of returned records.
`limit size`
  `size` (Long) — The maximum number of records.  [min:0]

## `load`
Load command to read tabular file stored by Save command.
`load tabularFile [, offset]`
  `tabularFile` (—) — The name of the tabular file that was saved.
  `offset:?` (Long) — Number of skipped records.  [min:0]

## `lookup`
Loads an external record and adds the fields to the current record.
`lookup lookupTable [, sourceField ,] lookupField [, prefix] [, fields: { [field, …] }] [, executionOrder]`
  `lookupTable` (—) — Sub-query for records with fields to add or overwrite in the input.
  `sourceField:?` (any) — The field to use from the source for equality comparison.
  `lookupField:` (any) — The field to use from the sub-query for equality comparison.
  `prefix:?` (—) — Specifies a prefix string for all new fields.  [default:"lookup."]
  `field*` (any) — A field from the sub-query to add to the source.  [assign:optional]
  `executionOrder:?` (—) — Defines which side of the join will be executed first.  [default:auto]
  `broadcast:?` (—) — Defines broadcasting strategy.  [default:enabled]

## `makeTimeseries`
Converts the input into the time series format.
`makeTimeseries [by: { [expression, …] }] [, interval] [, bins] [, from] [, to] [, timeframe] [, time] [, spread] [, nonempty ,] aggregation, …`
  `expression*` (any) — An expression to split the series by.  [assign:optional]
  `interval:?` (Duration) — An expression that provides the duration of a bins in the series.
  `bins:?` (Long) — An positive non-zero long integer number that defines the number of bins that shall be created within the series timeframe.  [default:120, min:0]
  `from:?` (Duration|Timestamp) — The global timeframe start for the series for which values should be considered.
  `to:?` (Duration|Timestamp) — The global timeframe end for the series for which values should be considered.
  `timeframe:?` (Timeframe) — The global timeframe end for the series for which values should be considered.
  `time:?` (Timestamp) — A timestamp expression that provides the timestamp for the bucket calculation of the values in the series.
  `spread:?` (Timeframe) — A timeframe expression that provides the timeframe for the bucket calculation of the values in the series.
  `nonempty:?` (Boolean) — Produces empty series when there is no data.  [default:FALSE]
  `aggregation*` (—) — The series that shall be calculated.  [assign:optional]
  `default:*?` (Double|Long) — The default value in the series bin, if no value is present.
  `rate:*?` (Duration) — The rate the resulting series values shall be scaled to.

## `metrics`
Loads metric data.
`metrics [[bucket: name, …] [, from] [, to] [, timeframe]]`
  `name*` (—) — A bucket (name or pattern) to retrieve data from.
  `from:?` (Duration|String|Timestamp) — The global timeframe start for retrieving metrics.
  `to:?` (Duration|String|Timestamp) — The global timeframe end for retrieving metrics.
  `timeframe:?` (String|Timeframe) — The global timeframe for retrieving metrics.

## `parse`
Parses a record field and puts the result(s) into one or more fields as specified in the pattern.
`parse expression, pattern [, preserveFieldsOnFailure] [, parsingPrerequisite]`
  `expression` (String) — A field or string expression to parse.
  `pattern` (—) — The parse pattern.
  `preserveFieldsOnFailure:?` (Boolean) — Determines if fields values should be preserved if parsing fails.  [default:FALSE]
  `parsingPrerequisite:?` (Boolean) — Determines if record should be parsed.  [default:TRUE]
  `baseTime:?` (Timestamp) — A timestamp expression providing the base time for date/time parsing.

## `search`
Reduces the number of records in a list by excluding all records where the search condition doesn't apply.
`search condition`
  `condition` (—) — The condition all records have to fulfill.
  `caseSensitive:?` (Boolean) — Whether search patterns should be considered as case-sensitive (default: false).  [default:FALSE]
  `scope:?` (—) — Where search patterns should be searched.  [default:"all"]
  `field*` (any) — A field on which to apply search patterns.
  `field*` (any) — A field to be excluded from the search for search patterns.

## `smartscapeEdges`
Returns the edges of a smartscape graph.
`smartscapeEdges [from] [, to] [, timeframe ,] type, …`
  `from:?` (Duration|String|Timestamp) — The global timeframe start for retrieving the smartscape edges.
  `to:?` (Duration|String|Timestamp) — The global timeframe end for retrieving the smartscape edges.
  `timeframe:?` (String|Timeframe) — The global timeframe for retrieving the smartscape edges.
  `type*` (—) — The type or type pattern of the smartscape edges.

## `smartscapeNodes`
Returns the nodes of a smartscape graph.
`smartscapeNodes [from] [, to] [, timeframe ,] type, …`
  `from:?` (Duration|String|Timestamp) — The global timeframe start for retrieving the smartscape edges.
  `to:?` (Duration|String|Timestamp) — The global timeframe end for retrieving the smartscape edges.
  `timeframe:?` (String|Timeframe) — The global timeframe for retrieving the smartscape edges.
  `type*` (—) — The type or type pattern of the smartscape nodes.

## `sort`
Sorts the records.
`sort expression [asc|desc], …`
  `expression*` (any) — An expression defining the sort order.
  `direction:*?` (—) — The direction of the sorting.  [default:"ascending"]

## `summarize`
Groups together records that have the same values for a given field and aggregates them.
`summarize aggregation, … [, by: { [expression, …] }]`
  `expression*` (any) — An expression to group by.  [assign:optional]
  `aggregation*` (any) — An aggregation function (min, max, avg, ...).  [assign:optional]

## `timeseries`
Reads metrics in the time series format from the data source.
`timeseries [bucket: name, …] [, from] [, to] [, timeframe] [, by: { [expression, …] }] [, filter] [, interval] [, bins] [, shift] [, nonempty] [, union ,] metric, …`
  `name*` (—) — A bucket (name or pattern) to retrieve data from.
  `from:?` (Duration|String|Timestamp) — The global timeframe start for the series for which values should be considered.
  `to:?` (Duration|String|Timestamp) — The global timeframe end for the series for which values should be considered.
  `timeframe:?` (String|Timeframe) — The global timeframe for the series for which values should be considered.
  `expression*` (any) — An expression to split the series by.  [assign:optional]
  `filter:?` (Boolean) — An additional filter condition that shall be applied on the source records before time-/space-aggregation.
  `interval:?` (Duration) — A suggested interval for the series.
  `bins:?` (Long) — A suggested number of bins in the series.  [default:120, min:0]
  `shift:?` (Duration) — Shifts the effective timeframe by the provided duration.
  `nonempty:?` (Boolean) — Produces empty series when there is no data.  [default:FALSE]
  `union:?` (Boolean) — Whether the results will be combined as union if multiple metric keys are specified.  [default:FALSE]
  `metric*` (—) — The metric that shall be calculated.  [assign:optional]
  `rollup:*?` (—) — The rollup type that shall be used for the metric.
  `default:*?` (Double|Long) — The default value to fill gaps.
  `rate:*?` (Duration) — The rate the resulting series values shall be scaled to.

## `traverse`
Switches from the current list of records to a different one.
`traverse edgeType, …, targetType, … [, direction] [, fieldsKeep: { [field, …] }] [, nodeId]`
  `edgeType*` (—) — The type of the edge to traverse.
  `targetType*` (—) — The type of the target nodes.
  `direction:?` (—) — The traversal direction.  [default:"forward"]
  `field*` (any) — A field or field pattern to keep in the traversal history.
  `nodeId:?` (SmartscapeId) — The field that contains the id of the node in the incoming records.  [default:id]
