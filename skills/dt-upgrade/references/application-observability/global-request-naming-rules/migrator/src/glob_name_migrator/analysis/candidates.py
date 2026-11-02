"""Find replacement candidates.

Scores entity and span query results and builds a per-rule
``derived/<rule_id>_candidates.json`` artifact describing which non-deprecated
attributes can replace the deprecated conditions.

Pure post-processing — no DQL queries are issued. Lookup tables are derived
from ``rules/mapping.py`` (the ``load_mapping()`` singleton).

Mode is derived from the rule's case:
  - Case A  → "entity_only" (only ``<entity_key>_s_super.json`` is read)
  - Case C → "full" (entity + span rows; entity rows narrowed to S_orig)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, TypedDict

from ..rules.mapping import (
    ConditionMapping,
    EntityAttributeRow,
    ScopeAwareEntry,
    base_attribute,
    compose_attribute,
    load_mapping,
)
from ..rules.tags import is_primary_tag_key

# ---------------------------------------------------------------------------
# Candidate quality
# ---------------------------------------------------------------------------

_VALUE_HEURISTICS: dict[str, Callable[[list[str]], bool]] = {
    "contextRoot": lambda vals: all(len(v) > 1 for v in vals),
}

# Attributes that are functionally equivalent for surviving-condition blocking.
# If any member is already a surviving condition, all members are blocked as candidates.
_SURVIVING_ATTR_EQUIVALENCES: tuple[frozenset[str], ...] = (
    frozenset({"WEBREQUEST_URL", "WEBREQUEST_URL_PATH"}),
)


def _expand_surviving_attrs(surviving: set[str]) -> set[str]:
    """Expand surviving attrs to include equivalence-group siblings.

    Ensures that if e.g. WEBREQUEST_URL is a surviving condition, candidates
    for WEBREQUEST_URL_PATH and WEBREQUEST_RELATIVE_URL are also suppressed
    since all three target the same DQL field (url.path).
    """
    expanded = set(surviving)
    for group in _SURVIVING_ATTR_EQUIVALENCES:
        if group & surviving:
            expanded |= group
    return expanded


class _ScoreKwargs(TypedDict):
    surviving_attrs: set[str]
    partial_cap: int
    service_type_index: dict[str, list[str]]
    entity_dql_to_api: dict[str, str]
    span_dql_to_api: dict[str, str]
    scope_aware: dict[str, ScopeAwareEntry]
    unmigratable_as_candidates: frozenset[str]
    api_matcher: dict[str, str]
    array_valued_keys: frozenset[str]

PARTIAL_CAP_DEFAULT = 5

# Matcher types that admit an ``*_ANY_OF`` / ``in(...)`` variant.
_MATCHER_SUPPORTS_ANY_OF: frozenset[str] = frozenset(
    {
        "STRING",
        "NUMBER",
        "BOOLEAN",
        "HTTP_METHOD",
        "HTTP_STATUS_CLASS",
        "SERVICE_TYPE",
        "ZOS_TRANSACTIONTYPE",
        "ESB_INPUT_NODE_TYPE",
        "FLAW_STATE",
        "TAG",
        "FAST_STRING",
        "REQUEST_ATTRIBUTE",
    }
)

# Structural columns that are never candidate axes.
_STRUCTURAL_ENTITY: frozenset[str] = frozenset({"id"})
_STRUCTURAL_SPAN: frozenset[str] = frozenset(
    {"dt.smartscape.service", "endpoint.name", "span_count"}
)


# ---------------------------------------------------------------------------
# Lookup-table builders (derived from rules/mapping.py via load_mapping())
# ---------------------------------------------------------------------------


def _build_entity_dql_key_to_api(m: ConditionMapping) -> dict[str, str]:
    """Map entity-side DQL column names to their primary api_attribute.

    Restricted to candidate_eligible dt.entity.service rows.  Scope-aware
    defaults are stored here; scope resolution happens at scoring time.
    Duplicate dql_keys: first candidate_eligible dt.entity.service entry wins.
    """
    result: dict[str, str] = {}
    for k, api in m.dql_key_index(candidate_eligible_only=True).items():
        row = m.by_api_attribute(api)
        if isinstance(row, EntityAttributeRow) and row.fetch_source == "dt.entity.service":
            result[k] = api
    return result


def _build_span_dql_key_to_api(m: ConditionMapping) -> dict[str, str]:
    """Map span DQL column names to api_attribute (candidate_eligible only)."""
    result: dict[str, str] = {}
    for k, api in m.dql_key_index(candidate_eligible_only=True).items():
        if not m.is_entity(api):
            result[k] = api
    return result


def _build_api_matcher(m: ConditionMapping) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in list(m.entity_attributes) + list(m.span_attributes):
        result[row.api_attribute] = row.matcher_type
    return result



def _build_array_valued(m: ConditionMapping) -> frozenset[str]:
    return frozenset(
        row.dql_key
        for row in list(m.entity_attributes) + list(m.span_attributes)
        if row.array_valued and row.dql_key is not None
    )


# ---------------------------------------------------------------------------
# Scope-aware resolution
# ---------------------------------------------------------------------------


def resolve_api_attribute(  # pylint: disable=too-many-return-statements
    dql_key: str,
    observed_service_types: list[str] | None,
    *,
    entity_dql_to_api: dict[str, str],
    span_dql_to_api: dict[str, str],
    scope_aware: dict[str, ScopeAwareEntry],
) -> str | None:
    """Resolve a DQL key to its final api_attribute, honouring scope partitions.

    Returns ``None`` when the key is unresolvable (scope mixed with
    ``"unmigratable"`` behavior, or no data, or key unknown).
    """
    entry = scope_aware.get(dql_key)
    if entry is None:
        # Not scope-aware — look up in combined tables.
        return entity_dql_to_api.get(dql_key) or span_dql_to_api.get(dql_key)

    types = set(observed_service_types or [])
    narrower_types = {p.service_type for p in entry.partitions}
    type_to_attr = {p.service_type: p.api_attribute for p in entry.partitions}
    intersection = types & narrower_types

    behavior = entry.mixed_behavior

    if behavior in ("default_unless_scoped", "default_only"):
        return entry.default_api_attribute

    if behavior == "narrower_wins":
        if len(intersection) == 1:
            return type_to_attr[next(iter(intersection))]
        return entry.default_api_attribute

    # "unmigratable" behavior: strict single-type resolution.
    if len(intersection) == 0:
        return entry.default_api_attribute  # may be None
    if len(intersection) == 1:
        return type_to_attr[next(iter(intersection))]
    return None  # mixed → unmigratable


# ---------------------------------------------------------------------------
# Sidecar helpers
# ---------------------------------------------------------------------------


def surviving_api_attributes(sidecar: dict[str, Any]) -> set[str]:
    """Return the set of api_attributes for surviving (non-deprecated) conditions.

    Prefers the ``api_attributes`` list, which carries one composite identity per
    primary tag key — a condition can survive on several keys at once.
    """
    result: set[str] = set()
    for c in sidecar.get("conditions", []):
        if c.get("lifecycle") != "surviving":
            continue
        result.update(c.get("api_attributes") or [c["attribute"]])
    return result


def has_unmigratable(sidecar: dict[str, Any]) -> bool:
    """Return True if the sidecar contains at least one unmigratable condition."""
    return sidecar.get("unmigratable_count", 0) > 0


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def _is_null(v: Any) -> bool:
    return v is None or v == "" or (isinstance(v, list) and len(v) == 0)


def distinct_values(rows: list[dict[str, Any]], key: str, *, array_valued_keys: frozenset[str]) -> list[Any]:
    """Distinct values for ``key`` across ``rows``.  Array-valued keys are
    flattened element-wise.  Order of first appearance is preserved; nulls are
    excluded.
    """
    seen: set = set()
    result: list[Any] = []

    def _add(v: Any) -> None:
        if _is_null(v) or v in seen:
            return
        seen.add(v)
        result.append(v)

    is_array = key in array_valued_keys
    for row in rows:
        val = row.get(key)
        if val is None:
            continue
        if is_array and isinstance(val, list):
            for elem in val:
                _add(elem)
        else:
            _add(val)
    return result


def _quote(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _emit_dql_fragment(
    dql_key: str, matcher: str, values: list[Any], *, array_valued_keys: frozenset[str]
) -> str:
    """Build the DQL filter fragment for a candidate condition."""
    def _val(v: Any) -> str:
        # NUMBER matcher fields are numeric in Grail — never quote them.
        if matcher == "NUMBER":
            try:
                n = int(str(v))
                return str(n)
            except (ValueError, TypeError):
                try:
                    return str(float(str(v)))
                except (ValueError, TypeError):
                    pass
        return _quote(v)

    if dql_key in array_valued_keys:
        # Array-valued fields: in(needle, haystack...) — no set braces.
        if len(values) == 1:
            return f"in({dql_key}, {_val(values[0])})"
        return f"in({dql_key}, {', '.join(_val(v) for v in values)})"
    if len(values) == 1:
        return f"{dql_key} == {_val(values[0])}"
    inner = ", ".join(_val(v) for v in values)
    return f"in({dql_key}, {{{inner}}})"


def _api_operator(distinct_count: int) -> str:
    return "EQUALS" if distinct_count == 1 else "EQUALS_ANY_OF"


# ---------------------------------------------------------------------------
# Per-attribute scoring
# ---------------------------------------------------------------------------


def _row_service_types(
    row: dict[str, Any],
    service_type_index: dict[str, list[str]] | None,
) -> list[str]:
    v = row.get("serviceType")
    if v is not None:
        return list(v) if isinstance(v, list) else [v]
    if service_type_index is not None:
        sid = row.get("dt.smartscape.service")
        if sid is not None:
            return list(service_type_index.get(sid, []))
    return []


def _row_id(row: dict[str, Any]) -> str | None:
    for k in ("id", "dt.entity.service", "dt.smartscape.service"):
        if k in row and row[k] is not None:
            return row[k]
    return None


def _score_primary_tag(
    rows: list[dict[str, Any]],
    dql_key: str,
    *,
    surviving_attrs: set[str],
    partial_cap: int,
    array_valued_keys: frozenset[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Score a discovered ``primary_tags.*`` span column as a TAG candidate.

    Deliberately simpler than :func:`_score_attribute`: primary tags are not in
    the static mapping (they are tenant data), are never scope-aware, and get no
    substring rescue — Phase 3 matches them with exact string equality, so a
    prefix or contains candidate could not be expressed as a condition.

    Dedup is key-level: the composite ``PROCESS_GROUP_TAG@<key>`` identity means a
    surviving condition on one tag key does not suppress candidates on another.
    """
    api_attribute = compose_attribute("PROCESS_GROUP_TAG", dql_key)
    if api_attribute in surviving_attrs:
        return None, None

    raw_values = [row.get(dql_key) for row in rows if dql_key in row]

    # An array-valued tag can never match: the runtime requires a String and
    # rejects anything else before comparing, so a candidate built on this key
    # would produce a rule that matches nothing. Drop the key, not the rule.
    if any(isinstance(v, list) for v in raw_values):
        return None, {
            "dql_key": dql_key,
            "distinct_count": 0,
            "reason": "array_valued",
        }

    values = distinct_values(rows, dql_key, array_valued_keys=array_valued_keys)
    distinct = len(values)
    if distinct == 0:
        return None, None

    if any(_is_null(row.get(dql_key)) for row in rows):
        return None, {
            "dql_key": dql_key,
            "distinct_count": distinct,
            "reason": "null_in_some_rows",
        }

    if distinct == 1:
        kind = "full"
    elif distinct <= partial_cap:
        kind = "partial_promoted"
    else:
        return None, {
            "dql_key": dql_key,
            "distinct_count": distinct,
            "reason": "above_partial_cap",
        }

    candidate = {
        "dql_key": dql_key,
        "distinct_count": distinct,
        "values": values,
        "dql_fragment": _emit_dql_fragment(
            dql_key, "TAG", values, array_valued_keys=array_valued_keys
        ),
        "kind": kind,
        "api_attribute": api_attribute,
        "api_matcher_type": "TAG",
        "api_operator": _api_operator(distinct),
    }
    return candidate, None


