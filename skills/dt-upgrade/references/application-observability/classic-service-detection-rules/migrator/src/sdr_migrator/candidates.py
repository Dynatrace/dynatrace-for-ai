from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .conditions import ATTRIBUTE_MAP

DiscardReason = Literal["null_present", "too_many_values", "array_valued"]

_ENTITY_CANDIDATE_FIELDS: list[tuple[str, str]] = [
    ("APPLICATION_ID", "webApplicationId"),
    ("CONTEXT_ROOT", "contextRoot"),
]

_PARTIAL_CAP = 5
_MIN_SUBSTRING_LEN = 4

_SUBSTRING_KINDS = frozenset({"prefix", "suffix", "contains"})


def _sort_key(c: Candidate) -> tuple:
    """Deterministic candidate ordering (ascending = best first).

    kind rank full(0) < partial(1) < substring(2); within substrings the longest
    shared value first (more specific); then fewer distinct values first; then a
    lexical tie-break on (grail_key, attribute_type).
    """
    if c.kind in _SUBSTRING_KINDS:
        kind_rank = 2
        substring_len = -len(c.values[0]) if c.values else 0
        distinct = len(c.raw_values or ())
    else:
        kind_rank = 0 if len(c.values) == 1 else 1
        substring_len = 0
        distinct = len(c.values)
    return (kind_rank, substring_len, distinct, c.grail_key, c.attribute_type)


@dataclass(frozen=True)
class Candidate:
    attribute_type: str
    grail_key: str
    values: list[str]
    quality: str
    kind: str = "exact"  # "exact" | "prefix" | "suffix" | "contains"
    raw_values: list[str] | None = None  # full distinct set behind a substring candidate


@dataclass(frozen=True)
class DiscardedAttribute:
    attribute_type: str
    grail_key: str
    reason: DiscardReason
    distinct_count: int


def score_entity_candidates(entity_rows: list[dict]) -> list[Candidate]:
    """Score APPLICATION_ID and CONTEXT_ROOT candidates from service entity rows."""
    if not entity_rows:
        return []

    candidates: list[Candidate] = []
    for attr_type, entity_field in _ENTITY_CANDIDATE_FIELDS:
        raw_values = [row.get(entity_field) for row in entity_rows]
        if any(v is None for v in raw_values):
            continue
        distinct = sorted({str(v) for v in raw_values})
        if 1 <= len(distinct) <= _PARTIAL_CAP:
            candidates.append(
                Candidate(
                    attribute_type=attr_type,
                    grail_key="",
                    values=distinct,
                    quality="entity-only",
                )
            )
    return candidates


def _longest_common_prefix(values: list[str]) -> str:
    shortest = min(values, key=len)
    for i, ch in enumerate(shortest):
        if any(v[i] != ch for v in values):
            return shortest[:i]
    return shortest


def _longest_common_suffix(values: list[str]) -> str:
    reversed_values = [v[::-1] for v in values]
    return _longest_common_prefix(reversed_values)[::-1]


def _common_substring_of_length(values: list[str], length: int) -> str | None:
    """First substring of exactly `length` shared by every value, or None."""
    sets = [{v[i : i + length] for i in range(len(v) - length + 1)} for v in values]
    common = sets[0]
    for s in sets[1:]:
        common &= s
        if not common:
            return None
    return min(common)


def _longest_common_substring(values: list[str]) -> str:
    """Longest substring shared by all values, via descending-length set intersection.

    O(L^2 * N) worst case (L = shortest value length, N = value count) -- adequate
    for span-derived string cardinalities; not worth a suffix-automaton here.
    """
    max_len = min(len(v) for v in values)
    for length in range(max_len, _MIN_SUBSTRING_LEN - 1, -1):
        found = _common_substring_of_length(values, length)
        if found is not None:
            return found
    return ""


def _rescue_substring(values: list[str]) -> tuple[str, str] | None:
    """Try shared prefix, then suffix, then substring, each above the minimum length."""
    prefix = _longest_common_prefix(values)
    if len(prefix) >= _MIN_SUBSTRING_LEN:
        return prefix, "prefix"
    suffix = _longest_common_suffix(values)
    if len(suffix) >= _MIN_SUBSTRING_LEN:
        return suffix, "suffix"
    substring = _longest_common_substring(values)
    if len(substring) >= _MIN_SUBSTRING_LEN:
        return substring, "contains"
    return None


