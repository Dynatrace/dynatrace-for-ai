---
name: dt-app-notebooks
description: Work with Dynatrace notebooks - create, modify, query, and analyze notebook JSON including sections, DQL queries, visualizations, markdown documentation, and analytics workflows. Supports notebook creation from scratch, section-based updates, data extraction from Document Store, structure analysis, investigation workflows, and collaborative documentation.
license: Apache-2.0
---

# Dynatrace Notebook Skill

## Overview

Dynatrace notebooks are JSON documents stored in the Document Store for interactive data analysis, investigation, and documentation. Each notebook contains:

- **Sections**: Modular blocks organizing markdown and query content
- **DQL Queries**: Executable queries with cached results and visualizations
- **Markdown**: Documentation, context, and narrative content
- **Timeframes**: Default and section-specific time ranges
- **Metadata**: Ownership, versioning, and modification tracking

**When to use this skill:**
- Creating investigation notebooks or analysis templates
- Modifying existing notebooks (queries, sections, visualizations, markdown)
- Querying notebook JSON to extract DQL queries or analyze structure
- Analyzing notebook purpose, investigation workflow, and data coverage
- Building collaborative documentation with embedded analytics

**Four main workflows:**
1. **Creating** - Build notebooks from scratch for investigations, documentation, or query libraries
2. **Modifying** - Update sections, queries, visualizations, markdown, or timeframes
3. **Querying** - Extract data from notebook JSON or search Document Store
4. **Analyzing** - Understand structure, purpose, investigation workflow, and content gaps


## Notebook Document Structure

Notebooks in the Dynatrace Document Store include both metadata and content:

```json
{
  "id": "notebook-abc123",
  "name": "Production Investigation",
  "type": "notebook",
  "owner": "user-uuid",
  "isPrivate": false,
  "version": 42,
  "modificationInfo": {...},
  "content": {
    "version": "7",
    "defaultTimeframe": {
      "from": "now()-2h",
      "to": "now()"
    },
    "sections": [...]
  }
}
```

**Metadata (top-level):**
- `.id` - Document ID (UUID or semantic like "dynatrace.notebooks.getting-started")
- `.name` - Notebook display name
- `.type` - Always "notebook"
- `.owner` - Owner UUID
- `.isPrivate` - Visibility (true = private, false = shared)
- `.version` - Document version (incremental, auto-managed)
- `.modificationInfo` - Creation/modification timestamps

**Notebook content (`.content`):**
- `.content.version` - Content schema version (currently "7")
- `.content.defaultTimeframe` - Default time range for all DQL sections
- `.content.defaultSegments` - Default filter segments (usually empty)
- `.content.sections` - Array of markdown and DQL query sections

All jq examples in this skill use the `.content.*` paths.

---

## When to Load References

This skill uses **progressive disclosure** - load only what you need:

- **Start here:** SKILL.md provides core concepts and quick-start examples
- **Load references on-demand:** Each reference file covers a specific deep-dive topic
- **Context efficiency:** Progressive loading enables task completion without external documentation

**Loading strategy:**
1. Try answering with just SKILL.md first
2. If you need detailed specifications or advanced patterns, load the relevant reference file
3. The "References" section below maps each file to its use case

> 💡 **Tip:** Reference files are linked throughout this document with `→` arrows pointing to when you should load them.

---

## Working with Notebooks

**For detailed workflows and mandatory requirements:**

- **Creating & Updating notebooks** → Load `references/create-update.md` for complete workflow, test-first approach, DQL query validation, and modification patterns
- **Analyzing notebooks** → Load `references/analyzing.md` for structure analysis, JSON extraction, and query execution

**⚠️ MANDATORY for creation/modification:**
1. Always load the relevant reference file first
2. Load relevant skills for query generation (MANDATORY - do not invent queries)
3. Test and validate all DQL queries before adding to notebook (see create-update.md)
4. Validate notebook JSON against schema before save/upload (see Schema Validation below)

---

## Notebook Structure

### Root Properties

**Required properties:**
```json
{
  "version": "7",              // Content schema version (current: "7")
  "sections": []               // Array of markdown and DQL sections
}
```

**Optional properties:**
- `defaultTimeframe` - Default time range for all DQL sections
- `defaultSegments` - Default filter segments (usually empty)

**Structure concept:** Sections are ordered array (display order = array order). Each section has unique UUID. Section types: markdown (documentation) and dql (queries with visualizations).

### Sections Overview

> 📝 **For detailed section specifications, visualization settings, and configuration options**, load `references/sections.md`

**Markdown sections:** `{"type": "markdown", "markdown": "# Content"}`
**DQL sections:** `{"type": "dql", "state": {"input": {"value": "query"}, "visualization": "table"}}`

**Visualizations:** `table`, `lineChart`, `barChart`, `pieChart`, `singleValue`, `areaChart`

→ **See [references/sections.md](references/sections.md) for complete specifications**

---

## Schema Validation

**⚠️ MANDATORY for create/update workflows:** Always validate notebook JSON before save/upload.
→ Load `references/create-update.md` for validation commands, query validation, error interpretation, and test workflow.

**Schema location:** `notebook-schema.json` (Notebook content schema v7)

---

## References

| Reference File | When to Use |
|----------------|-------------|
| [create-update.md](references/create-update.md) | Creating and updating notebooks - workflows, test-first approach, DQL query validation, patterns |
| [analyzing.md](references/analyzing.md) | Extract information from notebooks, understand structure and content, query execution |
| [sections.md](references/sections.md) | Section types, visualization settings, configuration reference |

---

## Common Patterns & Best Practices

**Notebook types:**
- **Investigation**: Markdown context → DQL queries → Analysis → Findings
- **Documentation**: Narrative with embedded queries demonstrating concepts
- **Query Library**: Collection of reusable DQL patterns with explanations

**Key rules:**
- Use unique UUIDs for section IDs · Start with markdown context · Set content version="7" · Use relative timeframes (`now()-2h`) · Omit result objects when creating sections · Order sections logically · Add markdown between query sections for context

**Timeframe strategies:**
- **Default timeframe**: Sets baseline for all DQL sections
- **Section-specific**: Override default for specific queries (e.g., longer lookback for trends)
- **Relative**: `now()-2h`, `now()-7d` for dynamic ranges
- **Absolute**: ISO timestamps for historical analysis

---

## Related Skills

- **dt-dql-essentials** - DQL query syntax, functions, and optimization
- **dt-app-dashboards** - Dashboard creation for operational monitoring (vs notebooks for investigation)
