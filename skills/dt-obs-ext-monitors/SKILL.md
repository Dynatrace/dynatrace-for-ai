---
name: dt-obs-ext-monitors
description: >-
  3rd-party test and monitor result ingestion into Dynatrace Grail via the platform events
  ingest API (platform/ingest/custom/events/). Use when sending external synthetic test outcomes,
  CI monitor data, or third-party check results to Dynatrace. Covers token scope, full event
  schema for external_test_run and external_test_step (including dt.security_context, ci.*,
  trace correlation, and pipeline-added fields), curl and Java DTO examples, and DQL verification.
  Trigger: "ingest test results", "send monitor results", "third party monitor",
  "external test ingestion", "send synthetic results to Grail", "push external test data
  to Dynatrace", "external monitor results", "external test run event schema".
  Do NOT use for Dynatrace-native Synthetic Monitoring browser/HTTP checks, or
  Real User Monitoring (use dt-obs-frontends for RUM).
license: Apache-2.0
---

# External Monitor Ingestion

Send 3rd-party test and monitor results to Dynatrace Grail using the events ingest API.
This is the canonical replacement for the deprecated `POST /api/v1/synthetic/ext/tests` endpoint.

## Overview

Events posted to `/platform/ingest/custom/events/{endpoint}` land in Grail and are processed
by OpenPipeline, which:

- Extracts metrics (`external.test.availability`, `external.test.duration`) for alerting and SLOs
- Registers each unique `test.id` as an `EXT_TEST` Smartscape node — enabling Davis Problems to
  attach to a named entity ("External test X went down") rather than floating without topology context
- Adds `result.status.category` to step events (`SUCCESS` / `SKIPPED` / `FAIL`) for dashboard filtering

Two event types form a test result:

| Type | Purpose |
|------|---------|
| `external_test_run` | Overall pass/fail result for one test execution |
| `external_test_step` | One step within that run (optional; enables step-level metrics) |

## Authentication

Two token types are accepted:

| Token type | Scope |
|------------|-------|
| Classic Api-Token | `openpipeline.events.custom` |
| Platform Token / OAuth | `openpipeline:events.custom:ingest` |

Common wrong guess that does NOT work: `events.ingest`.

## Quick Start

> **Prerequisite:** The ingest endpoint must be created in OpenPipeline before sending events.
> The `external.tests` endpoint is provisioned automatically by the
> default Dynatrace 3rd-party monitors Monaco bundle.
> See `references/event-ingestion.md` for setup details and custom endpoint creation.

Send one minimal test result (replace `external.tests` with your configured endpoint name):

```text
curl -X POST "https://{env-id}.live.dynatrace.com/platform/ingest/custom/events/external.tests" \
  -H "Authorization: Api-Token {token}" \
  -H "Content-Type: application/json" \
  -d '[{
    "event.kind": "EXTERNAL_TEST_EVENT",
    "event.type": "external_test_run",
    "test.id": "my-api-health-check",
    "test.run.id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "test.name": "My API Health Check",
    "test.type": "api",
    "test.run.status": "passed",
    "test.run.availability": 1,
    "test.run.duration_ms": 245,
    "test.run.location": "us-east-1",
    "dt.security_context": "team-checkout",
    "timestamp": "2024-01-15T10:30:00Z"
  }]'
```

**Expected response:** HTTP 200 (empty body).

> Full event schema, step events, extended examples with error fields and CI metadata,
> Java DTO shapes, and DQL queries: `references/event-ingestion.md`

## Verify in Grail

After sending, confirm the event appears:

```dql
fetch events, from:now()-1h
| filter event.type == "external_test_run"
| fields timestamp, test.id, test.name, test.run.status, test.run.duration_ms, test.run.location
| sort timestamp desc
| limit 20
```

## Key Constraints

- Body **must** be a JSON array (`[{...}]`), not an object wrapper (`{"events":[...]}`).
- A single request can mix run events and step events in the same array.
- `timestamp` must be ISO 8601 UTC (e.g. `"2024-01-15T10:30:00Z"`).
- `test.run.availability` must be integer `1` or `0`, not a string.
- All step events in a run must share the same `test.run.id` and `test.id` as the parent run event.
- Step events must include `test.step.id` (unique within the run) in addition to `test.run.id`.
- `event.kind: "EXTERNAL_TEST_EVENT"` must be present — used by Grail for event classification.
  Routing to the correct pipeline is driven by `event.type`, not `event.kind`.
- Do **not** send `dt.smartscape.ext_test` or `result.status.category` — these are written by
  the pipeline after ingestion and will be overwritten if included.
- `dt.security_context` controls data access policies; it’s recommended to set it on every event to enable
  per-team access control and cost attribution in multi-team tenants.

## Multi-Location Tests

Send the same `test.id` from multiple locations — each with a different `test.run.location`
value — to build a multi-location test. OpenPipeline creates one `EXT_TEST` node per `test.id`
and one availability metric timeseries per `(test.id, location)` pair.

This enables two alerting tiers out of the box:

| Alert type | Fires when |
|------------|-----------|
| Local outage | A single location's availability drops (per-location timeseries) |
| Global outage | Average across all locations drops below threshold (e.g. majority failing) |

Threshold maths for a 3-location test: 1 location failing → avg 0.67 (no alert at 0.5 threshold);
2 failing → avg 0.33 (fires); all 3 failing → avg ≈ 0 (fires immediately).

Keep `test.id` stable across all locations — changing it creates a new Smartscape node and
breaks metric history.

## Related Skills

- **dt-dql-essentials** — DQL syntax for querying ingested events and building analysis queries
- **dt-obs-frontends** — Link test runs to frontend entities via `dt.smartscape.frontend` to
  draw EXT_TEST → FRONTEND dependency edges in Smartscape
