"""Deciding, from the configuration object alone, which request attributes Phase 3 stops.

Nothing here issues a query: everything a verdict rests on is in the body the reader returned.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from ..clients.transports import RequestAttributeConfig
from ..reporting.outcomes import AffectedReason, AttributeClass, DataSourceNote, UnprocessableReason
from .tags import Tag, is_bare_prefix, is_primary, parse_tag

# The capture location that targets client-side external calls only. Phase 3 deletes those, so a
# data source carrying it captures nothing that survives - and the test keys on the location
# alone, because no `source` is external-only.
_EXTERNAL_ONLY = "CAPTURE_AND_STORE_ON_CLIENT"
# Captures on the external service call and on the full one. Phase 3 takes the first half away,
# so it migrates like any other data source while quietly capturing less than it used to.
_BOTH_SIDES = "CAPTURE_AND_STORE_ON_BOTH"

# The four sources no capturing processor exists for - the whole processor-less set, not a
# sample. A data source on one of them captures nothing, and the backend drops it before it
# looks at its conditions, so it can never stop its request attribute either.
_WITHOUT_PROCESSOR = frozenset(
    {
        "HTTP_REQUEST_JSON_BODY",
        "HTTP_RESPONSE_JSON_BODY",
        "HTTP_REQUEST_XML_BODY",
        "HTTP_RESPONSE_XML_BODY",
    }
)

# Every condition a scope can hold. A scope carrying anything else is a shape this tool has
# never been shown, and reading it as though the unknown condition were not there would report a
# narrower scope as a wider one - so it is refused by name instead.
_SCOPE_CONDITIONS = frozenset(
    {"serviceTechnology", "processGroup", "hostGroup", "tagOfProcessGroup"}
)


class _Unclassifiable(Exception):
    """One request attribute this tool cannot read. Costs one row, never the run."""

    def __init__(self, reason: UnprocessableReason, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Scope:
    """The conditions one data source captures under, as the tenant stores them.

    Four exist and they are AND-ed. The surviving ones are carried forward rather than
    discarded: a later stage evaluates them on both sides of the comparison.
    """

    service_technology: str | None = None
    process_group: str | None = None
    host_group: str | None = None
    deprecated_tag: Tag | None = None
    surviving_tag: Tag | None = None
    # Which of its conditions Phase 3 rejects, as reasons rather than as a flag: a technology
    # problem and a tag problem call for different work.
    reasons: tuple[AffectedReason, ...] = field(default=())


@dataclass(frozen=True)
class DataSourceClassification:
    """One data source, read for what decides its request attribute's bucket."""

    index: int
    enabled: bool
    scope: Scope = field(default_factory=Scope)
    # Whether a capturing processor exists for its source at all.
    captures: bool = True
    # Captures onto the external service call only, which Phase 3 deletes. Decided from the
    # capture location alone: no `source` is external-only.
    obsolete: bool = False
    # What is true of this data source beyond its verdict, for the report to render.
    notes: tuple[DataSourceNote, ...] = field(default=())

    @property
    def affecting(self) -> bool:
        """Whether this data source alone would stop its request attribute under Phase 3.

        Both gates come from the backend's own evaluation order: a disabled data source and one
        with no processor are dropped before its conditions are examined, so neither can make
        its request attribute affected however deprecated its scope is.
        """
        return self.enabled and self.captures and bool(self.scope.reasons)


@dataclass(frozen=True)
class AttributeClassification:
    """One request attribute's bucket, and what put it there."""

    id: str
    name: str
    enabled: bool
    verdict: AttributeClass
    data_sources: tuple[DataSourceClassification, ...] = field(default=())
    reasons: tuple[AffectedReason, ...] = field(default=())
    # Why this one could not be classified, and what went wrong, so a run that could not read
    # everything says so instead of quietly reporting a smaller tenant.
    unprocessable_reason: UnprocessableReason | None = None
    detail: str = ""

    @property
    def carries_deprecated(self) -> bool:
        """Whether Phase 3 would stop it, asked without regard for whether it is enabled.

        A disabled request attribute is never affected - but re-enabling one after Phase 3 gives
        a request attribute that does not capture, so the figure is worth reporting.
        """
        return bool(self.reasons)


def classify(config: RequestAttributeConfig) -> AttributeClassification:
    """Which bucket one request attribute falls into, and why."""
    try:
        data_sources = _data_sources_of(config)
    except _Unclassifiable as failure:
        return _unprocessable(config, failure.reason, failure.detail)
    except Exception as failure:  # pylint: disable=broad-exception-caught
        # Whatever the surprise was, it belongs to this one configuration. A run against a
        # tenant holding hundreds is worthless if the first one it cannot make sense of ends it.
        return _unprocessable(config, UnprocessableReason.MALFORMED_BODY, str(failure))
    reasons = _reasons_of(data_sources)
    verdict = _verdict(config.enabled, data_sources, reasons)
    return AttributeClassification(
        config.id, config.name, config.enabled, verdict, data_sources, reasons
    )


def _unprocessable(
    config: RequestAttributeConfig, reason: UnprocessableReason, detail: str
) -> AttributeClassification:
    return AttributeClassification(
        config.id,
        config.name,
        config.enabled,
        AttributeClass.UNPROCESSABLE,
        unprocessable_reason=reason,
        detail=detail,
    )


