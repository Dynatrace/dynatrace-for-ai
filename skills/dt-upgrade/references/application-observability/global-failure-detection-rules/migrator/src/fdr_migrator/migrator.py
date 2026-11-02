"""One pass over the tenant's Global Failure Detection Rules."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .cache import AnsweringQueryRunner, CachingQueryRunner
from .checks import SettingsReader
from .dql.queries import translate_affected
from .emission.artifacts import emit_artifacts
from .dql.windowing import QueryWindow
from .reconstruction.candidates import discover_primary_tag_keys
from .reconstruction.replacement import determine_replacements
from .reconstruction.resolution import resolve_rules
from .reporting.html import REPORT_FILE, write_report
from .reporting.outcomes import bucket_rules, is_subject
from .reporting.summary import SUMMARY_FILE, write_summary
from .rules.classification import (
    ClassifiedRule,
    PredicateType,
    RuleStanding,
    classify_rules,
    summarise,
)
from .run_result import RunResult
from .workdir import DEFAULT_OUTPUT, create_run_workdir


class NoRequestedRule(Exception):
    """Every object id the run was asked about is one the tenant holds no rule for.

    Raised rather than reported, and raised before anything is written: a run that looked at no
    rule has nothing to say, and a report saying nothing reads exactly like a clean tenant.
    """


def run_migration(
    settings_client: SettingsReader,
    dql_client: AnsweringQueryRunner,
    *,
    platform_url: str,
    window: QueryWindow,
    output: Path = DEFAULT_OUTPUT,
    rule_ids: Sequence[str] | None = None,
) -> RunResult:
    requested = _requested(classify_rules(settings_client.list_rule_objects()), rule_ids)
    workdir = create_run_workdir(output)
    query_runner = CachingQueryRunner(dql_client, workdir / "cache")
    primary_tags = discover_primary_tag_keys(query_runner)
    translations = translate_affected(
        requested.rules,
        window,
        zone_names=_zone_names(settings_client, requested.rules),
        primary_tag_keys=primary_tags.keys,
    )
    resolutions = resolve_rules(translations, query_runner)
    replacements = determine_replacements(translations, resolutions, query_runner)
    # Over the corpus, never the subset: an artifact carries the position its rule is evaluated
    # at, which is a fact about the whole ruleset. Read off the requested rules instead, the
    # first one asked for would claim first position and be deployed ahead of every rule it
    # sits behind today.
    artifacts = emit_artifacts(requested.corpus, replacements, workdir)
    result = RunResult(
        rules=requested.rules,
        # Over everything read, never over the subset: the scan figures describe the pass across
        # the tenant, which happened in full even when the findings below cover a few rules.
        coverage=summarise(requested.corpus),
        translations=translations,
        resolutions=resolutions,
        replacements=replacements,
        artifacts=artifacts,
        window=window,
        workdir=workdir,
        platform_url=platform_url,
        # Both names are the run's own choice, so they are known before either file exists and
        # nothing has to look in the directory afterwards to find out where they went.
        summary_path=workdir / SUMMARY_FILE,
        report_path=workdir / REPORT_FILE,
        primary_tags_unavailable=not primary_tags.answered,
        primary_tag_keys_capped=not primary_tags.complete,
        requested_rule_ids=requested.ids,
        unmatched_rule_ids=requested.unmatched,
        requested_not_affected=requested.not_affected,
    )
    return _written(result)


def _written(result: RunResult) -> RunResult:
    """Put this run's two files where it said they go, and answer with what it found."""
    bucketed = bucket_rules(result)
    write_summary(result, bucketed)
    write_report(result, bucketed)
    return result


@dataclass(frozen=True)
class _Requested:
    """Which rules a run is about, beside every rule it read to decide that.

    The two are kept together because neither is readable without the other: the findings cover
    the rules, the scan figures cover the corpus, and a rendering showing one as the other states
    something about the tenant that was never measured.
    """

    corpus: tuple[ClassifiedRule, ...]
    rules: tuple[ClassifiedRule, ...]
    ids: tuple[str, ...] = ()
    unmatched: tuple[str, ...] = ()
    not_affected: tuple[str, ...] = ()


def _requested(corpus: Sequence[ClassifiedRule], rule_ids: Sequence[str] | None) -> _Requested:
    """The rules this run is about: everything read, or only the ones asked for by object id.

    Kept in the order they were read rather than the order they were typed, so two runs over the
    same subset are comparable line for line.
    """
    read = tuple(corpus)
    if rule_ids is None:
        return _Requested(read, read)
    asked = tuple(dict.fromkeys(rule_ids))
    rules = tuple(rule for rule in read if rule.object_id in set(asked))
    held = {rule.object_id for rule in read}
    unmatched = tuple(rid for rid in asked if rid not in held)
    if not rules:
        raise NoRequestedRule(
            "no rule on this tenant has " + ", ".join(unmatched) + ", so there was nothing to run"
        )
    return _Requested(
        read,
        rules,
        asked,
        unmatched,
        tuple(rule.object_id for rule in rules if not is_subject(rule)),
    )


def _zone_names(settings_client: SettingsReader, rules: Iterable[ClassifiedRule]) -> dict[str, str]:
    """Read the tenant's management zones once, and only if a rule actually refers to one."""
    if not any(
        c.predicate_type is PredicateType.MANAGEMENT_ZONES_CONTAINS_ALL
        for rule in rules
        if rule.standing is RuleStanding.AFFECTED
        for c in rule.conditions
    ):
        return {}
    return settings_client.list_zone_names()
