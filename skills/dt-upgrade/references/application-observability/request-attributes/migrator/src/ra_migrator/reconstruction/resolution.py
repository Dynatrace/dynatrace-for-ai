"""What each affected data source's scope selects today - the thing a replacement must reproduce.

Every read is built from one data source's own conditions. Sharing between scopes is the cache's
job and never a wider query's: two scopes asking the same question render the same text and cost
one read.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from ..attributes.classification import (
    AttributeClassification,
    DataSourceClassification,
    Scope,
)
from ..attributes.tags import Tag, parse_tag
from ..attributes.technologies import spellings_of
from ..clients.transports import DqlAnswer, QueryRunner, RateLimited
from ..dql.queries import Read, TargetShape, process_group_read, service_read
from ..dql.windowing import QueryWindow
from ..reporting.outcomes import AttributeClass, DataSourceOutcome, ResolutionReason


class _Unresolvable(Exception):
    """One data source this layer could not answer for. Costs one row, never the run."""

    def __init__(self, reason: ResolutionReason, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class HostGroups:
    """What this resolution learned about host groups, as the harvest reads it.

    One value rather than three loose maps, because the three answer one question together: the
    host group rung is only available when the target set is *exactly* some host group's
    membership, and telling "exactly these" from "these and more" needs all three.
    """

    # Which host group each member of the target set belongs to. Absent for a service-shaped
    # set: a service carries no host group relationship at all.
    of_member: Mapping[str, str | None] = field(default_factory=dict)
    # The names looked up for display. Filtering is always on the identifier, because that is
    # what the condition stores; a name is display material and never a filter.
    names: Mapping[str, str] = field(default_factory=dict)
    # Every process group of each touched host group, where that read was issued. Absent is
    # `None` and never an empty mapping: a host group with no tagged member and a host group
    # that is gone mean opposite things, and only the read can tell them apart.
    members: Mapping[str, tuple[str, ...]] | None = None


@dataclass(frozen=True)
class Resolution:
    """One data source's target set, and how the run arrived at it.

    One field over pylint's default, and left that way: this is a row in the contract a
    consuming skill classifies on, so its fields are the ones the contract has. Collapsing two
    of them to satisfy a threshold would make the row say less than it is asked to say.
    """

    # pylint: disable=too-many-instance-attributes

    attribute_id: str
    data_source_index: int
    shape: TargetShape
    target_set: tuple[str, ...] = ()
    host_groups: HostGroups = field(default_factory=HostGroups)
    # A surviving primary tag is span-side, so no entity read can apply it and the set resolved
    # here is wider than the one the scope selects. The error direction is refusal.
    superset: bool = False
    # Whether the scope still carries a deprecated `tagOfProcessGroup` - a second Deprecated
    # Condition Phase 3 removes beside the technology. A closed service set does not settle while
    # one remains: closure licenses removing the *technology*, and the tag still needs replacing.
    carries_deprecated_tag: bool = False
    # Whether the scope carries any Surviving Condition (process group, host group or Primary Tag)
    # to reproduce the Target Set once the Deprecated Conditions are removed. Closure proves the
    # technology narrowed nothing; a set with nothing surviving is not `condition-dropped` but an
    # empty Scope, so it too must reach the candidate search.
    has_surviving_condition: bool = False
    # Set only where resolution is terminal: a target set that is genuinely empty, a read that
    # was capped, or a failure contained to this data source.
    outcome: DataSourceOutcome | None = None
    reason: ResolutionReason | None = None
    detail: str = ""


def resolve_target_sets(
    runner: QueryRunner,
    classifications: Sequence[AttributeClassification],
    *,
    window: QueryWindow,
) -> tuple[Resolution, ...]:
    """The target set of every affected data source the run has to find a replacement for.

    Unaffected request attributes do not exist for this layer, and neither do the data sources of
    an affected one that carry nothing deprecated: there is nothing to replace. An obsolete data
    source is skipped too - it captures only onto external service calls Phase 3 removes, so no
    query is spent hunting a replacement; `100` Neutralises it from the classification flag.
    """
    return tuple(
        resolve_one(runner, one, source, window=window)
        for one in classifications
        if one.verdict is AttributeClass.AFFECTED
        for source in one.data_sources
        if source.affecting and not source.obsolete
    )


def resolve_one(
    runner: QueryRunner,
    classification: AttributeClassification,
    data_source: DataSourceClassification,
    *,
    window: QueryWindow,
) -> Resolution:
    """What one data source's scope selects, in the fixed order the reads compose.

    The shape is settled from the scope before anything is read, and it decides which reads are
    asked: a technology condition makes the set service-shaped, because that is the condition
    able to tell apart services sharing a process group.
    """
    scope = data_source.scope
    shape = (
        TargetShape.SERVICE
        if scope.service_technology is not None
        else TargetShape.PROCESS_GROUP
    )
    resolved = Resolution(
        classification.id,
        data_source.index,
        shape,
        # A surviving primary tag is the one condition no entity read can carry: it is compared
        # against the server entry point span's resource attributes even below Phase 3. So
        # whatever is resolved here is wider than what the scope selects, and it is recorded as
        # wider rather than presented as exact.
        superset=scope.surviving_tag is not None,
        carries_deprecated_tag=scope.deprecated_tag is not None,
        has_surviving_condition=_has_surviving_condition(scope),
    )
    try:
        return _resolved(runner, resolved, scope, window=window)
    except _Unresolvable as failure:
        return _failed(resolved, failure.reason, failure.detail)
    except RateLimited:
        # Not this data source's failure to own. A rate limit says nothing about the scope being
        # resolved, so recording it here would hand out hundreds of identical rows and a run
        # that looks complete; it belongs to the run, and the run stops.
        raise
    except Exception as failure:  # pylint: disable=broad-exception-caught
        # Whatever the surprise was, it belongs to this one data source. A run against a tenant
        # holding hundreds of affected request attributes is worthless if the first read it
        # cannot make sense of ends it.
        return _failed(resolved, ResolutionReason.RESOLUTION_FAILED, str(failure))


def _has_surviving_condition(scope: Scope) -> bool:
    """Whether the scope carries a condition that survives Phase 3 to reproduce the Target Set.

    The three Surviving Conditions (CONTEXT.md → Language): a process group, a host group, or a
    Primary Tag. Where the scope carries none, removing the Deprecated Conditions leaves an empty
    Scope, which selects everything - so a closed service set with nothing surviving is not settled.
    """
    return (
        scope.process_group is not None
        or scope.host_group is not None
        or scope.surviving_tag is not None
    )


def _failed(resolved: Resolution, reason: ResolutionReason, detail: str) -> Resolution:
    """One data source recorded as unresolved, so nothing disappears silently."""
    return replace(
        resolved,
        outcome=DataSourceOutcome.UNPROCESSABLE,
        reason=reason,
        detail=detail,
    )


def _resolved(
    runner: QueryRunner, resolved: Resolution, scope: Scope, *, window: QueryWindow
) -> Resolution:
    """The reads this scope's own conditions ask for, in the order they compose."""
    rows = _tagged_rows(runner, scope, window=window)
    tagged = _tagged_ids(rows)
    if tagged is not None and not tagged:
        # Terminal, and nothing further is asked: with no target set there is nothing for a
        # second read to be about.
        return _resolved_empty(runner, resolved, scope, window=window)
    if scope.service_technology is not None:
        # No host group material: a service carries no host group relationship at all, so a
        # service-shaped target set cannot supply it and must not appear to.
        members = _service_members(
            runner,
            scope.service_technology,
            _service_scoping(runner, scope, tagged, window=window),
            window=window,
        )
        if not members:
            # A complete service read naming no service is a measured nothing - a capped one
            # already raised TRUNCATED_SERVICE_READ inside _service_members and never reaches
            # here. Terminal, like the tagged-empty results and for the same reason: with no
            # target set there is nothing for a second read to be about, and the action is the
            # same re-run-wider-then-delete. Left non-terminal it leaks into the harvest, where a
            # span read scoped to an empty set is refused and misreported as a read that failed.
            return replace(
                resolved,
                outcome=DataSourceOutcome.EMPTY_TARGET_SET,
                reason=ResolutionReason.SURVIVING_CONDITIONS_SELECT_NOTHING,
                detail=(
                    f"no service ran {scope.service_technology!r} on the scoped process groups "
                    f"within {window.timeframe}"
                ),
            )
        return replace(resolved, target_set=members)
    members = _host_groups_of(rows or ())
    return replace(
        resolved,
        target_set=tagged or (),
        host_groups=_with_membership(runner, members, tagged or (), window=window),
    )


