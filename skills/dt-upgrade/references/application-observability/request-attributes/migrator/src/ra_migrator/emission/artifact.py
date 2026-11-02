"""The Artifact wrapper and the replacement Request Attribute body.

One Artifact per Request Attribute that earned a body - `covered` and `partially-covered`, and
nothing else, because a body that captures nothing while looking like a fix is worse than no body.
The wrapper carries the reasoning - per Data Source the Deprecated Conditions found, the Surviving
Conditions carried through, the verdict and its reason, and on a covered one that the match is exact
and which read established it - around a `replacement_request_attribute_body` that is a **complete**
`RequestAttributeDto`, never a diff and never a patch.

No write path: this layer builds values and writes files, and constructs no request to the
tenant - deployment is the customer's step. A body that fails a validity check is not written; its
Request Attribute becomes
`unprocessable` with the failing constraint named, because handing a customer an Artifact the API
rejects is worse than handing them nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..attributes.classification import AttributeClassification, DataSourceClassification, Scope
from ..attributes.tags import CONTEXTLESS, PRIMARY_TAG_PREFIX, Tag
from ..clients.transports import RequestAttributeConfig
from ..reporting.outcomes import (
    DataSourceNote,
    DataSourceOutcome,
    EmissionRejectionReason,
    RequestAttributeOutcome,
)
from ..reconstruction.candidate_search import FAN_OUT_CAP, Candidate
from ..reconstruction.verdict import DataSourceVerdict, ReasonCode, RequestAttributeVerdict

# The Data Source outcomes whose replacement is emitted enabled: a covered replacement, and one
# whose only Deprecated Condition was a service technology now dropped. Every other affected Data
# Source is emitted disabled, keeping its original Scope.
_COVERED_LIKE = frozenset(
    {DataSourceOutcome.COVERED, DataSourceOutcome.CONDITION_DROPPED}
)
# The Request Attribute outcomes that earn a body. Everything else gets none.
_EMITTED = frozenset(
    {RequestAttributeOutcome.COVERED, RequestAttributeOutcome.PARTIALLY_COVERED}
)
# The hex digits an emitted entity-side id's suffix may carry, read case-insensitively.
_HEX = frozenset("0123456789abcdefABCDEF")


@dataclass(frozen=True)
class DataSourceReasoning:
    """Why one original Data Source came out as it did, for the Artifact wrapper to render.

    Over pylint's default by one, and left that way: this is the wrapper's per-Data-Source story a
    customer reads, so its fields are the ones that story has - the conditions found and carried,
    the verdict and its reason, the match and the dormancy caveat. Collapsing two to reach eight
    would make the row say less than the report is asked to render from it.
    """

    # pylint: disable=too-many-instance-attributes

    data_source_index: int
    verdict: DataSourceOutcome
    reason: ReasonCode | None
    detail: str
    # The Deprecated Conditions found on the original Scope, and the Surviving Conditions carried
    # through, as the wire strings a reader recognises.
    deprecated_conditions: tuple[str, ...] = ()
    surviving_conditions: tuple[str, ...] = ()
    # On a covered Data Source: that the replacement selects exactly the Target Set. The read that
    # established it is the verdict's own `reason`. False on every Data Source the run did not cover,
    # so a `no-verdict` one earns no claim of coverage.
    match_exact: bool = False
    note: DataSourceNote | None = None
    dormant: tuple[str, ...] = ()


@dataclass(frozen=True)
class Artifact:
    """One Request Attribute that earned a body: the reasoning, and the deployable body."""

    attribute_id: str
    attribute_name: str
    verdict: RequestAttributeOutcome
    reason: ReasonCode | None
    data_sources: tuple[DataSourceReasoning, ...]
    replacement_request_attribute_body: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmissionRejection:
    """A Request Attribute whose body failed a validity check, refused rather than written."""

    attribute_id: str
    attribute_name: str
    reason: EmissionRejectionReason
    detail: str


class _Rejected(Exception):
    """A body a validity check refused. Costs one Request Attribute its Artifact, never the run."""

    def __init__(self, reason: EmissionRejectionReason, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def emit_all(
    classifications: Sequence[AttributeClassification],
    request_attributes: Sequence[RequestAttributeConfig],
    data_source_verdicts: Sequence[DataSourceVerdict],
    request_attribute_verdicts: Sequence[RequestAttributeVerdict],
) -> tuple[tuple[Artifact, ...], tuple[EmissionRejection, ...]]:
    """An Artifact for every Request Attribute that earned a body, and a rejection for every body
    a validity check refused."""
    bodies = {one.id: one.body for one in request_attributes}
    classified = {one.id: one for one in classifications}
    verdicts_by_attribute: dict[str, list[DataSourceVerdict]] = {}
    for verdict in data_source_verdicts:
        verdicts_by_attribute.setdefault(verdict.attribute_id, []).append(verdict)
    artifacts: list[Artifact] = []
    rejections: list[EmissionRejection] = []
    for attribute in request_attribute_verdicts:
        if attribute.verdict not in _EMITTED:
            continue
        try:
            artifacts.append(
                _artifact(
                    attribute,
                    classified[attribute.attribute_id],
                    bodies[attribute.attribute_id],
                    verdicts_by_attribute.get(attribute.attribute_id, []),
                )
            )
        except _Rejected as failure:
            rejections.append(
                EmissionRejection(
                    attribute.attribute_id,
                    classified[attribute.attribute_id].name,
                    failure.reason,
                    failure.detail,
                )
            )
    return tuple(artifacts), tuple(rejections)


def _artifact(
    attribute: RequestAttributeVerdict,
    classification: AttributeClassification,
    body: dict[str, Any],
    verdicts: Sequence[DataSourceVerdict],
) -> Artifact:
    """One Request Attribute's Artifact: the wrapper reasoning around the rebuilt body."""
    by_index = {one.data_source_index: one for one in verdicts}
    replacement = _replacement_body(body, classification, by_index)
    return Artifact(
        attribute.attribute_id,
        classification.name,
        attribute.verdict,
        attribute.reason,
        tuple(
            _reasoning(source, verdict, body)
            for source in classification.data_sources
            if (verdict := by_index.get(source.index)) is not None
        ),
        replacement,
    )


