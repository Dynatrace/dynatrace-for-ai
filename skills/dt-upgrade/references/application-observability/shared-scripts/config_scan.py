#!/usr/bin/env python3
"""Shared configuration-scan layer for the ``dt-upgrade`` topic scanners.

Every Phase 3 topic asks the same question of a tenant — *which of the agreed
configuration sources reference the thing I care about?* — and differs only in
the detector applied to the bodies. This module is that common half:

- **Sources.** Dashboards, notebooks, SLOs (both the Service-Level Objectives
  app and the classic ``builtin:monitoring.slo`` schema), Site Reliability
  Guardians, and metric-event/Davis custom alerts, fetched whole so a caller can
  match anything.
- **Coverage state.** Every fetch returns a :class:`SourceResult` carrying
  ``complete`` / ``partial`` / ``failed``. Usage-gated reporting depends on this:
  an unreadable source must never be presentable as "no usage", which is exactly
  the trap ``scan_external_services.py`` falls into by returning ``[]`` on error.
- **Transports.** :class:`DtctlClient` reuses the CLI's current context, so a
  scan needs no token and no tenant URL. :class:`HttpClient` is the fallback for
  environments without ``dtctl`` and takes a platform token.
- **Links.** :func:`artifact_link` turns any fetched artifact into a URL that
  opens it in the tenant.

Stdlib only, so consumers need no install step. Import it by putting this
directory on ``sys.path``.

Verified against dtctl 0.30.3, whose output shapes are:

- ``get settings --schema <id>`` — flat JSON array of objects carrying
  ``objectId``, ``scope``, ``summary``, ``value``.
- ``get dashboards`` / ``get notebooks`` — flat JSON array of metadata
  (``id``, ``name``, ``type``, ``owner``); no document body.
- ``get dashboard <id>`` / ``get notebook <id>`` — the metadata plus a
  ``content`` object holding ``tiles`` (dashboards, a map) or ``sections``
  (notebooks, a list).
- ``get slos`` — flat JSON array of Service-Level Objectives app objects
  (``id``, ``name``, ``criteria``, ``customSli``/``sliReference``, ``tags``).
- ``query <dql>`` — an object with a ``records`` array.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Iterable

# --------------------------------------------------------------------------
# Sources and coverage state
# --------------------------------------------------------------------------

#: Classic, settings-backed SLOs. Gen2 configurations are no longer migrated into
#: the Service-Level Objectives app, so a classic SLO that reads a retired metric
#: or entity is the customer's own work to schedule and has to be reported like
#: any other source.
CLASSIC_SLO_SOURCE = "classic_slos"
CLASSIC_SLO_SCHEMA = "builtin:monitoring.slo"

#: Log events (``builtin:logmonitoring.log-events``) are deliberately **not** a
#: source, even though the Settings app lists them on its *all alerts* page next
#: to metric events and Davis anomaly detectors. A log event is a matcher over
#: log records plus the text of the event it raises: no metric selector, no
#: entity selector, no DQL. There is no field in it for a Phase 3 topic to match.
#: Verified on a tenant with 41 objects — zero references of any kind.

#: The settings schemas holding classic SLOs, classic metric events, Davis custom
#: alerts, and guardians. Order decides the order sources appear in a report, so
#: the classic SLO schema sits next to the SLO app it is compared against.
SETTINGS_SOURCES: dict[str, str] = {
    CLASSIC_SLO_SOURCE: CLASSIC_SLO_SCHEMA,
    "metric_events": "builtin:anomaly-detection.metric-events",
    "davis_anomaly_detectors": "builtin:davis.anomaly-detectors",
    "srgs": "app:dynatrace.site.reliability.guardian:guardians",
}

#: The two platform document types.
DOCUMENT_SOURCES: tuple[tuple[str, str], ...] = (
    ("dashboards", "dashboard"),
    ("notebooks", "notebook"),
)

#: The Service-Level Objectives app (``dynatrace.service.level.objectives``).
#: Its objects are *not* a settings schema — they are read through the platform
#: SLO API, ``GET /platform/slo/v1/slos``, which is also what ``dtctl get slos``
#: calls. Classic ``builtin:monitoring.slo`` objects are a separate source,
#: ``CLASSIC_SLO_SOURCE``; the two never overlap, so both are reported.
SLO_SOURCE = "slos"
SLO_KIND = "SLO"
SLO_API_PATH = "/platform/slo/v1/slos"

#: The classic SLO fields that carry a metric selector or an entity selector —
#: the only places in a ``builtin:monitoring.slo`` object where a retired metric
#: key or entity ID can change what the SLO evaluates. Everything else is a
#: name, a threshold, or a timeframe, and matching there would report prose.
#:
#: This is the whole list, not a subset: schema 6.0.14 defines exactly two such
#: fields, and the Settings API returns every object at the current schema
#: version, so the older rate-based form (``metricRate`` and friends) cannot
#: reach a caller no matter when the object was written. ``metricName`` is the
#: identifier of the metric this SLO *produces*, not one it reads.
CLASSIC_SLO_FIELDS = frozenset({"filter", "metricExpression"})

#: Field allowlists this layer owns, keyed by source name. A topic detector
#: delegates every source listed here instead of hand-rolling the paths, so
#: adding a shared settings source later is a one-line change here and none in
#: the scanners, and the rule cannot drift between topics.
SHARED_SETTINGS_FIELDS: dict[str, frozenset[str]] = {
    CLASSIC_SLO_SOURCE: CLASSIC_SLO_FIELDS,
}


def is_shared_settings_field(source: str, path: str) -> bool:
    """Whether *path* addresses an evaluated field of a shared-owned *source*.

    Matching is on the last path segment rather than the full ``value.<field>``
    path: the settings body nests the object under ``value``, but the same
    predicate is reused by topics that hand in an already-unwrapped body.
    Returns ``False`` for any source this layer does not own, so a caller can
    guard with ``if source in SHARED_SETTINGS_FIELDS``.
    """
    fields = SHARED_SETTINGS_FIELDS.get(source)
    return bool(fields) and path.rsplit(".", 1)[-1] in fields


COMPLETE = "complete"
PARTIAL = "partial"
FAILED = "failed"


@dataclass
class SourceResult:
    """One configuration source, with its coverage state preserved."""

    name: str
    state: str = COMPLETE
    reason: str = ""
    # Items the source *listed*. Bodies are fetched afterwards and some can miss,
    # so this is not the number actually examined — subtract ``items_unread``.
    # Keeping the two apart is what stops a report from calling an unread object
    # clean.
    items_checked: int = 0
    items_unread: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)

    def degrade(self, state: str, reason: str) -> None:
        """Lower the state; never upgrade it. ``failed`` beats ``partial``."""
        rank = {COMPLETE: 0, PARTIAL: 1, FAILED: 2}
        if rank[state] >= rank[self.state]:
            if self.reason and reason and reason not in self.reason:
                self.reason = f"{self.reason}; {reason}"
            else:
                self.reason = reason or self.reason
            self.state = state


def strip_cached_results(obj: Any) -> Any:
    """Recursively drop cached query output from document bodies.

    Each tile or section stores its last-run result under ``state.result``
    alongside the query definition in ``state.input``. That payload is data, not
    configuration: a match found only in a cached result is not a config that
    needs migration, so leaving it in produces false findings (and can add
    megabytes per document).
    """
    if isinstance(obj, dict):
        cleaned = {k: strip_cached_results(v) for k, v in obj.items()}
        if isinstance(cleaned.get("state"), dict):
            cleaned["state"] = {k: v for k, v in cleaned["state"].items() if k != "result"}
        return cleaned
    if isinstance(obj, list):
        return [strip_cached_results(v) for v in obj]
    return obj


# --------------------------------------------------------------------------
# Tenant URLs
# --------------------------------------------------------------------------


class ConfigError(ValueError):
    """Raised when required configuration is missing or malformed."""


def normalise_url(url: str) -> str:
    return url.rstrip("/")


def derive_url_pair(
    *, tenant: str | None, classic: str | None = None, platform: str | None = None
) -> tuple[str, str]:
    """Derive the ``(classic, platform)`` URL pair from any of the three inputs.

    The classic Settings 2.0 API and the platform document/DQL APIs live on
    different hosts (``<env>.live.dynatrace.com`` vs ``<env>.apps.dynatrace.com``);
    when only one is given the other follows the standard naming convention.
    Priority: explicit ``classic``/``platform`` > generic ``tenant``.
    """
    if not (tenant or classic or platform):
        raise ConfigError("missing tenant URL (provide --tenant, --classic-url, or --platform-url)")

    if classic and platform:
        return normalise_url(classic), normalise_url(platform)
    if classic:
        return normalise_url(classic), normalise_url(_infer_platform(classic))
    if platform:
        return normalise_url(_infer_classic(platform)), normalise_url(platform)

    norm = normalise_url(tenant)  # type: ignore[arg-type]
    if ".apps." in norm:
        return _infer_classic(norm), norm
    return norm, _infer_platform(norm)


def _infer_platform(classic: str) -> str:
    return classic.replace(".live.dynatrace.com", ".apps.dynatrace.com").replace(
        ".dynatracelabs.com", ".apps.dynatracelabs.com"
    )


def _infer_classic(platform: str) -> str:
    return platform.replace(".apps.dynatrace.com", ".live.dynatrace.com").replace(
        ".apps.dynatracelabs.com", ".dynatracelabs.com"
    )


# --------------------------------------------------------------------------
# Links back to the configuration
# --------------------------------------------------------------------------

# ``(appId, intentId, payload key)`` per artifact kind. Links are built as app
# intents — the navigation contract the tenant itself registers, listable with
# ``dtctl get intents`` — rather than hand-assembled app routes, which differ per
# app and change without notice. The URL shape is
#   <tenant>/ui/intent/<appId>/<intentId>#<encodeURIComponent(JSON.stringify(payload))>
# verified byte-for-byte against ``dtctl open intent``.
_DASHBOARD_INTENT = ("dynatrace.dashboards", "view-dashboard", "dt.document.id")
_NOTEBOOK_INTENT = ("dynatrace.notebooks", "view-notebook", "dt.document.id")
# The Service-Level Objectives app takes the SLO's own id — the opaque string the
# SLO API returns as `id` — verbatim. No translation is needed, unlike the
# retired classic SLO app, whose intent wanted a UUID buried inside a settings
# objectId.
_SLO_INTENT = ("dynatrace.service.level.objectives", "view-slo", "dt.slo.id")
# Everything else settings-backed — classic SLOs, metric events, and Site
# Reliability Guardians. The guardian app registers no per-object intent, the
# classic SLO app is retired, and the settings object is what has to be reworked
# anyway, so all three land in the settings editor.
_SETTINGS_INTENT = (
    "dynatrace.classic.settings",
    "settings-open-settings-by-id",
    "dt.settings.object_id",
)

#: Schemas the classic Settings app cannot open. It maps the schemas the old interface had a
#: page for; everything else lands under *Settings -> Unmapped schemas*, which a customer
#: normally cannot reach at all. Such a schema belongs to the platform app that owns it, and
#: that app registers its own intent — Davis custom alerts open in Anomaly Detection.
#:
#: Keyed by schema id: ``(appId, intentId, payload keys)``. The first key takes the settings
#: ``objectId``; a second one, where the intent has one, takes the schema id, so the app is told
#: which editor to open rather than only what to open in it.
#:
#: The guardian intent is named for validation results and takes its ``validation.id`` as
#: optional: with only ``guardian.id`` it opens the guardian. That id is the settings
#: ``objectId`` — the app's own workflow action addresses a guardian by ``objectId``, and the
#: validation events it raises carry the same string as ``dt.srg.id``.
_SCHEMA_INTENTS = {
    "builtin:davis.anomaly-detectors": (
        "dynatrace.davis.anomalydetection",
        "open_anomaly_detector_schema",
        ("dt.settings.object_id", "dt.settings.schema_id"),
    ),
    "app:dynatrace.site.reliability.guardian:guardians": (
        "dynatrace.site.reliability.guardian",
        "view_validation",
        ("guardian.id",),
    ),
}


def intent_url(base_url: str, app_id: str, intent_id: str, payload: dict[str, str]) -> str:
    """Build one intent URL.

    ``quote(..., safe="")`` matches ``encodeURIComponent`` for these payloads: the
    only characters the two disagree on (``!*'()``) cannot occur in a document
    UUID or a base64 settings ``objectId``.
    """
    fragment = urllib.parse.quote(json.dumps(payload, separators=(",", ":")), safe="")
    return f"{normalise_url(base_url)}/ui/intent/{app_id}/{intent_id}#{fragment}"


def artifact_link(base_url: str, kind: str, artifact_id: str) -> str | None:
    """Link to the screen that owns *artifact_id*, or ``None`` if not derivable.

    A link is best-effort. When the tenant URL is unknown — ``dtctl`` against a
    context whose environment could not be resolved — findings are still
    reported, just without a link.
    """
    if not base_url or not artifact_id:
        return None

    if kind == "DASHBOARD":
        target = _DASHBOARD_INTENT
    elif kind == "NOTEBOOK":
        target = _NOTEBOOK_INTENT
    elif kind == SLO_KIND:
        target = _SLO_INTENT
    elif kind.startswith("SETTINGS/"):
        schema = kind.split("/", 1)[1]
        owner = _SCHEMA_INTENTS.get(schema)
        if owner:
            app_id, intent_id, keys = owner
            payload = {keys[0]: artifact_id}
            for key in keys[1:]:
                payload[key] = schema
            return intent_url(base_url, app_id, intent_id, payload)
        target = _SETTINGS_INTENT
    else:
        return None

    app_id, intent_id, key = target
    return intent_url(base_url, app_id, intent_id, {key: artifact_id})


def report_ui_url(summary: dict[str, Any], override: str | None = None) -> str:
    """Resolve the UI base URL for a new or previously generated report."""
    tenant = summary.get("tenant") or {}
    candidates = (
        override,
        tenant.get("ui_url"),
        tenant.get("platform_url"),
        tenant.get("label"),
    )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.startswith(("https://", "http://")):
            url = normalise_url(candidate)
            return url if ".apps." in url else normalise_url(_infer_platform(url))
    return ""


def add_artifact_links(artifacts: Iterable[dict[str, Any]], base_url: str) -> None:
    """Add or refresh direct UI links on report artifact dictionaries."""
    if not base_url:
        return
    for artifact in artifacts:
        artifact["link"] = artifact_link(
            base_url,
            str(artifact.get("kind") or ""),
            str(artifact.get("id") or ""),
        )


# --------------------------------------------------------------------------
# HTTP transport
# --------------------------------------------------------------------------


class ApiError(Exception):
    def __init__(self, url: str, code: int, body: str):
        super().__init__(f"HTTP {code} -- {url}: {body[:300]}")
        self.code = code


class HttpClient:
    """Reaches the tenant over raw HTTP with a platform (``dt0s16.*``) token."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        # Platform APIs accept platform tokens as Bearer credentials. The
        # Environment/Configuration APIs retain the Api-Token scheme.
        self.headers = {
            "Authorization": "Bearer " + cfg.platform_token,
            "Accept": "application/json",
        }
        # A platform token is rejected by the classic Configuration API
        # ("unsupported authorization scheme 'Api-Token'"), so a classic
        # ``dt0c01.*`` token is used when one is supplied. Falling back to the
        # platform token keeps existing callers working unchanged.
        classic_token = getattr(cfg, "classic_token", "") or os.environ.get("DT_CLASSIC_TOKEN", "")
        self.classic_headers = {
            "Authorization": "Api-Token " + (classic_token or cfg.platform_token),
            "Accept": "application/json",
        }

    # -- primitives ------------------------------------------------------

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers or self.headers)
        for attempt in range(1, 4):
            try:
                with urllib.request.urlopen(req, timeout=self.cfg.timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")
                if e.code == 429 and attempt < 3:
                    time.sleep(attempt * 10)
                    continue
                raise ApiError(url, e.code, body) from e
            except Exception as exc:  # network hiccup
                if attempt < 3:
                    time.sleep(attempt * 5)
                    continue
                raise ApiError(url, 0, str(exc)) from exc
        raise ApiError(url, 0, "no response after retries")

    def _pages(
        self,
        url: str,
        items_key: str,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> list[Any]:
        current, items = dict(params), []
        while True:
            data = self.get(url, current, headers)
            items.extend(data.get(items_key, []))
            nk = data.get("nextPageKey")
            if not nk:
                break
            current = {"nextPageKey": nk}
        return items

    def dql(self, query: str, max_records: int | None = None) -> list[dict[str, Any]]:
        """Execute DQL through the platform storage query API."""
        url = self.cfg.platform_url + "/platform/storage/query/v1/query:execute"
        timeout = max(90, self.cfg.timeout)
        headers = dict(self.headers)
        headers["Content-Type"] = "application/json"
        body: dict[str, Any] = {"query": query, "requestTimeoutMilliseconds": 60000}
        if max_records is not None:
            body["maxResultRecords"] = max_records
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        for attempt in range(1, 4):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    resp = json.loads(r.read())
                if resp.get("state") != "SUCCEEDED":
                    raise ApiError(url, 0, f"DQL state={resp.get('state')}")
                return resp.get("result", {}).get("records", [])
            except ApiError:
                raise
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")
                if e.code == 429 and attempt < 3:
                    time.sleep(attempt * 10)
                    continue
                raise ApiError(url, e.code, text) from e
            except Exception as exc:
                if attempt < 3:
                    time.sleep(attempt * 5)
                    continue
                raise ApiError(url, 0, str(exc)) from exc
        raise ApiError(url, 0, "no response after retries")

    def calculated_service_metrics_on_grail(self) -> list[dict[str, Any]]:
        """List calculated service metrics enabled on Grail through Config API v1."""
        data = self.get(
            self.cfg.classic_url
            + "/api/config/v1/calculatedMetrics/service/metricsOnGrail",
            headers=self.classic_headers,
        )
        return [row for row in data.get("values") or [] if isinstance(row, dict)]

    # -- sources ---------------------------------------------------------

    def fetch_settings_source(self, name: str, schema_id: str) -> SourceResult:
        """Read every object of one settings schema.

        A schema that does not exist on the tenant (404) is genuinely zero
        objects — that is ``complete``, not a failure. Any other error is
        ``failed``, so the caller cannot mistake it for absence of usage.
        """
        result = SourceResult(name=name)
        try:
            rows = self._pages(
                self.cfg.classic_url + "/api/v2/settings/objects",
                "items",
                {"schemaIds": schema_id, "pageSize": 500},
                self.classic_headers,
            )
        except ApiError as exc:
            if exc.code == 404:
                result.reason = f"schema {schema_id} not present on tenant (0 objects)"
                return result
            result.degrade(FAILED, f"{schema_id}: {exc}")
            return result

        result.items = [_settings_item(name, schema_id, r) for r in rows]
        result.items_checked = len(result.items)
        return result

    def fetch_slos(self) -> SourceResult:
        """Read every objective of the Service-Level Objectives app.

        The SLO API paginates with its own ``page-key`` parameter rather than the
        settings API's ``nextPageKey``, so :meth:`_pages` does not apply. Needs
        the ``slo:slos:read`` scope; without it the source is ``failed``, never
        an empty (and therefore falsely clean) list.
        """
        result = SourceResult(name=SLO_SOURCE)
        url = self.cfg.platform_url + SLO_API_PATH
        params: dict[str, Any] = {"page-size": 500}
        rows: list[dict[str, Any]] = []
        while True:
            try:
                page = self.get(url, params)
            except ApiError as exc:
                result.degrade(FAILED, f"listing SLOs failed: {exc} (check the slo:slos:read scope)")
                return result
            rows.extend(r for r in page.get("slos") or [] if isinstance(r, dict))
            next_key = page.get("nextPageKey")
            if not next_key:
                break
            params = {"page-key": next_key}

        result.items = [_slo_item(r) for r in rows]
        result.items_checked = len(result.items)
        return result

    def fetch_documents(self, doc_type: str, name: str) -> SourceResult:
        """List and fetch the content of every dashboard or notebook.

        Coverage equals what the token is permitted to read. A token without
        tenant-wide document access sees only its own documents, which the
        caller must report as partial rather than as full coverage.
        """
        result = SourceResult(name=name)
        base = self.cfg.platform_url + "/platform/document/v1/documents"

        listed: list[dict[str, Any]] = []
        admin_access = True
        page_key = ""
        while True:
            try:
                params = {
                    "page-size": 1000,
                    "filter": f"type=='{doc_type}'",
                }
                if page_key:
                    params = {"page-key": page_key, "page-size": 1000}
                if admin_access:
                    params["admin-access"] = "true"
                page = self.get(base, params)
            except ApiError as exc:
                if page_key or exc.code not in {401, 403}:
                    result.degrade(FAILED, f"listing {doc_type}s with admin access failed: {exc}")
                    return result
                admin_access = False
                result.degrade(
                    PARTIAL,
                    "tenant-wide document access unavailable; scanned only documents visible "
                    "to the token (add document:documents:admin)",
                )
                try:
                    page = self.get(
                        base,
                        {"page-size": 1000, "filter": f"type=='{doc_type}'"},
                    )
                except ApiError as fallback_exc:
                    result.degrade(FAILED, f"listing visible {doc_type}s failed: {fallback_exc}")
                    return result
            if not isinstance(page, dict) or not isinstance(page.get("documents"), list):
                result.degrade(FAILED, f"listing {doc_type}s returned an unexpected response shape")
                return result
            batch = page["documents"]
            listed.extend(batch)
            page_key = str(page.get("nextPageKey") or "")
            if not page_key:
                break

        result.items_checked = len(listed)
        if not listed:
            return result

        def _content(doc_id: str) -> Any:
            url = base + f"/{doc_id}/content"
            if admin_access:
                url += "?admin-access=true"
            req = urllib.request.Request(url, headers=self.headers)
            # 30s is generous for one document; the full cfg.timeout would let a
            # failing document hold a worker slot twice as long.
            with urllib.request.urlopen(req, timeout=min(self.cfg.timeout, 30)) as r:
                body = json.loads(r.read())
            if not isinstance(body, dict):
                raise ApiError(url, 0, "document content returned an unexpected response shape")
            return body

        failed = _fetch_bodies(result, listed, doc_type, name, _content, self.cfg.max_workers)
        if failed:
            result.items_unread = len(failed)
            result.degrade(
                PARTIAL,
                f"{len(failed)}/{len(listed)} {doc_type} content fetches failed "
                "(check the document:read scope)",
            )
        return result


# --------------------------------------------------------------------------
# dtctl transport
# --------------------------------------------------------------------------

# Chunk size passed to every list command so dtctl paginates to the end.
_CHUNK = "500"

# The dtctl build whose output shapes — and whose one known gap, see
# `_note_dropped_sli` — this layer was verified against.
_DTCTL_VERIFIED = "0.30.3"


class DtctlError(RuntimeError):
    """Raised when a dtctl invocation cannot be used."""


class DtctlAuthError(DtctlError):
    """dtctl could not authenticate — every later call would fail the same way."""


def _envelope_error(text: str) -> str | None:
    """Extract the message from dtctl's ``{"ok": false, "error": {...}}`` envelope.

    dtctl reports failures as JSON on **stdout** with an empty stderr, so naively
    reading the last line of either stream yields ``}`` and hides the real cause
    (for example ``token "<ref>" not found``). Always look inside the envelope.
    """
    text = (text or "").strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("ok") is not False:
        return None
    err = data.get("error") or {}
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or "unknown dtctl error")
    return str(err)


_AUTH_HINTS = ("unauthorized", "forbidden", "401", "403", "oauth", "expired", "login", "credential")

# A missing credential reads `token "<ref>" not found`. Matching bare "not found"
# or bare "token" instead is what makes this dangerous: `404 Document not found`
# is an ordinary per-object miss — a dashboard deleted between the list call and
# its content fetch — and classifying it as an auth failure aborts the whole
# sweep and marks a fully readable source `failed`. Under usage-gated reporting
# that turns into a false "incomplete", so the two must not be confused.
_TOKEN_MISSING_RE = re.compile(r"""token\s+["'][^"']*["']\s+not found""", re.IGNORECASE)
_MISSING_OBJECT_RE = re.compile(r"\b404\b|not found:", re.IGNORECASE)


def _is_auth_error(message: str) -> bool:
    """True only when *message* is about the credential, not about a missing object."""
    if _TOKEN_MISSING_RE.search(message):
        return True
    if _MISSING_OBJECT_RE.search(message):
        return False
    return any(hint in message.lower() for hint in _AUTH_HINTS)

# Markdown punctuation dtctl escapes for terminal rendering.
_MD_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|>~])")


