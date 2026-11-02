"""In-process overselect verification loop.

Drives the verification state machine to a terminal verdict synchronously,
executing DQL queries via the injected ``DqlClient`` and caching every result
to ``cache/`` so re-runs are idempotent.

Terminal verdicts
-----------------
- ``exact_match``                          — candidates select exactly S_orig/E_orig
- ``exact_match_after_under_select_retry`` — exact after one window-shifted retry
- ``no_replacement``                        — over-select could not be resolved

The written artifact is ``derived/<rule_id>_verdict.json``.

Two-phase verification
----------------------
When a span_key is present (span data available) verification runs in two phases:

  1. **Entity pre-phase** — runs an entity query using only entity-level fragments
     (``entity_candidates`` + ``surviving`` where ``level == "entity"``).  Produces
     a ``service_filter`` (set of service IDs) that constrains Phase 2.

  2. **Span phase** — runs span queries using only span-level fragments
     (``span_candidates`` + ``surviving`` where ``level == "span"``) plus an
     optional ``in(dt.smartscape.service, …)`` service filter from Phase 1.

When no span_key is present (entity-only rule), only the entity loop runs and
its result is the final verdict.

Fragment routing
----------------
| Source                                    | Entity pre-phase | Span phase        |
|-------------------------------------------|-----------------|-------------------|
| surviving where level == "entity"         | yes             | no                |
| surviving where level == "span"           | no              | yes               |
| entity_candidates                         | yes             | no                |
| span_candidates                           | no              | yes               |
| entity negations                          | yes             | no                |
| span negations                            | no              | yes               |
| in(dt.smartscape.service, service_filter) | no              | yes (when not None)|
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..analysis.candidates import _quote, is_good_candidate  # noqa: PLC2701
from ..queries.verification import (
    build_entity_verification_query,
    build_span_verification_query,
    verification_cache_key,
)
from ..rules.mapping import ConditionMapping, load_mapping

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SPAN_WINDOW_FROM = "now()-2h"
DEFAULT_SPAN_WINDOW_TO = "now()"
DEFAULT_MAX_NEGATIONS_PER_ATTRIBUTE = 5
DEFAULT_MAX_UNDER_SELECT_RETRIES = 1

# Structural keys that appear in verification result rows but are never useful
# as negation axes.
_STRUCTURAL_KEYS: frozenset[str] = frozenset(
    {"id", "entity.name", "dt.smartscape.service", "endpoint.name", "span_count"}
)

_WINDOW_RE = re.compile(r"^now\(\)-(\d+)(h|m|s|d)$")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class VerificationResult:
    """Verdict produced by the overselect verification loop."""

    rule_id: str
    status: str  # exact_match | exact_match_after_under_select_retry | no_replacement
    failure_reason: str | None = None
    iterations: int = 0
    negations_applied: int = 0
    entity_negations_applied: int = 0
    entity_phase_outcome: str = "skipped"
    demotions_applied: int = 0
    suboptimal_used: int = 0
    verdict_path: str = ""
    final_conditions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True when status is an exact-match variant."""
        return self.status in (
            "exact_match",
            "exact_match_after_under_select_retry",
        )


# ---------------------------------------------------------------------------
# Fragment routing helpers
# ---------------------------------------------------------------------------


def _entity_frags(artifact: dict[str, Any]) -> list[str]:
    """Positive DQL fragments that belong to the entity pre-phase."""
    frags: list[str] = []
    for c in artifact.get("surviving_original_conditions", []):
        if c.get("level", "entity") == "entity":
            frag = c.get("dql_fragment")
            if frag:
                frags.append(frag)
    for c in artifact.get("entity_candidates", []):
        frag = c.get("dql_fragment")
        if frag:
            frags.append(frag)
    return frags


def _span_frags(artifact: dict[str, Any]) -> list[str]:
    """Positive DQL fragments that belong to the span phase."""
    frags: list[str] = []
    for c in artifact.get("surviving_original_conditions", []):
        if c.get("level", "entity") == "span":
            frag = c.get("dql_fragment")
            if frag:
                frags.append(frag)
    for c in artifact.get("span_candidates", []):
        frag = c.get("dql_fragment")
        if frag:
            frags.append(frag)
    return frags


