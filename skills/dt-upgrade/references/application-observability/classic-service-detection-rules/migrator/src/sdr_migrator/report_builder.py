from __future__ import annotations

import collections
import copy
import html as html_lib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from .candidates import Candidate
from .conditions import (
    PRIMARY_TAGS_PREFIX,
    strip_deprecated_pg_tag_ops,
)
from .verifier import API_VALUE_CAP, Negation

if TYPE_CHECKING:
    from .orchestrator import RuleResult

def _esc(value: object) -> str:
    """Escape a value for interpolation into report markup. quote=True so
    values landing inside attributes are safe too."""
    return html_lib.escape(str(value), quote=True)


_KIND_TO_OP_TYPE = {
    "exact": "STRING_EQUALS",
    "prefix": "STARTS_WITH",
    "suffix": "ENDS_WITH",
    "contains": "STRING_CONTAINS",
}


def _compare_operation(kind: str, values: Sequence, negate: bool) -> dict | None:
    """Build one Config v1 compareOperation. Returns None if values is empty."""
    op = {
        "type": _KIND_TO_OP_TYPE[kind],
        "values": list(values),
        "negate": negate,
        "ignoreCase": False,
    }
    if len(op["values"]) > API_VALUE_CAP:
        # The verifier caps demotions at API_VALUE_CAP; reaching here means
        # an over-cap candidate slipped through. Fail loudly rather than emit a body
        # the Config v1 API rejects (@Size(max=10)).
        raise ValueError(
            f"compareOperation for {op['type']} has {len(op['values'])} values, "
            f"exceeding the Config v1 cap of {API_VALUE_CAP}"
        )
    return op


def _candidate_condition(candidate: Candidate) -> dict | None:
    if candidate.attribute_type == "PG_TAG":
        return _primary_tag_condition(candidate)
    op = _compare_operation(candidate.kind, candidate.values, negate=False)
    if op is None:
        return None
    return {"attributeType": candidate.attribute_type, "compareOperations": [op]}


def _primary_tag_condition(candidate: Candidate) -> dict:
    """Emit a scalar primary-tag candidate as a structured Config v1 TAG condition
    one ``TagDto`` per value, ORed within a single compareOperation.

    Fail loudly on any PG_TAG candidate shape this function doesn't handle — a
    non-``primary_tags.`` key, a substring kind, or an over-cap value set — rather
    than fall through to a scalar STRING_EQUALS body the API would reject. This
    matters because array-valued tags are discarded at scoring, and a loud failure
    here is far safer than a malformed POST if one ever slips through.
    """
    if candidate.kind != "exact" or not candidate.grail_key.startswith(PRIMARY_TAGS_PREFIX):
        raise ValueError(
            f"unrecognised PG_TAG candidate (kind={candidate.kind!r}, "
            f"grail_key={candidate.grail_key!r}); cannot emit a structured TAG condition"
        )
    if len(candidate.values) > API_VALUE_CAP:
        raise ValueError(
            f"PG_TAG candidate has {len(candidate.values)} values, "
            f"exceeding the Config v1 cap of {API_VALUE_CAP}"
        )
    tags = [
        {"context": "CONTEXTLESS", "key": candidate.grail_key, "value": v}
        for v in candidate.values
    ]
    return {
        "attributeType": "PG_TAG",
        "compareOperations": [{"type": "TAG", "compareKeyOnly": False, "tags": tags}],
    }