# The most data sources one replacement is fanned out into. Well below what the API permits, and
# a judgement about what a human will actually review rather than a selectivity threshold. It
# matters to resolution for one reason: within the cap a target set is covered one data source
# per process group, so no host group is ever contemplated and its membership is not worth a
# read.
FAN_OUT_CAP = 10


def _with_membership(
    runner: QueryRunner,
    host_groups: HostGroups,
    target_set: tuple[str, ...],
    *,
    window: QueryWindow,
) -> HostGroups:
    """The same material, with one host group's full membership where that rung is reachable.

    Two conditions, both answerable from the target set already in hand. The set has to sit
    inside a **single** host group, because a scope holds one host group condition and nothing
    fans out over them - a set spanning two can never be reproduced by one. And it has to be
    above the fan-out cap, because below it the set is covered one data source per process group
    and the host group is never contemplated at all.

    Where both hold, the membership read is what tells "exactly this host group" from "this host
    group and more": the tagged read returns only *tagged* process groups, so an untagged member
    of the same host group is invisible to it.
    """
    touched = {group for group in host_groups.of_member.values() if group is not None}
    if len(touched) != 1 or len(target_set) <= FAN_OUT_CAP:
        return host_groups
    (host_group,) = touched
    return replace(host_groups, members=_membership(runner, host_group, window=window))