def unescape_markdown(text: str | None) -> str | None:
    """Undo dtctl's markdown escaping of display strings."""
    if not text:
        return text
    return _MD_ESCAPE_RE.sub(r"\1", text)


def _label(args: list[str]) -> str:
    """The subcommand words of an argv, without the trailing output flags."""
    words: list[str] = []
    for arg in args:
        if arg.startswith("-"):
            break
        words.append(arg)
    return " ".join(words[:3]) or "?"


def _raise_for(args: list[str], returncode: int, stdout: str, stderr: str) -> None:
    """Raise the most specific error available for a failed dtctl call."""
    message = _envelope_error(stdout)
    if not message:
        lines = (stderr or stdout or "").strip().splitlines()
        message = lines[-1] if lines else f"exited {returncode} with no output"

    label = f"`dtctl {_label(args)}`"
    if _is_auth_error(message):
        raise DtctlAuthError(
            f"{label} failed to authenticate: {message}. "
            "Check `dtctl auth status`, then re-authenticate with `dtctl auth login` "
            "(or `dtctl auth refresh`) and re-run."
        )
    raise DtctlError(f"{label} exited {returncode}: {message}")


def _raw(args: list[str], timeout: int = 120) -> str:
    """Run dtctl and return stdout. Raises :class:`DtctlError` on failure."""
    if shutil.which("dtctl") is None:
        raise DtctlError(
            "dtctl not found on PATH. Install and configure it, or run with "
            "--transport http and a platform token."
        )
    cmd = ["dtctl", *args]
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise DtctlError(f"`dtctl {_label(args)}` timed out after {timeout}s") from exc
    if proc.returncode != 0:
        _raise_for(args, proc.returncode, proc.stdout, proc.stderr)
    # An `ok: false` envelope can also arrive with exit 0; treat it as a failure.
    if _envelope_error(proc.stdout):
        _raise_for(args, 0, proc.stdout, proc.stderr)
    return proc.stdout


