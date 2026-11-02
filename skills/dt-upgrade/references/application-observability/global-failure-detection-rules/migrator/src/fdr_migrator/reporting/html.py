"""The customer-facing rendering of a run: one self-contained page, no external requests.

Written from the outcome codes rather than grown out of any other rendering, so that the sentences
a customer reads are chosen for a customer. Every value that came from the tenant - rule names, tag
values, condition values, query text, diagnostics, free-text detail - goes out through one escaping
helper on every path: ordinary data corrupts the page silently, and adversarial data is script
execution in the reviewer's browser.
"""

from __future__ import annotations

import html
import json
from collections.abc import Iterable, Sequence
from pathlib import Path

from ..cache import cache_key
from ..dql.translation import Dataset
from ..reconstruction.candidates import DropReason, Harvest
from ..reconstruction.replacement import Replacement
from ..reconstruction.resolution import (
    IssuedQuery,
    ResolutionOutcome,
    ResolvedRule,
    partition_external,
)
from ..rules.classification import (
    Attribute,
    ClassifiedCondition,
    ClassifiedRule,
    ConditionStanding,
    DeprecationReason,
    PredicateType,
)
from ..rules.tags import ParsedTag
from ..run_result import RunResult
from .outcomes import BucketedRule, Outcome, bucket_counts

REPORT_FILE = "report.html"

TITLE = "Global Failure Detection Rules - migration report"

# The one sentence that binds every finding below it. The tool reads every rule once and then
# considers only the affected ones, so the absence of a rule here says nothing about that rule.
SCOPE_SENTENCE = (
    "Everything below concerns the affected rules only - the enabled rules carrying a condition "
    "that is no longer evaluated. Rules outside that subset were read once so they could be ruled "
    "out, and nothing else was asked about them, so their absence from this report is not a "
    "finding about them."
)


def write_report(result: RunResult, bucketed: Sequence[BucketedRule]) -> Path:
    """Write this run's report where the run said it goes, and answer with the path."""
    result.report_path.write_text(render_report(result, bucketed), encoding="utf-8")
    return result.report_path


def render_report(result: RunResult, bucketed: Sequence[BucketedRule]) -> str:
    counts = bucket_counts(bucketed)
    body = "\n".join(
        [
            f"<h1>{_e(TITLE)}</h1>",
            _header(result),
            _caveats(result),
            _scan(result, bucketed),
            _index(bucketed, counts),
            _sections(bucketed, counts),
        ]
    )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_e(TITLE)}</title>\n<style>{_CSS}</style>\n</head>\n"
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def _e(value: object) -> str:
    """The one escaping helper. Everything interpolated into the page comes through here."""
    return html.escape("" if value is None else str(value))


def _header(result: RunResult) -> str:
    return _panel(
        _rows(
            ("Tenant", _e(result.platform_url)),
            ("Query window", f"{_e(result.window.expression)} ({_e(result.window.timeframe)})"),
            ("Run directory", f"<code>{_e(result.workdir)}</code>"),
        )
    )


def _caveats(result: RunResult) -> str:
    """A caveat over every bucket: what was looked at, and where a tag-key read fell short.

    Not a bucket of its own: a verdict may be an artefact of that read rather than a fact about
    the rule, and that changes how the whole page is read.
    """
    said = []
    if result.requested_rule_ids:
        said.append(
            f"This run was restricted to rules named when it was started, so the findings below "
            f"cover {len(result.rules)} rule(s) and are not this tenant's totals. The scan "
            "figures describe the whole pass, which read every rule on the tenant in order to "
            "find them."
        )
    if result.primary_tags_unavailable:
        said.append(
            "The read that says which primary tag keys this tenant carries did not answer, so no "
            "rule below was weighed on that attribute. A rule reported as having no safe "
            "replacement may well have one once that read succeeds."
        )
    if result.primary_tag_keys_capped:
        said.append(
            "The read that says which primary tag keys this tenant carries came back capped, so "
            "the keys weighed below are a subset of the ones this tenant carries. Every key found "
            "was measured and verified as usual; a rule reported as having no safe replacement "
            "may have one on a key that read stopped short of."
        )
    if not said:
        return ""
    items = "".join(f"<li>{_e(line)}</li>" for line in said)
    return f'<div class="caveat"><strong>Read this first</strong><ul>{items}</ul></div>'


