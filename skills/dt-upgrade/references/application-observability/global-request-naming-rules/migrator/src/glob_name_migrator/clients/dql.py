"""Dynatrace Platform Storage Query (DQL) API client.

Wraps the asynchronous ``query:execute`` / ``query:poll`` flow into a single
synchronous ``execute(dql) -> records`` call. Polling uses exponential backoff
capped at 30s; the overall wait is bounded by ``timeout_seconds``.

Read-limit and timeout failures surface as typed exceptions and are NOT
retried at this level; query_executor implements shifted-window retries above the client.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .utils import safe_error_hint

_EXECUTE_PATH = "/platform/storage/query/v1/query:execute"
_POLL_PATH = "/platform/storage/query/v1/query:poll"
_CANCEL_PATH = "/platform/storage/query/v1/query:cancel"

_INITIAL_POLL_INTERVAL = 0.5
_MAX_POLL_INTERVAL = 30.0
_DEFAULT_TIMEOUT = 300.0  # 5 minutes hard cap per query


class DqlClient:
    """Synchronous DQL executor backed by the async storage query API."""

    def __init__(
        self,
        *,
        tenant_url: str,
        bearer_token_provider,  # callable returning a fresh bearer string
        http: httpx.Client | None = None,
        sleeper=time.sleep,
        max_result_records: int = 50_000,
    ) -> None:
        if not tenant_url:
            raise ValueError("tenant_url is required")
        if not callable(bearer_token_provider):
            raise ValueError("bearer_token_provider must be callable")
        self._base = tenant_url.rstrip("/")
        self._token_provider = bearer_token_provider
        self._http = http or httpx.Client(timeout=60.0, trust_env=False)
        self._sleep = sleeper
        self._max_result_records = max_result_records

    def execute_with_meta(
        self,
        query: str,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Run ``query`` to completion and return ``(records, grail_metadata)``.

        ``grail_metadata`` is the full ``result.metadata.grail`` dict from the
        response — empty dict when the field is absent.
        """
        if not query.strip():
            raise ValueError("query must be non-empty")

        request_token = self._start(query)
        deadline = time.monotonic() + timeout_seconds
        interval = _INITIAL_POLL_INTERVAL
        try:
            while True:
                if time.monotonic() > deadline:
                    raise DqlTimeoutError(
                        f"query did not complete within {timeout_seconds}s"
                    )
                payload = self._poll(request_token)
                state = payload.get("state")
                if state == "SUCCEEDED":
                    records = _extract_records(payload)
                    grail = payload.get("result", {}).get("metadata", {}).get("grail", {})
                    return records, grail
                if state in ("FAILED", "CANCELLED"):
                    self._raise_typed_failure(payload, state)
                # RUNNING / NOT_STARTED — wait and try again.
                self._sleep(interval)
                interval = min(interval * 2, _MAX_POLL_INTERVAL)
        except Exception:
            # Best-effort cancel so the server doesn't keep computing.
            self._safe_cancel(request_token)
            raise

    def execute(
        self,
        query: str,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT,
    ) -> list[dict[str, Any]]:
        """Run ``query`` to completion and return its record rows."""
        records, _ = self.execute_with_meta(query, timeout_seconds=timeout_seconds)
        return records

    # ----- internal helpers -----

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token_provider()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _start(self, query: str) -> str:
        response = self._http.post(
            self._base + _EXECUTE_PATH,
            headers=self._headers(),
            json={"query": query, "maxResultRecords": self._max_result_records},
        )
        if response.status_code not in (200, 202):
            raise DqlError(
                f"query:execute failed: HTTP {response.status_code}"
                f"{safe_error_hint(response)}"
            )
        payload = response.json()
        token = payload.get("requestToken")
        if not token:
            # Some platforms inline the result on the execute call when the
            # query is trivially cheap. Treat that as a successful immediate
            # completion.
            if payload.get("state") == "SUCCEEDED":
                # Stash a sentinel; callers will never reach _poll.
                return _InlineRecords.wrap(payload)
            raise DqlError(f"query:execute missing requestToken: keys={list(payload)}")
        return token

    def _poll(self, request_token: str) -> dict[str, Any]:
        if request_token.startswith(_InlineRecords.PREFIX):
            return _InlineRecords.unwrap(request_token)
        response = self._http.get(
            self._base + _POLL_PATH,
            headers=self._headers(),
            params={"request-token": request_token},
        )
        if response.status_code != 200:
            raise DqlError(
                f"query:poll failed: HTTP {response.status_code}"
                f"{safe_error_hint(response)}"
            )
        return response.json()

    def _safe_cancel(self, request_token: str) -> None:
        if request_token.startswith(_InlineRecords.PREFIX):
            return
        try:
            self._http.post(
                self._base + _CANCEL_PATH,
                headers=self._headers(),
                params={"request-token": request_token},
            )
        except Exception:  # pragma: no cover - best-effort cleanup  # pylint: disable=broad-exception-caught
            pass

    def _raise_typed_failure(self, payload: dict[str, Any], state: str) -> None:
        error = payload.get("error") or {}
        code = error.get("code")
        message = error.get("message", "")
        details = error.get("details", "")
        if _looks_like_read_limit(error):
            raise DqlReadLimitError(
                f"query exceeded read volume limit: code={code} message={message!r}"
            )
        raise DqlError(
            f"query {state}: code={code} message={message!r} details={details!r}"
        )


def _extract_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result") or {}
    records = result.get("records")
    if records is None:
        # Some shapes nest under ``data``.
        records = result.get("data") or []
    if not isinstance(records, list):
        raise DqlError(f"unexpected records shape: {type(records).__name__}")
    return records


def _looks_like_read_limit(error: dict[str, Any]) -> bool:
    blob = (str(error.get("code", "")) + " " + str(error.get("message", ""))).lower()
    return "read" in blob and "limit" in blob


class _InlineRecords:
    """Sentinel-encoding for the (rare) inline-result case of execute."""

    PREFIX = "__inline__:"

    @staticmethod
    def wrap(payload: dict[str, Any]) -> str:
        """Encode payload as a sentinel token string."""
        # Round-trip through JSON to keep _poll's signature stable.
        return _InlineRecords.PREFIX + json.dumps(payload)

    @staticmethod
    def unwrap(token: str) -> dict[str, Any]:
        """Decode a sentinel token back to the original payload dict."""
        return json.loads(token[len(_InlineRecords.PREFIX):])


class DqlError(RuntimeError):
    """Generic DQL execution failure (transport, schema, query error)."""


class DqlReadLimitError(DqlError):
    """Query hit the Grail read-volume limit. Not retried by the client."""


class DqlTimeoutError(DqlError):
    """Polling exceeded the configured per-query timeout."""
