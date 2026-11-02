from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import SecretToken
from .utils import safe_error_hint, transport_errors_contained

_EXECUTE_PATH = "/platform/storage/query/v1/query:execute"
_POLL_PATH = "/platform/storage/query/v1/query:poll"
_CANCEL_PATH = "/platform/storage/query/v1/query:cancel"

_INITIAL_POLL_INTERVAL = 0.5
_MAX_POLL_INTERVAL = 30.0
_DEFAULT_DEADLINE = 300.0
_DEFAULT_MAX_RECORDS = 50_000


class DqlError(RuntimeError):
    pass


class DqlReadError(DqlError):
    pass


class DqlTimeoutError(DqlError):
    pass


class DqlTransportError(DqlError):
    pass


# A query the backend failed carries its own reason, and the client does not need to know which one
# to report it faithfully: the code and message travel with the error, unread. Nothing is inferred
# from their wording, so no spelling the platform may change can turn one outcome into another.
def _raise_terminal(payload: dict[str, Any], state: str) -> None:
    error = payload.get("error")
    error = error if isinstance(error, dict) else {}
    code = error.get("code")
    message = str(error.get("message", ""))[:200]
    described = f"query {state}: code={code!r} message={message!r}"
    # CANCELLED is terminal too, but it is a state something else put the query in rather than a
    # read the backend refused, so it stays on the family error.
    if state == "FAILED":
        raise DqlReadError(described)
    raise DqlError(described)


@dataclass(frozen=True)
class DqlAnswer:
    """The rows a query came back with, and whether they are all of them.

    The platform reports when it capped a result set, and a capped answer cannot be told from a
    complete one by its rows alone - so completeness travels with the answer rather than being
    asked about afterwards.
    """

    records: list[dict[str, Any]]
    complete: bool


# A truncated read is reported as a notification on a query that *succeeded* - the rows are real,
# the query ran, and only their completeness is in question. Nothing in the rows says so, and an
# aggregate over them is simply a smaller number, so the notification is the only evidence there is.
#
# One rule covers every way the platform truncates, whether or not this client has heard of it: a
# limit this client predates would arrive as a type it does not know, and reading that as "all the
# rows" is the one answer that cannot be walked back. So a notification counts as a cap when it
# announces a limit, keyed on the words the type names and messages actually use - never on
# "records", which the row-limit message does not contain.
# "limited" needs no entry of its own - it contains "limit".
#
# The three the platform names today all answer to that rule and are therefore not listed
# separately: API_RECORDS_LIMIT_ADDED (the result set was cut to a number of rows),
# SCAN_LIMIT_GBYTES (the read stopped after a volume of data was scanned, mid-answer) and
# BYTE_LIMIT_ADDED (the result was cut to a number of bytes). An allowlist of the three would only
# spell the same decision twice, and every name in it carries "limit" anyway.
_LIMIT_WORDS = ("limit", "stopped")


def _announces_a_limit(notification: dict[str, Any]) -> bool:
    said = f"{notification.get('notificationType', '')} {notification.get('message', '')}".lower()
    return any(word in said for word in _LIMIT_WORDS)


# Announces a limit, and is not one: a per-record ceiling on how many related entity ids a row may
# carry, raised on every read that projects a relationship field whatever comes back. Reading it as
# a truncation would report every entity read as partial and cost every rule its outcome, so it is
# named here rather than left to fall through the check below. Losing a row to it needs a shape
# these reads do not produce - an entity related to more ids than the ceiling - and the day one
# does, the fix is to ask along the relationship a different way, not to widen this list.
_TOLERATED_TYPES = frozenset({"RELATIONSHIP_RESULT_SIZE_LIMIT"})


def _looks_like_a_capped_result(notification: dict[str, Any]) -> bool:
    kind = str(notification.get("notificationType", ""))
    if kind in _TOLERATED_TYPES:
        return False
    return _announces_a_limit(notification)


