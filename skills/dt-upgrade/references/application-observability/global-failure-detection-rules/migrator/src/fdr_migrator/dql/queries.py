"""Composing translated conditions into the queries a run issues."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from ..rules.classification import (
    Attribute,
    ClassifiedCondition,
    ClassifiedRule,
    ConditionStanding,
    PredicateType,
    RuleStanding,
)
from .translation import (
    Dataset,
    MatchesNothing,
    Untranslatable,
    attribute_name,
    literal,
    translate_condition,
)
from .windowing import QueryWindow


@dataclass(frozen=True)
class TranslatedRule:
    """The filters one rule's Target Set is resolved from, or why there are none.

    Filters rather than finished query text because a rule's conditions AND across datasets: a
    service matching every service-side condition but hosted by no process group the rule matched
    is not in the Target Set. Adding the resolved process groups is composition on a filter list,
    and string surgery on a built query.
    """

    # pylint: disable=too-many-instance-attributes
    object_id: str
    name: str
    window: QueryWindow
    filters: Mapping[Dataset, tuple[str, ...]] = field(default_factory=dict)
    matches_nothing: str = ""
    untranslatable: str = ""
    primary_tag_keys: tuple[str, ...] = ()
    surviving: tuple[ClassifiedCondition, ...] = ()

    @property
    def queries(self) -> Mapping[Dataset, str]:
        """The queries that are runnable as they stand.

        A rule with a process-group condition has no finished service query, and the one built
        from its service-side filters alone would answer with rows rather than an error while
        selecting wider than the rule. So it is withheld: the only route is `query_for` with the
        resolved process groups passed in.
        """
        withheld = Dataset.PROCESS_GROUPS in self.filters
        return {
            dataset: self.query_for(dataset)
            for dataset in self.filters
            if not (withheld and dataset is Dataset.SERVICES)
        }

    def query_for(
        self, dataset: Dataset, *, extra: Iterable[str] = (), yields: str | None = None
    ) -> str:
        """This rule's filters over one dataset, with anything a later step resolved added."""
        return build_query(
            dataset,
            [*self.filters.get(dataset, ()), *extra],
            self.window,
            yields=yields or harvest_yield(dataset, self.primary_tag_keys),
        )


def translate_affected(
    rules: Iterable[ClassifiedRule],
    window: QueryWindow,
    *,
    zone_names: Mapping[str, str],
    primary_tag_keys: Iterable[str] = (),
) -> tuple[TranslatedRule, ...]:
    """The affected (i.e. containing deprecated conditions) rules as query material, and nothing for other rules.
    """
    return tuple(
        translate_rule(rule, window, zone_names=zone_names, primary_tag_keys=primary_tag_keys)
        for rule in rules
        if rule.standing is RuleStanding.AFFECTED
    )


def translate_rule(
    rule: ClassifiedRule,
    window: QueryWindow,
    *,
    zone_names: Mapping[str, str],
    primary_tag_keys: Iterable[str] = (),
) -> TranslatedRule:
    """Every condition of one rule, as the queries that reproduce what it selects today.

    Deprecated and surviving conditions alike: the set a rule selects today is the set with all
    of its conditions still evaluated, so a tag condition is exactly as much a part of the
    question as a name condition.

    The zone index is required rather than defaulted, because an absent one is indistinguishable
    from an index in which nothing resolves - and that reads out as a rule already selecting no
    service today, which is a finding about the tenant rather than about the call.
    """
    grouped: dict[Dataset, list[str]] = {}
    try:
        for condition in rule.conditions:
            fragment = translate_condition(condition, zone_names=zone_names)
            grouped.setdefault(fragment.dataset, []).append(fragment.text)
    # One condition the tool cannot express, or one that can select nothing, settles the whole
    # rule: a partial filter list would resolve a set that is not the rule's.
    except Untranslatable as refused:
        return TranslatedRule(rule.object_id, rule.name, window, untranslatable=str(refused))
    except MatchesNothing as empty:
        return TranslatedRule(rule.object_id, rule.name, window, matches_nothing=str(empty))
    return TranslatedRule(
        rule.object_id,
        rule.name,
        window,
        {dataset: tuple(filters) for dataset, filters in grouped.items()},
        primary_tag_keys=tuple(primary_tag_keys),
        surviving=tuple(
            c for c in rule.conditions if c.standing is ConditionStanding.SURVIVING
        ),
    )