def _scan(result: RunResult, bucketed: Sequence[BucketedRule]) -> str:
    """Figures about the one pass over the ruleset, labelled as figures rather than findings."""
    coverage = result.coverage
    reasons = "".join(
        f"<li>{count} carrying {_e(_AFFECTED_PROSE[reason])}</li>"
        for reason, count in sorted(coverage.affected_reasons.items(), key=lambda item: -item[1])
    )
    breakdown = f"<p>Of the affected rules:</p><ul>{reasons}</ul>" if reasons else ""
    extra = len(bucketed) - coverage.affected
    unreadable = (
        f"<p>{extra} further rule(s) could not be read at all, so whether they are affected could "
        "not be established. They are reported below too, because the tool being unable to read a "
        "rule is not the same as the rule being unaffected.</p>"
        if extra > 0
        else ""
    )
    return (
        '<h2 id="scan">Scan coverage</h2>'
        "<p>These three figures describe the pass over the ruleset, not findings about any "
        "rule.</p>"
        + _panel(
            _rows(
                ("Rules read", str(coverage.rules_read)),
                ("Enabled", str(coverage.enabled)),
                ("Affected", str(coverage.affected)),
            )
        )
        + breakdown
        + unreadable
        + _unread_switched_off(result)
        + f'<p class="scope">{_e(SCOPE_SENTENCE)}</p>'
    )


def _unread_switched_off(result: RunResult) -> str:
    """The switched-off rules this tool could not read: not a finding about them, one about it.

    Phase 3 evaluates nothing in a switched-off rule, so none of these needs reworking and none
    of them belongs in a bucket. That the tool could not read them is its own defect, it is
    already known by the time this page is written, and it is what Dynatrace would want to
    receive - so it is said here, among the figures about the pass.
    """
    unread = [rule for rule in result.rules if not rule.enabled and rule.diagnostics]
    if not unread:
        return ""
    items = "".join(
        f"<li><strong>{_e(rule.name)}</strong> - {_e(line)}</li>"
        for rule in unread
        for line in rule.diagnostics
    )
    return (
        f"<p>{len(unread)} switched-off rule(s) could not be read by this tool. Phase 3 evaluates "
        "nothing in a switched-off rule, so none of them needs reworking and none of them is "
        "reported below - but a rule this tool cannot read is a gap in the tool rather than in "
        "the rule, and is worth reporting to Dynatrace:</p>"
        f"<ul class=diagnostics>{items}</ul>"
    )


def _index(bucketed: Sequence[BucketedRule], counts: dict[Outcome, int]) -> str:
    """Counts and verdicts and no detail, so the part read first stays skimmable."""
    bucket_rows = "".join(
        f'<tr><td><a href="#{_anchor(outcome)}">{_e(_OUTCOME_LABEL[outcome])}</a></td>'
        f"<td><code>{_e(outcome.value)}</code></td>"
        f"<td class=num><strong>{counts[outcome]}</strong></td></tr>"
        for outcome in Outcome
        if counts[outcome]
    )
    rule_rows = "".join(
        f'<tr><td><a href="#{_rule_anchor(position)}">{_e(entry.rule.name)}</a></td>'
        f"<td>{_e(_OUTCOME_LABEL[entry.outcome])}</td>"
        f"<td><code>{_e(entry.reason)}</code></td></tr>"
        for position, entry in enumerate(bucketed, start=1)
    )
    if not rule_rows:
        return (
            '<h2 id="summary">Summary</h2>'
            "<p>No affected rule was found on this tenant, so there is nothing to rework.</p>"
        )
    return (
        '<h2 id="summary">Summary</h2>'
        + _panel(
            "<table><thead><tr><th>Outcome</th><th>Code</th><th class=num>Rules</th></tr></thead>"
            f"<tbody>{bucket_rows}</tbody>"
            f"<tfoot><tr><td><strong>Total</strong></td><td></td>"
            f"<td class=num><strong>{len(bucketed)}</strong></td></tr></tfoot></table>"
        )
        + _panel(
            "<table><thead><tr><th>Rule</th><th>Outcome</th><th>Code</th></tr></thead>"
            f"<tbody>{rule_rows}</tbody></table>"
        )
    )


def _sections(bucketed: Sequence[BucketedRule], counts: dict[Outcome, int]) -> str:
    """One section per bucket that holds something, in the taxonomy's own order."""
    positions = {id(entry): position for position, entry in enumerate(bucketed, start=1)}
    rendered = []
    for outcome in Outcome:
        if not counts[outcome]:
            continue
        blocks = "".join(
            _rule_block(positions[id(entry)], entry)
            for entry in bucketed
            if entry.outcome is outcome
        )
        rendered.append(
            f'<h2 id="{_anchor(outcome)}">{_e(_OUTCOME_LABEL[outcome])} ({counts[outcome]})</h2>'
            f'<p class="meaning">{_e(_OUTCOME_MEANING[outcome])}</p>'
            f'<p class="next"><strong>What to do:</strong> {_e(_OUTCOME_ACTION[outcome])}</p>'
            f"{blocks}"
        )
    return "\n".join(rendered)


