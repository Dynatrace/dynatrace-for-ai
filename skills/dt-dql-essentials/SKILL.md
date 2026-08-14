---
name: dt-dql-essentials
description: "Core DQL syntax, pitfalls, query patterns, and query optimization. Load to write, build, fix, or OPTIMIZE a DQL query — prevents syntax errors and makes queries faster, more efficient, and cheaper (less data scanned = lower query consumption/cost per run). Covers fetch commands, data models, field namespaces, time alignment, entity/smartscape patterns, metric discovery, and performance/cost optimization (filter early, bucket filters, short time ranges, field selection, sampling, cardinality). Trigger: \"write/build/fix a DQL query\", \"DQL syntax\", \"query logs/spans/metrics\", \"create a timeseries\", \"optimize my DQL\", \"make my query faster/cheaper\", \"reduce DQL cost/consumption/scanned data\", \"keep DQL cost under control\". Do NOT use to explain an existing query or answer product questions. For MONITORING a tenant's ACTUAL query consumption/billing (how much queries cost, who scanned most, cost trends) use dt-platform-costs — this tunes the query text, not billing data."
license: Apache-2.0
---

# DQL Essentials Skill

DQL is a pipeline-based query language. Queries chain commands with `|` to filter, transform, and aggregate data. DQL has unique syntax that differs from SQL — load this skill before writing any DQL query.

______________________________________________________________________

## When to Load References

Before working on specific tasks, load the relevant reference:

| Task                                                                          | Required Reading                                                                             |
| ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Field names, namespaces, data models, stability levels, query patterns        | [references/semantic-dictionary.md](references/semantic-dictionary.md)                       |
| Query optimization — make a query faster / more efficient / cheaper, reduce consumption & scanned data (filter early, bucket filters, time ranges, field selection, sampling, cardinality) | [references/optimization.md](references/optimization.md)                                     |
| Smartscape topology navigation for discovering relationships between entities | [references/smartscape-topology-navigation.md](references/smartscape-topology-navigation.md) |
| `summarize` and `makeTimeseries` patterns (bucketing, calendar months)        | [references/summarization.md](references/summarization.md)                                   |
| Array and timeseries manipulation (`arrayFilter`, `collectArray`, iterative)  | [references/iterative-expressions.md](references/iterative-expressions.md)                   |
| Conditional logic (`if/else` chains), `coalesce`, string/date helpers         | [references/useful-expressions.md](references/useful-expressions.md)                         |
| `in` operator (subquery), full `@` time alignment unit table                  | [references/operators.md](references/operators.md)                                           |
| `matchesValue`, `matchesPhrase`, `matchesPattern`, `in()` — string pattern matching, regex, array matching, wildcards, case sensitivity | [references/string-matching.md](references/string-matching.md)                               |

______________________________________________________________________

## DQL Reference Index

Use this index to route from a function group (e.g. time functions, conversions) to its detailed spec, or from a function name to its spec file.

