"""Proving, against live data, that a condition set carrying no Deprecated Condition selects
exactly what the rule selects today.

The proof is the deliverable: a condition set that reproduces the Target Set exactly *is* the
replacement rule's condition set. Nothing reproduces it, and the rule is not coverable.

Candidates are AND-ed with the Surviving Conditions and the set is tested whole - no ranking, no
per-candidate test. Each candidate's values were harvested from every service in the Target Set,
so intersecting them narrows an over-selection and can never drop a service that belongs; testing
one at a time would cost more and call a rule uncoverable whenever no single attribute expresses
its Target Set but two together do.

Whole, but in two rungs where the harvest yielded a span-side candidate: the entity side is asked
first, and a harvested Primary Tag candidate is only added if the entity side over-selects without
it. A Surviving Condition is never held back this way - what the customer wrote is theirs, at
whatever selectivity.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from dataclasses import dataclass, field, replace
from enum import StrEnum

from ..dql.queries import (
    NOT_EXTERNAL,
    TranslatedRule,
    build_query,
    filters_for,
    on_process_groups,
    on_services,
    verification_yield,
)
from ..dql.translation import Dataset, MatchesNothing, Untranslatable
from ..dql.windowing import QueryWindow
from ..rules.classification import Attribute, ClassifiedCondition, PredicateType, Side
from ..rules.tags import ParsedTag
from .candidates import Candidate, Harvest, harvest, spans_of
from .resolution import (
    IssuedQuery,
    RecordingQueryRunner,
    ResolutionOutcome,
    ResolvedRule,
    service_ids_of,
    within_element_cap,
)


class Coverage(StrEnum):
    """Where a rule's replacement ended, as a code a caller matches on.

    Two outcomes and no middle one: a replacement either reproduces what the rule selects or it is
    not shipped. A partial match would have to be a measurement artefact to be worth shipping, and
    there is no mechanism left that could make one - so a comparison that does not hold is a
    condition set nothing may be built on.
    """

    EXACT = "exact"
    NOT_COVERABLE = "not-coverable"


class NotCoverableReason(StrEnum):
    """Why no replacement could be shipped, one code per distinct cause.

    Kept apart because they call for different things: over-selection is a finding about the rule,
    an empty set is a shape the schema would reject, and an inexpressible one is a gap in what the
    tool can say. `UNDER_SELECTING` and `UNVERIFIED` are the odd ones out - neither says anything
    about the rule, and both call for someone to read the run instead.
    """

    OVER_SELECTING = "over-selecting"
    TOO_MANY_CONDITIONS = "too-many-conditions"
    UNVERIFIED = "unverified"
    SERVICE_TYPE_ONLY = "service-type-only"
    UNDER_SELECTING = "under-selecting"
    EMPTY_REPLACEMENT = "empty-replacement"
    NO_EXPRESSIBLE_CANDIDATE = "no-expressible-candidate"
    ERROR = "processing-error"


@dataclass(frozen=True)
class Replacement:
    """What one rule's replacement turned out to be, and the evidence for it."""

    # pylint: disable=too-many-instance-attributes
    object_id: str
    name: str
    coverage: Coverage
    reason: NotCoverableReason | None = None
    conditions: tuple[ClassifiedCondition, ...] = ()
    # Surviving Conditions a candidate on the same attribute makes redundant. They stay in the
    # replacement - a minimal diff of the customer's own rule, not a rewrite - but they narrow
    # nothing, so nothing may present them as contributing.
    superseded: tuple[ClassifiedCondition, ...] = ()
    # Harvested candidates the replacement reproduces the Target Set without, and therefore does
    # not carry. Kept because they were available: a reader deciding to narrow the rule further,
    # by hand and for their own reasons, should not have to rediscover what the tenant offered.
    unneeded: tuple[Candidate, ...] = ()
    harvested: Harvest = field(default_factory=Harvest)
    queries: tuple[IssuedQuery, ...] = ()
    selected: frozenset[str] = frozenset()
    excess: frozenset[str] = frozenset()
    missed: frozenset[str] = frozenset()
    detail: str = ""


def determine_replacements(
    translations: Sequence[TranslatedRule],
    resolutions: Sequence[ResolvedRule],
    runner: RecordingQueryRunner,
) -> tuple[Replacement, ...]:
    """A replacement, or the reason there is none, for every rule that resolved to a Target Set.

    A rule that did not resolve has no Target Set to reproduce and no yardstick to be measured
    against, so nothing is attempted for it and nothing is claimed about it.
    """
    by_id = {translated.object_id: translated for translated in translations}
    return tuple(
        _contained(by_id[resolved.object_id], resolved, runner)
        for resolved in resolutions
        if resolved.outcome is ResolutionOutcome.RESOLVED and resolved.object_id in by_id
    )


