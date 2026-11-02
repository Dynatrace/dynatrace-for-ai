"""End-to-end run pipeline wiring Phases 1-5 together.

For each rule:

1. Hydrate the rule body via Config v1.
2. Parse into :class:`Rule` (pydantic).
3. Classify into Case A/C + (entity/span) × (surviving/deprecated)
   buckets.
4. Compute the ``(entity_key, span_key)`` cache pair.
5. Translate each condition (and ``managementZones``) into DQL fragments,
   recording any unmigratable reasons.
6. Persist a per-rule sidecar to ``derived/<rule_id>.json``.
7. Execute entity + span DQL queries; write ``cache/`` artifacts.
8. Score replacement candidates; write ``derived/<rule_id>_candidates.json``.
9. Run overselect verification loop; write ``derived/<rule_id>_verdict.json``.
10. Build per-rule report artifact; write ``report/<rule_id>.json``.
11. Append to aggregate ``report/summary.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .analysis.candidates import UnmigratableRuleError, build_candidates, write_candidates
from .analysis.overselect_loop import VerificationResult, run_overselect_loop
from .analysis.substring_candidate_rescue import augment_candidates
from .cache import compute_keys
from .clients.config_v1 import ConfigV1Client
from .clients.dql import DqlClient
from .config import AppConfig, ensure_workdir
from .queries import build_primary_tag_discovery_query
from .report import build_rule_report, write_html_report, write_rule_report
from .rules.classifier import Classification, classify
from .rules.models import Condition, Rule
from .rules.mapping import compose_attribute
from .rules.tags import (
    PRIMARY_TAGS_PREFIX,
    is_primary_tag_condition,
    is_primary_tag_key,
    tag_pairs,
)
from .rules.translator import (
    Translation,
    fetch_source_for,
    translate_condition,
    translate_management_zones,
)
from .query_executor import DqlQueryResult, execute_dql_queries, execute_span_fallback_query


@dataclass(frozen=True)
class CandidateScoringResult:
    """Scoring outcome for one rule's candidate set."""

    candidates_path: str
    entity_candidate_count: int
    span_candidate_count: int
    failure_reason: str | None = None

    @property
    def success(self) -> bool:
        """True when candidate scoring produced no failure."""
        return self.failure_reason is None


@dataclass(frozen=True)
class RuleOutcome:
    """Full pipeline result for one rule."""
    rule_id: str
    naming_pattern: str | None
    enabled: bool
    case: str
    is_deprecated: bool
    entity_key: str
    span_key: str
    translations: list[dict[str, Any]]
    management_zones_translation: dict[str, Any] | None
    unmigratable_count: int
    query_result: DqlQueryResult | None = None
    span_fallback_result: DqlQueryResult | None = None
    candidate_result: CandidateScoringResult | None = None
    verification_result: VerificationResult | None = None
    report_path: str | None = None


def discover_primary_tag_keys(dql: DqlClient | None) -> list[str]:
    """List the tenant's ``primary_tags.*`` span columns, sorted.

    Keys are tenant-global, so this runs once per run rather than per rule. A
    discovery failure is not fatal: primary tags simply do not become candidate
    sources for this run.
    """
    if dql is None:
        return []
    try:
        rows = dql.execute(build_primary_tag_discovery_query())
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return []
    keys = {
        row["field"]
        for row in rows
        if isinstance(row.get("field"), str) and row["field"].startswith(PRIMARY_TAGS_PREFIX)
    }
    return sorted(keys)


