from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from ..clients.settings import RuleObject
from .tags import ParsedTag, is_primary_tag_key, parse_universal_tag


class Attribute(StrEnum):
    """The six condition attributes a rule can be built from, and no others.

    The values are the exact API strings: they are read from a stored rule and written back into
    an emitted one, so nothing may normalise or prettify them.
    """

    SERVICE_NAME = "SERVICE_NAME"
    SERVICE_TYPE = "SERVICE_TYPE"
    SERVICE_TAG = "SERVICE_TAG"
    SERVICE_MANAGEMENT_ZONE = "SERVICE_MANAGEMENT_ZONE"
    PG_NAME = "PG_NAME"
    PG_TAG = "PG_TAG"


class PredicateType(StrEnum):
    """The nine ways a condition can compare, and no others. Values are the exact API strings."""

    STRING_EQUALS = "STRING_EQUALS"
    STARTS_WITH = "STARTS_WITH"
    ENDS_WITH = "ENDS_WITH"
    CONTAINS = "CONTAINS"
    STRING_EXISTS = "STRING_EXISTS"
    SERVICE_TYPE_EQUALS = "SERVICE_TYPE_EQUALS"
    MANAGEMENT_ZONES_CONTAINS_ALL = "MANAGEMENT_ZONES_CONTAINS_ALL"
    TAG_EQUALS = "TAG_EQUALS"
    TAG_KEY_EQUALS = "TAG_KEY_EQUALS"


class Side(StrEnum):
    """Which data a condition is evaluated against."""

    ENTITY = "entity-side"
    SPAN = "span-side"


class FilteredEntity(StrEnum):
    SERVICE = "SERVICE"
    PROCESS_GROUP = "PROCESS_GROUP"


class ConditionStanding(StrEnum):
    DEPRECATED = "deprecated"
    SURVIVING = "surviving"
    UNCLASSIFIABLE = "unclassifiable"


class RuleStanding(StrEnum):
    """What the tool does with a rule after the one classification pass.

    Only :attr:`AFFECTED` rules go on to have their Target Set resolved. The rest are reported
    and left alone - a disabled rule assigns nothing today, so Phase 3 changes nothing about it,
    and the two remaining standings need a human rather than a replacement.
    """

    AFFECTED = "affected"
    COMPLIANT = "compliant"
    DISABLED = "disabled"
    DEAD_TODAY = "dead-today"
    UNCLASSIFIABLE = "unclassifiable"


class DeprecationReason(StrEnum):
    """Why Phase 3 stops evaluating a condition, one code per cause.

    A tag problem has to be tellable from a zone problem without reading the condition back, so
    these are the reasons carried up to the rule and counted in the scan coverage breakdown.
    """

    SERVICE_TAG = "service-tag"
    MANAGEMENT_ZONE = "management-zone"
    NON_PRIMARY_PG_TAG = "non-primary-pg-tag"
    MIXED_PG_TAG = "mixed-pg-tag"


@dataclass(frozen=True)
class ClassifiedCondition:
    # pylint: disable=too-many-instance-attributes
    # `None` on either vocabulary field means the stored value is outside the known input space;
    # the raw value is then named in `diagnostic`.
    attribute: Attribute | None
    predicate_type: PredicateType | None
    standing: ConditionStanding
    # Both are unknown for an unclassifiable condition, and saying so beats guessing a side.
    side: Side | None
    entity: FilteredEntity | None
    case_sensitive: bool
    values: tuple[str, ...] = ()
    tags: tuple[ParsedTag, ...] = ()
    reason: DeprecationReason | None = None
    # Free text for a human, set only on an unclassifiable one. Never matched on.
    diagnostic: str = ""
    # Where this sits in the rule's stored `conditions` array, and `None` for one synthesised
    # from the vocabulary above. An index rather than the raw mapping, so this stays hashable.
    index: int | None = None


@dataclass(frozen=True)
class ClassifiedRule:
    # pylint: disable=too-many-instance-attributes
    """One rule's outcome: the codes a caller counts, and the free text a human reads.

    The two are kept apart on purpose - a diagnostic says the tool could not read something,
    which is not a statement about Phase 3 and must never be counted as one.
    """

    object_id: str
    name: str
    enabled: bool
    standing: RuleStanding
    reasons: tuple[DeprecationReason, ...]
    diagnostics: tuple[str, ...]
    conditions: tuple[ClassifiedCondition, ...]
    # The object as it is stored. A condition that survives is written back from here rather than
    # re-serialised from the vocabulary above, and the rule's own envelope fields are only
    # reachable here. Out of the comparison so that this stays a hashable value type.
    value: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


