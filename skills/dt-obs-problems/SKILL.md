---
name: dt-obs-problems
description: >-
  DAVIS problem analysis including root cause identification, impact assessment,
  and correlation with other telemetry. Use when querying or investigating detected problems.
  Trigger: "active problems", "root cause analysis", "problem impact", "affected users",
  "list problems", "P-12345 details", "recurring problems", "problem history",
  "problem trending", "blast radius", "which entity caused the problem",
  "problems affecting Kubernetes", "problems by service".
  Do NOT use for explaining existing queries, product documentation questions, generic
  log searching, distributed tracing, or host-level resource monitoring.
license: Apache-2.0
---

# Problem Analysis Skill

Analyze Dynatrace AI-detected problems including root cause identification, impact assessment, and correlation with logs and metrics.

---

## Use Cases

### 1. Active Problem Triage
- **Goal:** List and prioritize currently active problems
- **Trigger:** "active problems", "what problems are open", "current issues", "availability issues"
- **Done:** Prioritized list of active problems with category, user impact, and display IDs

### 2. Root Cause Investigation
- **Goal:** Identify the root cause entity for a specific problem
- **Trigger:** "root cause of P-12345", "what caused this problem", "which entity is the root cause"
- **Done:** Root cause entity identified with affected entity list and blast radius

### 3. Problem Trending
- **Goal:** Analyze problem patterns over time to identify recurring issues
- **Trigger:** "recurring problems", "problem history", "problem trends last 30 days"
- **Done:** Trend data showing problem frequency, recurring root causes, and resolution times

---

## Overview

Dynatrace automatically detects anomalies, performance degradations, and failures across your environment, creating **problems** that aggregate related alert, warning and info-level events and provide root cause and impact insights.

### What are Problems?

Problems are automatically detected, software and infrastructure health and resilience issues that:

- **Automatically correlate** related alert, warning, and info-level events across services, infrastructure, frontend applications, and user sessions
- **Identify root causes** using causal analysis of Smartscape dependencies
- **Assess business impact** by tracking affected users and services
- **Reduce alert noise** by grouping related symptoms into single problems that share the same root cause and impact
- **Track problem lifecycle** from early detection through resolution

### Event Kinds

The `event.kind` field (stable, permission) identifies the high-level event type:

| `event.kind` value | Description |
|---|---|
| `DAVIS_EVENT` | Davis-detected infrastructure/application events |
| `BIZ_EVENT` | Business events (ingested via API or captured from spans) |
| `RUM_EVENT` | Real User Monitoring events |
| `AUDIT_EVENT` | Administrative/security audit events |

`event.provider` (stable, permission) identifies the event source.

## Problem Categories

Common `event.category` values:

| Category | Description | Example |
|----------|-------------|---------|
| **AVAILABILITY** | Infrastructure or service unavailable | Web service returns no data, synthetic test actively fails, database connection lost |
| **ERROR** | Increased error rates beyond baseline | API error rate jumped from 0.1% to 15% |
| **SLOWDOWN** | Performance degradation | Response time increased from 200ms to 5000ms |
| **RESOURCE** | Resource saturation | Container memory at 95%, causing OOM kills |
| **CUSTOM** | Custom anomaly detections | Business KPI (orders/minute) dropped below threshold |

## Problem Lifecycle

```text
Detection → ACTIVE → Under Investigation → CLOSED
```

- **ACTIVE**: Currently occurring issues requiring attention
- **CLOSED**: Resolved issues used for historical analysis

## Essential Fields

### Common Field Name Mistakes

| ❌ WRONG | ✅ CORRECT | Description |
|---------|-----------|-------------|
| `title` | `event.name` | Problem title/description |
| `status` | `event.status` | Problem lifecycle status |
| `severity` | `event.category` | Problem type/category |
| `start` | `event.start` | Problem start time |

### Correct Status Values

```dql
// ✅ CORRECT: Use these status values
fetch dt.davis.problems
| filter event.status == "ACTIVE"   // Currently occurring problems
//     or event.status == "CLOSED"  // Resolved problems
// ❌ INCORRECT: event.status == "OPEN" does not exist!
| limit 1
```