def run(
    cfg: AppConfig,
    *,
    client: ConfigV1Client | None = None,
    dql: DqlClient | None = None,
) -> dict[str, Any]:
    """Execute the pipeline and persist artifacts. Returns the summary dict.

    Disabled rules are skipped unconditionally. Of the remaining enabled rules,
    only those carrying at least one Phase-3 deprecated condition (deprecated
    ``managementZones``, ``SERVICE_TAG``, or non-primary ``PROCESS_GROUP_TAG``)
    are classified and translated; everything else is skipped after a cheap
    deprecation probe. The count of skipped rules is reported in the summary.

    Pass ``dql=None`` to skip Step 2 DQL execution (translation only).
    """
    # pylint: disable=too-many-locals,too-many-statements
    paths = ensure_workdir(cfg.output_dir)
    cv1 = client or ConfigV1Client(
        tenant_url=cfg.classic_url, api_token=cfg.platform_token
    )
    dql_client: DqlClient | None = dql

    stub_ids = _resolve_target_ids(cv1, cfg.rule_ids)
    primary_tag_keys = discover_primary_tag_keys(dql_client)
    outcomes: list[RuleOutcome] = []
    skipped_no_deprecated = 0
    skipped_rules: list[dict[str, Any]] = []

    for rid in stub_ids:
        raw = cv1.get_rule(rid)
        rule = Rule.model_validate(raw)
        if not rule.enabled:
            skipped_rules.append({
                "id": rule.id,
                "naming_pattern": rule.namingPattern,
                "enabled": False,
                "skip_reason": "disabled",
            })
            continue
        if not classify(rule).is_deprecated:
            skipped_no_deprecated += 1
            skipped_rules.append({
                "id": rule.id,
                "naming_pattern": rule.namingPattern,
                "enabled": True,
                "skip_reason": "no_deprecated_conditions",
            })
            continue
        outcome = _process_rule(
            rule,
            dql=dql_client,
            cache_dir=paths["cache"],
            query_timeframe=cfg.query_timeframe,
            primary_tag_keys=primary_tag_keys,
        )
        outcomes.append(outcome)
        _write_sidecar(paths["derived"], outcome)
        if outcome.query_result is not None and outcome.query_result.success:
            candidate_result = _run_candidate_scoring(
                outcome, cache_dir=paths["cache"], derived_dir=paths["derived"]
            )
            outcomes[-1] = replace(outcomes[-1], candidate_result=candidate_result)

            # Case A span fallback: no entity candidates → A.2 span query, re-score in full mode.
            if (outcome.case == "A"
                    and candidate_result.success
                    and candidate_result.entity_candidate_count == 0
                    and dql_client is not None):
                span_fallback_result = _run_span_fallback_query(
                    outcomes[-1],
                    dql=dql_client,
                    cache_dir=paths["cache"],
                    query_timeframe=cfg.query_timeframe,
                    primary_tag_keys=primary_tag_keys,
                )
                outcomes[-1] = replace(outcomes[-1], span_fallback_result=span_fallback_result)
                # Re-write the sidecar now that span_fallback_result is known.
                _write_sidecar(paths["derived"], outcomes[-1])
                if span_fallback_result.success:
                    candidate_result = _run_candidate_scoring(
                        outcomes[-1],
                        cache_dir=paths["cache"],
                        derived_dir=paths["derived"],
                        force_full=True,
                    )
                    outcomes[-1] = replace(outcomes[-1], candidate_result=candidate_result)

            if candidate_result.success and dql_client is not None and _should_verify_candidates(outcomes[-1]):
                # Case A early exit: entity candidates found, no span fallback ran →
                # entity-only overselect check (span_key=None activates that path).
                cur = outcomes[-1]
                use_entity_only = (
                    cur.case == "A"
                    and cur.span_fallback_result is None
                    and cur.candidate_result is not None
                    and cur.candidate_result.entity_candidate_count > 0
                )
                verification_result = _run_candidate_verification(
                    cur,
                    cache_dir=paths["cache"],
                    derived_dir=paths["derived"],
                    dql=dql_client,
                    effective_span_key=None if use_entity_only else cur.span_key,
                    query_timeframe=cfg.query_timeframe,
                    effective_timeframe=cur.query_result.effective_timeframe if cur.query_result else None,
                )
                outcomes[-1] = replace(outcomes[-1], verification_result=verification_result)

                # Case A: entity-only overselect exhausted → retry with span fallback.
                if (use_entity_only
                        and verification_result.status == "no_replacement"
                        and dql_client is not None):
                    span_fallback_result = _run_span_fallback_query(
                        outcomes[-1],
                        dql=dql_client,
                        cache_dir=paths["cache"],
                        query_timeframe=cfg.query_timeframe,
                    )
                    outcomes[-1] = replace(outcomes[-1], span_fallback_result=span_fallback_result)
                    _write_sidecar(paths["derived"], outcomes[-1])
                    if span_fallback_result.success:
                        candidate_result = _run_candidate_scoring(
                            outcomes[-1],
                            cache_dir=paths["cache"],
                            derived_dir=paths["derived"],
                            force_full=True,
                        )
                        outcomes[-1] = replace(outcomes[-1], candidate_result=candidate_result)
                        if _should_verify_candidates(outcomes[-1]):
                            cur2 = outcomes[-1]
                            verification_result = _run_candidate_verification(
                                cur2,
                                cache_dir=paths["cache"],
                                derived_dir=paths["derived"],
                                dql=dql_client,
                                effective_span_key=cur2.span_key,
                                query_timeframe=cfg.query_timeframe,
                                effective_timeframe=cur2.query_result.effective_timeframe if cur2.query_result else None,
                            )
                            outcomes[-1] = replace(outcomes[-1], verification_result=verification_result)
        # Build per-rule report artifact (runs regardless of verification outcome).
        report_path = _run_report_generation(outcomes[-1], derived_dir=paths["derived"], report_dir=paths["report"], raw_rule=raw)
        outcomes[-1] = replace(outcomes[-1], report_path=report_path)

    summary = _build_summary(
        outcomes,
        cfg=cfg,
        inspected=len(stub_ids),
        skipped_no_deprecated=skipped_no_deprecated,
        skipped_rules=skipped_rules,
    )
    _write_summary(paths["report"], summary)
    write_html_report(paths["report"])
    return summary


