#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External Services Report

Reads the JSON report and detail files produced by scan_external_services.py
and generates a consolidated JSON + HTML report grouped by config type
(Settings, SLOs, Notebooks, Dashboards, Third-party services).

Usage:
    python external_services_report.py --tenant https://abc12345.apps.dynatrace.com
    python external_services_report.py --tenant https://abc12345.apps.dynatrace.com --shared-dir /path/to/shared-scripts

Output is written to the shared-scripts directory:
    external_services_report_{tenant_name}.json
    external_services_report_{tenant_name}.html

Exit codes:
    0  completed successfully
    1  error
"""
import argparse
import base64
import hashlib
import html
import json
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

if sys.version_info < (3, 7):
    sys.exit("Python 3.7 or later is required.")

_STYLE_CSS = (
    "  body { font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; max-width: 1400px; }\n"
    "  h1   { font-size: 1.4rem; margin-bottom: 0.25rem; }\n"
    "  .meta { color: #666; font-size: 0.85rem; margin-bottom: 2rem; }\n"
    "  details { border: 1px solid #ddd; border-radius: 6px; margin-bottom: 1.25rem; }\n"
    "  details[open] summary { border-bottom: 1px solid #ddd; border-radius: 6px 6px 0 0; }\n"
    "  summary { cursor: pointer; font-size: 1.05rem; font-weight: 600; padding: 0.75rem 1.25rem;\n"
    "             background: #f8f8f8; border-radius: 6px; list-style: none;\n"
    "             display: flex; align-items: center; gap: 0.5rem; user-select: none; }\n"
    "  summary::-webkit-details-marker { display: none; }\n"
    "  summary::before { content: '▶'; font-size: 0.75rem; transition: transform 0.15s;\n"
    "                    display: inline-block; color: #888; }\n"
    "  details[open] summary::before { transform: rotate(90deg); }\n"
    "  .count { font-weight: normal; color: #666; font-size: 0.85rem; margin-left: auto; }\n"
    "  .section-body { padding: 1rem 1.25rem; }\n"
    "  h3   { font-size: 0.95rem; font-weight: 600; margin: 1rem 0 0.4rem; color: #333; }\n"
    "  h3:first-child { margin-top: 0; }\n"
    "  .svc-id { font-family: monospace; font-size: 0.82rem; color: #555; white-space: nowrap; }\n"
    "  table.refs { border-collapse: collapse; width: 100%; font-size: 0.875rem; table-layout: fixed; }\n"
    "  table.refs th { background: #f4f4f4; text-align: left; padding: 0.4rem 0.75rem;\n"
    "                   border-bottom: 2px solid #ccc; white-space: nowrap; overflow: hidden;\n"
    "                   text-overflow: ellipsis; }\n"
    "  table.refs td { padding: 0.35rem 0.75rem; border-bottom: 1px solid #eee;\n"
    "                   vertical-align: top; overflow: hidden; text-overflow: ellipsis; }\n"
    "  table.refs tr:last-child td { border-bottom: none; }\n"
    "  table.refs tr:hover td { background: #fafafa; }\n"
    "  .schema { font-family: monospace; color: #0055aa; white-space: nowrap; }\n"
    "  .none      { color: #888; font-style: italic; }\n"
    "  .description { font-size: 0.9rem; color: #444; line-height: 1.6; margin-bottom: 1.5rem;\n"
    "                  max-width: 860px; }\n"
    "  .description code { font-family: monospace; font-size: 0.85em; background: #f0f0f0;\n"
    "                       padding: 0.1em 0.3em; border-radius: 3px; }\n"
    "  .banner    { background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px;\n"
    "               padding: 0.75rem 1rem; margin-bottom: 1.5rem; font-size: 0.875rem; }\n"
    "  .banner b  { color: #856404; }\n"
    "  .gen2-badge { display: inline-block; background: #e8f0fe; color: #1a56db; font-size: 0.75rem;\n"
    "                padding: 0.1rem 0.5rem; border-radius: 3px; font-weight: 600; }\n"
    "  .gen3-badge { display: inline-block; background: #def7ec; color: #03543f; font-size: 0.75rem;\n"
    "                padding: 0.1rem 0.5rem; border-radius: 3px; font-weight: 600; }\n"
    "  .doc-badge  { display: inline-block; background: #fdf2f8; color: #9d174d; font-size: 0.75rem;\n"
    "                padding: 0.1rem 0.5rem; border-radius: 3px; font-weight: 600; }\n"
)


def _style_csp_hash():
    content = "\n" + _STYLE_CSS + "\n"
    digest = hashlib.sha256(content.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


_SRG_SCHEMA = "app:dynatrace.site.reliability.guardian:guardians"


def _normalize_tenant_url(url):
    """Strip the 'apps' subdomain from a Dynatrace platform URL.

    https://abc.apps.dynatrace.com      -> https://abc.dynatrace.com
    """
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.replace(".apps.", ".")
    return parsed._replace(netloc=netloc).geturl()


def _settings_url(base_url, object_id):
    if not object_id:
        return None
    return f"{base_url.rstrip('/')}/ui/settings?objectId={object_id}"


def _notebook_url(base_url, doc_id):
    if not doc_id:
        return None
    return f"{base_url.rstrip('/')}/ui/apps/dynatrace.notebooks/notebook/{doc_id}"


def _dashboard_url(base_url, doc_id):
    if not doc_id:
        return None
    return f"{base_url.rstrip('/')}/ui/apps/dynatrace.dashboards/dashboard/{doc_id}"


def _service_url(base_url, service_id):
    if not service_id:
        return None
    return f"{base_url.rstrip('/')}/ui/apps/dynatrace.classic.services/ui/entity/{service_id}"


def _srg_url(base_url, object_id):
    if not object_id:
        return None
    qs = urllib.parse.urlencode({"gtf": "-2h", "gf": "all", "id": object_id})
    return f"{base_url.rstrip('/')}/ui/apps/dynatrace.classic.settings/ui/settings/app:dynatrace.site.reliability.guardian:guardians?{qs}"


def _slo_url(base_url, slo_id):
    if not slo_id:
        return None
    return f"{base_url.rstrip('/')}/ui/apps/dynatrace.service.level.objectives/slo/{slo_id}"


def _load_report(shared_dir, tenant_name):
    path = shared_dir / f"report_{tenant_name}.json"
    if not path.exists():
        print(f"Error: report file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_details(details_dir, tenant_name):
    """Return (settings_by_schema, slos, anomaly_detectors, srgs, nb_by_id, dash_by_id, third_party)."""
    settings_by_schema: dict = {}
    slos: list = []
    anomaly_detectors: list = []
    srgs: list = []
    nb_by_id: dict = {}
    dash_by_id: dict = {}
    third_party = []

    if not details_dir.exists():
        return settings_by_schema, slos, anomaly_detectors, srgs, nb_by_id, dash_by_id, third_party

    for detail_file in sorted(details_dir.iterdir()):
        if detail_file.suffix != ".json":
            continue
        name = detail_file.name

        if name == f"THIRD_PARTY_{tenant_name}.json":
            with open(detail_file, encoding="utf-8") as fh:
                third_party = json.load(fh)

        elif name == f"SLO_{tenant_name}.json":
            with open(detail_file, encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, list):
                slos = raw

        elif name == f"ANOMALY_DETECTOR_{tenant_name}.json":
            with open(detail_file, encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, list):
                anomaly_detectors = raw

        elif name.startswith("SETTINGS_") and name.endswith(f"_{tenant_name}.json"):
            with open(detail_file, encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, list):
                for entry in raw:
                    schema_id = entry.get("_schema_id") or ""
                    if schema_id == _SRG_SCHEMA:
                        srgs.append({
                            "objectId":        entry.get("objectId"),
                            "value":           entry.get("value"),
                            "service_id":      entry.get("service_id"),
                            "service_name":    entry.get("service_name"),
                            "service_type":    entry.get("service_type"),
                            "service_sub_type": entry.get("service_sub_type"),
                        })
                    else:
                        settings_by_schema.setdefault(schema_id, []).append({
                            "objectId":        entry.get("objectId"),
                            "value":           entry.get("value"),
                            "service_id":      entry.get("service_id"),
                            "service_name":    entry.get("service_name"),
                            "service_type":    entry.get("service_type"),
                            "service_sub_type": entry.get("service_sub_type"),
                        })

        elif name.startswith("NOTEBOOK_") and name.endswith(f"_{tenant_name}.json"):
            with open(detail_file, encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, list):
                for entry in raw:
                    doc_id = entry.get("_doc_id") or ""
                    if doc_id not in nb_by_id:
                        nb_by_id[doc_id] = {"services": []}
                    nb_by_id[doc_id]["services"].append({
                        "service_id":      entry.get("service_id"),
                        "service_name":    entry.get("service_name"),
                        "service_type":    entry.get("service_type"),
                        "service_sub_type": entry.get("service_sub_type"),
                    })

        elif name.startswith("DASHBOARD_") and name.endswith(f"_{tenant_name}.json"):
            with open(detail_file, encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, list):
                for entry in raw:
                    doc_id = entry.get("_doc_id") or ""
                    if doc_id not in dash_by_id:
                        dash_by_id[doc_id] = {"services": []}
                    dash_by_id[doc_id]["services"].append({
                        "service_id":      entry.get("service_id"),
                        "service_name":    entry.get("service_name"),
                        "service_type":    entry.get("service_type"),
                        "service_sub_type": entry.get("service_sub_type"),
                    })

    return settings_by_schema, slos, anomaly_detectors, srgs, nb_by_id, dash_by_id, third_party


def _setting_name(entry):
    value = entry.get("value") or {}
    return value.get("name") or value.get("summary") or entry.get("objectId") or ""


def _format_service(s):
    """Return 'ServiceName (TYPE / sub_type)' or fall back to service_id."""
    label = s.get("service_name") or s.get("service_id") or ""
    svc_type = s.get("service_type") or ""
    svc_sub  = s.get("service_sub_type") or ""
    type_part = svc_type + (f" / {svc_sub}" if svc_sub else "")
    return f"{label} ({type_part})" if type_part else label


def _type_str(entry):
    svc_type = entry.get("service_type") or ""
    svc_sub  = entry.get("service_sub_type") or ""
    return svc_type + (f" / {svc_sub}" if svc_sub else "")


def _details_block(title, badge_class, count_label, inner_html, open_by_default=True):
    open_attr = " open" if open_by_default else ""
    return (
        f"<details{open_attr}>"
        f"<summary>{title} <span class='count'>{count_label}</span></summary>"
        f"<div class='section-body'>{inner_html}</div>"
        f"</details>"
    )


def _render_settings_inner(settings_by_schema, settings_base_url, tenant_url):
    if not settings_by_schema:
        return "<p class='none'>None found.</p>"
    schema_blocks = []
    for schema_id, entries in settings_by_schema.items():
        schema_h = html.escape(schema_id)
        rows = []
        for entry in entries:
            label     = html.escape(_setting_name(entry))
            svc_name  = html.escape(entry.get("service_name") or "")
            raw_svc_id = entry.get("service_id") or ""
            type_cell = html.escape(_type_str(entry))
            url       = _settings_url(settings_base_url, entry.get("objectId"))
            name_cell = f"<a href='{html.escape(url)}'>{label}</a>" if url else label
            svc_url   = _service_url(tenant_url, raw_svc_id)
            svc_id_cell = (f"<a href='{html.escape(svc_url)}' class='svc-id'>{html.escape(raw_svc_id)}</a>"
                           if svc_url else f"<span class='svc-id'>{html.escape(raw_svc_id)}</span>")
            rows.append(
                f"<tr>"
                f"<td style='width:30%'>{name_cell}</td>"
                f"<td style='width:30%'>{svc_name}</td>"
                f"<td style='width:25%'>{svc_id_cell}</td>"
                f"<td style='width:15%'>{type_cell}</td>"
                f"</tr>"
            )
        schema_blocks.append(
            f"<h3><span class='schema'>{schema_h}</span></h3>"
            f"<table class='refs'>"
            f"<thead><tr>"
            f"<th style='width:30%'>Setting Name / Summary</th>"
            f"<th style='width:30%'>Service Name</th>"
            f"<th style='width:25%'>Service ID</th>"
            f"<th style='width:15%'>Service Type</th>"
            f"</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            f"</table>"
        )
    return "".join(schema_blocks)


def _anomaly_detector_url(base_url, title):
    if not title:
        return None
    filters = f'Title = *"{title}"*'
    qs = urllib.parse.urlencode({
        "dt.settings.schema_id": "builtin:davis.anomaly-detectors",
        "filters": filters,
    })
    return f"{base_url.rstrip('/')}/ui/apps/dynatrace.settings/settings/all-alerts/?{qs}"


def _render_anomaly_detectors_inner(anomaly_detectors, tenant_url):
    if not anomaly_detectors:
        return "<p class='none'>None found.</p>"
    rows = []
    for entry in anomaly_detectors:
        obj_id     = entry.get("objectId") or ""
        title      = html.escape(entry.get("title") or obj_id)
        svc_name   = html.escape(entry.get("service_name") or "")
        raw_svc_id = entry.get("service_id") or ""
        type_cell  = html.escape(_type_str(entry))
        url        = _anomaly_detector_url(tenant_url, entry.get("title") or obj_id)
        name_cell  = f"<a href='{html.escape(url)}'>{title}</a>" if url else title
        svc_url    = _service_url(tenant_url, raw_svc_id)
        svc_id_cell = (f"<a href='{html.escape(svc_url)}' class='svc-id'>{html.escape(raw_svc_id)}</a>"
                       if svc_url else f"<span class='svc-id'>{html.escape(raw_svc_id)}</span>")
        rows.append(
            f"<tr>"
            f"<td style='width:35%'>{name_cell}</td>"
            f"<td style='width:30%'>{svc_name}</td>"
            f"<td style='width:25%'>{svc_id_cell}</td>"
            f"<td style='width:10%'>{type_cell}</td>"
            f"</tr>"
        )
    return (
        "<table class='refs'>"
        "<thead><tr>"
        "<th style='width:35%'>Anomaly Detector Title</th>"
        "<th style='width:30%'>Service Name</th>"
        "<th style='width:25%'>Service ID</th>"
        "<th style='width:10%'>Service Type</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _srg_name(entry):
    value = entry.get("value") or {}
    return value.get("name") or value.get("summary") or entry.get("objectId") or ""


def _render_srgs_inner(srgs, tenant_url):
    if not srgs:
        return "<p class='none'>None found.</p>"
    rows = []
    for entry in srgs:
        obj_id     = entry.get("objectId") or ""
        title      = html.escape(_srg_name(entry))
        svc_name   = html.escape(entry.get("service_name") or "")
        raw_svc_id = entry.get("service_id") or ""
        type_cell  = html.escape(_type_str(entry))
        url        = _srg_url(tenant_url, obj_id)
        name_cell  = f"<a href='{html.escape(url)}'>{title}</a>" if url else title
        svc_url    = _service_url(tenant_url, raw_svc_id)
        svc_id_cell = (f"<a href='{html.escape(svc_url)}' class='svc-id'>{html.escape(raw_svc_id)}</a>"
                       if svc_url else f"<span class='svc-id'>{html.escape(raw_svc_id)}</span>")
        rows.append(
            f"<tr>"
            f"<td style='width:35%'>{name_cell}</td>"
            f"<td style='width:30%'>{svc_name}</td>"
            f"<td style='width:25%'>{svc_id_cell}</td>"
            f"<td style='width:10%'>{type_cell}</td>"
            f"</tr>"
        )
    return (
        "<table class='refs'>"
        "<thead><tr>"
        "<th style='width:35%'>Guardian Name</th>"
        "<th style='width:30%'>Service Name</th>"
        "<th style='width:25%'>Service ID</th>"
        "<th style='width:10%'>Service Type</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _render_slos_inner(slos, tenant_url):
    if not slos:
        return "<p class='none'>None found.</p>"
    rows = []
    for entry in slos:
        slo_name   = html.escape(entry.get("name") or "")
        slo_id     = entry.get("id") or ""
        svc_name   = html.escape(entry.get("service_name") or "")
        raw_svc_id = entry.get("service_id") or ""
        type_cell  = html.escape(_type_str(entry))
        url        = _slo_url(tenant_url, slo_id)
        name_cell  = f"<a href='{html.escape(url)}'>{slo_name}</a>" if url else slo_name
        svc_url    = _service_url(tenant_url, raw_svc_id)
        svc_id_cell = (f"<a href='{html.escape(svc_url)}' class='svc-id'>{html.escape(raw_svc_id)}</a>"
                       if svc_url else f"<span class='svc-id'>{html.escape(raw_svc_id)}</span>")
        rows.append(
            f"<tr>"
            f"<td style='width:30%'>{name_cell}</td>"
            f"<td style='width:30%'>{svc_name}</td>"
            f"<td style='width:25%'>{svc_id_cell}</td>"
            f"<td style='width:15%'>{type_cell}</td>"
            f"</tr>"
        )
    return (
        "<table class='refs'>"
        "<thead><tr>"
        "<th style='width:30%'>SLO Name</th>"
        "<th style='width:30%'>Service Name</th>"
        "<th style='width:25%'>Service ID</th>"
        "<th style='width:15%'>Service Type</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _render_docs_inner(notebooks, dashboards, tenant_url):
    parts = []

    def _doc_rows(docs):
        rows = []
        for doc in docs:
            doc_name  = html.escape(doc.get("name") or "")
            doc_url   = doc.get("url")
            doc_link  = f"<a href='{html.escape(doc_url)}'>{doc_name}</a>" if doc_url else doc_name
            for svc in doc.get("services", []):
                raw_svc_id = svc.get("service_id") or ""
                svc_name   = html.escape(svc.get("service_name") or "")
                type_cell  = html.escape(_type_str(svc))
                svc_url    = _service_url(tenant_url, raw_svc_id)
                svc_id_cell = (f"<a href='{html.escape(svc_url)}' class='svc-id'>{html.escape(raw_svc_id)}</a>"
                               if svc_url else f"<span class='svc-id'>{html.escape(raw_svc_id)}</span>")
                rows.append(
                    f"<tr>"
                    f"<td style='width:30%'>{doc_link}</td>"
                    f"<td style='width:30%'>{svc_name}</td>"
                    f"<td style='width:25%'>{svc_id_cell}</td>"
                    f"<td style='width:15%'>{type_cell}</td>"
                    f"</tr>"
                )
        return rows

    _THEAD = (
        "<thead><tr>"
        "<th style='width:30%'>Name</th>"
        "<th style='width:30%'>Service Name</th>"
        "<th style='width:25%'>Service ID</th>"
        "<th style='width:15%'>Service Type</th>"
        "</tr></thead>"
    )

    nb_rows = _doc_rows(notebooks)
    parts.append(
        "<h3>Notebooks</h3>"
        + ("<table class='refs'>" + _THEAD + f"<tbody>{''.join(nb_rows)}</tbody></table>"
           if nb_rows else "<p class='none'>None found.</p>")
    )

    dash_rows = _doc_rows(dashboards)
    parts.append(
        "<h3>Dashboards</h3>"
        + ("<table class='refs'>" + _THEAD + f"<tbody>{''.join(dash_rows)}</tbody></table>"
           if dash_rows else "<p class='none'>None found.</p>")
    )

    return "".join(parts)


def _render_third_party_inner(third_party, tenant_url):
    if not third_party:
        return "<p class='none'>None found.</p>"
    rows = []
    for svc in third_party:
        raw_id   = svc.get("id") or ""
        svc_name = html.escape(svc.get("name") or "")
        svc_type = svc.get("service_type") or svc.get("type") or ""
        svc_sub  = svc.get("service_sub_type") or svc.get("subType") or svc.get("sub_type") or ""
        type_str = html.escape(svc_type + (f" / {svc_sub}" if svc_sub else ""))
        url      = _service_url(tenant_url, raw_id)
        id_cell  = (f"<a href='{html.escape(url)}' class='svc-id'>{html.escape(raw_id)}</a>"
                    if url else f"<span class='svc-id'>{html.escape(raw_id)}</span>")
        rows.append(
            f"<tr>"
            f"<td style='width:30%'>{id_cell}</td>"
            f"<td style='width:40%'>{svc_name}</td>"
            f"<td style='width:30%'>{type_str}</td>"
            f"</tr>"
        )
    return (
        "<table class='refs'>"
        "<thead><tr>"
        "<th style='width:30%'>Service ID</th>"
        "<th style='width:40%'>Name</th>"
        "<th style='width:30%'>Service Type</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _write_html_report(out, output_file):
    tenant     = html.escape(out["tenant"])
    scanned_at = html.escape(out["scanned_at"])
    csp = (
        f"default-src 'none'; "
        f"style-src 'sha256-{_style_csp_hash()}'; "
        f"base-uri 'none'"
    )

    settings_base_url = out.get("settings_base_url", out["tenant"])
    tenant_url        = out["tenant"]

    completeness_data   = out.get("scan_completeness", {})
    banner_status       = completeness_data.get("status", "complete")
    banner_warnings     = completeness_data.get("warnings", [])
    failed_requests     = completeness_data.get("failed_requests", [])
    doc_content_failed  = [r for r in failed_requests if r.get("type") == "DOCUMENT_CONTENT"]

    if banner_status != "complete":
        li_items = []
        for w in banner_warnings:
            li_content = html.escape(w)
            if doc_content_failed and "document content fetch" in w:
                rows = "".join(
                    f"<tr>"
                    f"<td style='padding:0.2rem 0.5rem;font-family:monospace;font-size:0.8rem;word-break:break-all'>{html.escape(r.get('doc_id') or '')}</td>"
                    f"<td style='padding:0.2rem 0.5rem'>{html.escape(r.get('doc_name') or '')}</td>"
                    f"<td style='padding:0.2rem 0.5rem;color:#c00;font-size:0.8rem'>{html.escape(r.get('error') or '')}</td>"
                    f"</tr>"
                    for r in doc_content_failed
                )
                li_content += (
                    f"<details style='margin-top:0.4rem'>"
                    f"<summary style='cursor:pointer;font-size:0.85rem;color:#666'>"
                    f"Show failed requests ({len(doc_content_failed)})</summary>"
                    f"<table style='width:100%;border-collapse:collapse;margin-top:0.4rem;font-size:0.82rem'>"
                    f"<thead><tr>"
                    f"<th style='text-align:left;padding:0.2rem 0.5rem;border-bottom:1px solid #ccc;width:35%'>Document ID</th>"
                    f"<th style='text-align:left;padding:0.2rem 0.5rem;border-bottom:1px solid #ccc;width:30%'>Name</th>"
                    f"<th style='text-align:left;padding:0.2rem 0.5rem;border-bottom:1px solid #ccc;width:35%'>Error</th>"
                    f"</tr></thead>"
                    f"<tbody>{rows}</tbody>"
                    f"</table>"
                    f"</details>"
                )
            li_items.append(f"<li>{li_content}</li>")
        items = "".join(li_items)
        banner = (
            f"<div class='banner'><b>Warning: scan completeness is '{html.escape(banner_status)}'."
            f" This report may be missing affected configs.</b><ul>{items}</ul></div>"
        )
    else:
        banner = ""

    settings_by_schema  = out.get("settings_by_schema", {})
    slos                = out.get("slos", [])
    anomaly_detectors   = out.get("anomaly_detectors", [])
    srgs                = out.get("srgs", [])
    notebooks           = out.get("notebooks", [])
    dashboards          = out.get("dashboards", [])
    third_party         = out.get("third_party_services", [])

    settings_count = sum(len(v) for v in settings_by_schema.values())
    slo_count      = len(slos)
    ad_count       = len(anomaly_detectors)
    srg_count      = len(srgs)
    doc_count      = len(notebooks) + len(dashboards)
    tp_count       = len(third_party)

    gen3_inner = (
        "<h3>SLOs</h3>" + _render_slos_inner(slos, tenant_url) +
        "<h3 style='margin-top:1.25rem'>Anomaly Detectors</h3>" +
        _render_anomaly_detectors_inner(anomaly_detectors, tenant_url) +
        "<h3 style='margin-top:1.25rem'>Site Reliability Guardians</h3>" +
        _render_srgs_inner(srgs, tenant_url)
    )

    gen2_section = _details_block(
        "<span class='gen2-badge'>2nd gen</span> Settings",
        "gen2-badge",
        f"{settings_count} setting(s) across {len(settings_by_schema)} schema(s)",
        _render_settings_inner(settings_by_schema, settings_base_url, tenant_url),
    )

    gen3_section = _details_block(
        "<span class='gen3-badge'>3rd gen</span> SLOs, Anomaly Detectors &amp; Guardians",
        "gen3-badge",
        f"{slo_count} SLO(s), {ad_count} anomaly detector(s), {srg_count} guardian(s)",
        gen3_inner,
    )

    docs_section = _details_block(
        "<span class='doc-badge'>Documents</span> Notebooks &amp; Dashboards",
        "doc-badge",
        f"{len(notebooks)} notebook(s), {len(dashboards)} dashboard(s)",
        _render_docs_inner(notebooks, dashboards, tenant_url),
    )

    tp_section = _details_block(
        "Third-party services <small style='font-weight:normal;color:#888'>(WEB_REQUEST_WATCHED)</small>",
        "",
        f"{tp_count} service(s)",
        _render_third_party_inner(third_party, tenant_url),
        open_by_default=(tp_count > 0),
    )

    description = (
        "<p class='description'>"
        "Dynatrace Phase 3 migration removes external service entities (database services, "
        "third-party web request services, and opaque services). "
        "Any configuration that references these entity IDs — such as SLOs, anomaly detectors, "
        "Site Reliability Guardians, metric events, notebooks, and dashboards — will "
        "<strong>stop working</strong> once the migration is applied. "
        "Review the configs below and update them to use span- or metric-based filters "
        "that do not rely on <code>dt.entity.service</code> dimensions."
        "</p>"
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{html.escape(csp)}">
<title>External Services Report — {tenant}</title>
<style>
{_STYLE_CSS}
</style>
</head>
<body>
<h1>External Services Report — {tenant}</h1>
<p class="meta">Scanned at {scanned_at}</p>
{description}
{banner}
{gen2_section}
{gen3_section}
{docs_section}
{tp_section}
</body>
</html>
"""
    output_file.write_text(page, encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(
        description="Generate a report of external services from a scan_external_services report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--tenant",           required=True, help="Tenant URL (e.g. https://abc12345.apps.dynatrace.com)")
    ap.add_argument("--shared-dir",       default=None,  help="Path to shared-scripts directory (default: script's own directory)")
    ap.add_argument("--allow-incomplete", action="store_true",
                    help="Process the report even if scan_completeness is not 'complete'. "
                         "Results may be missing affected configs.")
    args = ap.parse_args()

    tenant_url = args.tenant.rstrip("/")
    _parsed = urllib.parse.urlparse(tenant_url)
    if _parsed.scheme not in ("http", "https") or not _parsed.netloc:
        ap.error(f"--tenant must be a valid URL (e.g. https://abc12345.apps.dynatrace.com), got: {args.tenant!r}")
    tenant_name       = _parsed.netloc.split(".")[0]
    settings_base_url = _normalize_tenant_url(tenant_url)

    shared_dir  = Path(args.shared_dir) if args.shared_dir else Path(__file__).parent
    details_dir = shared_dir / f"report_{tenant_name}_details"

    report = _load_report(shared_dir, tenant_name)

    completeness  = report.get("scan_completeness", {})
    scan_status   = completeness.get("status", "complete")
    scan_warnings = completeness.get("warnings", [])
    if scan_status != "complete":
        print(f"\nWARNING: Source report completeness is '{scan_status}':", file=sys.stderr)
        for w in scan_warnings:
            print(f"  - {w}", file=sys.stderr)
        if scan_status == "partial" and not args.allow_incomplete:
            print(
                "\nError: refusing to generate a report from a partial scan — results may silently"
                " omit affected configs. Fix the scan errors and re-run, or pass"
                " --allow-incomplete to override.", file=sys.stderr)
            sys.exit(1)

    # Extract document names for ID → name lookup.
    # affected_configs is a dict {"2nd gen": [...], "3rd gen": [...], "documents": [...]}
    # in reports produced by current versions of scan_external_services.py.
    # Fall back to flat-list format for backward compatibility with older reports.
    affected_configs = report.get("affected_configs", {})
    if isinstance(affected_configs, list):
        doc_names = {c["id"]: c.get("name") for c in affected_configs}
    else:
        doc_names = {c["id"]: c.get("name") for c in affected_configs.get("documents", [])}

    print(f"Loading detail files from: {details_dir}")
    settings_by_schema, slos, anomaly_detectors, srgs, nb_by_id, dash_by_id, third_party = _load_details(details_dir, tenant_name)

    schema_count  = len(settings_by_schema)
    setting_count = sum(len(v) for v in settings_by_schema.values())
    print(f"  2nd gen — Settings: {setting_count} setting(s) across {schema_count} schema(s).")
    print(f"  3rd gen — SLOs: {len(slos)} SLO(s), Anomaly detectors: {len(anomaly_detectors)}, Guardians: {len(srgs)}.")
    print(f"  Documents — Notebooks: {len(nb_by_id)}, Dashboards: {len(dash_by_id)}.")
    print(f"  Third-party services: {len(third_party)} service(s).")

    notebooks = [
        {"id": doc_id, "name": doc_names.get(doc_id), "url": _notebook_url(tenant_url, doc_id),
         "services": data["services"]}
        for doc_id, data in nb_by_id.items()
    ]

    dashboards = [
        {"id": doc_id, "name": doc_names.get(doc_id), "url": _dashboard_url(tenant_url, doc_id),
         "services": data["services"]}
        for doc_id, data in dash_by_id.items()
    ]

    out = {
        "scanned_at":           datetime.now(timezone.utc).isoformat(),
        "tenant":               tenant_url,
        "source_report":        str(shared_dir / f"report_{tenant_name}.json"),
        "settings_by_schema":   settings_by_schema,
        "slos":                 slos,
        "anomaly_detectors":    anomaly_detectors,
        "srgs":                 srgs,
        "notebooks":            notebooks,
        "dashboards":           dashboards,
        "third_party_services": third_party,
    }

    json_file = shared_dir / f"external_services_report_{tenant_name}.json"
    with open(json_file, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    html_file = json_file.with_suffix(".html")
    _write_html_report({**out, "settings_base_url": settings_base_url,
                        "scan_completeness": completeness}, html_file)

    print(f"\nJSON report : {json_file}")
    print(f"HTML report : {html_file}")
    sys.exit(0)


if __name__ == "__main__":
    main()
