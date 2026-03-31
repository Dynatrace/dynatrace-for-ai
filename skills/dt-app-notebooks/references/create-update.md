# Notebook Create & Update Workflows

Comprehensive guide for creating new Dynatrace notebooks and updating existing ones.

## Overview

**When to Create vs Update:**
- **Create** - New notebook from scratch
- **Update** - Modify existing notebook (sections, queries, markdown, timeframes)

**Key Principles:**
- Start with context markdown (MANDATORY)
- Test DQL queries before adding
- Follow structured workflow steps
- Maintain narrative flow

---

## Creating Notebooks


### Step 1: Define Notebook Purpose

**BEFORE WRITING ANY JSON, YOU MUST ANSWER:**

- **What is the notebook type?** (investigation, documentation, query library)
- **What questions are you answering?** (Why are errors spiking? How does feature X work?)
- **Who is the audience?** (incident responders, developers, operations team)
- **What is the narrative flow?** (context → exploration → findings)

**Common Notebook Types:**

| Type | Purpose | Section Pattern |
|------|---------|-----------------|
| **Investigation** | Troubleshoot issues, analyze incidents | Context → queries → analysis → findings |
| **Documentation** | Explain systems, demonstrate concepts | Overview → examples → patterns → best practices |
| **Query Library** | Reusable DQL patterns | Category header → query + explanation × N |
| **Analysis** | Trend analysis, capacity planning | Question → data → visualization → interpretation |

---

### Step 2: Plan Section Structure

**Section Planning Template:**

```
1. Markdown: Title and context (what, why, when)
2. DQL: Initial data exploration
3. Markdown: Observations and questions
4. DQL: Deeper analysis query
5. Markdown: Findings and recommendations
```

**Section Organization Patterns:**

**Investigation Pattern:**

```
Context → Symptoms → Root cause queries → Correlation → Findings
```

**Documentation Pattern:**

```
Overview → Concept explanation → Example query → Results interpretation → Best practices
```

**Query Library Pattern:**

```
Category header → Query 1 + docs → Query 2 + docs → ...
```

**Best Practices:**
- Start with markdown context (never start with a query)
- Alternate markdown and DQL for narrative flow
- Use markdown to explain query purpose
- Add findings after queries
- End with markdown summary or next steps

---

### Step 3: Create Minimal Structure

Start with the minimal required structure:

```json
{
  "version": "7",
  "defaultTimeframe": {
    "from": "now()-2h",
    "to": "now()"
  },
  "sections": []
}
```

**Required Properties:**
- `version`: Always "7" (current notebook schema version)
- `sections`: Array of section objects (can start empty)

**Optional Properties:**
- `defaultTimeframe`: Default time range for all query sections
- `defaultSegments`: Default filter segments (usually empty array)

---

### Step 4: Add Opening Context (MANDATORY)

**Always start with markdown context:**

```json
{
  "sections": [
    {
      "id": "8a7f3b21-4c5d-6e2f-1a0b-9c8d7e6f5a4b",
      "type": "markdown",
      "markdown": "# Production Error Spike Investigation\n\n**Date:** 2026-01-27\n**Reporter:** SRE Team\n**Symptom:** 500% increase in error rate at 10:30 UTC\n\n## Goal\nIdentify the root cause and affected services."
    }
  ]
}
```

**Tips:**
- Use descriptive headers (H1 for title, H2 for sections)
- Include context (date, reporter, symptom)
- State the goal or question clearly
- Use markdown formatting for readability

---

### Step 5: Add DQL Query Sections

**Section Structure:**

```json
{
  "id": "1b2c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
  "type": "dql",
  "title": "Error Count by Service",
  "showTitle": true,
  "showInput": true,
  "state": {
    "input": {
      "value": "fetch logs | filter status == \"ERROR\" and timestamp >= now()-2h | summarize error_count = count(), by: {service.name} | sort error_count desc | limit 10",
      "timeframe": {
        "from": "now()-2h",
        "to": "now()"
      }
    },
    "visualization": "table",
    "visualizationSettings": {
      "autoSelectVisualization": false,
      "table": {
        "linewrapEnabled": false
      }
    },
    "querySettings": {
      "maxResultRecords": 1000,
      "defaultScanLimitGbytes": 500,
      "enableSampling": false
    }
  }
}
```

