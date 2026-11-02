"""The one layer that spends a read which may decide, and the only one that assigns a terminal code.

Takes `090`'s candidate assessments, proves or refutes the ones that need proving, and records how
each surviving replacement's exactness was established. Everything downstream - the emitted body
(`120`) and the Report and Summary Index (`130`) - reads what this layer produces: a
`DataSourceVerdict` per resolved Data Source and a `RequestAttributeVerdict` per Request Attribute,
each carrying a verdict, a reason and a detail, and - where covered - the replacement to emit and the
read that established it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ..attributes.classification import AttributeClassification
from ..clients.transports import DqlAnswer, QueryRunner
from ..dql.queries import Read, TargetShape, verification_span_read
from ..dql.windowing import QueryWindow
from ..reporting.outcomes import (
    AttributeClass,
    ConditionDroppedReason,
    CoveredReason,
    CoveredRequestAttributeReason,
    DataSourceNote,
    DataSourceOutcome,
    HarvestDropReason,
    HarvestGate,
    MatchProof,
    NeutralisedObsoleteReason,
    NeutralisedUncoverableReason,
    NotCoverableReason,
    NoVerdictReason,
    PartiallyCoveredReason,
    RequestAttributeOutcome,
    ResolutionReason,
    SelectsNothingReason,
    UnprocessableReason,
)
from .candidate_search import Candidate, CandidateAssessment
from .harvest import Harvest
from .resolution import Resolution

# Every reason code a row at either level can carry, one closed set per verdict. A union rather than
# a free string, so a consumer classifies on a code the type system knows the shape of.
ReasonCode = (
    CoveredReason
    | CoveredRequestAttributeReason
    | ConditionDroppedReason
    | NeutralisedObsoleteReason
    | NeutralisedUncoverableReason
    | NotCoverableReason
    | NoVerdictReason
    | PartiallyCoveredReason
    | SelectsNothingReason
    | ResolutionReason
    | UnprocessableReason
)


@dataclass(frozen=True)
class DataSourceVerdict:
    """How one Data Source came out, and everything a later stage renders or emits from it."""

    attribute_id: str
    data_source_index: int
    verdict: DataSourceOutcome
    reason: ReasonCode | None = None
    detail: str = ""
    # The replacement to emit and render, on a covered row - the harvested additions filling free
    # Scope slots (fan-out, host group, Primary Tag, and the key-only alternative). None on every
    # non-covered row.
    candidate: Candidate | None = None
    # The dormancy caveat riding a covered verdict, where some members were dormant.
    note: DataSourceNote | None = None
    dormant: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class RequestAttributeVerdict:
    """How one Request Attribute came out, rolled up from its Data Sources."""

    attribute_id: str
    verdict: RequestAttributeOutcome
    reason: ReasonCode | None = None
    detail: str = ""


# Which read or construction each of `090`'s free proofs stands on, in this layer's own vocabulary.
_COVERED_BY_PROOF = {
    MatchProof.FAN_OUT: CoveredReason.FAN_OUT_CONSTRUCTION,
    MatchProof.HOST_GROUP_MEMBERSHIP: CoveredReason.HOST_GROUP_MEMBERSHIP_READ,
    MatchProof.SERVICE_CLOSURE: CoveredReason.SERVICE_CLOSURE_READ,
}

# Which id a comparison against the Target Set reads off a verification row, by the set's shape:
# a process-group-shaped set is compared on process groups, a service-shaped one on services.
_ID_FIELD = {
    TargetShape.PROCESS_GROUP: "dt.entity.process_group",
    TargetShape.SERVICE: "dt.entity.service",
}

# The harvest drop reasons that mean the run *could not measure* an axis rather than refuting it: a
# read capped or a read that did not answer. A gap outranks a refutation, because a candidate a cap
# hid might have covered the set - so the action is re-run, never rework.
_UNMEASURED = frozenset(
    {HarvestDropReason.UNMEASURED_POPULATION, HarvestDropReason.UNREADABLE}
)


def decide_all(
    runner: QueryRunner,
    classifications: Sequence[AttributeClassification],
    resolutions: Sequence[Resolution],
    harvests: Sequence[Harvest],
    assessments: Sequence[CandidateAssessment],
    *,
    window: QueryWindow,
) -> tuple[tuple[DataSourceVerdict, ...], tuple[RequestAttributeVerdict, ...]]:
    """The verdict of every resolved Data Source, and the roll-up of every Request Attribute."""
    harvested = {(one.attribute_id, one.data_source_index): one for one in harvests}
    assessed = {(one.attribute_id, one.data_source_index): one for one in assessments}
    data_source_verdicts = (
        *(
            _decide_one(runner, resolution, harvested, assessed, window=window)
            for resolution in resolutions
        ),
        *_obsolete_verdicts(classifications),
    )
    return data_source_verdicts, _roll_up(data_source_verdicts)


def _obsolete_verdicts(
    classifications: Sequence[AttributeClassification],
) -> tuple[DataSourceVerdict, ...]:
    """The obsolete Data Sources of affected Request Attributes, Neutralised with no query spent.

    Decided at `050` from the capture location alone and carried through here: an obsolete source
    captures only onto external service calls Phase 3 removes, so it is skipped by resolution and
    never harvested. Only affected attributes are walked - an all-obsolete one is `obsolete` at the
    attribute level (`050`) and not this layer's to re-derive.
    """
    return tuple(
        DataSourceVerdict(
            one.id,
            source.index,
            DataSourceOutcome.NEUTRALISED_OBSOLETE,
            NeutralisedObsoleteReason.CAPTURES_ONLY_EXTERNAL_CALLS,
            detail="captures only onto external service calls, which Phase 3 removes",
        )
        for one in classifications
        if one.verdict is AttributeClass.AFFECTED
        for source in one.data_sources
        if source.obsolete
    )


def _decide_one(
    runner: QueryRunner,
    resolution: Resolution,
    harvested: dict[tuple[str, int], Harvest],
    assessed: dict[tuple[str, int], CandidateAssessment],
    *,
    window: QueryWindow,
) -> DataSourceVerdict:
    """One Data Source's verdict: the terminal one `070` already reached, or one this layer reaches.

    A resolution that carries an outcome is terminal - `empty-target-set` or `unprocessable`,
    decided at `050`/`070` - and is inherited unchanged. Everything else was harvested and assessed,
    so its verdict is dispatched off the assessment.
    """
    terminal = resolution.outcome
    if terminal is not None:
        return DataSourceVerdict(
            resolution.attribute_id,
            resolution.data_source_index,
            terminal,
            resolution.reason,
            detail=resolution.detail,
        )
    key = (resolution.attribute_id, resolution.data_source_index)
    return _decide(runner, assessed[key], resolution, harvested[key], window=window)


def _decide(
    runner: QueryRunner,
    assessment: CandidateAssessment,
    resolution: Resolution,
    harvest: Harvest,
    *,
    window: QueryWindow,
) -> DataSourceVerdict:
    """One Data Source's verdict, dispatched off what `090` assessed - no re-derivation."""
    candidate = assessment.candidate
    if candidate is not None and not candidate.needs_observation and candidate.proof is not None:
        # A free route: the fan-out construction, the host group membership read or the service
        # closure read already established the exact match, so it ships with no read of its own.
        return _one(
            assessment,
            DataSourceOutcome.COVERED,
            _COVERED_BY_PROOF[candidate.proof],
            candidate=candidate,
        )
    if assessment.condition_dropped:
        # The technology narrowed nothing, so its removal is exact: the replacement is the
        # Surviving Conditions alone, and no read is owed.
        return _one(
            assessment,
            DataSourceOutcome.CONDITION_DROPPED,
            ConditionDroppedReason.TECHNOLOGY_NARROWED_NOTHING,
        )
    if assessment.no_candidate:
        return _no_candidate(assessment, harvest)
    if candidate is not None and candidate.needs_observation:
        # The Primary Tag rung: the one route this layer spends a read to prove.
        return _verify(runner, assessment, candidate, resolution, harvest, window=window)
    return _one(assessment, DataSourceOutcome.NO_VERDICT)


