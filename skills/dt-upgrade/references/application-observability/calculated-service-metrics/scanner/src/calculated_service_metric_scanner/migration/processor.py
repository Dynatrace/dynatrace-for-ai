"""Turn one classic calculated service metric into an OpenPipeline span processor.

The output is a single ``metricExtraction`` processor per classic metric, as a file. It is not
wrapped in a pipeline, not attached to a pipeline group and not routed anywhere: how the
processor is deployed is the customer's decision, and this migration deliberately does not make
it for them.

Nothing here contacts the tenant. Two rules make that possible:

* **The matcher grammar is a narrow subset of DQL.** ``contains()``, ``startsWith()``,
  ``endsWith()``, ``in()``, ``lower()``, ``if()``, ``like`` and ``caseSensitive: true`` are all
  rejected by the tenant validator, so substring comparisons go through ``matchesValue``
  wildcards and a case-sensitive substring comparison is refused outright.
* **``SERVICE_TYPE`` is dropped rather than resolved.** Spans carry no service-type field, so the
  condition cannot be matched per record. Resolving it against the tenant means freezing a
  service list, and the earlier attempt cost one span query per metric. The condition is dropped
  and the metric is reported as an inexact migration that may match more than classic did.
"""

from __future__ import annotations

import re

# Classic CSMs are evaluated once per service call. On spans that is the subtrace root:
# `request.is_root_span` says the same thing but is deprecated, while `subtrace.is_root_span`
# is the supported successor and is the span endpoint detection runs on. Measured against a
# live environment, subtrace roots are a small fraction of a service's spans and
# `endpoint.name` is non-null on exactly those, so without this predicate an extracted metric
# counts every span of a request instead of one per call — several times too many.
ENTRY_SPAN = "subtrace.is_root_span == true"

# Live schema limit, confirmed by the tenant validator: "Size must be lower than or equal to
# 4096" on the processor matcher.
MATCHER_MAX = 4096

# Classic measurement -> (processor type, payload additions, status-code range to add to the
# matcher). Every target here comes from ``mapping-catalog.json``, and every span field is one
# measured to carry values on a live environment -- documented in the span model is not enough:
# ``error.exception_count`` was documented, absent from the schema, and null on every span. The
# payload shapes were
# validated against a live schema: `measurement: field` is accepted, and its `field` obeys the
# same bare-identifier pattern as a matcher field name, so it goes through `dql_field`.
MEASUREMENTS = {
    "RESPONSE_TIME": ("samplingAwareValueMetric", {"measurement": "duration"}, None),
    "REQUEST_COUNT": ("samplingAwareCounterMetric", {}, None),
    "CPU_TIME": ("samplingAwareValueMetric",
                 {"measurement": "field", "field": "span.timing.cpu"}, None),
    "HTTP_4XX_ERROR_COUNT": ("samplingAwareCounterMetric", {}, (400, 499)),
    "HTTP_5XX_ERROR_COUNT": ("samplingAwareCounterMetric", {}, (500, 599)),
    # The field is not fixed: it comes from the definition's own `requestAttribute`.
    "REQUEST_ATTRIBUTE": ("samplingAwareValueMetric", {"measurement": "field"}, None),
}

# What a measured value means once it comes off a span rather than off the classic service call.
# Only where the two differ: `CPU_TIME` is the case where the number is built from a different
# scope, so a reader comparing the two charts has to know why they do not line up.
MEASUREMENT_NOTES = {
    "CPU_TIME": (
        "Classic recorded the CPU time of the whole service call. The migrated metric reads the "
        "CPU time on the request's own span, which covers the work done on that request's thread "
        "and the calls it made further down the same thread. Work the request handed to another "
        "thread is not counted, so the migrated metric can read lower than the classic one. A "
        "request whose CPU time the agent did not record adds nothing to either metric."),
}