| Description | Items |
|-------------|-------|
| [Data Types](references/dql/dql-data-types.md) | `array`, `binary`, `boolean`, `double`, `duration`, `long`, `record`, `string`, `timeframe`, `timestamp`, `uid` |
| [Parameter Value Types](references/dql/dql-parameter-value-types.md) | `bucket`, `dataObject`, `dplPattern`, `entityAttribute`, `entitySelector`, `entityType`, `enum`, `executionBlock`, `expressionTimeseriesAggregation`, `expressionWithConstantValue`, `expressionWithFieldAccess`, `fieldPattern`, `filePattern`, `identifierForAnyField`, `identifierForEdgeType`, `identifierForFieldOnRootLevel`, `identifierForNodeType`, `joinCondition`, `jsonPath`, `metricKey`, `metricTimeseriesAggregation`, `namelessDplPattern`, `nonEmptyExecutionBlock`, `prefix`, `primitiveValue`, `simpleIdentifier`, `tabularFileExisting`, `tabularFileNew`, `url` |
| [Commands](references/dql/dql-commands.md) | `append`, `data`, `dedup`, `describe`, `expand`, `fetch`, `fields`, `fieldsAdd`, `fieldsFlatten`, `fieldsKeep`, `fieldsRemove`, `fieldsRename`, `fieldsSnapshot`, `fieldsSummary`, `filter`, `filterOut`, `join`, `joinNested`, `limit`, `load`, `lookup`, `makeTimeseries`, `metrics`, `parse`, `search`, `smartscapeEdges`, `smartscapeNodes`, `sort`, `summarize`, `timeseries`, `traverse` |
| [Functions — Aggregation](references/dql/dql-functions-aggregation.md) | `avg`, `collectArray`, `collectDistinct`, `correlation`, `count`, `countDistinct`, `countDistinctApprox`, `countDistinctExact`, `countIf`, `max`, `median`, `min`, `percentRank`, `percentile`, `percentileFromSamples`, `percentiles`, `stddev`, `sum`, `takeAny`, `takeFirst`, `takeLast`, `takeMax`, `takeMin`, `variance` |
| [Functions — Array](references/dql/dql-functions-array.md) | `arrayAvg`, `arrayConcat`, `arrayCumulativeSum`, `arrayDelta`, `arrayDiff`, `arrayDistinct`, `arrayFirst`, `arrayFlatten`, `arrayIndexOf`, `arrayLast`, `arrayLastIndexOf`, `arrayMax`, `arrayMedian`, `arrayMin`, `arrayMovingAvg`, `arrayMovingMax`, `arrayMovingMin`, `arrayMovingSum`, `arrayPercentile`, `arrayRemoveNulls`, `arrayReverse`, `arraySize`, `arraySlice`, `arraySort`, `arraySum`, `arrayToString`, `vectorCosineDistance`, `vectorInnerProductDistance`, `vectorL1Distance`, `vectorL2Distance` |
| [Functions — Bitwise](references/dql/dql-functions-bitwise.md) | `bitwiseAnd`, `bitwiseCountOnes`, `bitwiseNot`, `bitwiseOr`, `bitwiseShiftLeft`, `bitwiseShiftRight`, `bitwiseXor` |
| [Functions — Boolean](references/dql/dql-functions-boolean.md) | `exists`, `in`, `isFalseOrNull`, `isNotNull`, `isNull`, `isTrueOrNull`, `isUid128`, `isUid64`, `isUuid` |
| [Functions — Cast](references/dql/dql-functions-cast.md) | `asArray`, `asBinary`, `asBoolean`, `asDouble`, `asDuration`, `asIp`, `asLong`, `asNumber`, `asRecord`, `asSmartscapeId`, `asString`, `asTimeframe`, `asTimestamp`, `asUid` |
| [Functions — Constant](references/dql/dql-functions-constant.md) | `e`, `pi` |
| [Functions — Conversion](references/dql/dql-functions-conversion.md) | `toArray`, `toBoolean`, `toDouble`, `toDuration`, `toIp`, `toLong`, `toSmartscapeId`, `toString`, `toTimeframe`, `toTimestamp`, `toUid`, `toVariant` |
| [Functions — Create](references/dql/dql-functions-create.md) | `array`, `duration`, `ip`, `record`, `smartscapeId`, `timeframe`, `timestamp`, `timestampFromUnixMillis`, `timestampFromUnixNanos`, `timestampFromUnixSeconds`, `uid128`, `uid64`, `uuid` |
| [Functions — Cryptographic](references/dql/dql-functions-cryptographic.md) | `hashCrc32`, `hashMd5`, `hashSha1`, `hashSha256`, `hashSha512`, `hashXxHash32`, `hashXxHash64` |
| [Functions — Entities](references/dql/dql-functions-entities.md) | `classicEntitySelector`, `entityAttr`, `entityName` |
| [Functions — Time series aggregation for expressions](references/dql/dql-functions-expression-timeseries.md) | `avg`, `count`, `countDistinct`, `countDistinctApprox`, `countDistinctExact`, `countIf`, `end`, `max`, `median`, `min`, `percentRank`, `percentile`, `percentileFromSamples`, `start`, `sum` |
| [Functions — Flow](references/dql/dql-functions-flow.md) | `coalesce`, `if` |
| [Functions — General](references/dql/dql-functions-general.md) | `jsonField`, `jsonPath`, `lookup`, `parse`, `parseAll`, `type` |
| [Functions — Get](references/dql/dql-functions-get.md) | `arrayElement`, `getEnd`, `getHighBits`, `getLowBits`, `getStart` |
| [Functions — Iterative](references/dql/dql-functions-iterative.md) | `iAny`, `iCollectArray`, `iIndex` |
| [Functions — Mathematical](references/dql/dql-functions-mathematical.md) | `abs`, `acos`, `asin`, `atan`, `atan2`, `bin`, `cbrt`, `ceil`, `cos`, `cosh`, `degreeToRadian`, `exp`, `floor`, `hexStringToNumber`, `hypotenuse`, `log`, `log10`, `log1p`, `numberToHexString`, `power`, `radianToDegree`, `random`, `range`, `round`, `signum`, `sin`, `sinh`, `sqrt`, `tan`, `tanh` |
| [Functions — Network](references/dql/dql-functions-network.md) | `ipIn`, `ipIsLinkLocal`, `ipIsLoopback`, `ipIsPrivate`, `ipIsPublic`, `ipMask`, `isIp`, `isIpV4`, `isIpV6` |
| [Functions — Smartscape](references/dql/dql-functions-smartscape.md) | `getNodeField`, `getNodeName` |
| [Functions — String](references/dql/dql-functions-string.md) | `concat`, `contains`, `decodeBase16ToBinary`, `decodeBase16ToString`, `decodeBase64ToBinary`, `decodeBase64ToString`, `decodeUrl`, `encodeBase16`, `encodeBase64`, `encodeUrl`, `endsWith`, `escape`, `getCharacter`, `indexOf`, `lastIndexOf`, `levenshteinDistance`, `like`, `lower`, `matchesPattern`, `matchesPhrase`, `matchesRegex`, `matchesValue`, `punctuation`, `replacePattern`, `replaceString`, `splitByPattern`, `splitString`, `startsWith`, `stringLength`, `substring`, `trim`, `unescape`, `unescapeHtml`, `upper` |
| [Functions — Time](references/dql/dql-functions-time.md) | `formatTimestamp`, `getDayOfMonth`, `getDayOfWeek`, `getDayOfYear`, `getHour`, `getMinute`, `getMonth`, `getSecond`, `getWeekOfYear`, `getYear`, `now`, `unixMillisFromTimestamp`, `unixNanosFromTimestamp`, `unixSecondsFromTimestamp` |
| [Functions — Time series aggregation for metrics](references/dql/dql-functions-timeseries.md) | `avg`, `count`, `countDistinct`, `end`, `max`, `median`, `min`, `percentRank`, `percentile`, `start`, `sum` |