### Key Fields Reference

```dql
fetch dt.davis.problems, from:now() - 1h
| filter not(dt.davis.is_duplicate)
| fields
    event.start,                          // Problem start timestamp
    event.end,                            // Problem end timestamp (if closed)
    display_id,                           // Human-readable problem ID (P-XXXXX)
    event.name,                           // Problem title
    event.description,                    // Detailed description
    event.category,                       // Problem type
    event.status,                         // ACTIVE or CLOSED
    dt.smartscape_source.id,              // The smartscape ID for the affected resource
    dt.davis.affected_users_count,        // Number of affected users
    affected_entity_ids = smartscape.affected_entities[][id],  // Array of affected entity IDs
    dt.smartscape.service,                // Affected services (may be array)
    dt.davis.root_cause_entity,           // Entity identified as root cause
    root_cause_entity_id,                 // Root cause entity ID
    root_cause_entity_name,               // Human-readable root cause name
    dt.davis.is_duplicate,                // Whether duplicate detection
    dt.davis.is_rootcause                 // Root cause vs. symptom
| limit 10
```

## Standard Query Pattern

Always start problem queries with this foundation:

```dql
fetch dt.davis.problems, from:now() - 2h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| fields event.start, display_id, event.name, event.category
| sort event.start desc
| limit 20
```

**Key components:**

- `fetch dt.davis.problems` - The problems data source
- `not(dt.davis.is_duplicate)` - Filter out duplicate detections
- `event.status == "ACTIVE"` - Show only active problems
- Time range - Always specify a reasonable window

## Common Query Patterns

### Active Problems by Category

```dql
fetch dt.davis.problems
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| summarize problem_count = count(), by: {event.category}
| sort problem_count desc
```

### High-Impact Active Problems (affecting many users)

```dql
fetch dt.davis.problems
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter dt.davis.affected_users_count > 100
| fields event.start, display_id, event.name, dt.davis.affected_users_count, event.category
| sort dt.davis.affected_users_count desc
```

### High-Impact Active Problems (affecting many smartscape entities)

```dql
fetch dt.davis.problems
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter arraySize(affected_entity_ids) > 5
| fields event.start, display_id, event.name, affected_entity_ids, event.category, impacted_entity_count = arraySize(affected_entity_ids)
| sort impacted_entity_count desc
```

### Specific Problem Details

```dql
fetch dt.davis.problems
| filter display_id == "P-XXXXXXXXXX"
| fields event.start, event.end, event.name, event.description, affected_entity_ids, dt.davis.affected_users_count, root_cause_entity_id, root_cause_entity_name
```

### Service-Specific Problem History

```dql
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| filter in(dt.smartscape.service, toSmartscapeId("SERVICE-XXXXXXXXX"))
| summarize problems = count(), by: {event.category, event.status}
```

## Root Cause Analysis Patterns

### Basic Root Cause Query

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| fields
    display_id,
    event.name,
    event.description,
    root_cause_entity_id,
    root_cause_entity_name,
    affected_entity_ids = smartscape.affected_entities[][id]
```

### Root Cause by Entity Type

Identify which entity types most frequently cause problems:

```dql
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| filter isNotNull(root_cause_entity_id)
| summarize problem_count = count(), by:{root_cause_entity_name}
| sort problem_count desc
| limit 20
```

### Affected entity is an AWS resource 

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter iAny(startsWith(smartscape.affected_entities[][type], "AWS_"))
```


### Infrastructure Root Cause with Service Impact

```dql
fetch dt.davis.problems, from:now() - 30m
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter matchesPhrase(root_cause_entity_id, "HOST-")
| filter isNotNull(dt.smartscape.service)
| fields display_id, event.name, root_cause_entity_name, dt.smartscape.service
```

### Problem Blast Radius

Calculate entity impact per root cause:

```dql
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| filter isNotNull(root_cause_entity_id)
| fieldsAdd affected_count = arraySize(smartscape.affected_entities)
| summarize
    avg_affected = avg(affected_count),
    max_affected = max(affected_count),
    problem_count = count(),
    by:{root_cause_entity_name}
| sort avg_affected desc
```

