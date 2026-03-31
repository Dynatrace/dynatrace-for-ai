---
name: dt-platform
description: "Dynatrace platform operations — billing analytics (DPS consumption, billable usage, feature usage, cost trends, chargeback), audit trail (API calls, settings changes, authentication), query analytics (DQL execution performance, scan costs, failure rates), workflow automation (execution tracking, error rates, action performance), GenAI/CoPilot usage (skill invocations, MCP tools, feedback), and anomaly detector/data management health using dt.system.events."
license: Apache-2.0
---

# dt-platform

Query and analyze Dynatrace platform operational data using DQL. All data lives
in `dt.system.events`, segmented by `event.kind`:

| event.kind | Coverage |
|------------|----------|
| `BILLING_USAGE_EVENT` | DPS consumption, cost trends, chargeback |
| `AUDIT_EVENT` | API calls, auth events, settings changes |
| `QUERY_EXECUTION_EVENT` | DQL query performance, scan costs, failures |
| `WORKFLOW_EVENT` | Workflow/task/action execution, errors |
| `GENAI_EVENT` | CoPilot skills, MCP tools, user feedback |
| `ANALYZER_EXECUTION_EVENT` | Davis anomaly detector runs |
| `ANOMALY_DETECTOR_STATUS_EVENT` | Detector health status changes |
| `ENRICHMENT_EXECUTION_EVENT` | Security intelligence enrichment |
| `EXTENSIONS_EVENT` | Extensions 2.0 self-monitoring (SFM) |
| `DATA_ACQUISITION_EVENT` | Cloud data acquisition status |

## When to Use This Skill

- **Billing & Cost** — DPS consumption breakdown, trends, spike investigation, chargeback/showback, ingestion vs. query vs. retention cost
- **Security & Compliance** — API audit trail, authentication monitoring, settings change tracking, token vs. OAuth analysis
- **Query Optimization** — DQL failure analysis, expensive queries by scan volume, query cost by table/pool/user
- **Automation Health** — Workflow success/failure rates, slowest workflows, lifecycle tracking, sub-workflow and throttling detection
- **AI Usage** — CoPilot skill invocations, MCP tool usage, user adoption, feedback sentiment
- **Platform Health** — Anomaly detector failures, data enrichment, cloud data acquisition, extension self-monitoring

## Agent Instructions

### Intent Mapping

| User Request | Action | Reference |
|---|---|---|
| "cost drivers", "what costs most", "top spenders", "where is spend going" | USD-normalized cost estimation | cost-estimations.md → Estimated Cost by Capability |
| "save money", "reduce costs", "billed costs", "actual bill" | Included volume deduction first, then cost estimation | billing-included-volume.md, then cost-estimations.md |
| "cost by team", "chargeback", "showback" | Cost center attribution | cost-allocation.md |
| "how much log ingest", "trace volume" (single category) | Raw usage query | billing-event-types.md |
| "cost trend", "spending spike", "budget forecast" | Daily cost trend | cost-estimations.md → Daily Cost Trend |
| "who called this API", "audit trail", "settings changes" | Audit event query | audit-events.md |
| "slow queries", "expensive queries", "query failures" | Query analytics | query-analytics.md |
| "workflow errors", "failed automations" | Workflow execution | automation-events.md |
| "CoPilot usage", "AI adoption", "Dynatrace Assist" | GenAI events | genai-events.md |
| "detector failures", "anomaly detection health" | Analyzer events | anomaly-detector-events.md |
| "detector costs", "anomaly detector query cost", "ALERTING pool costs" | Cross-reference detector → query cost | cost-investigation.md → Query Cost Attribution |
| "workflow cost", "what does this workflow cost", "workflow spending" | Composite workflow cost (3 signals) | cost-investigation.md → Workflow Total Cost |
| "what's driving costs", "cost investigation", "cost spike" | Step-by-step cost investigation | cost-investigation.md |
| "query cost by source", "who is scanning most", "cost attribution by app" | BUE query cost by source | cost-investigation.md → Step 1 |
| "enrichment failures", "cloud data issues", "data management" | Data management events | data-management-events.md |
| "extension errors", "extension health", "SFM", "polling failures" | Extension self-monitoring | extensions-events.md |
| "included volume", "billed vs total", "baseline usage" | Included volume analysis | billing-included-volume.md |

### Cost Disclaimer Requirement

When presenting any cost estimation, estimated USD amounts, or rate-card-based
calculations, you **MUST** display the following disclaimer **immediately before
the cost results** (not buried later in the response):

> ⚠️ **Estimated costs only** — Calculated using public list prices as of
> March 2026. Actual costs depend on your negotiated DPS contract. Use for
> directional analysis and relative comparisons, not invoice reconciliation.

This is mandatory for every response that includes dollar amounts or cost
figures. Never omit it, never move it to the bottom of the response.

## Prerequisites

- Access to a Dynatrace environment
- DQL query permissions on `dt.system.events`
- Load `dt-dql-essentials` before writing queries — covers DQL syntax, type
  handling, and field discovery via `dt.semantic_dictionary.fields`

## Knowledge Base Structure