@dataclass(frozen=True)
class CandidateAttribute:
    """One attribute a replacement condition can be built on, and where its values are read.

    Declared once and read twice - by the projection that asks for the column, and by the
    harvest that reads it back off the rows. Two hand-maintained lists is the failure this
    exists to prevent, and it fails quietly in both directions: a column asked for and never
    read is never harvested, and a column read but never asked for is a null on every row.
    """

    attribute: Attribute
    predicate_type: PredicateType
    dataset: Dataset
    column: str


CANDIDATE_ATTRIBUTES: tuple[CandidateAttribute, ...] = (
    CandidateAttribute(
        Attribute.SERVICE_NAME, PredicateType.STRING_EQUALS, Dataset.SERVICES, "entity.name"
    ),
    CandidateAttribute(
        Attribute.SERVICE_TYPE, PredicateType.SERVICE_TYPE_EQUALS, Dataset.SERVICES, "serviceType"
    ),
    CandidateAttribute(
        Attribute.PG_NAME, PredicateType.STRING_EQUALS, Dataset.PROCESS_GROUPS, "entity.name"
    ),
)

# The relation a service is reached through when a rule filters the process group hosting it.
RUNS_ON_PG = "runs_on[`dt.entity.process_group`]"

# Carried by every read of a dataset whatever the rule asks: the identity a Target Set is built
# from, the flag that partitions external services out, and the hosting relation the harvest
# needs to ask about a service's process groups.
_ALWAYS_CARRIED = {
    Dataset.SERVICES: ("id", "isExternalService", RUNS_ON_PG),
    Dataset.PROCESS_GROUPS: ("id",),
}


def harvest_yield(dataset: Dataset, primary_tag_keys: Iterable[str] = ()) -> str:
    """The identities a Target Set is built from and the columns its candidates are harvested
    from, in one read.

    A span query summarised by service *and* the discovered tag keys answers one row per
    combination, not one per service: readers extract distinct service ids and never count rows.
    """
    if dataset is Dataset.ENTRY_SPANS:
        grouped = ", ".join([str(Dataset.SERVICES), *_attribute_names(primary_tag_keys)])
        return "| summarize count(), by:{" + grouped + "}"
    return "| fields " + ", ".join([*_ALWAYS_CARRIED[dataset], *_candidate_columns(dataset)])


# Proving a replacement asks only whether it selects the same identities, so nothing downstream
# reads a value off these rows: carrying the candidate columns would only widen the row set for
# no reader.
_VERIFICATION_YIELDS = {
    Dataset.SERVICES: "| fields id",
    Dataset.PROCESS_GROUPS: "| fields id",
    Dataset.ENTRY_SPANS: "| summarize count(), by:{dt.entity.service}",
}


def verification_yield(dataset: Dataset) -> str:
    return _VERIFICATION_YIELDS[dataset]


def filters_for(conditions: Iterable[ClassifiedCondition]) -> Mapping[Dataset, tuple[str, ...]]:
    """A condition set as the filters that reproduce what it selects, grouped by dataset.

    Built from the conditions given, so a query proving a replacement carries no
    filter the replacement itself does not have.
    """
    grouped: dict[Dataset, list[str]] = {}
    for condition in conditions:
        fragment = translate_condition(condition)
        grouped.setdefault(fragment.dataset, []).append(fragment.text)
    return {dataset: tuple(filters) for dataset, filters in grouped.items()}


def _candidate_columns(dataset: Dataset) -> tuple[str, ...]:
    """The columns declared for one dataset, with anything already carried left to the caller."""
    return tuple(
        dict.fromkeys(
            candidate.column
            for candidate in CANDIDATE_ATTRIBUTES
            if candidate.dataset is dataset
            and candidate.column not in _ALWAYS_CARRIED.get(dataset, ())
        )
    )


