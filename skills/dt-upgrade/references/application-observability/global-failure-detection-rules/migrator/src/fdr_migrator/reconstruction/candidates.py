"""Building, from a rule's own Target Set, the conditions that reproduce it without a
Deprecated Condition.

Values are read off the rows that resolved the Target Set and pruned against what the API can
express and what the whole Target Set carries. Whether they reproduce it is not decided here.
"""

from __future__ import annotations

# A synthesised tag condition has the same shape as one read off a stored rule because it is the
# same domain object arrived at from the other direction. Sharing a constructor would make the
# classifier depend on the harvester.
# pylint: disable=duplicate-code

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from ..dql.queries import (
    CANDIDATE_ATTRIBUTES,
    RUNS_ON_PG,
    CandidateAttribute,
    TranslatedRule,
    build_query,
    harvest_yield,
    on_entity_ids,
    on_services,
)
from ..dql.translation import Dataset, stored_service_types
from ..rules.classification import (
    Attribute,
    ClassifiedCondition,
    ConditionStanding,
    FilteredEntity,
    PredicateType,
    Side,
)
from ..rules.tags import ParsedTag
from .resolution import (
    MAX_ARRAY_ELEMENTS,
    IssuedQuery,
    RecordingQueryRunner,
    ResolvedRule,
)

# `fieldsSnapshot` answers with the field names spans carry, which is how the run learns which
# `primary_tags.*` keys exist at all
PRIMARY_TAG_KEY_DISCOVERY = (
    "fieldsSnapshot spans\n"
    '| filter matchesValue(field, "primary_tags.*")\n'
    "| fields field"
)


@dataclass(frozen=True)
class DiscoveredKeys:
    """The `primary_tags.*` keys a tenant's spans carry, and how fully the read answered.

    Three findings, not two: no keys is a fact about the tenant, no answer is the absence of one,
    and a capped answer is a *shorter list* than the tenant carries. Only the first two close the
    attribute. A short list costs nothing but the chance of a better replacement - every key in it
    is measured, verified and used exactly as it would be otherwise - so it is said once and
    changes nothing.
    """

    keys: tuple[str, ...] = ()
    answered: bool = True
    complete: bool = True


def discover_primary_tag_keys(runner: RecordingQueryRunner) -> DiscoveredKeys:
    """The `primary_tags.*` keys this tenant's spans carry, and what the read that asked can say.

    Best-effort on purpose: the Primary Tag attribute is one of four, and a tenant that cannot
    answer this question should still have the other three harvested rather than lose the run.
    """
    try:
        outcome = runner.run(PRIMARY_TAG_KEY_DISCOVERY)
    except Exception:  # pylint: disable=broad-exception-caught
        return DiscoveredKeys(answered=False)
    keys = tuple(sorted({key for row in outcome.records if (key := row.get("field"))}))
    return DiscoveredKeys(keys, complete=outcome.complete)


class DropReason(StrEnum):
    """Why an attribute produced no candidate, as a code a caller matches on.

    Each drops the *attribute*, never the rule: the remaining attributes carry on, and the rule
    is only uncoverable if what remains fails to reproduce the Target Set.
    """

    MISSING_VALUE = "value-missing-on-some-selected-service"
    MISSING_ON_SOME_SPAN = "value-missing-on-some-of-the-selected-entry-point-spans"
    UNREADABLE = "the-read-that-would-have-harvested-it-did-not-answer"
    UNMEASURED_POPULATION = "the-read-that-would-have-measured-it-came-back-capped"
    TOO_LARGE_TO_SCOPE = "more-selected-entities-than-the-harvest-can-be-scoped-by"
    TOO_MANY_VALUES = "more-values-than-the-condition-can-carry"
    NO_STORED_SPELLING = "no-stored-spelling-for-the-value"
    AFFIX_TOO_SHORT = "shared-affix-too-short"
    REDUNDANT = "identical-to-a-surviving-condition"


@dataclass(frozen=True)
class Candidate:
    """One condition built from what the Target Set's own services carry.

    It narrows the conjunction rather than reproducing the Target Set alone, so nothing ranks it
    or tests it by itself.

    Identity is key-level for Primary Tags, so `attribute` carries the key alongside the
    attribute there - two keys are two candidates, not one taken attribute.
    """

    attribute: str
    condition: ClassifiedCondition


@dataclass(frozen=True)
class DroppedAttribute:
    """One attribute that yielded no condition, with the code that says why.

    Named as `Candidate` names it, key included for Primary Tags: what dropped is one key, never
    the Primary Tag attribute as a whole.
    """

    attribute: str
    reason: DropReason
    detail: str = ""


