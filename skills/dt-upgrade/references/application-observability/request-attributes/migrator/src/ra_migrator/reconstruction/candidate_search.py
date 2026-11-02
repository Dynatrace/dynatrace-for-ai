"""Which harvested material actually qualifies as a candidate, and what each still has to prove.

Pure computation - it issues no query. Given the harvest, this layer decides what qualifies as a
candidate, what is discarded and why, and which data sources still need observation at all. Its
output is a ranked, pruned candidate list per data source; `100` spends the queries and reaches a
verdict.

Keeping this separate from `100` is what makes "we may not have to issue all the queries" a
property of one layer: this layer decides *which* data sources still need a read.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from ..attributes.tags import CONTEXTLESS, Tag
from ..dql.queries import TargetShape
from ..reporting.outcomes import (
    DataSourceNote,
    AssessmentDropReason,
    HarvestDropReason,
    MatchProof,
)
from .harvest import Harvest, PrimaryTagKey
from .resolution import Resolution

# The most data sources one replacement fans out into, and the most values one Primary Tag key may
# carry across the target set. A reviewability ceiling, not a selectivity threshold: ten process
# group IDs is what a human will actually check.
FAN_OUT_CAP = 10


@dataclass(frozen=True)
class Candidate:
    """One replacement rung: the harvested conditions filling free Scope slots, and how its match
    against the target set is established.

    The Surviving Conditions are not copied here - they live on the Scope and `100` composes them
    in on both sides. What this carries is the harvested additions and the ground for the match
    where one is owed without a read.
    """

    host_group: str | None = None
    # The process groups this candidate fans out over, one data source each. Set only on the
    # fan-out route.
    fan_out: tuple[str, ...] = ()
    # The Primary Tag this rung adds, as the runtime evaluates it, one entry per data source it
    # fans out into: several values of one key are fanned out rather than folded to key-only. A
    # single value is one entry; a key-only form is one entry carrying no value. Empty on an
    # entity-side rung.
    primary_tag: tuple[Tag, ...] = ()
    # The key-only form retained where `key:value` is the shipped candidate, so the report can
    # offer it as a deliberate choice. None where the shipped tag is already key-only.
    key_only_alternative: Tag | None = None
    # Whether `100` must spend a verification read to establish this rung's match against the
    # target set. False where the construction or an already-spent read establishes it.
    needs_observation: bool = False
    # What proves the match without observation, where it is. None where observation does.
    proof: MatchProof | None = None


@dataclass(frozen=True)
class CandidateDrop:
    """One axis this layer or the harvest pruned, with the code that says why.

    Named by the axis and never by the data source: dropping an axis is never dropping the data
    source, which carries on with what is left.
    """

    axis: str
    reason: AssessmentDropReason | HarvestDropReason
    detail: str = ""


@dataclass(frozen=True)
class CandidateAssessment:
    """What one data source's harvest qualified as, before `100` verifies it.

    Reaches no terminal verdict: `100` assigns those. This says what `100` must do next - ship a
    candidate exact by construction, spend a read on one that needs observation, drop the
    deprecated technology where its removal is exact, or record that nothing was coverable.

    Over pylint's default by three, and the three are the dormancy caveat this row now carries
    forward for `100` and the report: collapsing them to satisfy a threshold would make the row say
    less than the next stage is asked to read from it.
    """

    # pylint: disable=too-many-instance-attributes

    attribute_id: str
    data_source_index: int
    shape: TargetShape
    # The rung `100` should verify or ship, or `None` where none was found.
    candidate: Candidate | None = None
    # The service technology narrowed nothing and its removal is exact, so nothing is added and no
    # read is owed. Distinct from a candidate: the replacement is the Surviving Conditions alone.
    condition_dropped: bool = False
    # Every rung pruned out. Distinct from a candidate still to be observed and from an empty
    # target set, and it never reaches `100` as a candidate to verify.
    no_candidate: bool = False
    # Harvested candidates the entity side reproduced the target set without, retained and named so
    # the report can offer them as a deliberate narrowing (issue: recorded unneeded, not shipped).
    unneeded: tuple[Candidate, ...] = ()
    drops: tuple[CandidateDrop, ...] = ()
    # The Target Set members that produced no entry-point span, carried forward from
    # `Harvest.dormant` so the report and `100` read it without re-deriving it. Empty where none
    # were dormant or the harvest read was never spent.
    dormant: tuple[str, ...] = ()
    # The caveat riding a shipped candidate where some members were dormant: the replacement is
    # proven on the live members, and if the dormant ones resume traffic it may not cover them.
    # `None` where no candidate ships or none were dormant, so a consumer branches on the named
    # note rather than on "`dormant` non-empty and a candidate shipped".
    note: DataSourceNote | None = None
    # Every member of the Target Set was dormant, so no key could be a candidate and no free rung
    # covered the set. The No-Verdict routing signal that replaces the retired per-key dormant
    # drop: `100` records `no-spans-and-no-free-rung-to-fall-back-on`, not a rework.
    wholly_dormant: bool = False


def assess_all(
    resolutions: Sequence[Resolution], harvests: Sequence[Harvest]
) -> tuple[CandidateAssessment, ...]:
    """The candidate assessment for every data source a replacement is still to be found for.

    One per harvest, paired back to the resolution it was harvested from - the Target Set is read
    from `Resolution.target_set`, and the Harvest carries the axes. Issues no query: the material is
    already in hand, and the Surviving Conditions the customer wrote stay on the Scope, which `100`
    composes back in on both sides of its comparison.
    """
    resolved = {(one.attribute_id, one.data_source_index): one for one in resolutions}
    return tuple(
        _assess(harvest, resolved[(harvest.attribute_id, harvest.data_source_index)])
        for harvest in harvests
    )


def _assess(harvest: Harvest, resolution: Resolution) -> CandidateAssessment:
    """One data source's candidate assessment, rung by rung.

    A wholly dormant Target Set is settled before any candidate is contemplated: no live member was
    measured, so every discovered key is vacuously carried by no live span, and the removed dormant
    drop no longer prunes those keys. Without this guard a zero-carrier key would ship as a key-only
    candidate built on no evidence; with it the Data Source is no-candidate, which `100` routes to
    No Verdict from the whole-set dormant signal (never a per-key drop). A free-rung set never
    reaches here dormant - its harvest read was gated off, so `Harvest.dormant` is `None`.

    Otherwise the one free route that needs no query comes first: within the cap a
    process-group-shaped set is covered one data source per process group. Everything else is the
    conjunction, which `100` proves.
    """
    if _wholly_dormant(harvest, resolution):
        return _one(harvest, no_candidate=True, wholly_dormant=True)
    if _fans_out(resolution):
        return _one(
            harvest,
            candidate=Candidate(
                fan_out=resolution.target_set, proof=MatchProof.FAN_OUT
            ),
        )
    return _conjunction(harvest, resolution)


def _wholly_dormant(harvest: Harvest, resolution: Resolution) -> bool:
    """Whether every member of the Target Set was dormant, so no live member measured anything.

    `Harvest.dormant` is `None` where the harvest read was never spent (a free rung covered the
    set), and empty where every member had traffic; only a non-empty set covering the whole Target
    Set is wholly dormant. Non-empty already implies a non-empty Target Set, so no separate guard on
    that is needed.
    """
    return bool(harvest.dormant) and set(harvest.dormant) == set(resolution.target_set)


def _conjunction(harvest: Harvest, resolution: Resolution) -> CandidateAssessment:
    """The replacement where no free route covers the set: what fills the free Scope slots.

    Assembled and never ranked against itself: every candidate's value was harvested from every
    member of the target set, so AND-ing them narrows an over-selection and can never drop a
    member. `100` tests the whole thing in one read.

    Two rungs, and the second is only reached when the first over-selects. The entity side is asked
    first: where the host group reproduces the target set alone - established by the full-membership
    read `080` already spent - no read is owed and the Primary Tag candidates are recorded unneeded
    rather than shipped. Otherwise the harvested host group rides in the conjunction with the
    Primary Tag, which `100` proves.
    """
    if _service_set_closed(harvest, resolution):
        # The technology narrowed nothing, so removing it is exact and no Primary Tag is
        # contemplated at all - the one rung that ships with no span read and no observation.
        return _one(harvest, condition_dropped=True, drops=tuple(_harvested_drops(harvest)))
    if _service_closure_replaces(harvest, resolution):
        # The edit-path declined - a deprecated tag would be left behind, or nothing survives to
        # edit - but the closure read proves the touched process groups hold exactly the Target
        # Set. So a `SPECIFIC_PG` per touched process group is constructed, subsuming every original
        # condition, proven by the read already spent and needing no observation.
        return _one(
            harvest,
            candidate=Candidate(
                fan_out=harvest.process_groups.ids, proof=MatchProof.SERVICE_CLOSURE
            ),
        )
    host_group, exact, host_group_drop = _host_group(harvest, resolution)
    drops = [
        *_fan_out_drops(resolution),
        *([host_group_drop] if host_group_drop else []),
        *_harvested_drops(harvest),
    ]
    if exact:
        return _one(
            harvest,
            candidate=Candidate(
                host_group=host_group, proof=MatchProof.HOST_GROUP_MEMBERSHIP
            ),
            unneeded=_unneeded_primary_tags(harvest),
            drops=tuple(drops),
        )
    primary_tag, tag_drops = _primary_tag_candidate(harvest)
    drops += tag_drops
    if primary_tag is not None:
        return _one(
            harvest, candidate=replace(primary_tag, host_group=host_group), drops=tuple(drops)
        )
    return _one(harvest, no_candidate=True, drops=tuple(drops))


def _service_set_closed(harvest: Harvest, resolution: Resolution) -> bool:
    """Whether every service of every touched process group is in the target set, read and compared.

    Service-shaped only, and only on a **complete** closure answer: a dropped axis never says so.
    Every service a cap hid is one that would have refuted closure, so a short answer is refused
    rather than read as closed - the data source falls through to the Primary Tag route, the priced
    cost of refusing.

    Closure licenses removing the *technology* only. It settles the data source solely when nothing
    else is left to replace: no deprecated `tagOfProcessGroup` remains, and a Surviving Condition
    reproduces the Target Set. A set still carrying a deprecated tag, or carrying no Surviving
    Condition at all (whose replacement would be an empty Scope), falls through to the candidate
    search instead of a false `condition-dropped`.
    """
    if resolution.shape is not TargetShape.SERVICE:
        return False
    closure = harvest.service_closure
    if closure.dropped is not None or not closure.services:
        return False
    if resolution.carries_deprecated_tag or not resolution.has_surviving_condition:
        return False
    return set(closure.services) <= set(resolution.target_set)


def _service_closure_replaces(harvest: Harvest, resolution: Resolution) -> bool:
    """Whether a constructed `SPECIFIC_PG` per touched process group reproduces the set exactly.

    Service-shaped only, and only on a **complete** closure answer that **equals** the Target Set:
    equality, not the edit-path's subset, because a constructed replacement over the touched process
    groups selects every service they hold - so an over-select (a service in a process group but not
    in the Target Set) must rule the route out, and the by-construction `target ⊆ closure` makes the
    over-select check `closure == target`. A dropped or capped closure never says so: every service a
    cap hid is one that would have refuted equality.

    Within the fan-out cap: over it the replacement would need more Data Sources than a human will
    review, so the axis is not taken and the set falls through to the Primary Tag conjunction.
    Reached only after `_service_set_closed` declined, so what remains is the case it routed away -
    a deprecated `tagOfProcessGroup` (`175`) or no Surviving Condition. The touched process groups
    are the process group axis of a service-shaped set, carried on the harvest.
    """
    if resolution.shape is not TargetShape.SERVICE:
        return False
    closure = harvest.service_closure
    if closure.dropped is not None or not closure.services:
        return False
    if len(harvest.process_groups.ids) > FAN_OUT_CAP:
        return False
    return set(closure.services) == set(resolution.target_set)


def _host_group(
    harvest: Harvest, resolution: Resolution
) -> tuple[str | None, bool, CandidateDrop | None]:
    """The host group filling the free `hostGroup` slot, whether it settles the set, and any drop.

    A host group whose full membership is exactly the target set reproduces it alone, no read owed.
    One that holds a further process group over-selects alone: it does not settle the data source,
    but it still narrows, so it rides in the conjunction with the Primary Tag. A target set spanning
    two host groups yields none - a Scope holds one `hostGroup` and nothing fans out over them.
    """
    if harvest.host_groups.unavailable:
        return None, False, None
    groups = {group for group in harvest.host_groups.of_member.values() if group is not None}
    if len(groups) > 1:
        return (
            None,
            False,
            CandidateDrop(
                "host-group",
                AssessmentDropReason.MULTIPLE_HOST_GROUPS,
                f"the target set spans {len(groups)} host groups, and a Scope holds one",
            ),
        )
    if not groups:
        return None, False, None
    (group,) = groups
    return group, _is_full_membership(harvest, resolution), None


def _is_full_membership(harvest: Harvest, resolution: Resolution) -> bool:
    """Whether some host group's full membership is exactly the target set, read and compared.

    Only the membership read can say so: the tagged read returns tagged process groups alone, so an
    untagged member of the same host group is invisible to it. Absent membership is never a match.
    """
    membership = harvest.host_groups.membership
    if membership is None:
        return False
    target = set(resolution.target_set)
    return any(set(held) == target for held in membership.values())


def _unneeded_primary_tags(harvest: Harvest) -> tuple[Candidate, ...]:
    """The Primary Tag candidates the entity side reproduced the target set without.

    Retained and named rather than shipped: a tag condition that excludes nothing still costs a
    comparison against every entry-point span for as long as the data source lives, and ties the
    capture to a tag someone else owns. Kept so the report can offer it as a deliberate narrowing.
    """
    return tuple(
        candidate
        for key in _usable_keys(harvest)
        if isinstance(candidate := _tag_form(key), Candidate)
    )


def _fan_out_drops(resolution: Resolution) -> list[CandidateDrop]:
    """The process group axis dropped where it needs more data sources than the cap allows.

    A cap hit on one axis never takes the data source down with it: the set falls through to the
    conjunction.
    """
    if (
        resolution.shape is TargetShape.PROCESS_GROUP
        and len(resolution.target_set) > FAN_OUT_CAP
    ):
        return [
            CandidateDrop(
                "process-group-fan-out",
                AssessmentDropReason.FAN_OUT_OVER_CAP,
                f"reproducing the target set needs {len(resolution.target_set)} data sources, "
                f"where the fan-out carries at most {FAN_OUT_CAP}",
            )
        ]
    return []


def _primary_tag_candidate(
    harvest: Harvest,
) -> tuple[Candidate | None, list[CandidateDrop]]:
    """The Primary Tag rung, from the one key that stands as a candidate on its own, and any drops.

    One key, always: a Scope holds one `tagOfProcessGroup`, so two keys can never be AND-ed. The
    harvest already dropped every key not carried by every member on every span, so a key it left
    standing covers the target set alone; where several do, the first fills the slot and the rest
    stay unused. A key needing more values than the cap allows is dropped here and the next usable
    key is tried.
    """
    drops: list[CandidateDrop] = []
    for key in _usable_keys(harvest):
        candidate = _tag_form(key)
        if isinstance(candidate, CandidateDrop):
            drops.append(candidate)
            continue
        return candidate, drops
    return None, drops


def _tag_form(key: PrimaryTagKey) -> Candidate | CandidateDrop:
    """One key as the tag form its values allow: key-only, a single value, or a value fan-out.

    `key:value` is preferred over key-only where both are exact, because key-only matches any value
    being present and would quietly widen as new deployments appear - so it is shipped and the
    key-only form is retained as the named alternative. One case the preference cannot apply to:
    a non-string value never matches a valued tag through `String.equals`, while key-only still
    matches, so a non-string key ships key-only. Several string values are fanned out rather than
    folded to key-only, and more than the cap allows is a drop.
    """
    if key.non_string or not key.values:
        return Candidate(primary_tag=(_tag(key, None),), needs_observation=True)
    if len(key.values) > FAN_OUT_CAP:
        return CandidateDrop(
            key.key,
            AssessmentDropReason.FAN_OUT_OVER_CAP,
            f"reproducing the target set needs {len(key.values)} values of {key.key!r}, "
            f"where the fan-out carries at most {FAN_OUT_CAP}",
        )
    return Candidate(
        primary_tag=tuple(_tag(key, value) for value in key.values),
        key_only_alternative=_tag(key, None),
        needs_observation=True,
    )


def _tag(key: PrimaryTagKey, value: str | None) -> Tag:
    """One Primary Tag as the runtime evaluates it: the bare key and the value, context aside."""
    return Tag(CONTEXTLESS, key.key, value)


def _harvested_drops(harvest: Harvest) -> list[CandidateDrop]:
    """The harvest's own drops, surfaced so the report shows every pruning reason.

    The codes are `080`'s - statements about material and about reads - and they travel through
    unchanged: a key the harvest refuted on a live member, one whose population went unmeasured, or
    the whole axis dropped where the read itself failed. Each drops the axis, never the data source.
    """
    tags = harvest.primary_tags
    drops = [
        CandidateDrop(key.key, key.dropped, key.detail)
        for key in tags.keys
        if key.dropped is not None
    ]
    if tags.dropped is not None:
        drops.append(CandidateDrop("primary-tag", tags.dropped, tags.detail))
    return drops


def _usable_keys(harvest: Harvest) -> tuple[PrimaryTagKey, ...]:
    """The discovered keys the harvest left standing, sorted so the choice is deterministic."""
    return tuple(
        sorted(
            (key for key in harvest.primary_tags.keys if key.dropped is None),
            key=lambda one: one.key,
        )
    )


def _fans_out(resolution: Resolution) -> bool:
    """Whether the process group route covers the set: process-group-shaped, within the cap.

    The one route that needs no query: `SPECIFIC_PG` reads the very value the deprecated tag read,
    so one data source per process group is exact by construction.
    """
    return (
        resolution.shape is TargetShape.PROCESS_GROUP
        and len(resolution.target_set) <= FAN_OUT_CAP
    )


def _one(
    harvest: Harvest,
    *,
    candidate: Candidate | None = None,
    condition_dropped: bool = False,
    no_candidate: bool = False,
    unneeded: tuple[Candidate, ...] = (),
    drops: tuple[CandidateDrop, ...] = (),
    wholly_dormant: bool = False,
) -> CandidateAssessment:
    """One candidate assessment, carrying its data source's identity and any dormancy off the harvest.

    The dormant members ride forward whatever the outcome; the caveat note is attached only where a
    candidate ships alongside them - a covered replacement proven on the live members, with the
    dormant remainder named so the report flags it rather than re-deriving it.
    """
    dormant = harvest.dormant or ()
    note = (
        DataSourceNote.DORMANT_TARGET_SET_MEMBERS
        if candidate is not None and dormant
        else None
    )
    return CandidateAssessment(
        harvest.attribute_id,
        harvest.data_source_index,
        harvest.shape,
        candidate=candidate,
        condition_dropped=condition_dropped,
        no_candidate=no_candidate,
        unneeded=unneeded,
        drops=drops,
        dormant=dormant,
        note=note,
        wholly_dormant=wholly_dormant,
    )
