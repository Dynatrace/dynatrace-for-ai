from __future__ import annotations

from .conditions import ATTRIBUTE_MAP, dql_field, dql_string

_FIXED_FILTERS = [
    "isNotNull(endpoint.name)",
    'dt.openpipeline.source != "/api/v2/otlp/v1/traces"',
    "isNull(dt.endpoint_detection.rule_id)",
]


def build_pg_query(mgmt_zone_names: list[str], window: str) -> str:
    """Build a DQL entity query that resolves management zone names to process-group IDs."""
    zone_parts = sorted(f"matchesValue(managementZones, {dql_string(z)})" for z in mgmt_zone_names)
    if len(zone_parts) == 1:
        zone_filter = zone_parts[0]
    else:
        zone_filter = "(" + " or ".join(zone_parts) + ")"
    return f"fetch dt.entity.process_group, from:{window} | filter {zone_filter} | fields id"


def _pg_tag_expr(value: str) -> str:
    """A single tag's dt.entity.process_group match expression.

    A ``key:value`` tag is an exact match; a bare key matches the key with any value
    (bug 20).
    """
    if ":" in value:
        return f"iAny(tags[] == {dql_string(value)})"
    return f"iAny(tags[] == {dql_string(value)} or startsWith(tags[], {dql_string(value + ':')}))"


def build_pg_tag_query(tag_groups: list[list[str]], window: str) -> str:
    """Build a DQL entity query resolving non-primary PG tag values to process-group IDs.

    ``tag_groups`` carries one group per PG_TAG compareOperation. The product ORs the
    tags within one operation and ANDs across operations and conditions
    so groups are OR-joined internally and AND-joined with each other.

    Both joins sort so that equivalent conditions render identically and share a cache
    key. A single-tag group renders unparenthesised, keeping the query text
    byte-identical to the pre-grouping form.
    """
    group_parts: list[str] = []
    for group in tag_groups:
        parts = sorted(_pg_tag_expr(v) for v in group)
        if not parts:
            continue
        group_parts.append(parts[0] if len(parts) == 1 else "(" + " or ".join(parts) + ")")
    filter_clause = " and ".join(sorted(group_parts))
    return f"fetch dt.entity.process_group, from:{window} | filter {filter_clause} | fields id"


_SERVICE_TYPE_FILTER = 'serviceType == "WEB_REQUEST_SERVICE" and isExternalService != true'


def build_service_entity_query(pg_ids: list[str] | None, window: str) -> str:
    """Build a DQL entity query to discover APPLICATION_ID and CONTEXT_ROOT values.

    pg_ids=None means no PG-level conditions on the rule; the query is legitimately
    unscoped. pg_ids=[] means PG conditions resolved to zero results, which the caller
    must already have short-circuited before reaching here — treated as a hard error.
    """
    if pg_ids is not None and not pg_ids:
        raise ValueError("build_service_entity_query: pg_ids must be non-empty or None, got []")
    parts = [f"fetch dt.entity.service, from:{window}", f"filter {_SERVICE_TYPE_FILTER}"]
    if pg_ids:
        pg_array = ", ".join(f'"{p}"' for p in sorted(pg_ids))
        parts.append(f"filter in(runs_on[`dt.entity.process_group`], array({pg_array}))")
    return " | ".join(parts) + " | fields id, webApplicationId, contextRoot"


def build_service_id_query(
    entity_fragments: list[str],
    window: str,
    *,
    pg_ids: list[str] | None = None,
) -> str:
    """Build a DQL entity query to resolve entity fragments to service IDs and hosting PGs.

    Returns a query yielding {id, runs_on[dt.entity.process_group]} rows for services
    matching the entity conditions. Includes serviceType and isExternalService guards.
    pg_ids=None means the query is not narrowed to specific PGs; pg_ids=[] is a hard error.
    """
    if pg_ids is not None and not pg_ids:
        raise ValueError("build_service_id_query: pg_ids must be non-empty or None, got []")
    parts = [f"fetch dt.entity.service, from:{window}", f"filter {_SERVICE_TYPE_FILTER}"]
    if pg_ids:
        pg_array = ", ".join(f'"{p}"' for p in sorted(pg_ids))
        parts.append(f"filter in(runs_on[`dt.entity.process_group`], array({pg_array}))")
    for fragment in sorted(entity_fragments):
        parts.append(f"filter {fragment}")
    parts.append("fields id, runs_on[dt.entity.process_group]")
    return " | ".join(parts)


def build_primary_tag_discovery_query() -> str:
    """Enumerate the tenant's ``primary_tags.<key>`` span field names.

    Value-consuming DQL ops don't accept a wildcard, so keys must be discovered
    before they can be aggregated. ``fieldsSnapshot`` reads cheap precomputed field
    metadata; keys are tenant-global, so this runs once per migration run.
    """
    return 'fieldsSnapshot spans | filter matchesValue(field, "primary_tags.*") | fields field'


def build_span_query(  # pylint: disable=too-many-arguments
    pg_ids: list[str] | None,
    surviving_fragments: list[str],
    window: str,
    rule_type: str,
    *,
    include_candidate_keys: bool = True,
    primary_tag_keys: list[str] | None = None,
    service_ids: list[str] | None = None,
) -> str:
    """Build a DQL span query for target-set computation or verification.

    pg_ids=None means no PG-level conditions on the rule; the query is legitimately
    unscoped by PG. pg_ids=[] means PG conditions resolved to zero results, which the
    caller must already have short-circuited before reaching here — treated as a hard
    error.
    """
    if pg_ids is not None and not pg_ids:
        raise ValueError("build_span_query: pg_ids must be non-empty or None, got []")
    filters = list(_FIXED_FILTERS)

    if pg_ids:
        pg_array = ", ".join(f'"{p}"' for p in sorted(pg_ids))
        filters.append(f"in(dt.entity.process_group, array({pg_array}))")

    if service_ids:
        svc_array = ", ".join(f'"{s}"' for s in sorted(service_ids))
        filters.append(f"in(dt.entity.service, array({svc_array}))")

    filters.extend(surviving_fragments)

    # Canonical (sorted) fragment order so filters that differ only in condition
    # order produce identical query text and therefore share a cache key.
    filter_clause = " and ".join(sorted(filters))

    group_keys: list[str] = ["dt.entity.process_group", "endpoint.name"]
    if include_candidate_keys:
        for info in ATTRIBUTE_MAP.get(rule_type, {}).values():
            if info.candidate_eligible and info.grail_key:
                group_keys.append(info.grail_key)
        group_keys.extend(dql_field(key) for key in primary_tag_keys or [])

    summarize_clause = ", ".join(sorted(set(group_keys)))

    return (
        f"fetch spans, from:{window}"
        f" | filter {filter_clause}"
        f" | summarize count(), by: {{{summarize_clause}}}"
    )
