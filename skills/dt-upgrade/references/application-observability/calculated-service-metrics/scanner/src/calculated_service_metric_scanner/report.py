"""Build the JSON summary and self-contained HTML report.

The page answers one question: *what has to be checked before Phase 3?* Anything
that does not move that forward is left out — no inventory of what was read and
no commentary on how the scan works. Sources with nothing to check collapse into
a single line.

Typography is deliberately flat inside an entry. Only section headings look like
headings; an artifact name and its link stay at body size, so several open
entries still read as one list rather than as competing sections. This mirrors
the messaging-queues report: the two are handed over together and a change to
one is a change to both.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .scan import CLASSIC_PREFIX, Finding
from .shared import COMPLETE, SourceResult, artifact_link, derive_url_pair, normalise_url

_SOURCE_LABELS = {
    "grail_metric_inventory": "Calculated service metric inventory",
    "calculated_metric_definitions": "Calculated service metric definitions",
    "calculated_metric_traffic": "Calculated service metric datapoints",
    "dashboards": "Dashboards",
    "notebooks": "Notebooks",
    "slos": "SLOs",
    "classic_slos": "Classic SLOs",
    "srgs": "Site Reliability Guardians",
    "metric_events": "Metric events",
    "davis_anomaly_detectors": "Davis custom alerts",
}

#: What one configuration *is*, in the words the customer uses for it. The raw
#: ``kind`` is precise but unreadable — a settings object badge renders as
#: ``SETTINGS/builtin:anomaly-detection.metric-events`` — so the category carries
#: the badge and ``kind`` stays out of the page.
_CATEGORIES = {
    "dashboards": "Dashboard",
    "notebooks": "Notebook",
    "slos": "SLO",
    "classic_slos": "Classic SLO",
    "srgs": "Site Reliability Guardian",
    "metric_events": "Metric event",
    "davis_anomaly_detectors": "Davis custom alert",
}

#: Classic sources. A classic SLO or a metric event cannot read a metric produced by an
#: OpenPipeline processor, so a configuration here is reworked by hand whatever the migration
#: verdict of the metric it reads. Kept apart from the rest for that reason alone.
CLASSIC_SOURCES = frozenset({"classic_slos", "metric_events"})

PLATFORM = "platform"
CLASSIC = "classic"

#: How each side is named on the page. "Classic" is the customer's own word for the old
#: interface; the other side is simply the platform.
_BAND_LABELS = {
    PLATFORM: "Platform configurations",
    CLASSIC: "Classic configurations",
}

_BAND_NOTES = {
    PLATFORM: "",
    CLASSIC: " — these cannot read a replacement metric",
}


def generation_of(source: str) -> str:
    """Whether *source* is a classic configuration or a platform one."""
    return CLASSIC if source in CLASSIC_SOURCES else PLATFORM


#: Classic place that opens one calculated service metric's own definition.
#: ``serviceMetricsEdit`` accepts either an internal config id or the metric key
#: under ``serviceTSM`` (``ServiceMetricEditPresenter.prepareFromRequest`` ->
#: ``getTSMServiceMetricUrl``); only the key is available here, and it is what the
#: Configuration API calls ``tsmMetricKey``. The place hierarchy is
#: ``settings / serviceMetrics / serviceMetricsEdit``
#: (``PlaceUtilities.getServiceMetricEditLocation``). The metric is not a
#: Settings 2.0 object -- ``builtin:settings.calculated-service-metrics`` is a GWT
#: pseudo-schema -- so there is no app intent to build this from.
_METRIC_EDIT_PLACE = "#settings/serviceMetrics/serviceMetricsEdit;serviceTSM="


def classic_base_url(platform_url: str, classic_url: str = "") -> str:
    """The classic host, taken as given or derived from the platform host."""
    if classic_url:
        return normalise_url(classic_url)
    if not platform_url:
        return ""
    try:
        return derive_url_pair(tenant=None, platform=platform_url)[0]
    except Exception:  # noqa: BLE001 - a missing link never fails a report
        return ""


def metric_link(classic_url: str, classic_metric_key: str) -> str | None:
    """Link to the classic definition of *classic_metric_key*, or ``None``.

    The key is placed raw: GWT splits a place token on ``;`` and ``=`` only, and
    percent-encoding the ``:`` in ``calc:service.x`` is not what the UI itself
    produces.
    """
    if not classic_url or not classic_metric_key:
        return None
    return f"{normalise_url(classic_url)}/{_METRIC_EDIT_PLACE}{classic_metric_key}"


def add_metric_links(metrics: Iterable[dict[str, Any]], classic_url: str) -> None:
    """Add or refresh the classic-definition link on metric dictionaries."""
    if not classic_url:
        return
    for metric in metrics:
        metric["link"] = metric_link(classic_url, str(metric.get("classic_metric_key") or ""))

#: The inventory names the metrics a Grail-form reference is checked against; it
#: can never produce a finding, so it must never render as a review/no-reference
#: split — that would read as a false all-clear.
_INVENTORY_SOURCE = "grail_metric_inventory"

#: Sources that describe the metrics rather than search for references to them: the Grail
#: inventory, the classic definitions the migration verdict is computed from, and the datapoint
#: check behind it. None of them can produce a finding, so none may render as a
#: review/no-reference split — that would read as a false all-clear.
_CONTEXT_SOURCES = {
    _INVENTORY_SOURCE: "metric key(s) discovered",
    "calculated_metric_definitions": "definition(s) read",
    "calculated_metric_traffic": "metric(s) with recent datapoints",
}

# Neutral wording on purpose: a reference found is work to schedule, not damage
# to announce. "Needs review" is what the customer is being asked to do.
_VERDICT_BADGES = {
    "affected": ("blue", "Needs review"),
    "clean": ("complete", "Nothing to review — omit this topic from the customer report"),
    "incomplete": ("partial", "Coverage incomplete — not a no-usage result"),
}

_VERDICT_NOTES = {
    "affected": "Configurations reference calculated service metrics.",
    "clean": "The metric inventory and every configuration source were read completely and nothing references a calculated service metric. Omit this topic from the customer report.",
    "incomplete": "No reference was found, but the metric inventory or at least one configuration source was not read completely. This is not a no-usage result.",
}


def _artifact_order(artifact: dict[str, Any]) -> tuple[Any, ...]:
    """Sort key for the configurations of one metric.

    Third generation first: within a metric the migratable half is what a reader
    acts on, and the Gen2 half is context they cannot change. Shared with
    :func:`backfill_generations` so a re-rendered report and a fresh scan agree
    on array order — ``scan-data.json`` is a documented input for a later
    migrator, so that order is part of the contract, not a display detail.
    """
    return (
        artifact.get("generation", PLATFORM) != PLATFORM,
        str(artifact.get("category") or ""),
        str(artifact.get("name") or ""),
        str(artifact.get("id") or ""),
    )


def build_summary(
        *,
        cfg,
        findings: list[Finding],
        sources: list[SourceResult],
        metric_inventory: dict[str, dict[str, Any]],
        stale_findings: list[Finding] | None = None,
) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for finding in findings:
        classic_in_field = set(finding.classic_metric_keys)
        for metric_key in finding.metric_keys:
            inventory = metric_inventory.get(metric_key) or {}
            classic_key = inventory.get("classic_metric_key", CLASSIC_PREFIX + metric_key)
            group = groups.setdefault(
                metric_key,
                {
                    "metric_key": metric_key,
                    "classic_metric_key": classic_key,
                    "name": inventory.get("name", ""),
                    # A metric referenced only by its classic key can be absent
                    # from the Grail inventory — it was never enabled there. The
                    # reference is still work to schedule, so it is reported;
                    # the flag keeps the report honest about which it is.
                    "in_grail_inventory": metric_key in metric_inventory,
                    "artifacts": [],
                },
            )
            group["artifacts"].append(
                {
                    "source": finding.source,
                    "kind": finding.kind,
                    "category": _CATEGORIES.get(finding.source, finding.source),
                    "generation": generation_of(finding.source),
                    "id": finding.artifact_id,
                    "name": finding.artifact_name,
                    "link": artifact_link(cfg.ui_url, finding.kind, finding.artifact_id),
                    "field_path": finding.field_path,
                    "dql": finding.dql,
                    "scope": finding.scope,
                    "key_form": "classic" if classic_key in classic_in_field else "grail",
                }
            )

    classic_url = classic_base_url(cfg.ui_url, cfg.classic_url)
    ordered = sorted(groups.values(), key=lambda group: group["metric_key"])
    for group in ordered:
        group["artifacts"].sort(key=_artifact_order)
        group["artifact_count"] = len(
            {(artifact["kind"], artifact["id"]) for artifact in group["artifacts"]}
        )
        group["reference_count"] = len(group["artifacts"])
        group["key_forms"] = sorted({artifact["key_form"] for artifact in group["artifacts"]})
        group["generations"] = sorted({artifact["generation"] for artifact in group["artifacts"]})
        # A metric read only from classic configurations still gets a verdict — a metric
        # worth a definition is worth knowing about — but the consumers themselves have to be
        # rebuilt by hand, so the flag stays and drives the ordering.
        group["review_only"] = group["generations"] == [CLASSIC]
        group["link"] = metric_link(classic_url, group["classic_metric_key"])

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
    verdict = "affected" if ordered else "incomplete" if incomplete else "clean"
    affected_artifacts = {
        (artifact["kind"], artifact["id"])
        for group in ordered
        for artifact in group["artifacts"]
    }
    classic_artifacts = {
        (artifact["kind"], artifact["id"])
        for group in ordered
        for artifact in group["artifacts"]
        if artifact["generation"] == CLASSIC
    }
    review_only = [group for group in ordered if group["review_only"]]

    return {
        "tool": "calculated-service-metric-scanner",
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
            "metrics_available_in_grail": len(metric_inventory),
            "metrics_referenced": len(ordered),
            "metrics_referenced_platform": len(ordered) - len(review_only),
            "metrics_referenced_classic_only": len(review_only),
            "metrics_referenced_outside_grail_inventory": sum(
                1 for group in ordered if not group["in_grail_inventory"]
            ),
            "artifacts_affected": len(affected_artifacts),
            "artifacts_classic": len(classic_artifacts),
            "references": sum(len(finding.metric_keys) for finding in findings),
        },
        # References to calculated service metric keys the environment does not define. Kept
        # out of the metric list on purpose — a metric that does not exist has no usage and no
        # migration — but not thrown away: the configuration reading it returns no data today.
        "stale_references": [
            {
                "source": finding.source,
                "kind": finding.kind,
                "id": finding.artifact_id,
                "name": finding.artifact_name,
                "category": _CATEGORIES.get(finding.source, finding.source),
                "generation": generation_of(finding.source),
                "field_path": finding.field_path,
                "keys": finding.classic_metric_keys or finding.metric_keys,
                "link": artifact_link(cfg.ui_url, finding.kind, finding.artifact_id),
            }
            for finding in sorted(
                stale_findings or [],
                key=lambda f: (f.source, f.artifact_name, f.artifact_id),
                )
        ],
        "report_scope": "read-only usage assessment",
        "cache": {
            "format": 1,
            "purpose": "Reusable calculated-service-metric usage scan data",
            "contains": "affected metric identities, matching values, and affected configuration bodies",
        },
        "metrics": ordered,
    }


def attach_migration(
        summary: dict[str, Any],
        records: list[dict[str, Any]],
        *,
        classic_url: str,
        traffic_window: str,
        definitions_complete: bool,
        grail_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Fold the migration records into the summary, one per metric.

    Two things happen here. Every metric the scan already found gains its verdict, and every
    metric the tenant *defines* but nothing references is added to the list. The second half is
    what stops the report being a usage report only: a metric nothing references still stops
    receiving data in Phase 3, and an ad-hoc query in Data Explorer leaves no configuration
    behind for a scan to find.
    """
    from .migration import blocking_reasons, decisions, totals

    by_key = {record["classic_metric_key"]: record for record in records}
    metrics = summary.setdefault("metrics", [])
    for metric in metrics:
        metric["referenced"] = True
        record = by_key.pop(str(metric.get("classic_metric_key")), None)
        if record is not None:
            metric["migration"] = record
        elif definitions_complete:
            # The reference names a metric this tenant does not define. The reference is still
            # work — it stops returning data either way — but there is nothing to migrate.
            metric["migration"] = {
                "verdict": "unknown",
                "reason": "no classic definition exists on this tenant for this key",
            }
        else:
            metric["migration"] = {
                "verdict": "unknown",
                "reason": "the classic definition could not be read",
            }

    for record in by_key.values():
        metrics.append(
            {
                "metric_key": record["metric_key"],
                "classic_metric_key": record["classic_metric_key"],
                "name": record.get("name") or "",
                "in_grail_inventory": record["metric_key"] in (grail_keys or set()),
                "referenced": False,
                "artifacts": [],
                "artifact_count": 0,
                "reference_count": 0,
                "key_forms": [],
                "generations": [],
                "review_only": False,
                "link": metric_link(classic_url, record["classic_metric_key"]),
                "migration": record,
            }
        )
    metrics.sort(key=lambda metric: str(metric.get("metric_key")))

    counts = totals(records)
    summary["migration"] = {
        "assessed": counts["assessed"],
        "totals": counts,
        "traffic_window": traffic_window,
        "processor_dir": "processors",
        "reasons": blocking_reasons(records),
        "decisions": decisions(records),
        "complete": definitions_complete,
    }
    summary.setdefault("totals", {}).update(
        {
            "metrics_defined": counts["assessed"],
            "metrics_migratable": counts["migratable_total"],
            "metrics_not_migratable": counts["not_migratable"],
            "metrics_without_data": counts["no_traffic"],
        }
    )
    return summary