def classify_rules(objects: Iterable[RuleObject]) -> list[ClassifiedRule]:
    """Label every rule in the ruleset once, and every condition of every rule.

    This is the only pass over the whole ruleset: from here on a rule that is not affected does
    not exist for the tool, so nothing else resolves, queries or analyses it.
    """
    return [_classified_or_unclassifiable(obj) for obj in objects]


def _classified_or_unclassifiable(obj: RuleObject) -> ClassifiedRule:
    try:
        return _classify_rule(obj)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # One unreadable rule must not cost the classification of the rest. A rule that is
        # switched off is recorded as switched off whatever the tool could make of it, the same
        # way a readable one is: Phase 3 evaluates nothing here, so there is no rework to hand
        # anyone. The diagnostic is kept either way, because failing to read a rule is this
        # tool's own defect and stays worth reporting.
        return ClassifiedRule(
            object_id=obj.object_id,
            name=obj.name,
            enabled=obj.enabled,
            standing=RuleStanding.UNCLASSIFIABLE if obj.enabled else RuleStanding.DISABLED,
            reasons=(),
            diagnostics=(f"could not be read: {type(exc).__name__}: {exc}",),
            conditions=(),
            value=obj.value,
        )


def _classify_rule(obj: RuleObject) -> ClassifiedRule:
    conditions = tuple(
        replace(_classify_condition(raw), index=index)
        for index, raw in enumerate(obj.value.get("conditions") or [])
    )
    deprecated = tuple(dict.fromkeys(_deprecation_reasons(conditions)))
    unreadable = tuple(
        dict.fromkeys(
            c.diagnostic for c in conditions if c.standing is ConditionStanding.UNCLASSIFIABLE
        )
    )
    if not obj.enabled:
        # A disabled rule needs no reason: being disabled is the whole of its Phase 3 standing.
        # A diagnostic is not a statement about Phase 3, though - it says the tool could not read
        # something - so it is kept, because failing to read a stored rule is this tool's own
        # defect whether or not the rule is switched off.
        standing, reasons, diagnostics = RuleStanding.DISABLED, (), unreadable
    elif not conditions:
        standing, reasons, diagnostics = RuleStanding.UNCLASSIFIABLE, (), (_NO_CONDITIONS,)
    elif unreadable:
        # Reported with whatever else was found: a rule the tool did not fully understand cannot
        # have its Target Set reproduced, whether or not it also carries a deprecated condition.
        standing, reasons, diagnostics = RuleStanding.UNCLASSIFIABLE, deprecated, unreadable
    elif DeprecationReason.MIXED_PG_TAG in deprecated:
        standing, reasons, diagnostics = RuleStanding.DEAD_TODAY, deprecated, ()
    elif deprecated:
        standing, reasons, diagnostics = RuleStanding.AFFECTED, deprecated, ()
    else:
        standing, reasons, diagnostics = RuleStanding.COMPLIANT, (), ()
    return ClassifiedRule(
        object_id=obj.object_id,
        name=obj.name,
        enabled=obj.enabled,
        standing=standing,
        reasons=reasons,
        diagnostics=diagnostics,
        conditions=conditions,
        value=obj.value,
    )


def _deprecation_reasons(conditions: Iterable[ClassifiedCondition]) -> Iterator[DeprecationReason]:
    for condition in conditions:
        if condition.standing is ConditionStanding.DEPRECATED and condition.reason is not None:
            yield condition.reason


_NO_CONDITIONS = "carries no condition, which no rule can - the tool has no reading for it"