def _rule_block(position: int, entry: BucketedRule) -> str:
    """Everything the run knows about one rule, verbose by design."""
    rule = entry.rule
    parts = [
        f'<div class="rule" id="{_rule_anchor(position)}">',
        f"<h3>{_e(rule.name)}</h3>",
        _panel(
            _rows(
                ("Object id", f"<code>{_e(rule.object_id)}</code>"),
                ("Outcome", _e(_OUTCOME_LABEL[entry.outcome])),
                ("Code", f"<code>{_e(entry.reason)}</code>"),
                ("What that code means", _e(_REASON_PROSE.get(entry.reason, entry.reason))),
            )
        ),
        _detail(entry),
        _diagnostics(rule),
        _conditions(entry),
        _figures(entry),
        _harvest(entry),
        _attempted(entry),
        _shortfall(entry),
        _queries(entry),
        _payload(entry),
        "</div>",
    ]
    return "".join(part for part in parts if part)


def _detail(entry: BucketedRule) -> str:
    """The free text beneath the code, which is sometimes all that separates two causes of one."""
    if not entry.detail:
        return ""
    return f'<p class="detail">{_e(entry.detail)}</p>'


def _diagnostics(rule: ClassifiedRule) -> str:
    """What could not be read, in full: this is the substance of what Dynatrace needs to receive."""
    if not rule.diagnostics:
        return ""
    items = "".join(f"<li>{_e(line)}</li>" for line in rule.diagnostics)
    return f"<h4>What could not be read</h4><ul class=diagnostics>{items}</ul>"


def _conditions(entry: BucketedRule) -> str:
    rule = entry.rule
    if not rule.conditions:
        # A rule with no condition at all is a shape no rule can be stored in, and the diagnostic
        # above already says so. A heading over nothing would read as a gap in the report.
        return ""
    deprecated = [c for c in rule.conditions if c.standing is ConditionStanding.DEPRECATED]
    surviving = [c for c in rule.conditions if c.standing is ConditionStanding.SURVIVING]
    unreadable = [c for c in rule.conditions if c.standing is ConditionStanding.UNCLASSIFIABLE]
    superseded = entry.replacement.superseded if entry.replacement else ()
    return "".join(
        [
            "<h4>Conditions this rule carries</h4>",
            _condition_table("No longer evaluated", deprecated, superseded),
            _condition_table("Still evaluated", surviving, superseded),
            _condition_table("Not readable by this tool", unreadable, superseded),
        ]
    )


def _condition_table(
    heading: str,
    conditions: Sequence[ClassifiedCondition],
    superseded: Sequence[ClassifiedCondition],
) -> str:
    if not conditions:
        return ""
    rows = "".join(
        "<tr>"
        f"<td><code>{_e(c.attribute or 'unknown attribute')}</code></td>"
        f"<td><code>{_e(c.predicate_type or 'unknown predicate type')}</code></td>"
        f"<td>{_e(_compared(c))}</td>"
        f"<td>{_values_cell(c)}</td>"
        f"<td>{_e(_condition_note(c, superseded))}</td>"
        "</tr>"
        for c in conditions
    )
    return _panel(
        f"<p class=caption>{_e(heading)}</p>"
        "<table><thead><tr><th>Attribute</th><th>Predicate</th><th>Compares</th>"
        "<th>Values</th><th>Note</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _condition_note(
    condition: ClassifiedCondition, superseded: Sequence[ClassifiedCondition]
) -> str:
    if condition in superseded:
        # It stays in the replacement - a minimal diff of the customer's own rule - but a
        # candidate on the same attribute already says everything it says.
        return "kept, but narrows nothing: a harvested condition on the same attribute says as much"
    if condition.standing is ConditionStanding.UNCLASSIFIABLE:
        return condition.diagnostic
    if condition.reason is not None:
        return _AFFECTED_PROSE[condition.reason]
    return ""


def _values_cell(condition: ClassifiedCondition) -> str:
    if condition.tags:
        return ", ".join(f"<code>{_e(_tag_text(condition, tag))}</code>" for tag in condition.tags)
    if condition.values:
        return ", ".join(f"<code>{_e(value)}</code>" for value in condition.values)
    if condition.predicate_type is PredicateType.STRING_EXISTS:
        return "<em>any value</em>"
    return ""


