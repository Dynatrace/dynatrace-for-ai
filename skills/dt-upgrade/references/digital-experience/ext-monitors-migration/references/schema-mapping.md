# Schema Mapping: Legacy External Synthetic API → New Event Ingest API

This is the primary lookup reference for migrating external synthetic monitor integrations. Read this before touching any migration code.

---

## 1. Conceptual Shifts

These are structural changes that affect migration strategy — not just field renames.

### Fan-out: one payload → many events

The legacy API receives a single `SyntheticPayload` object per POST. The new API receives a **JSON array** of events.

For each test result, expand as follows:

- For each entry in `testResults[]`:
  - For each `locationResult` in `locationResults[]`:
    - Emit **one** `external_test_run` event
    - For each `stepResult` in `stepResults[]` (if present): emit **one** `external_test_step` event

All events from a single payload are collected into one array and sent in one POST.

### Run ID: generated, not inherited

The legacy payload has no run ID concept. For each (test, location) pair within an execution cycle, **generate a fresh UUID v4**. Use this same UUID as `test.run.id` in both the `external_test_run` event and all corresponding `external_test_step` events for that pair. Do not reuse run IDs across cycles.

### Timestamp format conversion

| Legacy | New |
|---|---|
| `messageTimestamp` — epoch milliseconds on the payload root | Not used directly |
| `locationResult.startTimestamp` — epoch milliseconds | `timestamp` — ISO 8601 UTC string (e.g. `"2024-11-14T12:13:19Z"`) |
| `stepResult.startTimestamp` — epoch milliseconds | `timestamp` — ISO 8601 UTC string |

Conversion: divide epoch ms by 1000, then format as `YYYY-MM-DDThh:mm:ssZ`. Use `locationResult.startTimestamp` as the source for the run event's timestamp.

### Body is always a JSON array

Even when sending a single event, wrap it in an array: `[{ ... }]`. The new endpoint rejects bare objects.

### Auth scope change

The token format (`Authorization: Api-Token {token}`) is identical, but the **required scope changes**. Existing tokens with `ExternalSyntheticIntegration` scope will not work against the new endpoint. A new token with `openpipeline.events.custom` scope is required.

### Endpoint domain change

The new endpoint is on the **apps domain**, not the classic environment domain.

- Classic domain (legacy): `abc12345.live.dynatrace.com`
- Apps domain (new): `abc12345.apps.dynatrace.com`

The subdomain prefix (e.g. `abc12345`) is the same, only the suffix changes. **Verify the correct apps domain with the customer** — do not assume the suffix; environment configurations vary.

### Multi-monitor payloads

If the legacy `tests[]` array contains multiple entries, each produces its own independent set of run and step events. There is no per-monitor batching in the new API — all events for all monitors go into the same array in a single POST.

---

## 2. Field Mapping Table

### Top-level payload fields

| Legacy field | New field | Notes |
|---|---|---|
| `syntheticEngineName` | `runner.name` | Optional. Direct copy. |
| `syntheticEngineIconUrl` | — | No equivalent. Drop it. |
| `messageTimestamp` | — | Not used directly. Use `locationResult.startTimestamp` per event. |
| `locations[].id` | `test.run.location` | Copy the location ID string. |
| `locations[].name` | — | No equivalent. Drop it. |
| `locations[].ip` | — | No equivalent. Drop it. |

### Test definition fields (`tests[]`)

| Legacy field | New field | Notes |
|---|---|---|
| `tests[].id` | `test.id` | Must match `testResults[].id` for the same monitor. |
| `tests[].title` | `test.name` | Direct copy. |
| `tests[].scheduleIntervalInSeconds` | `test.frequency_sec` | Optional. Direct copy (integer seconds). |
| `tests[].enabled` | — | No equivalent. |
| `tests[].deleted` | — | No equivalent. If `deleted: true`, emit one final `external_test_run` with `test.run.status: "decommissioned"` to signal retirement. Do not emit step events for decommissioned tests. |
| `tests[].locations[].id` | — | Used to correlate which locations a test runs on; drives the fan-out but is not a separate field in the output. |
| `tests[].steps[].id` | `test.step.index` | Integer step ordering. |
| `tests[].steps[].title` | `test.step.name` | Slugification recommended (e.g. `"Open homepage"` → `"open-homepage"`) but not required. |

### Test result fields (`testResults[]`)

| Legacy field | New field | Notes |
|---|---|---|
| `testResults[].id` | `test.id` | Must match `tests[].id` for the same monitor. |
| `testResults[].totalStepCount` | — | No equivalent. Drop it. |
| `testResults[].locationResults[].id` | `test.run.location` | Copy the location ID string. |
| `testResults[].locationResults[].startTimestamp` | `timestamp` | Convert epoch ms → ISO 8601 UTC. This is the run event's timestamp. |
| `testResults[].locationResults[].success` | `test.run.status` + `test.run.availability` | `true` → `"passed"` + `1`; `false` → `"failed"` + `0` |
| `testResults[].locationResults[].responseTimeMillis` | `test.run.duration_ms` | Direct copy (integer milliseconds). |
| `testResults[].locationResults[].successRate` | — | No equivalent. Drop it. |

### Step result fields (`stepResults[]`)