def _host_groups_of(rows: Sequence[Mapping[str, Any]]) -> HostGroups:
    """The host group each member belongs to, and the name each of those resolved to.

    Both ride on the tagged read, which already projects the relationship and already joins the
    name: the relationship is single-valued on the process group's own side, so it is the one
    direction that cannot be capped.
    """
    return HostGroups(
        of_member={str(row["id"]): _text_of(row.get("host_group")) for row in rows},
        names={
            host_group: name
            for row in rows
            if (host_group := _text_of(row.get("host_group"))) is not None
            and (name := _text_of(row.get("host_group_name"))) is not None
        },
    )


def _resolved_empty(
    runner: QueryRunner, resolved: Resolution, scope: Scope, *, window: QueryWindow
) -> Resolution:
    """An empty target set, said as whichever of the two empty results actually answered.

    The tagged read cannot tell them apart: it only ever returns *tagged* process groups, so a
    host group holding nothing but untagged members answers the same nothing as a host group
    that is not there. The distinction costs the membership read and is worth paying for on this
    path, because the two mean opposite things to whoever reads the report - one says the tag has
    moved on, the other says the scope names something gone.

    Both are terminal within this run and neither is a final statement about the scope: an
    entity read is bounded by the window, steeply, while the tags the runtime reads at request
    time carry no window at all. So the reason travels with the stretch it was measured over,
    and the action is to re-run wider rather than to rework the scope by hand.
    """
    members = _host_group_membership(runner, scope, window=window)
    if members is not None and not any(members.values()):
        return replace(
            resolved,
            host_groups=HostGroups(members=members),
            outcome=DataSourceOutcome.EMPTY_TARGET_SET,
            reason=ResolutionReason.SURVIVING_CONDITIONS_SELECT_NOTHING,
            detail=(
                f"the scope's host group {scope.host_group} holds no process group "
                f"within {window.timeframe}"
            ),
        )
    key = scope.deprecated_tag.key if scope.deprecated_tag is not None else ""
    return replace(
        resolved,
        host_groups=HostGroups(members=members),
        outcome=DataSourceOutcome.EMPTY_TARGET_SET,
        reason=ResolutionReason.TAG_MATCHED_NOTHING,
        detail=f"no process group carried {key!r} within {window.timeframe}",
    )


def _host_group_membership(
    runner: QueryRunner, scope: Scope, *, window: QueryWindow
) -> Mapping[str, tuple[str, ...]] | None:
    """Every process group of the scope's surviving host group, or `None` where it sets none.

    The same builder as the tagged read with the host group alone and no tag, which is the one
    form deliberately left unnarrowed: the question is which process groups the host group
    holds, and the ones carrying no tag are exactly the ones that decide it.
    """
    if scope.host_group is None:
        return None
    return _membership(runner, scope.host_group, window=window)


