# Secondary Observable Extraction

When a primary IoC hunt returns matched log or span records, those records often
carry **additional IPs** in proxy/relay headers, structured fields, or metadata
that were NOT part of the initial IoC list. These are **secondary observables**:
IPs discovered inside matched evidence rather than in the original user or
advisory input.

Secondary observables must be extracted, deduplicated, and re-hunted
**automatically** before exposure scoring. For logs, extraction is a **separate
aggregating DQL query** (`hunt-logs-secondary.md` § Secondary-IP extraction rollup) that parses
every matched line server-side and returns only the distinct derived IPs — the agent
does **not** fetch or read raw log lines for this. Omitting this step can miss the true
origin or relay chain of an attack (for example a request where the CDN/proxy IP
is the initial match but `X-Forwarded-For` reveals the actual client).

---

## Contents

- [What Counts as a Secondary Observable](#what-counts-as-a-secondary-observable)
- [Mandatory Derived-IP Sources](#mandatory-derived-ip-sources)
  - [HTTP proxy / forwarding headers (look inside `content`)](#http-proxy--forwarding-headers-look-inside-content)
  - [Structured log fields (look inside parsed `content` JSON or message body)](#structured-log-fields-look-inside-parsed-content-json-or-message-body)
  - [Span fields (already parsed by DQL)](#span-fields-already-parsed-by-dql)
- [Extraction and Normalization](#extraction-and-normalization)
- [Re-Hunt Policy](#re-hunt-policy)
  - [Window and scope](#window-and-scope)
  - [Eligible legs](#eligible-legs)
  - [Encoded log-content fallback](#encoded-log-content-fallback)
  - [Recursion guard](#recursion-guard)
  - [Capped collectors (saturation)](#capped-collectors-saturation)
  - [Cap on derived-IP queue size](#cap-on-derived-ip-queue-size)
- [Reporting](#reporting)

## What Counts as a Secondary Observable

Only **IP addresses** are promoted to secondary observables by default. Domains,
URLs, emails, and hashes embedded in evidence content are not auto-promoted
because they are too noisy and may require analyst review before hunting.

---

## Mandatory Derived-IP Sources

These sources are read for every matched log line (server-side, by the rollup in
`hunt-logs-secondary.md`) and every matched span:

### HTTP proxy / forwarding headers (look inside `content`)

| Header | Notes |
|---|---|
| `X-Forwarded-For` | May contain a comma-separated chain; hunt all values |
| `Forwarded` | RFC 7239; extract from `for=...` parameter |
| `X-Real-IP` | Single IP from Nginx/HAProxy |
| `X-Client-IP` | Apache proxy convention |
| `True-Client-IP` | Akamai / Cloudflare true client IP |
| `CF-Connecting-IP` | Cloudflare-specific |
| `Fastly-Client-IP` | Fastly CDN |
| `Akamai-True-Client-IP` | Akamai-specific |
| `Via` | Skip — this is proxy hostnames, not client IPs |

### Structured log fields (look inside parsed `content` JSON or message body)

| Field name | Common source |
|---|---|
| `clientIP` | Akamai SIEM, WAF events |
| `src_ip` | Firewall/syslog events |
| `source.ip` | ECS-structured events |
| `remote_addr` | Nginx/Apache access logs |
| `actor.ip` | Security events inlined in logs |
| `xff` / `x_forwarded_for` | Some proxy log formats |

### Span fields (already parsed by DQL)

When a span matched (via `client.ip`, `server.resolved_ips`, or
`request_attribute.SourceIP`), also extract:

- `request_attribute.*` — any IP-valued request attribute not already in the
  primary IoC list.

---

## Extraction and Normalization

For logs, steps 1-6 are performed inside the rollup query; for spans the same policy
applies to the already-parsed fields. Nothing here requires returning log `content`.

1. **Parse** — header-scoped DPL `parse` extracts values only from the named headers and
   fields above; it does not guess IP positions from unlabelled text.
2. **Decode common encodings** — the rollup lower-cases `content` and decodes `%2c`, `%3a` and `%20`
   inside the query before the `parse` (details and limits in `hunt-logs-secondary.md`), and the header
   patterns are case-insensitive, so encoded and mixed-case headers are read without returning the raw
   content. The patterns also
   read the JSON key/value header shape (`{"key":"X-Forwarded-For","value":"<ip>"}`) and
   backslash-escaped quotes around bracketed IPv6 in `Forwarded: for=`. The raw
   header is not returned.
3. **Split chains** — `X-Forwarded-For` chains (`"1.2.3.4, 5.6.7.8"`) yield up to 3
   entries per line, one candidate row each.
4. **Validate** — `IPADDR` / `toIp()` discard anything that is not a valid IPv4 or IPv6
   address.
5. **Deduplicate and exclude already-hunted IoCs** — `filterOut in(derived_ip, HuntedIPs)`
   removes IPs already in the primary hunt set; rows are grouped by `{derived_ip,
   via_header}`, so each IP appears once per header.
6. **Exclude well-known private ranges** — `ipIsPrivate`, `ipIsLoopback`, and
   `ipIsLinkLocal` drop RFC 1918, loopback, and link-local addresses. Remove those
   `filterOut` terms only if the hunt is explicitly scoped to an internal network.

Known limits (report them, do not paper over them): the rollup keeps the first
occurrence per header pattern per line and at most 3 `X-Forwarded-For` entries; header
formats it does not match are not seen. In that case offer the explicit-request
Drill-down in `hunt-logs.md` instead of fetching raw lines automatically.

The result is the **derived-IP queue**: the net-new IPs to hunt.

---

## Re-Hunt Policy

### Window and scope

- Use the **same window and scope** as the primary hunt that produced the matched
  evidence.
- Do not widen the logs or spans window for secondary re-hunts. The detections re-hunt
  follows the primary detections leg (2h, then the automatic 24h re-run on zero rows). If
  additional widening is later needed, apply the approval gate from `timeframe-gating.md` in the same way as
  for primary IoCs.
- If the primary evidence had an event-anchored window, use the same anchored
  range for secondary re-hunts.

### Eligible legs

Secondary derived IPs are IPs — hunt them on all IP-eligible legs:

| Leg | Reference |
|---|---|
| `fetch logs` | `hunt-logs-secondary.md` § Secondary re-hunt (logs) with next-level IPs |
| `fetch spans` | `hunt-spans.md` |
| `security.events` DETECTION_FINDING `actor.ips` | `hunt-security-events.md` § Detection hunt rollup, with the derived-IP queue as the literal IP list. Use it even when the primary hunt was report-driven: the report-driven join (§ Report-driven correlation) only searches IPs listed in `THREAT_REPORT.threat.observables.ips`, and a secondary IP found in a log or span need not appear in any report. |

### Encoded log-content fallback

For derived IPs extracted from encoded log content, run the canonical
`matchesPhrase(content, "<ip>")` log re-hunt first. If it returns zero rows but
the IP was found in an encoded header or field of a matched primary record, run
a bounded supplemental verification query using `contains(content, "<ip>")` for
only the derived IPs, with the same window and scope. This fallback exists
because tokenized phrase matching can miss values embedded in URL-encoded header
blobs even though raw `contains` can verify the occurrence.

Guardrails:
- Use this fallback only for derived IPs already observed in matched evidence.
- Keep the same window and scope; do not widen.
- If the supplemental query times out, mark that secondary log leg
  **INCONCLUSIVE**, not no-match.
- Label fallback matches as supplemental verification in the final report.

### Recursion guard

The secondary re-hunt may itself return matched records. Apply **one level of
secondary extraction only**. Any new derived IPs found in secondary results must
be **reported and queued for user-approved follow-up** — do not automatically
recurse. State explicitly in the report how many recursion-level IPs were
discovered but not auto-hunted.

Take those next-level IPs from the re-hunt scans you already ran: the `next_level_ips` column
of the log re-hunt (`hunt-logs-secondary.md` § Secondary re-hunt (logs) with next-level IPs) and the
`source_ips` / `resolved_ips` / `client_ips` columns of the span re-hunt (`source_ips` can be strings: cast with `toIp()` before comparing), minus IPs already
hunted. **Do not run the extraction rollup again over the re-hunt matches** — that is a second
full scan of the re-hunt window just to count IPs.

### Capped collectors (saturation)

The IP collectors in the log re-hunt and the span rollup are capped lists: `next_level_ips` 100,
`source_ips` 50, `resolved_ips` 50, `client_ips` 100 (`maxLength` in the templates). A row with more
distinct addresses than the cap silently keeps only some of them, and the row `limit` never signals it.
Each template therefore carries a flag, true when a collector is within one slot of its cap (one slot
may hold a `null`, so the check is `maxLength - 1`): `next_level_ips_capped` in
`hunt-logs-secondary.md` and `ips_capped` in `hunt-spans.md` (the span re-hunt reuses the same
template, so it carries the same flag). Keep the flag thresholds in step with the `maxLength` values.

For every row where the flag is `true`, extraction for that source is **incomplete**:

- Close the gap by re-running that IoC (or `log.source` group) alone as several time slices of the
  same window, or per chunk, and merging the results; never widen the window or scope.
- If it cannot be closed, report the secondary extraction as **INCOMPLETE**, name the capped column,
  give the address count as a lower bound, and present the exposure score as provisional (it does not
  drop for the gap, see `exposure-scoring.md` § Incomplete legs rule) until the gap is closed or the
  user accepts it.

### Cap on derived-IP queue size

If the derived-IP queue exceeds **60 IPs** (the content-only IP chunk maximum), apply the
clause-budget chunking policy from `hunt-logs-large-sets.md` § "Large IoC Sets and Chunking". Do not
produce a single DQL query with hundreds of new values.

---

## Reporting

Report derived-IP evidence distinctly from primary evidence:

- In **exposure scoring**: secondary observables use the same band logic as
  primary observables. If a secondary IP match is the only evidence, it is a
  real log/span hit (≥80 band), not downgraded.
- In the **legs line / coverage notes**: list every capped collector (see § Capped collectors) as
  an incomplete secondary extraction, with the lower-bound count.
- In **IoC coverage tables** (Section 5 of the exposure report): use the
  `Primary/Secondary` column to distinguish origin.
  - **Primary** — from original user/advisory input.
  - **Secondary** — discovered in matched evidence during the hunt.
- In **Section 4** (matched IP details): for each secondary IP, state which
  primary IoC the carrying lines matched (`matched_observables`), which header/field it
  was extracted from (`via_header`), how many lines carried it (`log_count`), the
  first/last-seen window, and the emitting `log.source`/entity.
- If secondary re-hunts returned zero matches, do not list those secondary IPs; unmatched
  IoCs are not reported (a one-line "N of M IoCs had no match" coverage count is fine).
- If the derived-IP queue was truncated or any secondary re-hunt was INCONCLUSIVE,
  state so and recommend follow-up.
