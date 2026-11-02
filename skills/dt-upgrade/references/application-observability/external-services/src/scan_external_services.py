#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
External Service Config Scanner

Identifies Dynatrace configuration artifacts that reference external service entity
IDs (SERVICE-*). These configs break when Phase 3 migration activates because the
dt.entity.service dimension is no longer written to span/metric data.

Scans: SLOs | SRGs | Davis alerts | Custom metric events | Dashboards | Notebooks

Usage:
    python scan_external_services.py --tenant https://abc.apps.dynatrace.com --token dt0s16.XXX
    python scan_external_services.py --tenant https://abc.apps.dynatrace.com --token dt0s16.XXX --output /custom/path/report.json

Output is written to the script's own directory (shared-scripts/report_<tenant>.json) by
default so that database_services.py can find it without any extra flags.

    # Token can also be supplied via environment variable (--token takes precedence):
    export DT_PLATFORM_TOKEN=dt0s16.XXX
    python scan_external_services.py --tenant https://abc.apps.dynatrace.com

Required token scopes (a platform token -- dt0s16.* prefix -- is sufficient):
    Storage read    (DQL entity query -- built into platform tokens)
    settings.read   (classic settings API)
    document:read   (dashboards and notebooks)
    slo:slos:read   (gen3 SLOs from the Service-Level Objectives app)

Exit codes:
    0  completed successfully (check report for affected configs)
    1  fatal error (auth failure, unreachable tenant, etc.)
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

if sys.version_info < (3, 7):
    sys.exit("Python 3.7 or later is required.")

# Output defaults to the script's own directory so downstream tools that
# look for report_{tenant}.json in shared-scripts/ find it without extra flags.
_SCRIPT_DIR = Path(__file__).parent

_SETTINGS_SCHEMAS = [
    "builtin:monitoring.slo",                               # SLOs (settings-based)
    "builtin:anomaly-detection.metric-events",              # Custom metric events / Davis alerts
    "app:dynatrace.site.reliability.guardian:guardians",    # SRGs Only exists in 3rd gen.
]

_SLO_API_PATH = "/platform/slo/v1/slos"
_OBJECTS_API_PATH = "/platform/settings/v1/objects"

# DQL is used instead of Entity API v2 because it works with a plain platform token
# DQL is used instead of Entity API v2 because it works with a plain platform token
# (dt0s16.*); Entity API v2 requires the extra environment-api:entities:read scope.
_DQL_EXTERNAL_SERVICES = (
    "fetch dt.entity.service"
    " | filter isExternalService == true " 
    " | fields id, entity.name, entity.type, serviceType, serviceSubType, remoteCrossEnvironments"
    " | limit 100000"
)

_Cfg = namedtuple("_Cfg", ["platform", "classic", "hdrs", "timeout"])


def _derive_bases(url):
    """Return (platform_base, classic_base) for a tenant URL."""
    url = url.rstrip("/")
    if ".apps.dynatrace.com" in url:                              # production SaaS
        return url, url.replace(".apps.dynatrace.com", ".live.dynatrace.com", 1)
    if ".apps." in url:                                           # dev/staging
        return url, url.replace(".apps.", ".", 1)
    return url, url


class _ApiError(Exception):
    def __init__(self, url, code, body):
        super().__init__("HTTP {} -- {}: {}".format(code, url, body[:300]))


def _get(cfg, url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=cfg.hdrs)
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=cfg.timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 429 and attempt < 3:
                time.sleep(attempt * 10)
                continue
            raise _ApiError(url, e.code, body) from e
    raise _ApiError(url, 0, "no response after retries")


def _pages(cfg, url, items_key, params):
    current, items = dict(params), []
    while True:
        data = _get(cfg, url, current)
        items.extend(data.get(items_key, []))
        nk = data.get("nextPageKey")
        if not nk:
            break
        current = {"nextPageKey": nk}
    return items


