"""HTML aggregate report generator.

Reads all ``report/<rule_id>.json`` artifacts produced by Step 5 and writes
a self-contained ``report/report.html`` with:

- Summary table (rule name, status, verdict, condition counts)
- Per-rule detail sections (deprecated conditions replaced, surviving
  conditions carried forward, proposed replacement conditions, discarded
  attributes, verification history)

No external dependencies — uses only inline CSS/JS.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Bucketing
# ---------------------------------------------------------------------------

def _bucket(r: dict[str, Any]) -> str:
    """Assign a display bucket to a report entry."""
    vs = r.get("verdict_status", "")
    ms = r.get("migration_status", "")

    if vs in ("exact_match", "exact_match_after_under_select_retry"):
        return "resolved"
    if ms.startswith("verification_error") or ms.startswith("report_error"):
        return "failure"
    # Checked before the not_run/no_data rule: an unmigratable rule has no verdict
    # because no query was issued, not because no traffic matched it.
    if ms == "unmigratable_conditions":
        return "not_coverable"
    if vs == "not_run" or ms in ("no_traffic_data", "verification_not_run"):
        return "no_data"
    return "not_coverable"


_BUCKET_LABEL = {
    "resolved":      "Replacement found",
    "not_coverable": "No safe replacement — manual migration required",
    "no_data":       "Rule not observed in live traffic",
    "failure":       "Processing error — please contact Dynatrace Support",
}

_BUCKET_ORDER = ["resolved", "not_coverable", "no_data", "failure"]

_BUCKET_ANCHOR = {
    "resolved":      "section-resolved",
    "not_coverable": "section-not-coverable",
    "no_data":       "section-no-data",
    "failure":       "section-failure",
}

_STATUS_BADGE = {
    "resolved":      "badge-green",
    "not_coverable": "badge-yellow",
    "no_data":       "badge-grey",
    "failure":       "badge-red",
}

_BUCKET_DESCRIPTION = {
    "resolved": (
        "The deprecated condition was successfully translated to an equivalent using "
        "supported attributes. The proposed rule is ready to apply. "
        "No further manual work is required."
    ),
    "not_coverable": (
        "These rules need manual migration, for one of two reasons. Either matching traffic "
        "was found but every candidate replacement attribute matched a broader set of "
        "services than the original deprecated condition — the original was acting as a "
        "very precise filter that cannot be reproduced from the available span/entity "
        "attributes — or the rule carries a condition the migrator cannot reproduce at all, "
        "in which case the reason is stated on the condition below."
    ),
    "no_data": (
        "No trace data matching this rule&#39;s conditions was found across multiple time "
        "windows spanning the last ~20 hours. This usually means the matched endpoint is "
        "dormant or decommissioned — consider whether this rule is still needed at all. "
        "If the service does receive traffic, use <code>--query-timeframe</code> to "
        "target a specific period when traffic is known to have been flowing."
    ),
    "failure": (
        "An unexpected error occurred while analysing this rule. The other rules were "
        "not affected. Please report the rule ID and the error details to "
        "Dynatrace Support."
    ),
}


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

def _e(s: Any) -> str:
    """HTML-escape a value."""
    return html.escape(str(s) if s is not None else "")


def _badge(text: str, cls: str) -> str:
    return f'<span class="badge {cls}">{_e(text)}</span>'


def _render_note(note: Any) -> str:
    """Render a single note entry — handles both strings and dicts."""
    if isinstance(note, str):
        return _e(note)
    if isinstance(note, dict):
        parts = []
        if "iteration" in note:
            parts.append(f"iter {note['iteration']}")
        if "outcome" in note:
            parts.append(f"outcome: <strong>{_e(note['outcome'])}</strong>")
        if "window_from" in note:
            parts.append(f"window: {_e(note['window_from'])} → {_e(note.get('window_to', 'now()'))}")
        if "s_cand_size" in note or "e_cand_size" in note:
            parts.append(f"span_cands={note.get('s_cand_size', '?')} entity_cands={note.get('e_cand_size', '?')}")
        if "negations_count" in note and note["negations_count"]:
            parts.append(f"negations={note['negations_count']}")
        return " | ".join(parts) if parts else _e(str(note))
    return _e(str(note))


def _condition_table(conditions: list[dict[str, Any]], kind: str) -> str:
    if not conditions:
        return f"<p class='muted'>No {kind} conditions.</p>"
    rows = ""
    for c in conditions:
        attr = c.get("attribute") or c.get("api_attribute") or "?"
        frag = c.get("dql_fragment") or c.get("dql") or ""
        negate = "✓" if c.get("negate") else ""
        rows += f"<tr><td><code>{_e(attr)}</code></td><td><code>{_e(frag)}</code></td><td>{negate}</td></tr>"
    return (
        "<table>"
        "<thead><tr><th>Attribute</th><th>DQL fragment</th><th>Negated</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


def _candidates_table(candidates: list[dict[str, Any]], muted: bool = False) -> str:
    if not candidates:
        return "<p class='muted'>None.</p>"
    rows = ""
    for c in candidates:
        key = c.get("dql_key") or "?"
        side = c.get("side") or "?"
        kind = c.get("kind") or "?"
        values = c.get("values") or []
        vals_str = ", ".join(_e(str(v)) for v in values[:5])
        if len(values) > 5:
            vals_str += f" … +{len(values) - 5}"
        rows += (
            f"<tr><td><code>{_e(key)}</code></td>"
            f"<td>{_e(side)}</td>"
            f"<td>{_e(kind)}</td>"
            f"<td>{_e(vals_str)}</td></tr>"
        )
    cls = " style='opacity:0.65'" if muted else ""
    return (
        f"<table{cls}>"
        "<thead><tr><th>DQL key</th><th>Side</th><th>Kind</th><th>Values</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


def _discarded_table(discarded: list[dict[str, Any]]) -> str:
    if not discarded:
        return "<p class='muted'>None discarded.</p>"
    rows = ""
    for d in discarded:
        key = d.get("dql_key") or "?"
        reason = d.get("reason") or "?"
        count = d.get("distinct_count", "")
        rows += f"<tr><td><code>{_e(key)}</code></td><td>{_e(reason)}</td><td>{_e(count)}</td></tr>"
    return (
        "<table>"
        "<thead><tr><th>DQL key</th><th>Reason</th><th>Distinct count</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


def _replacement_body_block(body: dict[str, Any] | None) -> str:
    if body is None:
        return "<p class='muted'>No replacement body (raw rule not available or no replacement found).</p>"
    escaped = _e(json.dumps(body, indent=2, ensure_ascii=False))
    return f"<pre class='code-block'>{escaped}</pre>"


def _rule_section(r: dict[str, Any], bucket: str) -> str:
    rule_id = r["rule_id"]
    name = r.get("naming_pattern") or "<unnamed>"
    ms = r.get("migration_status", "unknown")
    vs = r.get("verdict_status", "unknown")
    neg = r.get("verdict_negations", 0) or 0
    dem = r.get("verdict_demotions", 0) or 0
    iters = r.get("verdict_iterations") or "-"
    enabled = r.get("enabled", True)

    badge_cls = _STATUS_BADGE.get(bucket, "badge-grey")

    deprecated = r.get("deprecated_conditions", [])
    surviving = r.get("surviving_conditions", [])
    proposed = r.get("proposed_conditions", [])
    discarded = r.get("discarded_attributes", [])
    good_cands = r.get("good_candidates", [])
    suboptimal_cands = r.get("suboptimal_candidates", [])
    notes = r.get("notes", [])
    replacement = r.get("replacement_rule_body")

    notes_html = ""
    if notes:
        items = "".join(f"<li>{_render_note(n)}</li>" for n in notes)
        notes_html = f"<ul class='notes'>{items}</ul>"
    else:
        notes_html = "<p class='muted'>No notes.</p>"

    enabled_label = "" if enabled else " <span class='badge badge-grey'>disabled</span>"

    blockers = r.get("unmigratable_reasons") or []
    blockers_html = ""
    if blockers:
        items = "".join(f"<li>{_e(b)}</li>" for b in blockers)
        blockers_html = (
            "<h4>Why this rule could not be migrated automatically</h4>"
            f"<ul class='notes'>{items}</ul>"
        )

    if bucket == "no_data":
        detail_html = ""
    else:
        detail_html = f"""
    {blockers_html}
    <h4>Proposed replacement conditions ({len(proposed)})</h4>
    {_condition_table(proposed, "proposed")}

    <h4>Good candidates ({len(good_cands)})</h4>
    {_candidates_table(good_cands)}

    <h4>Suboptimal candidates — fallback pool ({len(suboptimal_cands)})</h4>
    {_candidates_table(suboptimal_cands, muted=True)}

    <h4>Discarded attributes</h4>
    {_discarded_table(discarded)}

    <h4>Verification history</h4>
    {notes_html}

    <h4>Replacement rule body (Config v1 JSON)</h4>
    {_replacement_body_block(replacement)}"""

    return f"""
