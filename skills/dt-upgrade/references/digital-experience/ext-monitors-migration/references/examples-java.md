# Java Before/After Examples: External Monitor Migration

Migration from `POST /api/v1/synthetic/ext/tests` to `POST /platform/ingest/custom/events/external.tests`.

Source: `samples/2ndgen3rdpartymonitors/java` in the legacy monitor repo.

---

## 1. Models

### Before — legacy bean hierarchy

Five plain Java beans, one wrapper object per POST.

```text
// SyntheticPayload.java — the single root object POSTed each cycle
@JsonInclude(JsonInclude.Include.NON_NULL)
public class SyntheticPayload {
    private String syntheticEngineName;
    private String syntheticEngineIconUrl;
    private long messageTimestamp;           // epoch ms — payload-level clock
    private List<LocationInfo> locations;    // static location metadata
    private List<TestDefinition> tests;      // test definitions (stable)
    private List<TestResult> testResults;    // per-cycle results
    // constructor, getters, setters …
}

// TestDefinition.java — describes what runs
@JsonInclude(JsonInclude.Include.NON_NULL)
public class TestDefinition {
    private String id;
    private String title;
    private int scheduleIntervalInSeconds;
    private boolean enabled;
    private boolean deleted;
    private List<LocationRef> locations;
    private List<TestStep> steps;            // step id (int) + title (String)
    // constructor, getters, setters …
}

// TestResult.java — top-level result wrapper
@JsonInclude(JsonInclude.Include.NON_NULL)
public class TestResult {
    private String id;                       // matches TestDefinition.id
    private int totalStepCount;
    private List<LocationResult> locationResults;
    // constructor, getters, setters …
}

// LocationResult.java — one entry per location per test per cycle
@JsonInclude(JsonInclude.Include.NON_NULL)
public class LocationResult {
    private String id;                       // location id string
    private long startTimestamp;             // epoch ms
    private boolean success;
    private int responseTimeMillis;
    private double successRate;
    private List<StepResult> stepResults;
    // constructor, getters, setters …
}

// StepResult.java — one entry per step
@JsonInclude(JsonInclude.Include.NON_NULL)
public class StepResult {
    private int id;                          // matches TestStep.id
    private long startTimestamp;             // epoch ms
    private int responseTimeMillis;
    // constructor, getters, setters …
    // Note: error field not shown in base sample; see schema-mapping.md §stepResults
}
```

### After — two Jackson records

Delete the entire `model/` package. Replace with two records. One POST sends a `List<Object>` mixing both types.

```text
// ExternalTestRunEvent.java
package com.dynatrace.monitors.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

import static com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL;

@JsonInclude(NON_NULL)
public record ExternalTestRunEvent(
    // required — always set
    @JsonProperty("event.kind")             String  eventKind,         // always "EXTERNAL_TEST_EVENT"
    @JsonProperty("event.type")             String  eventType,         // always "external_test_run"
    @JsonProperty("test.id")               String  testId,
    @JsonProperty("test.run.id")           String  testRunId,          // UUID v4, generated per (test, location)
    @JsonProperty("test.name")             String  testName,
    @JsonProperty("test.type")             String  testType,           // "api" | "browser" | "http" | "mobile"
    @JsonProperty("test.run.status")       String  testRunStatus,      // "passed" | "failed"
    @JsonProperty("test.run.availability") int     testRunAvailability, // 1 or 0
    @JsonProperty("test.run.duration_ms")  long    testRunDurationMs,
    @JsonProperty("test.run.location")     String  testRunLocation,
    @JsonProperty("timestamp")             String  timestamp,           // ISO 8601 UTC
    // optional — null fields omitted by @JsonInclude(NON_NULL)
    @JsonProperty("test.frequency_sec")     Integer testFrequencySec,
    @JsonProperty("runner.name")            String  runnerName,
    @JsonProperty("test.run.error_code")    String  testRunErrorCode,
    @JsonProperty("test.run.error_message") String  testRunErrorMessage
) {}
```

