from __future__ import annotations

import re
from dataclasses import dataclass, field

_DQL_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def dql_string(value: str) -> str:
    """Render a Python string as a DQL double-quoted string literal.

    Escape set verified against the DQL escape() rules in the Dynatrace docs
    (string-functions.md). Single quotes are deliberately not escaped — a
    double-quoted DQL string may contain them verbatim.
    """
    return '"' + "".join(_DQL_ESCAPES.get(c, c) for c in value) + '"'


_BARE_FIELD_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_.]*")


def dql_field(name: str) -> str:
    """Render a field name as a DQL identifier, backticking it when the name uses
    characters that are not legal bare.

    Rules per dql-reference.md: bare identifiers may use only [a-zA-Z0-9_.] and must
    start with [a-zA-Z_]; inside backticks, backticks and backslashes are escaped.
    """
    if _BARE_FIELD_RE.fullmatch(name):
        return name
    escaped = name.replace("\\", "\\\\").replace("`", "\\`")
    return f"`{escaped}`"


@dataclass(frozen=True)
class AttributeInfo:
    grail_key: str
    candidate_eligible: bool
    quality: str  # "good" | "suboptimal"
    negation_forbidden: bool = False


# FULL_WEB_REQUEST condition attribute map.
# URL_HOST_NAME splits into server.address + server.port at storage — complex to reconstruct; deferred.
# PG_TAG has no single Grail key: its tags map onto primary_tags.* span fields and
# are translated separately.
_FWR: dict[str, AttributeInfo] = {
    "URL_PATH":       AttributeInfo("url.path",           candidate_eligible=True,  quality="good"),
    "SERVER_NAME":    AttributeInfo("http.server_name",   candidate_eligible=True,  quality="good"),
    "URL_HOST_NAME":  AttributeInfo("server.address",     candidate_eligible=False, quality="good"),
    "APPLICATION_ID": AttributeInfo("",                   candidate_eligible=False, quality="good"),
    "CONTEXT_ROOT":   AttributeInfo("",                   candidate_eligible=False, quality="good"),
    "PG_TAG":         AttributeInfo("",                   candidate_eligible=False, quality="good"),
}

# FULL_WEB_SERVICE condition attribute map.
# The classic web-request/web-service merge writes URL fields onto the endpoint.name
# span that the migrator keys its target set on, so URL_PATH/SERVER_NAME/URL_HOST_NAME
# are queryable here identically to FULL_WEB_REQUEST.
# URL_HOST_NAME mirrors FWR: not candidate-eligible (server.address splits with
# server.port at storage; mining deferred). FRAMEWORK/IS_SOAP_SERVICE remain in
# ENDPOINT_SPAN_UNRECOVERABLE_FWS because their values on the endpoint span are
# numeric codes, not the true vendor string.
_FWS: dict[str, AttributeInfo] = {
    "URL_PATH":             AttributeInfo("url.path",              candidate_eligible=True,  quality="good"),
    "SERVER_NAME":          AttributeInfo("http.server_name",      candidate_eligible=True,  quality="good"),
    "URL_HOST_NAME":        AttributeInfo("server.address",        candidate_eligible=False, quality="good"),
    "WEBSERVICE_METHOD":    AttributeInfo("rpc.method",            candidate_eligible=True,  quality="good"),
    "WEBSERVICE_NAME":      AttributeInfo("rpc.service",           candidate_eligible=True,  quality="good"),
    "WEBSERVICE_NAMESPACE": AttributeInfo("rpc.namespace",         candidate_eligible=True,  quality="good"),
    "IS_SOAP_SERVICE":      AttributeInfo("network.protocol.name", candidate_eligible=False, quality="suboptimal"),
    "FRAMEWORK":            AttributeInfo("rpc.system",            candidate_eligible=False, quality="good"),
    "APPLICATION_ID":       AttributeInfo("",                      candidate_eligible=False, quality="good"),
    "CONTEXT_ROOT":         AttributeInfo("",                      candidate_eligible=False, quality="good"),
    "PG_TAG":               AttributeInfo("",                      candidate_eligible=False, quality="good"),
}

