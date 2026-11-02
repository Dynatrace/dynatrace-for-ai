"""Stable cache keys for entity- and span-side query results.

Two keys per rule:

- ``entity_key`` — over ``managementZones`` + entity-level conditions. Two
  rules with the same entity-side shape share cached entity-query rows.
- ``span_key`` — over ``entity_key`` + span-level conditions. Two rules with
  the same entity shape AND the same span-side filters share cached span rows.

Keys are SHA-256[:12] of canonical JSON (dict keys sorted recursively, list
elements sorted by canonical JSON of each element). Conditions are stored in
their raw dict form so equivalent payloads with reordered keys collide.

``entity_key`` is always derived from the entity-side input; there is no
special collapse because all migratable rules have entity-side content.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .rules.classifier import condition_side
from .rules.models import Condition, Rule


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _canonical(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return sorted(
            (_canonical(v) for v in value),
            key=lambda v: json.dumps(v, sort_keys=True),
        )
    return value


def _hash12(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _cond_to_dict(cond: Condition) -> dict[str, Any]:
    """Round-trip via JSON so ``extra="allow"`` fields are preserved verbatim."""
    return json.loads(cond.model_dump_json(by_alias=True, exclude_none=True))


def split_conditions(
    conditions: list[Condition],
) -> tuple[list[Condition], list[Condition]]:
    """Split into (entity-level, span-level) using the condition mapping.

    Conditions whose ``attribute`` is unknown to the mapping default to
    entity-level — same conservative fallback used by the algorithm spec so
    cache keys remain deterministic in the face of new attributes.

    Uses the same per-condition side helper as the classifier: the two must never
    disagree (see :func:`~glob_name_migrator.rules.classifier.condition_side`).
    """
    entity: list[Condition] = []
    span: list[Condition] = []
    for cond in conditions:
        (span if condition_side(cond) == "span" else entity).append(cond)
    return entity, span


def compute_keys(rule: Rule) -> tuple[str, str]:
    """Return ``(entity_key, span_key)`` for the given rule."""
    entity_conds, span_conds = split_conditions(rule.conditions)

    entity_input = {
        "managementZones": _canonical(list(rule.managementZones)),
        "conditions": _canonical([_cond_to_dict(c) for c in entity_conds]),
    }
    entity_key = _hash12(entity_input)

    span_input = {
        "entity_key": entity_key,
        "conditions": _canonical([_cond_to_dict(c) for c in span_conds]),
    }
    span_key = _hash12(span_input)

    return entity_key, span_key


__all__ = ["compute_keys", "split_conditions"]
