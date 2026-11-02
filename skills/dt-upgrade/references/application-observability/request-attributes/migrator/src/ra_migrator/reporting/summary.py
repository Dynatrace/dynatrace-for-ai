"""The Summary Index: the machine contract a consuming skill classifies a run on.

Built from the `RunResult` alone and never from the Report, so the two renderings of one run cannot
disagree. Every field a consumer branches on is a value it can match - a verdict, a reason, a health
flag - and never prose it would have to parse: `detail` is free text and nothing here reads it back.
"""

from __future__ import annotations

from typing import Any

from .outcomes import (
    AttributeClass,
    NoVerdictReason,
    ResolutionReason,
)
from ..run_result import RunResult

# The verdict reasons that mean a read was capped rather than the tenant refuting the axis: the
# summary raises one health flag for the pair so a consumer can qualify its report.
_CAPPED_VERDICT_REASONS = frozenset({NoVerdictReason.TRUNCATED_VERIFICATION_READ})
_CAPPED_RESOLUTION_REASONS = frozenset(
    {ResolutionReason.TRUNCATED_PROCESS_GROUP_READ, ResolutionReason.TRUNCATED_SERVICE_READ}
)


def build_summary(result: RunResult) -> dict[str, Any]:
    """The run as a value: its provenance, its health, the scan funnel, and one row per unit."""
    artifacts = {one.attribute_id for one in result.artifacts}
    data_sources: dict[str, list[dict[str, Any]]] = {}
    for verdict in result.data_source_verdicts:
        data_sources.setdefault(verdict.attribute_id, []).append(
            {
                "index": verdict.data_source_index,
                "verdict": str(verdict.verdict),
                "reason": None if verdict.reason is None else str(verdict.reason),
                "detail": verdict.detail,
            }
        )
    return {
        "run": {
            "tenant": result.platform_url,
            "window": {
                "requested": result.window.expression,
                "timeframe": result.window.timeframe,
            },
        },
        "health": _health(result),
        "scan": {
            "scanned": result.scanned,
            "enabled": result.enabled,
            "obsolete": result.obsolete,
            "affected": result.affected,
            "disabled": sum(
                1 for one in result.classifications if one.verdict is AttributeClass.DISABLED
            ),
            "unprocessable": result.unprocessable,
            "affected_by_reason": {
                str(reason): count for reason, count in result.affected_by_reason.items()
            },
            "disabled_carrying_deprecated": result.disabled_carrying_deprecated,
        },
        "request_attributes": [
            {
                "id": verdict.attribute_id,
                "verdict": str(verdict.verdict),
                "reason": None if verdict.reason is None else str(verdict.reason),
                "detail": verdict.detail,
                "artifact": (
                    f"artifacts/{verdict.attribute_id}.json"
                    if verdict.attribute_id in artifacts
                    else None
                ),
                "data_sources": data_sources.get(verdict.attribute_id, []),
            }
            for verdict in result.request_attribute_verdicts
        ],
    }


def _health(result: RunResult) -> dict[str, bool]:
    """What a consumer must know to qualify its report rather than overstate the run.

    The span side unavailable (discovery named no key, so it was gated off run-wide), a read capped
    (a verification or resolution read the platform truncated), and a Request Attribute the run
    could not read at all - each read off the codes a stage already assigned, never re-derived.
    """
    verdict_reasons = {one.reason for one in result.data_source_verdicts}
    resolution_reasons = {one.reason for one in result.resolutions}
    return {
        "primary_tag_discovery_unavailable": (
            NoVerdictReason.NO_PRIMARY_TAG_KEY_ON_THE_TENANT in verdict_reasons
        ),
        "some_read_capped": bool(
            verdict_reasons & _CAPPED_VERDICT_REASONS
            or resolution_reasons & _CAPPED_RESOLUTION_REASONS
        ),
        "some_attribute_unreadable": any(
            one.verdict is AttributeClass.UNPROCESSABLE for one in result.classifications
        ),
    }