```text
// ExternalTestStepEvent.java
package com.dynatrace.monitors.model;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

import static com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL;

@JsonInclude(NON_NULL)
public record ExternalTestStepEvent(
    // required
    @JsonProperty("event.kind")              String eventKind,         // always "EXTERNAL_TEST_EVENT"
    @JsonProperty("event.type")              String eventType,         // always "external_test_step"
    @JsonProperty("test.run.id")             String testRunId,         // same UUID as the parent run event
    @JsonProperty("test.id")                String testId,
    @JsonProperty("test.step.id")           String testStepId,         // e.g. "step-1"
    @JsonProperty("test.step.name")         String testStepName,       // slugified title
    @JsonProperty("test.step.index")        int    testStepIndex,      // integer step ordering
    @JsonProperty("test.step.status")       String testStepStatus,     // "passed" | "failed"
    @JsonProperty("test.step.duration_ms")  long   testStepDurationMs,
    @JsonProperty("timestamp")              String timestamp,           // ISO 8601 UTC
    // optional
    @JsonProperty("test.step.error_code")    String testStepErrorCode,    // string, e.g. "500"
    @JsonProperty("test.step.error_message") String testStepErrorMessage
) {}
```

---

## 2. Config

### Before

```text
public final class Config {

    private final String tenantUrl;   // classic env domain, e.g. abc12345.live.dynatrace.com
    private final String apiToken;    // scope: ExternalSyntheticIntegration
    private final int intervalSeconds;
    private final int durationSeconds;
    private final String endpoint;

    private Config(String tenantUrl, String apiToken, int intervalSeconds, int durationSeconds) {
        this.tenantUrl = tenantUrl;
        this.apiToken = apiToken;
        this.intervalSeconds = intervalSeconds;
        this.durationSeconds = durationSeconds;
        this.endpoint = tenantUrl + "/api/v1/synthetic/ext/tests";
    }

    public static Config fromEnv() {
        String tenantUrl   = System.getenv("DT_TENANT_URL");
        String apiToken    = System.getenv("DT_API_TOKEN");
        String intervalStr = System.getenv("INTERVAL");
        String durationStr = System.getenv("DURATION");
        return fromValues(tenantUrl, apiToken, intervalStr, durationStr);
    }

    static Config fromValues(String tenantUrl, String apiToken, String intervalStr, String durationStr) {
        if (tenantUrl == null || tenantUrl.isBlank()) {
            throw new IllegalStateException("Required environment variable DT_TENANT_URL is missing or blank");
        }
        if (apiToken == null || apiToken.isBlank()) {
            throw new IllegalStateException("Required environment variable DT_API_TOKEN is missing or blank");
        }
        int intervalSeconds = parseIntOrDefault(intervalStr, 10);
        int durationSeconds = parseIntOrDefault(durationStr, 0);
        return new Config(tenantUrl.trim(), apiToken.trim(), intervalSeconds, durationSeconds);
    }

    public String getTenantUrl() { return tenantUrl; }
    public String getApiToken()  { return apiToken; }
    // …
}
```

### After

Two changes: env var renamed `DT_TENANT_URL` → `DT_ENV_URL` (apps domain); endpoint path updated.

```text
public final class Config {

    // Apps domain, e.g. abc12345.apps.dynatrace.com — NOT the classic *.live.dynatrace.com domain.
    // Verify the correct apps domain with the customer; do not derive it by swapping the suffix.
    private final String envUrl;
    private final String apiToken;    // scope: openpipeline.events.custom
    private final int intervalSeconds;
    private final int durationSeconds;
    private final String endpoint;

    private Config(String envUrl, String apiToken, int intervalSeconds, int durationSeconds) {
        this.envUrl = envUrl;
        this.apiToken = apiToken;
        this.intervalSeconds = intervalSeconds;
        this.durationSeconds = durationSeconds;
        this.endpoint = envUrl + "/platform/ingest/custom/events/external.tests";
    }

    public static Config fromEnv() {
        String envUrl      = System.getenv("DT_ENV_URL");   // renamed; must be apps domain
        String apiToken    = System.getenv("DT_API_TOKEN");
        String intervalStr = System.getenv("INTERVAL");
        String durationStr = System.getenv("DURATION");
        return fromValues(envUrl, apiToken, intervalStr, durationStr);
    }

    static Config fromValues(String envUrl, String apiToken, String intervalStr, String durationStr) {
        if (envUrl == null || envUrl.isBlank()) {
            throw new IllegalStateException("Required environment variable DT_ENV_URL is missing or blank");
        }
        if (apiToken == null || apiToken.isBlank()) {
            throw new IllegalStateException("Required environment variable DT_API_TOKEN is missing or blank");
        }
        int intervalSeconds = parseIntOrDefault(intervalStr, 10);
        int durationSeconds = parseIntOrDefault(durationStr, 0);
        return new Config(envUrl.trim(), apiToken.trim(), intervalSeconds, durationSeconds);
    }

    private static int parseIntOrDefault(String value, int defaultValue) {
        if (value == null || value.isBlank()) return defaultValue;
        try {
            return Integer.parseInt(value.trim());
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }

    public String getEnvUrl()        { return envUrl; }
    public String getApiToken()      { return apiToken; }
    public int getIntervalSeconds()  { return intervalSeconds; }
    public int getDurationSeconds()  { return durationSeconds; }
    public String getEndpoint()      { return endpoint; }
}
```