def _negation_fragment(dql_key: str, value: Any) -> str:
    return f"not {dql_key} == {_quote(value)}"


def _service_filter_fragment(service_ids: set[str]) -> str:
    svc_list = ", ".join(f'toSmartscapeId({_quote(sid)})' for sid in sorted(service_ids))
    return f"in(dt.smartscape.service, {{{svc_list}}})"


# ---------------------------------------------------------------------------
# Orig-set loading
# ---------------------------------------------------------------------------


def _load_entity_orig_set(cache_dir: Path, entity_key: str) -> set[str]:
    rows: list[dict[str, Any]] = json.loads(
        (cache_dir / f"{entity_key}_s_super.json").read_text()
    )
    return {r["id"] for r in rows if "id" in r}


def _load_span_orig_sets(
    cache_dir: Path, span_key: str
) -> tuple[set[str], set[tuple[str, str]]]:
    s_orig_list: list[str] = json.loads(
        (cache_dir / f"{span_key}_s_orig.json").read_text()
    )
    e_rows: list[dict[str, Any]] = json.loads(
        (cache_dir / f"{span_key}_e_orig.json").read_text()
    )
    s_orig: set[str] = set(s_orig_list)
    e_orig: set[tuple[str, str]] = set()
    for r in e_rows:
        sid = r.get("dt.smartscape.service")
        ep = r.get("endpoint.name")
        if sid is not None and ep is not None:
            e_orig.add((sid, ep))
    return s_orig, e_orig


# ---------------------------------------------------------------------------
# Set extraction from DQL rows
# ---------------------------------------------------------------------------


def _extract_s_cand(rows: list[dict[str, Any]], phase: str) -> set[str]:
    if phase == "entity":
        return {r["id"] for r in rows if "id" in r}
    return {r["dt.smartscape.service"] for r in rows if "dt.smartscape.service" in r}


