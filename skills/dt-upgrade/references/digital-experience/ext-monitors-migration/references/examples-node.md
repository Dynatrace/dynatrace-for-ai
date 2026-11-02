# Node.js Migration Examples: Legacy Synthetic API → Grail Events Ingest

Before/after code for every component that changes when migrating the Node.js sample monitor from `POST /api/v1/synthetic/ext/tests` to `POST /platform/ingest/custom/events/external.tests`.

Source: `samples/2ndgen3rdpartymonitors/node/` in the dt-external-tests repo.

---

## 1. Models (`lib/models.js`)

### Before

Eight factory functions that mirror the `SyntheticPayload` schema — one object, nested deeply.

```js
'use strict';

function makeLocationInfo(id, name, ip) {
    return { id, name, ip };
}

function makeLocationRef(id) {
    return { id };
}

function makeTestStep(id, title) {
    return { id, title };
}

function makeStepResult(id, startTimestamp, responseTimeMillis, error) {
    const result = { id, startTimestamp, responseTimeMillis };
    if (error != null) result.error = error;
    return result;
}

function makeLocationResult(id, startTimestamp, success, responseTimeMillis, successRate, stepResults) {
    return { id, startTimestamp, success, responseTimeMillis, successRate, stepResults };
}

function makeTestResult(id, totalStepCount, locationResults) {
    return { id, totalStepCount, locationResults };
}

function makeTestDefinition(id, title, scheduleIntervalInSeconds, enabled, deleted, locationRefs, steps) {
    return { id, title, scheduleIntervalInSeconds, enabled, deleted, locations: locationRefs, steps };
}

function makeSyntheticPayload(engineName, engineIconUrl, messageTimestamp, locations, tests, testResults) {
    return { syntheticEngineName: engineName, syntheticEngineIconUrl: engineIconUrl, messageTimestamp, locations, tests, testResults };
}

module.exports = {
    makeLocationInfo, makeLocationRef, makeTestStep,
    makeStepResult, makeLocationResult, makeTestResult,
    makeTestDefinition, makeSyntheticPayload,
};
```

### After

Two factory functions — one per event type. The entire legacy model set is replaced.

> JavaScript note: dotted field names like `"test.run.id"` cannot be set with dot notation. Use string literal keys or bracket notation: `event['test.run.id'] = value`.

```js
'use strict';

/**
 * Produces one external_test_run event object.
 * @param {{ testId, testRunId, testName, testType, testRunStatus, testRunAvailability,
 *           testRunDurationMs, testRunLocation, timestamp,
 *           testFrequencySec?, runnerName?, testRunErrorCode?, testRunErrorMessage? }} params
 */
function makeExternalTestRunEvent({
    testId, testRunId, testName, testType,
    testRunStatus, testRunAvailability, testRunDurationMs,
    testRunLocation, timestamp,
    testFrequencySec, runnerName, testRunErrorCode, testRunErrorMessage,
}) {
    const event = {
        'event.kind': 'EXTERNAL_TEST_EVENT',
        'event.type': 'external_test_run',
        'test.id': testId,
        'test.run.id': testRunId,
        'test.name': testName,
        'test.type': testType,
        'test.run.status': testRunStatus,
        'test.run.availability': testRunAvailability,
        'test.run.duration_ms': testRunDurationMs,
        'test.run.location': testRunLocation,
        timestamp,
    };
    if (testFrequencySec != null)     event['test.frequency_sec']      = testFrequencySec;
    if (runnerName != null)           event['runner.name']              = runnerName;
    if (testRunErrorCode != null)     event['test.run.error_code']      = testRunErrorCode;
    if (testRunErrorMessage != null)  event['test.run.error_message']   = testRunErrorMessage;
    return event;
}

/**
 * Produces one external_test_step event object.
 * @param {{ testRunId, testId, testStepId, testStepName, testStepIndex,
 *           testStepStatus, testStepDurationMs, timestamp,
 *           testStepErrorCode?, testStepErrorMessage? }} params
 */
function makeExternalTestStepEvent({
    testRunId, testId, testStepId, testStepName, testStepIndex,
    testStepStatus, testStepDurationMs, timestamp,
    testStepErrorCode, testStepErrorMessage,
}) {
    const event = {
        'event.kind': 'EXTERNAL_TEST_EVENT',
        'event.type': 'external_test_step',
        'test.run.id': testRunId,
        'test.id': testId,
        'test.step.id': testStepId,
        'test.step.name': testStepName,
        'test.step.index': testStepIndex,
        'test.step.status': testStepStatus,
        'test.step.duration_ms': testStepDurationMs,
        timestamp,
    };
    if (testStepErrorCode != null)    event['test.step.error_code']    = testStepErrorCode;
    if (testStepErrorMessage != null) event['test.step.error_message'] = testStepErrorMessage;
    return event;
}

module.exports = { makeExternalTestRunEvent, makeExternalTestStepEvent };
```