---

## 3. HTTP Client

### Before

```text
/**
 * Thin HTTP client that POSTs {@link SyntheticPayload} to the Dynatrace v1 synthetic API.
 */
public class DynatraceClient {

    private final Config config;
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;

    public DynatraceClient(Config config) {
        this.config = config;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
        this.objectMapper = new ObjectMapper();
    }

    public void post(SyntheticPayload payload) {
        try {
            String json = objectMapper.writeValueAsString(payload);  // single object

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(config.getEndpoint()))
                    .header("Authorization", "Api-Token " + config.getApiToken())
                    .header("Content-Type", "application/json; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofString(json))
                    .timeout(Duration.ofSeconds(10))
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            String body = response.body();
            if (body == null || body.isBlank()) body = "(empty)";
            else body = body.trim();

            System.out.printf("HTTP %d  body: %s%n", response.statusCode(), body);

        } catch (Exception e) {
            System.err.println("ERROR posting payload: " + e.getMessage());
        }
    }
}
```

### After

Parameter type changes from `SyntheticPayload` to `List<Object>`. The new endpoint requires a JSON array; `objectMapper.writeValueAsString(events)` serializes the list directly. Auth header format is unchanged.

```text
/**
 * Thin HTTP client that POSTs a JSON array of events to the Dynatrace custom events ingest API.
 */
public class DynatraceClient {

    private final Config config;
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;

    public DynatraceClient(Config config) {
        this.config = config;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
        this.objectMapper = new ObjectMapper();
    }

    public void post(List<Object> events) {
        try {
            String json = objectMapper.writeValueAsString(events);  // serializes as JSON array

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(config.getEndpoint()))
                    .header("Authorization", "Api-Token " + config.getApiToken())
                    .header("Content-Type", "application/json; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofString(json))
                    .timeout(Duration.ofSeconds(10))
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            String body = response.body();
            if (body == null || body.isBlank()) body = "(empty)";
            else body = body.trim();

            System.out.printf("HTTP %d  body: %s%n", response.statusCode(), body);

        } catch (Exception e) {
            System.err.println("ERROR posting events: " + e.getMessage());
        }
    }
}
```

---

## 4. Builder

### Before

