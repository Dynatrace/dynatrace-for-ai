"""The mapping catalog and the per-metric readiness verdict derived from it.

Ported unchanged in substance from the research artifact that built the catalog out of the
cluster source. Two things
live here:

* the catalog itself (``mapping-catalog.json``) — every classic measurement, condition
  attribute, comparison, dimension and top-level setting, each with a status and the reason
  behind it; and
* :func:`metric_report`, which reads one classic definition and says which of its parts have a
  Phase 3 equivalent, which do not, and which change behaviour.

No tenant is contacted from here. The verdict is a property of the definition and the catalog,
not of the environment: whether a mapped span field carries values was measured once while the
catalog was built and is not re-measured per scan.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_CATALOG = Path(__file__).resolve().parent / "mapping-catalog.json"

# Statuses that cannot yield a generated processor without further work.
BLOCKING = {"UNSUPPORTED", "CROSS_SPAN", "SEMANTIC_CHANGE", "UNCLASSIFIED"}

# Element kinds that are reported as a warning even when their catalog status is
# terminal. ``topX`` has no ingestion-time equivalent, but OpenPipeline extracts *all*
# dimension values -- a superset of what classic keeps. Only the ranking and limiting is
# lost, and a consumer can do that at query time. Treating it as a blocker marked every
# metric unmigratable and hid the genuine blockers.
WARNING_ONLY = {"topX"}

# Statuses that are migratable in principle but need evidence we do not have at catalog
# level: DIRECT_CONDITIONAL needs the field proven present on the tenant's spans,
# ENTITY_ENRICHED needs an entity/Smartscape lookup resolved at config-generation time, and
# DERIVED needs a preceding processor to be built and verified.
NEEDS_CHECK = {"DIRECT_CONDITIONAL", "ENTITY_ENRICHED", "DERIVED"}
TERMINAL = {"UNSUPPORTED", "CROSS_SPAN"}

PLACEHOLDER = re.compile(r"\{([A-Za-z]+):([^}]*)\}")


# Built-in dimension placeholder -> classic API condition attribute.
#
# Derived from the classic request-attribute enum, where every constant declares the
# placeholder name it is written as; the API condition attribute uses the same name
# except for the web-request family, which carries a ``WEBREQUEST_`` prefix. A
# placeholder with no condition-attribute counterpart (``HTTP-Method``, the
# ``Messaging:*`` and ``AKKA:*`` families, ``Service:Instance``, ``CTG:Program``) is
# deliberately absent: it stays ``UNCLASSIFIED`` and is reported by ``check_coverage``
# rather than silently approved.
PLACEHOLDER_ATTRIBUTE = {
    "AKKA:ActorSystem": "ACTOR_SYSTEM",
    "AzureFunctions:FunctionName": "AZURE_FUNCTIONS_FUNCTION_NAME",
    "AzureFunctions:SiteName": "AZURE_FUNCTIONS_SITE_NAME",
    "CICS:ProgramName": "CICS_PROGRAM_NAME",
    "CICS:SystemId": "CICS_SYSTEM_ID",
    "CICS:TaskId": "CICS_TASK_ID",
    "CICS:TransactionId": "CICS_TRANSACTION_ID",
    "CICS:UserId": "CICS_USER_ID",
    "CTG:GatewayURL": "CTG_GATEWAY_URL",
    "CTG:ServerName": "CTG_SERVER_NAME",
    "CTG:TransactionId": "CTG_TRANSACTION_ID",
    "CustomService:Class": "CUSTOMSERVICE_CLASS",
    "CustomService:Method": "CUSTOMSERVICE_METHOD",
    "Database-Statement": "DATABASE_STATEMENT",
    "Database:Host": "DATABASE_HOST",
    "Database:Name": "DATABASE_NAME",
    "Database:Type": "DATABASE_TYPE",
    "Database:URL": "DATABASE_URL",
    "ESB:ApplicationName": "ESB_APPLICATION_NAME",
    "ESB:LibraryName": "ESB_LIBRARY_NAME",
    "ESB:MessageFlowName": "ESB_MESSAGE_FLOW_NAME",
    "Exception:Class": "EXCEPTION_CLASS",
    "Exception:Message": "EXCEPTION_MESSAGE",
    "HTTP-Status": "HTTP_STATUS",
    "HTTP-StatusClass": "HTTP_STATUS_CLASS",
    "IMS:ProgramName": "IMS_PROGRAM_NAME",
    "IMS:TransactionId": "IMS_TRANSACTION_ID",
    "IMS:UserId": "IMS_USER_ID",
    "RMI:Class": "RMI_CLASS",
    "RMI:Method": "RMI_METHOD",
    "Relative-URL": "WEBREQUEST_RELATIVE_URL",
    "Remote:Endpoint": "REMOTE_ENDPOINT",
    "Remote:Method": "REMOTE_METHOD",
    "Remote:ServiceName": "REMOTE_SERVICE_NAME",
    "Request:ApplicationBuildVersion": "APPLICATION_BUILD_VERSION",
    "Request:ApplicationProduct": "APPLICATION_NAME",
    "Request:ApplicationReleaseVersion": "APPLICATION_RELEASE_VERSION",
    "Request:ApplicationStage": "APPLICATION_ENVIRONMENT",
    "Request:Failure": "FAILURE_REASON",
    "Request:IsKeyRequest": "IS_KEY_REQUEST",
    "Request:Name": "REQUEST_NAME",
    "Request:Type": "REQUEST_TYPE",
    "Service:Name": "SERVICE_NAME",
    "Service:Port": "SERVICE_PORT",
    "Service:PublicDomainName": "SERVICE_PUBLIC_DOMAIN_NAME",
    "Service:WebApplicationId": "SERVICE_WEB_APPLICATION_ID",
    "Service:WebContextRoot": "SERVICE_WEB_CONTEXT_ROOT",
    "Service:WebServerName": "SERVICE_WEB_SERVER_NAME",
    "Service:WebServiceName": "SERVICE_WEB_SERVICE_NAME",
    "Service:WebServiceNamespace": "SERVICE_WEB_SERVICE_NAMESPACE",
    "URL": "WEBREQUEST_URL",
    "URL:Host": "WEBREQUEST_URL_HOST",
    "URL:Path": "WEBREQUEST_URL_PATH",
    "URL:Path-Clean": "WEBREQUEST_URL_PATH_CLEAN",
    "URL:Port": "WEBREQUEST_URL_PORT",
    "URL:Query": "WEBREQUEST_QUERY",
    "WebService:Endpoint": "WEBSERVICE_ENDPOINT",
    "WebService:Method": "WEBSERVICE_METHOD",
}

# Worst-first precedence used to fold the several catalog rows that together decide a
# custom placeholder (its kind, normalization, child-call handling, aggregation and
# source) into one status for the dimension.
STATUS_SEVERITY = {
    "UNCLASSIFIED": 5,
    "UNSUPPORTED": 4,
    "CROSS_SPAN": 4,
    "SEMANTIC_CHANGE": 3,
    "DERIVED": 2,
    "ENTITY_ENRICHED": 2,
    "DIRECT_CONDITIONAL": 1,
    "DIRECT": 0,
}


def worst(statuses) -> str:
    return max(statuses, key=lambda s: STATUS_SEVERITY.get(s, 5))


def load_catalog(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def index(catalog: dict, name: str) -> dict[str, dict]:
    """Index a catalog by source.

    ``build_catalog.py`` strips backticks from every source, so lookups here must use
    the bare name. Keys are also registered under their backticked form so a stale
    lookup cannot silently miss and be reported as ``UNCLASSIFIED``.
    """
    items = {item["source"]: item for item in catalog["catalogs"][name]}
    return items | {f"`{source}`": item for source, item in items.items()}


def check_integrity(catalog: dict) -> list[str]:
    problems: list[str] = []
    known = set(catalog["statuses"])
    for name, items in catalog["catalogs"].items():
        if not items:
            problems.append(f"{name}: catalog is empty")
        seen: set[str] = set()
        for item in items:
            source = item["source"]
            if source in seen:
                problems.append(f"{name}: duplicate source key {source!r}")
            seen.add(source)
            if item["status"] not in known:
                problems.append(f"{name}/{source}: unknown status {item['status']!r}")
            if item["status"] in TERMINAL and item["targetFields"]:
                problems.append(
                    f"{name}/{source}: status {item['status']} must not name target fields "
                    f"({item['targetFields']})"
                )
    return problems


def definition_usage(definitions: list[dict]) -> dict[str, set[str]]:
    """Every catalog-relevant enum value that occurs in the fetched definitions."""
    used: dict[str, set[str]] = {
        "conditionAttributes": set(),
        "measurements": set(),
        "comparisons": set(),
        "comparisonTypes": set(),
        "units": set(),
        # Built-in {Kind:Name} dimension placeholders, and the catalog row names that a
        # custom placeholder's kind/normalization/child-call/aggregation settings resolve to.
        "placeholders": set(),
        "placeholderRows": set(),
    }
    for definition in definitions:
        dimension = definition.get("dimensionDefinition") or {}
        literal = (dimension.get("dimension") or "").strip()
        match = PLACEHOLDER.fullmatch(literal)
        if match and match.group(1) not in ("RequestAttribute",):
            used["placeholders"].add(match.group(0).strip("{}"))
        for placeholder in dimension.get("placeholders") or []:
            if placeholder.get("attribute"):
                used["conditionAttributes"].add(placeholder["attribute"])
            if placeholder.get("kind"):
                used["placeholderRows"].add(f"Placeholder kind: {placeholder['kind']}")
            if placeholder.get("normalization"):
                used["placeholderRows"].add(
                    f"Placeholder normalization: {placeholder['normalization']}")
            if placeholder.get("useFromChildCalls") is not None:
                used["placeholderRows"].add(
                    "Placeholder useFromChildCalls: "
                    + str(placeholder["useFromChildCalls"]).lower())
            if placeholder.get("aggregation"):
                used["placeholderRows"].add(
                    f"Placeholder aggregation: {placeholder['aggregation']}")
        measure = (definition.get("metricDefinition") or {}).get("metric")
        if measure:
            used["measurements"].add(measure)
        if definition.get("unit"):
            used["units"].add(definition["unit"])
        for condition in definition.get("conditions") or []:
            used["conditionAttributes"].add(condition["attribute"])
            info = condition.get("comparisonInfo") or {}
            if info.get("comparison"):
                used["comparisons"].add(info["comparison"])
            if info.get("type"):
                used["comparisonTypes"].add(info["type"])
    return used


def check_coverage(catalog: dict, used: dict[str, set[str]]) -> list[str]:
    problems: list[str] = []
    units = set(catalog["units"]["values"])
    for name in ("conditionAttributes", "measurements", "comparisons", "comparisonTypes"):
        known = set(index(catalog, name))
        for value in sorted(used[name] - known):
            problems.append(f"{name}: {value!r} occurs in a definition but is not in the catalog")
    for value in sorted(used["units"] - units):
        problems.append(f"units: {value!r} occurs in a definition but is not in the unit enum")
    # Dimensions were previously left out entirely, so a definition could use a built-in
    # placeholder or a placeholder kind that no catalog row covers and still get a clean
    # "coverage: ok" while the per-metric listing marked it UNCLASSIFIED.
    known_dimensions = set(index(catalog, "dimensions"))
    for value in sorted(used["placeholders"] - set(PLACEHOLDER_ATTRIBUTE)):
        problems.append(
            f"dimensions: built-in placeholder {{{value}}} occurs in a definition but has no "
            "condition attribute in PLACEHOLDER_ATTRIBUTE"
        )
    for value in sorted(used["placeholderRows"] - known_dimensions):
        problems.append(f"dimensions: {value!r} occurs in a definition but is not in the catalog")
    return problems


def dimension_status(catalog: dict, definition: dict) -> list[tuple[str, str, str]]:
    """Resolve the dimension definition to (element, source, status) triples."""
    attributes = index(catalog, "conditionAttributes")
    dimensions = index(catalog, "dimensions")
    result: list[tuple[str, str, str]] = []

    dimension = (definition.get("dimensionDefinition") or {})
    literal = dimension.get("dimension")
    if literal:
        match = PLACEHOLDER.fullmatch(literal.strip())
        if match is None:
            entry = dimensions.get("Literal dimensionDefinition.dimension, including All requests")
            result.append(("dimension", f"literal {literal!r}", entry["status"] if entry else "UNCLASSIFIED"))
        elif match.group(1) == "RequestAttribute":
            entry = attributes["SERVICE_REQUEST_ATTRIBUTE"]
            result.append(("dimension", f"request attribute {match.group(2)!r}", entry["status"]))
        else:
            # Every other built-in placeholder resolves through the condition-attribute
            # table, exactly as ``MetricPlaceholderDimEnricher`` does at runtime. Before
            # this lookup existed only ``{Request:Name}`` was recognised and every other
            # built-in placeholder was reported UNCLASSIFIED, which blocked metrics whose
            # dimension was already catalogued as a plain field mapping.
            attribute = PLACEHOLDER_ATTRIBUTE.get(match.group(0).strip("{}"))
            entry = dimensions.get("Built-in placeholder such as {Request:Name}")
            if attribute is None or entry is None:
                result.append(("dimension", literal, "UNCLASSIFIED"))
            else:
                result.append(
                    ("dimension", literal, worst([attributes[attribute]["status"], entry["status"]]))
                )

    if dimension.get("topX"):
        entry = dimensions.get("`topX`")
        result.append(("topX", str(dimension["topX"]), entry["status"] if entry else "UNCLASSIFIED"))
    for placeholder in dimension.get("placeholders") or []:
        result.append(
            ("placeholder", placeholder.get("name", "?"), placeholder_status(catalog, placeholder))
        )
    return result


def placeholder_status(catalog: dict, placeholder: dict) -> str:
    """Fold the catalog rows that jointly decide one custom ``{placeholder}``.

    A custom placeholder is not one catalog entry: its extraction ``kind``, its
    ``normalization``, whether it reads child calls, its ``aggregation`` and its
    ``source`` are catalogued separately, and the attribute it reads from is a
    condition attribute. The dimension is only as migratable as its worst part.
    """
    attributes = index(catalog, "conditionAttributes")
    dimensions = index(catalog, "dimensions")
    statuses = []

    base = dimensions.get("Custom {placeholder}")
    statuses.append(base["status"] if base else "UNCLASSIFIED")

    attribute = placeholder.get("attribute")
    if attribute:
        entry = attributes.get(attribute)
        statuses.append(entry["status"] if entry else "UNCLASSIFIED")

    rows = []
    if placeholder.get("kind"):
        rows.append(f"Placeholder kind: {placeholder['kind']}")
    if placeholder.get("normalization"):
        rows.append(f"Placeholder normalization: {placeholder['normalization']}")
    if placeholder.get("useFromChildCalls") is not None:
        rows.append(f"Placeholder useFromChildCalls: {str(placeholder['useFromChildCalls']).lower()}")
    if placeholder.get("aggregation"):
        rows.append(f"Placeholder aggregation: {placeholder['aggregation']}")
    if placeholder.get("source"):
        rows.append("Placeholder source.managementZone")
    for row in rows:
        entry = dimensions.get(row)
        statuses.append(entry["status"] if entry else "UNCLASSIFIED")

    return worst(statuses)


def placeholder_culprits(catalog: dict, placeholder: dict) -> list[tuple[str, str, str]]:
    """Which catalogued parts of a custom placeholder carry a blocking status.

    A custom ``{placeholder}`` is reported under the name the customer gave it -- and that
    name has no catalog row, so the report would show a blocker with no explanation. This
    names the part that is actually blocking, with its own catalog comment.
    """
    attributes = index(catalog, "conditionAttributes")
    dimensions = index(catalog, "dimensions")
    out: list[tuple[str, str, str]] = []

    def consider(source: str, entry: dict | None) -> None:
        status = entry["status"] if entry else "UNCLASSIFIED"
        if status in BLOCKING:
            # ``report_comment``, never ``comment``: this text is printed in the customer
            # report, and ``comment`` is an internal engineering note.
            out.append((source, status, (entry or {}).get("report_comment") or ""))

    consider("Custom {placeholder}", dimensions.get("Custom {placeholder}"))
    if placeholder.get("attribute"):
        consider(placeholder["attribute"], attributes.get(placeholder["attribute"]))
    for label, key in (("kind", "kind"), ("normalization", "normalization"),
                       ("aggregation", "aggregation")):
        if placeholder.get(key):
            row = f"Placeholder {label}: {placeholder[key]}"
            consider(placeholder[key], dimensions.get(row))
    if placeholder.get("useFromChildCalls") is not None:
        row = f"Placeholder useFromChildCalls: {str(placeholder['useFromChildCalls']).lower()}"
        consider(f"useFromChildCalls={str(placeholder['useFromChildCalls']).lower()}",
                 dimensions.get(row))
    if placeholder.get("source"):
        consider("source.managementZone", dimensions.get("Placeholder source.managementZone"))
    return out


# Phase 3 has no non-key requests, so a classic ``IS_KEY_REQUEST EQUALS true`` test is
# always satisfied and the condition is dropped (catalogued ``DIRECT``). The inverted
# test selects a set that cannot exist in Phase 3, so the metric would match nothing --
# that is a blocker, and the catalog cannot express it because it keys on the attribute
# name alone, not on the compared value.
def key_request_status(condition: dict, catalogued: str) -> str:
    info = condition.get("comparisonInfo") or {}
    selects_key_requests = bool(info.get("value")) != bool(info.get("negate"))
    return catalogued if selects_key_requests else "UNSUPPORTED"


# Individual enum *values* whose status differs from the comparison *type* they belong to.
# The catalog keys on the type name and has no row for a single value, so the overrides live
# here. A value may be terminal (never matchable) or merely harder to express than the type.
#
# The text in each entry is **printed in the customer report**, so it obeys the same rule as
# ``report_comment`` in the catalog: plain language, and nothing about the environments we
# happened to measure on. The evidence behind each one:
#
# * ``DATABASE_SERVICE`` / ``EXTERNAL`` — databases and external services are not part of the
#   Phase 3 topology, so a condition selecting one can never match. The *data* is not gone:
#   database calls survive as client spans carrying `db.*`, so the measurement is reachable
#   from a client-span extraction — but every matcher this code generates selects the
#   service-entry span (`subtrace.is_root_span == true`), and client spans are not subtrace
#   roots. External services as a topic are covered by the external-services skill.
#   MESSAGING_SERVICE is deliberately absent: it survives. The queue service types disappear
#   but cannot be selected in a calculated service metric in the first place.
# * ``HTTP_METHOD UNKNOWN`` — classic `HttpRequestMethod.fromString()` folds every
#   non-standard verb *and* a missing method into UNKNOWN; the span keeps the raw verb. So the
#   condition is an inverted set match over the nine standard verbs plus `isNull`, not an
#   equality.
# * ``HTTP_STATUS_CLASS C_1XX`` — classic buckets the combined HTTP status with no 1xx branch,
#   so such a condition matches nothing and the classic metric is already empty.
COMPARISON_VALUE_OVERRIDES = {
    **{
        ("SERVICE_TYPE", value): (
            "UNSUPPORTED",
            "The condition requires the service to be a database or an external service. Phase 3 "
            "has no such service, so the condition can never match. The calls themselves are "
            "still recorded, as client-side spans, but a metric built from those needs a "
            "different extraction than this migration produces.",
        )
        for value in ("DATABASE_SERVICE", "EXTERNAL")
    },
    ("HTTP_METHOD", "UNKNOWN"): (
        "DERIVED",
        "Classic puts every unusual HTTP verb, and a missing one, into one UNKNOWN bucket. The "
        "span keeps the verb as it came in, so the same condition has to be written the other "
        "way round: everything that is not one of the standard verbs.",
    ),
    ("HTTP_STATUS_CLASS", "C_1XX"): (
        "UNSUPPORTED",
        "The condition selects 1xx responses, which classic never puts in that bucket, so the "
        "classic metric counts nothing today. There is nothing to migrate.",
    ),
}


def comparison_value_status(condition: dict, catalogued: str) -> tuple[str, str | None]:
    """Downgrade a condition whose compared value is terminal by itself."""
    info = condition.get("comparisonInfo") or {}
    values = info.get("values") or ([info["value"]] if info.get("value") is not None else [])
    for value in values:
        hit = COMPARISON_VALUE_OVERRIDES.get((info.get("type"), str(value)))
        if hit:
            return hit
    return catalogued, None


def metric_report(catalog: dict, definition: dict) -> dict:
    attributes = index(catalog, "conditionAttributes")
    measurements = index(catalog, "measurements")
    comparisons = index(catalog, "comparisons")
    top_level = index(catalog, "topLevel")

    elements: list[tuple[str, str, str]] = []
    # Reasons for elements that have no catalog row of their own, because the block comes
    # from the compared *value* rather than from the operator. Without this the report
    # blames the operator -- "EQUALS blocks 17 metrics" -- which is nonsense to a reader.
    reasons: dict[str, str] = {}

    measure = (definition.get("metricDefinition") or {}).get("metric")
    if measure:
        elements.append(("measurement", measure, measurements[measure]["status"]))

    for condition in definition.get("conditions") or []:
        attribute = condition["attribute"]
        status = attributes[attribute]["status"]
        if attribute == "IS_KEY_REQUEST":
            status = key_request_status(condition, status)
        elements.append(("condition", attribute, status))
        comparison = (condition.get("comparisonInfo") or {}).get("comparison")
        if comparison:
            catalogued = comparisons[comparison]["status"]
            value_status, reason = comparison_value_status(condition, catalogued)
            if reason is None:
                elements.append(("comparison", comparison, value_status))
            else:
                # The operator itself is fine; the value it compares against is not. Report
                # both, so the operator keeps its real status and the block is attributed to
                # the value that actually causes it.
                info = condition.get("comparisonInfo") or {}
                values = info.get("values") or (
                    [info["value"]] if info.get("value") is not None else [])
                offending = next(
                    (str(v) for v in values
                     if (info.get("type"), str(v)) in COMPARISON_VALUE_OVERRIDES), "")
                label = f"{info.get('type')} {comparison} {offending}".strip()
                elements.append(("comparison", comparison, catalogued))
                elements.append(("comparison value", label, value_status))
                reasons[label] = reason

    elements.extend(dimension_status(catalog, definition))

    # A custom placeholder is reported under the customer's own name, which has no catalog
    # row, so spell out which of its catalogued parts is blocking.
    for placeholder in ((definition.get("dimensionDefinition") or {}).get("placeholders") or []):
        culprits = placeholder_culprits(catalog, placeholder)
        if not culprits:
            continue
        name = placeholder.get("name", "?")
        # Named after the customer's own placeholder, which has no catalog row of its own, so
        # the blocking parts are spelled out. No status names in the sentence: `UNSUPPORTED`
        # means nothing to the reader, and the explanation already says what is wrong.
        reasons[name] = "This is a custom dimension. " + " ".join(
            comment.rstrip() for _source, _status, comment in culprits if comment)

    if definition.get("entityId"):
        entry = top_level.get("`entityId`")
        elements.append(("scope", definition["entityId"], entry["status"] if entry else "UNCLASSIFIED"))
    if definition.get("managementZones"):
        entry = top_level.get("`managementZones`")
        elements.append(("scope", "managementZones", entry["status"] if entry else "UNCLASSIFIED"))
    if definition.get("ignoreMutedRequests"):
        elements.append(("mutedRequests", "true", "UNSUPPORTED"))

    blockers = [e for e in elements if e[2] in BLOCKING and e[0] not in WARNING_ONLY]
    warnings = [e for e in elements if e[2] in BLOCKING and e[0] in WARNING_ONLY]
    # Elements that are migratable but cannot be approved from the catalog alone: the field
    # has to be confirmed on the tenant, or an entity lookup has to be resolved first.
    checks = [e for e in elements if e[2] in NEEDS_CHECK]
    return {
        "key": definition["tsmMetricKey"],
        "name": definition.get("name"),
        "elements": elements,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "reasons": reasons,
        "verdict": ("blocked" if blockers else "needs validation" if checks else "ready"),
    }


def load_default_catalog() -> dict:
    """The bundled catalog. One file, read once per scan."""
    return load_catalog(DEFAULT_CATALOG)