def _replacement_body(
    body: dict[str, Any],
    classification: AttributeClassification,
    by_index: dict[int, DataSourceVerdict],
) -> dict[str, Any]:
    """The complete `RequestAttributeDto` to emit: the original body, its Scopes rebuilt.

    Everything on the body other than the Scopes is copied through untouched, save the server-owned
    `metadata`, which is not part of a body the tool constructs.
    """
    rebuilt = {key: value for key, value in body.items() if key != "metadata"}
    originals = body.get("dataSources")
    originals = originals if isinstance(originals, list) else []
    emitted: list[dict[str, Any]] = []
    for source in classification.data_sources:
        verdict = by_index.get(source.index)
        produced = _emit_data_source(originals, source, verdict)
        if verdict is not None and verdict.verdict in _COVERED_LIKE and len(produced) > FAN_OUT_CAP:
            raise _Rejected(
                EmissionRejectionReason.DATA_SOURCES_OUT_OF_BOUNDS,
                f"Data Source {source.index} fans out into {len(produced)}, over the Fan-Out cap "
                f"of {FAN_OUT_CAP}",
            )
        emitted.extend(produced)
    rebuilt["dataSources"] = emitted
    _validate(rebuilt)
    return rebuilt


def _validate(body: dict[str, Any]) -> None:
    """The body's own schema constraints, checked before it is written.

    Against the DTO's constraints rather than a hand-kept list: `@Size(min=1, max=2000)` on
    `dataSources`, no server-owned `metadata`, no `serviceTechnology` left on an enabled Data Source
    (the one condition the API validator accepts and the runtime kills the Request Attribute over),
    and every emitted `processGroup` / `hostGroup` an id `ExpMEIdentifier.parse` accepts. The written
    Primary Tag is checked where it is written, not here, so a Neutralised Data Source keeping a
    non-primary tag copied through is not refused.
    """
    if "metadata" in body:
        raise _Rejected(
            EmissionRejectionReason.SERVER_OWNED_FIELD, "the body carries the server-owned metadata"
        )
    sources = body["dataSources"]
    if not 1 <= len(sources) <= 2000:
        raise _Rejected(
            EmissionRejectionReason.DATA_SOURCES_OUT_OF_BOUNDS,
            f"the body carries {len(sources)} Data Sources, outside the schema's 1..2000",
        )
    for source in sources:
        scope = source.get("scope") if isinstance(source, dict) else None
        _validate_scope(scope if isinstance(scope, dict) else {}, source.get("enabled") is True)


