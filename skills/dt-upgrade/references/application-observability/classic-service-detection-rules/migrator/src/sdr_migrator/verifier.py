from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .candidates import Candidate
from .conditions import ATTRIBUTE_MAP, dql_field, dql_string

DEFAULT_MAX_NEGATIONS_PER_ATTRIBUTE = 5

# Config v1 caps a compareOperation's `values` at 10 (@Size(min=1, max=10)), and >10
# OR-values for one attribute is inexpressible in the API. Distinct from the detection
# threshold candidates._PARTIAL_CAP = 5 (normal partials are already safe at ≤5).
API_VALUE_CAP = 10

_SUBSTRING_DQL_FN = {"prefix": "startsWith", "suffix": "endsWith", "contains": "contains"}
_SUBSTRING_KINDS = frozenset(_SUBSTRING_DQL_FN)


@dataclass(frozen=True)
class Negation:
    attribute_type: str
    grail_key: str
    value: str


@dataclass(frozen=True)
class VerifyResult:
    verdict: str  # "exact" | "under_select" | "no_replacement"
    # The positive conjunction actually used: surviving good candidates (with any
    # substrings replaced by their demoted exact form) plus escalated reserve ones.
    candidates: list[Candidate] = field(default_factory=list)
    negations: list[Negation] = field(default_factory=list)
    escalated: list[Candidate] = field(default_factory=list)
    demoted_from: list[Candidate] = field(default_factory=list)


@dataclass(frozen=True)
class _VerifyContext:
    """Bundles the parameters shared by every ladder-rung query attempt."""

    target_set: frozenset[tuple[str, str]]
    negatable_attrs: dict[str, str]
    build_query: Callable[[list[str]], str]
    dql_client: Any
    max_negations_per_attribute: int


def verify(  # pylint: disable=too-many-arguments
    target_set: frozenset[tuple[str, str]],
    candidates: list[Candidate],
    rule_type: str,
    build_query: Callable[[list[str]], str],
    dql_client: Any,
    *,
    max_negations_per_attribute: int = DEFAULT_MAX_NEGATIONS_PER_ATTRIBUTE,
    has_surviving_conditions: bool = False,
) -> VerifyResult:
    """Verify a Grail replacement by combining candidates, then refining.

    Verification starts from the conjunction of ALL good-quality candidates and
    climbs the over-selection ladder: greedy negation -> substring demotion (one
    candidate at a time) -> suboptimal-reserve escalation (accumulating, one at a
    time) -> no_replacement. Because every candidate's values come from the target
    rows themselves, ANDing candidates can only narrow an over-selection, never
    turn a covered target row into a missed one -- so combining is safe.

    build_query(extra_fragments) must return a verification span query string.

    With zero candidates and ``has_surviving_conditions`` true, the emitted rule would
    carry only its surviving conditions. Under unscoped verification that
    surviving-only conjunction is a REAL global query, not a tautology, so it must be
    run: the surviving fragments alone (an empty extra-fragment set) must reduce the
    global span result to the target set, directly or via negation, else no_replacement.
    With no surviving conditions either, the
    emitted rule would be empty (match-all) so nothing is queried -> no_replacement.
    """
    ctx = _VerifyContext(
        target_set=target_set,
        negatable_attrs={
            info.grail_key: attr_type
            for attr_type, info in ATTRIBUTE_MAP.get(rule_type, {}).items()
            if info.candidate_eligible and info.grail_key and not info.negation_forbidden
        },
        build_query=build_query,
        dql_client=dql_client,
        max_negations_per_attribute=max_negations_per_attribute,
    )
    good = [c for c in candidates if c.quality != "suboptimal"]
    reserve = [c for c in candidates if c.quality == "suboptimal"]
    if not good and not reserve:
        if has_surviving_conditions and target_set:
            result = _refine(ctx, [], [])
            return result if result is not None else VerifyResult(verdict="no_replacement")
        return VerifyResult(verdict="no_replacement")
    return _combine_and_refine(ctx, good, reserve)


