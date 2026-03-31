# Cost Estimations

Estimate DPS (Dynatrace Platform Subscription) costs by applying public rate
card prices to billing usage data. This enables cross-capability cost comparison,
chargeback normalization, and budget forecasting.

> **ESTIMATED COSTS ONLY — NOT ACTUAL BILLING DATA.** Every customer has a
> custom rate card negotiated as part of their DPS contract. The public rate card
> prices used throughout this document are **list prices** and **will differ from
> actual costs**. Use these queries exclusively for directional analysis, relative
> comparisons, and spike detection — **never for invoice reconciliation**.
>
> For actual billing data, use **Account Management > Subscription > Overview >
> Cost and usage details**.

## Contents

- [Important Disclaimers](#important-disclaimers)
- [Public Rate Card](#public-rate-card)
- [BUE-to-Rate-Card Mapping](#bue-to-rate-card-mapping)
- [Cost Estimation Pattern](#cost-estimation-pattern)
- [Usage Normalization](#usage-normalization)
- [Inline Lookup Pattern](#inline-lookup-pattern)
  - [Inline Lookup Snippet](#inline-lookup-snippet)
  - [Complete Rate Card Inline Lookup](#complete-rate-card-inline-lookup)
- [Ready-to-Use Queries](#ready-to-use-queries)
  - [Estimated Cost by Capability](#estimated-cost-by-capability)
  - [Estimated Cost by Cost Center](#estimated-cost-by-cost-center)
  - [Estimated Query Cost by Source](#estimated-query-cost-by-source)
  - [Daily Cost Trend](#daily-cost-trend)

## Important Disclaimers

> **1. Estimated costs only.** Every customer has a custom rate card negotiated
> as part of their DPS contract. The public rate card prices used here are list
> prices and will differ from actual costs. Use these queries for directional
> analysis, relative comparisons, and spike detection — not for invoice
> reconciliation.

> **2. Rate card may change.** The prices in this document reflect the
> [Dynatrace public rate card](https://www.dynatrace.com/pricing/rate-card/)
> as of March 2026. Always verify current prices before using cost estimations.
> Every cost estimation produced from this skill MUST include a disclaimer
> stating: "Estimated using public list prices as of March 2026. Actual costs
> depend on your negotiated DPS contract."

> **3. Not all BUE types have a rate card price.** Some billing usage event
> types (Files, Digital Experience Monitoring, Data Egress) either map to another
> rate card item or are in preview with no published price. See
> [BUE-to-Rate-Card Mapping](#bue-to-rate-card-mapping) below.

> **4. Included volume not deducted.** The queries in this file use raw usage
> totals. Metrics Ingest and Traces Ingest include a baseline from host
> monitoring that should be subtracted for accurate billed usage. See
> [billing-included-volume.md](billing-included-volume.md) for deduction queries.

> **CRITICAL: Cross-Capability Cost Comparison.** NEVER compare raw usage across
> billing categories — units are incomparable (bytes, GiB-hours, sessions,
> pod-hours). Always use the USD-normalized rate-card queries in this file.
> Single-category questions (e.g., "how much log ingest?") can use raw usage
> because units are consistent within a category.

## Public Rate Card

Prices from the [Dynatrace public rate card](https://www.dynatrace.com/pricing/rate-card/)
(as of March 2026). The `price` and `priceUnit` columns are used in the DQL
lookup pattern — estimated cost = `(total_usage / priceUnit) * price`.

| Event Type | Category | Unit | Price (USD) | Price Unit | Notes |
|------------|----------|------|-------------|------------|-------|
| `Full-Stack Monitoring` | App & Infra Observability | GiB-hours | 1,000.00 | 100,000 | |
| `Infrastructure Monitoring` | App & Infra Observability | host-hours | 4,000.00 | 100,000 | |
| `Foundation & Discovery` | App & Infra Observability | host-hours | 1,000.00 | 100,000 | |
| `Mainframe Monitoring` | App & Infra Observability | MSU-hours | 1,000.00 | 10,000 | |
| `Code Monitoring` | Container Observability | container-hours | 500.00 | 100,000 | |
| `Kubernetes Platform Monitoring` | Container Observability | pod-hours | 200.00 | 100,000 | |
| `Log Management & Analytics - Ingest & Process` | Log Analytics | GiB | 2,000.00 | 10,000 | |
| `Log Management & Analytics - Query` | Log Analytics | GiB scanned | 3,500.00 | 1,000,000 | |
| `Log Management & Analytics - Retain` | Log Analytics | GiB-days | 700.00 | 1,000,000 | |
| `Log Management & Analytics - Retain with Included Queries` | Log Analytics | GiB-days | 20,000.00 | 1,000,000 | |
| `Traces - Ingest & Process` | Traces | GiB | 2,000.00 | 10,000 | |
| `Traces - Query` | Traces | GiB scanned | 3,500.00 | 1,000,000 | |
| `Traces - Retain` | Traces | GiB-days | 700.00 | 1,000,000 | Free first 10 days ¹ |
| `Metrics - Ingest & Process` | Metrics | data points | 150.00 | 100,000,000 | |
| `Metrics - Retain` | Metrics | GiB-days | 700.00 | 1,000,000 | Free first 15 months ¹ |
| `Events - Ingest & Process` | Events | GiB | 2,000.00 | 10,000 | |
| `Events - Query` | Events | GiB scanned | 3,500.00 | 1,000,000 | |
| `Events - Retain` | Events | GiB-days | 700.00 | 1,000,000 | |
| `Real User Monitoring` | DEM | sessions | 225.00 | 100,000 | |
| `Real User Monitoring with Session Replay` | DEM | replay captures | 450.00 | 100,000 | |
| `Real User Monitoring Property` | DEM | properties/session | 10.00 | 100,000 | |
| `Browser Monitor or Clickpath` | DEM | synthetic actions | 450.00 | 100,000 | |
| `HTTP Monitor` | DEM | synthetic requests | 100.00 | 100,000 | |
| `Third-Party Synthetic API Ingestion` | DEM | synthetic results | 100.00 | 100,000 | |
| `Runtime Application Protection` | App Security | GiB-hours | 225.00 | 100,000 | |
| `Runtime Vulnerability Analytics` | App Security | GiB-hours | 225.00 | 100,000 | |
| `Security Posture Management` | App Security | host-hours | 700.00 | 100,000 | |
| `Automation Workflow` | Automation | workflow-hours | 300.00 | 10,000 | |
| `AppEngine Functions - Small` | Automation | invocations | 1,000.00 | 1,000,000 | |

¹ See [capability pricing docs](https://docs.dynatrace.com/docs/license/capabilities) for free-tier details.

> **Reminder:** These are public list prices. Your actual contracted rates will
> differ. See Disclaimer #1 above.

## BUE-to-Rate-Card Mapping

Not every billing usage event (BUE) type has a direct entry on the public rate
card. The following table documents known mapping gaps:

| BUE Event Type | Rate Card Mapping |
|----------------|-------------------|
| `Files - Ingest & Process` | Billed at **Events - Ingest & Process** rate |
| `Files - Query` | Billed at **Events - Query** rate |
| `Files - Retain` | Billed at **Events - Retain** rate |
| `Digital Experience Monitoring - Query` | **Preview** — no public price ¹ |
| `Digital Experience Monitoring - Retain` | **Preview** — no public price ¹ |
| `Data Egress` | **Preview** — no public price ¹ |

¹ Preview types return `null` for `estimated_cost_usd` in cost queries.

## Cost Estimation Pattern

The formula to convert raw usage to estimated USD cost:

```
estimated_cost = (total_usage / priceUnit) * price
```

The challenge is that each billing event type uses a **different billed field**
(see [billing-event-types.md](billing-event-types.md)). To aggregate across types, normalize all usage
into a single value using `coalesce()`:

```dql-snippet
| fieldsAdd usage = coalesce(
    billed_gibibyte_hours,
    billed_host_hours,
    billed_msu_hours,
    billed_container_hours,
    toDouble(billed_bytes) / 1073741824,
    billed_sessions,
    billed_replay_sessions,
    billed_property_sessions,
    billed_pod_hours,
    billed_synthetic_action_count,
    billed_http_request_count,
    billed_test_result_ingestion_count,
    billed_invocations,
    data_points,
    toDouble(ingested_bytes) / 1073741824)
```

Each event type has exactly one non-null billed field, so `coalesce()` picks the
correct value. Byte-valued fields are divided by 1,073,741,824 to convert to GiB
matching the rate card units. The `toDouble()` on byte fields ensures
floating-point division.

> **Retain events and the ÷24 adjustment:** Retain events are emitted hourly,
> each recording the bytes currently stored — representing 1/24th of a GiB-day.
> The `coalesce()` converts bytes to GiB but does NOT divide by 24. Instead,
> the retain `priceUnit` values in the inline lookup are multiplied by 24
> (e.g., 1,000,000 × 24 = 24,000,000) so the cost formula automatically
> accounts for the hourly-to-daily conversion.

## Usage Normalization

How each billed field maps to the rate card unit:

| Billed Field | Conversion | Rate Card Unit |
|-------------|-----------|----------------|
| `billed_gibibyte_hours` | as-is | GiB-hours |
| `billed_host_hours` | as-is | host-hours |
| `billed_msu_hours` | as-is | MSU-hours |
| `billed_container_hours` | as-is | container-hours |
| `billed_bytes` (Ingest/Query) | ÷ 1,073,741,824 | GiB / GiB scanned |
| `billed_bytes` (Retain) | ÷ 25,769,803,776 (1,073,741,824 × 24) | GiB-days — hourly events each record 1/24th of a GiB-day |
| `billed_sessions` | as-is | sessions |
| `billed_replay_sessions` | as-is | replay captures |
| `billed_property_sessions` | as-is | properties/session |
| `billed_pod_hours` | as-is | pod-hours |
| `billed_synthetic_action_count` | as-is | synthetic actions |
| `billed_http_request_count` | as-is | synthetic requests |
| `billed_test_result_ingestion_count` | as-is | synthetic results |
| `billed_invocations` | as-is | invocations |
| `data_points` | as-is | data points |
| `ingested_bytes` | ÷ 1,073,741,824 | GiB |

## Inline Lookup Pattern

To apply rates from the [Public Rate Card](#public-rate-card) in DQL, use
`data json:"""..."""` as an inline lookup table. Build the JSON array from the
rate card table above, using `event_type`, `price`, and `priceUnit` fields.

> For `lookup` command syntax and chaining rules, see `dt-dql-essentials`.

**CRITICAL — Retain `priceUnit` adjustment:** Retain events are emitted hourly,
each recording 1/24th of a GiB-day. Multiply the rate card `priceUnit` by 24
(e.g., 1,000,000 → 24,000,000) in the inline JSON so the cost formula
automatically converts hourly to daily.

### Inline Lookup Snippet

```dql-snippet
| lookup [
    data json:"""
    [
      {"event_type": "<Event Type>", "price": <price>, "priceUnit": <priceUnit>}
    ]
    """
  ], sourceField: event.type, lookupField: event_type, fields: {price, priceUnit}
| fieldsAdd estimated_cost_usd = total_usage / toDouble(priceUnit) * price
```

Include only the event types relevant to the query — use the full rate card for
cross-capability comparisons, or a subset for focused analysis. The agent MUST
derive `price` and `priceUnit` values from the [Public Rate Card](#public-rate-card)
table above.

### Complete Rate Card Inline Lookup

Full rate card as an inline JSON block for cross-capability cost estimation.
Retain `priceUnit` values are already multiplied by 24 for hourly-to-daily
conversion.

```dql-template
| lookup [
    data json:"""
    [
      {"event_type": "Full-Stack Monitoring", "price": 1000, "priceUnit": 100000},
      {"event_type": "Infrastructure Monitoring", "price": 4000, "priceUnit": 100000},
      {"event_type": "Foundation & Discovery", "price": 1000, "priceUnit": 100000},
      {"event_type": "Mainframe Monitoring", "price": 1000, "priceUnit": 10000},
      {"event_type": "Code Monitoring", "price": 500, "priceUnit": 100000},
      {"event_type": "Kubernetes Platform Monitoring", "price": 200, "priceUnit": 100000},
      {"event_type": "Log Management & Analytics - Ingest & Process", "price": 2000, "priceUnit": 10000},
      {"event_type": "Log Management & Analytics - Query", "price": 3500, "priceUnit": 1000000},
      {"event_type": "Log Management & Analytics - Retain", "price": 700, "priceUnit": 24000000},
      {"event_type": "Log Management & Analytics - Retain with Included Queries", "price": 20000, "priceUnit": 24000000},
      {"event_type": "Traces - Ingest & Process", "price": 2000, "priceUnit": 10000},
      {"event_type": "Traces - Query", "price": 3500, "priceUnit": 1000000},
      {"event_type": "Traces - Retain", "price": 700, "priceUnit": 24000000},
      {"event_type": "Metrics - Ingest & Process", "price": 150, "priceUnit": 100000000},
      {"event_type": "Metrics - Retain", "price": 700, "priceUnit": 24000000},
      {"event_type": "Events - Ingest & Process", "price": 2000, "priceUnit": 10000},
      {"event_type": "Events - Query", "price": 3500, "priceUnit": 1000000},
      {"event_type": "Events - Retain", "price": 700, "priceUnit": 24000000},
      {"event_type": "Files - Ingest & Process", "price": 2000, "priceUnit": 10000},
      {"event_type": "Files - Query", "price": 3500, "priceUnit": 1000000},
      {"event_type": "Files - Retain", "price": 700, "priceUnit": 24000000},
      {"event_type": "Real User Monitoring", "price": 225, "priceUnit": 100000},
      {"event_type": "Real User Monitoring with Session Replay", "price": 450, "priceUnit": 100000},
      {"event_type": "Real User Monitoring Property", "price": 10, "priceUnit": 100000},
      {"event_type": "Browser Monitor or Clickpath", "price": 450, "priceUnit": 100000},
      {"event_type": "HTTP Monitor", "price": 100, "priceUnit": 100000},
      {"event_type": "Third-Party Synthetic API Ingestion", "price": 100, "priceUnit": 100000},
      {"event_type": "Runtime Application Protection", "price": 225, "priceUnit": 100000},
      {"event_type": "Runtime Vulnerability Analytics", "price": 225, "priceUnit": 100000},
      {"event_type": "Security Posture Management", "price": 700, "priceUnit": 100000},
      {"event_type": "Automation Workflow", "price": 300, "priceUnit": 10000},
      {"event_type": "AppEngine Functions - Small", "price": 1000, "priceUnit": 1000000}
    ]
    """
  ], sourceField: event.type, lookupField: event_type, fields: {price, priceUnit}
| fieldsAdd estimated_cost_usd = total_usage / toDouble(priceUnit) * price
```

> **Note:** `Files` types are mapped to `Events` rate card prices. Preview types
> (`Digital Experience Monitoring - Query/Retain`, `Data Egress`) are omitted —
> they will return `null` for `estimated_cost_usd`.

## Ready-to-Use Queries

> **IMPORTANT — All queries in this section produce ESTIMATED costs using public
> list prices. Actual costs depend on your negotiated DPS contract rates. Use for
> directional analysis only.**

### Estimated Cost by Capability

Total estimated cost per billing event type over the last 30 days. Build the
inline lookup from the full [Public Rate Card](#public-rate-card) table.

> ⚠️ **Raw totals — included volume not deducted.** Metrics Ingest and Traces
> Ingest results overstate billed usage because host-monitoring baselines are
> not subtracted. For accurate billed costs on those two categories, use the
> deduction queries in [billing-included-volume.md](billing-included-volume.md).

```dql-template
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| dedup event.id
| fieldsAdd usage = coalesce(
    billed_gibibyte_hours,
    billed_host_hours,
    billed_msu_hours,
    billed_container_hours,
    toDouble(billed_bytes) / 1073741824,
    billed_sessions,
    billed_replay_sessions,
    billed_property_sessions,
    billed_pod_hours,
    billed_synthetic_action_count,
    billed_http_request_count,
    billed_test_result_ingestion_count,
    billed_invocations,
    data_points,
    toDouble(ingested_bytes) / 1073741824)
| summarize total_usage = sum(usage), by: {event.type}
| lookup [<INLINE_RATE_CARD_JSON>],
    sourceField: event.type, lookupField: event_type, fields: {price, priceUnit}
| fieldsAdd estimated_cost_usd = total_usage / toDouble(priceUnit) * price
| fields event.type, total_usage, estimated_cost_usd
| sort estimated_cost_usd desc
```

> **Note:** `Automation Workflow` and `Security Posture Management` use
> count-based metering (`countDistinct()`) that `coalesce()` cannot capture —
> their `estimated_cost_usd` will be `null`. Query those separately
> (see [billing-event-types.md](billing-event-types.md)). Preview types without
> a public price (`Digital Experience Monitoring - Query/Retain`, `Data Egress`)
> also return `null`.

### Estimated Cost by Cost Center

Cost center attribution for chargeback. Filter to event types where
`dt.cost.costcenter` is a string, build inline lookup with matching subset:

```dql-template
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type, <SUBSET_OF_EVENT_TYPES>)
| filter isNotNull(dt.cost.costcenter)
| dedup event.id
| fieldsAdd usage = coalesce(
    billed_gibibyte_hours,
    billed_host_hours,
    billed_container_hours,
    toDouble(billed_bytes) / 1073741824,
    toDouble(ingested_bytes) / 1073741824)
| summarize total_usage = sum(usage),
    by: {event.type, dt.cost.costcenter}
| lookup [<INLINE_RATE_CARD_SUBSET_JSON>],
    sourceField: event.type, lookupField: event_type, fields: {price, priceUnit}
| fieldsAdd estimated_cost_usd = total_usage / toDouble(priceUnit) * price
| fields dt.cost.costcenter, event.type, total_usage, estimated_cost_usd
| sort dt.cost.costcenter asc, estimated_cost_usd desc
```

### Estimated Query Cost by Source

Attribute query scan costs to originating source (app, detector, service).
Uses BUE Query events with `client.source` for **billable truth**:

```dql-template
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type,
    "Log Management & Analytics - Query",
    "Events - Query",
    "Traces - Query",
    "Files - Query")
| dedup event.id
| filter isNotNull(client.source)
| fieldsAdd usage_gib = toDouble(billed_bytes) / 1073741824
| summarize total_gib = sum(usage_gib), by: {client.source, event.type}
| lookup [<QUERY_RATE_CARD_JSON>],
    sourceField: event.type, lookupField: event_type, fields: {price, priceUnit}
| fieldsAdd estimated_cost_usd = total_gib / toDouble(priceUnit) * price
| fields client.source, event.type, total_gib, estimated_cost_usd
| sort estimated_cost_usd desc
| limit 30
```

> - `client.source` semantics vary by pool — see [query-analytics.md](query-analytics.md) →
>   `client.source` Semantics
> - BUE Query events lack `client.client_context` — for per-detector drill-down
>   and the full investigation workflow, see [cost-investigation.md](cost-investigation.md)

### Daily Cost Trend

Track estimated daily cost to detect spikes. Restricted to ingest types using
`billed_bytes`:

```dql-template
fetch dt.system.events, from: -30d
| filter event.kind == "BILLING_USAGE_EVENT"
| filter in(event.type, <INGEST_EVENT_TYPES>)
| dedup event.id
| fieldsAdd usage_gib = toDouble(billed_bytes) / 1073741824
| lookup [<INGEST_RATE_CARD_JSON>],
    sourceField: event.type, lookupField: event_type, fields: {price, priceUnit}
| fieldsAdd daily_cost = usage_gib / toDouble(priceUnit) * price
| makeTimeseries total_daily_cost = sum(daily_cost),
    by: {event.type}, interval: 1d
```