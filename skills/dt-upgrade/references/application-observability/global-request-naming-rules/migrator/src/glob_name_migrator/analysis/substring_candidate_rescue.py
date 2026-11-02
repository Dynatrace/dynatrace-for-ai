"""Substring candidate synthesis (rescue pass).

Augments the candidates artifact with BEGINS_WITH / ENDS_WITH /
CONTAINS candidates when the cached rows support them.  Pure post-processing
— no DQL is issued.

Eligibility: matcher is STRING or ME_INDEX_STRING.  BEGINS_WITH / ENDS_WITH
require STRING.  ME_INDEX_STRING admits CONTAINS only.

Contains fallback fires once per rule, only when the artifact has no
candidate of any kind on either side after the prefix/suffix pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..rules.mapping import ConditionMapping, load_mapping
from ..rules.tags import is_primary_tag_key
from .candidates import (
    UnmigratableRuleError,
    _build_api_matcher,
    _build_array_valued,
    _build_entity_dql_key_to_api,
    _build_span_dql_key_to_api,
    _candidate_keys,
    _default_load,
    _expand_surviving_attrs,
    _is_null,
    _quote,
    _row_id,
    _row_service_types,
    _STRUCTURAL_ENTITY,
    _STRUCTURAL_SPAN,
    distinct_values,
    has_unmigratable,
    resolve_api_attribute,
    surviving_api_attributes,
)

MIN_SUBSTRING_LEN = 4

_SUBSTRING_ELIGIBLE: frozenset[str] = frozenset({"STRING", "ME_INDEX_STRING"})
_PREFIX_SUFFIX_MATCHERS: frozenset[str] = frozenset({"STRING"})

_KIND_RANK = {"full": 0, "partial_promoted": 1, "substring_full": 2}


# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------


def longest_common_prefix(values: list[str]) -> str:
    """Return the longest common prefix of all strings in values."""
    if not values:
        return ""
    p = values[0]
    for v in values[1:]:
        i = 0
        while i < len(p) and i < len(v) and p[i] == v[i]:
            i += 1
        p = p[:i]
        if not p:
            return ""
    return p


def longest_common_suffix(values: list[str]) -> str:
    """Return the longest common suffix of all strings in values."""
    if not values:
        return ""
    s = values[0]
    for v in values[1:]:
        i = 0
        while i < len(s) and i < len(v) and s[-1 - i] == v[-1 - i]:
            i += 1
        s = s[len(s) - i:] if i else ""
        if not s:
            return ""
    return s


def longest_common_substring(values: list[str], min_len: int) -> str:
    """Longest substring of length >= min_len shared by ALL values.

    Naive O(L²·N) set-intersection; only called as a last-resort fallback.
    """
    if not values:
        return ""

    def _subs(s: str) -> set[str]:
        return {s[i:j] for i in range(len(s)) for j in range(i + min_len, len(s) + 1)}

    common = _subs(values[0])
    for v in values[1:]:
        common &= _subs(v)
        if not common:
            return ""
    return max(common, key=len) if common else ""


# ---------------------------------------------------------------------------
# DQL emit for substring operators
# ---------------------------------------------------------------------------


def _rescuable_keys(rows: list[dict[str, Any]], skip: frozenset[str]) -> list[str]:
    """Candidate keys eligible for substring rescue.

    Primary tags are excluded: Phase 3 compares them with exact string equality
    (``NamingRuleEvaluation``), so a prefix/suffix/contains candidate could never
    be expressed as a condition.
    """
    return [k for k in _candidate_keys(rows, skip) if not is_primary_tag_key(k)]


def _emit_substring_dql(dql_key: str, operator: str, value: str, *, array_valued_keys: frozenset[str]) -> str | None:
    """Return the DQL fragment for a substring filter, or None if not emittable.

    Array-valued keys have no plain substring idiom without arrayFilter lambdas.
    """
    if dql_key in array_valued_keys:
        return None
    fn = {"BEGINS_WITH": "startsWith", "ENDS_WITH": "endsWith", "CONTAINS": "contains"}.get(operator)
    if fn is None:
        return None
    return f"{fn}({dql_key}, {_quote(value)})"


# ---------------------------------------------------------------------------
# Eligibility check
# ---------------------------------------------------------------------------


def _eligible_attribute(  # pylint: disable=too-many-arguments,too-many-locals,too-many-return-statements
    dql_key: str,
    *,
    rows: list[dict[str, Any]],
    surviving_attrs: set[str],
    chosen_attrs: set[str],
    allowed_matchers: frozenset[str],
    service_type_index: dict[str, list[str]] | None,
    entity_dql_to_api: dict[str, str],
    span_dql_to_api: dict[str, str],
    scope_aware,
    unmigratable_as_candidates: frozenset[str],
    api_matcher: dict[str, str],
) -> tuple[str | None, str | None]:
    """Resolve (api_attribute, matcher) if eligible, else (None, None)."""
    if dql_key in scope_aware:
        resolved: set[str] = set()
        for row in rows:
            if dql_key not in row or _is_null(row.get(dql_key)):
                continue
            sts = _row_service_types(row, service_type_index)
            attr = resolve_api_attribute(
                dql_key, sts,
                entity_dql_to_api=entity_dql_to_api,
                span_dql_to_api=span_dql_to_api,
                scope_aware=scope_aware,
            )
            if attr is None:
                return None, None
            resolved.add(attr)
        if len(resolved) != 1:
            return None, None
        api_attribute = next(iter(resolved))
    else:
        api_attribute = resolve_api_attribute(
            dql_key, None,
            entity_dql_to_api=entity_dql_to_api,
            span_dql_to_api=span_dql_to_api,
            scope_aware=scope_aware,
        )
        if api_attribute is None:
            return None, None

    if api_attribute in surviving_attrs or api_attribute in chosen_attrs:
        return None, None
    if api_attribute in unmigratable_as_candidates:
        return None, None
    if api_attribute == "__MANAGEMENT_ZONES__":
        return None, None
    matcher = api_matcher.get(api_attribute)
    if matcher is None or matcher not in allowed_matchers:
        return None, None
    return api_attribute, matcher


def _coerce_strings(values: list[Any]) -> list[str]:
    out: list[str] = []
    for v in values:
        if isinstance(v, str):
            out.append(v)
        else:
            return []
    return out


# ---------------------------------------------------------------------------
# Prefix / suffix scan
# ---------------------------------------------------------------------------


def _prefix_suffix_scan(  # pylint: disable=too-many-arguments,too-many-locals
    rows: list[dict[str, Any]],
    keys: list[str],
    *,
    surviving_attrs: set[str],
    chosen_attrs: set[str],
    min_len: int,
    service_type_index: dict[str, list[str]] | None,
    entity_dql_to_api: dict[str, str],
    span_dql_to_api: dict[str, str],
    scope_aware,
    unmigratable_as_candidates: frozenset[str],
    api_matcher: dict[str, str],
    array_valued_keys: frozenset[str],
) -> tuple[list[dict[str, Any]], list[tuple[str, str, str, list[str]]]]:
    """Run prefix-then-suffix scan.

    Returns (emitted, contains_eligible) where contains_eligible is a list of
    (dql_key, api_attribute, matcher, str_values) for attributes that did not
    produce a prefix or suffix candidate.
    """
    emitted: list[dict[str, Any]] = []
    contains_eligible: list[tuple[str, str, str, list[str]]] = []

    for k in keys:
        api_attribute, matcher = _eligible_attribute(
            k,
            rows=rows,
            surviving_attrs=surviving_attrs,
            chosen_attrs=chosen_attrs,
            allowed_matchers=_SUBSTRING_ELIGIBLE,
            service_type_index=service_type_index,
            entity_dql_to_api=entity_dql_to_api,
            span_dql_to_api=span_dql_to_api,
            scope_aware=scope_aware,
            unmigratable_as_candidates=unmigratable_as_candidates,
            api_matcher=api_matcher,
        )
        if api_attribute is None or matcher is None:
            continue
        raw_values = distinct_values(rows, k, array_valued_keys=array_valued_keys)
        if len(raw_values) < 2:
            continue
        str_values = _coerce_strings(raw_values)
        if not str_values:
            continue

        emitted_something = False
        if matcher in _PREFIX_SUFFIX_MATCHERS:
            lcp = longest_common_prefix(str_values)
            if len(lcp) >= min_len:
                frag = _emit_substring_dql(k, "BEGINS_WITH", lcp, array_valued_keys=array_valued_keys)
                if frag:
                    emitted.append(_make_candidate(
                        dql_key=k, api_attribute=api_attribute, matcher=matcher,
                        values=raw_values, substring=lcp,
                        operator="BEGINS_WITH", substring_kind="prefix",
                        dql_fragment=frag,
                    ))
                    chosen_attrs.add(api_attribute)
                    emitted_something = True

            if not emitted_something:
                lcs = longest_common_suffix(str_values)
                if len(lcs) >= min_len:
                    frag = _emit_substring_dql(k, "ENDS_WITH", lcs, array_valued_keys=array_valued_keys)
                    if frag:
                        emitted.append(_make_candidate(
                            dql_key=k, api_attribute=api_attribute, matcher=matcher,
                            values=raw_values, substring=lcs,
                            operator="ENDS_WITH", substring_kind="suffix",
                            dql_fragment=frag,
                        ))
                        chosen_attrs.add(api_attribute)
                        emitted_something = True

        if not emitted_something:
            contains_eligible.append((k, api_attribute, matcher, str_values))

    return emitted, contains_eligible


def _contains_scan(
    contains_eligible: list[tuple[str, str, str, list[str]]],
    *,
    chosen_attrs: set[str],
    min_len: int,
    rows: list[dict[str, Any]],
    array_valued_keys: frozenset[str],
) -> list[dict[str, Any]]:
    emitted: list[dict[str, Any]] = []
    for k, api_attribute, matcher, str_values in contains_eligible:
        if api_attribute in chosen_attrs:
            continue
        common = longest_common_substring(str_values, min_len)
        if len(common) < min_len:
            continue
        raw_values = distinct_values(rows, k, array_valued_keys=array_valued_keys)
        frag = _emit_substring_dql(k, "CONTAINS", common, array_valued_keys=array_valued_keys)
        if frag is None:
            continue
        emitted.append(_make_candidate(
            dql_key=k, api_attribute=api_attribute, matcher=matcher,
            values=raw_values, substring=common,
            operator="CONTAINS", substring_kind="contains",
            dql_fragment=frag,
        ))
        chosen_attrs.add(api_attribute)
    return emitted


def _make_candidate(  # pylint: disable=too-many-arguments
    *,
    dql_key: str,
    api_attribute: str,
    matcher: str,
    values: list[Any],
    substring: str,
    operator: str,
    substring_kind: str,
    dql_fragment: str,
) -> dict[str, Any]:
    return {
        "dql_key": dql_key,
        "distinct_count": len(values),
        "values": [substring],
        "dql_fragment": dql_fragment,
        "kind": "substring_full",
        "api_attribute": api_attribute,
        "api_matcher_type": matcher,
        "api_operator": operator,
        "substring_kind": substring_kind,
    }


def _sort_candidates(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        cands,
        key=lambda c: (
            _KIND_RANK.get(c["kind"], 99),
            -len(c["values"][0]) if c["kind"] == "substring_full" and c.get("values") else 0,
            c["distinct_count"] if c["kind"] != "substring_full" else 0,
            c["dql_key"],
        ),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def augment_candidates(  # pylint: disable=too-many-arguments,too-many-locals,too-many-statements
    *,
    rule_id: str,
    case: str,
    entity_key: str,
    span_key: str | None,
    cache_dir: Path,
    derived_dir: Path,
    min_substring_len: int = MIN_SUBSTRING_LEN,
    mapping: ConditionMapping | None = None,
    _io_load=None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Augment the Step-3 artifact with substring candidates."""
    m = mapping or load_mapping()
    load = _io_load or _default_load

    sidecar = load(derived_dir / f"{rule_id}.json")
    if has_unmigratable(sidecar):
        raise UnmigratableRuleError(rule_id)

    surviving_attrs = _expand_surviving_attrs(surviving_api_attributes(sidecar))

    entity_dql_to_api = _build_entity_dql_key_to_api(m)
    span_dql_to_api = _build_span_dql_key_to_api(m)
    api_matcher = _build_api_matcher(m)
    array_valued_keys = _build_array_valued(m)
    unmigratable_as_candidates = frozenset(m.unmigratable_as_candidates)
    scope_aware = m.scope_aware_partitions

    mode = mode or ("entity_only" if case == "A" else "full")

    step3: dict[str, Any] = load(derived_dir / f"{rule_id}_candidates.json")

    entity_rows: list[dict[str, Any]] = load(cache_dir / f"{entity_key}_s_super.json")
    span_rows: list[dict[str, Any]] = []

    if mode == "full":
        if not span_key:
            raise ValueError("span_key required for mode 'full'")
        span_rows = load(cache_dir / f"{span_key}_e_orig.json")
        s_orig = set(load(cache_dir / f"{span_key}_s_orig.json"))
        entity_rows = [r for r in entity_rows if _row_id(r) in s_orig]

    # Build artifact copy (idempotent: feeding output back → identical result).
    artifact: dict[str, Any] = {
        "rule_id": step3["rule_id"],
        "mode": step3["mode"],
        "source_keys": dict(step3.get("source_keys", {})),
        "surviving_original_conditions": list(step3.get("surviving_original_conditions", [])),
        "entity_candidates": list(step3.get("entity_candidates", [])),
        "span_candidates": list(step3.get("span_candidates", [])),
        "discarded_for_report": list(step3.get("discarded_for_report", [])),
        "notes": list(step3.get("notes", [])),
    }

    chosen_attrs: set[str] = {
        c["api_attribute"]
        for c in artifact["entity_candidates"] + artifact["span_candidates"]
    }

    # Build service-id → serviceType index for scope-aware resolution.
    service_type_index: dict[str, list[str]] = {}
    for row in entity_rows:
        rid = _row_id(row)
        if rid is None:
            continue
        v = row.get("serviceType")
        service_type_index[rid] = list(v) if isinstance(v, list) else ([v] if v is not None else [])

    entity_new, entity_contains_pool = _prefix_suffix_scan(
        entity_rows,
        _rescuable_keys(entity_rows, _STRUCTURAL_ENTITY),
        surviving_attrs=surviving_attrs,
        chosen_attrs=chosen_attrs,
        min_len=min_substring_len,
        service_type_index=service_type_index,
        entity_dql_to_api=entity_dql_to_api,
        span_dql_to_api=span_dql_to_api,
        scope_aware=scope_aware,
        unmigratable_as_candidates=unmigratable_as_candidates,
        api_matcher=api_matcher,
        array_valued_keys=array_valued_keys,
    )
    artifact["entity_candidates"].extend(entity_new)

    span_contains_pool: list[tuple[str, str, str, list[str]]] = []
    if mode == "full":
        span_new, span_contains_pool = _prefix_suffix_scan(
            span_rows,
            _rescuable_keys(span_rows, _STRUCTURAL_SPAN),
            surviving_attrs=surviving_attrs,
            chosen_attrs=chosen_attrs,
            min_len=min_substring_len,
            service_type_index=service_type_index,
            entity_dql_to_api=entity_dql_to_api,
            span_dql_to_api=span_dql_to_api,
            scope_aware=scope_aware,
            unmigratable_as_candidates=unmigratable_as_candidates,
            api_matcher=api_matcher,
            array_valued_keys=array_valued_keys,
        )
        artifact["span_candidates"].extend(span_new)

    # Contains fallback — fires only when no candidates exist yet on either side.
    if not artifact["entity_candidates"] and not artifact["span_candidates"]:
        entity_contains = _contains_scan(
            entity_contains_pool,
            chosen_attrs=chosen_attrs,
            min_len=min_substring_len,
            rows=entity_rows,
            array_valued_keys=array_valued_keys,
        )
        artifact["entity_candidates"].extend(entity_contains)
        if mode == "full":
            span_contains = _contains_scan(
                span_contains_pool,
                chosen_attrs=chosen_attrs,
                min_len=min_substring_len,
                rows=span_rows,
                array_valued_keys=array_valued_keys,
            )
            artifact["span_candidates"].extend(span_contains)

    # Re-sort.
    artifact["entity_candidates"] = _sort_candidates(artifact["entity_candidates"])
    artifact["span_candidates"] = _sort_candidates(artifact["span_candidates"])

    # Drop discard entries whose dql_key now has a candidate.
    covered_keys = {
        c["dql_key"]
        for c in artifact["entity_candidates"] + artifact["span_candidates"]
    }
    artifact["discarded_for_report"] = sorted(
        [d for d in artifact["discarded_for_report"] if d["dql_key"] not in covered_keys],
        key=lambda d: d["dql_key"],
    )

    # Append rescue notes for newly emitted substring candidates.
    pre_existing_sigs = {
        (c["dql_key"], c.get("substring_kind"))
        for c in step3.get("entity_candidates", []) + step3.get("span_candidates", [])
    }
    for c in artifact["entity_candidates"] + artifact["span_candidates"]:
        if c["kind"] != "substring_full":
            continue
        sig = (c["dql_key"], c.get("substring_kind"))
        if sig in pre_existing_sigs:
            continue
        artifact["notes"].append(
            f"substring rescue: {c['dql_key']} {c['substring_kind']}({c['values'][0]}) "
            f"covers all {c['distinct_count']} distinct values"
        )

    return artifact


__all__ = [
    "augment_candidates",
    "longest_common_prefix",
    "longest_common_suffix",
    "longest_common_substring",
]