def _no_candidate(assessment: CandidateAssessment, harvest: Harvest) -> DataSourceVerdict:
    """A Data Source `090` found no candidate for - which is not, on its own, the verdict.

    Two opposite actions hide behind the one boolean. A gap - the span side gated off run-wide
    because the tenant emits no key, every member dormant, or an axis a cap hid or a read that did
    not answer - established nothing, so it is no-verdict (re-run). Only where every axis was
    measured and none reproduced the Target Set is it neutralised-uncoverable (rework): a
    refutation the run actually made.
    """
    if harvest.primary_tags.gated is HarvestGate.NO_DISCOVERED_KEY:
        return _one(
            assessment,
            DataSourceOutcome.NO_VERDICT,
            NoVerdictReason.NO_PRIMARY_TAG_KEY_ON_THE_TENANT,
            detail="Primary Tag key discovery named no key, so the span side of the run was gated off",
        )
    if assessment.wholly_dormant:
        return _one(
            assessment,
            DataSourceOutcome.NO_VERDICT,
            NoVerdictReason.NO_SPANS_AND_NO_FREE_RUNG,
            detail="every member of the Target Set was dormant, so no live span could prove a candidate",
        )
    if any(drop.reason in _UNMEASURED for drop in assessment.drops):
        return _one(
            assessment,
            DataSourceOutcome.NO_VERDICT,
            NoVerdictReason.TRUNCATED_VERIFICATION_READ,
            detail="the read that would have harvested a candidate was capped or did not answer",
        )
    if any(
        drop.reason is HarvestDropReason.KEY_NOT_ON_ALL_TARGET_SET_SPANS
        for drop in assessment.drops
    ):
        return _one(
            assessment,
            DataSourceOutcome.NEUTRALISED_UNCOVERABLE,
            NeutralisedUncoverableReason.REFUTED_ON_EVERY_CANDIDATE,
            detail="a candidate key was genuinely null on a live entry-point span of the Target Set",
        )
    return _one(
        assessment,
        DataSourceOutcome.NEUTRALISED_UNCOVERABLE,
        NeutralisedUncoverableReason.NO_CANDIDATE_FITS_A_FREE_SLOT,
        detail="no harvested candidate fits a free Scope slot",
    )