def _score_attribute(  # pylint: disable=too-many-arguments,too-many-locals,too-many-return-statements,too-many-branches
    rows: list[dict[str, Any]],
    dql_key: str,
    *,
    surviving_attrs: set[str],
    partial_cap: int,
    service_type_index: dict[str, list[str]] | None,
    entity_dql_to_api: dict[str, str],
    span_dql_to_api: dict[str, str],
    scope_aware: dict[str, ScopeAwareEntry],
    unmigratable_as_candidates: frozenset[str],
    api_matcher: dict[str, str],
    array_valued_keys: frozenset[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Score a single DQL key. Returns (candidate, discarded) — at most one set."""
    if is_primary_tag_key(dql_key):
        return _score_primary_tag(
            rows, dql_key,
            surviving_attrs=surviving_attrs,
            partial_cap=partial_cap,
            array_valued_keys=array_valued_keys,
        )

    is_scope_aware = dql_key in scope_aware

    if is_scope_aware:
        entry = scope_aware[dql_key]
        resolved_attrs: set[str] = set()
        row_level_mixed = False
        contributing = 0
        for row in rows:
            if dql_key not in row or _is_null(row.get(dql_key)):
                continue
            contributing += 1
            sts = _row_service_types(row, service_type_index)
            attr = resolve_api_attribute(
                dql_key, sts,
                entity_dql_to_api=entity_dql_to_api,
                span_dql_to_api=span_dql_to_api,
                scope_aware=scope_aware,
            )
            if attr is None:
                row_level_mixed = True
                continue
            resolved_attrs.add(attr)

        if contributing == 0:
            return None, None

        # For "unmigratable" behavior: any row-level mixed or inter-row mixed → discard
        if entry.mixed_behavior == "unmigratable":
            if row_level_mixed or len(resolved_attrs) > 1:
                return None, {
                    "dql_key": dql_key,
                    "distinct_count": len(distinct_values(rows, dql_key, array_valued_keys=array_valued_keys)),
                    "reason": "mixed_service_types",
                }
            if len(resolved_attrs) == 0:
                return None, {
                    "dql_key": dql_key,
                    "distinct_count": len(distinct_values(rows, dql_key, array_valued_keys=array_valued_keys)),
                    "reason": "no_scope_narrower_service_type_and_no_default",
                }

        if len(resolved_attrs) == 0 and entry.default_api_attribute is not None:
            api_attribute = entry.default_api_attribute
        elif len(resolved_attrs) == 1:
            api_attribute = next(iter(resolved_attrs))
        else:
            # For default_only / default_unless_scoped, resolved_attrs is always
            # empty here and a non-None default was already checked above, so this
            # branch is only reachable for "narrower_wins" / "unmigratable" with
            # zero resolved attrs and no default (i.e. no data → skip silently).
            return None, None

    else:
        api_attribute = resolve_api_attribute(
            dql_key, None,
            entity_dql_to_api=entity_dql_to_api,
            span_dql_to_api=span_dql_to_api,
            scope_aware=scope_aware,
        )
        if api_attribute is None:
            return None, None

    if api_attribute in surviving_attrs:
        return None, None
    if api_attribute in unmigratable_as_candidates:
        return None, None
    if api_attribute == "__MANAGEMENT_ZONES__":
        return None, None

    matcher = api_matcher.get(api_attribute)
    if matcher is None:
        return None, None

    values = distinct_values(rows, dql_key, array_valued_keys=array_valued_keys)
    distinct = len(values)
    if distinct == 0:
        return None, None

    # Every row must have a non-null value for this key.  A candidate with
    # null in some rows would exclude those services when used as an AND filter
    # in verification (e.g. in(applicationEnvironment, "dev") returns 0 rows
    # for a service with applicationEnvironment=None).
    null_count = sum(1 for row in rows if _is_null(row.get(dql_key)))
    if null_count > 0:
        return None, {
            "dql_key": dql_key,
            "distinct_count": distinct,
            "reason": "null_in_some_rows",
        }

    if distinct == 1:
        kind = "full"
    elif distinct <= partial_cap:
        if matcher in _MATCHER_SUPPORTS_ANY_OF:
            kind = "partial_promoted"
        else:
            return None, {
                "dql_key": dql_key,
                "distinct_count": distinct,
                "reason": "matcher_does_not_support_any_of",
            }
    else:
        return None, {
            "dql_key": dql_key,
            "distinct_count": distinct,
            "reason": "above_partial_cap",
        }

    candidate = {
        "dql_key": dql_key,
        "distinct_count": distinct,
        "values": values,
        "dql_fragment": _emit_dql_fragment(dql_key, matcher, values, array_valued_keys=array_valued_keys),
        "kind": kind,
        "api_attribute": api_attribute,
        "api_matcher_type": matcher,
        "api_operator": _api_operator(distinct),
    }
    return candidate, None


def _candidate_keys(rows: list[dict[str, Any]], skip: frozenset[str]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row:
            if k in skip or k in seen:
                continue
            seen.add(k)
            keys.append(k)
    return keys


def _sort_candidates(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kind_rank = {"full": 0, "partial_promoted": 1}
    return sorted(
        cands,
        key=lambda c: (kind_rank.get(c["kind"], 99), c["distinct_count"], c["dql_key"]),
    )


# ---------------------------------------------------------------------------
# Quality classification (single source of truth)
# ---------------------------------------------------------------------------


def is_good_candidate(c: dict[str, Any], *, api_to_quality: dict[str, str]) -> bool:
    """Return True if *c* is a good-quality candidate.

    Quality is looked up from the mapping (never stored in the candidate dict)
    so it stays consistent regardless of which list the candidate lives in or
    whether it was injected by a post-processing step.
    """
    api_attribute = base_attribute(c.get("api_attribute", ""))
    if api_to_quality.get(api_attribute, "good") != "good":
        return False
    dql_key = c.get("dql_key", "")
    if dql_key in _VALUE_HEURISTICS:
        values = [str(v) for v in c.get("values", [])]
        return _VALUE_HEURISTICS[dql_key](values)
    return True


# ---------------------------------------------------------------------------
# Quality filtering and deduplication
# ---------------------------------------------------------------------------



def _deduplicate_by_values(
    candidates: list[dict[str, Any]],
    discarded: list[dict[str, Any]],
    *,
    seen: set[frozenset] | None = None,
) -> tuple[list[dict[str, Any]], set[frozenset]]:
    """Remove candidates whose value set is identical to an earlier candidate.

    Accepts an optional *seen* set so callers can chain entity and span passes —
    a span candidate whose values already appeared on the entity side is dropped.
    Returns the filtered list and the updated seen set.
    """
    if seen is None:
        seen = set()
    result: list[dict[str, Any]] = []
    for c in candidates:
        key = frozenset(str(v) for v in c.get("values", []))
        if key in seen:
            discarded.append({
                "dql_key": c["dql_key"],
                "distinct_count": c["distinct_count"],
                "reason": "duplicate_values",
            })
        else:
            seen.add(key)
            result.append(c)
    return result, seen


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


class UnmigratableRuleError(Exception):
    """Raised when a rule contains a condition that cannot be migrated."""

    def __init__(self, rule_id: str) -> None:
        super().__init__(f"rule {rule_id} contains an unmigratable condition")
        self.rule_id = rule_id


def build_candidates(  # pylint: disable=too-many-arguments,too-many-locals
    *,
    rule_id: str,
    case: str,
    entity_key: str,
    span_key: str | None,
    cache_dir: Path,
    derived_dir: Path,
    partial_cap: int = PARTIAL_CAP_DEFAULT,
    mapping: ConditionMapping | None = None,
    _io_load=None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Build the Step-3 candidates artifact for one rule.

    ``mapping`` defaults to ``load_mapping()``; pass a fixture for tests.
    ``_io_load`` is a ``path -> Any`` injection point for tests.
    """
    m = mapping or load_mapping()
    load = _io_load or _default_load

    sidecar = load(derived_dir / f"{rule_id}.json")
    if has_unmigratable(sidecar):
        raise UnmigratableRuleError(rule_id)

    surviving_attrs = _expand_surviving_attrs(surviving_api_attributes(sidecar))

    # Build lookup tables from mapping.
    entity_dql_to_api = _build_entity_dql_key_to_api(m)
    span_dql_to_api = _build_span_dql_key_to_api(m)
    api_matcher = _build_api_matcher(m)
    array_valued_keys = _build_array_valued(m)
    unmigratable_as_candidates = frozenset(m.unmigratable_as_candidates)
    scope_aware = m.scope_aware_partitions

    mode = mode or ("entity_only" if case == "A" else "full")

    entity_rows: list[dict[str, Any]] = load(cache_dir / f"{entity_key}_s_super.json")
    span_rows: list[dict[str, Any]] = []
    s_orig: set[str] | None = None

    if mode == "full":
        if not span_key:
            raise ValueError("span_key is required for mode 'full'")
        span_rows = load(cache_dir / f"{span_key}_e_orig.json")
        s_orig_list: list[str] = load(cache_dir / f"{span_key}_s_orig.json")
        s_orig = set(s_orig_list)
        # Narrow entity rows to S_orig.
        entity_rows = [r for r in entity_rows if _row_id(r) in s_orig]

    # Build service-id → serviceType index from entity rows (for span scope resolution).
    service_type_index: dict[str, list[str]] = {}
    for row in entity_rows:
        rid = _row_id(row)
        if rid is None:
            continue
        v = row.get("serviceType")
        service_type_index[rid] = list(v) if isinstance(v, list) else ([v] if v is not None else [])

    _score_kwargs: _ScoreKwargs = _ScoreKwargs(
        surviving_attrs=surviving_attrs,
        partial_cap=partial_cap,
        service_type_index=service_type_index,
        entity_dql_to_api=entity_dql_to_api,
        span_dql_to_api=span_dql_to_api,
        scope_aware=scope_aware,
        unmigratable_as_candidates=unmigratable_as_candidates,
        api_matcher=api_matcher,
        array_valued_keys=array_valued_keys,
    )

    entity_candidates: list[dict[str, Any]] = []
    span_candidates: list[dict[str, Any]] = []
    discarded: list[dict[str, Any]] = []

    # Entity side.
    for k in _candidate_keys(entity_rows, _STRUCTURAL_ENTITY):
        cand, disc = _score_attribute(entity_rows, k, **_score_kwargs)
        if cand is not None:
            entity_candidates.append(cand)
        if disc is not None:
            discarded.append(disc)

    # Span side (full mode only).
    if mode == "full":
        for k in _candidate_keys(span_rows, _STRUCTURAL_SPAN):
            cand, disc = _score_attribute(span_rows, k, **_score_kwargs)
            if cand is not None:
                span_candidates.append(cand)
            if disc is not None:
                discarded.append(disc)

    # Entity side runs first so entity candidates always win cross-side dedup:
    # a span candidate whose value set matches an entity candidate is discarded.
    entity_candidates, _seen = _deduplicate_by_values(_sort_candidates(entity_candidates), discarded)
    span_candidates, _ = _deduplicate_by_values(_sort_candidates(span_candidates), discarded, seen=_seen)

    # Build surviving conditions list for downstream steps.
    surviving = [
        {
            "api_attribute": c["attribute"],
            "level": c.get("side", "entity"),
            "dql_fragment": c.get("dql"),
            "api_condition": None,
        }
        for c in sidecar.get("conditions", [])
        if c.get("lifecycle") == "surviving"
    ]

    return {
        "rule_id": rule_id,
        "mode": mode,
        "source_keys": {
            "entity_key": entity_key,
            "span_key": span_key if mode == "full" else None,
        },
        "surviving_original_conditions": surviving,
        "entity_candidates": entity_candidates,
        "span_candidates": span_candidates,
        "discarded_for_report": sorted(discarded, key=lambda d: d["dql_key"]),
        "notes": [],
    }


def write_candidates(derived_dir: Path, artifact: dict[str, Any]) -> Path:
    """Write the candidates artifact atomically and return the path."""
    derived_dir.mkdir(parents=True, exist_ok=True)
    out = derived_dir / f"{artifact['rule_id']}_candidates.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(artifact, indent=2, ensure_ascii=False))
    tmp.replace(out)
    return out


def _default_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "UnmigratableRuleError",
    "is_good_candidate",
    "build_candidates",
    "write_candidates",
    "distinct_values",
    "surviving_api_attributes",
    "has_unmigratable",
]
