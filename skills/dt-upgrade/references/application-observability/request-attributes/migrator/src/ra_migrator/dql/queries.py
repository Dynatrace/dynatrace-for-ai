"""The reads a run asks, as text, and how each one's answer is read back.

Query text, the window and completeness are one concern: the window is rendered into the text,
the cache keys on that text, and whether an answer is whole is a property of what that text
came back with. The stage order is the builder's own and never the Scope's, so two Scopes asking
the same question render the same bytes and the cache answers the second.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..attributes.tags import PRIMARY_TAG_PREFIX, Tag
from ..attributes.technologies import spellings_of
from ..clients.transports import DqlAnswer
from .windowing import QueryWindow

# The process group's side of the host group relationship: single-valued, and so uncappable.
_HOST_GROUP = "groups[dt.entity.host_group]"

# The service's side of the process group relationship, single-valued for the same reason.
_RUNS_ON = "runs_on[dt.entity.process_group]"

# The most ids one `in(...)` group takes. One more is rejected outright, so a longer list is asked
# as several queries whose answers are read as one.
MAX_GROUP_ELEMENTS = 10_000


class QueryBuildError(ValueError):
    """A read this layer will not render, named by the set that cannot be rendered."""


class PartialReadError(ValueError):
    """A read assembled from fewer answers than it has queries, which is not an answer at all."""


@dataclass(frozen=True)
class Read:
    """One question, as the query text it takes to ask it."""

    queries: tuple[str, ...]
    # The fields this read counts with, which arrive as text: Grail serialises a `long` as a JSON
    # string and aliasing it changes nothing, so `count()` answers `"384"`. Named per read rather
    # than guessed, and coerced here so no later stage can compare a count against a number and
    # quietly get `false`.
    integral_fields: tuple[str, ...] = ()

    def answered(self, answers: Sequence[DqlAnswer]) -> DqlAnswer:
        """What this read came back with, as one answer however many queries it took.

        Whole only if every chunk was: completeness is read from all of them, because one capped
        chunk among five makes the assembled answer short by rows nothing else can notice.
        """
        if len(answers) != len(self.queries):
            raise PartialReadError(
                f"a read of {len(self.queries)} queries cannot be assembled from "
                f"{len(answers)} answer(s): the missing ones are neither empty nor complete"
            )
        records = [self._typed(record) for answer in answers for record in answer.records]
        return DqlAnswer(records, complete=all(answer.complete for answer in answers))

    def _typed(self, record: dict[str, Any]) -> dict[str, Any]:
        counted = {
            field: int(record[field])
            for field in self.integral_fields
            if isinstance(record.get(field), str)
        }
        return record | counted if counted else record


def process_group_read(
    window: QueryWindow,
    *,
    tag: Tag | None = None,
    host_group: str | None = None,
    process_group: str | None = None,
) -> Read:
    """What one Scope's own conditions select, with the tags that decide which rows are in.

    Handed none of the three it refuses. There is no read of the population here: a process group
    read with nothing to narrow it asks for the whole tenant, and the Candidate Universe it would
    be answering is not read at all - it lives in the Surviving Conditions, which are in the
    replacement Scope, which is what a candidate is compared as.

    Both halves of a tag reach the query text - the key, and the value where it carries one - as
    two nets that narrow and never decide: the rows they return are settled by the parsed-triple
    comparison afterwards. The whole tag rather than a loose key and value, so a value cannot be
    rendered without the key it belongs to. Handed a host group alone this is the membership read,
    the one form deliberately left unnarrowed, because the host group rung needs the members
    carrying no tag and because an empty Target Set and an empty universe are otherwise
    indistinguishable.

    Driven from the process group side, which is required rather than merely cheaper: a host
    group's `group_of[dt.entity.process_group]` projects at most a hundred ids per record and says
    nothing about which records lost some, while a process group's own `groups[dt.entity.host_group]`
    is single-valued and so cannot be capped. The host group's name is pulled in for the report;
    the filtering is on the identifier, which is what the condition stores.
    """
    if host_group is None and tag is None and process_group is None:
        raise QueryBuildError(
            "refusing to render a process group read carrying none of the resolving Scope's "
            "conditions: with nothing to narrow it, it asks for every process group on the "
            "tenant and truncates as soon as the window is widened"
        )
    stages = [f"fetch dt.entity.process_group, {window.timeframe}"]
    if host_group is not None:
        stages.append(f'filter {_HOST_GROUP} == "{host_group}"')
    if process_group is not None:
        stages.append(f'filter id == "{process_group}"')
    stages.append(f"fields id, tags, host_group = {_HOST_GROUP}")
    stages.append(
        f"lookup [fetch dt.entity.host_group, {window.timeframe}"
        " | fields id, host_group_name = entity.name],"
        " sourceField:host_group, lookupField:id, fields:{host_group_name}"
    )
    if tag is not None:
        stages.append("expand tags")
        stages.extend(_tag_nets(tag))
    return Read((_piped(stages),))


def _tag_nets(tag: Tag) -> list[str]:
    """The narrowing filters one Scope tag renders: its key, and its value where it has one.

    A key-only tag renders one net. `parse_tag` returns `value or None`, so a `Tag.value` that is
    there is never empty - and one beginning with a colon cuts to an empty segment, which is a
    `contains(tags, "")` matching every non-null row rather than an error. So the degenerate case
    is a no-op net and needs no guard; the comparison still decides.
    """
    nets = [tag.key] if tag.value is None else [tag.key, tag.value]
    return [f'filter contains(tags, "{_tag_text(one)}", caseSensitive: true)' for one in nets]


def _tag_text(part: str) -> str:
    """As much of a tag key or value as a text match on a rendered tag can safely look for.

    The segment up to the first colon, and no further: Grail renders an entity tag with its
    colons escaped while the Scope stores the same tag with none, so the text beyond that point
    differs between the two sides even where the tag is the same one. The rule is the key's and
    the value's alike, because the escaping is applied to both.

    Narrowing on less than the whole of either is safe because these filters decide nothing. They
    are nets: `contains` is case-sensitive by default and `UniversalTag.equals` compares
    case-sensitively too, so every row the parsed-triple comparison would have kept is still in
    the answer, and the rows they let through that do not belong are dropped by that comparison.

    What comes out is a string literal, so the two characters a double-quoted one cannot carry as
    themselves are escaped. Nothing constrains what a tenant puts in a tag key - the backend
    trims nothing and validates nothing there - so an unescaped quote would not narrow the read
    but end it, as a syntax error the run would have to decode.
    """
    segment = part.split(":", 1)[0]
    return segment.replace("\\", "\\\\").replace('"', '\\"')


def _piped(stages: list[str]) -> str:
    return " | ".join(stages)


def service_read(
    window: QueryWindow,
    *,
    process_groups: Sequence[str] | None = None,
    service_technology: str | None = None,
) -> Read:
    """Every service the resolving Scope's own conditions leave in play, and its technologies.

    Read from the service side, where the process group relationship is single-valued: the process
    group side of it caps at a hundred ids per record without saying which records lost any.

    The technology is narrowed server-side, in every spelling the runtime accepts. It is rendered
    at all because Grail's `type:` segment carries the `KnownTechnologyDto` spelling - the very
    string the Scope stores - so the filter tests the string the in-memory comparison tests and
    cannot drop a row that comparison would have kept. The refusal without one still licenses the
    read: a Target Set is service-shaped only when a `serviceTechnology` condition made it so, and
    every other Scope is answered by the process group read alone.

    This is resolution's read and not closure's. Closure asks the opposite question - every
    service of every touched process group, including the ones *not* carrying the technology - so
    it has its own builder and its own bound.
    """
    if service_technology is None:
        raise QueryBuildError(
            "refusing to render a service read for a Scope carrying no serviceTechnology "
            "condition: nothing else makes a Target Set service-shaped"
        )
    scoped = (
        _groups_of(process_groups, named="the Surviving host group's process groups")
        # The Scope sets no host group, process group or deprecated tag, so nothing bounds the
        # read but the technology - which is now in the query text, so the read is still the
        # rule's question. Naming a population instead would render tens of thousands of ids to
        # express no restriction at all.
        if process_groups is not None
        else [None]
    )
    return Read(
        tuple(
            _service_query(window, scoped_by=group, technology=service_technology)
            for group in scoped
        )
    )


def _service_query(window: QueryWindow, *, scoped_by: str | None, technology: str) -> str:
    """One narrowed service read, with the relationship projected before the array is expanded.

    `contains()` over an array field matches nothing and raises only a warning, so the array is
    `expand`ed first and the scalar matched - written the direct way this read answers an empty
    Target Set that looks measured. `expand` multiplies the rows, so `dedup` collapses them back
    to one per service; `fieldsAdd` is what keeps `process_group` projectable afterwards.
    """
    stages = [f"fetch dt.entity.service, {window.timeframe}"]
    if scoped_by is not None:
        stages.append(f"filter in({_RUNS_ON}, {scoped_by})")
    stages.append(f"fieldsAdd process_group = {_RUNS_ON}")
    stages.append("expand softwareTechnologies")
    stages.append(f"filter {_technology_net(technology)}")
    stages.append("fields id, process_group, softwareTechnologies")
    stages.append("dedup id")
    return _piped(stages)


def service_closure_read(window: QueryWindow, *, process_groups: Sequence[str]) -> Read:
    """Every service of the process groups a Target Set touches, carrying **no** technology.

    The other half of the population resolution's read narrows away, and the half a closure
    verdict is decided from: whether every service of every touched process group carries the
    technology is a question about the ones that do not. A read narrowed by the technology would
    make that comparison trivially true and gate every service-shaped Data Source as narrowing
    nothing.

    Its own builder rather than a flag on `service_read`, so each refuses over its own condition:
    this one without process groups to bound it, that one without a technology to render. Neither
    has an unbounded form left. The bound here is not a fresh question - resolution's read already
    projected the process group of every target service, and those process groups *are* the
    bound - so `softwareTechnologies` is not projected at all.
    """
    return Read(
        tuple(
            _piped(
                [
                    f"fetch dt.entity.service, {window.timeframe}",
                    f"filter in({_RUNS_ON}, {group})",
                    f"fields id, process_group = {_RUNS_ON}",
                ]
            )
            for group in _groups_of(process_groups, named="the touched process groups")
        )
    )


def _technology_net(technology: str) -> str:
    """The narrowing filter one technology condition renders, OR-ed over its spellings.

    Case-insensitive, because the runtime's verbatim branch is and because the tenant holds both
    `KAFKA` and `Kafka`. The trailing comma is load-bearing: it is what stops `type:KAFKA,`
    matching `type:CONFLUENT_KAFKA_CLIENT,`, and every non-null entry carries one.

    It decides nothing either way - `_carries_technology` compares the `type:` segment afterwards
    over the same spelling set, so a row this admits and that rejects is still dropped.
    """
    return " or ".join(
        f'contains(softwareTechnologies, "type:{one},", caseSensitive: false)'
        for one in spellings_of(technology)
    )


def _groups_of(ids: Sequence[str], *, named: str) -> list[str]:
    """The `in(...)` groups an id list renders as: never none of them, never an over-long one.

    Both ends of the refusal sit here rather than in each caller, because a caller that forgets
    has two ways to be wrong and only one of them is loud. An empty group and an over-long one are
    both rejected by the backend, so they cost a failed read and a decoded syntax error; dropping
    the clause instead turns a scoped read into a scan of the whole tenant, which succeeds.
    """
    if not ids:
        raise QueryBuildError(f"refusing to render a read scoped to an empty set: {named}")
    return [
        "{" + ", ".join(f'"{one}"' for one in ids[at : at + MAX_GROUP_ELEMENTS]) + "}"
        for at in range(0, len(ids), MAX_GROUP_ELEMENTS)
    ]


class TargetShape(Enum):
    """Which entity a Target Set is a set of, as the span field that identifies one."""

    PROCESS_GROUP = "dt.entity.process_group"
    SERVICE = "dt.entity.service"


def span_read(
    window: QueryWindow,
    *,
    shape: TargetShape,
    targets: Sequence[str],
    primary_tag_keys: Sequence[str],
) -> Read:
    """What the Target Set's spans carry, per Primary Tag key, counted rather than listed.

    This read measures **the original**: which Primary Tag values occur on what the deprecated
    Scope selects, and how many entry-point calls each target carries. Those are the values a
    candidate is drawn from and the count a replacement's own count is compared against - and
    they are the whole of its role. It may reach no verdict: its filter carries Target Set ids,
    which are the output of evaluating the Deprecated Condition, so asking it what a candidate
    does is asking what the candidate does inside the set the deprecated condition already
    picked. `verification_span_read` is the read that may answer that.

    Counted because the count is what shows partial coverage: a target appearing both with and
    without a value means a candidate carrying that value under-selects it.

    The filter key follows the Target Set's shape while the grouping never does: the answer has to
    say which process group *and* which service a count belongs to whichever set was asked for.

    Grouped only by the keys the probe left standing - null-free and within the fan-out cap - which
    can be **none** where the one surviving candidate is a high-cardinality key-only key with no
    values to enumerate. That keyless form still groups by Target Set member, because the harvest's
    remaining job there is the dormant list (`Harvest.dormant`), which only a member grouping yields.
    The discovery gate is upstream now (`_primary_tag_material`), so no keys here is an ordinary
    pruned harvest and never a keyless scan of the whole tenant.
    """
    grouped = ", ".join(
        [
            "dt.entity.process_group",
            "dt.entity.service",
            *(_quoted_field(key) for key in primary_tag_keys),
        ]
    )
    return Read(
        tuple(
            _piped(
                [
                    *_entry_spans(window, shape=shape, scoped_by=group),
                    "summarize span_count = count(), by: { " + grouped + " }",
                ]
            )
            for group in _groups_of(targets, named="the Target Set")
        ),
        integral_fields=("span_count",),
    )


@dataclass(frozen=True)
class ProbeReading:
    """What the probe measured over the Target Set's entry-point spans, summed across chunks.

    `total` is the span population the null gate is read against; `present` is per key the spans
    carrying it (`isNotNull`), and `distinct` its approximate value cardinality. `present == total`
    is the universal usability gate - a genuine null on any span disqualifies the key in every
    form - and `distinct` only sorts the null-free survivors into `key:value` (<= cap) and key-only.
    """

    total: int
    present: Mapping[str, int]
    distinct: Mapping[str, int]


def _probe_present(index: int) -> str:
    return f"present_{index}"


def _probe_distinct(index: int) -> str:
    return f"distinct_{index}"


_PROBE_TOTAL = "total"


def primary_tag_probe_read(
    window: QueryWindow,
    *,
    shape: TargetShape,
    targets: Sequence[str],
    primary_tag_keys: Sequence[str],
) -> Read:
    """One bounded read that measures null-coverage and value cardinality without ever capping.

    Ungrouped: one `summarize` over the same Target-Set-scoped entry-point spans the harvest reads,
    so its output is one row per chunk and the record cap can never bite. Per discovered key it
    measures `countIf(isNotNull(...))` against a shared `count()` - the null gate - and
    `countDistinct(...)`, the approximate alias, which never fails where `countDistinctExact` would
    past a million distinct values (`180`, *Exact vs approx*).

    The keys are aliased by **position** rather than by name: a `summarize` alias must be an
    identifier, and a discovered key can carry characters (`primary_tags.pri/ma/ry/`) that no alias
    accepts. `primary_tag_probe_of` maps the positions back to the keys in the same order.

    Refuses with no keys, the one shape that measures nothing: the discovery gate upstream means a
    probe is only ever rendered where at least one key was discovered.
    """
    if not primary_tag_keys:
        raise QueryBuildError(
            "refusing to render a primary tag probe with no keys to measure: "
            "the tenant emits none, so there is nothing to probe"
        )
    aggregations = [f"{_PROBE_TOTAL} = count()"]
    for index, key in enumerate(primary_tag_keys):
        quoted = _quoted_field(key)
        aggregations.append(f"{_probe_present(index)} = countIf(isNotNull({quoted}))")
        aggregations.append(f"{_probe_distinct(index)} = countDistinct({quoted})")
    integral = (
        _PROBE_TOTAL,
        *(_probe_present(index) for index in range(len(primary_tag_keys))),
        *(_probe_distinct(index) for index in range(len(primary_tag_keys))),
    )
    return Read(
        tuple(
            _piped(
                [
                    *_entry_spans(window, shape=shape, scoped_by=group),
                    "summarize " + ", ".join(aggregations),
                ]
            )
            for group in _groups_of(targets, named="the Target Set")
        ),
        integral_fields=integral,
    )


def primary_tag_probe_of(answer: DqlAnswer, primary_tag_keys: Sequence[str]) -> ProbeReading:
    """The probe's per-key figures, summed across the chunks the id list was asked in.

    `total` and `present` are counts, so they sum cleanly and the null gate is exact however many
    chunks it took. `distinct` cannot be unioned exactly across chunks, so it is summed as an upper
    bound - which only ever pushes a key toward key-only, never toward a `key:value` that could
    re-explode the harvest, and `090` decides the boundary on the actual enumerated values anyway
    (`180`, *Chunking note*).
    """
    total = sum(_probe_int(record, _PROBE_TOTAL) for record in answer.records)
    present = {
        key: sum(_probe_int(record, _probe_present(index)) for record in answer.records)
        for index, key in enumerate(primary_tag_keys)
    }
    distinct = {
        key: sum(_probe_int(record, _probe_distinct(index)) for record in answer.records)
        for index, key in enumerate(primary_tag_keys)
    }
    return ProbeReading(total, present, distinct)


def _probe_int(record: Mapping[str, Any], field_name: str) -> int:
    value = record.get(field_name)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def verification_span_read(
    window: QueryWindow,
    *,
    primary_tag: Tag,
    process_groups: Sequence[str] | None = None,
) -> Read:
    """What one replacement condition set selects, asked of the spans themselves.

    Built from the condition set and nothing else. No Target Set id, no deprecated tag and no
    technology may reach it: those are the output of evaluating the Deprecated Condition, and a
    read carrying them asks what the replacement does *inside the set the deprecated condition
    already picked* - a question with no "no" available.

    Scoped by the replacement's own entity side, which is the answer to the entity leg and never
    the Target Set. Where the set carries no entity-side condition the read is unbounded, which
    is accepted rather than worked around: naming every process group instead would constrain
    nothing and exceed the element cap.

    The tag is asked for the way the runtime asks it - a valued condition by equality against the
    resource attribute, a key-only one by the attribute being present at all.
    """
    scoped = (
        _groups_of(process_groups, named="the replacement's own entity side")
        if process_groups is not None
        else [None]
    )
    return Read(
        tuple(
            _piped(
                [
                    *_entry_spans(window, scoped_by=scoped_by),
                    _tag_condition(primary_tag),
                    "summarize span_count = count(), by: "
                    "{ dt.entity.process_group, dt.entity.service }",
                ]
            )
            for scoped_by in scoped
        ),
        integral_fields=("span_count",),
    )


def observed_capture_set_read(
    window: QueryWindow,
    *,
    attribute_name: str,
    shape: TargetShape,
    targets: Sequence[str],
) -> Read:
    """What one Request Attribute demonstrably captures on today, per service call.

    The field is named after the Request Attribute and quoted by the rule a Primary Tag key is
    quoted by, because a name is free text and most of what a tenant writes there needs it.

    It corroborates and never defines: the answer says where capture is happening today, which a
    Data Source can be in Scope for and still show nothing in, merely because the value was
    absent from those requests this window. So it is scoped to the Target Set rather than asked
    of the tenant, and refuses where there is nothing to scope it by.

    The values come back grouped rather than summed because the field is an **array**: one span
    can carry several captured values, and a caller comparing the group against a single value
    would be wrong before it started.
    """
    captured = _quoted_field(f"captured_attribute.{attribute_name}")
    return Read(
        tuple(
            _piped(
                [
                    *_entry_spans(window, shape=shape, scoped_by=group),
                    f"filter isNotNull({captured})",
                    "summarize span_count = count(), by: "
                    "{ dt.entity.process_group, dt.entity.service, " + captured + " }",
                ]
            )
            for group in _groups_of(targets, named="the Target Set")
        ),
        integral_fields=("span_count",),
    )


def _entry_spans(
    window: QueryWindow,
    *,
    shape: TargetShape = TargetShape.PROCESS_GROUP,
    scoped_by: str | None = None,
) -> list[str]:
    """The stages every entry-span read opens with, prefilter included.

    The prefilter is injected here rather than written by each builder, so a builder that omits
    it cannot be written: the two sides of a span-grain comparison are one population by
    construction and not by each caller remembering. `endpoint.name` is written to the entry
    point node, which is the node the runtime reads a Primary Tag from (`035`).
    """
    stages = [f"fetch spans, {window.timeframe}"]
    if scoped_by is not None:
        stages.append(f"filter in({shape.value}, {scoped_by})")
    stages.append("filter isNotNull(endpoint.name)")
    return stages


def _tag_condition(tag: Tag) -> str:
    """One Primary Tag candidate as the runtime evaluates it.

    A valued condition compares the raw resource attribute with `String.equals`, so it matches a
    single-valued tag and never an array-valued one; a key-only condition matches whenever the
    attribute is there at all, arrays included. The context is not asked about: the span side
    carries the bare key, and a context prefix changes the stored value without changing what is
    matched.
    """
    field = _quoted_field(tag.key)
    if tag.value is None:
        return f"filter isNotNull({field})"
    return f'filter {field} == "{tag.value}"'


def _quoted_field(key: str) -> str:
    """One discovered key as a field reference, which a `summarize ... by` cannot take raw.

    Anything outside `a-zA-Z0-9_.` has to be backtick-quoted, and the tenant really holds such a
    key, so this is not a hypothetical: a group by an unquoted `primary_tags.pri/ma/ry/` is a
    syntax error. Backslash and backtick are escaped because they are the two characters a
    backtick-quoted name cannot carry as itself.
    """
    escaped = key.replace("\\", "\\\\").replace("`", "\\`")
    return f"`{escaped}`"


def primary_tag_key_discovery() -> Read:
    """Which Primary Tag keys the tenant emits on spans at all, once for the whole run.

    Metadata rather than a span scan, and the one read carrying no window: `fieldsSnapshot` takes
    no timeframe, so this text renders the same whatever window a run was given and the cache
    answers every later ask of it.

    A prerequisite as much as a gate. A `summarize` cannot group by a wildcard, so the span read
    is built from the keys named here and refuses without them - which is what turns a tenant
    emitting none into a run that spends no span read at all.

    Case-sensitive, for the reason the runtime gives: it looks a Primary Tag key up by exact
    match, so a case variant names a field no condition could decide on. The filter is still a
    net rather than the decision - `primary_tag_keys_of` tests the prefix again on the way out.

    What it answers is a snapshot of the fields spans have carried, which is evidence that a key
    exists on the tenant and never that it occurs inside any window.
    """
    return Read(
        (
            _piped(
                [
                    "fieldsSnapshot spans",
                    f'filter matchesValue(field, "{PRIMARY_TAG_PREFIX}*", caseSensitive: true)',
                    "fields field",
                ]
            ),
        )
    )


def primary_tag_keys_of(answer: DqlAnswer) -> tuple[str, ...]:
    """The keys the discovery read named, in the order it named them.

    The prefix is checked here as well as asked for in the query, and case-sensitively in both
    places, for the reason the runtime gives: a key it cannot look up by exact match is not a
    Primary Tag, so naming one would put a field in the span read that can never decide anything.

    No keys is an ordinary answer. It gates every later span read off - there is nothing to group
    by and nothing to observe - and it is never an error of its own.
    """
    named = (str(record["field"]) for record in answer.records if "field" in record)
    return tuple(key for key in named if key.startswith(PRIMARY_TAG_PREFIX))