### Recurring Root Causes

Identify entities repeatedly causing problems:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate)
| filter isNotNull(root_cause_entity_id)
| summarize
    problem_count = count(),
    first_occurrence = min(event.start),
    last_occurrence = max(event.start),
    by:{root_cause_entity_id, root_cause_entity_name}
| filter problem_count > 3
| sort problem_count desc
```

### Cause Category vs. Root Cause Entity

These are different questions — pick the right approach:

- **"What causes problems?"** / **"most common cause"** → Summarize by `event.category`
  (SLOWDOWN, ERROR, RESOURCE, AVAILABILITY, CUSTOM). Explain what triggers each category.
- **"Which entity causes problems?"** / **"root cause entity"** → Group by
  `root_cause_entity_name`. Lists specific services, hosts, or apps.

**Cause category breakdown** (use when asked about common causes, patterns, or types):

```dql
fetch dt.davis.problems, from:now() - 30d
| filter not(dt.davis.is_duplicate)
| summarize problem_count = count(), by: {event.category}
| sort problem_count desc
```

Then for each category, explain what triggers it using the Problem Categories table and
cite specific entities from the tenant data as examples.

## Problem Trending and Pattern Analysis

Track problem trends over time, identify recurring issues, and analyze resolution performance.

**Primary Files:**
- `references/problem-trending.md` - Timeseries analysis and pattern detection

**Common Use Cases:**
- Active problems over time with `makeTimeseries`
- Problem creation rate by category
- Recurring problem detection by schedule
- Resolution time trends and P95 duration analysis

**Key Techniques:**
- **`makeTimeseries`** vs **`bin()`**: Choose the right approach for lifecycle spans vs discrete events
- **NULL handling**: Use `coalesce(event.end, now())` for active problems
- **Peak hours analysis**: Identify when problems occur most frequently
- **Impact trending**: Track user impact changes over time

See `references/problem-trending.md` for complete query patterns and best practices.

## Cross-Domain Problem Queries

### Problems Associated with Kubernetes Clusters

Use `affected_entity_ids` or `dt.smartscape_source.id` to find problems related to Kubernetes:

```dql
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| filter matchesPhrase(dt.smartscape_source.id, "KUBERNETES_CLUSTER")
    OR matchesPhrase(dt.smartscape_source.id, "K8S_")
| fields event.start, display_id, event.name, event.category, event.status,
    dt.smartscape_source.id, affected_entity_ids
| sort event.start desc
```

Alternative: expand affected entities and filter for K8s entity types:

```dql
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| expand entity_id = affected_entity_ids
| filter matchesPhrase(entity_id, "KUBERNETES_CLUSTER")
    OR matchesPhrase(entity_id, "K8S_")
| fields event.start, display_id, event.name, event.category, entity_id
| sort event.start desc
```

### Simple Problem Listing

List all problems from the last 24 hours (common request):

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate)
| fields event.start, event.end, display_id, event.name, event.category, event.status
| sort event.start desc
```

## Response Construction

### Problem Cause Summaries

When summarizing problem causes, categories, or patterns, provide a **comprehensive
breakdown** across all standard categories present in the data: AVAILABILITY, ERROR,
SLOWDOWN, RESOURCE, and CUSTOM. For each category found:

1. **Category name** and count of problems
2. **What triggers it** — brief explanation (e.g., RESOURCE = CPU/memory/disk threshold
   exceeded; AVAILABILITY = service or entity became unreachable)
3. **Specific examples** from the tenant's data (affected entity names, problem IDs)

Do not stop after the first two categories — users expect the full picture. Reference
the Problem Categories table above for trigger descriptions.

### Analysis Results

When presenting query results:
- Include **entity names** (not just IDs) — but choose the efficient method:
  - **Few entities (< 5):** `get-entity-name` calls are fine
  - **Many entities:** Use `query-problems` tool which returns names directly, or
    include `root_cause_entity_name` / `entityName()` in the DQL query to resolve
    names inline. Avoid calling `get-entity-name` in a loop for 10+ entities —
    this can exhaust the tool call limit and return no answer at all.
