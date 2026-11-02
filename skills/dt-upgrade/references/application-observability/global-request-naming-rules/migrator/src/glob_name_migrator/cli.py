"""CLI entrypoint.

Commands:
  - ``list-rules`` — list all global request naming rules via Config v1.
  - ``dql-smoke`` — execute a trivial DQL query end-to-end (connectivity check).
  - ``run`` — full migration pipeline: fetch rules, query live span/entity data,
    find replacement candidates, verify with overselect check, emit per-rule
    reports and an HTML summary.  Read-only — never modifies the tenant.
  - ``apply`` — upload disabled replacement rules above each original, based on a
    completed ``run`` workdir.  POSTs each replacement as a disabled rule directly
    above its original in the global evaluation order, then reorders.  Originals
    are never modified.

Common flags (all commands):
  --tenant URL            Preferred. Classic or platform tenant URL; the other is
                          derived automatically via the ``.apps.`` naming convention.
  --classic-url URL       Specialist override for the classic API base URL (Config v1).
                          Prefer --tenant. If set alone, the platform URL is still
                          derived from it via ``.apps``, so pass a matching non-.apps
                          classic host; set BOTH overrides to bypass derivation entirely
                          (needed only for non-standard hostnames).
  --platform-url URL      Specialist override for the platform API base URL (DQL).
                          Same caveats as --classic-url (pass the ``.apps`` platform host).
  --platform-token TOKEN  dt0s16.* token with ReadConfig + storage:*:read scopes.
                          ``apply`` additionally requires WriteConfig.
  --output-dir DIR        Working directory (default: ./workdir/run-<UTC timestamp>).

``run``-only flags:
  --rule-ids ID [ID ...]  Process only these rule IDs (default: all rules).
  --query-timeframe STR   DQL time window for both span and entity queries,
                          e.g. ``from:now()-2h, to:now()`` (default).
                          Entity queries filter by entity lifetime overlap with
                          this window; span queries use it as the fetch range.

``apply``-only flags:
  --run-dir DIR           Path to a completed run workdir (required).
  --rule-ids ID [ID ...]  Apply only these rule IDs (default: all with a replacement).
"""

from __future__ import annotations

import argparse
import sys

from pathlib import Path

from . import __version__
from .clients.config_v1 import ConfigV1Client
from .clients.dql import DqlClient
from .config import AppConfig, ConfigError, from_cli_and_env
from .orchestrator import run as orchestrator_run
from .upload_replacements import ApplyReorderError, apply_rules


def main(argv: list[str] | None = None) -> int:
    """Parse argv, resolve config, dispatch to the appropriate subcommand."""
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

    dispatch = {
        "list-rules": lambda: _cmd_list_rules(cfg),
        "dql-smoke": lambda: _cmd_dql_smoke(cfg, args.query),
        "run": lambda: _cmd_run(cfg),
        "apply": lambda: _cmd_apply(cfg, args),
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    try:
        return handler()
    except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="glob-name-migrator",
        description="Migrate global request naming rules off Phase-3 deprecated conditions.",
    )
    parser.add_argument("--version", action="version", version=__version__)

    sub = parser.add_subparsers(dest="command")

    for name, help_ in (
        ("list-rules", "List all global request naming rule stubs."),
        ("dql-smoke", "Execute a trivial DQL query end-to-end."),
        ("run", "Run the full migration pipeline."),
        ("apply", "Upload disabled replacement rules above each original."),
    ):
        sp = sub.add_parser(name, help=help_)
        _add_common_flags(sp)
        if name == "dql-smoke":
            sp.add_argument(
                "--query",
                default="fetch dt.entity.service | fields id | limit 1",
                help="DQL to execute (default: trivial entity probe).",
            )
        if name == "run":
            sp.add_argument(
                "--rule-ids",
                nargs="+",
                metavar="ID",
                help="Process only these rule IDs (default: all rules).",
            )
            sp.add_argument(
                "--query-timeframe",
                default=None,
                help=(
                    "DQL time window for span and entity queries, e.g. 'from:now()-2h, to:now()'. "
                    "Defaults to 'from:now()-2h, to:now()'."
                ),
            )
        if name == "apply":
            sp.add_argument(
                "--run-dir",
                required=True,
                metavar="DIR",
                help="Path to a completed run workdir (must contain report/summary.json).",
            )
            sp.add_argument(
                "--rule-ids",
                nargs="+",
                metavar="ID",
                help="Apply only these rule IDs (default: all rules with a replacement).",
            )

    return parser


