"""The closed set of terminal codes a run can record.

Declared as enums rather than as strings because the taxonomy is already settled and a consuming
skill classifies a run against it: a code invented later as a string literal is a contract change
nobody notices. Nothing assigns the verdicts yet.

Every row a run produces carries three things, and they are three. A **verdict** is the grouping a
consumer classifies on, and it implies a recommended action - which is the only thing that justifies
splitting one verdict into two. A **reason** is the exact code within that verdict, so a consumer
can explain an outcome and not merely bucket it; the reason enums below are per verdict, because a
reason that could sit under two verdicts is a verdict that was not split on an action. A **detail**
is free text for a human, carrying the specifics - which read was capped, which member was missing
the value - and nothing parses it.
"""

from __future__ import annotations

from enum import StrEnum


class DataSourceOutcome(StrEnum):
    """How one data source came out. The resolution unit."""

    COVERED = "covered"
    CONDITION_DROPPED = "condition-dropped"
    NEUTRALISED_UNCOVERABLE = "neutralised-uncoverable"
    NEUTRALISED_OBSOLETE = "neutralised-obsolete"
    # A deprecated tag matching no process group. Terminal and never resolved: with nothing to
    # reproduce, no replacement can be caught under-selecting, so the only one comparing as exact
    # is one that selects nothing either - which would ship a data source that captures nothing
    # while reading as covered.
    EMPTY_TARGET_SET = "empty-target-set"
    # The run could not measure this data source: the verification read was capped, or its target
    # set produced no spans and no free rung covered it, or the primary tag route was gated off
    # because discovery named no key. None of those established that it cannot be covered, so the
    # action is to re-run and never to rework.
    NO_VERDICT = "no-verdict"
    UNPROCESSABLE = "unprocessable"


class RequestAttributeOutcome(StrEnum):
    """How one request attribute came out. The migration unit."""

    COVERED = "covered"
    PARTIALLY_COVERED = "partially-covered"
    NOT_COVERABLE = "not-coverable"
    # Captures nothing Phase 3 keeps: every enabled data source targets external service calls,
    # or there is no enabled data source at all. Both mean deletion rather than migration.
    OBSOLETE = "obsolete"
    # Every data source resolved an empty target set. The scopes select nothing, so the action is
    # deletion - which is what separates it from `not-coverable`, where there is something to
    # rework.
    SELECTS_NOTHING = "selects-nothing"
    # The run could not measure this one. Never a claim that it cannot be covered: the action is to
    # re-run. Traffic is not a verdict of its own - a dormant process group is still covered by its
    # own id - so no traffic-shaped verdict exists to reach for.
    NO_VERDICT = "no-verdict"
    UNPROCESSABLE = "unprocessable"


class AttributeClass(StrEnum):
    """Which bucket of the scan funnel one request attribute fell into.

    Disjoint by construction: the funnel narrows scanned -> enabled -> obsolete -> affected, and
    a request attribute is counted once.
    """

    AFFECTED = "affected"
    OBSOLETE = "obsolete"
    UNAFFECTED = "unaffected"
    DISABLED = "disabled"
    UNPROCESSABLE = "unprocessable"


class AffectedReason(StrEnum):
    """Why a request attribute stops capturing. Two conditions, two reasons, never merged.

    A technology problem and a tag problem call for different work, so a breakdown that folded
    them together would tell a customer nothing they can act on.
    """

    SERVICE_TECHNOLOGY = "service-technology"
    NON_PRIMARY_PROCESS_GROUP_TAG = "non-primary-process-group-tag"


class DataSourceNote(StrEnum):
    """What is worth saying about one data source beyond how it came out."""

    # No capturing processor exists for the source, so the data source captures nothing today and
    # cannot break its request attribute either.
    NO_CAPTURING_PROCESSOR = "no-capturing-processor"
    # A tag key of exactly `primary_tags.` survives the runtime's rule but names no span field,
    # so the data source captures nothing - and no tenant would accept the key back.
    BARE_PRIMARY_TAG_PREFIX = "bare-primary-tag-prefix"
    # Captures on both the external service call and the full one; the external half goes away.
    EXTERNAL_HALF_LOST = "external-half-lost"
    # Some Target Set member produced no entry-point span in the window, so the replacement is
    # proven exact on the live members only. A non-blocking caveat riding a covered verdict: the
    # dormant member ids are the payload (`Harvest.dormant`), and if they resume traffic the
    # replacement may not cover them.
    DORMANT_TARGET_SET_MEMBERS = "dormant-target-set-members"


