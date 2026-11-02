# Calculated Service Metric Usage and Migration

**Replacement**: OpenPipeline span metric extraction, for the part of a definition that can be
expressed on spans

**Phase 2 required**: yes

## What changes

Calculated service metrics stop receiving new data in Phase 3. One read-only run answers both
questions the customer has: **which configurations read them**, and **which of them can be
migrated** to an OpenPipeline metric extracted from spans.

- **Usage** reports exact references in the seven configuration sources: dashboards, notebooks,
  Service-Level Objectives, classic SLOs, Site Reliability Guardians, metric events, and Davis
  custom alerts.
- **The migration verdict** covers every calculated service metric the environment defines,
  referenced or not.

Both key spellings are matched:

| Key form | Counts as a reference when |
|---|---|
| `service.<key>` | the key is in the **Grail inventory** — `service.name` and friends are ordinary attributes |
| `calc:service.<key>` | the `calc:` prefix matches **and** the key is in the **classic definitions** |

A configuration reading a key nothing defines is reported as a stale reference: no metric to
migrate, and no data returned today.

## Instructions

### Prerequisites

- Python 3.12+; no package installation is required.
- Run before Phase 3 while calculated service metrics still produce data.

Set both tokens as environment variables. Each one reads a different half, and a complete run
needs both:

| Token | Reads |
|---|---|
| `DT_PLATFORM_TOKEN` — platform token (`dt0s16.*`) with `storage:metrics:read`, `settings:objects:read`, `document:documents:read`, `document:documents:admin`, `slo:slos:read` | the seven configuration sources, and the datapoint check |
| `DT_CLASSIC_TOKEN` — classic token (`dt0c01.*`) with `ReadConfig` | the metric inventory and the classic definitions the verdict is computed from |

Without `DT_CLASSIC_TOKEN` the scan reports usage only: no verdict, no processors, and the usage
verdict cannot be `clean`.

### Step 1 - Scan the tenant

From this directory, run the recommended HTTP scan:

```bash
cd scanner
PYTHONPATH=src python3 -m calculated_service_metric_scanner scan \
  --transport http \
  --tenant https://<environment>.apps.dynatrace.com
```

Use `--output-dir <path>` for another report location.

Alternatively, reuse an authenticated `dtctl` context:

```bash
PYTHONPATH=src python3 -m calculated_service_metric_scanner scan --context <name>
```

`dtctl` avoids handling the platform token, but its Grail inventory is timeframe-bound and always
partial, and without tenant-wide document access dashboards and notebooks are partial too. Use
HTTP when a complete clean verdict is required. `DT_CLASSIC_TOKEN` is read in both transports.

| Flag | Effect |
|---|---|
| `--skip-migration` | usage only; no definitions are read and no verdict is produced |
| `--traffic-window <window>` | how far back a datapoint counts as recent, default and maximum `10d` (the series index holds no more) |

The scanner reads all seven configuration sources, matches exact keys, reads every classic
definition, checks which metrics still hold datapoints, and writes one candidate processor per
metric it can migrate.

### Step 2 - Report the result

`report.html` is self-contained and grouped by what can be done with a metric. Every defined
metric carries one verdict:

| Verdict | Report label | What it means |
|---|---|---|
| `migratable` | Can be migrated | Every part of the classic definition has a span equivalent; the processor is attached |
| `migratable_inexact` | Can be migrated, not exactly | The processor matches a **superset** of the classic metric; the entry says which condition was dropped |
| `not_migratable` | Cannot be migrated | At least one part of the definition has no Phase 3 equivalent, named in the entry |
| `unknown` | Not assessed | The classic definition could not be read, or it uses an element the mapping catalog is missing. Rare, and a sign the scan was incomplete |

The verdict comes from the definition and the bundled `migration/mapping-catalog.json`, so it does
not depend on the environment. `traffic` (`recent`, `none`, `unknown`) is a separate column; a
dormant metric is assessed like any other and gets its processor.

Usage has its own verdict:

