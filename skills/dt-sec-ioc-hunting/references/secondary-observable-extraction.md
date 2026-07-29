# Secondary Observable Extraction

When a primary IoC hunt returns matched log or span records, those records often
carry **additional IPs** in proxy/relay headers, structured fields, or metadata
that were NOT part of the initial IoC list. These are **secondary observables**:
IPs discovered inside matched evidence rather than in the original user or
advisory input.

Secondary observables must be extracted, deduplicated, and re-hunted
**automatically** before exposure scoring. Omitting this step can miss the true
origin or relay chain of an attack (for example a request where the CDN/proxy IP
is the initial match but `X-Forwarded-For` reveals the actual client).

---

## What Counts as a Secondary Observable

Only **IP addresses** are promoted to secondary observables by default. Domains,
URLs, emails, and hashes embedded in evidence content are not auto-promoted
because they are too noisy and may require analyst review before hunting.

---

## Mandatory Derived-IP Sources

Inspect these sources in every matched log record or span:

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

1. **Parse** — extract raw values from the matched record; do not guess IP
   positions from unlabelled fields.
2. **Decode common encodings before extraction** — matched log `content` can
  contain URL-encoded headers (for example `X-Forwarded-For%3a%20152.56.166.16`).
  Percent-decode and HTML-decode header values before extracting secondary IPs,
  but preserve the original raw representation as provenance.
3. **Split chains** — `X-Forwarded-For` can be `"1.2.3.4, 5.6.7.8"` (or `"1.2.3.4,5.6.7.8"`); split on `,` then trim whitespace
   and include all entries.
4. **Validate** — discard values that are not valid IPv4 or IPv6 addresses.
5. **Deduplicate and exclude already-hunted IoCs** — compute the set difference
   against all IPs already in the primary hunt set. Do not re-hunt values already
   searched.
6. **Exclude well-known private ranges** — skip RFC 1918 (`10.x`, `172.16–31.x`,
   `192.168.x`) and loopback (`127.x`, `::1`) unless the hunt is explicitly scoped
   to an internal network.

The result is the **derived-IP queue**: the net-new IPs to hunt.

---

## Re-Hunt Policy

### Window and scope

- Use the **same window and scope** as the primary hunt that produced the matched
  evidence.
- Do not widen the window for secondary re-hunts. If additional widening is later
  needed, apply the approval gate from `timeframe-gating.md` in the same way as
  for primary IoCs.
- If the primary evidence had an event-anchored window, use the same anchored
  range for secondary re-hunts.

### Eligible legs

Secondary derived IPs are IPs — hunt them on all IP-eligible legs:

| Leg | Reference |
|---|---|
| `fetch logs` | `hunt-logs.md` |
| `fetch spans` | `hunt-spans.md` |
| `security.events` DETECTION_FINDING `actor.ips` | **dt-sec-insights** → `threat-intelligence.md` § Attacker IPs → detections |

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

### Cap on derived-IP queue size

If the derived-IP queue exceeds **25 IPs**, apply the same 25-IoC chunking
policy from `hunt-logs.md` § "Large IoC Sets and Chunking". Do not produce a
single DQL query with hundreds of new values.

---

## Reporting

Report derived-IP evidence distinctly from primary evidence:

- In **exposure scoring**: secondary observables use the same band logic as
  primary observables. If a secondary IP match is the only evidence, it is a
  real log/span hit (≥80 band), not downgraded.
- In **IoC coverage tables** (Section 5 of the exposure report): use the
  `Primary/Secondary` column to distinguish origin.
  - **Primary** — from original user/advisory input.
  - **Secondary** — discovered in matched evidence during the hunt.
- In **Section 4** (matched IP details): for each secondary IP, state which
  primary record contained it and which header/field it was extracted from.
- If secondary re-hunts returned zero matches, still include secondary IPs in
  Table B (Unmatched IoCs) with `Sources searched` and provenance noted.
- If the derived-IP queue was truncated or any secondary re-hunt was INCONCLUSIVE,
  state so and recommend follow-up.