def build_replacement_body(
    original_rule: dict,
    candidates: Sequence[Candidate],
    negations: Sequence[Negation] = (),
) -> dict:
    """Build a Config v1 POST-ready replacement rule body.

    The result is a valid ``POST /service/detectionRules/{type}`` create payload,
    not a mirror of the source rule: ``id`` (server-assigned), ``metadata``
    (readOnly) and ``order`` (ignored on POST) are stripped, and ``enabled`` is
    unconditionally forced to ``False`` so the artifact is always a disabled
    clone — a human must review and enable it deliberately. The deprecated
    managementZones scope and non-primary PG_TAG conditions are removed, then one
    AND'd condition per verified candidate is appended (the positive conjunction,
    which already includes any escalated reserve candidate), followed by one
    AND'd condition per negation (dropping only the over-selected excess).
    Everything else — including ``name``, ``type``, ``description`` and the
    FWS-only fields — is preserved verbatim.
    """
    body = copy.deepcopy(original_rule)
    body.pop("managementZones", None)
    body.pop("id", None)
    body.pop("metadata", None)
    body.pop("order", None)
    body["enabled"] = False
    body["conditions"] = [
        stripped
        for c in body.get("conditions", [])
        if (stripped := strip_deprecated_pg_tag_ops(c)) is not None
    ]

    candidate_conditions = [
        cond
        for c in candidates
        if (cond := _candidate_condition(c)) is not None
    ]
    negation_conditions = []
    for n in negations:
        op = _compare_operation("exact", [n.value], negate=True)
        if op is None:
            continue
        negation_conditions.append(
            {"attributeType": n.attribute_type, "compareOperations": [op]}
        )
    body["conditions"] = body["conditions"] + candidate_conditions + negation_conditions
    return body


def emit_results(
    results: list[RuleResult],
    output_dir: Path,
    unknown_rule_ids: list[str] | None = None,
    cache_stats: Any = None,
) -> None:
    """Write per-rule JSONs, summary.json, and an HTML report to output_dir."""
    report_dir = output_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    counts: collections.Counter[str] = collections.Counter()
    for r in results:
        counts[r.verdict] += 1
        if r.verdict == "migrated" and r.replacement_body is not None:
            (report_dir / f"{r.rule_id}.json").write_text(
                json.dumps(r.replacement_body, indent=2)
            )

    summary: dict[str, object] = dict(counts)
    summary["unknown_rule_ids"] = unknown_rule_ids or []
    if cache_stats is not None:
        summary["cache"] = {
            "total": cache_stats.total,
            "hits": cache_stats.hits,
            "misses": cache_stats.misses,
        }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    (report_dir / "report.html").write_text(_build_html(results, cache_stats))


def find_duplicate_groups(results: Sequence[RuleResult]) -> list[list[str]]:
    """Group rules that are configured identically — same rule_type, conditions
    (order-insensitive), and management zones — so a user can spot unnecessary
    duplicate service-detection rules to consolidate.

    Such rules produce byte-identical Grail queries, which is why the second one
    processed shows all cache hits and zero misses; this surfaces the underlying
    config duplication directly. Only rules that were read (original_conditions is
    not None) and carry a non-trivial scope are considered; a rule with no
    conditions and no management zones matches everything and is not a meaningful
    duplicate. Returns groups (size > 1) of rule ids, each group sorted, groups
    sorted for deterministic output.
    """
    by_signature: dict[tuple, list[str]] = {}
    for r in results:
        if r.original_conditions is None:
            continue
        if not r.original_conditions and not r.management_zones:
            continue
        by_signature.setdefault(_duplicate_signature(r), []).append(r.rule_id)
    return sorted(sorted(ids) for ids in by_signature.values() if len(ids) > 1)


def _duplicate_signature(r: RuleResult) -> tuple:
    conditions = json.dumps(_canonical(r.original_conditions or []), sort_keys=True)
    zones = tuple(sorted(r.management_zones or []))
    return (r.rule_type, conditions, zones)


