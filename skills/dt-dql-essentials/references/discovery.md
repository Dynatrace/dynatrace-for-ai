# Discover data in Grail using DQL

## List all data objects
```dql
fetch dt.system.data_objects
```

Important fields in results:
* `type` : `table`|`view`
* `usable_with` : list of commands which can be used to address the data object
* Special cases — these data objects use dedicated commands instead of `fetch`:
   * `metrics` : `timeseries`
   * `smartscape.nodes` : `smartscapeNodes`
   * `smartscape.edges` : `smartscapeEdges` and `traverse`

## List all buckets
```dql
fetch dt.system.buckets
```

Important fields in results:
* `dt.system.table` : the table this bucket belongs to

## Get information about fields

* Always present fields (name and data type): `describe` command
  ```dql
  describe logs
  ```
* Dynamic fields: `fieldsSnapshot`
  * Statistical info over the last 24h; may lag and may omit very infrequent fields. `relative_count` is the percentage (0–100) of records containing the field.
  * Output columns: `field` (field name), `type` (data type), `relative_count` (% of records containing it), plus any `by:` group keys.
  * To get information by bucket add:
    ```dql-snippet
    , by:{dt.system.bucket}
    ```
  * To get information by data type (fields with same name can be of different type in different records) add:
    ```dql-snippet
    , by:{type}
    ```

## Get additional information about metrics

* Discover metric keys themselves:
```dql
fieldsSnapshot metrics, by: {metric.key}
| fields metric.key
| dedup  metric.key
```
* Find dimensions for a metric:
```dql
fieldsSnapshot metrics, by:{metric.key}
| filter metric.key == "<metric_key>"
```
* Find metrics that expose a given dimension:
```dql
fieldsSnapshot metrics, by:{metric.key}
| filter field == "<dimension_name>"
```
* Find metrics for a particular dimension value (substitute `<dimension_key>` with the actual dimension field, e.g. `host.name`):
```dql-template
metrics
| filter <dimension_key> == "<dimension_value>"
| fields metric.key
| dedup metric.key
```
* List dimension combinations (series) for a metric — each row is one series:
```dql
metrics
| filter metric.key == "<metric_key>"
```
* Project a specific dimension to get its values (substitute `<dimension_key>` with the actual dimension field, e.g. `host.name`):
```dql-template
metrics
| filter metric.key == "<metric_key>"
| fields <dimension_key>
| dedup <dimension_key>
```


## List resource files (lookup tables)
```dql
fetch dt.system.files
```
Important fields in results:
* `name` : file name used by `load`
