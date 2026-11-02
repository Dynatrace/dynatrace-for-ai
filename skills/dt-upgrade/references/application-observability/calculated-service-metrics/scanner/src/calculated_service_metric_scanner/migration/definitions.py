"""Read classic calculated service metric definitions from the Configuration API.

The migration verdict is computed from the definition, so every metric that gets a verdict has
to be fetched. Two calls: one listing of what the tenant defines, then one definition each.

Only the classic Configuration API answers this. A platform token (``dt0s16.*``) is rejected
with *unsupported authorization scheme 'Api-Token'*, and the platform proxy does not expose the
``/api/config/v1`` family, so a classic ``dt0c01.*`` token with ``ReadConfig`` is required —
under the HTTP transport as well as under ``dtctl``, which has no Config API v1 command at all.
Without one the migration assessment is reported as unavailable rather than as *nothing to
migrate*.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..shared import FAILED, PARTIAL, SourceResult

LIST_ENDPOINT = "/api/config/v1/calculatedMetrics/service"
CLASSIC_TOKEN_PREFIX = "dt0c01."


class ClassicApiError(RuntimeError):
    pass


def classic_token() -> str:
    """The classic token, or an empty string.

    Read from the environment only. A token on the command line ends up in shell history and in
    the process list, and this one carries ``ReadConfig`` over the whole tenant.
    """
    value = (os.environ.get("DT_CLASSIC_TOKEN") or "").strip()
    return value if value.startswith(CLASSIC_TOKEN_PREFIX) else ""


def _classic_headers(client) -> dict[str, str] | None:
    """The client's classic ``Api-Token`` headers, or ``None`` when they carry no classic token.

    The presence of the attribute says nothing: the HTTP transport sets ``classic_headers``
    unconditionally and falls back to the platform token when no classic token is configured,
    and that token is rejected by Configuration API v1. Only a ``dt0c01.*`` token counts, so
    the caller that has none is told to set one instead of being sent to fail against the API.
    """
    headers = getattr(client, "classic_headers", None)
    if not isinstance(headers, dict):
        return None
    authorization = str(headers.get("Authorization") or "")
    if not authorization.startswith(f"Api-Token {CLASSIC_TOKEN_PREFIX}"):
        return None
    return headers


def _get(client, url: str, timeout: int) -> Any:
    """GET *url* against the classic API, reusing the shared client where there is one.

    The HTTP transport already holds a client with the classic ``Api-Token`` header and its
    retry policy, so it is used as-is -- but only when that header really carries a classic
    token, see :func:`_classic_headers`. ``dtctl`` has no classic client, and rather than teach
    the shared layer a Config API v1 command that only this topic needs, the request is made
    directly here with the same token.
    """
    headers = _classic_headers(client)
    if headers is not None and getattr(client, "get", None) is not None:
        try:
            return client.get(url, headers=headers)
        except Exception as exc:  # noqa: BLE001 - the shared client raises its own error type
            # Uniform error type: the caller degrades the source on ClassicApiError, and a raw
            # transport error escaping from here would abort the whole scan instead.
            raise ClassicApiError(str(exc)) from exc
    token = classic_token()
    if not token:
        raise ClassicApiError("no classic token")
    request = urllib.request.Request(
        url, headers={"Authorization": f"Api-Token {token}", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:200]
        raise ClassicApiError(f"HTTP {exc.code} -- {url}: {body}") from exc
    except Exception as exc:  # noqa: BLE001 - transport errors become report state
        raise ClassicApiError(str(exc)) from exc


def fetch_definitions(
    client,
    classic_url: str,
    *,
    timeout: int = 60,
    max_workers: int = 10,
) -> tuple[dict[str, dict[str, Any]], SourceResult]:
    """Every calculated service metric defined on the tenant, keyed by classic key.

    The listing is what makes the assessment complete: a metric nothing references today still
    stops receiving data in Phase 3, and whether anybody looks at it in an ad-hoc query leaves
    no configuration behind to find.
    """
    source = SourceResult(name="calculated_metric_definitions")
    if not classic_url:
        source.degrade(FAILED, "no classic API URL could be derived for this tenant")
        return {}, source
    if _classic_headers(client) is None and not classic_token():
        source.degrade(
            FAILED,
            "set DT_CLASSIC_TOKEN to a classic token with ReadConfig; Configuration API v1 "
            "rejects a platform token and dtctl cannot call it",
        )
        return {}, source

    try:
        listing = _get(client, classic_url.rstrip("/") + LIST_ENDPOINT, timeout)
    except ClassicApiError as exc:
        source.degrade(FAILED, f"listing the tenant's calculated service metrics failed: {exc}")
        return {}, source
    if not isinstance(listing, dict):
        # A 200 that is not the documented object leaves the assessment without its input. Said
        # out loud, like an unreadable definition is: reading `values` off it would raise past
        # the handling above and take the whole scan down with it.
        source.degrade(
            FAILED,
            "listing the tenant's calculated service metrics returned an unexpected shape "
            f"({type(listing).__name__} rather than an object with a `values` list)",
        )
        return {}, source

    keys: list[str] = []
    names: dict[str, str] = {}
    for value in listing.get("values") or []:
        if not isinstance(value, dict):
            continue
        key = value.get("id") or value.get("tsmMetricKey")
        if isinstance(key, str) and key.startswith("calc:service."):
            keys.append(key)
            if isinstance(value.get("name"), str):
                names[key] = value["name"]
    source.items_checked = len(keys)
    source.reason = "Configuration API calculatedMetrics/service"

    def one(key: str) -> tuple[str, dict[str, Any] | str]:
        url = (
            classic_url.rstrip("/")
            + LIST_ENDPOINT
            + "/"
            + urllib.parse.quote(key, safe="")
        )
        try:
            return key, _get(client, url, timeout)
        except Exception as exc:  # noqa: BLE001 - one unreadable definition is not a failed scan
            # Broad on purpose: the shared HTTP client raises its own error type, and one
            # metric the token cannot read must degrade that metric, not abort the pass over
            # the other 346.
            return key, str(exc)

    definitions: dict[str, dict[str, Any]] = {}
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        for key, result in pool.map(one, keys):
            if isinstance(result, dict) and result.get("tsmMetricKey"):
                definitions[key] = result
            else:
                failed.append(key)
    if failed:
        # A definition that did not arrive is not a metric without a verdict problem -- it is a
        # metric whose verdict is unknown, and saying so is the difference between an honest
        # partial assessment and a silent hole in it.
        source.items_unread = len(failed)
        source.degrade(
            PARTIAL,
            f"{len(failed)} definition(s) could not be read, so those metrics carry no "
            "migration verdict",
        )
    for key, definition in definitions.items():
        definition.setdefault("tsmMetricKey", key)
        if not definition.get("name") and names.get(key):
            definition["name"] = names[key]
    return definitions, source
