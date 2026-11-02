"""Proving a run can work before one is attempted."""

from __future__ import annotations

from dataclasses import dataclass

from .clients.transports import AttributeStub, ConfigReader, QueryRunner
from .dql.windowing import QueryWindow

CONFIG_LIST_CHECK = "request attribute list"
CONFIG_BODY_CHECK = "request attribute body"
ENTITY_QUERY_CHECK = "entity query"
SPAN_QUERY_CHECK = "span query"
FIELD_METADATA_CHECK = "span field metadata"

ENTITY_PROBE = "fetch dt.entity.process_group | fields id | limit 1"
FIELD_METADATA_PROBE = (
    'fieldsSnapshot spans | filter matchesValue(field, "primary_tags.*") | fields field'
)


def span_probe(window: QueryWindow) -> str:
    return f"fetch spans, {window.timeframe} | fields start_time | limit 1"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def run_connection_checks(
    config_reader: ConfigReader, query_runner: QueryRunner, *, window: QueryWindow
) -> list[CheckResult]:
    """Five probes, each exercising a shape a run depends on.

    A grant is proven by exercising it rather than by reading a token's scope list: the mapping
    from a scope string to a permitted command is not something the docs settle, while a probe
    that runs the real shape cannot be wrong about it.
    """
    listed, stubs = _config_list_check(config_reader)
    return [
        listed,
        _config_body_check(config_reader, stubs),
        _query_check(ENTITY_QUERY_CHECK, query_runner, ENTITY_PROBE),
        _query_check(SPAN_QUERY_CHECK, query_runner, span_probe(window)),
        _query_check(FIELD_METADATA_CHECK, query_runner, FIELD_METADATA_PROBE),
    ]


def _config_list_check(config_reader: ConfigReader) -> tuple[CheckResult, list[AttributeStub]]:
    try:
        stubs = config_reader.list_stubs()
    except Exception as failure:  # pylint: disable=broad-exception-caught
        return CheckResult(CONFIG_LIST_CHECK, False, str(failure)), []
    return CheckResult(CONFIG_LIST_CHECK, True, f"listed {len(stubs)} request attribute(s)"), stubs


def _config_body_check(config_reader: ConfigReader, stubs: list[AttributeStub]) -> CheckResult:
    """One body read, because listing an attribute does not prove the body can be read.

    Nothing in a run works without it: the stub carries no `enabled` and no data source, so a
    token that lists and cannot read is a token that finds every attribute and can classify none.
    """
    if not stubs:
        # The grant is unproven and there is nothing to prove it on, which is not a refusal.
        return CheckResult(CONFIG_BODY_CHECK, True, "no request attribute on this tenant to read")
    try:
        body = config_reader.read_body(stubs[0].id)
    except Exception as failure:  # pylint: disable=broad-exception-caught
        return CheckResult(CONFIG_BODY_CHECK, False, str(failure))
    return CheckResult(CONFIG_BODY_CHECK, True, f"read {len(body)} field(s) of {stubs[0].id}")


def _query_check(name: str, query_runner: QueryRunner, query: str) -> CheckResult:
    try:
        records = query_runner.execute(query)
    except Exception as failure:  # pylint: disable=broad-exception-caught
        return CheckResult(name, False, str(failure))
    return CheckResult(name, True, f"read {len(records)} row(s)")
