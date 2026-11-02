"""Upload disabled replacement rules to the tenant.

Reads:
- ``report/summary.json``               — identifies rules with a replacement
- ``report/<rule_id>.json``             — provides ``replacement_rule_body``

Writes:
- ``report/apply_log.json``             — per-rule outcome + reorder status

For each rule that has ``migration_status == "replacement_found"`` (derived
from ``verification_status`` in summary), the replacement is POSTed as a *disabled*
rule inserted directly above the original in the global evaluation order.
The original rule is never touched.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .clients.config_v1 import ConfigV1Client, ConfigV1Error

_REPLACEMENT_STATUSES = frozenset({"exact_match", "exact_match_after_under_select_retry"})

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApplyResult:
    """Outcome of processing one rule through the upload step."""

    rule_id: str
    new_rule_id: str | None
    naming_pattern: str | None
    status: Literal["applied", "dry_run", "skipped", "failed"]
    skip_reason: str | None = None
    error: str | None = None


class ApplyReorderError(RuntimeError):
    """Raised when POST succeeded but the subsequent reorder call failed.

    The posted rules exist in the tenant but sit at the tail of the evaluation
    order. Surface ``posted`` to the user so they can reorder manually.
    """

    def __init__(self, posted: list[tuple[str, str]], cause: Exception) -> None:
        self.posted = posted
        super().__init__(
            f"reorder failed after {len(posted)} rule(s) posted — "
            f"new IDs: {[p[0] for p in posted]}. Cause: {cause}"
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def apply_rules(
    *,
    run_dir: Path,
    client: ConfigV1Client,
    dry_run: bool = True,
    rule_ids: list[str] | None = None,
) -> list[ApplyResult]:
    """Upload disabled replacement rules above each original.

    Raises :class:`ApplyReorderError` if POST succeeded for at least one rule
    but the reorder call failed. The apply log is written before raising.

    ``dry_run`` is a test-only seam: it lets the unit tests exercise the target
    resolution, classification, and apply-log paths without touching the tenant.
    It is intentionally not exposed on the CLI — ``apply`` is a dedicated,
    explicit write command and always calls this with ``dry_run=False``.
    """
    results: list[ApplyResult] = []
    pre_skip, valid_targets, live_ids = _resolve_targets(run_dir, client, rule_ids)
    results.extend(pre_skip)

    posted: list[tuple[str, str]] = []  # (new_id, original_id)
    for rid in valid_targets:
        report = json.loads((run_dir / "report" / f"{rid}.json").read_text(encoding="utf-8"))
        naming_pattern = report.get("naming_pattern")
        replacement_body = report.get("replacement_rule_body")

        if replacement_body is None:
            results.append(ApplyResult(
                rule_id=rid, new_rule_id=None,
                naming_pattern=naming_pattern, status="skipped",
                skip_reason="no_replacement_body",
            ))
            continue

        if dry_run:
            results.append(ApplyResult(
                rule_id=rid, new_rule_id=None,
                naming_pattern=naming_pattern, status="dry_run",
            ))
            continue

        # The builder guarantees replacement_rule_body is a valid create payload
        # (id stripped, enabled=false), so it is POSTed verbatim.
        try:
            new_id = client.post_rule(replacement_body)
            posted.append((new_id, rid))
            results.append(ApplyResult(
                rule_id=rid, new_rule_id=new_id,
                naming_pattern=naming_pattern, status="applied",
            ))
        except ConfigV1Error as exc:
            results.append(ApplyResult(
                rule_id=rid, new_rule_id=None,
                naming_pattern=naming_pattern, status="failed", error=str(exc),
            ))

    if not dry_run and posted:
        try:
            client.reorder_rules(_insert_above(live_ids, posted))
        except ConfigV1Error as exc:
            _write_apply_log(run_dir, results, dry_run,
                             reorder_failure={"error": str(exc), "posted": posted})
            raise ApplyReorderError(posted=posted, cause=exc) from exc

    _write_apply_log(run_dir, results, dry_run)
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_targets(
    run_dir: Path,
    client: ConfigV1Client,
    rule_ids: list[str] | None,
) -> tuple[list[ApplyResult], list[str], list[str]]:
    """Load summary, validate against live tenant; return (pre_skips, valid_targets, live_ids)."""
    summary = json.loads((run_dir / "report" / "summary.json").read_text(encoding="utf-8"))
    replaceable = {
        r["id"]
        for r in summary.get("rules", [])
        if r.get("verification_status") in _REPLACEMENT_STATUSES
    }

    pre_skips: list[ApplyResult] = []
    if rule_ids is not None:
        requested = set(rule_ids)
        for rid in sorted(requested - replaceable):
            pre_skips.append(ApplyResult(
                rule_id=rid, new_rule_id=None, naming_pattern=None,
                status="skipped", skip_reason="no_replacement_found",
            ))
        target_set = replaceable & requested
    else:
        target_set = set(replaceable)

    live_ids = [s.id for s in client.list_rules()]
    live_id_set = set(live_ids)
    valid: list[str] = []
    for rid in target_set:
        if rid not in live_id_set:
            pre_skips.append(ApplyResult(
                rule_id=rid, new_rule_id=None, naming_pattern=None,
                status="skipped", skip_reason="original_not_found",
            ))
        else:
            valid.append(rid)

    live_pos = {rid: i for i, rid in enumerate(live_ids)}
    valid.sort(key=lambda rid: live_pos[rid])
    return pre_skips, valid, live_ids


def _insert_above(
    live_ids: list[str],
    posted: list[tuple[str, str]],
) -> list[str]:
    """Return a new ordered list with each new_id inserted just before its original."""
    anchor = {orig: new for new, orig in posted}
    result: list[str] = []
    for rid in live_ids:
        if rid in anchor:
            result.append(anchor[rid])
        result.append(rid)
    return result


def _write_apply_log(
    run_dir: Path,
    results: list[ApplyResult],
    dry_run: bool,
    reorder_failure: dict[str, Any] | None = None,
) -> None:
    """Write apply_log.json. ``reorder_failure`` carries error + posted pairs on failure."""
    counts = {s: sum(1 for r in results if r.status == s)
              for s in ("applied", "dry_run", "skipped", "failed")}
    log: dict[str, Any] = {
        "dry_run": dry_run,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "applied": counts["applied"],
        "dry_run_count": counts["dry_run"],
        "skipped": counts["skipped"],
        "failed": counts["failed"],
        "reorder_ok": reorder_failure is None,
        "rules": [
            {
                "rule_id": r.rule_id,
                "new_rule_id": r.new_rule_id,
                "naming_pattern": r.naming_pattern,
                "status": r.status,
                "skip_reason": r.skip_reason,
                "error": r.error,
            }
            for r in results
        ],
    }
    if reorder_failure is not None:
        log["reorder_error"] = reorder_failure.get("error")
        log["posted_pairs"] = [
            {"new_id": n, "original_id": o}
            for n, o in reorder_failure.get("posted", [])
        ]
    (run_dir / "report" / "apply_log.json").write_text(
        json.dumps(log, indent=2, ensure_ascii=False)
    )


__all__ = ["ApplyResult", "ApplyReorderError", "apply_rules"]
