"""Turning one classified condition into the DQL that selects what it selects."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from ..rules.classification import (
    ClassifiedCondition,
    ConditionStanding,
    FilteredEntity,
    PredicateType,
    Side,
)
from ..rules.tags import ParsedTag


class Dataset(StrEnum):
    """The data a filter runs over, spelled as the `fetch` target that reads it."""

    SERVICES = "dt.entity.service"
    PROCESS_GROUPS = "dt.entity.process_group"
    ENTRY_SPANS = "spans"


class Untranslatable(Exception):
    """The tool has no way to express this condition, and says so rather than leaving it out.

    A query missing one of a rule's conditions selects wider than the rule, and a replacement
    built from that set would then be "verified" against it.
    """


class MatchesNothing(Exception):
    """The condition selects nothing without a query being issued.

    Not an error and not a query returning no rows: the shape itself cannot select anything, so
    there is nothing to ask the tenant.
    """


@dataclass(frozen=True)
class Fragment:
    """One condition as a DQL boolean expression over one dataset.

    An empty expression is a condition that constrains nothing, still bounded by dataset and
    window - not an omission.
    """

    dataset: Dataset
    text: str = ""


# How each string predicate compares, keyed by the predicate type itself so that a mistyped
# spelling cannot slip past as a silently different comparison.
_STRING_COMPARISONS = {
    PredicateType.STRING_EQUALS: "{attribute} == {value}",
    PredicateType.STARTS_WITH: "startsWith({attribute}, {value})",
    PredicateType.ENDS_WITH: "endsWith({attribute}, {value})",
    PredicateType.CONTAINS: "contains({attribute}, {value})",
}


# A condition filters what its side and entity name say and nothing else: the two process-group
# attributes select process groups, and a service only because the process group hosting it matched.
_DATASETS: dict[tuple[Side | None, FilteredEntity | None], Dataset] = {
    (Side.ENTITY, FilteredEntity.SERVICE): Dataset.SERVICES,
    (Side.ENTITY, FilteredEntity.PROCESS_GROUP): Dataset.PROCESS_GROUPS,
    (Side.SPAN, FilteredEntity.SERVICE): Dataset.ENTRY_SPANS,
}


def dataset_of(condition: ClassifiedCondition) -> Dataset:
    dataset = _DATASETS.get((condition.side, condition.entity))
    if dataset is None:
        raise Untranslatable(
            condition.diagnostic or "the condition names no data the filter could run over"
        )
    return dataset


def translate_condition(
    condition: ClassifiedCondition, *, zone_names: Mapping[str, str] | None = None
) -> Fragment:
    if condition.standing is ConditionStanding.UNCLASSIFIABLE or condition.predicate_type is None:
        # Only a shape the read pass could not make sense of. Everything the API can store has a
        # translation, and declaring some shapes "hard" here would short-circuit rules the normal
        # path handles - under-migration that looks like a clean run.
        raise Untranslatable(condition.diagnostic)
    if condition.predicate_type is PredicateType.SERVICE_TYPE_EQUALS:
        return Fragment(dataset_of(condition), _service_type_filter(condition.values))
    if condition.predicate_type is PredicateType.MANAGEMENT_ZONES_CONTAINS_ALL:
        return Fragment(dataset_of(condition), _zone_filter(condition, zone_names or {}))
    if condition.side is Side.SPAN:
        return Fragment(
            Dataset.ENTRY_SPANS, _any_of(_primary_tag_match(tag) for tag in condition.tags)
        )
    if condition.tags:
        key_only = condition.predicate_type is PredicateType.TAG_KEY_EQUALS
        matches = _any_of(_tag_match(tag, key_only=key_only) for tag in condition.tags)
        # One `iAny` around the whole disjunction, because the condition asks whether the entity
        # carries *some* tag matching *some* entry - not whether one entry matches every tag.
        return Fragment(dataset_of(condition), f"iAny({matches})")
    if condition.predicate_type not in _STRING_COMPARISONS:
        return Fragment(dataset_of(condition))
    attribute = "entity.name" if condition.case_sensitive else "lower(entity.name)"
    comparison = _STRING_COMPARISONS[condition.predicate_type]
    return Fragment(dataset_of(condition), _any_of(
        comparison.format(
            attribute=attribute,
            value=literal(value if condition.case_sensitive else value.lower()),
        )
        for value in condition.values
    ))


# An entity carries its tags as the same serialised strings a rule stores - `key`, `key:value`,
# either behind an optional `[Context]` prefix. The backend compares the parsed key and ignores the
# context, and anchoring both ends is what keeps `team` from matching `my-team` or `team-payments`.
_CONTEXT_PREFIX = r"^(\[[^\]]*\])?"


# A rule stores a service type under one spelling and the entity data carries another, and the
# two are not a case transformation of each other: what a rule calls `Method` is stored as
# `CUSTOM_SERVICE`, and one stored type answers to two entity spellings. A type absent from this
# table has no entity spelling at all - several of them are not services in the first place - so
# it is kept as written: nothing carries it, which is exactly what such a condition selects.
_ENTITY_SERVICE_TYPES = {
    "WebRequest": ("WEB_REQUEST_SERVICE",),
    "WebService": ("WEB_SERVICE",),
    "Database": ("DATABASE_SERVICE",),
    "Method": ("CUSTOM_SERVICE",),
    "Messaging": ("MESSAGING_SERVICE",),
    "Process": ("BACKGROUND_ACTIVITY",),
    "RMI": ("RMI_SERVICE",),
    "External": ("EXTERNAL",),
    "QueueListener": ("QUEUE_LISTENER_SERVICE",),
    "RemoteCall": ("RPC_SERVICE",),
    "CICS": ("CICS_SERVICE",),
    "IMS": ("IMS_SERVICE",),
    "EnterpriseServiceBus": ("ENTERPRISE_SERVICE_BUS_SERVICE", "IBM_INTEGRATION_BUS_SERVICE"),
    "zOSConnect": ("ZOS_CONNECT",),
}


def stored_service_types(entity_spelling: str) -> tuple[str, ...]:
    """The stored spellings a service type observed in the entity data can be written back as.

    Derived from the forward table so the two cannot drift, and many-to-one because that table is
    not injective: a stored value reached from one entity spelling can also select another. The
    condition therefore selects a little more than was harvested - ordinary over-selection for a
    verification query to catch. An entity spelling with no stored value cannot be expressed at
    all, and the empty answer says so rather than guessing.
    """
    return _STORED_SERVICE_TYPES.get(entity_spelling, ())


_STORED_SERVICE_TYPES: dict[str, tuple[str, ...]] = {}
for _stored, _spellings in _ENTITY_SERVICE_TYPES.items():
    for _spelling in _spellings:
        _STORED_SERVICE_TYPES[_spelling] = _STORED_SERVICE_TYPES.get(_spelling, ()) + (_stored,)


def _service_type_filter(values: tuple[str, ...]) -> str:
    if not values:
        raise MatchesNothing(
            "the condition lists no service type, so no service can satisfy it"
        )
    spellings = sorted(
        {
            spelling
            for value in values
            for spelling in _ENTITY_SERVICE_TYPES.get(value, (value,))
        }
    )
    listed = ", ".join(literal(spelling) for spelling in spellings)
    return f"in(serviceType, array({listed}))"


def _primary_tag_match(tag: ParsedTag) -> str:
    """Match one primary tag on the span the backend evaluates the rule on.

    The tag key *is* the resource attribute name, prefix included, so nothing about it is
    stripped. The comparison is exact and case-sensitive, unlike the entity-side name
    predicates, and an entry carrying no value asks only whether the attribute is present.
    """
    attribute = attribute_name(tag.key)
    if tag.value is None:
        return f"isNotNull({attribute})"
    return f"{attribute} == {literal(tag.value)}"


def attribute_name(key: str) -> str:
    """Compose a tag key into the query as the attribute name it is.

    A dotted name has to be quoted, which is only safe if the quote character cannot appear
    unescaped inside it.
    """
    escaped = key.replace("\\", "\\\\").replace("`", "\\`")
    return "`" + escaped + "`"


def _zone_filter(condition: ClassifiedCondition, zone_names: Mapping[str, str]) -> str:
    """Require every zone the condition lists, on its own code path.

    Management zones are the one all-of predicate in this API and must never share the any-of
    joining the tag predicates use, which would turn "in all three zones" into "in any of them".

    A zone is stored as its settings object id while the entity data carries *names*, so each is
    resolved through the index the run read once. A zone yielding no name is as unresolved as one
    that is gone - comparing against the empty name selects nothing while looking like a filter
    that worked.
    """
    names = [zone_names[zone] for zone in condition.values if zone_names.get(zone)]
    if not names:
        # The backend drops references it cannot resolve, so a condition where none of them
        # resolve is left requiring membership of no zone at all - which nothing satisfies.
        raise MatchesNothing(
            "every management zone the condition names has been deleted, so the rule already "
            "selects no service today"
        )
    return _all_of(f"iAny(managementZones[] == {literal(name)})" for name in names)


def _all_of(comparisons: Iterable[str]) -> str:
    return " and ".join(sorted(comparisons))


def _tag_match(tag: ParsedTag, *, key_only: bool) -> str:
    """Match one tag entry: its key, and - unless the key is all that is compared - its value.

    A key-only entry matches a tag whatever value it carries, while an exact entry that parsed to
    a *null* value matches only tags carrying no value - strictly narrower, so the two patterns
    must not collapse.
    """
    if key_only:
        value_part = "(:.*)?$"
    elif tag.value is None:
        value_part = "$"
    else:
        value_part = ":" + _regexliteral(tag.value) + "$"
    # A colon inside a key is stored escaped, since an unescaped one is what separates key from
    # value; matching the parsed key verbatim would find the wrong split of the wrong tag.
    pattern = _CONTEXT_PREFIX + _regexliteral(tag.key.replace(":", "\\:")) + value_part
    return f"matchesRegex(tags[], {literal(pattern)})"


# Escaped by hand rather than with `re.escape`, which also backslashes characters that several
# regex dialects reject as unknown escapes.
_REGEX_METACHARACTERS = set(r"\.^$*+?()[]{}|/")


def _regexliteral(value: str) -> str:
    return "".join("\\" + c if c in _REGEX_METACHARACTERS else c for c in value)


def _any_of(comparisons: Iterable[str]) -> str:
    """Join comparisons the way a condition matches: any one of them is enough.

    Sorted, because the same filter is assembled repeatedly from parts in whatever order the call
    site held them, and two spellings of one question are two queries and two bills.
    """
    return " or ".join(sorted(comparisons))


def literal(value: str) -> str:
    """Compose a value into the query text so that nothing in it can be read as syntax.

    The one place the rule lives: a second copy is a second thing to correct when the parser turns
    out to want an escape spelled differently, and the missed copy composes a value in as syntax.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + escaped + '"'