@dataclass(frozen=True)
class _AnswerTruncated:
    """A harvest read that answered, with the platform capping the rows it answered with.

    Neither of the two neighbouring readings: the read did answer, so it is not unreadable, and
    the scope was expressible, so it is not too large to scope by. What is lost is the population
    - whichever selected services the missing rows would have spoken for - so no claim about what
    they carry can be made from the rows that did arrive.
    """

    rows: int

    @property
    def detail(self) -> str:
        return f"the read answered with {self.rows} row(s) and was capped there"


def _dropped_for(attribute: str, read: DropReason | _AnswerTruncated) -> DroppedAttribute:
    """The drop one failed harvest read makes, in the wording that reading deserves.

    A capped answer and a resolution read's capped answer are the same signal with opposite
    consequences: a resolution read builds the Target Set, so capping it leaves the rule without a
    subject and the rule is given up; a harvest read feeds one attribute's values, and the Target
    Set is already known, so only that attribute is given up and the rule carries on.
    """
    if isinstance(read, _AnswerTruncated):
        return DroppedAttribute(attribute, DropReason.UNMEASURED_POPULATION, read.detail)
    return DroppedAttribute(attribute, read)


@dataclass(frozen=True)
class Harvest:
    """What one rule's Target Set yielded: the conditions it can be narrowed by, and the rest."""

    candidates: tuple[Candidate, ...] = ()
    dropped: tuple[DroppedAttribute, ...] = ()
    values: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    queries: tuple[IssuedQuery, ...] = ()
    # The entry-point spans the rule is evaluated on, or `None` where the read that would have
    # counted them did not answer in full. Unknown rather than zero: a replacement compared
    # against a population nobody measured would be compared against nothing.
    target_spans: int | None = None


def harvest(
    translated: TranslatedRule, resolved: ResolvedRule, runner: RecordingQueryRunner
) -> Harvest:
    """Every candidate one rule's Target Set yields, and the reason each dropped attribute did not.

    Two attributes have their values elsewhere than the service rows - process-group names on the
    process groups, Primary Tags on the entry-point spans - and reach that dataset here, once.
    """
    issued: list[IssuedQuery] = []
    rows = _of_target_set(resolved.rows.services, resolved.target_set)
    hosts = _host_rows(translated, resolved, runner, rows, issued)
    spans = _span_rows(translated, resolved, runner, issued)
    candidates: list[Candidate] = []
    dropped: list[DroppedAttribute] = []
    values: dict[str, tuple[str, ...]] = {}
    harvested = [
        *_entity_attributes(rows, hosts),
        *_primary_tag_attributes(spans, translated.primary_tag_keys, resolved.target_set),
    ]
    for attribute, carried, outcome in harvested:
        values[attribute] = carried
        settled = _not_already_said(translated, attribute, outcome)
        if isinstance(settled, DroppedAttribute):
            dropped.append(settled)
        else:
            candidates.append(Candidate(attribute, settled))
    return Harvest(
        tuple(candidates),
        tuple(dropped),
        values,
        tuple(issued),
        _target_spans(spans, resolved.target_set),
    )


def _target_spans(
    rows: Sequence[Mapping[str, Any]] | DropReason | _AnswerTruncated, target_set: frozenset[str]
) -> int | None:
    """How many entry-point spans the rule targets, over the same rows a candidate is measured on.

    The rows are a partition of that population - one group-by over the service and every
    discovered key at once, so every span falls into exactly one of them, null-valued keys
    included - which is why summing them row-wise needs no correction for overlap.
    """
    if isinstance(rows, (DropReason, _AnswerTruncated)):
        return None
    return spans_of(_of_selected_services(rows, target_set))


# An attribute name, the values it harvested, and the condition they make or the reason they make none.
_Harvested = tuple[str, tuple[str, ...], "ClassifiedCondition | DroppedAttribute"]


def _entity_attributes(
    rows: Sequence[Mapping[str, Any]],
    hosts: Sequence[Mapping[str, Any]] | DropReason | _AnswerTruncated,
) -> list[_Harvested]:
    """The declared attributes, each read from the dataset its declaration names."""
    found: list[_Harvested] = []
    for candidate in CANDIDATE_ATTRIBUTES:
        if candidate.dataset is Dataset.SERVICES:
            carried, missing = _column_values(rows, candidate.column)
        elif isinstance(hosts, (DropReason, _AnswerTruncated)):
            # Nothing partial is kept: the names that did arrive cannot say whether the ones that
            # did not would have covered the rest of the selected services.
            found.append((candidate.attribute, (), _dropped_for(candidate.attribute, hosts)))
            continue
        else:
            # A process group is not a service: what decides this attribute is whether every
            # selected service is reachable through a name, not whether every row carries one.
            carried, _ = _column_values(hosts, candidate.column)
            missing = not carried or not _every_service_has_a_named_host(rows, hosts)
        found.append(
            (candidate.attribute, carried, _condition_for(candidate, carried, missing))
        )
    return found


