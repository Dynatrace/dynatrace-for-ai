"""DQL query executor — runs the entity and span queries for each rule.

Dispatches by case:

- **Case A** — A.1 entity query (1 or 2 queries if PG branching). Writes
  ``cache/<entity_key>_s_super.json``. No span query in this phase; A.2 is a
  Step-4 concern.
- **Case C** — C.1 entity query → derive ``S_super_orig`` → C.2 span query
  constrained to ``S_super_orig``. Writes ``cache/<entity_key>_s_super.json``,
  ``cache/<span_key>_e_orig.json`` and ``cache/<span_key>_s_orig.json``.

Read-limit and other DQL failures abort the rule and surface as a
``failure_reason`` so the orchestrator can record them and move on.

Within a run, the first rule of a given cache key writes a ``<key>_result.json``
sidecar; a later rule with the same key reuses that outcome instead of
re-issuing identical DQL. Scope is within-run only — the workdir is timestamped
per run, so each run starts with an empty cache.
"""

from __future__ import annotations

import json
import re as _re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .clients.dql import DqlClient, DqlError, DqlReadLimitError
from .queries.entity import (
    PG_IDS_PLACEHOLDER,
    EntityQueryPlan,
    build_entity_plan,
)
from .queries.span import build_span_query
from .rules.classifier import Classification
from .rules.models import Rule
from .rules.translator import (
    fetch_source_for,
    translate_condition,
    translate_management_zones,
)


_STEP_MINUTES: int = 360  # 6 h gap between retry windows
_MAX_RETRIES: int = 3


@dataclass(frozen=True)
class DqlQueryResult:
    """DQL query execution result for one rule."""

    # pylint: disable=too-many-instance-attributes
    rule_id: str
    case: str
    success: bool
    failure_reason: str | None
    files_written: list[str] = field(default_factory=list)
    s_super_count: int | None = None
    s_orig_count: int | None = None
    e_orig_count: int | None = None
    queries: list[dict[str, Any]] = field(default_factory=list)
    effective_timeframe: str | None = None  # window that produced s_orig; None on failure
    span_retries: int = 0                   # retry attempts consumed (0 = first window worked)


