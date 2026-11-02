from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .candidates import Candidate, DiscardedAttribute, score_candidates, score_entity_candidates
from .conditions import _ENTITY_ATTRIBUTE_KEYS, translate_conditions
from .query_builder import (
    build_pg_query,
    build_pg_tag_query,
    build_primary_tag_discovery_query,
    build_service_entity_query,
    build_service_id_query,
    build_span_query,
)
from .report_builder import build_replacement_body
from .verifier import Negation, VerifyResult, extract_target_keys, verify
from .windowing import retry_window

# Every verdict `RuleResult.verdict` can carry, in CLI summary display order.
# Single source of truth — the console summary iterates this, so a new verdict cannot
# go missing from the table or the counts.
VERDICTS: tuple[str, ...] = (
    "error",
    "migrated",
    "no_replacement",
    "untranslatable",
    "skipped_not_deprecated",
    "skipped_disabled",
)

_DEFAULT_WINDOW = "now()-2h"
_MAX_SPAN_RETRIES = 3
_MAX_UNDER_SELECT_RETRIES = 1


@dataclass
class RuleResult:  # pylint: disable=too-many-instance-attributes
    rule_id: str
    rule_type: str
    verdict: str  # one of VERDICTS
    rule_name: str | None = None
    replacement_body: dict | None = None
    reasons: list[str] = field(default_factory=list)
    entity_candidates: list[Candidate] = field(default_factory=list)
    target_set: frozenset[tuple[str, str]] | None = None
    candidates: list[Candidate] = field(default_factory=list)
    discarded_attributes: list[DiscardedAttribute] = field(default_factory=list)
    chosen_candidates: list[Candidate] = field(default_factory=list)
    pg_ids: list[str] = field(default_factory=list)
    window: str | None = None
    negations: list[Negation] = field(default_factory=list)
    escalated_candidates: list[Candidate] = field(default_factory=list)
    demoted_from: list[Candidate] = field(default_factory=list)
    span_retries: int = 0
    under_select_retries: int = 0
    best_effort: bool = False
    cache_hits: int = 0
    cache_misses: int = 0
    # Report auditability: original_conditions/management_zones are the
    # rule's classic scope before translation, populated for every rule that was
    # read (None on the error path where the rule was never fetched).
    # surviving_fragments are the DQL span fragments translation kept and applied;
    # None means translation did not run (skipped_* paths), [] means it ran and
    # kept nothing.
    original_conditions: list[dict] | None = None
    management_zones: list[str] | None = None
    surviving_fragments: list[str] | None = None


@dataclass
class MigrationOutcome:
    results: list[RuleResult]
    unknown_rule_ids: list[str]


def discover_primary_tag_keys(dql_client: Any) -> list[str]:
    """Enumerate the tenant's ``primary_tags.<key>`` span fields.

    Keys are tenant-global, so a migration run discovers them once and threads the
    list into every rule's target-set span query and candidate scoring."""
    rows = dql_client.execute(build_primary_tag_discovery_query())
    return sorted({row["field"] for row in rows if row.get("field")})


def run_migration(
    config_client: Any,
    dql_client: Any,
    window: str = _DEFAULT_WINDOW,
    rule_ids: list[str] | None = None,
) -> MigrationOutcome:
    rule_stubs = config_client.list_all_rules()
    unknown: list[str] = []
    if rule_ids is not None:
        # requested stays an ordered, deduped list (not a set) so `unknown` is reported
        # in the same order the caller asked for the IDs; wanted is a set purely for
        # O(1) membership checks in the rule_stubs filter below.
        requested = list(dict.fromkeys(rule_ids))
        present = {s.id for s in rule_stubs}
        unknown = [rid for rid in requested if rid not in present]
        wanted = set(requested)
        rule_stubs = [s for s in rule_stubs if s.id in wanted]
    # Primary-tag keys are tenant-global: discover them once and reuse across rules.
    # The result feeds every rule's target-set span query + scoring.
    # Discovery is best-effort — a failed metadata query just disables tag mining
    # for the run rather than aborting every rule.
    try:
        primary_tag_keys = discover_primary_tag_keys(dql_client)
    except Exception:  # pylint: disable=broad-except
        primary_tag_keys = []
    results = [
        _run_one_rule(rule_stub, config_client, dql_client, window, primary_tag_keys)
        for rule_stub in rule_stubs
    ]
    return MigrationOutcome(results=results, unknown_rule_ids=unknown)