def _contained(
    translated: TranslatedRule, resolved: ResolvedRule, runner: RecordingQueryRunner
) -> Replacement:
    """Determine one rule's replacement inside its own boundary.

    A failure is that rule's outcome, never the run's: one rule the tool cannot finish must not
    cost the rules whose queries the run has already paid for.
    """
    try:
        return determine_replacement(translated, resolved, runner)
    except _Inexpressible as refused:
        return Replacement(
            resolved.object_id,
            resolved.name,
            Coverage.NOT_COVERABLE,
            reason=NotCoverableReason.NO_EXPRESSIBLE_CANDIDATE,
            detail=str(refused),
        )
    except Exception as failure:  # pylint: disable=broad-exception-caught
        return Replacement(
            resolved.object_id,
            resolved.name,
            Coverage.NOT_COVERABLE,
            reason=NotCoverableReason.ERROR,
            detail=str(failure),
        )


def determine_replacement(
    translated: TranslatedRule, resolved: ResolvedRule, runner: RecordingQueryRunner
) -> Replacement:
    """Harvest one rule's candidates, assemble the conjunction, and prove it over one window.

    One window, the one the run was asked about, and no second ask over any other stretch of time.
    A replacement is measured against the Target Set of the stretch the customer named; re-asking
    an earlier one would answer a different question and let its answer stand in for the verdict,
    cancelling a finding whenever the earlier stretch happened to be kinder.
    """
    found = harvest(translated, resolved, runner)
    conditions = (*translated.surviving, *(c.condition for c in found.candidates))
    if not conditions:
        # Zero candidates *and* zero survivors is the one genuine short-circuit. Zero candidates
        # alone is not: the Deprecated Condition may have been redundant, leaving the survivors to
        # reproduce the Target Set - which only a query can say.
        return Replacement(
            resolved.object_id,
            resolved.name,
            Coverage.NOT_COVERABLE,
            reason=NotCoverableReason.EMPTY_REPLACEMENT,
            harvested=found,
            queries=found.queries,
        )
    if _only_service_type(conditions):
        # A handful of values the whole service population is spread across, so a conjunction
        # saying nothing else selects nearly all of it. Settled without asking, because the query
        # would read back every service on the tenant only to count the excess.
        return Replacement(
            resolved.object_id,
            resolved.name,
            Coverage.NOT_COVERABLE,
            reason=NotCoverableReason.SERVICE_TYPE_ONLY,
            conditions=conditions,
            harvested=found,
            queries=found.queries,
        )
    harvested = tuple(c.condition for c in found.candidates)
    span_side = tuple(c for c in found.candidates if c.condition.side is Side.SPAN)
    entity_side = tuple(c for c in harvested if c.side is not Side.SPAN)
    without_them = (*translated.surviving, *entity_side)
    prior: tuple[IssuedQuery, ...] = ()
    if (
        span_side
        and _narrows_on_the_entity_side(without_them)
        and not _over_condition_cap(without_them)
    ):
        # The entity side is asked first, and reproducing the Target Set settles the rule. A
        # harvested Primary Tag candidate that excludes nothing is not free: it is compared
        # against every entry-point span for as long as the rule lives, and it ties a rule that
        # never named a tag to one whose configuration someone else owns.
        proven = _selected_by(without_them, runner, translated.window)
        verdict = _verdict(resolved, found, translated.surviving, entity_side, proven)
        if verdict.coverage is Coverage.EXACT:
            return replace(verdict, unneeded=span_side)
        # Not the replacement, so the harvested candidates go back in and the conjunction is
        # asked again. The reads already paid for are carried into whatever that says.
        prior = proven.issued
    if _over_condition_cap(conditions):
        # Settled without asking: however well this set reproduces the Target Set, no rule can
        # hold it, and proving it would only buy a verdict nothing could be built on.
        return Replacement(
            resolved.object_id,
            resolved.name,
            Coverage.NOT_COVERABLE,
            reason=NotCoverableReason.TOO_MANY_CONDITIONS,
            conditions=conditions,
            harvested=found,
            queries=(*found.queries, *prior),
            detail=(
                f"reproducing the Target Set needs {len(conditions)} conditions, where a rule "
                f"carries at most {MAX_CONDITIONS}"
            ),
        )
    proven = _selected_by(conditions, runner, translated.window)
    return _verdict(
        resolved,
        found,
        translated.surviving,
        harvested,
        replace(proven, issued=(*prior, *proven.issued)),
    )


