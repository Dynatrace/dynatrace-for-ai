# Python Migration Examples

Before/after code for each component in the legacy Python sample monitor (`samples/2ndgen3rdpartymonitors/python`). Read `schema-mapping.md` first for the conceptual shifts these examples implement.

---

## 1. Models

### Before — `monitor/models.py`

```python
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class StepDefinition:
    id: int
    title: str

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title}


@dataclass
class StepError:
    code: int
    message: str

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


@dataclass
class StepResult:
    id: int
    start_timestamp: int
    response_time_millis: int
    error: Optional[StepError] = field(default=None)

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "startTimestamp": self.start_timestamp,
            "responseTimeMillis": self.response_time_millis,
        }
        if self.error is not None:
            d["error"] = self.error.to_dict()
        return d


@dataclass
class LocationDefinition:
    id: str

    def to_dict(self) -> dict:
        return {"id": self.id}


@dataclass
class LocationInfo:
    id: str
    name: str
    ip: str

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "ip": self.ip}


@dataclass
class LocationResult:
    id: str
    start_timestamp: int
    success: bool
    response_time_millis: int
    success_rate: float
    step_results: List[StepResult]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "startTimestamp": self.start_timestamp,
            "success": self.success,
            "responseTimeMillis": self.response_time_millis,
            "successRate": self.success_rate,
            "stepResults": [sr.to_dict() for sr in self.step_results],
        }


@dataclass
class TestResult:
    id: str
    total_step_count: int
    location_results: List[LocationResult]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "totalStepCount": self.total_step_count,
            "locationResults": [lr.to_dict() for lr in self.location_results],
        }


@dataclass
class TestDefinition:
    id: str
    title: str
    schedule_interval_in_seconds: int
    enabled: bool
    deleted: bool
    locations: List[LocationDefinition]
    steps: List[StepDefinition]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "scheduleIntervalInSeconds": self.schedule_interval_in_seconds,
            "enabled": self.enabled,
            "deleted": self.deleted,
            "locations": [loc.to_dict() for loc in self.locations],
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass
class SyntheticPayload:
    synthetic_engine_name: str
    synthetic_engine_icon_url: str
    message_timestamp: int
    locations: List[LocationInfo]
    tests: List[TestDefinition]
    test_results: List[TestResult]

    def to_dict(self) -> dict:
        return {
            "syntheticEngineName": self.synthetic_engine_name,
            "syntheticEngineIconUrl": self.synthetic_engine_icon_url,
            "messageTimestamp": self.message_timestamp,
            "locations": [loc.to_dict() for loc in self.locations],
            "tests": [t.to_dict() for t in self.tests],
            "testResults": [tr.to_dict() for tr in self.test_results],
        }
```

### After — `monitor/models.py`

`LocationResult`, `TestResult`, `TestDefinition`, `LocationDefinition`, `LocationInfo`, and `SyntheticPayload` are removed. `StepDefinition` and `StepError` are kept unchanged — the builder still uses them as internal data holders. Replace everything else with the two event dataclasses below.

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class StepDefinition:
    id: int
    title: str


@dataclass
class StepError:
    code: int
    message: str


@dataclass
class ExternalTestRunEvent:
    # required
    test_id: str            # → "test.id"
    test_run_id: str        # → "test.run.id"  (UUID v4, one per location per cycle)
    test_name: str          # → "test.name"
    test_type: str          # → "test.type"  ("api", "browser", "http", "mobile")
    test_run_status: str    # → "test.run.status"  ("passed" or "failed")
    test_run_availability: int   # → "test.run.availability"  (1 or 0)
    test_run_duration_ms: int    # → "test.run.duration_ms"
    test_run_location: str       # → "test.run.location"
    timestamp: str               # → "timestamp"  (ISO 8601 UTC, e.g. "2024-11-14T12:13:19Z")
    # optional
    test_frequency_sec: int | None = None
    runner_name: str | None = None
    test_run_error_code: str | None = None
    test_run_error_message: str | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "event.kind": "EXTERNAL_TEST_EVENT",
            "event.type": "external_test_run",
            "test.id": self.test_id,
            "test.run.id": self.test_run_id,
            "test.name": self.test_name,
            "test.type": self.test_type,
            "test.run.status": self.test_run_status,
            "test.run.availability": self.test_run_availability,
            "test.run.duration_ms": self.test_run_duration_ms,
            "test.run.location": self.test_run_location,
            "timestamp": self.timestamp,
        }
        if self.test_frequency_sec is not None:
            d["test.frequency_sec"] = self.test_frequency_sec
        if self.runner_name is not None:
            d["runner.name"] = self.runner_name
        if self.test_run_error_code is not None:
            d["test.run.error_code"] = self.test_run_error_code
        if self.test_run_error_message is not None:
            d["test.run.error_message"] = self.test_run_error_message
        return d


