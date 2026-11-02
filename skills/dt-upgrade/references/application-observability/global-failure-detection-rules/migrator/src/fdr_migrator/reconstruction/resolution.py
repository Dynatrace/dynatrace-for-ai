"""Resolving, for one rule, the exact set of services it selects today.

Deprecated Conditions are still evaluated here - the set a rule selects today is the set with all
of its conditions in force, and that is the yardstick every later step is measured against. Its
conditions AND across the whole rule, so they are asked in the one order that reproduces them.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from ..dql.queries import TranslatedRule, on_process_groups, on_services
from ..dql.translation import Dataset


# What the query API accepts, and therefore what a rule can be asked about. Real ceilings rather
# than chosen policy: past either, the query is rejected outright. The element cap is per array,
# not per query, so two composed lists do not share it; the text cap is not redundant with it,
# because a rule's own conditions add text of their own.
MAX_ARRAY_ELEMENTS = 10_000
MAX_QUERY_CHARACTERS = 1_000_000


class ResolutionOutcome(StrEnum):
    """Where a rule's resolution ended, as a code a caller matches on.

    Whatever renders these owns the wording. The empty ones stay apart because collapsing them is
    how a rule with no services gets handed to an engineer as if it merely lacked traffic.
    """

    RESOLVED = "resolved"
    EMPTY_SCOPE = "empty-scope"
    ONLY_EXTERNAL = "only-external-services"
    DORMANT = "dormant"
    INCOMPLETE_READ = "incomplete-read"
    QUERY_TOO_LARGE = "query-too-large"
    ERROR = "processing-error"
    UNTRANSLATABLE = "untranslatable"
    MATCHES_NOTHING = "matches-nothing"


class QueryTooLarge(Exception):
    """The rule resolved to more than the query API will accept in one query.

    Reported rather than worked around. Splitting across several queries is not built, and neither
    is resolving against the part of the list that fits: a Target Set assembled from part of a
    rule's scope is not what the rule selects, and a replacement verified against it would carry
    that error into the customer's tenant.
    """


class IncompleteRead(Exception):
    """A read that builds the Target Set came back capped, so the rule has no subject.

    Kept apart from the caps met while harvesting one attribute's values, which cost that
    attribute and leave the rule standing. There is no attribute to charge this one to: the reads
    guarded here are the only account of what the rule selects, and a Target Set assembled from
    part of one is not the rule's. It fails in the direction that looks best, too - fewer selected
    services is fewer for a candidate to cover, and the proof is compared against the same short
    set, so the error sits on both sides of the comparison and cancels into a confident verdict.
    """


@dataclass(frozen=True)
class IssuedQuery:
    """One query a rule's resolution asked, and whether the run had already paid for it."""

    dataset: Dataset
    query: str
    cache_hit: bool


@dataclass(frozen=True)
class HarvestRows:
    """The rows a rule's own queries came back with, kept for the step that harvests from them.

    Held rather than re-read: asking the same dataset twice would double the reads and, on the
    span side, return a different set of rows than the Target Set was built from.
    """

    services: tuple[dict[str, Any], ...] = ()
    process_groups: tuple[dict[str, Any], ...] = ()
    spans: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ResolvedRule:
    """What one rule resolved to: its Target Set, or the reason there is none."""

    # pylint: disable=too-many-instance-attributes
    object_id: str
    name: str
    outcome: ResolutionOutcome
    target_set: frozenset[str] = frozenset()
    external_services: frozenset[str] = frozenset()
    detail: str = ""
    queries: tuple[IssuedQuery, ...] = field(default_factory=tuple)
    rows: HarvestRows = field(default_factory=HarvestRows)


@dataclass
class _Rows:
    """The rows gathered so far, mutable while a rule is still being resolved.

    Frozen once the rule has an outcome, so nothing downstream rewrites what a query returned.
    """

    services: tuple[dict[str, Any], ...] = ()
    process_groups: tuple[dict[str, Any], ...] = ()
    spans: tuple[dict[str, Any], ...] = ()

    def taken(self) -> HarvestRows:
        return HarvestRows(self.services, self.process_groups, self.spans)


@dataclass(frozen=True)
class QueryOutcome:
    """An answer, whether this run had already paid for it, and whether it is all of the rows.

    A plain record rather than a second query-running protocol: hit or miss has to be read from
    the runner that did the work, since asking afterwards whether a cache file exists answers a
    different question and says "hit" for a query the run itself just wrote. Completeness travels
    the same way and for the same reason: the platform caps a result set at read time, and a
    capped answer cannot be told from a complete one by its rows alone.
    """

    records: list[dict[str, Any]]
    cache_hit: bool
    complete: bool = True


class RecordingQueryRunner(Protocol):
    """A runner that says whether an answer was already paid for.

    Deliberately not the `QueryRunner` protocol: hit or miss has to be read from the runner that
    did the work, and the connection checks that use `QueryRunner` have no use for it.
    """

    def run(self, query: str) -> QueryOutcome: ...


