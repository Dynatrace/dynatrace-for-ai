# Hunt Logs

Search `fetch logs` for indicators of compromise across supported IoC types:
IPs, Domains, URLs, Emails, and file Hashes (md5/sha1/sha256). Use
`matchesPhrase(content, "<ioc>")` as the broad, unscoped prefilter, then use
`contains(content, <ioc>)` only after that prefilter to populate matched
observable columns.

## Supported IoC Types

| Type | Matched via | Notes |
|---|---|---|
| IPs | `matchesPhrase(content, "<ip>")` prefilter; `contains` for result extraction | Plain string; no `toIp()` needed |
| Domains | `matchesPhrase(content, "<domain>")` prefilter; `contains` for result extraction | Includes hostnames |
| URLs | `matchesPhrase(content, "<url>")` prefilter; `contains` for result extraction | Exact URL phrase first; use domain/path components if URL tokenization is uncertain |
| Emails | `matchesPhrase(content, "<email>")` prefilter; `contains` for result extraction | |
| Hashes | `matchesPhrase(content, "<hash>")` prefilter; `contains` for result extraction | Algorithm-agnostic; pool md5/sha1/sha256 into one `Hashes` array |

Emails and hashes have no span field. Logs are their only hunt surface.

## Canonical Template (adapted from Threat Exposure Analysis dashboard, tile 28)

Adapt by replacing placeholder arrays with literal IoC values. Omit any
observable class with no values. The `matchesPhrase` prefilter must use literal
constants, not array expansion; generate one `matchesPhrase` clause per IoC and
join them with `or`. For large IoC sets, do not generate one huge query — see
"Large IoC Sets and Chunking" below.

```dql-template
fetch logs, from:now()-15m
| filter matchesPhrase(content, "<ip1>") or matchesPhrase(content, "<ip2>")
  or matchesPhrase(content, "<domain1>") or matchesPhrase(content, "<url1>")
  or matchesPhrase(content, "<email1>") or matchesPhrase(content, "<hash1>")
| fieldsAdd IPs     = array("<ip1>", "<ip2>"),
            Domains = array("<domain1>", "<domain2>"),
            URLs    = array("<url1>"),
            Emails  = array("<email1>"),
            Hashes  = array("<hash1>", "<hash2>")
| fieldsAdd matchedIPs     = arrayRemoveNulls(iCollectArray(if(contains(content, IPs[]),     IPs[])))
| fieldsAdd matchedDomains = arrayRemoveNulls(iCollectArray(if(contains(content, Domains[]), Domains[])))
| fieldsAdd matchedURLs    = arrayRemoveNulls(iCollectArray(if(contains(content, URLs[]),    URLs[])))
| fieldsAdd matchedEmails  = arrayRemoveNulls(iCollectArray(if(contains(content, Emails[]),  Emails[])))
| fieldsAdd matchedHashes  = arrayRemoveNulls(iCollectArray(if(contains(content, Hashes[]),  Hashes[])))
| fieldsAdd `Matched observables` = arrayConcat(matchedIPs, matchedDomains, matchedURLs, matchedEmails, matchedHashes)
| fields timestamp, log.source, loglevel, status, `Matched observables`,
         dt.smartscape_source.id, dt.smartscape_source.type, dt.process_group.id,
         host.name, k8s.namespace.name, k8s.pod.name, content
| limit 50
```

## Large IoC Sets and Chunking

When the IoC list is large, one `matchesPhrase(... ) or matchesPhrase(... )`
filter can become too long or too complex. Do **not** build a single DQL query
with hundreds of `or` clauses. Split the hunt into smaller DQL chunks and merge
the results outside DQL.

Default chunking policy:
- Deduplicate and normalize IoCs before chunking.
- Use **25 IoCs per chunk** as a conservative default.
- Use **10 IoCs per chunk** for mostly long URLs, emails, or hashes, or after a
  query-length / parse / complexity failure.
- Keep the same timeframe, bucket filter, and optional entity scope across all
  chunks so results remain comparable.
- Run chunks sequentially by default. If the runtime supports concurrency, use
  only small batches (for example 2–3 parallel queries) and report that chunks
  were run independently.

Each chunk repeats the canonical pattern with only that chunk's IoCs:

```dql-template
fetch logs, from:now()-15m
| filter matchesPhrase(content, "<chunk-ip1>") or matchesPhrase(content, "<chunk-domain1>")
| fieldsAdd IPs = array("<chunk-ip1>"), Domains = array("<chunk-domain1>")
| fieldsAdd matchedIPs     = arrayRemoveNulls(iCollectArray(if(contains(content, IPs[]),     IPs[])))
| fieldsAdd matchedDomains = arrayRemoveNulls(iCollectArray(if(contains(content, Domains[]), Domains[])))
| fieldsAdd `Matched observables` = arrayConcat(matchedIPs, matchedDomains)
| fields timestamp, log.source, loglevel, status, `Matched observables`,
         dt.smartscape_source.id, dt.smartscape_source.type, dt.process_group.id,
         host.name, k8s.namespace.name, k8s.pod.name, content
| limit 50
```

Completion semantics:
- **Overall no-match** is valid only if every chunk completes and returns zero rows.
- **Rows in any chunk** are valid evidence; report the chunk and window used.
- **Any chunk with `FETCH_EXEC_TIME_LIMIT`, parse/query-length failure, or other
  execution failure** makes only that chunk's IoCs INCONCLUSIVE. Retry the failed
  chunk once with a smaller chunk size before asking the user whether to narrow
  scope or accept partial INCONCLUSIVE.
- If a chunk returns exactly the `limit`, treat that chunk as possibly truncated;
  increase the limit or split that chunk further before claiming complete results.
- Keep a chunk summary in the final report: chunk count, chunk size, completed
  chunks, failed/inconclusive chunks, matched IoCs, unmatched IoCs, and time window.

## Default Timeframe and Widening

Default: `from:now()-15m`.

For hunts derived from timestamped detections/logs/events, use the anchored
window rules in `timeframe-gating.md` → "Event-Anchored Hunts".

If you see `FETCH_EXEC_TIME_LIMIT`:
- Mark the result as **INCONCLUSIVE**. Do not treat as no-match.
- First verify that the query uses the `matchesPhrase` prefilter form above.
  The older `iAny(contains(content, allObservables[]))` form is too expensive
  for high-volume unscoped hunts.
- If entity context is available from a prior hunt phase (spans, security
  events, user-named service/namespace/host), offer a scoped follow-up —
  see "Scoped vs Unscoped Hunting" below.
- Do NOT invent a scope. Do not silently re-run with a made-up filter.
- Ask the user whether they want to narrow by entity or accept INCONCLUSIVE.

Widen only when the 15m pass returns zero rows and the user approves.
Follow `timeframe-gating.md` for exact expansion protocol.

Suggested sequence:
`15m -> 1h -> 3h -> 24h -> 7d (only if explicitly requested)`.

## Scoped vs Unscoped Hunting

### Unscoped hunt (default — broad discovery)

**Use when**: the user has only IoCs and no service, host, namespace, or cluster
context. The goal is to discover *all* places those indicators appear.

Run the canonical template without an entity pre-filter. Keep the
`matchesPhrase(content, "<ioc>")` prefilter because it preserves the all-log
lookup domain while using the tokenized/full-text path for speed. Accept the
following outcomes:

| Outcome | Meaning | Action |
|---|---|---|
| Rows returned | IoC matched in logs | Report matched observables and entity IDs |
| Zero rows | No match in this window | Valid result; ask approval before widening |
| `FETCH_EXEC_TIME_LIMIT` | Scan too large to complete | **INCONCLUSIVE** — not no-match. Ask user whether to narrow scope or accept INCONCLUSIVE. |

> **Do NOT invent a scope.** If the user has not named a service, namespace,
> host, or cluster, do not add one silently. Adding an arbitrary filter shrinks
> the lookup domain and can miss evidence outside that scope.

### Scoped hunt (optional — speed optimization when entity context exists)

**Use only when** entity context already exists:
- A prior hunt phase (spans, security events) identified an affected entity.
- The user explicitly named a service, namespace, host, or cluster.
- The threat report specifies a particular component or product.

**Trade-off**: faster (validated: 43 GB / 15-minute window timed out unscoped,
completed in 179 ms scoped), but coverage is limited to the selected scope.
Evidence outside that scope will not appear.

Available scope filters (insert immediately after `fetch logs, from:now()-15m`,
before the `fieldsAdd` IoC arrays):

- K8s namespace: `| filter k8s.namespace.name == "production"`
- K8s cluster: `| filter k8s.cluster.name == "aks-live"`
- Multiple namespaces: `| filter in(k8s.namespace.name, array("ns-a", "ns-b"))`
- Host: `| filter host.name == "my-host-01"`
- Log source / service: `| filter log.source == "my-service"`
- Process group: `| filter dt.process_group.id == "PROCESS_GROUP-XXXX"`