______________________________________________________________________

## Syntax Pitfalls

| ❌ Wrong | ✅ Right | Issue |
| --- | --- | --- |
| `filter field in ["a", "b"]` | `filter in(field, {"a", "b"})` | `[` and `]` wrap sub-queries in DQL but do not wrap **static** array literals. Use `{}` or `array()` for static values. |
| `filter: { in(field, [sub-query]) }` (e.g. in `timeseries filter:`) | `filter: { field in [sub-query] }` | `in()` does not accept execution blocks as arguments. When the right-hand side is a sub-query (execution block), use the `in` operator: `field in [execution block]`. |
| `by: severity, status` | `by: {severity, status}` | List of fields must be grouped by curly braces in `by:` clauses (`summarize`, `makeTimeseries`, etc.). |
| `contains(toLowercase(field), "err")` | `contains(field, "err", false)` | Don't wrap in `lower()` for case-insensitive matching. `contains()` has a built-in third positional `caseSensitive` parameter (default `true`). |
| `filter name == "*serv*9*"` | `filter matchesValue(name, "*serv*") and matchesValue(name, "*9*")` | `==` does not support wildcards. `matchesValue()` supports `*` wildcards but only at the beginning and/or end of the pattern—split mid-string wildcard intent into multiple calls combined with `and`. |
| `matchesValue(field, "prod")` on string field | `contains(field, "prod")` | Without wildcards, `matchesValue()` performs an exact (case-insensitive) match — it will not find `"production"`. Use `contains()` for substring matching (or `matchesValue(field, "*prod*")` for wildcard matching). |
| `iAny(matchesValue(arr[], "x") OR matchesValue(arr[], "y"))` | `matchesValue(arr, {"x", "y"})` | `matchesValue` accepts an array field in the first param and an array literal `{}` in the second — no `iAny` or `[]` needed. The same applies when consolidating multiple `contains(f, x) OR contains(f, y)` on the same field: use `matchesValue(f, {"*x*", "*y*"})`. |
| `iAny(matchesPhrase(arr[], "phrase"))` | `matchesPhrase(arr, "phrase")` | `matchesPhrase` iterates array fields natively — drop `iAny(` and `[]`. Note: the **second** parameter must be a static string; `matchesPhrase(f, array("a","b")[])` is a runtime error. |
| `contains(field, "pip")` on a short or common token | `matchesPhrase(field, "pip")` | `contains` is a pure substring match — `"pip"` also fires on `"pipenv"`, `"gripping"`. `matchesPhrase` tokenizes the string and matches whole words only, giving fewer false positives. |
| `iAny(in(lower(arr[]), array("a", "b")))` | `matchesValue(arr, {"a", "b"}, caseSensitive: false)` | `matchesValue` is case-insensitive by default — no `lower()`, `in()`, or `iAny` wrapper needed. `caseSensitive: false` shown explicitly here only to mirror the intent of the `lower()` it replaces. |
| `iAny(f1[] == "a" AND f2[] == "b")` iterating two separate arrays | `in(f1, "a") AND in(f2, "b")` | Multi-array `iAny` is **pairwise**, not a cross-product: element `i` of `f1[]` is tested against element `i` of `f2[]`. If the arrays differ in length the result is `null`. Use independent `in()` checks instead. See [references/iterative-expressions.md](references/iterative-expressions.md). |
| `toLowercase(field)` | `lower(field)` | The function is `lower()`, not `toLowercase()`. Only type-casting functions use the `to` prefix (`toString()`, `toLong()`, etc.). |
| `arrayAvg(field[])` or `arraySum(field[])` | `arrayAvg(field)` or `field[]` | `field[]` = element-wise iterative expression (array→array); `arrayAvg(field)` = collapse to scalar (array→single value). Never mix both — `arrayAvg(field[])` is semantically wrong. |
| `my_field` after `lookup` or `join` | `lookup.my_field` / `right.my_field` | `lookup` prefixes added fields with `lookup.` by default (configurable via `prefix:`). `join` prefixes right-side fields with `right.`. |
| `substring(field, 0, 200)` | `substring(field, from: 0, to: 200)` | The first parameter (expression) is positional, but `from:` and `to:` are named optional parameters and must include their names. |
| `filter host = "A"` | `filter host == "A"` | DQL uses `==` for equality comparison, not `=`. Single `=` is assignment (e.g., in `fieldsAdd`, summarize aliases). |
| `fetch logs, from: toTimestamp('2026-01-01')` | `fetch logs, from: -24h` | `from:` / `to:` accept duration literals (e.g., `-24h`, `-7d`) or `now()` expressions — not `toTimestamp()`. For absolute ranges use `timeframe: "start/end"` (ISO 8601). |
| `filter log.level == "ERROR"` | `filter loglevel == "ERROR"` | Log severity field is `loglevel` (no dot) — `log.level` does not exist. |
| `sort count() desc` | `` sort `count()` desc `` | Fields with special characters (like parentheses) must be wrapped in backticks. |
| `length(field)` | `stringLength(field)` | DQL string length function is `stringLength` — there is no `length()`. |
| `metrics dt.host.cpu.usage` | `timeseries avg(dt.host.cpu.usage)` | `metrics` loads metric metadata, not values — use `timeseries` for data. |
| `join [...], on:{left.a.b == right.a.b}` | `` join [...], on:{left[`a.b`] == right[`a.b`]} `` | Dotted field names in join/lookup conditions require bracket notation with backticks. |
| `fieldsSummary` (no arguments) | `fieldsSummary field1, field2` | `fieldsSummary` requires at least one field parameter. |
| `timeseries` with `percentile`/`median`/`percentRank` — no results | Add `rollup: avg` (or `min`/`max`/`sum`) to the `timeseries` command | These three functions **require `rollup:`** on gauge/count metrics — without it the query silently returns empty. |
| `summarize p95 = percentile(duration, 95, rollup: avg)` | `summarize p95 = percentile(duration, 95)` | `rollup:` is a **`timeseries`-only** parameter. The same-named aggregations in `summarize` over logs/spans/events reject it with `UNKNOWN_PARAMETER_DEFINED`. Only add `rollup:` when aggregating a *metric* inside `timeseries`. |
| `filter array.contains(field, "v")` or `arrayContains(field, "v")` | `filter in(field, {"v"})` | Neither function exists in DQL — both are hallucinated from Python/Java/SQL. `in()` already matches **array-typed** fields natively (e.g. `k8s.namespace.name` on `dt.davis.problems`): it returns true if any element of the needle matches any haystack element. See [references/iterative-expressions.md](references/iterative-expressions.md). |
| `filter k8s.namespace.name == "ns"` where the field is array-typed | `filter in(k8s.namespace.name, {"ns"})` | `==` against an array-typed field matches **nothing** — it returns zero rows with no error, which reads as "no data" rather than a mistake. `k8s.*` fields are arrays on `dt.davis.problems`. Use `in()` for exact membership, or `matchesValue(field, {...})`. |
| `parseJson(field)` or `extractJsonField(field, jsonPath: "$.x")` | `parse field, "JSON:parsed"` then `parsed[x]` | Neither function exists. JSON embedded in a string field is unpacked with the `parse` command and the `JSON` DPL matcher, then accessed with bracket notation. |
| `filter hour(timestamp) == 4` / `minute(timestamp)` | `filter getHour(timestamp) == 4` / `getMinute(timestamp)` | There are no `hour()`/`minute()` functions. The `get*` family returns **numbers**, so numeric comparison and ranges work. Do not substitute `formatTimestamp(timestamp, format: "HH")` — that returns a *string*, so `== 4` silently matches nothing. |
| `fields fromRelationships, toRelationships, containerImageTag` on `dt.entity.*` | `describe dt.entity.<type>` first, then select real fields | Classic entity objects do **not** expose the Entities REST API's attribute names. Field names must be discovered with `describe <dataObject>`, not guessed from API payloads. |
| `by: {bin(timestamp, 1h)}` then `` sort `bin(timestamp,1h)` `` | `by: {t = bin(timestamp, 1h)}` then `sort t` | DQL normalizes the auto-generated group-key name to `bin(timestamp, 1h)` — with a space after the comma, regardless of how the expression was written. A backticked reference that omits the space raises `FIELD_DOES_NOT_EXIST`. Always alias group keys. |
| `fetch spans \| ... by: {bin(timestamp, 1h)}` | `fetch spans \| ... by: {t = bin(start_time, 1h)}` | `spans` has no `timestamp` field — its time fields are `start_time` and `end_time`. Referencing `timestamp` either errors or yields nulls depending on position. |
| `` lookup [...], fields: {`dotted.name`} `` | `lookup [...], fields: {dotted.name}` | Do not backtick field names inside the `fields:` parameter of `lookup` — causes PARSE_ERROR. |
| `data record(key: "val")` | `data record(key = "val")` | `record()` uses `=` for named fields, not `:` — `:` is for command parameters like `rollup:`. |
| `getNodeField(dt.smartscape.host, "tags")["tag.key"]` | `getNodeField(dt.smartscape.host, "tags")[tag.key]` | In this tag-map access pattern, bracket keys must use unquoted identifier syntax; quoted keys cause a parse error. |
| `by: {dt.entity.host}` or `dt.entity.*` | `by: {dt.smartscape.host}` or `dt.smartscape.*` | `dt.entity.*` is **deprecated** — always use `dt.smartscape.*` in new queries. |