def _membership(
    runner: QueryRunner, host_group: str, *, window: QueryWindow
) -> Mapping[str, tuple[str, ...]]:
    """Every process group of one host group, tagged or not."""
    answer = _answered(runner, process_group_read(window, host_group=host_group))
    _whole(answer, ResolutionReason.TRUNCATED_PROCESS_GROUP_READ, "the host group membership read")
    return {
        host_group: tuple(str(record["id"]) for record in answer.records if "id" in record)
    }


def _tagged_rows(
    runner: QueryRunner, scope: Scope, *, window: QueryWindow
) -> tuple[Mapping[str, Any], ...] | None:
    """The rows carrying this scope's deprecated tag, or `None` where it sets none.

    Absent is `None` and never an empty tuple: a scope with no deprecated tag asked no question,
    which is a different fact from a question that came back with nothing.
    """
    if scope.deprecated_tag is None:
        return None
    answer = _answered(
        runner,
        process_group_read(
            window,
            tag=scope.deprecated_tag,
            host_group=scope.host_group,
            process_group=scope.process_group,
        ),
    )
    _whole(answer, ResolutionReason.TRUNCATED_PROCESS_GROUP_READ, "the process group read")
    return _tagged_members(answer.records, scope.deprecated_tag)


def _tagged_ids(rows: Sequence[Mapping[str, Any]] | None) -> tuple[str, ...] | None:
    """The process groups a tagged read named, or `None` where no such read was asked."""
    return None if rows is None else tuple(str(row["id"]) for row in rows)


def service_rows(
    runner: QueryRunner, scope: Scope, *, window: QueryWindow
) -> tuple[Mapping[str, Any], ...]:
    """The service read's own rows, asked exactly as this scope's resolution asked them.

    The rows themselves, and not the ids a resolution keeps: the harvest needs the process group
    each target service runs on, which this read projects and the target set does not carry. Those
    process groups are what bounds the closure read, and that read - carrying no technology - is
    what answers the services a target service shares its process group with.

    Re-rendered rather than handed forward. The builders fix their own stage order, the cache
    keys on the rendered text and every stage is handed the caching runner, so asking the same
    question twice costs a file read and no transport call - which is what keeps a resolution the
    contract row a consuming stage classifies on rather than one carrying raw records.
    """
    if scope.service_technology is None:
        return ()
    tagged = _tagged_ids(_tagged_rows(runner, scope, window=window))
    scoped_by = _service_scoping(runner, scope, tagged, window=window)
    answer = _answered(
        runner,
        service_read(
            window, process_groups=scoped_by, service_technology=scope.service_technology
        ),
    )
    return tuple(answer.records)


def _service_scoping(
    runner: QueryRunner,
    scope: Scope,
    tagged: tuple[str, ...] | None,
    *,
    window: QueryWindow,
) -> tuple[str, ...] | None:
    """The process groups the service read is restricted to, or `None` for no restriction.

    A service carries no host group relationship - probed, `groups[dt.entity.host_group]` on a
    service is null - so a surviving host group cannot be applied to the read's own rows and has
    to bound the read instead. Where the scope also carries a deprecated tag, the set that tag
    resolved to is already inside that host group, so it is the narrower bound and the
    membership read is not asked for: the host group is in force through it either way.

    Where the scope sets neither, nothing here restricts the read and the technology in its query
    text is the whole of its bound. Naming a population instead would render tens of thousands of
    identifiers to express no restriction at all.
    """
    if tagged is not None:
        return tagged
    if scope.process_group is not None:
        return (scope.process_group,)
    members = _host_group_membership(runner, scope, window=window)
    return None if members is None else tuple(members[scope.host_group or ""])


def _service_members(
    runner: QueryRunner,
    technology: str,
    scoped_by: tuple[str, ...] | None,
    *,
    window: QueryWindow,
) -> tuple[str, ...]:
    """The services every deprecated condition on this scope agrees on.

    Read from the service side, where the process group relationship is single-valued and so
    cannot be capped. The technology reaches the query text, in each spelling the runtime
    accepts: Grail's `type:` segment carries the `KnownTechnologyDto` name the scope stores, so
    the filter tests the same string the comparison below tests and no translation is involved on
    either side.

    Where the scope carries a deprecated tag as well, both conditions are in force today and the
    set it selects is the one they agree on. Answering the technology alone would yield every
    service of every process group, tagged or not - and a superset is the direction that ships,
    because the condition then reads as narrowing nothing and the emitted data source captures
    more than the original did.

    The restriction bounds the read *and* is applied to its rows. The first is what keeps the
    read the rule's question rather than the tenant's; the second is what decides, for the same
    reason the tag filter decides nothing - what a resolution claims rests on the comparison it
    made, never on a filter having been rendered.
    """
    answer = _answered(
        runner,
        service_read(window, process_groups=scoped_by, service_technology=technology),
    )
    _whole(answer, ResolutionReason.TRUNCATED_SERVICE_READ, "the service read")
    return tuple(
        str(record["id"])
        for record in answer.records
        if "id" in record
        and _carries_technology(record, technology)
        and _runs_on_one_of(record, scoped_by)
    )