<details class="rule-section">
  <summary>
    {_badge(ms, badge_cls)}
    <strong>{_e(name)}</strong>{enabled_label}
    <span class="rule-id">{_e(rule_id)}</span>
    <span class="meta">verdict: {_e(vs)} | iter={_e(iters)} | neg={neg} | dem={dem}</span>
  </summary>
  <div class="rule-body">
    <h4>Deprecated conditions replaced ({len(deprecated)})</h4>
    {_condition_table(deprecated, "deprecated")}

    <h4>Surviving conditions carried forward ({len(surviving)})</h4>
    {_condition_table(surviving, "surviving")}
{detail_html}
  </div>
</details>
"""


# ---------------------------------------------------------------------------
# CSS + page template
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       margin: 0; padding: 24px; background: #f8f9fa; color: #212529; }
h1 { font-size: 1.6rem; margin-bottom: 4px; }
h2 { font-size: 1.2rem; margin: 32px 0 8px; border-bottom: 2px solid #dee2e6; padding-bottom: 4px; }
h3 { font-size: 1rem; margin: 24px 0 4px; }
h4 { font-size: 0.85rem; margin: 16px 0 4px; color: #495057; text-transform: uppercase;
     letter-spacing: 0.05em; }
p.muted { color: #6c757d; font-size: 0.85rem; margin: 0; }
code { font-family: 'SFMono-Regular', Consolas, monospace; font-size: 0.82rem;
       background: #e9ecef; padding: 1px 4px; border-radius: 3px; }
pre.code-block { background: #1e1e2e; color: #cdd6f4; padding: 16px;
                 border-radius: 6px; overflow-x: auto; font-size: 0.78rem;
                 white-space: pre; line-height: 1.5; margin: 8px 0; }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; margin: 4px 0 12px; }
th { background: #e9ecef; text-align: left; padding: 6px 8px;
     font-weight: 600; font-size: 0.75rem; text-transform: uppercase; }
td { padding: 5px 8px; border-bottom: 1px solid #dee2e6; vertical-align: top; }
tr:last-child td { border-bottom: none; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px;
         font-size: 0.72rem; font-weight: 600; margin-right: 6px; }
.badge-green { background: #d1fae5; color: #065f46; }
.badge-yellow { background: #fef9c3; color: #854d0e; }
.badge-red { background: #fee2e2; color: #991b1b; }
.badge-grey { background: #f1f5f9; color: #475569; }
details.rule-section { background: #fff; border: 1px solid #dee2e6; border-radius: 8px;
                        margin: 8px 0; overflow: hidden; }
details.rule-section > summary { padding: 12px 16px; cursor: pointer;
                                  display: flex; align-items: center; gap: 8px;
                                  flex-wrap: wrap; user-select: none; }
details.rule-section > summary:hover { background: #f8f9fa; }
.rule-id { color: #6c757d; font-size: 0.75rem; font-family: monospace; }
.meta { color: #6c757d; font-size: 0.75rem; margin-left: auto; }
.rule-body { padding: 0 16px 16px; border-top: 1px solid #dee2e6; }
ul.notes { margin: 4px 0; padding-left: 20px; }
ul.notes li { font-size: 0.82rem; margin: 2px 0; font-family: monospace; color: #374151; }
p.bucket-desc { color: #374151; font-size: 0.85rem; margin: 0 0 12px;
                padding: 10px 14px; background: #f1f5f9; border-radius: 6px;
                border-left: 3px solid #94a3b8; }
.summary-table { background: #fff; border: 1px solid #dee2e6; border-radius: 8px;
                 margin: 16px 0; overflow: hidden; }
.summary-table table { margin: 0; }
.summary-table th, .summary-table td { padding: 8px 12px; }
"""


