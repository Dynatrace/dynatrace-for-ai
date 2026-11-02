"""Span-side DQL query builder for C.2 and the Case A span fallback.

All queries share the same shape:

```
fetch spans, from:now()-5m, to:now()
| filter isNotNull(endpoint.name)
   and <translated span conditions>
   [and in(dt.smartscape.service, toSmartscapeId("SERVICE-…"), …)]   // C.2 and A.2 only
| summarize span_count = count(),
            by: { dt.smartscape.service, endpoint.name, <Grail keys…> }
```

The ``summarize ... by`` keys are derived from ``rules/mapping.py`` (``load_mapping()``):
every span attribute with ``candidate_eligible == True``, plus the two
structural axes ``dt.smartscape.service`` and ``endpoint.name``.  The mapping
loader enforces that every ``candidate_eligible`` row has a non-null
``dql_key``.  Non-candidate fields (e.g.
``supportability.is_non_key_requests_endpoint_bucket`` → IS_KEY_REQUEST) are
excluded.
"""

from __future__ import annotations

from functools import lru_cache

from ..rules.mapping import load_mapping
from ..rules.tags import PRIMARY_TAGS_PREFIX

_FIXED_GROUP_BY: tuple[str, ...] = ("dt.smartscape.service", "endpoint.name")
_DEFAULT_WINDOW = "from:now()-2h, to:now()"

# Artificial column that reconstructs WEBREQUEST_URL from its runtime fragments.
# WEBREQUEST_URL = server.address + optional ":port" + url.path (no scheme, no query).
# server.port is null on ~94% of server spans so the port segment is null-guarded.
_WEBREQUEST_URL_FIELD = "dt_webrequest_url"
_WEBREQUEST_URL_EXPR = (
    f'| fieldsAdd {_WEBREQUEST_URL_FIELD} = concat('
    'server.address, '
    'if(isNotNull(server.port), concat(":", toString(server.port)), else: ""), '
    'url.path)\n'
)


@lru_cache(maxsize=1)
def _span_group_by_keys() -> tuple[str, ...]:
    """Stable, sorted Grail keys for the span group-by list.

    Only ``candidate_eligible == True`` attributes are included — non-candidate
    fields add no value to the returned row set and unnecessarily widen the
    summarize projection.  Order is sorted for deterministic query text →
    deterministic cache keys.
    """
    keys: set[str] = set()
    for row in load_mapping().span_attributes:
        if row.candidate_eligible:
            keys.add(row.dql_key)  # type: ignore[arg-type]  # validator guarantees non-null
    # Remove anything already in the fixed axes to avoid duplicates.
    for fixed in _FIXED_GROUP_BY:
        keys.discard(fixed)
    return tuple(sorted(keys))


# Public, lazily-computed view.  Tests import this to assert stability.
def __getattr__(name: str):  # noqa: D401 - dunder helper
    if name == "SPAN_GROUP_BY_KEYS":
        return _span_group_by_keys()
    raise AttributeError(name)


def build_span_query(
    *,
    span_filters: list[str],
    service_id_constraint: list[str] | None = None,
    window: str | None = None,
    primary_tag_keys: list[str] | None = None,
) -> str:
    """Render a span query for C.2 (with constraint) or the Case A span fallback.

    ``span_filters`` are DQL fragments from the translator. ``service_id_constraint``
    contains raw service IDs (e.g. ``"SERVICE-1234"``) which become
    ``in(dt.smartscape.service, toSmartscapeId("SERVICE-1234"), …)``.

    ``window`` overrides the default ``from:now()-2h, to:now()`` range.

    ``primary_tag_keys`` are tenant-discovered ``primary_tags.*`` columns to
    project alongside the mapped span attributes, so they can be scored as
    candidates. They are not in ``rules/mapping.py`` because they are tenant
    data, not a static attribute table.
    """

    effective_window = window or _DEFAULT_WINDOW
    filters: list[str] = [
        "isNotNull(endpoint.name)",
        'dt.openpipeline.source != "/api/v2/otlp/v1/traces"',
        "isNull(dt.endpoint_detection.rule_id)",
        *span_filters,
    ]
    if service_id_constraint:
        filters.append(_smartscape_in(service_id_constraint))

    extra_keys = sorted(set(primary_tag_keys or ()) - set(_FIXED_GROUP_BY))
    by_list = ", ".join((*_FIXED_GROUP_BY, *_span_group_by_keys(), *extra_keys))

    return (
        f"fetch spans, {effective_window}\n"
        f"{_WEBREQUEST_URL_EXPR}"
        f"| filter {_and_join(filters)}\n"
        "| summarize span_count = count(),\n"
        f"            by: {{ {by_list} }}"
    )


def build_primary_tag_discovery_query() -> str:
    """Enumerate the tenant's ``primary_tags.*`` span columns.

    Value-consuming DQL operations reject a wildcard field reference, so the keys
    have to be listed from the schema snapshot before they can be aggregated.
    Keys are tenant-global — one call per run covers the whole corpus.
    """
    return (
        "fieldsSnapshot spans\n"
        f'| filter matchesValue(field, "{PRIMARY_TAGS_PREFIX}*")\n'
        "| fields field"
    )


# ---------- internals ----------------------------------------------------- #


def _smartscape_in(ids: list[str]) -> str:
    args = ", ".join(f'toSmartscapeId("{i}")' for i in ids)
    return f"in(dt.smartscape.service, {{{args}}})"


def _and_join(filters: list[str]) -> str:
    if not filters:
        raise ValueError("span query requires at least one filter")
    return "\n   and ".join(filters)


__all__ = ["build_primary_tag_discovery_query", "build_span_query"]