ATTRIBUTE_MAP: dict[str, dict[str, AttributeInfo]] = {
    "FULL_WEB_REQUEST":  _FWR,
    "FULL_WEB_SERVICE":  _FWS,
}

# Maps FWR entity-condition attribute types to their dt.entity.service field names.
# These conditions are resolved via the service entity for FULL_WEB_REQUEST rules.
# FULL_WEB_SERVICE rules keep them untranslatable (entity is always null for web services).
_ENTITY_ATTRIBUTE_KEYS: dict[str, str] = {
    "APPLICATION_ID": "webApplicationId",
    "CONTEXT_ROOT": "contextRoot",
}

# For FULL_WEB_SERVICE rules, FRAMEWORK (rpc.system) and IS_SOAP_SERVICE
# (network.protocol.name) carry numeric internal codes / "http" on the merged
# endpoint span — not the true vendor string or "soap". The real values live on the
# non-endpoint web-service node span; cross-span joins are explicitly out of scope.
# No stable code→vendor mapping exists across services. Not reconstructable.
ENDPOINT_SPAN_UNRECOVERABLE_FWS = {"FRAMEWORK", "IS_SOAP_SERVICE"}


@dataclass(frozen=True)
class TranslationResult:  # pylint: disable=too-many-instance-attributes
    surviving_fragments: list[str]
    deprecated_found: bool
    unmigratable_reasons: list[str]
    # One inner list per PG_TAG compareOperation. The product ORs the tags of one
    # operation and ANDs across operations/conditions, so a flat list cannot express
    # the semantics.
    pg_tag_values: list[list[str]] = field(default_factory=list)
    # Candidate-relevant attributeTypes already present as surviving conditions.
    # score_candidates blocks these so it never re-derives a condition the rule
    # already carries. Primary PG_TAG is excluded here — it is not a
    # candidate-eligible attribute type, so it can never collide with a candidate.
    surviving_attribute_types: frozenset[str] = frozenset()
    # Grail keys of surviving primary PG_TAG conditions (e.g. "primary_tags.ownership").
    # Mined primary-tag candidacy dedups per key against these, since a
    # rule may survive one primary_tags.<key> while another is still a valid candidate.
    surviving_primary_tag_keys: frozenset[str] = frozenset()
    # DQL filter fragments for dt.entity.service (FWR entity conditions).
    # Kept separate from surviving_fragments (span fragments) — these scope the
    # service-ID resolution query, not the span query directly.
    surviving_entity_fragments: list[str] = field(default_factory=list)
    # Attribute types present as surviving entity conditions (for candidate dedup,
    # mirroring surviving_attribute_types for span conditions).
    surviving_entity_attribute_types: frozenset[str] = frozenset()


def translate_conditions(rule: dict) -> TranslationResult:  # pylint: disable=too-many-locals
    deprecated_found = bool(rule.get("managementZones"))
    surviving_fragments: list[str] = []
    surviving_entity_fragments: list[str] = []
    unmigratable_reasons: list[str] = []
    pg_tag_values: list[list[str]] = []
    surviving_attribute_types: set[str] = set()
    surviving_entity_attribute_types: set[str] = set()
    surviving_primary_tag_keys: set[str] = set()

    rule_type = rule.get("type", "FULL_WEB_REQUEST")
    attr_map = ATTRIBUTE_MAP.get(rule_type, {})

    for condition in rule.get("conditions", []):
        attr_type = condition.get("attributeType", "")

        if attr_type == "PG_TAG":
            if _handle_pg_tag(
                condition, surviving_fragments, unmigratable_reasons,
                pg_tag_values, surviving_primary_tag_keys,
            ):
                deprecated_found = True
            continue

        # FWR entity conditions: resolved via dt.entity.service, not the span.
        if attr_type in _ENTITY_ATTRIBUTE_KEYS and rule_type == "FULL_WEB_REQUEST":
            entity_key = _ENTITY_ATTRIBUTE_KEYS[attr_type]
            fragment = _translate_to_entity_dql(condition, entity_key)
            if fragment is None:
                unmigratable_reasons.append(
                    f"Cannot translate {attr_type}: unsupported compareOperation"
                )
            else:
                surviving_entity_fragments.append(fragment)
                surviving_entity_attribute_types.add(attr_type)
            continue

        reason = _unmigratable_reason(rule_type, attr_type, attr_map)
        if reason is not None:
            unmigratable_reasons.append(reason)
            continue

        fragment = _translate_to_dql(condition, attr_map[attr_type])
        if fragment is None:
            unmigratable_reasons.append(
                f"Cannot translate {attr_type}: unsupported compareOperation"
            )
            continue
        surviving_fragments.append(fragment)
        surviving_attribute_types.add(attr_type)

    return TranslationResult(
        surviving_fragments=surviving_fragments,
        deprecated_found=deprecated_found,
        unmigratable_reasons=unmigratable_reasons,
        pg_tag_values=pg_tag_values,
        surviving_attribute_types=frozenset(surviving_attribute_types),
        surviving_primary_tag_keys=frozenset(surviving_primary_tag_keys),
        surviving_entity_fragments=surviving_entity_fragments,
        surviving_entity_attribute_types=frozenset(surviving_entity_attribute_types),
    )