def _json(args: list[str], context: str | None = None, timeout: int = 120) -> Any:
    """Run a dtctl command with JSON output and parse it."""
    full = [*args, "-o", "json", "--plain"]
    if context:
        full += ["--context", context]
    out = _raw(full, timeout=timeout)
    if not out.strip():
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise DtctlError(
            f"`dtctl {_label(args)}` did not return JSON: {exc}. "
            "Run the command by hand to see what it printed."
        ) from exc


def preflight(context: str | None = None) -> str:
    """Verify dtctl can actually authenticate before a long scan starts.

    Without this, a bad or missing credential is only discovered per-request, and
    a tenant with hundreds of documents produces hundreds of identical failures
    before reporting anything useful.
    """
    # `auth whoami` needs a real credential, so it detects a missing or expired
    # token. `auth status` is NOT sufficient — it prints the configured context and
    # exits 0 even when the referenced token is absent from the credential store.
    try:
        _json(["auth", "whoami"], context, timeout=60)
        return "ok"
    except DtctlAuthError:
        raise
    except DtctlError:
        # Older builds may lack `auth whoami`; fall back to a cheap authenticated
        # read rather than letting a scan start blind.
        _json(["get", "settings-schemas", "--chunk-size", "0"], context, timeout=60)
        return "ok"