---

## 2. Config (`lib/config.js`)

### Before

Reads `DT_TENANT_URL` (classic environment domain) and appends the v1 path.

```js
'use strict';

function loadConfig() {
    const tenantUrl = (process.env.DT_TENANT_URL || '').trim();
    const apiToken  = (process.env.DT_API_TOKEN  || '').trim();
    const interval  = parseInt(process.env.INTERVAL || '10', 10);
    const duration  = parseInt(process.env.DURATION || '0',  10);

    if (!tenantUrl) throw new Error('DT_TENANT_URL is required');
    if (!apiToken)  throw new Error('DT_API_TOKEN is required');

    const endpoint = `${tenantUrl}/api/v1/synthetic/ext/tests`;

    return Object.freeze({ tenantUrl, apiToken, interval, duration, endpoint });
}

module.exports = { loadConfig };
```

### After

Reads `DT_ENV_URL` (apps domain — `<env-id>.apps.dynatrace.com` instead of the classic `<env-id>.live.dynatrace.com`) and targets the new ingest path. The token must have `openpipeline.events.custom` scope, not `ExternalSyntheticIntegration`.

```js
'use strict';

function loadConfig() {
    const envUrl   = (process.env.DT_ENV_URL   || '').trim();
    const apiToken = (process.env.DT_API_TOKEN  || '').trim();
    const interval = parseInt(process.env.INTERVAL || '10', 10);
    const duration = parseInt(process.env.DURATION || '0',  10);

    if (!envUrl)   throw new Error('DT_ENV_URL is required');
    if (!apiToken) throw new Error('DT_API_TOKEN is required');

    // Apps domain: e.g. https://abc12345.apps.dynatrace.com  (not the classic .live.dynatrace.com)
    const endpoint = `${envUrl}/platform/ingest/custom/events/external.tests`;

    return Object.freeze({ envUrl, apiToken, interval, duration, endpoint });
}

module.exports = { loadConfig };
```

---

## 3. HTTP Client (`lib/client.js`)

### Before

`post(payload)` serialises a single object. `Content-Length` is derived from that object's JSON string.

```js
'use strict';

const https = require('https');
const http  = require('http');
const { URL } = require('url');

class DynatraceClient {
    constructor(endpoint, token) {
        this._endpoint = endpoint;
        this._token    = token;
    }

    post(payload) {
        return new Promise((resolve, reject) => {
            const parsed = new URL(this._endpoint);
            const body   = JSON.stringify(payload);   // single object

            const options = {
                hostname: parsed.hostname,
                port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
                path: parsed.pathname + (parsed.search || ''),
                method: 'POST',
                headers: {
                    'Authorization':  `Api-Token ${this._token}`,
                    'Content-Type':   'application/json',
                    'Content-Length': Buffer.byteLength(body),
                },
            };

            const lib = parsed.protocol === 'https:' ? https : http;
            const req = lib.request(options, res => {
                let data = '';
                res.on('data', chunk => { data += chunk; });
                res.on('end', () => {
                    console.log(`  -> HTTP ${res.statusCode}  body: ${data.trim() || '(empty)'}`);
                    resolve();
                });
            });

            req.on('error', reject);
            req.setTimeout(10000, () => { req.destroy(new Error('Request timeout')); });
            req.write(body);
            req.end();
        });
    }
}

module.exports = { DynatraceClient };
```

### After