def _unmigratable_reason(rule_type: str, attr_type: str, attr_map: dict[str, AttributeInfo]) -> str | None:
    """Return why a non-PG_TAG condition can't be translated, or None if it can."""
    if rule_type == "FULL_WEB_SERVICE" and attr_type in _ENTITY_ATTRIBUTE_KEYS:
        return (
            f"{attr_type} is not reliably available for web services — absent from the "
            "web-service entity and only present on the span for some agents "
            "(OneAgent resource attribute servlet.context.*); insufficient coverage to migrate safely"
        )
    if rule_type == "FULL_WEB_SERVICE" and attr_type in ENDPOINT_SPAN_UNRECOVERABLE_FWS:
        return (
            f"{attr_type} reads from the merged endpoint span where the stored value "
            "is an internal code, not the true discriminator; not reconstructable from "
            "the endpoint span (cross-span join is explicitly out of scope)"
        )
    if attr_type not in attr_map:
        return f"Unknown attributeType: {attr_type!r}"
    return None


def _translate_to_entity_dql(condition: dict, entity_key: str) -> str | None:
    """Translate a condition to a dt.entity.service DQL filter fragment.

    Reuses _op_expr with the entity attribute key instead of a span grail_key.
    Returns None if any compareOperation uses an unsupported matcher type.
    """
    ops = condition.get("compareOperations", [])
    if not ops:
        return None
    info = AttributeInfo(grail_key=entity_key, candidate_eligible=False, quality="good")
    parts: list[str] = []
    for op in ops:
        part = _translate_op(op, info)
        if part is None:
            return None
        parts.append(part)
    return " and ".join(parts) if parts else None


def _handle_pg_tag(  # pylint: disable=too-many-arguments
    condition: dict,
    surviving_fragments: list[str],
    unmigratable_reasons: list[str],
    pg_tag_values: list[list[str]],
    surviving_primary_tag_keys: set[str],
) -> bool:
    """Process a PG_TAG condition in place. Returns True if it carries anything
    deprecated; primary tags are translated as surviving fragments and their grail
    keys recorded (for candidate key-level dedup).

    Each compareOperation is judged on its own, because a v1 compareOperation *is* a
    settings-2.0 condition: the UI shows one condition per compareOperation. So one
    condition may legitimately hold an all-legacy operation to replace beside an
    all-primary operation to keep — that is not the illegal mixed shape.
    """
    ops = condition.get("compareOperations", [])
    # A condition with no operations, like an operation carrying no tags below, marks
    # the rule deprecated but contributes no PG scope: _resolve_pg_ids then returns
    # None (unscoped) rather than [] (abort). Pre-existing behaviour, pinned by
    # test_deprecated_pg_tag_with_unextractable_value_leaves_pg_ids_none_not_error.
    deprecated_found = not ops
    for op in ops:
        primary_pairs = _op_primary_tags(op)
        if primary_pairs and _op_non_primary_tag_count(op):
            # A single tags[] array mixing primary_tags.* with legacy tags. The classic
            # API is not supposed to accept this shape; the backend validation enforcing
            # that is not in place yet, so such a rule can still be created today and the
            # migrator has to handle it defensively. The Phase 3 mapper drops the whole
            # rule when any tag of a condition is non-primary.
            # Refuse it loudly rather than guess. Returning True is load-bearing: the
            # orchestrator's deprecated_found gate precedes its reasons gate, so a
            # reason recorded with a False return would be discarded.
            unmigratable_reasons.append(
                "PG_TAG compareOperation mixes primary_tags.* and deprecated tags "
                f"({_op_tag_summary(op)}). The classic API does not accept this "
                "combination, and on a Phase 3 tenant a single non-primary tag causes the "
                "entire rule to be dropped — migrate this rule by hand"
            )
            deprecated_found = True
            continue
        if primary_pairs:
            surviving_fragments.append(
                _primary_tag_op_fragment(primary_pairs, op.get("negate", False))
            )
            surviving_primary_tag_keys.update(key for key, _ in primary_pairs)
            continue
        group = [val for val in _extract_tag_strings(op) if val]
        if group:
            pg_tag_values.append(group)
        deprecated_found = True
    return deprecated_found