def resolve_context(context: str | None = None) -> tuple[str, str]:
    """Return ``(context_name, environment_url)`` from the dtctl config.

    The environment URL is the base for report links; a scan works without it.
    """
    name = context or _raw(["config", "current-context"]).strip()
    if not name:
        raise DtctlError(
            "dtctl has no current context. Select one with `dtctl config use-context <name>` "
            "or pass --context."
        )
    environment = ""
    try:
        cfg = json.loads(_raw(["config", "view", "-o", "json"]))
        for entry in cfg.get("Contexts") or []:
            if entry.get("Name") == name:
                environment = (entry.get("Context") or {}).get("Environment", "")
                break
    except (DtctlError, json.JSONDecodeError, AttributeError):
        pass
    return name, environment


class DtctlClient:
    """Reaches the tenant through the dtctl CLI's current context.

    Same surface as :class:`HttpClient`, but needs no token and no tenant URL.
    """

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.context = getattr(cfg, "dtctl_context", None)

    # -- primitives ------------------------------------------------------

    def dql(self, query: str, max_records: int | None = None) -> list[dict[str, Any]]:
        args = ["query", query]
        if max_records is not None:
            args += ["--max-result-records", str(max_records)]
        result = _json(args, self.context, timeout=max(120, self.cfg.timeout))
        if isinstance(result, dict):
            return result.get("records") or []
        if isinstance(result, list):
            return result
        return []

    # -- sources ---------------------------------------------------------

    def fetch_settings_source(self, name: str, schema_id: str) -> SourceResult:
        """Read every object of one settings schema.

        A schema absent from the tenant is genuinely zero objects and stays
        ``complete``. Anything else is ``failed``, so an unreadable source can
        never be mistaken for an absence of usage.
        """
        result = SourceResult(name=name)
        try:
            rows = _json(
                ["get", "settings", "--schema", schema_id, "--chunk-size", _CHUNK],
                self.context,
                timeout=max(120, self.cfg.timeout),
            )
        except DtctlAuthError:
            raise
        except DtctlError as exc:
            message = str(exc).lower()
            if "404" in message or "not found" in message or "unknown schema" in message:
                result.reason = f"schema {schema_id} not present on tenant (0 objects)"
                return result
            result.degrade(FAILED, f"{schema_id}: {exc}")
            return result

        if not isinstance(rows, list):
            result.degrade(FAILED, f"listing {schema_id} returned an unexpected response shape")
            return result
        result.items = [_settings_item(name, schema_id, r) for r in rows if isinstance(r, dict)]
        result.items_checked = len(result.items)
        return result

    def fetch_slos(self) -> SourceResult:
        """Read every objective of the Service-Level Objectives app."""
        result = SourceResult(name=SLO_SOURCE)
        try:
            rows = _json(
                ["get", "slos", "--chunk-size", _CHUNK],
                self.context,
                timeout=max(120, self.cfg.timeout),
            )
        except DtctlAuthError:
            raise
        except DtctlError as exc:
            result.degrade(FAILED, f"listing SLOs failed: {exc}")
            return result

        if not isinstance(rows, list):
            result.degrade(FAILED, "listing SLOs returned an unexpected response shape")
            return result
        rows = [r for r in rows if isinstance(r, dict)]
        result.items = [_slo_item(r) for r in rows]
        result.items_checked = len(result.items)
        _note_dropped_sli(result, rows)
        return result

    def fetch_documents(self, doc_type: str, name: str) -> SourceResult:
        """List and fetch the content of every dashboard or notebook.

        Tenant-wide access is requested first. If the current context lacks
        ``document:documents:admin``, visible documents are still scanned but the
        source is ``partial`` so the result cannot be presented as clean.
        """
        result = SourceResult(name=name)

        admin_access = True
        try:
            listed = _json(
                ["get", f"{doc_type}s", "--admin-access", "--chunk-size", _CHUNK],
                self.context,
                timeout=max(180, self.cfg.timeout),
            )
        except DtctlError as admin_exc:
            admin_access = False
            try:
                listed = _json(
                    ["get", f"{doc_type}s", "--chunk-size", _CHUNK],
                    self.context,
                    timeout=max(180, self.cfg.timeout),
                )
            except DtctlError as exc:
                result.degrade(
                    FAILED,
                    f"listing {doc_type}s failed after admin-access attempt: {admin_exc}; {exc}",
                )
                return result
            result.degrade(
                PARTIAL,
                "tenant-wide document access unavailable; scanned only documents visible "
                "to the current dtctl identity (add document:documents:admin)",
            )

        if not isinstance(listed, list):
            result.degrade(FAILED, f"listing {doc_type}s returned an unexpected response shape")
            return result
        listed = [d for d in listed if isinstance(d, dict) and d.get("id")]
        result.items_checked = len(listed)
        if not listed:
            return result

        def _content(doc_id: str) -> Any:
            args = ["get", doc_type, doc_id]
            if admin_access:
                args.append("--admin-access")
            body = _json(args, self.context, timeout=min(self.cfg.timeout, 60))
            if isinstance(body, list):
                body = body[0] if body else None
            if not isinstance(body, dict):
                raise DtctlError(f"`dtctl get {doc_type}` returned an unexpected response shape")
            return body

        failed = _fetch_bodies(result, listed, doc_type, name, _content, self.cfg.max_workers)
        if result.state == FAILED:  # credentials died mid-sweep
            return result
        if failed:
            result.items_unread = len(failed)
            result.degrade(
                PARTIAL, f"{len(failed)}/{len(listed)} {doc_type} content fetches failed"
            )
        return result


