# Hunt Logs — Large IoC Sets and Dedicated SD Fields

Load this file when the retained IoC count exceeds the per-class chunk budget of `hunt-logs.md`, or
when the Dedicated-field IP pass applies. That section owns the conditions; the other load gates
(`SKILL.md`, `hunt-logs.md`) point to it. Small hunts that meet none of them stay on the content-only
canonical template and do not need this file.

## Contents

- [Large IoC Sets and Chunking](#large-ioc-sets-and-chunking)
- [Dedicated SD Fields](#dedicated-sd-fields)
  - [Dedicated-field IP pass (on request, tenant-populated, or scoped fallback)](#dedicated-field-ip-pass-on-request-tenant-populated-or-scoped-fallback)

## Large IoC Sets and Chunking

When the IoC list is large, one `matchesPhrase(... ) or matchesPhrase(... )`
filter can become too long or too complex. Do **not** build a single DQL query
with hundreds of `or` clauses. Split the hunt into smaller DQL chunks and merge
the results outside DQL.

Default chunking policy:
- Deduplicate and normalize IoCs before chunking.
- Size chunks by a **clause budget**, not a flat IoC count. The canonical filter ([hunt-logs.md](hunt-logs.md)) emits
  several `or` clauses per IoC, and DQL rejects a filter above roughly 75 clauses
  (`EXPRESSION_TOO_MANY_SUB_EXPRESSIONS`, 250 sub-expressions) or ~100 clauses
  (`EXPRESSION_TOO_DEEPLY_NESTED`). Keep every chunk at **≤ 60 `or` clauses**:

  | IoC class | Clauses per IoC | Max IoCs in a single-class chunk |
  |---|---|---|
  | IP, content pass | 1 (`content`) | 60 |
  | IP, dedicated-field pass | 2 (`client.ip`, `actor.ips`) | 30 |
  | Domain / hostname | 3 (`content`, `url.domain`, `server.address`) | 20 |
  | URL | 2 (`content`, `url.full`) | 30 |
  | Hash, email | 1 (`content`) | 60 |

  The 250-sub-expression limit counts every operator and function call, so a clause is only as
  cheap as its shape: the content-pass `matchesPhrase` clauses fit 60 per chunk, and the
  dedicated pass only fits 30 IPs in the array form (see Dedicated-field IP pass).
  For a mixed chunk, add up clauses per IoC × count and stay ≤ 60 (for example 30 IPs +
  10 domains, 20 IPs + 10 domains + 10 hashes, or 40 IPs + 6 domains). Group IoCs by class first
  so chunks stay homogeneous where possible. The Secondary-IP extraction rollup ([hunt-logs-secondary.md](hunt-logs-secondary.md)) uses the
  same prefilter and the same budget. After a query-length / parse / complexity failure,
  halve the chunk and retry once.
- Keep the same timeframe and optional entity scope across all
  chunks so results remain comparable.
- Run chunks sequentially by default. If the runtime supports concurrency, use
  only small batches (for example 2–3 parallel queries) and report that chunks
  were run independently.

Each chunk repeats the canonical pattern of `hunt-logs.md` with only that chunk's IoCs.

**Placeholders** (substitute before running; the template is executable afterwards):

- `<chunk-ip1>`, `<chunk-domain1>`: the IoCs assigned to this chunk by the clause budget above,
  in the normalized form of `ioc-intake.md` (for example `192.0.2.11`, `example.test`). Add one
  clause and one array element per further value (domains: three clauses each), keeping the chunk
  at 60 clauses or fewer. Every chunk uses the same window and scope.

```dql-template
fetch logs, from:now()-30m
| filter matchesPhrase(content, "<chunk-ip1>") or matchesPhrase(content, "<chunk-domain1>")
  or matchesPhrase(url.domain, "<chunk-domain1>") or matchesPhrase(server.address, "<chunk-domain1>")
| fieldsAdd IPs = array("<chunk-ip1>"), Domains = array("<chunk-domain1>")
| fieldsAdd matchedIPs     = arrayRemoveNulls(iCollectArray(
    if(contains(content, IPs[]),
       IPs[]
    )))
| fieldsAdd matchedDomains = arrayRemoveNulls(iCollectArray(
    if(contains(content, Domains[])
       OR url.domain == Domains[]
       OR server.address == Domains[],
       Domains[]
    )))
| fieldsAdd `Matched observables` = arrayConcat(matchedIPs, matchedDomains)
| filter isNotNull(`Matched observables`[0])
| summarize by:{log.source},
  {
    log_count = count(),
    minTime   = takeMin(timestamp),
    maxTime   = takeMax(timestamp),
    matched_observables = arrayRemoveNulls(collectDistinct(`Matched observables`, expand:true, maxLength:1000)),
    source_entities    = arrayRemoveNulls(collectDistinct(dt.source_entity, expand:true, maxLength:100)),
    smartscape_sources = collectDistinct(dt.smartscape_source.id, maxLength:100),
    process_groups     = collectDistinct(dt.process_group.id, maxLength:100),
    hosts              = collectDistinct(host.name, maxLength:100),
    k8s_namespaces     = collectDistinct(k8s.namespace.name, maxLength:100),
    k8s_pods           = collectDistinct(k8s.pod.name, maxLength:100),
    k8s_workloads      = collectDistinct(k8s.workload.name, maxLength:100)
  }
| sort log_count desc
| limit 25
```

Use the same summarize tail across all chunks and merge the per-chunk rollups
outside DQL, keyed by `log.source`:

| Column | Merge rule |
|---|---|
| `log_count` | Sum across chunks. Exact when each line carries IoCs from one chunk; a line carrying IoCs from two chunks is counted twice, so report the sum as an upper bound if that is possible. |
| `minTime` / `maxTime` | Earliest `minTime` / latest `maxTime` |
| `matched_observables`, entity and context arrays | Union, drop `null`, de-duplicate |
| `loglevels` / `statuses` | Union |

A `log.source` that appears in only one chunk is copied unchanged. Merge chunks within one pass
this way. Do not sum `log_count` across the content pass and the dedicated-field pass: a line whose IP is
in both `content` and a typed field is matched by both. Instead report the two counts labelled
(`content pass: N lines`, `dedicated-field pass: M lines`) for every `log.source`, and treat the larger as
a lower bound for the distinct lines unless the overlap was measured (on a tenant where both passes matched
the same IP, the two `log_count` values were equal). For the rest of the row, merge across the passes the
way chunks are merged, including for a `log.source` and observable both passes returned: union
`matched_observables` and every entity and context array (a typed-field-only hit can sit on a different
host or entity than the content hit), and take the earliest `minTime` and latest `maxTime`. Dropping the
dedicated-pass row because the content pass already returned that source and IP loses that evidence.

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
  chunks, failed/inconclusive chunks, matched IoCs, the count of IoCs with no match
  (a number such as "N of M", not the list), and time window.

## Dedicated SD Fields

Structured log integrations (OpenPipeline, HTTP log class, audit log class) populate
dedicated SD fields. An IoC may appear only in a dedicated field and not be reflected in
the raw `content` string. The string fields (`url.domain`, `server.address`, `url.full`) are
indexed and are already part of the canonical filter; the typed IP fields (`actor.ips`,
`client.ip`) are not, and are checked in the separate pass below.

| Field | Type | IoC type | Log class | Notes |
|---|---|---|---|---|
| `actor.ips` | array (strings or ips) | IP | authentication, audit | Cast the elements: `in(toIp("<ip>"), iCollectArray(toIp(actor.ips[])))` per IP in fieldsAdd; for several IPs in the filter use `in(iCollectArray(toIp(actor.ips[])), array(toIp("<ip1>"), ...))` (see Dedicated-field IP pass) |
| `client.ip` | string or ip | IP | HTTP, audit | Cast the field: `toIp(client.ip) == toIp("<ip>")` per IP in fieldsAdd; for several IPs in the filter use `in(toIp(client.ip), array(toIp("<ip1>"), ...))` (see Dedicated-field IP pass) |
| `url.domain` | string | Domain | HTTP | String field — use `matchesPhrase(url.domain, "<domain>")` in filter; `url.domain == Domains[]` in fieldsAdd |
| `server.address` | string | Domain | HTTP | String field — use `matchesPhrase(server.address, "<domain>")` in filter; `server.address == Domains[]` in fieldsAdd |
| `url.full` | string | URL | HTTP | String field — use `matchesPhrase(url.full, "<url>")` in filter; `contains(url.full, URLs[])` in fieldsAdd |

The IP fields are strings on some tenants and ips on others, and a typed comparison against a
string returns zero rows without any error. Always cast the field with `toIp()` as the templates
do (`toIp()` of a null or already-typed value is harmless). Verified on a tenant where
`client.ip == toIp("<ip>")` and `in(toIp("<ip>"), actor.ips)` matched 0 rows while the cast forms
matched all 2 expected rows.

**Extension fields** (not in core log SD but may appear in some log sources):
- `host.ip` (OTel host resource attribute) — to hunt it in the dedicated-field IP pass, extend **both**
  places: add `or in(iCollectArray(toIp(host.ip[])), array(toIp("<ip1>"), ...))` to the filter, and
  `OR in(toIp(IPs[]), iCollectArray(toIp(host.ip[])))` to the `matchedIPs` condition. Adding it to the filter
  alone matches the line but leaves `Matched observables` empty, and the pass then drops it. A third typed
  field adds clauses: if the query fails with `EXPRESSION_TOO_MANY_SUB_EXPRESSIONS`, halve the chunk (30 to 15 IPs).

**When these fields are null:** For unstructured logs or integrations that do not
populate these fields, all dedicated-field clauses evaluate to false — no false positives.
Typed IP clauses still cost a full scan, which is why they live in their own pass. Always
run the `matchesPhrase(content, ...)` pass; it handles unstructured sources.

### Dedicated-field IP pass (on request, tenant-populated, or scoped fallback)

A separate query that checks only the typed IP fields. It is **not part of the default
unscoped hunt**. Run it, and load this file for it, in exactly these cases:

1. the user asks for dedicated-field coverage;
2. the environment is known to populate `client.ip` / `actor.ips` on logs. "Known" means the user said so,
   or evidence already in this hunt shows it (a matched log row or a detection rollup carrying those
   fields). The agent does not probe for it;
3. a scoped hunt's typed clauses hit `FETCH_EXEC_TIME_LIMIT`. The scoped template in `hunt-logs.md`
   already carries those clauses, so this pass is its fallback, with the same scope filter.

Without it, an IP that appears *only* in a dedicated field is not found; say so in the report.

Cost: a full scan of the window. Measured 2026-10-16 over 30m with 5 documentation-range IPs
(scales with log volume):

| Tenant | Content-only pass | Dedicated-field pass | Ratio |
|---|---|---|---|
| uan dev tenant, 30m (three runs) | 19–28 MB | 286–522 MB | 10–27× |
| demo.live, 30m | 7.3 GB | 331 GB | 46× |
| uan dev tenant, 3d | 1.05 GB | 51.4 GB | 49× |

An earlier, smaller dev tenant measured about 9×. On large tenants expect
`FETCH_EXEC_TIME_LIMIT` at 30m; apply the usual automatic retry at 15m then 5m and
state the narrower window. A timeout here never invalidates the content pass. Chunk by the
clause budget (2 clauses per IP, at most 30 IPs per chunk). Keep both IP lists in the array
form shown: the per-IP form (`toIp(client.ip) == toIp("<ip>") or in(toIp("<ip>"), ...)` repeated
per IP) costs about 12 sub-expressions per IP, ran with 20 IPs but failed at 30 IPs with
`EXPRESSION_TOO_MANY_SUB_EXPRESSIONS` (limit 250). Each `in(<typed field>, array(...))` is one
clause however many IPs it holds, and a 30-IP chunk in the array form ran. Both forms read the
same rows (same matches on a tenant where the typed fields are populated).

**Placeholders** (substitute before running; the template is executable afterwards):

- `<ip1>`, `<ip2>`: normalized IPs from `ioc-intake.md`, for example `192.0.2.11` (IPv6 in the
  compressed form). The same list appears in all three places: the `client.ip` array, the
  `actor.ips` array, and the `IPs` array. To hunt N IPs, add one `toIp("<ipN>")` element to each of
  the two filter arrays and one `"<ipN>"` element to `IPs`; the filter stays two clauses. Keep
  **at most 30 IPs per chunk** (the 2-clauses-per-IP budget in Large IoC Sets and Chunking), run
  the chunks with the same window and merge by `log.source`.
- Window: `from:now()-30m` is the default from `timeframe-gating.md`; on `FETCH_EXEC_TIME_LIMIT`
  use the 15m, then 5m retry that file prescribes.

```dql-template
fetch logs, from:now()-30m
| filter in(toIp(client.ip), array(toIp("<ip1>"), toIp("<ip2>")))
  or in(iCollectArray(toIp(actor.ips[])), array(toIp("<ip1>"), toIp("<ip2>")))
| fieldsAdd IPs = array("<ip1>", "<ip2>")
| fieldsAdd matchedIPs = arrayRemoveNulls(iCollectArray(
    if(toIp(client.ip) == toIp(IPs[]) OR in(toIp(IPs[]), iCollectArray(toIp(actor.ips[]))), IPs[])))
| fieldsAdd `Matched observables` = matchedIPs
| filter isNotNull(`Matched observables`[0])
| summarize by:{log.source},
  {
    log_count = count(),
    minTime   = takeMin(timestamp),
    maxTime   = takeMax(timestamp),
    matched_observables = arrayRemoveNulls(collectDistinct(`Matched observables`, expand:true, maxLength:1000)),
    loglevels = collectDistinct(loglevel, maxLength:20),
    statuses  = collectDistinct(status, maxLength:20),
    source_entities    = arrayRemoveNulls(collectDistinct(dt.source_entity, expand:true, maxLength:100)),
    smartscape_sources = collectDistinct(dt.smartscape_source.id, maxLength:100),
    process_groups     = collectDistinct(dt.process_group.id, maxLength:100),
    hosts              = collectDistinct(host.name, maxLength:100),
    k8s_namespaces     = collectDistinct(k8s.namespace.name, maxLength:100),
    k8s_pods           = collectDistinct(k8s.pod.name, maxLength:100)
  }
| sort log_count desc
| limit 25
```

**Domain matching on typed fields is exact.** `url.domain == "<domain>"` does not catch subdomains. If
subdomain coverage is needed, compare on a dot boundary: `url.domain == "<domain>" OR endsWith(url.domain, ".<domain>")`.
Never use `contains(url.domain, "<domain>")`: hunting `bad.com` would also match `bad.com.unrelated.net` and
`notbad.com`, and those hits would become exposure evidence for domains outside the indicator.