class UnprocessableReason(StrEnum):
    """Why one request attribute could not be classified. One poisoned config costs one row."""

    BODY_UNREADABLE = "body-unreadable"
    MALFORMED_BODY = "malformed-body"
    UNCLASSIFIABLE_SCOPE = "unclassifiable-scope"


class ResolutionReason(StrEnum):
    """Why a target set resolution came out the way it did. The codes Layer 4 contributes.

    A verdict implies an action; a reason explains it within that verdict. The two empty results
    share the verdict `empty-target-set` because they share an action - re-run wider - and differ
    here, because a host group with no tagged member and a host group that is gone mean opposite
    things to whoever reads the report.
    """

    # The surviving conditions do select process groups; none of them carries the tag.
    TAG_MATCHED_NOTHING = "tag-matched-nothing"
    # A surviving condition selects nothing that is there: the host group or process group the
    # scope names has no members in this window, or its technology matches no service on the
    # scoped process groups.
    SURVIVING_CONDITIONS_SELECT_NOTHING = "surviving-conditions-select-nothing"
    # A target set short by rows a cap hid is a wrong set, and every verdict built on it is wrong
    # while looking sound. Named per read, because the service read is the one whose truncation
    # ships a scope that captures more than the original.
    TRUNCATED_PROCESS_GROUP_READ = "truncated-process-group-read"
    TRUNCATED_SERVICE_READ = "truncated-service-read"
    # Whatever the surprise was, it belongs to this one data source.
    RESOLUTION_FAILED = "resolution-failed"


class NoVerdictReason(StrEnum):
    """Which measurement the run was missing. Every one of them means re-run, never rework.

    They differ in *what* to re-run with, which is the whole reason they are three codes and not
    one: a cap clears on a retry, a silent target set needs a wider window, and a tenant emitting
    no primary tag key needs neither - it needs a key.
    """

    # The read that would have decided what the replacement selects came back capped. Neither
    # confirmed nor refuted: a capped answer makes over-selection look exact.
    TRUNCATED_VERIFICATION_READ = "truncated-verification-read"
    # Every member of the target set was dormant and no free rung covered it, so the primary tag
    # route - the only one left - could not be observed. Within the fan-out cap this never fires:
    # there the members are covered by their own ids whether or not traffic returns.
    NO_SPANS_AND_NO_FREE_RUNG = "no-spans-and-no-free-rung-to-fall-back-on"
    # The discovery read named no primary tag key at all, so the span side of the run was gated off
    # before any data source reached it. A property of the tenant, not of this data source.
    NO_PRIMARY_TAG_KEY_ON_THE_TENANT = "no-primary-tag-key-on-the-tenant"
    # Every data source of this request attribute is itself `no-verdict`, or the ones that are not
    # were covered while at least one was unmeasured. Request-attribute level only.
    SOME_DATA_SOURCE_UNMEASURED = "some-data-source-could-not-be-measured"
    # The verification read reached every process group of the Target Set but selected fewer than
    # it holds. On this path that cannot happen without a cap - every kept candidate's value was
    # harvested from every member - so, absent a truncation, it points to a defect in the migrator
    # or to an entity that changed between the resolve read and the verify read, not to a fact
    # about the Data Source. The verdict is withheld rather than a finding asserted.
    REPLACEMENT_UNDER_SELECTS = "the-replacement-under-selects"


class NeutralisedUncoverableReason(StrEnum):
    """Why a data source was *established* to be uncoverable. Every one of them means rework.

    The line against `no-verdict` is what these codes exist to hold: each of them is a refutation
    the run actually made, and none of them is a measurement it failed to make.
    """

    # Some live member of the target set carries none of the candidate's value on any of its
    # entry-point spans. A refutation: no window changes it.
    REFUTED_ON_EVERY_CANDIDATE = "every-candidate-was-refuted"
    # No candidate was harvested that fits a free scope slot at all, so there was nothing to test.
    NO_CANDIDATE_FITS_A_FREE_SLOT = "no-candidate-fits-a-free-scope-slot"
    # Every candidate reached entities the original scope did not. There is no negation operator in
    # the scope, so an over-selection cannot be narrowed and there is no refinement to attempt.
    EVERY_CANDIDATE_OVER_SELECTS = "every-candidate-over-selects"


