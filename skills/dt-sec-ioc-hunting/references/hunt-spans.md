# Hunt Spans

Search `fetch spans` for indicators of compromise across inbound (server) and
outbound (client) root spans in one combined pass. Matches IPs, Domains, and
URLs.

## Supported IoC Types

| Type | Fields checked | Notes |
|---|---|---|
| IP | `client.ip`, `request_attribute.SourceIP`, `server.resolved_ips` | typed IP fields; cast IoC strings with `toIp()` before comparison; output is grouped by `span.kind` |
| Domain | `http.host`, `contains(url.full, domain)` | Includes hostnames |
| URL | `contains(url.full, url)` | Substring match |

Emails and file hashes have no span field. Use `hunt-logs.md` for those.

## Combined Template (adapted from Threat Exposure Analysis dashboard, tile 31)

```dql-template
fetch spans, from:now()-15m
| filter request.is_root_span == true
| filter in(span.kind, {"client", "server"})
| fieldsAdd IPs     = array("<ip1>", "<ip2>"),
            Domains = array("<domain1>"),
            URLs    = array("<url1>")
| fieldsAdd IPs = iCollectArray(toIp(IPs[]))
| filter in(IPs, server.resolved_ips)
      OR in(request_attribute.SourceIP, IPs)
      OR in(client.ip, IPs)
      OR in(http.host, Domains)
      OR iAny(contains(url.full, Domains[]))
      OR iAny(contains(url.full, URLs[]))
| fieldsAdd matchedIPs = arrayRemoveNulls(iCollectArray(
    if(client.ip == IPs[]
       OR request_attribute.SourceIP == IPs[]
       OR in(IPs[], server.resolved_ips),
       toString(IPs[])
    )))
| fieldsAdd matchedDomains = arrayRemoveNulls(iCollectArray(
    if(http.host == Domains[]
       OR contains(url.full, Domains[]),
       Domains[]
    )))
| fieldsAdd matchedURLs = arrayRemoveNulls(iCollectArray(
    if(contains(url.full, URLs[]),
       URLs[]
    )))
| fieldsAdd `Matched observables` = arrayFlatten(arrayConcat(matchedIPs, matchedDomains, matchedURLs))
| summarize {
    span_count          = count(),
    matched_observables = arrayDistinct(arrayRemoveNulls(collectArray(`Matched observables`, expand: true, maxLength: 1000))),
    spans               = collectDistinct(span.name, maxLength: 100),
    services            = collectDistinct(dt.service.name, maxLength: 100),
    process_groups      = collectDistinct(dt.process_group.id, maxLength: 100),
    smartscape_services = collectDistinct(dt.smartscape.service, maxLength: 100),
    hosts               = collectDistinct(host.name, maxLength: 100)
  }, by: {span.kind, client.ip}
| sort span_count desc
| limit 50
```

`maxLength: 100` on `collectDistinct` calls is required to bound row size on
high-fanout groups.

Omit empty classes entirely. Include only IoC classes that contain values, but
always keep entity collectors in `summarize`.

## Default Timeframe and Widening

Default: `from:now()-15m`.

For hunts derived from timestamped detections/logs/events, use the anchored
window rules in `timeframe-gating.md` → "Event-Anchored Hunts".

Spans are high volume. Even 1h can hit Grail execution limits and produce
incomplete results.

If you see `FETCH_EXEC_TIME_LIMIT`, mark result as INCONCLUSIVE. Do not treat as
no-match.

## Secondary Observable Extraction

After collecting matched span records, check whether any matched span exposes
additional IPs in request attributes or span fields that were not in the primary
IoC list — for example `request_attribute.SourceIP` values on spans that matched
via `client.ip`, or additional IP-valued `request_attribute.*` fields surfaced
in the summarized output.

Extracted IPs feed the same derived-IP queue as log-extracted secondaries. Apply
the same policy: deduplicate, validate, exclude RFC 1918 / loopback, re-hunt at
the same window/scope. See `secondary-observable-extraction.md`.

Widen only when the query completed and returned zero rows, and only with user
approval. Follow `timeframe-gating.md`.

## Why Combined (Inbound + Outbound)

Single-query combined mode:

- Covers inbound exploitation attempts and outbound C2 communication.
- Matches validated dashboard logic.
- Keeps inbound/outbound separable using `by: {span.kind, client.ip}`.

Split into separate passes only if large IoC arrays cause timeout or scan-limit
issues.

## IP Normalization

`server.resolved_ips`, `client.ip`, and `request_attribute.SourceIP` are typed
IP fields. Cast string IoCs with `toIp()` before comparison.

```dql-snippet
| fieldsAdd IPs = iCollectArray(toIp(IPs[]))
```

## Reading the Output

| Column | Description |
|---|---|
| `span.kind` | `client` outbound, `server` inbound |
| `client.ip` | Source IP |
| `span_count` | Number of spans matching at least one IoC |
| `matched_observables` | Distinct IoC values matched in this group |
| `spans` | Matched span names |
| `services` | Dynatrace service display names |
| `process_groups` | Classic IDs; join key for RVA/CVE `affected_entity.id` |
| `smartscape_services` | 3rd-gen IDs; join key for FINDING `dt.smartscape_source.id` |
| `hosts` | `host.name` values for matched spans |
