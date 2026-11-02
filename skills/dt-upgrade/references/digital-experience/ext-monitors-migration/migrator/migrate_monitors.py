"""
migrate_monitors.py — Migrate legacy Dynatrace external synthetic monitor payloads
to the new external test event format.

Usage:
    python migrator/migrate_monitors.py --type <test_type> [--validate] <input_path> [<output_path>]

    --type        Required. The test type emitted in every migrated event:
                    browser | api | http | mobile
                  The legacy SyntheticPayload format carries no type field, so the
                  value cannot be inferred automatically. Pass the type that matches
                  the monitors in the input. When a directory contains monitors of
                  mixed types, run the script once per type on separate sub-directories
                  or files.
    --validate    Dry-run: parse and migrate in memory, report what would be written,
                  but do not write any files.
    input_path    File or directory to migrate.
    output_path   Destination file or directory (default: overwrite input in place).

Importable API:
    looksLikeMonitor(data)           -> bool
    migrate(data, test_type)         -> list[dict] | None
    main(args)                       -> None
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

VALID_TEST_TYPES = frozenset({"browser", "api", "http", "mobile"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def looksLikeMonitor(data: dict) -> bool:
    """Return True if *data* looks like a legacy synthetic monitor payload.

    The heuristic: both ``syntheticEngineName`` and ``testResults`` must be
    present as keys (values may be empty).
    """
    return "syntheticEngineName" in data and "testResults" in data


def migrate(data: dict, test_type: str) -> list[dict] | None:
    """Transform a legacy synthetic monitor payload into a list of events.

    Args:
        data:      Parsed JSON dict of a legacy SyntheticPayload.
        test_type: Value for ``test.type`` on every emitted run event.
                   Must be one of: browser, api, http, mobile.
                   The legacy format carries no type field — the caller must
                   supply the correct value for the monitors being migrated.

    Returns None when *data* does not pass the ``looksLikeMonitor`` heuristic.

    For active tests, each (testResult, locationResult) pair produces:
      - one  ``external_test_run``  event
      - zero or more ``external_test_step`` events (one per entry in
        ``stepResults``, omitted entirely when the array is empty or absent)

    For deleted tests (``tests[*].deleted == true``), each locationResult
    produces only one ``external_test_run`` event with
    ``test.run.status: "decommissioned"``; no step events are emitted.

    A fresh UUID v4 is generated for every (test, location) pair and shared
    across the run event and all its step events via ``test.run.id``.

    Run timestamps come from ``locationResult.startTimestamp``.
    Step timestamps come from each ``stepResult.startTimestamp``.
    Both are epoch milliseconds converted to ISO 8601 UTC.
    """
    if test_type not in VALID_TEST_TYPES:
        raise ValueError(
            f"Invalid test_type {test_type!r}. Must be one of: {', '.join(sorted(VALID_TEST_TYPES))}"
        )

    if not looksLikeMonitor(data):
        return None

    events: list[dict] = []

    engine_name: str = data.get("syntheticEngineName", "") or ""

    # Index test definitions by their id for O(1) lookups.
    tests_by_id: dict[str, dict] = {t["id"]: t for t in data.get("tests", [])}

    for test_result in data.get("testResults", []):
        test_id: str = test_result["id"]
        test_def: dict = tests_by_id.get(test_id, {})

        test_name: str = test_def.get("title", test_id)
        test_frequency = test_def.get("scheduleIntervalInSeconds")  # may be absent
        is_deleted: bool = bool(test_def.get("deleted", False))

        # Index step definitions by step id so we can look up titles quickly.
        steps_by_id: dict[int, str] = {
            step["id"]: step["title"]
            for step in test_def.get("steps", [])
        }

        for loc_result in test_result.get("locationResults", []):
            location: str = loc_result["id"]
            run_id: str = str(uuid.uuid4())
            run_timestamp: str = _epoch_ms_to_iso(loc_result["startTimestamp"])

            if is_deleted:
                run_event: dict = {
                    "event.kind": "EXTERNAL_TEST_EVENT",
                    "event.type": "external_test_run",
                    "test.id": test_id,
                    "test.run.id": run_id,
                    "test.name": test_name,
                    "test.type": test_type,
                    "test.run.status": "decommissioned",
                    "test.run.availability": 0,
                    "test.run.duration_ms": loc_result.get("responseTimeMillis", 0),
                    "test.run.location": location,
                    "timestamp": run_timestamp,
                }
                if test_frequency is not None:
                    run_event["test.frequency_sec"] = test_frequency
                if engine_name:
                    run_event["runner.name"] = engine_name
                events.append(run_event)
                continue  # no step events for decommissioned monitors

            success: bool = bool(loc_result.get("success", False))

            # --- run event ---------------------------------------------------
            run_event = {
                "event.kind": "EXTERNAL_TEST_EVENT",
                "event.type": "external_test_run",
                "test.id": test_id,
                "test.run.id": run_id,
                "test.name": test_name,
                "test.type": test_type,
                "test.run.status": "passed" if success else "failed",
                "test.run.availability": 1 if success else 0,
                "test.run.duration_ms": loc_result.get("responseTimeMillis", 0),
                "test.run.location": location,
                "timestamp": run_timestamp,
            }

            if test_frequency is not None:
                run_event["test.frequency_sec"] = test_frequency

            if engine_name:
                run_event["runner.name"] = engine_name

            events.append(run_event)

            # --- step events -------------------------------------------------
            step_results = loc_result.get("stepResults", [])
            for step_result in step_results:
                step_id = step_result["id"]
                raw_title: str = steps_by_id.get(step_id, f"step-{step_id}")
                step_name: str = raw_title.lower().replace(" ", "-")
                has_error: bool = "error" in step_result
                step_timestamp: str = _epoch_ms_to_iso(
                    step_result.get("startTimestamp", loc_result["startTimestamp"])
                )

                step_event: dict = {
                    "event.kind": "EXTERNAL_TEST_EVENT",
                    "event.type": "external_test_step",
                    "test.run.id": run_id,
                    "test.id": test_id,
                    "test.step.id": f"step-{step_id}",
                    "test.step.name": step_name,
                    "test.step.index": step_id,
                    "test.step.status": "failed" if has_error else "passed",
                    "test.step.duration_ms": step_result.get("responseTimeMillis", 0),
                    "timestamp": step_timestamp,
                }

                if has_error:
                    error = step_result["error"]
                    step_event["test.step.error_code"] = str(error["code"])
                    step_event["test.step.error_message"] = error["message"]

                events.append(step_event)

    return events


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(args: list[str]) -> None:
    """CLI entry point.

    Synopsis:
        migrate_monitors.py --type <test_type> [--validate] <input_path> [<output_path>]
    """
    # --- argument parsing ---------------------------------------------------
    validate_only: bool = False
    test_type: str | None = None
    remaining: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--validate":
            validate_only = True
        elif args[i] == "--type":
            i += 1
            if i >= len(args):
                print("Error: --type requires a value", file=sys.stderr)
                sys.exit(2)
            test_type = args[i]
        else:
            remaining.append(args[i])
        i += 1

    if test_type is None:
        print(
            "Error: --type is required. Must be one of: "
            + ", ".join(sorted(VALID_TEST_TYPES)),
            file=sys.stderr,
        )
        print(
            "Usage: migrate_monitors.py --type <test_type> [--validate] <input_path> [<output_path>]",
            file=sys.stderr,
        )
        sys.exit(2)

    if test_type not in VALID_TEST_TYPES:
        print(
            f"Error: invalid --type {test_type!r}. Must be one of: "
            + ", ".join(sorted(VALID_TEST_TYPES)),
            file=sys.stderr,
        )
        sys.exit(2)

    if not remaining:
        print(
            "Usage: migrate_monitors.py --type <test_type> [--validate] <input_path> [<output_path>]",
            file=sys.stderr,
        )
        sys.exit(2)

    input_path = Path(remaining[0])
    output_path = Path(remaining[1]) if len(remaining) > 1 else None

    if not input_path.exists():
        print(f"Error: path does not exist: {input_path}", file=sys.stderr)
        sys.exit(1)

    # --- dispatch -----------------------------------------------------------
    if input_path.is_file():
        _process_file(input_path, output_path or input_path, test_type=test_type, validate_only=validate_only)
    else:
        # Directory: walk recursively, mirror structure to output dir.
        out_dir = output_path or input_path
        for json_file in sorted(input_path.rglob("*.json")):
            relative = json_file.relative_to(input_path)
            out_file = out_dir / relative
            out_file.parent.mkdir(parents=True, exist_ok=True)
            _process_file(json_file, out_file, test_type=test_type, validate_only=validate_only)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _epoch_ms_to_iso(epoch_ms: int) -> str:
    """Convert epoch milliseconds to an ISO 8601 UTC string (second precision)."""
    return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _process_file(
    input_path: Path, output_path: Path, *, test_type: str, validate_only: bool = False
) -> None:
    """Read *input_path*, migrate if appropriate, write result to *output_path*.

    When *validate_only* is True the migration runs in memory but no file is
    written; the function prints "would migrate:" or "would skip:" instead.
    """
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"Error reading {input_path}: {exc}", file=sys.stderr)
        return

    if not looksLikeMonitor(data):
        print(f"{'would skip' if validate_only else 'skipped'}: {input_path}")
        return

    try:
        result = migrate(data, test_type)
    except Exception as exc:  # noqa: BLE001
        print(f"Error migrating {input_path}: {exc}", file=sys.stderr)
        return

    if result is None:
        print(f"{'would skip' if validate_only else 'skipped'}: {input_path}")
        return

    if validate_only:
        print(f"would migrate: {input_path} → {len(result)} event(s)")
        return

    try:
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"migrated: {input_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"Error writing {output_path}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