def _run_one_rule(
    rule_stub: Any, config_client: Any, dql_client: Any, window: str, primary_tag_keys: list[str]
) -> RuleResult:
    """Process one rule and attribute this rule's cache hits/misses to its result."""
    before_hits, before_misses = _cache_counts(dql_client)
    try:
        rule = config_client.get_rule(rule_stub.rule_type, rule_stub.id)
        result = _process_rule(rule_stub, rule, dql_client, window, primary_tag_keys)
        # The rule was read: attach its classic scope for the report.
        result.original_conditions = rule.get("conditions", [])
        result.management_zones = rule.get("managementZones", [])
    except Exception as exc:  # pylint: disable=broad-except
        result = RuleResult(
            rule_id=rule_stub.id,
            rule_type=rule_stub.rule_type,
            verdict="error",
            reasons=[f"{type(exc).__name__}: {exc}"],
        )
    result.rule_name = rule_stub.name
    hits, misses = _cache_counts(dql_client)
    result.cache_hits = hits - before_hits
    result.cache_misses = misses - before_misses
    return result


def _cache_counts(dql_client: Any) -> tuple[int, int]:
    """Read (hits, misses) off a caching client, or (0, 0) if it has no stats."""
    stats = getattr(dql_client, "stats", None)
    if stats is None:
        return (0, 0)
    return (stats.hits, stats.misses)


def _derive_cap_b_service_ids(entity_rows: list[dict], cap_b_candidates: list[Candidate]) -> list[str]:
    """Derive service_ids in-memory from entity rows whose attribute values match
    all discovered capability-B candidates (AND across types, OR within a type).

    Used when a FWR rule has no surviving entity condition but entity candidates
    are discovered — the span and verify queries are scoped to those services so
    services lacking the candidate values are excluded from the target set.
    """
    entity_field_to_values: dict[str, frozenset[str]] = {}
    for c in cap_b_candidates:
        entity_field = _ENTITY_ATTRIBUTE_KEYS.get(c.attribute_type)
        if entity_field:
            entity_field_to_values[entity_field] = frozenset(c.values)
    if not entity_field_to_values:
        return []
    matching: list[str] = []
    for row in entity_rows:
        if all(str(row.get(f, "")) in vs for f, vs in entity_field_to_values.items()):
            if row.get("id"):
                matching.append(row["id"])
    return sorted(set(matching))