def resolve_rules(
    translations: Iterable[TranslatedRule], runner: RecordingQueryRunner
) -> tuple[ResolvedRule, ...]:
    return tuple(_contained(translated, runner) for translated in translations)


def _contained(translated: TranslatedRule, runner: RecordingQueryRunner) -> ResolvedRule:
    """Resolve one rule inside its own boundary.

    A failure is that rule's outcome, never the run's. The text recorded here is persisted and
    eventually read by a customer, which is why it comes from typed errors only - nothing raw
    from the transport reaches this string.
    """
    refused = _already_refused(translated)
    if refused is not None:
        return refused
    try:
        return resolve_rule(translated, runner)
    except IncompleteRead as capped:
        return ResolvedRule(
            translated.object_id,
            translated.name,
            ResolutionOutcome.INCOMPLETE_READ,
            detail=str(capped),
        )
    except QueryTooLarge as oversized:
        return ResolvedRule(
            translated.object_id,
            translated.name,
            ResolutionOutcome.QUERY_TOO_LARGE,
            detail=str(oversized),
        )
    except Exception as failure:  # pylint: disable=broad-exception-caught
        return ResolvedRule(
            translated.object_id,
            translated.name,
            ResolutionOutcome.ERROR,
            detail=str(failure),
        )


def _already_refused(translated: TranslatedRule) -> ResolvedRule | None:
    """The rules translation would not build a query for, under the code that says which kind.

    Kept apart because one is a gap in the tool and the other a finding about the tenant, and
    neither may be reported as the other. Nothing is asked for either.
    """
    if translated.untranslatable:
        return ResolvedRule(
            translated.object_id,
            translated.name,
            ResolutionOutcome.UNTRANSLATABLE,
            detail=translated.untranslatable,
        )
    if translated.matches_nothing:
        return ResolvedRule(
            translated.object_id,
            translated.name,
            ResolutionOutcome.MATCHES_NOTHING,
            detail=translated.matches_nothing,
        )
    return None


def resolve_rule(translated: TranslatedRule, runner: RecordingQueryRunner) -> ResolvedRule:
    _require_an_entity_side(translated)
    issued: list[IssuedQuery] = []
    rows = _Rows()
    hosts = _resolve_process_groups(translated, runner, issued, rows)
    if hosts is not None and not hosts:
        # A scope asked for and answered with nothing means the rule selects nothing. Decided here
        # rather than by catching the builder's refusal to compose an empty set, which comes after
        # the rule has already been asked about a scope it never had.
        return ResolvedRule(
            translated.object_id,
            translated.name,
            ResolutionOutcome.EMPTY_SCOPE,
            detail="the process-group scope resolved to no process group",
            queries=tuple(issued),
            rows=rows.taken(),
        )
    scope = (
        []
        if hosts is None
        else [on_process_groups(within_element_cap(hosts, "process group"))]
    )
    query = translated.query_for(Dataset.SERVICES, extra=scope)
    outcome = _ask(runner, Dataset.SERVICES, query)
    services, external = partition_external(outcome.records)
    issued.append(IssuedQuery(Dataset.SERVICES, query, outcome.cache_hit))
    rows.services = tuple(outcome.records)
    if not services and not external:
        return ResolvedRule(
            translated.object_id,
            translated.name,
            ResolutionOutcome.EMPTY_SCOPE,
            detail="the service query resolved to no service",
            queries=tuple(issued),
            rows=rows.taken(),
        )
    if services and Dataset.ENTRY_SPANS in translated.filters:
        return _resolve_spans(translated, runner, services, external, issued=issued, rows=rows)
    if not services:
        # Load-bearing ordering: an external service is never the one an entry-point span enters,
        # so an entirely external entity side would intersect to nothing and read as dormant if
        # this were decided after the span step rather than before it.
        return ResolvedRule(
            translated.object_id,
            translated.name,
            ResolutionOutcome.ONLY_EXTERNAL,
            external_services=external,
            queries=tuple(issued),
            rows=rows.taken(),
        )
    return ResolvedRule(
        translated.object_id,
        translated.name,
        ResolutionOutcome.RESOLVED,
        target_set=services,
        external_services=external,
        queries=tuple(issued),
        rows=rows.taken(),
    )


def _require_an_entity_side(translated: TranslatedRule) -> None:
    """Refuse a rule that selects on spans alone, because none can exist.

    The span side is intersected with a service result that already excludes the services this
    tool does not govern; without one, a Target Set would quietly include them. Guarded rather
    than branched on, so that a span-side condition turning deprecated fires here instead.
    """
    if Dataset.ENTRY_SPANS in translated.filters and not (
        translated.filters.keys() & {Dataset.SERVICES, Dataset.PROCESS_GROUPS}
    ):
        raise ValueError(
            "the rule selects on entry spans alone, which no rule this tool resolves can do"
        )