def _tag_text(condition: ClassifiedCondition, tag: ParsedTag) -> str:
    """One tag entry as a reader can act on it.

    A key-existence predicate ignores the value, and a value predicate carrying none matches only
    tags whose value is null - two different things that must not share a spelling.
    """
    if condition.predicate_type is PredicateType.TAG_KEY_EQUALS:
        return f"{tag.key} (any value)"
    return f"{tag.key}={tag.value}" if tag.value is not None else f"{tag.key} (no value)"


def _compared(condition: ClassifiedCondition) -> str:
    if condition.predicate_type is PredicateType.STRING_EXISTS:
        return "every entity of its type"
    return "case-sensitive" if condition.case_sensitive else "case-insensitive"


def _figures(entry: BucketedRule) -> str:
    """What the rule targets today, at both grains failure detection is decided on."""
    if entry.resolution is None:
        return ""
    figures = [("Services targeted today", _e(_service_figure(entry.resolution)))]
    if _established(entry.resolution):
        # Withheld with the count itself: a read that settled nothing leaves this empty too, and
        # "it also selects no external service" is a claim of its own.
        figures.append(
            ("External services it also selects", str(len(entry.resolution.external_services)))
        )
    spans = _span_figure(entry)
    if spans:
        figures.append(("Entry-point spans targeted today", spans))
    return _panel(_rows(*figures))


def _service_figure(resolution: ResolvedRule) -> str:
    """The services the rule selects, in the one reading the number actually carries.

    The set that arrives here is the one left after the traffic intersection, so a rule whose
    services were all idle arrives with none of them. A bare zero then reads as "this rule
    selects nothing", which is a different finding with a bucket of its own and the opposite of
    what the code beside it says. What its conditions did select is still in the rows the
    resolution kept.
    """
    if not _established(resolution):
        return "not established: the read that would have counted them did not complete"
    if resolution.outcome is ResolutionOutcome.DORMANT:
        selected, _ = partition_external(resolution.rows.services)
        return (
            f"{len(selected)} selected by its conditions, none of which carried traffic in the "
            "query window"
        )
    return str(len(resolution.target_set))


_NOTHING_ESTABLISHED = frozenset(
    {
        ResolutionOutcome.INCOMPLETE_READ,
        ResolutionOutcome.QUERY_TOO_LARGE,
        ResolutionOutcome.ERROR,
    }
)


def _established(resolution: ResolvedRule) -> bool:
    """Whether this run settled what the rule selects at all.

    A read that came back capped, one too large to be issued, and one that failed all leave the
    Target Set empty for want of an answer rather than for want of services. Reporting that
    emptiness as a count is the claim the buckets exist to keep apart.
    """
    return resolution.outcome not in _NOTHING_ESTABLISHED


def _span_figure(entry: BucketedRule) -> str:
    """The Target Span count, or "" where nothing ever set out to establish one.

    Three different silences, and none of them may be spelled as another. A rule with no harvest
    behind it - one that never reached a replacement, or one the tool failed on part-way through -
    had no read set out to count its spans, so there is no figure to report either way. A rule
    with nothing decided per span costs no span read, and the count would default to zero - which
    reads as "this rule targets no traffic", a different finding with a bucket of its own. Only a
    harvest whose span read came back capped is a figure the run tried and failed to establish.
    """
    if entry.replacement is None or not _harvested(entry.replacement):
        return ""
    spans = entry.replacement.harvested.target_spans
    if spans is None:
        return "not established: the read that would have counted them came back capped"
    if not any(query.dataset is Dataset.ENTRY_SPANS for query in _issued(entry)):
        return "not measured: nothing about this rule is decided per span, so none were counted"
    return str(spans)


def _harvest(entry: BucketedRule) -> str:
    """Every attribute the Target Set offered, and what became of it.

    Kept whether it helped or not: someone deciding to narrow this rule by hand should not have to
    rediscover what the tenant offered.
    """
    replacement = entry.replacement
    if replacement is None:
        return ""
    found = replacement.harvested
    dropped = {drop.attribute: drop for drop in found.dropped}
    attributes = list(dict.fromkeys([*found.values, *dropped]))
    if not attributes:
        return ""
    keyed = [attribute for attribute in attributes if _is_tag_key(attribute)]
    plain = [attribute for attribute in attributes if attribute not in set(keyed)]
    parts = ["<h4>What the targeted services offered</h4>"]
    if plain:
        parts.append(_offered_table(plain, replacement, found))
    if keyed:
        # One expander over all of them rather than one each: they are read as a set - which key
        # could have carried this rule - and a dozen expanders is the same wall in another shape.
        parts.append(
            "<details>"
            f"<summary>Primary tag keys the services offered ({len(keyed)})</summary>"
            f"{_offered_table(keyed, replacement, found)}</details>"
        )
    return "".join(parts)