def _dql_execute(cfg, query, max_records=None):
    """Execute a DQL query and return the records list."""
    url = cfg.platform + "/platform/storage/query/v1/query:execute"
    # Grail can be slow on large tenants; use a longer timeout than the default.
    dql_timeout = None if cfg.timeout is None else max(90, cfg.timeout)
    hdrs = dict(cfg.hdrs)
    hdrs["Content-Type"] = "application/json"
    body = {"query": query, "requestTimeoutMilliseconds": 60000}
    if max_records is not None:
        body["maxResultRecords"] = max_records
    payload = json.dumps(body).encode()
    req = urllib.request.Request(url, data=payload, headers=hdrs, method="POST")
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=dql_timeout) as r:
                resp = json.loads(r.read())
            if resp.get("state") != "SUCCEEDED":
                raise _ApiError(url, 0, "DQL state={}: {}".format(
                    resp.get("state"), json.dumps(resp)[:200]))
            return resp.get("result", {}).get("records", [])
        except _ApiError:
            raise
        except urllib.error.HTTPError as e:
            body_text = e.read().decode(errors="replace")
            if e.code == 429 and attempt < 3:
                time.sleep(attempt * 10)
                continue
            raise _ApiError(url, e.code, body_text) from e
        except Exception as exc:
            if attempt < 3:
                time.sleep(attempt * 5)
                continue
            raise _ApiError(url, 0, str(exc)) from exc
    raise _ApiError(url, 0, "no response after retries")


def _fetch_external_service_ids(cfg):
    records = _dql_execute(cfg, _DQL_EXTERNAL_SERVICES, max_records=100000)
    ids = {r["id"]: {
               "name":                    r.get("entity.name", r["id"]),
               "entity_type":             r.get("entity.type"),
               "service_type":            r.get("serviceType"),
               "service_sub_type":        r.get("serviceSubType"),
               "remote_cross_environments": r.get("remoteCrossEnvironments"),
           } for r in records}
    truncated = False
    if len(records) == 100000:
        truncated = True
        # Hit the cap — run a summarize count to report the true total.
        try:
            count_rec = _dql_execute(cfg,
                                     "fetch dt.entity.service"
                                     " | filter isExternalService == true"
                                     " | summarize count = count()")
            exact = count_rec[0].get("count") if count_rec else None
        except Exception:
            exact = None
        if exact and exact > 100000:
            print("WARNING: tenant has {:,} external services; scan is limited to the first 100,000.".format(exact),
                  file=sys.stderr, flush=True)
        else:
            print("WARNING: result may be truncated at 100,000 external services.",
                  file=sys.stderr, flush=True)
    return ids, truncated


def _strip_cached_results(obj):
    """
    Recursively remove cached query results from notebook/dashboard document bodies.

    Each notebook tile stores its last-run query output in state.result alongside the
    query definition in state.input. The cached data is irrelevant for finding entity
    ID references and can be megabytes of records. Removing it also avoids false
    positives: a service ID that appears only as a query result value (not hardcoded
    in the query definition) is not a config that needs migration.
    """
    if isinstance(obj, dict):
        cleaned = {k: _strip_cached_results(v) for k, v in obj.items()}
        if isinstance(cleaned.get("state"), dict):
            cleaned["state"] = {k: v for k, v in cleaned["state"].items() if k != "result"}
        return cleaned
    if isinstance(obj, list):
        return [_strip_cached_results(v) for v in obj]
    return obj


def _filter_body(body, matched_ids, doc_type):
    """Return a copy of body containing only the sections/tiles that reference a matched ID.

    Notebooks store content in sections[] (list); dashboards store it in tiles{} (dict).
    Keeping only matching parts makes the detail file focused and readable, and ensures
    line numbers from _find_hits (computed on the filtered body) match the file exactly.
    """
    if doc_type == "NOTEBOOK":
        kept = [s for s in body.get("sections", [])
                if any(sid in json.dumps(s, ensure_ascii=False) for sid in matched_ids)]
        return dict(body, sections=kept)
    if doc_type == "DASHBOARD":
        tiles = body.get("tiles") or {}
        kept = {tid: t for tid, t in tiles.items()
                if any(sid in json.dumps(t, ensure_ascii=False) for sid in matched_ids)}
        return dict(body, tiles=kept)
    return body


def _find_hits(body, service_ids):
    """Return {service_id: [line_number, ...]} for each service ID found in the body.
    Line numbers are 1-indexed relative to the body serialised with two-space indentation.
    """
    text = json.dumps(body, indent=2, ensure_ascii=False)
    present = {sid for sid in service_ids if sid in text}
    if not present:
        return {}
    hits = {}
    for i, ln in enumerate(text.splitlines()):
        for sid in present:
            if sid in ln:
                hits.setdefault(sid, []).append(i + 1)
    return hits


def _fetch_settings(cfg, schema_id):
    rows = _pages(cfg, cfg.classic + "/api/v2/settings/objects", "items",
                  {"schemaIds": schema_id, "pageSize": 500})
    return [{"type": "SETTINGS/" + schema_id,
             "id": r.get("objectId"),
             "name": (r.get("value") or {}).get("name")
                     or (r.get("value") or {}).get("summary")
                     or r.get("objectId"),
             "body": r}
            for r in rows]