def execute_dql_queries(
    *,
    rule: Rule,
    classification: Classification,
    entity_key: str,
    span_key: str,
    dql: DqlClient,
    cache_dir: Path,
    query_timeframe: str | None = None,
    primary_tag_keys: list[str] | None = None,
) -> DqlQueryResult:
    """Execute entity and span queries for one rule. Always writes whatever it
    can; failure_reason is set on the first error."""
    # pylint: disable=too-many-arguments,too-many-locals,too-many-return-statements,too-many-branches
    case = classification.case
    queries_log: list[dict[str, Any]] = []
    files: list[str] = []

    # Translate everything once.
    svc_filters, pg_filters = _entity_fragments(classification)
    span_filters = _span_fragments(classification)
    mz_dql = (
        translate_management_zones(list(rule.managementZones)).dql
        if rule.managementZones
        else None
    )

    try:
        if case == "A":
            cached = _load_cached_result(cache_dir, entity_key, rule.id)
            if cached is not None:
                return cached
            s_super = _run_entity(
                dql,
                build_entity_plan(
                    service_side_filters=svc_filters,
                    pg_side_filters=pg_filters,
                    management_zones_dql=mz_dql,
                    timeframe=query_timeframe,
                ),
                queries_log,
            )
            path = _write(cache_dir, f"{entity_key}_s_super.json", s_super)
            files.append(path.name)
            if not s_super:
                return _store(cache_dir, entity_key, DqlQueryResult(
                    rule_id=rule.id,
                    case=case,
                    success=False,
                    failure_reason="rule_matching_no_data",
                    files_written=files,
                    s_super_count=0,
                    queries=queries_log,
                ))
            return _store(cache_dir, entity_key, DqlQueryResult(
                rule_id=rule.id,
                case=case,
                success=True,
                failure_reason=None,
                files_written=files,
                s_super_count=len(s_super),
                queries=queries_log,
            ))

        if case == "C":
            cached = _load_cached_result(cache_dir, span_key, rule.id)
            if cached is not None:
                return cached
            # C.1 — entity query.
            s_super = _run_entity(
                dql,
                build_entity_plan(
                    service_side_filters=svc_filters,
                    pg_side_filters=pg_filters,
                    management_zones_dql=mz_dql,
                    timeframe=query_timeframe,
                ),
                queries_log,
            )
            files.append(_write(cache_dir, f"{entity_key}_s_super.json", s_super).name)
            s_super_ids = _distinct(s_super, "id")

            # C.2 — span query constrained to S_super_orig.
            if s_super_ids:
                e_rows = _run_span(
                    dql,
                    build_span_query(
                        span_filters=span_filters,
                        service_id_constraint=s_super_ids,
                        window=query_timeframe,
                        primary_tag_keys=primary_tag_keys,
                    ),
                    queries_log,
                )
            else:
                e_rows = []
            s_orig = _distinct(e_rows, "dt.smartscape.service")
            files.append(_write(cache_dir, f"{span_key}_e_orig.json", e_rows).name)
            files.append(_write(cache_dir, f"{span_key}_s_orig.json", s_orig).name)

            if not s_orig and s_super_ids:
                # Retry with time-shifted windows before giving up.
                retried_window, retried_rows, retries_used = _span_retry(
                    dql, span_filters, s_super_ids, queries_log,
                    original_window=query_timeframe,
                    primary_tag_keys=primary_tag_keys,
                )
                if retried_rows is not None:
                    e_rows = retried_rows
                    s_orig = _distinct(e_rows, "dt.smartscape.service")
                    _write(cache_dir, f"{span_key}_e_orig.json", e_rows)
                    _write(cache_dir, f"{span_key}_s_orig.json", s_orig)
                    effective_tf: str | None = retried_window
                    span_retries = retries_used
                else:
                    return _store(cache_dir, span_key, DqlQueryResult(
                        rule_id=rule.id,
                        case=case,
                        success=False,
                        failure_reason="rule_matching_no_data",
                        files_written=files,
                        s_super_count=len(s_super),
                        s_orig_count=0,
                        e_orig_count=len(e_rows),
                        queries=queries_log,
                        span_retries=_MAX_RETRIES,
                    ))
            elif not s_orig:
                return _store(cache_dir, span_key, DqlQueryResult(
                    rule_id=rule.id,
                    case=case,
                    success=False,
                    failure_reason="rule_matching_no_data",
                    files_written=files,
                    s_super_count=len(s_super),
                    s_orig_count=0,
                    e_orig_count=len(e_rows),
                    queries=queries_log,
                ))
            else:
                effective_tf = query_timeframe
                span_retries = 0

            return _store(cache_dir, span_key, DqlQueryResult(
                rule_id=rule.id,
                case=case,
                success=True,
                failure_reason=None,
                files_written=files,
                s_super_count=len(s_super),
                s_orig_count=len(s_orig),
                e_orig_count=len(e_rows),
                queries=queries_log,
                effective_timeframe=effective_tf,
                span_retries=span_retries,
            ))

    except DqlReadLimitError as exc:
        return DqlQueryResult(
            rule_id=rule.id,
            case=case,
            success=False,
            failure_reason=f"read_limit_hit: {exc}",
            files_written=files,
            queries=queries_log,
        )
    except DqlError as exc:
        return DqlQueryResult(
            rule_id=rule.id,
            case=case,
            success=False,
            failure_reason=f"dql_error: {exc}",
            files_written=files,
            queries=queries_log,
        )

    raise ValueError(f"unhandled case: {case!r}")