`post(events)` accepts an **array**. The body is `JSON.stringify(events)`. `Content-Length` is recalculated from the array string — the calculation itself is identical, only the input changes. Auth header format is unchanged.

```js
'use strict';

const https = require('https');
const http  = require('http');
const { URL } = require('url');

class DynatraceClient {
    constructor(endpoint, token) {
        this._endpoint = endpoint;
        this._token    = token;
    }

    /**
     * POST an array of event objects to the Grail ingest endpoint.
     * @param {object[]} events
     * @returns {Promise<void>}
     */
    post(events) {
        return new Promise((resolve, reject) => {
            const parsed = new URL(this._endpoint);
            const body   = JSON.stringify(events);    // array — new endpoint rejects bare objects

            const options = {
                hostname: parsed.hostname,
                port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
                path: parsed.pathname + (parsed.search || ''),
                method: 'POST',
                headers: {
                    'Authorization':  `Api-Token ${this._token}`,
                    'Content-Type':   'application/json',
                    'Content-Length': Buffer.byteLength(body),  // recalculated from array body
                },
            };

            const lib = parsed.protocol === 'https:' ? https : http;
            const req = lib.request(options, res => {
                let data = '';
                res.on('data', chunk => { data += chunk; });
                res.on('end', () => {
                    console.log(`  -> HTTP ${res.statusCode}  body: ${data.trim() || '(empty)'}`);
                    resolve();
                });
            });

            req.on('error', reject);
            req.setTimeout(10000, () => { req.destroy(new Error('Request timeout')); });
            req.write(body);
            req.end();
        });
    }
}

module.exports = { DynatraceClient };
```

---

## 4. Builder (`lib/builder.js`)

### Before

`build(nowMs)` returns a single nested `SyntheticPayload` object. Two locations: Singapore always passes, Tokyo always fails. The runner accesses the result as `payload.testResults[0].locationResults`.

```js
'use strict';

const {
    makeLocationInfo, makeLocationRef, makeTestStep, makeStepResult,
    makeLocationResult, makeTestResult, makeTestDefinition, makeSyntheticPayload,
} = require('./models');

const ENGINE_NAME   = 'NodeMultiLocation';
const ENGINE_ICON   = 'https://static.thenounproject.com/png/1745-200.png';
const MONITOR_ID    = 'monitor-3-node-multi-location';
const MONITOR_TITLE = '3rd party test - node multi-location';
const SCHEDULE_INTERVAL_SECONDS = 60;

const LOCATIONS = [
    makeLocationInfo('ap-southeast-1', 'AP Southeast (Singapore)', '192.0.2.100'),
    makeLocationInfo('ap-northeast-1', 'AP Northeast (Tokyo)',     '192.0.2.200'),
];

const STEPS = [
    makeTestStep(1, 'DNS resolution'),
    makeTestStep(2, 'TCP connect'),
    makeTestStep(3, 'HTTP request'),
    makeTestStep(4, 'Content validation'),
];

const BASE_STEP_MS = [45, 80, 320, 60];

const ERROR_SCENARIOS = [
    { code: 502, message: 'Bad gateway — upstream unreachable' },
    { code: 504, message: 'Gateway timeout after 30s' },
    { code: 503, message: 'Service temporarily unavailable' },
    { code: 0,   message: 'DNS resolution failed: NXDOMAIN' },
];

class PayloadBuilder {
    build(nowMs) {
        const locationResults = [
            this._buildSuccessResult(LOCATIONS[0].id, nowMs),
            this._buildFailureResult(LOCATIONS[1].id, nowMs),
        ];

        const locationRefs = LOCATIONS.map(l => makeLocationRef(l.id));
        const testDef = makeTestDefinition(
            MONITOR_ID, MONITOR_TITLE, SCHEDULE_INTERVAL_SECONDS,
            true, false, locationRefs, STEPS
        );
        const testResult = makeTestResult(MONITOR_ID, STEPS.length, locationResults);

        return makeSyntheticPayload(ENGINE_NAME, ENGINE_ICON, nowMs, LOCATIONS, [testDef], [testResult]);
    }

    _jitter(baseMs) {
        return Math.round(baseMs * (0.8 + Math.random() * 0.4));
    }

    _buildSuccessResult(locationId, nowMs) {
        const stepMs = STEPS.map((_, i) => this._jitter(BASE_STEP_MS[i]));
        const totalMs = stepMs.reduce((a, b) => a + b, 0);
        const locationStartMs = nowMs - totalMs;
        let offset = 0;
        const stepResults = STEPS.map((step, i) => {
            const r = makeStepResult(step.id, locationStartMs + offset, stepMs[i], null);
            offset += stepMs[i];
            return r;
        });
        return makeLocationResult(locationId, locationStartMs, true, totalMs, 1.0, stepResults);
    }

    _buildFailureResult(locationId, nowMs) {
        const failingStepIndex = Math.floor(Math.random() * STEPS.length);
        const error = ERROR_SCENARIOS[Math.floor(Math.random() * ERROR_SCENARIOS.length)];

        const stepMs = STEPS.map((_, i) => (i < failingStepIndex ? this._jitter(BASE_STEP_MS[i]) : 0));
        const totalMs = stepMs.reduce((a, b) => a + b, 0);
        const locationStartMs = nowMs - totalMs;
        let offset = 0;
        const stepResults = STEPS.map((step, i) => {
            const err = (i === failingStepIndex) ? { code: error.code, message: error.message } : null;
            const r = makeStepResult(step.id, locationStartMs + offset, stepMs[i], err);
            offset += stepMs[i];
            return r;
        });
        return makeLocationResult(locationId, locationStartMs, false, totalMs, 0.0, stepResults);
    }
}

module.exports = { PayloadBuilder };
```