**Section Properties:**
- `id` - Unique UUID for the section (generate with uuidgen or similar)
- `type` - Always "dql" for query sections
- `title` - Optional display title above the query
- `showTitle` - Boolean, show/hide the title
- `showInput` - Boolean, show/hide the query input box
- `height` - Optional height in pixels (default: auto)

**State Properties:**
- `state.input.value` - The DQL query string
- `state.input.timeframe` - Time range for this query
- `state.visualization` - Visualization type (table, lineChart, barChart, pieChart, singleValue)
- `state.visualizationSettings` - Visualization configuration
- `state.querySettings` - Query execution settings

**Important:** DO NOT include `state.result` when creating new sections - Dynatrace populates this when the query executes.

---

### Step 6: Write and TEST DQL Queries (MANDATORY)

🚨 **CRITICAL**: NEVER add a query to notebook without testing it first.

**Test-First Workflow:**

1. **Write query in .dql file (NOT in notebook yet)**

   ```bash
   cat > test-query.dql << 'EOF'
   fetch spans
   | filter dt.smartscape.service == "SERVICE-REAL-ID"
   | summarize count()
   EOF
   ```

2. **Execute query to validate syntax and results**
   - DQL queries MUST be executed before adding to notebook
   - Verify syntax is correct and query returns expected data structure

3. **Verify results:**
   - ✅ Exit code 0 (success)
   - ✅ Returns actual data
   - ✅ Data makes logical sense
   - ✅ Aggregations correct
   - ✅ No syntax errors

4. **Fix any errors:**
   - Read error message
   - Fix syntax/logic
   - Re-test
   - Repeat until query works

5. **ONLY THEN add to notebook JSON**

**Query Testing Checklist:**
- [ ] Query written in .dql file
- [ ] Executed and validated
- [ ] Returns successful results
- [ ] Data verified for correctness
- [ ] No errors encountered

**NEVER:**
- ❌ Write query in notebook JSON first
- ❌ Skip testing phase
- ❌ Add untested queries
- ❌ Assume syntax is correct

**Query Structure:**

```dql-template
fetch [data_source]
| filter [conditions]
| summarize [aggregations], by: {dimensions}
| fieldsAdd [calculations]
| sort [field] [asc|desc]
| limit [count]
```

**Best Practices:**

✅ **DO:**
- Use `limit` to prevent excessive data (e.g., `limit 100`)
- Add `summarize` for aggregations
- Use descriptive field names (`error_count`, not `c`)
- Test and validate queries BEFORE adding to notebook
- Use relative timeframes (`now()-2h`)
- Use REAL entity IDs from the environment

❌ **DON'T:**
- Fetch unlimited data without `limit`
- Omit filter conditions on large datasets
- Use ambiguous field names
- Include `result` objects in new sections
- Use fake/test entity IDs

**Example - Well-Structured Query:**

```dql
fetch logs
| filter loglevel == "ERROR" and timestamp >= now()-2h
| summarize error_count = count(), unique_messages = countDistinct(content), by: {dt.smartscape.service, loglevel}
| sort error_count desc
| limit 20
```

---

### Step 7: Configure Visualizations

**Visualization Selection Guide:**

| Data Type | Recommended Visualization |
|-----------|---------------------------|
| Time-series metrics | `lineChart` |
| Comparisons, rankings | `barChart`, `table` |
| Proportions (≤7 slices) | `pieChart` |
| Single KPI value | `singleValue` |
| Detailed multi-column data | `table` |

**Table Visualization Settings:**

```json
{
  "state": {
    "visualization": "table",
    "visualizationSettings": {
      "autoSelectVisualization": false,
      "table": {
        "linewrapEnabled": true,
        "lineWrapIds": [["content"]],
        "columnOrder": [["service.name"], ["error_count"]],
        "columnWidths": {
          "[\"content\"]": 400
        }
      }
    }
  }
}
```

**Chart Visualization Settings:**

```json
{
  "state": {
    "visualization": "lineChart",
    "visualizationSettings": {
      "autoSelectVisualization": false,
      "chartSettings": {
        "curve": "smooth",
        "legend": {
          "hidden": false
        },
        "fieldMapping": {
          "leftAxisValues": ["error_count"],
          "timestamp": "timeframe"
        }
      }
    }
  }
}
```

