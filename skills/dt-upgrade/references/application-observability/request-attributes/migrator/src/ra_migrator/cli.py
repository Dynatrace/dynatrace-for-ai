from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from . import __version__
from .attributes.tags import Tag
from .checks import CheckResult, run_connection_checks
from .clients.config_v1 import ConfigV1Client
from .clients.dql import DqlClient
from .clients.transports import ConfigReader, QueryRunner
from .config import AppConfig, ConfigError, build_config
from .dql.windowing import DEFAULT_QUERY_WINDOW, QueryWindowError, parse_query_window
from .migrator import run_migration
from .reconstruction.candidate_search import CandidateAssessment
from .reconstruction.harvest import PrimaryTags
from .run_result import RunResult
from .workdir import DEFAULT_OUTPUT

ClientPair = tuple[ConfigReader, QueryRunner]
ClientFactory = Callable[[AppConfig], ClientPair]


def build_clients(config: AppConfig) -> ClientPair:
    return (
        ConfigV1Client(classic_url=config.classic_url, platform_token=config.platform_token),
        DqlClient(platform_url=config.platform_url, platform_token=config.platform_token),
    )


def main(argv: list[str] | None = None, *, client_factory: ClientFactory = build_clients) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    try:
        config = build_config(
            tenant=args.tenant, classic_url=args.classic_url, platform_url=args.platform_url
        )
        window = parse_query_window(args.window)
    except (ConfigError, QueryWindowError) as failure:
        print(f"error: {failure}", file=sys.stderr)
        return 2

    config_reader, query_runner = client_factory(config)
    if args.command == "check-connection":
        results = run_connection_checks(config_reader, query_runner, window=window)
        _print_checks(config, results)
        return 0 if all(result.ok for result in results) else 1
    if args.command == "run-migration":
        try:
            result = run_migration(
                config_reader,
                query_runner,
                platform_url=config.platform_url,
                window=window,
                output=Path(args.output_dir),
            )
        except Exception as failure:  # pylint: disable=broad-exception-caught
            # A stack trace is not an answer, and the text is redacted because an upstream may
            # have echoed the credential back in the error it raised.
            print(f"error: {config.platform_token.redact(str(failure))}", file=sys.stderr)
            return 2
        _print_attributes(result)
        return 0
    return 0


def _print_attributes(result: RunResult) -> None:
    """What the run read, as the run counted it - nothing here recomputes anything.

    The figures describe this pass over the configuration and nothing wider: each one says how
    much of what was scanned reached the next step.
    """
    print(f"Scanned: {result.scanned} request attribute(s)")
    print(f"Enabled: {result.enabled}")
    print(f"Of those enabled, obsolete: {result.obsolete}")
    print(f"Of the remainder, affected: {result.affected}")
    for reason, count in result.affected_by_reason.items():
        print(f"  {reason}: {count}")
    print(f"Disabled and carrying a deprecated condition: {result.disabled_carrying_deprecated}")
    print(f"Unprocessable: {result.unprocessable}")
    print(f"Window: {result.window.expression} ({result.window.timeframe})")
    print(f"Workdir: {result.workdir}")
    for one in result.classifications:
        print(f"  {one.id}  {one.name}  [{one.verdict}]")
    _print_resolutions(result)
    _print_harvests(result)
    _print_assessed_candidates(result)


def _print_resolutions(result: RunResult) -> None:
    """Interim output, and the only way to watch resolution work before the report exists.

    Per data source: the shape its scope decided, how big the set came out, what is known about
    its host groups, and which of the terminal cases it reached. Removed once the report renders
    the same story properly.
    """
    if not result.resolutions:
        return
    print(f"Resolved: {len(result.resolutions)} affected data source(s)")
    for one in result.resolutions:
        shape = "process-group" if one.shape.name == "PROCESS_GROUP" else "service"
        line = f"  {one.attribute_id}#{one.data_source_index}  {shape}-shaped"
        line += f"  target set: {len(one.target_set)}"
        if one.superset:
            line += " (superset)"
        members = one.host_groups.members
        if members is not None:
            sizes = ", ".join(f"{group}={len(held)}" for group, held in members.items())
            line += f"  host group membership: {sizes or 'none'}"
        if one.outcome is not None:
            line += f"  [{one.outcome}: {one.reason}]"
            if one.detail:
                line += f" {one.detail}"
        print(line)