| # | Reference | Content |
|---|-----------|---------|
| 1 | [billing-event-types.md](references/billing-event-types.md) | Billing event type catalog — fields, metering intervals, per-type tables |
| 2 | [billing-usage-queries.md](references/billing-usage-queries.md) | DQL query examples for every billing category |
| 3 | [cost-allocation.md](references/cost-allocation.md) | Cost center/product attribution, chargeback queries |
| 4 | [cost-estimations.md](references/cost-estimations.md) | Public rate card prices, BUE-to-rate-card mapping, cross-capability cost estimation |
| 5 | [billing-included-volume.md](references/billing-included-volume.md) | Metrics/Traces Ingest included volume deduction (14-day limit) |
| 6 | [audit-events.md](references/audit-events.md) | API audit trail, auth events, settings changes, provider/type catalog |
| 7 | [query-analytics.md](references/query-analytics.md) | DQL execution telemetry, scan costs, failure rates, table/pool/user analysis |
| 8 | [automation-events.md](references/automation-events.md) | Workflow/task/action execution, error rates, lifecycle events |
| 9 | [genai-events.md](references/genai-events.md) | CoPilot skills, MCP tools, user feedback analysis |
| 10 | [anomaly-detector-events.md](references/anomaly-detector-events.md) | Davis analyzer execution, detector status events |
| 11 | [data-management-events.md](references/data-management-events.md) | Security enrichment, cloud data acquisition events |
| 12 | [extensions-events.md](references/extensions-events.md) | Extensions 2.0 self-monitoring (SFM), connection errors, polling health |
| 13 | [cost-investigation.md](references/cost-investigation.md) | Step-by-step cost investigation — query attribution, workflow total cost (3 signals) |

## Key Concepts

### Data Source

All platform operational data lives in `dt.system.events`. Filter by
`event.kind` to isolate specific event types. See the
[Platform Event Kind Overview](#platform-event-kind-overview) query below.

### Billing Categories & Billed Unit Fields

All billing events share `event.kind == "BILLING_USAGE_EVENT"`. The
`event.type` field identifies the consumption category (Ingest, Query, Retain,
Host monitoring, RUM, Synthetic, Security, Containers, Automation, Data Egress).

There is **no universal `usage` field** — each event type uses a type-specific
billed field (`billed_bytes`, `data_points`, `billed_gibibyte_hours`, etc.).
See [billing-event-types.md](references/billing-event-types.md) for the
complete catalog of billing categories, per-type billed fields, and metering
intervals.

### Cost & Entity Attribution

See [cost-allocation.md](references/cost-allocation.md) for the full reference
on cost center / product tags, entity references, and the `usage.start` /
`usage.end` / `usage.bucket` measurement window fields.

## Quick Start Workflows

### Platform Event Kind Overview

```dql
fetch dt.system.events, from: -7d
| summarize event_count = count(), by: {event.kind}
| sort event_count desc
```

### Billing Usage Overview

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| summarize event_count = count(), by: {event.type}
| sort event_count desc
```

### Recent Failed API Calls

```dql
fetch dt.system.events, from: -24h
| filter event.kind == "AUDIT_EVENT"
| filter NOT in(event.outcome, "200", "201", "204", "success")
| summarize failures = count(), by: {event.provider, event.type, event.outcome}
| sort failures desc
```

For detailed per-category queries (ingest volumes, chargeback, cost estimation,
query analytics, workflow failures, etc.), see the reference files in the
Knowledge Base Structure table above.

## Common Mistakes & Best Practices

**Mistakes to avoid:**
1. **Summing raw usage across billing categories** — Units are incomparable
   (bytes, GiB-hours, sessions, pod-hours). Use USD-normalized rate-card queries
   from [cost-estimations.md](references/cost-estimations.md).
2. **Using `billed_bytes` for all event types** — Each type has its own billed
   field. Check [billing-event-types.md](references/billing-event-types.md).
3. **Forgetting `dedup event.id` for billing** — Billing events can be refreshed;
   without dedup, aggregations double-count.
4. **Using `dt.system.events` as a `lookup` source** — Use
   `data json:"""..."""` inline lookups instead.
5. **Counting automation events without `state.is_final == true`** — Each
   execution emits RUNNING + final state; counting all doubles the numbers.

**Best practices:**
6. **Always filter by `event.kind` first** — Narrows scope, avoids scanning
   irrelevant event types.
7. **Automation: duration is nanosecond precision** — Use
   `toDouble(duration) / 1000000000` for fractional seconds.
8. **Audit: filter by `event.provider`** — High volume; provider
   filter narrows scope significantly.
9. **Start with short time ranges** — Platform data is high volume; use 7d first.
10. **Empty results?** Verify available event types with the Discovery Query in
    [billing-event-types.md](references/billing-event-types.md).

## Limitations

- **No universal usage field** — Each billing event type uses a different billed
  unit field. You cannot sum across categories without DPS conversion.
- **Public rate card ≠ contract rates** — See [Cost Disclaimer Requirement](#cost-disclaimer-requirement).
- **Included volume limits accuracy** — Metrics/Traces Ingest include a host
  baseline that must be deducted (~14 days max). See [billing-included-volume.md](references/billing-included-volume.md).
- **Cost attribution is optional** — Only populated when configured; Retention
  events often lack entity references.
- **`dt.system.events` cannot be used as a lookup source** — DQL `lookup`
  requires `fetch bizevents` or `data json:"""..."""` as the lookup dataset.
  `fetch dt.system.events` cannot appear in a `lookup` subquery. To join
  platform data with other tables, materialize results first or use
  `data json:"""..."""` inline lookups.

## Next Steps

Load reference files above for detailed per-event-kind queries. Combine with
`dt-dql-essentials` for advanced patterns or `dt-app-dashboards` for operational dashboards.
