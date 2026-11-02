# Hunt Logs

Search `fetch logs` for indicators of compromise across supported IoC types:
IPs, Domains, URLs, Emails, and file Hashes (md5/sha1/sha256). Use
`matchesPhrase(content, "<ioc>")` as the broad, unscoped prefilter, then use
`contains(content, <ioc>)` only after that prefilter to populate matched
observable columns.

## Contents

- [Supported IoC Types](#supported-ioc-types)
- [Canonical Template (adapted from Threat Exposure Analysis dashboard, tile 28)](#canonical-template-adapted-from-threat-exposure-analysis-dashboard-tile-28)
- [Drill-down (raw lines — explicit request only)](#drill-down-raw-lines--explicit-request-only)
- [Default Timeframe and Widening](#default-timeframe-and-widening)
- [Scoped vs Unscoped Hunting](#scoped-vs-unscoped-hunting)
  - [Unscoped hunt (default — broad discovery)](#unscoped-hunt-default--broad-discovery)
  - [Scoped hunt (optional — speed optimization when entity context exists)](#scoped-hunt-optional--speed-optimization-when-entity-context-exists)
- [Notes](#notes)
- [Output Columns](#output-columns)

Conditional material lives in two sibling files, loaded only when their trigger fires:

- [hunt-logs-secondary.md](hunt-logs-secondary.md) — **load automatically whenever this logs leg
  returned at least one matched row.** The Secondary-IP extraction rollup is mandatory and automatic
  after a match; skip this file only when the logs leg returned zero rows.
- [hunt-logs-large-sets.md](hunt-logs-large-sets.md) — load when the retained IoC count exceeds
  the per-class chunk budget, or when the Dedicated-field IP pass applies (conditions in that file's
  § Dedicated-field IP pass).

## Supported IoC Types

| Type | `content` prefilter | Dedicated SD fields | Notes |
|---|---|---|---|
| IPs | `matchesPhrase(content, "<ip>")` | `actor.ips` (array), `client.ip` (string or ip, tenant-dependent) | Content-only by default. The IP dedicated fields force a full scan and are checked by the separate Dedicated-field IP pass (see [hunt-logs-large-sets.md](hunt-logs-large-sets.md) § Dedicated SD Fields) |
| Domains | `matchesPhrase(content, "<domain>")` | `url.domain` (string), `server.address` (string) | Includes hostnames; exact match on dedicated fields |
| URLs | `matchesPhrase(content, "<url>")` | `url.full` (string) | Substring match on `url.full`; exact URL phrase first in content |
| Emails | `matchesPhrase(content, "<email>")` | — | Emails have no dedicated log SD field |
| Hashes | `matchesPhrase(content, "<hash>")` | — | Pool md5/sha1/sha256 into one `Hashes` array; no dedicated log SD field |

Emails and hashes have no span field. Logs are their only hunt surface.

## Canonical Template (adapted from Threat Exposure Analysis dashboard, tile 28)

Adapt by replacing placeholder arrays with literal IoC values. Omit any
observable class with no values.

**Prefilter rules:**
- `matchesPhrase` must use literal constants, not array expansion; generate one
  clause per IoC and join with `or`.
- For string dedicated fields (`url.domain`, `server.address`, `url.full`), use
  `matchesPhrase` so the tokenized index is used — not `contains` or equality.
- **IP clauses are content-only** (`matchesPhrase(content, "<ip>")`). The typed IP fields
  (`actor.ips`, `client.ip`) cannot use the content index, and OR-ing even one typed clause
  into the filter turns the whole query into a full scan. Measured 2026-10-16 over 30m with 5 IPs
  (scales with log volume), the typed pass scanned 10–27× the bytes of the content
  pass on the uan dev tenant (27.5 MB versus 286 MB in the latest run; 19–24 MB versus 437–522 MB in earlier runs), 46× on demo.live
  (7.3 GB versus 331 GB) and 49× over 3d on uan (1.05 GB versus 51.4 GB); an earlier small tenant
  showed about 9×. On a tenant larger than demo.live the typed pass approaches the 10 s
  `FETCH_EXEC_TIME_LIMIT`. Check the typed
  fields in the separate **Dedicated-field IP pass** (see [hunt-logs-large-sets.md](hunt-logs-large-sets.md) § Dedicated SD Fields), not here.
- Generate one clause per IoC per field.

For large IoC sets, do not generate one huge query — see "Large IoC Sets and
Chunking" in [hunt-logs-large-sets.md](hunt-logs-large-sets.md).

**Placeholders** (substitute before running; the template is executable afterwards):

- `<ip1>`, `<ip2>`: normalized IPs from `ioc-intake.md` (defanging removed), for example
  `192.0.2.11`. Each IP adds one `matchesPhrase(content, ...)` clause and one element in `IPs`.
- `<domain1>`, `<domain2>`: normalized lowercase domains and hostnames, for example
  `example.test`. Each domain adds three clauses (`content`, `url.domain`, `server.address`) and one
  element in `Domains`.
- `<url1>`: cleaned URL from `ioc-intake.md`, DQL-escaped (see Notes), for example
  `http://example.test/a.php`. Each URL adds two clauses (`content`, `url.full`) and one element in
  `URLs`.
- `<email1>`, `<hash1>`, `<hash2>`: lowercase email and md5/sha1/sha256 values from `ioc-intake.md`.
  Each adds one `content` clause and one element in `Emails` or `Hashes` (all hash algorithms share
  the one `Hashes` array).
- Window: `from:now()-30m` is the default decided by `timeframe-gating.md`; replace it only with
  the window that file selects (anchored window, or the 15m then 5m retry).

The filter clauses and the arrays must list the same values: a value in an array but not in the
filter can never match, and a clause without an array element matches lines that the `matched*`
collectors then drop. To scale to N values of a class, add one clause per value (per field for the
domain and URL fields) and one array element per value, then keep each chunk within the 60-clause
budget in "Large IoC Sets and Chunking" ([hunt-logs-large-sets.md](hunt-logs-large-sets.md); for example 60 hashes, 60 emails, 20 domains).

```dql-template
fetch logs, from:now()-30m
| filter matchesPhrase(content, "<ip1>") or matchesPhrase(content, "<ip2>")
  or matchesPhrase(content, "<domain1>") or matchesPhrase(content, "<domain2>")
  or matchesPhrase(content, "<url1>")
  or matchesPhrase(content, "<email1>")
  or matchesPhrase(content, "<hash1>") or matchesPhrase(content, "<hash2>")
  or matchesPhrase(url.domain, "<domain1>") or matchesPhrase(url.domain, "<domain2>")
  or matchesPhrase(server.address, "<domain1>") or matchesPhrase(server.address, "<domain2>")
  or matchesPhrase(url.full, "<url1>")
| fieldsAdd IPs     = array("<ip1>", "<ip2>"),
            Domains = array("<domain1>", "<domain2>"),
            URLs    = array("<url1>"),
            Emails  = array("<email1>"),
            Hashes  = array("<hash1>", "<hash2>")
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
| fieldsAdd matchedURLs    = arrayRemoveNulls(iCollectArray(
    if(contains(content, URLs[])
       OR contains(url.full, URLs[]),
       URLs[]
    )))
| fieldsAdd matchedEmails  = arrayRemoveNulls(iCollectArray(if(contains(content, Emails[]),  Emails[])))
| fieldsAdd matchedHashes  = arrayRemoveNulls(iCollectArray(if(contains(content, Hashes[]),  Hashes[])))
| fieldsAdd `Matched observables` = arrayConcat(matchedIPs, matchedDomains, matchedURLs, matchedEmails, matchedHashes)
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
    smartscape_types   = collectDistinct(dt.smartscape_source.type, maxLength:20),
    process_groups     = collectDistinct(dt.process_group.id, maxLength:100),
    hosts              = collectDistinct(host.name, maxLength:100),
    k8s_namespaces     = collectDistinct(k8s.namespace.name, maxLength:100),
    k8s_pods           = collectDistinct(k8s.pod.name, maxLength:100),
    k8s_workloads      = collectDistinct(k8s.workload.name, maxLength:100),
    k8s_clusters       = collectDistinct(k8s.cluster.name, maxLength:100),
    k8s_nodes          = collectDistinct(k8s.node.name, maxLength:100),
    smartscape_containers = collectDistinct(dt.smartscape.container, maxLength:100),
    aws_resource_ids   = collectDistinct(aws.resource.id, maxLength:100)
  }
| sort log_count desc
| limit 25
```

**Summarize-first (default).** The template rolls matched log lines up to **one
row per `log.source`**, collecting matched observables, entity identifiers, a
`log_count`, and first/last-seen timestamps — it does **not** return raw
`content`. This is the data-efficient default; every matched observable and entity
join key is preserved, so the exposure report stays complete (summarize-first ≠
truncation). Secondary IPs hidden in proxy/relay headers are extracted by the separate
**Secondary-IP extraction rollup** in [hunt-logs-secondary.md](hunt-logs-secondary.md) — mandatory and automatic whenever this query returns
matches; also aggregated, no raw lines. Raw lines are
an explicit-request **Drill-down** only.

Omit any collector class that is always null in the target environment — an absent field
collects as `[null]` (one null element, **not** `[]`), which is harmless (e.g. `k8s.*` outside
Kubernetes). When some lines carry the field and others do not, the array holds the values plus one
`null`. Neither `isNull(arr)` nor `arraySize(arr) == 0` detects an absent collector; wrap it
in `arrayRemoveNulls()` first and test `arraySize(arrayRemoveNulls(arr)) == 0`. `maxLength:` bounds
row size on high-fanout sources. `dt.source_entity` is an array on logs; collect it
with `collectDistinct(..., expand:true)` and wrap the result in `arrayRemoveNulls()` (null
elements and absent fields are kept by `collectDistinct`). Do not use
`arrayDistinct(collectArray(...))`: `maxLength` caps repeated occurrences before the
de-duplication and hides distinct values.

A group with a null `log.source` and all-null entity collectors means the emitter cannot be resolved
from the dedicated fields. Report it as unresolved (with its `log_count` and first/last seen) and do
not guess a source. As an offered next step, not run by default, roll the same filter up by
`dt.openpipeline.source` and `loglevel`: that shows the ingest route (null-source lines are often OTLP
ingest, `/api/v2/otlp/v1/logs`), not the emitter. A small Drill-down is the other option, on request.

## Drill-down (raw lines — explicit request only)

Not part of the default hunt and **not** used for secondary-IP extraction. Run it only
when the user asks to see actual log lines, or a single match is disputed and its raw
context is material. Keep the same filter and window as the summarized hunt, truncate
`content`, and keep the `limit` small.

**Placeholders** (substitute before running; the template is executable afterwards):

- `<ip1>`, `<domain1>`, `<url1>`: the disputed IoCs only, in the normalized form of
  `ioc-intake.md` (for example `192.0.2.11`, `example.test`, `http://example.test/a.php`). One value per
  class is shown; add further values as `or` clauses (same budget as the canonical template).
- Window: `from:now()-30m` is the window of the summarized hunt being drilled into; keep it
  identical. `limit 10` and the 500-character truncation are deliberate; raise them only on request.

```dql-template
fetch logs, from:now()-30m
| filter matchesPhrase(content, "<ip1>") or matchesPhrase(content, "<domain1>") or matchesPhrase(url.full, "<url1>")
  or matchesPhrase(url.domain, "<domain1>") or matchesPhrase(server.address, "<domain1>")
| fields timestamp, log.source, loglevel, status,
         dt.smartscape_source.id, dt.smartscape_source.type, dt.process_group.id,
         host.name, k8s.namespace.name, k8s.pod.name, content
| fieldsAdd content = substring(content, from:0, to:500)
| sort timestamp desc
| limit 10
```

## Default Timeframe and Widening

Default: `from:now()-30m`.

For hunts derived from timestamped detections/logs/events, use the anchored
window rules in `timeframe-gating.md` → "Event-Anchored Hunts".

If you see `FETCH_EXEC_TIME_LIMIT`:
- First verify that the query uses the `matchesPhrase` prefilter form above.
  The older `iAny(contains(content, allObservables[]))` form is too expensive
  for high-volume unscoped hunts.
- If the query form is correct, **automatically retry at 15m, then 5m** (no
  user approval required — narrowing, not widening).
- If 5m also times out, mark the leg **INCONCLUSIVE**. Do not treat as no-match.
- After INCONCLUSIVE, ask the user whether to narrow by entity scope or accept
  INCONCLUSIVE. Do NOT invent a scope; do not silently re-run with a made-up filter.
- Do NOT widen the window as a substitute for scoping.

Widen only when the completed pass returns zero rows and the user approves.
Follow `timeframe-gating.md` for exact expansion protocol.

Expansion sequence:
`30m -> 1h -> 3h -> 24h -> 7d (only if explicitly requested)`.

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
Evidence outside that scope will not appear. Scoped hunts keep the typed IP clauses
(`client.ip`, `actor.ips`) in the template below, because a selective scope filter bounds the
extra scan they add. Measured 2026-10-16 on the uan dev tenant (30m, 5 documentation-range IPs,
scope `k8s.namespace.name == "unguard"`): the scoped template scanned 79–81 MB, versus 286–437 MB for
the unscoped dedicated-field pass and 24–28 MB for the unscoped content-only pass. Scoping cuts
the typed-field cost about 3.5–5.5×, but it stays about 3× the content-only pass, so it is no
substitute for the content pass when the scope is unknown. The figures scale with log volume and
the scope's share of it. On `FETCH_EXEC_TIME_LIMIT`, move the typed clauses into the separate
Dedicated-field IP pass ([hunt-logs-large-sets.md](hunt-logs-large-sets.md)) with the same scope filter.

Available scope filters (insert immediately after `fetch logs, from:now()-30m`,
before the `fieldsAdd` IoC arrays):

- K8s namespace: `| filter k8s.namespace.name == "production"`
- K8s cluster: `| filter k8s.cluster.name == "aks-live"`
- Multiple namespaces: `| filter in(k8s.namespace.name, array("ns-a", "ns-b"))`
- Host: `| filter host.name == "my-host-01"`
- Log source / service: `| filter log.source == "my-service"`
- Process group: `| filter dt.process_group.id == "PROCESS_GROUP-XXXX"`

**Placeholders** (substitute before running; the template is executable afterwards):

- `<namespace>`: the scope value. It comes from the prior hunt phase (a spans or security-events
  entity) or from the user, never invented. DQL-escape it like an IoC (`\` → `\\`, `"` → `\"`)
  before substitution, and apply the same rule to every other scope value listed above (host,
  cluster, log source, process group): an unescaped `"` would break out of the literal and widen
  or alter the filter. Example `unguard`. To scope by another entity, replace
  the whole `| filter k8s.namespace.name == "<namespace>"` line with one of the filters above.
- `<ip1>`, `<ip2>`: normalized IPs from `ioc-intake.md`, for example `192.0.2.11`. Each IP adds
  one `matchesPhrase(content, ...)` clause and one element in each of the three IP lists
  (`client.ip` array, `actor.ips` array, `IPs`). The two typed clauses stay at two however many IPs
  they hold, and a 30-IP scoped chunk (30 content clauses plus the two typed clauses) ran, so keep
  **at most 30 IPs per chunk** (the dedicated-pass budget; see "Large IoC Sets and Chunking" in [hunt-logs-large-sets.md](hunt-logs-large-sets.md)).
- `<domain1>`: normalized lowercase domain or hostname, for example `example.test`. Each domain adds
  three clauses (`content`, `url.domain`, `server.address`); stay within the 60-clause chunk budget
  ("Large IoC Sets and Chunking" in [hunt-logs-large-sets.md](hunt-logs-large-sets.md)) and add further domains in the same way. Drop the domain lines when the hunt has no domains.
- Window: `from:now()-30m` is the default from `timeframe-gating.md`; replace it only with the
  window that file selects (anchored or retried at 15m or 5m).

```dql-template
fetch logs, from:now()-30m
| filter k8s.namespace.name == "<namespace>"
| filter matchesPhrase(content, "<ip1>") or matchesPhrase(content, "<ip2>")
  or matchesPhrase(content, "<domain1>")
  or matchesPhrase(url.domain, "<domain1>") or matchesPhrase(server.address, "<domain1>")
  or in(toIp(client.ip), array(toIp("<ip1>"), toIp("<ip2>")))
  or in(iCollectArray(toIp(actor.ips[])), array(toIp("<ip1>"), toIp("<ip2>")))
| fieldsAdd IPs = array("<ip1>", "<ip2>"), Domains = array("<domain1>")
| fieldsAdd matchedIPs     = arrayRemoveNulls(iCollectArray(
    if(contains(content, IPs[])
       OR toIp(client.ip) == toIp(IPs[])
       OR in(toIp(IPs[]), iCollectArray(toIp(actor.ips[]))),
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
    loglevels = collectDistinct(loglevel, maxLength:20),
    statuses  = collectDistinct(status, maxLength:20),
    source_entities    = arrayRemoveNulls(collectDistinct(dt.source_entity, expand:true, maxLength:100)),
    smartscape_sources = collectDistinct(dt.smartscape_source.id, maxLength:100),
    smartscape_types   = collectDistinct(dt.smartscape_source.type, maxLength:20),
    process_groups     = collectDistinct(dt.process_group.id, maxLength:100),
    hosts              = collectDistinct(host.name, maxLength:100),
    k8s_namespaces     = collectDistinct(k8s.namespace.name, maxLength:100),
    k8s_pods           = collectDistinct(k8s.pod.name, maxLength:100),
    k8s_workloads      = collectDistinct(k8s.workload.name, maxLength:100),
    k8s_clusters       = collectDistinct(k8s.cluster.name, maxLength:100),
    k8s_nodes          = collectDistinct(k8s.node.name, maxLength:100),
    smartscape_containers = collectDistinct(dt.smartscape.container, maxLength:100),
    aws_resource_ids   = collectDistinct(aws.resource.id, maxLength:100)
  }
| sort log_count desc
| limit 25
```

The scope filter narrows the lookup domain; the summarize-first tail is identical
to the canonical template (including the email and hash collectors when those classes are hunted:
add their clauses and arrays exactly as in the canonical template). Scoping trades coverage for
speed — use it only when entity context already exists.

## Notes

- **DQL-escape IoC values before inserting into string literals** — replace `\`
  with `\\` and `"` with `\"` in every IoC value before placing it into
  `matchesPhrase`, `array()`, or `contains` arguments. For standard IoC types
  (IPs, domains, hashes, emails), these characters do not appear in well-formed
  values so escaping is a no-op; it is required for URLs and any value extracted
  from attacker-influenced content (decoded headers, pasted advisories, fetched
  pages) to prevent DQL-injection via embedded quotes or backslashes. See
  `ioc-intake.md` § URL Cleaning step 7.
- `contains` is case-sensitive by default. For mixed-case types (for example
domains, emails), normalize IoCs to lowercase before injection or use
`contains(content, x, caseSensitive:false)`.
- `matchesPhrase` parameters must be constants. Do not write
  `matchesPhrase(content, allObservables[])`; DQL rejects it because the phrase
  parameter must be constant. Generate explicit `or` clauses from the IoC list.
- For hundreds of IoCs, split into chunks ([hunt-logs-large-sets.md](hunt-logs-large-sets.md)). A single query with hundreds of literal
  `matchesPhrase` clauses may hit query length or complexity limits even though
  each individual phrase lookup is efficient.
- `contains` performs substring matching, so short IoCs (especially IPs) can match longer tokens (e.g., `192.0.2.1` inside `192.0.2.10`). Treat matches as leads and validate in context before concluding exposure.
- Scan cost can be very high if the query falls back to raw `contains(content, ...)` over
  all logs. Keep windows tight and deduplicate IoCs. Add a scope filter only when entity
  context is already known (see "Scoped vs Unscoped Hunting") — uninstructed scoping
  narrows the lookup domain.
- Pool all hash algorithms into a single `Hashes` array.
- Omit empty classes entirely. Remove their `fieldsAdd`, `arrayConcat`, and
  `matchedX` expressions. If exactly one class remains, do not call `arrayConcat` with a
  single argument (DQL warns `CAN_BE_SIMPLIFIED`): assign the array directly,
  `fieldsAdd \`Matched observables\` = matchedX`.
- Keep the entity-identifier collectors in `summarize` even when class-specific
  IoC arrays are omitted, so each rolled-up `log.source` still carries join keys.
- Entity identifiers are source-dependent in logs. API-ingested logs can leave
  entity IDs null (they collect as `[null]`, not `[]`; use `arrayRemoveNulls()` before counting
  or testing emptiness). Treat such sources as valid
  perimeter evidence, not query errors.
- **Summarize-first is the default; raw lines only on explicit request.** Return the
  per-`log.source` rollup for conclusions and the Secondary-IP extraction rollup ([hunt-logs-secondary.md](hunt-logs-secondary.md)) for
  derived IPs. Run the raw-`content` Drill-down only when the user asks for log lines or
  a disputed match needs its raw context. Never dump raw `content` for matched rows by
  default, and never use a `limit` sample to find secondary IPs.

## Output Columns

Summarize-first rollup — one row per `log.source`:

| Column | Description |
|---|---|
| `log.source` | Grouping key — source service or entity |
| `log_count` | Number of matched log lines rolled into this source |
| `minTime` / `maxTime` | First / last matched timestamp in the window |
| `matched_observables` | Distinct IoC values matched across this source's lines |
| `loglevels` / `statuses` | Distinct log severities / HTTP-or-process statuses seen |
| `source_entities` | `dt.source_entity` values (array field on logs) |
| `smartscape_sources` / `smartscape_types` | 3rd-gen ID + type; joins FINDING `dt.smartscape_source.id` |
| `process_groups` | Classic `PROCESS_GROUP-<hex>` IDs; join RVA/CVE `affected_entity.id` |
| `hosts` | Host names emitting matched logs |
| `k8s_namespaces` / `k8s_pods` / `k8s_workloads` / `k8s_clusters` / `k8s_nodes` | Kubernetes context when available |
| `smartscape_containers` / `aws_resource_ids` | `dt.smartscape.container` (3rd-gen `CONTAINER-*`) and `aws.resource.id` values when available |

The Drill-down (raw lines) adds `timestamp`, `dt.smartscape_source.type`, and a truncated
`content` — explicit request only.