def _carries_technology(record: Mapping[str, Any], technology: str) -> bool:
    """Whether this service runs the scope's technology, on the one field that says so.

    The comparison is on the `type:` segment of `softwareTechnologies`, because that is the field
    the runtime's `SOFTWARE_TECH_TYPE_EQUALS` reads. The sibling `serviceTechnologyTypes` holds
    display names (`Java`) and is never read: a resolution keyed off it would put a service in the
    target set of a scope naming a different technology.

    Either spelling, case-folded, because the runtime dispatches on the **service**'s own
    technology and not on the condition's: a typed one is compared as the enum - which Grail
    spells the `KnownTechnologyDto` way - and an untyped one as a case-insensitive string against
    the condition's `KNOWN_TECHNOLOGY` verbatim name. A read cannot say which branch a row would
    take, so both are accepted. That leaves one seam, and it is the direction this project
    records rather than refuses: a verbatim entry spelled like the DTO name matches here and not
    at runtime, which over-selects.

    Still the decider. The read's net admits rows on the same spellings and this drops the ones
    whose `type:` segment only looks like one.
    """
    accepted = {one.casefold() for one in spellings_of(technology)}
    rendered = record.get("softwareTechnologies")
    entries = rendered if isinstance(rendered, list) else [rendered]
    found = (_technology_type_of(entry) for entry in entries)
    return any(segment is not None and segment.casefold() in accepted for segment in found)


def _technology_type_of(rendered: Any) -> str | None:
    """The `type:` segment of one `type:T,edition:…,version:…` entry, and nothing else of it.

    Edition and version do not round-trip through a scope at all - the mapper builds the stored
    condition from the type alone - so nothing beyond that segment can take part.
    """
    text = _text_of(rendered)
    if text is None:
        return None
    for segment in text.split(","):
        if segment.startswith("type:"):
            return segment.removeprefix("type:")
    return None


def _runs_on_one_of(record: Mapping[str, Any], process_groups: tuple[str, ...] | None) -> bool:
    """Whether this service runs on a process group the scope's other conditions left in play.

    `None` is no restriction rather than an empty one: the scope set no deprecated tag, so no
    process group set was ever resolved to restrict it to.
    """
    if process_groups is None:
        return True
    return _text_of(record.get("process_group")) in process_groups


def _tagged_members(
    records: Sequence[Mapping[str, Any]], tag: Tag
) -> tuple[Mapping[str, Any], ...]:
    """The rows whose own tag is the scope's tag, compared as parsed triples.

    Never as strings: Grail renders an entity tag with its colons escaped while Config v1 stores
    the same tag with none, so the two sides of an identical tag do not spell the same. A string
    comparison does not fail loudly - it yields an empty target set, which is the one outcome
    that must never be reached by accident.
    """
    return tuple(
        record
        for record in records
        if "id" in record and parse_tag(_text_of(record.get("tags"))) == tag
    )


def _text_of(rendered: Any) -> str | None:
    return rendered if isinstance(rendered, str) else None


def _whole(answer: DqlAnswer, reason: ResolutionReason, named: str) -> None:
    """Refuse to read a capped answer as an answer, naming which read was capped.

    Read off the assembled answer, chunked reads included: one capped chunk among five makes the
    whole of it short by rows nothing downstream can notice.
    """
    if not answer.complete:
        raise _Unresolvable(reason, f"{named} came back capped, so it names no target set")


def _answered(runner: QueryRunner, read: Read) -> DqlAnswer:
    """One read's answer, however many queries it took to ask it."""
    return read.answered([runner.answer(query) for query in read.queries])
