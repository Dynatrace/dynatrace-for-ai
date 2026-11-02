"""Pure DQL query builders for the migration workflow.

The orchestrator is responsible for:

- splitting a rule's translated conditions by ``fetch_source`` (service vs PG),
- collecting any service-ID constraint (``S_super_orig``) from a prior query,
- and calling :func:`build_entity_plan` or :func:`build_span_query`.

The builders themselves are deterministic, side-effect-free and known-good
against the SKILL spec's example queries.

Coverage in this module:

- A.1, C.1 — :func:`build_entity_plan`
- C.2 (+ Case A span fallback) — :func:`build_span_query`

A.2 is the span fallback query, invoked only when entity-side candidate scoring
yields zero candidates; it is dispatched by the orchestrator, not this module.
"""

from __future__ import annotations

from .entity import (  # pylint: disable=no-name-in-module
    ENTITY_PROJECTION,
    EntityQueryPlan,
    build_entity_plan,
)
from .span import (  # pylint: disable=no-name-in-module
    SPAN_GROUP_BY_KEYS,
    build_primary_tag_discovery_query,
    build_span_query,
)

__all__ = [
    "ENTITY_PROJECTION",
    "EntityQueryPlan",
    "SPAN_GROUP_BY_KEYS",
    "build_entity_plan",
    "build_primary_tag_discovery_query",
    "build_span_query",
]