# --------------------------------------------------------------------------
# Shared fetch helpers
# --------------------------------------------------------------------------


def _settings_item(name: str, schema_id: str, row: dict[str, Any]) -> dict[str, Any]:
    """Normalise one settings object into the common item shape.

    ``value.*`` comes first for the object name: dtctl's top-level ``summary`` is
    markdown-escaped (``GET requests \\- Performance``), so preferring it produced
    escaped names and made the two transports disagree about the same object. It
    stays as a last resort, with the escaping undone.
    """
    value = row.get("value") or {}
    return {
        "source": name,
        "kind": "SETTINGS/" + schema_id,
        "id": row.get("objectId"),
        "name": value.get("name")
        or value.get("title")
        or value.get("summary")
        or unescape_markdown(row.get("summary"))
        or row.get("objectId"),
        "scope": row.get("scope"),
        "body": row,
    }


def _slo_item(row: dict[str, Any]) -> dict[str, Any]:
    """Normalise one Service-Level Objectives app object into the item shape.

    The whole object is the body: an SLO carries its definition either as DQL in
    ``customSli.indicator`` or as a template binding in ``sliReference``, and a
    detector must be free to match anywhere. SLOs have no settings scope.
    """
    return {
        "source": SLO_SOURCE,
        "kind": SLO_KIND,
        "id": row.get("id"),
        "name": row.get("name") or row.get("id"),
        "scope": None,
        "body": row,
    }