```text
/**
 * Builds complete {@link SyntheticPayload} objects for Monitor 1 — Java Happy Path.
 * All steps always succeed; response times are jittered ±20% on each call.
 */
public class PayloadBuilder {

    private static final String ENGINE_NAME  = "JavaHappyPath";
    private static final String ENGINE_ICON_URL = "https://static.thenounproject.com/png/1745-200.png";
    private static final String MONITOR_ID   = "monitor-1-java-happy-path";
    private static final String MONITOR_TITLE = "3rd party test - java happy path";
    private static final LocationInfo LOCATION =
            new LocationInfo("us-east-1", "US East (N. Virginia)", "203.0.113.10");
    private static final int SCHEDULE_INTERVAL_SECONDS = 60;
    private static final List<TestStep> STEPS = List.of(
            new TestStep(1, "Open homepage"),
            new TestStep(2, "Search for product"),
            new TestStep(3, "Add to cart")
    );
    private static final int[] BASE_STEP_MS = {320, 480, 210};

    private final Random rng = new Random();

    public SyntheticPayload build(long nowMs) {
        int[] stepMs = new int[STEPS.size()];
        int totalMs = 0;
        for (int i = 0; i < STEPS.size(); i++) {
            stepMs[i] = Jitter.apply(BASE_STEP_MS[i], rng);
            totalMs += stepMs[i];
        }

        long locationStartMs = nowMs - totalMs;
        List<StepResult> stepResults = new ArrayList<>();
        long offset = 0;
        for (int i = 0; i < STEPS.size(); i++) {
            stepResults.add(new StepResult(STEPS.get(i).getId(), locationStartMs + offset, stepMs[i]));
            offset += stepMs[i];
        }

        LocationResult locationResult = new LocationResult(
                LOCATION.getId(), locationStartMs, true, totalMs, 1.0, stepResults);

        TestResult testResult = new TestResult(MONITOR_ID, STEPS.size(), List.of(locationResult));

        TestDefinition testDefinition = new TestDefinition(
                MONITOR_ID, MONITOR_TITLE, SCHEDULE_INTERVAL_SECONDS,
                true, false,
                List.of(new LocationRef(LOCATION.getId())), STEPS);

        return new SyntheticPayload(
                ENGINE_NAME, ENGINE_ICON_URL, nowMs,
                List.of(LOCATION), List.of(testDefinition), List.of(testResult));
    }
}
```

### After

Return type changes from `SyntheticPayload` to `List<Object>`. Fan-out: one run event + one step event per step, all in one list. A UUID is generated per location and shared across run and step events.

```text
import com.dynatrace.monitors.model.ExternalTestRunEvent;
import com.dynatrace.monitors.model.ExternalTestStepEvent;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Random;
import java.util.UUID;

/**
 * Builds a list of events for Monitor 1 — Java Happy Path.
 * Emits one external_test_run event and one external_test_step event per step.
 */
public class PayloadBuilder {

    private static final String ENGINE_NAME  = "JavaHappyPath";
    private static final String MONITOR_ID   = "monitor-1-java-happy-path";
    private static final String MONITOR_TITLE = "3rd party test - java happy path";
    private static final String LOCATION_ID  = "us-east-1";
    private static final String TEST_TYPE    = "api";
    private static final int SCHEDULE_INTERVAL_SECONDS = 60;

    // Step definitions carried forward from the legacy sample unchanged.
    private static final List<int[]> STEPS = List.of(
            new int[]{1},   // step ids — titles stored separately for slugification
            new int[]{2},
            new int[]{3}
    );
    private static final String[] STEP_TITLES = {"Open homepage", "Search for product", "Add to cart"};
    private static final int[] BASE_STEP_MS   = {320, 480, 210};

    private final Random rng = new Random();

    public List<Object> build(long nowMs) {
        List<Object> events = new ArrayList<>();

        // Compute jittered step durations (same logic as before).
        int[] stepMs = new int[BASE_STEP_MS.length];
        int totalMs = 0;
        for (int i = 0; i < BASE_STEP_MS.length; i++) {
            stepMs[i] = Jitter.apply(BASE_STEP_MS[i], rng);
            totalMs += stepMs[i];
        }

        long locationStartMs = nowMs - totalMs;

        // One UUID per (test, location) pair per cycle — shared by run + all step events.
        String runId = UUID.randomUUID().toString();

        // ISO 8601 UTC timestamps from epoch ms.
        String runTimestamp = Instant.ofEpochMilli(locationStartMs).toString();

        // Run event — maps from TestResult.LocationResult.
        events.add(new ExternalTestRunEvent(
                "EXTERNAL_TEST_EVENT",
                "external_test_run",
                MONITOR_ID,
                runId,
                MONITOR_TITLE,
                TEST_TYPE,
                "passed",               // happy path always succeeds
                1,                      // availability: 1 = passed, 0 = failed
                totalMs,
                LOCATION_ID,
                runTimestamp,
                SCHEDULE_INTERVAL_SECONDS,   // optional: test.frequency_sec
                ENGINE_NAME,                  // optional: runner.name (was syntheticEngineName)
                null,                         // test.run.error_code — none on success
                null                          // test.run.error_message — none on success
        ));

        // Step events — one per StepResult.
        // stepResults[i].startTimestamp was locationStartMs + cumulative offset.
        long offset = 0;
        for (int i = 0; i < BASE_STEP_MS.length; i++) {
            int stepIndex = i + 1;                                   // 1-based, matches legacy StepResult.id
            String stepTimestamp = Instant.ofEpochMilli(locationStartMs + offset).toString();

            events.add(new ExternalTestStepEvent(
                    "EXTERNAL_TEST_EVENT",
                    "external_test_step",
                    runId,                                           // same UUID as run event
                    MONITOR_ID,
                    "step-" + stepIndex,                             // test.step.id
                    slugify(STEP_TITLES[i]),                         // test.step.name — slugified title
                    stepIndex,                                       // test.step.index
                    "passed",                                        // happy path
                    stepMs[i],
                    stepTimestamp,
                    null,                                            // test.step.error_code
                    null                                             // test.step.error_message
            ));

            offset += stepMs[i];
        }

        return events;
    }

    // Slugify step title: lowercase, spaces replaced with hyphens.
    // "Open homepage" → "open-homepage"
    private static String slugify(String title) {
        return title.toLowerCase(Locale.ROOT).replaceAll("\\s+", "-");
    }
}
```

