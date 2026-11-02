"""Condition attribute mapping — types, data, and convenience accessors.

All mapping data is hardcoded as Python literals below. Edit this file
directly to fix mapping issues.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Literal

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Phase3Status = Literal["safe", "deprecated", "partial"]


@dataclass(frozen=True)
class AttributeRow:
    """Base row for attribute mapping data."""

    api_attribute: str
    dql_key: str | None
    matcher_type: str
    array_valued: bool
    phase3_status: Phase3Status
    candidate_eligible: bool
    candidate_quality: str = "good"  # "good" | "suboptimal"


@dataclass(frozen=True)
class EntityAttributeRow(AttributeRow):
    """Entity-side attribute row.  ``fetch_source`` identifies which DT entity
    type backs this attribute."""

    fetch_source: Literal["dt.entity.service", "dt.entity.process_group"] = (
        "dt.entity.service"
    )


@dataclass(frozen=True)
class SpanAttributeRow(AttributeRow):
    """Span-side attribute row.  Used as a type tag in isinstance() checks."""


@dataclass(frozen=True)
class ScopePartition:
    """A single service-type/api-attribute partition entry."""

    service_type: str
    api_attribute: str


@dataclass(frozen=True)
class ScopeAwareEntry:
    """DQL keys whose API-attribute mapping depends on the service type."""

    default_api_attribute: str | None
    partitions: tuple[ScopePartition, ...]
    mixed_behavior: Literal[
        "unmigratable", "narrower_wins", "default_unless_scoped", "default_only"
    ]


# ---------------------------------------------------------------------------
# Composite attributes
# ---------------------------------------------------------------------------

# Separator for composite attributes such as
# ``PROCESS_GROUP_TAG@primary_tags.team``. ``PROCESS_GROUP_TAG`` is one attribute
# serving arbitrarily many tag keys, so the key has to be part of the candidate's
# identity. ``@`` cannot occur in an api_attribute (those are UPPER_SNAKE), while
# tag keys are arbitrary text — hence every split is on the *first* separator only.
_COMPOSITE_SEP = "@"


def compose_attribute(base: str, tag_key: str) -> str:
    """Build the composite ``BASE@tag_key`` attribute identity."""
    return f"{base}{_COMPOSITE_SEP}{tag_key}"


def base_attribute(api_attribute: str) -> str:
    """Return the base attribute of a possibly-composite identity.

    Plain attributes pass through unchanged.
    """
    return api_attribute.split(_COMPOSITE_SEP, 1)[0]


def split_attribute(api_attribute: str) -> tuple[str, str | None]:
    """Split a composite identity into ``(base, tag_key)``.

    ``tag_key`` is ``None`` for a plain attribute.
    """
    base, sep, tag_key = api_attribute.partition(_COMPOSITE_SEP)
    return base, tag_key if sep else None


# ---------------------------------------------------------------------------
# ConditionMapping
# ---------------------------------------------------------------------------


class ConditionMapping:
    """Container for all mapping data with O(1) convenience accessors."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        ignored_attributes: frozenset[str],
        negation_forbidden: frozenset[str],
        exists_forbidden: frozenset[str],
        unmigratable_as_candidates: frozenset[str],
        entity_attributes: tuple[EntityAttributeRow, ...],
        span_attributes: tuple[SpanAttributeRow, ...],
        scope_aware_partitions: dict[str, ScopeAwareEntry],
    ) -> None:
        self.ignored_attributes = ignored_attributes
        self.negation_forbidden = negation_forbidden
        self.exists_forbidden = exists_forbidden
        self.unmigratable_as_candidates = unmigratable_as_candidates
        self.entity_attributes = entity_attributes
        self.span_attributes = span_attributes
        self.scope_aware_partitions = scope_aware_partitions

    @cached_property
    def _by_api(self) -> dict[str, AttributeRow]:
        """O(1) index: api_attribute → AttributeRow (built once on first access)."""
        return {r.api_attribute: r for r in (*self.entity_attributes, *self.span_attributes)}

    def by_api_attribute(self, api_attribute: str) -> AttributeRow | None:
        """Return the AttributeRow for the given api_attribute, or None.

        Accepts a composite ``BASE@tag_key`` attribute and resolves it to the row
        of its base attribute, so callers never need to strip the suffix
        themselves — an unstripped lookup would silently return ``None``.
        """
        return self._by_api.get(base_attribute(api_attribute))

    def is_entity(self, api_attribute: str) -> bool:
        """Return True when api_attribute maps to an entity-side attribute."""
        return isinstance(self._by_api.get(api_attribute), EntityAttributeRow)

    def is_span(self, api_attribute: str) -> bool:
        """Return True when api_attribute maps to a span-side attribute."""
        row = self._by_api.get(api_attribute)
        return row is not None and not isinstance(row, EntityAttributeRow)

    def dql_key_index(self, *, candidate_eligible_only: bool = False) -> dict[str, str]:
        """Map dql_key → api_attribute across all attribute rows.

        Duplicate dql_keys are resolved first-wins (entity rows precede span rows).
        Pass ``candidate_eligible_only=True`` to restrict to candidate-eligible rows.
        """
        result: dict[str, str] = {}
        for row in (*self.entity_attributes, *self.span_attributes):
            if candidate_eligible_only and not row.candidate_eligible:
                continue
            if row.dql_key is None or row.dql_key in result:
                continue
            result[row.dql_key] = row.api_attribute
        return result

    def is_negation_forbidden(self, api_attribute: str) -> bool:
        """Return True when negation is not allowed for api_attribute."""
        return base_attribute(api_attribute) in self.negation_forbidden


