# Problem Impact Analysis

Assess business and technical impact of DAVIS problems by analyzing affected users, entities, service dependencies, and problem scope to prioritize incident response.

## Overview

Impact analysis helps answer critical questions:
- **How many users are affected?** (`dt.davis.affected_users_count`)
- **Which services are impacted?** (`dt.smartscape.service`, `smartscape.affected_entity.ids`)
- **What is the blast radius?** (count of affected entities)
- **At what system layer?** (`dt.davis.impact_level`)
- **How critical is this?** (combination of users + services + category)

## Key Impact Fields

| Field | Description | Type | Usage |
|-------|-------------|------|-------|
| `dt.davis.affected_users_count` | Estimated users impacted | integer | Prioritization metric |
| `dt.davis.impact_level` | System layer (Application, Services, Infrastructure) | string | Determines user visibility |
| `smartscape.affected_entity.ids` | Array of directly impacted entity IDs | array | Calculate blast radius |
| `smartscape.affected_entity.types` | Types of affected entities | array | Understand scope |
| `dt.smartscape.service` | Affected service IDs | array | Business criticality |
| `event.category` | Problem type (AVAILABILITY, ERROR, etc.) | string | Severity indicator |

## User Impact Analysis

### High-Impact Problems

Problems affecting many users:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter dt.davis.affected_users_count > 0
| fields
    display_id,
    event.name,
    event.category,
    dt.davis.affected_users_count,
    dt.davis.impact_level
| sort dt.davis.affected_users_count desc
```

### User Impact Threshold Categorization

Classify problems by user impact severity:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter isNotNull(dt.davis.affected_users_count)
| fieldsAdd impact_severity = if(dt.davis.affected_users_count > 1000, "CRITICAL",
    else: if(dt.davis.affected_users_count > 100, "HIGH",
    else: if(dt.davis.affected_users_count > 10, "MEDIUM", else: "LOW")))
| summarize problem_count = count(), by:{impact_severity, event.category}
| sort impact_severity asc
```

### User Impact Trending

Track user impact over time:

```dql
fetch dt.davis.problems, from:now() - 14d
| filter not(dt.davis.is_duplicate)
| filter isNotNull(dt.davis.affected_users_count)
| summarize
    total_users_affected = sum(dt.davis.affected_users_count),
    avg_users_per_problem = avg(dt.davis.affected_users_count),
    max_users_in_problem = max(dt.davis.affected_users_count),
    by:{time_bucket = bin(event.start, 1h)}
| sort time_bucket asc
```

### Active Problem Impact Dashboard

Real-time impact view:

```dql
fetch dt.davis.problems, from:now() - 2h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| summarize
    total_problems = count(),
    total_affected_users = sum(dt.davis.affected_users_count),
    total_affected_entities = sum(arraySize(smartscape.affected_entity.ids)),
    critical_problems = countIf(dt.davis.affected_users_count > 100),
    availability_issues = countIf(event.category == "AVAILABILITY"),
    error_issues = countIf(event.category == "ERROR")
```

## Service Impact Analysis

### Multi-Service Impact

Problems affecting multiple services:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| fieldsAdd service_count = arraySize(dt.smartscape.service)
| filter service_count > 1
| fields display_id, event.name, service_count, dt.smartscape.service
| sort service_count desc
```

### Business-Critical Service Problems

Focus on specific critical services:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate)
| expand dt.smartscape.service
| filter dt.smartscape.service == "SERVICE-CRITICAL-APP"
| fields
    event.start,
    display_id,
    event.name,
    event.status,
    event.category,
    dt.davis.affected_users_count,
    dt.smartscape.service
| sort event.start desc
```

### Service Problem History

Identify services with recurring problems:

```dql
fetch dt.davis.problems, from:now() - 30d
| filter not(dt.davis.is_duplicate)
| expand dt.smartscape.service
| summarize
    problem_count = count(),
    unique_categories = collectDistinct(event.category),
    total_users_affected = sum(dt.davis.affected_users_count),
    avg_users_per_problem = avg(dt.davis.affected_users_count),
    by:{dt.smartscape.service}
| filter problem_count > 5
| sort problem_count desc
```

### Service Dependency Impact

When one service affects many others:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter isNotNull(root_cause_entity_id)
| fieldsAdd downstream_services = arraySize(dt.smartscape.service)
| filter downstream_services > 1
| fields
    display_id,
    event.name,
    root_cause_entity_name,
    downstream_services,
    dt.smartscape.service
