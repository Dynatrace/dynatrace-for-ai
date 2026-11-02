"""Reading request attributes from Config v1, which takes two calls per attribute."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

from ..config import SecretToken
from .transports import AttributeStub, RateLimited
from .utils import safe_error_hint, transport_errors_contained

_BASE_PATH = "/api/config/v1/service/requestAttributes"
# The endpoint defaults it to false, and without it a scope's `processGroup` condition is left
# out of the answer entirely - absent, not null, indistinguishable from a scope that never had
# one. The scope then reads broader than it is. There is no switch for it here: a partially
# read scope is never the wanted answer.
_PROCESS_GROUP_REFERENCES = "includeProcessGroupReferences=true"

_ATTEMPTS = 5
_BACKOFF_BASE = 0.25
_TOO_MANY_REQUESTS = 429


class ConfigV1Error(RuntimeError):
    """Every way a Config v1 read can fail, as one family the caller handles.

    A transport failure normalises into it too, so no raw `httpx` exception escapes the reader.
    """


class ConfigV1RateLimitError(ConfigV1Error, RateLimited):
    """The retry budget for a rate-limited read is spent."""


class ConfigV1Client:
    """Read-only reader for the tenant's request attributes.

    Read-only in the sense that matters: the class exposes no method that creates, updates or
    deletes a configuration, so there is no write code path to misuse and no write scope to ask
    for.
    """

    def __init__(
        self,
        *,
        classic_url: str,
        platform_token: SecretToken,
        http: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not classic_url:
            raise ValueError("classic_url is required")
        self._base = classic_url.rstrip("/") + _BASE_PATH
        self._token = platform_token
        self._http = http or httpx.Client(timeout=60.0, trust_env=False)
        self._sleep = sleeper

    def list_stubs(self) -> list[AttributeStub]:
        """Every request attribute the tenant holds, as the list endpoint returns them.

        Id and name only: the list endpoint answers with stubs, and nothing about how many are
        enabled can be read off them.
        """
        payload = self._get(self._base, "request attribute list")
        return [
            AttributeStub(str(value.get("id") or ""), str(value.get("name") or ""))
            for value in payload.get("values") or []
        ]

    def read_body(self, attribute_id: str) -> dict[str, Any]:
        if not attribute_id:
            raise ValueError("attribute_id is required")
        return self._get(
            f"{self._base}/{attribute_id}?{_PROCESS_GROUP_REFERENCES}",
            f"request attribute {attribute_id}",
        )

    def _get(self, url: str, described: str) -> dict[str, Any]:
        """One read, retried while the environment says it is too busy to answer.

        The backoff is blind by design. A Config v1 429 means the environment's request thread
        pool and its queue are full, and the rate-limit headers that would say for how long are
        documented for Managed only - so on SaaS there is nothing to honour and the retry budget
        is the whole story.
        """
        for attempt in range(_ATTEMPTS):
            with transport_errors_contained(
                path=_BASE_PATH, token=self._token, error_type=ConfigV1Error
            ):
                response = self._http.get(url, headers=self._headers())
            if response.status_code != _TOO_MANY_REQUESTS:
                if not response.is_success:
                    raise ConfigV1Error(
                        f"{described} failed: HTTP {response.status_code}"
                        f"{safe_error_hint(response, self._token)}"
                    )
                body = response.json()
                return body if isinstance(body, dict) else {}
            if attempt + 1 < _ATTEMPTS:
                self._sleep(_BACKOFF_BASE * 2**attempt)
        # A spent 429 budget fails the whole read rather than yielding a shorter list: it says
        # nothing about the request attribute being read, and a list read as complete when it is
        # not under-reports the affected set, which is the one failure nothing downstream can
        # notice.
        raise ConfigV1RateLimitError(
            f"{described} failed: rate limited on all {_ATTEMPTS} attempts"
        )

    def _headers(self) -> dict[str, str]:
        # The classic host takes the platform token as an Api-Token; the endpoint accepts it for
        # the list read and the per-id read alike.
        return {
            "Authorization": f"Api-Token {self._token.reveal()}",
            "Accept": "application/json",
        }