class SelectsNothingReason(StrEnum):
    """Why a request attribute's scopes select nothing. The action is deletion, after a re-run.

    Terminal within a run and never a final statement about the scopes: an entity read is bounded
    by the window, steeply, while the tags the runtime reads at request time carry no window at
    all. So the report says re-run wider before deleting.
    """

    # Every data source's deprecated tag matched no process group within this run's window.
    EVERY_TAG_MATCHED_NOTHING = "every-data-sources-tag-matched-nothing"
    # Every data source's surviving conditions select nothing - the host group or process group
    # named is gone, rather than merely untagged.
    EVERY_SCOPE_SELECTS_NOTHING = "every-data-sources-surviving-conditions-select-nothing"


class HarvestProvenance(StrEnum):
    """Which of the run's six reads a harvested item came from.

    Recorded on the material itself rather than inferred from its axis: what a later stage may
    claim depends on whether the evidence is entity material or span material, and two axes can
    ride on the same read.
    """

    DISCOVERY_READ = "discovery-read"
    TAGGED_PROCESS_GROUP_READ = "tagged-process-group-read"
    HOST_GROUP_MEMBERSHIP_READ = "host-group-membership-read"
    SERVICE_READ = "service-read"
    # The technology-free service read, which is a read of its own and so a provenance of its own:
    # the only member naming a read the harvest issues rather than re-renders.
    SERVICE_CLOSURE_READ = "service-closure-read"
    HARVEST_SPAN_READ = "harvest-span-read"

    @property
    def span_material(self) -> bool:
        """Whether what it carries was read off spans rather than off the topology."""
        return self is HarvestProvenance.HARVEST_SPAN_READ


class HarvestGate(StrEnum):
    """Why a data source was never paid a harvest span read.

    Every one of them is a set comparison over material already in hand, and none of them decides
    an outcome: they decide only whether a read is worth paying for. A gated axis is recorded as
    not asked, which is a different fact from one that was asked and found nothing.
    """

    # The tenant emits no primary tag key at all, so there is nothing to group by and nothing to
    # observe. It gates the whole span side of the run off.
    NO_DISCOVERED_KEY = "no-primary-tag-key-on-the-tenant"
    # Within the cap the set is covered one data source per process group, exact by construction.
    COVERED_BY_FAN_OUT = "covered-by-fan-out-over-the-process-groups"
    # The set is exactly one host group's full membership, which the membership read establishes.
    COVERED_BY_HOST_GROUP = "covered-by-the-host-groups-full-membership"
    # Every service of every touched process group is in the set, so the technology narrowed
    # nothing and removing it is exact.
    TECHNOLOGY_NARROWS_NOTHING = "target-service-set-closed-under-its-process-groups"
    # The service-shaped set equals the full service membership of its touched process groups, and
    # those are within the fan-out cap, so a `SPECIFIC_PG` per process group reproduces it exactly
    # from the closure read alone - even where a deprecated tag or no Surviving Condition would have
    # kept the edit-path from settling it. The Primary Tag span read is skipped.
    COVERED_BY_SERVICE_CLOSURE = "target-service-set-coextensive-with-its-process-groups"
    # The scope's one tag slot is occupied by a surviving primary tag, so there is no primary tag
    # route to observe.
    TAG_SLOT_TAKEN = "tag-slot-taken-by-a-surviving-primary-tag"


