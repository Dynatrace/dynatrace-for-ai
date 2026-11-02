# Hunt Spans

Search `fetch spans` for indicators of compromise across inbound (server root) spans and
outbound (client) spans in one combined pass. Matches IPs, Domains, and URLs.

## Contents

- [Supported IoC Types](#supported-ioc-types)
- [Combined Template (adapted from Threat Exposure Analysis dashboard, tile 31)](#combined-template-adapted-from-threat-exposure-analysis-dashboard-tile-31)
  - [Optional: per-direction grouping (higher-signal)](#optional-per-direction-grouping-higher-signal)
- [Default Timeframe and Widening](#default-timeframe-and-widening)
- [Secondary Observable Extraction](#secondary-observable-extraction)
- [Why Combined (Inbound + Outbound)](#why-combined-inbound--outbound)
- [IP Normalization](#ip-normalization)
- [Reading the Output](#reading-the-output)

## Supported IoC Types

| Type | Fields checked | Notes |
|---|---|---|
| IP | `client.ip`, `request_attribute.SourceIP`, `server.resolved_ips`, `server.address` (outbound only) | typed IP fields + `server.address` string cast with `toIp()`; cast IoC strings with `toIp()` before comparison; output is one row per matched observable and `span.kind` |
| Domain | `http.host`, `server.address`, `contains(url.full, domain)` | Includes hostnames. `server.address` is the field most spans populate (`http.host` / `url.domain` are often null) |
| URL | `contains(url.full, url)` | Substring match |

`request_attribute.SourceIP` is a **string** on some tenants and an IP on others, and a typed comparison against a string returns zero rows without any error. Always wrap it in `toIp()` as the template does (`toIp()` of a null or already-typed value is harmless); verified on a tenant where the uncast form returned 0 rows and the cast form matched 17,908 spans.

Emails and file hashes have no span field. Use `hunt-logs.md` for those.

## Combined Template (adapted from Threat Exposure Analysis dashboard, tile 31)

**Placeholders** (substitute before running; the template is executable afterwards):

- `<ip1>`, `<ip2>`: normalized IPs from `ioc-intake.md`, for example `192.0.2.11`. Each IP is one
  element in `IPs`; the typed `in(...)` comparisons take the whole array, so the filter does not grow
  per IP.
- `<domain1>`: normalized lowercase domain or hostname, for example `example.test`. One element in
  `Domains` per domain; matched against `http.host`, `server.address`, and `url.full`.
- `<url1>`: cleaned, DQL-escaped URL from `ioc-intake.md`, for example `http://example.test/a.php`.
  One element in `URLs` per URL; matched as a substring of `url.full`.
- Window: `from:now()-30m` is the default from `timeframe-gating.md`; use the window that file
  selects (anchored, or the 15m then 5m retry). Spans are high volume, so keep the window tight. On
  large IoC sets split the arrays into chunks and merge the rollups outside DQL, as in `hunt-logs-large-sets.md`.
- Omit a class with no values together with its array, its `in(...)`/`iAny(...)` filter lines, and its
  `matched*` line.

```dql-template
fetch spans, from:now()-30m
| filter in(span.kind, {"client", "server"})
| filter span.kind == "client" OR request.is_root_span == true
| fieldsAdd IPs     = array("<ip1>", "<ip2>"),
            Domains = array("<domain1>"),
            URLs    = array("<url1>")
| fieldsAdd IPs = iCollectArray(toIp(IPs[]))
| filter in(IPs, server.resolved_ips)
      OR in(toIp(request_attribute.SourceIP), IPs)
      OR in(toIp(client.ip), IPs)
      OR (span.kind == "client" AND in(toIp(server.address), IPs))
      OR in(http.host, Domains)
      OR in(server.address, Domains)
      OR iAny(contains(url.full, Domains[]))
      OR iAny(contains(url.full, URLs[]))
| fieldsAdd matchedIPs = arrayRemoveNulls(iCollectArray(
    if(toIp(client.ip) == IPs[]
       OR toIp(request_attribute.SourceIP) == IPs[]
       OR in(IPs[], server.resolved_ips)
       OR (span.kind == "client" AND toIp(server.address) == IPs[]),
       toString(IPs[])
    )))
| fieldsAdd matchedDomains = arrayRemoveNulls(iCollectArray(
    if(http.host == Domains[]
       OR server.address == Domains[]
       OR contains(url.full, Domains[]),
       Domains[]
    )))
| fieldsAdd matchedURLs = arrayRemoveNulls(iCollectArray(
    if(contains(url.full, URLs[]),
       URLs[]
    )))
| fieldsAdd `Matched observables` = arrayFlatten(arrayConcat(matchedIPs, matchedDomains, matchedURLs))
| expand `Matched observables`
| filter isNotNull(`Matched observables`)
| summarize {
    span_count          = count(),
    client_ips          = arrayRemoveNulls(collectDistinct(client.ip, maxLength: 100)),
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
    smartscape_containers = collectDistinct(dt.smartscape.container, maxLength: 100),
    aws_resource_ids    = collectDistinct(aws.resource.id, maxLength: 100),
    source_ips          = arrayRemoveNulls(collectDistinct(request_attribute.SourceIP, maxLength: 50)),
    resolved_ips        = arrayRemoveNulls(collectDistinct(server.resolved_ips, expand: true, maxLength: 50))
  }, by: {`Matched observables`, span.kind}
| fieldsAdd ips_capped = arraySize(source_ips) >= 49 OR arraySize(resolved_ips) >= 49 OR arraySize(client_ips) >= 99
| sort span_count desc
| limit 500
```

**Why this grouping.** The rollup is keyed by *what was hunted* (`Matched observables`) and
`span.kind`, so the row count is bounded by the IoC set (at most IoCs × 2 rows) and the
attacker addresses move into the `client_ips` collector. Grouping by `client.ip` made the
row count depend on the data (one row per client IP), so a busy inbound hunt silently lost
entities to the `limit`. A span that matches several IoCs is counted once per matched IoC
(`span_count` is per row, do not sum it across rows). If a result still returns exactly its
`limit` rows, treat it as possibly truncated and split the IoC chunk before reporting the
spans leg as complete. Outbound `client` spans are not root spans, so they are matched
without the `request.is_root_span` condition; the IoC filter keeps the scan selective.

`maxLength: 100` on `collectDistinct` calls is required to bound row size on
high-fanout groups.

Omit empty classes entirely. Include only IoC classes that contain values, but
always keep entity collectors in `summarize`. The descriptive collectors
(`k8s_*`, container/AWS resource refs) are source-dependent and collect as `[null]`
(not `[]`) when absent (e.g. non-Kubernetes spans) — harmless, so keep them for
Kubernetes/cloud coverage. To test emptiness, use `arraySize(arrayRemoveNulls(arr)) == 0`;
`isNull(arr)` and `arraySize(arr) == 0` are both false for `[null]`.

### Optional: per-direction grouping (higher-signal)

The combined default groups by `{Matched observables, span.kind}`. When you want direction-
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

The spans rollup already carries the candidate IPs, so no separate query is needed
and no raw span rows are fetched: `source_ips` (`request_attribute.SourceIP`),
`resolved_ips` (`server.resolved_ips`), and `client_ips` (`client.ip`). After the hunt,
take `source_ips` and `resolved_ips` from every matched row, drop IPs already in the primary
IoC list and private / loopback / link-local addresses (`ipIsPrivate`, `ipIsLoopback`,
`ipIsLinkLocal`), and queue the rest as derived IPs. `client_ips` on a row matched by a
Domain or URL are the visitors or callers of that host, not relay addresses: report their
count (and the public ones the user may want to follow up) but do not queue them for the
re-hunt unless the user asks. On a row matched by an IP IoC, `client_ips` is **not** guaranteed
to be only the hunted IP: the IP filter also matches `request_attribute.SourceIP`,
`server.resolved_ips` and `server.address`, so a span can match through one of those while
carrying a different `client.ip`. For IP-matched rows, apply the same filters to `client_ips`
(drop the primary IoCs and private / loopback / link-local addresses) and queue the net-new
public ones as derived IPs too.
Provenance for the report is the row's `{Matched observables, span.kind}` group plus the
column the IP came from.

**Saturation.** The three IP collectors are capped (`maxLength` 50, 50 and 100), and the 500-row limit
does not signal it. `ips_capped` is `true` when a collector is within one slot of its cap. A row with
`ips_capped == true` has an incomplete secondary extraction: follow
`secondary-observable-extraction.md` § Capped collectors (it also covers the span re-hunt, which
reuses this template).

Derived IPs feed the same derived-IP queue as the log-extracted secondaries. Apply
the same policy: deduplicate, validate, re-hunt at the same window/scope. See
`secondary-observable-extraction.md`.

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

`server.resolved_ips`, `client.ip`, and `request_attribute.SourceIP` are IP fields whose type
can differ per tenant (`client.ip` is a string on some tenants and an IP on others, and a typed
comparison against a string returns zero rows without any error). Cast both sides with `toIp()`
before comparison: the IoC strings and the span field.

`server.address` is a string field (outbound/client spans only) that can hold
an IP address or a hostname. Cast it with `toIp(server.address)` before
comparing against the typed IPs array — `toIp()` returns null for hostname
values, so hostname-addressed spans are automatically skipped.

The snippet below is the typed-IP line of the template above; it is a fragment, not a standalone
query. `IPs` is the array of IoC strings defined by the preceding `fieldsAdd IPs = array(...)`.

```dql-snippet
| fieldsAdd IPs = iCollectArray(toIp(IPs[]))
```

## Reading the Output

| Column | Description |
|---|---|
| `Matched observables` | The IoC value this row is about (group key; one row per IoC and `span.kind`) |
| `span.kind` | `client` outbound, `server` inbound |
| `ips_capped` | `true` when `source_ips`, `resolved_ips` or `client_ips` reached its collector cap; the IP lists of that row may be incomplete (see `secondary-observable-extraction.md` § Capped collectors) |
| `client_ips` | Distinct `client.ip` values on the matched spans (the attacker/source addresses for inbound hits; on an IP-matched row it can include a net-new public address when the span matched through another IP field) |
| `span_count` | Number of spans matching this IoC (a span matching several IoCs is counted in each row) |
| `spans` | Matched span names |
| `services` | Dynatrace service display names |
| `process_groups` | Classic IDs; join key for RVA/CVE `affected_entity.id` |
| `smartscape_services` | 3rd-gen IDs; join key for FINDING `dt.smartscape_source.id` |
| `hosts` | `host.name` values for matched spans |
| `k8s_namespaces` / `k8s_workloads` / `k8s_clusters` / `k8s_pods` / `k8s_nodes` | Kubernetes context when spans originate in K8s |
| `smartscape_containers` / `aws_resource_ids` | `dt.smartscape.container` (3rd-gen `CONTAINER-*`) and `aws.resource.id` values when available |
| `source_ips` / `resolved_ips` | Distinct `request_attribute.SourceIP` and `server.resolved_ips` values on matched spans — the secondary-IP candidates (empty when the attribute is absent) |
