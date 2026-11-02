from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .utils import safe_error_hint

_BASE_PATH = "/api/config/v1/service/detectionRules"


@dataclass(frozen=True)
class RuleStub:
    id: str
    name: str | None
    rule_type: str


class ConfigV1Client:
    def __init__(
        self,
        *,
        classic_url: str,
        api_token: str,
        http: httpx.Client | None = None,
    ) -> None:
        if not classic_url:
            raise ValueError("classic_url is required")
        self._base = classic_url.rstrip("/") + _BASE_PATH
        self._headers = {"Authorization": f"Api-Token {api_token}", "Accept": "application/json"}
        self._http = http or httpx.Client(timeout=60.0, trust_env=False)

    def list_rules(self, rule_type: str) -> list[RuleStub]:
        response = self._http.get(f"{self._base}/{rule_type}", headers=self._headers)
        _raise_for_status(response, f"list_rules({rule_type})")
        return [
            RuleStub(id=v["id"], name=v.get("name"), rule_type=rule_type)
            for v in response.json().get("values", [])
        ]

    def list_all_rules(self) -> list[RuleStub]:
        return self.list_rules("FULL_WEB_REQUEST") + self.list_rules("FULL_WEB_SERVICE")

    def get_rule(self, rule_type: str, rule_id: str) -> dict[str, Any]:
        if not rule_id:
            raise ValueError("rule_id is required")
        response = self._http.get(f"{self._base}/{rule_type}/{rule_id}", headers=self._headers)
        _raise_for_status(response, f"get_rule({rule_type}, {rule_id})")
        return response.json()


class ConfigV1Error(RuntimeError):
    pass


def _raise_for_status(response: httpx.Response, op: str) -> None:
    if 200 <= response.status_code < 300:
        return
    raise ConfigV1Error(f"{op} failed: HTTP {response.status_code}{safe_error_hint(response)}")