def _verify(
    runner: QueryRunner,
    assessment: CandidateAssessment,
    candidate: Candidate,
    resolution: Resolution,
    harvest: Harvest,
    *,
    window: QueryWindow,
) -> DataSourceVerdict:
    """What the whole replacement Scope selects, asked of live spans, compared at two grains.

    One read of the conjunction - the harvested Primary Tag scoped by the replacement's own entity
    side - fanned out one read per value where the tag carries several. Its union is what must
    reproduce the Target Set: the same process groups (or services) it selected, and no fewer
    entry-point spans than the harvest measured on the original.
    """
    entity_side = _entity_side(candidate, harvest)
    if entity_side is not None and not entity_side:
        # A named entity side that selects nothing cannot reproduce a non-empty Target Set, and a
        # read scoped by nothing would scan the whole tenant - the empty-group guard refuses it. So
        # no read is spent: the replacement is not covered.
        return _one(assessment, DataSourceOutcome.NO_VERDICT)
    answers = [
        _answered(runner, verification_span_read(window, primary_tag=tag, process_groups=entity_side))
        for tag in candidate.primary_tag
    ]
    if not all(answer.complete for answer in answers):
        # A capped answer makes over-selection look exact and exact look short, so it is not a
        # comparison at all: inconclusive, and re-run rather than rework.
        return _one(
            assessment,
            DataSourceOutcome.NO_VERDICT,
            NoVerdictReason.TRUNCATED_VERIFICATION_READ,
            detail="the verification read came back capped, so what the replacement selects is unmeasured",
        )
    return _compare(assessment, candidate, resolution, harvest, answers)


