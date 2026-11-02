"""Writing one reviewable file per covered rule: the reasoning and the deployable body together.

The body is a *create payload*, not the original rule with the deprecated scope subtracted. What
someone does with the file is POST what is under its body key, so that is the contract it is built
to: only the members a create accepts, every server-assigned field gone, and the safety-relevant
flag chosen here rather than inherited.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..clients.settings import RULES_SCHEMA_ID
from ..reconstruction.replacement import MAX_CONDITIONS, Coverage, Replacement
from ..rules.classification import (
    STRING_PREDICATES,
    TAG_FIELDS,
    VALUE_FIELDS,
    ClassifiedCondition,
    ClassifiedRule,
    ConditionStanding,
)
from ..rules.tags import serialise_universal_tag


class EmissionError(RuntimeError):
    """A body that must not be written, caught before anything can deploy it."""


@dataclass(frozen=True)
class EmittedArtifact:
    """One written file, named so a reader can be pointed at it without opening it."""

    rule_id: str
    path: Path
    # What was written, carried alongside the path so that showing the body and its insert
    # position needs no second read of the file this same process just wrote. Out of the
    # comparison so that this stays a hashable value type.
    content: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


# The only scope this schema allows. Written as the constant it is: the read that lists the rules
# asks for `objectId,value`, which does not carry `scope`, and a create is rejected without one.
SCOPE = "environment"


def emit_artifacts(
    corpus: Sequence[ClassifiedRule], replacements: Sequence[Replacement], workdir: Path
) -> tuple[EmittedArtifact, ...]:
    """Write the artifact of every covered rule into the run's own directory.

    Takes every rule that was read, not the ones a run was asked to rework: an insert position is
    only a position within the whole ruleset, and a subset cannot say where in it a rule sits.
    """
    directory = workdir / "artifacts"
    directory.mkdir(parents=True, exist_ok=True)
    by_id = {rule.object_id: rule for rule in corpus}
    predecessors = _predecessors(corpus)
    written: list[EmittedArtifact] = []
    for replacement in replacements:
        if replacement.coverage is not Coverage.EXACT:
            continue
        rule = by_id[replacement.object_id]
        artifact = _artifact(rule, replacement, predecessors[rule.object_id])
        path = directory / f"{replacement.object_id}.json"
        path.write_text(json.dumps(artifact, indent=2) + "\n")
        written.append(EmittedArtifact(replacement.object_id, path, artifact))
    return tuple(written)


def _predecessors(corpus: Sequence[ClassifiedRule]) -> dict[str, str]:
    """The rule each one sits behind, by objectId, and `""` for the one that is first.

    The order rules are read in *is* the order they are evaluated in, so a position is a fact
    about the list and needs no second read to establish. It is a fact about the *whole* list,
    though: hand this a subset and every position in it is wrong but the last.
    """
    return {
        rule.object_id: corpus[position - 1].object_id if position else ""
        for position, rule in enumerate(corpus)
    }


def _artifact(
    rule: ClassifiedRule, replacement: Replacement, insert_after: str
) -> dict[str, Any]:
    kept, dropped = _emitted_conditions(rule, replacement)
    return {
        "rule_id": rule.object_id,
        # The rule name lives inside because the file name cannot hold it: an object id is
        # filename-safe and a name someone typed is not.
        "name": rule.name,
        "outcome": replacement.coverage.value,
        "insert_after": insert_after,
        "deprecated_conditions": [
            {"reason": _member(c.reason), "condition": _condition(rule, c)}
            for c in rule.conditions
            if c.standing is ConditionStanding.DEPRECATED
        ],
        "surviving_conditions": [
            _condition(rule, c)
            for c in rule.conditions
            if c.standing is ConditionStanding.SURVIVING
        ],
        "dropped_duplicates": dropped,
        "replacement_rule_body": _body(rule, kept),
    }


def _emitted_conditions(
    rule: ClassifiedRule, replacement: Replacement
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The body's conditions, and the ones left out for saying what another already says.

    Compared as they are written rather than as they were assembled: a Surviving Condition is
    copied and a candidate is synthesised, so two that arrive from different directions are only
    duplicates if the stored form they end up in is the same one. `superseded` survivors are
    untouched - same attribute is not the same condition, and they are a minimal diff of the
    customer's own rule.
    """
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for condition in replacement.conditions:
        written = _condition(rule, condition)
        identity = json.dumps(written, sort_keys=True)
        if identity in seen:
            dropped.append(written)
            continue
        seen.add(identity)
        kept.append(written)
    return kept, dropped