def rebuild_migration_views(summary: dict[str, Any]) -> dict[str, Any]:
    """Recompute the aggregate migration views from the per-metric records.

    The totals, the root-cause list and the tenant-wide decisions are all derived from the
    records already stored on each metric, so ``render`` rebuilds them rather than reprinting
    what an older scan happened to word. That is what lets the customer-facing wording be fixed
    without re-reading a tenant — the same reason :func:`backfill_generations` exists. Nothing is
    invented: a summary with no migration records is left alone.
    """
    from .migration import blocking_reasons, decisions, totals

    records = [
        metric["migration"]
        for metric in summary.get("metrics", [])
        if (metric.get("migration") or {}).get("classic_metric_key")
    ]
    if not records:
        return summary
    for record in records:
        _upgrade_dormant_record(record)
    migration = summary.setdefault("migration", {})
    migration["totals"] = totals(records)
    migration["assessed"] = migration["totals"]["assessed"]
    migration["reasons"] = blocking_reasons(records)
    migration["decisions"] = decisions(records)
    migration.setdefault("processor_dir", "processors")
    migration.setdefault(
        "traffic_window", str(records[0].get("traffic_window") or "")
    )
    return summary


#: What an older scan wrote instead of a verdict when a metric had no recent data. Dormancy is
#: now a property beside the verdict, so such a record carries no answer at all — and a metric
#: whose verdict is a key no section renders would silently vanish from the page.
_LEGACY_DORMANT = "no_data"