### After

`build(nowMs)` returns a **flat array** of event objects. One UUID is generated per location (per cycle) and shared between the run event and its step events. Timestamps are ISO 8601 strings. `success` boolean → `"passed"`/`"failed"` + `1`/`0`. Step error codes cast from integer to string.

> `runner.js` also needs a small update: replace `payload.testResults[0].locationResults` with the event-array equivalent shown at the end of this section.

```js
'use strict';

const { randomUUID } = require('crypto');   // Node 14.17+ — no external deps
const { makeExternalTestRunEvent, makeExternalTestStepEvent } = require('./models');

const ENGINE_NAME   = 'NodeMultiLocation';
const MONITOR_ID    = 'monitor-3-node-multi-location';
const MONITOR_TITLE = '3rd party test - node multi-location';
const MONITOR_TYPE  = 'http';               // set to match the actual test type
const SCHEDULE_INTERVAL_SECONDS = 60;

// ip and name fields have no equivalent in new schema — drop them
const LOCATIONS = [
    { id: 'ap-southeast-1' },
    { id: 'ap-northeast-1' },
];

const STEPS = [
    { id: 1, title: 'DNS resolution' },
    { id: 2, title: 'TCP connect' },
    { id: 3, title: 'HTTP request' },
    { id: 4, title: 'Content validation' },
];

const BASE_STEP_MS = [45, 80, 320, 60];

const ERROR_SCENARIOS = [
    { code: 502, message: 'Bad gateway — upstream unreachable' },
    { code: 504, message: 'Gateway timeout after 30s' },
    { code: 503, message: 'Service temporarily unavailable' },
    { code: 0,   message: 'DNS resolution failed: NXDOMAIN' },
];

// Slugify step titles for test.step.name: "TCP connect" → "tcp-connect"
function slugify(title) {
    return title.toLowerCase().replace(/\s+/g, '-');
}

// Pad step id for test.step.id: 1 → "step-001"
function stepId(id) {
    return `step-${String(id).padStart(3, '0')}`;
}

class PayloadBuilder {
    /**
     * @param {number} nowMs  Current epoch ms
     * @returns {object[]}    Flat array of external_test_run and external_test_step events
     */
    build(nowMs) {
        return [
            ...this._buildSuccessEvents(LOCATIONS[0].id, nowMs),
            ...this._buildFailureEvents(LOCATIONS[1].id, nowMs),
        ];
    }

    _jitter(baseMs) {
        return Math.round(baseMs * (0.8 + Math.random() * 0.4));
    }

    _buildSuccessEvents(locationId, nowMs) {
        const runId   = randomUUID();                           // one UUID per (test, location) pair
        const stepMs  = STEPS.map((_, i) => this._jitter(BASE_STEP_MS[i]));
        const totalMs = stepMs.reduce((a, b) => a + b, 0);
        const startMs = nowMs - totalMs;

        const runEvent = makeExternalTestRunEvent({
            testId:              MONITOR_ID,
            testRunId:           runId,
            testName:            MONITOR_TITLE,
            testType:            MONITOR_TYPE,
            testRunStatus:       'passed',
            testRunAvailability: 1,
            testRunDurationMs:   totalMs,
            testRunLocation:     locationId,
            timestamp:           new Date(startMs).toISOString(),   // epoch ms → ISO 8601
            testFrequencySec:    SCHEDULE_INTERVAL_SECONDS,
            runnerName:          ENGINE_NAME,
        });

        let offset = 0;
        const stepEvents = STEPS.map((step, i) => {
            const ev = makeExternalTestStepEvent({
                testRunId:        runId,
                testId:           MONITOR_ID,
                testStepId:       stepId(step.id),
                testStepName:     slugify(step.title),
                testStepIndex:    step.id,
                testStepStatus:   'passed',
                testStepDurationMs: stepMs[i],
                timestamp:        new Date(startMs + offset).toISOString(),
            });
            offset += stepMs[i];
            return ev;
        });

        return [runEvent, ...stepEvents];
    }

    _buildFailureEvents(locationId, nowMs) {
        const runId            = randomUUID();
        const failingStepIndex = Math.floor(Math.random() * STEPS.length);
        const error            = ERROR_SCENARIOS[Math.floor(Math.random() * ERROR_SCENARIOS.length)];

        const stepMs  = STEPS.map((_, i) => (i < failingStepIndex ? this._jitter(BASE_STEP_MS[i]) : 0));
        const totalMs = stepMs.reduce((a, b) => a + b, 0);
        const startMs = nowMs - totalMs;

        const runEvent = makeExternalTestRunEvent({
            testId:              MONITOR_ID,
            testRunId:           runId,
            testName:            MONITOR_TITLE,
            testType:            MONITOR_TYPE,
            testRunStatus:       'failed',
            testRunAvailability: 0,
            testRunDurationMs:   totalMs,
            testRunLocation:     locationId,
            timestamp:           new Date(startMs).toISOString(),
            testFrequencySec:    SCHEDULE_INTERVAL_SECONDS,
            runnerName:          ENGINE_NAME,
        });

        let offset = 0;
        const stepEvents = STEPS.map((step, i) => {
            const isFailing = i === failingStepIndex;
            const ev = makeExternalTestStepEvent({
                testRunId:          runId,
                testId:             MONITOR_ID,
                testStepId:         stepId(step.id),
                testStepName:       slugify(step.title),
                testStepIndex:      step.id,
                testStepStatus:     isFailing ? 'failed' : 'passed',
                testStepDurationMs: stepMs[i],
                timestamp:          new Date(startMs + offset).toISOString(),
                // error.code is integer — cast to string for test.step.error_code
                testStepErrorCode:    isFailing ? String(error.code) : undefined,
                testStepErrorMessage: isFailing ? error.message      : undefined,
            });
            offset += stepMs[i];
            return ev;
        });

        return [runEvent, ...stepEvents];
    }
}

module.exports = { PayloadBuilder };
```