# Classic condition attribute -> span field. Only the attributes the generator can express;
# anything else must already have been blocked by the catalog.
CONDITION_FIELDS = {
    "SERVICE_DISPLAY_NAME": "dt.service.name",
    "SERVICE_NAME": "dt.service.name",
    "SERVICE_WEB_SERVER_NAME": "http.server_name",
    "WEBREQUEST_URL": "url.full",
    "WEBREQUEST_URL_PATH": "url.path",
    "WEBREQUEST_QUERY": "url.query",
    "REQUEST_NAME": "endpoint.name",
    "HTTP_STATUS": "http.response.status_code",
    "HTTP_REQUEST_METHOD": "http.request.method",
    "PROCESS_GROUP_NAME": "dt.process_group.detected_name",
    "APPLICATION_RELEASE_VERSION": "deployment.release_version",
}

# Classic attributes with no single span field, which decompose into an or-chain over several.
# `WEBREQUEST_RELATIVE_URL` is `url.path` plus an optional `?` and `url.query` -- the catalog
# records it as DERIVED for exactly that reason. Only a containment test decomposes soundly: if a
# substring occurs in `path + "?" + query` it occurs in one of the two parts, unless it straddles
# the `?`. An anchored or exact comparison needs the concatenation itself and is refused.
DECOMPOSED_CONDITION_FIELDS = {
    "WEBREQUEST_RELATIVE_URL": ("url.path", "url.query"),
}

DECOMPOSABLE_COMPARISONS = {"CONTAINS", "EXISTS"}

# Attributes classic evaluates against the monitored-entity index rather than the request, so the
# span field is the *detected* name while classic compared the name shown in the UI. The two are
# the same string until a naming rule renames the entity. The matcher is still emitted -- the
# alternative is resolving an entity list and freezing it into the config -- and the metric is
# declared inexact so nobody reads it as an exact migration. Measured on a live environment:
# 12 of 44 service-name conditions and 2 of 7 process-group conditions hit a renamed entity.
INEXACT_ENTITY_NAME = {
    "SERVICE_DISPLAY_NAME": (
        "The classic metric picks services by the name shown in the UI. The migrated metric "
        "compares the name the agent detected, which is the same name unless a naming rule "
        "renamed the service. For a renamed service the condition does not match, so check "
        "whether the services this metric is about carry their detected name."),
    "PROCESS_GROUP_NAME": (
        "The classic metric picks process groups by the name shown in the UI. The migrated metric "
        "compares the name the agent detected, which is the same name unless a naming rule "
        "renamed the group. For a renamed group the condition does not match, so check whether "
        "the groups this metric is about carry their detected name."),
}

# Attributes whose span field cannot carry everything classic evaluated, so a generated matcher
# is narrower than the classic condition and the reader has to be told. Empty since the exception
# family left: `exception.type` and `exception.message` are declared span fields but are populated
# only inside `span.events`, measured null on every span of a live environment, so the catalog
# blocks them outright rather than warning about them.
NARROWER_THAN_CLASSIC: dict[str, str] = {}

# Attributes that are only ever compared as a number. Everything else is decided per condition
# from `comparisonInfo.type`, which is what actually distinguishes a numeric comparison from a
# string one -- `HTTP_STATUS` carries `type: NUMBER` and was previously pushed through
# `matchesValue`, which the schema accepts on a `long` field but which does not mean the same
# thing.
NUMERIC_CONDITION_FIELDS = {
    "RESPONSE_TIME": "duration",
}

# The unit the classic API stores a threshold in, where it is not unitless. `RESPONSE_TIME` is
# **milliseconds**: `...lessthan250ms` holds 250, `...below5s` holds 5000 and
# `releasesapi_2mins` holds 120000 -- the definitions name their own threshold, so the unit is
# read off the data, not assumed. Grail `duration` is nanoseconds and the matcher grammar accepts
# a duration literal, so the threshold is emitted as `<value>ms` and no conversion arithmetic
# ends up in the config.
NUMERIC_UNITS = {"RESPONSE_TIME": "ms"}