def _upgrade_dormant_record(record: dict[str, Any]) -> None:
    """Give a legacy ``no_data`` record a verdict the page can place.

    The assessment cannot be redone here — that needs the classic definition — so the metric is
    reported as unassessed and the re-run is named. Its dormant sentence is kept where the
    current report expects it.
    """
    if record.get("verdict") != _LEGACY_DORMANT:
        return
    record["verdict"] = "unknown"
    record["traffic"] = record.get("traffic") or "none"
    notes = record.get("notes") or []
    if not record.get("traffic_note") and notes:
        record["traffic_note"] = notes.pop(0)
        record["notes"] = notes
    record["reason"] = (
        "this metric was assessed by an earlier version of the scan, which gave no verdict to a "
        "metric without recent data. Re-run the scan to get one."
    )


def backfill_generations(summary: dict[str, Any]) -> dict[str, Any]:
    """Derive the generation/category fields on a summary written before them.

    ``render`` exists to rebuild a report from an existing ``summary.json``, so it
    has to cope with one produced by an earlier scan. Everything here is derived
    from the source name that was already recorded — no tenant is contacted and
    no finding is invented.
    """
    metrics = summary.get("metrics") or []
    for metric in metrics:
        for artifact in metric.get("artifacts", []):
            source = str(artifact.get("source", ""))
            artifact.setdefault("category", _CATEGORIES.get(source, source))
            # Set, not defaulted: the value is derived from the source name, and a summary
            # written before the classic/platform wording carries the older spelling.
            artifact["generation"] = generation_of(source)
        metric.get("artifacts", []).sort(key=_artifact_order)
        generations = sorted({a.get("generation", PLATFORM) for a in metric.get("artifacts", [])})
        metric["generations"] = generations
        metric["review_only"] = generations == [CLASSIC]
        metric.setdefault("referenced", bool(metric.get("artifacts")))

    totals = summary.setdefault("totals", {})
    # Only referenced metrics have a generation split to count. Since the metric list stopped
    # being reference-gated it also carries metrics with no artifact at all, and counting those
    # as read by a platform configuration counted the whole inventory as referenced.
    referenced = [metric for metric in metrics if metric.get("artifacts")]
    review_only = sum(1 for m in referenced if m.get("review_only"))
    totals["metrics_referenced_platform"] = len(referenced) - review_only
    totals["metrics_referenced_classic_only"] = review_only
    totals["artifacts_classic"] = len(
        {
            (a.get("kind"), a.get("id"))
            for m in metrics
            for a in m.get("artifacts", [])
            if a.get("generation") == CLASSIC
        }
    )
    return summary


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
    """Persist affected identities and configurations without repeating the scan.

    This file stays what it has always been: the *usage* record. Metrics nothing references and
    the migration verdicts are left out — those belong to ``summary.json``, and copying the
    generated processors into a second file would double an 800 KiB report for no reader.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "scan-data.json"
    payload = {
        "format": 1,
        "generated_at": summary.get("generated_at"),
        "tenant": summary.get("tenant"),
        "verdict": summary.get("verdict"),
        "sources": summary.get("sources", []),
        "metrics": [
            {key: value for key, value in metric.items() if key != "migration"}
            for metric in summary.get("metrics", [])
            if metric.get("artifacts")
        ],
        "configurations": configurations,
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return path


def _escape(value: Any) -> str:
    return html.escape(str(value) if value is not None else "")


#: A settings ``objectId`` is a ~90-character base64 blob. Printed in full it is
#: the widest thing on the line and pushes the field path and the link onto a
#: second row, so it is shortened for display with the full value on hover.
_ID_DISPLAY_LIMIT = 24


def _short_id(value: str) -> tuple[str, str]:
    """``(shown, title)`` for an artifact id."""
    if len(value) <= _ID_DISPLAY_LIMIT:
        return value, ""
    return value[:_ID_DISPLAY_LIMIT] + "\u2026", value


def _badge(text: str, css_class: str) -> str:
    safe_class = css_class if css_class.isidentifier() else "grey"
    return f'<span class="badge {safe_class}">{_escape(text)}</span>'


def _review_counts(metrics: list[dict[str, Any]]) -> dict[str, int]:
    seen: dict[str, set[tuple[str, str]]] = {}
    for metric in metrics:
        for artifact in metric.get("artifacts", []):
            seen.setdefault(str(artifact.get("source", "")), set()).add(
                (str(artifact.get("kind", "")), str(artifact.get("id", "")))
            )
    return {source: len(artifacts) for source, artifacts in seen.items()}


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


def _sources_html(sources: list[dict[str, Any]], metrics: list[dict[str, Any]]) -> str:
    """List only the sources that ask something of the reader.

    A source that was read in full and holds nothing to review needs no row: it
    contributes no work, and printing six such rows buries the one or two that
    do. Those sources are named in a single line underneath, which is what makes
    the review counts trustworthy — they came from the whole tenant.
    """
    review_counts = _review_counts(metrics)
    settled: list[str] = []
    # Keyed by band so classic and platform sources never interleave: a classic configuration
    # is reworked by hand whatever the metric it reads can do, so it is a different pile of
    # work.
    banded: dict[str, str] = {"inventory": "", PLATFORM: "", CLASSIC: ""}
    for source in sources:
        name = source["name"]
        label = _SOURCE_LABELS.get(name, name)
        to_review = review_counts.get(name, 0)
        is_context = name in _CONTEXT_SOURCES
        if not to_review and source["state"] == COMPLETE and not is_context:
            settled.append(label)
            continue
        result = (
            f"<span class='muted'>{_escape(source.get('items_checked', 0))} "
            f"{_CONTEXT_SOURCES[name]}</span>"
            if is_context
            else _result_cell(source, to_review)
        )
        band = "inventory" if is_context else generation_of(name)
        banded[band] += (
            f"<tr><td>{_escape(label)}</td>"
            f"<td>{_badge(source['state'], source['state'])}</td>"
            f"<td>{result}</td>"
            f"<td>{_escape(source.get('reason'))}</td></tr>"
        )

    rows = banded["inventory"]
    for band in (PLATFORM, CLASSIC):
        if not banded[band]:
            continue
        heading = _BAND_LABELS[band] + _BAND_NOTES[band]
        rows += (
                f"<tr class='band'><th colspan='4'>{_escape(heading)}</th></tr>" + banded[band]
        )
    table = ""
    if rows:
        table = (
            "<table><thead><tr><th>Source</th><th>Coverage</th><th>Result</th><th>Note</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
        )
    if settled:
        table += (
            "<p class='muted'>Read in full, nothing to review: "
            f"{_escape(', '.join(settled))}.</p>"
        )
    return table or "<p class='muted'>No source was read.</p>"


def _artifact_html(artifact: dict[str, Any]) -> str:
    """One configuration to review.

    The name is plain text and the link is a small trailing action. A bold blue
    heading-sized link here reads as a section title and breaks the list apart
    once several entries are open at the same time.
    """
    open_link = ""
    if artifact.get("link"):
        open_link = (
            f' &nbsp;&middot;&nbsp; <a class="open-link" href="{_escape(artifact["link"])}" '
            'target="_blank" rel="noopener">Open in tenant &#8599;</a>'
        )
    scope = (
        f" &nbsp;&middot;&nbsp; scope <code>{_escape(artifact['scope'])}</code>"
        if artifact.get("scope")
        else ""
    )
    form = ""
    if artifact.get("key_form") == "classic":
        form = _badge("classic key", "grey")
    category = artifact.get("category") or _CATEGORIES.get(
        artifact.get("source", ""), artifact.get("source", "")
    )
    shown, title = _short_id(str(artifact.get("id") or ""))
    title_attr = f' title="{_escape(title)}"' if title else ""
    return f"""
    <div class="reference">
      <p class="artifact-head">{_badge(category, 'grey')}
        <span class="artifact-name">{_escape(artifact.get('name'))}</span>{form}</p>
      <p class="artifact-meta"><span class="mono-sm"{title_attr}>{_escape(shown)}</span>
        &nbsp;&middot;&nbsp; field
        <code>{_escape(artifact.get('field_path'))}</code>{scope}{open_link}</p>
      <pre class="code-block">{_escape(artifact.get('dql'))}</pre>
    </div>"""


_INLINE_CODE = re.compile(r"`([^`]+)`")
_INLINE_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def _inline(text: str) -> str:
    """Render the ``**bold**`` and ``` `code` ``` the assessment prose is written in.

    The migration wording is authored once, in :mod:`.migration.assess`, and read both from the
    JSON and from this page. Keeping the markers there rather than HTML here means the sentence
    a machine reader sees is the sentence the customer sees.
    """
    escaped = _escape(text)
    escaped = _INLINE_CODE.sub(r"<code>\1</code>", escaped)
    return _INLINE_BOLD.sub(r"<strong>\1</strong>", escaped)


#: Verdict badge per migration outcome. Neutral wording, and no red: a metric that cannot be
#: migrated is a decision to make, not a failure to announce. The verdict says only whether the
#: metric can be rebuilt — whether it still receives data is a separate column.
_MIGRATION_BADGES = {
    "migratable": ("complete", "Can be migrated"),
    "migratable_inexact": ("partial", "Can be migrated, not exactly"),
    "not_migratable": ("grey", "Cannot be migrated"),
    "unknown": ("grey", "Not assessed"),
}

#: Reading order inside every section: what is in use first, what nothing reads last, and a
#: metric with no recent data below all of them. Display only — ``summary.json`` stays sorted
#: by metric key, which is the stable machine order.
_IN_USE = 0
_CLASSIC_ONLY = 1
_UNREFERENCED = 2


def usage_rank(metric: dict[str, Any]) -> int:
    """How much of a claim this metric has on the reader's attention."""
    if not metric.get("artifacts"):
        return _UNREFERENCED
    return _CLASSIC_ONLY if metric.get("review_only") else _IN_USE