def _op_tag_keys(op: dict) -> list[str]:
    """The tag keys a PG_TAG compareOperation carries, in either format.

    The scalar format carries exactly one tag, so it can never be internally
    mixed — only mixed against a sibling operation.

    Scalar format:     {"value": "[cs]team:frontend"}     -> ["team"]
    Structured format: {"tags": [{"key": "k", ...}, ...]} -> ["k", ...]
    """
    if "value" in op:
        raw = str(op["value"])
        if raw.startswith("["):
            raw = raw.partition("]")[2]
        return [raw.partition(":")[0]]
    return [str(tag.get("key", "")) for tag in op.get("tags", [])]


def _op_non_primary_tag_count(op: dict) -> int:
    """How many of this operation's tags are *not* primary tags.

    Counting at the tag level is what distinguishes the illegal shape (mixing inside
    one ``tags[]`` array) from the legal one (an all-legacy operation beside an
    all-primary sibling, which is simply two conditions).
    """
    return len(_op_tag_keys(op)) - len(_op_primary_tags(op))


def _op_tag_summary(op: dict) -> str:
    """Operator-facing list of the tag keys one compareOperation names, deduplicated
    in first-seen order. Used in report reasons — never a raw dict repr."""
    return ", ".join(dict.fromkeys(key for key in _op_tag_keys(op) if key))


def _extract_tag_strings(op: dict) -> list[str]:
    """Serialise every tag a PG_TAG compareOperation carries, in either format.

    The structured format carries an array, and the product ORs the whole array, so
    all of them are returned — collecting only the first silently narrows the
    process-group scope.

    Scalar format: {"value": "[cs]team:frontend"} -> one element
    Structured format: {"tags": [{"context": "CONTEXTLESS", "key": "k", "value": "v"}, ...]}
    """
    if "value" in op:
        return [str(op["value"])]
    values: list[str] = []
    for tag in op.get("tags", []):
        context = tag.get("context", "CONTEXTLESS")
        key = tag.get("key", "")
        value = tag.get("value")
        prefix = "" if context == "CONTEXTLESS" else f"[{context}]"
        values.append(f"{prefix}{key}:{value}" if value else f"{prefix}{key}")
    return values


def _translate_to_dql(condition: dict, info: AttributeInfo) -> str | None:
    ops = condition.get("compareOperations", [])
    if not ops:
        return None

    parts: list[str] = []
    for op in ops:
        part = _translate_op(op, info)
        if part is None:
            return None
        parts.append(part)

    return " and ".join(parts) if parts else None


def _translate_op(op: dict, info: AttributeInfo) -> str | None:
    op_type = op.get("type", "")
    # API uses "values" (array); tolerate legacy "value" (scalar) too
    raw_values: list = op.get("values") or ([op["value"]] if "value" in op else [])
    negate = op.get("negate", False)
    ignore_case = op.get("ignoreCase", False)

    key = info.grail_key
    if not key or not raw_values:
        return None

    value_parts: list[str] = []
    for val in raw_values:
        expr = _op_expr(op_type, key, str(val), ignore_case)
        if expr is None:
            return None
        value_parts.append(expr)

    # Canonical (sorted) value order so a multi-value condition is order-insensitive
    # and equivalent conditions share a cache key.
    part = " or ".join(sorted(value_parts))
    if len(value_parts) > 1:
        part = f"({part})"
    if negate:
        part = f"not({part})"
    return part