**Mapping notes:**
- `syntheticEngineIconUrl` — dropped, no equivalent.
- `successRate` — dropped, no equivalent.
- `messageTimestamp` (payload root) — not forwarded; each event uses `locationResult.startTimestamp` converted to ISO 8601.
- `tests[].deleted` — if ever `true`, emit a single run event with `test.run.status: "decommissioned"` and skip step events (see `schema-mapping.md` §2).

---

## 5. Tests

### Before

```text
class PayloadBuilderTest {

    private static final long FIXED_TIMESTAMP = 1_700_000_000_000L;
    private PayloadBuilder builder;

    @BeforeEach
    void setUp() { builder = new PayloadBuilder(); }

    @Test
    void buildReturnsNonNullPayload() {
        SyntheticPayload payload = builder.build(FIXED_TIMESTAMP);
        assertNotNull(payload);
    }

    @Test
    void buildSetsCorrectEngineName() {
        SyntheticPayload payload = builder.build(FIXED_TIMESTAMP);
        assertEquals("JavaHappyPath", payload.getSyntheticEngineName());
    }

    @Test
    void buildSetsCorrectMessageTimestamp() {
        SyntheticPayload payload = builder.build(FIXED_TIMESTAMP);
        assertEquals(FIXED_TIMESTAMP, payload.getMessageTimestamp());
    }

    @Test
    void buildHasExactlyOneLocationWithCorrectId() {
        SyntheticPayload payload = builder.build(FIXED_TIMESTAMP);
        assertEquals(1, payload.getLocations().size());
        assertEquals("us-east-1", payload.getLocations().get(0).getId());
    }

    @Test
    void buildHasExactlyOneTestWithThreeSteps() {
        SyntheticPayload payload = builder.build(FIXED_TIMESTAMP);
        assertEquals(1, payload.getTests().size());
        assertEquals(3, payload.getTests().get(0).getSteps().size());
    }

    @Test
    void buildHasExactlyOneTestResult() {
        SyntheticPayload payload = builder.build(FIXED_TIMESTAMP);
        assertEquals(1, payload.getTestResults().size());
    }

    @Test
    void buildLocationResultIsSuccessful() {
        SyntheticPayload payload = builder.build(FIXED_TIMESTAMP);
        LocationResult lr = payload.getTestResults().get(0).getLocationResults().get(0);
        assertTrue(lr.isSuccess());
    }

    @Test
    void buildLocationResultHasThreeStepResultsWithPositiveResponseTimes() {
        SyntheticPayload payload = builder.build(FIXED_TIMESTAMP);
        LocationResult lr = payload.getTestResults().get(0).getLocationResults().get(0);
        assertEquals(3, lr.getStepResults().size());
        for (StepResult sr : lr.getStepResults()) {
            assertTrue(sr.getResponseTimeMillis() > 0);
        }
    }
}
```

### After