---

### Step 8: Configure Timeframes

**Default Timeframe (Content Level):**

```json
{
  "version": "7",
  "defaultTimeframe": {
    "from": "now()-2h",
    "to": "now()"
  }
}
```

**Section-Specific Timeframe (Overrides Default):**

```json
{
  "sections": [
    {
      "type": "dql",
      "state": {
        "input": {
          "timeframe": {
            "from": "now()-7d",
            "to": "now()"
          }
        }
      }
    }
  ]
}
```

**Timeframe Strategies:**
- **Default timeframe**: Sets baseline for all DQL sections
- **Section-specific**: Override for longer/shorter lookback
- **Relative**: `now()-2h`, `now()-7d` for dynamic ranges
- **Absolute**: ISO timestamps for historical analysis (e.g., `2026-01-27T10:00:00Z`)

**Common Timeframes:**
- Investigation: `now()-2h` to `now()` (recent incident)
- Trend analysis: `now()-7d` to `now()` (weekly trends)
- Historical: Absolute timestamps for specific time windows

---

### Step 9: Add Analysis and Findings

**Add markdown sections between queries:**

```json
{
  "sections": [
    {
      "id": "2c3d4e5f-6a7b-8c9d-0e1f-2a3b4c5d6e7f",
      "type": "markdown",
      "markdown": "## Observations\n\n- **auth-service** has 85% of all errors\n- Error spike started at 10:32 UTC\n- Error message: \"Database connection timeout\"\n\n## Next Steps\nInvestigate database connection pool configuration."
    }
  ]
}
```

**Analysis Best Practices:**
- Use bullet points for findings
- Include specific numbers and times
- State what you learned from the query
- Suggest next investigation steps

---

### Step 10: EXECUTE AND VALIDATE NOTEBOOK (MANDATORY)

🚨 **CRITICAL**: Never deploy a notebook without executing ALL queries successfully.

**Validation Protocol:**

1. **Extract and Execute Each Query**

   ```bash
   # Extract all DQL queries from notebook
   jq -r '.sections[] | select(.type == "dql") | .state.input.value' notebook-content.json > all-queries.txt

   # Test each query individually
   jq -r '.sections[] | select(.type == "dql") | .state.input.value' notebook-content.json | \
   while IFS= read -r query; do
       echo "Testing query..."
       # Execute query validation (implementation-specific)
       echo "✅ Query passed"
   done
   ```

2. **Verify Each Query Returns Data**
   - ✅ Exit code 0 (success)
   - ✅ Returns actual data (not empty results)
   - ✅ Data makes logical sense
   - ❌ "No results" = NOT validated

3. **🚨 IF ANY QUERY FAILS:**
   - STOP IMMEDIATELY
   - Read the error message carefully
   - Fix the query in notebook JSON
   - Re-extract and re-test ALL queries
   - Do NOT proceed until all pass

**Quick Validation Commands:**

```bash
# 1. Check JSON syntax
jq . notebook-content.json

# 2. Validate against schema (if using ajv-cli)
ajv validate -s notebook-schema.json -d notebook-content.json

# 3. Count sections
jq '.sections | length' notebook-content.json

# 4. Verify section IDs are unique
jq '.sections[].id' notebook-content.json | sort | uniq -d

# 5. Test ALL queries (batch)
jq -r '.sections[] | select(.type == "dql") | .state.input.value' notebook-content.json | \
while IFS= read -r query; do
    # Execute query validation
done && echo "✅ All queries validated"
```

**Production Readiness Criteria:**

A notebook is production-ready ONLY when ALL of these are true:
- ✅ JSON syntax valid (jq parses without error)
- ✅ Schema validation passes
- ✅ Every DQL query executes successfully (exit 0)
- ✅ Every query returns actual data
- ✅ Tested with real entity IDs from environment
- ✅ Results make logical sense for the use case
- ✅ No syntax errors, no "query failed" messages
- ✅ Narrative flow is clear and logical

**❌ NEVER Deploy If:**
- ANY query fails to execute
- ANY query returns errors
- Queries use fake/example entity IDs
- Validation was skipped
- "No results" without verifying the query is correct

**Validation Checklist:**