| Legacy field | New field | Notes |
|---|---|---|
| `stepResults[].id` | `test.step.index` | Integer step ordering. |
| `stepResults[].startTimestamp` | `timestamp` | Convert epoch ms → ISO 8601 UTC. |
| `stepResults[].responseTimeMillis` | `test.step.duration_ms` | Direct copy (integer milliseconds). |
| `stepResults[].error` | `test.step.status`, `test.step.error_code`, `test.step.error_message` | When `error` is present: `status = "failed"`, `error.code` (integer) → `test.step.error_code` (string, e.g. `"500"`), `error.message` → `test.step.error_message`. When no `error`: `status = "passed"`. |

### Fields with no legacy equivalent (always set)

| New field | Value |
|---|---|
| `event.kind` | Always `"EXTERNAL_TEST_EVENT"` |
| `event.type` | `"external_test_run"` or `"external_test_step"` depending on event type |
| `test.run.id` | Generate a UUID v4 per (test, location) pair per execution cycle |
| `test.type` | Infer from context or ask the customer: `"browser"`, `"api"`, `"http"`, or `"mobile"` |

---

## 3. Auth and Endpoint Reference

| | Legacy | New |
|---|---|---|
| Endpoint | `{tenantUrl}/api/v1/synthetic/ext/tests` | `{envUrl}/platform/ingest/custom/events/external.tests` |
| Token scope | `ExternalSyntheticIntegration` | `openpipeline.events.custom` |
| Auth header | `Authorization: Api-Token {token}` | Same format |
| Body format | Single JSON object | JSON array |
| Domain | Classic environment domain | Apps domain (verify with customer) |

---

## 4. Step Events Rule

Emit `external_test_step` events **only when** the legacy integration was populating `stepResults`. Specifically:

- If `locationResult.stepResults` is present and non-empty → emit one `external_test_step` per step.
- If `locationResult.stepResults` is absent or `[]` → omit step events entirely.

Do not add step instrumentation that was not present in the legacy integration. The migration should preserve the level of detail the customer originally had, not add new telemetry signals.

---

## 5. Complete Example

### Legacy payload (before)

One `SyntheticPayload` with one test, one location, two steps — step 2 fails.

```json
{
  "syntheticEngineName": "MyEngine",
  "syntheticEngineIconUrl": "https://example.com/icon.png",
  "messageTimestamp": 1700000000000,
  "locations": [
    { "id": "us-east-1", "name": "US East (N. Virginia)", "ip": "203.0.113.10" }
  ],
  "tests": [
    {
      "id": "monitor-1",
      "title": "My Monitor",
      "scheduleIntervalInSeconds": 60,
      "enabled": true,
      "deleted": false,
      "locations": [{ "id": "us-east-1" }],
      "steps": [
        { "id": 1, "title": "Open homepage" },
        { "id": 2, "title": "Search for product" }
      ]
    }
  ],
  "testResults": [
    {
      "id": "monitor-1",
      "totalStepCount": 2,
      "locationResults": [
        {
          "id": "us-east-1",
          "startTimestamp": 1699999999000,
          "success": false,
          "responseTimeMillis": 810,
          "successRate": 0.5,
          "stepResults": [
            { "id": 1, "startTimestamp": 1699999999000, "responseTimeMillis": 320 },
            { "id": 2, "startTimestamp": 1699999999320, "responseTimeMillis": 0, "error": { "code": 500, "message": "Connection refused" } }
          ]
        }
      ]
    }
  ]
}
```

### New payload (after)

Three events in one array: 1 run event + 2 step events. A single UUID is shared across the run and both step events.

```json
[
  {
    "event.kind": "EXTERNAL_TEST_EVENT",
    "event.type": "external_test_run",
    "test.id": "monitor-1",
    "test.run.id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "test.name": "My Monitor",
    "test.type": "api",
    "test.run.status": "failed",
    "test.run.availability": 0,
    "test.run.duration_ms": 810,
    "test.run.location": "us-east-1",
    "timestamp": "2024-11-14T22:13:19Z",
    "test.frequency_sec": 60,
    "runner.name": "MyEngine"
  },
  {
    "event.kind": "EXTERNAL_TEST_EVENT",
    "event.type": "external_test_step",
    "test.run.id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "test.id": "monitor-1",
    "test.step.id": "step-001",
    "test.step.name": "open-homepage",
    "test.step.index": 1,
    "test.step.status": "passed",
    "test.step.duration_ms": 320,
    "timestamp": "2024-11-14T22:13:19Z"
  },
  {
    "event.kind": "EXTERNAL_TEST_EVENT",
    "event.type": "external_test_step",
    "test.run.id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "test.id": "monitor-1",
    "test.step.id": "step-002",
    "test.step.name": "search-for-product",
    "test.step.index": 2,
    "test.step.status": "failed",
    "test.step.duration_ms": 0,
    "test.step.error_code": "500",
    "test.step.error_message": "Connection refused",
    "timestamp": "2024-11-14T22:13:19Z"
  }
]
```

**Mapping decisions visible in this example:**

- `success: false` → `test.run.status: "failed"` + `test.run.availability: 0`
- `locationResult.startTimestamp: 1699999999000` → `timestamp: "2024-11-14T22:13:19Z"` (epoch ms ÷ 1000, formatted as ISO 8601 UTC)
- `syntheticEngineIconUrl` and `successRate` are dropped — no equivalents
- `messageTimestamp` at the payload root is not used
- `test.run.id` is a generated UUID shared across the run event and both step events
- `tests[].steps[].title` values are slugified for `test.step.name`
- `stepResult.error.code` (integer `500`) is cast to string `"500"` for `test.step.error_code`
- `test.type` is set to `"api"` — this was inferred from context; verify with the customer
- `syntheticEngineName` is copied to `runner.name` on the run event only (not repeated on step events)