class HarvestDropReason(StrEnum):
    """Why a harvested axis or key yields no candidate. The codes the harvest owns.

    Each of them is a statement about material or about a read, which is what separates them from
    the codes the candidate search layer owns - those are statements about what a scope field can carry. Every
    one of them drops the *axis*, never the data source: what is left is still harvested, and a
    data source is only uncoverable if what remains fails to reproduce its target set.
    """

    # The tag key is genuinely null on some existing entry-point span of the Target Set (the probe's
    # `present < total`). It means only that this key cannot be a Primary Tag candidate in any form:
    # a null span carries no value for a `key:value` or a fanned-out value to match, and the runtime's
    # key-only condition (`!= null`) does not match it either. Merges the two old `MISSING_*` codes -
    # a member carrying it on no span and a member carrying it on only some are both `present < total`,
    # both route to rework, and the ungrouped probe measures them as one signal (telling them apart
    # again would need the group-harvest the prune avoids). Empty (`""`/`[]`) is presence, not a drop:
    # the key is there, and key-only matches it. A refutation - no window changes it.
    KEY_NOT_ON_ALL_TARGET_SET_SPANS = "primary-tag-key-not-on-all-target-set-entry-point-spans"
    # The read that would have harvested it did not answer at all.
    UNREADABLE = "the-read-that-would-have-harvested-it-did-not-answer"
    # The read answered and the platform capped the rows it answered with, so the members the
    # missing rows would have spoken for are unmeasured. Never read as the value being absent.
    UNMEASURED_POPULATION = "the-read-that-would-have-measured-it-came-back-capped"


class AssessmentDropReason(StrEnum):
    """Why the candidate search yields no candidate on an axis. The codes this layer owns.

    Each is a statement about what a Scope field can *carry*, which is what separates them from the
    harvest's codes - those are statements about material and about reads. Like the harvest's, each
    drops the *axis* and never the data source: a cap hit on one axis taking out the whole item is
    a bug the sibling shipped.
    """

    # A fanned-out axis needs more values than the fan-out cap allows - more than ten process
    # groups, or more than ten values of one Primary Tag key. A reviewability ceiling and not a
    # selectivity threshold, so the axis is dropped and the data source falls through to the
    # conjunction rather than being failed.
    FAN_OUT_OVER_CAP = "more-values-on-a-fanned-out-axis-than-the-fan-out-cap-allows"
    # The target set spans more than one host group. A Scope holds one `hostGroup` and nothing fans
    # out over host groups, so no one host group condition can reproduce the set. Distinct from a
    # host group that holds one further process group, which is a single host group that
    # over-selects rather than two the set cannot sit inside.
    MULTIPLE_HOST_GROUPS = "the-target-set-spans-more-than-one-host-group"


class MatchProof(StrEnum):
    """What proves a candidate's exact match without a verification read.

    The Primary Tag route is absent: its match is established by the verification read `100` spends,
    not by this layer. Recorded on the candidate rather than inferred from its shape, because two of
    these routes are sound because of a read and not an identity (`CONTEXT.md` -> Language,
    *Exact Match / the read that proved it*).
    """

    # One data source per process group, so the selected set *is* the target set. The one route
    # that rests on an identity.
    FAN_OUT = "the-fan-out-construction"
    # The target set is exactly one host group's full membership, which the membership read `080`
    # already spent tested it against.
    HOST_GROUP_MEMBERSHIP = "the-host-group-full-membership-read"
    # A service-shaped target set shown coextensive with its process group(s) by the closure read:
    # every service of every touched process group is in the set, so one `SPECIFIC_PG` per touched
    # process group reproduces it exactly. Rests on the closure read already spent, not an identity
    # (`155`/`165`), so it needs no observation.
    SERVICE_CLOSURE = "the-service-closure-read"


class CoveredReason(StrEnum):
    """Which read or construction established that a covered replacement selects exactly the set.

    `covered`'s own closed set, so a covered row carries a verdict *and* a reason like every other.
    The first three mirror `MatchProof` - the free routes `090` proved without a read - and the
    fourth is the one this layer earns: the Primary Tag route, exact only because the verification
    read said so. Kept distinct from `MatchProof` because that enum is "provable without a read" and
    the verification read is exactly a read; the covered row records which of the four it was.
    """

    FAN_OUT_CONSTRUCTION = "the-fan-out-construction"
    HOST_GROUP_MEMBERSHIP_READ = "the-host-group-full-membership-read"
    SERVICE_CLOSURE_READ = "the-service-closure-read"
    VERIFICATION_READ = "the-verification-read"


class ConditionDroppedReason(StrEnum):
    """Why a Data Source was resolved by dropping its `serviceTechnology` and nothing else.

    One cause, so one member: the technology narrowed nothing - every service of every touched
    process group already carried it - so removing it is exact and no candidate is owed. A
    single-member enum rather than a free string, for the contract reason the rest carry one.
    """

    TECHNOLOGY_NARROWED_NOTHING = "the-service-technology-narrowed-nothing"