# ---------- internals ----------------------------------------------------- #


def _resolve_target_ids(
    cv1: ConfigV1Client, rule_ids: list[str] | None
) -> list[str]:
    if rule_ids:
        return list(rule_ids)
    return [s.id for s in cv1.list_rules()]


def _process_rule(
    rule: Rule,
    *,
    dql: DqlClient | None,
    cache_dir: Path,
    query_timeframe: str | None = None,
    primary_tag_keys: list[str] | None = None,
) -> RuleOutcome:
    cls = classify(rule)
    entity_key, span_key = compute_keys(rule)

    translations: list[dict[str, Any]] = []
    unmigratable = 0

    for cond in rule.conditions:
        t = translate_condition(cond)
        translations.append(_translation_to_dict(cond, t, classification=cls))
        if not t.ok:
            unmigratable += 1

    mz_dict: dict[str, Any] | None = None
    if rule.managementZones:
        mz = translate_management_zones(list(rule.managementZones))
        mz_dict = {
            "field": "managementZones",
            "values": list(rule.managementZones),
            "side": "entity",
            "phase3_status": mz.phase3_status,
            "dql": mz.dql,
            "unmigratable_reason": mz.unmigratable_reason,
        }
        if not mz.ok:
            unmigratable += 1

    query_result: DqlQueryResult | None = None
    if dql is not None and unmigratable == 0:
        query_result = execute_dql_queries(
            rule=rule,
            classification=cls,
            entity_key=entity_key,
            span_key=span_key,
            dql=dql,
            cache_dir=cache_dir,
            query_timeframe=query_timeframe,
            primary_tag_keys=primary_tag_keys,
        )

    return RuleOutcome(
        rule_id=rule.id,
        naming_pattern=rule.namingPattern,
        enabled=rule.enabled,
        case=cls.case,
        is_deprecated=cls.is_deprecated,
        entity_key=entity_key,
        span_key=span_key,
        translations=translations,
        management_zones_translation=mz_dict,
        unmigratable_count=unmigratable,
        query_result=query_result,
    )


def _translation_to_dict(
    cond: Condition, t: Translation, *, classification: Classification
) -> dict[str, Any]:
    side, status = _side_and_status(cond, classification)
    composites = _composite_attributes(cond)
    return {
        # A primary-tag condition is identified per tag key, so that a surviving
        # condition on one key does not suppress candidates on another.
        "attribute": composites[0] if len(composites) == 1 else cond.attribute,
        "api_attributes": composites or [cond.attribute],
        "operator": cond.comparisonInfo.comparison,
        "negate": cond.comparisonInfo.negate,
        "side": side,  # entity | span | unknown
        "phase3_status": t.phase3_status,
        "lifecycle": status,  # surviving | deprecated
        "fetch_source": fetch_source_for(cond),
        "dql": t.dql,
        "unmigratable_reason": t.unmigratable_reason,
    }