def _attribute_names(keys: Iterable[str]) -> list[str]:
    # Sorted and de-duplicated, because the query text is the cache key: two orderings of one
    # question must not read as two.
    return [attribute_name(key) for key in sorted(set(keys))]


ENTRY_POINT = "supportability.failure_detection.is_entry_point == true"
NOT_ENDPOINT_DETECTED = "isNull(dt.endpoint_detection.rule_id)"
NOT_UNIFIED_FAILURE_DETECTION = "isNull(dt.failure_detection.ruleset_id)"
ONEAGENT_INGESTED = 'dt.openpipeline.source == "oneagent"'
NOT_EXTERNAL = "isExternalService == false or isNull(isExternalService)"
NOT_UNIFIED = 'serviceType != "UNIFIED"'

# Carried by every read of a dataset whether or not a rule says anything about it: the spans a
# rule is evaluated on are the entry-point spans this ruleset still classifies, and the services
# a rule can select exclude the newer generation's.
_PREFILTERS: dict[Dataset, tuple[str, ...]] = {
    Dataset.SERVICES: (NOT_UNIFIED,),
    Dataset.ENTRY_SPANS: (
        ENTRY_POINT,
        NOT_ENDPOINT_DETECTED,
        NOT_UNIFIED_FAILURE_DETECTION,
        ONEAGENT_INGESTED,
    ),
}


def build_query(
    dataset: Dataset,
    filters: Iterable[str],
    query_window: QueryWindow,
    *,
    yields: str | None = None,
) -> str:
    """One query over one dataset, bounded by the window and by the conditions given.

    Conditions are AND-ed and each arrives as a disjunction of its own values, so every one is
    parenthesised: joined bare, a condition's `or` would swallow the next and select wider than
    the rule. The projection defaults to the harvest one and is stated by any caller reading
    these rows for something else - inherited by accident, it is either a column nobody reads or
    one a reader silently never gets.
    """
    clauses = [f"fetch {dataset}, {query_window.timeframe}"]
    conjunction = _all_of(filters)
    required = [*_PREFILTERS.get(dataset, ()), *([conjunction] if conjunction else [])]
    if required:
        clauses.append("| filter " + "\n    and ".join(required))
    clauses.append(yields if yields is not None else harvest_yield(dataset))
    return "\n".join(clauses)


class EmptyFilterError(ValueError):
    """Refuses to build a query whose only constraint resolved to nothing."""


def on_process_groups(process_group_ids: Iterable[str]) -> str:
    """The filter that keeps the services a set of process groups hosts.
    """
    # Refused rather than dropped: dropped, the scope disappears and the query becomes a scan of
    # every service on the tenant.
    listed = ", ".join(sorted(literal(pg) for pg in process_group_ids))
    if not listed:
        raise EmptyFilterError(
            "no process group was resolved, so there is no set of services to ask about"
        )
    return f"in(runs_on[`dt.entity.process_group`], array({listed}))"


def on_services(service_ids: Iterable[str]) -> str:
    """The filter that keeps the entry-point spans of a set of services."""
    listed = ", ".join(sorted(literal(service) for service in service_ids))
    if not listed:
        raise EmptyFilterError("no service was resolved, so there is no set of spans to ask about")
    return f"in(dt.entity.service, array({listed}))"


def on_entity_ids(entity_ids: Iterable[str]) -> str:
    """The filter that keeps a named set of entities, asked about by their own identities."""
    listed = ", ".join(sorted(literal(entity) for entity in entity_ids))
    if not listed:
        raise EmptyFilterError("no entity was named, so there is no set of entities to ask about")
    return f"in(id, array({listed}))"


def _all_of(filters: Iterable[str]) -> str:
    """AND the conditions, in a fixed order so that the same question spells the same way."""
    return " and ".join(sorted(f"({text})" for text in filters if text))
