"""Per-rule report artifact builder.

Reads:
- ``derived/<rule_id>.json``          — sidecar (original conditions + metadata)
- ``derived/<rule_id>_candidates.json`` — scored candidates
- ``derived/<rule_id>_verdict.json``   — Step 4 terminal verdict

Writes:
- ``report/<rule_id>.json``            — structured per-rule report

The report includes:
- Migration status and metadata
- Original deprecated conditions (for reference)
- Surviving original conditions carried forward
- Proposed replacement conditions
- Proposed replacement rule body (Config v1 ``RequestNamingDto`` shape, ready to
  POST — ``id`` stripped and ``enabled`` forced to false, so it creates a disabled clone)
- Discarded candidate attributes with reasons
- Notes
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..analysis.candidates import is_good_candidate
from ..rules.mapping import base_attribute, load_mapping, split_attribute
from ..rules.tags import is_primary_tag_key

# TagComparisonInfoDto caps ``values`` at 50; PARTIAL_CAP_DEFAULT (5) is the
# binding limit in practice, so this is a backstop against a raised cap.
_TAG_VALUES_MAX = 50


# ---------------------------------------------------------------------------
# comparisonInfo reconstruction
# ---------------------------------------------------------------------------

# Maps our api_matcher_type to the Config v1 ``type`` field.
_MATCHER_TO_TYPE: dict[str, str] = {
    "STRING": "STRING",
    "NUMBER": "NUMBER",
    "BOOLEAN": "BOOLEAN",
    "HTTP_METHOD": "HTTP_METHOD",
    "HTTP_STATUS_CLASS": "HTTP_STATUS_CLASS",
    "SERVICE_TYPE": "SERVICE_TYPE",
    "ZOS_TRANSACTIONTYPE": "ZOS_TRANSACTIONTYPE",
    "ESB_INPUT_NODE_TYPE": "ESB_INPUT_NODE_TYPE",
    "FLAW_STATE": "FLAW_STATE",
    "FAST_STRING": "FAST_STRING",
    "TAG": "TAG",
    "REQUEST_ATTRIBUTE": "REQUEST_ATTRIBUTE",
}


def _tag_dto(key: str, value: Any) -> dict[str, Any]:
    """Build a ``TagDto``.

    ``context`` is required by the DTO but never read by the Phase 3 evaluator
    (only ``getKey()`` / ``getValue()``), so ``CONTEXTLESS`` is always safe.
    """
    return {"context": "CONTEXTLESS", "key": key, "value": value}


def _build_tag_comparison_info(
    api_attribute: str,
    operator: str,
    values: list[Any],
    negate: bool,
) -> dict[str, Any]:
    """Build a ``TagComparisonInfoDto`` for a composite primary-tag attribute.

    Raises ``ValueError`` for shapes this path cannot express, rather than
    falling through to a scalar body the API would reject against the enum.
    """
    # A negated PG tag condition cannot be expressed at all: TagComparisonDto has
    # no NOT_EQUALS, and rewriting it as EQUALS + negate=true is rejected too —
    # PROCESS_GROUP_TAG is an ME-index attribute, and
    # ConditionSpecificationValidator.noNegationForMEIndex forbids negation on
    # those (MethodAttribute.PROCESS_GROUP_TAG declares isIndexCondition()).
    # Fail loudly rather than emit a body the API will reject.
    if operator == "NOT_EQUALS" or negate:
        raise ValueError(
            f"negation is not expressible for {api_attribute}: PROCESS_GROUP_TAG is an "
            "ME-index attribute and the Config v1 API rejects negate=true on it"
        )

    _, tag_key = split_attribute(api_attribute)
    if tag_key is None or not is_primary_tag_key(tag_key):
        raise ValueError(
            f"TAG comparison requires a primary_tags.* composite attribute, got {api_attribute!r}"
        )
    if not values:
        raise ValueError(f"TAG comparison for {tag_key} carries no values")
    if len(values) > _TAG_VALUES_MAX:
        raise ValueError(
            f"TAG comparison for {tag_key} has {len(values)} values, "
            f"DTO maximum is {_TAG_VALUES_MAX}"
        )
    if len(values) == 1:
        return {
            "type": "TAG",
            "comparison": operator,
            "value": _tag_dto(tag_key, values[0]),
            "values": None,
            "negate": negate,
        }
    return {
        "type": "TAG",
        "comparison": operator,
        "value": None,
        "values": [_tag_dto(tag_key, v) for v in values],
        "negate": negate,
    }


def _build_comparison_info(
    _api_attribute: str,
    operator: str,
    values: list[Any],
    negate: bool,
    matcher_type: str,
) -> dict[str, Any]:
    """Reconstruct a Config v1 ``comparisonInfo`` object."""
    if matcher_type == "TAG":
        return _build_tag_comparison_info(_api_attribute, operator, values, negate)
    ci_type = _MATCHER_TO_TYPE.get(matcher_type, "STRING")
    # NUMBER values must be integers, not strings (API uses NumberComparisonInfoDto).
    if ci_type == "NUMBER":
        values = [int(v) for v in values]
    if len(values) == 1:
        return {
            "type": ci_type,
            "comparison": operator,
            "value": values[0],
            "values": None,
            "negate": negate,
        }
    return {
        "type": ci_type,
        "comparison": operator,
        "value": None,
        "values": values,
        "negate": negate,
    }


# ---------------------------------------------------------------------------
# Candidate index builder
# ---------------------------------------------------------------------------


def _build_candidate_index(candidates: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map api_attribute → candidate entry for fast lookup (good + suboptimal)."""
    index: dict[str, dict[str, Any]] = {}
    for group in ("entity_candidates", "span_candidates",
                  "entity_candidates_suboptimal", "span_candidates_suboptimal"):
        for c in candidates.get(group, []):
            index[c["api_attribute"]] = c
    return index


