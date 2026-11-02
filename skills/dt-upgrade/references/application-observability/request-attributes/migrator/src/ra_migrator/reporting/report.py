"""The Report: the one output a customer is meant to read.

Self-contained - one HTML file, its style inline, no network access and no local asset - so it can be
shared without the tool. It carries the per-Data-Source story off the verdicts a run assigned, never
re-deriving one: which Data Sources were covered and on what grounds, which were Neutralised and
separately why, and which the run could not measure. The presentation is modelled on the dev report
generator; the verdicts, reasons and vocabulary are this package's own.
"""

from __future__ import annotations

import html
import operator
import re
from collections.abc import Sequence

from ..attributes.classification import AttributeClassification, DataSourceClassification
from ..reconstruction.verdict import DataSourceVerdict, RequestAttributeVerdict
from ..run_result import RunResult
from .outcomes import CoveredReason, DataSourceNote, DataSourceOutcome, RequestAttributeOutcome

# The action each Request-Attribute roll-up implies, so a reader is never left to infer it. Deletion
# and rework must read differently: a selects-nothing Request Attribute has nothing to cover and is
# deleted, a not-coverable one has something to cover but nothing coverable and is reworked.
_ATTRIBUTE_ACTION = {
    RequestAttributeOutcome.COVERED: "Deploy the Artifact.",
    RequestAttributeOutcome.PARTIALLY_COVERED: (
        "Deploy the Artifact; its Neutralised Data Sources ship disabled for hand rework."
    ),
    RequestAttributeOutcome.NOT_COVERABLE: (
        "No Artifact — nothing was coverable, so rework these Data Sources by hand."
    ),
    RequestAttributeOutcome.SELECTS_NOTHING: (
        "Delete — the Scopes select nothing, so there is nothing to cover; re-run wider first to "
        "be sure."
    ),
    RequestAttributeOutcome.NO_VERDICT: (
        "Re-run — the run could not measure this Request Attribute, so no decision is owed yet."
    ),
    RequestAttributeOutcome.OBSOLETE: "Delete — nothing it captures survives Phase 3.",
    RequestAttributeOutcome.UNPROCESSABLE: (
        "This Request Attribute could not be read, so the run reached no verdict for it."
    ),
}

# The four actions a customer takes, in the order the Report presents them: Deploy, then Rework,
# then Delete, then Re-run. Grouping is on the Report's display outcome (`_display_outcome`), not the
# rolled-up verdict, so a partially-covered Request Attribute lands by what it actually needs: an
# obsolete-only one displays covered and deploys, an uncoverable one is reworked by hand and heads
# that section, above the wholly not-coverable ones. Two verdicts still share a section where they
# share an action - selects-nothing and obsolete are both deleted, no-verdict and unprocessable both
# re-run. Order within a section follows this tuple first, then the run order.
_ACTION_GROUPS: tuple[tuple[str, tuple[RequestAttributeOutcome, ...]], ...] = (
    ("Deploy the Artifact", (RequestAttributeOutcome.COVERED,)),
    (
        "Rework by hand",
        (RequestAttributeOutcome.PARTIALLY_COVERED, RequestAttributeOutcome.NOT_COVERABLE),
    ),
    ("Delete", (RequestAttributeOutcome.SELECTS_NOTHING, RequestAttributeOutcome.OBSOLETE)),
    ("Re-run", (RequestAttributeOutcome.NO_VERDICT, RequestAttributeOutcome.UNPROCESSABLE)),
)

# Which read or construction each covered route rests on, in words. The distinction is load-bearing:
# a Fan-Out is exact by construction, the other three by a read that was actually spent, and a
# customer choosing what to trust must see which.
_COVERED_READ = {
    CoveredReason.FAN_OUT_CONSTRUCTION: "the fan-out construction",
    CoveredReason.HOST_GROUP_MEMBERSHIP_READ: "the host group full-membership read",
    CoveredReason.SERVICE_CLOSURE_READ: "the service closure read",
    CoveredReason.VERIFICATION_READ: "the verification read over live spans",
}