______________________________________________________________________

## Fetch Command → Data Model

DQL queries start with `fetch <data_object>` or `timeseries`. There is **no `fetch dt.metric`** — metrics use `timeseries`.

| Fetch Command | Data Model | Key Fields / Notes |
|---------------|------------|--------------------|
| `fetch spans` | Distributed tracing | `span.*`, `service.*`, `http.*`, `db.*`, `code.*`, `exception.*` |
| `fetch logs` | Log events | `log.*`, `k8s.*`, `host.*` — message body is `content`, severity is `loglevel` (NOT `log.level`) |
| `fetch events` | DAVIS / infra events | `event.*`, `dt.smartscape.*` |
| `fetch bizevents` | Business events | `event.*`, custom fields |
| `fetch security.events` | Security events | `vulnerability.*`, `event.*` |
| `fetch user.sessions` | RUM sessions | `dt.rum.*`, `browser.*`, `geo.*` |
| `fetch user.events` | RUM individual events | page views, clicks, requests, errors |
| `fetch user.replays` | Session replay recordings | |
| `fetch application.snapshots` | Application snapshots | |
| `fetch dt.davis.events` | Davis-detected events | |
| `fetch dt.davis.problems` | Davis-detected problems | |
| `timeseries avg(metric.key)` | Metrics | NOT `fetch` — hyphenated keys need backticks: `` timeseries sum(`my.metric-name`) `` |
| `smartscapeNodes "HOST"` | Topology | NOT `fetch` — types: `HOST`, `SERVICE`, `K8S_CLUSTER`, etc. |