📋 [ ] JSON syntax valid (jq parses)
📋 [ ] Schema validation passes
📋 [ ] All section IDs unique
📋 [ ] Version set to "7"
📋 [ ] Every DQL query executed and validated
📋 [ ] Every query returned data successfully
📋 [ ] Tested with real entity IDs
📋 [ ] Results verified for correctness
📋 [ ] No error messages in any query
📋 [ ] Narrative flow logical
📋 [ ] No `result` objects in new sections

**Common Validation Issues:**

| Issue | Fix |
|-------|-----|
| Query syntax error | Read error message, fix query, re-test |
| "contains isn't allowed" | Use correct DQL syntax (e.g., `contains` vs `in`) |
| Empty results | Verify entity IDs are real, adjust filters |
| Timeout errors | Add `limit`, optimize query |
| Missing timeframe | Add `defaultTimeframe` at content level |

---

## Common Creation Patterns

### Pattern 1: Investigation Notebook

**Layout:** Context → Symptom queries → Analysis → Root cause → Remediation

```
1. Markdown: Title, date, symptom, goal
2. DQL: Initial data exploration (errors by service)
3. Markdown: Observations, hypothesis
4. DQL: Detailed analysis (timeline, affected entities)
5. Markdown: Root cause, impact, remediation
```

**Key Features:**
- Clear timeline and facts
- Hypothesis-driven investigation
- Quantified impact
- Actionable remediation

### Pattern 2: Documentation Notebook

**Layout:** Overview → Concept → Example → Interpretation → Best practices

```
1. Markdown: Concept overview
2. DQL: Example query demonstrating concept
3. Markdown: Explain query and results
4. DQL: Advanced variant
5. Markdown: Best practices and pitfalls
```

**Key Features:**
- Educational narrative
- Progressive complexity
- Real examples
- Practical guidance

### Pattern 3: Query Library Notebook

**Layout:** Category headers → Query + documentation pairs

```
1. Markdown: "## Log Analysis Queries"
2. DQL: Query 1
3. Markdown: When to use, what it shows
4. DQL: Query 2
5. Markdown: When to use, what it shows
... repeat
```

**Key Features:**
- Organized by category
- Reusable patterns
- Clear documentation
- Copy-paste ready

---

## Common Creation Pitfalls

❌ **MISTAKE: Including result objects**

```json
{
  "state": {
    "result": {
      "code": 200,
      "value": {...}
    }
  }
}
```

✅ **FIX: Omit results, Dynatrace populates them**

```json
{
  "state": {
    "input": {...},
    "visualization": "table"
  }
}
```

❌ **MISTAKE: Starting with a query**

```json
{
  "sections": [
    {
      "type": "dql",
      "state": {...}
    }
  ]
}
```

✅ **FIX: Always start with markdown context**

```json
{
  "sections": [
    {
      "type": "markdown",
      "markdown": "# Investigation Title\n\nContext here..."
    },
    {
      "type": "dql",
      "state": {...}
    }
  ]
}
```

❌ **MISTAKE: No timeframe specified**

```json
{
  "version": "7",
  "sections": [...]
}
```

✅ **FIX: Include default timeframe**

```json
{
  "version": "7",
  "defaultTimeframe": {
    "from": "now()-2h",
    "to": "now()"
  },
  "sections": [...]
}
```

❌ **MISTAKE: Non-unique section IDs**

```json
{
  "sections": [
    {"id": "1", ...},
    {"id": "1", ...}
  ]
}
```

✅ **FIX: Use unique UUIDs**

```json
{
  "sections": [
    {"id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d", ...},
    {"id": "b2c3d4e5-f6a7-4b5c-9d0e-1f2a3b4c5d6e", ...}
  ]
}
```

---

## Updating Notebooks

### Modification Workflow

1. **Identify changes** - What needs modification?
2. **Locate elements** - Find sections by ID or content
3. **Apply modifications** - Add, remove, or update
4. **Validate** - Check structure and queries
5. **Test** - Verify narrative flow

**Risk assessment:**

| Change | Validation |
|--------|-----------|
| Fix typos | Syntax only |
| Update markdown | Syntax + flow |
| Modify query | Syntax + DQL |
| Add section | Syntax + DQL |
| Remove section | Syntax + flow |
| Reorder sections | Syntax + flow |

---

### Locating Sections

**List all sections:**

```bash
jq '.sections[] | {id, type, title: (.title // .markdown[0:50])}' notebook.json
```