# `comparisonInfo.type` values that mean "compare this as a number".
NUMERIC_COMPARISON_TYPES = {"NUMBER", "NUMBER_REQUEST_ATTRIBUTE"}

NUMERIC_COMPARISONS = {
    "LOWER_THAN": "<", "LOWER_THAN_OR_EQUAL": "<=",
    "GREATER_THAN": ">", "GREATER_THAN_OR_EQUAL": ">=",
    "EQUALS": "==",
}

PLACEHOLDER = re.compile(r"\{([A-Za-z]+):(.+)\}$")

# Built-in placeholders other than `{RequestAttribute:...}`, and the span field each names.
# Every field confirmed in the semantic dictionary, not inferred from the placeholder text.
PLACEHOLDER_FIELDS = {
    ("Request", "Name"): "endpoint.name",
    ("URL", "Path"): "url.path",
    ("Service", "Name"): "dt.service.name",
    ("Request", "ApplicationReleaseVersion"): "deployment.release_version",
}

# Classic's older dimension tokens, which are not `{Kind:Name}` placeholders but name one
# request property all the same.
LEGACY_DIMENSION_FIELDS = {
    "{Database-Statement}": "db.query.text",
    "{HTTP-Method}": "http.request.method",
    "{URL}": "url.full",
}

# Classic tokens that name more than one span field, so no single field copy reproduces them.
# `{Relative-URL}` is the path plus an optional `?` and query string -- the catalog records the
# same source as DERIVED for exactly that reason. Splitting on `url.path` alone was silently
# dropping the query string from every dimension value, which is a different metric, not a
# footnote. A dimension copies one field, and metric extraction has no step that builds the
# concatenation first, so the token is refused.
REJECTED_DIMENSIONS = {
    "{Relative-URL}": (
        "The metric splits by the relative URL, which classic writes as the path followed by the "
        "query string. The span keeps those in two separate fields and a split copies one field, "
        "so the value cannot be rebuilt here."),
}

# Fields where dropping classic's top-N cap is a real change, not a footnote.
HIGH_CARDINALITY_FIELDS = {"db.query.text", "url.path", "url.full"}

# The schema's own pattern for a dimension key, taken verbatim from the validator message:
# "Must match pattern [a-zA-Z_][.a-zA-Z0-9_\-:]+". Note the two-character minimum.
DESTINATION_FIELD = re.compile(r"[a-zA-Z_][.a-zA-Z0-9_\-:]+")

# The schema's own pattern for an unquoted field name, taken verbatim from the validator
# message: "Must match pattern [a-zA-Z_][a-zA-Z0-9_.]*, or be wrapped with backticks".
BARE_FIELD = re.compile(r"[a-zA-Z_][a-zA-Z0-9_.]*")


class Unsupported(Exception):
    """The generator cannot express this element, so nothing is emitted for the metric.

    Two texts, on purpose. ``str(exc)`` is the engineering message — it names the schema limit
    or the grammar gap and is what tells us which gap to close — and it is kept in the machine
    record. ``plain`` is the sentence the customer report prints, in the same register as the
    catalog's ``report_comment``: what the classic metric asked for, and why a processor cannot
    do it. Never print the engineering message in a report.
    """

    DEFAULT_PLAIN = (
        "This part of the definition cannot be written as a span processor, so the metric is "
        "not migrated."
    )

    def __init__(self, message: str, plain: str | None = None) -> None:
        super().__init__(message)
        self.plain = plain or self.DEFAULT_PLAIN


def dql_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def dql_field(name: str) -> str:
    """Backtick a field name unless the schema accepts it bare."""
    if BARE_FIELD.fullmatch(name):
        return name
    if "`" in name:
        # Reachable from a request-attribute or placeholder name, which is the customer's own
        # string. The grammar has no escape inside a backticked name, so the reference would end
        # early and the rest of the matcher -- or of the dimension -- would mean something else.
        raise Unsupported(
            f"field name {name!r} contains a backtick, which the matcher grammar cannot escape",
            plain="The metric reads a value whose name contains a backtick. A processor has no "
                  "way to spell that name, so the metric is not migrated.")
    return f"`{name}`"