`dt.entity.*` is deprecated — use `dt.smartscape.*` and `smartscapeNodes` for new queries.

Discover all available data objects: `fetch dt.system.data_objects | fields name, display_name, type`

→ [references/semantic-dictionary.md](references/semantic-dictionary.md) for full field namespaces

______________________________________________________________________

## `samplingRatio` Parameter

`fetch` supports a `samplingRatio:` parameter to reduce the volume of data read — useful for improving query performance on large datasets.

```dql
fetch spans, samplingRatio:100   // reads ~1% of data
```

**Allowed values:** depend on the concrete data object and range from `1`, `10`, `100`, `1000`, `10000` to `100000`, the highest level only available for `logs` and `spans`.


Sampling is **hierarchical** for `spans`, `user.events` and `user.sessions`: a record included at a higher ratio (e.g. `100`) is guaranteed to also appear at lower ratios (e.g. `10`, `1`), but not vice versa. This means results at different ratios are  subsets of each other. All other non-metric data objects are sampled independently per record, so results at different ratios are not subsets.

The actual ratio applied is accessible via the `dt.system.sampling_ratio` field. Use it to extrapolate sampled counts back to true totals:

```dql
fetch logs, samplingRatio:10
| summarize count_extrapolated = sum(dt.system.sampling_ratio)
```

______________________________________________________________________

## Metric Discovery

To search for available metrics by keyword, use the command `metrics`:

```dql
metrics from: now() - 1h
| filter contains(metric.key, "replay")
| summarize count(), by: {metric.key}
| sort `count()` desc
```

There is **no `fetch dt.metric`** or `fetch dt.metrics` or `fetch dt.system.metrics` — those data objects do not exist.

______________________________________________________________________

## Timeseries Aggregation Functions

The `timeseries` command supports only these aggregation functions:

| Function | Description |
|----------|-------------|
| `sum` | Sum of metric data points per time slot |
| `avg` | Average of metric data points per time slot |
| `min` | Minimum of metric data points per time slot |
| `max` | Maximum of metric data points per time slot |
| `count` | Count of metric data points per time slot |
| `percentile(metric, N)` | Nth percentile per time slot. **Requires `rollup:`** — see below. |
| `median(metric)` | 50th percentile per time slot (= `percentile(metric, 50)`). **Requires `rollup:`**. |
| `percentRank(metric, value)` | Percentile rank of a value per time slot. **Requires `rollup:`**. |
| `countDistinct(metric)` | Approximate distinct count per time slot (cardinality metrics only; does NOT accept `rollup:`). |

Helpers (use alongside an aggregation): `start()`, `end()`.

**Not supported by `timeseries`:** `countIf`, `collectArray`, `stddev`, `variance`, `takeAny`, `takeFirst`, `takeLast` — use `summarize` or `makeTimeseries`.

### The `rollup:` parameter

Metrics are pre-aggregated at ingest time. `rollup:` controls how raw data points are combined per time slot. Required for `percentile`, `median`, `percentRank` — without it the query silently returns no results. `avg`/`min`/`max`/`sum`/`count` work without `rollup:`.

`rollup:` is a **`timeseries`-only** parameter — it belongs to metric aggregations and nothing else. The identically-named aggregation functions available in `summarize` over event data (logs, spans, events) do **not** accept it: `summarize p95 = percentile(duration, 95, rollup: avg)` fails with `UNKNOWN_PARAMETER_DEFINED`. In `summarize`, use `percentile(field, N)` with no `rollup:`.

Single aggregation — `rollup:` at command level. Multiple aggregations in `{}` — `rollup:` must go **inside each function call** (command-level `rollup:` causes `UNKNOWN_PARAMETER_DEFINED`):

```dql
timeseries p90 = percentile(dt.process.handles.file_descriptors_percent_used, 90), rollup: avg
```

```dql
timeseries {
  p90 = percentile(dt.process.handles.file_descriptors_percent_used, 90, rollup: avg),
  med = median(dt.process.handles.file_descriptors_percent_used, rollup: avg),
  avg_val = avg(dt.process.handles.file_descriptors_percent_used)
}, by: {dt.smartscape.host}
```

Values: `avg` (gauges), `min`, `max`, `sum` (counters), `total`.

### Timeseries-to-scalar conversion

There are two ways to collapse a timeseries to a scalar. Prefer the `scalar:true` parameter when you only need the single aggregated value — it is more efficient because no array is materialized. Fall back to array functions when you need both the full series and a derived scalar in the same query.

**Preferred: `scalar:true` on the aggregation function**

Pass `scalar:true` to any timeseries aggregation function. The result field contains a single value instead of an array, and no intermediate array is allocated:

```dql
timeseries avg_cpu = avg(dt.host.cpu.usage, scalar:true), by:{dt.smartscape.host}
```

```dql
timeseries {
  avg_cpu = avg(dt.host.cpu.usage, scalar:true),
  max_cpu = max(dt.host.cpu.usage, scalar:true)
}, by:{dt.smartscape.host}
```

**Fallback: array functions in `fieldsAdd`**

When you need the full time series array alongside a derived scalar, use array functions in a subsequent `| fieldsAdd`:

| Function | Description |
|----------|-------------|
| `arrayAvg(arr)` | Average of all values in the array |
| `arraySum(arr)` | Sum of all values |
| `arrayMin(arr)` | Minimum value |
| `arrayMax(arr)` | Maximum value |
| `arrayMedian(arr)` | Median value |
| `arrayPercentile(arr, N)` | Nth percentile (0–100) |
| `arrayLast(arr)` | Last non-null value (latest data point) |
| `arrayFirst(arr)` | First non-null value (earliest data point) |

```dql
timeseries cpu = avg(dt.host.cpu.usage), by:{dt.smartscape.host}
| fieldsAdd avg_cpu = arrayAvg(cpu), max_cpu = arrayMax(cpu)
```

______________________________________________________________________

## Time Alignment (@-operator)

The `@` operator aligns timestamps to a boundary — agents often get this wrong.

| Expression   | Meaning                                                     |
| ------------ | ----------------------------------------------------------- |
| `now()@h`    | Current time, aligned to the hour boundary                  |
| `now()@d`    | Midnight today                                              |
| `now()@w1`   | Monday this week                                            |
| `now()-2h@h` | 2 hours ago, aligned to the hour (offset first, then align) |

**Rules:**

- Order: offset before alignment — `now()-2h@h`, not `now()@h-2h`
- No space between `@` and the unit — `now()@h` not `now() @h`
- `m` = minutes, `M` = months — do not confuse them

→ [references/dql/dql-functions-timeseries.md](references/dql/dql-functions-timeseries.md) for the full list of `timeseries` aggregations and `rollup:` rules
→ [references/dql/dql-functions-array.md](references/dql/dql-functions-array.md) for `arrayAvg` / `arrayMax` / `arrayPercentile` / … spec

______________________________________________________________________