def _skipped_rules_section(report_dir: Path) -> str:
    """Read skipped_rules from summary.json and return a rendered HTML section."""
    summary_path = report_dir / "summary.json"
    try:
        summary = json.loads(summary_path.read_text())
    except (json.JSONDecodeError, OSError):
        return ""
    skipped: list[dict[str, Any]] = summary.get("skipped_rules", [])
    if not skipped:
        return ""

    active = [r for r in skipped if r.get("skip_reason") != "disabled"]
    disabled = [r for r in skipped if r.get("skip_reason") == "disabled"]
    ordered = active + disabled

    rows = ""
    for r in ordered:
        name = r.get("naming_pattern") or "<unnamed>"
        rid = r.get("id", "")
        is_disabled = r.get("skip_reason") == "disabled"
        badge = " <span class='badge badge-grey'>disabled</span>" if is_disabled else ""
        rows += f"<tr><td><code>{_e(rid)}</code></td><td>{_e(name)}{badge}</td></tr>"

    return f"""
<h2>Untouched rules ({len(skipped)})</h2>
<div class="summary-table">
  <table>
    <thead><tr><th>Rule ID</th><th>Naming pattern</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
"""


def generate_html(report_dir: Path) -> str:
    """Read all ``<rule_id>.json`` in *report_dir* and build a self-contained HTML string."""
    reports: list[dict[str, Any]] = []
    for p in sorted(report_dir.glob("*.json")):
        if p.stem == "summary":
            continue
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        # Skip non-rule artifacts (e.g. apply_log.json written by ``apply``).
        if not isinstance(data, dict) or "rule_id" not in data:
            continue
        reports.append(data)

    bucketed: dict[str, list[dict]] = {b: [] for b in _BUCKET_ORDER}
    for r in reports:
        bucketed[_bucket(r)].append(r)

    counts = {b: len(v) for b, v in bucketed.items()}

    # Summary table — one row per non-empty bucket with a link to its section.
    summary_rows = ""
    for b in _BUCKET_ORDER:
        if counts[b] == 0:
            continue
        anchor = _BUCKET_ANCHOR[b]
        summary_rows += (
            f'<tr><td><a href="#{anchor}">{_BUCKET_LABEL[b]}</a></td>'
            f"<td><strong>{counts[b]}</strong></td></tr>"
        )
    summary_rows += (
        f"<tr style='border-top:2px solid #dee2e6'>"
        f"<td><strong>Total</strong></td><td><strong>{len(reports)}</strong></td></tr>"
    )

    summary_html = f"""
<div class="summary-table">
  <table>
    <thead><tr><th>Category</th><th>Count</th></tr></thead>
    <tbody>{summary_rows}</tbody>
  </table>
</div>
"""

    # Per-bucket sections
    sections_html = ""
    for b in _BUCKET_ORDER:
        rules = bucketed[b]
        if not rules:
            continue
        desc = _BUCKET_DESCRIPTION.get(b, "")
        desc_html = f"<p class='bucket-desc'>{desc}</p>\n" if desc else ""
        rule_items = "".join(_rule_section(r, b) for r in rules)
        section_id = _BUCKET_ANCHOR[b]
        sections_html += f'<h2 id="{section_id}">{_BUCKET_LABEL[b]} ({len(rules)})</h2>\n{desc_html}{rule_items}\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Global Request Naming — Migration Report</title>
  <style>{_CSS}</style>
</head>
<body>
  <h1>Global Request Naming — Migration Report</h1>
  <p style="color:#6c757d;font-size:0.85rem">
    {len(reports)} rule(s) processed &nbsp;·&nbsp;
    {counts['resolved']} replacement found &nbsp;·&nbsp;
    {counts['not_coverable']} no safe replacement &nbsp;·&nbsp;
    {counts['no_data']} no traffic data &nbsp;·&nbsp;
    {counts['failure']} errors
  </p>
  {summary_html}
  {sections_html}
  {_skipped_rules_section(report_dir)}
</body>
</html>
"""


def write_html_report(report_dir: Path) -> Path:
    """Generate and write ``report/report.html``. Returns the output path."""
    content = generate_html(report_dir)
    out = report_dir / "report.html"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(out)
    return out


__all__ = ["generate_html", "write_html_report"]
