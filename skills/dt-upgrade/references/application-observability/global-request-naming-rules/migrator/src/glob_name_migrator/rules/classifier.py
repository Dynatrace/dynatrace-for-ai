"""Classify a request naming rule into Case A / C and split its
conditions into (entity vs span) × (surviving vs deprecated) buckets.

Case dispatch is by where the rule's conditions live:

- **Case A** — entity-level conditions only (including a non-empty
  ``managementZones``).
- **Case C** — both sides populated.

Deprecation is determined per condition:

- ``managementZones`` field — entire field is deprecated.
- ``SERVICE_TAG`` — always deprecated.
- ``PROCESS_GROUP_TAG`` — surviving when *every* one of its tag keys starts with
  ``primary_tags.``, deprecated otherwise. A condition mixing a primary and an
  ordinary tag is deprecated because it is not a valid rule at all — request
  naming cannot evaluate it correctly and validators block it, so its presence is
  a product bug. Marking it deprecated keeps the rule visible; the translator
  then makes the whole rule unmigratable.
- Everything else — surviving.

Surviving primary tags are **span**-side: Phase 3 evaluates them against the
entry-point span's resource attributes, not the process group entity. Because
``PROCESS_GROUP_TAG`` is a single mapping row serving both primary and ordinary
tags, the side cannot be derived from the attribute alone — :func:`condition_side`
is the single source of truth, shared with cache-key computation.

A rule whose only non-``managementZones`` condition is a primary tag therefore
classifies as Case C rather than A: it cannot be verified without a span query.
Case C tolerates a rule with surviving-but-no-deprecated span conditions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .mapping import load_mapping
from .models import Condition, Rule
from .tags import is_primary_tag_condition, is_primary_tag_key, tag_pairs

Case = Literal["A", "C"]


@dataclass(frozen=True)
class Classification:
    """Classification result for a single rule."""

    case: Case
    has_deprecated_management_zones: bool
    surviving_entity: tuple[Condition, ...] = field(default_factory=tuple)
    surviving_span: tuple[Condition, ...] = field(default_factory=tuple)
    deprecated_entity: tuple[Condition, ...] = field(default_factory=tuple)
    deprecated_span: tuple[Condition, ...] = field(default_factory=tuple)

    @property
    def is_deprecated(self) -> bool:
        """True when the rule contains at least one deprecated condition."""
        return bool(
            self.has_deprecated_management_zones
            or self.deprecated_entity
            or self.deprecated_span
        )

    @property
    def entity_conditions(self) -> tuple[Condition, ...]:
        """All entity conditions (surviving + deprecated)."""
        return self.surviving_entity + self.deprecated_entity

    @property
    def span_conditions(self) -> tuple[Condition, ...]:
        """All span conditions (surviving + deprecated)."""
        return self.surviving_span + self.deprecated_span


def _condition_deprecated(cond: Condition) -> bool:
    attr = cond.attribute
    if attr == "SERVICE_TAG":
        return True
    if attr == "PROCESS_GROUP_TAG":
        pairs = tag_pairs(cond.comparisonInfo)
        if not pairs:
            # No readable tag — treat as deprecated so the rule stays visible
            # to downstream stages rather than silently passing through.
            return True
        primary = [k for k, _ in pairs if is_primary_tag_key(k)]
        # A condition carrying *only* primary tags survives Phase 3 untouched.
        # A mixed condition is not a valid rule at all — request naming cannot
        # evaluate it and validators block it, so it should never exist. Marking
        # it deprecated keeps the rule visible so the translator can report it
        # unmigratable; treating it as surviving made it disappear from the
        # report entirely.
        return not primary or len(primary) != len(pairs)
    return False


def condition_side(cond: Condition) -> Literal["entity", "span", "unknown"]:
    """Return the evaluation side of a single condition.

    The single source of truth for entity-vs-span. ``PROCESS_GROUP_TAG`` is one
    mapping row serving both primary and ordinary tags, so the side cannot be
    derived from the attribute alone: classification and cache-key computation
    must both come through here or they will disagree, silently sharing cache
    entries between rules that are not equivalent.
    """
    if is_primary_tag_condition(cond):
        return "span"
    mapping = load_mapping()
    if mapping.is_entity(cond.attribute):
        return "entity"
    if mapping.is_span(cond.attribute):
        return "span"
    return "unknown"


def classify(rule: Rule) -> Classification:
    """Inspect a rule and return its (case, split) classification."""
    surviving_entity: list[Condition] = []
    surviving_span: list[Condition] = []
    deprecated_entity: list[Condition] = []
    deprecated_span: list[Condition] = []

    for cond in rule.conditions:
        side = condition_side(cond)
        # Unknown attributes fall back to entity-side to keep the rule visible
        # to downstream stages, which can flag them as unmigratable.
        is_entity = side != "span"
        bucket = (
            (deprecated_entity if is_entity else deprecated_span)
            if _condition_deprecated(cond)
            else (surviving_entity if is_entity else surviving_span)
        )
        bucket.append(cond)

    has_mz = bool(rule.managementZones)
    has_span = bool(surviving_span or deprecated_span)

    # Deprecated rules have entity-side content, so span-only rules are
    # non-deprecated and skipped before case is consumed. The one exception is a
    # mixed primary/ordinary PG tag: deprecated *and* span-side. Such a rule is
    # unmigratable and stops at the sidecar, so its case is never consumed.
    case: Case = "C" if has_span else "A"

    return Classification(
        case=case,
        has_deprecated_management_zones=has_mz,
        surviving_entity=tuple(surviving_entity),
        surviving_span=tuple(surviving_span),
        deprecated_entity=tuple(deprecated_entity),
        deprecated_span=tuple(deprecated_span),
    )


__all__ = [
    "Case",
    "Classification",
    "classify",
    "condition_side",
]