@dataclass
class ExternalTestStepEvent:
    # required
    test_run_id: str         # → "test.run.id"  (same UUID as the parent run event)
    test_id: str             # → "test.id"
    test_step_id: str        # → "test.step.id"  (e.g. "step-001")
    test_step_name: str      # → "test.step.name"  (slugified step title)
    test_step_index: int     # → "test.step.index"
    test_step_status: str    # → "test.step.status"  ("passed" or "failed")
    test_step_duration_ms: int   # → "test.step.duration_ms"
    timestamp: str               # → "timestamp"  (ISO 8601 UTC from stepResult.startTimestamp)
    # optional
    test_step_error_code: str | None = None      # → "test.step.error_code"  (error.code as string)
    test_step_error_message: str | None = None   # → "test.step.error_message"

    def to_dict(self) -> dict:
        d: dict = {
            "event.kind": "EXTERNAL_TEST_EVENT",
            "event.type": "external_test_step",
            "test.run.id": self.test_run_id,
            "test.id": self.test_id,
            "test.step.id": self.test_step_id,
            "test.step.name": self.test_step_name,
            "test.step.index": self.test_step_index,
            "test.step.status": self.test_step_status,
            "test.step.duration_ms": self.test_step_duration_ms,
            "timestamp": self.timestamp,
        }
        if self.test_step_error_code is not None:
            d["test.step.error_code"] = self.test_step_error_code
        if self.test_step_error_message is not None:
            d["test.step.error_message"] = self.test_step_error_message
        return d
```

---

## 2. Config

### Before — `monitor/config.py`

```python
@classmethod
def from_env(cls) -> "MonitorConfig":
    tenant_url = os.environ.get("DT_TENANT_URL", "").strip()
    # ...
    endpoint = f"{tenant_url}/api/v1/synthetic/ext/tests"

    return cls(
        tenant_url=tenant_url,
        # ...
        endpoint=endpoint,
    )
```

### After — `monitor/config.py`

The field is renamed `tenant_url` → `env_url` and the env var `DT_TENANT_URL` → `DT_ENV_URL` because the new endpoint requires the **apps domain**, not the classic environment domain (e.g. `abc12345.apps.dynatrace.com`, not `abc12345.live.dynatrace.com`). The subdomain prefix is the same; only the suffix changes — verify the correct apps domain with the customer.

```python
import os
from dataclasses import dataclass


@dataclass
class MonitorConfig:
    env_url: str    # apps domain, e.g. https://abc12345.live.dynatrace.com
    api_token: str
    interval: int
    duration: int
    endpoint: str   # derived: env_url + "/platform/ingest/custom/events/external.tests"

    @classmethod
    def from_env(cls) -> "MonitorConfig":
        env_url = os.environ.get("DT_ENV_URL", "").strip()
        api_token = os.environ.get("DT_API_TOKEN", "").strip()
        interval = int(os.environ.get("INTERVAL", "10") or "10")
        duration = int(os.environ.get("DURATION", "0") or "0")

        if not env_url:
            raise ValueError("DT_ENV_URL environment variable is required but not set")
        if not api_token:
            raise ValueError("DT_API_TOKEN environment variable is required but not set")

        endpoint = f"{env_url}/platform/ingest/custom/events/external.tests"

        return cls(
            env_url=env_url,
            api_token=api_token,
            interval=interval,
            duration=duration,
            endpoint=endpoint,
        )
```

---

## 3. HTTP Client

### Before — `monitor/client.py`

```python
from monitor.models import SyntheticPayload


class DynatraceClient:
    def __init__(self, config: MonitorConfig) -> None:
        self._config = config

    def post(self, payload: SyntheticPayload) -> None:
        resp = requests.post(
            self._config.endpoint,
            headers={
                "Authorization": f"Api-Token {self._config.api_token}",
                "Content-Type": "application/json",
            },
            json=payload.to_dict(),  # single object
            timeout=10,
        )
        body = resp.text.strip() or "(empty)"
        logger.info("HTTP %d  body: %s", resp.status_code, body)