## Entity & Smartscape Patterns

Entity fields are scoped per type — `entity.id` does not exist. Use `smartscapeNodes` for topology queries.

| Entity      | ID field in data             | `smartscapeNodes` type |
| ----------- | ---------------------------- | ---------------------- |
| Host        | `dt.smartscape.host`         | `"HOST"`               |
| Service     | `dt.smartscape.service`      | `"SERVICE"`            |
| Process     | `dt.smartscape.process`      | `"PROCESS"`            |
| K8s cluster | `dt.smartscape.k8s_cluster`  | `"K8S_CLUSTER"`        |

**These four are examples, not the inventory.** A real environment carries well over a hundred node
types, and the set is not closed — OpenPipeline can extract user-defined `CUSTOM_*` / `EXT_*` nodes.
Discover them rather than working from a list:

```dql
smartscapeNodes "*" | dedup type | fields type
```

Use `toSmartscapeId()` for ID conversion from strings (required!). Nodes also carry `id_classic`, the
classic entity ID, which is the bridge when migrating off `dt.entity.*`.

→ [references/smartscape-topology-navigation.md](references/smartscape-topology-navigation.md)

______________________________________________________________________

## makeTimeseries Command

`makeTimeseries` builds a time-bucketed series from event data (logs, spans, bizevents). Unlike `timeseries` (which queries pre-ingested metrics), `makeTimeseries` aggregates data in a pipeline.

**Do not pipe `timeseries` directly into `makeTimeseries`** — it fails with `INVALID_IMPLICIT_TIME_DEFAULT`. To re-aggregate metric data, use `start()` + expand (see [references/summarization.md](references/summarization.md)).

```dql
fetch logs
| makeTimeseries
    total = count(),
    errors = countIf(loglevel == "ERROR"),
    interval: 5m,
    by: {k8s.cluster.name}
| fieldsAdd error_rate = errors[] * 100.0 / total[]
```

Key parameters: `interval:`, `by:{}`, `from:`/`to:`, `bins:`, `time:` (timestamp field), `spread:` (for `count`/`countIf` only), `nonempty:`.

→ [references/summarization.md](references/summarization.md) for full `makeTimeseries` patterns and `summarize` bucketing
→ [references/iterative-expressions.md](references/iterative-expressions.md) for timeseries array manipulation

______________________________________________________________________

## String Matching Functions

DQL has four main functions for string and array pattern matching. See [references/string-matching.md](references/string-matching.md) for the full guide and quick-reference table.

- **`matchesValue(field, {"pattern*", "*other*"})`** — wildcard matching (`*` at start/end). Accepts an array field in the first param and an array literal `{}` in the second — no `iAny` or `[]` needed. Case-insensitive by default (`caseSensitive: true` to enforce case-sensitive matching). Replaces `contains()` + `iAny` chains and `lower()` workarounds.
- **`matchesPhrase(field, "token")`** — tokenizes the string and matches whole words, unlike `contains()` which is a bare substring match. First param accepts an array field natively; second param must be a **static string** (array unwrapping causes a runtime error).
- **`in(field, array("a", "b"))`** — set membership. Both params accept arrays, making it an overlap/intersection check.

______________________________________________________________________

## Chained Lookup Pattern


Each `lookup` command without a `fields` parameter **removes all existing fields starting with the prefix (default: `lookup.`)** before adding new ones. When chaining multiple lookups, use `fields` parameter or custom prefixes to preserve the result:

**Option 1 (default)**: the desired fields are known.
```dql
fetch bizevents
// Step 1: First lookup — enrich orders with product info
| lookup [fetch bizevents
    | filter event.type == "product_catalog"
    | fields product_id, category],
  sourceField: product_id, lookupField: product_id, fields: {product_id, product_category = category}

// Step 2: Second lookup — specify fields with a different name
| lookup [fetch bizevents
    | filter event.type == "warehouse_stock"
    | fields category, warehouse_region],
  sourceField: product_category, lookupField: category, fields: {warehouse_region, warehouse_category = category}

```
All 4 lookup fields product_id, product_category, warehouse_region, and warehouse_category are available.
Without the `fields:{...}` parameter, the fields would be prefixed with `lookup.` and the second lookup command would delete the fields added by the first lookup.

**Option 2**: keep all fields from the lookup.
```dql
fetch bizevents
// Step 1: First lookup — enrich orders with product info
| lookup [fetch bizevents
    | filter event.type == "product_catalog"
    | fields product_id, category],
  sourceField: product_id, lookupField: product_id, prefix: "product."

// Step 2: Second lookup — specify fields with a different prefix
| lookup [fetch bizevents
    | filter event.type == "warehouse_stock"
    | fields category, warehouse_region],
  sourceField: product_category, lookupField: category, prefix: "warehouse."

```
The new fields are: `product.product_id`, `product.category`, `warehouse.category`, `warehouse.warehouse_region`.
All fields starting with `product.` or `warehouse.` are removed from the original source.
Without the dedicated `prefix`, both `lookup` commands would use the same prefix (`lookup.`) and the second `lookup` drops the first lookup's results — producing empty fields.