def wildcard_literal(value: str, prefix: str, suffix: str) -> str:
    """A matchesValue pattern for a classic substring comparison.

    ``matchesValue`` is the only pattern function the matcher grammar enables, and it treats
    ``*`` as a wildcard, so a classic value containing a literal star cannot be expressed --
    generating one anyway would silently widen what the metric counts.
    """
    if "*" in value:
        raise Unsupported(
            "the compared value contains '*', which matchesValue reads as a wildcard, and the "
            "matcher grammar has no literal substring function to fall back on",
            plain="The condition compares against a value that contains a `*`. A processor reads "
                  "`*` as a wildcard, so the same comparison cannot be written without changing "
                  "which requests it matches.")
    return dql_string(f"{prefix}{value}{suffix}")


def string_predicate(field: str, comparison: str, values: list[str], case_sensitive: bool) -> str:
    """Render one classic string comparison in the OpenPipeline *matcher* grammar.

    That grammar is a narrow subset of DQL, established against the tenant validator on
    2026-09-02, not assumed from DQL in general:

    * enabled -- ``==`` and the numeric comparisons, ``isNull``/``isNotNull``,
      ``matchesValue``, ``matchesPhrase``, ``not``, ``and``/``or``, ``toSmartscapeId``
      (only next to ``==``), backticked field names, indexed array access;
    * **not** enabled -- ``contains()``, ``startsWith()``, ``endsWith()``, ``in()``,
      ``lower()``, ``if()``, the ``like`` operator, and ``caseSensitive: true`` on
      ``matchesValue``/``matchesPhrase``.

    Two consequences the catalog did not anticipate: substring comparisons have to go
    through ``matchesValue`` wildcards, and a *case-sensitive* substring comparison cannot
    be expressed at all.
    """
    ref = dql_field(field)
    # EXISTS carries no value at all, so it cannot be driven off the value loop.
    if comparison == "EXISTS":
        return f"isNotNull({ref})"
    if not values:
        raise Unsupported(f"comparison {comparison} without a value")
    parts = []
    for value in values:
        literal = dql_string(value)
        if comparison in ("EQUALS", "EQUALS_ANY_OF"):
            if case_sensitive:
                # `==` is the only case-sensitive string test the grammar offers, and it is
                # an exact literal, so no wildcard escaping problem arises.
                parts.append(f"{ref} == {literal}")
            else:
                parts.append(f"matchesValue({ref}, {wildcard_literal(value, '', '')})")
        elif comparison in ("CONTAINS", "BEGINS_WITH", "ENDS_WITH"):
            if case_sensitive:
                raise Unsupported(
                    f"a case-sensitive {comparison} cannot be expressed: the matcher grammar "
                    "has no contains/startsWith/endsWith, and matchesValue rejects "
                    "`caseSensitive: true`. Generating a case-insensitive match instead would "
                    "count records classic excludes",
                    plain="The condition matches part of a text and cares about upper and lower "
                          "case. A processor can only compare text ignoring case, so it would "
                          "count requests the classic metric leaves out.")
            affix = {"CONTAINS": ("*", "*"), "BEGINS_WITH": ("", "*"),
                     "ENDS_WITH": ("*", "")}[comparison]
            parts.append(f"matchesValue({ref}, {wildcard_literal(value, *affix)})")
        else:
            raise Unsupported(
                f"comparison {comparison} is not implemented by the generator",
                plain=f"The {comparison} comparison cannot be written in a processor.")
    return parts[0] if len(parts) == 1 else "(" + " or ".join(parts) + ")"


