# DQL Parameter Value Types

| key | name | description |
|-----|------|-------------|
| `bucket` | name or pattern for bucket filters | plain string used to specify the name or pattern for buckets to filter on |
| `dataObject` | data object | is validated against the data objects in the record type repository |
| `dplPattern` | pattern for parsing | validated DPL pattern string |
| `entityAttribute` | entity attribute | an entity attribute |
| `entitySelector` | entity selector | an entity selector |
| `entityType` | entity type | an entity type |
| `enum` | predefined string value | a static string, but only a predefined list of values is allowed |
| `executionBlock` | execution block | an execution block that may or may not contain commands (e.g. for a fork where [] means identity) |
| `expressionTimeseriesAggregation` | expression-based timeseries aggregation | a timeseries aggregation in the form of functionName(field) used to calculate timeseries on expressions |
| `expressionWithConstantValue` | constant expression | an expression with a constant value, e.g. `1+1` is constant, but no primitive value as the `+` is executed |
| `expressionWithFieldAccess` | expression | any expression; it might also access fields from records |
| `fieldPattern` | pattern for filtering field names | plain string used to specify multiple fields using a pattern with wildcards |
| `filePattern` | pattern for file listing | pattern for selecting files |
| `identifierForAnyField` | field identifier | has to refer to an existing field, but it might also be a nested record list |
| `identifierForEdgeType` | edge type | edge types are for smartscape - they do NOT refer to an existing field and can't be nested |
| `identifierForFieldOnRootLevel` | field identifier on root level | has to refer to an existing field on root level |
| `identifierForNodeType` | node type | node types are for smartscape - they do NOT refer to an existing field and can't be nested |
| `joinCondition` | join condition | can either be a field identifier or an equality comparison of left and right fields |
| `jsonPath` | JSONPath | validated JSONPath |
| `metricKey` | metric key | it has to be a metric key and will provide special suggestions |
| `metricTimeseriesAggregation` | metric-based timeseries aggregation | a timeseries aggregation in the form of functionName(metric) to calculate timeseries on metrics |
| `namelessDplPattern` | pattern for parsing | validated DPL pattern string, that might not contain field names |
| `nonEmptyExecutionBlock` | non-empty execution block | an execution block that has to contain at least one command (e.g. for a join) |
| `prefix` | prefix for flattening fields | plain string used to specify the prefix of all fields that are pushed to the root record |
| `primitiveValue` | primitive value | a primitive value; usually represented by a literal |
| `simpleIdentifier` | new field name | new field names are for aliases and names - they do NOT refer to an existing field and can't be nested |
| `tabularFileExisting` | tabular file name | a string that represents the name of a tabular file to load |
| `tabularFileNew` | new tabular file name | a string that represents the name of a tabular file to save |
| `url` | URL | fully qualified HTTP(S) URL |