```

### After — `monitor/client.py`

`SyntheticPayload` import is removed. The method now accepts the already-serialized list of event dicts and passes it directly as the JSON body.

```python
import logging

import requests

from monitor.config import MonitorConfig

logger = logging.getLogger(__name__)


class DynatraceClient:
    def __init__(self, config: MonitorConfig) -> None:
        self._config = config

    def post(self, events: list[dict]) -> None:  # list, not SyntheticPayload
        resp = requests.post(
            self._config.endpoint,
            headers={
                "Authorization": f"Api-Token {self._config.api_token}",
                "Content-Type": "application/json",
            },
            json=events,  # array; new endpoint rejects bare objects
            timeout=10,
        )
        body = resp.text.strip() or "(empty)"
        logger.info("HTTP %d  body: %s", resp.status_code, body)
```

---

## 4. Builder

### Before — `monitor/builder.py`

```python
import random
from abc import ABC, abstractmethod
from typing import List

from monitor.models import (
    LocationDefinition, LocationInfo, LocationResult,
    StepDefinition, StepError, StepResult,
    SyntheticPayload, TestDefinition, TestResult,
)


class PayloadBuilder(ABC):
    @abstractmethod
    def build(self, now_ms: int) -> SyntheticPayload:
        ...


class CyclicPayloadBuilder(PayloadBuilder):
    ENGINE_NAME = "PythonFailureDemo"
    ENGINE_ICON_URL = "https://static.thenounproject.com/png/1745-200.png"
    MONITOR_ID = "monitor-2-python-failure"
    MONITOR_TITLE = "3rd party test - python failure demo"
    LOCATION_ID = "eu-west-1"
    LOCATION_NAME = "EU West (Ireland)"
    LOCATION_IP = "198.51.100.42"
    SCHEDULE_INTERVAL_SECONDS = 60
    PHASE_SECONDS = 300
    STEPS: List[StepDefinition] = [
        StepDefinition(1, "Authenticate user"),
        StepDefinition(2, "Fetch dashboard data"),
        StepDefinition(3, "Render report"),
    ]
    BASE_STEP_MS: List[int] = [250, 600, 380]
    ERROR_SCENARIOS: List[StepError] = [
        StepError(401, "Authentication token expired"),
        StepError(503, "Upstream service unavailable"),
        StepError(500, "Internal server error during data fetch"),
        StepError(408, "Request timed out after 30s"),
    ]

    def _is_failure_phase(self, now_ms: int) -> bool:
        return (now_ms // 1000) % (2 * self.PHASE_SECONDS) < self.PHASE_SECONDS

    def build(self, now_ms: int) -> SyntheticPayload:
        if self._is_failure_phase(now_ms):
            failing_step_ids = set(
                random.sample([s.id for s in self.STEPS], k=random.randint(1, 2))
            )
        else:
            failing_step_ids = set()

        step_ms = [
            0 if step.id in failing_step_ids else self._jitter(self.BASE_STEP_MS[step.id - 1])
            for step in self.STEPS
        ]
        total_ms = sum(step_ms)
        location_start_ms = now_ms - total_ms

        step_results: List[StepResult] = []
        offset = 0
        for i, step in enumerate(self.STEPS):
            start_ts = location_start_ms + offset
            if step.id in failing_step_ids:
                error = random.choice(self.ERROR_SCENARIOS)
                step_results.append(
                    StepResult(id=step.id, start_timestamp=start_ts,
                               response_time_millis=0, error=error)
                )
            else:
                step_results.append(
                    StepResult(id=step.id, start_timestamp=start_ts,
                               response_time_millis=step_ms[i])
                )
            offset += step_ms[i]

        overall_success = len(failing_step_ids) == 0

        location_result = LocationResult(
            id=self.LOCATION_ID,
            start_timestamp=location_start_ms,
            success=overall_success,
            response_time_millis=total_ms,
            success_rate=0.0 if not overall_success else 1.0,
            step_results=step_results,
        )
        test_result = TestResult(
            id=self.MONITOR_ID,
            total_step_count=len(self.STEPS),
            location_results=[location_result],
        )
        test_definition = TestDefinition(
            id=self.MONITOR_ID, title=self.MONITOR_TITLE,
            schedule_interval_in_seconds=self.SCHEDULE_INTERVAL_SECONDS,
            enabled=True, deleted=False,
            locations=[LocationDefinition(self.LOCATION_ID)],
            steps=self.STEPS,
        )
        location_info = LocationInfo(
            id=self.LOCATION_ID, name=self.LOCATION_NAME, ip=self.LOCATION_IP,
        )
        return SyntheticPayload(
            synthetic_engine_name=self.ENGINE_NAME,
            synthetic_engine_icon_url=self.ENGINE_ICON_URL,
            message_timestamp=now_ms,
            locations=[location_info],
            tests=[test_definition],
            test_results=[test_result],
        )

    def _jitter(self, base_ms: int) -> int:
        return int(base_ms * (0.8 + random.random() * 0.4))
```

### After — `monitor/builder.py`

Key changes:
- `build()` return type is `list[dict]` instead of `SyntheticPayload`
- Generate a UUID per (test, location) pair per cycle; share it across the run event and all its step events
- Convert epoch ms timestamps to ISO 8601 UTC strings
- Map `success: bool` to `"passed"`/`"failed"` and `1`/`0`
- Slugify step titles for `test.step.name`
- Cast `StepError.code` (int) to string for `test.step.error_code`
- All the `LocationResult`, `TestResult`, `TestDefinition`, `LocationDefinition`, `LocationInfo`, `SyntheticPayload` intermediates are gone

```python
import random
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List

from monitor.models import (
    ExternalTestRunEvent,
    ExternalTestStepEvent,
    StepDefinition,
    StepError,
)


def _ms_to_iso(epoch_ms: int) -> str:
    """Convert epoch milliseconds to ISO 8601 UTC string."""
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _slugify(title: str) -> str:
    """Lower-case and hyphenate a step title for test.step.name."""
    return title.lower().replace(" ", "-")


class PayloadBuilder(ABC):
    @abstractmethod
    def build(self, now_ms: int) -> list[dict]:
        ...


class CyclicPayloadBuilder(PayloadBuilder):
    ENGINE_NAME = "PythonFailureDemo"
    MONITOR_ID = "monitor-2-python-failure"
    MONITOR_TITLE = "3rd party test - python failure demo"
    LOCATION_ID = "eu-west-1"
    SCHEDULE_INTERVAL_SECONDS = 60
    PHASE_SECONDS = 300
    STEPS: List[StepDefinition] = [
        StepDefinition(1, "Authenticate user"),
        StepDefinition(2, "Fetch dashboard data"),
        StepDefinition(3, "Render report"),
    ]
    BASE_STEP_MS: List[int] = [250, 600, 380]
    ERROR_SCENARIOS: List[StepError] = [
        StepError(401, "Authentication token expired"),
        StepError(503, "Upstream service unavailable"),
        StepError(500, "Internal server error during data fetch"),
        StepError(408, "Request timed out after 30s"),
    ]

    def _is_failure_phase(self, now_ms: int) -> bool:
        return (now_ms // 1000) % (2 * self.PHASE_SECONDS) < self.PHASE_SECONDS

    def build(self, now_ms: int) -> list[dict]:
        if self._is_failure_phase(now_ms):
            failing_step_ids = set(
                random.sample([s.id for s in self.STEPS], k=random.randint(1, 2))
            )
        else:
            failing_step_ids = set()

        step_ms = [
            0 if step.id in failing_step_ids else self._jitter(self.BASE_STEP_MS[step.id - 1])
            for step in self.STEPS
        ]
        total_ms = sum(step_ms)
        location_start_ms = now_ms - total_ms
        overall_success = len(failing_step_ids) == 0

        # One UUID per (test, location) pair; shared across run event and all step events.
        run_id = str(uuid.uuid4())
        events: list[dict] = []

        run_event = ExternalTestRunEvent(
            test_id=self.MONITOR_ID,
            test_run_id=run_id,
            test_name=self.MONITOR_TITLE,
            test_type="api",
            test_run_status="passed" if overall_success else "failed",
            test_run_availability=1 if overall_success else 0,
            test_run_duration_ms=total_ms,
            test_run_location=self.LOCATION_ID,
            timestamp=_ms_to_iso(location_start_ms),  # from locationResult.startTimestamp
            test_frequency_sec=self.SCHEDULE_INTERVAL_SECONDS,
            runner_name=self.ENGINE_NAME,
        )
        events.append(run_event.to_dict())

        offset = 0
        for i, step in enumerate(self.STEPS):
            step_start_ms = location_start_ms + offset
            if step.id in failing_step_ids:
                error = random.choice(self.ERROR_SCENARIOS)
                step_event = ExternalTestStepEvent(
                    test_run_id=run_id,
                    test_id=self.MONITOR_ID,
                    test_step_id=f"step-{step.id:03d}",
                    test_step_name=_slugify(step.title),
                    test_step_index=step.id,
                    test_step_status="failed",
                    test_step_duration_ms=0,
                    timestamp=_ms_to_iso(step_start_ms),
                    test_step_error_code=str(error.code),   # int → string
                    test_step_error_message=error.message,
                )
            else:
                step_event = ExternalTestStepEvent(
                    test_run_id=run_id,
                    test_id=self.MONITOR_ID,
                    test_step_id=f"step-{step.id:03d}",
                    test_step_name=_slugify(step.title),
                    test_step_index=step.id,
                    test_step_status="passed",
                    test_step_duration_ms=step_ms[i],
                    timestamp=_ms_to_iso(step_start_ms),
                )
            events.append(step_event.to_dict())
            offset += step_ms[i]

        return events

    def _jitter(self, base_ms: int) -> int:
        return int(base_ms * (0.8 + random.random() * 0.4))
```

---

## 5. Tests

### Before — `tests/test_builder.py`

```python
from monitor.builder import CyclicPayloadBuilder
from monitor.models import SyntheticPayload

FAIL_PHASE_MS = 0
PASS_PHASE_MS = 300_000


def test_build_returns_synthetic_payload():
    builder = CyclicPayloadBuilder()
    payload = builder.build(FAIL_PHASE_MS)
    assert isinstance(payload, SyntheticPayload)


def test_build_has_single_location():
    builder = CyclicPayloadBuilder()
    payload = builder.build(FAIL_PHASE_MS)
    assert len(payload.locations) == 1


def test_build_has_failing_steps_in_failure_phase():
    builder = CyclicPayloadBuilder()
    found_failure = False
    for i in range(20):
        payload = builder.build(FAIL_PHASE_MS + i * 1000)
        location_result = payload.test_results[0].location_results[0]
        if any(sr.error is not None for sr in location_result.step_results):
            found_failure = True
            break
    assert found_failure, "Expected at least one run with a failing step in failure phase"


def test_build_failure_phase_has_1_or_2_failures():
    builder = CyclicPayloadBuilder()
    for i in range(50):
        payload = builder.build(FAIL_PHASE_MS + i * 1000)
        location_result = payload.test_results[0].location_results[0]

        assert not location_result.success, f"Run {i}: expected success=False in failure phase"

        failing_count = sum(1 for sr in location_result.step_results if sr.error is not None)
        assert 1 <= failing_count <= 2, f"Run {i}: expected 1-2 failing steps, got {failing_count}"


def test_build_pass_phase_has_no_failures():
    builder = CyclicPayloadBuilder()
    for i in range(20):
        payload = builder.build(PASS_PHASE_MS + i * 1000)
        location_result = payload.test_results[0].location_results[0]

        assert location_result.success, f"Run {i}: expected success=True in pass phase"
        assert all(sr.error is None for sr in location_result.step_results), \
            f"Run {i}: expected no errors in pass phase"


def test_build_timestamp_propagated():
    builder = CyclicPayloadBuilder()
    now_ms = 1700000000000
    payload = builder.build(now_ms)
    assert payload.message_timestamp == now_ms
```

### After — `tests/test_builder.py`

```python
import re
import uuid

from monitor.builder import CyclicPayloadBuilder

FAIL_PHASE_MS = 0
PASS_PHASE_MS = 300_000

ISO8601_RE = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')


def test_build_returns_list_of_dicts():
    builder = CyclicPayloadBuilder()
    events = builder.build(FAIL_PHASE_MS)
    assert isinstance(events, list)
    assert len(events) > 0


def test_build_first_event_is_run_event():
    builder = CyclicPayloadBuilder()
    events = builder.build(FAIL_PHASE_MS)
    assert events[0]["event.type"] == "external_test_run"


def test_build_run_event_has_valid_uuid():
    builder = CyclicPayloadBuilder()
    events = builder.build(FAIL_PHASE_MS)
    run_id = events[0]["test.run.id"]
    # Raises ValueError if not a valid UUID
    uuid.UUID(run_id, version=4)


def test_build_run_event_has_valid_status():
    builder = CyclicPayloadBuilder()
    for i in range(20):
        events = builder.build(FAIL_PHASE_MS + i * 1000)
        run_event = events[0]
        assert run_event["test.run.status"] in ("passed", "failed")
        assert run_event["test.run.availability"] in (0, 1)


def test_build_run_event_timestamp_is_iso8601():
    builder = CyclicPayloadBuilder()
    events = builder.build(FAIL_PHASE_MS)
    assert ISO8601_RE.match(events[0]["timestamp"]), \
        f"timestamp not ISO 8601: {events[0]['timestamp']}"


def test_build_step_events_share_run_id():
    builder = CyclicPayloadBuilder()
    events = builder.build(PASS_PHASE_MS)
    run_id = events[0]["test.run.id"]
    step_events = [e for e in events if e["event.type"] == "external_test_step"]
    assert all(e["test.run.id"] == run_id for e in step_events), \
        "All step events must share the run event's test.run.id"


def test_build_failure_phase_has_failed_step_event():
    builder = CyclicPayloadBuilder()
    found_failed_step = False
    for i in range(20):
        events = builder.build(FAIL_PHASE_MS + i * 1000)
        step_events = [e for e in events if e["event.type"] == "external_test_step"]
        if any(e["test.step.status"] == "failed" for e in step_events):
            found_failed_step = True
            break
    assert found_failed_step, "Expected at least one failed step event in failure phase"


def test_build_failure_phase_has_1_or_2_failed_steps():
    builder = CyclicPayloadBuilder()
    for i in range(50):
        events = builder.build(FAIL_PHASE_MS + i * 1000)
        run_event = events[0]
        assert run_event["test.run.status"] == "failed", \
            f"Run {i}: expected test.run.status=failed in failure phase"

        step_events = [e for e in events if e["event.type"] == "external_test_step"]
        failed_count = sum(1 for e in step_events if e["test.step.status"] == "failed")
        assert 1 <= failed_count <= 2, \
            f"Run {i}: expected 1-2 failed step events, got {failed_count}"


def test_build_failure_phase_failed_step_has_error_fields():
    builder = CyclicPayloadBuilder()
    for i in range(20):
        events = builder.build(FAIL_PHASE_MS + i * 1000)
        step_events = [e for e in events if e["event.type"] == "external_test_step"]
        for step_event in step_events:
            if step_event["test.step.status"] == "failed":
                assert "test.step.error_code" in step_event
                assert isinstance(step_event["test.step.error_code"], str)  # int cast to str
                assert "test.step.error_message" in step_event
                return
    assert False, "No failed step event found in 20 iterations"


def test_build_pass_phase_all_events_passed():
    builder = CyclicPayloadBuilder()
    for i in range(20):
        events = builder.build(PASS_PHASE_MS + i * 1000)
        run_event = events[0]
        assert run_event["test.run.status"] == "passed", \
            f"Run {i}: expected test.run.status=passed in pass phase"
        assert run_event["test.run.availability"] == 1, \
            f"Run {i}: expected test.run.availability=1 in pass phase"

        step_events = [e for e in events if e["event.type"] == "external_test_step"]
        assert all(e["test.step.status"] == "passed" for e in step_events), \
            f"Run {i}: expected all step events passed in pass phase"
```

### Before — `tests/test_client.py`

```python
from monitor.config import MonitorConfig
from monitor.models import (
    LocationDefinition, LocationInfo, LocationResult,
    StepDefinition, StepResult,
    SyntheticPayload, TestDefinition, TestResult,
)


def _make_config() -> MonitorConfig:
    return MonitorConfig(
        tenant_url="https://abc12345.live.dynatrace.com",
        api_token="dt0c01.TEST_TOKEN",
        interval=10,
        duration=0,
        endpoint="https://abc12345.live.dynatrace.com/api/v1/synthetic/ext/tests",
    )


def _make_payload() -> SyntheticPayload:
    return SyntheticPayload(
        synthetic_engine_name="TestEngine",
        synthetic_engine_icon_url="https://example.com/icon.png",
        message_timestamp=1234567890000,
        locations=[LocationInfo(id="eu-west-1", name="EU West", ip="1.2.3.4")],
        tests=[
            TestDefinition(
                id="test-1", title="Test 1",
                schedule_interval_in_seconds=60,
                enabled=True, deleted=False,
                locations=[LocationDefinition("eu-west-1")],
                steps=[StepDefinition(1, "Step 1")],
            )
        ],
        test_results=[
            TestResult(
                id="test-1", total_step_count=1,
                location_results=[
                    LocationResult(
                        id="eu-west-1", start_timestamp=1234567890000,
                        success=True, response_time_millis=250,
                        success_rate=1.0,
                        step_results=[
                            StepResult(id=1, start_timestamp=1234567890000,
                                       response_time_millis=250)
                        ],
                    )
                ],
            )
        ],
    )


def test_post_calls_requests_post(mocker):
    mock_post = mocker.patch("requests.post")
    mock_response = mocker.MagicMock()
    mock_response.status_code = 204
    mock_response.text = ""
    mock_post.return_value = mock_response

    config = _make_config()
    client = DynatraceClient(config)
    client.post(_make_payload())

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == config.endpoint
    headers = call_args[1]["headers"]
    assert headers["Authorization"].startswith("Api-Token ")
    assert "dt0c01.TEST_TOKEN" in headers["Authorization"]
```

### After — `tests/test_client.py`

`_make_payload()` is replaced by `_make_events()` returning a `list[dict]`. The config endpoint and domain are updated. The assertion on `json=` now verifies a list is passed.

```python
import logging

import pytest

from monitor.client import DynatraceClient
from monitor.config import MonitorConfig


def _make_config() -> MonitorConfig:
    return MonitorConfig(
        env_url="https://abc12345.apps.dynatrace.com",   # apps domain, not the classic live domain
        api_token="dt0c01.TEST_TOKEN",
        interval=10,
        duration=0,
        endpoint="https://abc12345.live.dynatrace.com/platform/ingest/custom/events/external.tests",
    )


def _make_events() -> list[dict]:
    return [
        {
            "event.kind": "EXTERNAL_TEST_EVENT",
            "event.type": "external_test_run",
            "test.id": "test-1",
            "test.run.id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "test.name": "Test 1",
            "test.type": "api",
            "test.run.status": "passed",
            "test.run.availability": 1,
            "test.run.duration_ms": 250,
            "test.run.location": "eu-west-1",
            "timestamp": "2009-02-13T23:31:30Z",
        }
    ]


def test_post_calls_requests_post(mocker):
    mock_post = mocker.patch("requests.post")
    mock_response = mocker.MagicMock()
    mock_response.status_code = 202
    mock_response.text = ""
    mock_post.return_value = mock_response

    config = _make_config()
    client = DynatraceClient(config)
    client.post(_make_events())

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == config.endpoint
    headers = call_args[1]["headers"]
    assert headers["Authorization"].startswith("Api-Token ")
    assert "dt0c01.TEST_TOKEN" in headers["Authorization"]


def test_post_sends_list_body(mocker):
    mock_post = mocker.patch("requests.post")
    mock_response = mocker.MagicMock()
    mock_response.status_code = 202
    mock_response.text = ""
    mock_post.return_value = mock_response

    events = _make_events()
    DynatraceClient(_make_config()).post(events)

    call_args = mock_post.call_args
    sent_json = call_args[1]["json"]
    assert isinstance(sent_json, list), "New endpoint requires a JSON array, not a bare object"
    assert sent_json == events


def test_post_uses_json_content_type(mocker):
    mock_post = mocker.patch("requests.post")
    mock_response = mocker.MagicMock()
    mock_response.status_code = 202
    mock_response.text = ""
    mock_post.return_value = mock_response

    DynatraceClient(_make_config()).post(_make_events())

    headers = mock_post.call_args[1]["headers"]
    assert headers.get("Content-Type") == "application/json"


def test_post_logs_status_code(mocker, caplog):
    mock_post = mocker.patch("requests.post")
    mock_response = mocker.MagicMock()
    mock_response.status_code = 202
    mock_response.text = ""
    mock_post.return_value = mock_response

    import monitor.client as client_module
    client_module.logger.propagate = True

    with caplog.at_level(logging.INFO, logger="monitor.client"):
        DynatraceClient(_make_config()).post(_make_events())

    assert any("202" in record.message for record in caplog.records)
```
