"""Everything needed to start looking for a replacement, gathered and typed.

Not the choice of candidate and not the proof of one: what is assembled here is material, with
the read it came from recorded beside it, so a later stage knows what it may claim from what.

Two reads are spent, and each is spent only where it can decide something: the target-set-scoped
span read where a span-side route is still open, and the service closure read where the target set
is service-shaped. Everything else costs no transport call - the reads carrying it are the reads
target set resolution already asked, the run's runner is the caching decorator, and the builders
fix their own stage order, so a re-rendered read is answered from disk. The closure read is the one
exception, and a deliberate one: it carries no technology, so resolution's technology-narrowed read
cannot answer it.

Both are guarded, and each guard is around one read: a refusal costs the axis that read would have
filled and never the run. A run against a tenant holding hundreds of affected request attributes is
worthless if the first read it cannot make sense of ends it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..attributes.classification import AttributeClassification, Scope
from ..clients.transports import DqlAnswer, QueryRunner, RateLimited
from ..dql.queries import (
    ProbeReading,
    Read,
    TargetShape,
    primary_tag_key_discovery,
    primary_tag_keys_of,
    primary_tag_probe_of,
    primary_tag_probe_read,
    service_closure_read,
    span_read,
)
from ..dql.windowing import QueryWindow
from ..reporting.outcomes import HarvestDropReason, HarvestGate, HarvestProvenance
from .resolution import FAN_OUT_CAP, Resolution, service_rows


@dataclass(frozen=True)
class ProcessGroups:
    """The process group axis: exact wherever it is available, and never observed."""

    ids: tuple[str, ...] = ()
    provenance: HarvestProvenance = HarvestProvenance.TAGGED_PROCESS_GROUP_READ


@dataclass(frozen=True)
class HostGroups:
    """The host group axis, and which side of it a read actually answered.

    Absent membership is `None` and never an empty mapping: *not asked* and *the host group holds
    nothing* mean opposite things, and target set resolution spends a read to keep them apart.
    """

    of_member: Mapping[str, str | None] = field(default_factory=dict)
    names: Mapping[str, str] = field(default_factory=dict)
    membership: Mapping[str, tuple[str, ...]] | None = None
    # A service carries no host group relationship at all, so a service-shaped target set cannot
    # supply this axis and must not appear to: unavailable, rather than empty.
    unavailable: bool = False
    provenance: HarvestProvenance = HarvestProvenance.TAGGED_PROCESS_GROUP_READ
    # Set only where the membership read was issued, which is the read that carries that half.
    membership_provenance: HarvestProvenance | None = None


@dataclass(frozen=True)
class ServiceClosure:
    """Service-shaped only: every service of every process group the target set touches.

    The material a later stage decides closure from, and the reason it costs a read of its own:
    the question is whether *every* service of every touched process group carries the
    technology, so the half of the population that answers it is the half resolution's
    technology-narrowed read throws away.

    Everything on it came off that one read, which is what makes one `provenance` honest. The
    process groups it is bounded by are **not** here: they came off resolution's read and they are
    the process group axis of a service-shaped set, carried once by `ProcessGroups` with the
    provenance of the read they came off. Two copies of one fact are free to drift.
    """

    services: tuple[str, ...] = ()
    provenance: HarvestProvenance = HarvestProvenance.SERVICE_CLOSURE_READ
    # Why the axis yields no closure verdict, where it yields none: the read did not answer, or it
    # answered and was capped. Three states and not two, because a read of its own is a read that
    # can fail on its own - and every service a cap hides makes the set look *more* closed than it
    # is, so a short answer is recorded rather than read as one and the closure gate refuses on it.
    dropped: HarvestDropReason | None = None
    detail: str = ""


@dataclass(frozen=True)
class PrimaryTagKey:
    """What one discovered key carried across the target set's entry-point spans.

    The material and the verdict on it travel together: a key that cannot stand as a candidate is
    still material, and the code saying why it cannot is the whole of what a later stage needs.
    """

    key: str
    # The values the harvest enumerated, set only for a null-free key within the cap - the keys the
    # probe left standing that a `key:value` form can enumerate. Empty on a key-only (> cap) key,
    # which is never grouped into the harvest, and on a dropped one.
    values: tuple[str, ...] = ()
    # Why this key yields no candidate, where it yields none. Absent means it is one.
    dropped: HarvestDropReason | None = None
    detail: str = ""
    # Whether the key arrived as something a valued condition can never match - an array or a
    # number - on any one of the rows. Judged over every enumerated row rather than the first
    # carrying the key, because a key can be scalar on one and an array on the next.
    non_string: bool = False
    # The two probe figures. `present` is the entry-point spans carrying the key (`isNotNull`), of
    # the shared `Harvest.target_spans` total: `present == total` is the null gate, genuine-null
    # only, an empty value being presence. `distinct` is its approximate value cardinality, which
    # sorts the null-free survivors into `key:value` (<= cap) and key-only (> cap).
    present: int = 0
    distinct: int = 0


@dataclass(frozen=True)
class PrimaryTags:
    """The primary tag axis, which is the only one no entity read can ever supply."""

    keys: tuple[PrimaryTagKey, ...] = ()
    # Why no read was spent, where none was. Absent means the axis was harvested.
    gated: HarvestGate | None = None
    # Why the whole axis yielded nothing where the read itself failed it. One drop for the axis
    # rather than one per key: the read says nothing about any of them, and a key-shaped drop
    # would read as that key being absent - which is exactly what was not established.
    dropped: HarvestDropReason | None = None
    detail: str = ""
    provenance: HarvestProvenance = HarvestProvenance.HARVEST_SPAN_READ


@dataclass(frozen=True)
class Harvest:
    """What one data source's target set yielded, per axis.

    One field per axis plus the two run-level figures, and over pylint's default by one: this is
    the row the next stage decides from, so collapsing two of its fields to satisfy a threshold
    would make it say less than it is asked to say.
    """

    # pylint: disable=too-many-instance-attributes

    attribute_id: str
    data_source_index: int
    shape: TargetShape
    process_groups: ProcessGroups = ProcessGroups()
    host_groups: HostGroups = HostGroups()
    service_closure: ServiceClosure = ServiceClosure()
    primary_tags: PrimaryTags = PrimaryTags()
    # The members of the target set that produced no entry-point span in the window. `None`
    # where the harvest read was never spent: dormancy is a property of that read's own rows, so
    # a gated data source has not observed it rather than found none - and recording every member
    # of a skipped set as dormant would say the opposite of what was measured.
    dormant: tuple[str, ...] | None = None
    # The entry-point spans the target set carries, as the row-wise sum over the harvest rows.
    # Unknown rather than zero wherever that read was not spent or did not answer in full: a
    # replacement compared against a population nobody measured is compared against nothing.
    target_spans: int | None = None


def harvest_all(
    runner: QueryRunner,
    classifications: Sequence[AttributeClassification],
    resolutions: Sequence[Resolution],
    *,
    window: QueryWindow,
) -> tuple[Harvest, ...]:
    """The material every data source a replacement is still to be found for yields.

    Each resolution is paired back to the scope it was resolved from, which is what the entity
    reads are re-rendered from. Pairing rather than widening the resolution: a resolution is the
    contract row, and what a harvest needs off a scope is needed here and nowhere later.
    """
    scopes = {
        (one.id, source.index): source.scope
        for one in classifications
        for source in one.data_sources
    }
    discovered = _DiscoveredKeys(runner)
    return tuple(
        _harvested(
            runner,
            one,
            scopes[(one.attribute_id, one.data_source_index)],
            discovered,
            window=window,
        )
        # A data source resolution left terminal is never harvested for. There is no target set
        # to read material off, and re-rendering a read for one would ask for a scope bounded by
        # an empty set - which is refused rather than asked.
        for one in resolutions
        if one.outcome is None
    )


def _harvested(
    runner: QueryRunner,
    resolved: Resolution,
    scope: Scope,
    discovered: _DiscoveredKeys,
    *,
    window: QueryWindow,
) -> Harvest:
    """One data source's material, axis by axis.

    The touched process groups are derived once and handed to both axes that are about them: the
    process group axis of a service-shaped set *is* them, and the closure read is bounded by them.
    Derived here rather than read back off the closure value, so a closure read that did not
    answer cannot empty an axis it never spoke for.
    """
    touched = _touched(service_rows(runner, scope, window=window), resolved.target_set)
    closure = _closure(runner, touched, window=window)
    primary_tags, target_spans, dormant = _primary_tag_material(
        runner, resolved, closure, touched, discovered, window=window
    )
    return Harvest(
        resolved.attribute_id,
        resolved.data_source_index,
        resolved.shape,
        process_groups=_process_groups(resolved, touched),
        host_groups=_host_groups(resolved),
        service_closure=closure,
        primary_tags=primary_tags,
        dormant=dormant,
        target_spans=target_spans,
    )


def _process_groups(resolved: Resolution, touched: tuple[str, ...]) -> ProcessGroups:
    """The process group axis, off whichever read the target set's own shape puts it on.

    Always exact and never observed: a process-group-shaped set is its own answer, and a
    service-shaped one runs on the process groups its services project - a relationship that is
    single-valued on the service side and so cannot be capped.
    """
    if resolved.shape is TargetShape.PROCESS_GROUP:
        return ProcessGroups(resolved.target_set)
    return ProcessGroups(touched, HarvestProvenance.SERVICE_READ)


def _host_groups(resolved: Resolution) -> HostGroups:
    """The host group axis as target set resolution left it, with each side's read named.

    Both halves ride on reads already asked: the host group of each member and its looked-up name
    on the tagged read, the full membership on the read issued only where that rung is reachable.
    """
    if resolved.shape is TargetShape.SERVICE:
        return HostGroups(unavailable=True)
    found = resolved.host_groups
    return HostGroups(
        found.of_member,
        found.names,
        found.members,
        membership_provenance=(
            None if found.members is None else HarvestProvenance.HOST_GROUP_MEMBERSHIP_READ
        ),
    )


def _closure(
    runner: QueryRunner, touched: tuple[str, ...], *, window: QueryWindow
) -> ServiceClosure:
    """Every service of the process groups the target set touches, off the read that says so.

    Two reads, and the split is the whole point. Touched came off resolution's own read - free,
    because that read is re-rendered through the caching runner - and is decided by the target
    services rather than by that read's scoping, which reaches wider than the technology does.
    The services of those process groups then cost a read that carries no technology, because the
    ones *not* carrying it are what a closure verdict is about.

    An empty touched set asks nothing: the builder refuses a read bounded by nothing, and there is
    no closure to be had where the target set is not service-shaped.

    One data source's axis is all a refused read costs. The guard is around that read and nothing
    else: resolution's own reads are re-rendered above this and a failure there is that layer's to
    contain, so a wider one would take it on by accident and record it as an unreadable *closure*.
    """
    if not touched:
        return ServiceClosure()
    try:
        answer = _answered(runner, service_closure_read(window, process_groups=touched))
    except RateLimited:
        # Not this data source's axis to lose. A rate limit says nothing about what its touched
        # process groups hold, so dropping an axis over one would hand out a run that looks
        # measured.
        raise
    except Exception as failure:  # pylint: disable=broad-exception-caught
        # The family and not one class: a timeout, a transport error, a non-200 and a read
        # assembled from too few answers all say the same thing about this axis.
        return ServiceClosure(dropped=HarvestDropReason.UNREADABLE, detail=str(failure))
    within = set(touched)
    held = _ordered(
        str(row["id"])
        for row in answer.records
        if "id" in row and _process_group_of(row) in within
    )
    if not answer.complete:
        # The short answer is kept rather than emptied: a cap did see the services it answered
        # with, and what it hides is services that would have *refuted* closure. So the code is
        # what the gate refuses on, and the rows it did answer with are still material.
        return ServiceClosure(
            held,
            dropped=HarvestDropReason.UNMEASURED_POPULATION,
            detail=(
                f"the closure read answered with {len(answer.records)} row(s) "
                "and was capped there"
            ),
        )
    return ServiceClosure(held)


def _touched(
    services: Sequence[Mapping[str, Any]], target_set: Sequence[str]
) -> tuple[str, ...]:
    """The process groups the target set's own services run on, in the order the read named them.

    Single-valued on the service side, so this relationship cannot be capped - which is what
    makes these process groups an exact bound rather than a partial one.
    """
    targeted = set(target_set)
    return _ordered(
        _process_group_of(row) for row in services if str(row.get("id")) in targeted
    )


def _process_group_of(row: Mapping[str, Any]) -> str | None:
    rendered = row.get("process_group")
    return rendered if isinstance(rendered, str) else None


def _ordered(found: Iterable[str | None]) -> tuple[str, ...]:
    """What was found, deduplicated and in the order the read answered with it."""
    return tuple(dict.fromkeys(one for one in found if one is not None))


def _primary_tag_material(
    runner: QueryRunner,
    resolved: Resolution,
    closure: ServiceClosure,
    touched: tuple[str, ...],
    discovered: _DiscoveredKeys,
    *,
    window: QueryWindow,
) -> tuple[PrimaryTags, int | None, tuple[str, ...] | None]:
    """The one axis that costs reads: the probe, then a harvest pruned by what it measured.

    Two reads replace the one that used to cap. The probe measures null-coverage and value
    cardinality per key over the target-set-scoped entry-point spans, and cannot cap on rows. The
    harvest then groups **only** by the keys the probe left null-free and within the cap - so a
    single very-high-cardinality key can no longer overflow the Primary Tag axis - and still by
    Target Set member, so the dormant list survives.

    Returns the axis, the target set's entry-point span count (the probe's exact `total`), and the
    dormant members - the last two `None` wherever a gate or a read failure left the span side
    unmeasured. The gate is applied before any read is asked, so a run whose every data source is
    covered by a free rung asks nothing at all.
    """
    gate = _gate(resolved, closure, touched)
    if gate is not None:
        return PrimaryTags(gated=gate), None, None
    named = discovered.named()
    if named is None:
        return (
            PrimaryTags(
                dropped=HarvestDropReason.UNREADABLE,
                detail="the primary tag key discovery read did not answer",
            ),
            None,
            None,
        )
    if not named:
        return PrimaryTags(gated=HarvestGate.NO_DISCOVERED_KEY), None, None
    try:
        probe = primary_tag_probe_of(
            _answered(
                runner,
                primary_tag_probe_read(
                    window,
                    shape=resolved.shape,
                    targets=resolved.target_set,
                    primary_tag_keys=named,
                ),
            ),
            named,
        )
    except RateLimited:
        # Not this data source's axis to lose. A rate limit says nothing about what its target
        # set carries, so dropping an axis over one would hand out a run that looks measured.
        raise
    except Exception as failure:  # pylint: disable=broad-exception-caught
        return PrimaryTags(dropped=HarvestDropReason.UNREADABLE, detail=str(failure)), None, None
    return _pruned_harvest(runner, resolved, named, probe, window=window)


def _pruned_harvest(
    runner: QueryRunner,
    resolved: Resolution,
    named: Sequence[str],
    probe: ProbeReading,
    *,
    window: QueryWindow,
) -> tuple[PrimaryTags, int | None, tuple[str, ...] | None]:
    """The harvest grouped by the probe's survivors, and the axis it assembles from both reads.

    A key null-free by the probe (`present == total`) that fits the cap is grouped in and its values
    enumerated; a null-free key over the cap is a key-only candidate settled from the probe alone and
    never grouped in, which is what stops it re-exploding the read. A nulled key is dropped on the
    probe's `present < total` with no harvest row needed at all. The harvest still runs whenever any
    null-free key survives - including a key-only-only data source with nothing to enumerate - so
    `Harvest.dormant` is populated for `179`'s caveat.
    """
    null_free = [key for key in named if probe.present.get(key, 0) == probe.total]
    if not null_free:
        # Every discovered key carries a genuine null: no Primary Tag candidate stands in any form,
        # so no harvest row could add anything and none is read. The dropped keys still carry their
        # probe figures for the report.
        keys = tuple(_key_from_probe(key, probe, {}) for key in named)
        return PrimaryTags(keys), probe.total, ()
    pruned = tuple(key for key in null_free if probe.distinct.get(key, 0) <= FAN_OUT_CAP)
    try:
        answer = _answered(
            runner,
            span_read(
                window,
                shape=resolved.shape,
                targets=resolved.target_set,
                primary_tag_keys=pruned,
            ),
        )
    except RateLimited:
        raise
    except Exception as failure:  # pylint: disable=broad-exception-caught
        return PrimaryTags(dropped=HarvestDropReason.UNREADABLE, detail=str(failure)), None, None
    if not answer.complete:
        # The residual cap: the pruned keys cannot overflow, but a Target Set whose own member
        # enumeration exceeds the record cap still can. One drop for the axis, never read as a value
        # being absent - the population the missing rows would have spoken for is unmeasured.
        return (
            PrimaryTags(
                dropped=HarvestDropReason.UNMEASURED_POPULATION,
                detail=(
                    f"the harvest read answered with {len(answer.records)} row(s) "
                    "and was capped there"
                ),
            ),
            None,
            None,
        )
    rows = _of_target_set(answer.records, resolved)
    enumerated = _enumerated_values(rows, pruned, resolved)
    keys = tuple(_key_from_probe(key, probe, enumerated) for key in named)
    return PrimaryTags(keys), probe.total, _dormant(rows, resolved)


def _of_target_set(
    rows: Sequence[Mapping[str, Any]], resolved: Resolution
) -> tuple[Mapping[str, Any], ...]:
    """The rows standing for a member of the target set, read off the field its shape names.

    The read is filtered on the target set already; the rows are narrowed again here for the
    reason the tag filter narrows nothing on the entity side - what a harvest claims rests on the
    comparison it made, never on a filter having been rendered.
    """
    targeted = set(resolved.target_set)
    return tuple(row for row in rows if _member_of(row, resolved) in targeted)


def _member_of(row: Mapping[str, Any], resolved: Resolution) -> str | None:
    """Which member of the target set one row stands for, in the set's own shape.

    The grouping never follows the shape - the answer says which process group *and* which
    service a count belongs to whichever set was asked for - so the shape decides which of the
    two fields is the member here.
    """
    rendered = row.get(resolved.shape.value)
    return rendered if isinstance(rendered, str) else None


def _key_from_probe(
    key: str,
    probe: ProbeReading,
    enumerated: Mapping[str, tuple[tuple[str, ...], bool]],
) -> PrimaryTagKey:
    """One discovered key as the probe (and, for a survivor, the harvest) measured it.

    The probe's `present == total` is the whole verdict: a genuine null on any existing span
    (`present < total`) is `KEY_NOT_ON_ALL_TARGET_SET_SPANS`, an empty value being presence rather
    than a drop. A null-free key keeps its enumerated values where the harvest grouped it in
    (within the cap); over the cap it carries none, which is a key-only candidate settled from the
    probe alone.
    """
    present = probe.present.get(key, 0)
    distinct = probe.distinct.get(key, 0)
    if present < probe.total:
        return PrimaryTagKey(
            key,
            dropped=HarvestDropReason.KEY_NOT_ON_ALL_TARGET_SET_SPANS,
            detail=(
                f"{key!r} is present on {present} of the target set's {probe.total} "
                "entry-point spans"
            ),
            present=present,
            distinct=distinct,
        )
    values, non_string = enumerated.get(key, ((), False))
    return PrimaryTagKey(
        key, values=values, non_string=non_string, present=present, distinct=distinct
    )


def _enumerated_values(
    rows: Sequence[Mapping[str, Any]], pruned: Sequence[str], resolved: Resolution
) -> dict[str, tuple[tuple[str, ...], bool]]:
    """The values and the non-string flag of each key the harvest grouped in.

    The two things only a value grouping can answer, and the harvest's whole remaining job on the
    key material. An empty string is an ordinary matchable value and is enumerated; an array is
    non-string and is flagged rather than enumerated, since no valued condition can match it. A
    genuine null (`_of_member`-absent on a row) is neither - the probe already gated on it.
    """
    del resolved  # rows are already narrowed to the target set by `_of_target_set`.
    result: dict[str, tuple[tuple[str, ...], bool]] = {}
    for key in pruned:
        values: list[str] = []
        non_string = False
        for row in rows:
            value = row.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                values.append(value)
            else:
                non_string = True
        result[key] = (tuple(sorted(set(values))), non_string)
    return result


def _measured(rows: Sequence[Mapping[str, Any]], resolved: Resolution) -> frozenset[str]:
    """The members of the target set the harvest read actually saw a span of."""
    return frozenset(
        member for row in rows if (member := _member_of(row, resolved)) is not None
    )


def _gate(
    resolved: Resolution, closure: ServiceClosure, touched: tuple[str, ...]
) -> HarvestGate | None:
    """Which free rung already covers this data source, where one does.

    Knowledge about determination's rungs, living here deliberately: the alternative is a lazy
    harvest whose span material is pulled by the layer whose whole contract is that it issues no
    read. The gate decides no outcome - every one of these is still assigned there - it decides
    only whether a read is worth paying for.
    """
    if resolved.shape is TargetShape.PROCESS_GROUP and len(resolved.target_set) <= FAN_OUT_CAP:
        return HarvestGate.COVERED_BY_FAN_OUT
    if _is_a_whole_host_group(resolved):
        return HarvestGate.COVERED_BY_HOST_GROUP
    if _is_closed(resolved, closure):
        return HarvestGate.TECHNOLOGY_NARROWS_NOTHING
    if _service_closure_covers(resolved, closure, touched):
        return HarvestGate.COVERED_BY_SERVICE_CLOSURE
    if resolved.superset:
        return HarvestGate.TAG_SLOT_TAKEN
    return None


def _is_closed(resolved: Resolution, closure: ServiceClosure) -> bool:
    """Whether every service of every touched process group is in the target set.

    Where it is, the technology condition was narrowing nothing: it is removed exactly. But closure
    licenses removing the *technology* only, so it settles the data source - and suppresses the
    primary tag harvest - only when nothing else is left to replace: no deprecated `tagOfProcessGroup`
    remains, and a Surviving Condition reproduces the target set. Where a deprecated tag remains or
    no Surviving Condition does, the tag slot is free and the primary tag harvest must still run.

    A dropped closure axis never says so. Every service a cap hid is one that would have refuted
    closure, so reading a short answer as closed drops the technology and ships a data source
    capturing more than the original - and that route reaches no observation, so nothing later
    catches it. Refusal instead costs coverage, which is the direction this project takes.
    """
    if resolved.shape is not TargetShape.SERVICE or not closure.services:
        return False
    if closure.dropped is not None:
        return False
    if resolved.carries_deprecated_tag or not resolved.has_surviving_condition:
        return False
    return set(closure.services) <= set(resolved.target_set)


def _service_closure_covers(
    resolved: Resolution, closure: ServiceClosure, touched: tuple[str, ...]
) -> bool:
    """Whether a constructed `SPECIFIC_PG` per touched process group reproduces the set exactly.

    Reached only after `_is_closed` declined, so this is the case it routes away - a deprecated
    `tagOfProcessGroup` (`175`) or no Surviving Condition - where the closure read nonetheless proves
    the touched process groups hold exactly the Target Set. Equality, not the edit-path's subset: the
    constructed replacement selects every service the touched process groups hold, so an over-select
    must rule it out, and the by-construction `target ⊆ closure` makes that check `closure == target`.

    Within the fan-out cap: over it the replacement would need more Data Sources than a human will
    review, so the axis is not taken and the span read is spent so the Primary Tag can be tried
    instead. A dropped or capped closure never says so - every service a cap hid is one that would
    have refuted equality. Where it holds, determination constructs the `SPECIFIC_PG` fan-out and the
    Primary Tag span read is skipped.
    """
    if resolved.shape is not TargetShape.SERVICE or not closure.services:
        return False
    if closure.dropped is not None or len(touched) > FAN_OUT_CAP:
        return False
    return set(closure.services) == set(resolved.target_set)


def _is_a_whole_host_group(resolved: Resolution) -> bool:
    """Whether the target set is exactly some host group's membership, read and compared.

    Only the membership read can say so: the tagged read returns tagged process groups alone, so
    an untagged member of the same host group is invisible to it. Where that read was not issued
    the comparison is not available at all, which is why an absent membership is `None` here and
    never an empty mapping.
    """
    members = resolved.host_groups.members
    if members is None:
        return False
    return any(set(held) == set(resolved.target_set) for held in members.values())


def _dormant(rows: Sequence[Mapping[str, Any]], resolved: Resolution) -> tuple[str, ...]:
    """The members the harvest read saw no entry-point span of.

    The population is the entry-point spans the read selects, which is the population the runtime
    evaluates a primary tag over - not spans at large. A dormant member makes the primary tag
    route unverifiable and changes no outcome of its own: it is covered by its own id whether or
    not traffic returns.
    """
    measured = _measured(rows, resolved)
    return tuple(one for one in resolved.target_set if one not in measured)


class _DiscoveredKeys:
    """Which primary tag keys the tenant emits on spans at all, asked at most once in a run.

    Asked lazily, and only where some data source could still spend a span read: the answer gates
    the whole span side of the run off, and a run whose every data source is covered by a free
    rung has no use for it.
    """

    def __init__(self, runner: QueryRunner) -> None:
        self._runner = runner
        self._named: tuple[str, ...] | None = None
        self._asked = False

    def named(self) -> tuple[str, ...] | None:
        """The keys the discovery read named, or `None` where that read did not answer."""
        if not self._asked:
            self._asked = True
            self._named = self._read()
        return self._named

    def _read(self) -> tuple[str, ...] | None:
        read = primary_tag_key_discovery()
        try:
            return primary_tag_keys_of(_answered(self._runner, read))
        except RateLimited:
            # The run's failure and not this question's: a rate limit says nothing about which
            # keys the tenant emits, and a run that carried on would look measured.
            raise
        except Exception:  # pylint: disable=broad-exception-caught
            # Best-effort on purpose: the primary tag axis is one of four, and a tenant that
            # cannot answer this question should still have the other three harvested.
            return None


def _answered(runner: QueryRunner, read: Read) -> DqlAnswer:
    """One read's answer, however many queries it took to ask it."""
    return read.answered([runner.answer(query) for query in read.queries])