def _composite_attributes(cond: Condition) -> list[str]:
    """Composite ``PROCESS_GROUP_TAG@<tag_key>`` identities for a primary-tag
    condition, one per primary tag key; empty for any other condition.
    """
    if not is_primary_tag_condition(cond):
        return []
    keys = {
        key for key, _ in tag_pairs(cond.comparisonInfo) if is_primary_tag_key(key)
    }
    return [compose_attribute(cond.attribute, key) for key in sorted(keys)]


def _side_and_status(
    cond: Condition, cls: Classification
) -> tuple[str, str]:
    if cond in cls.surviving_entity:
        return "entity", "surviving"
    if cond in cls.deprecated_entity:
        return "entity", "deprecated"
    if cond in cls.surviving_span:
        return "span", "surviving"
    if cond in cls.deprecated_span:
        return "span", "deprecated"
    return "unknown", "surviving"


def _write_sidecar(derived_dir: Path, o: RuleOutcome) -> None:
    payload = {
        "rule_id": o.rule_id,
        "naming_pattern": o.naming_pattern,
        "enabled": o.enabled,
        "case": o.case,
        "is_deprecated": o.is_deprecated,
        "cache_keys": {"entity": o.entity_key, "span": o.span_key},
        "management_zones": o.management_zones_translation,
        "conditions": o.translations,
        "unmigratable_count": o.unmigratable_count,
        "query_result": _query_result_to_dict(o.query_result),
        "span_fallback_result": _query_result_to_dict(o.span_fallback_result),
    }
    out = derived_dir / f"{o.rule_id}.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=False))


def _run_candidate_scoring(
    outcome: RuleOutcome,
    *,
    cache_dir: Path,
    derived_dir: Path,
    force_full: bool = False,
) -> CandidateScoringResult:
    """Run candidate building and substring augmentation.

    ``force_full=True`` overrides the case-A entity-only mode, used when the
    Case A span fallback (A.2) has already written span cache files.
    """
    effective_mode = "full" if force_full else None
    try:
        artifact = build_candidates(
            rule_id=outcome.rule_id,
            case=outcome.case,
            entity_key=outcome.entity_key,
            span_key=outcome.span_key,
            cache_dir=cache_dir,
            derived_dir=derived_dir,
            mode=effective_mode,
        )
        artifact = augment_candidates(
            rule_id=outcome.rule_id,
            case=outcome.case,
            entity_key=outcome.entity_key,
            span_key=outcome.span_key,
            cache_dir=cache_dir,
            derived_dir=derived_dir,
            mode=effective_mode,
            # Pass the just-built artifact via an in-memory loader so we don't
            # need to write/re-read it in between.
            _io_load=_make_candidates_io_loader(derived_dir, outcome.rule_id, artifact),
        )
        out_path = write_candidates(derived_dir, artifact)
        return CandidateScoringResult(
            candidates_path=out_path.name,
            entity_candidate_count=len(artifact.get("entity_candidates", [])),
            span_candidate_count=len(artifact.get("span_candidates", [])),
        )
    except UnmigratableRuleError as exc:
        return CandidateScoringResult(
            candidates_path="",
            entity_candidate_count=0,
            span_candidate_count=0,
            failure_reason=f"unmigratable_rule: {exc}",
        )
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return CandidateScoringResult(
            candidates_path="",
            entity_candidate_count=0,
            span_candidate_count=0,
            failure_reason=f"candidate_scoring_error: {exc}",
        )


def _make_candidates_io_loader(_derived_dir: Path, rule_id: str, built_artifact: dict[str, Any]):
    """Return an _io_load for augment_candidates that serves the in-memory artifact
    for the ``_candidates.json`` file, falling through to disk for everything else."""
    candidates_name = f"{rule_id}_candidates.json"

    def _load(path: Path) -> Any:
        if path.name == candidates_name:
            return built_artifact
        return json.loads(path.read_text(encoding="utf-8"))

    return _load