def execute_span_fallback_query(  # pylint: disable=too-many-arguments
    *,
    rule_id: str,
    entity_key: str,
    span_key: str,
    dql: DqlClient,
    cache_dir: Path,
    query_timeframe: str | None = None,
    primary_tag_keys: list[str] | None = None,
) -> DqlQueryResult:
    """Case A.2 span fallback — span query for Case A rules that had no entity candidates.

    Reads the already-written ``{entity_key}_s_super.json`` to get S_orig service
    IDs, then runs a no-condition span query constrained to those IDs.  S_orig is
    re-derived from the span results (services without endpoint spans cannot be
    targeted by request naming rules, consistent with Cases B and C).
    """
    queries_log: list[dict[str, Any]] = []
    files: list[str] = []

    try:
        entity_rows: list[dict[str, Any]] = json.loads(
            (cache_dir / f"{entity_key}_s_super.json").read_text(encoding="utf-8")
        )
        s_orig_ids = [r["id"] for r in entity_rows if r.get("id")]

        if not s_orig_ids:
            return DqlQueryResult(
                rule_id=rule_id,
                case="A",
                success=False,
                failure_reason="a2_no_s_orig",
                files_written=files,
                s_super_count=0,
                queries=queries_log,
            )

        e_rows = _run_span(
            dql,
            build_span_query(
                span_filters=[],
                service_id_constraint=s_orig_ids,
                window=query_timeframe,
                primary_tag_keys=primary_tag_keys,
            ),
            queries_log,
        )
        s_orig = _distinct(e_rows, "dt.smartscape.service")
        files.append(_write(cache_dir, f"{span_key}_e_orig.json", e_rows).name)
        files.append(_write(cache_dir, f"{span_key}_s_orig.json", s_orig).name)

        if not s_orig:
            return DqlQueryResult(
                rule_id=rule_id,
                case="A",
                success=False,
                failure_reason="a2_no_endpoint_spans",
                files_written=files,
                s_super_count=len(s_orig_ids),
                s_orig_count=0,
                e_orig_count=len(e_rows),
                queries=queries_log,
            )

        return DqlQueryResult(
            rule_id=rule_id,
            case="A",
            success=True,
            failure_reason=None,
            files_written=files,
            s_super_count=len(s_orig_ids),
            s_orig_count=len(s_orig),
            e_orig_count=len(e_rows),
            queries=queries_log,
        )

    except DqlReadLimitError as exc:
        return DqlQueryResult(
            rule_id=rule_id,
            case="A",
            success=False,
            failure_reason=f"read_limit_hit: {exc}",
            files_written=files,
            queries=queries_log,
        )
    except DqlError as exc:
        return DqlQueryResult(
            rule_id=rule_id,
            case="A",
            success=False,
            failure_reason=f"dql_error: {exc}",
            files_written=files,
            queries=queries_log,
        )


# ---------- internals ----------------------------------------------------- #


def _entity_fragments(cls: Classification) -> tuple[list[str], list[str]]:
    """Split entity conditions by fetch_source and translate.

    Untranslatable conditions are silently dropped here — they're already
    captured in the per-rule sidecar with their unmigratable_reason.
    """
    svc: list[str] = []
    pg: list[str] = []
    for cond in cls.entity_conditions:
        t = translate_condition(cond)
        if t.ok:
            assert t.dql is not None
            src = fetch_source_for(cond)
            (svc if src == "dt.entity.service" else pg).append(t.dql)
    return svc, pg


def _span_fragments(cls: Classification) -> list[str]:
    out: list[str] = []
    for cond in cls.span_conditions:
        t = translate_condition(cond)
        if t.ok:
            assert t.dql is not None
            out.append(t.dql)
    return out