# ---------------------------------------------------------------------------
# Replacement rule body assembly
# ---------------------------------------------------------------------------


def _build_replacement_conditions(
    verdict: dict[str, Any],
    candidate_index: dict[str, dict[str, Any]],
    sidecar: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Build the Config v1 ``conditions`` list for the replacement rule.

    Returns None if the verdict has no final_conditions (no_replacement).
    """
    final = verdict.get("final_conditions")
    if not final:
        return None

    conditions: list[dict[str, Any]] = []
    for fc in final:
        api_attr = fc["api_attribute"]
        negate = fc.get("negate", False)

        if negate:
            # Negation condition: NOT_EQUALS on the negated attribute's value.
            cand = candidate_index.get(api_attr)
            matcher_type = (
                fc.get("api_matcher_type")
                or (cand["api_matcher_type"] if cand else "STRING")
            )
            value = fc["value"] if "value" in fc else _extract_negation_value(fc["dql_fragment"])
            conditions.append({
                "attribute": base_attribute(api_attr),
                "comparisonInfo": _build_comparison_info(
                    api_attr, "NOT_EQUALS", [value], False, matcher_type
                ),
            })
            continue

        cand = candidate_index.get(api_attr)
        if cand is not None:
            # Prefer fields embedded in final_conditions — they reflect the
            # post-demotion working_artifact state (e.g. BEGINS_WITH demoted to
            # EQUALS_ANY_OF). Fall back to candidates file for older runs.
            operator = fc["api_operator"] if "api_operator" in fc else cand["api_operator"]
            values = fc["values"] if "values" in fc else cand["values"]
            matcher = fc["api_matcher_type"] if "api_matcher_type" in fc else cand["api_matcher_type"]
            conditions.append({
                "attribute": base_attribute(api_attr),
                "comparisonInfo": _build_comparison_info(
                    api_attr, operator, values, False, matcher,
                ),
            })
        else:
            # Surviving original condition — copy verbatim from sidecar.
            orig = _find_original_condition(sidecar, api_attr)
            if orig is not None:
                conditions.append(orig)

    return conditions


def _find_original_condition(sidecar: dict[str, Any], api_attribute: str) -> dict[str, Any] | None:
    """Find the original Config v1 condition dict from the sidecar raw_rule if stored,
    otherwise produce a minimal stub from the sidecar conditions list."""
    # Check if sidecar carries the raw rule body. A composite identity
    # (PROCESS_GROUP_TAG@primary_tags.team) matches on its base attribute — the
    # original condition is stored under the plain API attribute.
    base = base_attribute(api_attribute)
    raw = sidecar.get("raw_rule")
    if raw:
        for c in raw.get("conditions", []):
            if c.get("attribute") == base:
                return c

    # Fall back: build from sidecar conditions metadata.
    for c in sidecar.get("conditions", []):
        identities = c.get("api_attributes") or [c["attribute"]]
        if api_attribute in identities and c.get("lifecycle") == "surviving":
            # We don't have the original values here — mark as reference-only.
            return {
                "attribute": base,
                "_note": "surviving condition — comparisonInfo preserved from original rule",
            }
    return None


def _extract_negation_value(dql_fragment: str) -> Any:
    """Extract the literal value from a ``not field == "value"`` fragment."""
    # Format: not <key> == "<value>"
    m = re.search(r'==\s*"([^"]*)"', dql_fragment)
    if m:
        return m.group(1)
    m = re.search(r'==\s*(\S+)', dql_fragment)
    if m:
        return m.group(1)
    return dql_fragment


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_rule_report(  # pylint: disable=too-many-locals
    rule_id: str,
    *,
    derived_dir: Path,
    raw_rule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the per-rule report artifact.

    ``raw_rule`` is the original Config v1 rule body (optional — used to
    preserve surviving conditions verbatim in the replacement body).
    """
    sidecar_path = derived_dir / f"{rule_id}.json"
    candidates_path = derived_dir / f"{rule_id}_candidates.json"
    verdict_path = derived_dir / f"{rule_id}_verdict.json"

    sidecar: dict[str, Any] = json.loads(sidecar_path.read_text())
    candidates: dict[str, Any] = json.loads(candidates_path.read_text()) if candidates_path.exists() else {}
    verdict: dict[str, Any] = json.loads(verdict_path.read_text()) if verdict_path.exists() else {}

    if raw_rule:
        sidecar["raw_rule"] = raw_rule

    candidate_index = _build_candidate_index(candidates)

    # Migration status
    if not verdict:
        verdict_status = "not_run"
        qr = sidecar.get("query_result") or {}
        if sidecar.get("unmigratable_count", 0) > 0:
            # No query was ever issued for this rule, so "not observed in live
            # traffic" would be a false statement — it was never looked for. The
            # rule carries a condition the migrator cannot reproduce.
            migration_status = "unmigratable_conditions"
        elif not qr or qr.get("failure_reason") == "rule_matching_no_data":
            migration_status = "no_traffic_data"
        else:
            migration_status = "verification_not_run"
    else:
        verdict_status = verdict.get("status", "not_run")
        if verdict_status in ("exact_match", "exact_match_after_under_select_retry"):
            migration_status = "replacement_found"
        elif verdict_status == "no_replacement":
            migration_status = verdict.get("failure_reason") or "no_replacement"
        else:
            migration_status = verdict_status

    # Original deprecated conditions
    deprecated_conditions = [
        c for c in sidecar.get("conditions", [])
        if c.get("lifecycle") == "deprecated"
    ]
    # Management zones (also deprecated)
    mz = sidecar.get("management_zones")
    if mz:
        deprecated_conditions.append({"attribute": "__MANAGEMENT_ZONES__", **mz})

    # Surviving conditions
    surviving_conditions = [
        c for c in sidecar.get("conditions", [])
        if c.get("lifecycle") == "surviving"
    ]

    # Proposed replacement conditions (from verdict)
    proposed_conditions = verdict.get("final_conditions") or []

    # Build replacement rule body
    replacement_conditions = _build_replacement_conditions(verdict, candidate_index, sidecar)
    replacement_body: dict[str, Any] | None = None
    if replacement_conditions is not None and raw_rule is not None:
        # Strip the source rule's server-assigned id and force enabled=false so
        # the body is a valid *create* payload — a disabled clone — regardless of
        # who POSTs it (the apply command, MONACO, Terraform, or a raw request).
        replacement_body = {
            k: v for k, v in raw_rule.items()
            if k not in ("id", "enabled", "metadata", "conditions", "managementZones")
        }
        replacement_body["conditions"] = replacement_conditions
        replacement_body["managementZones"] = []
        replacement_body["enabled"] = False

    # Discarded candidates
    discarded = candidates.get("discarded_for_report", [])

    # Build quality lookup from the mapping — the single source of truth.
    _mapping = load_mapping()
    _api_to_quality = {
        r.api_attribute: r.candidate_quality
        for r in list(_mapping.entity_attributes) + list(_mapping.span_attributes)
    }

    def _tag(side: str, c: dict[str, Any]) -> dict[str, Any]:
        return {"side": side, **c}

    def _good(_side: str, c: dict[str, Any]) -> bool:
        return is_good_candidate(c, api_to_quality=_api_to_quality)

    all_with_side = (
        [_tag("entity", c) for c in candidates.get("entity_candidates", [])]
        + [_tag("span",   c) for c in candidates.get("span_candidates",   [])]
    )
    good_candidates      = [c for c in all_with_side if     _good(c["side"], c)]
    suboptimal_candidates = [c for c in all_with_side if not _good(c["side"], c)]

    return {
        "rule_id": rule_id,
        "naming_pattern": sidecar.get("naming_pattern"),
        "enabled": sidecar.get("enabled", True),
        "case": sidecar.get("case"),
        "migration_status": migration_status,
        "unmigratable_reasons": _unmigratable_reasons(sidecar),
        "verdict_status": verdict_status,
        "verdict_iterations": verdict.get("iterations"),
        "verdict_negations": len(verdict.get("negations_applied") or []),
        "verdict_demotions": len(verdict.get("demotions_applied") or []),
        "deprecated_conditions": deprecated_conditions,
        "surviving_conditions": surviving_conditions,
        "proposed_conditions": proposed_conditions,
        "replacement_rule_body": replacement_body,
        "discarded_attributes": discarded,
        "good_candidates": good_candidates,
        "suboptimal_candidates": suboptimal_candidates,
        "notes": candidates.get("notes", []) + verdict.get("history", []),
    }


def _unmigratable_reasons(sidecar: dict[str, Any]) -> list[str]:
    """Every reason a condition of this rule could not be reproduced.

    Surfaced in the report so "manual migration required" is actionable; includes
    the rule-level ``managementZones`` entry, which is not in ``conditions``.
    """
    sources = list(sidecar.get("conditions", []))
    mz = sidecar.get("management_zones")
    if mz:
        sources.append(mz)
    reasons: list[str] = []
    for c in sources:
        reason = c.get("unmigratable_reason")
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons


def write_rule_report(report_dir: Path, report: dict[str, Any]) -> Path:
    """Atomically write a rule report JSON file and return its path."""
    report_dir.mkdir(parents=True, exist_ok=True)
    out = report_dir / f"{report['rule_id']}.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    tmp.replace(out)
    return out


__all__ = ["build_rule_report", "write_rule_report"]
