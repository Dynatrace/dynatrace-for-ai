from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .clients.settings import RuleObject
from .config import AppConfig

PROBE_QUERY = "fetch spans, from:now()-5m | fields start_time | limit 1"

CREDENTIAL_CHECK = "credential kind"
URL_CHECK = "tenant URL"
SETTINGS_CHECK = "Settings 2.0 read"
GRAIL_CHECK = "Grail query"


class RuleReader(Protocol):

    def list_rule_objects(self) -> list[RuleObject]: ...


class SettingsReader(RuleReader, Protocol):

    def list_zone_names(self) -> dict[str, str]: ...


class QueryRunner(Protocol):
    def execute(self, query: str, *, deadline_seconds: float = ...) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def run_connection_checks(
    config: AppConfig,
    *,
    settings_client: RuleReader,
    dql_client: QueryRunner,
) -> list[CheckResult]:
    """Prove a run can work before one is attempted.
    """
    return [
        CheckResult(CREDENTIAL_CHECK, True, f"platform token {config.platform_token}"),
        CheckResult(URL_CHECK, True, config.platform_url),
        _settings_check(settings_client),
        _grail_check(dql_client),
    ]


def _settings_check(settings_client: RuleReader) -> CheckResult:
    try:
        objects = settings_client.list_rule_objects()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return CheckResult(SETTINGS_CHECK, False, str(exc))
    return CheckResult(SETTINGS_CHECK, True, f"read {len(objects)} Global Failure Detection Rule(s)")


def _grail_check(dql_client: QueryRunner) -> CheckResult:
    try:
        records = dql_client.execute(PROBE_QUERY)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return CheckResult(GRAIL_CHECK, False, str(exc))
    if not records:
        # The grant is proven either way, so this is not a failed check. It is still worth saying:
        # span-side work in a later run has nothing to read from a query window with no spans in it.
        return CheckResult(
            GRAIL_CHECK,
            True,
            "query succeeded but returned 0 spans in the last 5m - "
            "span-side rules will find no data in such a query window",
        )
    return CheckResult(GRAIL_CHECK, True, f"query returned {len(records)} span(s)")