| sort downstream_services desc
```

## Entity Impact Analysis

### Problem Blast Radius

Calculate how many entities each problem affects:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| fieldsAdd affected_count = arraySize(smartscape.affected_entity.ids)
| fields display_id, event.name, event.category, affected_count
| sort affected_count desc
```

### Scope Categorization

Categorize by breadth of impact:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate)
| fieldsAdd affected_count = arraySize(smartscape.affected_entity.ids)
| fieldsAdd scope = if(affected_count == 1, "Single",
    else: if(affected_count <= 5, "Limited",
    else: if(affected_count <= 20, "Moderate", else: "Wide")))
| summarize problem_count = count(), by:{scope, event.category}
| sort scope asc
```

### Entity Type Impact

Which entity types are most frequently affected:

```dql
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| expand smartscape.affected_entity.types
| summarize
    problem_count = count(),
    avg_users_affected = avg(dt.davis.affected_users_count),
    by:{smartscape.affected_entity.types}
| sort problem_count desc
```

### Cross-Entity Problems

Entities appearing in multiple problems:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate)
| expand smartscape.affected_entity.ids
| summarize
    problem_count = countDistinct(display_id),
    categories = collectDistinct(event.category),
    total_user_impact = sum(dt.davis.affected_users_count),
    by:{smartscape.affected_entity.ids}
| filter problem_count > 1
| sort problem_count desc
```

## Impact Level Analysis

### Distribution by Impact Level

Analyze problems by system layer:

```dql
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| summarize
    problem_count = count(),
    avg_affected_users = avg(dt.davis.affected_users_count),
    total_affected_users = sum(dt.davis.affected_users_count),
    by:{dt.davis.impact_level, event.category}
| sort problem_count desc
```

### Application-Level Problems

Focus on user-facing issues:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter dt.davis.impact_level == "Application"
| fields
    display_id,
    event.name,
    event.category,
    dt.davis.affected_users_count,
    dt.smartscape.service
| sort dt.davis.affected_users_count desc
```

## Combined Impact Scoring

### Priority Score Calculation

Create a composite priority score:

```dql
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| fieldsAdd
    user_score = coalesce(dt.davis.affected_users_count, 0) / 10,
    entity_score = arraySize(smartscape.affected_entity.ids) * 5,
    category_score = if(event.category == "AVAILABILITY", 100,
        else: if(event.category == "ERROR", 50,
        else: if(event.category == "SLOWDOWN", 25, else: 10))),
    priority_score = user_score + entity_score + category_score
| fields display_id, event.name, priority_score, event.category, dt.davis.affected_users_count
| sort priority_score desc
| limit 20
```

### Critical Problem Identification

Multi-criteria critical problem detection:

```dql
fetch dt.davis.problems, from:now() - 4h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| fieldsAdd
    is_high_user_impact = dt.davis.affected_users_count > 100,
    is_availability_issue = event.category == "AVAILABILITY",
    is_wide_scope = arraySize(smartscape.affected_entity.ids) > 10,
    is_critical = is_high_user_impact or is_availability_issue or is_wide_scope
| filter is_critical
| fields
    display_id,
    event.name,
    dt.davis.affected_users_count,
    event.category,
    affected_entity_count = arraySize(smartscape.affected_entity.ids)
| sort dt.davis.affected_users_count desc
```

## Time-Based Impact Analysis

### Problem Duration vs Impact

Analyze if high-impact problems take longer to resolve:

```dql
fetch dt.davis.problems, from:now() - 30d
| filter not(dt.davis.is_duplicate) and event.status == "CLOSED"
| filter isNotNull(dt.davis.affected_users_count)
| fieldsAdd
    duration_minutes = (event.end - event.start) / 60000000000,
    impact_category = if(dt.davis.affected_users_count > 100, "High",
        else: if(dt.davis.affected_users_count > 10, "Medium", else: "Low"))
| summarize
    avg_duration = avg(duration_minutes),
    p95_duration = percentile(duration_minutes, 95),
    problem_count = count(),
    by:{impact_category}
```

### Peak Impact Hours

When do high-impact problems occur:

```dql
fetch dt.davis.problems, from:now() - 7d
| filter not(dt.davis.is_duplicate)
| filter dt.davis.affected_users_count > 50
| fieldsAdd hour_of_day = formatTimestamp(event.start, format:"HH")
| summarize
    problem_count = count(),
    avg_users_affected = avg(dt.davis.affected_users_count),
    by:{hour_of_day}
