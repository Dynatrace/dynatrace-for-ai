"""Build the JSON summary and self-contained HTML report.

The page answers one question: *what has to be checked before Phase 3?* Anything
that does not move that forward is left out — no inventory of what was read and
no commentary on how the scan works. Sources with nothing to check collapse into
a single line.

Typography is deliberately flat inside an entry. Only section headings look like
headings; an artifact name and its link stay at body size, so several open
entries still read as one list rather than as competing sections. The layout
keeps the report focused on configurations that require review.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .scan import Finding
from .shared import COMPLETE, SourceResult, artifact_link, normalise_url

# The classic Message Queues app owns the QUEUE entity page; there is no
# platform intent for a classic entity, so the link goes through the app wrapper
# the same way the external-services report reaches a SERVICE. The app is retired
# by the upgrade, which is the same window the assessment already asks for: run
# it before Phase 3, while the entity still exists.
_QUEUE_ENTITY_PATH = "/ui/apps/dynatrace.classic.queues/ui/entity/"

_SOURCE_LABELS = {
    "dashboards": "Dashboards",
    "notebooks": "Notebooks",
    "slos": "SLOs",
    "classic_slos": "Classic SLOs",
    "srgs": "Site Reliability Guardians",
    "metric_events": "Metric events",
    "davis_anomaly_detectors": "Davis custom alerts",
    "queue_lookup": "Queue entity lookup (enrichment)",
}

# Enrichment sources add context to a finding; they never produce one.
_ENRICHMENT_SOURCES = frozenset({"queue_lookup"})

# Neutral wording on purpose: a reference found is work to schedule, not damage
# to announce. "Needs review" is what the customer is being asked to do.
_VERDICT_BADGE = {
    "affected": ("blue", "Needs review"),
    "clean": ("complete", "Nothing to review — omit this topic from the customer report"),
    "incomplete": ("partial", "Coverage incomplete — not a no-usage result"),
}

_VERDICT_NOTES = {
    "affected": "Configurations explicitly reference classic queue entities or metrics.",
    "clean": "Every configuration source was read completely and nothing references a classic queue entity or metric. Omit this topic from the customer report.",
    "incomplete": "No reference was found, but at least one source was not read completely. This is not a no-usage result.",
}


def queue_link(base_url: str, queue_id: str) -> str | None:
    """Link to the classic entity page for *queue_id*, or ``None``."""
    if not base_url or not queue_id:
        return None
    return f"{normalise_url(base_url)}{_QUEUE_ENTITY_PATH}{queue_id}"


def add_queue_links(queues: Iterable[dict[str, Any]], base_url: str) -> None:
    """Add or refresh the entity link on referenced queue dictionaries.

    Only a resolved queue is linked. An ID that enrichment could not resolve has
    no entity page behind it, so a link would open an error — and a finding whose
    only offered action fails reads as a broken report rather than as the "this
    queue is already gone" that it is.
    """
    if not base_url:
        return
    for queue in queues:
        queue["link"] = (
            queue_link(base_url, str(queue.get("id") or ""))
            if queue.get("resolved")
            else None
        )


def build_summary(
    *,
    cfg,
    findings: list[Finding],
    sources: list[SourceResult],
    resolved_queues: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    all_queue_ids: set[str] = set()
    all_metric_keys: set[str] = set()

    for finding in findings:
        key = (finding.kind, finding.artifact_id)
        artifact = grouped.setdefault(
            key,
            {
                "source": finding.source,
                "kind": finding.kind,
                "id": finding.artifact_id,
                "name": finding.artifact_name,
                "link": artifact_link(cfg.ui_url, finding.kind, finding.artifact_id),
                "scope": finding.scope,
                "queue_ids": set(),
                "metric_keys": set(),
                "references": [],
            },
        )
        artifact["queue_ids"].update(finding.queue_ids)
        artifact["metric_keys"].update(finding.metric_keys)
        artifact["references"].append(
            {
                "field_path": finding.field_path,
                "text": finding.text,
                "queue_ids": finding.queue_ids,
                "metric_keys": finding.metric_keys,
            }
        )
        all_queue_ids.update(finding.queue_ids)
        all_metric_keys.update(finding.metric_keys)

    artifacts = sorted(grouped.values(), key=lambda a: (a["source"], a["name"], a["id"]))
    for artifact in artifacts:
        artifact["queue_ids"] = sorted(artifact["queue_ids"])
        artifact["metric_keys"] = sorted(artifact["metric_keys"])
        artifact["impact_types"] = [
            label
            for present, label in (
                (artifact["queue_ids"], "queue entity ID"),
                (artifact["metric_keys"], "classic queue metric"),
            )
            if present
        ]
        artifact["reference_count"] = len(artifact["references"])

    queues = []
    for queue_id in sorted(all_queue_ids):
        queue = dict(
            resolved_queues.get(
                queue_id,
                {
                    "id": queue_id,
                    "name": None,
                    "queue_name": None,
                    "destination_type": None,
                    "vendor": None,
                    "resolved": False,
                },
            )
        )
        queue["affected_artifact_count"] = sum(queue_id in a["queue_ids"] for a in artifacts)
        queues.append(queue)
    add_queue_links(queues, cfg.ui_url)

    source_blocks = [
        {
            "name": source.name,
            "state": source.state,
            "reason": source.reason,
            "items_checked": source.items_checked,
            "items_unread": source.items_unread,
        }
        for source in sources
    ]
    incomplete = [source["name"] for source in source_blocks if source["state"] != COMPLETE]
    if artifacts:
        verdict = "affected"
    elif incomplete:
        verdict = "incomplete"
    else:
        verdict = "clean"

    return {
        "tool": "messaging-queue-scanner",
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tenant": {
            "label": cfg.tenant_label,
            "transport": cfg.transport,
            "dtctl_context": cfg.dtctl_context,
            "ui_url": cfg.ui_url,
            "classic_url": cfg.classic_url,
            "platform_url": cfg.platform_url,
        },
        "verdict": verdict,
        "verdict_note": _VERDICT_NOTES[verdict],
        "sources": source_blocks,
        "incomplete_sources": incomplete,
        "totals": {
            "artifacts_affected": len(artifacts),
            "references": len(findings),
            "queue_ids_referenced": len(all_queue_ids),
            "classic_metric_keys_referenced": len(all_metric_keys),
        },
        "report_scope": "detection only; no replacement queries or configurations are generated",
        "cache": {
            "format": 1,
            "purpose": "Reusable messaging and queue usage scan data",
            "contains": "referenced queue identities, matching values, and affected configuration bodies",
        },
        "queues": queues,
        "classic_metric_keys": sorted(all_metric_keys),
        "artifacts": artifacts,
    }


def write_summary(output_dir: Path, summary: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "summary.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return path


def write_scan_data(
    output_dir: Path,
    summary: dict[str, Any],
    configurations: list[dict[str, Any]],
) -> Path:
    """Persist affected identities and configurations without repeating the scan."""
    path = output_dir / "scan-data.json"
    payload = {
        "format": 1,
        "generated_at": summary.get("generated_at"),
        "tenant": summary.get("tenant"),
        "verdict": summary.get("verdict"),
        "sources": summary.get("sources", []),
        "enrichment": summary.get("enrichment", {}),
        "queues": summary.get("queues", []),
        "classic_metric_keys": summary.get("classic_metric_keys", []),
        "artifacts": summary.get("artifacts", []),
        "configurations": configurations,
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return path


def _escape(value: Any) -> str:
    return html.escape(str(value) if value is not None else "")


def _badge(text: str, css_class: str) -> str:
    safe_class = css_class if css_class.isidentifier() else "grey"
    return f'<span class="badge {safe_class}">{_escape(text)}</span>'


def _artifact_html(artifact: dict[str, Any]) -> str:
    """One configuration to review.

    The name is plain text and the link is a small trailing action. A bold blue
    heading-sized link here reads as a section title and breaks the list apart
    once several entries are open at the same time.
    """
    count = artifact.get("reference_count", 0)
    references = "".join(
        f"""
        <div class="reference">
          <p class="artifact-meta">field <code>{_escape(ref.get('field_path'))}</code></p>
          <pre class="code-block">{_escape(ref.get('text'))}</pre>
        </div>
        """
        for ref in artifact.get("references", [])
    )
    impacts = " ".join(_badge(value, "grey") for value in artifact.get("impact_types", []))
    queues = ", ".join(artifact.get("queue_ids", [])) or "none"
    metrics = ", ".join(artifact.get("metric_keys", [])) or "none"
    scope = (
        f" &nbsp;&middot;&nbsp; scope <code>{_escape(artifact['scope'])}</code>"
        if artifact.get("scope")
        else ""
    )
    open_link = ""
    if artifact.get("link"):
        open_link = (
            f' &nbsp;&middot;&nbsp; <a class="open-link" href="{_escape(artifact["link"])}" '
            'target="_blank" rel="noopener">Open in tenant &#8599;</a>'
        )
    label = _SOURCE_LABELS.get(artifact.get("source", ""), artifact.get("source", ""))
    return f"""
    <details class="group">
      <summary>
        {_badge(artifact.get('kind', ''), 'grey')}
        <span class="artifact-name">{_escape(artifact.get('name'))}</span>
        {impacts}
        <span class="meta">{count} reference(s)</span>
      </summary>
      <div class="group-body">
        <p class="artifact-meta">{_escape(label)} &nbsp;&middot;&nbsp;
           <span class="mono-sm">{_escape(artifact.get('id'))}</span>{scope}{open_link}</p>
        <p class="label">Context</p>
        <table><tbody>
          <tr><th>Queue IDs</th><td><code>{_escape(queues)}</code></td></tr>
          <tr><th>Classic metrics</th><td><code>{_escape(metrics)}</code></td></tr>
        </tbody></table>
        <p class="label">References ({count})</p>
        {references}
      </div>
    </details>
    """


def _result_cell(source: dict[str, Any], to_review: int) -> str:
    """The actionable half of a coverage row: what has to be checked.

    A raw object count answers a question nobody asked. The review count is the
    work; the remainder is only there to show it was drawn from the whole source
    rather than a sample.
    """
    checked = source.get("items_checked")
    unread = source.get("items_unread") or 0
    found = (
        f"<strong>{to_review} to review</strong>"
        if to_review
        else "<span class='muted'>nothing to review</span>"
    )
    if not isinstance(checked, int):
        return found
    # ``items_checked`` counts what the source listed; an object whose body never
    # arrived was not examined and must not be counted as carrying no reference.
    # Clamped: a listing that under-reports its own size must not print a
    # negative count into a customer-facing report.
    rest = (
        f"<span class='muted'>&middot; {max(checked - to_review - unread, 0)} "
        "with no reference</span>"
    )
    if unread:
        rest += f" <span class='warn'>&middot; {unread} unread</span>"
    return f"{found} {rest}"


def _sources_html(sources: list[dict[str, Any]], artifacts: list[dict[str, Any]]) -> str:
    """List only the sources that ask something of the reader.

    A source that was read in full and holds nothing to review needs no row: it
    contributes no work, and printing five such rows buries the one or two that
    do. Those sources are named in a single line underneath, which is what makes
    the review counts trustworthy — they came from the whole tenant.
    """
    to_review_by_source: dict[str, int] = {}
    for artifact in artifacts:
        name = str(artifact.get("source", ""))
        to_review_by_source[name] = to_review_by_source.get(name, 0) + 1

    rows = ""
    settled: list[str] = []
    for source in sources:
        name = source["name"]
        label = _SOURCE_LABELS.get(name, name)
        to_review = to_review_by_source.get(name, 0)
        if not to_review and source["state"] == COMPLETE:
            settled.append(label)
            continue
        # Enrichment sources produce no findings, so a review/no-reference split
        # against them would read as a false all-clear.
        result = (
            "<span class='muted'>context only</span>"
            if name in _ENRICHMENT_SOURCES
            else _result_cell(source, to_review)
        )
        rows += (
            f"<tr><td>{_escape(label)}</td>"
            f"<td>{_badge(source['state'], source['state'])}</td>"
            f"<td>{result}</td>"
            f"<td>{_escape(source['reason'])}</td></tr>"
        )

    table = ""
    if rows:
        table = (
            "<table><thead><tr><th>Source</th><th>Coverage</th><th>Result</th>"
            f"<th>Note</th></tr></thead><tbody>{rows}</tbody></table>"
        )
    if settled:
        table += (
            "<p class='muted'>Read in full, nothing to review: "
            f"{_escape(', '.join(settled))}.</p>"
        )
    return table or "<p class='muted'>No source was read.</p>"


def _queue_open_link(queue: dict[str, Any]) -> str:
    """Trailing action on the queue ID, sized like the one on a configuration."""
    if not queue.get("link"):
        return ""
    return (
        f' &nbsp;&middot;&nbsp; <a class="open-link" href="{_escape(queue["link"])}" '
        'target="_blank" rel="noopener">Open queue &#8599;</a>'
    )


def _queues_html(queues: list[dict[str, Any]]) -> str:
    if not queues:
        return "<p class='muted'>No queue IDs were explicitly referenced.</p>"
    rows = "".join(
        f"<tr><td><code>{_escape(queue['id'])}</code>{_queue_open_link(queue)}</td>"
        f"<td>{_escape(queue.get('name') or 'unresolved')}</td>"
        f"<td>{_escape(queue.get('destination_type'))}</td>"
        f"<td>{_escape(queue.get('vendor'))}</td>"
        f"<td>{_escape(queue.get('affected_artifact_count'))}</td></tr>"
        for queue in queues
    )
    return f"<table><thead><tr><th>Queue ID</th><th>Name</th><th>Destination type</th><th>Vendor</th><th>Configurations</th></tr></thead><tbody>{rows}</tbody></table>"


def _enrichment_html(enrichment: dict[str, Any]) -> str:
    lookup = enrichment.get("queue_lookup") or {}
    if not lookup:
        return ""
    state = lookup.get("state", "")
    details = (
        f"Queue entity enrichment: {_badge(state, state or 'grey')} "
        f"{_escape(lookup.get('ids_resolved', 0))}/{_escape(lookup.get('ids_checked', 0))} "
        f"referenced IDs resolved. {_escape(lookup.get('reason', ''))}"
    )
    css_class = "callout" if state == "failed" else "callout info"
    return f'<div class="{css_class}">{details}</div>'


def generate_html(summary: dict[str, Any]) -> str:
    verdict = summary.get("verdict", "incomplete")
    verdict_class, verdict_label = _VERDICT_BADGE.get(verdict, ("grey", verdict))
    tenant = summary.get("tenant", {}).get("label", "")
    incomplete = summary.get("incomplete_sources", [])
    warning = ""
    if incomplete:
        warning = (
            '<div class="callout"><strong>Coverage is incomplete:</strong> '
            + _escape(", ".join(_SOURCE_LABELS.get(name, name) for name in incomplete))
            + ". Re-run before treating missing findings as no usage.</div>"
        )
    artifacts = "".join(_artifact_html(a) for a in summary.get("artifacts", []))
    if not artifacts:
        artifacts = "<p class='muted'>No explicit classic queue reference was found.</p>"
    link_warning = ""
    if summary.get("artifacts") and not any(a.get("link") for a in summary.get("artifacts", [])):
        link_warning = (
            '<div class="callout"><strong>Configuration links unavailable.</strong> '
            'Re-render this report with <code>--ui-url https://&lt;environment&gt;.apps.dynatrace.com</code>.</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Messaging and Queue Usage - Phase 3 Report</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 24px; background: #f7f8fa; color: #202124; }}
    h1 {{ margin-bottom: 4px; }} h2 {{ margin-top: 30px; border-bottom: 2px solid #dde1e6; padding-bottom: 5px; }}
    .muted, .meta {{ color: #68707a; font-size: .85rem; }} .meta {{ margin-left: auto; font-size: .75rem; }}
    p.muted {{ margin: 0; }}
    .description {{ background: white; border: 1px solid #dce1e6; border-radius: 8px; padding: 13px 16px; margin: 16px 0 0; font-size: .9rem; line-height: 1.6; color: #39424d; }}
    .warn {{ color: #8a5b00; font-weight: 600; }}
    .label {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; color: #68707a; margin: 14px 0 2px; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: .75rem; font-weight: 600; margin-right: 6px; }}
    .complete {{ background: #d5f5e3; color: #12613b; }} .partial {{ background: #fff1b8; color: #704f00; }}
    .failed {{ background: #fde0df; color: #8f1d18; }} .grey {{ background: #e9edf2; color: #46515d; }}
    .blue {{ background: #dbeafe; color: #1e40af; }}
    table {{ width: 100%; border-collapse: collapse; background: white; font-size: .86rem; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #e1e5ea; vertical-align: top; }}
    th {{ background: #edf0f3; font-size: .76rem; text-transform: uppercase; }}
    tr:last-child td {{ border-bottom: none; }}
    details.group {{ background: white; border: 1px solid #dce1e6; border-radius: 8px; margin: 9px 0; overflow: hidden; }}
    details.group > summary {{ display: flex; align-items: center; gap: 6px; padding: 12px 14px; cursor: pointer; flex-wrap: wrap; font-size: .9rem; user-select: none; }}
    details.group > summary:hover, details.group[open] > summary {{ background: #f7f8fa; }}
    .group-body {{ border-top: 1px solid #e2e6ea; padding: 2px 16px 14px; }}
    .group-body table {{ font-size: .8rem; }}
    .group-body th {{ width: 150px; }}
    .artifact-name {{ font-size: .9rem; font-weight: 600; }}
    .artifact-meta {{ color: #68707a; font-size: .78rem; margin: 3px 0 0; }}
    .mono-sm {{ color: #68707a; font-size: .75rem; font-family: ui-monospace, monospace; }}
    .reference {{ border-left: 3px solid #dfe3e8; padding: 2px 0 6px 12px; margin: 10px 0 0; }}
    code {{ font-family: ui-monospace, monospace; background: #edf0f3; padding: 1px 4px; border-radius: 3px; }}
    pre.code-block {{ background: #20232b; color: #edf2f7; padding: 12px 14px; border-radius: 5px; font-size: .75rem; line-height: 1.5; white-space: pre-wrap; word-break: break-word; overflow-x: auto; margin: 4px 0 0; }}
    a {{ color: #175cd3; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
    a.open-link {{ font-size: .78rem; white-space: nowrap; }}
    .callout {{ background: white; border-left: 4px solid #e0a000; padding: 12px 15px; margin: 16px 0; font-size: .85rem; }}
    .info {{ border-left-color: #3976d3; }}
  </style>
</head>
<body>
  <h1>Messaging and Queue Usage - Phase 3 Report</h1>
  <p class="muted">{_badge(verdict_label, verdict_class)} {_escape(tenant)}; generated {_escape(summary.get('generated_at'))}</p>
  <p class="muted">{_escape(summary.get('verdict_note'))}</p>
  <p class="description">
    Phase 3 removes classic <code>QUEUE</code> entities, and the classic queue metrics
    <code>builtin:queue.incoming_requests</code> and <code>builtin:queue.outgoing_requests</code>
    stop receiving data. Any configuration that reads them &mdash; a Service-Level Objective,
    guardian, metric event, alert, dashboard, or notebook &mdash; stops returning data once Phase 3
    is applied: the objective stops evaluating, the alert stops firing, the tile stays empty.
    The entries below are the ones found on this environment. Messaging is monitored
    service-centrically in Phase 3, through <code>dt.service.messaging.*</code> metrics and
    messaging spans.
  </p>
  {warning}

  <h2>What to check</h2>
  {_sources_html(summary.get('sources', []), summary.get('artifacts', []))}

  <h2>Configurations to review ({len(summary.get('artifacts', []))})</h2>
  {link_warning}
  {artifacts}

  <h2>Referenced queues</h2>
  {_queues_html(summary.get('queues', []))}
  {_enrichment_html(summary.get('enrichment', {}))}

  <div class="callout info">Each entry keeps the original query or selector so it can be located and reworked by hand. Classic queue entities have no Phase 3 replacement; monitoring becomes service-centric through messaging metrics and spans. Nothing in this report was written to the tenant.</div>
</body>
</html>
"""


def write_html(output_dir: Path, summary: dict[str, Any]) -> Path:
    path = output_dir / "report.html"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(generate_html(summary), encoding="utf-8")
    temporary.replace(path)
    return path