# What each terminal outcome means to a customer, in the action it implies. Three of them look alike
# at a glance and must never read alike: a Neutralised-uncoverable Data Source is reworked by hand, a
# Neutralised-obsolete one goes away because Phase 3 removes what it captured, and a no-verdict one is
# re-run because the run could not measure it. The verdict's own detail is appended after this.
_GROUNDS = {
    DataSourceOutcome.CONDITION_DROPPED: (
        "Covered — the service technology narrowed nothing, so removing it is exact and no "
        "replacement condition was needed."
    ),
    DataSourceOutcome.NEUTRALISED_UNCOVERABLE: (
        "Neutralised — the run established this Data Source cannot be covered, so it ships disabled "
        "for hand rework."
    ),
    DataSourceOutcome.NEUTRALISED_OBSOLETE: (
        "Neutralised — it captures only onto external service calls, which Phase 3 removes, so "
        "nothing it captures survives."
    ),
    DataSourceOutcome.NO_VERDICT: (
        "No verdict — the run could not measure this Data Source, so re-run before deciding; it is "
        "not a finding that it cannot be covered."
    ),
    DataSourceOutcome.EMPTY_TARGET_SET: (
        "Selects nothing — its Scope matched nothing in the window, so there is nothing to cover; "
        "re-run wider before deleting it."
    ),
    DataSourceOutcome.UNPROCESSABLE: (
        "Unprocessable — this Data Source could not be read, so the run reached no verdict for it."
    ),
}