def _body(rule: ClassifiedRule, conditions: list[dict[str, Any]]) -> dict[str, Any]:
    """The rule as a create payload: `schemaId`, `scope` and `value`, and nothing else.

    The envelope fields are carried over rather than re-derived. `parameterId` in particular is
    the objectId of a parameter set, and a rule pointing at one that does not exist is skipped
    whole - so it is copied exactly as the customer stored it.
    """
    if not conditions:
        raise EmissionError(
            f"rule {rule.object_id} was covered by a condition set that would be stored empty"
        )
    if len(conditions) > MAX_CONDITIONS:
        # The verdict refuses such a set before it can be covered, so reaching here means
        # something upstream assembled one anyway. Refused rather than written out short.
        raise EmissionError(
            f"rule {rule.object_id} was covered by {len(conditions)} conditions, "
            f"where a rule carries at most {MAX_CONDITIONS}"
        )
    stored = rule.value
    value: dict[str, Any] = {
        key: stored[key] for key in ("name", "description", "parameterId") if key in stored
    }
    # Never inherited: an artifact that arrives enabled changes behaviour the moment it lands.
    value["enabled"] = False
    value["conditions"] = conditions
    return {"schemaId": RULES_SCHEMA_ID, "scope": SCOPE, "value": value}


def _condition(rule: ClassifiedRule, condition: ClassifiedCondition) -> dict[str, Any]:
    """One condition of the replacement, in the form a rule stores it in.

    A condition the customer wrote is copied from where they wrote it. Nothing in the tree
    re-serialises the typed vocabulary losslessly - a recognised context prefix is folded away by
    the parse, and one predicate carries no value field at all - so copying is both cheaper and
    the only way the surviving half of a rule stays byte-identical.
    """
    if condition.index is not None:
        # Copied, so nothing written can reach back into what was read.
        return deepcopy(rule.value["conditions"][condition.index])
    return {
        "attribute": _member(condition.attribute),
        "predicate": _predicate(condition),
    }


def _predicate(condition: ClassifiedCondition) -> dict[str, Any]:
    """A harvested condition's predicate, written from the vocabulary that already spells it.

    `Attribute` and `PredicateType` hold the exact API strings, so the member value goes out
    verbatim and nothing here re-spells an attribute or a predicate name.
    """
    predicate_type = condition.predicate_type
    if predicate_type is None:
        raise EmissionError("a condition with no readable predicate reached emission")
    field_name = VALUE_FIELDS.get(predicate_type) or TAG_FIELDS.get(predicate_type)
    if field_name is None:
        raise EmissionError(
            f"no stored field for a synthesised {predicate_type.value} predicate"
        )
    entries = (
        [serialise_universal_tag(tag) for tag in condition.tags]
        if predicate_type in TAG_FIELDS
        else list(condition.values)
    )
    predicate: dict[str, Any] = {
        "predicateType": predicate_type.value,
        field_name: entries,
    }
    if predicate_type in STRING_PREDICATES:
        # Only the four string predicates are configurable. A tag predicate carries no case flag
        # at all - the compiled predicate compares tags exactly whatever one would say.
        predicate["caseSensitive"] = condition.case_sensitive
    return predicate


def _member(vocabulary: StrEnum | None) -> str:
    if vocabulary is None:
        raise EmissionError("a condition with no readable attribute or predicate reached emission")
    return vocabulary.value
