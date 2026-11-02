"""Detect exact classic queue IDs and queue metric keys in configuration bodies."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterator

from . import CLASSIC_QUEUE_METRICS
from .shared import SHARED_SETTINGS_FIELDS, is_shared_settings_field, strip_cached_results

_QUEUE_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_-])QUEUE-[0-9A-Fa-f]{16}(?![A-Za-z0-9_-])"
)
_METRIC_RE = re.compile(
    r"(?<![A-Za-z0-9_.:-])builtin:queue\.(?:incoming_requests|outgoing_requests)"
    r"(?![A-Za-z0-9_.-])"
)


@dataclass
class Finding:
    source: str
    kind: str
    artifact_id: str
    artifact_name: str
    field_path: str
    text: str
    queue_ids: list[str] = field(default_factory=list)
    metric_keys: list[str] = field(default_factory=list)
    scope: str | None = None


def iter_strings(obj: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(obj, str):
        yield path or "$", obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from iter_strings(value, f"{path}.{key}" if path else str(key))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from iter_strings(value, f"{path}[{index}]")


def scan_item(item: dict[str, Any]) -> list[Finding]:
    body = strip_cached_results(item.get("body"))
    try:
        body_text = json.dumps(body, ensure_ascii=False)
    except (TypeError, ValueError):
        body_text = str(body)
    if "QUEUE-" not in body_text.upper() and not any(
        metric in body_text for metric in CLASSIC_QUEUE_METRICS
    ):
        return []

    findings: list[Finding] = []
    for path, text in iter_strings(body):
        if not _is_configuration_field(item.get("source", ""), path):
            continue
        queue_ids = sorted({match.upper() for match in _QUEUE_ID_RE.findall(text)})
        metric_keys = sorted(set(_METRIC_RE.findall(text)))
        if not queue_ids and not metric_keys:
            continue
        findings.append(
            Finding(
                source=item["source"],
                kind=item["kind"],
                artifact_id=item.get("id") or "",
                artifact_name=item.get("name") or item.get("id") or "<unnamed>",
                field_path=path,
                text=text,
                queue_ids=queue_ids,
                metric_keys=metric_keys,
                scope=item.get("scope"),
            )
        )
    return findings


def _is_configuration_field(source: str, path: str) -> bool:
    """Limit matching to fields that execute or configure telemetry queries."""
    if source in {"dashboards", "notebooks"}:
        dotted = f".{path}."
        return (
            ".state.input." in dotted
            or ".variables[" in dotted
            or path.startswith("variables[")
            or path.endswith((".query", ".dql"))
            or path in {"query", "dql", "state.input"}
        )
    if source == "slos":
        return path.endswith("customSli.indicator") or re.search(
            r"(?:^|\.)sliReference\.variables\[\d+\]\.value$", path
        ) is not None
    # Classic SLOs; the shared layer owns their field lists so a new shared source
    # needs no change here.
    if source in SHARED_SETTINGS_FIELDS:
        return is_shared_settings_field(source, path)
    if source == "srgs":
        return path.endswith(".dqlQuery") or path == "dqlQuery"
    if source == "metric_events":
        return path.startswith("value.queryDefinition.")
    if source == "davis_anomaly_detectors":
        return re.search(r"(?:^|\.)value\.analyzer\.input\[\d+\]\.value$", path) is not None
    return False