```dql-template
fetch logs, from:now()-15m
| filter k8s.namespace.name == "<namespace>"
| filter matchesPhrase(content, "<ip1>") or matchesPhrase(content, "<domain1>")
| fieldsAdd IPs = array("<ip1>"), Domains = array("<domain1>")
| fieldsAdd matchedIPs     = arrayRemoveNulls(iCollectArray(if(contains(content, IPs[]),     IPs[])))
| fieldsAdd matchedDomains = arrayRemoveNulls(iCollectArray(if(contains(content, Domains[]), Domains[])))
...
```

## Notes

- `contains` is case-sensitive by default. For mixed-case types (for example
domains, emails), normalize IoCs to lowercase before injection or use
`contains(content, x, caseSensitive:false)`.
- `matchesPhrase` parameters must be constants. Do not write
  `matchesPhrase(content, allObservables[])`; DQL rejects it because the phrase
  parameter must be constant. Generate explicit `or` clauses from the IoC list.
- For hundreds of IoCs, split into chunks. A single query with hundreds of literal
  `matchesPhrase` clauses may hit query length or complexity limits even though
  each individual phrase lookup is efficient.
- `contains` performs substring matching, so short IoCs (especially IPs) can match longer tokens (e.g., `192.0.2.1` inside `192.0.2.10`). Treat matches as leads and validate in context before concluding exposure.
- Scan cost can be very high if the query falls back to raw `contains(content, ...)` over
  all logs. Keep windows tight and deduplicate IoCs. Add a scope filter only when entity
  context is already known (see "Scoped vs Unscoped Hunting") — uninstructed scoping
  narrows the lookup domain.
- Pool all hash algorithms into a single `Hashes` array.
- Omit empty classes entirely. Remove their `fieldsAdd`, `arrayConcat`, and
  `matchedX` expressions.
- Keep trailing entity-identifier fields even when class-specific fields are
  omitted so matched rows still carry join keys.
- Entity identifiers are source-dependent in logs. API-ingested logs can leave
  entity IDs null. Treat such rows as valid perimeter evidence, not query errors.

## Output Columns

| Column | Description |
|---|---|
| `timestamp` | Log entry timestamp |
| `log.source` | Source service or entity |
| `loglevel` | Log severity |
| `status` | HTTP or process status if present |
| `Matched observables` | IoC values matched in this log line |
| `dt.smartscape_source.id` | 3rd-gen ID; joins FINDING `dt.smartscape_source.id` |
| `dt.smartscape_source.type` | Entity type for `dt.smartscape_source.id` |
| `dt.process_group.id` | Classic `PROCESS_GROUP-<hex>` ID; joins RVA/CVE `affected_entity.id` |
| `host.name` | Host name emitting the log |
| `k8s.namespace.name` / `k8s.pod.name` | Kubernetes namespace and pod when available |
| `content` | Raw log line |

## Secondary Observable Extraction

After collecting matched log records, inspect every matched record's `content`
for additional IPs in proxy and relay headers and structured fields before
scoring. This step is **mandatory and automatic** — do not wait for user prompting.

**Where to look** (inside matched `content`):

- HTTP headers: `X-Forwarded-For`, `Forwarded` (`for=...`), `X-Real-IP`,
  `X-Client-IP`, `True-Client-IP`, `CF-Connecting-IP`, `Fastly-Client-IP`,
  `Akamai-True-Client-IP`.
- Structured JSON fields: `clientIP`, `src_ip`, `source.ip`, `remote_addr`,
  `actor.ip`, `xff`.

**Policy:** Deduplicate extracted IPs against already-hunted values, validate
that they are valid IPv4/IPv6, exclude RFC 1918 / loopback, then re-hunt using
the same window and scope. See `secondary-observable-extraction.md` for the full
extraction policy, recursion guard, cap, and reporting requirements.

If a secondary IP came from a URL-encoded or escaped header blob, percent-decode
the matched content before extraction and preserve the raw header as provenance.
For the log re-hunt, run the canonical `matchesPhrase(content, "<ip>")` pass
first. If it returns zero but the IP was already observed in encoded matched
evidence, run the bounded supplemental `contains(content, "<ip>")` verification
described in `secondary-observable-extraction.md`.