def _is_dormant(metric: dict[str, Any]) -> bool:
    return (metric.get("migration") or {}).get("traffic") == "none"


def _metric_order(metric: dict[str, Any]) -> tuple[Any, ...]:
    return (usage_rank(metric), str(metric.get("metric_key") or ""))


def _usage_cell(metric: dict[str, Any]) -> str:
    """The *where is it used* column.

    A column, not a badge: a badge sits after the metric name, so its position moves with the
    length of the name above it and the answer cannot be read down the page.

    It counts **references**, not configurations: what is listed inside the entry is one block
    per place the key appears, and a dashboard naming the same metric in three tiles is three
    things to rework. "1 configuration" against three blocks read as a contradiction.
    """
    if not metric.get("artifacts"):
        return "<span class='muted'>not referenced</span>"
    count = metric.get("reference_count") or metric.get("artifact_count", 0)
    plural = "" if count == 1 else "s"
    if metric.get("review_only"):
        return f"{count} classic reference{plural}"
    return f"<strong>{count} reference{plural}</strong>"


def _data_cell(metric: dict[str, Any]) -> str:
    """The *is it still collecting* column.

    Empty when the metric produced data: on a long-lived environment most metrics are dormant,
    so the exception worth printing is the absence, not the presence.
    """
    migration = metric.get("migration") or {}
    if migration and not migration.get("classic_metric_key"):
        return "<span class='muted'>not defined</span>"
    traffic = migration.get("traffic")
    if traffic == "none":
        return "<span class='muted'>no data</span>"
    if traffic == "recent":
        return ""
    if not metric.get("in_grail_inventory", True):
        # With the definitions read, the metric is known to exist and simply not be forwarded.
        # Without them, that cannot be claimed, and the cell says only what was observed.
        known = "not enabled for Grail" if migration else "not available in Grail"
        return f"<span class='muted'>{known}</span>"
    if traffic == "unknown":
        return "<span class='muted'>data unknown</span>"
    return ""