def _combine_and_refine(
    ctx: _VerifyContext, good: list[Candidate], reserve: list[Candidate]
) -> VerifyResult:
    """Refine the good conjunction, escalating one reserve candidate at a time.

    Refinement at each level (good + N escalated) is terminal on exact or
    under_select; only over-selection advances to the next reserve candidate. An
    empty positive conjunction is never queried -- with no good candidates,
    refinement begins only once a reserve candidate has been escalated.
    """
    escalated: list[Candidate] = []
    idx = 0
    while True:
        if good or escalated:
            result = _refine(ctx, good, escalated)
            if result is not None:
                return result
        if idx < len(reserve):
            escalated = escalated + [reserve[idx]]
            idx += 1
            continue
        break
    return VerifyResult(verdict="no_replacement")


def _refine(
    ctx: _VerifyContext, good: list[Candidate], escalated: list[Candidate]
) -> VerifyResult | None:
    """Attempt the good+escalated conjunction, demoting over-generalising substrings
    one at a time. Returns an exact/under_select VerifyResult, or None if the
    conjunction still over-selects after every substring has been demoted."""
    working = list(good)
    demoted_from: list[Candidate] = []

    status, negations = _attempt_conjunction(ctx, working, escalated)
    result = _finish(status, negations, working, escalated, demoted_from)
    if result is not None:
        return result

    for i, candidate in enumerate(working):
        if candidate.kind in _SUBSTRING_KINDS and candidate.raw_values:
            if len(candidate.raw_values) > API_VALUE_CAP:
                # Demoting would need >10 exact values -- inexpressible in Config v1
                # and never accepted as a valid replacement. Leave the
                # substring loose; if nothing else reaches exact, fall through.
                continue
            working[i] = _demote_to_exact(candidate)
            demoted_from.append(candidate)
            status, negations = _attempt_conjunction(ctx, working, escalated)
            result = _finish(status, negations, working, escalated, demoted_from)
            if result is not None:
                return result
    return None


def _attempt_conjunction(
    ctx: _VerifyContext, working: list[Candidate], escalated: list[Candidate]
) -> tuple[str, list[Negation]]:
    fragments = [_candidate_fragment(c) for c in working] + [
        _candidate_fragment(c) for c in escalated
    ]
    return _attempt(ctx, fragments)


def _finish(
    status: str,
    negations: list[Negation],
    working: list[Candidate],
    escalated: list[Candidate],
    demoted_from: list[Candidate],
) -> VerifyResult | None:
    """Turn a terminal attempt status into a VerifyResult, or None to keep climbing."""
    if status == "exact":
        return VerifyResult(
            verdict="exact",
            candidates=working + escalated,
            negations=negations,
            escalated=list(escalated),
            demoted_from=demoted_from,
        )
    if status == "under_select":
        return VerifyResult(
            verdict="under_select",
            candidates=working + escalated,
            escalated=list(escalated),
            demoted_from=demoted_from,
        )
    return None


def _attempt(ctx: _VerifyContext, fragments: list[str]) -> tuple[str, list[Negation]]:
    """Run one verification query attempt.

    Returns ("exact", negations) if it matches the target set directly or via a
    fully-covering negation, ("over_select", []) if it strictly over-selects but
    negation can't fully cover the excess, ("under_select", []) if it strictly
    under-selects (a sign of sparse/ephemeral span data rather than a bad
    candidate), or ("other", []) otherwise.
    """
    rows = ctx.dql_client.execute(ctx.build_query(fragments))
    if not rows:
        raise RuntimeError(
            "verification query returned 0 rows; by construction it must match "
            "at least the target set"
        )

    verify_set = extract_target_keys(rows)
    if verify_set == ctx.target_set:
        return "exact", []

    if ctx.target_set < verify_set:  # strict superset -> over-selection
        negations, fully_covered = _find_negations(
            rows, ctx.target_set, ctx.negatable_attrs, ctx.max_negations_per_attribute
        )
        if fully_covered:
            return "exact", negations
        return "over_select", []

    if verify_set < ctx.target_set:  # strict subset -> under-selection
        return "under_select", []

    return "other", []


def _demote_to_exact(candidate: Candidate) -> Candidate:
    """Rewrite a substring candidate back into an exact multi-value candidate
    using its original raw distinct values (no 5-value cap -- this is a
    last-resort rescue, not a normal partial candidate)."""
    assert candidate.raw_values is not None
    return Candidate(
        attribute_type=candidate.attribute_type,
        grail_key=candidate.grail_key,
        values=list(candidate.raw_values),
        quality=candidate.quality,
        kind="exact",
    )