def _should_verify_candidates(outcome: RuleOutcome) -> bool:
    """Return False when there is nothing to verify.

    For Case A with a span fallback: skip verification if the fallback query
    failed or if candidate scoring produced zero candidates — running the
    overselect loop on an empty artifact would be meaningless and would likely error.
    """
    if outcome.case != "A" or outcome.span_fallback_result is None:
        return True  # all other cases / early-exit path: use normal gating
    if not outcome.span_fallback_result.success:
        return False
    c = outcome.candidate_result
    return c is not None and (c.entity_candidate_count > 0 or c.span_candidate_count > 0)


def _run_span_fallback_query(
    outcome: RuleOutcome,
    *,
    dql: DqlClient,
    cache_dir: Path,
    query_timeframe: str | None,
    primary_tag_keys: list[str] | None = None,
) -> DqlQueryResult:
    """Thin wrapper around execute_span_fallback_query with uniform exception handling."""
    try:
        return execute_span_fallback_query(
            rule_id=outcome.rule_id,
            entity_key=outcome.entity_key,
            span_key=outcome.span_key,
            dql=dql,
            cache_dir=cache_dir,
            query_timeframe=query_timeframe,
            primary_tag_keys=primary_tag_keys,
        )
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return DqlQueryResult(
            rule_id=outcome.rule_id,
            case="A",
            success=False,
            failure_reason=f"span_fallback_error: {exc}",
        )


def _run_candidate_verification(  # pylint: disable=too-many-arguments
    outcome: RuleOutcome,
    *,
    cache_dir: Path,
    derived_dir: Path,
    dql: DqlClient,
    effective_span_key: str | None,
    query_timeframe: str | None = None,
    effective_timeframe: str | None = None,
) -> VerificationResult:
    """Run the overselect verification loop.

    ``effective_span_key=None`` activates the entity-only verification path in
    the overselect loop (Case A early exit).
    """
    try:
        candidates_path = derived_dir / f"{outcome.rule_id}_candidates.json"
        artifact = json.loads(candidates_path.read_text(encoding="utf-8"))

        return run_overselect_loop(
            rule_id=outcome.rule_id,
            artifact=artifact,
            entity_key=outcome.entity_key,
            span_key=effective_span_key,
            cache_dir=cache_dir,
            derived_dir=derived_dir,
            dql_execute=dql.execute,
            query_timeframe=effective_timeframe or query_timeframe,
        )
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        return VerificationResult(
            rule_id=outcome.rule_id,
            status="no_replacement",
            failure_reason=f"verification_error: {exc}",
        )


def _run_report_generation(
    outcome: RuleOutcome,
    *,
    derived_dir: Path,
    report_dir: Path,
    raw_rule: dict[str, Any] | None,
) -> str | None:
    """Build and write the per-rule report artifact."""
    try:
        report = build_rule_report(
            outcome.rule_id,
            derived_dir=derived_dir,
            raw_rule=raw_rule,
        )
        out_path = write_rule_report(report_dir, report)
        return out_path.name
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        # Non-fatal — report generation failure does not abort the run.
        return f"report_error: {exc}"


def _query_result_to_dict(s: DqlQueryResult | None) -> dict[str, Any] | None:
    if s is None:
        return None
    return {
        "success": s.success,
        "failure_reason": s.failure_reason,
        "files_written": list(s.files_written),
        "s_super_count": s.s_super_count,
        "s_orig_count": s.s_orig_count,
        "e_orig_count": s.e_orig_count,
        "queries": list(s.queries),
        "effective_timeframe": s.effective_timeframe,
        "span_retries": s.span_retries,
    }