# What one rule can hold, counting the Surviving Conditions. A ceiling, not policy: past it the
# object is rejected outright, and trimming a conjunction to fit would silently over-select.
MAX_CONDITIONS = 10


def _over_condition_cap(conditions: Sequence[ClassifiedCondition]) -> bool:
    """Whether a condition set is one no rule could store, whatever it selects.

    Decided here rather than where the body is written: a set refused at emission would leave its
    rule reported as covered with nothing to deploy, and the rung asked first is judged on its own
    count, which is the smaller of the two.
    """
    return len(conditions) > MAX_CONDITIONS


def _only_service_type(conditions: Sequence[ClassifiedCondition]) -> bool:
    """Whether a condition set says nothing beyond which service types it wants.

    True of the empty set, which is the shape with even less to say.
    """
    return all(c.attribute is Attribute.SERVICE_TYPE for c in conditions)


def _narrows_on_the_entity_side(conditions: Sequence[ClassifiedCondition]) -> bool:
    """Whether a condition set names the entities to read, and so can be proved cheaply.

    What asking the entity side first buys is a read scoped by the services it selects, and one
    the span read of the fuller set is then spared. A set that names no entity buys neither: its
    span read is bounded by the window alone and passes over every entry-point span on the
    tenant, so asking it to save a second such pass spends more than it saves. Service type is no
    scope either - the whole population is spread across a handful of values.
    """
    return any(
        c.side is Side.ENTITY and c.attribute is not Attribute.SERVICE_TYPE for c in conditions
    )


def _verdict(
    resolved: ResolvedRule,
    found: Harvest,
    surviving: tuple[ClassifiedCondition, ...],
    candidates: tuple[ClassifiedCondition, ...],
    proven: _Proof,
) -> Replacement:
    """One condition set's comparison against the Target Set, and what it leaves saying nothing."""
    return replace(
        _compared(resolved, found, (*surviving, *candidates), proven),
        superseded=_superseded(surviving, candidates),
    )


# Predicates whose harvested values are a *subset* of what a survivor on the same attribute
# matches, having been read off services that already satisfied it. Not affixes: a prefix and a
# suffix on one attribute imply nothing about each other and both genuinely narrow.
_EXACT_PREDICATES = frozenset(
    {
        PredicateType.STRING_EQUALS,
        PredicateType.SERVICE_TYPE_EQUALS,
        PredicateType.TAG_EQUALS,
        PredicateType.TAG_KEY_EQUALS,
    }
)


def _superseded(
    surviving: tuple[ClassifiedCondition, ...], candidates: tuple[ClassifiedCondition, ...]
) -> tuple[ClassifiedCondition, ...]:
    """The Surviving Conditions an exact candidate on the same attribute leaves selecting nothing.

    The candidate supersedes the survivor, not the other way round - a note for the report, not a
    reason to drop either. Read off the candidates the replacement carries and no others: one left
    out narrows nothing in it, so it can make nothing redundant either.
    """
    exact = [c for c in candidates if c.predicate_type in _EXACT_PREDICATES]
    return tuple(
        survivor
        for survivor in surviving
        if any(
            candidate.attribute is survivor.attribute
            and _same_subject(candidate, survivor)
            for candidate in exact
        )
    )


def _same_subject(candidate: ClassifiedCondition, survivor: ClassifiedCondition) -> bool:
    """Whether the candidate is about no more than the survivor is, so the survivor adds nothing.

    A candidate on one primary tag key says nothing about a survivor on another - conditions AND,
    so the two genuinely narrow together. A tag condition matches any of its own entries, so the
    candidate matches more than the survivor unless *every* entry it carries is one the survivor
    would have matched too. Carrying an entry the survivor does not lets through services the
    survivor excludes, whether what differs is the key or the value under it: sharing a key is not
    being implied by one.
    """
    if not candidate.tags and not survivor.tags:
        return True
    return bool(candidate.tags) and all(
        any(_implies(entry, tag) for entry in survivor.tags) for tag in candidate.tags
    )