**Find sections by type:**

```bash
# Find all DQL sections
jq '.sections[] | select(.type == "dql")' notebook.json

# Find all markdown sections
jq '.sections[] | select(.type == "markdown")' notebook.json
```

**Find sections by content:**

```bash
# Find DQL sections containing specific query text
jq '.sections[] | select(.type == "dql" and (.state.input.value | contains("ERROR")))' notebook.json

# Find markdown sections containing specific text
jq '.sections[] | select(.type == "markdown" and (.markdown | contains("Root Cause")))' notebook.json
```

---

### Adding Sections

**Markdown Section:**

1. Generate unique UUID
2. Add section to array at desired position
3. Maintain narrative flow

```json
{
  "sections": [
    "... existing sections ...",
    {
      "id": "f7e6d5c4-b3a2-4918-8e7f-6d5c4b3a2918",
      "type": "markdown",
      "markdown": "## Additional Findings\n\n- Discovery 1\n- Discovery 2"
    }
  ]
}
```

**DQL Query Section:**

1. Test query first
2. Generate UUID and add section
3. Include visualization and settings

```json
{
  "sections": [
    "... existing sections ...",
    {
      "id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
      "type": "dql",
      "title": "Service Error Correlation",
      "showTitle": true,
      "showInput": true,
      "state": {
        "input": {
          "value": "fetch logs | filter loglevel == \\\"ERROR\\\" | summarize count(), by: {dt.smartscape.service, dt.smartscape.host} | sort count desc | limit 20",
          "timeframe": {
            "from": "now()-2h",
            "to": "now()"
          }
        },
        "visualization": "table",
        "visualizationSettings": {
          "autoSelectVisualization": false
        },
        "querySettings": {
          "maxResultRecords": 1000
        }
      }
    }
  ]
}
```

**Position considerations:**
- Add at end: Append to sections array
- Insert in middle: Array order determines display order
- After query: Add observations after related DQL section

---

### Removing Sections

**Steps:**

1. Identify section to remove
2. Remove section from array
3. Verify narrative still flows

```bash
# List sections with indices
jq '.sections | to_entries[] | {index: .key, id: .value.id, type: .value.type}' notebook.json

# Remove section with specific ID
jq '.sections = [.sections[] | select(.id != "section-id-to-remove")]' notebook.json > notebook-updated.json

# Remove section at index 2 (0-based)
jq 'del(.sections[2])' notebook.json > notebook-updated.json
```

**Verify:**
- Read markdown context around removed section
- Ensure no references to removed content
- Check if surrounding sections need updates

---

### Updating Queries

**Common query updates:**
- Fix syntax errors
- Add filters
- Change aggregations
- Optimize performance
- Update timeframes

**Before Making Changes:**
1. Copy original query for rollback
2. Test new query in DQL console or notebook
3. Verify results match expectations

**Example - Add Filter:**

```json
// Before
{
  "state": {
    "input": {
      "value": "fetch logs | summarize count(), by: {service.name}"
    }
  }
}

// After
{
  "state": {
    "input": {
      "value": "fetch logs | filter loglevel == \"ERROR\" | summarize count(), by: {service.name}"
    }
  }
}
```

**Example - Optimize with Limit:**

```json
// Before (potentially slow)
{
  "state": {
    "input": {
      "value": "fetch logs | summarize count(), by: {host.name}"
    }
  }
}

// After (optimized)
{
  "state": {
    "input": {
      "value": "fetch logs | summarize count(), by: {host.name} | sort count desc | limit 20"
    }
  }
}
```

**Example - Update Timeframe:**

```json
// Before: 2-hour window
{
  "state": {
    "input": {
      "timeframe": {
        "from": "now()-2h",
        "to": "now()"
      }
    }
  }
}

// After: 24-hour window for trends
{
  "state": {
    "input": {
      "timeframe": {
        "from": "now()-24h",
        "to": "now()"
      }
    }
  }
}
```

**Query Optimization Checklist:**

✅ **Performance improvements:**
- [ ] Add `limit` clause to cap results
- [ ] Use `filter` early in query pipeline
- [ ] Replace multiple queries with single query using `by: {dimension}`
- [ ] Use `timeseries` with appropriate `interval` for time-series data
- [ ] Remove unnecessary fields or calculations

