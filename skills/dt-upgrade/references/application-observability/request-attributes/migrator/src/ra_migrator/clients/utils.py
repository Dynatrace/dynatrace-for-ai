"""Handling shared by both transports: containing transport failures, and safe error text."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import httpx

from ..config import SecretToken

MAX_FIELD_LEN = 200


@contextmanager
def transport_errors_contained(
    *, path: str, token: SecretToken, error_type: type[Exception]
) -> Iterator[None]:
    """Normalise every transport failure into the calling client's own error family.

    Callers then handle one family rather than a mix with raw `httpx` ones - which matters because
    a network timeout mistaken for a refused read makes a slow-but-succeeding query
    indistinguishable from a failure, and a run records the wrong outcome for it. Only the
    exception type and message are surfaced, token redacted first: an upstream may echo request
    headers into a transport error, and that text passes through no other allowlist.
    """
    try:
        yield
    except httpx.HTTPError as exc:
        detail = token.redact(f"{type(exc).__name__}: {exc}")[:MAX_FIELD_LEN]
        raise error_type(f"{path} transport failure: {detail}") from exc


def safe_error_hint(response: httpx.Response, token: SecretToken) -> str:
    """A sanitised hint about an error response: what it said, minus anything it echoed.

    Well-known fields of a JSON error envelope only, with **no** fallback to `response.text`: an
    echoing gateway, WAF or debug error page reflects the request headers, so raw text can carry
    the `Authorization` header into an exception message and on into a file the run writes. What
    survives the allowlist is redacted anyway, because a backend is free to quote the credential
    inside its own message. The caller keeps the status code, which carries no secret.
    """
    try:
        payload = response.json()
    except ValueError:
        # An unparseable body just means no hint, and must never mask the HTTP error the caller
        # is about to raise.
        return ""
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    error = error if isinstance(error, dict) else {}
    code = _field(error.get("code"))
    # The bare top-level `message` is what a host returns for an auth failure rejected ahead of
    # the API itself.
    message = _field(error.get("message")) or _field(payload.get("message"))
    parts = [
        rendered
        for rendered in (
            f"code={code!r}" if code else "",
            f"message={message!r}" if message else "",
        )
        if rendered
    ]
    return (" " + token.redact(" ".join(parts))) if parts else ""


def _field(value: object) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value)[:MAX_FIELD_LEN]