def _note_dropped_sli(result: SourceResult, rows: list[dict[str, Any]]) -> None:
    """Degrade the SLO source for definitions dtctl did not pass through.

    Every SLO defines its indicator one of two ways: inline DQL in ``customSli``
    or a template binding in ``sliReference``. dtctl 0.30.3 models only the
    first, so a template-based SLO arrives with **neither** field — its
    definition and its variable values (which carry entity ids) are gone, and a
    detector run over that body would report no usage without ever having seen
    the configuration. The API itself returns both fields, so an object missing
    both is a transport gap, not an SLO without an indicator.

    Counting those as unread and degrading to ``partial`` is the honest state:
    usage-gated reporting must never present an unread definition as clean.
    """
    blind = [r for r in rows if not r.get("customSli") and not r.get("sliReference")]
    if not blind:
        return
    result.items_unread = len(blind)
    result.degrade(
        PARTIAL,
        f"{len(blind)}/{len(rows)} SLOs are template-based and dtctl {_DTCTL_VERIFIED} "
        "drops their `sliReference`, so their definition was not read. Re-run with "
        "`--transport http` (platform token, scope slo:slos:read) to read them in full",
    )


def _fetch_bodies(
    result: SourceResult,
    listed: list[dict[str, Any]],
    doc_type: str,
    name: str,
    fetch_one,
    max_workers: int,
) -> list[str]:
    """Fetch every document body in parallel into ``result.items``.

    Returns the list of failures. A :class:`DtctlAuthError` stops the sweep and
    marks the source ``failed``: credentials dying mid-run means every remaining
    fetch would fail identically, and logging hundreds of copies of the same
    error helps nobody.
    """
    failed: list[str] = []
    done = 0
    auth_lost = ""
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_one, d["id"]): (d["id"], d.get("name")) for d in listed}
        for fut in as_completed(futures):
            doc_id, doc_name = futures[fut]
            done += 1
            if auth_lost:
                fut.cancel()
                continue
            try:
                result.items.append(
                    {
                        "source": name,
                        "kind": doc_type.upper(),
                        "id": doc_id,
                        "name": doc_name,
                        "scope": None,
                        "body": strip_cached_results(fut.result()),
                    }
                )
            except DtctlAuthError as exc:
                auth_lost = str(exc)
                failed.append(f"{doc_id}: {exc}")
            except Exception as exc:  # noqa: BLE001 - one bad document must not abort
                failed.append(f"{doc_id}: {exc}")
            if done % 50 == 0 or done == len(futures):
                print(f"    {name}: {done}/{len(futures)} fetched", file=sys.stderr, flush=True)

    if auth_lost:
        result.items_unread = len(listed) - len(result.items)
        result.degrade(
            FAILED,
            f"authentication was lost after {len(result.items)}/{len(listed)} "
            f"{doc_type}s: {auth_lost}",
        )
    return failed


