from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx

from ..config import SecretToken

_MAX_FIELD_LEN = 200
_MAX_VIOLATIONS = 5


def safe_error_hint(response: httpx.Response) -> str:
    """Return a sanitised hint about an error response.

    Well-known fields of a JSON error envelope only, with **no** fallback to ``response.text``:
    an echoing gateway, WAF or debug error page reflects the request headers, so raw text can
    carry the ``Authorization`` header into an exception message and on into the on-disk report.
    The caller keeps the status code, which carries no secret.
    """
    try:
        payload = response.json()
    except Exception:  # pylint: disable=broad-exception-caught
        # Parsing an untrusted body is best-effort; any failure just means no hint, and must
        # never mask the HTTP error the caller is about to raise.
        return ""
    if not isinstance(payload, dict):
        return ""

    error = payload.get("error")
    error = error if isinstance(error, dict) else {}
    # Both APIs document the envelope {error: {code, message, details}}; the bare top-level
    # `message` is what the platform host returns for auth failures rejected ahead of the API.
    code = _field(error.get("code"))
    message = _field(error.get("message")) or _field(payload.get("message"))

    parts = []
    if code:
        parts.append(f"code={code!r}")
    if message:
        parts.append(f"message={message!r}")
    violations = _violations(error)
    if violations:
        parts.append(f"violations={violations!r}")
    return (" " + " ".join(parts)) if parts else ""


def _violations(error: dict[str, Any]) -> str:
    """Summarise a Settings 2.0 ``constraintViolations`` list.

    Still an allowlist: only the ``path`` and ``message`` the API generates are read. Without them
    the envelope says no more than "Constraints violated.", which does not name the offending
    parameter.
    """
    raw = error.get("constraintViolations")
    if not isinstance(raw, list):
        return ""
    rendered = [
        f"{_field(v.get('path'))}: {_field(v.get('message'))}"
        for v in raw[:_MAX_VIOLATIONS]
        if isinstance(v, dict)
    ]
    return "; ".join(p for p in rendered if p.strip(": "))


def _field(value: Any) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value)[:_MAX_FIELD_LEN]


@contextmanager
def transport_errors_contained(
    *, path: str, token: SecretToken, error_type: type[Exception]
) -> Iterator[None]:
    """Normalise every transport failure into the calling client's own error family.

    Callers handle one error family rather than a mix with raw ``httpx`` ones. Only the exception
    type and message are surfaced, token redacted first - an upstream may echo request headers
    into a transport error, and that text never passes through :func:`safe_error_hint`.
    """
    try:
        yield
    except httpx.HTTPError as exc:
        detail = token.redact(f"{type(exc).__name__}: {exc}")[:_MAX_FIELD_LEN]
        raise error_type(f"{path} transport failure: {detail}") from exc