_STYLE = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       font-size: 13px; background: #f5f5f5; color: #222; }
.container { max-width: 1100px; margin: 0 auto; padding: 20px; }
h1 { font-size: 20px; margin-bottom: 4px; }
.run-meta { color: #666; font-size: 12px; margin-bottom: 16px; }
.apply { background: #eef7ee; border: 1px solid #bcdcbc; border-radius: 6px;
         padding: 10px 14px; margin-bottom: 18px; }
.scan { background: #fff; border: 1px solid #ddd; border-radius: 6px;
        padding: 12px 16px; margin-bottom: 20px; }
details.group { margin: 22px 0 8px; }
summary { list-style-position: inside; }
.attr-group { font-size: 15px; padding-bottom: 4px; border-bottom: 2px solid #ddd;
              cursor: pointer; overflow: hidden; }
.group-title { font-weight: 600; }
.group-body { margin-top: 8px; }
.toggle-ds { float: right; font-size: 11px; font-weight: 400; padding: 2px 8px;
             border: 1px solid #bbb; border-radius: 3px; background: #fff; color: #333;
             cursor: pointer; }
.toggle-ds:hover { background: #f0f0f0; }
.attr-card { background: #fff; border: 1px solid #ddd; border-radius: 6px;
             margin-bottom: 12px; overflow: hidden; }
.attr-header { padding: 10px 14px; background: #fafafa; border-bottom: 1px solid #eee;
               cursor: pointer; }
.attr-name { font-weight: 600; }
.attr-id { color: #888; font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.attr-body { padding: 6px 14px 12px; }
.ds-row { border: 1px solid #e8e8e8; border-radius: 4px; margin: 8px 0; padding: 8px 12px; }
.badge { display: inline-block; padding: 2px 7px; border-radius: 3px; font-size: 11px;
         font-weight: 600; color: #fff; }
.covered { background: #27ae60; }
.condition-dropped { background: #16a085; }
.neutralised-uncoverable { background: #c0392b; }
.neutralised-obsolete { background: #8e44ad; }
.no-verdict { background: #e67e22; }
.empty-target-set { background: #7f8c8d; }
.unprocessable { background: #7f8c8d; }
.grounds { font-size: 12px; color: #444; margin-top: 4px; }
.caveat { font-size: 11px; color: #666; font-style: italic; margin-top: 3px; }
.entity-overflow { font-size: 11px; color: #666; margin-top: 2px; }
.entity-overflow summary { cursor: pointer; color: #2980b9; }
"""

# The group button's toggle: expand or collapse every Data Source card in its own group, and flip its
# own label. `preventDefault` keeps the click off the group's disclosure so the button does not close
# the group it is toggling; expanding also opens the group so the effect is visible.
_TOGGLE_SCRIPT = """<script>
function toggleGroupDs(event, btn) {
  event.preventDefault();
  event.stopPropagation();
  var group = btn.closest('details.group');
  var expand = btn.getAttribute('data-state') !== 'expanded';
  if (expand) { group.open = true; }
  group.querySelectorAll('details.attr').forEach(function (card) { card.open = expand; });
  btn.setAttribute('data-state', expand ? 'expanded' : 'collapsed');
  btn.textContent = expand ? 'Collapse all datasources' : 'Show all datasources';
}
</script>"""


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _display_outcome(
    attribute: RequestAttributeVerdict, verdicts: Sequence[DataSourceVerdict]
) -> RequestAttributeOutcome:
    """The outcome the Report groups and labels a Request Attribute on.

    It parts from the rolled-up verdict in one place: a partially-covered Request Attribute whose
    Neutralised Data Sources are all obsolete needs no hand rework - Phase 3 removes what they
    captured - so the Report shows it covered and deploys it. One carrying any uncoverable Data
    Source stays partially-covered and is reworked by hand.
    """
    if attribute.verdict is RequestAttributeOutcome.PARTIALLY_COVERED and not any(
        one.verdict is DataSourceOutcome.NEUTRALISED_UNCOVERABLE for one in verdicts
    ):
        return RequestAttributeOutcome.COVERED
    return attribute.verdict


def render_report(result: RunResult) -> str:
    """The whole Report as one self-contained HTML document."""
    classifications = {one.id: one for one in result.classifications}
    verdicts_by_attribute: dict[str, list[DataSourceVerdict]] = {}
    for verdict in result.data_source_verdicts:
        verdicts_by_attribute.setdefault(verdict.attribute_id, []).append(verdict)
    display_by_id = {
        attribute.attribute_id: _display_outcome(
            attribute, verdicts_by_attribute.get(attribute.attribute_id, [])
        )
        for attribute in result.request_attribute_verdicts
    }
    def card(attribute: RequestAttributeVerdict) -> str:
        return _card(
            attribute,
            classifications.get(attribute.attribute_id),
            verdicts_by_attribute.get(attribute.attribute_id, []),
        )

    sections = []
    for label, outcomes in _ACTION_GROUPS:
        members = [
            (outcomes.index(display_by_id[attribute.attribute_id]), attribute)
            for attribute in result.request_attribute_verdicts
            if display_by_id[attribute.attribute_id] in outcomes
        ]
        if not members:
            continue
        members.sort(key=operator.itemgetter(0))
        rendered = "\n".join(card(attribute) for _, attribute in members)
        sections.append(
            '<details class="group">'
            '<summary class="attr-group">'
            f'<span class="group-title">{_esc(label)}</span>'
            '<button type="button" class="toggle-ds" data-state="collapsed" '
            'onclick="toggleGroupDs(event, this)">Show all datasources</button>'
            f'</summary>\n<div class="group-body">{rendered}</div></details>'
        )
    cards = "\n".join(sections)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Request Attribute migration report</title>
  <style>{_STYLE}</style>
</head>
<body>
<div class="container">
  <h1>Request Attribute migration report</h1>
  <div class="run-meta">
    Tenant: <strong>{_esc(result.platform_url)}</strong> &middot;
    Window: <strong>{_esc(result.window.expression)}</strong>
    ({_esc(result.window.timeframe)})
  </div>
  <div class="apply">
    Each Artifact under <code>artifacts/</code> is a complete replacement Request Attribute body.
    <strong>Apply each one before Phase 3.</strong> A Neutralised Data Source keeps its original
    non-primary tag, which a pre-Phase-3 tenant accepts and a Phase 3 tenant rejects — so the window
    to deploy these closes when Phase 3 lands.
  </div>
  {_scan_section(result)}
  {cards}
</div>
{_TOGGLE_SCRIPT}
</body>
</html>
"""


def _scan_section(result: RunResult) -> str:
    """This run's scan coverage - worded as coverage, never as a claim about the tenant at large.

    A figure here says how far this pass got over the configurations it read, not what the tenant
    holds in general: a different window or a rate-limited read would move it. The
    disabled-carrying-deprecated count rides here as it does in the summary's scan block.
    """
    disabled_line = (
        f"<p>{result.disabled_carrying_deprecated} disabled request attribute(s) carry a "
        "deprecated condition and will not capture if re-enabled after Phase 3.</p>"
    )
    return (
        '<div class="scan">'
        "<h2 style=\"font-size:15px;margin-bottom:6px;\">Scan coverage</h2>"
        "<p>This run scanned "
        f"<strong>{result.scanned}</strong> request attribute(s): "
        f"<strong>{result.enabled}</strong> enabled, of those "
        f"<strong>{result.obsolete}</strong> obsolete and "
        f"<strong>{result.affected}</strong> affected. These figures describe this run's coverage, "
        "not the tenant's request attributes in general.</p>"
        f"{disabled_line}"
        "</div>"
    )


def _card(
    attribute: RequestAttributeVerdict,
    classification: AttributeClassification | None,
    verdicts: Sequence[DataSourceVerdict],
) -> str:
    """One Request Attribute's card: its display verdict and a row per Data Source."""
    display = _display_outcome(attribute, verdicts)
    name = classification.name if classification is not None else attribute.attribute_id
    sources = (
        {one.index: one for one in classification.data_sources}
        if classification is not None
        else {}
    )
    rows = "\n".join(
        _ds_row(verdict, sources.get(verdict.data_source_index)) for verdict in verdicts
    )
    return (
        f'<div class="attr-card"><details class="attr">'
        f'<summary class="attr-header">'
        f'<span class="attr-name">{_esc(name)}</span> '
        f'<span class="attr-id">{_esc(attribute.attribute_id)}</span> '
        f'<span class="badge {_esc(display)}">{_esc(display)}</span>'
        f'<div class="grounds">{_esc(_ATTRIBUTE_ACTION.get(display, ""))}</div>'
        f'</summary><div class="attr-body">{rows}</div></details></div>'
    )


_ENTITY_ID_RE = re.compile(r"\b[A-Z_]+-[0-9A-F]{16,}\b")
_VISIBLE_ENTITIES = 10


def _detail_html(detail: str) -> str:
    """Render a detail string, collapsing long entity-ID runs to first 10 + expandable remainder."""
    ids = _ENTITY_ID_RE.findall(detail)
    if len(ids) <= _VISIBLE_ENTITIES:
        return _esc(detail)
    # Split into: text-before-ids, ids, text-after-ids
    first_match = _ENTITY_ID_RE.search(detail)
    last_match = None
    for last_match in _ENTITY_ID_RE.finditer(detail):
        pass
    prefix = _esc(detail[: first_match.start()])  # type: ignore[union-attr]
    suffix = _esc(detail[last_match.end() :])  # type: ignore[union-attr]
    visible = ", ".join(_esc(i) for i in ids[:_VISIBLE_ENTITIES])
    hidden = ", ".join(_esc(i) for i in ids[_VISIBLE_ENTITIES:])
    return (
        f"{prefix}{visible}"
        f'<details class="entity-overflow">'
        f"<summary>… and {len(ids) - _VISIBLE_ENTITIES} more</summary>"
        f"{hidden}"
        f"</details>"
        f"{suffix}"
    )


def _ds_row(verdict: DataSourceVerdict, source: DataSourceClassification | None) -> str:
    """One Data Source's row: its own verdict, and the grounds that name the action it implies."""
    grounds = _covered_grounds(verdict) if verdict.verdict is DataSourceOutcome.COVERED else ""
    grounds = grounds or _GROUNDS.get(verdict.verdict, "")
    if verdict.detail:
        detail_html = _detail_html(verdict.detail)
        grounds = f"{grounds} {detail_html}" if grounds else detail_html
    caveats = "".join(f'<div class="caveat">{one}</div>' for one in _caveats(verdict, source))
    return (
        f'<div class="ds-row">'
        f'Data source #{verdict.data_source_index} '
        f'<span class="badge {_esc(verdict.verdict)}">{_esc(verdict.verdict)}</span>'
        f'<div class="grounds">{grounds}</div>'
        f'{caveats}'
        f'</div>'
    )


def _caveats(verdict: DataSourceVerdict, source: DataSourceClassification | None) -> list[str]:
    """What rides a verdict beyond how it came out: a retained alternative the customer may prefer,
    the dormant-member caveat, and the external-half note read off the original classification."""
    caveats: list[str] = []
    candidate = verdict.candidate
    if candidate is not None and candidate.key_only_alternative is not None:
        caveats.append(
            "Retained alternative: key-only "
            f"<code>{_esc(candidate.key_only_alternative.key)}</code> — not shipped, because "
            "key:value was chosen so the replacement does not widen as new deployments appear."
        )
    if verdict.note is DataSourceNote.DORMANT_TARGET_SET_MEMBERS and verdict.dormant:
        members = ", ".join(f"<code>{_esc(one)}</code>" for one in verdict.dormant)
        caveats.append(
            "Dormant-member caveat: the replacement covers every member that had traffic in the "
            f"window; member(s) {members} were dormant, so if they resume traffic it may not cover "
            "them — re-run to confirm."
        )
    if source is not None and DataSourceNote.EXTERNAL_HALF_LOST in source.notes:
        caveats.append(
            "This Data Source captured on both the external service call and the full one; the "
            "external half goes away because Phase 3 removes external service calls. The Data Source "
            "migrates fine, and no replacement can reach that half — nothing you or the tool does "
            "changes it."
        )
    return caveats


def _covered_grounds(verdict: DataSourceVerdict) -> str:
    """A covered Data Source: that the match is exact, and which of the four reads established it."""
    read = _COVERED_READ.get(verdict.reason) if isinstance(verdict.reason, CoveredReason) else None
    established = f", established by {read}" if read is not None else ""
    return f"Covered — the replacement selects exactly the Target Set{established}."