def _primary_tag_attributes(
    rows: Sequence[Mapping[str, Any]] | DropReason | _AnswerTruncated,
    keys: Sequence[str],
    target_set: frozenset[str],
) -> list[_Harvested]:
    """One attribute per discovered Primary Tag key, off the entry-point spans of the selected
    services, plus one for a union of keys where no single key reaches every one of them.

    Identity is key-level, never "the tag attribute is taken": a Surviving Condition on one key
    must not stop another key becoming a candidate, and two keys do narrow each other, since a
    condition matches any of its own entries while conditions AND.
    """
    if isinstance(rows, _AnswerTruncated):
        # One drop for the axis rather than one per key: the read says nothing about any of them,
        # and repeating an identical line per key would read as ten separate findings.
        axis = str(Attribute.PG_TAG)
        return [(axis, (), _dropped_for(axis, rows))]
    if isinstance(rows, DropReason):
        # No rows means no evidence about any key, and a union is assembled out of that evidence,
        # so the keys drop one by one and there is nothing left to cover the Target Set with.
        return [
            (f"{Attribute.PG_TAG} {key}", (), DroppedAttribute(f"{Attribute.PG_TAG} {key}", rows))
            for key in keys
        ]
    narrowed = _of_selected_services(rows, target_set)
    found: list[_Harvested] = []
    per_key: dict[str, _PrimaryTagValues] = {}
    for key in keys:
        attribute = f"{Attribute.PG_TAG} {key}"
        carried = _primary_tag_values(narrowed, key, target_set)
        per_key[key] = carried
        found.append((attribute, carried.values, _primary_tag_condition(attribute, key, carried)))
    union = _primary_tag_union(narrowed, per_key, found, target_set)
    if union is not None:
        found.append(union)
    return found


def _primary_tag_union(
    rows: Sequence[Mapping[str, Any]],
    per_key: Mapping[str, _PrimaryTagValues],
    harvested: Sequence[_Harvested],
    target_set: frozenset[str],
) -> _Harvested | None:
    """Several keys in one condition, for a Target Set no single key is carried by.

    The bottom rung of the Primary Tag ladder, and reached only when the two above it cannot be. A
    key carried by every selected service is a condition on its own, and two such conditions AND to
    the intersection of what they match where one any-of over both keys matches the union - so
    merging usable keys would manufacture over-selection the per-key conditions do not have.
    """
    if any(isinstance(outcome, ClassifiedCondition) for _, _, outcome in harvested):
        return None
    # Every key that could not stand as a condition on its own, on either of the two counts. A key
    # on every selected service can still leave spans of one of them matching nothing, and that is
    # a key another key in the cover can supply the missing spans for.
    pool = {
        key: carried
        for key, carried in per_key.items()
        if carried.missing_on_some_service or carried.missing_on_some_span
    }
    cover = _covering_keys(rows, pool, target_set)
    if not cover:
        return None
    attribute = _union_name(cover)
    values = tuple(sorted({value for key in cover for value in pool[key].values}))
    return (attribute, values, _union_condition(attribute, cover, pool, rows))


def _union_condition(
    attribute: str,
    cover: Sequence[str],
    pool: Mapping[str, _PrimaryTagValues],
    rows: Sequence[Mapping[str, Any]],
) -> ClassifiedCondition | DroppedAttribute:
    """The condition one cover makes, in whichever of the two tag forms every key in it allows.

    The value form is the narrower one and is preferred, but a span matches it only through a whole
    (key, value) pair, so it has to pass the cover's own test one rung finer: no targeted span may
    be left carrying none of the emitted pairs. A span whose only key of the cover holds a value
    the comparison cannot express - an array, or one absent from the rows - is such a span. Where
    the pairs fall short the whole condition weakens to key existence rather than the cover losing
    a key, since dropping the key would leave the services only it carries selected by nothing.
    """
    if not _spans_missing_all_pairs(rows, cover, pool):
        exact = _within_cap(
            attribute,
            _primary_tag_comparison(
                PredicateType.TAG_EQUALS,
                tuple(ParsedTag(key, value) for key in cover for value in pool[key].values),
            ),
        )
        if not (
            isinstance(exact, DroppedAttribute) and exact.reason is DropReason.TOO_MANY_VALUES
        ):
            return exact
    # Nothing weaker than key existence to fall back to, so an overflowing cover is a drop.
    return _within_cap(
        attribute,
        _primary_tag_comparison(
            PredicateType.TAG_KEY_EQUALS, tuple(ParsedTag(key, None) for key in cover)
        ),
    )