def _add_common_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--tenant",
        help=(
            "Preferred input. Tenant URL (either classic or platform host). "
            "The migrator derives the other from the standard ``.apps`` naming."
        ),
    )
    sp.add_argument(
        "--classic-url",
        help="Specialist override for the classic API base URL (Config v1). "
             "Prefer --tenant. If set alone, the platform URL is still derived via "
             "``.apps``; set both overrides to bypass derivation for non-standard hosts.",
    )
    sp.add_argument(
        "--platform-url",
        help="Specialist override for the platform API base URL (DQL). "
             "Prefer --tenant. If set alone, the classic URL is still derived via "
             "``.apps``; set both overrides to bypass derivation for non-standard hosts.",
    )
    sp.add_argument(
        "--platform-token",
        help="dt0s16.* token with ReadConfig + storage:*:read scopes (used for both APIs).",
    )
    sp.add_argument(
        "--output-dir",
        help="Output directory (default: ./workdir/run-<UTC timestamp>).",
    )


def _resolve_config(args: argparse.Namespace) -> AppConfig:
    return from_cli_and_env(
        tenant=getattr(args, "tenant", None),
        classic_url=getattr(args, "classic_url", None),
        platform_url=getattr(args, "platform_url", None),
        platform_token=getattr(args, "platform_token", None),
        output_dir=getattr(args, "output_dir", None),
        rule_ids=getattr(args, "rule_ids", None),
        query_timeframe=getattr(args, "query_timeframe", None),
    )


def _cmd_list_rules(cfg: AppConfig) -> int:
    client = ConfigV1Client(tenant_url=cfg.classic_url, api_token=cfg.platform_token)
    stubs = client.list_rules()
    print(f"found {len(stubs)} rule(s):")
    for stub in stubs:
        print(f"  {stub.id}\t{stub.name or '<no name>'}")
    return 0


def _cmd_dql_smoke(cfg: AppConfig, query: str) -> int:
    token = cfg.platform_token
    dql = DqlClient(tenant_url=cfg.platform_url, bearer_token_provider=lambda: token)
    rows = dql.execute(query)
    print(f"query returned {len(rows)} row(s).")
    if rows:
        print(f"first row keys: {sorted(rows[0].keys())}")
    return 0


def _cmd_run(cfg: AppConfig) -> int:
    token = cfg.platform_token
    dql = DqlClient(
        tenant_url=cfg.platform_url,
        bearer_token_provider=lambda: token,
    )
    summary = orchestrator_run(cfg, dql=dql)
    print(f"workdir: {summary['output_dir']}")
    print(f"inspected {summary['inspected_rules']} rule(s); "
          f"{summary['skipped_no_deprecated']} had no deprecated conditions (skipped); "
          f"{summary['migrating_rules']} sent through the migrator")
    print(f"case counts (migrating only): {summary['case_counts']}")
    print(f"translation status: {summary['translation_status']}")
    print(f"dql_queries: {summary['dql_queries']}")
    print(f"candidate_scoring: {summary['candidate_scoring']}")
    print(f"verification: {summary['verification']}")
    print(f"report_generation: {summary['report_generation']}")
    return 0


def _cmd_apply(cfg: AppConfig, args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir).expanduser().resolve()
    if not (run_dir / "report" / "summary.json").exists():
        print(f"error: {run_dir}/report/summary.json not found", file=sys.stderr)
        return 2

    client = ConfigV1Client(tenant_url=cfg.classic_url, api_token=cfg.platform_token)
    try:
        results = apply_rules(
            run_dir=run_dir,
            client=client,
            dry_run=False,
            rule_ids=getattr(args, "rule_ids", None),
        )
    except ApplyReorderError as exc:
        print(f"warning: {exc}", file=sys.stderr)
        print("posted rule IDs that need manual reordering:", file=sys.stderr)
        for new_id, orig_id in exc.posted:
            print(f"  new={new_id}  original={orig_id}", file=sys.stderr)
        return 1

    for r in results:
        tag = f"[{r.status.upper()}]"
        extra = r.new_rule_id or r.skip_reason or r.error or ""
        print(f"  {tag} {r.rule_id}  ->  {extra}  {r.naming_pattern or ''}".rstrip())

    counts = {s: sum(1 for r in results if r.status == s)
              for s in ("applied", "skipped", "failed")}
    print(f"\napplied={counts['applied']} skipped={counts['skipped']} failed={counts['failed']}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