def _implies(survivor_entry: ParsedTag, candidate_entry: ParsedTag) -> bool:
    """Whether one survivor entry matches everything the candidate entry does.

    A valueless entry asks for the key alone, so it covers every value under it. A valued one
    covers that value and no other - which is why a key-existence candidate is not implied by a
    value survivor, being the looser test of the two.
    """
    if survivor_entry.key != candidate_entry.key:
        return False
    return survivor_entry.value is None or survivor_entry.value == candidate_entry.value


def _compared(
    resolved: ResolvedRule,
    found: Harvest,
    conditions: tuple[ClassifiedCondition, ...],
    proven: _Proof,
) -> Replacement:
    """The verdict, from what the replacement selected against the whole original Target Set.

    Both sides were read over the run's one query window and no other, which is what makes the
    difference between them a statement about the replacement rather than about the passage of
    time.
    """
    target = resolved.target_set
    selected = proven.services
    verdict = Replacement(
        resolved.object_id,
        resolved.name,
        Coverage.EXACT,
        conditions=conditions,
        harvested=found,
        queries=(*found.queries, *proven.issued),
        selected=selected,
    )
    if not proven.complete:
        # Distinct from a shortfall, and never resolved into one: the sets are not compared at
        # all, because a capped read is no evidence of what the condition set selects.
        return replace(
            verdict,
            coverage=Coverage.NOT_COVERABLE,
            reason=NotCoverableReason.UNVERIFIED,
            detail=(
                "a read proving the replacement came back capped, so what the condition set "
                "selects was never compared against what the rule selects"
            ),
        )
    if selected == target:
        return _at_span_grain(verdict, found, proven)
    excess = selected - target
    missed = target - selected
    if excess:
        # No negation operator in this API, so there is nothing to subtract and no refinement to
        # attempt. Reported with what it over-selected by, and no best-effort body.
        return replace(
            verdict,
            coverage=Coverage.NOT_COVERABLE,
            reason=NotCoverableReason.OVER_SELECTING,
            excess=excess,
            missed=missed,
        )
    # No path here can select fewer services than the rule does: every kept candidate's values
    # were harvested from every service in the Target Set, and a surviving span-side condition is
    # carried verbatim. So a shortfall is either a candidate kept whose value was missing on one of
    # them, or a service that changed between the read that resolved the Target Set and the read
    # that proved this set - an entity read answers with the entity's latest values, so a service
    # renamed, re-tagged or re-zoned in between drops out of the second one. Neither is a finding
    # about the rule, and the two cannot be told apart, so the verdict is withheld either way.
    return replace(
        verdict,
        coverage=Coverage.NOT_COVERABLE,
        reason=NotCoverableReason.UNDER_SELECTING,
        missed=missed,
        detail=(
            f"the replacement selected {len(missed)} fewer services than the rule does, on a path "
            "that cannot under-select"
        ),
    )


@dataclass
class _Reads:
    """The verification queries asked so far, and whether all of them answered in full.

    The verification yield groups by the service alone, so it is far less likely to be capped than
    a read that also groups by every discovered tag key - but "less likely" is not a guarantee,
    and this is the one comparison whose two sides could otherwise be capped at once.
    """

    issued: list[IssuedQuery] = field(default_factory=list)
    complete: bool = True


@dataclass(frozen=True)
class _Proof:
    """What one condition set was found to select, at both of the grains it is judged on.

    The span population is `None` where the set carries no span-side condition: the backend then
    applies it to every entry-point span of the services it selects, so there is nothing to count
    and nothing to ask.
    """

    services: frozenset[str]
    spans: int | None
    issued: tuple[IssuedQuery, ...]
    # Whether every read behind those two numbers answered in full. A capped one is not a smaller
    # answer to the same question: it makes over-selection look exact and exact look short,
    # whichever way the capping happens to fall, so neither number may be compared.
    complete: bool = True