def _compare(
    assessment: CandidateAssessment,
    candidate: Candidate,
    resolution: Resolution,
    harvest: Harvest,
    answers: Sequence[DqlAnswer],
) -> DataSourceVerdict:
    """The one comparison, at two grains, over a complete verification answer.

    Entity grain first - the process groups (or services) the replacement selected against the
    Target Set - then the span grain, because a Primary Tag is compared per entry point and can lose
    spans while keeping every process group.
    """
    id_field = _ID_FIELD[resolution.shape]
    selected = {row[id_field] for answer in answers for row in answer.records}
    target = set(resolution.target_set)
    # A dormant member produces no span, so verification cannot see it. The comparison is against
    # the live members; the dormant ones are covered by the caveat, never counted a shortfall.
    live = target - set(assessment.dormant)
    spans = sum(int(row["span_count"]) for answer in answers for row in answer.records)
    over = selected - target
    if over:
        # A candidate reaching entities the original Scope did not. There is no negation operator
        # in the Scope, so the over-selection cannot be narrowed: a refutation, not a re-run.
        return _one(
            assessment,
            DataSourceOutcome.NEUTRALISED_UNCOVERABLE,
            NeutralisedUncoverableReason.EVERY_CANDIDATE_OVER_SELECTS,
            detail=f"the replacement also selects {', '.join(sorted(over))}, outside the Target Set",
        )
    missing = live - selected
    if missing:
        # Fewer process groups than the live Target Set. Every kept candidate's value was harvested
        # from every live member, so this cannot happen without a cap: it points to a migrator
        # defect or an entity that changed between the reads, not to a fact about the Data Source.
        # The verdict is withheld rather than a shortfall asserted.
        return _one(
            assessment,
            DataSourceOutcome.NO_VERDICT,
            NoVerdictReason.REPLACEMENT_UNDER_SELECTS,
            detail=(
                f"the replacement did not reach {', '.join(sorted(missing))}; absent a cap this "
                "under-selection should not happen and points to a migrator defect"
            ),
        )
    if harvest.target_spans is None:
        # The harvest never measured the target span count, so the span-grain comparison cannot be
        # made - and an unmeasured one is never one the replacement passes.
        return _one(
            assessment,
            DataSourceOutcome.NO_VERDICT,
            NoVerdictReason.TRUNCATED_VERIFICATION_READ,
            detail="the harvest did not measure the Target Set's span count, so the grains do not compare",
        )
    if spans < harvest.target_spans:
        # Every process group kept but fewer entry-point spans: a Primary Tag is compared per entry
        # point, so the tag covers only part of the population. A measured refutation, reported
        # with both counts.
        return _one(
            assessment,
            DataSourceOutcome.NEUTRALISED_UNCOVERABLE,
            NeutralisedUncoverableReason.REFUTED_ON_EVERY_CANDIDATE,
            detail=(
                f"the replacement covers {spans} entry-point spans against the Target Set's "
                f"{harvest.target_spans}"
            ),
        )
    return _one(
        assessment,
        DataSourceOutcome.COVERED,
        CoveredReason.VERIFICATION_READ,
        candidate=candidate,
    )


def _entity_side(candidate: Candidate, harvest: Harvest) -> list[str] | None:
    """The process groups the replacement's own entity side selects, to scope the span read by.

    The host group's full membership where the replacement carries one - the read `080` already
    spent - and `None` where it carries no entity-side condition at all, which is an unbounded span
    read the sibling accepts rather than naming every process group. A named host group whose
    membership is empty or was never read returns an empty list, kept distinct from `None`: the
    caller spends no read for it rather than turning it into an unbounded one.
    """
    if candidate.host_group is None:
        return None
    membership = harvest.host_groups.membership or {}
    return list(membership.get(candidate.host_group, ()))


def _answered(runner: QueryRunner, read: Read) -> DqlAnswer:
    """One read's answer, assembled from the one answer per query it takes."""
    return read.answered([runner.answer(query) for query in read.queries])


def _one(
    assessment: CandidateAssessment,
    verdict: DataSourceOutcome,
    reason: ReasonCode | None = None,
    *,
    detail: str = "",
    candidate: Candidate | None = None,
) -> DataSourceVerdict:
    """One verdict row, carrying its Data Source's identity and the dormancy caveat off the assessment."""
    return DataSourceVerdict(
        assessment.attribute_id,
        assessment.data_source_index,
        verdict,
        reason,
        detail=detail,
        candidate=candidate,
        note=assessment.note,
        dormant=assessment.dormant,
    )


