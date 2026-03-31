# Content Security Policy (CSP) Violations

Monitor and analyze Content Security Policy violations for security and compliance.

**Data Source:** `fetch user.events` with `characteristics.has_csp_violation`

**Key Fields:**

- `csp.violated_directive` - Original policy directive violated
- `csp.effective_directive` - Actual enforced directive
- `csp.blocked_uri.*` - Blocked resource details
- `csp.document_uri.*` - Page where violation occurred
- `csp.disposition` - `enforce` (blocked) or `report` (logged only)

## All CSP Violations

Query all CSP violations:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_csp_violation == true
| summarize
    violation_count = count(),
    affected_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, csp.violated_directive}
| sort violation_count desc

```

**Use Case:** Overview of CSP violation patterns.

## Violations by Blocked Resource

Identify blocked resources:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_csp_violation == true
| summarize
    violation_count = count(),
    by: {frontend.name, csp.blocked_uri.full, csp.effective_directive}
| sort violation_count desc
| limit 30

```

**Use Case:** Find resources to allow or fix.

## Third-Party Violations

Analyze third-party resource blocks:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_csp_violation == true
| filter csp.blocked_uri.provider == "third_party"
| summarize
    violation_count = count(),
    by: {frontend.name, csp.blocked_uri.domain, csp.effective_directive}
| sort violation_count desc
| limit 20

```

**Use Case:** Review third-party integrations causing violations.

## Inline Script/Style Violations

Find inline content blocks:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_csp_violation == true
| filter csp.blocked_uri.full == "inline"
| summarize
    violation_count = count(),
    by: {frontend.name, csp.effective_directive, csp.document_uri.path}
| sort violation_count desc
| limit 20

```

**Use Case:** Identify pages needing CSP nonces or hashes.

## Violations by Page

Map violations to pages:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_csp_violation == true
| summarize
    violation_count = count(),
    unique_blocked = countDistinct(csp.blocked_uri.full),
    by: {frontend.name, csp.document_uri.path}
| sort violation_count desc
| limit 20

```

**Use Case:** Prioritize pages for CSP policy updates.

## Enforced vs Report-Only

Compare enforcement modes:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_csp_violation == true
| summarize
    enforced_count = countIf(csp.disposition == "enforce"),
    reported_count = countIf(csp.disposition == "report"),
    by: {frontend.name}

```

**Use Case:** Plan CSP enforcement rollout.

## CSP Violation Trends

Track violations over time:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_csp_violation == true
| summarize
    violation_count = count(),
    by: {frontend.name, time_bucket = bin(start_time, 1d)}
| sort time_bucket asc

```

**Use Case:** Monitor CSP policy effectiveness.

## Directive-Specific Analysis

Deep dive into specific directives:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_csp_violation == true
| filter csp.effective_directive == "script-src"
| summarize
    violation_count = count(),
    by: {frontend.name, csp.blocked_uri.domain, csp.document_uri.path}
| sort violation_count desc
| limit 20

```

**Use Case:** Focus on high-risk directive violations.

## Violation Details

Get detailed violation context:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_csp_violation == true
| fields
    start_time,
    csp.violated_directive,
    csp.effective_directive,
    csp.blocked_uri.full,
    csp.document_uri.path,
    csp.line_number,
    csp.column_number,
    csp.sample
| sort start_time desc
| limit 50

```

**Use Case:** Debug specific CSP issues with code context.

## User Impact

Measure user impact of violations:

```dql
fetch user.events, from: now() - 2h
| filter characteristics.has_csp_violation == true
| filter csp.disposition == "enforce"
| summarize
    affected_users = countDistinct(dt.rum.instance.id, precision: 9),
    affected_sessions = countDistinct(dt.rum.session.id),
    by: {frontend.name, csp.effective_directive}
| sort affected_users desc

```

**Use Case:** Prioritize fixes by user impact.