def _at_span_grain(verdict: Replacement, found: Harvest, proven: _Proof) -> Replacement:
    """The same comparison one rung finer, on the spans rather than on the services carrying them.

    Failure classification happens per span, so a replacement that keeps every service and loses
    their spans has not reproduced what the rule targeted - and a comparison at service grain
    alone cannot tell the two apart, since one span of a service is enough to keep it in the set.
    The numbers are carried into the outcome, so a reader can see how much traffic it lost.

    Reached only where the service sets already compare equal, and a surviving span-side condition
    selects exactly the spans that defined the Target Span Set - so unlike the service grain, there
    is no latest-state race that could explain a shortfall. If this fires, this tool is wrong.

    Either count being absent means there is nothing to compare rather than a comparison being
    skipped: the Target Span Set is unknown only where no span-side condition survives into the
    replacement, and that is also the shape whose proof counts no spans.
    """
    if proven.spans is None or found.target_spans is None or proven.spans >= found.target_spans:
        return verdict
    return replace(
        verdict,
        coverage=Coverage.NOT_COVERABLE,
        reason=NotCoverableReason.UNDER_SELECTING,
        detail=(
            f"the replacement selected {proven.spans} of the {found.target_spans} entry-point "
            "spans the rule is evaluated on, which this tool has no sound explanation for"
        ),
    )


def _selected_by(
    conditions: tuple[ClassifiedCondition, ...],
    runner: RecordingQueryRunner,
    window: QueryWindow,
) -> _Proof:
    """What one condition set selects, asked in the one order that reproduces it.

    Conditions AND across datasets, so process groups resolve first and compose into the service
    query, whose answer scopes the span query. Built from the conditions given and nothing else:
    a filter from a Deprecated Condition would blind the comparison to everything outside the old
    scope.
    """
    try:
        filters = filters_for(conditions)
    except (Untranslatable, MatchesNothing) as refused:
        raise _Inexpressible(str(refused)) from refused
    entity_side = filters.keys() & {Dataset.SERVICES, Dataset.PROCESS_GROUPS}
    reads = _Reads()
    if not entity_side:
        # The one shape with genuinely no scope. Naming every service on the tenant instead would
        # constrain nothing, exceed the element cap outright above it, and turn a short answer
        # into a replacement reported as missing services it never missed - so the unbounded span
        # read is accepted. A capped answer from it is caught by the same guard as any other, so
        # nothing rests on telling a short read apart from a truncated one here.
        matched = _ask(
            Dataset.ENTRY_SPANS, filters[Dataset.ENTRY_SPANS], window, runner, reads
        )
        return _proof(service_ids_of(matched), spans_of(matched), reads)
    scope: list[str] = []
    if Dataset.PROCESS_GROUPS in filters:
        hosts = _ask(
            Dataset.PROCESS_GROUPS, filters[Dataset.PROCESS_GROUPS], window, runner, reads
        )
        ids = frozenset(row["id"] for row in hosts if row.get("id"))
        if not ids:
            return _proof(frozenset(), None, reads)
        scope = [on_process_groups(within_element_cap(ids, "process group"))]
    services = _ask(
        Dataset.SERVICES,
        [*filters.get(Dataset.SERVICES, ()), *scope, NOT_EXTERNAL],
        window,
        runner,
        reads,
    )
    # Already the non-external services: filtered out of the question rather than partitioned out
    # of the answer, since nothing downstream wants those rows.
    selected = frozenset(row["id"] for row in services if row.get("id"))
    if Dataset.ENTRY_SPANS not in filters:
        return _proof(selected, None, reads)
    if not selected:
        # No service on the entity side is a replacement selecting no service, and the span side
        # can only narrow further. Dropping the scope would turn "no service" into "every
        # service" - the mistake `on_services` refuses an empty list for.
        return _proof(frozenset(), None, reads)
    # Scoped by the replacement's own entity-side result, never by the Target Set - scoping it by
    # the set it is compared against would make over-selection invisible.
    spans = _ask(
        Dataset.ENTRY_SPANS,
        [*filters[Dataset.ENTRY_SPANS], on_services(within_element_cap(selected, "service"))],
        window,
        runner,
        reads,
    )
    return _proof(selected & service_ids_of(spans), spans_of(spans), reads)


def _proof(services: frozenset[str], spans: int | None, reads: _Reads) -> _Proof:
    """One condition set's answer, carrying the standing of the reads that produced it."""
    return _Proof(services, spans, tuple(reads.issued), reads.complete)


def _ask(
    dataset: Dataset,
    filters: Sequence[str],
    window: QueryWindow,
    runner: RecordingQueryRunner,
    reads: _Reads,
) -> Sequence[dict[str, Any]]:
    query = build_query(dataset, filters, window, yields=verification_yield(dataset))
    outcome = runner.run(query)
    reads.issued.append(IssuedQuery(dataset, query, outcome.cache_hit))
    reads.complete = reads.complete and outcome.complete
    return outcome.records


class _Inexpressible(Exception):
    """A condition set this tool cannot put into a query, and therefore cannot prove."""
