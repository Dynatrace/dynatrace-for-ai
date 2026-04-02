# Request Timing Analysis

Analyze W3C Resource Timing data to diagnose WHERE latency occurs in frontend requests.

**Data Source:** `fetch user.events` with `characteristics.has_request == true`

**Key Timing Phases (all in nanoseconds, relative to `performance.time_origin`):**

- `performance.domain_lookup_start/end` - DNS resolution
- `performance.connect_start/end` - TCP connection
- `performance.secure_connection_start` - TLS handshake start
- `performance.request_start` - Request sent to server
- `performance.response_start` - First byte received (TTFB)
- `performance.response_end` - Download complete

## Request Timing Breakdown

Analyze timing phases for slow requests:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| filter duration > 1s
| fieldsAdd
    dns_time = performance.domain_lookup_end - performance.domain_lookup_start,
    connect_time = performance.connect_end - performance.connect_start,
    tls_time = performance.connect_end - performance.secure_connection_start,
    server_time = performance.response_start - performance.request_start,
    download_time = performance.response_end - performance.response_start
| summarize
    avg_dns = avg(dns_time),
    avg_connect = avg(connect_time),
    avg_tls = avg(tls_time),
    avg_server = avg(server_time),
    avg_download = avg(download_time),
    request_count = count(),
    by: {url.domain}
| sort avg_server desc
| limit 20
```

**Use Case:** Identify bottleneck phase (DNS, connection, server, download).

## Third-Party Resource Performance

Compare first-party vs third-party resource timing:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| summarize
    avg_duration = avg(duration),
    p75_duration = percentile(duration, 75),
    request_count = count(),
    by: {url.provider, url.domain}
| filter request_count > 50
| sort p75_duration desc
| limit 30
```

**Use Case:** Identify slow third-party resources impacting page performance.

## HTTP Protocol Performance

Analyze performance by HTTP protocol version:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| summarize
    avg_duration = avg(duration),
    p90_duration = percentile(duration, 90),
    request_count = count(),
    by: {performance.next_hop_protocol}
| sort request_count desc
```

**Use Case:** Compare HTTP/1.1 vs HTTP/2 vs HTTP/3 performance.

## Request Initiator Analysis

Analyze performance by request type:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| summarize
    avg_duration = avg(duration),
    p75_duration = percentile(duration, 75),
    avg_size = avg(performance.transfer_size),
    request_count = count(),
    by: {performance.initiator_type}
| sort request_count desc
```

**Use Case:** Compare API calls (xmlhttprequest/fetch) vs static resources.

## Response Size Analysis

Identify oversized responses:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| filter performance.transfer_size > 100000
| fieldsAdd
    compression_ratio = if(performance.encoded_body_size > 0,
        toDouble(performance.decoded_body_size) / toDouble(performance.encoded_body_size),
        else: 1.0)
| summarize
    avg_transfer_size = avg(performance.transfer_size),
    avg_compression_ratio = avg(compression_ratio),
    request_count = count(),
    by: {url.domain, url.path}
| sort avg_transfer_size desc
| limit 20
```

**Use Case:** Find large payloads and compression opportunities.

## Render-Blocking Resources

Identify resources blocking page render:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| filter performance.render_blocking_status == "blocking"
| summarize
    avg_duration = avg(duration),
    request_count = count(),
    by: {url.domain, url.path, performance.initiator_type}
| sort avg_duration desc
| limit 20
```

**Use Case:** Optimize critical rendering path.

## ISP Performance Analysis

Identify network provider issues:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_request == true
| summarize
    avg_duration = avg(duration),
    p90_duration = percentile(duration, 90),
    request_count = count(),
    by: {client.isp, geo.country.iso_code}
| filter request_count > 100
| sort p90_duration desc
| limit 20
```

**Use Case:** Detect ISP-specific performance degradation.