def _classify_condition(raw: dict[str, Any]) -> ClassifiedCondition:
    predicate = raw.get("predicate") or {}
    raw_attribute = str(raw.get("attribute") or "")
    raw_predicate_type = str(predicate.get("predicateType") or "")
    # Never raises: a value outside the known input space becomes `None` and is reported, because
    # refusing to read the rule would hide it from the customer.
    attribute = _known(Attribute, raw_attribute)
    predicate_type = _known(PredicateType, raw_predicate_type)
    tags = _parsed_tags(predicate_type, predicate)
    values = _matched_values(predicate_type, predicate)

    if attribute is None or predicate_type is None:
        unknown = (
            f"unknown condition attribute {raw_attribute!r}"
            if attribute is None
            else f"unknown predicate type {raw_predicate_type!r}"
        )
        return _unreadable(attribute, predicate_type, values, tags, unknown)
    unsupported = _unsupported_shape(attribute, predicate_type, predicate, tags, values)
    if unsupported:
        return _unreadable(attribute, predicate_type, values, tags, unsupported)
    if attribute is Attribute.PG_TAG:
        return _classify_pg_tag(attribute, predicate_type, tags)
    deprecation = _DEPRECATED_ATTRIBUTES.get(attribute)
    return ClassifiedCondition(
        attribute=attribute,
        predicate_type=predicate_type,
        standing=ConditionStanding.DEPRECATED if deprecation else ConditionStanding.SURVIVING,
        side=Side.ENTITY,
        entity=_ATTRIBUTE_ENTITIES[attribute],
        case_sensitive=_compares_case_sensitively(predicate_type, predicate),
        values=values,
        tags=tags,
        reason=deprecation,
    )


def _unreadable(
    attribute: Attribute | None,
    predicate_type: PredicateType | None,
    values: tuple[str, ...],
    tags: tuple[ParsedTag, ...],
    diagnostic: str,
) -> ClassifiedCondition:
    """A condition the tool has no reading for, carrying the free text that says why."""
    return ClassifiedCondition(
        attribute=attribute,
        predicate_type=predicate_type,
        standing=ConditionStanding.UNCLASSIFIABLE,
        side=None,
        entity=None,
        case_sensitive=False,
        values=values,
        tags=tags,
        diagnostic=diagnostic,
    )


def _known[T: StrEnum](vocabulary: type[T], raw: str) -> T | None:
    """Read a stored string as its enum member, or `None` when it is not one of them."""
    try:
        return vocabulary(raw)
    except ValueError:
        return None


def _unsupported_shape(
    attribute: Attribute,
    predicate_type: PredicateType,
    predicate: dict[str, Any],
    tags: tuple[ParsedTag, ...],
    values: tuple[str, ...],
) -> str:
    """Name what is wrong with a condition, or return "" when it is one of the known shapes.

    An unknown shape is recorded with its diagnostic rather than defaulted to surviving, which
    would drop the rule out of the affected subset and hide it from the customer entirely.
    """
    if predicate_type not in _ATTRIBUTE_PREDICATES[attribute]:
        return (
            f"predicate type {predicate_type.value!r} is not offered "
            f"for attribute {attribute.value!r}"
        )
    return _value_shape_problem(predicate_type, predicate, tags, values)


def _value_shape_problem(  # pylint: disable=too-many-return-statements
    # Each return is a differently-worded problem; collapsing them costs the diagnostic its point.
    predicate_type: PredicateType,
    predicate: dict[str, Any],
    tags: tuple[ParsedTag, ...],
    values: tuple[str, ...],
) -> str:
    if predicate_type is PredicateType.STRING_EXISTS:
        # The one predicate with no value field: it matches every entity of its type, so "no
        # values present" is its legal shape and must not fall through as an unknown one.
        return ""
    field_name = VALUE_FIELDS.get(predicate_type) or TAG_FIELDS[predicate_type]
    entries = predicate.get(field_name)
    if not isinstance(entries, list):
        return f"{predicate_type} carries no {field_name}"
    if predicate_type in TAG_FIELDS:
        if not entries:
            return f"{predicate_type} carries an empty {field_name}"
        if len(tags) != len(entries):
            return f"{predicate_type} carries a {field_name} entry that yields no tag key"
        return ""
    # A service-type condition may legitimately list no types at all; every other value field
    # cannot be stored empty, so an empty one means the shape was not what it claims to be.
    if not entries and predicate_type is not PredicateType.SERVICE_TYPE_EQUALS:
        return f"{predicate_type} carries an empty {field_name}"
    if len(values) != len(entries):
        return f"{predicate_type} carries a non-text {field_name} entry"
    return ""