# ---------------------------------------------------------------------------
# Mapping data
# ---------------------------------------------------------------------------

# Comparison operators allowed per matcher type.  Not a field on
# ConditionMapping (never consumed at runtime) but kept as a module-level
# constant for tests and future tooling.
COMPARISON_MATCHERS: dict[str, tuple[str, ...]] = {
    "STRING": (
        "EQUALS", "BEGINS_WITH", "ENDS_WITH", "CONTAINS",
        "REGEX_MATCHES", "EXISTS", "EQUALS_ANY_OF",
        "BEGINS_WITH_ANY_OF", "ENDS_WITH_ANY_OF",
    ),
    "NUMBER": (
        "EQUALS", "GREATER_THAN", "LOWER_THAN",
        "GREATER_THAN_OR_EQUAL", "LOWER_THAN_OR_EQUAL",
        "EXISTS", "EQUALS_ANY_OF",
    ),
    "BOOLEAN":          ("EQUALS", "EXISTS", "EQUALS_ANY_OF"),
    "HTTP_METHOD":      ("EQUALS", "EXISTS", "EQUALS_ANY_OF"),
    "HTTP_STATUS_CLASS": ("EQUALS", "EXISTS", "EQUALS_ANY_OF"),
    "SERVICE_TYPE":     ("EQUALS", "EXISTS", "EQUALS_ANY_OF"),
    "ZOS_TRANSACTIONTYPE": ("EQUALS", "EXISTS", "EQUALS_ANY_OF"),
    "TAG":              ("EQUALS", "TAG_KEY_EQUALS", "EQUALS_ANY_OF", "TAG_KEY_EQUALS_ANY_OF"),
    "FAST_STRING":      ("EQUALS", "CONTAINS", "EQUALS_ANY_OF"),
}

# Shorthand aliases for the row constructors — keeps the data section concise.
# Constructor arg order for EntityAttributeRow:
#   (api_attribute, dql_key, matcher_type, array_valued, phase3_status,
#    candidate_eligible, fetch_source)
# Constructor arg order for SpanAttributeRow:
#   (api_attribute, dql_key, matcher_type, array_valued, phase3_status,
#    candidate_eligible)

_SVC = "dt.entity.service"
_PG  = "dt.entity.process_group"


def _e(
    api: str,
    dql: str | None,
    mt: str,
    av: bool,
    st: Phase3Status,
    ce: bool,
    fs: Literal["dt.entity.service", "dt.entity.process_group"] = "dt.entity.service",
    quality: str = "good",
) -> EntityAttributeRow:
    return EntityAttributeRow(
        api_attribute=api,
        dql_key=dql,
        matcher_type=mt,
        array_valued=av,
        phase3_status=st,
        candidate_eligible=ce,
        candidate_quality=quality,
        fetch_source=fs,
    )


def _s(
    api: str,
    dql: str | None,
    mt: str,
    av: bool,
    st: Phase3Status,
    ce: bool,
    quality: str = "good",
) -> SpanAttributeRow:
    return SpanAttributeRow(
        api_attribute=api,
        dql_key=dql,
        matcher_type=mt,
        array_valued=av,
        phase3_status=st,
        candidate_eligible=ce,
        candidate_quality=quality,
    )


def _p(service_type: str, api_attribute: str) -> ScopePartition:
    return ScopePartition(service_type, api_attribute)


