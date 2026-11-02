"""Dynatrace Config v1 REST client (request naming rules).

Implements the read paths needed for migration (list/get) plus the write
paths used by ``apply``: ``post_rule`` (POST a replacement) and
``reorder_rules`` (PUT the evaluation order).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ..auth.api_token import auth_header
from .utils import safe_error_hint

_BASE_PATH = "/api/config/v1/service/requestNaming"


@dataclass(frozen=True)
class RuleSummary:
    """Stub entry returned by the list endpoint."""

    id: str
    name: str | None


class ConfigV1Client:
    """Minimal client for the request naming Config v1 endpoints."""

    def __init__(
        self,
        *,
        tenant_url: str,
        api_token: str,
        http: httpx.Client | None = None,
    ) -> None:
        if not tenant_url:
            raise ValueError("tenant_url is required")
        self._base = tenant_url.rstrip("/") + _BASE_PATH
        self._headers = auth_header(api_token) | {"Accept": "application/json"}
        self._http = http or httpx.Client(timeout=60.0, trust_env=False)

    def list_rules(self) -> list[RuleSummary]:
        """Return all request naming rule stubs (id + name)."""

        response = self._http.get(self._base, headers=self._headers)
        _raise_for_status(response, "list_rules")
        payload = response.json()
        return [
            RuleSummary(id=v["id"], name=v.get("name"))
            for v in payload.get("values", [])
        ]

    def get_rule(self, rule_id: str) -> dict[str, Any]:
        """Return the full rule body for ``rule_id``."""

        if not rule_id:
            raise ValueError("rule_id is required")
        response = self._http.get(f"{self._base}/{rule_id}", headers=self._headers)
        _raise_for_status(response, f"get_rule({rule_id})")
        return response.json()

    def post_rule(self, body: dict[str, Any]) -> str:
        """POST a new RequestNamingDto; returns the assigned rule ID."""
        headers = self._headers | {"Content-Type": "application/json"}
        response = self._http.post(self._base, headers=headers, json=body)
        _raise_for_status(response, "post_rule")
        return response.json()["id"]

    def reorder_rules(self, ordered_ids: list[str]) -> None:
        """PUT the full evaluation order for all request naming rules.

        ``ordered_ids`` must contain every existing rule ID (including newly
        posted ones). Expects ``{"values": [{"id": "<id>"}, ...]}``.
        """
        headers = self._headers | {"Content-Type": "application/json"}
        body = {"values": [{"id": rid} for rid in ordered_ids]}
        response = self._http.put(f"{self._base}/order", headers=headers, json=body)
        _raise_for_status(response, "reorder_rules")


class ConfigV1Error(RuntimeError):
    """Raised on Config v1 REST failures with status/body context."""


def _raise_for_status(response: httpx.Response, op: str) -> None:
    if 200 <= response.status_code < 300:
        return
    raise ConfigV1Error(
        f"{op} failed: HTTP {response.status_code}{safe_error_hint(response)}"
    )