def _covering_keys(
    rows: Sequence[Mapping[str, Any]],
    pool: Mapping[str, _PrimaryTagValues],
    target_set: frozenset[str],
) -> tuple[str, ...]:
    """The keys that together leave no targeted span carrying none of them, or none if there are no
    such keys.

    A tag condition is compared against each entry-point span, and it matches a span when any one
    of its entries does, so the population a cover has to reach is the spans and not the services
    carrying them. Several keys each sitting on a sliver of one service's spans cover that service
    between them and still leave most of its spans matching nothing.

    The rows are a partition of those spans - one group-by over the service and every key at once -
    so a row counts towards the uncovered total exactly when every key of the cover is absent from
    it, with no correction for overlap. The arithmetic never to reach for is a sum per key: "this
    key is on 50 spans and that one on 50, so together they are on the 100" double-counts every
    span carrying both.

    Greedy, then pruned of any key the others made unnecessary, then sorted. Fewest keys is a proxy
    for the most selective cover rather than a proof of it - two covers are not nested, so only the
    direction is certain: within one cover, every key removed narrows. Sorted output is what lets a
    union that repeats a Surviving Condition be recognised as one, and what makes two runs over the
    same rows emit the same condition.
    """
    uncovered = tuple(rows)
    chosen: list[str] = []
    while spans_of(uncovered):
        widest = _widest_key(pool, uncovered)
        if widest is None:
            return ()
        chosen.append(widest)
        uncovered = tuple(row for row in uncovered if not _carries(row, widest))
    if not chosen or not _reaches_every_service(chosen, pool, target_set):
        return ()
    return tuple(sorted(_without_redundant(chosen, rows, pool, target_set)))


def _widest_key(
    pool: Mapping[str, _PrimaryTagValues], uncovered: Sequence[Mapping[str, Any]]
) -> str | None:
    """The key on the most spans still uncovered, by name where two are on as many.

    `None` where none of them is on any, which is a span population the pool cannot cover at all.
    """
    widest: str | None = None
    reached = 0
    for key in sorted(pool):
        found = spans_of(row for row in uncovered if _carries(row, key))
        if found > reached:
            widest, reached = key, found
    return widest


def _without_redundant(
    chosen: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    pool: Mapping[str, _PrimaryTagValues],
    target_set: frozenset[str],
) -> list[str]:
    """The cover with any key the others made unnecessary taken back out.

    Greedy can leave one behind, and a key on no span the rest are not on only widens the match. A
    key goes only when what is left still leaves no span uncovered, which is the same test the
    cover as a whole had to pass.
    """
    kept = list(chosen)
    for key in chosen:
        others = [other for other in kept if other != key]
        if (
            others
            and not _spans_missing_all(rows, others)
            and _reaches_every_service(others, pool, target_set)
        ):
            kept.remove(key)
    return kept


def _reaches_every_service(
    keys: Sequence[str], pool: Mapping[str, _PrimaryTagValues], target_set: frozenset[str]
) -> bool:
    """Whether every selected service carries one of these keys on at least one of its spans.

    Span coverage says this too wherever a selected service has spans at all, and says nothing at
    all about one that has none - which is the service the cover cannot select and the rows cannot
    show, so it is asked separately.
    """
    reached: frozenset[str] = frozenset()
    for key in keys:
        reached |= pool[key].covered
    return target_set <= reached


