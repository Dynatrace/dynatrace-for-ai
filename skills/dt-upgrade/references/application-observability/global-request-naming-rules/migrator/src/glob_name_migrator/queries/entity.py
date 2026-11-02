"""Entity-side DQL query builder for A.1 and C.1.

Branches by which entity ``fetch_source`` the rule's conditions target:

- **service-only** — single ``fetch dt.entity.service`` query.
- **PG-only**      — two queries: ``fetch dt.entity.process_group`` followed
  by a service query constrained to those PG IDs.
- **mixed**        — same as PG-only, but the service query also AND-joins
  the rule's service-side conditions.

Projection is derived from ``rules/mapping.py`` (``load_mapping()``): ``id`` and
``serviceType`` are structural (row identity + scope-aware resolution), plus
every entity attribute where ``fetch_source == dt.entity.service`` and
``candidate_eligible == True``.  A startup assertion enforces that every
``candidate_eligible`` entry carries a non-null ``dql_key`` so the null check
is not needed at query-build time.
Non-candidate fields (``tags`` → SERVICE_TAG, ``managementZones``) are
excluded — they are used in filter conditions but add no value to the
returned row set.

Timeframe note
--------------
``fetch dt.entity.*`` filters by entity lifetime — only entities whose
lifetime overlaps the query timeframe are returned.  The DQL API default is
the last 2 hours.  Callers should pass ``timeframe`` explicitly so the
entity and span queries use the same window and results are consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ..rules.mapping import load_mapping

# Structural columns always included regardless of candidate_eligible.
_STRUCTURAL: tuple[str, ...] = ("id", "serviceType")

# Placeholder substring used in service-side queries when PG IDs from the
# first query need to be substituted in by the orchestrator.  Choosing a
# DQL-unsafe token guarantees a malformed query if it leaks unsubstituted.
PG_IDS_PLACEHOLDER = "<<PG_IDS>>"

# Default timeframe applied to entity queries to match the span query default.
_DEFAULT_ENTITY_WINDOW = "from:now()-2h, to:now()"


@lru_cache(maxsize=1)
def _entity_projection() -> tuple[str, ...]:
    """Stable, sorted projection for ``fetch dt.entity.service``.

    Includes ``id``, ``serviceType``, and all entity attributes with
    ``fetch_source == dt.entity.service`` and ``candidate_eligible == True``.
    The mapping loader enforces that every ``candidate_eligible`` row has a
    non-null ``dql_key``, so no null check is needed here.
    Structural columns come first; the rest are sorted for deterministic query text.
    """
    structural = list(_STRUCTURAL)
    candidate_keys: list[str] = []
    seen: set[str] = set(structural)
    for row in load_mapping().entity_attributes:
        if (
            row.dql_key is not None
            and row.fetch_source == "dt.entity.service"
            and row.candidate_eligible
            and row.dql_key not in seen
        ):
            seen.add(row.dql_key)
            candidate_keys.append(row.dql_key)
    return tuple(structural + sorted(candidate_keys))


# Public, lazily-computed view for tests.
def __getattr__(name: str):  # noqa: D401
    if name == "ENTITY_PROJECTION":
        return _entity_projection()
    raise AttributeError(name)


@dataclass(frozen=True)
class EntityQueryPlan:
    """A 1- or 2-query plan for an entity-side step.

    ``pg_query`` is ``None`` for the service-only branch; otherwise it must be
    run first and its ``id`` rows substituted for :data:`PG_IDS_PLACEHOLDER` in
    ``service_query`` before execution.
    """

    pg_query: str | None
    service_query: str


def build_entity_plan(
    *,
    service_side_filters: list[str],
    pg_side_filters: list[str],
    management_zones_dql: str | None = None,
    timeframe: str | None = None,
) -> EntityQueryPlan:
    """Build the entity-side query plan.

    ``*_filters`` are DQL fragments already produced by the translator (no
    further escaping is performed). ``management_zones_dql`` is service-side
    and always AND-joined onto the service query.

    ``timeframe`` is the DQL time window string (e.g. ``"from:now()-2h, to:now()"``).
    Defaults to :data:`_DEFAULT_ENTITY_WINDOW` (``from:now()-2h, to:now()``) when
    ``None``.
    """

    effective_timeframe = timeframe or _DEFAULT_ENTITY_WINDOW

    service_filters = list(service_side_filters)
    if management_zones_dql:
        service_filters.append(management_zones_dql)

    pg_only = bool(pg_side_filters) and not service_filters
    needs_pg = bool(pg_side_filters)

    if not needs_pg:
        return EntityQueryPlan(
            pg_query=None,
            service_query=_render_service_query(service_filters, effective_timeframe),
        )

    pg_query = _render_pg_query(pg_side_filters, effective_timeframe)
    # Service query must additionally constrain to PG IDs the orchestrator
    # will substitute. PG-only case still produces a service query so the
    # downstream cache file (``_s_super.json``) always exists.
    service_filters_with_pg = list(service_filters)
    service_filters_with_pg.append(
        f"in(runs_on[`dt.entity.process_group`], {PG_IDS_PLACEHOLDER})"
    )
    _ = pg_only  # variable kept for readability of intent above
    return EntityQueryPlan(
        pg_query=pg_query,
        service_query=_render_service_query(service_filters_with_pg, effective_timeframe),
    )


# ---------- internals ----------------------------------------------------- #


def _render_service_query(filters: list[str], timeframe: str) -> str:
    filter_clause = _and_join(["isExternalService != true", *filters])
    projection = ",\n         ".join(_entity_projection())
    return (
        f"fetch dt.entity.service, {timeframe}\n"
        f"| filter {filter_clause}\n"
        f"| fields {projection}"
    )


def _render_pg_query(filters: list[str], timeframe: str) -> str:
    filter_clause = _and_join(filters)
    return (
        f"fetch dt.entity.process_group, {timeframe}\n"
        f"| filter {filter_clause}\n"
        "| fields id"
    )


def _and_join(filters: list[str]) -> str:
    if not filters:
        # Defensive — an empty filter would be a malformed DQL query; the
        # service-side branch always has at least ``isExternalService != true``.
        raise ValueError("entity query requires at least one filter")
    if len(filters) == 1:
        return filters[0]
    return "\n   and ".join(filters)


__all__ = [
    "EntityQueryPlan",
    "PG_IDS_PLACEHOLDER",
    "build_entity_plan",
]
