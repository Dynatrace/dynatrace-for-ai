---
name: dt-dql-essentials
description: REQUIRED before generating any DQL queries. Provides critical syntax rules, common pitfalls, and patterns. Load this skill BEFORE writing DQL to avoid syntax errors.
license: Apache-2.0
---

# DQL Essentials Skill

DQL is a pipeline-based query language. Queries chain commands with `|` to filter, transform, and aggregate data. DQL has unique syntax that differs from SQL — load this skill before writing any DQL query.

______________________________________________________________________

## Use Cases

| Use case                                                                                                           | Reference                                                                                    |
|--------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| Useful expressions in DQL                                                                                          | [references/useful-expressions.md](references/useful-expressions.md)                         |
| Smartscape topology navigation syntax and patterns                                                                 | [references/smartscape-topology-navigation.md](references/smartscape-topology-navigation.md) |
| Dynatrace Semantic Dictionary: field namespaces, data models, stability levels, query patterns, and best practices | [references/semantic-dictionary.md](references/semantic-dictionary.md)                       |
| Various applications of summarize and makeTimeseries commands                                                      | [references/summarization.md](references/summarization.md)                                   |
| Operators (in, time alignment `@`)                                                                                  | [references/operators.md](references/operators.md)                                           |
| Array and timeseries manipulation (creation, modifications, use in filters) using DQL                              | [references/iterative-expressions.md](references/iterative-expressions.md)                   |
| Query optimization (filter early, time ranges, field selection, performance)                                       | [references/optimization.md](references/optimization.md)                                     |


## DQL Reference Index

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

| ❌ Wrong                                      | ✅ Right                        | Issue                                                                |
| --------------------------------------------- | ------------------------------- | -------------------------------------------------------------------- |
| `filter field in ["a", "b"]`                  | `filter in(field, "a", "b")`    | No array literal syntax                                              |
| `by: severity, status`                        | `by: {severity, status}`        | Multiple grouping fields require curly braces                        |
| `contains(toLowercase(field), "err")`         | `contains(lower(field), "err")`  or `contains(field, "err", caseSensitive: false)`       | There's no function for `toLowerCase` in DQL |
| `filter name == "*serv*9*"`                   | `filter contains(name, "serv")` | Mid-string wildcards not allowed; use `contains()`                   |
| `matchesValue(field, "prod")` on string field | `contains(field, "prod")`       | `matchesValue()` is for array fields only                            |
| `toLowercase(field)`                          | `lower(field)`                  | The correct function in DQL is called `lower`                        |
| `arrayAvg(field[])` or `arraySum(field[])`    | `arrayAvg(field)` or `field[]`  | `field[]` = element-wise (array→array); `arrayAvg(field)` = collapse to scalar. Never mix both. |
| `my_field` after `lookup` or `join`           | `lookup.my_field` / `right.my_field` | `lookup` prefixes fields with `lookup.`; `join` prefixes right-side fields with `right.` |
| Chained `lookup` losing fields                | `fieldsRename` between lookups       | Each `lookup` **removes all existing `lookup.*` fields**. Rename after each lookup to preserve results (see below) |
| `substring(field, 0, 200)`                    | `substring(field, from: 0, to: 200)` | DQL functions use **named parameters** — positional args cause `TOO_MANY_POSITIONAL_PARAMETERS` |
| `filter log.level == "ERROR"`                 | `filter loglevel == "ERROR"`        | Log severity field is `loglevel` (no dot) — `log.level` does not exist                          |
| `sort count() desc`                           | ``sort `count()` desc``              | fields with special characters must use backticks                |

______________________________________________________________________

## Fetch Command → Data Model

Each data model has a specific fetch command — using the wrong one returns no results.