def _is_tag_key(attribute: str) -> bool:
    """Whether a harvested attribute is one tag key rather than an attribute of the rule.

    The tag axis dropped whole is not one of these: it is a single line saying nothing about any
    key was learnt, which is the one thing in this account a reader must not have to open.
    """
    return attribute.startswith(f"{Attribute.PG_TAG} ")


def _offered_table(attributes: Sequence[str], replacement: Replacement, found: Harvest) -> str:
    rows = ""
    for attribute, (fate, note) in _by_fate(attributes, replacement):
        rows += (
            f"<tr><td><code>{_e(attribute)}</code></td>"
            f"<td>{_values_found(found.values.get(attribute, ()))}</td>"
            f"<td>{_e(fate)}</td><td>{_e(note)}</td></tr>"
        )
    return _panel(
        "<table><thead><tr><th>Attribute</th><th>Values found</th><th>What became of it</th>"
        "<th>Why</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def _by_fate(
    attributes: Sequence[str], replacement: Replacement
) -> list[tuple[str, tuple[str, str]]]:
    """The attributes with what became of each, most useful to a reader first.

    Read off the dataset each attribute is declared on, they arrive interleaved: what the rule
    ended up narrowed by sits wherever its declaration happens to fall, among everything that went
    nowhere. The sort is stable, so within one fate the declaration order is still what orders
    them.
    """
    fates = [(attribute, _fate(attribute, replacement)) for attribute in attributes]
    return sorted(fates, key=lambda entry: _FATE_ORDER.index(entry[1][0]))


# Kept first, then the one that was usable and did not have to be used, then the two that never
# reached the condition set - a reader working down this table is working away from the rule.
_FATE_ORDER = ["kept in the condition set", "not needed", "dropped", "not tried"]


def _values_found(values: Sequence[str]) -> str:
    """The values one attribute offered, behind their own count once there are too many to read.

    A single tag key runs to thousands of values on a tenant of any size. They are kept - someone
    narrowing the rule by hand should not have to rediscover what it offered - but a page that
    spells them all out is that list with the report buried somewhere inside it.
    """
    if not values:
        return "<em>none</em>"
    listed = ", ".join(f"<code>{_e(value)}</code>" for value in values)
    if len(values) <= _VALUES_AT_A_GLANCE:
        return listed
    return f"<details><summary>{len(values)} values</summary>{listed}</details>"


# Where a list stops being read at a glance and starts being scrolled past.
_VALUES_AT_A_GLANCE = 10


def _fate(attribute: str, replacement: Replacement) -> tuple[str, str]:
    for drop in replacement.harvested.dropped:
        if drop.attribute == attribute:
            return "dropped", " ".join(filter(None, (_DROP_PROSE[drop.reason], drop.detail)))
    for unneeded in replacement.unneeded:
        if unneeded.attribute == attribute:
            return (
                "not needed",
                "the conditions kept reproduce what the rule targets without it, and a condition "
                "that excludes nothing still costs a comparison on every span for as long as the "
                "rule lives",
            )
    for candidate in replacement.harvested.candidates:
        if candidate.attribute == attribute and candidate.condition in replacement.conditions:
            return "kept in the condition set", ""
    return "not tried", "the rule was settled before this attribute could be used"


def _attempted(entry: BucketedRule) -> str:
    """The condition set a rule that cannot be covered was measured on.

    Labelled as an attempt and shaped as a table rather than a payload: nothing was emitted for
    this rule and nothing here may be mistaken for something deployable.
    """
    replacement = entry.replacement
    if replacement is None or entry.outcome is Outcome.COVERED or not replacement.conditions:
        return ""
    return (
        "<h4>The condition set that was tried</h4>"
        "<p>This is what the tool measured, not a replacement. "
        f"{_e(_ATTEMPT_PROSE[entry.outcome])}</p>"
        + _condition_table(
            "Attempted, not deployable", replacement.conditions, replacement.superseded
        )
    )


def _shortfall(entry: BucketedRule) -> str:
    """The services that withheld the verdict, which are the ones a reviewer has to act on."""
    replacement = entry.replacement
    if replacement is None:
        return ""
    said = ""
    if replacement.excess:
        said += _identifiers(
            "Services the attempted set would have selected that the rule does not",
            replacement.excess,
        )
    if replacement.missed:
        said += _identifiers(
            "Services the rule targets that the attempted set did not select", replacement.missed
        )
    return f"<h4>Where it fell short</h4>{said}" if said else ""


def _identifiers(heading: str, identifiers: Iterable[str]) -> str:
    listed = "".join(f"<li><code>{_e(identifier)}</code></li>" for identifier in sorted(identifiers))
    return f"<p class=caption>{_e(heading)}</p><ul class=ids>{listed}</ul>"