| Verdict | Report label | Meaning | Customer report action |
|---|---|---|---|
| `affected` | Needs review | At least one exact reference was found | Report every configuration to review and the matching query or expression |
| `clean` | No configuration references one | The inventory and all seven sources above were read completely; no reference was found | Keep the topic in the report when metrics are still defined — they stop receiving data regardless |
| `incomplete` | Coverage incomplete | No reference was found, but inventory or source coverage is incomplete | Report the incomplete assessment; do not claim no usage |

Findings alongside incomplete coverage stay `affected` and are not exhaustive. Report the
incomplete sources and re-run them.

### Step 3 - Customer actions

The report states the differences a migrated metric brings, so walk the customer through the page
rather than repeating it. What to add:

- Every reported configuration needs a decision on whether the metric is still required, starting
  with the metrics that still receive data.
- Classic SLOs and metric events have to be reworked by hand; they cannot read a replacement
  metric.
- Re-run the scan after resolving any partial or failed source.

### Step 4 - Hand a processor to the customer on request

Every migratable metric already has a processor file and shows it in the report. The customer
asks in words; match on intent, not on wording, and run the command for them:

| What the customer wants | Run |
|---|---|
| "give me the processor for `service.<key>`" (or `calc:service.<key>`) | `processors --metric service.<key> --show` |
| "all the processors that are not an exact migration" | `processors --group migratable-inexact` |
| "the processors for the metrics with no data" | `processors --group all` - the output marks each one `(no recent data)` |
| "every processor" | `processors --group all` |

```bash
cd scanner
PYTHONPATH=src python3 -m calculated_service_metric_scanner processors \
  --output-dir <the folder holding report.html> --metric service.<key> --show
```

`--metric` is repeatable and takes the key with or without the `calc:` prefix. The processors come
out of `summary.json`, so no tenant is contacted. For a metric that cannot be migrated the command
fails with the reason; point at the metric's entry in the report for what blocks it.

## The processors

Each migratable metric gets one `metricExtraction` processor, in `processors/<new key>.json`.
Nothing else is generated, and the report tells the customer that placing them is their decision.

Known limits:

- Custom `{placeholder}` dimensions, a dimension composed of several properties, and
  `ignoreMutedRequests` are not implemented. A composite dimension needs a preceding DQL processor
  to materialize the combined field.
- A case-sensitive `CONTAINS` / `BEGINS_WITH` / `ENDS_WITH` is refused: the matcher grammar has no
  `contains()`, `startsWith()` or `endsWith()`, and `matchesValue` rejects `caseSensitive: true`.
- `SERVICE_TYPE` has no span field. It is dropped from the matcher and the metric is reported as
  `migratable_inexact`; the other conditions still bound the match.
- Classic's top-N cap has no ingestion-time equivalent, so the extracted metric keeps every
  dimension value and ranking moves into the query.
- **A valid processor can still produce different numbers.** Counts come out lower than the
  classic metric, because spans are sampled and a classic metric was computed on every request;
  averages match closely. Compare the new metric against the classic one over the same timeframe
  before switching a consumer over.

## Outputs

- `summary.json` - usage verdict, coverage, counts, and one record per metric (verdict, `traffic`,
  blockers, notes, the processor, its definition `link`), plus the migration totals and root
  causes;
- `report.html` - self-contained customer report with tenant links;
- `processors/<new key>.json` - one processor per migratable metric, dormant ones included;
  rewritten from scratch on every scan; and
- `scan-data.json` - the identities to review with names, artifacts, field paths, links, matching
  queries, and complete configuration bodies.

Rebuild HTML and repair tenant links from an existing `summary.json`, without contacting the
tenant:

```bash
PYTHONPATH=src python3 -m calculated_service_metric_scanner render \
  --output-dir ./calculated-service-metric-report \
  --ui-url https://<environment>.apps.dynatrace.com
```

`render` keeps an existing `scan-data.json` and `processors/`; it cannot recreate configuration
bodies from `summary.json` alone.

## Validation

A `clean` usage verdict is valid only when the inventory and all seven configuration sources are
complete. An empty successful `metricsOnGrail` response is complete; inventory errors and the
timeframe-bound `dtctl` fallback are incomplete.

## References

- [Shared configuration scan](../shared-scripts/README.md)
