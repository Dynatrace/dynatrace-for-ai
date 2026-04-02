# Networking and IP Analysis

Trace data contains networking information including IP addresses, server addresses, and DNS resolution results.

## Server Addresses and IPs

### Outgoing Request Destinations

Collect all server addresses and resolved IPs:

```dql
fetch spans, from:now() - 30m
| filter isNotNull(server.resolved_ips)

// Collect all server IP addresses
| summarize {
    ips=collectDistinct(arraySort(server.resolved_ips))
  }, by: { server.address, server.port }

// Double expand: ips is array of arrays, flatten to list
| expand ips
| expand ips
| sort ips
```

**Note**: `server.resolved_ips` contains array of IP addresses from DNS lookup at request time.

### Outgoing Requests by Service

Show which services connect to which servers:

```dql
fetch spans, from:now() - 30m
| filter isNotNull(server.resolved_ips)
| fieldsAdd getNodeName(dt.smartscape.service)

| summarize {
    count(),
    ips=collectDistinct(server.resolved_ips)
  }, by: {
    k8s.namespace.name,
    dt.smartscape.service.name,
    server.address,
    operation=coalesce(span.name, concat(code.namespace, ".", code.function)),
    span.kind
  }
| expand ips
```

## Client IP Analysis

### Client IP Count by Service

Analyze incoming client IPs with masking:

```dql
fetch spans, from:now() - 24h
| filter isNotNull(client.ip)

// Convert to structured IP type
| fieldsAdd client.ip = toIp(client.ip)

// Mask to not expose full IP
| fieldsAdd client.ip.masked = ipMask(client.ip, 16)

| fieldsAdd getNodeName(dt.smartscape.service)

| summarize {
    distinct_clients = countDistinct(client.ip),
    masked_client_ips=toString(arraySort(collectDistinct(client.ip.masked)))
  }, by: { k8s.namespace.name, dt.smartscape.service.name, span.kind }
| sort distinct_clients desc
```

### Geographic Distribution

Analyze client IPs by subnet:

```dql
fetch spans, from:now() - 6h
| filter isNotNull(client.ip)
| filter request.is_root_span == true

// Convert and mask IPs
| fieldsAdd client.ip = toIp(client.ip)
| fieldsAdd client.subnet = ipMask(client.ip, 24)

| summarize {
    requests=count(),
    unique_clients=countDistinct(client.ip)
  }, by: { client.subnet, endpoint.name }
| sort requests desc
| limit 100
```

## IP Functions

### Working with IP Addresses

DQL provides IP manipulation functions:

```dql
fetch spans
| filter isNotNull(client.ip)

// Convert string to IP type
| fieldsAdd client.ip = toIp(client.ip)

// Mask IP to subnet (bits to keep)
| fieldsAdd subnet_24 = ipMask(client.ip, 24)  // /24 network
| fieldsAdd subnet_16 = ipMask(client.ip, 16)  // /16 network

| fields client.ip, subnet_24, subnet_16
| limit 10
```

## Network Attributes

Common networking attributes:

- `server.address` - Server hostname/address for outgoing calls
- `server.port` - Server port
- `server.resolved_ips` - Array of IPs from DNS resolution
- `client.ip` - Client IP address for incoming calls
- `client.port` - Client port
- `network.protocol.name` - Protocol name (e.g., http, amqp)
- `network.transport` - Transport layer (tcp, udp, pipe)

## Service Communication Map

### Identify Service Dependencies

Map service-to-service communication:

```dql
fetch spans, from:now() - 1h
| filter span.kind == "client"
| filter isNotNull(server.address)

| fieldsAdd caller_service = getNodeName(dt.smartscape.service)

| summarize {
    calls=count(),
    avg_duration=avg(duration),
    resolved_ips=toString(collectDistinct(server.resolved_ips))
  }, by: {
    caller_service,
    server.address,
    server.port
  }
| sort calls desc
| limit 50
```

## Best Practices

- **Use `toIp()`** to convert string IPs to structured IP type for IP functions
- **Use `ipMask()`** to mask IPs for privacy (specify bits to keep)
- **`server.resolved_ips` is an array** - use `expand` or `collectDistinct()` to work with values
- **Double expand** array of arrays: `| expand ips | expand ips`
- **Filter by `span.kind`** - "client" spans have `server.address`, "server" spans have `client.ip`
- **Convert to string** for display: `toString(arraySort(collectDistinct(...)))`
- **Combine with service context** using `getNodeName(dt.smartscape.service)`

---

**← Back to**: [Application Tracing Skill](../SKILL.md)