❌ **Avoid:**
- Unlimited result sets on large datasets
- Complex calculations without `summarize`
- Fetching all data then filtering (filter first)
- Overly broad timeframes without need

---

### Editing Markdown

**Common markdown updates:**
- Fix typos
- Add findings
- Update timestamps
- Add observations
- Clarify context

**Example - Add Findings:**

```json
// Before
{
  "markdown": "## Initial Analysis\n\nLooking at error distribution..."
}

// After
{
  "markdown": "## Initial Analysis\n\nLooking at error distribution...\n\n### Findings\n- 85% of errors from auth-service\n- Peak at 10:32 UTC\n- Root cause: Database connection timeout"
}
```

**Example - Update Context:**

```json
// Before
{
  "markdown": "# Investigation Started\n\nAnalyzing error spike."
}

// After
{
  "markdown": "# Investigation Completed\n\n**Status:** RESOLVED\n**Start:** 2026-01-27 10:45 UTC\n**End:** 2026-01-27 11:30 UTC\n**Root Cause:** Database connection pool exhaustion\n\nAnalyzing error spike."
}
```

**Markdown Best Practices:**
- Use headings (H2, H3) for structure
- Use bullet points for findings
- Include timestamps for investigations
- Add status indicators (OPEN, IN PROGRESS, RESOLVED)
- Link to related tickets or documentation

---

### Reordering Sections

**Sections display in array order** - reorder by rearranging array elements.

**Example - Move section up:**

```json
// Before: [section-1, section-2, section-3, section-4]
// Move section-3 before section-2
// After: [section-1, section-3, section-2, section-4]

{
  "sections": [
    {"id": "section-1", "type": "markdown", "markdown": "# Title"},
    {"id": "section-3", "type": "dql", "title": "Moved query"},
    {"id": "section-2", "type": "dql", "title": "Original query"},
    {"id": "section-4", "type": "markdown", "markdown": "## Findings"}
  ]
}
```

**Using jq to reorder:**

```bash
# Swap sections at indices 1 and 2
jq '.sections = [.sections[0], .sections[2], .sections[1]] + .sections[3:]' notebook.json
```

**Reordering strategies:**
- Group related queries together
- Move context before queries
- Move findings after queries
- Organize chronologically for investigations

---

### Modifying Visualizations

**Change Visualization Type:**

```json
// Before: Table
{
  "state": {
    "visualization": "table",
    "visualizationSettings": {
      "table": {
        "linewrapEnabled": false
      }
    }
  }
}

// After: Line chart
{
  "state": {
    "visualization": "lineChart",
    "visualizationSettings": {
      "chartSettings": {
        "curve": "smooth",
        "legend": {
          "hidden": false
        }
      }
    }
  }
}
```

**Visualization Selection:**
- **table** → Multi-column data, logs, detailed results
- **lineChart** → Time-series trends
- **barChart** → Comparisons, rankings
- **pieChart** → Proportions (≤7 categories)
- **singleValue** → Single KPI or metric

**Update Visualization Settings:**

```json
// Enable Table Line Wrapping
{
  "state": {
    "visualizationSettings": {
      "table": {
        "linewrapEnabled": true,
        "lineWrapIds": [["content"]],
        "columnWidths": {
          "[\"content\"]": 500
        }
      }
    }
  }
}
```

---

## Common Modification Patterns

### Pattern 1: Adding Investigation Steps

**Scenario:** Add new analysis to existing investigation

**Steps:**
1. Read through existing sections to understand narrative
2. Identify insertion point (after related query)
3. Add markdown explaining new hypothesis
4. Add DQL query to test hypothesis
5. Add markdown with findings

**Example:**

```json
{
  "sections": [
    "... existing sections ...",
    {
      "id": "new-uuid-1",
      "type": "markdown",
      "markdown": "## Hypothesis: Related Database Issues\n\nChecking if database errors correlate with service errors."
    },
    {
      "id": "new-uuid-2",
      "type": "dql",
      "title": "Database Connection Errors",
      "state": {
        "input": {
          "value": "fetch logs | filter dt.entity.type == \"DATABASE\" and loglevel == \"ERROR\" | timeseries count(), interval: 1m"
        }
      }
    },
    {
      "id": "new-uuid-3",
      "type": "markdown",
      "markdown": "### Findings\n\nDatabase errors start at 10:31 UTC, 1 minute before service errors. Strong correlation confirmed."
    }
  ]
}
```