def _validate_scope(scope: dict[str, Any], enabled: bool) -> None:
    """One emitted Scope's schema constraints - the ones that hold whatever wrote the Scope."""
    if enabled and scope.get("serviceTechnology") is not None:
        raise _Rejected(
            EmissionRejectionReason.SERVICE_TECHNOLOGY_ON_ENABLED_SOURCE,
            f"an enabled Data Source carries serviceTechnology={scope['serviceTechnology']}",
        )
    for slot, me_type in (("processGroup", "PROCESS_GROUP"), ("hostGroup", "HOST_GROUP")):
        value = scope.get(slot)
        if value is not None and not _valid_me_id(value, me_type):
            raise _Rejected(
                EmissionRejectionReason.MALFORMED_ME_IDENTIFIER,
                f"{slot}={value!r} is not a {me_type}-<hex> id ExpMEIdentifier.parse accepts",
            )


def _emit_data_source(
    originals: Sequence[Any],
    source: DataSourceClassification,
    verdict: DataSourceVerdict | None,
) -> list[dict[str, Any]]:
    """The emitted Data Source(s) for one original.

    A covered replacement is emitted enabled with its Scope rebuilt - the Surviving Conditions
    carried through, the Deprecated Conditions gone, the harvested additions filling the free slots -
    and fans out into several Data Sources differing only in Scope where the candidate carries
    several values. Every other affected Data Source is Neutralised: emitted disabled with its
    original Scope unchanged, so a human can see what it was meant to do and recovery is a single
    `enabled` edit. A Data Source the run never resolved carries nothing Phase 3 stops and is copied
    through untouched.
    """
    raw = originals[source.index] if source.index < len(originals) else {}
    original = dict(raw) if isinstance(raw, dict) else {}
    if verdict is None:
        return [original]
    if verdict.verdict in _COVERED_LIKE:
        return [
            {**original, "scope": scope, "enabled": True}
            for scope in _replacement_scopes(source.scope, _wire_scope(original), verdict.candidate)
        ]
    return [{**original, "enabled": False}]


def _replacement_scopes(
    scope: Scope, wire: dict[str, Any], candidate: Candidate | None
) -> list[dict[str, Any]]:
    """The replacement Scope(s) for one covered Data Source: Surviving Conditions plus the candidate.

    The Surviving Conditions are carried through unchanged - a surviving Primary Tag as its original
    wire string, so the customer's exact value is preserved - and the candidate fills the free slots:
    a Fan-Out over process groups, a host group, or a Primary Tag fanned out one Data Source per
    value. The Deprecated Conditions never appear, because the base is built from the surviving
    fields alone.
    """
    base: dict[str, Any] = {}
    if scope.process_group is not None:
        base["processGroup"] = scope.process_group
    if scope.host_group is not None:
        base["hostGroup"] = scope.host_group
    if scope.surviving_tag is not None:
        base["tagOfProcessGroup"] = wire.get("tagOfProcessGroup")
    if candidate is None:
        return [base]
    if candidate.fan_out:
        return [{**base, "processGroup": pg} for pg in candidate.fan_out]
    if candidate.primary_tag:
        entity = {**base, **({"hostGroup": candidate.host_group} if candidate.host_group else {})}
        return [
            {**entity, "tagOfProcessGroup": _serialise_tag(_checked_tag(tag))}
            for tag in candidate.primary_tag
        ]
    if candidate.host_group is not None:
        return [{**base, "hostGroup": candidate.host_group}]
    return [base]


def _wire_scope(original: dict[str, Any]) -> dict[str, Any]:
    """One emitted Data Source's original wire Scope, for the Surviving tag it stores verbatim."""
    scope = original.get("scope")
    return scope if isinstance(scope, dict) else {}


