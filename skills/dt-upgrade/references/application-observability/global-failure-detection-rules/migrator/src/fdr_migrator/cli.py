from __future__ import annotations

import argparse
import sys
from pathlib import Path
from collections.abc import Callable, Sequence
from typing import Protocol

from . import __version__
from .cache import AnsweringQueryRunner
from .checks import CheckResult, QueryRunner, SettingsReader, run_connection_checks
from .clients.dql import DqlClient
from .clients.settings import SettingsClient
from .config import AppConfig, ConfigError, build_config
from .dql.windowing import DEFAULT_QUERY_WINDOW, QueryWindow, QueryWindowError, parse_query_window
from .migrator import run_migration
from .reporting.outcomes import BucketedRule, Outcome, bucket_counts, bucket_rules
from .run_result import RunResult
from .workdir import DEFAULT_OUTPUT

class DqlReader(QueryRunner, AnsweringQueryRunner, Protocol):
    """Both readings of one client: the connection checks want rows, a run wants completeness too."""


ClientPair = tuple[SettingsReader, DqlReader]
ClientFactory = Callable[[AppConfig], ClientPair]


def build_clients(config: AppConfig) -> tuple[SettingsClient, DqlClient]:
    return (
        SettingsClient(platform_url=config.platform_url, platform_token=config.platform_token),
        DqlClient(platform_url=config.platform_url, platform_token=config.platform_token),
    )


def main(argv: list[str] | None = None, *, client_factory: ClientFactory = build_clients) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2

    try:
        config = build_config(tenant=args.tenant)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    settings_client, dql_client = client_factory(config)
    if args.command == "check-connection":
        results = run_connection_checks(config, settings_client=settings_client, dql_client=dql_client)
        _print_checks(results)
        return 0 if all(r.ok for r in results) else 1
    if args.command == "run":
        try:
            window = parse_query_window(args.window)
        except QueryWindowError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return _run(
            settings_client,
            dql_client,
            config=config,
            window=window,
            output=Path(args.output),
            rule_ids=args.rule_ids,
        )
    return 0


def _run(
    settings_client: SettingsReader,
    dql_client: DqlReader,
    *,
    config: AppConfig,
    window: QueryWindow,
    output: Path,
    rule_ids: Sequence[str] | None,
) -> int:
    try:
        result = run_migration(
            settings_client,
            dql_client,
            platform_url=config.platform_url,
            window=window,
            output=output,
            rule_ids=rule_ids,
        )
    except Exception as failure:  # pylint: disable=broad-exception-caught
        # Everything a single rule can lose is already that rule's own outcome, so anything
        # arriving here ended the pass itself and left no report to read. A stack trace is not an
        # answer to that, and the text is redacted because an upstream may echo the credential
        # back in an error it raised.
        print(f"error: {config.platform_token.redact(str(failure))}", file=sys.stderr)
        return 2
    _warn_unmatched(result)
    bucketed = bucket_rules(result)
    _print_outcome(result, bucketed)
    return _status(bucketed)


def _status(bucketed: Sequence[BucketedRule]) -> int:
    """What the run is worth to whatever called it, and which rules that verdict is about.

    Read off the buckets rather than off classification: a rule the run could not finish is a
    rule the run could not finish whichever stage lost it, and one that failed while being
    measured is invisible to a check that only counts unreadable configuration. A rule left
    without a verdict is deliberately not counted here - a read that came back short is a
    measurement that did not conclude, not a fault in the tool.
    """
    unfinished = [entry for entry in bucketed if entry.outcome is Outcome.UNPROCESSABLE]
    if not unfinished:
        return 0
    print(
        "error: this run could not finish "
        + ", ".join(entry.rule.name or entry.rule.object_id for entry in unfinished),
        file=sys.stderr,
    )
    return 1


def _warn_unmatched(result: RunResult) -> None:
    """Say which requested rules the tenant does not hold, rather than quietly reworking fewer."""
    if result.unmatched_rule_ids:
        print(
            "warning: no rule on this tenant has "
            + ", ".join(result.unmatched_rule_ids)
            + " - those ids were not reworked",
            file=sys.stderr,
        )
    if result.requested_not_affected:
        print(
            "warning: "
            + ", ".join(result.requested_not_affected)
            + " is disabled or carries no deprecated condition, so there was nothing to rework",
            file=sys.stderr,
        )


def _print_outcome(result: RunResult, bucketed: Sequence[BucketedRule]) -> None:
    """The report and how the affected rules came out, which is the whole of what a run says."""
    print(f"\nReport: {result.report_path}")
    # What was measured, beside where the answer is: what a rule targets is only true of the
    # stretch of time it was read over, and a caller comparing two runs needs to see which.
    print(f"Window: {result.window.expression} ({result.window.timeframe})")
    for outcome, count in bucket_counts(bucketed).items():
        print(f"  {count:>4}  {outcome}")


def _print_checks(results: list[CheckResult]) -> None:
    for result in results:
        print(f"[{'ok' if result.ok else 'FAIL'}] {result.name}: {result.detail}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fdr-migrator",
        description="Rework Global Failure Detection Rules off Phase 3 deprecated conditions.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    _add_common_flags(sub.add_parser("check-connection", help="Verify a run can work before attempting one."))
    run_parser = sub.add_parser(
        "run", help="Rework the rules Phase 3 stops evaluating on this tenant."
    )
    _add_common_flags(run_parser)
    run_parser.add_argument(
        "--window",
        default=DEFAULT_QUERY_WINDOW,
        help=(
            "How far back the query window reaches, as a whole number and a unit - m, h or d "
            f"(default: {DEFAULT_QUERY_WINDOW})."
        ),
    )
    run_parser.add_argument(
        "--rule-ids",
        nargs="+",
        metavar="ID",
        help=(
            "Rework only the rules with these object ids, as shown in a previous run's report "
            "(default: every affected rule)."
        ),
    )
    run_parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Where to put this run's own directory (default: {DEFAULT_OUTPUT}).",
    )
    return parser


def _add_common_flags(sub: argparse.ArgumentParser) -> None:
    # Deliberately no token flag: the credential comes from DT_PLATFORM_TOKEN only. A command-line
    # token is readable from the process list by any local user and lands in shell history; the
    # environment is owner-only.
    sub.add_argument(
        "--tenant",
        help="Tenant URL, classic or platform host (env: DT_TENANT).",
    )