- Provide **actionable recommendations** aligned to the identified causes
- Organize by frequency or impact for easy prioritization

## Best Practices

### Essential Rules

1. **Always filter duplicates**: Use `not(dt.davis.is_duplicate)` to avoid counting the same problem multiple times
2. **Use correct status values**: `"ACTIVE"` or `"CLOSED"`, never `"OPEN"`
3. **Specify time ranges**: Always include time bounds to optimize performance
4. **Include display_id**: Essential for problem identification and linking
5. **Test incrementally**: Add one filter or field at a time when building queries
6. **Filter early**: Apply `not(dt.davis.is_duplicate)` immediately after fetch

### Query Development

- **Start simple**: Begin with basic filtering, then add complexity
- **Test fields first**: Run with `| limit 1` to verify field names exist
- **Use meaningful time ranges**: Too broad wastes resources, too narrow misses data
- **Document problem IDs**: Always capture and store `display_id` for reference

### Root Cause Verification

- Always filter `isNotNull(root_cause_entity_id)` when required
- Cross-reference events using `dt.davis.event_ids`
- Consider time delays: root cause may appear in logs minutes before problem

### Time Range Guidelines

```dql
// ✅ GOOD - Specific time range
fetch dt.davis.problems, from:now() - 4h
```

```dql
// ❌ BAD - Scans all historical data
fetch dt.davis.problems
```

### Absolute Timeframes Require Double Quotes

When using absolute ISO 8601 timestamps for `from` and `to` in DQL queries, **always wrap them in double quotes**. Unquoted timestamps are a syntax error.

```dql
// ✅ CORRECT - absolute timestamps quoted
fetch dt.davis.problems, from: "2026-05-18T22:50:00Z", to: "2026-05-18T23:35:00Z"
| filter not(dt.davis.is_duplicate)
| fields event.start, display_id, event.name, event.category, event.status
| sort event.start desc
```

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| No problems returned | Using `event.status == "OPEN"` | Use `"ACTIVE"` or `"CLOSED"` — `"OPEN"` does not exist |
| Duplicate problems in results | Missing deduplication filter | Add `filter not(dt.davis.is_duplicate)` immediately after fetch |
| Wrong field name (`title`, `status`, `severity`) | SQL-like naming | Use `event.name`, `event.status`, `event.category` — see field name table above |
| `root_cause_entity_id` is null | Not all problems have identified root causes | Add `filter isNotNull(root_cause_entity_id)` when querying root causes |
| Query scans too much data / times out | Missing time range | Always specify `from:now() - <duration>` on the fetch command |
| `affected_entity_ids` is empty array | Problem has no mapped affected entities | Check `dt.smartscape.service` or `dt.smartscape_source.id` as alternatives |

## When to Load References

### Load [problem-trending.md](references/problem-trending.md) when:
- Analyzing problem frequency over time
- Detecting recurring problems on a schedule
- Calculating resolution time trends and P95 durations
- Comparing problem creation rates by category

### Load [problem-correlation.md](references/problem-correlation.md) when:
- Correlating problems with logs or other telemetry
- Investigating events that preceded a problem
- Linking problems to deployment or config changes

### Load [impact-analysis.md](references/impact-analysis.md) when:
- Assessing business impact (affected users, services)
- Calculating blast radius for a root cause entity
- Prioritizing problems by technical and user impact

## References

- [problem-trending.md](references/problem-trending.md) — Problem trending and timeseries analysis patterns
- [problem-correlation.md](references/problem-correlation.md) — Correlating problems with logs and other telemetry
- [impact-analysis.md](references/impact-analysis.md) — Business and technical impact assessment
- [problem-merging.md](references/problem-merging.md) — When and why DAVIS merges events into problems

## Related Skills

- **dt-dql-essentials** - Core DQL syntax and query structure for problem queries
- **dt-obs-logs** - Correlate problems with application and infrastructure logs
- **dt-obs-tracing** - Investigate problems through distributed trace analysis