**Runner update (`lib/runner.js`)** — the build result shape changed, so the logging line must change:

```js
// Before
const payload = this._builder.build(nowMs);
const results = payload.testResults[0].locationResults;
const outcomes = results.map(r => `${r.id}: ${r.success ? 'pass' : 'fail'}`).join(', ');
await this._client.post(payload);

// After
const events   = this._builder.build(nowMs);
const runEvents = events.filter(e => e['event.type'] === 'external_test_run');
const outcomes  = runEvents.map(e => `${e['test.run.location']}: ${e['test.run.status']}`).join(', ');
await this._client.post(events);
```

---

## 5. Tests

### Before (`test/builder.test.js`)

Tests assert the nested `SyntheticPayload` structure.

```js
'use strict';

const { PayloadBuilder } = require('../lib/builder');

describe('PayloadBuilder', () => {
    let builder;

    beforeEach(() => { builder = new PayloadBuilder(); });

    test('build returns object with required top-level keys', () => {
        const payload = builder.build(Date.now());
        expect(payload).toHaveProperty('syntheticEngineName');
        expect(payload).toHaveProperty('syntheticEngineIconUrl');
        expect(payload).toHaveProperty('messageTimestamp');
        expect(payload).toHaveProperty('locations');
        expect(payload).toHaveProperty('tests');
        expect(payload).toHaveProperty('testResults');
    });

    test('build has two locations', () => {
        const payload = builder.build(Date.now());
        expect(payload.locations.length).toBe(2);
    });

    test('build has two locationResults', () => {
        const payload = builder.build(Date.now());
        expect(payload.testResults[0].locationResults.length).toBe(2);
    });

    test('first location result is always success', () => {
        for (let i = 0; i < 20; i++) {
            const payload = builder.build(Date.now());
            expect(payload.testResults[0].locationResults[0].success).toBe(true);
        }
    });

    test('second location result is always failure', () => {
        for (let i = 0; i < 20; i++) {
            const payload = builder.build(Date.now());
            expect(payload.testResults[0].locationResults[1].success).toBe(false);
        }
    });

    test('failure result has at least one step with error', () => {
        const payload = builder.build(Date.now());
        const failureResult = payload.testResults[0].locationResults[1];
        const hasError = failureResult.stepResults.some(s => s.hasOwnProperty('error'));
        expect(hasError).toBe(true);
    });

    test('success result has no step errors', () => {
        const payload = builder.build(Date.now());
        const successResult = payload.testResults[0].locationResults[0];
        const hasError = successResult.stepResults.some(s => s.hasOwnProperty('error'));
        expect(hasError).toBe(false);
    });
});
```