| sort hour_of_day asc
```

## Best Practices

### Prioritization Strategy

1. **User-facing first**: `affected_users_count > 0` = highest priority
2. **Impact level**: `Application` level indicates end-user visibility
3. **Scope**: More affected entities = wider blast radius
4. **Category**: `AVAILABILITY` typically more urgent than `SLOWDOWN`
5. **Root cause**: Infrastructure problems may have cascading effects

### Query Optimization

```dql
// ✅ GOOD - Filter early, calculate later
fetch dt.davis.problems, from:now() - 4h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter dt.davis.affected_users_count > 50
| fieldsAdd priority_score = dt.davis.affected_users_count * 10
```

```dql
// ❌ BAD - Calculating before filtering
fetch dt.davis.problems, from:now() - 4h
| fieldsAdd priority_score = dt.davis.affected_users_count * 10
| filter not(dt.davis.is_duplicate)
```

### Handle Null Values

```dql
// ❌ WRONG - Nulls sort first, skew results
fetch dt.davis.problems
| sort dt.davis.affected_users_count desc
```

```dql
// ✅ CORRECT - Filter nulls first
fetch dt.davis.problems
| filter isNotNull(dt.davis.affected_users_count)
| sort dt.davis.affected_users_count desc
```

```dql
// ✅ CORRECT - Use coalesce for calculations
fetch dt.davis.problems
| fieldsAdd user_score = coalesce(dt.davis.affected_users_count, 0) * 10
```

### Array Field Handling

```dql
// ✅ CORRECT - Check array size
fetch dt.davis.problems
| fieldsAdd service_count = arraySize(dt.smartscape.service)
| filter service_count > 0
```

```dql
// ✅ CORRECT - Check array contains
fetch dt.davis.problems
| filter in("SERVICE-ABC", dt.smartscape.service)
```

```dql
// ✅ CORRECT - Expand array for aggregation
fetch dt.davis.problems
| expand dt.smartscape.service
| summarize count(), by:{dt.smartscape.service}
```

## Investigation Workflow

### Step 1: Identify High-Impact Active Problems

```dql
fetch dt.davis.problems, from:now() - 2h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| filter dt.davis.affected_users_count > 10 or arraySize(smartscape.affected_entity.ids) > 5
| fields display_id, event.name, event.category, dt.davis.affected_users_count
| sort dt.davis.affected_users_count desc
```

### Step 2: Assess Service Impact

```dql
fetch dt.davis.problems
| filter display_id == "P-XXXXXXXXXX"
| fields display_id, dt.smartscape.service, smartscape.affected_entity.ids, dt.davis.impact_level
```

### Step 3: Calculate Blast Radius

```dql
fetch dt.davis.problems
| filter display_id == "P-XXXXXXXXXX"
| fieldsAdd
    total_entities = arraySize(smartscape.affected_entity.ids),
    total_services = arraySize(dt.smartscape.service)
| fields display_id, total_entities, total_services, smartscape.affected_entity.ids
```

### Step 4: Correlate with Business Context

- Map affected services to business functions
- Check if critical services are impacted
- Consider time of day (business hours vs off-hours)
- Assess compliance/SLA implications

## Common Pitfalls

### Not Filtering Duplicates

```dql
// ❌ WRONG - Counts duplicate problems
fetch dt.davis.problems, from:now() - 24h
| summarize total_users = sum(dt.davis.affected_users_count)
```

```dql
// ✅ CORRECT
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate)
| summarize total_users = sum(dt.davis.affected_users_count)
```

### Ignoring Active vs Closed Status

```dql
// ❌ WRONG - Includes resolved problems in "current impact"
fetch dt.davis.problems, from:now() - 24h
| summarize current_impact = sum(dt.davis.affected_users_count)
```

```dql
// ✅ CORRECT
fetch dt.davis.problems, from:now() - 24h
| filter not(dt.davis.is_duplicate) and event.status == "ACTIVE"
| summarize current_impact = sum(dt.davis.affected_users_count)
```

### Not Considering Time Context

```dql
// ❌ BAD - Too broad, includes old problems
fetch dt.davis.problems
| filter event.status == "ACTIVE"
```

```dql
// ✅ GOOD - Recent problems only
fetch dt.davis.problems, from:now() - 4h
| filter event.status == "ACTIVE"
```

## Related Documentation

- **problem-correlation.md**: Correlating problems with logs and telemetry
- **../SKILL.md**: Core problem analysis concepts
