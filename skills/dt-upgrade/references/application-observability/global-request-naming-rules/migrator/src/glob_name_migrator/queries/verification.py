"""Verification DQL builders for the overselect loop.

Two query shapes depending on dispatch mode:

- **entity**: ``fetch dt.entity.service | filter … | fields id, <extra>``
- **span**: ``fetch spans, from:…, to:… | filter … | summarize …``

The filter string is built externally (in ``overselect_loop``) from the
combined surviving + candidate + negation fragments and passed in as a plain
string.  These builders are pure functions with no side effects.
"""

from __future__ import annotations

import hashlib

from .span import _WEBREQUEST_URL_EXPR

_DEFAULT_ENTITY_WINDOW = "from:now()-2h, to:now()"


def build_entity_verification_query(
    filter_str: str,
    extra_fields: list[str] | None = None,
    timeframe: str | None = None,
) -> str:
    """Verification entity query — returns service IDs (and optional extra fields) matching the filter.

    ``extra_fields`` should list additional DQL column names to fetch alongside
    ``id`` so that the overselect loop can run negation search on the returned rows.
    ``timeframe`` must match the timeframe used for the original entity query so
    the same entities are visible.
    """
    field_list = ["id"]
    if extra_fields:
        field_list.extend(extra_fields)
    fields_clause = ", ".join(field_list)
    tf = timeframe or _DEFAULT_ENTITY_WINDOW
    return (
        f"fetch dt.entity.service, {tf}\n"
        f"| filter isExternalService != true and {filter_str}\n"
        f"| fields {fields_clause}"
    )


def build_span_verification_query(
    filter_str: str, window_from: str, window_to: str
) -> str:
    """Verification span query — returns (service, endpoint) pairs matching the filter."""
    return (
        f"fetch spans, from:{window_from}, to:{window_to}\n"
        f"{_WEBREQUEST_URL_EXPR}"
        f"| filter isNotNull(endpoint.name)\n"
        f'   and dt.openpipeline.source != "/api/v2/otlp/v1/traces"\n'
        f"   and isNull(dt.endpoint_detection.rule_id)\n"
        f"   and {filter_str}\n"
        "| summarize span_count = count(), "
        "by: { dt.smartscape.service, endpoint.name }"
    )


def verification_cache_key(  # pylint: disable=too-many-arguments
    *,
    dispatch: str,
    entity_key: str,
    span_key: str | None,
    filter_str: str,
    window_from: str | None,
    window_to: str | None,
) -> str:
    """Deterministic 16-hex cache key for a verification query.

    Sensitive to every input so a changed filter or shifted window produces a
    distinct key and therefore a distinct cache file — no stale hits.
    """
    parts = [
        dispatch,
        entity_key,
        span_key or "",
        filter_str,
        window_from or "",
        window_to or "",
    ]
    digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()
    return digest[:16]


__all__ = [
    "build_entity_verification_query",
    "build_span_verification_query",
    "verification_cache_key",
]