def numeric_value(attribute: str, comparison: str, value) -> int | float:
    """The condition's own number, or ``Unsupported``.

    The numeric path is chosen from ``comparisonInfo.type``, and the value it carries goes into
    the matcher as a bare literal. A declared type that does not match the stored value -- a
    malformed or unexpected classic payload -- would otherwise be written to disk as a
    migratable processor whose matcher is broken or means something else.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Unsupported(
            f"{attribute} {comparison} carries a non-numeric value ({value!r}), which the "
            "classic API is not expected to produce for a numeric comparison",
            plain="The condition is declared as a comparison against a number, but the "
                  "definition stores something else as the compared value, so the comparison "
                  "cannot be written in a processor.")
    return value


def numeric_predicate(attribute: str, field: str, comparison: str,
                      values: list) -> tuple[str, list[str]]:
    """Render a classic numeric condition, carrying its unit into a duration literal."""
    unit = NUMERIC_UNITS.get(attribute, "")
    if not values:
        raise Unsupported(f"{attribute} numeric condition without a value")
    numbers = [numeric_value(attribute, comparison, value) for value in values]
    notes: list[str] = []
    ref = dql_field(field)
    if comparison == "EQUALS_ANY_OF":
        # `in()` is not in the matcher grammar, so a value set is an or-chain of equalities.
        parts = [f"{ref} == {v}{unit}" for v in numbers]
        predicate = parts[0] if len(parts) == 1 else "(" + " or ".join(parts) + ")"
    else:
        operator = NUMERIC_COMPARISONS.get(comparison)
        if operator is None:
            raise Unsupported(
                f"numeric comparison {comparison} is not implemented for {attribute}")
        if len(numbers) != 1:
            raise Unsupported(
                f"{attribute} {comparison} carries {len(numbers)} values, which is not a "
                "shape the classic API is expected to produce")
        predicate = f"{ref} {operator} {numbers[0]}{unit}"
    if numbers == [0]:
        notes.append(
            f"The classic condition is `{comparison} 0`, which no request can satisfy, so the "
            "classic metric reports nothing today. The migrated metric keeps the same condition "
            "— fix or delete the metric rather than expecting data from it.")
    if attribute == "RESPONSE_TIME":
        notes.append(
            "Classic compares the time the service took and falls back to the time the caller "
            "saw. The migrated metric only uses the time the service took.")
    if attribute == "HTTP_STATUS":
        notes.append(
            "Classic combines the status the service returned with the one the caller saw, "
            "preferring the service. The migrated metric reads the status on the request's own "
            "span.")
    return predicate, notes


def matcher_for(definition: dict, extra_predicates: tuple[str, ...] = ()
                ) -> tuple[str, list[str], list[str]]:
    """Build the processor matcher, the notes a reader has to see, and the inexact reasons.

    ``extra_predicates`` are conditions the *measurement* implies rather than the classic
    condition list -- an HTTP error count is a plain counter over a status-code range.

    The third return value is what makes the migration *inexact*: a condition the matcher
    cannot carry and that was dropped, so the extracted metric matches a superset of what
    classic matched. It is reported, never silently applied.
    """
    parts = [ENTRY_SPAN, *extra_predicates]
    notes: list[str] = []
    inexact: list[str] = []

    for condition in definition.get("conditions") or []:
        attribute = condition["attribute"]
        info = condition.get("comparisonInfo") or {}
        comparison = info.get("comparison")
        negate = bool(info.get("negate"))
        case_sensitive = bool(info.get("caseSensitive"))
        values = info.get("values") or (
            [info["value"]] if info.get("value") is not None else [])

        # EXISTS is a presence test whatever the declared type, and it carries no value, so it
        # can never take the numeric path.
        numeric = comparison != "EXISTS" and (
            info.get("type") in NUMERIC_COMPARISON_TYPES
            or attribute in NUMERIC_CONDITION_FIELDS)

        if attribute == "SERVICE_REQUEST_ATTRIBUTE":
            name = info.get("requestAttribute")
            if not name:
                raise Unsupported("request-attribute condition without an attribute name")
            field = f"request_attribute.{name}"
            if numeric:
                predicate, numeric_notes = numeric_predicate(
                    attribute, field, comparison, list(values))
                notes.extend(numeric_notes)
            else:
                predicate = string_predicate(
                    field, comparison, [str(v) for v in values], case_sensitive)
        elif attribute == "SERVICE_TYPE":
            # Spans carry no service-type field, so this condition has no per-record form. It
            # is dropped and declared, which keeps the processor free of a frozen service list
            # and keeps the scan free of a span query. The over-match is bounded by the
            # metric's other conditions, which are all still evaluated. A definition scoped
            # by SERVICE_TYPE alone would be the exception, and none has been observed.
            if negate:
                shown = "a negated service-type condition"
            else:
                shown = " or ".join(f"`{v}`" for v in [str(v) for v in values]) or "a value"
            inexact.append(
                f"The classic metric only counted requests to a {shown} service. Spans do not "
                "say what type a service is, so the migrated metric leaves that condition out "
                "and also counts requests to services of another type — but only among the "
                "requests this metric's other conditions already allow."
            )
            continue
        elif attribute in DECOMPOSED_CONDITION_FIELDS:
            fields = DECOMPOSED_CONDITION_FIELDS[attribute]
            if comparison not in DECOMPOSABLE_COMPARISONS:
                raise Unsupported(
                    f"{attribute} has no single span field -- it is {' + '.join(fields)} -- and "
                    f"a {comparison} comparison needs the concatenated value, which the matcher "
                    "grammar cannot build. Only a containment test decomposes soundly",
                    plain="The condition compares the URL path and the query string as one "
                          "value. The span keeps them in two separate fields, and only a "
                          "\"contains\" comparison can be split across the two.")
            if any("?" in str(v) for v in values):
                raise Unsupported(
                    f"the {attribute} value contains '?', so the match may straddle the "
                    "path/query boundary and cannot be decomposed into per-field tests",
                    plain="The compared value spans the boundary between the URL path and the "
                          "query string, which the span keeps in two separate fields.")
            parts_or = [string_predicate(f, comparison, [str(v) for v in values], case_sensitive)
                        for f in fields]
            predicate = "(" + " or ".join(parts_or) + ")"
            notes.append(
                "Classic compared the URL path and the query string as one value. The span keeps "
                "them in two fields, so the migrated metric accepts a match in either one. The "
                "two only differ for a value that spans the boundary between them, which is not "
                "migrated at all.")
        else:
            field = NUMERIC_CONDITION_FIELDS.get(attribute) or CONDITION_FIELDS.get(attribute)
            if field is None:
                raise Unsupported(
                    f"condition attribute {attribute} has no generator rule",
                    plain=f"The condition on {attribute} has no known span field.")
            if numeric:
                predicate, numeric_notes = numeric_predicate(
                    attribute, field, comparison, list(values))
                notes.extend(numeric_notes)
            else:
                predicate = string_predicate(
                    field, comparison, [str(v) for v in values], case_sensitive)
            if attribute in NARROWER_THAN_CLASSIC:
                notes.append(NARROWER_THAN_CLASSIC[attribute])
            if attribute in INEXACT_ENTITY_NAME:
                inexact.append(INEXACT_ENTITY_NAME[attribute])

        parts.append(f"not ({predicate})" if negate else predicate)

    if definition.get("ignoreMutedRequests"):
        raise Unsupported(
            "ignoreMutedRequests has no span representation",
            plain="The metric skips requests that were muted. Phase 3 has no request muting, so "
                  "this cannot be carried over.")

    matcher = " and ".join(parts)
    if len(matcher) > MATCHER_MAX:
        raise Unsupported(
            f"matcher is {len(matcher)} characters, over the schema limit of {MATCHER_MAX}",
            plain="The definition has more conditions than a single processor can hold.")
    return matcher, notes, inexact


def schema_safe_dimension_name(classic_name: str, placeholder_inner: str) -> str:
    """Coerce a classic dimension name into a key the OpenPipeline schema accepts.

    Classic permits a dimension to be *named* after a placeholder -- `loadfromtenants` is named
    `{RequestAttribute:Dynatrace Tenant}` -- and forwards that name to Grail verbatim. The schema
    pattern allows no braces, so such a name has to change or the whole metric is lost. Renaming
    a dimension key is the smaller loss, and it is recorded as a note rather than applied quietly.
    """
    if DESTINATION_FIELD.fullmatch(classic_name):
        return classic_name
    match = PLACEHOLDER.fullmatch(classic_name.replace("_", " "))
    candidate = match.group(2) if match else classic_name
    candidate = re.sub(r"[^.a-zA-Z0-9_\-:]", "_", candidate.replace(" ", "_"))
    if not re.match(r"[a-zA-Z_]", candidate):
        candidate = "d_" + candidate
    if len(candidate) < 2:
        candidate += "_"
    if DESTINATION_FIELD.fullmatch(candidate):
        return candidate
    # Nothing derived from the classic name survives the pattern; fall back to the placeholder
    # the dimension *value* resolves from, which is always a plain identifier.
    return re.sub(r"[^.a-zA-Z0-9_\-:]", "_", placeholder_inner.replace(" ", "_"))


def dimensions_for(definition: dict) -> tuple[list[dict], list[str]]:
    dimension = definition.get("dimensionDefinition") or {}
    literal = (dimension.get("dimension") or "").strip()
    notes: list[str] = []
    if dimension.get("placeholders"):
        raise Unsupported(
            "custom placeholders are not implemented by the generator",
            plain="The metric splits by a custom dimension built from a captured value. A "
                  "processor copies one field value and cannot build that dimension.")
    if not literal or literal == "All requests":
        return [], notes

    if literal in REJECTED_DIMENSIONS:
        raise Unsupported(
            f"dimension {literal} names more than one span field and cannot be rebuilt by a "
            "field copy",
            plain=REJECTED_DIMENSIONS[literal])

    if literal in LEGACY_DIMENSION_FIELDS:
        # Classic's own pre-placeholder dimension tokens. They name a single request property,
        # so they map to one field copy exactly like a placeholder does.
        source = LEGACY_DIMENSION_FIELDS[literal]
        name = source.replace(".", "_")
    else:
        match = PLACEHOLDER.fullmatch(literal)
        if match is None:
            raise Unsupported(
                f"dimension {literal!r} is neither a placeholder nor a known classic token. "
                "A dimension is one field copy, so a composite of several properties needs a "
                "preceding DQL processor to materialize the combined field first",
                plain="The metric splits by a value built from more than one request property. "
                      "A processor copies a single field, so this needs an extra step that "
                      "builds the combined value first.")
        kind, name = match.group(1), match.group(2)
        if kind == "RequestAttribute":
            source = f"request_attribute.{name}"
        else:
            source = PLACEHOLDER_FIELDS.get((kind, name))
            if source is None:
                raise Unsupported(
                f"placeholder {{{kind}:{name}}} has no generator rule",
                plain=f"The metric splits by {kind}:{name}, which has no known span field.")

    if source in HIGH_CARDINALITY_FIELDS:
        notes.append(
            f"The split is on `{source}`, which takes many different values and can contain "
            "sensitive text. Classic only kept the top ones; the migrated metric keeps them all. "
            "Check how many values that produces, and whether any of them need masking, before "
            "putting this one to work.")

    # MetricGrailForwarder uses the configured dimension name verbatim with spaces replaced
    # by underscores, so the migrated metric keeps the name its consumers already read.
    classic_name = (dimension.get("name") or name).replace(" ", "_")
    destination = schema_safe_dimension_name(classic_name, name)
    if destination != classic_name:
        notes.append(
            f"The classic split is named `{classic_name}`, which is not a name a migrated "
            f"metric can use, so it becomes `{destination}`. Anything reading the old name has "
            "to be updated.")
    if dimension.get("topX"):
        notes.append(
            f"Classic kept only the top {dimension['topX']} values of this split. The migrated "
            "metric keeps every value, so sorting and limiting move into the query that reads "
            "it.")
    return [{
        "strategy": "equals",
        "extractionType": "field",
        # The schema applies the same bare-identifier pattern here as in a matcher, so a
        # request attribute whose name has a space or a hyphen must be backticked.
        "sourceFieldName": dql_field(source),
        "destinationFieldName": destination,
    }], notes


def target_metric_key(classic_key: str) -> str:
    # The classic key is already forwarded to Grail without its `calc:` root, so reusing it
    # would give one metric two writers. A `migrated.` root cannot collide and keeps the
    # required two non-empty dot-separated sections.
    return "migrated." + classic_key.removeprefix("calc:")


def build_processor(definition: dict) -> tuple[dict, list[str], list[str]]:
    """``(processor, notes, inexact)`` for one classic definition.

    Raises :class:`Unsupported` when the definition cannot be expressed, rather than emitting a
    processor that measures something else.
    """
    metric_definition = definition.get("metricDefinition") or {}
    measure = metric_definition.get("metric")
    if measure not in MEASUREMENTS:
        raise Unsupported(
            f"measurement {measure} is not implemented by the generator",
            plain=f"The metric measures {measure}, which this migration cannot express as a "
                  "span metric.")
    processor_type, fixed, status_range = MEASUREMENTS[measure]
    extra = dict(fixed)
    measurement_notes: list[str] = list(
        [MEASUREMENT_NOTES[measure]] if measure in MEASUREMENT_NOTES else [])
    implied: tuple[str, ...] = ()

    if measure == "REQUEST_ATTRIBUTE":
        attribute = metric_definition.get("requestAttribute")
        if not attribute:
            raise Unsupported("a REQUEST_ATTRIBUTE measurement without an attribute name")
        extra["field"] = dql_field(f"request_attribute.{attribute}")
        measurement_notes.append(
            f"The metric measures the request attribute `{attribute}`. This works only if the "
            "attribute holds a single number per request: classic added up every value it "
            "captured during a request, while the migrated metric reads one value. If the "
            "attribute holds text, or several values, the migrated metric will be empty or "
            "wrong — the definition alone does not say which.")

    if status_range is not None:
        low, high = status_range
        field = dql_field("http.response.status_code")
        implied = (f"{field} >= {low} and {field} <= {high}",)
        measurement_notes.append(
            f"Classic counted requests answered with a {low // 100}xx status, preferring the "
            "status the service returned over the one the caller saw. The migrated metric reads "
            "the status on the request's own span. A request that is not HTTP at all is counted "
            "by neither.")

    matcher, notes, inexact = matcher_for(definition, implied)
    notes.extend(measurement_notes)
    dimensions, dimension_notes = dimensions_for(definition)
    notes.extend(dimension_notes)

    key = target_metric_key(definition["tsmMetricKey"])
    attributes = {
        "metricKey": key,
        "dimensions": dimensions,
        "sampling": "enabled",
        "aggregation": "enabled",
        **extra,
    }
    if definition.get("unit") == "MICRO_SECOND":
        notes.append(
            "Classic reports this metric in microseconds. The migrated metric reports the same "
            "scale, so a dashboard or alert that switches to the new key does not need its "
            "thresholds rescaled. Checked against a live metric, not assumed.")

    processor = {
        "id": key,
        "type": processor_type,
        "enabled": bool(definition.get("enabled", True)),
        "description": f"Migrated from {definition['tsmMetricKey']} ({definition.get('name')})",
        "matcher": matcher,
        processor_type: attributes,
    }
    return processor, notes, inexact