### After (`test/builder.test.js`)

Tests assert a flat event array with dotted-key fields.

```js
'use strict';

const { PayloadBuilder } = require('../lib/builder');

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const ISO_PATTERN  = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;

describe('PayloadBuilder', () => {
    let builder;

    beforeEach(() => { builder = new PayloadBuilder(); });

    test('build returns an array', () => {
        const events = builder.build(Date.now());
        expect(Array.isArray(events)).toBe(true);
        expect(events.length).toBeGreaterThan(0);
    });

    test('two run events exist — one per location', () => {
        const events = builder.build(Date.now());
        const runEvents = events.filter(e => e['event.type'] === 'external_test_run');
        expect(runEvents).toHaveLength(2);
    });

    test('run events have event.kind EXTERNAL_TEST_EVENT', () => {
        const events = builder.build(Date.now());
        for (const e of events) {
            expect(e['event.kind']).toBe('EXTERNAL_TEST_EVENT');
        }
    });

    test('test.run.id matches UUID v4 pattern', () => {
        const events = builder.build(Date.now());
        const runEvents = events.filter(e => e['event.type'] === 'external_test_run');
        for (const e of runEvents) {
            expect(e['test.run.id']).toMatch(UUID_PATTERN);
        }
    });

    test('timestamp matches ISO 8601 UTC pattern', () => {
        const events = builder.build(Date.now());
        for (const e of events) {
            expect(e.timestamp).toMatch(ISO_PATTERN);
        }
    });

    test('first location always passes, second always fails', () => {
        for (let i = 0; i < 20; i++) {
            const events = builder.build(Date.now());
            const runEvents = events.filter(e => e['event.type'] === 'external_test_run');
            expect(runEvents[0]['test.run.status']).toBe('passed');
            expect(runEvents[1]['test.run.status']).toBe('failed');
        }
    });

    test('test.run.availability is 1 for passed, 0 for failed', () => {
        const events = builder.build(Date.now());
        const runEvents = events.filter(e => e['event.type'] === 'external_test_run');
        expect(runEvents[0]['test.run.availability']).toBe(1);
        expect(runEvents[1]['test.run.availability']).toBe(0);
    });

    test('step events share test.run.id with their parent run event', () => {
        const events    = builder.build(Date.now());
        const runIds    = new Set(events.filter(e => e['event.type'] === 'external_test_run').map(e => e['test.run.id']));
        const stepEvents = events.filter(e => e['event.type'] === 'external_test_step');
        for (const step of stepEvents) {
            expect(runIds.has(step['test.run.id'])).toBe(true);
        }
    });

    test('the two run events have different test.run.id values', () => {
        const events    = builder.build(Date.now());
        const runEvents = events.filter(e => e['event.type'] === 'external_test_run');
        expect(runEvents[0]['test.run.id']).not.toBe(runEvents[1]['test.run.id']);
    });

    test('failure location has at least one failed step event', () => {
        const events    = builder.build(Date.now());
        const runEvents = events.filter(e => e['event.type'] === 'external_test_run');
        const failedRunId = runEvents.find(e => e['test.run.status'] === 'failed')['test.run.id'];
        const failedSteps = events.filter(
            e => e['event.type'] === 'external_test_step'
              && e['test.run.id'] === failedRunId
              && e['test.step.status'] === 'failed'
        );
        expect(failedSteps.length).toBeGreaterThanOrEqual(1);
    });

    test('failed step event has string error code', () => {
        const events     = builder.build(Date.now());
        const runEvents  = events.filter(e => e['event.type'] === 'external_test_run');
        const failedRunId = runEvents.find(e => e['test.run.status'] === 'failed')['test.run.id'];
        const failedStep = events.find(
            e => e['event.type'] === 'external_test_step'
              && e['test.run.id'] === failedRunId
              && e['test.step.status'] === 'failed'
        );
        expect(typeof failedStep['test.step.error_code']).toBe('string');
        expect(failedStep['test.step.error_message']).toBeTruthy();
    });

    test('success location has no failed step events', () => {
        const events    = builder.build(Date.now());
        const runEvents = events.filter(e => e['event.type'] === 'external_test_run');
        const passedRunId = runEvents.find(e => e['test.run.status'] === 'passed')['test.run.id'];
        const failedSteps = events.filter(
            e => e['event.type'] === 'external_test_step'
              && e['test.run.id'] === passedRunId
              && e['test.step.status'] === 'failed'
        );
        expect(failedSteps).toHaveLength(0);
    });
});
```