def _queries(entry: BucketedRule) -> str:
    """Every query this rule cost, one expandable each.

    The rows they came back with are not here: they are large, and they are in this run's own
    cache directory should one ever need checking.
    """
    issued = _issued(entry)
    if not issued:
        return ""
    blocks = ""
    for query in issued:
        paid = "answered from this run's cache" if query.cache_hit else "issued to the tenant"
        blocks += (
            "<details><summary>"
            f"Query over {_e(_DATASET_NAMES[query.dataset])} - {_e(paid)} "
            f"(cache key <code>{_e(cache_key(query.query))}</code>)"
            f"</summary><pre>{_e(query.query)}</pre></details>"
        )
    return f"<h4>Queries this rule cost ({len(issued)})</h4>{blocks}"


def _harvested(replacement: Replacement) -> bool:
    """Whether the harvest ran at all.

    It reports every declared attribute, taken or dropped, so an empty account of both means it
    never got to run rather than that the Target Set offered nothing.
    """
    return bool(replacement.harvested.values or replacement.harvested.dropped)


def _issued(entry: BucketedRule) -> list[IssuedQuery]:
    """Every query this rule cost, across the two stages that asked one."""
    return [
        *(entry.resolution.queries if entry.resolution else ()),
        *(entry.replacement.queries if entry.replacement else ()),
    ]


def _payload(entry: BucketedRule) -> str:
    """The deployable body, where one exists, with where it goes and where it was written."""
    artifact = entry.artifact
    if artifact is None:
        return ""
    body = artifact.content.get("replacement_rule_body")
    if body is None:
        return ""
    insert_after = artifact.content.get("insert_after") or ""
    position = (
        f"Insert after the rule with object id <code>{_e(insert_after)}</code>."
        if insert_after
        else "Insert ahead of every other rule: this one is evaluated first today."
    )
    return (
        "<h4>The replacement</h4>"
        "<p>This body reproduces exactly what the rule targets today, and arrives disabled so "
        f"that landing it changes nothing until it is turned on. {position}</p>"
        f"<p>Written to <code>{_e(artifact.path)}</code>.</p>"
        "<details><summary>Replacement rule body</summary>"
        f"<pre>{_e(json.dumps(body, indent=2))}</pre></details>"
    )


def _panel(inner: str) -> str:
    return f'<div class="panel">{inner}</div>'


def _rows(*pairs: tuple[str, str]) -> str:
    rows = "".join(f"<tr><th>{_e(label)}</th><td>{value}</td></tr>" for label, value in pairs)
    return f"<table class=facts><tbody>{rows}</tbody></table>"


def _anchor(outcome: Outcome) -> str:
    return f"bucket-{outcome.value}"


def _rule_anchor(position: int) -> str:
    """A positional anchor, because a stored object id is not safe in a fragment."""
    return f"rule-{position}"


# What to call each read in a sentence a reader can act on: the `fetch` target a dataset is
# spelled as says nothing about which of a rule's three reads it was.
_DATASET_NAMES: dict[Dataset, str] = {
    Dataset.SERVICES: "services",
    Dataset.PROCESS_GROUPS: "process groups",
    Dataset.ENTRY_SPANS: "entry-point spans",
}

_OUTCOME_LABEL: dict[Outcome, str] = {
    Outcome.COVERED: "Replacement found",
    Outcome.NOT_COVERABLE: "No safe replacement",
    Outcome.SELECTS_NOTHING: "Targets nothing today",
    Outcome.NO_TRAFFIC: "No traffic in the query window",
    Outcome.NO_VERDICT: "No verdict reached",
    Outcome.UNPROCESSABLE: "Could not be processed",
}

# What became of the condition set a rule was measured on, in the reading its own bucket carries.
# Never the not-coverable sentence for all of them: a comparison that was never made has no
# result, and stating one contradicts the bucket the rule is standing in.
_ATTEMPT_PROSE: dict[Outcome, str] = {
    Outcome.NOT_COVERABLE: (
        "It did not reproduce what the rule targets, so nothing was written out for it and there "
        "is nothing here to deploy."
    ),
    Outcome.NO_VERDICT: (
        "Whether it reproduces what the rule targets was never established, so nothing was "
        "written out for it and there is nothing here to deploy."
    ),
    Outcome.UNPROCESSABLE: (
        "The tool did not finish measuring it, so nothing was written out for it and there is "
        "nothing here to deploy."
    ),
}

