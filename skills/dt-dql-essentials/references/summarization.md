# Various applications of summarize and makeTimeseries commands

## Table of Contents
- [General rules](#general-rules)
- [Examples](#examples)

## General rules
* `makeTimeseries` accepts timeframe from `from:` and `to:` or from `timeframe:` parameters, but if they are not present timeframe is inherited from query providing data. In case time values from expression/field provided in `time:` parameter is outside from this inherited timeframe, data will be ignored. For such cases providing proper timeframe is necessary.      

## Examples

### How to aggregate data by calendar months
* Question: If there is data present for past year in bizevents table it is easy to aggregate by calendar month.
```dql
fetch bizevents, from: -1y
| summarize {cnt=count()}, by: { month=timestamp@M } 
```
Is the same possible for metrics?
* Answer: if data is available as metrics, first daily aggregates need to be retrieved, then they can be aggregated by calendar months:
```dql
timeseries {cnt=sum(dt.service.request.count), timestamp=start()}, from:-1y, interval:24h
| fieldsAdd d=record(cnt=cnt[], timestamp=timestamp[])
| expand d
| fields cnt=d[cnt], timestamp=d[timestamp]
| summarize {cnt=sum(cnt)}, by: { month=timestamp@M }
```
Data presented this way is chartable the same as if it were a time series.

### How to filter rows by property of group of them
* Question: I want to get only hosts if they belong to cluster smaller than N hosts. Cluster belonging is defined by `host.custom.metadata[Cluster]` 
```dql
    smartscapeNodes "HOST"
    | fieldsAdd cluster = host.custom.metadata[Cluster]
```
* Answer: during summarization besides calculation count, sums and averages we can preserve original data in arrays
```dql
    smartscapeNodes "HOST"
    | fieldsAdd cluster = host.custom.metadata[Cluster]
    | filter isNotNull(cluster)
    | summarize { host_count = count(), dt.smartscape.host=collectArray(id) } , by: {cluster}
    | filter host_count < 100  // Filter clusters with less than 100 hosts
    | fields dt.smartscape.host
    | expand dt.smartscape.host
```

### Histogram metric visualization
* Question: I have a histogram metric with "le" dimension representing less-or-equal so upper bounds of histogram bucket. How can I graph a histogram over time for this metric?
* Answer: Our heatmap visualization is perfect for this use case. You just need to prepare data in the right format:
```dql
timeseries {cnt = sum(istio_request_duration_milliseconds_bucket), timestamp=start()}, by:{le}, interval:15m
| fieldsAdd d = record(timestamp=timestamp[], cnt=cnt[])
| expand d
| summarize d = collectArray(record(le_s=toDouble(le), le, cnt=d[cnt])), by:{ timestamp=d[timestamp]}
| fieldsAdd d = arraySort(d, direction:"ascending")
| fieldsAdd cnt = arrayRemoveNulls(arrayDelta( arrayFlatten(arrayConcat(array(0),iCollectArray( d[][cnt] )))))
| fieldsAdd d = record(le = d[][le], cnt=cnt[])
| expand d
| makeTimeseries cnt=sum(d[cnt]), by: {le=d[le]}, interval:15m
| sort toDouble(le) desc
```

### Calculating percentages for results of summarization (summarize with count())
* Question: I have a summarize with count() and I want to calculate percentage of each value in total count. How can I do it? I have this DQL query:
```dql
fetch logs
| summarize {c=count()}, by: {loglevel}
```
* Answer:
```dql
fetch logs 
| summarize {c=count()}, by: {loglevel}
| summarize {d=collectArray(record(c, loglevel)), total=sum(c)}
| expand d
| fields loglevel=d[loglevel], c=d[c], perc=100.0*d[c]/total
```

### calculating difference between values for subsequent days
* Question: Let's assume that data looks like this and being aggregated this way:
```dql
data record(BusinessProcessDate = "2026-02-27", value = 110.000),
record(BusinessProcessDate = "2026-02-28", value = 115.500),
record(BusinessProcessDate = "2026-03-01", value = 112.300),
record(BusinessProcessDate = "2026-03-01", value = 112.300),
record(BusinessProcessDate = "2026-03-03", value = 119.800),
record(BusinessProcessDate = "2026-03-04", value = 122.100),
record(BusinessProcessDate = "2026-03-05", value = 118.600)
| summarize current = max(value), by: {BusinessProcessDate=toTimestamp(BusinessProcessDate)}
```
I want to calculate difference (absolute and relative) of current value for specific date and value for previous data (null if there was no data for previous date).
* Answer: Collect array gathers data in single arrays as records containing date and value (in this order). Array needs to be sorted, because collectArray does not guarantee any sorting. using arrayElement and iIndex()-1 we can look at array's previous elements and if this is for previous date we can take a value from there as "previous". After expanding array to records, calculation of differences is possible
```dql
data record(BusinessProcessDate = "2026-02-27", underlyingsInStream = 110.000),
     record(BusinessProcessDate = "2026-02-28", underlyingsInStream = 115.500),
     record(BusinessProcessDate = "2026-03-01", underlyingsInStream = 112.300),
     record(BusinessProcessDate = "2026-03-02", underlyingsInStream = 114.574),
     record(BusinessProcessDate = "2026-03-03", underlyingsInStream = 119.800),
     record(BusinessProcessDate = "2026-03-04", underlyingsInStream = 122.100),
     record(BusinessProcessDate = "2026-03-05", underlyingsInStream = 118.600)
| summarize current = max(underlyingsInStream), by: {BusinessProcessDate=toTimestamp(BusinessProcessDate)}
| summarize d = collectArray(record(BusinessProcessDate, current))
| fieldsAdd d = arraySort(d, direction:"ascending")
| fieldsAdd previous = if( d[][BusinessProcessDate] - arrayElement(d,iIndex()-1)[BusinessProcessDate] == 1d , arrayElement(d,iIndex()-1)[current])
| fields d = record(BusinessProcessDate=d[][BusinessProcessDate], current=d[][current], previous=previous[] )
| expand d
| fields BusinessProcessDate=d[BusinessProcessDate], current=d[current], previous=d[previous], absChange=d[current]-d[previous], relChange=(d[current]-d[previous])*100.0/d[previous]
| sort BusinessProcessDate desc
```

### Join operation expressed as summarization
* Question: Query below fails due to size limit related to result of right query 
```dql
  fetch user.events, scanLimitGBytes:-1
  | filter isNotNull(trace.id)
  | dedup dt.rum.session.id, trace.id
  | join [
      fetch spans, scanLimitGBytes:-1
      | filter isNotNull(host.name)
      | dedup trace.id, host.name
  ], on:{trace.id}, fields:{host.name}
  | summarize session_count=countDistinct(dt.rum.session.id), by:{hostname=host.name}
```
* Answer: With `append` and `summarize` same effect can be achieved 
```dql
fetch user.events, scanLimitGBytes:-1
| filter isNotNull(trace.id)
| dedup dt.rum.session.id, trace.id
| append [ 
    fetch spans, scanLimitGBytes:-1
    | filter isNotNull(host.name)
    | summarize host.name=collectDistinct(host.name), by:{trace.id}
]
| summarize { dt.rum.session.id=takeAny(dt.rum.session.id),
host.name=takeAny(host.name) }, by:{trace.id}
| filterOut isNull(dt.rum.session.id)
| summarize session_count=countDistinct(dt.rum.session.id), by:{hostname=host.name}
| sort session_count desc
```
* Question: what if data is coming from same source:
```dql
fetch logs
| filter matchesPhrase(messageIdentification,"pacs8")    
| fields timestamp, messageIdentification, transactionIdentification, id  
| join [
  fetch logs
  | filter matchesPhrase(messageIdentification,"pacs2")
  | fields timestamp, messageIdentification, transactionIdentification, id
], on: { transactionIdentification}
    
| fields transactionIdentification, pacs8time = timestamp, pacs2time = right.timestamp
| fieldsAdd diffDuration = pacs2time - pacs8time
```
* Answer in this case `append` is not needed
```dql
fetch logs
| filter matchesPhrase(messageIdentification,"pacs8") or matchesPhrase(messageIdentification,"pacs2")   
| fields timestamp, messageIdentification, transactionIdentification, id
| summarize {
  pacs8time = takeAny(if(matchesPhrase(messageIdentification, "pacs8"), timestamp)),
  pacs2time = takeAny(if(matchesPhrase(messageIdentification, "pacs2"), timestamp))
}, by: { transactionIdentification }
| fieldsAdd diffDuration = pacs2time - pacs8time
```

### Use of `spread:` parameter
* Question: how to graph over time number of running containers by workload.kind. Container has `lifetime` property being timeframe in which it was active
* Answer: `spread:` parameter of `makeTimeseries` together with `count()`:
```dql
smartscapeNodes "CONTAINER"
| makeTimeseries count(), spread:lifetime, by: {k8s.workload.kind}, interval:30m
```
