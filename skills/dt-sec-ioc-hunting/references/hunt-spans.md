# Hunt Spans

Search `fetch spans` for indicators of compromise across inbound (server) and
outbound (client) root spans in one combined pass. Matches IPs, Domains, and
URLs.

## Supported IoC Types

| Type | Fields checked | Notes |
|---|---|---|
| IP | `client.ip`, `request_attribute.SourceIP`, `server.resolved_ips`, `server.address` (outbound only) | typed IP fields + `server.address` string cast with `toIp()`; cast IoC strings with `toIp()` before comparison; output is grouped by `span.kind` |
| Domain | `http.host`, `contains(url.full, domain)` | Includes hostnames |
| URL | `contains(url.full, url)` | Substring match |

Emails and file hashes have no span field. Use `hunt-logs.md` for those.

## Combined Template (adapted from Threat Exposure Analysis dashboard, tile 31)

```dql-template
fetch spans, from:now()-30m
| filter request.is_root_span == true
| filter in(span.kind, {"client", "server"})
| fieldsAdd IPs     = array("<ip1>", "<ip2>"),
            Domains = array("<domain1>"),
            URLs    = array("<url1>")
| fieldsAdd IPs = iCollectArray(toIp(IPs[]))
| filter in(IPs, server.resolved_ips)
      OR in(request_attribute.SourceIP, IPs)
      OR in(client.ip, IPs)
      OR (span.kind == "client" AND in(toIp(server.address), IPs))
      OR in(http.host, Domains)
      OR iAny(contains(url.full, Domains[]))
      OR iAny(contains(url.full, URLs[]))
| fieldsAdd matchedIPs = arrayRemoveNulls(iCollectArray(
    if(client.ip == IPs[]
       OR request_attribute.SourceIP == IPs[]
       OR in(IPs[], server.resolved_ips)
       OR (span.kind == "client" AND toIp(server.address) == IPs[]),
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
    hosts               = collectDistinct(host.name, maxLength: 100),
    k8s_namespaces      = collectDistinct(k8s.namespace.name, maxLength: 100),
    k8s_workloads       = collectDistinct(k8s.workload.name, maxLength: 100),
    k8s_clusters        = collectDistinct(k8s.cluster.name, maxLength: 100),
    k8s_pods            = collectDistinct(k8s.pod.name, maxLength: 100),
    k8s_nodes           = collectDistinct(k8s.node.name, maxLength: 100),
    container_group_instances = collectDistinct(dt.entity.container_group_instance, maxLength: 100),
    ec2_instances       = collectDistinct(dt.entity.ec2_instance, maxLength: 100)
  }, by: {span.kind, client.ip}
| sort span_count desc
| limit 50
```

`maxLength: 100` on `collectDistinct` calls is required to bound row size on
high-fanout groups.

Omit empty classes entirely. Include only IoC classes that contain values, but
always keep entity collectors in `summarize`. The descriptive collectors
(`k8s_*`, container/EC2 entity refs) are source-dependent and collect as empty
arrays when absent (e.g. non-Kubernetes spans) — harmless, so keep them for
Kubernetes/cloud coverage.

### Optional: per-direction grouping (higher-signal)

The combined default groups by `{span.kind, client.ip}`. When you want direction-
specific rollups, split the summarize into two passes over the same matched set:

- **Inbound (exploitation attempts):** `by: {client.ip, request_attribute.SourceIP}`
  — collect target endpoints/URIs (`endpoint.name`, `url.path`, `http.request.header.host`).
- **Outbound (C2 / exfil):** `by: {endpoint.name, url.full, server.resolved_ips}`
  — collect the calling entities.

Keep the same entity collectors. Use the combined default unless a hunt
specifically needs inbound vs outbound separation.

## Default Timeframe and Widening

Default: `from:now()-30m`.

For hunts derived from timestamped detections/logs/events, use the anchored
window rules in `timeframe-gating.md` → "Event-Anchored Hunts".

Spans are high volume. Even 1h can hit Grail execution limits and produce
incomplete results.

If you see `FETCH_EXEC_TIME_LIMIT`, **automatically retry at 15m, then 5m** (no
user approval required — narrowing, not widening). Only mark the result
INCONCLUSIVE if 5m also times out. Do not treat INCONCLUSIVE as no-match.

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

`server.address` is a string field (outbound/client spans only) that can hold
an IP address or a hostname. Cast it with `toIp(server.address)` before
comparing against the typed IPs array — `toIp()` returns null for hostname
values, so hostname-addressed spans are automatically skipped.

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
| `k8s_namespaces` / `k8s_workloads` / `k8s_clusters` / `k8s_pods` / `k8s_nodes` | Kubernetes context when spans originate in K8s |
| `container_group_instances` / `ec2_instances` | Container/EC2 entity refs when available |