_MAPPING = ConditionMapping(
    ignored_attributes=frozenset({
        "ESB_INPUT_TYPE",
        "FLAW_STATE",
        "IIB_INPUT_TYPE",
        "ONE_AGENT_ATTRIBUTE",
        "REQUEST_NAME",
        "REQUEST_TYPE",
        "RESPONSE_TIME",
        "RESPONSE_TIME_CLIENT",
        "SERVICE_PORT",
        "SERVICE_PUBLIC_DOMAIN_NAME",
        "SERVICE_REQUEST_ATTRIBUTE",
    }),
    # The API rejects negate=true for every ME-index attribute:
    # ConditionSpecificationValidator.noNegationForMEIndex refuses any condition
    # whose attribute declares isIndexCondition() in MethodAttribute. That is
    # exactly these five — verified against the cluster sources, not inferred.
    negation_forbidden=frozenset({
        "SERVICE_DISPLAY_NAME",
        "SERVICE_TYPE",
        "SERVICE_TAG",
        "PROCESS_GROUP_TAG",
        "PROCESS_GROUP_NAME",
    }),
    exists_forbidden=frozenset({
        "SERVICE_NAME",
        "SERVICE_TYPE",
    }),
    unmigratable_as_candidates=frozenset({
        "IS_KEY_REQUEST",
    }),
    entity_attributes=(
        #              api_attribute               dql_key               mt            av     status    ce    fetch_source
        _e("SERVICE_DISPLAY_NAME",       "entity.name",          "FAST_STRING", False, "safe",       True,  _SVC),
        _e("SERVICE_TYPE",               "serviceType",          "SERVICE_TYPE",False, "safe",       True,  _SVC),
        _e("SERVICE_TAG",                "tags",                 "TAG",         True,  "deprecated", False, _SVC),
        _e("PROCESS_GROUP_NAME",         "entity.name",          "FAST_STRING", False, "safe",       True,  _PG),
        _e("PROCESS_GROUP_TAG",          "tags",                 "TAG",         True,  "partial",    False, _PG),
        _e("SERVICE_WEB_APPLICATION_ID", "webApplicationId",     "STRING",      False, "safe",       True,  _SVC),
        _e("SERVICE_WEB_CONTEXT_ROOT",   "contextRoot",          "STRING",      False, "safe",       True,  _SVC),
        _e("SERVICE_WEB_SERVER_NAME",    "webServerName",        "STRING",      False, "safe",       True,  _SVC),
        _e("SERVICE_WEB_SERVICE_NAME",   "webServiceName",       "STRING",      False, "safe",       True,  _SVC),
        _e("SERVICE_WEB_SERVICE_NAMESPACE", "webServiceNamespace", "STRING",    False, "safe",       True,  _SVC),
        _e("ESB_APPLICATION_NAME",       "esbApplicationName",   "STRING",      False, "safe",       True,  _SVC),
        _e("IIB_APPLICATION_NAME",       "esbApplicationName",   "STRING",      False, "safe",       True,  _SVC),
        _e("APPLICATION_BUILD_VERSION",  "applicationBuildVersion", "STRING",   True,  "safe",       False, _SVC),
        _e("APPLICATION_RELEASE_VERSION","applicationReleaseVersion","STRING",  True,  "safe",       False, _SVC),
        _e("APPLICATION_NAME",           "applicationName",      "STRING",      True,  "safe",       True,  _SVC),
        _e("APPLICATION_ENVIRONMENT",    "applicationEnvironment","STRING",     True,  "safe",       True,  _SVC),
    ),
    span_attributes=(
        #              api_attribute              dql_key                        mt                av     status  ce
        _s("WEBREQUEST_URL",              "dt_webrequest_url",           "STRING",          False, "safe", True),
        _s("WEBREQUEST_RELATIVE_URL",     None,                          "STRING",          False, "safe", False),
        _s("WEBREQUEST_URL_PATH",         "url.path",                    "STRING",          False, "safe", True),
        _s("WEBREQUEST_URL_HOST",         "server.address",              "STRING",          False, "safe", True),
        _s("WEBREQUEST_URL_PORT",         "server.port",                 "NUMBER",          False, "safe", True),
        _s("WEBREQUEST_QUERY",            "url.query",                   "STRING",          False, "safe", True),
        _s("HTTP_REQUEST_METHOD",         "http.request.method",         "HTTP_METHOD",     False, "safe", True,  "suboptimal"),
        _s("HTTP_STATUS",                 "http.response.status_code",   "NUMBER",          False, "safe", True,  "suboptimal"),
        _s("HTTP_STATUS_CLASS",           "http.response.status_code",   "HTTP_STATUS_CLASS",False,"safe", True,  "suboptimal"),
        _s("SERVICE_NAME",                "dt.service.name",             "STRING",          False, "safe", True),
        _s("WEBSERVICE_ENDPOINT",         "entity.name",                 "STRING",          False, "safe", True),
        _s("WEBSERVICE_METHOD",           "rpc.method",                  "STRING",          False, "safe", True),
        _s("IS_KEY_REQUEST",              "supportability.is_non_key_requests_endpoint_bucket",
                                                                         "BOOLEAN",         False, "safe", False),
        _s("CUSTOMSERVICE_CLASS",         "custom_service.name",         "STRING",          False, "safe", True),
        _s("CUSTOMSERVICE_METHOD",        "custom_service.method",       "STRING",          False, "safe", True),
        _s("MESSAGING_QUEUE_NAME",        "messaging.destination.name",  "STRING",          False, "safe", True),
        _s("MESSAGING_QUEUE_VENDOR",      "messaging.system",            "STRING",          False, "safe", True),
        _s("MESSAGING_DESTINATION_TYPE",  "messaging.destination.kind",  "STRING",          False, "safe", True),
        _s("MESSAGING_IS_TEMPORARY_QUEUE","messaging.destination.temporary","BOOLEAN",      False, "safe", True),
        _s("ZOS_CALL_TYPE",               "zos.transaction.call_type",   "ZOS_TRANSACTIONTYPE",False,"safe",True),
        _s("CICS_TRANSACTION_ID",         "zos.transaction.id",          "STRING",          False, "safe", True),
        _s("CICS_TASK_ID",                "cics.transaction.task_id",    "NUMBER",          False, "safe", True),
        _s("CICS_SYSTEM_ID",              "cics.transaction.system_id",  "STRING",          False, "safe", True),
        _s("CICS_PROGRAM_NAME",           "ibm.cics.program",            "STRING",          False, "safe", True),
        _s("CICS_USER_ID",                "cics.transaction.user_id",    "STRING",          False, "safe", True),
        _s("IMS_TRANSACTION_ID",          "zos.transaction.id",          "STRING",          False, "safe", True),
        _s("IMS_PROGRAM_NAME",            "ims.execution.transaction.psb_name","STRING",    False, "safe", True),
        _s("IMS_USER_ID",                 "ims.message.transaction.user_id",  "STRING",     False, "safe", True),
        _s("RMI_CLASS",                   "rpc.service",                 "STRING",          False, "safe", True),
        _s("RMI_METHOD",                  "rpc.method",                  "STRING",          False, "safe", True),
        _s("ESB_MESSAGE_FLOW_NAME",       "esb.workflow.name",           "STRING",          False, "safe", True),
        _s("ESB_LIBRARY_NAME",            "esb.library.name",            "STRING",          False, "safe", True),
        _s("IIB_MESSAGE_FLOW_NAME",       "esb.workflow.name",           "STRING",          False, "safe", True),
        _s("IIB_LIBRARY_NAME",            "esb.library.name",            "STRING",          False, "safe", True),
        _s("ERROR_COUNT",                 "error.exception_count",       "NUMBER",          False, "safe", True,  "suboptimal"),
        _s("EXCEPTION_CLASS",             "exception.type",              "STRING",          False, "safe", True,  "suboptimal"),
        _s("EXCEPTION_MESSAGE",           "exception.message",           "STRING",          False, "safe", True,  "suboptimal"),
    ),
    scope_aware_partitions={
        "rpc.method": ScopeAwareEntry(
            default_api_attribute=None,
            partitions=(_p("RMI_SERVICE", "RMI_METHOD"), _p("WEB_SERVICE", "WEBSERVICE_METHOD")),
            mixed_behavior="unmigratable",
        ),
        "entity.name": ScopeAwareEntry(
            default_api_attribute="SERVICE_DISPLAY_NAME",
            partitions=(_p("WEB_SERVICE", "WEBSERVICE_ENDPOINT"),),
            mixed_behavior="narrower_wins",
        ),
        "zos.transaction.id": ScopeAwareEntry(
            default_api_attribute=None,
            partitions=(_p("CICS_SERVICE", "CICS_TRANSACTION_ID"), _p("IMS_SERVICE", "IMS_TRANSACTION_ID")),
            mixed_behavior="unmigratable",
        ),
        "url.path": ScopeAwareEntry(
            default_api_attribute="WEBREQUEST_URL_PATH",
            partitions=(),
            mixed_behavior="default_unless_scoped",
        ),
        "server.port": ScopeAwareEntry(
            default_api_attribute="WEBREQUEST_URL_PORT",
            partitions=(),
            mixed_behavior="default_only",
        ),
    },
)


def load_mapping() -> ConditionMapping:
    """Return the singleton condition mapping.  Call-site interface preserved."""
    return _MAPPING


__all__ = [
    "AttributeRow",
    "COMPARISON_MATCHERS",
    "base_attribute",
    "compose_attribute",
    "ConditionMapping",
    "EntityAttributeRow",
    "ScopeAwareEntry",
    "ScopePartition",
    "SpanAttributeRow",
    "load_mapping",
    "split_attribute",
]
