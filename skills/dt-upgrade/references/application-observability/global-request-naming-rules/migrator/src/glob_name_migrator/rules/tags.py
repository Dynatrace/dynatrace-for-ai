"""Uniform parsing of tag-valued ``comparisonInfo`` payloads.

A ``TAG`` comparison carries its tags in either of two shapes, and both occur in
the wild for the same operator:

- **TagDto** — ``{"context": "CONTEXTLESS", "key": "primary_tags.team",
  "value": "core"}``; the value is optional (key-only condition).
- **bare string** — ``"primary_tags.team:core"``, or ``"primary_tags.team"``
  for a key-only condition.

Both may appear under ``value`` (single) or ``values`` (any-of). Reading only
one shape from only one field silently misclassifies conditions, so every
caller goes through :func:`tag_pairs`.
"""

from __future__ import annotations

from .models import ComparisonInfo, Condition

PRIMARY_TAGS_PREFIX = "primary_tags."


def is_primary_tag_key(key: str) -> bool:
    """True for a tag key that survives Phase 3 (``primary_tags.*``)."""
    return key.startswith(PRIMARY_TAGS_PREFIX)


def _pair(entry: object) -> tuple[str, str | None] | None:
    if isinstance(entry, dict):
        key = entry.get("key")
        if not isinstance(key, str) or not key:
            return None
        value = entry.get("value")
        return (key, value if isinstance(value, str) and value else None)
    if isinstance(entry, str) and entry:
        # Serialised ``key:value`` form; a key-only tag carries no colon.
        key, _, value = entry.partition(":")
        if not key:
            return None
        return (key, value or None)
    return None


def tag_pairs(ci: ComparisonInfo) -> list[tuple[str, str | None]]:
    """Return the ``(tag_key, tag_value | None)`` pairs this comparison carries.

    Reads both the TagDto and bare-string shapes, from both ``value`` and
    ``values``. Entries that carry no usable key are dropped, so an empty
    result means "no tag could be read from this condition".
    """
    entries: list[object] = []
    if ci.value is not None:
        entries.append(ci.value)
    entries.extend(ci.values or [])
    pairs: list[tuple[str, str | None]] = []
    for entry in entries:
        pair = _pair(entry)
        if pair is not None:
            pairs.append(pair)
    return pairs


def is_primary_tag_condition(cond: Condition) -> bool:
    """True for a ``PROCESS_GROUP_TAG`` condition carrying a ``primary_tags.*`` tag.

    These are the only PG tag conditions Phase 3 still evaluates, and it does so
    against the entry-point span's resource attributes rather than the process
    group entity — which makes them span-side despite sharing a mapping row with
    ordinary PG tags.
    """
    if cond.attribute != "PROCESS_GROUP_TAG":
        return False
    return any(is_primary_tag_key(key) for key, _ in tag_pairs(cond.comparisonInfo))


__all__ = [
    "PRIMARY_TAGS_PREFIX",
    "is_primary_tag_condition",
    "is_primary_tag_key",
    "tag_pairs",
]