def _build_summary(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    outcomes: list[RuleOutcome],
    *,
    cfg: AppConfig,
    inspected: int,
    skipped_no_deprecated: int,
    skipped_rules: list[dict[str, Any]],
) -> dict[str, Any]:
    case_counts: dict[str, int] = {"A": 0, "C": 0}
    fully_migratable = 0
    partial = 0
    fully_unmigratable = 0
    query_success = 0
    query_failed = 0
    query_failures: dict[str, int] = {}
    candidates_success = 0
    candidates_failed = 0
    candidates_failures: dict[str, int] = {}
    verification_exact = 0
    verification_no_replacement = 0
    verification_failed = 0
    verification_failures: dict[str, int] = {}
    report_written = 0
    report_failed = 0
    for o in outcomes:
        case_counts[o.case] += 1
        total = len(o.translations) + (1 if o.management_zones_translation else 0)
        if total == 0:
            continue
        if o.unmigratable_count == 0:
            fully_migratable += 1
        elif o.unmigratable_count == total:
            fully_unmigratable += 1
        else:
            partial += 1
        if o.query_result is not None:
            if o.query_result.success:
                query_success += 1
            else:
                query_failed += 1
                key = (o.query_result.failure_reason or "unknown").split(":", 1)[0]
                query_failures[key] = query_failures.get(key, 0) + 1
        if o.candidate_result is not None:
            if o.candidate_result.success:
                candidates_success += 1
            else:
                candidates_failed += 1
                key = (o.candidate_result.failure_reason or "unknown").split(":", 1)[0]
                candidates_failures[key] = candidates_failures.get(key, 0) + 1
        if o.verification_result is not None:
            if o.verification_result.status in ("exact_match", "exact_match_after_under_select_retry"):
                verification_exact += 1
            elif o.verification_result.status == "no_replacement":
                if o.verification_result.failure_reason and o.verification_result.failure_reason.startswith("verification_error"):
                    verification_failed += 1
                    key = (o.verification_result.failure_reason or "unknown").split(":", 1)[0]
                    verification_failures[key] = verification_failures.get(key, 0) + 1
                else:
                    verification_no_replacement += 1
        if o.report_path is not None:
            if o.report_path.startswith("report_error"):
                report_failed += 1
            else:
                report_written += 1
    return {
        "tenant": {"classic": cfg.classic_url, "platform": cfg.platform_url},
        "output_dir": str(cfg.output_dir),
        "inspected_rules": inspected,
        "skipped_no_deprecated": skipped_no_deprecated,
        "skipped_rules": skipped_rules,
        "migrating_rules": len(outcomes),
        "case_counts": case_counts,
        "translation_status": {
            "fully_migratable": fully_migratable,
            "partial": partial,
            "fully_unmigratable": fully_unmigratable,
        },
        "dql_queries": {
            "success": query_success,
            "failed": query_failed,
            "failure_buckets": query_failures,
            "span_retries_triggered": sum(
                1 for o in outcomes
                if o.query_result and o.query_result.span_retries > 0
            ),
        },
        "candidate_scoring": {
            "success": candidates_success,
            "failed": candidates_failed,
            "failure_buckets": candidates_failures,
        },
        "verification": {
            "exact_match": verification_exact,
            "no_replacement": verification_no_replacement,
            "failed": verification_failed,
            "failure_buckets": verification_failures,
        },
        "report_generation": {
            "written": report_written,
            "failed": report_failed,
        },
        "rules": [
            {
                "id": o.rule_id,
                "case": o.case,
                "unmigratable_count": o.unmigratable_count,
                "entity_key": o.entity_key,
                "span_key": o.span_key,
                "query_success": (o.query_result.success if o.query_result else None),
                "query_failure_reason": (
                    o.query_result.failure_reason if o.query_result else None
                ),
                "s_super_count": (o.query_result.s_super_count if o.query_result else None),
                "s_orig_count": (o.query_result.s_orig_count if o.query_result else None),
                "e_orig_count": (o.query_result.e_orig_count if o.query_result else None),
                "candidates_success": (o.candidate_result.success if o.candidate_result else None),
                "candidates_failure_reason": (o.candidate_result.failure_reason if o.candidate_result else None),
                "entity_candidate_count": (o.candidate_result.entity_candidate_count if o.candidate_result else None),
                "span_candidate_count": (o.candidate_result.span_candidate_count if o.candidate_result else None),
                "verification_status": (o.verification_result.status if o.verification_result else None),
                "verification_failure_reason": (o.verification_result.failure_reason if o.verification_result else None),
                "verification_iterations": (o.verification_result.iterations if o.verification_result else None),
                "verification_negations": (o.verification_result.negations_applied if o.verification_result else None),
                "verification_demotions": (o.verification_result.demotions_applied if o.verification_result else None),
                "report_path": o.report_path,
            }
            for o in outcomes
        ],
    }


def _write_summary(report_dir: Path, summary: dict[str, Any]) -> None:
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2))


__all__ = ["RuleOutcome", "CandidateScoringResult", "run"]
