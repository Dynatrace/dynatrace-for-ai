# Entity Lookups and Service Context

Enrich traces with Smartscape node metadata, correlate with infrastructure, and analyze performance by hardware.

## Overview

Spans reference services via Smartscape node IDs. Service names and attributes are available through Dynatrace Smartscape (Entity Model) using node lookups. This enables enriching trace data with infrastructure context, analyzing performance by hardware, and correlating across multiple node types.

## Service Node Basics

### List Services

Fetch service nodes:

```dql
smartscapeNodes SERVICE | limit 100

```

### Add Service Name to Spans

Enrich spans with service names:

```dql
fetch spans
| fieldsAdd getNodeName(dt.smartscape.service)
| summarize spans=count(), by: { dt.smartscape.service, dt.smartscape.service.name }
| sort spans desc

```

## Filtering by Service

### Using Smartscape Node Filters

Filter spans for specific service (Smartscape node filters and `traverse` should be used instead of the legacy `classicEntitySelector()`):

```dql
fetch spans
// Smartscape node filters and traverse should be used instead of classicEntitySelector

// Via subquery (recommended)
| filter dt.smartscape.service in [
    smartscapeNodes SERVICE
    | filter name == "BookStore.Books.dev"
    | fields id
]
| filter request.is_root_span == true
| summarize { requests=count(), avg(duration) }, by: { url.path }

```

## Service Performance

### Service and Endpoint Response Times

Analyze performance by service and endpoint:

```dql
fetch spans
| filter request.is_root_span == true
| fieldsAdd getNodeName(dt.smartscape.service)
| summarize {
    requests=count(),
    avg_response_time=avg(duration)
  }, by: { dt.smartscape.service, dt.smartscape.service.name, endpoint.name }
| sort dt.smartscape.service.name, endpoint.name
| sort requests desc

```

## Advanced Node Lookups

### Host, Process Group, and Service Attributes

Lookup multiple node types with attributes:

```dql
fetch spans
| filter isNotNull(dt.smartscape.host) and isNotNull(dt.smartscape.service) and isNotNull(dt.process_group.id)

// Add host information including hardware
| fieldsAdd getNodeName(dt.smartscape.host),
            getNodeField(dt.smartscape.host, "bitness"),
            getNodeField(dt.smartscape.host, "additionalSystemInfo")

// Flatten system info
| fieldsFlatten dt.smartscape.host.additionalSystemInfo

| fieldsAdd getNodeName(dt.smartscape.service)

// Add process group detected name and technologies (process_group is not a Smartscape node)
| fieldsAdd dt.process_group.detected_name

// Note: process_group attributes like softwareTechnologies have no Smartscape equivalent
// The dt.process_group.detected_name field is available directly on spans

| limit 1

```

### Performance by Hardware

Analyze response times split by CPU type:

```dql
fetch spans
| filter request.is_root_span == true

// Add host information including hardware
| fieldsAdd getNodeName(dt.smartscape.host),
            getNodeField(dt.smartscape.host, "bitness"),
            getNodeField(dt.smartscape.host, "additionalSystemInfo")

// Extract CPU information
| fieldsAdd host.cpu = dt.smartscape.host.additionalSystemInfo[system.processor.model]

| filter isNotNull(host.cpu)

| summarize {
    count(),
    avg(duration)
  }, by: { dt.smartscape.service, endpoint.name, bitness=dt.smartscape.host.bitness, host.cpu }

```

## Best Practices

- **Use `getNodeName()`** to add node names: `getNodeName(dt.smartscape.service)` adds `dt.smartscape.service.name`
- **Use `getNodeField()`** to access specific node attributes
- **Use Smartscape node filters and `traverse`** instead of `classicEntitySelector()` for better performance and readability
- **Filter early** - apply node filters before expensive operations
- **Access nested attributes** using bracket notation after `fieldsFlatten`
- **Parse complex attributes** when node attributes contain structured text (e.g., software technologies)
