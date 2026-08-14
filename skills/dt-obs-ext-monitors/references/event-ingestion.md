# Event Ingestion Reference

Complete reference for posting external test and monitor results to Dynatrace via the
platform ingest API.

## Endpoint

```
POST https://{env-id}.live.dynatrace.com/platform/ingest/custom/events/{endpoint}
```

`{endpoint}` is the `pathSegment` of an ingest source configured in OpenPipeline
(`builtin:openpipeline.events.ingest-sources`). The endpoint must exist before events can be
sent to it.

**The `external.tests` endpoint is created automatically** when you deploy the
default Dynatrace 3rd-party monitors Monaco bundle.
That bundle provisions the ingest source, processing pipelines, and the routing rules
as a single `monaco deploy` operation. If you are setting up the full external monitors
observability stack from scratch, deploying that bundle is the recommended starting point.

**Headers:**

| Header | Value |
|--------|-------|
| `Authorization` | `Api-Token {token}` or `Bearer {oauth-token}` |
| `Content-Type` | `application/json` |

**Auth options — either works:**

| Token type | Required scope |
|------------|----------------|
| Classic Api-Token | `openpipeline.events.custom` (dot-separated) |
| Platform Token / OAuth | `openpipeline:events.custom:ingest` (colon-separated) |

**Max payload size:** 10 MiB per request. Larger payloads return HTTP 413.

**Body:** JSON array of event objects. A single request can contain a run event and its step
events together:

```json
[
  { "event.type": "external_test_run", "placeholder": "..." },
  { "event.type": "external_test_step", "placeholder": "..." }
]
```

---

## Event Schema

### external_test_run

Represents one complete execution of a test or monitor.

**Required fields:**

| Field | Type | Description |
|-------|------|-------------|
| `event.kind` | string | Always `"EXTERNAL_TEST_EVENT"` |
| `event.type` | string | Always `"external_test_run"` |
| `test.id` | string | Stable test identifier. Used as the `EXT_TEST` Smartscape node key — must be consistent across runs to accumulate history. |
| `test.run.id` | string | Unique run ID (UUID recommended). Step events use this to reference their parent run. |
| `test.name` | string | Human-readable test name shown in the UI. |
| `test.type` | string | `"browser"` \| `"api"` \| `"mobile"` \| `"http"` |
| `test.run.status` | string | `"passed"` \| `"failed"` \| `"errored"` \| `"timeout"` \| `"maintenance"` \| `"decommissioned"` |
| `test.run.availability` | integer | `1` = available, `0` = unavailable. Drives `external.test.availability` metric and SLOs. Runs with status `"maintenance"` or `"decommissioned"` are excluded from availability metrics. |
| `test.run.duration_ms` | integer | Total run duration in milliseconds. |
| `test.run.location` | string | Location identifier (e.g. `"us-east-1"`, `"eu-west-1"`, `"local"`). |
| `timestamp` | string | ISO 8601 UTC (e.g. `"2024-01-15T10:30:00Z"`). |

**Optional fields:**