def _spans_missing_all(rows: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> int:
    """How many targeted spans carry none of these keys, and so are matched by none of them."""
    return spans_of(row for row in rows if not any(_carries(row, key) for key in keys))


def _spans_missing_all_pairs(
    rows: Sequence[Mapping[str, Any]], cover: Sequence[str], pool: Mapping[str, _PrimaryTagValues]
) -> int:
    """How many targeted spans carry none of the (key, value) pairs a cover would be written as."""
    return spans_of(
        row for row in rows if not any(row.get(key) in pool[key].values for key in cover)
    )


def spans_of(rows: Iterable[Mapping[str, Any]]) -> int:
    """The spans a set of harvested rows stands for."""
    return sum(_spans_in(row) for row in rows)


def _carries(row: Mapping[str, Any], key: str) -> bool:
    """Whether the spans of one harvested row carry a value under a key.

    Null, empty string and empty list are all absence: a condition on a key a span does not carry
    cannot select that span, in either of the two tag forms.
    """
    value = row.get(key)
    return value is not None and value != "" and value != []


def _union_name(cover: Sequence[str]) -> str:
    """How a multi-key condition is named in the harvest, distinct from any one key's name."""
    return f"{Attribute.PG_TAG} any of {', '.join(cover)}"


def _span_rows(
    translated: TranslatedRule,
    resolved: ResolvedRule,
    runner: RecordingQueryRunner,
    issued: list[IssuedQuery],
) -> tuple[Mapping[str, Any], ...] | DropReason | _AnswerTruncated:
    """The entry-point spans the Primary Tag attribute reads.

    A rule with span-side conditions reuses the rows its Target Set was built from;

    A drop reason in place of rows means the attribute was given up, which is the absence of
    evidence about the selected services - not the evidence that they carry no tags. A capped
    answer lands on that same side despite having rows: the keys absent from the rows that did
    arrive are unmeasured, not absent.
    """
    if Dataset.ENTRY_SPANS in translated.filters:
        return tuple(resolved.rows.spans)
    if not translated.primary_tag_keys or not resolved.target_set:
        return ()
    if len(resolved.target_set) > MAX_ARRAY_ELEMENTS:
        return DropReason.TOO_LARGE_TO_SCOPE
    query = build_query(
        Dataset.ENTRY_SPANS,
        [on_services(resolved.target_set)],
        translated.window,
        yields=harvest_yield(Dataset.ENTRY_SPANS, translated.primary_tag_keys),
    )
    try:
        outcome = runner.run(query)
    except Exception:  # pylint: disable=broad-exception-caught
        return DropReason.UNREADABLE
    issued.append(IssuedQuery(Dataset.ENTRY_SPANS, query, outcome.cache_hit))
    if not outcome.complete:
        return _AnswerTruncated(len(outcome.records))
    return tuple(outcome.records)


@dataclass(frozen=True)
class _PrimaryTagValues:
    """What one Primary Tag key carried across the selected services' entry-point spans."""

    values: tuple[str, ...]
    # The selected services this key was found on, and the ones it had to cover. Kept as the two
    # sets rather than the "carried by all" answer they settle, because keys that each carry part of
    # the Target Set can cover it together.
    covered: frozenset[str]
    target_set: frozenset[str]
    # A key can be scalar on one record and array on the next, so this is judged from every
    # harvested row rather than from the first one carrying the key.
    non_string_somewhere: bool
    # The entry-point spans the rule targets, and how many of them this key is absent from. A
    # Primary Tag is compared against *each* span, so this - not the service set above - is what
    # decides whether the key can stand as a condition.
    spans: int
    uncovered_spans: int

    @property
    def missing_on_some_service(self) -> bool:
        """A key absent from every span of some selected service cannot select it, in either form."""
        return bool(self.target_set - self.covered)

    @property
    def missing_on_some_span(self) -> bool:
        """A key absent from even one targeted span cannot select that span, in either form.

        Every single span, with no tolerance: the compiled condition is evaluated on each of them,
        so one span without the key is one span the replacement stops applying to.
        """
        return self.uncovered_spans > 0

    @property
    def span_coverage(self) -> str:
        """The two counts a reader needs to see the size of what a key would give up."""
        return (
            f"carried on {self.spans - self.uncovered_spans} of {self.spans} "
            "failure-detection entry-point spans of the selected services"
        )


def _primary_tag_values(
    rows: Sequence[Mapping[str, Any]], key: str, target_set: frozenset[str]
) -> _PrimaryTagValues:
    """One key's values, the services carrying it, and how much of the span population it reaches.

    The rows are one group-by over the service and *every* discovered key at once, so each targeted
    span falls into exactly one of them - null-valued keys included, since a span missing a key
    lands in that key's null bucket rather than being left out. That makes the buckets disjoint,
    which is what lets the spans be counted row by row with no correction for overlap. The
    arithmetic never to reach for is a sum per key - "this key covers 50 spans and that one 50, so
    together they cover the 100" - which double-counts every span carrying both.
    """
    found: set[str] = set()
    non_string = False
    carrying: set[str] = set()
    spans = 0
    uncovered = 0
    for row in rows:
        service = row.get(str(Dataset.SERVICES))
        value = row.get(key)
        counted = _spans_in(row)
        spans += counted
        if not _carries(row, key):
            uncovered += counted
            continue
        if isinstance(value, str):
            found.add(value)
        else:
            non_string = True
        if isinstance(service, str):
            carrying.add(service)
    return _PrimaryTagValues(
        tuple(sorted(found)),
        frozenset(carrying) & target_set,
        target_set,
        non_string,
        spans,
        uncovered,
    )


# The spans one harvested group holds, under the name the summarised read answers with.
_SPAN_COUNT = "count()"


def _spans_in(row: Mapping[str, Any]) -> int:
    """How many entry-point spans one harvested row stands for.

    An aggregation column arrives spelled as a string of digits, so that is the reading that has to
    work; an integer is read too, since nothing guarantees the spelling.

    A row that arrived stands for at least one span, so a count that cannot be read is read as one
    and not as none: none would let every key cover the population by counting nothing at all. That
    fallback is for a count that is genuinely unreadable - a row weighing 1 where it should weigh
    thousands makes a group count masquerade as a span count, and two reads grouped differently
    then compare as though they measured the same thing.
    """
    counted = row.get(_SPAN_COUNT)
    if isinstance(counted, str) and counted.isascii() and counted.isdigit():
        counted = int(counted)
    if isinstance(counted, int) and not isinstance(counted, bool) and counted > 0:
        return counted
    return 1


def _primary_tag_condition(
    attribute: str, key: str, carried: _PrimaryTagValues
) -> ClassifiedCondition | DroppedAttribute:
    """The condition one Primary Tag key makes, in whichever of its two forms the values allow.

    The compiled value comparison holds a string, so a non-string value can never match an exact
    tag, while key existence checks presence only and is satisfied by any type. An array-valued
    key is therefore unusable as a value candidate and still usable as a key-existence one.

    Two ways of failing to reach the population, kept apart because they say different things to
    whoever reads the drop: a selected service that never carries the key at all, and selected
    services that carry it on only part of the entry-point spans the rule targets. The second is
    the one only a span-level attribute can suffer - a Primary Tag is compared against each span -
    and it is a drop for the same reason as the first, since neither form of the condition can
    select a span carrying no such key.
    """
    if carried.missing_on_some_service:
        return DroppedAttribute(attribute, DropReason.MISSING_VALUE)
    if carried.missing_on_some_span:
        return DroppedAttribute(
            attribute, DropReason.MISSING_ON_SOME_SPAN, carried.span_coverage
        )
    if carried.non_string_somewhere or not carried.values:
        return _primary_tag_key_exists(key)
    exact = _within_cap(
        attribute,
        _primary_tag_comparison(
            PredicateType.TAG_EQUALS,
            tuple(ParsedTag(key, value) for value in carried.values),
        ),
    )
    if isinstance(exact, DroppedAttribute) and exact.reason is DropReason.TOO_MANY_VALUES:
        # Reaching here means the key is carried by every selected service, which is the whole of
        # what key existence asks - so the attribute weakens rather than being trimmed to fit.
        return _primary_tag_key_exists(key)
    return exact


def _primary_tag_key_exists(key: str) -> ClassifiedCondition:
    """The weaker of the two Primary Tag forms: this key is present, whatever it carries."""
    return _primary_tag_comparison(PredicateType.TAG_KEY_EQUALS, (ParsedTag(key, None),))


def _primary_tag_comparison(
    predicate_type: PredicateType, tags: tuple[ParsedTag, ...]
) -> ClassifiedCondition:
    # A span-side condition filters no entity: the identities it yields are the services of the
    # spans it matched. The case flag never reaches tags - the compiled predicate compares them
    # exactly whatever it says.
    return ClassifiedCondition(
        attribute=Attribute.PG_TAG,
        predicate_type=predicate_type,
        standing=ConditionStanding.SURVIVING,
        side=Side.SPAN,
        entity=FilteredEntity.SERVICE,
        case_sensitive=True,
        tags=tags,
    )


# What each predicate field accepts, from the schema that validates it. Ceilings, not policy: past
# one the rule is rejected outright, and trimming to fit would silently under-select.
VALUE_CAPS = {
    PredicateType.STRING_EQUALS: 10,
    PredicateType.STARTS_WITH: 10,
    PredicateType.ENDS_WITH: 10,
    PredicateType.CONTAINS: 10,
    PredicateType.SERVICE_TYPE_EQUALS: 100,
    PredicateType.TAG_EQUALS: 50,
    PredicateType.TAG_KEY_EQUALS: 50,
}


def _within_cap(
    attribute: str, condition: ClassifiedCondition
) -> ClassifiedCondition | DroppedAttribute:
    """The condition as built, or the reason it cannot be stored in one predicate.

    Overflowing a field is genuinely inexpressible: values within a field are the disjunction, so
    splitting them across fields or conditions would AND them instead.
    """
    carried = len(condition.values) + len(condition.tags)
    cap = VALUE_CAPS[condition.predicate_type] if condition.predicate_type else 0
    if carried > cap:
        return DroppedAttribute(
            attribute,
            DropReason.TOO_MANY_VALUES,
            f"{carried} distinct values, where the condition carries at most {cap}",
        )
    return condition


def _host_rows(
    translated: TranslatedRule,
    resolved: ResolvedRule,
    runner: RecordingQueryRunner,
    rows: Sequence[Mapping[str, Any]],
    issued: list[IssuedQuery],
) -> tuple[Mapping[str, Any], ...] | DropReason | _AnswerTruncated:
    """The process-group rows the name attribute is harvested from - one query per rule, never two.

    A rule with its own process-group filters reuses the rows it already read. Those are the
    process groups that *matched the condition*, not the ones hosting a selected service - the
    looser set, which can make a candidate over-select or overflow a cap but cannot make it
    wrong, since the service query was itself filtered by exactly those ids. Reusing them holds
    even when that filter is deprecated: reading values off what a deprecated condition selected
    is the point of the tool, and it is the query that *proves* a candidate that may carry none.

    A rule without such filters asks here instead, scoped by the hosting ids its service rows
    carried.
    """
    if Dataset.PROCESS_GROUPS in translated.filters:
        return tuple(resolved.rows.process_groups)
    hosted = _hosting_ids(rows)
    if not hosted:
        return ()
    if len(hosted) > MAX_ARRAY_ELEMENTS:
        return DropReason.TOO_LARGE_TO_SCOPE
    query = build_query(
        Dataset.PROCESS_GROUPS,
        [on_entity_ids(hosted)],
        translated.window,
    )
    try:
        outcome = runner.run(query)
    except Exception:  # pylint: disable=broad-exception-caught
        return DropReason.UNREADABLE
    issued.append(IssuedQuery(Dataset.PROCESS_GROUPS, query, outcome.cache_hit))
    if not outcome.complete:
        return _AnswerTruncated(len(outcome.records))
    return tuple(outcome.records)


def _hosting_ids(rows: Sequence[Mapping[str, Any]]) -> frozenset[str]:
    """The process groups the selected services run on, off the rows that resolved them."""
    return frozenset(
        identifier
        for row in rows
        for identifier in _as_list(row.get(_HOSTS))
        if isinstance(identifier, str) and identifier
    )


def _every_service_has_a_named_host(
    rows: Sequence[Mapping[str, Any]], hosts: Sequence[Mapping[str, Any]]
) -> bool:
    """Whether a name condition on the hosts can reach every selected service.

    One running on no process group the harvest found a name for is unreachable by any name
    condition, so the attribute would under-select by construction.
    """
    named = {row["id"] for row in hosts if row.get("id") and row.get("entity.name")}
    return all(named & _as_set(row.get(_HOSTS)) for row in rows)


def _as_list(value: Any) -> list[Any]:
    """One record's relationship, whether it came back as a list or as a single identity."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _as_set(value: Any) -> set[str]:
    return {entry for entry in _as_list(value) if isinstance(entry, str)}


# The hosting relation as it comes back on a row - deliberately not the spelling the query asks
# with, which is backticked. Reading rows by the projected spelling finds nothing on every one of
# them, and that surfaces as a silently dropped attribute rather than an error.
_HOSTS = RUNS_ON_PG.replace("`", "")


def _of_selected_services(
    rows: Sequence[Mapping[str, Any]], target_set: frozenset[str]
) -> tuple[Mapping[str, Any], ...]:
    """Narrow harvested span rows to the spans a replacement actually has to reproduce.

    The same narrowing the service rows get, and for the same reason: a span query scoped by a
    rule's own conditions also answers for services the Target Set excluded, and those spans are
    not part of what has to be reproduced. Letting them vote would drop a good candidate over a
    service the replacement never has to select.
    """
    return tuple(row for row in rows if row.get(str(Dataset.SERVICES)) in target_set)


def _of_target_set(
    rows: Sequence[Mapping[str, Any]], target_set: frozenset[str]
) -> tuple[Mapping[str, Any], ...]:
    """Narrow harvested rows to the services a replacement actually has to reproduce.

    A service query's rows also carry the externals that were partitioned out and, for a rule with
    span-side conditions, the services whose spans never matched. Neither is in the Target Set, so
    neither votes: dropping an attribute because an *excluded* service lacks a value would throw
    away a good candidate.
    """
    return tuple(row for row in rows if row.get("id") in target_set)


def _column_values(
    rows: Sequence[Mapping[str, Any]], column: str
) -> tuple[tuple[str, ...], bool]:
    """The distinct values of one column, and whether any row was missing one.

    Null, absent, empty string and empty list all count as missing: a condition on an attribute a
    selected service does not carry cannot select it.
    """
    found: set[str] = set()
    missing = not rows
    for row in rows:
        value = row.get(column)
        if isinstance(value, str) and value:
            found.add(value)
        else:
            missing = True
    return tuple(sorted(found)), missing


def _condition_for(
    candidate: CandidateAttribute, harvested: tuple[str, ...], missing: bool
) -> ClassifiedCondition | DroppedAttribute:
    if missing:
        return DroppedAttribute(candidate.attribute, DropReason.MISSING_VALUE)
    if candidate.predicate_type is PredicateType.SERVICE_TYPE_EQUALS:
        return _service_type_condition(candidate, harvested)
    exact = _within_cap(candidate.attribute, _string_condition(candidate, harvested))
    if isinstance(exact, DroppedAttribute) and exact.reason is DropReason.TOO_MANY_VALUES:
        # The only drop with a second chance: an attribute dropped for a *missing* value has no
        # common affix either, since a missing value yields no substring.
        return _affix_condition(candidate, harvested, exact)
    return exact


# Below this, an affix is shared by a large part of a tenant and costs a query to learn that.
# Measured against real service names, not chosen: selectivity improves sharply to about three
# characters and barely at all beyond four.
MIN_AFFIX_LENGTH = 4


def _affix_condition(
    candidate: CandidateAttribute, harvested: tuple[str, ...], dropped: DroppedAttribute
) -> ClassifiedCondition | DroppedAttribute:
    """The same names written as one affix condition, when they will not fit an exact one.

    Derived, never chosen: the longest common prefix, suffix and substring are deterministic over
    the harvested names, and whether the result over-selects is the verification query's answer.
    Prefix before suffix before substring, at most one of them, and on the name attributes alone -
    the only ones the API gives an affix predicate for.
    """
    if candidate.predicate_type is not PredicateType.STRING_EQUALS:
        return dropped
    for predicate, affix in (
        (PredicateType.STARTS_WITH, _common_prefix(harvested)),
        (PredicateType.ENDS_WITH, _common_suffix(harvested)),
        (PredicateType.CONTAINS, _common_substring(harvested)),
    ):
        if len(affix) >= MIN_AFFIX_LENGTH:
            return replace(
                _string_condition(candidate, (affix,)), predicate_type=predicate
            )
    return DroppedAttribute(
        candidate.attribute,
        DropReason.AFFIX_TOO_SHORT,
        f"{dropped.detail}, and they share no affix of at least "
        f"{MIN_AFFIX_LENGTH} characters",
    )


def _common_prefix(values: Sequence[str]) -> str:
    shortest = min(values, key=len)
    for length in range(len(shortest), 0, -1):
        head = shortest[:length]
        if all(value.startswith(head) for value in values):
            return head
    return ""


def _common_suffix(values: Sequence[str]) -> str:
    reversed_prefix = _common_prefix([value[::-1] for value in values])
    return reversed_prefix[::-1]


def _common_substring(values: Sequence[str]) -> str:
    """The longest run of characters every one of the names contains.

    Longest candidate first, so the first hit is the answer - a common substring is likelier to be
    coincidence than a common prefix, and a shorter one still more so.
    """
    shortest = min(values, key=len)
    for length in range(len(shortest), MIN_AFFIX_LENGTH - 1, -1):
        for start in range(len(shortest) - length + 1):
            run = shortest[start : start + length]
            if all(run in value for value in values):
                return run
    return ""


def _service_type_condition(
    candidate: CandidateAttribute, harvested: tuple[str, ...]
) -> ClassifiedCondition | DroppedAttribute:
    """Harvested service types, written back in the spelling a rule stores them under."""
    stored: set[str] = set()
    for spelling in harvested:
        written = stored_service_types(spelling)
        if not written:
            return DroppedAttribute(
                candidate.attribute,
                DropReason.NO_STORED_SPELLING,
                f"the service type {spelling} has no spelling a condition can be stored with",
            )
        stored.update(written)
    return _within_cap(
        candidate.attribute, _string_condition(candidate, tuple(sorted(stored)))
    )


def _string_condition(
    candidate: CandidateAttribute, harvested: tuple[str, ...]
) -> ClassifiedCondition:
    return ClassifiedCondition(
        attribute=candidate.attribute,
        predicate_type=candidate.predicate_type,
        standing=ConditionStanding.SURVIVING,
        side=Side.ENTITY,
        entity=_ATTRIBUTE_ENTITIES[candidate.attribute],
        # Emitted and translated case-sensitively, so the condition selects the harvested names
        # and not every service whose name differs from one only in case.
        case_sensitive=True,
        values=harvested,
    )


_ATTRIBUTE_ENTITIES = {
    Attribute.SERVICE_NAME: FilteredEntity.SERVICE,
    Attribute.SERVICE_TYPE: FilteredEntity.SERVICE,
    Attribute.PG_NAME: FilteredEntity.PROCESS_GROUP,
}


def _not_already_said(
    translated: TranslatedRule, attribute: str, outcome: ClassifiedCondition | DroppedAttribute
) -> ClassifiedCondition | DroppedAttribute:
    """Drop a candidate the rule already says in exactly the same words, and no more than that.

    Sharing an *attribute* with a Surviving Condition is not duplication - a harvested exact set
    alongside a surviving substring test is often the one thing that makes a rule coverable - and
    neither is a different tag key. Case sensitivity counts as part of the comparison because a
    case-insensitive survivor over the same values selects strictly more services.

    The entries of one predicate are a disjunction, so the order they are stored in is not part of
    what a condition says. A candidate spells them in its own deterministic order and a stored rule
    in whatever order it was written, so comparing them in sequence would emit a second copy of a
    condition the rule already carries.
    """
    if isinstance(outcome, DroppedAttribute):
        return outcome
    for survivor in translated.surviving:
        if (
            survivor.attribute == outcome.attribute
            and survivor.predicate_type == outcome.predicate_type
            and frozenset(survivor.values) == frozenset(outcome.values)
            and frozenset(survivor.tags) == frozenset(outcome.tags)
            and survivor.case_sensitive == outcome.case_sensitive
        ):
            return DroppedAttribute(attribute, DropReason.REDUNDANT)
    return outcome
