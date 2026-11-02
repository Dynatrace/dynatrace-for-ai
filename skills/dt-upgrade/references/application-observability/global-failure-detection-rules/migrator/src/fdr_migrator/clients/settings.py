from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ..config import SecretToken
from .utils import safe_error_hint, transport_errors_contained

RULES_SCHEMA_ID = "builtin:failure-detection.environment.rules"
ZONES_SCHEMA_ID = "builtin:management-zones"

# Settings 2.0 is reached through the platform host's classic-API passthrough
_OBJECTS_PATH = "/platform/classic/environment-api/v2/settings/objects"
_FIELDS = "objectId,value"
_PAGE_SIZE = 500


@dataclass(frozen=True)
class RuleObject:
    object_id: str
    value: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.value.get("name") or "")

    @property
    def enabled(self) -> bool:
        return self.value.get("enabled") is not False


class SettingsError(RuntimeError):
    pass


class SettingsClient:
    """Read-only reader for Global Failure Detection Rules.

    Read-only here means *nothing on the backend changes*. The class deliberately exposes no
    method that creates, updates or deletes a settings object, so there is no write code path to
    misuse and no write scope to request.
    """

    def __init__(
        self,
        *,
        platform_url: str,
        platform_token: SecretToken,
        http: httpx.Client | None = None,
    ) -> None:
        if not platform_url:
            raise ValueError("platform_url is required")
        self._url = platform_url.rstrip("/") + _OBJECTS_PATH
        self._token = platform_token
        self._http = http or httpx.Client(timeout=60.0, trust_env=False)

    def list_rule_objects(self) -> list[RuleObject]:
        """Every rule on the tenant, in the order it is evaluated in.

        The order is load-bearing: rules are first-match-wins, and where a replacement has to be
        deployed is read off this list and nothing else. It holds because no `sort` parameter is
        passed - this schema stores an ordered list, whose elements come back in stored order
        unless a sort is asked for. Adding one would scramble every position silently.
        """
        return [_to_rule_object(item) for item in self._list_items(RULES_SCHEMA_ID)]

    def list_zone_names(self) -> dict[str, str]:
        """Every management zone on the tenant, by the object id a rule refers to it with.

        Read once for the whole run rather than once per rule: a rule stores the object id, the
        entity data carries the zone's name, and nothing in the id yields the name.
        """
        return {
            str(item.get("objectId") or ""): str((item.get("value") or {}).get("name") or "")
            for item in self._list_items(ZONES_SCHEMA_ID)
        }

    def _list_items(self, schema_id: str) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "schemaIds": schema_id,
            "fields": _FIELDS,
            "pageSize": _PAGE_SIZE,
        }
        items: list[dict[str, Any]] = []
        while True:
            payload = self._get(params)
            items.extend(payload.get("items") or [])
            next_key = payload.get("nextPageKey")
            if not next_key:
                return items
            # A continuation request carries the page key and nothing else: Settings 2.0 rejects
            # nextPageKey combined with the filter parameters that produced it.
            params = {"nextPageKey": next_key}

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        with transport_errors_contained(path=_OBJECTS_PATH, token=self._token, error_type=SettingsError):
            response = self._http.get(self._url, headers=self._headers(), params=params)
        if response.status_code != 200:
            raise SettingsError(
                f"settings objects read failed: HTTP {response.status_code}{safe_error_hint(response)}"
            )
        return response.json()

    def _headers(self) -> dict[str, str]:
        # The route accepts both "Api-Token" and "Bearer" for a platform token; Bearer is the
        # platform host's own convention and the one the DQL client uses.
        return {
            "Authorization": f"Bearer {self._token.reveal()}",
            "Accept": "application/json",
        }


def _to_rule_object(item: dict[str, Any]) -> RuleObject:
    value = item.get("value")
    return RuleObject(
        object_id=str(item.get("objectId") or ""),
        value=value if isinstance(value, dict) else {},
    )