| Field | Type | Description |
|-------|------|-------------|
| `test.run.error_code` | string | Error code when status is `"failed"` or `"errored"`. See [Error Codes](#error-codes). |
| `test.run.error_message` | string | Human-readable error description. |
| `test.run.location.lat` | float | Latitude for geo-mapping. |
| `test.run.location.lon` | float | Longitude for geo-mapping. |
| `test.run.location_id` | string | Machine-readable location identifier (e.g. `"loc-eu-west-1"`). |
| `test.run.artifact_url` | string | Link to trace viewer, HAR archive, or screenshot archive for this run. |
| `test.frequency_sec` | integer | Scheduled repeat interval in seconds. Omit for CI-gate runs. |
| `trace.id` | string | Distributed trace ID (32-char hex). Enables APM correlation in Grail. |
| `span.id` | string | W3C span ID for this run-level span (16-char hex). |
| `runner.name` | string | Name of the test runner (e.g. `"playwright-wrapper"`, `"k6-template"`). |
| `runner.version` | string | Version of the runner (e.g. `"1.4.2"`). |
| `runner.instance.id` | string | Instance ID when multiple runner replicas send to the same endpoint. |
| `dt.smartscape.frontend` | string | FRONTEND entity ID (e.g. `"FRONTEND-5F280D9DD8EF6A55"`). Draws EXT_TEST → FRONTEND dependency edge in Smartscape. Must be `FRONTEND-*` format — `APPLICATION-*` IDs are a different entity system and will not work here. See [Linking to a Frontend](#linking-to-a-frontend). |
| `dt.entity.application` | string | APPLICATION entity ID (e.g. `"APPLICATION-4EFE35D6B0136138"`). Must be provided **together with** `dt.smartscape.frontend` — the pipeline and associated workflows fire Davis events on the application when both fields are present and the run failed, enabling frontend problem correlation. |
| `dt.security_context` | string | Data segregation tag (e.g. `"team-checkout"`). Controls data access policies — only token holders with the matching context can query this team's events. Also used for cost attribution per team. |
| `ci.job.url` | string | Link to the CI job that triggered this run. |
| `ci.trigger` | string | How the run was triggered: `"schedule"` \| `"ci"` \| `"deployment"` \| `"manual"`. |
| `ci.pipeline.id` | string | CI pipeline run ID. |
| `ci.pipeline.name` | string | CI pipeline name. |
| `ci.commit.sha` | string | Git commit SHA that triggered this run. |
| `ci.branch` | string | Git branch name. |
| `device.model` | string | Device model identifier for mobile test runs. |

---

### external_test_step

Represents one step within a test run. Optional — include alongside the run event to get
step-level metrics and drill-down capability.

**Required fields:**

| Field | Type | Description |
|-------|------|-------------|
| `event.kind` | string | Always `"EXTERNAL_TEST_EVENT"` |
| `event.type` | string | Always `"external_test_step"` |
| `test.run.id` | string | Must match the parent `external_test_run`'s `test.run.id`. |
| `test.id` | string | Must match the parent `external_test_run`'s `test.id`. Required for stitching to the parent EXT_TEST Smartscape node. |
| `test.step.id` | string | Unique step execution ID within this run (e.g. `"step-001"`). |
| `test.step.name` | string | Step identifier (e.g. `"open-homepage"`, `"fill-shipping"`). |
| `test.step.index` | integer | Ordinal position of this step in the run. Use a consistent convention within your runner (zero-based or one-based). |
| `test.step.status` | string | `"passed"` \| `"failed"` \| `"errored"` \| `"skipped"` |
| `test.step.duration_ms` | integer | Step duration in milliseconds. |
| `timestamp` | string | ISO 8601 UTC timestamp when the step started. |

**Optional fields:**

| Field | Type | Description |
|-------|------|-------------|
| `test.step.type` | string | Step category: `"navigation"` \| `"click"` \| `"api_call"` \| `"assertion"` |
| `test.step.error_code` | string | Error code when step status is `"failed"` or `"errored"`. |
| `test.step.error_message` | string | Human-readable description of the step failure. |
| `test.step.url` | string | URL being tested in this step. Credential-bearing query parameters (`token`, `api_key`, `password`, `secret`, `authorization`, `bearer_token`, `session_id`, `signature`) are automatically masked by the pipeline to `***MASKED***`. |
| `test.step.screenshot_url` | string | Link to a screenshot artifact captured at this step (clickable in dashboards). |
| `dt.security_context` | string | Data segregation tag — denormalize from the parent run for consistent query access control. |
| `trace.id` | string | Trace ID for distributed tracing correlation. |
| `span.id` | string | Span ID for this step (16-char hex). |

### Status values and OpenPipeline behaviour

| Status | `test.run.availability` | Counted in availability metric | Notes |
|--------|------------------------|-------------------------------|-------|
| `passed` | `1` | Yes | |
| `failed` | `0` | Yes | Triggers error-code counter metric and Davis alerting |
| `errored` | `0` | Yes | Runner-level error (setup failure, crash); treated same as failed |
| `timeout` | `0` | Yes | Global run timeout exceeded before any result |
| `maintenance` | `0` | **No** | Use for planned downtime windows |
| `decommissioned` | `0` | **No** | Send as the last event to signal test retirement |

The steps pipeline adds `result.status.category` to each step event after ingestion
(`SUCCESS` / `SKIPPED` / `FAIL`). Run events do not get this field — filter runs by the raw
`test.run.status` field instead.

---

## Pipeline-Added Fields

The following fields are written by OpenPipeline after ingestion. **Do not send these in the
event payload** — sending them has no effect since the pipeline overwrites them.

| Field | Written by | Value |
|-------|-----------|-------|
| `dt.smartscape.ext_test` | `smartscapeNode` processor on runs pipeline; `fieldsAdd` stitching processor on steps pipeline | Smartscape node ID derived from `test.id`. Used for topology correlation — keep `test.id` stable across runs to accumulate history. |
| `result.status.category` | `fieldsAdd` processor on steps pipeline | `SUCCESS` / `SKIPPED` / `FAIL` — normalized from `test.step.status`. Run events do **not** get this field. |

---

## Linking to a Frontend

To draw an EXT_TEST → FRONTEND dependency in Smartscape and have Davis correlate test failures
with frontend problems, include both fields on the run event:

- `dt.smartscape.frontend` — the `FRONTEND-XXXX` Smartscape node ID of the application
- `dt.entity.application` — the `APPLICATION-XXXX` classic entity ID of the same application

Both must be present together. When the run fails and both fields are set, the associated
Frontend Impact Notifier workflow creates a Davis event on the application entity, enabling
the Dynatrace Frontend-Driven Investigation (FDI) to correlate the test failure with a frontend
problem. Without `dt.entity.application`, no Davis event is created; without
`dt.smartscape.frontend`, no Smartscape edge is drawn.

**`FRONTEND-*` vs `APPLICATION-*` are different entity systems** — you cannot use one where the
other is expected. Find the correct IDs via Smartscape DQL:

```dql
smartscapeNodes "FRONTEND"
| filter contains(name, "My Web Application")
| fields id, name
```

The `id` value (e.g. `FRONTEND-5F280D9DD8EF6A55`) is what goes in `dt.smartscape.frontend`.
To find the matching APPLICATION entity ID, look in the Dynatrace Applications UI or run:

```dql
fetch dt.entity.application
| filter entity.name == "My Web Application"
| fields id, entity.name
```

---

## Error Codes

`test.run.error_code` and `test.step.error_code` are free-form strings (≤100 chars). The field
is intentionally open-ended — use whatever categorization your runner framework produces
naturally. The following taxonomy is recommended for consistency with community dashboards:

| Code | Meaning |
|------|---------|
| `TIMEOUT` | Operation exceeded its timeout (connection, element wait, or response) |
| `ASSERTION_FAILED` | A test assertion did not hold |
| `LOCATOR_NOT_FOUND` | CSS/XPath selector matched no elements |
| `JAVASCRIPT_ERROR` | Uncaught JavaScript exception in the page |
| `NETWORK_ERROR` | Network-level failure (DNS, connection refused, TLS) |
| `AUTH_FAILED` | Authentication or authorization failure |
| `RATE_LIMITED` | HTTP 429 — too many requests |
| `UNEXPECTED_STATUS_CODE` | HTTP response was an unexpected status code (e.g. 500 when expecting 200) |

HTTP-specific codes (`HTTP_401`, `HTTP_403`, `HTTP_500`, `HTTP_503`, `HTTP_504`,
`TIMEOUT_CONNECT`, `TIMEOUT_READ`) are also widely used and work fine; they are more precise
but reduce portability across dashboard templates. The recommended taxonomy maps these to broader
categories (`AUTH_FAILED`, `TIMEOUT`, `UNEXPECTED_STATUS_CODE`).

For business-level failures specific to your domain (e.g. payment declined, inventory empty),
use clear all-caps names that distinguish them from system-level codes:
`PAYMENT_DECLINED`, `INVENTORY_EMPTY`, or use a domain prefix: `BIZ_PAYMENT_DECLINED`.

---

## Examples

### Minimal — single run event

```text
curl -X POST "https://xdc84620.dev.apps.dynatracelabs.com/platform/ingest/custom/events/external.tests" \
  -H "Authorization: Api-Token {token}" \
  -H "Content-Type: application/json" \
  -d '[{
    "event.kind": "EXTERNAL_TEST_EVENT",
    "event.type": "external_test_run",
    "test.id": "api-health-check",
    "test.run.id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "test.name": "API Health Check",
    "test.type": "api",
    "test.run.status": "passed",
    "test.run.availability": 1,
    "test.run.duration_ms": 245,
    "test.run.location": "us-east-1",
    "timestamp": "2024-01-15T10:30:00Z"
  }]'
```

### Extended — run with steps, error context, and CI metadata

```json
[
  {
    "event.kind": "EXTERNAL_TEST_EVENT",
    "event.type": "external_test_run",
    "test.id": "checkout-flow",
    "test.run.id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "test.name": "Checkout Flow E2E",
    "test.type": "browser",
    "test.run.status": "failed",
    "test.run.availability": 0,
    "test.run.duration_ms": 8350,
    "test.run.location": "eu-west-1",
    "test.run.location.lat": 53.33,
    "test.run.location.lon": -6.25,
    "test.run.error_code": "LOCATOR_NOT_FOUND",
    "test.run.error_message": "Element '#checkout-button' not found after 5s wait",
    "runner.name": "playwright-wrapper",
    "runner.version": "1.4.2",
    "trace.id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span.id": "00f067aa0ba902b7",
    "ci.job.url": "https://github.com/acme/shop/actions/runs/12345678",
    "ci.trigger": "schedule",
    "ci.branch": "main",
    "dt.security_context": "team-checkout",
    "timestamp": "2024-01-15T14:22:10Z"
  },
  {
    "event.kind": "EXTERNAL_TEST_EVENT",
    "event.type": "external_test_step",
    "test.run.id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "test.id": "checkout-flow",
    "test.step.id": "step-001",
    "test.step.name": "open-homepage",
    "test.step.type": "navigation",
    "test.step.index": 1,
    "test.step.status": "passed",
    "test.step.duration_ms": 1200,
    "trace.id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span.id": "a3ce929d0e0e4736",
    "dt.security_context": "team-checkout",
    "timestamp": "2024-01-15T14:22:10Z"
  },
  {
    "event.kind": "EXTERNAL_TEST_EVENT",
    "event.type": "external_test_step",
    "test.run.id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "test.id": "checkout-flow",
    "test.step.id": "step-002",
    "test.step.name": "add-to-cart",
    "test.step.type": "click",
    "test.step.index": 2,
    "test.step.status": "failed",
    "test.step.duration_ms": 7150,
    "test.step.error_code": "LOCATOR_NOT_FOUND",
    "test.step.error_message": "Element '#checkout-button' not found after 5s wait",
    "trace.id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span.id": "b4cf030e1f1f5847",
    "dt.security_context": "team-checkout",
    "timestamp": "2024-01-15T14:22:11Z"
  }
]
```

---

## Java DTO

Uses Jackson for JSON serialisation. `@JsonInclude(NON_NULL)` ensures optional fields are
omitted when null rather than serialised as `null`.

```text
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ExternalTestRunEvent(
    @JsonProperty("event.kind")              String eventKind,              // "EXTERNAL_TEST_EVENT"
    @JsonProperty("event.type")              String eventType,              // "external_test_run"
    @JsonProperty("test.id")                 String testId,
    @JsonProperty("test.run.id")             String testRunId,
    @JsonProperty("test.name")               String testName,
    @JsonProperty("test.type")               String testType,               // "browser"|"api"|"mobile"|"http"
    @JsonProperty("test.run.status")         String testRunStatus,          // "passed"|"failed"|"errored"|"timeout"|"maintenance"|"decommissioned"
    @JsonProperty("test.run.availability")   int    testRunAvailability,    // 1 or 0
    @JsonProperty("test.run.duration_ms")    long   testRunDurationMs,
    @JsonProperty("test.run.location")       String testRunLocation,
    @JsonProperty("timestamp")               String timestamp,

    // Optional — set to null to omit
    @JsonProperty("test.run.error_code")     String testRunErrorCode,
    @JsonProperty("test.run.error_message")  String testRunErrorMessage,
    @JsonProperty("test.run.location.lat")   Double testRunLocationLat,
    @JsonProperty("test.run.location.lon")   Double testRunLocationLon,
    @JsonProperty("test.run.location_id")    String testRunLocationId,
    @JsonProperty("test.run.artifact_url")   String testRunArtifactUrl,
    @JsonProperty("test.frequency_sec")      Integer testFrequencySec,
    @JsonProperty("trace.id")                String traceId,
    @JsonProperty("span.id")                 String spanId,
    @JsonProperty("runner.name")             String runnerName,
    @JsonProperty("runner.version")          String runnerVersion,
    @JsonProperty("runner.instance.id")      String runnerInstanceId,
    @JsonProperty("dt.smartscape.frontend")  String dtSmartscapeFrontend,
    @JsonProperty("dt.entity.application")   String dtEntityApplication,
    @JsonProperty("dt.security_context")     String dtSecurityContext,
    @JsonProperty("ci.job.url")              String ciJobUrl,
    @JsonProperty("ci.trigger")              String ciTrigger,              // "schedule"|"ci"|"deployment"|"manual"
    @JsonProperty("ci.pipeline.id")          String ciPipelineId,
    @JsonProperty("ci.pipeline.name")        String ciPipelineName,
    @JsonProperty("ci.commit.sha")           String ciCommitSha,
    @JsonProperty("ci.branch")               String ciBranch,
    @JsonProperty("device.model")            String deviceModel
) {}

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ExternalTestStepEvent(
    @JsonProperty("event.kind")               String eventKind,             // "EXTERNAL_TEST_EVENT"
    @JsonProperty("event.type")               String eventType,             // "external_test_step"
    @JsonProperty("test.run.id")              String testRunId,
    @JsonProperty("test.id")                  String testId,
    @JsonProperty("test.step.id")             String testStepId,            // unique step execution ID, e.g. "step-001"
    @JsonProperty("test.step.name")           String testStepName,
    @JsonProperty("test.step.index")          int    testStepIndex,
    @JsonProperty("test.step.status")         String testStepStatus,        // "passed"|"failed"|"errored"|"skipped"
    @JsonProperty("test.step.duration_ms")    long   testStepDurationMs,
    @JsonProperty("timestamp")                String timestamp,

    // Optional
    @JsonProperty("test.step.type")           String testStepType,          // "navigation"|"click"|"api_call"|"assertion"
    @JsonProperty("test.step.error_code")     String testStepErrorCode,
    @JsonProperty("test.step.error_message")  String testStepErrorMessage,
    @JsonProperty("test.step.url")            String testStepUrl,           // credentials masked by pipeline
    @JsonProperty("test.step.screenshot_url") String testStepScreenshotUrl,
    @JsonProperty("dt.security_context")      String dtSecurityContext,
    @JsonProperty("trace.id")                 String traceId,
    @JsonProperty("span.id")                  String spanId
) {}
```

Send a batch containing the run and its steps:

```text
List<Object> batch = new ArrayList<>();
batch.add(runEvent);
batch.addAll(stepEvents);

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create(dtEndpoint))
    .header("Authorization", "Api-Token " + dtToken)
    .header("Content-Type", "application/json")
    .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(batch)))
    .build();
```

---

## DQL Verification

Verify run events were ingested:

```dql
fetch events, from:now()-1h
| filter event.type == "external_test_run"
| fields timestamp, test.id, test.name, test.run.status, test.run.duration_ms, test.run.location
| sort timestamp desc
| limit 20
```

Verify step events:

```dql
fetch events, from:now()-1h
| filter event.type == "external_test_step"
| fields timestamp, test.id, test.step.name, test.step.status, test.step.duration_ms
| sort timestamp desc
| limit 20
```

Look up all events for a specific run:

```dql
fetch events, from:now()-1h
| filter in(event.type, {"external_test_run", "external_test_step"})
| filter test.run.id == "f47ac10b-58cc-4372-a567-0e02b2c3d479"
| fields timestamp, event.type, test.step.name, test.run.status, test.step.status
| sort timestamp asc
```

Availability summary by test over the last 24h:

```dql
fetch events, from:now()-24h
| filter event.type == "external_test_run"
| summarize
    total = count(),
    passed = countIf(test.run.availability == 1),
    by: { test.id, test.name }
| fieldsAdd availability_pct = (toDouble(passed) / toDouble(total)) * 100
| sort availability_pct asc
```

Top error codes for a failing test:

```dql
fetch events, from:now()-7d
| filter event.type == "external_test_run" AND test.run.status == "failed"
| summarize failure_count = count(), by: { test.id, test.run.error_code }
| sort failure_count desc
| limit 20
```