def _print_harvests(result: RunResult) -> None:
    """Interim output, and the only way to watch the harvest work before the report exists.

    Per data source: what each axis yielded, what the primary tag axis cost, and the two figures
    that are unknown rather than zero where the read that would have measured them was not spent.
    Removed once the report renders the same story properly.
    """
    if not result.harvests:
        return
    print(f"Harvested: {len(result.harvests)} data source(s)")
    for one in result.harvests:
        line = f"  {one.attribute_id}#{one.data_source_index}"
        line += f"  process groups: {len(one.process_groups.ids)}"
        membership = one.host_groups.membership
        if membership is not None:
            held = sum(len(members) for members in membership.values())
            line += f"  host group membership: {held}"
        if one.service_closure.services:
            line += f"  service closure: {len(one.service_closure.services)}"
        line += f"  primary tags: {_primary_tags_of(one.primary_tags)}"
        if one.target_spans is not None:
            line += f"  entry-point spans: {one.target_spans}"
        if one.dormant:
            line += f"  dormant: {len(one.dormant)}"
        print(line)


def _print_assessed_candidates(result: RunResult) -> None:
    """Interim output, and the only way to see this layer work before the report exists.

    Per data source: the conjunction as assembled, each drop with its code, and which data sources
    still require observation. Removed once the report renders the same story properly.
    """
    if not result.assessed_candidates:
        return
    print(f"Assessed: {len(result.assessed_candidates)} data source(s)")
    for one in result.assessed_candidates:
        line = f"  {one.attribute_id}#{one.data_source_index}  {_candidate_of(one)}"
        if one.drops:
            line += "  dropped: " + ", ".join(
                f"{drop.axis} ({drop.reason})" for drop in one.drops
            )
        print(line)


def _candidate_of(one: CandidateAssessment) -> str:
    """What one data source's determination came to, said as the rung and what it will cost."""
    if one.condition_dropped:
        return "condition dropped, no observation"
    candidate = one.candidate
    if candidate is None:
        return "no candidate"
    parts: list[str] = []
    if candidate.fan_out:
        parts.append(f"fan-out over {len(candidate.fan_out)} process group(s)")
    if candidate.host_group is not None:
        parts.append(f"host group {candidate.host_group}")
    if candidate.primary_tag:
        parts.append(_tag_of(candidate.primary_tag))
    conjunction = " and ".join(parts) or "surviving conditions"
    if candidate.needs_observation:
        return f"{conjunction}  [needs observation]"
    return f"{conjunction}  [exact by {candidate.proof}, no observation]"


def _tag_of(tags: tuple[Tag, ...]) -> str:
    """The Primary Tag rung, said as its key and whether it is key-only or a value fan-out."""
    key = tags[0].key
    if tags[0].value is None:
        return f"primary tag {key} (key-only)"
    return f"primary tag {key} ({len(tags)} value(s))"


def _primary_tags_of(harvested: PrimaryTags) -> str:
    """What the one axis that costs a read came to, said as what it cost and what it yielded."""
    if harvested.gated is not None:
        return f"not asked ({harvested.gated})"
    if harvested.dropped is not None:
        return f"dropped ({harvested.dropped})"
    candidates = sum(1 for key in harvested.keys if key.dropped is None)
    return f"{candidates} of {len(harvested.keys)} key(s)"


def _print_checks(config: AppConfig, results: list[CheckResult]) -> None:
    print(f"Credential: platform token {config.platform_token}")
    print(f"Hosts: {config.classic_url} (config), {config.platform_url} (queries)")
    for result in results:
        print(f"[{'ok' if result.ok else 'FAIL'}] {result.name}: {result.detail}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ra-migrator",
        description="Rework request attributes off Phase 3 deprecated conditions.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    _add_common_flags(
        sub.add_parser("check-connection", help="Verify a run can work before attempting one.")
    )
    listing = sub.add_parser(
        "run-migration", help="Run the migrator. Will produce replacement artifacts, an HTML report and a json summary in the workdir."
    )
    _add_common_flags(listing)
    listing.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT),
        help=f"Where to put this run's own directory (default: {DEFAULT_OUTPUT}).",
    )
    return parser


def _add_common_flags(sub: argparse.ArgumentParser) -> None:
    # Deliberately no token flag: the credential comes from DT_PLATFORM_TOKEN only. A
    # command-line token is readable from the process list by any local user and lands in shell
    # history, while the environment of a process is owner-only.
    sub.add_argument("--tenant", help="Tenant URL, classic or platform host (env: DT_TENANT).")
    sub.add_argument(
        "--classic-url", help="Classic host, overriding derivation (env: DT_CLASSIC_URL)."
    )
    sub.add_argument(
        "--platform-url", help="Platform host, overriding derivation (env: DT_PLATFORM_URL)."
    )
    sub.add_argument(
        "--window",
        default=DEFAULT_QUERY_WINDOW,
        help=(
            "How far back the query window reaches, as a whole number and a unit - m, h or d "
            f"(default: {DEFAULT_QUERY_WINDOW})."
        ),
    )