def _extract_e_cand(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for r in rows:
        sid = r.get("dt.smartscape.service")
        ep = r.get("endpoint.name")
        if sid is not None and ep is not None:
            result.add((sid, ep))
    return result


# ---------------------------------------------------------------------------
# Outcome classification
# ---------------------------------------------------------------------------


def _classify(
    s_cand: set[str],
    e_cand: set[tuple[str, str]] | None,
    s_orig: set[str],
    e_orig: set[tuple[str, str]] | None,
    phase: str,
) -> str:
    """Returns 'exact', 'over', or 'under'. Never called with empty s_cand (0-row guard)."""
    if phase == "entity":
        if s_cand == s_orig:
            return "exact"
        return "under" if s_cand < s_orig else "over"
    # span
    s_exact = s_cand == s_orig
    e_exact = e_cand == e_orig
    if s_exact and e_exact:
        return "exact"
    assert e_cand is not None
    assert e_orig is not None
    s_under = s_cand <= s_orig
    e_under = e_cand <= e_orig
    if s_under and e_under:
        return "under"
    return "over"


# ---------------------------------------------------------------------------
# Greedy negation (single-pass set-cover)
# ---------------------------------------------------------------------------


def _find_negations(
    rows: list[dict[str, Any]],
    s_orig: set[str],
    e_orig: set[tuple[str, str]] | None,
    phase: str,
    negation_counts: dict[str, int],
    max_per_attribute: int,
    excluded_dql_keys: set[str],
    *,
    forbidden: frozenset[str],
    dql_to_api: dict[str, str],
) -> tuple[list[dict[str, Any]], bool]:
    """Greedy set-cover over the over-select rows.

    Returns (chosen_negations, fully_covered).
    """
    # pylint: disable=too-many-locals,too-many-branches,too-many-statements

    def _is_legit(row: dict[str, Any]) -> bool:
        if phase == "entity":
            return row.get("id") in s_orig
        sid = row.get("dt.smartscape.service")
        ep = row.get("endpoint.name")
        return sid in s_orig and (sid, ep) in (e_orig or set())

    over_rows = [r for r in rows if not _is_legit(r)]
    legit_rows = [r for r in rows if _is_legit(r)]

    if not over_rows:
        return [], True

    legit_values: dict[str, set[Any]] = {}
    for r in legit_rows:
        for k, v in r.items():
            if k in _STRUCTURAL_KEYS or v is None:
                continue
            try:
                legit_values.setdefault(k, set()).add(v)
            except TypeError:
                pass

    coverage: dict[tuple[str, Any], set[int]] = {}
    for i, r in enumerate(over_rows):
        for k, v in r.items():
            if k in _STRUCTURAL_KEYS or k in excluded_dql_keys or v is None:
                continue
            api = dql_to_api.get(k)
            if api is None or api in forbidden:
                continue
            try:
                if v in legit_values.get(k, set()):
                    continue
                coverage.setdefault((k, v), set()).add(i)
            except TypeError:
                pass

    chosen: list[dict[str, Any]] = []
    remaining = set(range(len(over_rows)))
    local_counts = dict(negation_counts)

    while remaining and coverage:
        best: tuple[str, Any] | None = None
        best_drops = 0
        best_api: str | None = None
        for (k, v), idx_set in coverage.items():
            api = dql_to_api.get(k)
            if api is None or api in forbidden:
                continue
            if local_counts.get(api, 0) >= max_per_attribute:
                continue
            drops = len(idx_set & remaining)
            if drops == 0:
                continue
            if drops > best_drops or (
                drops == best_drops
                and best is not None
                and (k, repr(v)) < (best[0], repr(best[1]))  # pylint: disable=unsubscriptable-object
            ):
                best = (k, v)
                best_drops = drops
                best_api = api
        if best is None:
            break
        k, v = best
        chosen.append({"dql_key": k, "api_attribute": best_api, "value": v, "dropped_rows": best_drops})
        remaining -= coverage[best]
        local_counts[best_api] = local_counts.get(best_api, 0) + 1  # type: ignore[index]
        del coverage[best]

    return chosen, len(remaining) == 0


# ---------------------------------------------------------------------------
# Substring demotion
# ---------------------------------------------------------------------------


def _demote_one_substring(
    artifact: dict[str, Any],
    cache_dir: Path,
    entity_key: str,
    span_key: str | None,
    already_demoted: set[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Find the first undemoted substring_full candidate and rewrite it as
    in(key, "v1", "v2", …) using the distinct values from the Step 2 cache.

    Returns (new_artifact, demotion_record) or (None, None).
    """
    from ..analysis.candidates import _build_array_valued, distinct_values  # pylint: disable=import-outside-toplevel  # local import to avoid circularity

    array_valued_keys = _build_array_valued(load_mapping())

    def _load_rows(level: str) -> list[dict[str, Any]]:
        if level == "entity_candidates":
            path = cache_dir / f"{entity_key}_s_super.json"
        else:
            if span_key is None:
                return []
            path = cache_dir / f"{span_key}_e_orig.json"
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return []

    new_artifact = json.loads(json.dumps(artifact))
    for level in ("entity_candidates", "span_candidates"):
        for cand in new_artifact[level]:
            if cand.get("kind") != "substring_full":
                continue
            if cand["dql_key"] in already_demoted:
                continue
            rows = _load_rows(level)
            values = distinct_values(rows, cand["dql_key"], array_valued_keys=array_valued_keys)
            if not values:
                continue
            if len(values) == 1:
                cand["dql_fragment"] = f"{cand['dql_key']} == {_quote(values[0])}"
                cand["api_operator"] = "EQUALS"
            else:
                args = ", ".join(_quote(v) for v in values)
                cand["dql_fragment"] = f"in({cand['dql_key']}, {{{args}}})"
                cand["api_operator"] = "EQUALS_ANY_OF"
            cand["kind"] = "full"
            cand["values"] = list(values)
            cand["distinct_count"] = len(values)
            cand.pop("substring_kind", None)
            record = {"dql_key": cand["dql_key"], "level": level, "values": list(values)}
            return new_artifact, record
    return None, None


# ---------------------------------------------------------------------------
# Window shifting (under-select retry)
# ---------------------------------------------------------------------------


def _shift_window(window_from: str, window_to: str) -> tuple[str, str]:
    """Slide window earlier by its own duration.

    (now()-2h, now()) → (now()-4h, now()-2h)
    """
    def _parse(expr: str) -> tuple[int, str] | None:
        m = _WINDOW_RE.match(expr.strip())
        return (int(m.group(1)), m.group(2)) if m else None

    from_parsed = _parse(window_from)
    to_parsed = _parse(window_to)
    if from_parsed is None:
        raise ValueError(f"unparseable window_from: {window_from!r}")
    from_dur, unit = from_parsed
    to_dur = to_parsed[0] if to_parsed else 0
    span = from_dur - to_dur
    if span <= 0:
        raise ValueError("window duration must be positive")
    return f"now()-{from_dur + span}{unit}", f"now()-{from_dur}{unit}"


# ---------------------------------------------------------------------------
# Final conditions assembly
# ---------------------------------------------------------------------------


def _assemble_final_conditions(
    artifact: dict[str, Any],
    entity_negations: list[dict[str, Any]],
    span_negations: list[dict[str, Any]],
    *,
    mapping: ConditionMapping,
) -> list[dict[str, Any]]:
    final: list[dict[str, Any]] = []
    for c in artifact.get("surviving_original_conditions", []):
        final.append({
            "api_attribute": c["api_attribute"],
            "dql_fragment": c["dql_fragment"],
            "api_condition": c.get("api_condition"),
            "negate": False,
        })
    for group in ("entity_candidates", "span_candidates"):
        for c in artifact.get(group, []):
            final.append({
                "api_attribute": c["api_attribute"],
                "dql_fragment": c["dql_fragment"],
                "api_condition": c.get("api_condition"),
                "api_operator": c.get("api_operator"),
                "values": c.get("values"),
                "api_matcher_type": c.get("api_matcher_type"),
                "negate": False,
            })
    for n in entity_negations + span_negations:
        # Carry the raw typed value and matcher type so the report builder
        # reconstructs a type-correct NOT_EQUALS comparisonInfo instead of
        # re-parsing the stringified dql_fragment (which loses NUMBER/BOOLEAN).
        row = mapping.by_api_attribute(n["api_attribute"])
        final.append({
            "api_attribute": n["api_attribute"],
            "dql_fragment": _negation_fragment(n["dql_key"], n["value"]),
            "api_condition": None,
            "value": n["value"],
            "api_matcher_type": row.matcher_type if row is not None else None,
            "negate": True,
        })
    return final


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _verify_cache_path(cache_dir: Path, phase: str, vkey: str) -> Path:
    suffix = "_verify_e.json" if phase == "entity" else "_verify_s.json"
    return cache_dir / f"{vkey}{suffix}"


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _parse_timeframe(tf: str) -> tuple[str, str]:
    """Parse ``'from:X, to:Y'`` → ``(X, Y)`` for span verification windows."""
    from_val, to_val = DEFAULT_SPAN_WINDOW_FROM, DEFAULT_SPAN_WINDOW_TO
    for part in tf.split(","):
        part = part.strip()
        if part.startswith("from:"):
            from_val = part[len("from:"):].strip()
        elif part.startswith("to:"):
            to_val = part[len("to:"):].strip()
    return from_val, to_val


def run_overselect_loop(
    *,
    rule_id: str,
    artifact: dict[str, Any],
    entity_key: str,
    span_key: str | None,
    cache_dir: Path,
    derived_dir: Path,
    dql_execute,  # Callable[[str], list[dict]] — injected DQL runner
    span_window_from: str = DEFAULT_SPAN_WINDOW_FROM,
    span_window_to: str = DEFAULT_SPAN_WINDOW_TO,
    max_negations_per_attribute: int = DEFAULT_MAX_NEGATIONS_PER_ATTRIBUTE,
    max_under_select_retries: int = DEFAULT_MAX_UNDER_SELECT_RETRIES,
    query_timeframe: str | None = None,
) -> VerificationResult:
    """Run the verification loop to a terminal verdict and write
    ``derived/<rule_id>_verdict.json``.

    ``dql_execute`` is a callable that accepts a DQL string and returns the
    parsed row list.  Caching is handled here — the callable is only invoked
    when the cache file for a given verification key is absent.
    """
    # pylint: disable=too-many-locals,too-many-branches,too-many-statements,too-many-arguments
    # --- Load orig sets (driven by data availability, not by mode) ----------
    if span_key is not None:
        s_orig, e_orig = _load_span_orig_sets(cache_dir, span_key)
    else:
        s_orig = _load_entity_orig_set(cache_dir, entity_key)
        e_orig = None

    # Derive effective span window — prefer explicit span_window_from/to, then
    # fall back to parsing query_timeframe, then fall back to defaults.
    if span_window_from == DEFAULT_SPAN_WINDOW_FROM and query_timeframe:
        span_window_from, span_window_to = _parse_timeframe(query_timeframe)

    # Pre-compute mapping-derived constants once.
    _mapping = load_mapping()
    _forbidden: frozenset[str] = frozenset(_mapping.negation_forbidden)
    _dql_to_api: dict[str, str] = _mapping.dql_key_index(candidate_eligible_only=True)
    _api_to_quality: dict[str, str] = {
        r.api_attribute: r.candidate_quality
        for r in list(_mapping.entity_attributes) + list(_mapping.span_attributes)
    }

    def _is_good(c: dict) -> bool:
        return is_good_candidate(c, api_to_quality=_api_to_quality)

    # Split the flat candidate lists into good (initial active set) and
    # suboptimal (escalation pool — used only when good-only + negations fail).
    _good_entity = [c for c in artifact.get("entity_candidates", []) if _is_good(c)]
    _good_span   = [c for c in artifact.get("span_candidates",   []) if _is_good(c)]
    _suboptimal_pool = (
        [c for c in artifact.get("entity_candidates", []) if not _is_good(c)]
        + [c for c in artifact.get("span_candidates",  []) if not _is_good(c)]
    )

    # Build a view of the artifact that starts with good candidates only.
    # Escalation appends suboptimal candidates to this copy as needed.
    _start_artifact = {**artifact, "entity_candidates": _good_entity, "span_candidates": _good_span}

    # =========================================================================
    # Phase 1 — Entity pre-phase
    # =========================================================================
    # extra_fields: dql_keys from entity_candidates so negation search can
    # operate on entity rows (candidate keys are dt.entity.service fields absent
    # from span data — they must be fetched explicitly).
    extra_entity_fields: list[str] = [
        c["dql_key"]
        for c in _start_artifact.get("entity_candidates", [])
        if c.get("dql_key")
    ]
    excluded_entity_keys: set[str] = set(extra_entity_fields)

    entity_pos_frags = _entity_frags(_start_artifact)
    entity_negations: list[dict[str, Any]] = []
    entity_negation_counts: dict[str, int] = {}
    entity_phase_outcome = "skipped"
    entity_history: list[dict[str, Any]] = []
    service_filter: set[str] | None = None
    entity_warning: str | None = None
    e_iter = 0

    if entity_pos_frags:
        while True:
            frags = list(entity_pos_frags)
            for n in entity_negations:
                frags.append(_negation_fragment(n["dql_key"], n["value"]))
            filter_str = " and ".join(frags)

            vkey = verification_cache_key(
                dispatch="entity",
                entity_key=entity_key,
                span_key=span_key,
                filter_str=filter_str,
                window_from=None,
                window_to=None,
            )
            cache_path = _verify_cache_path(cache_dir, "entity", vkey)

            if cache_path.exists():
                rows: list[dict[str, Any]] = json.loads(cache_path.read_text())
            else:
                dql_text = build_entity_verification_query(
                    filter_str,
                    extra_fields=extra_entity_fields or None,
                    timeframe=query_timeframe,
                )
                rows = dql_execute(dql_text)
                _write_json(cache_path, rows)

            # 0-row guard — should never happen; indicates a migrator bug.
            if not rows:
                raise RuntimeError(
                    f"entity verification query returned 0 rows at iter {e_iter} "
                    f"(rule={rule_id}, verify_key={vkey}); "
                    "this is a migrator bug — the entity candidates must match at least S_orig"
                )

            s_entity_cand = _extract_s_cand(rows, "entity")
            outcome = _classify(s_entity_cand, None, s_orig, None, "entity")

            entity_history.append({
                "phase": "entity",
                "iteration": e_iter,
                "outcome": outcome,
                "verify_key": vkey,
                "s_cand_size": len(s_entity_cand),
                "negations_count": len(entity_negations),
            })

            if outcome == "exact":
                entity_phase_outcome = "exact"
                service_filter = s_entity_cand
                break

            if outcome == "under":
                entity_phase_outcome = "under"
                service_filter = None  # unconstrained — span phase covers all services
                entity_warning = "entity_pre_phase_under_select"
                break

            # over — try greedy negation
            assert outcome == "over"
            new_negs, fully_covered = _find_negations(
                rows, s_orig, None, "entity",
                entity_negation_counts, max_negations_per_attribute,
                excluded_entity_keys,
                forbidden=_forbidden,
                dql_to_api=_dql_to_api,
            )

            if new_negs:
                for n in new_negs:
                    entity_negations.append(n)
                    entity_negation_counts[n["api_attribute"]] = (
                        entity_negation_counts.get(n["api_attribute"], 0) + 1
                    )
                e_iter += 1
                continue

            # Negation exhausted — keep over-selected service_filter; span phase
            # can still achieve a combined exact by filtering endpoints.
            entity_phase_outcome = "over_exhausted"
            service_filter = s_entity_cand
            break

    # =========================================================================
    # Entity-only path (no span data)
    # =========================================================================
    if span_key is None:
        if entity_phase_outcome == "exact":
            status = "exact_match"
        elif entity_phase_outcome in ("under", "skipped"):
            # under or nothing to verify → accept best-effort
            status = "exact_match_after_under_select_retry"
        else:
            # over_exhausted — no span phase to save us
            failure_reason = "refinement_exhausted"
            verdict = _terminal_verdict(
                rule_id, "no_replacement",
                failure_reason=failure_reason,
                final_conditions=None,
                iterations=e_iter,
                entity_negations=entity_negations,
                span_negations=[],
                demotions=[],
                history=entity_history,
            )
            _write_json(derived_dir / f"{rule_id}_verdict.json", verdict)
            return VerificationResult(
                rule_id=rule_id, status="no_replacement",
                failure_reason=failure_reason,
                iterations=e_iter,
                entity_negations_applied=len(entity_negations),
                entity_phase_outcome=entity_phase_outcome,
                verdict_path=f"{rule_id}_verdict.json",
            )

        verdict = _terminal_verdict(
            rule_id, status,
            final_conditions=_assemble_final_conditions(
                artifact, entity_negations, [], mapping=_mapping
            ),
            iterations=e_iter,
            entity_negations=entity_negations,
            span_negations=[],
            demotions=[],
            history=entity_history,
            warning=entity_warning,
        )
        _write_json(derived_dir / f"{rule_id}_verdict.json", verdict)
        return VerificationResult(
            rule_id=rule_id, status=status,
            iterations=e_iter,
            entity_negations_applied=len(entity_negations),
            entity_phase_outcome=entity_phase_outcome,
            verdict_path=f"{rule_id}_verdict.json",
            final_conditions=verdict["final_conditions"],
        )

    # =========================================================================
    # Phase 2 — Span loop
    # =========================================================================
    working_artifact = json.loads(json.dumps(_start_artifact))
    span_negations: list[dict[str, Any]] = []
    span_negation_counts: dict[str, int] = {}
    demotions: list[dict[str, Any]] = []
    demoted_keys: set[str] = set()
    under_select_retries = 0
    span_iteration = 0
    window_from = span_window_from
    window_to = span_window_to
    history: list[dict[str, Any]] = list(entity_history)

    # Suboptimal escalation pool — tried one-by-one when good+negations+demotion exhausted.
    _suboptimal_idx = 0
    _suboptimal_used = 0

    while True:
        # Build span filter string.
        frags = _span_frags(working_artifact)
        for n in span_negations:
            frags.append(_negation_fragment(n["dql_key"], n["value"]))
        if service_filter is not None:
            frags.append(_service_filter_fragment(service_filter))
        filter_str = " and ".join(frags) if frags else "true"

        vkey = verification_cache_key(
            dispatch="span",
            entity_key=entity_key,
            span_key=span_key,
            filter_str=filter_str,
            window_from=window_from,
            window_to=window_to,
        )
        cache_path = _verify_cache_path(cache_dir, "span", vkey)

        if cache_path.exists():
            rows = json.loads(cache_path.read_text())
        else:
            dql_text = build_span_verification_query(filter_str, window_from, window_to)
            rows = dql_execute(dql_text)
            _write_json(cache_path, rows)

        # 0-row guard — should never happen; indicates a migrator bug.
        if not rows:
            raise RuntimeError(
                f"span verification query returned 0 rows at iter {span_iteration} "
                f"(rule={rule_id}, verify_key={vkey}); "
                "this is a migrator bug — the span candidates must match at least S_orig/E_orig"
            )

        s_cand = _extract_s_cand(rows, "span")
        e_cand = _extract_e_cand(rows)
        outcome = _classify(s_cand, e_cand, s_orig, e_orig, "span")

        history.append({
            "phase": "span",
            "iteration": span_iteration,
            "outcome": outcome,
            "verify_key": vkey,
            "s_cand_size": len(s_cand),
            "e_cand_size": len(e_cand),
            "negations_count": len(span_negations),
            "window_from": window_from,
            "window_to": window_to,
        })

        # --- Exact ----------------------------------------------------------
        if outcome == "exact":
            status = (
                "exact_match_after_under_select_retry"
                if under_select_retries > 0
                else "exact_match"
            )
            verdict = _terminal_verdict(
                rule_id, status,
                final_conditions=_assemble_final_conditions(
                    working_artifact, entity_negations, span_negations, mapping=_mapping
                ),
                iterations=span_iteration,
                entity_negations=entity_negations,
                span_negations=span_negations,
                demotions=demotions,
                history=history,
                warning=entity_warning,
            )
            _write_json(derived_dir / f"{rule_id}_verdict.json", verdict)
            return VerificationResult(
                rule_id=rule_id,
                status=status,
                iterations=span_iteration,
                negations_applied=len(span_negations),
                entity_negations_applied=len(entity_negations),
                entity_phase_outcome=entity_phase_outcome,
                demotions_applied=len(demotions),
                suboptimal_used=_suboptimal_used,
                verdict_path=f"{rule_id}_verdict.json",
                final_conditions=verdict["final_conditions"],
            )

        # --- Under-select ---------------------------------------------------
        if outcome == "under":
            if under_select_retries >= max_under_select_retries:
                status = "exact_match_after_under_select_retry"
                verdict = _terminal_verdict(
                    rule_id, status,
                    final_conditions=_assemble_final_conditions(
                        working_artifact, entity_negations, span_negations, mapping=_mapping
                    ),
                    iterations=span_iteration,
                    entity_negations=entity_negations,
                    span_negations=span_negations,
                    demotions=demotions,
                    history=history,
                    warning=entity_warning,
                )
                _write_json(derived_dir / f"{rule_id}_verdict.json", verdict)
                return VerificationResult(
                    rule_id=rule_id,
                    status=status,
                    iterations=span_iteration,
                    negations_applied=len(span_negations),
                    entity_negations_applied=len(entity_negations),
                    entity_phase_outcome=entity_phase_outcome,
                    demotions_applied=len(demotions),
                    suboptimal_used=_suboptimal_used,
                    verdict_path=f"{rule_id}_verdict.json",
                    final_conditions=verdict["final_conditions"],
                )
            under_select_retries += 1
            span_iteration += 1
            window_from, window_to = _shift_window(window_from, window_to)
            continue

        # --- Over-select ----------------------------------------------------
        assert outcome == "over"

        excluded_span_keys: set[str] = {
            c.get("dql_key")
            for c in working_artifact.get("span_candidates", [])
            if c.get("dql_key")
        }
        new_negs, fully_covered = _find_negations(
            rows, s_orig, e_orig, "span",
            span_negation_counts, max_negations_per_attribute, excluded_span_keys,
            forbidden=_forbidden,
            dql_to_api=_dql_to_api,
        )

        if new_negs and fully_covered:
            for n in new_negs:
                span_negations.append(n)
                span_negation_counts[n["api_attribute"]] = (
                    span_negation_counts.get(n["api_attribute"], 0) + 1
                )
            span_iteration += 1
            continue

        # Greedy exhausted — try substring demotion.
        new_artifact, demotion = _demote_one_substring(
            working_artifact, cache_dir, entity_key, span_key, demoted_keys
        )
        if new_artifact is not None and demotion is not None:
            demotions.append(demotion)
            demoted_keys.add(demotion["dql_key"])
            working_artifact = new_artifact
            # Reset span loop state.
            span_negations = []
            span_negation_counts = {}
            under_select_retries = 0
            span_iteration = 0
            window_from = span_window_from
            window_to = span_window_to
            continue

        # No demotion possible — try suboptimal escalation before giving up.
        if _suboptimal_idx < len(_suboptimal_pool):
            next_cand = _suboptimal_pool[_suboptimal_idx]
            _suboptimal_idx += 1
            _suboptimal_used += 1
            side_key = (
                "entity_candidates"
                if _mapping.is_entity(next_cand.get("api_attribute", ""))
                else "span_candidates"
            )
            working_artifact[side_key] = working_artifact.get(side_key, []) + [next_cand]
            # Reset span loop state for a clean retry.
            span_negations = []
            span_negation_counts = {}
            demotions = []
            demoted_keys = set()
            under_select_retries = 0
            span_iteration = 0
            window_from = span_window_from
            window_to = span_window_to
            continue

        # Suboptimal pool also exhausted — terminal no_replacement.
        failure_reason = (
            "substring_demotion_exhausted" if demoted_keys else "refinement_exhausted"
        )
        verdict = _terminal_verdict(
            rule_id, "no_replacement",
            failure_reason=failure_reason,
            final_conditions=None,
            iterations=span_iteration,
            entity_negations=entity_negations,
            span_negations=span_negations,
            demotions=demotions,
            history=history,
        )
        _write_json(derived_dir / f"{rule_id}_verdict.json", verdict)
        return VerificationResult(
            rule_id=rule_id,
            status="no_replacement",
            failure_reason=failure_reason,
            iterations=span_iteration,
            negations_applied=len(span_negations),
            entity_negations_applied=len(entity_negations),
            entity_phase_outcome=entity_phase_outcome,
            demotions_applied=len(demotions),
            suboptimal_used=_suboptimal_used,
            verdict_path=f"{rule_id}_verdict.json",
        )


# ---------------------------------------------------------------------------
# Verdict skeleton
# ---------------------------------------------------------------------------


def _terminal_verdict(  # pylint: disable=too-many-arguments
    rule_id: str,
    status: str,
    *,
    final_conditions: list[dict[str, Any]] | None,
    iterations: int,
    entity_negations: list[dict[str, Any]],
    span_negations: list[dict[str, Any]],
    demotions: list[dict[str, Any]],
    history: list[dict[str, Any]] | None = None,
    failure_reason: str | None = None,
    warning: str | None = None,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "status": status,
        "failure_reason": failure_reason,
        "warning": warning,
        "iterations": iterations,
        "entity_negations_applied": entity_negations,
        "span_negations_applied": span_negations,
        "demotions_applied": demotions,
        "final_conditions": final_conditions,
        "history": history or [],
    }


__all__ = [
    "DEFAULT_SPAN_WINDOW_FROM",
    "DEFAULT_SPAN_WINDOW_TO",
    "VerificationResult",
    "run_overselect_loop",
]
