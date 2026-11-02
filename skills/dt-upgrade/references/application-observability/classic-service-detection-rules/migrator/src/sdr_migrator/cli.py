from __future__ import annotations

import argparse
import sys

from . import __version__
from .cache import CachingDqlClient
from .clients.config_v1 import ConfigV1Client
from .clients.dql import DqlClient
from .config import AppConfig, ConfigError, from_cli_and_env
from .orchestrator import VERDICTS, run_migration
from .report_builder import emit_results


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 2

    try:
        cfg = _resolve_config(args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    _handlers = {
        "dql-smoke": lambda: _cmd_dql_smoke(cfg, args.query),
        "list-rules": lambda: _cmd_list_rules(cfg),
        "run": lambda: _cmd_run(cfg, getattr(args, "window", "now()-2h")),
    }
    handler = _handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    try:
        return handler()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdr-migrator",
        description="Migrate classic service detection rules off Phase-3 deprecated conditions.",
    )
    parser.add_argument("--version", action="version", version=__version__)

    sub = parser.add_subparsers(dest="command")

    lr = sub.add_parser("list-rules", help="List all FULL_WEB_REQUEST and FULL_WEB_SERVICE rules.")
    _add_common_flags(lr)

    smoke = sub.add_parser("dql-smoke", help="Execute a trivial DQL query end-to-end (connectivity check).")
    _add_common_flags(smoke)
    smoke.add_argument(
        "--query",
        default="fetch dt.entity.process_group | fields id | limit 1",
        help="DQL to execute (default: trivial process_group probe).",
    )

    run = sub.add_parser("run", help="Migrate qualifying rules and emit replacement JSON.")
    _add_common_flags(run)
    run.add_argument(
        "--window",
        default="now()-2h",
        help="DQL lookback window for span queries (default: now()-2h).",
    )
    run.add_argument(
        "--rule-ids",
        nargs="+",
        metavar="ID",
        help="Process only these rule IDs (default: all rules).",
    )

    return parser


def _add_common_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--tenant", help="Tenant URL (classic or platform host).")
    sp.add_argument("--classic-url", help="Override classic API base URL.")
    sp.add_argument("--platform-url", help="Override platform API base URL.")
    sp.add_argument("--platform-token", help="dt0s16.* token with ReadConfig + storage:*:read scopes.")
    sp.add_argument("--classic-token", help="dt0c01.* token for the classic Config v1 API.")
    sp.add_argument("--output-dir", help="Output directory (default: ./workdir/run-<UTC timestamp>).")


def _resolve_config(args: argparse.Namespace) -> AppConfig:
    return from_cli_and_env(
        tenant=getattr(args, "tenant", None),
        classic_url=getattr(args, "classic_url", None),
        platform_url=getattr(args, "platform_url", None),
        platform_token=getattr(args, "platform_token", None),
        classic_token=getattr(args, "classic_token", None),
        output_dir=getattr(args, "output_dir", None),
        rule_ids=getattr(args, "rule_ids", None),
    )


def _cmd_list_rules(cfg: AppConfig) -> int:
    client = ConfigV1Client(classic_url=cfg.classic_url, api_token=cfg.classic_token)
    rules = client.list_all_rules()
    print(f"{'ID':<50} {'TYPE':<22} NAME")
    print("-" * 100)
    for rule in rules:
        print(f"{rule.id:<50} {rule.rule_type:<22} {rule.name or ''}")
    print(f"\n{len(rules)} rule(s) total.")
    return 0


def _cmd_run(cfg: AppConfig, window: str) -> int:
    token = cfg.platform_token
    config_client = ConfigV1Client(classic_url=cfg.classic_url, api_token=cfg.classic_token)
    dql_client = DqlClient(tenant_url=cfg.platform_url, bearer_token_provider=lambda: token)
    output_dir = cfg.output_dir
    caching_dql = CachingDqlClient(dql_client, cache_dir=output_dir / "cache")

    outcome = run_migration(config_client=config_client, dql_client=caching_dql, window=window, rule_ids=cfg.rule_ids)
    results = outcome.results

    if outcome.unknown_rule_ids:
        print(
            f"warning: {len(outcome.unknown_rule_ids)} requested rule id(s) not found: "
            + ", ".join(outcome.unknown_rule_ids),
            file=sys.stderr,
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    emit_results(
        results, output_dir,
        unknown_rule_ids=outcome.unknown_rule_ids or None,
        cache_stats=caching_dql.stats,
    )
    print(f"Report written to {output_dir / 'report' / 'report.html'}")

    verdict_order = list(VERDICTS)
    by_verdict: dict[str, list] = {v: [] for v in verdict_order}
    for r in results:
        by_verdict.setdefault(r.verdict, []).append(r)

    print(f"\n{'RULE ID':<50} {'TYPE':<22} VERDICT")
    print("-" * 100)
    for verdict in verdict_order:
        for r in by_verdict.get(verdict, []):
            detail = f"  [{'; '.join(r.reasons)}]" if r.reasons else ""
            print(f"{r.rule_id:<50} {r.rule_type:<22} {r.verdict}{detail}")

    print(f"\nTotal: {len(results)}")
    for verdict in verdict_order:
        count = len(by_verdict.get(verdict, []))
        if count:
            print(f"  {verdict}: {count}")
    return 0


def _cmd_dql_smoke(cfg: AppConfig, query: str) -> int:
    token = cfg.platform_token
    dql = DqlClient(tenant_url=cfg.platform_url, bearer_token_provider=lambda: token)
    rows = dql.execute(query)
    print(f"query returned {len(rows)} row(s).")
    if rows:
        print(f"first row keys: {sorted(rows[0].keys())}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
