"""Translate Config v1 conditions into DQL filter fragments.

Pure functions. Each public entry point returns a :class:`Translation`
describing either a successful DQL fragment or the reason the condition is
unmigratable. The orchestrator collects these into the per-rule sidecar.

Coverage:

- Scalar matchers (``STRING``, ``NUMBER``, ``BOOLEAN``, ``HTTP_METHOD``,
  ``SERVICE_TYPE``, ``ZOS_TRANSACTIONTYPE``, ``FAST_STRING``).
- Array-valued ``APPLICATION_*`` rows — emitted with ``in(<key>, <value>)``.
- ``TAG`` matcher with the dual-pattern ``TAG_KEY_EQUALS`` form.
- ``HTTP_STATUS_CLASS`` div-100 expansion incl. ``NO_RESPONSE``.
- ``IS_KEY_REQUEST`` mapping with one-way sentinel semantics.
- ``REQUEST_ATTRIBUTE`` / ``ONE_AGENT_ATTRIBUTE`` (declared unmigratable).
- ``REGEX_MATCHES`` (unmigratable).
- Negation wrapping via ``not (...)`` with the per-attribute restriction
  table enforced.
- Rule-level ``managementZones`` emitted as a synthetic entity-side condition.

The translator does **not** apply the entity-side ``isExternalService != true``
pre-filter or projection lists — those belong to the query builder (queries/entity.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .mapping import AttributeRow, EntityAttributeRow, load_mapping
from .models import ComparisonInfo, Condition
from .tags import is_primary_tag_condition, is_primary_tag_key, tag_pairs

_STRING_SCALAR_TYPES = {
    "STRING",
    "FAST_STRING",
    "HTTP_METHOD",
    "SERVICE_TYPE",
    "ZOS_TRANSACTIONTYPE",
}

_HTTP_STATUS_CLASS_TO_DIGIT = {
    "C_1XX": 1,
    "C_2XX": 2,
    "C_3XX": 3,
    "C_4XX": 4,
    "C_5XX": 5,
}


@dataclass(frozen=True)
class Translation:
    """Result of translating a single condition.

    Exactly one of :attr:`dql` / :attr:`unmigratable_reason` is set.
    """

    api_attribute: str
    phase3_status: str
    dql: str | None = None
    unmigratable_reason: str | None = None

    @property
    def ok(self) -> bool:
        """True when a DQL fragment was produced (condition is migratable)."""
        return self.dql is not None


class TranslationError(ValueError):
    """Internal helper raised when condition shape violates the API contract."""


def _quote(value: object) -> str:
    """JSON-quote a string for embedding in DQL."""
    return json.dumps(str(value), ensure_ascii=False)


def _negate(expr: str, ci: ComparisonInfo) -> str:
    return f"not ({expr})" if ci.negate else expr


def _require_negation_allowed(api_attribute: str, ci: ComparisonInfo) -> None:
    if ci.negate and load_mapping().is_negation_forbidden(api_attribute):
        raise TranslationError(
            f"negation not allowed on {api_attribute}"
        )


def _require_exists_allowed(api_attribute: str) -> None:
    if api_attribute in load_mapping().exists_forbidden:
        raise TranslationError(
            f"EXISTS not allowed on {api_attribute}"
        )


def _scalar_value(ci: ComparisonInfo) -> Any:
    if ci.value is None:
        raise TranslationError("scalar operator requires comparisonInfo.value")
    return ci.value


def _any_of_values(ci: ComparisonInfo) -> list[Any]:
    if not ci.values:
        raise TranslationError("_ANY_OF operator requires comparisonInfo.values")
    return list(ci.values)


def _emit_string_scalar(key: str, op: str, ci: ComparisonInfo) -> str:  # pylint: disable=too-many-return-statements
    if op == "EQUALS":
        return f'{key} == {_quote(_scalar_value(ci))}'
    if op == "BEGINS_WITH":
        return f"startsWith({key}, {_quote(_scalar_value(ci))})"
    if op == "ENDS_WITH":
        return f"endsWith({key}, {_quote(_scalar_value(ci))})"
    if op == "CONTAINS":
        return f"contains({key}, {_quote(_scalar_value(ci))})"
    if op == "EXISTS":
        return f"isNotNull({key})"
    if op == "EQUALS_ANY_OF":
        args = ", ".join(_quote(v) for v in _any_of_values(ci))
        return f"in({key}, {{{args}}})"
    if op == "BEGINS_WITH_ANY_OF":
        terms = " or ".join(
            f"startsWith({key}, {_quote(v)})" for v in _any_of_values(ci)
        )
        return f"({terms})"
    if op == "ENDS_WITH_ANY_OF":
        terms = " or ".join(
            f"endsWith({key}, {_quote(v)})" for v in _any_of_values(ci)
        )
        return f"({terms})"
    if op == "REGEX_MATCHES":
        raise TranslationError("REGEX_MATCHES is unmigratable")
    raise TranslationError(f"unsupported string operator: {op}")


def _emit_integer(key: str, op: str, ci: ComparisonInfo) -> str:  # pylint: disable=too-many-return-statements
    if op == "EQUALS":
        return f"{key} == {int(_scalar_value(ci))}"
    if op == "GREATER_THAN":
        return f"{key} > {int(_scalar_value(ci))}"
    if op == "LOWER_THAN":
        return f"{key} < {int(_scalar_value(ci))}"
    if op == "GREATER_THAN_OR_EQUAL":
        return f"{key} >= {int(_scalar_value(ci))}"
    if op == "LOWER_THAN_OR_EQUAL":
        return f"{key} <= {int(_scalar_value(ci))}"
    if op == "EXISTS":
        return f"isNotNull({key})"
    if op == "EQUALS_ANY_OF":
        args = ", ".join(str(int(v)) for v in _any_of_values(ci))
        return f"in({key}, {{{args}}})"
    raise TranslationError(f"unsupported integer operator: {op}")


def _emit_boolean(key: str, op: str, ci: ComparisonInfo) -> str:
    if op == "EQUALS":
        v = bool(_scalar_value(ci))
        return f"{key} == {'true' if v else 'false'}"
    if op == "EXISTS":
        return f"isNotNull({key})"
    if op == "EQUALS_ANY_OF":
        args = ", ".join("true" if bool(v) else "false" for v in _any_of_values(ci))
        return f"in({key}, {{{args}}})"
    raise TranslationError(f"unsupported boolean operator: {op}")


def _emit_array_string(key: str, op: str, ci: ComparisonInfo) -> str:
    """Idioms for ``array<string>`` Grail keys (the ``APPLICATION_*`` rows).

    DQL ``in(needle, haystack...)`` — the array field is the needle; the
    target values are the haystack.  A single ``in()`` call covers both
    EQUALS (one value) and EQUALS_ANY_OF (multiple values).
    """
    if op in ("EQUALS", "EQUALS_ANY_OF"):
        # Both operators map to the same DQL in(needle, haystack...) form —
        # EQUALS passes a single value; EQUALS_ANY_OF passes multiple.
        # A single in() call handles both, so the branches are intentionally merged.
        if op == "EQUALS":
            args = _quote(_scalar_value(ci))
        else:
            args = ", ".join(_quote(v) for v in _any_of_values(ci))
        return f"in({key}, {{{args}}})"
    if op == "EXISTS":
        return f"isNotNull({key})"
    raise TranslationError(
        f"operator {op} unmigratable against array<string> key {key}"
    )


def _format_tag_value(tag: object) -> str | None:
    """Serialize a ``TagDto`` value to the leading-wildcard ``matchesValue``
    pattern. Returns None for malformed input.

    Context prefix is stripped (``TagDto.context`` doesn't round-trip cleanly)
    and replaced with ``*`` so the pattern matches both prefixed and bare
    Grail tag forms. Caveat recorded in the mapping notes.
    """
    if not isinstance(tag, dict):
        return None
    key = tag.get("key")
    value = tag.get("value")
    if not isinstance(key, str) or not key:
        return None
    if value:
        return f"*{key}:{value}"
    return f"*{key}"


def _extract_tag_key(value: object) -> str | None:
    """``TAG_KEY_EQUALS`` accepts either a bare string key or a ``TagDto``
    ``{context, key}`` object — we tolerate both shapes (the API actually
    returns the TagDto form even though the operator name suggests a string).
    """
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        key = value.get("key")
        if isinstance(key, str) and key:
            return key
    return None


def _emit_tag(key: str, op: str, ci: ComparisonInfo) -> str:
    if op == "EQUALS":
        pattern = _format_tag_value(_scalar_value(ci))
        if pattern is None:
            raise TranslationError("TAG EQUALS requires a TagDto value")
        return f"matchesValue({key}, {_quote(pattern)})"
    if op == "EQUALS_ANY_OF":
        patterns = [_format_tag_value(v) for v in _any_of_values(ci)]
        if any(p is None for p in patterns):
            raise TranslationError("TAG EQUALS_ANY_OF requires TagDto values")
        args = ", ".join(_quote(p) for p in patterns)
        return f"matchesValue({key}, {{{args}}})"
    if op == "TAG_KEY_EQUALS":
        tag_key = _extract_tag_key(_scalar_value(ci))
        if tag_key is None:
            raise TranslationError("TAG_KEY_EQUALS requires a string key")
        return f"matchesValue({key}, {{{_quote(tag_key)}, {_quote(tag_key + ':*')}}})"
    if op == "TAG_KEY_EQUALS_ANY_OF":
        keys = [_extract_tag_key(v) for v in _any_of_values(ci)]
        if any(k is None for k in keys):
            raise TranslationError("TAG_KEY_EQUALS_ANY_OF requires string keys")
        tag_patterns: list[str] = []
        for k in keys:
            tag_patterns.append(_quote(k))
            tag_patterns.append(_quote(f"{k}:*"))
        return f"matchesValue({key}, {{{', '.join(tag_patterns)}}})"
    raise TranslationError(f"unsupported tag operator: {op}")


def _emit_http_status_class(op: str, ci: ComparisonInfo) -> str:
    key = "http.response.status_code"

    def one(value: str) -> str:
        if value == "NO_RESPONSE":
            return f"isNull({key})"
        digit = _HTTP_STATUS_CLASS_TO_DIGIT.get(value)
        if digit is None:
            raise TranslationError(f"unknown HTTP_STATUS_CLASS value: {value}")
        return f"{key} div 100 == {digit}"

    if op == "EQUALS":
        return one(str(_scalar_value(ci)))
    if op == "EQUALS_ANY_OF":
        terms = " or ".join(one(str(v)) for v in _any_of_values(ci))
        return f"({terms})"
    if op == "EXISTS":
        raise TranslationError(
            "EXISTS on HTTP_STATUS_CLASS is unmigratable"
        )
    raise TranslationError(f"unsupported HTTP_STATUS_CLASS operator: {op}")


def _emit_is_key_request(op: str, ci: ComparisonInfo) -> str:
    key = "supportability.is_non_key_requests_endpoint_bucket"
    if op == "EQUALS":
        v = bool(_scalar_value(ci))
        if v:
            raise TranslationError(
                "IS_KEY_REQUEST == true is unmigratable "
                "(would over-match unclassified spans)"
            )
        return f"{key} == true"
    raise TranslationError(
        f"IS_KEY_REQUEST {op} is unmigratable"
    )


def _emit_for_row(row: AttributeRow, ci: ComparisonInfo) -> str:  # pylint: disable=too-many-return-statements
    api = row.api_attribute
    op = ci.comparison
    matcher = row.matcher_type

    # EXISTS gating per the API contract.
    if op == "EXISTS":
        _require_exists_allowed(api)

    # Attribute-specific overrides first.
    if api == "HTTP_STATUS_CLASS":
        return _emit_http_status_class(op, ci)
    if api == "IS_KEY_REQUEST":
        return _emit_is_key_request(op, ci)
    if matcher == "TAG":
        return _emit_tag(row.dql_key or "tags", op, ci)
    if row.array_valued and matcher == "STRING":
        return _emit_array_string(row.dql_key or "", op, ci)

    key = row.dql_key
    if key is None:
        raise TranslationError(f"{api} has no DQL mapping (unverified)")

    if matcher in _STRING_SCALAR_TYPES:
        return _emit_string_scalar(key, op, ci)
    if matcher == "NUMBER":
        return _emit_integer(key, op, ci)
    if matcher == "BOOLEAN":
        return _emit_boolean(key, op, ci)
    raise TranslationError(f"unhandled matcher {matcher} for {api}")


def _emit_primary_tags(pairs: list[tuple[str, str | None]]) -> str:
    """Emit the span fragment for a primary-tag condition.

    Phase 3 matches these against the entry-point span's resource attributes with
    exact, case-sensitive string equality (``NamingRuleEvaluation``), and a
    key-only tag degrades to a presence check. Multiple tags in one condition are
    OR-ed, mirroring the any-of comparison they come from.

    Never negated: the caller rejects a negated PG tag before reaching here, since
    the API cannot express one. (``NamingRuleEvaluation`` does carry a ``negated``
    flag on its ``PgTagCondition``, but no rule can be created that sets it.)
    """
    fragments = [
        f"{key} == {_quote(value)}" if value is not None else f"isNotNull({key})"
        for key, value in pairs
    ]
    if not fragments:
        raise TranslationError("primary tag condition carries no readable tag")
    if len(fragments) == 1:
        return fragments[0]
    return f"({' or '.join(fragments)})"


def _mixed_tag_reason(cond: Condition) -> str | None:
    """Reason string when a ``PROCESS_GROUP_TAG`` condition mixes primary and
    ordinary tags, else ``None``.

    Product decision (2026-08-05): this combination is not supported by request
    naming and is blocked by API validators. It is not a migrator limitation and
    no cross-side union support is planned — the feature itself cannot evaluate
    such a condition correctly, so a rule carrying one is a product bug rather
    than an input to interpret. Reporting the rule unmigratable is the only
    correct handling.

    The reason it cannot work anywhere: such a condition is an any-of, i.e. a
    *disjunction* over a process-group entity attribute and a span attribute. The
    runtime AND-s its span-side ``pgTagConditions`` with the entity-side predicate
    (``NamingRuleEvaluation.matchesServiceCall``), exactly as this pipeline
    intersects its entity and span query stages — neither can express the union.
    So the rule has no well-defined set of matched services, and there is no target
    for the migrator to reproduce.
    """
    if cond.attribute != "PROCESS_GROUP_TAG":
        return None
    pairs = tag_pairs(cond.comparisonInfo)
    primary = [k for k, _ in pairs if is_primary_tag_key(k)]
    ordinary = [k for k, _ in pairs if not is_primary_tag_key(k)]
    if not primary or not ordinary:
        return None
    return (
        "PROCESS_GROUP_TAG combines a primary tag with an ordinary tag "
        f"({', '.join(sorted(ordinary))}) in a single condition. Request naming does "
        "not support this combination and cannot evaluate it correctly, so the rule "
        "has no well-defined set of matched services — neither today nor after "
        "migration. Rewrite the rule to use either primary tags or ordinary tags, "
        "then re-run the migrator."
    )


def translate_condition(cond: Condition) -> Translation:
    """Translate one condition. Returns a :class:`Translation` either way."""
    mapping = load_mapping()

    if cond.attribute in mapping.ignored_attributes:
        return Translation(
            api_attribute=cond.attribute,
            phase3_status="ignored",
            unmigratable_reason=f"{cond.attribute} is outside migration scope",
        )

    row = mapping.by_api_attribute(cond.attribute)
    if row is None:
        return Translation(
            api_attribute=cond.attribute,
            phase3_status="unknown",
            unmigratable_reason=f"unknown api_attribute: {cond.attribute}",
        )
    if row.dql_key is None:
        return Translation(
            api_attribute=cond.attribute,
            phase3_status=row.phase3_status,
            unmigratable_reason=f"{cond.attribute} has no DQL mapping",
        )

    ci = cond.comparisonInfo
    mixed = _mixed_tag_reason(cond)
    if mixed is not None:
        return Translation(
            api_attribute=cond.attribute,
            phase3_status=row.phase3_status,
            unmigratable_reason=mixed,
        )

    # Primary tags survive Phase 3, so their status is "safe" regardless of the
    # shared PROCESS_GROUP_TAG row, which is "partial".
    is_primary = is_primary_tag_condition(cond)
    status = "safe" if is_primary else row.phase3_status

    try:
        # Applies to primary tags too. PROCESS_GROUP_TAG is an ME-index attribute,
        # so ConditionSpecificationValidator has rejected negate=true on it since
        # the Config v1 API was introduced — and that API is the only write path
        # for a global rule with conditions. A negated PG tag therefore cannot
        # exist; if one appears, flag it rather than invent a fragment.
        _require_negation_allowed(cond.attribute, ci)
        dql = _emit_primary_tags(tag_pairs(ci)) if is_primary else _emit_for_row(row, ci)
    except TranslationError as exc:
        return Translation(
            api_attribute=cond.attribute,
            phase3_status=status,
            unmigratable_reason=str(exc),
        )

    return Translation(
        api_attribute=cond.attribute,
        phase3_status=status,
        dql=_negate(dql, ci),
    )


def translate_management_zones(zones: list[str]) -> Translation:
    """Emit the rule-level ``managementZones`` field as an entity condition."""
    if not zones:
        return Translation(
            api_attribute="managementZones",
            phase3_status="deprecated",
            unmigratable_reason="empty managementZones list",
        )
    args = ", ".join(_quote(z) for z in zones)
    return Translation(
        api_attribute="managementZones",
        phase3_status="deprecated",
        dql=f"matchesValue(managementZones, {{{args}}})",
    )


def fetch_source_for(condition: Condition) -> str | None:
    """Return ``dt.entity.service`` / ``dt.entity.process_group`` if the
    condition is entity-side, else ``None`` (span-side or unknown).

    Primary tags share the ``PROCESS_GROUP_TAG`` entity row but are evaluated on
    spans, so they must not be pulled onto a process-group entity query.
    """
    if is_primary_tag_condition(condition):
        return None
    row = load_mapping().by_api_attribute(condition.attribute)
    if isinstance(row, EntityAttributeRow):
        return row.fetch_source
    return None


__all__ = [
    "Translation",
    "TranslationError",
    "fetch_source_for",
    "translate_condition",
    "translate_management_zones",
]
