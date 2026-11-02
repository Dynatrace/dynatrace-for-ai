# Classic Pipeline Configuration Discovery

Before running the translation, first check the current OpenPipeline routing state to confirm whether an upgrade is still needed, then query the classic pipeline schemas to identify which stages have custom configuration.

## Table of Contents

- [Routing state checks](#routing-state-checks)
- [Instructions](#instructions)
- [Built-in baselines per schema](#built-in-baselines-per-schema)
- [Discovery summary](#discovery-summary)

## Routing state checks

Run these two checks to understand the current OpenPipeline routing state before proceeding. They help confirm the upgrade is still needed and catch cases where a partial upgrade is already in place.

### Check traffic through the default route

This metric shows how many records flowed through the default OpenPipeline route over the last 7 days. Traffic on the default route means no custom catch-all pipeline is wired yet — the upgrade is still needed.

```dql
timeseries datapoints=sum(dt.sfm.openpipeline.routing.records, default: 0), by:{configuration, route_name}, filter:{ configuration == "logs" AND route_name == "default"}, from: -7d
```

For Business events use `configuration == "bizevents"`.

Interpret results:
- **Datapoints > 0** — traffic is flowing through the default route; upgrade is relevant.
- **Datapoints = 0** — no traffic through the default route in the last 7 days; either the scope is not active on this tenant, or a catch-all pipeline is already in place. Cross-check with the routing entry check below.

### Check for an existing catch-all routing entry

Fetch the current routing configuration and look for any entry with `"matcher": "true"`:

```dtctl
dtctl get settings --schema builtin:openpipeline.logs.routing -o json
```

For Business events use `--schema builtin:openpipeline.bizevents.routing`.

The response is a JSON array; inspect `[0].value.routingEntries`. If any entry has `"matcher": "true"` (typically the last entry), a catch-all pipeline is already wired. Confirm with the user whether this is their upgraded pipeline before proceeding — if it is, the upgrade for this scope may already be complete.

## Instructions

Run all schema queries below. For each schema that responds successfully, apply the built-in filtering rules to count custom rules.

Run each query and note the result:

```dtctl
dtctl get settings --schema builtin:logmonitoring.log-dpp-rules -o json
dtctl get settings --schema builtin:logmonitoring.log-security-context-rules -o json
dtctl get settings --schema builtin:logmonitoring.schemaless-log-metric -o json
dtctl get settings --schema builtin:logmonitoring.log-events -o json
dtctl get settings --schema builtin:logmonitoring.log-buckets-rules -o json
dtctl get settings --schema builtin:bizevents-processing-pipelines.rule -o json
dtctl get settings --schema builtin:bizevents-security-context-rules -o json
dtctl get settings --schema builtin:bizevents-processing-metrics.rule -o json
dtctl get settings --schema builtin:bizevents-processing-buckets.rule -o json
```

## Built-in baselines per schema

Each successful response is an array of settings objects wrapped in an envelope:

```json
{
  "objectId": "...",
  "schemaId": "builtin:logmonitoring.log-dpp-rules",
  "schemaVersion": "1.0.28",
  "scope": "environment",
  "summary": "...",
  "value": { ... },
  "modificationInfo": {}
}
```

The rule data is always inside `value`. Use `value.ruleName` (or equivalent identifier field) to distinguish built-in from custom items.

### `builtin:logmonitoring.log-dpp-rules` — Logs processing

Built-in baseline: **26 items**, all with `value.ruleName` starting with `[Built-in]`. Example:

```json
{
  "objectId": "vu9U3hXa3q0AAAAB...",
  "schemaId": "builtin:logmonitoring.log-dpp-rules",
  "schemaVersion": "1.0.28",
  "scope": "environment",
  "summary": "\\[Built\\-in\\] one\\_agent:log\\_enrichment:dot\\_notation",
  "value": {
    "enabled": true,
    "ruleName": "[Built-in] one_agent:log_enrichment:dot_notation",
    "query": "isNull(trace_id) and isNull(span_id) and matchesPhrase(content, \"trace.id\") and matchesPhrase(content, \"span.id\")",
    "ProcessorDefinition": {
      "rule": "PARSE(content, \"DATA? 'trace.id' PUNCT SPACE? PUNCT? SPACE? PUNCT? ([0-9a-fA-F]{32}|[0-9a-fA-F]{16}):trace_id\")\n| PARSE(content, \"DATA 'span.id' PUNCT SPACE? PUNCT? SPACE? PUNCT? [0-9a-fA-F]{16}:span_id\")"
    },
    "RuleTesting": { "sampleLog": "..." }
  },
  "modificationInfo": {}
}
```

Custom rule count: items where `value.ruleName` does **not** start with `[Built-in]`.

In addition to the custom rule count, record the `value.ruleName` and `value.enabled` of each built-in rule (`value.ruleName` starts with `[Built-in]`). Both enabled and disabled built-in rules are needed in Step 2a — enabled state determines whether the corresponding technology bundle processor is added as `enabled: true` or `enabled: false`. See [technology-bundles.md](technology-bundles.md).

### `builtin:logmonitoring.log-security-context-rules` — Logs security context

Built-in baseline: **0 items**. All returned items are custom.

### `builtin:logmonitoring.schemaless-log-metric` — Logs metrics extraction

Built-in baseline: **0 items**. All returned items are custom.

### `builtin:logmonitoring.log-events` — Logs events extraction

Built-in baseline: **0 items**. All returned items are custom.

### `builtin:logmonitoring.log-buckets-rules` — Logs bucket assignment

Built-in baseline: **2 items** identified by `value.ruleName`:

```json
{
  "objectId": "...",
  "schemaId": "builtin:logmonitoring.log-buckets-rules",
  "scope": "environment",
  "value": {
    "enabled": true,
    "ruleName": "default",
    "bucketName": "default_logs",
    "matcher": "*"
  },
  "modificationInfo": {}
}
```

```json
{
  "objectId": "...",
  "schemaId": "builtin:logmonitoring.log-buckets-rules",
  "scope": "environment",
  "value": {
    "enabled": true,
    "ruleName": "Stores queries, configuration, and metadata for the Databases app",
    "bucketName": "default_database_monitoring",
    "matcher": "dt.extension.name == \"com.dynatrace.extension.postgres\" OR \ndt.extension.name == \"com.dynatrace.extension.sql-oracle\" OR \ndt.extension.name == \"com.dynatrace.extension.sql-db2\" OR \ndt.extension.name == \"com.dynatrace.extension.sql-snowflake\" OR \ndt.extension.name == \"com.dynatrace.extension.sql-server\" OR \ndt.extension.name == \"com.dynatrace.extension.sql-mysql\" OR \ndt.extension.name == \"com.dynatrace.extension.sql-sap-hana\" OR \ndt.extension.name == \"com.dynatrace.extension.mariadb\""
  },
  "modificationInfo": {}
}
```

Custom rule count: total items minus 2.

### `builtin:bizevents-processing-pipelines.rule` — Business events processing

Built-in baseline: **0 items**. All returned items are custom.

### `builtin:bizevents-security-context-rules` — Business events security context

Built-in baseline: **0 items**. All returned items are custom.

### `builtin:bizevents-processing-metrics.rule` — Business events metric extraction

Built-in baseline: **0 items**. All returned items are custom.

### `builtin:bizevents-processing-buckets.rule` — Business events bucket assignment

Built-in baseline: **1 item** — the default Business events bucket:

```json
{
  "objectId": "...",
  "schemaId": "builtin:bizevents-processing-buckets.rule",
  "scope": "environment",
  "value": {
    "enabled": true,
    "ruleName": "default",
    "bucketName": "default_bizevents",
    "matcher": "*"
  },
  "modificationInfo": {}
}
```

Custom rule count: total items minus 1.

## Discovery summary

Report findings as a table. For each schema record: whether it was accessible, the total number of rules returned, and how many of those are custom (built-ins excluded).

| Stage              | Logs schema | Total | Custom | Business events schema | Total | Custom |
|--------------------|---|---|---|---|---|---|
| Processing         | `logmonitoring.log-dpp-rules` | count or n/a | count or n/a | `bizevents-processing-pipelines.rule` | count or n/a | count or n/a |
| Security context   | `logmonitoring.log-security-context-rules` | count or n/a | count or n/a | `bizevents-security-context-rules` | count or n/a | count or n/a |
| Metrics extraction | `logmonitoring.schemaless-log-metric` | count or n/a | count or n/a | `bizevents-processing-metrics.rule` | count or n/a | count or n/a |
| Events extraction  | `logmonitoring.log-events` | count or n/a | count or n/a | — | — | — |
| Bucket assignment  | `logmonitoring.log-buckets-rules` | count or n/a | count or n/a | `bizevents-processing-buckets.rule` | count or n/a | count or n/a |

Determine scope for upgrade based on accessible schemas only:
- At least one accessible Logs schema has custom rules > 0 → **Logs scope needs upgrading**
- At least one accessible Business events schema has custom rules > 0 → **Business events scope needs upgrading**
- No schemas accessible at all → tenant does not have classic pipeline feature enabled; no upgrade needed
- All accessible schemas show 0 custom rules → confirm read rights first, then see below

For any scope that needs upgrading, also note which built-in Logs processing rules were enabled — these determine which technology bundle processors to add in Step 2a. See [technology-bundles.md](technology-bundles.md) for the mapping.

**If all accessible schemas return 0 custom rules:** ask the user to confirm they have `settings:objects:read` permission on all schemas listed above. Missing read permissions can cause custom rules to be silently omitted from the response, making a non-empty pipeline appear empty.

If read rights are confirmed and all schemas are genuinely empty, cross-check with the traffic metric from the routing state check above:

- **No custom rules AND no traffic in the last 7 days (datapoints = 0)** — ask the user whether their goal is to switch fully to OpenPipeline immediately or only to produce an artifact to be ready for a phase 3 switch:
  - **Switch immediately** — ask for the pipeline name, then build the artifact for the scope:
    - **Logs** — add technology bundle processors for any built-in rules that were enabled in the classic pipeline (see [technology-bundles.md](technology-bundles.md)); leave all other stages empty. Proceed to final validation (Step 7) and then going live (Step 8) of [classic-pipeline.md](classic-pipeline.md) to put the pipeline into place and wire it into Dynamic routing.
    - **Business events** — the pipeline is completely empty (no processors in any stage). Proceed to final validation (Step 7) and then going live (Step 8) of [classic-pipeline.md](classic-pipeline.md) to put the pipeline into place and wire it into Dynamic routing.
  - **Produce artifact for phase 3 only** — no upgrade is necessary. There is no custom configuration to translate and no traffic flowing through the classic pipeline. Inform the user that when phase 3 arrives, the switch can be made without any prior artifact preparation.

- **No custom rules AND traffic present (datapoints > 0)** — no translation is needed but the pipeline is active. Ask for the pipeline name and build the artifact for the scope:
  - **Logs** — add technology bundle processors for any built-in rules that were enabled in the classic pipeline (see [technology-bundles.md](technology-bundles.md)); leave all other stages empty.
  - **Business events** — the pipeline is completely empty.
  
  Proceed to final validation (Step 7) and then going live (Step 8) of [classic-pipeline.md](classic-pipeline.md) to put the pipeline into place and wire it into Dynamic routing.