### Pattern 2: Updating Investigation Status

**Scenario:** Mark investigation as resolved

**Steps:**
1. Update title markdown with status
2. Add resolution section at end
3. Update relevant queries if needed

**Example:**

```json
{
  "sections": [
    {
      "id": "title-section",
      "type": "markdown",
      "markdown": "# [RESOLVED] Production Error Spike\n\n**Status:** Resolved\n**Resolution Time:** 2026-01-27 11:30 UTC\n**Root Cause:** Database connection pool exhaustion"
    },
    "... analysis sections ...",
    {
      "id": "resolution-section",
      "type": "markdown",
      "markdown": "## Resolution\n\n### Actions Taken\n1. Increased connection pool from 50 to 100\n2. Deployed hotfix v2.3.2\n3. Added connection pool monitoring\n\n### Verification\nError rate returned to baseline (0.5%) at 11:25 UTC.\n\n### Follow-up\n- [ ] Review connection pool sizing for all services\n- [ ] Add capacity planning to sprint"
    }
  ]
}
```

### Pattern 3: Optimizing Slow Queries

**Scenario:** Notebook sections taking too long to execute

**Steps:**
1. Identify slow queries (check execution time in results)
2. Add filters to reduce data volume
3. Add limit clauses
4. Use appropriate time windows

**Example:**

```json
// Before: Slow query
{
  "state": {
    "input": {
      "value": "fetch logs | summarize count(), by: {host.name, service.name, pod.name}",
      "timeframe": {
        "from": "now()-7d",
        "to": "now()"
      }
    }
  }
}

// After: Optimized query
{
  "state": {
    "input": {
      "value": "fetch logs | filter loglevel == \"ERROR\" | summarize count(), by: {service.name} | sort count desc | limit 20",
      "timeframe": {
        "from": "now()-2h",
        "to": "now()"
      }
    }
  }
}
```

---

## Safety and Rollback

### Backup Strategy

**Before significant changes:**

```bash
# Create backup
cp notebook.json notebook-backup-$(date +%Y%m%d-%H%M%S).json
```

**Version control:**

```bash
# Track changes with git
git add notebook.json
git commit -m "Add correlation analysis section"
```

### Rollback

**If modification causes issues:**

1. **Restore from backup:**

```bash
cp notebook-backup.json notebook.json
```

2. **Selective rollback:**

```bash
# Remove last section added
jq 'del(.sections[-1])' notebook.json
```

### Validation Checklist

Before applying modifications:

📋 [ ] JSON syntax valid (`jq . notebook.json`)
📋 [ ] All section IDs are unique
📋 [ ] No duplicate section IDs
📋 [ ] All DQL queries tested and valid
📋 [ ] Timeframes appropriate
📋 [ ] No result objects in sections
📋 [ ] Narrative flow maintained
📋 [ ] Markdown formatting correct
📋 [ ] Backup created

---

## Anti-Patterns

❌ **MISTAKE: Changing section type**

```json
// Before
{"id": "uuid", "type": "markdown", "markdown": "..."}

// After - DON'T DO THIS
{"id": "uuid", "type": "dql", "state": {...}}
```

✅ **FIX: Remove old section, add new section with new UUID**

❌ **MISTAKE: Duplicate section IDs**

```json
{
  "sections": [
    {"id": "same-uuid", "type": "markdown"},
    {"id": "same-uuid", "type": "dql"}
  ]
}
```

✅ **FIX: Generate unique UUID for each section**

❌ **MISTAKE: Including result objects**

```json
{
  "state": {
    "result": {
      "code": 200,
      "value": {...}
    }
  }
}
```

✅ **FIX: Remove all result objects before saving**

❌ **MISTAKE: Breaking narrative flow**

```json
{
  "sections": [
    {"type": "dql", "title": "Query"},
    {"type": "markdown", "markdown": "Context that should come first"},
    {"type": "dql", "title": "Related query"}
  ]
}
```

✅ **FIX: Reorder sections for logical flow**

---

## Related Resources

**Reference Files:**
- [sections.md](./sections.md) - Section types and structure reference
- [analyzing.md](./analyzing.md) - Extract and understand notebook content