_OUTCOME_MEANING: dict[Outcome, str] = {
    Outcome.COVERED: (
        "A condition set built only from attributes that are still evaluated targets exactly the "
        "services this rule targets today, proved against live data over the query window above."
    ),
    Outcome.NOT_COVERABLE: (
        "The tool measured what this rule targets and found no condition set that reproduces it "
        "without a condition that is no longer evaluated. Either every set it could build also "
        "selected services the rule does not, or the rule carries something it cannot express."
    ),
    Outcome.SELECTS_NOTHING: (
        "This rule targets nothing today, before anything changes. The zone, tag or name it "
        "refers to resolved to nothing, or the only services it reaches are external ones this "
        "tool does not govern."
    ),
    Outcome.NO_TRAFFIC: (
        "The services this rule targets carried no failure-detection traffic in the query window, "
        "so there was nothing to measure a replacement against. That is a statement about the "
        "window, not about the rule."
    ),
    Outcome.NO_VERDICT: (
        "A measurement did not complete, so no claim is made either way. Nothing here says the "
        "rule cannot be reworked - only that this run could not establish it."
    ),
    Outcome.UNPROCESSABLE: (
        "This tool has no reading for the rule, or it failed while working on it. Neither is "
        "something that can be fixed by editing the rule, and neither changes on a re-run."
    ),
}

_OUTCOME_ACTION: dict[Outcome, str] = {
    Outcome.COVERED: (
        "review the body below, then create it and enable it in place of the original rule."
    ),
    Outcome.NOT_COVERABLE: (
        "rework the rule by hand. The attributes its services offered are listed per rule below, "
        "which is where to start."
    ),
    Outcome.SELECTS_NOTHING: (
        "check whether the zone, tag or name the rule refers to still exists. If it does not, the "
        "rule is dead configuration and may be deletable."
    ),
    Outcome.NO_TRAFFIC: (
        "re-run with a wider query window, over a stretch of time the services are known to have "
        "served traffic in."
    ),
    Outcome.NO_VERDICT: (
        "read the per-rule detail below, then narrow the query window or the rule's scope and run "
        "again."
    ),
    Outcome.UNPROCESSABLE: (
        "report this to Dynatrace, together with the rule and the diagnostics shown below."
    ),
}

# One sentence per terminal code. The codes form one flat space across the pipeline's stages, so
# this is keyed on the code itself and needs no per-stage prefixing.
_REASON_PROSE: dict[str, str] = {
    "exact": "the condition set targets exactly the services the rule targets today.",
    "over-selecting": (
        "every condition set the tool could build also selected services the rule does not "
        "target, and this API offers no way to exclude them."
    ),
    "service-type-only": (
        "nothing beyond the service type could be harvested from the targeted services, and a "
        "condition saying only that selects very nearly every service on the tenant."
    ),
    "empty-replacement": (
        "no attribute could be harvested and the rule keeps no condition of its own, and a rule "
        "carrying no condition at all targets every service."
    ),
    "no-expressible-candidate": (
        "the condition set the targeted services led to is one this tool cannot put into a query, "
        "so it could not be proved."
    ),
    "too-many-conditions": (
        "reproducing what the rule targets needs more conditions than a single rule can carry."
    ),
    "untranslatable": (
        "the rule carries a condition this tool cannot express as a query, so nothing was asked "
        "about it and nothing is claimed about its traffic."
    ),
    "empty-scope": "the rule's own scope resolved to nothing, so it targets no service.",
    "matches-nothing": (
        "the rule's conditions cannot all hold at once, so it targets nothing whatever the tenant "
        "carries."
    ),
    "only-external-services": (
        "the only services this rule reaches are external ones, which this tool does not govern "
        "and which failure detection rules will not apply to."
    ),
    "dead-today": (
        "the rule carries a process-group tag condition mixing primary and non-primary tag keys, "
        "which is skipped whole already today, so the rule targets nothing."
    ),
    "dormant": (
        "the services this rule targets carried no failure-detection traffic in the query window."
    ),
    "unverified": (
        "a read that would have proved the condition set came back capped, so it was never "
        "compared against what the rule targets."
    ),
    "under-selecting": (
        "the comparison that would have proved the condition set did not hold, on a path that "
        "cannot select fewer services than the rule does, so no replacement is offered."
    ),
    "incomplete-read": (
        "a read that establishes what the rule targets came back capped, so the rule has no "
        "subject to measure a replacement against."
    ),
    "query-too-large": (
        "the rule targets more entities than a single query can be scoped by, so it could not be "
        "measured in one read."
    ),
    "processing-error": "the tool failed while working on this rule.",
    "unclassifiable": (
        "the rule is in a shape this tool has no reading for, so it was not measured. Nothing a "
        "tenant administrator can change about the rule affects this."
    ),
}