| Fetch Command | Data Model | Key Fields / Notes |
|---------------|------------|--------------------|
| `fetch spans` | Distributed tracing | `span.*`, `service.*`, `http.*`, `db.*`, `code.*`, `exception.*` |
| `fetch logs` | Log events | `log.*`, `k8s.*`, `host.*` — message body is `content`, severity is `loglevel` (NOT `log.level`) |
| `fetch events` | Davis / infra events | `event.*`, `dt.smartscape.*` |
| `fetch bizevents` | Business events | `event.*`, custom fields |
| `fetch securityEvents` | Security events | `vulnerability.*`, `event.*` |
| `fetch usersessions` | RUM sessions | `dt.rum.*`, `browser.*`, `geo.*` |
| `timeseries` | Metrics | NOT `fetch` — uses `timeseries avg(metric.key)` syntax |

Legacy compatibility: `dt.entity.*` still works in older queries, but it is deprecated. Use `dt.smartscape.*` and `smartscapeNodes` for all new queries.

Metric-key note: keys containing **hyphens** are parsed as subtraction. Use backticks, for example: ``timeseries sum(`my.metric-name`)``.

→ Full field namespace reference: [references/semantic-dictionary.md](references/semantic-dictionary.md)

______________________________________________________________________

## Data Objects

DQL queries start with `fetch <data_object>` or `timeseries`. There is **no `fetch dt.metric`** or `fetch dt.metrics` — metrics are queried with `timeseries`.

**Core data objects for `fetch`:**

| Data Object | Description |
| --- | --- |
| `logs` | Log entries |
| `spans` | Distributed traces / spans |
| `events` | Platform events |
| `bizevents` | Business events |
| `user.events` | RUM individual events (page views, clicks, requests, errors) |
| `user.sessions` | RUM session-level aggregates |
| `user.replays` | Session replay recordings |
| `security.events` | Security events |
| `application.snapshots` | Application snapshots |
| `dt.smartscape.<type>` | Smartscape entity fields (e.g., `dt.smartscape.host`, `dt.smartscape.service`) |
| `dt.davis.problems` | DAVIS-detected problems |
| `dt.davis.events` | DAVIS events |

**Metrics** — use `timeseries`, not `fetch`:
```dql
timeseries cpu = avg(dt.host.cpu.usage), by: {dt.smartscape.host}
```

**Topology** — use `smartscapeNodes`, not `fetch`:
```dql
smartscapeNodes "HOST"
```

**Discover available data objects:**
```dql
fetch dt.system.data_objects | fields name, display_name, type
```

______________________________________________________________________

## Metric Discovery

To search for available metrics by keyword, use `metric.series`:

```dql
fetch metric.series, from: now() - 1h
| filter contains(metric.key, "replay")
| summarize count(), by: {metric.key}
| sort `count()` desc
```

There is **no `fetch dt.metric`** or `fetch dt.metrics` — those data objects do not exist.

______________________________________________________________________

## Entity Field Patterns

Entity fields in DQL are scoped to specific entity types — not universal like SQL columns.

- `entity.id` **does not exist** — use a typed field such as `dt.smartscape.host`.

| Entity             | ID field                       |
| ------------------ | ------------------------------ |
| Host               | `dt.smartscape.host`           |
| Service            | `dt.smartscape.service`        |
| Process            | `dt.smartscape.process`        |
| Kubernetes cluster | `dt.smartscape.k8s_cluster`    |

- For topology traversal and relationships, use `smartscapeNodes` instead of `fetch`.

______________________________________________________________________

## Smartscape Entity Patterns

Use `smartscapeNodes` for topology queries. Node types are uppercase strings and differ from field names.

| Entity      | Field name                      | `smartscapeNodes` type |
| ----------- | ------------------------------- | ---------------------- |
| Host        | `dt.smartscape.host`            | `"HOST"`               |
| Service     | `dt.smartscape.service`         | `"SERVICE"`            |
| K8s cluster | `dt.smartscape.k8s_cluster`     | `"K8S_CLUSTER"`        |

Use `toSmartscapeId()` for ID conversion from strings (required!).

→ [references/smartscape-topology-navigation.md](references/smartscape-topology-navigation.md)

______________________________________________________________________

## matchesValue() Usage

Use `matchesValue()` for **array fields** such as `dt.tags`:

```dql-snippet
| filter matchesValue(dt.tags, "env:production")
```

- **Not** for string fields with special characters — use `contains()` for those
- `matchesValue()` on a scalar string field does not behave like a wildcard or fuzzy match

