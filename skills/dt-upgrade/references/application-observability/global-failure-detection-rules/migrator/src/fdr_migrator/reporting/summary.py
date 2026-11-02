"""The machine-readable summary of a run, written for whatever calls the migrator.

The bucket and the terminal code are both always present, so a consumer reads two fields and
never branches on a missing one. It describes the affected rules and nothing else: naming a rule
the tool left alone would invite a reader to treat it as a finding about that rule.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..run_result import RunResult
from .outcomes import BucketedRule, bucket_counts

SUMMARY_FILE = "summary.json"


def write_summary(result: RunResult, bucketed: Sequence[BucketedRule]) -> Path:
    """Write this run's summary where the run said it goes, and answer with the path."""
    result.summary_path.write_text(
        json.dumps(summary_document(result, bucketed), indent=2) + "\n", encoding="utf-8"
    )
    return result.summary_path


def summary_document(result: RunResult, bucketed: Sequence[BucketedRule]) -> dict[str, Any]:
    """Run metadata, the scan counts, the bucket counts, and one entry per affected rule."""
    return {
        "run": {
            "platform_url": result.platform_url,
            "window": result.window.expression,
            "timeframe": result.window.timeframe,
            "workdir": str(result.workdir),
            # Empty on a run over the whole tenant. Non-empty says the counts below describe
            # the rules asked for, so a caller never reads them as figures about the tenant.
            "requested_rule_ids": list(result.requested_rule_ids),
            "unmatched_rule_ids": list(result.unmatched_rule_ids),
            "requested_not_affected": list(result.requested_not_affected),
            "primary_tags_unavailable": result.primary_tags_unavailable,
            "primary_tag_keys_capped": result.primary_tag_keys_capped,
        },
        "scan": {
            "rules_read": result.coverage.rules_read,
            "enabled": result.coverage.enabled,
            "affected": result.coverage.affected,
            "affected_reasons": {
                reason.value: count
                for reason, count in result.coverage.affected_reasons.items()
            },
        },
        "outcomes": {outcome.value: count for outcome, count in bucket_counts(bucketed).items()},
        "rules": [_entry(entry) for entry in bucketed],
    }


def _entry(entry: BucketedRule) -> dict[str, Any]:
    return {
        "object_id": entry.rule.object_id,
        "name": entry.rule.name,
        "outcome": entry.outcome.value,
        "reason": entry.reason,
        "affected_reasons": [reason.value for reason in entry.rule.reasons],
        "detail": entry.detail,
        # Only a covered rule has one, so the key is always present and sometimes null rather
        # than sometimes absent.
        "artifact": str(entry.artifact.path) if entry.artifact else None,
    }