def _extract_service_scope(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Extract (service_ids, derived_pg_ids) from build_service_id_query rows.

    Each row has 'id' (service ID) and 'runs_on[dt.entity.process_group]' (list of PG IDs).
    Returns both sorted for deterministic query text.
    """
    service_ids: list[str] = sorted({r["id"] for r in rows if r.get("id")})
    pg_ids: set[str] = set()
    for row in rows:
        pgs = row.get("runs_on[dt.entity.process_group]") or []
        if isinstance(pgs, list):
            pg_ids.update(pgs)
        elif pgs:
            pg_ids.add(pgs)
    return service_ids, sorted(pg_ids)


def _query_target_set(  # pylint: disable=too-many-arguments
    pg_ids: list[str] | None,
    translation: Any,
    win: str,
    rule_type: str,
    dql_client: Any,
    *,
    primary_tag_keys: list[str],
    service_ids: list[str] | None = None,
) -> tuple[list[dict], frozenset[tuple[str, str]], list[Candidate], list[DiscardedAttribute]]:
    rows = dql_client.execute(
        build_span_query(
            pg_ids, translation.surviving_fragments, win, rule_type,
            primary_tag_keys=primary_tag_keys,
            service_ids=service_ids,
        )
    )
    target_set = extract_target_keys(rows)
    # Block surviving-condition attribute types from candidacy so scoring never
    # re-derives a condition the rule already carries. Primary-tag keys already
    # surviving on the rule are deduped per key.
    candidates, discarded_attributes = score_candidates(
        rows, rule_type, translation.surviving_attribute_types,
        primary_tag_keys=primary_tag_keys,
        surviving_primary_tag_keys=translation.surviving_primary_tag_keys,
    )
    return rows, target_set, candidates, discarded_attributes


@dataclass
class _VerificationOutcome:  # pylint: disable=too-many-instance-attributes
    verify_result: VerifyResult
    window: str
    target_set: frozenset[tuple[str, str]]
    candidates: list[Candidate]
    discarded_attributes: list[DiscardedAttribute]
    span_retries: int = 0
    under_select_retries: int = 0
    best_effort: bool = False


def _query_target_set_with_retry(  # pylint: disable=too-many-arguments
    pg_ids: list[str] | None, translation: Any, window: str, rule_type: str, dql_client: Any,
    *, primary_tag_keys: list[str], service_ids: list[str] | None = None,
) -> tuple[frozenset[tuple[str, str]], list[Candidate], list[DiscardedAttribute], str, int]:
    """Run the span target-set query, retrying with time-shifted windows if it
    returns no data. Returns (target_set, candidates,
    discarded_attributes, effective_window, span_retries)."""
    rows, target_set, candidates, discarded_attributes = _query_target_set(
        pg_ids, translation, window, rule_type, dql_client,
        primary_tag_keys=primary_tag_keys, service_ids=service_ids,
    )
    span_retries = 0
    if not rows:
        for attempt in range(1, _MAX_SPAN_RETRIES + 1):
            retry_win = retry_window(window, attempt)
            rows, target_set, candidates, discarded_attributes = _query_target_set(
                pg_ids, translation, retry_win, rule_type, dql_client,
                primary_tag_keys=primary_tag_keys, service_ids=service_ids,
            )
            span_retries = attempt
            if rows:
                window = retry_win
                break
    return target_set, candidates, discarded_attributes, window, span_retries


def _query_and_verify(  # pylint: disable=too-many-arguments,too-many-locals
    pg_ids: list[str] | None, translation: Any, rule_type: str, window: str, dql_client: Any,
    *, primary_tag_keys: list[str],
    service_ids: list[str] | None = None,
    verify_pg_ids: list[str] | None = None,
) -> _VerificationOutcome:
    """Run the span target-set query (retrying on no data), verify the scored
    candidates against it, and retry once more with an earlier window if every
    candidate under-selects.

    service_ids / verify_pg_ids: from entity-condition resolution.
    When present, both span and verify queries are additionally scoped by these.
    """
    target_set, candidates, discarded_attributes, window, span_retries = _query_target_set_with_retry(
        pg_ids, translation, window, rule_type, dql_client,
        primary_tag_keys=primary_tag_keys, service_ids=service_ids,
    )
    # has_surviving_conditions: True when either span fragments OR entity fragments
    # survive (entity-only surviving conditions must also enable the surviving-only
    # verify path).
    has_surviving = bool(translation.surviving_fragments) or bool(translation.surviving_entity_fragments)

    def _build_verify_query(win: str, frags: list[str]) -> str:
        # Verification scopes by exactly the non-deprecated conditions retained in
        # the emitted rule. Entity conditions (APPLICATION_ID/CONTEXT_ROOT) are
        # surviving, so their service_ids + derived_pg_ids ARE applied. The
        # deprecated process-group scope (MZ/PG_TAG) is always excluded.
        return build_span_query(
            verify_pg_ids, translation.surviving_fragments + frags, win, rule_type,
            service_ids=service_ids,
        )

    verify_result = verify(
        target_set, candidates, rule_type, lambda frags: _build_verify_query(window, frags), dql_client,
        has_surviving_conditions=has_surviving,
    )

    outcome = _VerificationOutcome(
        verify_result, window, target_set, candidates, discarded_attributes, span_retries=span_retries
    )
    if verify_result.verdict != "under_select":
        return outcome

    outcome.under_select_retries = _MAX_UNDER_SELECT_RETRIES
    outcome.window = retry_window(window, _MAX_UNDER_SELECT_RETRIES)
    _, outcome.target_set, outcome.candidates, outcome.discarded_attributes = _query_target_set(
        pg_ids, translation, outcome.window, rule_type, dql_client,
        primary_tag_keys=primary_tag_keys, service_ids=service_ids,
    )
    retried_result = verify(
        outcome.target_set, outcome.candidates, rule_type,
        lambda frags: _build_verify_query(outcome.window, frags), dql_client,
        has_surviving_conditions=has_surviving,
    )
    if retried_result.verdict == "exact":
        outcome.verify_result = retried_result
    else:
        outcome.best_effort = True
        if retried_result.candidates:
            outcome.verify_result = retried_result
    return outcome


def _resolve_pg_ids(rule: dict, translation: Any, dql_client: Any, window: str) -> list[str] | None:
    """Return the resolved PG IDs.

    None  — no PG-level conditions; span query proceeds unfiltered.
    []    — PG-level conditions existed but resolved to 0 results; caller must abort.
    [..] — normal non-empty PG set.
    """
    mgmt_zone_names: list[str] = rule.get("managementZones", [])
    zone_ids: set[str] | None = None
    tag_ids: set[str] | None = None

    if mgmt_zone_names:
        zone_ids = {
            row["id"] for row in dql_client.execute(build_pg_query(mgmt_zone_names, window)) if row.get("id")
        }

    if translation.pg_tag_values:
        tag_ids = {
            row["id"]
            for row in dql_client.execute(build_pg_tag_query(translation.pg_tag_values, window))
            if row.get("id")
        }

    if zone_ids is None and tag_ids is None:
        return None
    if zone_ids is not None and tag_ids is not None:
        return sorted(zone_ids & tag_ids)
    if zone_ids is not None:
        return sorted(zone_ids)
    if tag_ids is not None:
        return sorted(tag_ids)
    return None  # unreachable; keeps type-checker happy


def _process_rule(  # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches
    rule_stub: Any, rule: dict, dql_client: Any, window: str, primary_tag_keys: list[str]
) -> RuleResult:
    rule_id: str = rule_stub.id
    rule_type: str = rule_stub.rule_type

    if not rule.get("enabled", True):
        return RuleResult(rule_id=rule_id, rule_type=rule_type, verdict="skipped_disabled")

    translation = translate_conditions(rule)

    if not translation.deprecated_found:
        return RuleResult(rule_id=rule_id, rule_type=rule_type, verdict="skipped_not_deprecated")

    if translation.unmigratable_reasons:
        return RuleResult(
            rule_id=rule_id,
            rule_type=rule_type,
            verdict="untranslatable",
            reasons=list(translation.unmigratable_reasons),
            surviving_fragments=translation.surviving_fragments,
        )

    pg_ids = _resolve_pg_ids(rule, translation, dql_client, window)
    if pg_ids == []:
        return RuleResult(
            rule_id=rule_id,
            rule_type=rule_type,
            verdict="no_replacement",
            reasons=["empty process group set"],
            surviving_fragments=translation.surviving_fragments,
        )
    # pg_ids is None (no PG-level conditions) or a non-empty list here; the []
    # (conditions resolved to zero) case was already handled above. Pass it through
    # as-is so the query builders can distinguish "unscoped" from "empty".

    # FWR entity-condition resolution — APPLICATION_ID/CONTEXT_ROOT
    # conditions are resolved via dt.entity.service to service_ids + derived_pg_ids.
    # derived_pg_ids is a tighter PG scope than the MZ-resolved pg_ids; only FWR.
    service_ids: list[str] | None = None
    verify_pg_ids: list[str] | None = None
    span_pg_ids: list[str] | None = pg_ids
    if rule_type == "FULL_WEB_REQUEST" and translation.surviving_entity_fragments:
        svc_rows = dql_client.execute(
            build_service_id_query(
                translation.surviving_entity_fragments, window, pg_ids=pg_ids or None,
            )
        )
        if not svc_rows:
            return RuleResult(
                rule_id=rule_id,
                rule_type=rule_type,
                verdict="no_replacement",
                reasons=["empty service set"],
                surviving_fragments=translation.surviving_fragments,
            )
        service_ids, derived_pg_ids = _extract_service_scope(svc_rows)
        span_pg_ids = derived_pg_ids or None
        verify_pg_ids = derived_pg_ids or None

    # Entity path (service entity query + candidate discovery) is gated to FWR.
    # A PG can host both a WEB_SERVICE and a co-located WEB_REQUEST_SERVICE; running
    # the entity query for FWS would surface co-located WEB_REQUEST_SERVICE attributes
    # (webApplicationId/contextRoot) as spurious entity candidates for a FWS rule.
    if rule_type == "FULL_WEB_REQUEST":
        entity_rows = dql_client.execute(build_service_entity_query(pg_ids, window))
        entity_candidates = score_entity_candidates(entity_rows)
    else:
        entity_rows = []
        entity_candidates = []

    # Capability B (FWR only): entity candidates (APPLICATION_ID/CONTEXT_ROOT
    # discovered from service entity rows) feed the replacement body directly.
    # Dedup by surviving_entity_attribute_types (block-at-source, for entity attrs).
    # Entity candidates bypass the span verifier because grail_key="" makes span
    # DQL impossible; their correctness is guaranteed by the entity-side scoping.
    if rule_type == "FULL_WEB_REQUEST":
        cap_b_candidates = [
            c for c in entity_candidates
            if c.attribute_type not in translation.surviving_entity_attribute_types
        ]
        # No surviving entity condition but cap B candidates exist: derive service_ids
        # in-memory so the span and verify queries exclude services without the value.
        if not translation.surviving_entity_fragments and cap_b_candidates:
            cap_b_svc_ids = _derive_cap_b_service_ids(entity_rows, cap_b_candidates)
            if cap_b_svc_ids:
                service_ids = cap_b_svc_ids
                verify_pg_ids = None  # MZ is deprecated, stay unscoped by PG
    else:
        cap_b_candidates = []

    outcome = _query_and_verify(
        span_pg_ids, translation, rule_type, window, dql_client, primary_tag_keys=primary_tag_keys,
        service_ids=service_ids, verify_pg_ids=verify_pg_ids,
    )
    verify_result = outcome.verify_result

    if verify_result.verdict != "exact" and not outcome.best_effort:
        return RuleResult(
            rule_id=rule_id,
            rule_type=rule_type,
            verdict="no_replacement",
            reasons=(
                ["empty target set"] if not outcome.target_set
                else ["no span candidates"] if not outcome.candidates
                else ["no exact candidate match"]
            ),
            entity_candidates=entity_candidates,
            target_set=outcome.target_set,
            candidates=outcome.candidates,
            discarded_attributes=outcome.discarded_attributes,
            pg_ids=pg_ids or [],
            window=outcome.window,
            escalated_candidates=verify_result.escalated,
            demoted_from=verify_result.demoted_from,
            span_retries=outcome.span_retries,
            under_select_retries=outcome.under_select_retries,
            surviving_fragments=translation.surviving_fragments,
        )

    # verify_result.candidates may be empty here: a surviving-only rule whose
    # surviving conditions reproduce the target set globally migrates with a
    # surviving-only body and no added conditions.
    # cap_b_candidates (entity candidates, FWR only) are appended directly — they
    # bypass the span verifier because grail_key="" makes span DQL impossible.
    return RuleResult(
        rule_id=rule_id,
        rule_type=rule_type,
        verdict="migrated",
        replacement_body=build_replacement_body(
            rule, verify_result.candidates + cap_b_candidates, verify_result.negations,
        ),
        entity_candidates=entity_candidates,
        target_set=outcome.target_set,
        candidates=outcome.candidates,
        discarded_attributes=outcome.discarded_attributes,
        chosen_candidates=verify_result.candidates,
        pg_ids=pg_ids or [],
        window=outcome.window,
        negations=verify_result.negations,
        escalated_candidates=verify_result.escalated,
        demoted_from=verify_result.demoted_from,
        span_retries=outcome.span_retries,
        under_select_retries=outcome.under_select_retries,
        best_effort=outcome.best_effort,
        reasons=["best-effort: under-selecting candidate after window retry"] if outcome.best_effort else [],
        surviving_fragments=translation.surviving_fragments,
    )