def _reasoning(
    source: DataSourceClassification,
    verdict: DataSourceVerdict,
    body: dict[str, Any],
) -> DataSourceReasoning:
    """The wrapper's reasoning for one Data Source: its conditions, verdict, and match."""
    deprecated, surviving = _conditions(source.scope, _scope_of(body, source.index))
    return DataSourceReasoning(
        source.index,
        verdict.verdict,
        verdict.reason,
        verdict.detail,
        deprecated_conditions=deprecated,
        surviving_conditions=surviving,
        match_exact=verdict.verdict in _COVERED_LIKE,
        note=verdict.note,
        dormant=verdict.dormant,
    )


def _scope_of(body: dict[str, Any], index: int) -> dict[str, Any]:
    """The original wire Scope dict of one Data Source, for the tag strings it stores verbatim."""
    sources = body.get("dataSources")
    if not isinstance(sources, list) or index >= len(sources):
        return {}
    one = sources[index]
    scope = one.get("scope") if isinstance(one, dict) else None
    return scope if isinstance(scope, dict) else {}


def _conditions(scope: Scope, wire: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The Deprecated and Surviving Conditions of one Scope, as the wire strings a reader knows."""
    deprecated: list[str] = []
    if scope.service_technology is not None:
        deprecated.append(f"serviceTechnology={scope.service_technology}")
    if scope.deprecated_tag is not None:
        deprecated.append(f"tagOfProcessGroup={wire.get('tagOfProcessGroup')}")
    surviving: list[str] = []
    if scope.process_group is not None:
        surviving.append(f"processGroup={scope.process_group}")
    if scope.host_group is not None:
        surviving.append(f"hostGroup={scope.host_group}")
    if scope.surviving_tag is not None:
        surviving.append(f"tagOfProcessGroup={wire.get('tagOfProcessGroup')}")
    return tuple(deprecated), tuple(surviving)


def _checked_tag(tag: Tag) -> Tag:
    """One written Primary Tag, refused unless it is a tag the API validator accepts and can store.

    Scoped to the tags the migrator **writes** - a Surviving tag copied through onto a Neutralised
    Data Source is not checked here, so a `partially-covered` body keeping a non-primary tag on a
    disabled Data Source is emitted rather than refused. The context is the load-bearing one: a
    prefix changes the stored value without changing what matches, and an unrecognised one turns the
    tag back into a Deprecated Condition. The colon-in-key is the one representability rule that
    bites - `asString()` escapes nothing, so a key colon cannot round-trip.
    """
    if tag.context != CONTEXTLESS:
        raise _Rejected(
            EmissionRejectionReason.CONTEXT_PREFIX_ON_EMITTED_TAG,
            f"the written tag carries the context {tag.context}",
        )
    if not tag.key.startswith(PRIMARY_TAG_PREFIX) or len(tag.key) <= len(PRIMARY_TAG_PREFIX):
        raise _Rejected(
            EmissionRejectionReason.NON_PRIMARY_EMITTED_TAG,
            f"the written tag key {tag.key!r} is not a Primary Tag longer than {PRIMARY_TAG_PREFIX!r}",
        )
    if ":" in tag.key:
        raise _Rejected(
            EmissionRejectionReason.UNREPRESENTABLE_TAG_KEY,
            f"the written tag key {tag.key!r} carries a colon and cannot round-trip",
        )
    return tag


def _serialise_tag(tag: Tag) -> str:
    """One written Primary Tag as the runtime reads it: the bare key, its value colons escaped.

    No context prefix - the candidate tag is `CONTEXTLESS` by construction, so `keyAsString()` is
    the bare key. Escaping a colon in the value is a no-op the server undoes on the way back, kept
    because it is what a human would write and it round-trips through `parse_tag`.
    """
    if tag.value is None:
        return tag.key
    return f"{tag.key}:{tag.value.replace(':', chr(92) + ':')}"


def _valid_me_id(value: Any, me_type: str) -> bool:
    """Whether an emitted entity-side id is one `ExpMEIdentifier.parse` accepts for this slot.

    The type segment exactly as the entity read returned it - the slot's own upper-case type, since
    `parse` does not upper-case it the way `fromString` does - and an id of one to sixteen hex
    digits, read case-insensitively.
    """
    if not isinstance(value, str) or "-" not in value:
        return False
    type_segment, _, identifier = value.partition("-")
    return (
        type_segment == me_type
        and 1 <= len(identifier) <= 16
        and all(char in _HEX for char in identifier)
    )