```text
import com.dynatrace.monitors.model.ExternalTestRunEvent;
import com.dynatrace.monitors.model.ExternalTestStepEvent;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class PayloadBuilderTest {

    private static final long FIXED_TIMESTAMP = 1_700_000_000_000L;
    private PayloadBuilder builder;

    @BeforeEach
    void setUp() { builder = new PayloadBuilder(); }

    @Test
    void buildReturnsNonEmptyList() {
        List<Object> events = builder.build(FIXED_TIMESTAMP);
        assertNotNull(events);
        assertFalse(events.isEmpty());
    }

    @Test
    void firstEventIsRunEvent() {
        List<Object> events = builder.build(FIXED_TIMESTAMP);
        assertInstanceOf(ExternalTestRunEvent.class, events.get(0));
        ExternalTestRunEvent run = (ExternalTestRunEvent) events.get(0);
        assertEquals("external_test_run", run.eventType());
        assertEquals("EXTERNAL_TEST_EVENT", run.eventKind());
    }

    @Test
    void runEventHasNonNullUuidRunId() {
        List<Object> events = builder.build(FIXED_TIMESTAMP);
        ExternalTestRunEvent run = (ExternalTestRunEvent) events.get(0);
        assertNotNull(run.testRunId());
        // UUID v4 format: 8-4-4-4-12 lowercase hex groups
        assertTrue(run.testRunId().matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
                "testRunId must be a UUID v4: " + run.testRunId());
    }

    @Test
    void runEventStatusIsStringNotBoolean() {
        List<Object> events = builder.build(FIXED_TIMESTAMP);
        ExternalTestRunEvent run = (ExternalTestRunEvent) events.get(0);
        // The new API uses string status; boolean isSuccess() no longer exists.
        String status = run.testRunStatus();
        assertTrue(status.equals("passed") || status.equals("failed"),
                "testRunStatus must be 'passed' or 'failed', got: " + status);
    }

    @Test
    void runEventTimestampIsIso8601() {
        List<Object> events = builder.build(FIXED_TIMESTAMP);
        ExternalTestRunEvent run = (ExternalTestRunEvent) events.get(0);
        assertNotNull(run.timestamp());
        // Instant.parse throws DateTimeParseException for invalid ISO 8601
        assertDoesNotThrow(() -> Instant.parse(run.timestamp()),
                "timestamp must be parseable ISO 8601: " + run.timestamp());
    }

    @Test
    void hasOneRunEventAndThreeStepEvents() {
        List<Object> events = builder.build(FIXED_TIMESTAMP);
        long runCount = events.stream().filter(e -> e instanceof ExternalTestRunEvent).count();
        long stepCount = events.stream().filter(e -> e instanceof ExternalTestStepEvent).count();
        assertEquals(1, runCount);
        assertEquals(3, stepCount);
    }

    @Test
    void stepEventsFollowRunEventWithMatchingRunId() {
        List<Object> events = builder.build(FIXED_TIMESTAMP);
        ExternalTestRunEvent run = (ExternalTestRunEvent) events.get(0);
        List<ExternalTestStepEvent> steps = events.stream()
                .skip(1)
                .map(e -> (ExternalTestStepEvent) e)
                .toList();
        assertFalse(steps.isEmpty());
        for (ExternalTestStepEvent step : steps) {
            assertEquals(run.testRunId(), step.testRunId(),
                    "step.testRunId must match run.testRunId");
            assertEquals("external_test_step", step.eventType());
            assertEquals("EXTERNAL_TEST_EVENT", step.eventKind());
        }
    }

    @Test
    void stepEventsHavePositiveDurationsAndValidTimestamps() {
        List<Object> events = builder.build(FIXED_TIMESTAMP);
        List<ExternalTestStepEvent> steps = events.stream()
                .filter(e -> e instanceof ExternalTestStepEvent)
                .map(e -> (ExternalTestStepEvent) e)
                .toList();
        for (ExternalTestStepEvent step : steps) {
            assertTrue(step.testStepDurationMs() > 0,
                    step.testStepId() + " duration must be > 0");
            assertDoesNotThrow(() -> Instant.parse(step.timestamp()),
                    step.testStepId() + " timestamp must be valid ISO 8601");
        }
    }
}
```