_AFFECTED_PROSE: dict[DeprecationReason, str] = {
    DeprecationReason.SERVICE_TAG: (
        "a service-tag condition, which is no longer evaluated"
    ),
    DeprecationReason.MANAGEMENT_ZONE: (
        "a management-zone condition, which is no longer evaluated"
    ),
    DeprecationReason.NON_PRIMARY_PG_TAG: (
        "a process-group tag condition on a non-primary tag key, which is no longer evaluated"
    ),
    DeprecationReason.MIXED_PG_TAG: (
        "a process-group tag condition mixing primary and non-primary tag keys, which is skipped "
        "whole already today"
    ),
}

_DROP_PROSE: dict[DropReason, str] = {
    DropReason.MISSING_VALUE: "one of the targeted services carries no value for it.",
    DropReason.MISSING_ON_SOME_SPAN: (
        "the targeted services carry it on only part of their failure-detection entry-point "
        "spans, and a primary tag is compared against every one of them."
    ),
    DropReason.UNREADABLE: "the read that would have harvested it did not answer.",
    DropReason.UNMEASURED_POPULATION: (
        "the read that would have measured these values came back capped, so whether they cover "
        "the targeted services could not be established."
    ),
    DropReason.TOO_LARGE_TO_SCOPE: "more targeted entities than one query can be scoped by.",
    DropReason.TOO_MANY_VALUES: "more distinct values than a single condition can carry.",
    DropReason.NO_STORED_SPELLING: "the values have no spelling a condition can be stored with.",
    DropReason.AFFIX_TOO_SHORT: (
        "no shared prefix, suffix or substring long enough to be meaningful."
    ),
    DropReason.REDUNDANT: "the rule already says exactly this.",
}

_CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       margin: 0 auto; padding: 24px; max-width: none; background: #f6f7f9; color: #1f2328; }
h1 { font-size: 1.55rem; margin: 0 0 16px; }
h2 { font-size: 1.2rem; margin: 40px 0 8px; padding-bottom: 6px; border-bottom: 2px solid #d0d7de; }
h3 { font-size: 1.02rem; margin: 0 0 10px; }
h4 { font-size: 0.78rem; margin: 18px 0 6px; color: #57606a; text-transform: uppercase;
     letter-spacing: 0.06em; }
p { margin: 8px 0; font-size: 0.9rem; line-height: 1.5; max-width: 90ch; }
ul { margin: 6px 0; padding-left: 22px; font-size: 0.9rem; line-height: 1.5; max-width: 90ch; }
code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 0.82rem;
       background: #eaeef2; padding: 1px 4px; border-radius: 3px; }
pre { background: #1f2328; color: #e6edf3; padding: 14px; border-radius: 6px; overflow-x: auto;
      font-size: 0.78rem; line-height: 1.45; white-space: pre; margin: 8px 0; }
table { width: 100%; border-collapse: collapse; font-size: 0.86rem; }
th { text-align: left; background: #eaeef2; padding: 6px 10px; font-size: 0.74rem;
     text-transform: uppercase; letter-spacing: 0.04em; color: #57606a; }
td { padding: 6px 10px; border-bottom: 1px solid #eaeef2; vertical-align: top;
     overflow-wrap: anywhere; }
tr:last-child td { border-bottom: none; }
td.num, th.num { text-align: right; }
table.facts th { width: 240px; background: transparent; text-transform: none; letter-spacing: 0;
                 font-size: 0.86rem; color: #57606a; border-bottom: 1px solid #eaeef2; }
.panel { background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 4px 0;
         margin: 10px 0; overflow: hidden; }
.panel p.caption { margin: 10px 12px 4px; font-size: 0.78rem; text-transform: uppercase;
                   letter-spacing: 0.05em; color: #57606a; }
.caveat { background: #fff8c5; border: 1px solid #d4a72c; border-radius: 8px; padding: 12px 16px;
          margin: 16px 0; font-size: 0.9rem; }
.scope { background: #fff; border-left: 3px solid #8c959f; padding: 10px 14px; color: #57606a; }
.meaning { background: #fff; border-left: 3px solid #8c959f; padding: 10px 14px; }
.next { margin: 4px 0 16px; }
.detail { background: #fff; border-left: 3px solid #d0d7de; padding: 8px 14px; }
.rule { background: #fff; border: 1px solid #d0d7de; border-radius: 8px; padding: 16px 20px;
        margin: 14px 0; }
.rule .panel { border: 1px solid #eaeef2; }
details { margin: 6px 0; font-size: 0.86rem; }
summary { cursor: pointer; padding: 6px 0; }
ul.ids, ul.diagnostics { font-size: 0.84rem; }
"""