def _fetch_documents(cfg, service_ids):
    """
    Fetch dashboards and notebooks, strip cached query results, and check hits inline.

    Only affected documents are retained in memory. OR-filter is unsupported by the
    API, so dashboards and notebooks are listed separately.
    """
    doc_base = cfg.platform + "/platform/document/v1/documents"

    def _list_pages(dtype):
        docs, page = [], 1
        while True:
            batch = _get(cfg, doc_base, {
                "page-size": 1000, "page": page, "filter": "type=='{}'".format(dtype)
            }).get("documents", [])
            docs.extend(batch)
            if len(batch) < 1000:
                break
            page += 1
        return docs

    targets = []
    listing_failed = []  # list of (document_type, error_str)
    for dtype in ("dashboard", "notebook"):
        try:
            targets.extend((d["id"], d.get("name"), dtype) for d in _list_pages(dtype))
        except Exception as exc:
            listing_failed.append((dtype, str(exc)))
            print("  WARNING: failed to list {}s: {}".format(dtype, exc), flush=True)

    if not targets:
        return 0, [], listing_failed, []

    print("  Fetching content for {} dashboards/notebooks...".format(len(targets)), flush=True)

    def _content(doc_id):
        req = urllib.request.Request(
            doc_base + "/{}/content".format(doc_id), headers=cfg.hdrs)
        # 30s is generous for a single doc; cfg.timeout (default 60s) would let
        # failing docs block a worker slot for twice as long, collapsing throughput
        # in the tail end of the fetch where slow/erroring docs accumulate.
        timeout = min(cfg.timeout, 30) if cfg.timeout else 30
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    affected, failed, done = [], [], 0  # failed: list of (doc_id, name, error_str)
    total = len(targets)
    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = {pool.submit(_content, doc_id): (doc_id, name, dtype)
                for doc_id, name, dtype in targets}
        for fut in as_completed(futs):
            doc_id, name, dtype = futs[fut]
            done += 1
            try:
                stripped = _strip_cached_results(fut.result())
                # Quick pre-filter on full stripped body before the expensive filter+scan.
                raw = json.dumps(stripped, ensure_ascii=False)
                matched_ids = {sid for sid in service_ids if sid in raw}
                if matched_ids:
                    kind = "DASHBOARD" if dtype == "dashboard" else "NOTEBOOK"
                    filtered = _filter_body(stripped, matched_ids, kind)
                    hits = _find_hits(filtered, matched_ids)
                    if hits:
                        affected.append({"type": kind, "id": doc_id, "name": name,
                                         "body": filtered, "hits": hits})
            except Exception as exc:
                failed.append((doc_id, name, str(exc)))
            if done % 200 == 0 or done == total:
                print("  Content fetch: {}/{} done{}".format(
                    done, total, ", {} failed".format(len(failed)) if failed else ""), flush=True)
    if failed:
        print("  ({}/{} document fetches failed -- check token document:read scope)".format(
            len(failed), total), flush=True)
    return total, affected, listing_failed, failed


def _id_part(item_type, item_id, item_name):
    """Return the ID portion of a detail filename.

    Documents (DASHBOARD, NOTEBOOK) already have clean UUIDs.
    Settings objectIds are opaque base64 blobs, so we use a sanitized name
    slug + 6-char hash for human readability while preserving uniqueness.
    """
    if item_type.startswith("SETTINGS/"):
        slug = "".join(c if c.isalnum() else "_" for c in (item_name or item_id))
        slug = slug.strip("_")
        while "__" in slug:
            slug = slug.replace("__", "_")
        slug = slug[:50].rstrip("_")
        short = hashlib.sha256(item_id.encode()).hexdigest()[:6]
        return slug + "_" + short
    return item_id