def _matched_values(
    predicate_type: PredicateType | None, predicate: dict[str, Any]
) -> tuple[str, ...]:
    """Read the one value field the predicate type is bound to, and no other.

    Each predicate type stores its values under exactly one field name, so reading by type keeps
    a management-zone reference - matched all-of - out of the any-of path.
    """
    field_name = VALUE_FIELDS.get(predicate_type) if predicate_type else None
    raw = predicate.get(field_name) if field_name else None
    if not isinstance(raw, list):
        return ()
    return tuple(str(value) for value in raw if isinstance(value, str))


# Which field each predicate type stores its values under. One binding, read by whatever
# reads a stored predicate and by whatever writes one.
VALUE_FIELDS = {
    PredicateType.STRING_EQUALS: "textValues",
    PredicateType.STARTS_WITH: "textValues",
    PredicateType.ENDS_WITH: "textValues",
    PredicateType.CONTAINS: "textValues",
    PredicateType.SERVICE_TYPE_EQUALS: "serviceType",
    PredicateType.MANAGEMENT_ZONES_CONTAINS_ALL: "managementZones",
}


def _compares_case_sensitively(predicate_type: PredicateType, predicate: dict[str, Any]) -> bool:
    """Resolve how the predicate compares, with the string default applied.

    Only the four string predicates are configurable, and their default is case-*insensitive* -
    the comparison lowercases both sides. Everything else compares exactly, and `STRING_EXISTS`
    compares nothing at all.
    """
    if predicate_type in STRING_PREDICATES:
        return predicate.get("caseSensitive") is True
    return predicate_type in _EXACT_PREDICATES


STRING_PREDICATES = frozenset(
    {
        PredicateType.STRING_EQUALS,
        PredicateType.STARTS_WITH,
        PredicateType.ENDS_WITH,
        PredicateType.CONTAINS,
    }
)
_EXACT_PREDICATES = frozenset(
    {
        PredicateType.TAG_EQUALS,
        PredicateType.TAG_KEY_EQUALS,
        PredicateType.SERVICE_TYPE_EQUALS,
        PredicateType.MANAGEMENT_ZONES_CONTAINS_ALL,
    }
)


def _classify_pg_tag(
    attribute: Attribute, predicate_type: PredicateType, tags: tuple[ParsedTag, ...]
) -> ClassifiedCondition:
    """Split a process-group tag condition by whether *every* key in it is primary.

    A whole-condition decision, never a per-tag one: the backend evaluates against span resource
    attributes only when every key is primary, and against the process-group entity otherwise.
    """
    primary = tuple(is_primary_tag_key(tag.key) for tag in tags)
    if any(primary) and not all(primary):
        return ClassifiedCondition(
            attribute=attribute,
            predicate_type=predicate_type,
            standing=ConditionStanding.DEPRECATED,
            side=Side.ENTITY,
            entity=FilteredEntity.PROCESS_GROUP,
            case_sensitive=True,
            tags=tags,
            reason=DeprecationReason.MIXED_PG_TAG,
        )
    if all(primary):
        return ClassifiedCondition(
            attribute=attribute,
            predicate_type=predicate_type,
            standing=ConditionStanding.SURVIVING,
            side=Side.SPAN,
            # A span-side condition filters no entity: it is evaluated on the entry-point span's
            # resource attributes, and yields the services of the spans it matched.
            entity=FilteredEntity.SERVICE,
            case_sensitive=True,
            tags=tags,
        )
    return ClassifiedCondition(
        attribute=attribute,
        predicate_type=predicate_type,
        standing=ConditionStanding.DEPRECATED,
        side=Side.ENTITY,
        entity=FilteredEntity.PROCESS_GROUP,
        case_sensitive=True,
        tags=tags,
        reason=DeprecationReason.NON_PRIMARY_PG_TAG,
    )


def _parsed_tags(
    predicate_type: PredicateType | None, predicate: dict[str, Any]
) -> tuple[ParsedTag, ...]:
    if predicate_type is PredicateType.TAG_EQUALS:
        return tuple(_parse_tag_entries(predicate.get("tags"), keep_value=True))
    if predicate_type is PredicateType.TAG_KEY_EQUALS:
        # The predicate ignores the value, so recording one would invent a narrowing the rule
        # does not have. `TAG_EQUALS` with no value is the narrower shape and keeps its null.
        return tuple(_parse_tag_entries(predicate.get("tagKeys"), keep_value=False))
    return ()


