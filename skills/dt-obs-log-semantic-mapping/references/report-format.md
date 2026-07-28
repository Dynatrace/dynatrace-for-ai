# Report Format

## TOC

- [Workflow A — Phase 1](#workflow-a--phase-1)
- [Workflow A — Phase 2 (after approval)](#workflow-a--phase-2-after-approval)
- [Workflow B1](#workflow-b1)
- [Workflow B2](#workflow-b2)

---

## Workflow A — Phase 1

### Mapping Summary

- Vendor / `log.source`:
- Log class:
- Sample count:
- Confidence: `high | medium | low`

### Mapping Table

| Source Field | Target Field | Transform | Required | Sample Value | Notes |
|---|---|---|---|---|---|
| `content.username` | `audit.identity` | direct | yes | `jsmith@acme.com` | |
| `content.source` | `actor.ips` | string→array | yes | `["44.198.0.1"]` | |
| `content.success` | `audit.result` | bool→title-case | recommended | `"Succeeded"` | |
| derived | `loglevel` | from `audit.result` | yes | `"INFO"` | |
| — | `log.source` | constant | yes | `"CyberArk"` | |

### Content Field Promotion Plan

| content sub-field | Target SD field | Transform | OpenPipeline rule needed |
|---|---|---|---|
| `content.username` | `audit.identity` | direct | yes |
| `content.ip_address` | `actor.ips` | string→array | yes |

### OpenPipeline Processor Sketch

```dql-snippet
// parseJson is NOT an OpenPipeline function — use parse content, "json:content" + subscript access instead.
| parse content, "json:content"                          // turn JSON string into a structured record
| fieldsAdd audit.identity = content[username]           // subscript access: content[key] for JSON keys
| fieldsAdd actor.ips = array(toIp(content[ip_address])) // → ipAddress[]
| fieldsAdd audit.result = if(content[success] == "True", "Succeeded", else: "Failed")
| fieldsAdd loglevel = if(content[success] == "True", "INFO", else: "ERROR")
| fieldsAdd status = loglevel
```

### Gap Summary

| Required Field | Status | Reason |
|---|---|---|
| `audit.result` | ⚠ derived | not explicit — derived from `content.success` |

### Discrepancies

| Severity | Issue | Suggested Fix |
|---|---|---|
| major | `audit.identity` not promoted from `content.username` | add OpenPipeline extraction |
| minor | `loglevel` absent | derive from outcome or set constant `"INFO"` |

---

## Workflow A — Phase 2 (after approval)

One mapped sample JSON per log class. Annotate every transform inline.

```json
// CyberArk Identity — authentication (MFA challenge)
// Transforms:
//   content.username → audit.identity  [direct]
//   content.source → actor.ips         [string→array]
//   content.success "False" → audit.result "Failed"  [bool map]
//   audit.result "Failed" → loglevel "ERROR"          [outcome map]
{
  "timestamp": "2026-05-08T16:23:07.539000000Z",
  "log.source": "CyberArk",
  "content": "{\"username\":\"i.rodriguez@example.com\",\"source\":\"207.162.45.12\",\"action\":\"Multifactor challenge\",\"success\":\"False\"}",
  "loglevel": "ERROR",
  "status": "ERROR",
  "event.type": "LOG",
  "audit.action": "Multifactor challenge",
  "audit.identity": "i.rodriguez@example.com",
  "audit.result": "Failed",
  "actor.ips": ["207.162.45.12"],
  "client.ip": "207.162.45.12",
  "actor.geo.city.name": "Montreal",
  "actor.geo.country.name": "Canada",
  "browser.name": "Chrome",
  "browser.version": "147.0.0.0",
  "device.os.name": "Mac",
  "cloud.provider": "aws",
  "cyberark.service": "Identity"
}
```

---

## Workflow B1

### Diff-Highlighted Mapping Table

Marker legend: ✅ ok · ⚠ change · ➕ add · ❌ remove

| Source Field | Current Target | Suggested Target | Transform | Status | Reason |
|---|---|---|---|---|---|
| `log.source` | `log.source` | `log.source` | direct | ✅ ok | |
| `content.username` | — | `audit.identity` | direct | ➕ add | required field not promoted |
| `content.ip_address` | `client.ip` | `actor.ips` | string→array | ⚠ change | primary IP field is array |
| `loglevel` | — | `loglevel` | derive from outcome | ➕ add | required field absent |
| `content.internalRef` | `internal.ref` | — | — | ❌ remove | not in SD or samples |

### Content Burial Report

| content sub-field | Top-level semantic field? | Target | Status |
|---|---|---|---|
| `content.username` | no | `audit.identity` | ➕ promote |
| `content.ip_address` | yes — `client.ip` | `actor.ips` | ⚠ promote to array field |
| `content.action` | no | `audit.action` | ➕ promote |
| `content.trace_id` | yes — `trace_id` | — | ✅ promoted |

**Burial score:** 2 of 4 content fields promotable, 2 gaps remaining.

### Required-Field Matrix

| Field | Status | Notes |
|---|---|---|
| `timestamp` | ✅ pass | |
| `log.source` | ✅ pass | |
| `content` | ⚠ warn | JSON object — must be serialized to string |
| `loglevel` | ❌ fail | absent — derive from outcome |
| `audit.action` | ❌ fail | buried in `content.action` |
| `audit.identity` | ❌ fail | buried in `content.username` |

### Discrepancies

| Severity | Issue | Suggested Fix |
|---|---|---|
| critical | `content` is JSON object, not string | serialize before ingest |
| major | `audit.identity` not promoted | extract from `content.username` via OpenPipeline |
| major | `loglevel` absent | derive from `audit.result` |

### OpenPipeline Improvement Plan

1. Extract `audit.identity` from `content.username`.
2. Derive `loglevel` / `status` from outcome.
3. Serialize `content` to JSON string.

---

## Workflow B2

B2 output uses the B1 format above, applied to fetched live records. Prefix the report with:

**Runtime Context:**
- `log.source` queried:
- Time window:
- Records fetched: N
- Execution method: live DQL execution

Then run B1 validation on the fetched records. Produce the same Diff-Highlighted Mapping Table, Content Burial Report, Required-Field Matrix, and Discrepancies sections.

Add a **Validation Summary** table:

| Check | Result | Evidence |
|---|---|---|
| Logs found for `log.source` | `🟢 pass` / `🔴 fail` | record count |
| `content` is string | `🟢 pass` / `🔴 fail` | type on sample |
| `loglevel` valid enum | `🟢 pass` / `🔴 fail` | distinct values seen |
| `audit.action` populated | `🟢 pass` / `🟡 warn` | null count |
| `audit.identity` populated | `🟢 pass` / `🟡 warn` | null count |
| `audit.result` populated | `🟢 pass` / `🟡 warn` | null count |
| Content burial score | `🟢 0` / `🟡 1–2` / `🔴 3+` | promotable field list |

Status legend: `🟢 pass` · `🟡 warn` · `🔴 fail`