def gather_sources(client, log=None, include: set[str] | None = None) -> list[SourceResult]:
    """Fetch every configuration area, splitting the two custom-alert schemas.

    Pass *include* to restrict the scan to named sources; the default reads all
    of them.
    """
    sources: list[SourceResult] = []

    def fetch(name: str, operation) -> SourceResult:
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001 - failures belong in the report
            result = SourceResult(name=name)
            result.degrade(FAILED, f"reading {name} failed: {exc}")
            return result

    for name, doc_type in DOCUMENT_SOURCES:
        if include is not None and name not in include:
            continue
        if log:
            log(f"  fetching {name}...")
        sources.append(
            fetch(
                name,
                lambda doc_type=doc_type, name=name: client.fetch_documents(doc_type, name),
            )
        )

    if include is None or SLO_SOURCE in include:
        if log:
            log(f"  fetching {SLO_SOURCE} (Service-Level Objectives app)...")
        sources.append(fetch(SLO_SOURCE, client.fetch_slos))

    for name, schema in SETTINGS_SOURCES.items():
        if include is not None and name not in include:
            continue
        if log:
            log(f"  fetching {name} ({schema})...")
        sources.append(
            fetch(
                name,
                lambda name=name, schema=schema: client.fetch_settings_source(name, schema),
            )
        )

    return sources


__all__ = [
    "ApiError",
    "add_artifact_links",
    "artifact_link",
    "CLASSIC_SLO_FIELDS",
    "CLASSIC_SLO_SCHEMA",
    "CLASSIC_SLO_SOURCE",
    "COMPLETE",
    "ConfigError",
    "derive_url_pair",
    "DOCUMENT_SOURCES",
    "DtctlAuthError",
    "DtctlClient",
    "DtctlError",
    "FAILED",
    "gather_sources",
    "HttpClient",
    "intent_url",
    "is_shared_settings_field",
    "normalise_url",
    "PARTIAL",
    "preflight",
    "report_ui_url",
    "resolve_context",
    "SETTINGS_SOURCES",
    "SHARED_SETTINGS_FIELDS",
    "SLO_API_PATH",
    "SLO_KIND",
    "SLO_SOURCE",
    "SourceResult",
    "strip_cached_results",
    "unescape_markdown",
]
