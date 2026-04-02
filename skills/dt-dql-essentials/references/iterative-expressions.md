# Iterative expressions and arrays - a way to work with arrays and timeseries in DQL

## Table of Contents
- [General rules](#general-rules)
- [Arrays and timeseries](#arrays-and-timeseries)
- [Filtering involving arrays](#filtering-involving-arrays)
    - [Testing membership in array](#testing-membership-in-array)
    - [Testing using iterative expressions](#testing-using-iterative-expressions)
- [Examples](#examples)
    - [New timeseries/array based on condition](#new-timeseriesarray-based-on-condition)
    - [Removing last array element, replacing last array element with null](#removing-last-array-element-replacing-last-array-element-with-null)
    - [Further time aggregation of timeseries](#further-time-aggregation-of-timeseries)
    - [Summarization of timeseries](#summarization-of-timeseries)
    - [How to get each datapoint of timeseries separately with its own timestamp](#how-to-get-each-datapoint-of-timeseries-produced-by-timeseries-or-maketimeseries-commands-separately-with-its-own-timestamp)
    - [How to get last timestamp when data was present in timeseries](#how-to-get-last-timestamp-when-data-was-present-in-timeseries)
    - [Timestamp of last metric ingestion](#timestamp-of-last-metric-ingestion)
    - [How to remove values from array and make it shorter](#how-to-remove-values-from-array-and-make-it-shorter-by-number-of-removed-elements)
    - [How to apply complex conditions on arrays](#how-to-apply-complex-conditions-on-arrays)

## General rules

* Iterative expression is a notation when specific operation is performed on every element of arrays used in the query
* Operation on multiple arrays are done in sync. While iteration over arrays operation is happening and elements of the same index
* All arrays need to be of the same length / size. If not iterative expressions fail.
* Result of iterative expression is another arrays.
* DQL has a set of dedicated array functions. Their names start with `array....()` — see [dql/dql-functions-array.md](dql/dql-functions-array.md) for the full reference.
* Iterative expression can be wrapped in `iCollectArray()` function. After this array functions can be used immediately.
* `iAny(logical_iterative_expression)` performs test of logical iterative expression. `TRUE` is returned when expression was `TRUE` for at least one element
* `not iAny(not logical_iterative_expression)` allows to check if `TRUE` was returned for all elements

## Arrays and timeseries
* Timeseries is array produced by `timeseries` command accompanied by timeframe and interval fields. Elements of array represent values for subsequent time buckets from earliest to latest (most recent)
* `timeframe` field (type of field: timeframe) defines time span covered by timeseries from the beginning (accessible via `timeframe[start]`) of first time bucket (represented by first element of array) to the end of last bucket (accessible via `timeframe[end]`)
* If timeseries produced is named e.g. `d`, following is true: `arraySize(d)*interval == timeframe[end]-timeframe[start]`
* Timeseries produced by `timeseries` command can carry unit and this information is tied to name of field. If transformations using iterative expression are reusing fields names, unit information will be kept. Metric unit can be found in query result metadata.
* **Time bucket mapping**: The timestamp of a value at array index `i` (0-based) is: `timeframe[start] + interval * i`. E.g. index 0 → `timeframe[start]`, index 1 → `timeframe[start] + interval`, index 2 → `timeframe[start] + interval * 2`, etc.

## Filtering involving arrays

### Testing membership in array

* `in()` function allows to have 1st (`needle`) and 2nd and following parameter (`haystacks`) as array. It returns true if any element of `needles` (or just `needle` if it is not an array) is element of any `haystacks` (or equal to any `haystacks` if eny of them is not an array)
* Syntax when `needle` is field, `haystacks` is constant
    - `in(field, {"a", "b", "c"})`
    - `in(field, array("a", "b", "c"))`
    - `in(field, {array("a", "b", "c"), array("d", "e")})` - 2 haystacks
    - `in(field, "a", "b", "c")` - simplified syntax where parameters except 1st one are treated as haystack
* Recommended syntax for dashboard multi-select variables: `in(field, array($variable))`. Omitting `array()` will cause error when nothing was selected which can happen when variable options are empty
    - In case variable is not string: `in(field, array($variable:noquote))` (by defuale each variable value is surrounded by double-quotes)
    - In case variable is string which may contain unescaped characters needing escaping  `in(field, array($variable:triplequote))`
* `in(needle_array, haystack_array)` checks it there are any common elements (intersections) between arrays. E.g.

```dql
data record(a1=array("1","2","3"), a2=array("3","4")),
record(a1=array("1","2","3"), a2=array("5"))
| fieldsAdd in(a1, a2)
```

checks if there is any common elements between array a1 and a2

### Testing using iterative expressions
* Checks if given string (a1) begins (`startsWith()` function) with any of strings in a2

```dql
data record(a1="a", a2=array("b","c"))
| fieldsAdd iAny(startsWith(a1, a2[]))
```

* Tests if all elements of array a1 are present in array a2

```dql
data record(a1=array("1","2"), a2=array("1", "2", "3","4")),
record(a1=array("1","2","3"), a2=array("1", "2", "4" , "5", "6")),
record(a1=array("a"), a2=array("1", "2", "4" , "5", "6"))
| fieldsAdd not iAny(not in(a1[], a2))
```

## Examples

### new timeseries/array based on condition
* Question: based on 2 timeseries: bad and total I want 3rd one: failed. Element of failed has to have value of bad when value of total is grater then 100. DQL query so far:

```dql
timeseries { bad = sum(dt.service.request.failure_count) ,
total = sum( dt.service.request.count ) }, union:true
```

* Answer: Last command can do it using iterative expression

```dql
timeseries { bad = sum(dt.service.request.failure_count) ,
total = sum( dt.service.request.count ) }, union:true
| fieldsAdd bad = if (total[]>350000, bad[], else:0)
```

### Removing last array element, replacing last array element with null
* Question: One of our customers tried to remove the last datapoint from the graphs. Incomplete data for last datapoints the aggregated calculations shows wrong, so they want to exclude the last incomplete data points.
  Are there options than using custom timeframe?
* Answer: you can set the last element of array to null this way:

```dql
  data record(a=array(1,2,3,2))
  | fieldsAdd a=if(iIndex()<arraySize(a)-1, a[], else:null)
```

### Further time aggregation of timeseries
* Question: Is it possible to rollup a timeseries on a larger time-interval (1h in my case)?
  Use case:

```dql
timeseries {
good = sum(dt.service.request.count, filter: not failed),
total = sum(dt.service.request.count)
}, by: { k8s.namespace.name }, interval: 1m
| fieldsAdd sli = good[] / total[] * 100
```

* Answer:

```dql
timeseries {
  good = sum(dt.service.request.count, filter: not failed),
  total = sum(dt.service.request.count),
  timestamp=start()
}, by: { k8s.namespace.name }, interval: 1m

| fieldsAdd d = record( sli = good[] / total[] * 100, timestamp=timestamp[] )
| expand d
| makeTimeseries sli = avg(d[sli]), time: d[timestamp], interval:1h
```

### Summarization of timeseries
* Question: I need some help summarizing a timeseries in another timeseries. So far I have this:

```dql
timeseries {
    memoryUsage = max(dt.kubernetes.container.memory_working_set),
    memoryRequest = avg(dt.kubernetes.container.requests_memory)
  },
  filter: (
    (k8s.cluster.name == "jenkins-worker"
    OR k8s.cluster.name == "jenkins-worker-ha"
    OR k8s.cluster.name == "jenkins-worker-windows")
    AND k8s.namespace.name != "kube-system"
    AND k8s.namespace.name != "dynatrace"
    AND k8s.container.name != "jnlp"
  ),
  by: { dt.smartscape.k8s_pod, k8s.cluster.name, k8s.namespace.name, k8s.pod.name, k8s.container.name }, interval: 60000ms
| fieldsAdd overUsage = memoryUsage[] / memoryRequest[]
```

and I want to summarize by dt.smartscape.k8s_pod, k8s.cluster.name, k8s.namespace.name, k8s.pod.name
* Answer: Summarize can produce timeseries:

```dql
timeseries {
memoryUsage = max(dt.kubernetes.container.memory_working_set),
memoryRequest = avg(dt.kubernetes.container.requests_memory)
},
filter: (
(k8s.cluster.name == "jenkins-worker"
OR k8s.cluster.name == "jenkins-worker-ha"
OR k8s.cluster.name == "jenkins-worker-windows")
AND k8s.namespace.name != "kube-system"
AND k8s.namespace.name != "dynatrace"
AND k8s.container.name != "jnlp"
),
by: { dt.smartscape.k8s_pod, k8s.cluster.name, k8s.namespace.name, k8s.pod.name, k8s.container.name }, interval: 60000ms
| fieldsAdd overUsage = memoryUsage[] / memoryRequest[]
| summarize overUsage = max(overUsage[]), by: {dt.smartscape.k8s_pod, k8s.cluster.name, k8s.namespace.name, k8s.pod.name, timeframe, interval}
```

Always keep timeframe and interval in the summarize by clause when you want to get timeseries as a result of summarize. Without it we cannot chart data on timeline.

### How to get each datapoint of timeseries produced by `timeseries` or `makeTimeseries` commands separately with its own timestamp?
Example metric: dt.service.request.count
Example aggregation used: sum()

```dql
timeseries {cnt=sum(dt.service.request.count), timestamp=start(), timestamp_end=end()}, from:-1y, interval:24h
| fieldsAdd d=record(cnt=cnt[], timestamp=timestamp[], timestamp_end=timestamp_end[])
| expand d
| fields cnt=d[cnt], timestamp=d[timestamp], timestamp_end=d[timestamp_end]
```

### How to get last timestamp when data was present in timeseries?

```dql
timeseries { d=sum(dt.service.request.count),  timestamp=start() }, filter: dt.smartscape.service == "SERVICE-0A596770A52979EB"
| fieldsAdd timestamp = arrayLast(iCollectArray(if (isNotNull(d[]), timestamp[] )))
```

### Timestamp of last metric ingestion
* Question: How to get last timestamp when data was ingested into timeseries?
* Answer: It is possible, but only with 1m accuracy. Timestamps of individual contributions

```dql
timeseries { d=sum(dt.service.request.count),  timestamp=start() }, filter: dt.smartscape.service == "SERVICE-0A596770A52979EB", interval:1m
| fieldsAdd timestamp = arrayLast(iCollectArray(if (isNotNull(d[]), timestamp[] )))
```

If this query is run for longer timeframes, the interval will not stay at 1m. It may be adjusted because only 1500 time bins/buckets are allowed.
Use the identified longer bin to run a second query with a 1m interval for that specific timeframe.


### How to remove values from array and make it shorter by number of removed elements
* Question: Let's assume I want to keep only strings beginning with capital letters in an array
* Answer

```dql
data record(a=array("John", "cat", "London", "cloud"))
| fieldsAdd a = arrayRemoveNulls( iCollectArray( if(substring(a[], from:0, to:1)==upper(substring(a[], from:0, to:1)), a[] ) ) )
```

but if the task included also keeping elements which are null this query requires additional step:

```dql
data record(a=array("John", "cat", "London", "cloud", null))
| fieldsAdd a = record(n = isNull(a[]), v=a[] )
| fieldsAdd a = arrayRemoveNulls( iCollectArray( if( a[][n] or substring(a[][v], from:0, to:1)==upper(substring(a[][v], from:0, to:1)), a[] ) ) )
| fieldsAdd a = a[][v]
```

### How to apply complex conditions on arrays
* Question: How to find hosts where average CPU usage measured in 1m intervals is higher than 70 at least 3 times
* Answer

```dql
timeseries cpu=avg(dt.host.cpu.usage), by: {dt.smartscape.host}, interval:1m
| filter arraySum(iCollectArray(if(cpu[]>70,1)))>3
```

* Question: How to find hosts where average CPU usage measured in 1m intervals is higher than 70 at least 50% of the times when measurement was provided
* Answer

```dql
timeseries cpu=avg(dt.host.cpu.usage), by: {dt.smartscape.host}, interval:1m
|filter arraySum(iCollectArray(if(cpu[]>70,1.0))) / arraySum(iCollectArray(if(isNotNull(cpu[]),1.0))) > 0.5
```

### Finding timestamp of highest value
* Question: In addition to the aggregated average and 95th percentile values, I would like to know the timeslot when the value was maximal?
* Answer: Using the array of maximal values and the array of timestamps, the exact time slot can be determined:
```dql
timeseries {
  avg_rt = avg(dt.service.request.response_time, scalar:true),
  p95_rt = percentile(dt.service.request.response_time, 95, scalar:true),
  max_rt = max(dt.service.request.response_time, default:0),
  timestamp = start()}, by:{endpoint.name}
| fieldsAdd d = record(max_rt=max_rt[], timestamp=timestamp[])
| fieldsAdd d = arraySort(d, direction:"descending")
| fields endpoint.name, avg_rt, p95_rt, max_rt=arrayFirst(d)[max_rt], when_max_rt = arrayFirst(d)[timestamp]
```
