---
name: dt-platform-costs
description: "Query and analyze a Dynatrace tenant's ACTUAL billing and usage data with DQL against dt.system.events — DPS consumption breakdown, cost-normalized spend ranking, included volume deduction, chargeback/showback, cost drivers, spending trends, cost investigation, metrics ingest optimization, query cost attribution, workflow total cost, entity-level cost drill-down (RUM, hosts, synthetic, K8s), and AI/LLM cost (AI Units, AI Function Standard Calls, AI-generated query consumption). Directs licensing/entitlement questions to documentation (not via DQL). USE ONLY to query/analyze the tenant's actual consumption. Do NOT use for conceptual 'explain' questions about how DPS billing/pricing works or what units/weights/the rate card mean — see Dynatrace documentation. Do NOT use for making DQL queries faster or cheaper to run (query optimization, reducing scanned data/consumption per run, filter-early best practices) — that belongs to dt-dql-essentials. This skill MEASURES consumption; it does not tune queries."
license: Apache-2.0
---

# dt-platform-costs

> **⛔ FIRST — CHECK SCOPE BEFORE DOING ANYTHING ELSE.**
> This skill **only** queries and analyzes a tenant's **actual** consumption
> data. It does **not** teach billing concepts. If the user is asking *how*
> billing/pricing works, *how* costs are calculated, what units / normalization
> weights / the rate card *mean*, or any conceptual "explain" question about DPS
> billing — **this skill does not answer it.** See
> [Billing Concepts — STOP](#billing-concepts--stop) and respond with **only**
> the prescribed two-sentence documentation redirect. Do **not** explain units,
> weights, included volume, or methodology, and do **not** show the Getting
> Started menu. Continue into the rest of this skill **only** when the user wants
> to query or analyze their own tenant's numbers.

Query and analyze Dynatrace platform billing and cost data using DQL. All data
lives in `dt.system.events` with `event.kind == "BILLING_USAGE_EVENT"`,
segmented by `event.type` (consumption category).

> **Scope boundary**: This skill covers Dynatrace *platform* billing (DPS consumption). For AWS cloud *infrastructure* costs ingested via FOCUS, use `dt-biz-cloud-costs` instead.

## Dynatrace Platform Subscription (DPS)

This skill applies **exclusively to DPS-licensed environments**. All billing
event types, unit conversions, the public rate card, and cost estimation
workflows are DPS-specific.

**NEVER apply this skill's unit conversions or cost estimates to classic license
models** (host units, DDUs, DEM units, ASUs). If the user mentions classic
licensing terms or units, explain that this skill covers DPS only and refer
them to https://docs.dynatrace.com/docs/license/monitoring-consumption-classic
for details.

## Licensing / Entitlement Questions — STOP

**Triggers:** "Am I allowed to use X?", "Is X licensed?", "Is X in my subscription?", "Do I have entitlement for X?"

**STOP — do not execute any DQL queries.** Billing usage events record **active
consumption only**, not subscription entitlements. Absence of billing events
means not currently consumed, NOT unlicensed. Do not infer entitlement from
usage patterns or their absence. **Respond directly without queries** and
direct to **Account Management > Subscription > Pricing**.

> **❌** Query billing events → no results → conclude "not licensed" — **WRONG** (absence ≠ no entitlement)
> **✅** Respond immediately: "Entitlement data is not available via DQL. Check Account Management > Subscription > Pricing."

## Billing Concepts — STOP

**Triggers:** "How does billing work?", "How are costs calculated?", "Explain DPS billing", "How is X billed?", "What is the billing model?", "How does DPS pricing work?", "How does Dynatrace charge?", "Explain the rate card"

**STOP — do not answer from this skill's content.** The normalization weights,
unit conversion formulas, and lookup values in this skill are **DQL-generation
tools**, not user-facing billing education. Presenting them as an explanation of
DPS billing is wrong — they are internal ranking aids, not contracted rates.

**Your entire response must be ONLY the two sentences below — nothing else.** Do
**not** list capabilities or units, do **not** describe metering, included
volume, or normalization, do **not** add a "How costs are calculated" section,
and do **not** append the Getting Started menu or a list of example prompts
beyond the single one shown:

> **❌** Explain metering / units / normalization weights, then offer the Getting Started menu — **WRONG** (that is the exact failure to avoid)
> **✅** Respond with *only*: "For how DPS pricing and billing work, see the [Dynatrace Platform Subscription documentation](https://docs.dynatrace.com/docs/manage/subscriptions-and-licensing/dynatrace-platform-subscription). If you'd like to analyze your tenant's actual consumption, ask e.g. *'What are my top cost drivers for the last 7 days?'*"

## When to Use This Skill

- **Usage Overview** — DPS consumption breakdown by capability, unit conversion, cross-capability comparison
- **Cost Estimation** — Cost-normalized usage comparison and relative spend ranking, daily cost trends, spending spikes
- **Cost Investigation** — Step-by-step drill-down into cost drivers, query scan cost attribution, workflow total cost (4 signals)
- **Chargeback / Showback** — Cost center and product attribution, team-level billing
- **Included Volume** — Metrics/Traces Ingest baseline deduction, billed vs. total usage

This skill **queries and analyzes** existing consumption data. It is not a DPS
pricing guide — for billing concepts, see the
[official documentation](https://docs.dynatrace.com/docs/manage/subscriptions-and-licensing/dynatrace-platform-subscription).


## Agent Instructions

### Intent Mapping

| User Request | Action | Reference |
|---|---|---|
| "how can you help", "what can you do", "where do I start", "help me understand my costs", "what can I analyze", "show me what's possible", "what is this skill", "help", "capabilities", "getting started", "tell me what you can do", "what are your capabilities" | Present Getting Started menu — 5 use cases with one suggested prompt each. **Do not run any queries yet.** | [Getting Started](#getting-started) |
| "am I allowed to use X", "is X licensed", "is X in my subscription", "entitlement for X", "can I use X from licensing perspective" | **STOP — do not query.** Respond directly: entitlement data is not available via DQL. Direct to Account Management > Subscription > Pricing. | [Entitlement — STOP](#licensing--entitlement-questions--stop) |
| "how does billing work", "how are costs calculated", "explain DPS billing", "how is X billed", "what is the billing model", "how does DPS pricing work", "how does Dynatrace charge", "explain the rate card" | **STOP — do not answer from skill content.** Respond directly: redirect to official documentation. | [Billing Concepts — STOP](#billing-concepts--stop) |
| "usage overview", "usage per capability", "what am I using", "how much usage" | Cross-capability usage with unit conversion (no cost) | billing-capabilities.md -> Cross-Capability Usage (4 Queries) |
| "cost drivers", "what costs most", "top spenders", "where is spend going" | Run Combined Query + Full Inline Lookup, sort by `cost_weight desc` in DQL | cost-estimations.md -> Estimated Cost by Capability |
| "save money", "reduce costs", "billed costs", "actual bill" | Usage with included volume deduction, then cost estimation | billing-capabilities.md -> Cross-Capability Usage (4 Queries), then cost-estimations.md |
| "cost by team", "chargeback", "showback" | Cost center attribution | cost-allocation.md |
| "metrics ingest by cost center", "metrics chargeback", "billable data points per team" | Metrics Ingest billable volume per cost center (with included volume deduction) | cost-allocation.md -> Metrics Ingest — Billable Volume per Cost Center |
| "how much log ingest", "trace volume" (single category) | Single-category usage query | billing-event-types.md, billing-capabilities.md |
| "cost trend", "spending spike", "budget forecast" | Daily cost trend | cost-estimations.md -> Daily Cost Trend |
| "compare this week to last", "week over week", "WoW", "MoM", "month over month", "how did costs change", "cost change vs last week", "cost change vs last month", "period comparison", "what grew", "what shrank", "usage trend", "notable changes in usage" | Period Comparison — two explicit UTC windows, compare `capability_usage` per capability, sort by largest absolute cost-weight delta | cost-estimations.md -> Period Comparison (WoW / MoM) |
| "detector costs", "anomaly detector query cost", "ALERTING pool costs" | Cross-reference detector -> query cost | query-cost-attribution.md |
| "workflow cost", "what does this workflow cost", "workflow spending" | Composite workflow cost (4 signals) | workflow-total-cost.md |
| "which workflow", "workflow name", "workflow owner", "how often does this workflow run", "workflow frequency" | Resolve workflow name/owner and run frequency | workflow-total-cost.md → Cross-Event Field Reference + Owner Identification + How Often Did the Workflow Run |
| "what's driving costs", "cost investigation", "cost spike" | Step-by-step cost investigation | query-cost-attribution.md, workflow-total-cost.md, entity-cost-drilldown.md |
| "which app", "which host", "which monitor", "drill down", "break down by application/host/cluster" | Entity-based drill-down with sample-first step | entity-cost-drilldown.md |
| "what's driving RUM/Full-Stack/Synthetic/K8s cost" | Entity drill-down for specific capability | entity-cost-drilldown.md |
| "optimize metrics ingest", "reduce data points", "high cardinality metrics", "which metrics cost most", "metrics cost optimization" | Run analysis (Steps 1–3), present data and explain optimization levers, then wait for user to choose what to optimize — NEVER recommend specific metrics to drop/reduce | metrics-ingest-optimization.md |
| "drop metric", "remove metric from ingestion", "stop ingesting metric" | Drop metric strategy via OpenPipeline or OTel Collector | metrics-ingest-optimization.md -> Strategy 1 — Drop Metric |
| "reduce cardinality", "remove dimension", "drop dimension from metric" | Reduce cardinality strategy via OpenPipeline or OTel Collector | metrics-ingest-optimization.md -> Strategy 2 — Reduce Cardinality |
| "change ingest interval", "reduce collection frequency", "scrape interval" | Change ingest interval at source | metrics-ingest-optimization.md -> Strategy 3 — Change Ingest Interval |
| "AI costs", "cost of AI agents", "what does AI cost", "AI spending", "AI agent costs", "direct and indirect AI cost", "how much is AI costing", "AI Units cost" | Direct AI costs (AI Units / AI Function Standard Call BUEs) + indirect AI costs (Query BUEs with `ai_generated == true`) | billing-event-types.md -> Agentic AppEngine, query-cost-attribution.md -> Step 2a |
| "query cost by source", "who is scanning most", "cost attribution by app" | BUE query cost by source | query-cost-attribution.md -> Step 1 |
| "expensive dashboards", "dashboard cost ranking", "top dashboards by cost" | Dashboard query cost ranking | query-cost-attribution.md -> Step 1b + Step 2 |
| "included volume", "billed vs total", "baseline usage" | Included volume analysis | billing-capabilities.md -> Included Volume |
| "hourly billing", "daily billing after deductions", "time-granular billed usage" | Time-bucketed usage with included volume subtracted | billing-capabilities.md -> Query 3 (Metrics Ingest — Billable Volume) / Query 4 (Traces Ingest — Billable Volume) |

### Usage vs Cost Distinction

- **"Usage"** → Unit conversion only, no cost estimates. Label with unit from [Cost Normalization Weights](references/cost-estimations.md#cost-normalization-weights) (or [billing-event-types.md](references/billing-event-types.md) for preview types).
- **"Cost"** → Unit conversion + compute `cost_weight` in DQL (via the Full Inline Lookup) for internal ordering/aggregation only. **Never display `cost_weight` as a dollar amount.** Omit from rankings for types not in the normalization table.
- **"Cost drivers"** → Ranked list sorted by `cost_weight` (computed in DQL via the Full Inline Lookup). **Output columns: rank, capability name, usage in native units.** Drop `cost_weight` before presenting — it never appears in any column, label, or sentence.
- **"Cost share / percentage"** → Compute share-of-total using normalized weights (usage × Normalization Weight per capability). Present as a percentage table. Use the standard ℹ️ disclaimer from Cost Ranking Rules step 3 — do not add any additional caveat or note.
- **"User-provided rate"** → If the user supplies a contracted rate (e.g. "$0.15/GiB for Log Ingest"), use that rate for that capability and display actual USD for it. All other capabilities show usage-only (no cost). Disclaimer: ⚠️ Calculated using your provided rate of $X/unit. For all capabilities without a provided rate, only usage is shown. For authoritative totals, refer to Account Management > Subscription. **Never infer or assume rates** — only accept them when the user explicitly states them.

Only add cost information when the user explicitly asks for it. Units are incomparable across categories — cost normalization is the only way to rank or sum them.

**Preview types:** Only capabilities explicitly marked as preview in [cost-estimations.md](references/cost-estimations.md#cost-normalization-weights) are preview — never infer preview status from zero usage.

### Cost Ranking Rules

When any intent involves cost ranking or cost drivers (cost drivers, cost trend, workflow
cost, query cost attribution, cost investigation, cost spike):

1. **Compute `cost_weight` in DQL** — run the base usage queries (Queries 1–4
   from [billing-capabilities.md](references/billing-capabilities.md)) up through
   the `| summarize billable_usage` step, then immediately append the
   [Full Inline Lookup for Cost Rankings](references/cost-estimations.md#full-inline-lookup-for-cost-rankings).
   The Full Inline Lookup handles unit conversion **and** cost weighting in one
   step — do **not** also apply the Unit Conversion Lookup from
   `billing-capabilities.md`; it is redundant and a chained `lookup` replaces
   all existing `lookup.*` fields, which breaks the cost-weight computation.
   Finish the query with `| filter isNotNull(cost_weight) | sort cost_weight desc | fields event.type, capability_usage, cost_weight`.
   **NEVER multiply normalization weights mentally** — values span orders of
   magnitude where silent arithmetic errors are undetectable.
2. **Present rankings, not dollar amounts** — the DQL results arrive pre-sorted. Drop the `cost_weight` column and present **only: rank number, capability name, usage in native units** (e.g. GiB, GiB-hours, sessions, data points — whatever unit that capability measures in). Never include a cost, weight, or dollar column. Example output for "top 5 cost drivers":
   ```
   1. Log Management & Analytics - Ingest & Process  62.3 TiB
   2. Full-Stack Monitoring                           2,366,800 GiB-hours
   3. Real User Monitoring                            51.5M sessions
   4. Infrastructure Monitoring                       847,200 host-hours
   5. Metrics - Ingest & Process                      18.2B data points
   ```
   For percentage questions, output a share-of-total table (see Cost share / percentage above). Never show raw USD estimates unless the user has provided their own contracted rate.
3. **Disclaimer BEFORE results** — applies to multi-capability results only (2+ capabilities, rankings, or percentage table). Copy this text **verbatim** — do not paraphrase or rephrase it:
   > ℹ️ Rankings show relative spend — for actual dollar figures, see **Account Management > Subscription > Overview > Cost and usage details**.

   For **single-capability** results (exactly one capability, no cross-capability comparison): **omit the disclaimer entirely** — the result is straightforward billing data with no normalization involved.

   **Exception:** if the response is in **user-provided rate** mode, include the warning required for that mode even for single-capability results. The single-capability omission applies only to the standard multi-capability ranking disclaimer above.
4. **No supplementary rate-card notes** — the prescribed disclaimer above is the only place normalization methodology may be referenced. Never add sentences like "These numbers are based on the public DPS rate card" or "based on public list prices" anywhere else in the response. This does **not** suppress the required warning for **user-provided rate** mode.

## Getting Started

When a user asks a generic or open-ended question about costs, usage, or what the skill can
do, respond with the menu below. **Do not run any DQL queries yet** — wait for the user to
choose a direction.

Here's what you can explore:

1. **Cost breakdown** — See which capabilities are driving spend, ranked by relative cost.
   > *"What are my top cost drivers for the last 7 days?"*

2. **Usage overview** — Full picture of DPS consumption across all capabilities, in native units.
   > *"Give me an overview of our platform usage across all capabilities."*

3. **Spike investigation** — Attribute a cost spike to its source (dashboard, workflow, detector).
   > *"My log query cost spiked last week — which source is causing it?"*

4. **Chargeback / showback** — Break down cost by team, product, or cost center.
   > *"Show me a cost breakdown by cost center for the last 30 days."*

5. **Metrics optimization** — If metrics ingest is a top cost driver, drill into which metric keys are billable and reduce the highest-cost ones.
   > *"Which metrics are driving our ingest cost? Help me optimize."*

Which of these matches what you're trying to do?

## Prerequisites

- Access to a Dynatrace environment
- DQL query permissions on `dt.system.events`
- Load `dt-dql-essentials` before writing queries — covers DQL syntax, type
  handling, and field discovery via `dt.semantic_dictionary.fields`

## Knowledge Base Structure

| # | Reference | Content |
|---|-----------|---------|
| 1 | [billing-event-types.md](references/billing-event-types.md) | Billing event type catalog — fields, metering intervals, per-type tables |
| 2 | [billing-capabilities.md](references/billing-capabilities.md) | BUE-to-capability mapping, unit conversion, cross-category usage queries, included volume deduction |
| 3 | [cost-estimations.md](references/cost-estimations.md) | Cost normalization weights, unit conversion lookup, cost estimation queries, full inline lookup for dashboards |
| 4 | [cost-allocation.md](references/cost-allocation.md) | Cost center/product attribution, chargeback queries |
| 5 | [query-cost-attribution.md](references/query-cost-attribution.md) | Query scan cost attribution — BUE by source, per-detector breakdown (ALERTING pool), QEE drill-down |
| 6 | [workflow-total-cost.md](references/workflow-total-cost.md) | Workflow total cost — four billing signals (query scan, AppEngine, workflow-hours, AI invocations) |
| 7 | [entity-cost-drilldown.md](references/entity-cost-drilldown.md) | Entity-based cost drill-down — RUM/Host/Synthetic/K8s/Security/Automation by entity |
| 8 | [metrics-ingest-optimization.md](references/metrics-ingest-optimization.md) | Per-metric-key cost drill-down — cardinality analysis, timeseries verification, optimization target identification |

## Quick Start

```dql
fetch dt.system.events, from: -7d
| filter event.kind == "BILLING_USAGE_EVENT"
| summarize event_count = count(), by: {event.type}
| sort event_count desc
```

## Best Practices

1. **Always filter by `event.kind` first** — avoids scanning irrelevant events.
2. **Start with 7d time ranges** — platform data is high volume.
3. **Use explicit UTC midnight boundaries** for billing totals — see [billing-capabilities.md § Billing Timeframe Boundaries](references/billing-capabilities.md#billing-timeframe-boundaries).
4. **Never use `~` for approximation** — use `≈` or "approximately" (bare `~` creates Markdown strikethrough).
5. **Empty results?** — Run the discovery query above to verify available event types.
6. **`count()` fans out — confirm one-row-per-thing before counting** — both
   `QUERY_EXECUTION_EVENT` (one row per bucket touched per DQL statement) and
   `WORKFLOW_EVENT` `WORKFLOW_EXECUTION` (≈2 rows per run: start + completion)
   over-count when you `count()` them. For DQL-statement volume use
   `countDistinct(query_id)`; for workflow run count and frequency use
   `countDistinct(dt.automation_engine.workflow_execution.id)` on
   `WORKFLOW_EXECUTION` — never bare `count()`. Never write "ran N times" or
   compute a per-second/per-minute rate from any raw `count()`. See
   [query-cost-attribution.md § Step 3](references/query-cost-attribution.md#step-3--drill-into-qee-for-details)
   and [workflow-total-cost.md § How Often Did the Workflow Run](references/workflow-total-cost.md#how-often-did-the-workflow-run).
7. **Never use entity-model functions** — `entityName()` (and any function that
   takes a `dt.entity.*` field to resolve entity metadata) is deprecated.
   Present raw `dt.entity.*` IDs (e.g. `HOST-1A2B3C`) in results. Grouping or
   counting on the ID (`by: {dt.entity.host}`, `countDistinct(dt.entity.host)`)
   is fine — that uses the ID as a plain value. See
   [entity-cost-drilldown.md § Entity IDs in Results](references/entity-cost-drilldown.md#entity-ids-in-results).

## Limitations

- **No universal usage field** — each event type uses a different billed unit. Cannot sum across categories without cost normalization.
- **Normalization weights ≠ contract rates** — see [Cost Ranking Rules](#cost-ranking-rules). Rankings are relative; for authoritative figures use Account Management.
- **Included volume** — Metrics/Traces Ingest include a host baseline (≈14 days max). See [billing-capabilities.md § Included Volume](references/billing-capabilities.md#included-volume).
- **Cost attribution is optional** — only populated when configured; Retention events often lack entity references.
- **Zero-rated queries** — Certain queries may be zero-rated based on execution context (user, apps, queried data). These produce QEE records but no corresponding BUE. A gap between QEE `scanned_bytes` and BUE `billed_bytes` totals indicates zero-rated usage, not a pipeline issue. See [query-cost-attribution.md § Investigating QEE↔BUE Mismatches](references/query-cost-attribution.md#investigating-qeebue-mismatches).