PRIMARY_TAGS_PREFIX = "primary_tags."


def _op_primary_tags(op: dict) -> list[tuple[str, str | None]]:
    """Return the ``(grail_key, value)`` pairs of any primary tags in this PG_TAG
    compareOperation, for either format; empty if the op carries no primary tag.

    A primary tag's key starts with ``primary_tags.``. ``value`` is ``None`` for a
    key-only tag (``compareKeyOnly`` / no value → ``isNotNull``).

    Scalar format:     {"value": "primary_tags.ownership:team-alpha"}
    Structured format: {"tags": [{"context": "CONTEXTLESS",
                                   "key": "primary_tags.ownership", "value": "team-alpha"}]}
    """
    if "value" in op:
        raw = str(op["value"])
        if not raw.startswith(PRIMARY_TAGS_PREFIX):
            return []
        suffix = raw[len(PRIMARY_TAGS_PREFIX):]
        if not suffix:
            return []
        key, sep, val = suffix.partition(":")
        return [(f"{PRIMARY_TAGS_PREFIX}{key}", val or None if sep else None)]

    pairs: list[tuple[str, str | None]] = []
    for tag in op.get("tags", []):
        key = tag.get("key", "")
        if key.startswith(PRIMARY_TAGS_PREFIX):
            pairs.append((key, tag.get("value") or None))
    return pairs


def strip_deprecated_pg_tag_ops(condition: dict) -> dict | None:
    """Drop the deprecated compareOperations from a PG_TAG condition.

    Returns the condition unchanged when it is not a PG_TAG condition, ``None``
    when nothing survives (the caller drops it), and otherwise a copy carrying only
    the operations that survive Phase 3.

    A v1 ``compareOperation`` is a settings-2.0 condition in its own right, so
    "deprecated" is decided per operation: a condition may legitimately hold one
    all-primary operation to keep beside one all-legacy operation to drop. A
    *mixed* operation never reaches here — _handle_pg_tag refuses the rule as
    untranslatable well before a replacement body is built.
    """
    if condition.get("attributeType") != "PG_TAG":
        return condition
    surviving = [op for op in condition.get("compareOperations", []) if _op_primary_tags(op)]
    if not surviving:
        return None
    if len(surviving) == len(condition.get("compareOperations", [])):
        return condition
    return {**condition, "compareOperations": surviving}


def _primary_tag_expr(grail_key: str, value: str | None) -> str:
    """A single primary tag's DQL match expression. A value gives an equality match;
    a key-only tag gives isNotNull."""
    quoted_key = dql_field(grail_key)
    return f"{quoted_key} == {dql_string(value)}" if value is not None else f"isNotNull({quoted_key})"


def _primary_tag_op_fragment(pairs: list[tuple[str, str | None]], negate: bool) -> str:
    """Build the DQL span fragment for one primary-tag compareOperation.

    The operation is a single settings-2.0 condition, so its tags OR. ANDing them
    would demand one key equal two values at once. Parenthesised only when there is
    more than one tag, so single-tag fragments stay byte-identical; sorted for a
    stable cache key. ``negate`` wraps the whole group — per-tag negation is only
    equivalent under AND.
    """
    exprs = sorted(_primary_tag_expr(key, value) for key, value in pairs)
    joined = exprs[0] if len(exprs) == 1 else "(" + " or ".join(exprs) + ")"
    return f"not({joined})" if negate else joined


def _op_expr(op_type: str, key: str, val: str, ignore_case: bool) -> str | None:
    if op_type == "STRING_EQUALS":
        if ignore_case:
            return f"lower({key}) == {dql_string(val.lower())}"
        return f"{key} == {dql_string(val)}"
    if op_type == "STRING_CONTAINS":
        return f"contains({key}, {dql_string(val)})"
    if op_type == "STARTS_WITH":
        return f"startsWith({key}, {dql_string(val)})"
    if op_type == "ENDS_WITH":
        return f"endsWith({key}, {dql_string(val)})"
    return None