def extract_target_keys(rows: list[dict[str, Any]]) -> frozenset[tuple[str, str]]:
    """Extract the (process_group, endpoint.name) key set from span rows, skipping
    any row missing one of those fields."""
    return frozenset(
        (row["dt.entity.process_group"], row["endpoint.name"])
        for row in rows
        if row.get("dt.entity.process_group") and row.get("endpoint.name")
    )


def _row_key(row: dict[str, Any]) -> tuple[Any, Any]:
    return (row.get("dt.entity.process_group"), row.get("endpoint.name"))


def _find_negations(
    rows: list[dict[str, Any]],
    target_set: frozenset[tuple[str, str]],
    negatable_attrs: dict[str, str],
    max_per_attribute: int,
) -> tuple[list[Negation], bool]:
    """Greedy single-pass set-cover over the over-selected (excess) rows.

    Picks attribute=value pairs that appear only in excess rows (never in a
    legitimate target-set row), each step choosing whichever pair drops the most
    remaining excess rows, bounded by max_per_attribute per attribute. Returns
    (chosen_negations, fully_covered).
    """
    excess_rows = [r for r in rows if _row_key(r) not in target_set]
    if not excess_rows:
        return [], True

    legit_rows = [r for r in rows if _row_key(r) in target_set]
    legit_values = _collect_values(legit_rows, negatable_attrs)
    coverage = _build_coverage(excess_rows, negatable_attrs, legit_values)

    chosen: list[Negation] = []
    remaining = set(range(len(excess_rows)))
    counts: dict[str, int] = {}

    while remaining and coverage:
        picked = _pick_best_negation(coverage, negatable_attrs, counts, max_per_attribute, remaining)
        if picked is None:
            break
        key, v = picked
        attr_type = negatable_attrs[key]
        chosen.append(Negation(attribute_type=attr_type, grail_key=key, value=v))
        remaining -= coverage[(key, v)]
        counts[attr_type] = counts.get(attr_type, 0) + 1
        del coverage[(key, v)]

    return chosen, len(remaining) == 0


def _collect_values(rows: list[dict[str, Any]], keys: dict[str, str]) -> dict[str, set[Any]]:
    """Distinct non-null values seen per negatable key across the given rows."""
    values: dict[str, set[Any]] = {}
    for r in rows:
        for key in keys:
            v = r.get(key)
            if v is not None:
                values.setdefault(key, set()).add(v)
    return values


def _build_coverage(
    excess_rows: list[dict[str, Any]],
    negatable_attrs: dict[str, str],
    legit_values: dict[str, set[Any]],
) -> dict[tuple[str, Any], set[int]]:
    """Map each (key, value) pair to the excess-row indices it would drop,
    excluding any value that also appears on a legitimate target-set row."""
    coverage: dict[tuple[str, Any], set[int]] = {}
    for i, r in enumerate(excess_rows):
        for key in negatable_attrs:
            v = r.get(key)
            if v is None or v in legit_values.get(key, set()):
                continue
            coverage.setdefault((key, v), set()).add(i)
    return coverage


def _pick_best_negation(
    coverage: dict[tuple[str, Any], set[int]],
    negatable_attrs: dict[str, str],
    counts: dict[str, int],
    max_per_attribute: int,
    remaining: set[int],
) -> tuple[str, Any] | None:
    """Pick the (key, value) pair dropping the most remaining excess rows,
    respecting the per-attribute cap; ties broken deterministically."""
    eligible = [
        (key, v, len(idx_set & remaining))
        for (key, v), idx_set in coverage.items()
        if counts.get(negatable_attrs[key], 0) < max_per_attribute
    ]
    eligible = [pair for pair in eligible if pair[2] > 0]
    if not eligible:
        return None
    key, v, _drops = min(eligible, key=lambda pair: (-pair[2], pair[0], str(pair[1])))
    return key, v


def _candidate_fragment(candidate: Candidate) -> str:
    key = dql_field(candidate.grail_key)
    if candidate.kind in _SUBSTRING_DQL_FN:
        fn = _SUBSTRING_DQL_FN[candidate.kind]
        return f"{fn}({key}, {dql_string(candidate.values[0])})"
    if len(candidate.values) == 1:
        return f"{key} == {dql_string(candidate.values[0])}"
    inner = ", ".join(dql_string(v) for v in candidate.values)
    return f"in({key}, {{{inner}}})"
