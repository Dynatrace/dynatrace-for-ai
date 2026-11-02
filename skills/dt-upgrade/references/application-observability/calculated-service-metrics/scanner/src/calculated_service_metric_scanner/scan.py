"""Detect calculated service metric keys in configuration bodies.

A calculated service metric is reachable under two spellings and both have to be
found:

- **Grail form**, ``service.<key>`` — what a platform configuration
  (dashboard, notebook, SLO app, guardian, Davis custom alert) writes in DQL.
- **Classic form**, ``calc:service.<key>`` — what a classic
  configuration (classic SLO, classic metric event) writes in a metric selector
  or expression.

The two are matched under different rules on purpose. ``service.`` by shape
alone is not a metric key — ``service.name`` is an ordinary OpenTelemetry
attribute — so the Grail form is only a finding when it is also in the tenant's
metric inventory. The ``calc:`` prefix carries no such ambiguity: it exists only
on calculated metrics, so the classic form is matched by shape. That also keeps
a classic reference visible when the metric behind it was never enabled on
Grail and therefore never entered the inventory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterator

from .shared import SHARED_SETTINGS_FIELDS, is_shared_settings_field, strip_cached_results

_KEY_BODY = r"service\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*"
_BOUNDARY_BEFORE = r"(?<![A-Za-z0-9_.:-])"
_BOUNDARY_AFTER = r"(?![A-Za-z0-9_.-])"

#: Grail spelling. The leading boundary rejects a ``:`` so ``calc:service.x``
#: cannot be counted twice, once here and once as a classic key.
_GRAIL_PATTERN = re.compile(_BOUNDARY_BEFORE + _KEY_BODY + _BOUNDARY_AFTER)

#: Classic spelling. The trailing boundary stops before the ``:splitBy()`` and
#: friends that a classic metric selector appends.
_CLASSIC_PATTERN = re.compile(_BOUNDARY_BEFORE + r"calc:" + _KEY_BODY + _BOUNDARY_AFTER)

CLASSIC_PREFIX = "calc:"


@dataclass
class Finding:
    source: str
    kind: str
    artifact_id: str
    artifact_name: str
    field_path: str
    dql: str
    metric_keys: list[str]
    scope: str | None = None
    # The literal ``calc:service.*`` strings this field carries. Empty when the
    # reference was written in the Grail spelling; the report uses it to show
    # which form has to be reworked.
    classic_metric_keys: list[str] = field(default_factory=list)


def iter_strings(obj: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(obj, str):
        yield path or "$", obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from iter_strings(value, f"{path}.{key}" if path else str(key))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from iter_strings(value, f"{path}[{index}]")


def scan_item(item: dict[str, Any], metric_keys: set[str]) -> list[Finding]:
    """Findings for one configuration item.

    *metric_keys* is the Grail inventory in canonical ``service.<key>`` form. An
    empty inventory disables Grail-form matching but not classic-form matching,
    so a failed inventory read cannot silently turn the classic sources into a
    clean result.
    """
    body = strip_cached_results(item.get("body"))
    findings: list[Finding] = []
    for path, text in iter_strings(body):
        if not _is_executable_field(item.get("source", ""), path):
            continue
        classic = sorted(set(_CLASSIC_PATTERN.findall(text)))
        grail = sorted(set(_GRAIL_PATTERN.findall(text)) & metric_keys)
        canonical = sorted(
            set(grail) | {key.removeprefix(CLASSIC_PREFIX) for key in classic}
        )
        if not canonical:
            continue
        findings.append(
            Finding(
                source=item["source"],
                kind=item["kind"],
                artifact_id=item.get("id") or "",
                artifact_name=item.get("name") or item.get("id") or "<unnamed>",
                field_path=path,
                dql=text,
                metric_keys=canonical,
                scope=item.get("scope"),
                classic_metric_keys=classic,
            )
        )
    return findings


def drop_undefined_classic_keys(
    findings: list[Finding], defined_keys: set[str]
) -> tuple[list[Finding], list[Finding]]:
    """Split findings into references to metrics that exist and references to keys that do not.

    The classic spelling is matched by shape — the ``calc:`` prefix belongs to calculated
    metrics and nothing else — which is what makes a reference visible even when the metric was
    never enabled on Grail and so never entered the Grail inventory. Shape alone cannot tell a
    live metric from a deleted one, though, and reporting *usage of a metric that does not
    exist* is not usage of anything: the answer the report owes is which existing metrics are
    read.

    So once the classic definitions have been read in full, they become the authority for that
    spelling. A key nothing defines is separated out rather than dropped in silence: the
    configuration reading it returns no data today, Phase 3 or no Phase 3, and that is worth one
    line.

    *defined_keys* holds Grail-form keys (``service.<key>``). A finding keeps the keys that
    exist; one whose keys are all undefined moves to the second list. A key matched in the Grail
    spelling is left alone — the Grail inventory already vouched for it.
    """
    kept: list[Finding] = []
    stale: list[Finding] = []
    for finding in findings:
        undefined = {
            key
            for key in finding.metric_keys
            if CLASSIC_PREFIX + key in finding.classic_metric_keys
            and key not in defined_keys
        }
        if not undefined:
            kept.append(finding)
            continue
        live = [key for key in finding.metric_keys if key not in undefined]
        stale.append(
            Finding(
                source=finding.source,
                kind=finding.kind,
                artifact_id=finding.artifact_id,
                artifact_name=finding.artifact_name,
                field_path=finding.field_path,
                dql=finding.dql,
                metric_keys=sorted(undefined),
                scope=finding.scope,
                classic_metric_keys=[
                    CLASSIC_PREFIX + key for key in sorted(undefined)
                ],
            )
        )
        if live:
            kept.append(
                Finding(
                    source=finding.source,
                    kind=finding.kind,
                    artifact_id=finding.artifact_id,
                    artifact_name=finding.artifact_name,
                    field_path=finding.field_path,
                    dql=finding.dql,
                    metric_keys=live,
                    scope=finding.scope,
                    classic_metric_keys=[
                        key
                        for key in finding.classic_metric_keys
                        if key.removeprefix(CLASSIC_PREFIX) in set(live)
                    ],
                )
            )
    return kept, stale


def _is_executable_field(source: str, path: str) -> bool:
    """Limit matching to fields that execute or configure a metric query."""
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
        return path.endswith("customSli.indicator") or ".sliReference." in f".{path}."
    # Classic SLOs; the shared layer owns their field lists so a new shared
    # source needs no change here.
    if source in SHARED_SETTINGS_FIELDS:
        return is_shared_settings_field(source, path)
    if source == "srgs":
        return path.endswith(".dqlQuery") or path == "dqlQuery"
    if source == "metric_events":
        return path.startswith("value.queryDefinition.")
    if source == "davis_anomaly_detectors":
        return re.search(r"(?:^|\.)value\.analyzer\.input\[\d+\]\.value$", path) is not None
    return False