def _resolve_spans(
    translated: TranslatedRule,
    runner: RecordingQueryRunner,
    services: frozenset[str],
    external: frozenset[str],
    *,
    issued: list[IssuedQuery],
    rows: "_Rows",
) -> ResolvedRule:
    """Intersect the entity side with the services whose entry-point spans matched.

    Scoped by the services already resolved rather than asked unbounded: a window's span side
    holds far more than one rule is about, and a truncated read comes back short - a wrong Target
    Set nothing later would reveal. Long query text is the risk taken instead, and it fails loudly.
    """
    scope = on_services(within_element_cap(services, "service"))
    query = translated.query_for(Dataset.ENTRY_SPANS, extra=[scope])
    outcome = _ask(runner, Dataset.ENTRY_SPANS, query)
    issued.append(IssuedQuery(Dataset.ENTRY_SPANS, query, outcome.cache_hit))
    rows.spans = tuple(outcome.records)
    matched = services & service_ids_of(outcome.records)
    return ResolvedRule(
        translated.object_id,
        translated.name,
        ResolutionOutcome.RESOLVED if matched else ResolutionOutcome.DORMANT,
        target_set=matched,
        external_services=external,
        detail="" if matched else "the rule's services carried no traffic in the query window",
        queries=tuple(issued),
        rows=rows.taken(),
    )


def within_element_cap(ids: Collection[str], subject: str) -> Collection[str]:
    """Refuse to compose a list the query API will not accept, before it is composed."""
    if len(ids) > MAX_ARRAY_ELEMENTS:
        raise QueryTooLarge(
            f"the rule resolved to {len(ids)} {subject}s, more than the {MAX_ARRAY_ELEMENTS} "
            "a single query can be scoped by"
        )
    return ids


# What to call each of these reads when telling a human which one came back capped, so they know
# where to look. The `fetch` target the dataset is spelled as says nothing to a reader.
_READ_NAMES: dict[Dataset, str] = {
    Dataset.PROCESS_GROUPS: "process-group",
    Dataset.SERVICES: "service",
    Dataset.ENTRY_SPANS: "entry-span",
}


def _ask(runner: RecordingQueryRunner, dataset: Dataset, query: str) -> QueryOutcome:
    """Issue one query, having checked the text itself is one the API will accept.

    Every query, not only the ones carrying a composed id list: a rule's own conditions can be
    long on their own. A capped answer stops the rule here, at the one place all three of its
    reads pass through, so no later step can be reached holding part of a Target Set.
    """
    if len(query) > MAX_QUERY_CHARACTERS:
        raise QueryTooLarge(
            f"the rule's query grew to {len(query)} characters, more than the "
            f"{MAX_QUERY_CHARACTERS} the query API accepts"
        )
    outcome = runner.run(query)
    if not outcome.complete:
        raise IncompleteRead(
            f"the {_READ_NAMES[dataset]} read came back capped: this rule selects more entities "
            "than a single read returns, so what it targets cannot be established"
        )
    return outcome


def service_ids_of(rows: Sequence[dict[str, Any]]) -> frozenset[str]:
    """The services an entry-span result named, skipping any row that named none."""
    return frozenset(
        identifier
        for row in rows
        if (identifier := row.get(str(Dataset.SERVICES)))
    )


def _resolve_process_groups(
    translated: TranslatedRule,
    runner: RecordingQueryRunner,
    issued: list[IssuedQuery],
    rows: "_Rows",
) -> tuple[str, ...] | None:
    """The process groups a rule is scoped to, or `None` when it is scoped to none.

    An absent scope and an empty one cannot share a spelling: no process-group condition leaves
    the service query unconstrained by the hosting relation, while one that resolved nothing
    means the rule selects nothing at all.
    """
    if Dataset.PROCESS_GROUPS not in translated.filters:
        return None
    query = translated.query_for(Dataset.PROCESS_GROUPS)
    outcome = _ask(runner, Dataset.PROCESS_GROUPS, query)
    issued.append(IssuedQuery(Dataset.PROCESS_GROUPS, query, outcome.cache_hit))
    rows.process_groups = tuple(outcome.records)
    return tuple(row["id"] for row in outcome.records if row.get("id"))


def partition_external(rows: Sequence[dict[str, Any]]) -> tuple[frozenset[str], frozenset[str]]:
    """Split resolved service rows into the ones a replacement must reproduce, and the rest.

    A row carrying no id is skipped, not fatal: one malformed row is not worth a rule's answer.
    """
    services: set[str] = set()
    external: set[str] = set()
    for row in rows:
        identifier = row.get("id")
        if not identifier:
            continue
        (external if row.get("isExternalService") else services).add(identifier)
    return frozenset(services), frozenset(external)
