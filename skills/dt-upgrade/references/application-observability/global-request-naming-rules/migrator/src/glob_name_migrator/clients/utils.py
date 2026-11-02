"""Shared helpers for the HTTP clients."""

from __future__ import annotations

import httpx


def safe_error_hint(response: httpx.Response) -> str:
    """Return a sanitized error hint from the response.

    Only extracts well-known message fields from JSON bodies so that raw
    response text (which a misconfigured or malicious endpoint could use to
    echo request headers including auth tokens) is never surfaced in logs or
    terminal output.
    """
    try:
        payload = response.json()
        if not isinstance(payload, dict):
            return ""
        msg = (
            payload.get("message")
            or payload.get("errorMessage")
            or (payload.get("error") or {}).get("message")
            or ""
        )
        if msg:
            return f" message={str(msg)[:200]!r}"
    except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        # Body parsing is best-effort on an untrusted payload; any failure just
        # means no hint. It must never mask the HTTP error being raised.
        pass
    return ""