def _is_complete(payload: dict[str, Any]) -> bool:
    result = payload.get("result")
    metadata = result.get("metadata") if isinstance(result, dict) else None
    grail = metadata.get("grail") if isinstance(metadata, dict) else None
    notifications = grail.get("notifications") if isinstance(grail, dict) else None
    if not isinstance(notifications, list):
        return True
    return not any(
        isinstance(entry, dict) and _looks_like_a_capped_result(entry) for entry in notifications
    )


def _records_of(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result")
    records = (result or {}).get("records") if isinstance(result, dict) else None
    if records is None:
        return []
    if not isinstance(records, list):
        raise DqlError(f"unexpected records shape: {type(records).__name__}")
    return records


class DqlClient:
    """Executes DQL against Grail and blocks until the query finishes.

    Read-only in the sense that matters: nothing on the backend changes. ``query:execute`` and
    ``query:cancel`` are POSTs that create, update and delete nothing, so they are not writes and
    must not be "fixed" into GETs.
    """

    def __init__(
        self,
        *,
        platform_url: str,
        platform_token: SecretToken,
        http: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_result_records: int = _DEFAULT_MAX_RECORDS,
    ) -> None:
        if not platform_url:
            raise ValueError("platform_url is required")
        self._base = platform_url.rstrip("/")
        self._token = platform_token
        self._http = http or httpx.Client(timeout=60.0, trust_env=False)
        self._sleep = sleeper
        self._now = clock
        self._max_result_records = max_result_records

    def execute(self, query: str, *, deadline_seconds: float = _DEFAULT_DEADLINE) -> list[dict[str, Any]]:
        """The rows alone, for callers that cannot act on completeness."""
        return self.answer(query, deadline_seconds=deadline_seconds).records

    def answer(self, query: str, *, deadline_seconds: float = _DEFAULT_DEADLINE) -> DqlAnswer:
        if not query.strip():
            raise ValueError("query must be non-empty")
        payload = self._post(_EXECUTE_PATH, json={"query": query, "maxResultRecords": self._max_result_records})
        request_token = payload.get("requestToken")
        try:
            return self._await_answer(payload, request_token, deadline_seconds)
        except Exception:
            # An abandoned query keeps consuming the tenant's budget until it finishes on its
            # own. Cancelling changes nothing on the backend - a POST, not a write.
            self._cancel(request_token)
            raise

    def _await_answer(
        self, payload: dict[str, Any], request_token: Any, deadline_seconds: float
    ) -> DqlAnswer:
        deadline = self._now() + deadline_seconds
        interval = _INITIAL_POLL_INTERVAL
        while True:
            state = payload.get("state")
            if state == "SUCCEEDED":
                return DqlAnswer(_records_of(payload), complete=_is_complete(payload))
            if state in ("FAILED", "CANCELLED"):
                _raise_terminal(payload, str(state))
            if self._now() > deadline:
                raise DqlTimeoutError(f"query did not complete within {deadline_seconds}s")
            self._sleep(interval)
            interval = min(interval * 2, _MAX_POLL_INTERVAL)
            payload = self._get(_POLL_PATH, params={"request-token": request_token})

    def _cancel(self, request_token: Any) -> None:
        if not request_token:
            return
        try:
            with transport_errors_contained(
                path=_CANCEL_PATH, token=self._token, error_type=DqlTransportError
            ):
                self._http.post(
                    self._base + _CANCEL_PATH,
                    headers=self._headers(),
                    params={"request-token": request_token},
                )
        except DqlError:
            # Best effort only: a cancel that cannot be delivered must never replace the error
            # that caused the abandonment in the first place.
            pass

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token.reveal()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _post(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        with transport_errors_contained(path=path, token=self._token, error_type=DqlTransportError):
            response = self._http.post(self._base + path, headers=self._headers(), json=json)
        return self._payload(response, path)

    def _get(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        with transport_errors_contained(path=path, token=self._token, error_type=DqlTransportError):
            response = self._http.get(self._base + path, headers=self._headers(), params=params)
        return self._payload(response, path)

    def _payload(self, response: httpx.Response, path: str) -> dict[str, Any]:
        if response.status_code not in (200, 202):
            raise DqlError(f"{path} failed: HTTP {response.status_code}{safe_error_hint(response)}")
        body = response.json()
        return body if isinstance(body, dict) else {}