def _canonical(obj: Any) -> Any:
    """Order-insensitive canonical form: sort dict keys and every list (by JSON
    repr). Matches the migrator's value-order-insensitive query canonicalization
    so rules differing only in condition/value ordering — which produce
    identical queries — share a signature."""
    if isinstance(obj, dict):
        return {k: _canonical(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return sorted((_canonical(x) for x in obj), key=lambda v: json.dumps(v, sort_keys=True))
    return obj


def _labelled_rule(rule_id: str, name_by_id: dict[str, str | None]) -> str:
    """Render a rule as ``name (id)`` for readability, falling back to the bare id
    when the rule has no name."""
    name = name_by_id.get(rule_id)
    return f"{name} ({rule_id})" if name else rule_id


def _duplicates_section(groups: list[list[str]], name_by_id: dict[str, str | None]) -> str:
    if not groups:
        return ""
    items = "".join(
        "<li>" + ", ".join(_esc(_labelled_rule(rid, name_by_id)) for rid in g) + "</li>"
        for g in groups
    )
    return (
        f"<section><h2>Duplicate rule groups ({len(groups)})</h2>"
        "<p>Rules configured identically (same type, conditions, and management "
        "zones). They produce identical queries — candidates for consolidation.</p>"
        f"<ul>{items}</ul></section>\n"
    )


_FULLY_RESOLVED = "Fully Resolved"
_APPROXIMATE = "Approximate — review before applying"
_NOT_COVERABLE = "Not Coverable — manual migration required"
_NOT_OBSERVED = "Not observed in live traffic"
_FAILURES = "Processing error — contact Dynatrace Support"
_SKIPPED = "Skipped / out of scope"

_BUCKET_ORDER = [
    _FULLY_RESOLVED,
    _APPROXIMATE,
    _NOT_COVERABLE,
    _NOT_OBSERVED,
    _FAILURES,
    _SKIPPED,
]

_BUCKET_DESCRIPTION = {
    _FULLY_RESOLVED: (
        "Verification returned an exact match. Some rules needed refinement "
        "(negation, substring demotion, suboptimal escalation, or window "
        "retries) to get there — the per-card refinement history records the "
        "detail — but the end result is exact, not approximate."
    ),
    _APPROXIMATE: (
        "Verification accepted an under-selecting candidate after a retry "
        "The replacement is not guaranteed to match everything "
        "the original rule matched — review before applying."
    ),
    _NOT_COVERABLE: (
        "Either traffic was observed but no safe replacement could be "
        "reproduced (over-selection, or no viable span candidates), or the "
        "rule carries a condition that cannot be expressed against spans at "
        "all. Manual migration is required; see the per-rule reason."
    ),
    _NOT_OBSERVED: (
        "Nothing failed — there was nothing to measure. Either the rule's "
        "scope resolved to zero process groups (dead configuration), or "
        "process groups exist but no spans matched in the window. The "
        "endpoint may be dormant or decommissioned; consider whether the "
        "rule is still needed, or widen --window if traffic is known to "
        "have flowed at another time."
    ),
    _FAILURES: (
        "Processing crashed while evaluating this rule. Any rule listed "
        "here reflects a genuine error, not a traffic or coverage gap — "
        "contact Dynatrace Support with the reason shown on the card."
    ),
    _SKIPPED: "Rules intentionally excluded from migration (disabled, or not deprecated).",
}


def _bucket(r: RuleResult) -> str:
    """Map a rule result into its canonical report bucket.

    Ordering matters: `untranslatable` must be checked before the no-data
    branch, since its target_set is None (no query was ever issued) but it
    must never be reported as "not observed in live traffic" — that would
    falsely imply we looked for traffic and didn't find any.
    """
    if r.verdict == "migrated":
        return _APPROXIMATE if r.best_effort else _FULLY_RESOLVED
    if r.verdict in ("skipped_disabled", "skipped_not_deprecated"):
        return _SKIPPED
    if r.verdict == "error":
        return _FAILURES
    if r.verdict == "untranslatable":
        return _NOT_COVERABLE
    if r.verdict == "no_replacement" and not r.target_set:
        # empty target set / empty process-group set — nothing was observed.
        return _NOT_OBSERVED
    # no_replacement with data (over-selection, or no span candidates).
    return _NOT_COVERABLE


def _bucket_anchor(bucket: str) -> str:
    return "bucket-" + "".join(c.lower() if c.isalnum() else "-" for c in bucket).strip("-")


def _summary_table(by_bucket: dict[str, list[RuleResult]]) -> str:
    rows = "".join(
        f"<tr><td><a href='#{_bucket_anchor(b)}'>{b}</a></td><td>{len(by_bucket.get(b, []))}</td></tr>"
        for b in _BUCKET_ORDER
        if by_bucket.get(b)
    )
    return f"<table border='1' cellpadding='4'><tr><th>Section</th><th>Count</th></tr>{rows}</table>"


def _build_html(results: list[RuleResult], cache_stats: Any = None) -> str:
    by_bucket: dict[str, list[RuleResult]] = {}
    for r in results:
        by_bucket.setdefault(_bucket(r), []).append(r)

    dup_groups = find_duplicate_groups(results)
    dup_map = {rid: [o for o in g if o != rid] for g in dup_groups for rid in g}
    name_by_id = {r.rule_id: r.rule_name for r in results}

    summary_table = _summary_table(by_bucket) if results else ""

    sections = ""
    for bucket in _BUCKET_ORDER:
        group = by_bucket.get(bucket, [])
        if not group:
            continue
        cards = "".join(_rule_card(r, dup_map, name_by_id) for r in group)
        sections += (
            f"<section id='{_bucket_anchor(bucket)}'><h2>{bucket} ({len(group)})</h2>"
            f"<p>{_BUCKET_DESCRIPTION[bucket]}</p>{cards}</section>\n"
        )

    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>SDR Migration Report</title>"
        "<style>body{font-family:monospace;padding:1em}"
        "details{border:1px solid #ccc;margin:.5em 0;padding:.5em}"
        "summary{cursor:pointer;font-weight:bold}"
        "pre{white-space:pre-wrap;word-break:break-all;background:#f5f5f5;padding:.5em}"
        "h2{border-bottom:2px solid #333}</style>"
        "</head><body>"
        "<h1>SDR Migration Report</h1>"
        f"{summary_table}"
        f"{_duplicates_section(dup_groups, name_by_id)}"
        f"{sections}"
        f"{_cache_section(cache_stats)}"
        "</body></html>"
    )


def _cache_section(cache_stats: Any) -> str:
    """Run-level cache statistics, rendered at the end of the report."""
    if cache_stats is None:
        return ""
    total = cache_stats.total
    hits = cache_stats.hits
    hit_rate = f"{(hits / total * 100):.0f}%" if total else "—"
    rows = [
        ("Total queries", total),
        ("Cache hits", hits),
        ("Cache misses", cache_stats.misses),
        ("Hit rate", hit_rate),
    ]
    table = "<table border='1' cellpadding='4'>" + "".join(
        f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in rows
    ) + "</table>"
    per_query = _per_query_cache_table(getattr(cache_stats, "query_events", None))
    return f"<section><h2>Cache statistics</h2>{table}{per_query}</section>\n"


def _per_query_cache_table(query_events: Any) -> str:
    """Group the live per-query event stream by distinct executed query and render
    each with its miss/hit counts and verbatim DQL.

    The query text is HTML-escaped for display; the source ``query_events``
    values stay byte-identical, so a copy/paste out of ``cache_stats`` (not
    out of the rendered page) still round-trips unchanged. Rows are ordered
    misses-first, then by total volume, so the queries a reviewer most wants
    to reproduce lead.
    """
    if not query_events:
        return ""
    misses: collections.Counter[str] = collections.Counter()
    hits: collections.Counter[str] = collections.Counter()
    order: list[str] = []
    for query, is_hit in query_events:
        if query not in misses and query not in hits:
            order.append(query)
        (hits if is_hit else misses)[query] += 1

    order.sort(key=lambda q: (misses[q] == 0, -(misses[q] + hits[q])))

    header = (
        "<tr><th>Misses</th><th>Hits</th><th>Query</th></tr>"
    )
    body = "".join(
        f"<tr><td>{misses[q]}</td><td>{hits[q]}</td><td><pre>{_esc(q)}</pre></td></tr>"
        for q in order
    )
    table = f"<table border='1' cellpadding='4'>{header}{body}</table>"
    return f"<h3>Per-query detail ({len(order)} distinct)</h3>{table}"


def _candidate_line(c: Candidate) -> str:
    badge = f" {{{_KIND_TO_OP_TYPE[c.kind]}}}" if c.kind != "exact" else ""
    return f"{c.attribute_type} ({c.grail_key}): {', '.join(c.values)} [{c.quality}]{badge}"


def _rule_card(
    r: RuleResult,
    dup_map: dict[str, list[str]] | None = None,
    name_by_id: dict[str, str | None] | None = None,
) -> str:
    rows = [
        ("Rule ID", _esc(r.rule_id)),
        ("Rule Name", _esc(r.rule_name) if r.rule_name else "—"),
        ("Rule Type", _esc(r.rule_type)),
        ("Verdict", _esc(r.verdict)),
        ("Window", _esc(r.window) if r.window else "—"),
        ("PG IDs", ", ".join(_esc(p) for p in r.pg_ids) if r.pg_ids else "—"),
        ("Reasons", "; ".join(_esc(reason) for reason in r.reasons) if r.reasons else "—"),
    ]

    duplicates = (dup_map or {}).get(r.rule_id)
    if duplicates:
        names = name_by_id or {}
        rows.append((
            "Duplicate of",
            ", ".join(_esc(_labelled_rule(d, names)) for d in duplicates),
        ))

    if r.target_set is not None:
        ts_items = "<br>".join(
            _esc(f"{pg} / {ep}") for pg, ep in sorted(r.target_set)
        )
        rows.append(("Target Set", ts_items or "∅"))

    if r.candidates:
        cand_lines = "<br>".join(_esc(_candidate_line(c)) for c in r.candidates)
        rows.append(("Candidates", cand_lines))

    if r.discarded_attributes:
        disc_lines = "<br>".join(
            _esc(f"{d.attribute_type} ({d.grail_key}): {d.reason}, distinct={d.distinct_count}")
            for d in r.discarded_attributes
        )
        rows.append(("Discarded Attributes", disc_lines))

    if r.entity_candidates:
        ent_lines = "<br>".join(
            _esc(f"{c.attribute_type}: {', '.join(c.values)}") for c in r.entity_candidates
        )
        rows.append(("Entity Candidates", ent_lines))

    if r.chosen_candidates:
        chosen_lines = "<br>".join(_esc(_candidate_line(c)) for c in r.chosen_candidates)
        rows.append(("Chosen Candidates", chosen_lines))

    rows.extend(_refinement_rows(r))

    if r.surviving_fragments is not None:
        surviving = (
            "<br>".join(_esc(f) for f in r.surviving_fragments)
            if r.surviving_fragments else "none"
        )
        rows.append(("Surviving Conditions", surviving))

    if r.cache_hits or r.cache_misses:
        rows.append(("Cache (hits/misses)", f"{r.cache_hits} / {r.cache_misses}"))

    table = "<table border='1' cellpadding='4'>" + "".join(
        f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in rows
    ) + "</table>"

    original_html = _original_conditions_block(r)

    body_html = ""
    if r.replacement_body is not None:
        body_html = (
            "<details><summary>Replacement Body</summary>"
            f"<pre>{_esc(json.dumps(r.replacement_body, indent=2))}</pre></details>"
        )

    return (
        f"<details open><summary>{_esc(r.rule_id)} — {_esc(r.verdict)}</summary>"
        f"{table}{original_html}{body_html}</details>\n"
    )


def _refinement_rows(r: RuleResult) -> list[tuple[str, str]]:
    """Best-effort refinement diagnostics (demotion, escalation, negation,
    under-selection, window retries) as report rows."""
    rows: list[tuple[str, str]] = []
    if r.demoted_from:
        demoted_lines = "<br>".join(
            _esc(f"demoted from {_candidate_line(c)}") for c in r.demoted_from
        )
        rows.append(("Substring Demotion", demoted_lines))
    if r.escalated_candidates:
        esc_lines = "<br>".join(_esc(_candidate_line(c)) for c in r.escalated_candidates)
        rows.append(("Escalated Candidates", esc_lines))
    if r.negations:
        neg_lines = "<br>".join(
            _esc(f"not {n.attribute_type} ({n.grail_key}) == {n.value}") for n in r.negations
        )
        rows.append(("Resolution", "best-effort (negation-refined)"))
        rows.append(("Negations Applied", neg_lines))
    if r.best_effort:
        rows.append(("Resolution", "best-effort (under-selection)"))
    if r.span_retries or r.under_select_retries:
        rows.append(("Retries", f"span: {r.span_retries}, under-select: {r.under_select_retries}"))
    return rows


def _original_conditions_block(r: RuleResult) -> str:
    """The rule's classic conditions + management zones, as they were before
    translation. Present for every rule that was read."""
    if r.original_conditions is None:
        return ""
    conds = _esc(json.dumps(r.original_conditions, indent=2))
    zones = _esc(", ".join(r.management_zones) if r.management_zones else "none")
    return (
        "<details><summary>Original Conditions</summary>"
        f"<pre>{conds}</pre>"
        f"<div>Management Zones: {zones}</div>"
        "</details>"
    )