# The Data Source outcomes that count as covered when a Request Attribute rolls up: a covered
# replacement, and a Data Source whose only Deprecated Condition was a technology now dropped.
_COVERED_LIKE = frozenset(
    {DataSourceOutcome.COVERED, DataSourceOutcome.CONDITION_DROPPED}
)
# The Data Source outcomes that are a Neutralisation - the run established the Data Source cannot be
# covered, so it ships disabled. `no-verdict` is deliberately not here: it is unmeasured, not
# uncoverable, which is why it outranks the covered/Neutralised mix in the roll-up.
_NEUTRALISED = frozenset(
    {DataSourceOutcome.NEUTRALISED_UNCOVERABLE, DataSourceOutcome.NEUTRALISED_OBSOLETE}
)


def _roll_up(
    data_source_verdicts: Sequence[DataSourceVerdict],
) -> tuple[RequestAttributeVerdict, ...]:
    """Each Request Attribute's verdict, rolled up from its Data Sources in precedence order."""
    by_attribute: dict[str, list[DataSourceVerdict]] = {}
    for one in data_source_verdicts:
        by_attribute.setdefault(one.attribute_id, []).append(one)
    return tuple(
        _roll_up_one(attribute_id, rows) for attribute_id, rows in by_attribute.items()
    )


def _roll_up_one(
    attribute_id: str, rows: Sequence[DataSourceVerdict]
) -> RequestAttributeVerdict:
    """One Request Attribute's verdict, in precedence order because more than one rung can apply.

    `no-verdict` sits above the covered/Neutralised mix on purpose: a body shipped with an
    unmeasured Data Source disabled would Neutralise something the run never established was
    uncoverable, which is the harm `no-verdict` exists to prevent. Re-run, then decide.
    """
    verdicts = [one.verdict for one in rows]
    if DataSourceOutcome.UNPROCESSABLE in verdicts:
        failed = next(one for one in rows if one.verdict is DataSourceOutcome.UNPROCESSABLE)
        return RequestAttributeVerdict(
            attribute_id, RequestAttributeOutcome.UNPROCESSABLE, failed.reason, failed.detail
        )
    if all(one is DataSourceOutcome.EMPTY_TARGET_SET for one in verdicts):
        return RequestAttributeVerdict(
            attribute_id, RequestAttributeOutcome.SELECTS_NOTHING, _selects_nothing_reason(rows)
        )
    if DataSourceOutcome.NO_VERDICT in verdicts:
        return RequestAttributeVerdict(
            attribute_id,
            RequestAttributeOutcome.NO_VERDICT,
            NoVerdictReason.SOME_DATA_SOURCE_UNMEASURED,
        )
    covered = any(one in _COVERED_LIKE for one in verdicts)
    neutralised = any(one in _NEUTRALISED for one in verdicts)
    if covered and neutralised:
        return RequestAttributeVerdict(
            attribute_id,
            RequestAttributeOutcome.PARTIALLY_COVERED,
            PartiallyCoveredReason.SOME_DATA_SOURCES_NEUTRALISED,
        )
    if covered:
        return RequestAttributeVerdict(
            attribute_id,
            RequestAttributeOutcome.COVERED,
            CoveredRequestAttributeReason.EVERY_DATA_SOURCE_COVERED,
        )
    return RequestAttributeVerdict(
        attribute_id,
        RequestAttributeOutcome.NOT_COVERABLE,
        NotCoverableReason.EVERY_DATA_SOURCE_NEUTRALISED,
    )


def _selects_nothing_reason(
    rows: Sequence[DataSourceVerdict],
) -> SelectsNothingReason:
    """Which empty every Data Source hit: the tag matched nothing, or a Surviving Condition did.

    Two opposite instructions to the reader - the tag has moved on, versus the Scope selects nothing
    that is there - so they stay two codes even rolled up. Where the Data Sources disagree, the
    Surviving-Condition empty is the wider statement and wins.
    """
    if all(one.reason is ResolutionReason.TAG_MATCHED_NOTHING for one in rows):
        return SelectsNothingReason.EVERY_TAG_MATCHED_NOTHING
    return SelectsNothingReason.EVERY_SCOPE_SELECTS_NOTHING