def score_candidates(  # pylint: disable=too-many-locals
    rows: list[dict],
    rule_type: str,
    surviving_attribute_types: frozenset[str] = frozenset(),
    *,
    primary_tag_keys: list[str] | None = None,
    surviving_primary_tag_keys: frozenset[str] = frozenset(),
) -> tuple[list[Candidate], list[DiscardedAttribute]]:
    """Score candidate conditions from span rows.

    Returns (candidates, discarded):
    - 1 distinct non-null value  → full Candidate (single EQUALS)
    - 2–5 distinct non-null values → partial Candidate (multi-value OR)
    - any null row               → DiscardedAttribute(reason="null_present")
    - >5 distinct values, shared prefix/suffix/substring ≥4 chars →
      substring-rescue Candidate (STARTS_WITH / ENDS_WITH / CONTAINS)
    - >5 distinct values, no shared prefix/suffix/substring → DiscardedAttribute(reason="too_many_values")
    - array-valued primary tag → DiscardedAttribute(reason="array_valued") (see _score_primary_tags)
    Candidates are returned in deterministic order (see _sort_key): full before
    partial before substring; longest substring first; fewer distinct first;
    lexical tie-break on grail_key.

    Attribute types in ``surviving_attribute_types`` are already present as surviving
    conditions on the rule; they are blocked at the source so scoring never re-derives
    a condition the rule already carries. Since every candidate-eligible attribute type maps to a
    distinct grail_key, a plain block-by-attribute-type suffices (no equivalence group).
    """
    if not rows:
        return [], []

    full: list[Candidate] = []
    partial: list[Candidate] = []
    substring: list[Candidate] = []
    discarded: list[DiscardedAttribute] = []

    for attr_type, info in ATTRIBUTE_MAP.get(rule_type, {}).items():
        if not info.candidate_eligible or not info.grail_key:
            continue
        if attr_type in surviving_attribute_types:
            continue

        raw_values = [row.get(info.grail_key) for row in rows]

        if any(v is None for v in raw_values):
            distinct_non_null = sorted({str(v) for v in raw_values if v is not None})
            discarded.append(
                DiscardedAttribute(
                    attribute_type=attr_type,
                    grail_key=info.grail_key,
                    reason="null_present",
                    distinct_count=len(distinct_non_null),
                )
            )
            continue

        distinct = sorted({str(v) for v in raw_values})

        if len(distinct) == 1:
            full.append(
                Candidate(
                    attribute_type=attr_type,
                    grail_key=info.grail_key,
                    values=distinct,
                    quality=info.quality,
                )
            )
        elif len(distinct) <= _PARTIAL_CAP:
            partial.append(
                Candidate(
                    attribute_type=attr_type,
                    grail_key=info.grail_key,
                    values=distinct,
                    quality=info.quality,
                )
            )
        else:
            rescue = _rescue_substring(distinct)
            if rescue is not None:
                value, kind = rescue
                substring.append(
                    Candidate(
                        attribute_type=attr_type,
                        grail_key=info.grail_key,
                        values=[value],
                        quality=info.quality,
                        kind=kind,
                        raw_values=distinct,
                    )
                )
            else:
                discarded.append(
                    DiscardedAttribute(
                        attribute_type=attr_type,
                        grail_key=info.grail_key,
                        reason="too_many_values",
                        distinct_count=len(distinct),
                    )
                )

    _score_primary_tags(
        rows, primary_tag_keys or [], surviving_primary_tag_keys,
        full=full, partial=partial, discarded=discarded,
    )

    return sorted(full + partial + substring, key=_sort_key), discarded


def _score_primary_tags(
    rows: list[dict],
    primary_tag_keys: list[str],
    surviving_primary_tag_keys: frozenset[str],
    *,
    full: list[Candidate],
    partial: list[Candidate],
    discarded: list[DiscardedAttribute],
) -> None:
    """Score discovered ``primary_tags.<key>`` columns as PG_TAG candidates.

    Primary tags are matched by the detector on the span at ingest, so an observed
    value is a direct replacement for a deprecated PG tag. Scored like every other
    attribute over the filtered target rows, but emitted as a structured PG_TAG
    condition rather than a string matcher. Keys already surviving on the rule are
    skipped (key-level dedup)."""
    for key in primary_tag_keys:
        if key in surviving_primary_tag_keys:
            continue
        raw_values = [row.get(key) for row in rows]
        if any(isinstance(v, list) for v in raw_values):
            # Array-valued (multi-value) primary tag — not representable by this
            # scalar candidate model, which carries a flat set of string values.
            discarded.append(
                DiscardedAttribute(
                    attribute_type="PG_TAG",
                    grail_key=key,
                    reason="array_valued",
                    distinct_count=0,
                )
            )
            continue
        if any(v is None for v in raw_values):
            discarded.append(
                DiscardedAttribute(
                    attribute_type="PG_TAG",
                    grail_key=key,
                    reason="null_present",
                    distinct_count=len({str(v) for v in raw_values if v is not None}),
                )
            )
            continue
        distinct = sorted({str(v) for v in raw_values})
        if len(distinct) <= _PARTIAL_CAP:
            target = full if len(distinct) == 1 else partial
            target.append(
                Candidate(
                    attribute_type="PG_TAG",
                    grail_key=key,
                    values=distinct,
                    quality="good",
                )
            )
        else:
            # No substring rescue for primary tags: only exact matches are emitted.
            discarded.append(
                DiscardedAttribute(
                    attribute_type="PG_TAG",
                    grail_key=key,
                    reason="too_many_values",
                    distinct_count=len(distinct),
                )
            )