______________________________________________________________________

## makeTimeseries Command

`makeTimeseries` builds a time-bucketed series from event data (logs, spans, bizevents). Unlike `timeseries` (which queries pre-ingested metrics), `makeTimeseries` aggregates data in a pipeline.

**Do not pipe `timeseries` directly into `makeTimeseries`** — it fails with `INVALID_IMPLICIT_TIME_DEFAULT`. To re-aggregate metric data, use `start()` + expand (see [references/summarization.md](references/summarization.md)).

```dql
fetch logs
| makeTimeseries
    {total = count(),
    errors = countIf(loglevel == "ERROR")},
    interval: 5m,
    by: {k8s.cluster.name}
| fieldsAdd error_rate = errors[] * 100.0 / total[]
```

Key parameters: `interval:`, `by:{}`, `from:`/`to:`, `bins:`, `time:` (timestamp field), `spread:` (for `count`/`countIf` only), `nonempty:`. → [references/dql/dql-commands.md](references/dql/dql-commands.md) for full spec.

Entity existence timeline using `spread:`:

```dql
smartscapeNodes "HOST"
| makeTimeseries concurrently_existing_hosts = count(), spread: lifetime
```

→ [references/iterative-expressions.md](references/iterative-expressions.md) for timeseries array manipulation

______________________________________________________________________

## Timeframe Specification

Access to data requires specification of a timeframe.
It can be specified in the UI, as REST API parameters, or in a DQL query explicitly using a pair of parameters: `from:` and `to:` (if one is omitted it defaults to `now()`), or alternatively using a single `timeframe:` parameter.
Timeframe can be expressed using absolute values or relative expressions vs. current time. The time alignment operator (`@`) can be used to round timestamps to time unit boundaries — see [references/operators.md](references/operators.md) for full details.

### Examples

```dql-snippet
from:now()-1h@h, to:now()@h     // last complete hour
```
```dql-snippet
from:now()-1d@d, to:now()@d     // yesterday complete
```
```dql-snippet
from:now()@M                    // this month so far, till now
```
```dql-snippet
from:now()-2h@h                 // go back 2 hours, then align to hour boundary
```

See [references/operators.md](references/operators.md) for the full `@` alignment-unit table (including `m` vs. `M`, week-day variants `w1`–`w7`, and factor rules like `@3h`).

### Absolute timestamps

Use ISO 8601 format:

```dql-snippet
from:"2024-01-15T08:00:00Z", to:"2024-01-15T09:00:00Z"
```

______________________________________________________________________

## Modifying Time

### Key concepts

- DQL has 3 specialized types related to time:
    - **timestamp** — internally kept as number of nanoseconds since epoch, but exposed as date/time in a particular timezone
    - **timeframe** — a pair of 2 timestamps (start and end)
    - **duration** — internally kept as number of nanoseconds, but exposed as duration scaled to a reasonable factor (e.g. ms, minutes, days)

### Rules

- Subtracting timestamps yields a duration: `timestamp - timestamp → duration`
- Duration divided by duration yields a double: e.g. `2h / 1m` = `120.0`
- Scalar times duration yields a duration: e.g. `no_of_h * 1h → duration`
- For extraction of time elements (hours, days of month, etc):
    - ✅ Use [time functions](references/dql/dql-functions-time.md). They support calendar and time zones properly including DST.
    - ❌ Avoid using `formatTimestamp` for extracting time components.
    - ❌ Avoid converting timestamps and durations to double/long and using division, modulo, and constants expressing time units as nanoseconds.

## References

- **[references/useful-expressions.md](references/useful-expressions.md)** — Useful expressions in DQL
- **[references/semantic-dictionary.md](references/semantic-dictionary.md)** — Dynatrace Semantic Dictionary: field namespaces, data models, stability levels, query patterns, and best practices
- **[references/summarization.md](references/summarization.md)** — Various applications of summarize and makeTimeseries commands
- **[references/iterative-expressions.md](references/iterative-expressions.md)** — Array and timeseries manipulation (creation, modifications, use in filters) using DQL
- **[references/smartscape-topology-navigation.md](references/smartscape-topology-navigation.md)** — Smartscape topology navigation syntax and patterns
- **[references/optimization.md](references/optimization.md)** — DQL query optimization: making queries faster, more efficient, and cheaper to run (lower consumption / scanned data per execution) — filter placement, bucket filters, time ranges, field selection, sampling, cardinality, and performance best practices
- **[references/operators.md](references/operators.md)** — `in` operator (subquery syntax) and full `@` time alignment unit reference