def _write_settings_detail(detail_dir, schema, entries, tenant_name=""):
    """Write a SETTINGS detail file as a JSON array.

    One file per schema collects every settings object of that schema across all
    matched services. Each entry contains: _schema_id, objectId, value, service_id,
    service_name.
    """
    schema_seg = "".join(c if c.isalnum() else "_" for c in schema)
    while "__" in schema_seg:
        schema_seg = schema_seg.replace("__", "_")
    schema_seg = schema_seg.strip("_")
    parts = ["SETTINGS", schema_seg, tenant_name] if tenant_name else ["SETTINGS", schema_seg]
    filename = "_".join(parts) + ".json"
    with open(os.path.join(detail_dir, filename), "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)
    return filename


def _write_dashboard_detail(detail_dir, doc_id, entries, tenant_name=""):
    """Write a DASHBOARD detail file as a JSON array.

    One file per dashboard collects every service it references.
    Each entry contains: _doc_id, service_id, service_name, tiles.
    """
    parts = ["DASHBOARD", doc_id, tenant_name] if tenant_name else ["DASHBOARD", doc_id]
    filename = "_".join(parts) + ".json"
    with open(os.path.join(detail_dir, filename), "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)
    return filename


def _write_notebook_detail(detail_dir, doc_id, entries, tenant_name=""):
    """Write a NOTEBOOK detail file as a JSON array.

    One file per notebook collects every service it references.
    Each entry contains: _doc_id, service_id, service_name, sections.
    """
    parts = ["NOTEBOOK", doc_id, tenant_name] if tenant_name else ["NOTEBOOK", doc_id]
    filename = "_".join(parts) + ".json"
    with open(os.path.join(detail_dir, filename), "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)
    return filename


def _write_detail(detail_dir, item_type, item_id, item_name, body, service_id, ext, tenant_name=""):
    """Write one detail file for a single (config, service_id) pair.

    For document types (NOTEBOOK, DASHBOARD) the body is re-filtered to only the
    sections/tiles that reference this service so the file stays focused.
    Line numbers in _matched_services are recomputed on the final body so they
    point to the exact lines in this file (accounting for the header offset).
    """
    type_prefix = item_type.split("/")[0]  # SETTINGS, NOTEBOOK, or DASHBOARD
    if item_type.startswith("SETTINGS/"):
        schema = item_type[len("SETTINGS/"):]
        schema_seg = "".join(c if c.isalnum() else "_" for c in schema)
        while "__" in schema_seg:
            schema_seg = schema_seg.replace("__", "_")
        id_seg = schema_seg.strip("_")
    else:
        id_seg = _id_part(item_type, item_id, item_name)
    service_seg = service_id.replace("-", "_")
    parts = [type_prefix, id_seg, tenant_name, service_seg] if tenant_name else [type_prefix, id_seg, service_seg]
    filename = "_".join(parts) + ".json"

    # For document types, narrow the body to only the tiles/sections for this service.
    if type_prefix in ("NOTEBOOK", "DASHBOARD"):
        body = _filter_body(body, {service_id}, type_prefix)

    # Re-find hits on the (possibly re-filtered) body for accurate line numbers.
    lines = _find_hits(body, {service_id}).get(service_id, [])

    # Use zero placeholders to measure how many lines the header will occupy.
    ms_placeholder = [{"service_id": service_id, "service_name": ext[service_id]["name"],
                        "lines": [0] * len(lines)}]
    offset = json.dumps({"_matched_services": ms_placeholder}, indent=2).count("\n") - 1

    matched_services = [
        {"service_id": service_id, "service_name": ext[service_id]["name"],
         "lines": [ln + offset for ln in lines]}
    ]
    annotated = {"_matched_services": matched_services}
    if item_type.startswith("SETTINGS/"):
        annotated["_schema_id"] = item_type[len("SETTINGS/"):]
    elif item_type == "NOTEBOOK":
        annotated["_doc_id"] = item_id
    annotated.update(body)

    with open(os.path.join(detail_dir, filename), "w", encoding="utf-8") as fh:
        json.dump(annotated, fh, indent=2, ensure_ascii=False)
    return filename


def _fetch_anomaly_detectors(cfg):
    """Fetch 3rd gen Davis anomaly detectors from the platform settings API."""
    url = cfg.platform + _OBJECTS_API_PATH
    params = {
        "schema-id":   "builtin:davis.anomaly-detectors",
        "scope":       "environment",
        "add-fields":  "objectId,value,scope",
        "admin-access": "false",
        "page-size":   "500",
    }
    rows = []
    while True:
        data = _get(cfg, url, params)
        rows.extend(data.get("items") or [])
        next_key = data.get("nextPageKey")
        if not next_key:
            break
        params = {"page-key": next_key}
    return [
        {
            "type": "ANOMALY_DETECTOR",
            "id":   r.get("objectId"),
            "name": (r.get("value") or {}).get("title") or r.get("objectId"),
            "analyzer": (r.get("value") or {}).get("analyzer"),
        }
        for r in rows
        if r.get("objectId")
    ]


def _fetch_slos(cfg):
    """Fetch gen3 SLOs from the Service-Level Objectives platform API."""
    url = cfg.platform + _SLO_API_PATH
    params = {"page-size": 500}
    rows = []
    while True:
        data = _get(cfg, url, params)
        rows.extend(r for r in data.get("slos") or [] if isinstance(r, dict))
        next_key = data.get("nextPageKey")
        if not next_key:
            break
        params = {"page-key": next_key}
    return [{"type": "SLO",
             "id": r.get("id"),
             "name": r.get("name") or r.get("id"),
             "body": r}
            for r in rows]


def _write_slo_detail(detail_dir, entries, tenant_name=""):
    """Write an SLO detail file as a JSON array.

    One file per tenant collects every SLO that references a matched service.
    Each entry contains: id, name, service_id, service_name, service_type, service_sub_type.
    """
    parts = ["SLO", tenant_name] if tenant_name else ["SLO"]
    filename = "_".join(parts) + ".json"
    with open(os.path.join(detail_dir, filename), "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)
    return filename


def _write_anomaly_detector_detail(detail_dir, entries, tenant_name=""):
    """Write an anomaly detector detail file as a JSON array.

    One file per tenant collects every anomaly detector that references a matched service.
    Each entry contains: objectId, title, service_id, service_name, service_type,
    service_sub_type, analyzer_name, matched_inputs.
    """
    parts = ["ANOMALY_DETECTOR", tenant_name] if tenant_name else ["ANOMALY_DETECTOR"]
    filename = "_".join(parts) + ".json"
    with open(os.path.join(detail_dir, filename), "w", encoding="utf-8") as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)
    return filename


def _exclude_cross_environment_services(ext):
    """Drop remote cross-environment services from the entity map.

    Such services are identified by:
      - remoteCrossEnvironments field being non-null/non-empty
    They are managed by the remote environment and don't need local migration.
    """
    filtered = {
        k: v for k, v in ext.items()
        if not (
            v.get("remote_cross_environments")
        )
    }
    excluded = len(ext) - len(filtered)
    if excluded:
        print("  Excluded {} remote cross-environment service(s) from scan.".format(excluded), flush=True)
    return filtered


def run(tenant_url, token, timeout=60, detail_dir=None):
    platform, classic = _derive_bases(tenant_url)
    tenant_name = tenant_url.split("//")[-1].split(".")[0]
    cfg = _Cfg(platform, classic,
               {"Authorization": "Api-Token " + token, "Accept": "application/json"},
               timeout)

    if platform != classic:
        print("Platform API : {}".format(platform), flush=True)
        print("Classic  API : {}\n".format(classic), flush=True)

    print("Fetching external service entities via DQL...", flush=True)
    ext, entity_truncated = _fetch_external_service_ids(cfg)
    ext = _exclude_cross_environment_services(ext)

    if not ext:
        print("No external services found -- nothing to migrate.")
        return _build_report(tenant_url, ext, 0, [], [], [], _completeness(entity_truncated, [], [], []))

    service_ids = set(ext)
    print("Found {} external service(s). Scanning configs...\n".format(len(service_ids)), flush=True)

    # Settings: all kept in memory (small objects, typically a few KB each).
    failed_schemas = []  # list of (schema_id, error_str) tuples
    settings_tasks = [(s, lambda s=s: _fetch_settings(cfg, s)) for s in _SETTINGS_SCHEMAS]
    settings_items = []
    with ThreadPoolExecutor(max_workers=len(settings_tasks)) as pool:
        futs = {pool.submit(fn): schema for schema, fn in settings_tasks}
        for fut in as_completed(futs):
            schema = futs[fut]
            label = "Settings({})".format(schema)
            try:
                items = fut.result()
                settings_items.extend(items)
                print("  {:<58} {:>4} item(s)".format(label, len(items)), flush=True)
            except Exception as exc:
                failed_schemas.append((schema, str(exc)))
                print("  {:<58}  ERROR -- {}".format(label, exc), file=sys.stderr, flush=True)

    # SLOs: gen3 Service-Level Objectives app (platform API, not classic settings).
    slo_error = None  # error string if fetch failed
    slo_items = []
    try:
        slo_items = _fetch_slos(cfg)
        print("  {:<58} {:>4} item(s)".format("SLOs (platform)", len(slo_items)), flush=True)
    except Exception as exc:
        slo_error = str(exc)
        print("  {:<58}  ERROR -- {}".format("SLOs (platform)", exc), file=sys.stderr, flush=True)

    # Anomaly detectors: gen3 Davis anomaly detectors (platform settings API).
    anomaly_detector_error = None  # error string if fetch failed
    anomaly_detector_items = []
    try:
        anomaly_detector_items = _fetch_anomaly_detectors(cfg)
        print("  {:<58} {:>4} item(s)".format("Anomaly detectors (platform)", len(anomaly_detector_items)), flush=True)
    except Exception as exc:
        anomaly_detector_error = str(exc)
        print("  {:<58}  ERROR -- {}".format("Anomaly detectors (platform)", exc), file=sys.stderr, flush=True)

    # Documents: content is stripped and checked inline; only affected docs are kept.
    doc_count, doc_hits, listing_failed, fetch_failed = 0, [], [], []
    try:
        doc_count, doc_hits, listing_failed, fetch_failed = _fetch_documents(cfg, service_ids)
        print("  {:<58} {:>4} item(s)".format("Dashboards + Notebooks", doc_count), flush=True)
    except Exception as exc:
        listing_failed = [("all documents", str(exc))]
        print("  {:<58}  ERROR -- {}".format("Dashboards + Notebooks", exc),
              file=sys.stderr, flush=True)

    affected_2nd: list = []
    affected_3rd: list = []
    affected_docs: list = []

    # Collect settings entries by schema — one file per schema, all matched services inside.
    settings_entries: dict = {}  # schema -> list of entry dicts
    for item in settings_items:
        hits = _find_hits(item["body"], service_ids)
        if hits:
            schema = item["type"][len("SETTINGS/"):]
            entry = _make_affected_entry(item["type"], item["id"], item["name"], hits, ext)
            if detail_dir:
                for sid in hits:
                    svc = ext[sid]
                    settings_entries.setdefault(schema, []).append({
                        "_schema_id":      schema,
                        "objectId":        item["id"],
                        "value":           item["body"].get("value"),
                        "service_id":      sid,
                        "service_name":    svc["name"],
                        "service_type":    svc.get("service_type"),
                        "service_sub_type": svc.get("service_sub_type"),
                    })
            affected_2nd.append(entry)

    if detail_dir and settings_entries:
        os.makedirs(detail_dir, exist_ok=True)
        for schema, entries in settings_entries.items():
            _write_settings_detail(detail_dir, schema, entries, tenant_name)

    # Collect SLO entries.
    slo_entries = []
    for item in slo_items:
        hits = _find_hits(item["body"], service_ids)
        if hits:
            entry = _make_affected_entry(item["type"], item["id"], item["name"], hits, ext)
            if detail_dir:
                for sid in hits:
                    svc = ext[sid]
                    slo_entries.append({
                        "id":              item["id"],
                        "name":            item["name"],
                        "service_id":      sid,
                        "service_name":    svc["name"],
                        "service_type":    svc.get("service_type"),
                        "service_sub_type": svc.get("service_sub_type"),
                    })
            affected_3rd.append(entry)

    if detail_dir and slo_entries:
        os.makedirs(detail_dir, exist_ok=True)
        _write_slo_detail(detail_dir, slo_entries, tenant_name)

    # Collect anomaly detector entries.
    anomaly_detector_entries = []
    for item in anomaly_detector_items:
        analyzer = item.get("analyzer") or {}
        hits = _find_hits(analyzer, service_ids)
        if hits:
            entry = _make_affected_entry(item["type"], item["id"], item["name"], hits, ext)
            if detail_dir:
                for sid in hits:
                    svc = ext[sid]
                    matched_inputs = [
                        inp for inp in (analyzer.get("input") or [])
                        if sid in (inp.get("value") or "")
                    ]
                    anomaly_detector_entries.append({
                        "objectId":        item["id"],
                        "title":           item["name"],
                        "service_id":      sid,
                        "service_name":    svc["name"],
                        "service_type":    svc.get("service_type"),
                        "service_sub_type": svc.get("service_sub_type"),
                        "analyzer_name":   analyzer.get("name"),
                        "matched_inputs":  matched_inputs,
                    })
            affected_3rd.append(entry)

    if detail_dir and anomaly_detector_entries:
        os.makedirs(detail_dir, exist_ok=True)
        _write_anomaly_detector_detail(detail_dir, anomaly_detector_entries, tenant_name)

    # Collect document entries by doc_id (all services in one file per document).
    notebook_entries: dict = {}   # doc_id -> list of entry dicts
    dashboard_entries: dict = {}  # doc_id -> list of entry dicts
    for item in doc_hits:
        entry = _make_affected_entry(item["type"], item["id"], item["name"], item["hits"], ext)
        if detail_dir:
            if item["type"] == "NOTEBOOK":
                for sid in item["hits"]:
                    svc = ext[sid]
                    filtered = _filter_body(item["body"], {sid}, "NOTEBOOK")
                    notebook_entries.setdefault(item["id"], []).append({
                        "_doc_id":          item["id"],
                        "service_id":       sid,
                        "service_name":     svc["name"],
                        "service_type":     svc.get("service_type"),
                        "service_sub_type": svc.get("service_sub_type"),
                        "sections":         filtered.get("sections", []),
                    })
            elif item["type"] == "DASHBOARD":
                for sid in item["hits"]:
                    svc = ext[sid]
                    filtered = _filter_body(item["body"], {sid}, "DASHBOARD")
                    dashboard_entries.setdefault(item["id"], []).append({
                        "_doc_id":          item["id"],
                        "service_id":       sid,
                        "service_name":     svc["name"],
                        "service_type":     svc.get("service_type"),
                        "service_sub_type": svc.get("service_sub_type"),
                        "tiles":            filtered.get("tiles", {}),
                    })
        affected_docs.append(entry)

    if detail_dir and (notebook_entries or dashboard_entries):
        os.makedirs(detail_dir, exist_ok=True)
        for doc_id, entries in notebook_entries.items():
            _write_notebook_detail(detail_dir, doc_id, entries, tenant_name)
        for doc_id, entries in dashboard_entries.items():
            _write_dashboard_detail(detail_dir, doc_id, entries, tenant_name)

    # Write WEB_REQUEST_WATCHED services unconditionally — they need attention regardless
    # of whether any scanned config currently references them.
    if detail_dir:
        third_party = [
            {
                "id":               k,
                "name":             v["name"],
                "entity_type":      v.get("entity_type"),
                "service_type":     v.get("service_type"),
                "service_sub_type": v.get("service_sub_type"),
            }
            for k, v in ext.items()
            if v.get("service_sub_type") == "WEB_REQUEST_WATCHED"
        ]
        if third_party:
            os.makedirs(detail_dir, exist_ok=True)
            tp_path = os.path.join(detail_dir, "THIRD_PARTY_{}.json".format(tenant_name))
            with open(tp_path, "w", encoding="utf-8") as fh:
                json.dump(third_party, fh, indent=2, ensure_ascii=False)
            print("  Third-party (WEB_REQUEST_WATCHED) services written: {:>4}".format(len(third_party)), flush=True)

    completeness = _completeness(entity_truncated, failed_schemas, listing_failed, fetch_failed,
                                 slo_error, anomaly_detector_error)
    return _build_report(tenant_url, ext,
                         len(settings_items) + len(slo_items) + len(anomaly_detector_items) + doc_count,
                         affected_2nd, affected_3rd, affected_docs, completeness)


def _completeness(entity_truncated, failed_schemas, listing_failed, fetch_failed,
                   slo_error=None, anomaly_detector_error=None):
    """Build scan_completeness block.

    Args:
        failed_schemas:  list of (schema_id, error_str) tuples
        listing_failed:  list of (document_type, error_str) tuples
        fetch_failed:    list of (doc_id, doc_name, error_str) tuples
        slo_error:       error string if SLO fetch failed, else None
        anomaly_detector_error: error string if anomaly detector fetch failed, else None
    """
    warnings = []
    failed_requests = []

    if entity_truncated:
        warnings.append(
            "External service query hit the 100,000-record cap; some services may be missing from the scan.")

    for schema, err in failed_schemas:
        warnings.append("Settings schema {} could not be fetched: {}.".format(schema, err))
        failed_requests.append({"type": "SETTINGS", "schema": schema, "error": err})

    if slo_error:
        warnings.append("SLO fetch from platform API failed: {}.".format(slo_error))
        failed_requests.append({"type": "SLO", "error": slo_error})

    if anomaly_detector_error:
        warnings.append("Anomaly detector fetch from platform API failed: {}.".format(anomaly_detector_error))
        failed_requests.append({"type": "ANOMALY_DETECTOR", "error": anomaly_detector_error})

    for dtype, err in listing_failed:
        warnings.append("Failed to list {}s: {}.".format(dtype, err))
        failed_requests.append({"type": "DOCUMENT_LISTING", "document_type": dtype, "error": err})

    if fetch_failed:
        warnings.append("{} document content fetch(es) failed; those configs were not scanned.".format(
            len(fetch_failed)))
        for doc_id, doc_name, err in fetch_failed:
            failed_requests.append({"type": "DOCUMENT_CONTENT", "doc_id": doc_id, "doc_name": doc_name, "error": err})

    if failed_schemas or slo_error or anomaly_detector_error or listing_failed or fetch_failed:
        status = "partial"
    elif entity_truncated:
        status = "truncated"
    else:
        status = "complete"
    return {"status": status, "warnings": warnings, "failed_requests": failed_requests}


def _make_affected_entry(item_type, item_id, item_name, hits, ext):
    return {
        "type":    item_type,
        "id":      item_id,
        "name":    item_name,
        "matches": [{"service_id": sid, "service_name": ext[sid]["name"], "occurrence_count": len(lines)}
                    for sid, lines in hits.items()],
    }


def _build_report(tenant, ext, scanned, affected_2nd, affected_3rd, affected_docs, completeness):
    all_affected = affected_2nd + affected_3rd + affected_docs
    referenced = {m["service_id"] for c in all_affected for m in c["matches"]}
    return {
        "scanned_at":                  datetime.now(timezone.utc).isoformat(),
        "tenant":                      tenant,
        "scan_completeness":           completeness,
        "external_services_on_tenant": len(ext),
        "configs_scanned":             scanned,
        "affected_config_count":       len(all_affected),
        "affected_external_services": [
            {
                "id":               k,
                "name":             v["name"],
                "entity_type":      v.get("entity_type"),
                "service_type":     v.get("service_type"),
                "service_sub_type": v.get("service_sub_type"),
            }
            for k, v in ext.items() if k in referenced
        ],
        "affected_configs": {
            "2nd gen": affected_2nd,
            "3rd gen": affected_3rd,
            "documents": affected_docs,
        },
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(
        description="Scan Dynatrace configs for external service entity ID references.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--tenant",      required=True, help="Tenant URL (.apps. or classic domain)")
    ap.add_argument("--token",       default=None,  help="Platform API token (dt0s16.XXX); overrides DT_PLATFORM_TOKEN env var")
    ap.add_argument("--output",  default=None, help="Output JSON report (default: <script-dir>/report_<tenant>.json)")
    ap.add_argument("--timeout", type=int, default=60, help="HTTP socket timeout in seconds (default: 60; 0 = no timeout)")
    args = ap.parse_args()

    token = args.token or os.environ.get("DT_PLATFORM_TOKEN")
    if not token:
        ap.error("provide --token or set the DT_PLATFORM_TOKEN environment variable")

    sock_timeout = args.timeout if args.timeout > 0 else None

    tenant_name = args.tenant.split("//")[-1].split(".")[0]
    output = args.output or str(_SCRIPT_DIR / "report_{}.json".format(tenant_name))
    base, _ = os.path.splitext(os.path.abspath(output))
    detail_dir = base + "_details"

    try:
        t0 = time.monotonic()
        report = run(args.tenant, token, timeout=sock_timeout, detail_dir=detail_dir)
        elapsed = time.monotonic() - t0
    except _ApiError as exc:
        print("\nFatal API error: {}".format(exc), file=sys.stderr)
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as exc:
        print("\nFatal: {}".format(exc), file=sys.stderr)
        sys.exit(1)

    with open(output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    n = report["affected_config_count"]
    sep = "-" * 62
    print("\n" + sep)
    print("External services found : {}".format(report["external_services_on_tenant"]))
    print("Configs scanned         : {}".format(report["configs_scanned"]))
    print("Affected configs        : {}".format(n))
    print("Duration                : {:.1f}s".format(elapsed))
    print("Report written to       : {}".format(output))
    if n > 0:
        print("Detail files written to : {}/".format(detail_dir))
    print(sep)

    affected_configs = report["affected_configs"]
    if any(affected_configs.values()):
        print("\nAffected configs:")
        for gen_label, configs in affected_configs.items():
            if not configs:
                continue
            print("  [{}]".format(gen_label))
            for c in configs:
                print("    [{}] {}".format(c["type"], c["name"]))
                matches = c["matches"]
                for m in matches[:5]:
                    print("      -> {} ({}) -- {} occurrence(s)".format(
                        m["service_name"], m["service_id"], m["occurrence_count"]))
                if len(matches) > 5:
                    print("      ... and {} more service reference(s) -- see detail file".format(
                        len(matches) - 5))

    sys.exit(0)


if __name__ == "__main__":
    main()
