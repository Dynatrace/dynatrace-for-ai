"""Running DQL against Grail, as one blocking call over an asynchronous API."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from ..config import SecretToken
from .transports import DqlAnswer
from .utils import MAX_FIELD_LEN, safe_error_hint, transport_errors_contained

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
    """The backend refused or failed the read itself."""


class DqlTimeoutError(DqlError):
    """The query did not finish inside the run's completion deadline."""


class DqlTransportError(DqlError):
    """The request never got an answer: a connection failure, or a per-request timeout.

    Its own type because a network hiccup, a refused read and a query that ran too long are three
    different things, and a run that cannot tell them apart records a false verdict for one of
    them.
    """


# A query the backend failed carries its own reason, and the client does not need to know which
# one to report it faithfully: the code and message travel with the error, unread. Nothing is
# inferred from their wording, so no spelling the platform may change can turn one outcome into
# another.
def _raise_terminal(payload: dict[str, Any], state: str, token: SecretToken) -> None:
    error = payload.get("error")
    error = error if isinstance(error, dict) else {}
    code = error.get("code")
    # Redacted before truncation, so a cut cannot leave a usable fragment behind: a backend is
    # free to quote the credential inside a message about it.
    message = token.redact(str(error.get("message", "")))[:MAX_FIELD_LEN]
    described = f"query {state}: code={code!r} message={message!r}"
    # CANCELLED is terminal too, but it is a state something else put the query in rather than a
    # read the backend refused, so it stays on the family error.
    if state == "FAILED":
        raise DqlReadError(described)
    raise DqlError(described)


# One rule covers every way the platform truncates, whether or not this client has heard of it: a
# limit this client predates would arrive as a type it does not know, and reading that as "all the
# rows" is the one answer that cannot be walked back. So a notification counts as a cap when it
# announces a limit, keyed on the words the type names and messages actually use.
_LIMIT_WORDS = ("limit", "stopped")

# Announces a limit, and is not one this tool's answers can be short by. It is the per-record
# ceiling on how many related entity ids a row may carry, and it is raised exactly when some record
# lost ids to it - not on every read that projects a relationship field. What makes tolerating it
# safe is therefore a rule the queries earn rather than a property of the notification: no read
# renders a to-many relationship field, and the two relationships that are projected - a process
# group's host group, a service's process group - are single-valued and so cannot reach the cap. An
# entity read that raises it while answering exactly is the ordinary case, and reading it as
# truncation would report a complete read as partial.
_TOLERATED_TYPES = frozenset({"RELATIONSHIP_RESULT_SIZE_LIMIT"})


def _announces_a_limit(notification: dict[str, Any]) -> bool:
    kind = str(notification.get("notificationType", ""))
    if kind in _TOLERATED_TYPES:
        return False
    said = f"{kind} {notification.get('message', '')}".lower()
    return any(word in said for word in _LIMIT_WORDS)


def _is_complete(payload: dict[str, Any]) -> bool:
    result = payload.get("result")
    metadata = result.get("metadata") if isinstance(result, dict) else None
    grail = metadata.get("grail") if isinstance(metadata, dict) else None
    notifications = grail.get("notifications") if isinstance(grail, dict) else None
    if not isinstance(notifications, list):
        return True
    return not any(
        isinstance(entry, dict) and _announces_a_limit(entry) for entry in notifications
    )


def _records_of(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result")
    records = result.get("records") if isinstance(result, dict) else None
    if records is None:
        return []
    if not isinstance(records, list):
        raise DqlError(f"unexpected records shape: {type(records).__name__}")
    return records


class DqlClient:
    """Executes DQL against Grail and blocks until the query finishes.

    Read-only in the sense that matters: nothing on the backend changes. `query:execute` and
    `query:cancel` are POSTs that create, update and delete nothing, so they are not writes and
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

    def execute(
        self, query: str, *, deadline_seconds: float = _DEFAULT_DEADLINE
    ) -> list[dict[str, Any]]:
        """The rows alone, for callers that cannot act on completeness."""
        return self.answer(query, deadline_seconds=deadline_seconds).records

    def answer(self, query: str, *, deadline_seconds: float = _DEFAULT_DEADLINE) -> DqlAnswer:
        if not query.strip():
            raise ValueError("query must be non-empty")
        payload = self._post(
            _EXECUTE_PATH, json={"query": query, "maxResultRecords": self._max_result_records}
        )
        request_token = payload.get("requestToken")
        try:
            return self._await_answer(payload, request_token, deadline_seconds)
        except Exception:
            # An abandoned query keeps consuming the tenant's budget until it finishes on its own.
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
                _raise_terminal(payload, str(state), self._token)
            if self._now() > deadline:
                raise DqlTimeoutError(f"query did not complete within {deadline_seconds}s")
            self._sleep(interval)
            interval = min(interval * 2, _MAX_POLL_INTERVAL)
            payload = self._get(_POLL_PATH, params={"request-token": request_token})

    def _cancel(self, request_token: Any) -> None:
        if not request_token:
            return
        try:
            with self._contained(_CANCEL_PATH):
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

    def _contained(self, path: str):
        return transport_errors_contained(
            path=path, token=self._token, error_type=DqlTransportError
        )

    def _post(self, path: str, *, json: dict[str, Any]) -> dict[str, Any]:
        with self._contained(path):
            response = self._http.post(self._base + path, headers=self._headers(), json=json)
        return self._payload(response, path)

    def _get(self, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
        with self._contained(path):
            response = self._http.get(self._base + path, headers=self._headers(), params=params)
        return self._payload(response, path)

    def _payload(self, response: httpx.Response, path: str) -> dict[str, Any]:
        if response.status_code not in (200, 202):
            raise DqlError(
                f"{path} failed: HTTP {response.status_code}"
                f"{safe_error_hint(response, self._token)}"
            )
        body = response.json()
        return body if isinstance(body, dict) else {}