class NeutralisedObsoleteReason(StrEnum):
    """Why a Data Source was Neutralised as obsolete rather than for being uncoverable.

    One cause, so one member: it captures only onto external service calls, which Phase 3 removes,
    so nothing it captures survives and there is nothing to cover. Decided at `050` from the capture
    location alone and carried through here, never re-derived.
    """

    CAPTURES_ONLY_EXTERNAL_CALLS = "captures-only-onto-external-service-calls"


class EmissionRejectionReason(StrEnum):
    """Why an emitted body was refused before it was written, naming the schema constraint it broke.

    Every one of these is a constraint the migrator's own construction is supposed to satisfy, so a
    violation is a defect upstream rather than a fact about the tenant - refused rather than shipped,
    because handing a customer an Artifact the API rejects is worse than handing them nothing. Enums
    rather than free strings for the reason the rest of this module carries them: a consuming skill
    classifies a refusal on the code, and the detail carries the specifics.
    """

    # More emitted Data Sources on one fanned-out replacement than the Fan-Out cap allows, or a body
    # outside the DTO's `@Size(min=1, max=2000)` on `dataSources`.
    DATA_SOURCES_OUT_OF_BOUNDS = "the-body-carries-a-data-source-count-the-schema-refuses"
    # A written `tagOfProcessGroup` whose key is not a Primary Tag the API validator accepts: not
    # `primary_tags.`-prefixed, or exactly the bare prefix.
    NON_PRIMARY_EMITTED_TAG = "a-written-tag-is-not-a-primary-tag-the-validator-accepts"
    # A written tag key carrying a colon, which the server's own serialisation does not escape, so it
    # cannot round-trip through Config v1.
    UNREPRESENTABLE_TAG_KEY = "a-written-tag-key-carries-a-colon-and-cannot-round-trip"
    # A written tag carrying a context prefix, which changes the stored value without changing what
    # matches and can silently turn the tag back into a Deprecated Condition.
    CONTEXT_PREFIX_ON_EMITTED_TAG = "a-written-tag-carries-a-context-prefix"
    # A `serviceTechnology` left on an enabled Data Source: the API validator accepts it, and the
    # runtime then deactivates the whole Request Attribute at Phase 3.
    SERVICE_TECHNOLOGY_ON_ENABLED_SOURCE = "an-enabled-data-source-carries-a-service-technology"
    # A `processGroup` or `hostGroup` value `ExpMEIdentifier.parse` would reject: not `TYPE-<hex>` of
    # that exact type, with the type segment's case not as the entity read returned it.
    MALFORMED_ME_IDENTIFIER = "a-process-group-or-host-group-id-would-not-parse"
    # A server-owned field the tool must not construct - `metadata` is `@Schema(READ_ONLY)`.
    SERVER_OWNED_FIELD = "the-body-carries-a-server-owned-field"


class CoveredRequestAttributeReason(StrEnum):
    """Why a whole Request Attribute came out covered. One cause, so one member.

    Every one of its Data Sources was covered or had its technology dropped, so the migrated body
    reproduces the original's capture in full. A closed set of its own rather than a shared roll-up
    code, so no reason ever sits under two Request-Attribute verdicts.
    """

    EVERY_DATA_SOURCE_COVERED = "every-data-source-covered"


class PartiallyCoveredReason(StrEnum):
    """Why a Request Attribute came out partially covered. One cause, so one member.

    At least one Data Source was covered and at least one was Neutralised, so the body deploys at a
    named cost: the covered sources capture, the Neutralised ones ship disabled for hand rework.
    """

    SOME_DATA_SOURCES_NEUTRALISED = "some-data-sources-neutralised"


class NotCoverableReason(StrEnum):
    """Why a Request Attribute came out not coverable. One cause, so one member.

    Every one of its Data Sources was Neutralised and none was covered, so no body is emitted -
    an all-disabled body would capture nothing while reading as a fix. Distinct from
    `selects-nothing`, where there was nothing to cover rather than nothing coverable.
    """

    EVERY_DATA_SOURCE_NEUTRALISED = "every-data-source-neutralised"