def _run_entity(
    dql: DqlClient, plan: EntityQueryPlan, log: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Execute an entity plan, handling PG → service substitution."""
    if plan.pg_query is None:
        rows, grail = dql.execute_with_meta(plan.service_query)
        log.append({"role": "entity_service", "rows": len(rows), "grail_metadata": grail})
        return rows

    pg_rows, pg_grail = dql.execute_with_meta(plan.pg_query)
    log.append({"role": "entity_pg", "rows": len(pg_rows), "grail_metadata": pg_grail})
    pg_ids = [r.get("id") for r in pg_rows if r.get("id")]
    if not pg_ids:
        # No PGs matched → service query would return nothing anyway.
        return []
    pg_ids_dql = "{" + ", ".join(f'"{i}"' for i in pg_ids) + "}"
    service_query = plan.service_query.replace(PG_IDS_PLACEHOLDER, pg_ids_dql)
    rows, grail = dql.execute_with_meta(service_query)
    log.append({"role": "entity_service_after_pg", "rows": len(rows), "grail_metadata": grail})
    return rows


def _run_span(
    dql: DqlClient, query: str, log: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows, grail = dql.execute_with_meta(query)
    log.append({"role": "span", "rows": len(rows), "grail_metadata": grail})
    return rows


def _distinct(rows: list[dict[str, Any]], field_name: str) -> list[str]:
    """Stable-sorted distinct non-empty string values for a field."""
    seen: set[str] = set()
    for r in rows:
        v = r.get(field_name)
        if isinstance(v, str) and v:
            seen.add(v)
    return sorted(seen)


def _write(cache_dir: Path, name: str, payload: Any) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def _store(cache_dir: Path, key: str, result: DqlQueryResult) -> DqlQueryResult:
    """Persist a result-meta sidecar keyed by ``key`` so a later rule with the
    same cache key can reuse this outcome without re-querying, then return it.

    Only the scalar fields are stored — the bulky row payloads already live in
    the data artifacts named in ``files_written``.
    """
    _write(
        cache_dir,
        f"{key}_result.json",
        {
            "case": result.case,
            "success": result.success,
            "failure_reason": result.failure_reason,
            "files_written": result.files_written,
            "s_super_count": result.s_super_count,
            "s_orig_count": result.s_orig_count,
            "e_orig_count": result.e_orig_count,
            "effective_timeframe": result.effective_timeframe,
            "span_retries": result.span_retries,
        },
    )
    return result


def _load_cached_result(cache_dir: Path, key: str, rule_id: str) -> DqlQueryResult | None:
    """Return a prior identical-shape rule's result for reuse, or ``None``.

    Reuse is within-run only: the workdir is timestamped per run, so a populated
    sidecar means an earlier rule with the same cache key already ran this run.
    The result is reusable only while the data artifacts it points at survive.
    """
    path = cache_dir / f"{key}_result.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for name in data.get("files_written", []):
        if not (cache_dir / name).exists():
            return None
    return DqlQueryResult(
        rule_id=rule_id,
        case=data["case"],
        success=data["success"],
        failure_reason=data.get("failure_reason"),
        files_written=list(data.get("files_written", [])),
        s_super_count=data.get("s_super_count"),
        s_orig_count=data.get("s_orig_count"),
        e_orig_count=data.get("e_orig_count"),
        queries=[{"role": "cache_hit", "key": key}],
        effective_timeframe=data.get("effective_timeframe"),
        span_retries=data.get("span_retries", 0),
    )


# ---------- span retry helpers --------------------------------------------- #


def _parse_window_minutes(timeframe: str | None) -> int:
    """Extract the window duration in minutes from a DQL timeframe string.

    Parses the ``from:now()-<dur>`` prefix, handling ``Xh``, ``Xm``, ``XhYm``.
    Falls back to 120 (2 h) on any parse failure.
    """
    if not timeframe:
        return 120
    m = _re.search(r"now\(\)-(?:(\d+)h)?(?:(\d+)m)?", timeframe)
    if not m or (m.group(1) is None and m.group(2) is None):
        return 120
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    total = hours * 60 + minutes
    return total if total > 0 else 120


def _mins_to_dql(minutes: int) -> str:
    """Convert a minute count to a compact DQL duration string.

    Examples: 120 → ``2h``, 90 → ``1h30m``, 30 → ``30m``.
    """
    h, m = divmod(minutes, 60)
    return ("" if h == 0 else f"{h}h") + ("" if m == 0 else f"{m}m")


def _build_retry_window(duration_min: int, retry_n: int) -> str:
    """Return the Nth retry window string (``retry_n`` >= 1).

    The window size matches ``duration_min``; each step shifts 6 h back.
    """
    end_min = _STEP_MINUTES * retry_n
    start_min = duration_min + end_min
    to_clause = f", to:now()-{_mins_to_dql(end_min)}"
    return f"from:now()-{_mins_to_dql(start_min)}{to_clause}"


def _span_retry(
    dql: DqlClient,
    span_filters: list[str],
    s_super_ids: list[str],
    log: list[dict[str, Any]],
    *,
    original_window: str | None,
    primary_tag_keys: list[str] | None = None,
) -> tuple[str | None, list[dict[str, Any]] | None, int]:
    """Try time-shifted windows until one returns span results.

    Returns ``(window, rows, attempts_used)`` on the first hit, or
    ``(None, None, _MAX_RETRIES)`` when all retries are exhausted.
    """
    duration_min = _parse_window_minutes(original_window)
    for n in range(1, _MAX_RETRIES + 1):
        window = _build_retry_window(duration_min, n)
        rows = _run_span(
            dql,
            build_span_query(
                span_filters=span_filters,
                service_id_constraint=s_super_ids,
                window=window,
                primary_tag_keys=primary_tag_keys,
            ),
            log,
        )
        if _distinct(rows, "dt.smartscape.service"):
            return window, rows, n
    return None, None, _MAX_RETRIES


__all__ = ["DqlQueryResult", "execute_dql_queries", "execute_span_fallback_query"]