def _parse_tag_entries(entries: Any, *, keep_value: bool) -> list[ParsedTag]:
    if not isinstance(entries, list):
        return []
    parsed: list[ParsedTag] = []
    for entry in entries:
        if not isinstance(entry, str):
            continue
        tag = parse_universal_tag(entry)
        if tag is not None:
            parsed.append(tag if keep_value else ParsedTag(tag.key, None))
    return parsed


# Which entity a condition's filter runs on. The two process-group attributes do not filter
# services: a service is selected because the process group hosting it matched, and that hosting
# relation - not the attribute name - is what a query reproducing the condition is built from.
_ATTRIBUTE_ENTITIES = {
    Attribute.SERVICE_NAME: FilteredEntity.SERVICE,
    Attribute.SERVICE_TYPE: FilteredEntity.SERVICE,
    Attribute.SERVICE_TAG: FilteredEntity.SERVICE,
    Attribute.SERVICE_MANAGEMENT_ZONE: FilteredEntity.SERVICE,
    Attribute.PG_NAME: FilteredEntity.PROCESS_GROUP,
    Attribute.PG_TAG: FilteredEntity.PROCESS_GROUP,
}

_DEPRECATED_ATTRIBUTES = {
    Attribute.SERVICE_TAG: DeprecationReason.SERVICE_TAG,
    Attribute.SERVICE_MANAGEMENT_ZONE: DeprecationReason.MANAGEMENT_ZONE,
}

# Which predicate types each attribute offers. Anything outside this is recorded as
# unclassifiable rather than assumed harmless.
_NAME_PREDICATES = frozenset(
    {
        PredicateType.STRING_EQUALS,
        PredicateType.STARTS_WITH,
        PredicateType.ENDS_WITH,
        PredicateType.CONTAINS,
        PredicateType.STRING_EXISTS,
    }
)
_TAG_PREDICATES = frozenset({PredicateType.TAG_EQUALS, PredicateType.TAG_KEY_EQUALS})
_ATTRIBUTE_PREDICATES = {
    Attribute.SERVICE_NAME: _NAME_PREDICATES,
    Attribute.PG_NAME: _NAME_PREDICATES,
    Attribute.SERVICE_TYPE: frozenset({PredicateType.SERVICE_TYPE_EQUALS}),
    Attribute.SERVICE_TAG: _TAG_PREDICATES,
    Attribute.PG_TAG: _TAG_PREDICATES,
    Attribute.SERVICE_MANAGEMENT_ZONE: frozenset(
        {PredicateType.MANAGEMENT_ZONES_CONTAINS_ALL}
    ),
}
TAG_FIELDS = {PredicateType.TAG_EQUALS: "tags", PredicateType.TAG_KEY_EQUALS: "tagKeys"}


@dataclass(frozen=True)
class ScanCoverage:
    """Figures about the scan itself, not findings about the tenant's rules.

    Reading a rule is the only way to rule it out, so all three counts describe the one
    classification pass. Everything downstream describes the affected subset alone.
    """

    rules_read: int
    enabled: int
    affected: int
    affected_reasons: dict[DeprecationReason, int]


def summarise(rules: Iterable[ClassifiedRule]) -> ScanCoverage:
    read = list(rules)
    affected = [rule for rule in read if rule.enabled and carries_deprecated_condition(rule)]
    # Once per rule, not per condition: the breakdown answers "how many affected rules have a tag
    # problem", so a rule carrying two service-tag conditions is still one rule.
    reasons = Counter(
        reason
        for rule in affected
        for reason in dict.fromkeys(_deprecation_reasons(rule.conditions))
    )
    return ScanCoverage(
        rules_read=len(read),
        enabled=sum(1 for rule in read if rule.enabled),
        affected=len(affected),
        affected_reasons=dict(reasons),
    )


def carries_deprecated_condition(rule: ClassifiedRule) -> bool:
    """Whether Phase 3 stops evaluating any of this rule's conditions.

    Kept apart from the standing: a rule that is dead today, or one the tool could not fully
    read, still counts as affected while being handled by a human rather than a replacement.
    """
    return any(c.standing is ConditionStanding.DEPRECATED for c in rule.conditions)