______________________________________________________________________

## Chained Lookup Pattern

Each `lookup` command **removes all existing fields starting with `lookup.`** before adding new ones. When chaining multiple lookups, use `fieldsRename` after each to preserve the result:

```dql
fetch bizevents
// Step 1: First lookup — enrich orders with product info
| lookup [fetch bizevents
    | filter event.type == "product_catalog"
    | fields product_id, category],
  sourceField: product_id, lookupField: product_id

// Step 2: Rename BEFORE next lookup — or lookup.category gets wiped
| fieldsRename product_category = lookup.category

// Step 3: Second lookup — lookup.* is now clean for new results
| lookup [fetch bizevents
    | filter event.type == "warehouse_stock"
    | fields category, warehouse_region],
  sourceField: product_category, lookupField: category

// Both product_category and lookup.warehouse_region are available
```

**Without the `fieldsRename`, the second `lookup` silently drops the first lookup's results — producing empty fields and collapsed aggregations.**

______________________________________________________________________

## makeTimeseries Command

`makeTimeseries` converts event-based data (logs, spans, bizevents) into a time-bucketed metric series. It is **not** the same as the `timeseries` command — `timeseries` queries pre-ingested metric data; `makeTimeseries` builds a series from signals in a pipeline.

**Basic syntax:**

```dql
fetch logs
| makeTimeseries count = count(), by: {loglevel}, interval: 5m
```

**Key parameters:**

| Parameter        | Required | Description                                                          |
| ---------------- | -------- | -------------------------------------------------------------------- |
| `<agg> = <expr>` | Yes      | Aggregation to compute per bucket (e.g. `count()`, `avg(duration)`) |
| `interval:`      | No       | Bucket size — e.g. `1m`, `5m`, `1h`                                 |
| `by:`            | No       | Optional grouping dimensions (same `{}` syntax as `summarize`)       |
| `from:` / `to:`  | No       | Explicit time range; defaults to the query timeframe                 |
| `bins:`          | No       | Number of time buckets (alternative to `interval:`)                  |
| `time:`          | No       | Field to use as the timestamp; defaults to `timestamp`               |
| `spread:`        | No       | Timeframe expression for bucket calculation; alternative to `time:`, only works with `count` or `countIf` |
| `nonempty:`      | No       | Boolean; when `true`, fills missing time buckets with null instead of omitting them |

→ Full formal parameter specification: [references/dql/dql-commands.md](references/dql/dql-commands.md)

**Example — error rate timeseries from logs:**

```dql
fetch logs
| makeTimeseries
    total = count(),
    errors = countIf(loglevel == "ERROR"),
    interval: 5m,
    by: {k8s.cluster.name}
| fieldsAdd error_rate = errors / total * 100
```

**Example — entity existence timeline using `spread:`:**

```dql
smartscapeNodes "HOST"
| makeTimeseries concurrently_existing_hosts = count(), spread: lifetime
```

`spread: lifetime` distributes each host's count across the timeframe it existed, producing a series that shows how many hosts were alive at any point in time.

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

______________________________________________________________________

## References

- **[references/useful-expressions.md](references/useful-expressions.md)** — Useful expressions in DQL
- **[references/semantic-dictionary.md](references/semantic-dictionary.md)** — Dynatrace Semantic Dictionary: field namespaces, data models, stability levels, query patterns, and best practices
- **[references/summarization.md](references/summarization.md)** — Various applications of summarize and makeTimeseries commands
- **[references/operators.md](references/operators.md)** — Operators: `in` comparison and `@` time alignment
- **[references/iterative-expressions.md](references/iterative-expressions.md)** — Array and timeseries manipulation (creation, modifications, use in filters) using DQL
- **[references/smartscape-topology-navigation.md](references/smartscape-topology-navigation.md)** — Smartscape topology navigation syntax and patterns
- **[references/optimization.md](references/optimization.md)** — DQL query optimization: filter placement, time ranges, field selection, and performance best practices
- **[references/dql/](references/dql/)** — Formal DQL 1.0 specification: commands, functions, data types, and parameter types