### Before (`test/client.test.js`)

Endpoint assertions target the classic domain and v1 path.

```js
test('post sends to correct endpoint', async () => {
    const client = new DynatraceClient(
        'https://abc12345.live.dynatrace.com/api/v1/synthetic/ext/tests',
        'token-xyz'
    );
    await client.post({});
    expect(capturedOptions.hostname).toBe('abc12345.live.dynatrace.com');
    expect(capturedOptions.path).toBe('/api/v1/synthetic/ext/tests');
});
```

### After (`test/client.test.js`)

Endpoint assertions target the apps domain and new ingest path. `post()` receives an array.

```js
test('post sends to correct endpoint', async () => {
    const client = new DynatraceClient(
        'https://abc12345.live.dynatrace.com/platform/ingest/custom/events/external.tests',
        'token-xyz'
    );
    await client.post([]);                               // array, not object
    expect(capturedOptions.hostname).toBe('abc12345.live.dynatrace.com');
    expect(capturedOptions.path).toBe('/platform/ingest/custom/events/external.tests');
});

test('post sets Authorization header', async () => {
    const client = new DynatraceClient(
        'https://abc12345.live.dynatrace.com/platform/ingest/custom/events/external.tests',
        'token-xyz'
    );
    await client.post([]);
    expect(capturedOptions.headers['Authorization']).toMatch(/^Api-Token /);
});

test('post sets Content-Type header', async () => {
    const client = new DynatraceClient(
        'https://abc12345.live.dynatrace.com/platform/ingest/custom/events/external.tests',
        'token-xyz'
    );
    await client.post([]);
    expect(capturedOptions.headers['Content-Type']).toBe('application/json');
});

test('post resolves on successful response', async () => {
    const client = new DynatraceClient(
        'https://abc12345.live.dynatrace.com/platform/ingest/custom/events/external.tests',
        'token-xyz'
    );
    await expect(client.post([])).resolves.toBeUndefined();
});
```