def _migration_html(metric: dict[str, Any]) -> str:
    """The migration half of one metric entry.

    Ordered by what the reader does with it: what the classic metric measures, then whether it
    still collects, then the verdict and what it costs, then the processor itself. The processor
    comes last and collapsed — it is the artifact, not the argument.
    """
    migration = metric.get("migration") or {}
    verdict = str(migration.get("verdict") or "unknown")
    blocks = ""

    description = migration.get("description") or []
    if description:
        blocks += (
                "<p class='label'>Classic definition</p><p class='artifact-meta'>"
                + "; ".join(_inline(line) for line in description)
                + "</p>"
        )

    if migration.get("traffic_note"):
        blocks += f"<p class='artifact-meta'>{_inline(migration['traffic_note'])}</p>"

    if verdict == "not_migratable":
        rows = "".join(
            f"<tr><td><code>{_escape(blocker.get('element'))}</code></td>"
            f"<td>{_escape(blocker.get('kind'))}</td>"
            f"<td>{_inline(blocker.get('why') or '')}</td></tr>"
            for blocker in migration.get("blockers") or []
        )
        blocks += (
            "<p class='label'>What has no Phase 3 equivalent</p>"
            "<table><thead><tr><th>Classic element</th><th>Part</th><th>Why</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    elif verdict in ("migratable", "migratable_inexact") and migration.get("inexact"):
        blocks += (
                "<div class='callout'><strong>Not an exact migration.</strong> "
                + " ".join(_inline(reason) for reason in migration["inexact"])
                + "</div>"
        )
    elif migration.get("reason"):
        blocks += f"<p class='artifact-meta'>{_inline(migration['reason'])}</p>"

    notes = migration.get("notes") or []
    if notes:
        blocks += "<p class='label'>Before you rely on it</p><ul class='notes'>" + "".join(
            f"<li>{_inline(note)}</li>" for note in notes
        ) + "</ul>"

    processor = migration.get("processor")
    if processor:
        blocks += f"""
        <p class="label">Replacement processor</p>
        <p class="artifact-meta">writes <code>{_escape(migration.get('target_metric_key'))}</code>
          &nbsp;&middot;&nbsp; <code>{_escape(migration.get('processor_file'))}</code></p>"""
        # Printed for every metric that has one, dormant included. It was held back for the
        # dormant ones to keep the page small, and that cost more than it saved: an entry with
        # a file path and no body reads as a processor that was never produced, and the one
        # question the section exists to answer came back twice.
        blocks += f"""
        <details class="json"><summary>Show the processor</summary>
        <pre class="code-block">{_escape(json.dumps(processor, indent=2))}</pre></details>"""

    return blocks


def _metric_html(metric: dict[str, Any]) -> str:
    """One metric, with its configurations split into platform and classic.

    The split survives the regrouping by verdict: a classic SLO cannot read a replacement
    metric, so those references are a different piece of work from the ones that can simply be
    pointed at the new key.
    """
    verdict = str((metric.get("migration") or {}).get("verdict") or "")
    verdict_badge = ""
    if verdict:
        badge_class, badge_label = _MIGRATION_BADGES.get(verdict, ("grey", verdict))
        verdict_badge = _badge(badge_label, badge_class)
    name = (
        f"<span class='artifact-name'>{_escape(metric['name'])}</span>"
        if metric.get("name")
        else ""
    )

    bands = [
        (band, [a for a in metric.get("artifacts", []) if a.get("generation", PLATFORM) == band])
        for band in (PLATFORM, CLASSIC)
    ]
    bands = [(band, entries) for band, entries in bands if entries]
    # The band label earns its place only when the entry actually holds both kinds. On a
    # single-kind metric it repeats what the usage column already said.
    labelled = len(bands) > 1
    blocks = ""
    if bands and not labelled:
        # With the migration verdict above it, the reference list needs a heading of its own or
        # the two run together. When the entry holds both kinds the band headings do that job.
        blocks += f"<p class='label'>Where it is referenced ({len(bands[0][1])})</p>"
    for band, entries in bands:
        if labelled:
            blocks += f"<p class='label'>{_escape(_BAND_LABELS[band])} ({len(entries)})</p>"
        blocks += "".join(_artifact_html(artifact) for artifact in entries)

    definition = ""
    if metric.get("link"):
        definition = (
            f' &nbsp;&middot;&nbsp; <a class="open-link" href="{_escape(metric["link"])}" '
            'target="_blank" rel="noopener">Open metric definition &#8599;</a>'
        )
    return f"""
    <details class="group">
      <summary>
        <span class="col-verdict">{verdict_badge}</span>
        <code class="col-key">{_escape(metric.get('metric_key'))}</code>
        <span class="col-name">{name}</span>
        <span class="col-usage">{_usage_cell(metric)}</span>
        <span class="col-data">{_data_cell(metric)}</span></summary>
      <div class="group-body">
        <p class="artifact-meta">classic key
          <code>{_escape(metric.get('classic_metric_key'))}</code>{definition}</p>
        {_migration_html(metric)}
        {blocks}
      </div>
    </details>"""


def _not_in_grail(metric: dict[str, Any]) -> bool:
    return not metric.get("in_grail_inventory", True)


def _metric_list(metrics: list[dict[str, Any]], window: str) -> str:
    """Render one section's metrics, with the ones that need no decision now folded away.

    Two blocks come off the bottom of every section. A metric with no recent data needs no
    decision now, and on a long-lived environment the dormant ones are usually the majority. A
    metric that was never enabled for Grail is a different case with the same effect on
    reading order: it cannot be measured from here, so it interrupts a list the reader is
    going through by traffic. Both keep their verdict and their processor — they are simply
    the last thing in their section, one click away.
    """
    ordered = sorted(metrics, key=_metric_order)
    live = [
        metric
        for metric in ordered
        if not _is_dormant(metric) and not _not_in_grail(metric)
    ]
    outside_grail = [
        metric for metric in ordered if _not_in_grail(metric) and not _is_dormant(metric)
    ]
    dormant = [metric for metric in ordered if _is_dormant(metric)]
    body = "".join(_metric_html(metric) for metric in live)
    if outside_grail:
        body += f"""
    <details class="bulk">
      <summary>{len(outside_grail)} metric(s) not enabled for Grail</summary>
      <div class="bulk-body">
        <p class="muted">The classic definition exists, but the metric is not forwarded to
           Grail, so there is no <code>service.&lt;key&gt;</code> series and whether it still
           collects could not be checked here. The verdict below still holds.</p>
        {"".join(_metric_html(metric) for metric in outside_grail)}
      </div>
    </details>"""
    if dormant:
        body += f"""
    <details class="bulk">
      <summary>{len(dormant)} metric(s) with no data in the last {_escape(window)}</summary>
      <div class="bulk-body">
        <p class="muted">Nothing here is producing data today, so there is nothing for a
           replacement to measure. Decide whether each metric is still wanted before migrating
           it.</p>
        {"".join(_metric_html(metric) for metric in dormant)}
      </div>
    </details>"""
    return body


def _migration_lead(summary: dict[str, Any]) -> str:
    """The one line that says how much of this environment can be migrated.

    Leads on what can be acted on, in the same shape as the per-source review counts: the
    actionable number first, the remainder behind it.
    """
    migration = summary.get("migration") or {}
    counts = migration.get("totals") or {}
    if not counts.get("assessed"):
        return ""
    parts = [
        f"<strong>{counts['migratable_total']} of {counts['assessed']} calculated service "
        "metric(s) can be migrated</strong>"
    ]
    if counts.get("not_migratable"):
        parts.append(f"{counts['not_migratable']} cannot")
    dormant = counts.get("no_traffic", 0)
    if dormant:
        parts.append(
            f"{dormant} received no data in the last "
            f"{_escape(migration.get('traffic_window'))}"
        )
    incomplete = ""
    if not migration.get("complete"):
        incomplete = (
            " <span class='warn'>&middot; the definition read was incomplete, so this split is "
            "not exhaustive</span>"
        )
    return (
            "<p class='muted'>"
            + " <span class='muted'>&middot;</span> ".join(parts)
            + incomplete
            + "</p>"
    )


def _section(
        title: str,
        body: str,
        *,
        intro: str = "",
        note: str = "",
        open_: bool = False,
) -> str:
    """A page section the reader can close.

    Every section on this page is collapsible, and the summary carries enough of the answer
    that a closed one is still worth reading: a report of a few hundred metrics is only usable
    if the reader chooses what to open.
    """
    intro_html = f"<p class='muted'>{intro}</p>" if intro else ""
    note_html = f"<span class='section-meta'>{note}</span>" if note else ""
    return f"""
  <details class="section"{' open' if open_ else ''}>
    <summary>{title}{note_html}</summary>
    <div class="section-body">{intro_html}{body}</div>
  </details>"""


def _section_note(metrics: list[dict[str, Any]]) -> str:
    """The count breakdown printed on a closed section."""
    parts = []
    in_use = sum(1 for metric in metrics if usage_rank(metric) == _IN_USE)
    classic = sum(1 for metric in metrics if usage_rank(metric) == _CLASSIC_ONLY)
    dormant = sum(1 for metric in metrics if _is_dormant(metric))
    if in_use:
        parts.append(f"{in_use} in use")
    if classic:
        parts.append(f"{classic} classic only")
    unreferenced = len(metrics) - in_use - classic
    if unreferenced:
        parts.append(f"{unreferenced} not referenced")
    if dormant:
        parts.append(f"{dormant} without data")
    outside_grail = sum(
        1 for metric in metrics if _not_in_grail(metric) and not _is_dormant(metric)
    )
    if outside_grail:
        parts.append(f"{outside_grail} not enabled for Grail")
    return " &middot; ".join(parts)


#: Reading order of the feature groups: the order the sources are declared in, platform ones
#: first. A classic configuration is reworked by hand whatever the metric it reads can do, so it
#: is a different pile of work and sits at the bottom.
_FEATURE_ORDER = {name: index for index, name in enumerate(_SOURCE_LABELS)}


def _feature_order(source: str) -> tuple[Any, ...]:
    return (
        generation_of(source) == CLASSIC,
        _FEATURE_ORDER.get(source, len(_FEATURE_ORDER)),
        source,
    )


def _usage_listing(metrics: list[dict[str, Any]]) -> tuple[str, int]:
    """Every configuration that reads a calculated service metric, grouped by feature.

    One line per configuration rather than per metric: the sections below already say what can
    be done with a metric, and what this section is for is getting to the dashboard or the SLO
    itself. So the row carries the name, the link and the keys it reads, and the groups are the
    features the work is scheduled in.

    Returns the table and the number of configurations in it.
    """
    configurations: dict[tuple[str, str, str], dict[str, Any]] = {}
    for metric in metrics:
        key = str(metric.get("metric_key") or "")
        for artifact in metric.get("artifacts", []):
            ident = (
                str(artifact.get("source") or ""),
                str(artifact.get("kind") or ""),
                str(artifact.get("id") or ""),
            )
            entry = configurations.setdefault(
                ident,
                {
                    "name": str(artifact.get("name") or ""),
                    "link": str(artifact.get("link") or ""),
                    "keys": [],
                },
            )
            if key and key not in entry["keys"]:
                entry["keys"].append(key)
    if not configurations:
        return "", 0
    grouped: dict[str, list[dict[str, Any]]] = {}
    for (source, _kind, artifact_id), entry in configurations.items():
        entry["id"] = artifact_id
        grouped.setdefault(source, []).append(entry)
    rows = ""
    for source in sorted(grouped, key=_feature_order):
        entries = sorted(grouped[source], key=lambda e: (e["name"].lower(), e["id"]))
        heading = f"{_SOURCE_LABELS.get(source, source)} ({len(entries)})"
        if generation_of(source) == CLASSIC:
            heading += _BAND_NOTES[CLASSIC]
        rows += f"<tr class='band'><th colspan='2'>{_escape(heading)}</th></tr>"
        for entry in entries:
            link = ""
            if entry["link"]:
                link = (
                    f' &nbsp;&middot;&nbsp; <a class="open-link" href="{_escape(entry["link"])}" '
                    'target="_blank" rel="noopener">Open in tenant &#8599;</a>'
                )
            keys = ", ".join(f"<code>{_escape(key)}</code>" for key in sorted(entry["keys"]))
            rows += f"<tr><td>{_escape(entry['name'])}{link}</td><td>{keys}</td></tr>"
    return (
        "<table><thead><tr><th>Configuration</th><th>Reads</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>",
        len(configurations),
    )


def _stale_html(summary: dict[str, Any]) -> str:
    """References to metric keys the environment does not define.

    Not in the metric list: a metric that does not exist has no usage to report and nothing to
    migrate, and listing it there was the thing that made the list wrong. Not silent either —
    the configuration is reading a key that returns nothing today.
    """
    stale = summary.get("stale_references") or []
    if not stale:
        return ""
    rows = ""
    for entry in stale:
        link = ""
        if entry.get("link"):
            link = (
                f' &nbsp;&middot;&nbsp; <a class="open-link" href="{_escape(entry["link"])}" '
                'target="_blank" rel="noopener">Open in tenant &#8599;</a>'
            )
        keys = ", ".join(f"<code>{_escape(key)}</code>" for key in entry.get("keys") or [])
        rows += (
            f"<tr><td>{_badge(entry.get('category') or '', 'grey')}"
            f"{_escape(entry.get('name'))}{link}</td><td>{keys}</td></tr>"
        )
    return f"""
  <details class="bulk">
    <summary>{len(stale)} configuration(s) read a calculated service metric this environment
      does not define</summary>
    <div class="bulk-body">
      <p class="muted">These keys belong to metrics that are not defined here — deleted at some
         point, most likely. Those configurations return no data today, before Phase 3 changes
         anything, so they are not counted as usage above.</p>
      <table><thead><tr><th>Configuration</th><th>Key it reads</th></tr></thead>
        <tbody>{rows}</tbody></table>
    </div>
  </details>
"""


def _processor_coverage(summary: dict[str, Any]) -> str:
    """Which metrics got a processor, and where the files are.

    A paragraph on the page rather than a line inside a section: the sections are grouped by
    verdict rather than by whether a file was written, which made a file that exists look like
    one that was never produced, and the answer has to be readable without opening anything.

    Every count here spans both migratable sections, so each one says so: the same numbers
    appear per section on the section headers, and the two were read as one.
    """
    counts = (summary.get("migration") or {}).get("totals") or {}
    total = counts.get("migratable_total") or 0
    if not total:
        return ""
    exact = counts.get("migratable", 0)
    inexact = counts.get("migratable_inexact", 0)
    dormant = counts.get("migratable_total", 0) - (counts.get("migratable_with_data", 0) or 0)
    split = [f"<strong>{total} processor file(s)</strong>, one per metric that can be migrated"]
    if inexact:
        split.append(f"{exact} an exact migration, {inexact} not")
    if dormant:
        split.append(f"{dormant} across both, for a metric with no recent data")
    return (
            '<p class="description">'
            + " <span class='muted'>&middot;</span> ".join(split)
            + ". A metric that cannot be migrated has none. Every one of them is shown in its own "
              "entry below, under <em>Show the processor</em>, and written to a file in "
              "<code>processors/</code>, next to this page.</p>"
    )


def _decisions_html(summary: dict[str, Any]) -> str:
    """Behaviour differences that hold across every migrated metric.

    Stated once, before the metric list. Repeating them per entry buries the part of an entry
    that is specific to that metric. How many processors there are is not in here: that is a
    count, it answers a question asked on the way in, and it sits in the paragraph above the
    sections — see :func:`_processor_coverage`.
    """
    decisions = (summary.get("migration") or {}).get("decisions") or []
    if not decisions:
        return ""
    items = "".join(f"<li>{_inline(text)}</li>" for text in decisions)
    return _section(
        "What a migrated metric does differently",
        f'<ul class="notes">{items}</ul>',
        intro=(
            "A migrated metric is not a drop-in replacement. These differences apply to every "
            "one of them."
        ),
        note=f"{len(decisions)} point(s)",
        open_=False,
    )


def _reasons_html(summary: dict[str, Any]) -> str:
    """The shape of what cannot be migrated, grouped by root cause."""
    reasons = (summary.get("migration") or {}).get("reasons") or []
    if not reasons:
        return ""
    rows = ""
    for reason in reasons:
        elements = ", ".join(f"<code>{_escape(name)}</code>" for name in reason["elements"])
        if elements == f"<code>{_escape(reason['family'])}</code>":
            elements = "<span class='muted'>&mdash;</span>"
        rows += (
            f"<tr><td>{_escape(reason['family'])}</td><td>{elements}</td>"
            f"<td>{reason['metrics']}</td><td>{_inline(reason.get('why') or '')}</td></tr>"
        )
    return _section(
        "Why some metrics cannot be migrated",
        "<table><thead><tr><th>Root cause</th><th>Classic elements</th><th>Metrics</th>"
        f"<th>Why</th></tr></thead><tbody>{rows}</tbody></table>",
        intro=(
            "Each classic element below has no Phase 3 equivalent, so a metric that uses one "
            "cannot be migrated from spans. The metric entries name the element that stops "
            "each of them individually."
        ),
        note=f"{len(reasons)} root cause(s)",
    )


#: The metric sections, in the order the reader works through them: what can be taken away
#: first, what needs a decision last. Every entry inside a section carries the same verdict, so
#: the ordering *within* one is by usage — see :func:`usage_rank`.
#:
#: The last field is whether the section starts open. Only *Can be migrated* does, on the whole
#: page: several open sections at once is a wall of entries with no starting point.
_VERDICT_SECTIONS = (
    (
        "migratable",
        "Can be migrated",
        "Every part of the classic definition has an equivalent on spans. Each one comes with "
        "a processor in <code>processors/</code>.",
        True,
    ),
    (
        "migratable_inexact",
        "Can be migrated, not exactly",
        "The replacement measures a little more than the classic metric did. Each entry says "
        "which part of the definition could not be carried over, and comes with a processor in "
        "<code>processors/</code> like the exact ones do.",
        False,
    ),
    (
        "not_migratable",
        "Cannot be migrated",
        "Part of the classic definition has no equivalent on spans. Each entry names it, and "
        "the root causes are grouped above.",
        False,
    ),
    (
        "unknown",
        "Not assessed",
        "No verdict could be given: the classic definition could not be read, or it uses "
        "something the bundled mapping is missing.",
        False,
    ),
)


def _verdict_sections(metrics: list[dict[str, Any]], window: str) -> str:
    """The metric list, grouped by what can be done with each metric."""
    out = ""
    for verdict, title, intro, open_ in _VERDICT_SECTIONS:
        entries = [
            metric
            for metric in metrics
            if str((metric.get("migration") or {}).get("verdict") or "") == verdict
        ]
        if not entries:
            continue
        out += _section(
            f"{_escape(title)} ({len(entries)})",
            _metric_list(entries, window),
            intro=intro,
            note=_section_note(entries),
            open_=open_,
        )
    return out


def _usage_sections(metrics: list[dict[str, Any]], window: str) -> str:
    """The grouping used when no migration verdict was computed (``--skip-migration``).

    Without a verdict there is nothing to group by but usage, which is the report this scanner
    produced before it assessed anything.
    """
    out = ""
    platform = [m for m in metrics if usage_rank(m) == _IN_USE]
    classic = [m for m in metrics if usage_rank(m) == _CLASSIC_ONLY]
    unreferenced = [m for m in metrics if usage_rank(m) == _UNREFERENCED]
    if platform:
        out += _section(
            f"Referenced by platform configurations ({len(platform)})",
            _metric_list(platform, window),
            intro="Dashboards, notebooks, SLOs, guardians and Davis custom alerts.",
            open_=True,
        )
    if classic:
        out += _section(
            f"Referenced only by classic configurations ({len(classic)})",
            _metric_list(classic, window),
            intro=(
                "Reached only from classic SLOs or metric events, which cannot read a "
                "replacement metric. Each one has to be reworked by hand."
            ),
            open_=True,
        )
    if unreferenced:
        out += _section(
            f"Defined on this environment, not referenced ({len(unreferenced)})",
            _metric_list(unreferenced, window),
            intro=(
                "No configuration names these. They are listed because a reference is not the "
                "only way a metric is read — an ad-hoc query leaves nothing behind."
            ),
        )
    return out


#: The opening paragraph: what Phase 3 removes, and what that does to a configuration that reads
#: one of these metrics. Stated in consequences the customer recognises rather than in alarm
#: vocabulary, and phrased so it stays true when nothing was found.
_DESCRIPTION = """<p class="description">
    Phase 3 stops calculated service metrics from receiving new data. Any configuration that
    reads one &mdash; by its Grail key <code>service.&lt;key&gt;</code> or its classic key
    <code>calc:service.&lt;key&gt;</code> &mdash; stops returning data once Phase 3 is applied:
    the objective stops evaluating, the alert stops firing, the tile stays empty. The entries
    below are the ones found on this environment; each one has to be rebuilt on a metric that
    still produces data after the cutover.
  </p>"""


def generate_html(summary: dict[str, Any]) -> str:
    verdict = summary.get("verdict", "incomplete")
    verdict_class, verdict_label = _VERDICT_BADGES.get(verdict, ("grey", verdict))
    metrics = summary.get("metrics", [])
    assessed = bool((summary.get("migration") or {}).get("assessed"))
    # With no migration assessment there is no verdict column, and an empty first track would
    # push every metric key across the page for nothing. The usage-only report keeps its old
    # layout.
    layout = "" if assessed else "no-verdict"
    note = summary.get("verdict_note")
    # The usage verdict is about *references* only, and it is printed next to a metric list that
    # is no longer usage-gated. Without this, an environment where nothing references a
    # calculated service metric reads as "nothing to do" above a list of metrics that stop
    # working anyway.
    if verdict == "clean" and assessed:
        verdict_label = "No configuration references one"
        note = (
            "No dashboard, notebook, SLO, guardian or alert on this environment references a "
            "calculated service metric. The metrics themselves still stop receiving data, so "
            "they are listed below with what can replace them."
        )
    window = str((summary.get("migration") or {}).get("traffic_window") or "")

    referenced = sum(1 for metric in metrics if metric.get("artifacts"))
    usage_section = ""
    listing, configurations = _usage_listing(metrics)
    if listing:
        usage_section = _section(
            f"Where these metrics are used ({configurations} configuration(s))",
            listing,
            intro=(
                "Every configuration that reads a calculated service metric, with a link to it. "
                "Classic ones come last: they cannot be pointed at a replacement metric. What "
                "can be done with each metric is in the sections below."
            ),
            note=f"{referenced} metric(s)",
            # Open only when there is no verdict to read instead: a fresh migration report opens
            # on *Can be migrated* and nothing else, so the first thing on screen is the work.
            open_=not assessed,
        )
    elif assessed:
        usage_section = (
            "<p class='muted'>No dashboard, notebook, SLO, guardian or alert on this "
            "environment references a calculated service metric.</p>"
        )

    link_warning = ""
    linked = [artifact for metric in metrics for artifact in metric.get("artifacts", [])]
    if linked and not any(artifact.get("link") for artifact in linked):
        link_warning = (
            '<div class="callout"><strong>Configuration links unavailable.</strong> '
            'Re-render this report with '
            '<code>--ui-url https://&lt;environment&gt;.apps.dynatrace.com</code>.</div>'
        )
    warning = ""
    if summary.get("incomplete_sources"):
        warning = (
                '<div class="callout"><strong>Coverage is incomplete:</strong> '
                + _escape(
            ", ".join(
                _SOURCE_LABELS.get(name, name) for name in summary["incomplete_sources"]
            )
        )
                + ". Re-run before treating missing findings as no usage.</div>"
        )
    coverage = _section(
        "What was read",
        _sources_html(summary.get("sources", []), metrics) + _stale_html(summary),
        intro=(
            "Where the counts above come from. A source read in full with nothing to review "
            "is named in one line rather than given a row."
        ),
        note=f"{len(summary.get('sources') or [])} source(s)",
        )
    body = (
        _verdict_sections(metrics, window) if assessed else _usage_sections(metrics, window)
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Calculated Service Metric Usage - Phase 3 Report</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 24px; background: #f7f8fa; color: #202124; }}
    h1 {{ margin-bottom: 4px; }}
    .muted {{ color: #68707a; font-size: .85rem; }}
    p.muted {{ margin: 0 0 8px; }}
    .warn {{ color: #8a5b00; font-weight: 600; }}
    .label {{ font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; color: #68707a; margin: 14px 0 2px; }}
    .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: .75rem; font-weight: 600; margin-right: 6px; }}
    .complete {{ background: #d5f5e3; color: #12613b; }} .partial {{ background: #fff1b8; color: #704f00; }}
    .failed {{ background: #fde0df; color: #8f1d18; }} .grey {{ background: #e9edf2; color: #46515d; }}
    .blue {{ background: #dbeafe; color: #1e40af; }}
    table {{ width: 100%; border-collapse: collapse; background: white; font-size: .86rem; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #e1e5ea; vertical-align: top; }}
    th {{ background: #edf0f3; font-size: .76rem; text-transform: uppercase; }}
    tr.band th {{ background: #e3e8ee; color: #3a444f; letter-spacing: .04em; }}
    tr:last-child td {{ border-bottom: none; }}
    details.section {{ margin: 26px 0 0; }}
    details.section > summary {{ display: flex; align-items: baseline; gap: 10px; font-size: 1.15rem; font-weight: 700; border-bottom: 2px solid #dde1e6; padding-bottom: 5px; cursor: pointer; user-select: none; list-style: none; }}
    details.section > summary::-webkit-details-marker {{ display: none; }}
    /* A flex summary drops the native marker, and a section header that cannot be told from
       a plain heading is a section nobody opens. */
    details.section > summary::before {{ content: "▸"; color: #98a1ab; font-weight: 400; }}
    details.section[open] > summary::before {{ content: "▾"; }}
    details.section > summary:hover {{ color: #175cd3; }}
    .section-meta {{ margin-left: auto; font-size: .78rem; font-weight: 400; color: #68707a; }}
    .section-body {{ padding-top: 10px; }}
    details.group {{ background: white; border: 1px solid #dce1e6; border-radius: 8px; margin: 9px 0; overflow: hidden; }}
    details.group > summary {{ display: grid; grid-template-columns: 13.5em minmax(0, auto) minmax(0, 1fr) 11em 9.5em; align-items: baseline; gap: 4px 10px; padding: 12px 14px; cursor: pointer; font-size: .9rem; user-select: none; }}
    .col-verdict {{ white-space: nowrap; }}
    .col-verdict .badge {{ margin-right: 0; }}
    .col-key {{ white-space: nowrap; }}
    .col-name {{ min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .col-usage {{ font-size: .78rem; color: #68707a; white-space: nowrap; }}
    .col-data {{ font-size: .78rem; color: #68707a; line-height: 1.35; }}
    .col-usage strong {{ color: #202124; }}
    @media (max-width: 1000px) {{ details.group > summary {{ grid-template-columns: 13.5em minmax(0, 1fr); }} }}
    body.no-verdict .col-verdict {{ display: none; }}
    body.no-verdict details.group > summary {{ grid-template-columns: minmax(0, auto) minmax(0, 1fr) 11em 9.5em; }}
    details.group > summary:hover, details.group[open] > summary {{ background: #f7f8fa; }}
    .group-body {{ border-top: 1px solid #e2e6ea; padding: 2px 16px 14px; }}
    .group-body table {{ font-size: .8rem; }}
    .group-body th {{ width: 150px; }}
    .artifact-name {{ font-size: .9rem; font-weight: 600; }}
    .artifact-head {{ margin: 0; }}
    .artifact-meta {{ color: #68707a; font-size: .78rem; margin: 3px 0 0; }}
    .mono-sm {{ color: #68707a; font-size: .75rem; font-family: ui-monospace, monospace; }}
    .reference {{ border-left: 3px solid #dfe3e8; padding: 2px 0 6px 12px; margin: 10px 0 0; }}
    code {{ font-family: ui-monospace, monospace; background: #edf0f3; padding: 1px 4px; border-radius: 3px; }}
    pre.code-block {{ background: #20232b; color: #edf2f7; padding: 12px 14px; border-radius: 5px; font-size: .75rem; line-height: 1.5; white-space: pre-wrap; word-break: break-word; overflow-x: auto; margin: 4px 0 0; }}
    a {{ color: #175cd3; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
    a.open-link {{ font-size: .78rem; white-space: nowrap; }}
    .callout {{ background: white; border-left: 4px solid #e0a000; padding: 12px 15px; margin: 16px 0; font-size: .85rem; }}
    .info {{ border-left-color: #3976d3; }}
    .description {{ background: white; border: 1px solid #dce1e6; border-radius: 8px; padding: 13px 16px; margin: 16px 0 0; font-size: .9rem; line-height: 1.6; color: #39424d; }}
    .description p {{ margin: 0 0 10px; }} .description p:last-child {{ margin-bottom: 0; }}
    ul.notes {{ margin: 6px 0 0; padding-left: 18px; font-size: .85rem; color: #39424d; }}
    ul.notes li {{ margin: 5px 0; line-height: 1.55; }}
    .group-body ul.notes {{ font-size: .8rem; }}
    details.json > summary {{ cursor: pointer; font-size: .78rem; color: #175cd3; margin: 4px 0 0; user-select: none; }}
    details.json[open] > summary {{ margin-bottom: 4px; }}
    details.bulk {{ margin: 9px 0; }}
    details.bulk > summary {{ cursor: pointer; padding: 10px 14px; background: #eef1f4; border: 1px dashed #ccd3da; border-radius: 8px; font-size: .84rem; color: #46515d; user-select: none; }}
    details.bulk > summary:hover {{ background: #e7ebef; }}
    .bulk-body {{ padding: 4px 0 0 14px; border-left: 2px solid #e1e5ea; margin-top: 6px; }}
  </style>
</head>
<body class="{layout}">
  <h1>Calculated Service Metric Usage - Phase 3 Report</h1>
  <p class="muted">{_badge(verdict_label, verdict_class)} {_escape(summary.get('tenant', {}).get('label'))}; generated {_escape(summary.get('generated_at'))}</p>
  <p class="muted">{_escape(note)}</p>
  {_migration_lead(summary)}
  {_DESCRIPTION}
  {warning}
  {link_warning}
{coverage}
{usage_section}
{_decisions_html(summary)}{_reasons_html(summary)}
{_processor_coverage(summary)}
{body}
  <div class="callout info">Each entry keeps the original query, selector, or expression so it can be located and reworked by hand. A configuration written against the classic <code>calc:service.*</code> key is marked as such. Every replacement processor is a file in <code>processors/</code>. Nothing in this report was written to the tenant.</div>
</body>
</html>"""


def write_html(output_dir: Path, summary: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "report.html"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(generate_html(summary), encoding="utf-8")
    temporary.replace(path)
    return path