def _data_sources_of(
    config: RequestAttributeConfig,
) -> tuple[DataSourceClassification, ...]:
    """Every data source of a body shaped the way the API says a body it returns is shaped.

    A body that is not is refused rather than read around: the API rejects an absent `enabled`
    at either level and never answers with one, so reading an absent flag as `true` would be
    inventing a request attribute the tenant does not hold.
    """
    if config.read_error is not None:
        raise _Unclassifiable(UnprocessableReason.BODY_UNREADABLE, config.read_error)
    if not isinstance(config.body.get("enabled"), bool):
        raise _Unclassifiable(UnprocessableReason.MALFORMED_BODY, "no enabled flag")
    sources = config.body.get("dataSources")
    if not isinstance(sources, list):
        raise _Unclassifiable(UnprocessableReason.MALFORMED_BODY, "no data sources")
    return tuple(_classify_data_source(index, one) for index, one in enumerate(sources))


def _verdict(
    enabled: bool,
    data_sources: tuple[DataSourceClassification, ...],
    reasons: tuple[AffectedReason, ...],
) -> AttributeClass:
    """The funnel's order, and the reason the buckets are disjoint.

    Obsolescence is decided before affectedness: an obsolete request attribute is reported for
    deletion, so counting it as affected as well would put one request attribute in two buckets
    and promise a migration nobody wants.
    """
    if not enabled:
        return AttributeClass.DISABLED
    if _obsolete(data_sources):
        return AttributeClass.OBSOLETE
    return AttributeClass.AFFECTED if reasons else AttributeClass.UNAFFECTED


def _obsolete(data_sources: tuple[DataSourceClassification, ...]) -> bool:
    """Nothing it captures survives Phase 3, so the recommended action is deletion."""
    capturing = [one for one in data_sources if one.enabled]
    if not capturing:
        # Stated rather than left to a vacuous `all`: a request attribute with no enabled data
        # source captures nothing today and nothing Phase 3 would keep, which is the same
        # recommendation for the same reason.
        return True
    return all(one.obsolete for one in capturing)


def classify_all(
    configs: Iterable[RequestAttributeConfig],
) -> tuple[AttributeClassification, ...]:
    return tuple(classify(config) for config in configs)


def _classify_data_source(index: int, body: Any) -> DataSourceClassification:
    if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
        raise _Unclassifiable(
            UnprocessableReason.MALFORMED_BODY, f"data source {index} carries no enabled flag"
        )
    scope = _read_scope(index, body.get("scope"))
    location = body.get("capturingAndStorageLocation")
    captures = body.get("source") not in _WITHOUT_PROCESSOR
    return DataSourceClassification(
        index=index,
        enabled=body.get("enabled") is True,
        scope=scope,
        captures=captures,
        obsolete=location == _EXTERNAL_ONLY,
        notes=_notes_of(scope, captures=captures, location=location),
    )


def _notes_of(
    scope: Scope, *, captures: bool, location: Any
) -> tuple[DataSourceNote, ...]:
    """What this data source is worth saying beyond how it came out."""
    notes: list[DataSourceNote] = []
    if not captures:
        notes.append(DataSourceNote.NO_CAPTURING_PROCESSOR)
    if location == _BOTH_SIDES:
        notes.append(DataSourceNote.EXTERNAL_HALF_LOST)
    if is_bare_prefix(scope.surviving_tag):
        notes.append(DataSourceNote.BARE_PRIMARY_TAG_PREFIX)
    return tuple(notes)


def _read_scope(index: int, raw: Any) -> Scope:
    """The four conditions, refused by name where the scope holds one outside them.

    The tag is read through the backend's own parser and judged on the key that comes out of
    it: judging the stored string instead reports a context-prefixed primary tag as deprecated.
    """
    conditions = _conditions_of(index, raw)
    reasons: list[AffectedReason] = []
    technology = conditions.get("serviceTechnology")
    if technology is not None:
        reasons.append(AffectedReason.SERVICE_TECHNOLOGY)
    stored_tag = conditions.get("tagOfProcessGroup")
    tag = parse_tag(stored_tag)
    surviving_tag = tag if is_primary(tag) else None
    deprecated_tag = None
    if stored_tag is not None and surviving_tag is None:
        deprecated_tag = tag
        reasons.append(AffectedReason.NON_PRIMARY_PROCESS_GROUP_TAG)
    return Scope(
        service_technology=technology,
        process_group=conditions.get("processGroup"),
        host_group=conditions.get("hostGroup"),
        deprecated_tag=deprecated_tag,
        surviving_tag=surviving_tag,
        reasons=tuple(reasons),
    )


def _conditions_of(index: int, raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise _Unclassifiable(
            UnprocessableReason.MALFORMED_BODY, f"data source {index} carries no readable scope"
        )
    unknown = sorted(str(condition) for condition in raw if condition not in _SCOPE_CONDITIONS)
    if unknown:
        raise _Unclassifiable(
            UnprocessableReason.UNCLASSIFIABLE_SCOPE,
            f"data source {index} carries unknown scope condition(s): {', '.join(unknown)}",
        )
    return raw


def _reasons_of(
    data_sources: Iterable[DataSourceClassification],
) -> tuple[AffectedReason, ...]:
    """Every reason its data sources carry, once each: the funnel counts request attributes."""
    found = [reason for one in data_sources if one.affecting for reason in one.scope.reasons]
    return tuple(reason for reason in AffectedReason if reason in found)
